#!/usr/bin/env python3
"""
KAMIS(농수산물유통정보) 월별 도매가격 수집기 → data/kamis/kamis_monthly.csv

사용 전 준비
    1) https://www.kamis.or.kr/customer/reference/openapi_list.do 에서 OpenAPI 신청
    2) 발급받은 cert_key / cert_id 를 인자 또는 환경변수로 전달

실행
    python scripts/fetch_kamis.py --cert-key XXXX --cert-id you@example.com \
        --start 2019 --end 2023

산출 스키마 (src/shipping.py 가 기대하는 형식)
    품목,연도,월,평균도매가격,단위
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "kamis")
OUT = os.path.join(OUT_DIR, "kamis_monthly.csv")

API = "https://www.kamis.or.kr/service/price/xml.do"

# KAMIS 부류코드(itemcategorycode) · 품목코드(itemcode)
# 임산물 관련 대표 품목. 코드는 KAMIS '품목코드 조회' 기준.
ITEMS = [
    # (표시명, 부류코드, 품목코드)
    ("밤",         "400", "419"),
    ("대추",       "400", "420"),
    ("단감",       "400", "413"),
    ("곶감",       "400", "414"),
    ("호두",       "400", "424"),
    ("잣",         "400", "425"),
    ("표고버섯",   "200", "256"),
    ("느타리버섯", "200", "257"),
    ("고사리",     "200", "230"),
    ("도라지",     "200", "231"),
    ("더덕",       "200", "232"),
]


def fetch_item(name: str, cat: str, code: str, year: int, key: str, cid: str) -> pd.DataFrame:
    """월별 도매가격(p_productclscode=02: 도매) 조회."""
    params = {
        "action": "monthlySalesList",
        "p_yyyy": str(year),
        "p_period": "3",
        "p_itemcategorycode": cat,
        "p_itemcode": code,
        "p_kindcode": "",
        "p_productrankcode": "",
        "p_countrycode": "",
        "p_convert_kg_yn": "Y",
        "p_cert_key": key,
        "p_cert_id": cid,
        "p_returntype": "json",
    }
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    rows = []
    items = data.get("data", {}).get("item", []) if isinstance(data.get("data"), dict) else []
    for it in items:
        # KAMIS 응답은 m1..m12 형태로 월별 값을 준다
        for m in range(1, 13):
            v = it.get(f"m{m}") or it.get(f"m{m:02d}")
            if v in (None, "", "-"):
                continue
            try:
                price = float(str(v).replace(",", ""))
            except ValueError:
                continue
            rows.append({"품목": name, "연도": year, "월": m,
                         "평균도매가격": price, "단위": it.get("unit", "kg")})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cert-key", default=os.environ.get("KAMIS_CERT_KEY"))
    ap.add_argument("--cert-id", default=os.environ.get("KAMIS_CERT_ID"))
    ap.add_argument("--start", type=int, default=2019)
    ap.add_argument("--end", type=int, default=2023)
    a = ap.parse_args()

    if not a.cert_key or not a.cert_id:
        print("ERROR: --cert-key / --cert-id (또는 KAMIS_CERT_KEY/KAMIS_CERT_ID) 필요",
              file=sys.stderr)
        return 2

    os.makedirs(OUT_DIR, exist_ok=True)
    frames = []
    for year in range(a.start, a.end + 1):
        for name, cat, code in ITEMS:
            try:
                df = fetch_item(name, cat, code, year, a.cert_key, a.cert_id)
                if not df.empty:
                    frames.append(df)
                print(f"[ok] {year} {name}: {len(df)}건")
            except Exception as e:  # noqa: BLE001
                print(f"[fail] {year} {name}: {e}", file=sys.stderr)
            time.sleep(0.3)

    if not frames:
        print("수집된 데이터가 없습니다.", file=sys.stderr)
        return 1
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n[saved] {OUT}  rows={len(out):,}  품목={out['품목'].nunique()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
