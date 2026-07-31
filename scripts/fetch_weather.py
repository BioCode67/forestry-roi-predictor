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

    base = d.groupby(["STN", "연도"], observed=True).agg(
        평균기온=("평균기온", "mean"),
        최저기온평균=("최저기온", "mean"),
        최고기온평균=("최고기온", "mean"),
        연강수량=("일강수량", "sum"),
        연일조시간=("일조합", "sum"),
        관측일수=("일자", "nunique"),
    )
    g = grow.groupby(["STN", "연도"], observed=True).agg(
        생육기평균기온=("평균기온", "mean"),
        생육기강수량=("일강수량", "sum"),
    )
    frost = (d[d["최저기온"] <= 0].groupby(["STN", "연도"], observed=True)
             .size().rename("서리일수"))
    heat = (d[d["최고기온"] >= 33].groupby(["STN", "연도"], observed=True)
            .size().rename("폭염일수"))
    rain = (d[d["일강수량"] >= 80].groupby(["STN", "연도"], observed=True)
            .size().rename("호우일수"))

    out = base.join([g, frost, heat, rain]).reset_index()
    for c in ["서리일수", "폭염일수", "호우일수"]:
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
    """일자료 API가 열려 있을 때의 경로 (연 단위로 끊어 요청)."""
    frames = []
    for y in range(start.year, end.year + 1):
        s = max(start, date(y, 1, 1)).strftime("%Y%m%d")
        e = min(end, date(y, 12, 31)).strftime("%Y%m%d")
        df = client.daily_range(s, e)
        if not df.empty:
            frames.append(df)
        print(f"  {y}: {len(df):,}행", flush=True)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


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
        print("[경로] 지상관측 일자료 API 사용 (기간 조회)")
        raw = collect_daily_api(client, start, end)
        raw.to_csv(os.path.join(OUT_DIR, "asos_daily_raw.csv"),
                   index=False, encoding="utf-8-sig")
        print(f"[saved] 원자료 {len(raw):,}행 — 컬럼 매핑은 파일을 확인해 후처리하세요.")
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
