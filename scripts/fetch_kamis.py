#!/usr/bin/env python3
"""
KAMIS(농수산물유통정보) 월별 도매가격 수집기 → data/kamis/kamis_monthly.csv

사용
    export KAMIS_CERT_KEY=...    # 발급받은 인증키
    export KAMIS_CERT_ID=...     # 가입 이메일
    python scripts/fetch_kamis.py

    # 품목 코드 표만 새로 탐색하고 싶을 때
    python scripts/fetch_kamis.py --discover

수집 대상에 관하여
------------------
KAMIS 일일 가격조사 대상은 63개 품목이며, 임산물 중 실제로 취급되는 것은
**단감·느타리버섯·새송이버섯·팽이버섯**뿐이다.
밤·대추·표고버섯·곶감·잣·고사리·도라지·더덕은 KAMIS 조사 대상이 아니다
(임산물 유통가격은 산림청 계열 시스템에서 별도 관리).
호두는 '수입(1kg)' 소매만 있어 국내 임가의 출하 의사결정에는 쓰지 않는다.

API 특성
--------
`periodProductList` 는 p_startday / p_endday 를 요청해도 이를 무시하고
**서버가 보유한 최근 구간(약 12~15개월)** 을 반환한다. 따라서 산출되는
월별 가격지수는 '최근 1개 순환주기 기준'이며, 이 사실을 산출물에 함께 기록한다.
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from kamis_client import KamisClient  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "kamis")
OUT = os.path.join(OUT_DIR, "kamis_monthly.csv")
OUT_DAILY = os.path.join(OUT_DIR, "kamis_daily.csv")
OUT_CODES = os.path.join(OUT_DIR, "kamis_item_codes.csv")

# (표시 품목명, 부류코드, 품목코드, 품종코드, 등급코드, 등급명)
TARGETS = [
    ("단감",       "400", "416", "00", "04", "상품"),
    ("단감",       "400", "416", "00", "05", "중품"),
    ("느타리버섯", "300", "315", "00", "04", "상품"),
    ("느타리버섯", "300", "315", "00", "05", "중품"),
    ("새송이버섯", "300", "317", "00", "04", "상품"),
    ("새송이버섯", "300", "317", "00", "05", "중품"),
    ("팽이버섯",   "300", "316", "00", "04", "상품"),
    ("팽이버섯",   "300", "316", "00", "05", "중품"),
]

DISCOVER_DAYS = ["2023-10-16", "2023-11-15", "2024-01-11", "2023-09-20",
                 "2024-10-15", "2023-12-13", "2024-02-14"]


def to_frame(rows: list[dict], item: str, grade: str) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if not {"yyyy", "regday", "price"} <= set(df.columns):
        return pd.DataFrame()
    df["평균도매가격"] = pd.to_numeric(
        df["price"].astype(str).str.replace(",", "", regex=False), errors="coerce")
    df["일자"] = pd.to_datetime(
        df["yyyy"].astype(str) + "-" + df["regday"].astype(str).str.replace("/", "-", regex=False),
        errors="coerce")
    df = df.dropna(subset=["평균도매가격", "일자"])
    df["품목"] = item
    df["등급"] = grade
    df["연도"] = df["일자"].dt.year
    df["월"] = df["일자"].dt.month
    return df[["품목", "등급", "일자", "연도", "월", "평균도매가격"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cert-key", default=os.environ.get("KAMIS_CERT_KEY"))
    ap.add_argument("--cert-id", default=os.environ.get("KAMIS_CERT_ID"))
    ap.add_argument("--discover", action="store_true", help="품목 코드 표를 새로 탐색해 저장")
    a = ap.parse_args()

    try:
        client = KamisClient(a.cert_key, a.cert_id)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    os.makedirs(OUT_DIR, exist_ok=True)

    if a.discover:
        codes = client.discover_items(DISCOVER_DAYS, categories=["100", "200", "300", "400"])
        pd.DataFrame(codes).to_csv(OUT_CODES, index=False, encoding="utf-8-sig")
        print(f"[saved] {OUT_CODES}  ({len(codes)}개 조합)")
        return 0

    frames = []
    for item, cat, code, kind, rank, grade in TARGETS:
        try:
            rows = client.period_series(cat, code, kind, rank)
            df = to_frame(rows, item, grade)
            if df.empty:
                print(f"[warn] {item} {grade}: 데이터 없음", file=sys.stderr)
                continue
            frames.append(df)
            print(f"[ok]   {item} {grade}: {len(df):,}건  "
                  f"{df['일자'].min().date()} ~ {df['일자'].max().date()}")
        except Exception as e:  # noqa: BLE001
            print(f"[fail] {item} {grade}: {type(e).__name__} {e}", file=sys.stderr)

    if not frames:
        print("수집된 데이터가 없습니다.", file=sys.stderr)
        return 1

    daily = pd.concat(frames, ignore_index=True)
    daily.to_csv(OUT_DAILY, index=False, encoding="utf-8-sig")

    # 같은 일자에 복수 시장 계열이 섞여 오므로 중앙값으로 집약한다
    monthly = (daily.groupby(["품목", "등급", "연도", "월"], observed=True)["평균도매가격"]
               .median().round(0).reset_index())
    monthly["단위"] = "kg"
    monthly = monthly[["품목", "등급", "연도", "월", "평균도매가격", "단위"]]
    monthly.to_csv(OUT, index=False, encoding="utf-8-sig")

    span = f"{daily['일자'].min().date()} ~ {daily['일자'].max().date()}"
    print(f"\n[saved] {OUT}  rows={len(monthly):,}  품목={monthly['품목'].nunique()}  기간={span}")
    print(f"[saved] {OUT_DAILY}  rows={len(daily):,}")
    print("\n참고: KAMIS periodProductList는 요청 기간을 무시하고 최근 보유 구간만 반환합니다.")
    print("      따라서 월별 가격지수는 '최근 1개 순환주기' 기준입니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
