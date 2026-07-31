"""
최적 출하시기 추천 모듈 (임업통계 × KAMIS 도매가격 융복합)

설계 원칙
---------
임가경제조사 총괄 마이크로데이터에는 월(月) 단위 출하·가격 정보가 없다.
따라서 출하시기 추천은 **KAMIS(농수산물유통정보) 월별 도매가격**을 외부
공공데이터로 결합해 산출한다.

  data/kamis/*.csv 가 존재하면  → 실제 월별 도매가 기반 추천 (권장)
  존재하지 않으면              → 수확 캘린더만 제시하고 '가격 데이터 미연결'을 명시

가격 데이터가 없을 때 가상의 가격을 만들어 추천하지 않는다.
KAMIS 원자료는 scripts/fetch_kamis.py 로 내려받는다.

기대 CSV 스키마 (fetch_kamis.py 산출과 동일)
    품목,연도,월,평균도매가격,단위
    밤,2023,9,4520,kg
"""
from __future__ import annotations

import glob
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KAMIS_DIR = os.path.join(ROOT, "data", "kamis")

# 임가경제조사 '업종별' 코드 ↔ KAMIS 대표 품목 매핑
SECTOR_TO_ITEMS: dict[str, list[str]] = {
    "육림/목재생산업": [],                      # KAMIS 미취급 (원목은 산림청 별도 통계)
    "채취업": ["고사리", "도라지"],
    "밤재배업": ["밤"],
    "떫은감재배업": ["단감", "곶감"],
    "수실류재배업": ["대추", "호두", "잣"],
    "버섯재배업": ["표고버섯", "느타리버섯"],
    "조경재업": [],                              # KAMIS 미취급 (조경수는 화훼공판장 별도)
    "기타재배업": ["더덕", "도라지"],
}

# 산림청 임산물 표준 수확·출하 가능 기간 (월). 저장성 품목은 저장 후 출하 가능 기간까지 포함.
HARVEST_CALENDAR: dict[str, dict] = {
    "밤":         {"수확기": [9, 10], "출하가능": [9, 10, 11, 12, 1, 2], "저장성": "중(저온저장 3~4개월)"},
    "단감":       {"수확기": [10, 11], "출하가능": [10, 11, 12, 1, 2], "저장성": "중(CA저장)"},
    "곶감":       {"수확기": [11, 12], "출하가능": [12, 1, 2, 3], "저장성": "상(건조·냉동)"},
    "대추":       {"수확기": [9, 10], "출하가능": [9, 10, 11, 12, 1], "저장성": "상(건조)"},
    "호두":       {"수확기": [9, 10], "출하가능": list(range(1, 13)), "저장성": "상(건과)"},
    "잣":         {"수확기": [9, 10], "출하가능": list(range(1, 13)), "저장성": "상(건과)"},
    "표고버섯":   {"수확기": [3, 4, 5, 9, 10, 11], "출하가능": [3, 4, 5, 9, 10, 11], "저장성": "하(생표고)"},
    "느타리버섯": {"수확기": list(range(1, 13)), "출하가능": list(range(1, 13)), "저장성": "하"},
    "고사리":     {"수확기": [4, 5], "출하가능": list(range(1, 13)), "저장성": "상(건나물)"},
    "도라지":     {"수확기": [10, 11], "출하가능": [10, 11, 12, 1, 2, 3], "저장성": "중"},
    "더덕":       {"수확기": [10, 11], "출하가능": [10, 11, 12, 1, 2, 3], "저장성": "중"},
}


# ---------------------------------------------------------------------------
def load_kamis() -> pd.DataFrame | None:
    """data/kamis/*.csv 를 읽어 품목×월 평균 도매가 테이블 반환. 없으면 None."""
    paths = sorted(glob.glob(os.path.join(KAMIS_DIR, "*.csv")))
    if not paths:
        return None
    frames = []
    for p in paths:
        for enc in ("utf-8-sig", "cp949", "utf-8"):
            try:
                frames.append(pd.read_csv(p, encoding=enc))
                break
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)

    required = {"품목", "월", "평균도매가격"}
    if not required.issubset(df.columns):
        raise ValueError(
            f"KAMIS CSV 스키마 불일치. 필요 컬럼={sorted(required)}, 실제={list(df.columns)}"
        )
    df["월"] = pd.to_numeric(df["월"], errors="coerce").astype("Int64")
    df["평균도매가격"] = pd.to_numeric(df["평균도매가격"], errors="coerce")
    return df.dropna(subset=["월", "평균도매가격"])


def price_index(kamis: pd.DataFrame, item: str) -> pd.DataFrame | None:
    """품목의 월별 평균가 및 연평균 대비 가격지수(100=연평균) 산출."""
    sub = kamis[kamis["품목"] == item]
    if sub.empty:
        return None
    m = sub.groupby("월", observed=True)["평균도매가격"].mean()
    out = pd.DataFrame({"월": m.index.astype(int), "평균도매가격": m.to_numpy()})
    out["가격지수"] = out["평균도매가격"] / out["평균도매가격"].mean() * 100
    return out.sort_values("월").reset_index(drop=True)


def recommend(sector_label: str, kamis: pd.DataFrame | None = None) -> dict:
    """업종 라벨에 대한 출하시기 추천 결과를 dict로 반환."""
    items = SECTOR_TO_ITEMS.get(sector_label, [])
    if not items:
        return {
            "status": "not_applicable",
            "sector": sector_label,
            "message": f"'{sector_label}'은 KAMIS 도매가격 조사 대상 품목이 아닙니다 "
                       f"(원목·조경수는 별도 유통 경로).",
            "items": [],
        }

    if kamis is None:
        kamis = load_kamis()

    results = []
    for item in items:
        cal = HARVEST_CALENDAR.get(item, {})
        rec = {
            "품목": item,
            "수확기": cal.get("수확기", []),
            "출하가능월": cal.get("출하가능", []),
            "저장성": cal.get("저장성", "-"),
        }
        pi = price_index(kamis, item) if kamis is not None else None
        if pi is None:
            rec["가격데이터"] = None
            rec["추천월"] = None
            rec["추천근거"] = "KAMIS 가격 데이터 미연결 — 수확 캘린더만 제공"
        else:
            allowed = set(cal.get("출하가능", list(range(1, 13))))
            cand = pi[pi["월"].isin(allowed)]
            cand = cand if not cand.empty else pi
            best = cand.loc[cand["가격지수"].idxmax()]
            base = pi.loc[pi["월"].isin(cal.get("수확기", [])), "가격지수"]
            gain = float(best["가격지수"] - base.mean()) if not base.empty else 0.0
            rec["가격데이터"] = pi.to_dict("records")
            rec["추천월"] = int(best["월"])
            rec["추천월_가격지수"] = round(float(best["가격지수"]), 1)
            rec["수확기대비_가격이득_pct"] = round(gain, 1)
            rec["추천근거"] = (
                f"출하 가능 기간 중 {int(best['월'])}월 도매가지수가 "
                f"{best['가격지수']:.0f}(연평균=100)으로 최고. "
                f"수확기 즉시 출하 대비 약 {gain:+.1f}%p 유리."
            )
        results.append(rec)

    return {
        "status": "ok" if kamis is not None else "no_price_data",
        "sector": sector_label,
        "items": results,
        "message": None if kamis is not None else
        "data/kamis/ 에 KAMIS 월별 도매가격 CSV가 없어 수확 캘린더 기준으로만 안내합니다. "
        "python scripts/fetch_kamis.py --api-key ... 로 내려받으면 가격 기반 추천이 활성화됩니다.",
    }


if __name__ == "__main__":
    import json

    k = load_kamis()
    print("KAMIS 연결:", "OK" if k is not None else "미연결")
    for s in SECTOR_TO_ITEMS:
        print(json.dumps(recommend(s, k), ensure_ascii=False, indent=2, default=str)[:600])
        print("-" * 70)
