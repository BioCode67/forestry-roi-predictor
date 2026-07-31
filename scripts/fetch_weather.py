#!/usr/bin/env python3
"""
기상청 지상관측 자료 수집 → data/weather/weather_daily.csv, weather_annual.csv

사용
    export KMA_AUTH_KEY=...
    python scripts/fetch_weather.py --start 2019 --end 2024

동작
    ① 「지상관측 일자료」(kma_sfcdd3.php)가 활용신청되어 있으면 기간 조회로 한 번에 받는다.
    ② 아직 신청 전이면 「시간자료」(kma_sfctm2.php)를 하루 몇 시각만 표본 추출해 집계한다.
       시간자료는 tm 단일 시각만 받지만 stn=0으로 전국 지점이 한 번에 오고,
       RN_DAY가 '해당 시각까지의 일강수량 누적'이라 하루 마지막 관측이 곧 그날 총 강수량이다.

산출 컬럼 (연·지점 집계)
    지점 · 연도 · 평균기온 · 최저기온 · 최고기온 · 연강수량 · 생육기(4~10월)평균기온
    · 생육기강수량 · 서리일수(최저 0℃ 이하) · 폭염일수(최고 33℃ 이상)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from datetime import timedelta  # noqa: E402

from kma_client import KmaClient, daterange  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "weather")
OUT_DAILY = os.path.join(OUT_DIR, "weather_daily.csv")
OUT_ANNUAL = os.path.join(OUT_DIR, "weather_annual.csv")
OUT_STN = os.path.join(OUT_DIR, "stations.csv")

# 하루 표본 시각. 마지막 23시는 일강수량 누계를 확보하기 위해 반드시 포함한다.
SAMPLE_HOURS = ["0000", "0300", "0600", "0900", "1200", "1500", "1800", "2100", "2300"]

GROW_MONTHS = list(range(4, 11))   # 생육기 4~10월


def aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    """표본 시각 관측 → 지점·일자 단위 집계."""
    g = df.groupby(["STN", "일자"], observed=True)
    out = g.agg(
        평균기온=("TA", "mean"),
        최저기온=("TA", "min"),
        최고기온=("TA", "max"),
        일강수량=("RN_DAY", "max"),      # 누계이므로 최댓값이 그날 총량
        평균습도=("HM", "mean"),
        일조합=("SS", "sum"),
        평균지면온도=("TS", "mean"),
        관측횟수=("TA", "size"),
    ).reset_index()
    out["일강수량"] = out["일강수량"].fillna(0.0)
    return out


def to_annual(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    d["연도"] = d["일자"].dt.year
    d["월"] = d["일자"].dt.month
    grow = d[d["월"].isin(GROW_MONTHS)]

    agg = {
        "평균기온": ("평균기온", "mean"),
        "최저기온평균": ("최저기온", "mean"),
        "최고기온평균": ("최고기온", "mean"),
        "연강수량": ("일강수량", "sum"),
        "연일조시간": ("일조합", "sum"),
        "관측일수": ("일자", "nunique"),
    }
    for src, name in [("평균습도", "평균습도"), ("일사합", "연일사량"),
                      ("증발량", "연증발량"), ("안개시간", "연안개시간"),
                      ("지중온도_05m", "지중온도_05m")]:
        if src in d.columns:
            agg[name] = (src, "sum" if name.startswith("연") else "mean")
    base = d.groupby(["STN", "연도"], observed=True).agg(**agg)
    g = grow.groupby(["STN", "연도"], observed=True).agg(
        생육기평균기온=("평균기온", "mean"),
        생육기강수량=("일강수량", "sum"),
    )
    frost = (d[d["최저기온"] <= 0].groupby(["STN", "연도"], observed=True)
             .size().rename("서리일수"))
    # 초상최저기온은 지면 가까이의 온도라 실제 서리 피해와 더 직결된다
    if "초상최저기온" in d.columns:
        gfrost = (d[d["초상최저기온"] <= 0].groupby(["STN", "연도"], observed=True)
                  .size().rename("초상서리일수"))
    else:
        gfrost = pd.Series(dtype=int, name="초상서리일수")
    # 밤·감은 개화기(4~5월) 저온에 결실이 크게 좌우된다
    bloom = d[d["월"].isin([4, 5])]
    bloom_frost = (bloom[bloom["최저기온"] <= 2]
                   .groupby(["STN", "연도"], observed=True).size().rename("개화기저온일수"))
    heat = (d[d["최고기온"] >= 33].groupby(["STN", "연도"], observed=True)
            .size().rename("폭염일수"))
    rain = (d[d["일강수량"] >= 80].groupby(["STN", "연도"], observed=True)
            .size().rename("호우일수"))

    out = base.join([g, frost, gfrost, bloom_frost, heat, rain]).reset_index()
    for c in ["서리일수", "초상서리일수", "개화기저온일수", "폭염일수", "호우일수"]:
        out[c] = out[c].fillna(0).astype(int)
    return out


def collect_hourly(client: KmaClient, start: date, end: date) -> pd.DataFrame:
    total = (end - start).days + 1
    frames, fails = [], 0
    for i, d in enumerate(daterange(start, end), 1):
        day = d.strftime("%Y%m%d")
        for hh in SAMPLE_HOURS:
            try:
                df = client.hourly_all_stations(f"{day}{hh}")
                if not df.empty:
                    frames.append(df[["STN", "일자", "TA", "RN_DAY", "HM", "SS", "TS"]])
            except Exception:  # noqa: BLE001
                fails += 1
        if i % 60 == 0 or i == total:
            got = sum(len(f) for f in frames)
            print(f"  [{i:>5}/{total}] {day}  누적 {got:,}행  실패 {fails}", flush=True)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def collect_daily_api(client: KmaClient, start: date, end: date) -> pd.DataFrame:
    """일자료 API 경로. 전 지점 x 1년이면 응답이 커서 월 단위로 끊는다."""
    frames = []
    for y in range(start.year, end.year + 1):
        for mth in range(1, 13):
            s0 = date(y, mth, 1)
            e0 = date(y + (mth == 12), (mth % 12) + 1, 1) - timedelta(days=1)
            if e0 < start or s0 > end:
                continue
            s0, e0 = max(s0, start), min(e0, end)
            try:
                df = client.daily_range(s0.strftime("%Y%m%d"), e0.strftime("%Y%m%d"))
            except Exception as ex:  # noqa: BLE001
                print(f"  [fail] {y}-{mth:02d}: {ex}", flush=True)
                continue
            if not df.empty:
                frames.append(df)
        got = sum(len(f) for f in frames)
        print(f"  {y}년까지 누적 {got:,}행", flush=True)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def aggregate_daily_api(df: pd.DataFrame) -> pd.DataFrame:
    """일자료 원본 → 분석용 컬럼만 추린 일 단위 표."""
    keep = {
        "STN": "STN", "일자": "일자",
        "TA_AVG": "평균기온", "TA_MAX": "최고기온", "TA_MIN": "최저기온",
        "TG_MIN": "초상최저기온", "TS_AVG": "평균지면온도",
        "HM_AVG": "평균습도", "HM_MIN": "최저습도",
        "RN_DAY": "일강수량", "RN_DUR": "강수시간", "RN_60M_MAX": "시간최다강수",
        "SS_DAY": "일조합", "SI_DAY": "일사합", "EV_S": "증발량",
        "FG_DUR": "안개시간", "CA_TOT": "평균운량",
        "WS_AVG": "평균풍속", "WS_INS": "최대순간풍속", "SD_MAX": "최심적설",
        "TE_05": "지중온도_05m",
    }
    cols = [c for c in keep if c in df.columns]
    out = df[cols].rename(columns={k: v for k, v in keep.items() if k in cols}).copy()
    out["일강수량"] = out.get("일강수량", pd.Series(dtype=float)).fillna(0.0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auth-key", default=os.environ.get("KMA_AUTH_KEY"))
    ap.add_argument("--start", type=int, default=2019)
    ap.add_argument("--end", type=int, default=2024)
    a = ap.parse_args()

    try:
        client = KmaClient(a.auth_key)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    os.makedirs(OUT_DIR, exist_ok=True)

    try:
        stn = client.stations()
        stn.to_csv(OUT_STN, index=False, encoding="utf-8-sig")
        print(f"[지점정보] {len(stn)}개 → {OUT_STN}")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 지점정보 수집 실패: {e}", file=sys.stderr)

    start, end = date(a.start, 1, 1), date(a.end, 12, 31)

    has_daily = client.available(
        "kma_sfcdd3.php", {"tm1": "20230101", "tm2": "20230102", "stn": "108"})
    if has_daily:
        print("[경로] 지상관측 일자료 API (기간 조회) — 관측값을 그대로 받는다")
        raw = collect_daily_api(client, start, end)
        if raw.empty:
            print("수집 실패", file=sys.stderr)
            return 1
        daily = aggregate_daily_api(raw)
        daily.to_csv(OUT_DAILY, index=False, encoding="utf-8-sig")
        annual = to_annual(daily)
        annual.to_csv(OUT_ANNUAL, index=False, encoding="utf-8-sig")
        print(f"\n[saved] {OUT_DAILY}   {len(daily):,}행 (지점×일자)")
        print(f"[saved] {OUT_ANNUAL}  {len(annual):,}행 (지점×연도)")
        print("\n연도별 전국 평균:")
        cols = {"평균기온": ("평균기온", "mean"), "연강수량": ("연강수량", "mean"),
                "서리일수": ("서리일수", "mean"), "폭염일수": ("폭염일수", "mean"),
                "개화기저온일수": ("개화기저온일수", "mean"), "지점수": ("STN", "nunique")}
        print(annual.groupby("연도").agg(**cols).round(1).to_string())
        return 0

    print("[경로] 일자료 미신청 → 시간자료 표본 집계 "
          f"(하루 {len(SAMPLE_HOURS)}회, {(end - start).days + 1}일)")
    hourly = collect_hourly(client, start, end)
    if hourly.empty:
        print("수집된 자료가 없습니다.", file=sys.stderr)
        return 1

    daily = aggregate_daily(hourly)
    daily.to_csv(OUT_DAILY, index=False, encoding="utf-8-sig")
    annual = to_annual(daily)
    annual.to_csv(OUT_ANNUAL, index=False, encoding="utf-8-sig")

    print(f"\n[saved] {OUT_DAILY}   {len(daily):,}행 (지점×일자)")
    print(f"[saved] {OUT_ANNUAL}  {len(annual):,}행 (지점×연도)")
    print("\n연도별 전국 평균:")
    print(annual.groupby("연도").agg(
        평균기온=("평균기온", "mean"), 연강수량=("연강수량", "mean"),
        서리일수=("서리일수", "mean"), 폭염일수=("폭염일수", "mean"),
        지점수=("STN", "nunique")).round(1).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
