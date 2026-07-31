"""
Phase 2-I — 시군구 단위 지도 데이터 구축

임산물생산조사는 시·군·구 단위로 조사된다. 지금까지 분석은 시도 9개로 접어서
썼는데, 시군구를 살리면 두 가지가 열린다.

  ① 지도 시각화 — "우리 군 밤 단가가 전국에서 몇 번째인가"
  ② 기상 결합 재시도 — 관측지점 97개를 시군구에 붙이면 시도 9개보다 훨씬 촘촘하다

행정경계는 통계청 2013년 시군구 GeoJSON(southkorea-maps)을 쓴다. 광역시 자치구까지
쪼개져 있어 조사 자료의 시군 단위와 어긋나므로, 필요한 곳은 병합해 맞춘다.

산출: web/public/geo/sgg_merged.json, models/region_stats.json
"""
from __future__ import annotations

import glob
import json
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO_SRC = os.path.join(ROOT, "web", "public", "geo", "sgg.json")
GEO_OUT = os.path.join(ROOT, "web", "public", "geo", "sgg_merged.json")
PROD_DIR = os.path.join(ROOT, "data", "임산물생산조사")
OUT_JSON = os.path.join(ROOT, "models", "region_stats.json")

SIDO_FULL = {
    "강원도", "강원특별자치도", "경기도", "경상남도", "경상북도", "광주광역시", "대구광역시",
    "대전광역시", "부산광역시", "서울특별시", "세종특별자치시", "울산광역시", "인천광역시",
    "전라남도", "전라북도", "전북특별자치도", "제주특별자치도", "충청남도", "충청북도",
}
# 국유림 관리기관은 지자체가 아니라 지도에 올릴 수 없다
NON_LOCAL = {"국립산림과학원", "국립산림품종관리센터", "국립수목원",
             "남부지방산림청", "동부지방산림청", "북부지방산림청",
             "서부지방산림청", "중부지방산림청"}

# 조사 자료에서 광역시 자치구는 '광주광산구'처럼 시도명이 앞에 붙는다
METRO_PREFIX = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종"]

# 행정경계 코드 앞 2자리 = 시도. 동구·중구·북구처럼 여러 시도에 같은 이름이 있어
# 이름만으로 묶으면 서울 강서구와 부산 강서구가 한 덩어리가 된다. 실제로 그렇게
# 묶였을 때 무게중심이 두 지역 사이(구미 부근)로 잡혀 기상 결합이 어긋났다.
SIDO_BY_CODE = {
    "11": "서울", "21": "부산", "22": "대구", "23": "인천", "24": "광주",
    "25": "대전", "26": "울산", "29": "세종",
    "31": "경기", "32": "강원", "33": "충북", "34": "충남",
    "35": "전북", "36": "전남", "37": "경북", "38": "경남", "39": "제주",
}

# 지도에는 있으나 조사 자료에 없는 표기 차이를 직접 잇는다
ALIAS = {
    "창원시": "창원시", "청주시": "청주시", "천안시": "천안시",
    "부천시": "부천시", "세종시": "세종특별자치시",
}


# 시도 전체 명칭 → 짧은 이름
SIDO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산",
    "세종특별자치시": "세종", "경기도": "경기", "강원도": "강원", "강원특별자치도": "강원",
    "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북",
    "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
}


def norm_survey_name(raw: str, sido: str | None = None,
                     geo_names: set[str] | None = None) -> str | None:
    """조사 자료의 시군구 표기를 지도 이름 체계로 옮긴다.

    '동구'·'고성군'처럼 여러 시도에 같은 이름이 있는 경우가 있어, 조사 자료의
    시도 칼럼을 함께 받아 '부산 동구'로 갈라 준다. 지도 쪽에서 이름이 유일한
    시군구는 접두사 없이 쓰므로 두 표기를 모두 시도해 맞춘다.
    """
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or s in SIDO_FULL or s in NON_LOCAL:
        return None
    # '남부지방청(울릉군)' 처럼 괄호 안에 실제 지자체가 들어 있는 경우
    m = re.search(r"\(([^)]+)\)", s)
    if m:
        s = m.group(1).strip()
    # '광주광산구'처럼 시도가 앞에 붙어 온 경우 떼어 낸다
    for p in METRO_PREFIX:
        if s.startswith(p) and len(s) > len(p) + 1 and s != p and s[len(p):].endswith(("구", "군")):
            sido = sido or p
            s = s[len(p):]
            break

    short = SIDO_SHORT.get(str(sido).strip(), str(sido).strip() if sido else "")
    if geo_names is None:
        return f"{short} {s}" if short else s
    # 지도에 있는 표기를 우선한다
    if s in geo_names:
        return s
    if short and f"{short} {s}" in geo_names:
        return f"{short} {s}"
    return None


def merge_geo() -> dict:
    """자치구로 쪼개진 통합시를 시 단위로 병합한다.

    조사 자료는 '고양시'로 오는데 지도는 '고양시덕양구'처럼 나뉘어 있다.
    경계를 합치는 대신 같은 시에 속한 폴리곤을 MultiPolygon으로 묶는다.
    """
    gj = json.load(open(GEO_SRC, encoding="utf-8"))

    # 전국에서 이름이 겹치는 시군구를 먼저 찾는다
    counts: dict[str, int] = {}
    for f in gj["features"]:
        n = f["properties"]["name"]
        m = re.match(r"^(.+시)(?:[가-힣]+구)$", n)
        counts[m.group(1) if m else n] = counts.get(m.group(1) if m else n, 0) + 1

    buckets: dict[str, list] = {}
    for f in gj["features"]:
        name = f["properties"]["name"]
        code = str(f["properties"].get("code") or "")
        m = re.match(r"^(.+시)(?:[가-힣]+구)$", name)
        base = m.group(1) if m else name
        # 자치구가 여러 개인 통합시(고양시덕양구 등)는 합쳐야 하므로 중복이 아니다.
        # 그 외에 이름이 겹치면 시도를 앞에 붙여 갈라 놓는다.
        sido = SIDO_BY_CODE.get(code[:2], "")
        ambiguous = counts.get(base, 0) > 1 and m is None
        key = f"{sido} {base}" if (ambiguous and sido) else base
        buckets.setdefault(key, []).append(f)

    feats = []
    for key, group in buckets.items():
        if len(group) == 1:
            f = group[0]
            f["properties"] = {"name": key, "code": f["properties"].get("code")}
            feats.append(f)
            continue
        polys = []
        for f in group:
            g = f["geometry"]
            if g["type"] == "Polygon":
                polys.append(g["coordinates"])
            elif g["type"] == "MultiPolygon":
                polys.extend(g["coordinates"])
        feats.append({
            "type": "Feature",
            "properties": {"name": key, "code": group[0]["properties"].get("code")},
            "geometry": {"type": "MultiPolygon", "coordinates": polys},
        })
    return {"type": "FeatureCollection", "features": feats}


def load_production() -> pd.DataFrame:
    frames = []
    for f in sorted(glob.glob(os.path.join(PROD_DIR, "*.csv"))):
        year = int(os.path.basename(f)[:4])
        for enc in ("cp949", "euc-kr", "utf-8-sig"):
            try:
                d = pd.read_csv(f, encoding=enc)
                break
            except Exception:  # noqa: BLE001
                continue
        else:
            continue
        d["연도"] = year
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    for c in ["생산량", "단가", "생산금액"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[(df["생산량"] > 0) & (df["단가"] > 0) & (df["생산금액"] > 0)]

    geo_names = None
    if os.path.exists(GEO_OUT):
        geo_names = {f["properties"]["name"]
                     for f in json.load(open(GEO_OUT, encoding="utf-8"))["features"]}
    df["지역"] = [norm_survey_name(r, s, geo_names)
                 for r, s in zip(df["시군구"], df["시도/청"])]
    return df.dropna(subset=["지역"])


# 지도에 올릴 대표 품목
FOCUS = ["밤", "떫은감", "대추", "생표고", "건표고", "고사리", "더덕", "도라지", "호두", "잣"]
# 시군구x품목은 대개 연 1건으로 집계되므로 관측 수로는 거를 수 없다.
# 대신 생산량이 지나치게 적은 지역을 뺀다. 텃밭 수준 몇 kg이 최고 단가로 잡히면
# 지도가 통째로 오해를 부른다. 전국 생산량의 0.05%를 문턱으로 두되 하한을 함께 건다.
MIN_SHARE = 0.0005
MIN_QTY_KG = 1000


def build_stats(df: pd.DataFrame, geo_names: set[str]) -> dict:
    latest = df[df["연도"] == df["연도"].max()]
    out: dict = {}
    for item in FOCUS:
        g = latest[latest["소분류"] == item]
        if g.empty:
            continue
        agg = (g.groupby("지역", observed=True)
                 .agg(생산금액=("생산금액", "sum"), 생산량=("생산량", "sum"), 관측=("단가", "size")))
        total_qty = float(g["생산량"].sum())
        floor = max(total_qty * MIN_SHARE, MIN_QTY_KG)
        dropped = int((agg["생산량"] < floor).sum())
        agg = agg[agg["생산량"] >= floor]
        agg["단가"] = (agg["생산금액"] / agg["생산량"]).round(1)
        agg = agg[agg.index.isin(geo_names)]
        if len(agg) < 5:
            continue
        nat = float(g["생산금액"].sum() / g["생산량"].sum())
        rows = []
        for name, r in agg.sort_values("단가", ascending=False).iterrows():
            rows.append({
                "지역": name,
                "단가": float(r["단가"]),
                "전국대비_pct": round(float(r["단가"] / nat - 1) * 100, 1),
                "생산량": int(r["생산량"]),
                "생산금액": int(r["생산금액"]),
            })
        out[item] = {
            "연도": int(latest["연도"].iloc[0]),
            "전국단가": round(nat, 1),
            "지역수": len(rows),
            "생산량_문턱_kg": int(floor),
            "문턱미달_제외": dropped,
            "최고": rows[0], "최저": rows[-1],
            "격차_배": round(rows[0]["단가"] / rows[-1]["단가"], 2) if rows[-1]["단가"] else None,
            "지역": rows,
        }
    return out


def main() -> None:
    geo = merge_geo()
    geo_names = {f["properties"]["name"] for f in geo["features"]}
    json.dump(geo, open(GEO_OUT, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"[saved] {GEO_OUT}  {len(geo['features'])}개 시군구 "
          f"({os.path.getsize(GEO_OUT)//1024}KB)")

    df = load_production()
    survey = set(df["지역"].unique())
    hit = survey & geo_names
    print(f"[match] 조사 {len(survey)}개 중 {len(hit)}개 지도 매칭 "
          f"({len(hit)/len(survey)*100:.0f}%)")
    miss = sorted(survey - geo_names)
    if miss:
        print(f"        미매칭 {len(miss)}개: {miss[:10]}")

    stats = build_stats(df, geo_names)
    result = {
        "출처": "산림청 「임산물생산조사」 전품목 · 통계청 시군구 행정경계(2013)",
        "품목": list(stats),
        "통계": stats,
        "주의": "시군구×품목 관측이 적은 조합은 제외했다. 단가는 생산금액÷생산량(물량가중)이며, "
                "국유림 관리기관은 지자체가 아니라 지도에서 제외했다.",
    }
    json.dump(result, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[saved] {OUT_JSON}  품목 {len(stats)}종")
    for k, v in stats.items():
        print(f"  {k:6s} {v['지역수']:>3}개 지역 · 최고 {v['최고']['지역']} "
              f"{v['최고']['단가']:,.0f}원 / 최저 {v['최저']['지역']} {v['최저']['단가']:,.0f}원 "
              f"({v['격차_배']}배)")


if __name__ == "__main__":
    main()
