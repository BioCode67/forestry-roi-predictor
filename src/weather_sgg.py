"""
Phase 2-J — 기상 자료를 시군구 단위로 재결합

앞선 시도(src/weather.py)는 임가경제조사의 지역 구분이 시도 9개뿐이라
기상이 시도×연도 54개 조합으로만 붙었고, 결국 지역 더미와 다를 바 없어
모델 성능이 오히려 내려갔다.

임산물생산조사는 시군구 단위다. 관측지점 97개를 시군구 200여 개에
**최근접 지점**으로 붙이면 해상도가 훨씬 올라간다. 지점이 없는 시군구도
거리로 이어지므로 결측 없이 전국을 덮는다.

한계는 그대로 남는다. 최근접 지점이 수십 km 떨어져 있거나 산을 사이에 두고
있으면 그 시군구의 실제 기상과 다를 수 있다. 거리와 고도차를 함께 기록해
어느 정도 믿을 값인지 판단할 수 있게 한다.

산출: data/weather/weather_sgg.csv, models/weather_region.json
"""
from __future__ import annotations

import json
import math
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W_DIR = os.path.join(ROOT, "data", "weather")
GEO = os.path.join(ROOT, "web", "public", "geo", "sgg_merged.json")
OUT_CSV = os.path.join(W_DIR, "weather_sgg.csv")
OUT_JSON = os.path.join(ROOT, "models", "weather_region.json")

WEATHER_COLS = [
    "평균기온", "최저기온평균", "최고기온평균", "연강수량", "연일조시간",
    "평균습도", "연일사량", "연증발량", "생육기평균기온", "생육기강수량",
    "서리일수", "초상서리일수", "개화기저온일수", "폭염일수", "호우일수",
]

MAX_ELEVATION_M = 700   # 고산 관측소는 주변 시군구를 대표하지 못한다
MIN_OBS_DAYS = 300


def centroids() -> pd.DataFrame:
    """시군구 경계의 무게중심. 폴리곤 꼭짓점 평균으로 충분하다."""
    gj = json.load(open(GEO, encoding="utf-8"))
    rows = []
    for f in gj["features"]:
        geom = f["geometry"]
        polys = ([geom["coordinates"]] if geom["type"] == "Polygon"
                 else geom["coordinates"])
        pts = [p for poly in polys for ring in poly for p in ring]
        if not pts:
            continue
        lon = sum(p[0] for p in pts) / len(pts)
        lat = sum(p[1] for p in pts) / len(pts)
        rows.append({"지역": f["properties"]["name"], "LON": lon, "LAT": lat})
    return pd.DataFrame(rows)


def haversine(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def build() -> pd.DataFrame:
    ann = pd.read_csv(os.path.join(W_DIR, "weather_annual.csv"))
    stn = pd.read_csv(os.path.join(W_DIR, "stations.csv"))[["STN", "STN_KO", "HT", "LON", "LAT"]]
    ann = ann.merge(stn, on="STN", how="left").dropna(subset=["LON", "LAT"])
    ann = ann[(ann["HT"] <= MAX_ELEVATION_M) & (ann["관측일수"] >= MIN_OBS_DAYS)]

    cen = centroids()
    pool = stn[(stn["HT"] <= MAX_ELEVATION_M)].dropna(subset=["LON", "LAT"])

    # 시군구마다 가장 가까운 관측지점을 찾는다
    link = []
    for _, c in cen.iterrows():
        d = pool.apply(
            lambda s: haversine(c["LAT"], c["LON"], s["LAT"], s["LON"]), axis=1)
        i = d.idxmin()
        link.append({
            "지역": c["지역"],
            "STN": int(pool.loc[i, "STN"]),
            "지점명": pool.loc[i, "STN_KO"],
            "거리_km": round(float(d.loc[i]), 1),
            "지점고도_m": round(float(pool.loc[i, "HT"]), 1),
        })
    link = pd.DataFrame(link)

    cols = [c for c in WEATHER_COLS if c in ann.columns]
    out = link.merge(ann[["STN", "연도"] + cols], on="STN", how="left")
    return out.dropna(subset=["연도"]).astype({"연도": int})


def main() -> None:
    df = build()
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    dist = df.drop_duplicates("지역")["거리_km"]
    summary = {
        "출처": "기상청 지상관측(ASOS) 일자료 2019~2024 · 최근접 관측지점 결합",
        "시군구": int(df["지역"].nunique()),
        "연도": [int(df["연도"].min()), int(df["연도"].max())],
        "관측지점": int(df["STN"].nunique()),
        "거리_km": {
            "중앙값": round(float(dist.median()), 1),
            "평균": round(float(dist.mean()), 1),
            "최대": round(float(dist.max()), 1),
            "30km_이내_비율_pct": round(float((dist <= 30).mean() * 100), 1),
        },
        "지표": [c for c in WEATHER_COLS if c in df.columns],
        "한계": "시군구 무게중심에서 가장 가까운 관측지점 값을 그대로 쓴다. "
                "지점이 멀거나 산을 사이에 둔 경우 실제 기상과 다를 수 있어 "
                "거리와 지점 고도를 함께 기록했다.",
    }
    json.dump(summary, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"[saved] {OUT_CSV}  {len(df):,}행 (시군구×연도)")
    print(f"시군구 {summary['시군구']}개 · 지점 {summary['관측지점']}개")
    print(f"연결 거리 중앙값 {summary['거리_km']['중앙값']}km · "
          f"30km 이내 {summary['거리_km']['30km_이내_비율_pct']}%  최대 {summary['거리_km']['최대']}km")
    far = df.drop_duplicates("지역").nlargest(5, "거리_km")[["지역", "지점명", "거리_km"]]
    print("\n가장 먼 연결:")
    print(far.to_string(index=False))


if __name__ == "__main__":
    main()
