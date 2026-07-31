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

# KAMIS 일일 가격조사 대상은 63개 품목이며, 임산물 중 실제 취급되는 것은
# 단감·느타리버섯·새송이버섯·팽이버섯뿐이다. 나머지 임산물(밤·대추·표고·곶감·잣·
# 고사리·도라지·더덕·원목·조경수)은 KAMIS 조사 대상이 아니므로 가격 기반 추천을 하지 않는다.
KAMIS_COVERED = {"단감", "느타리버섯", "새송이버섯", "팽이버섯"}

# 임가경제조사 '업종별' 코드 ↔ KAMIS 대표 품목 매핑
SECTOR_TO_ITEMS: dict[str, list[str]] = {
    "육림/목재생산업": [],
    "채취업": [],
    "밤재배업": [],
    "떫은감재배업": ["단감"],   # 떫은감 자체는 미취급. 감류 시세 참고치로만 사용한다.
    "수실류재배업": [],
    "버섯재배업": ["느타리버섯", "새송이버섯", "팽이버섯"],
    "조경재업": [],
    "기타재배업": [],
}

# 업종별로 KAMIS 미취급 사유를 명시한다 (빈 매핑을 침묵으로 넘기지 않기 위함).
NOT_COVERED_REASON: dict[str, str] = {
    "육림/목재생산업": "원목·제재목은 KAMIS 조사 대상이 아니며 산림청 원목시장 통계에서 관리됩니다.",
    "채취업": "고사리·도라지 등 산나물은 KAMIS 일일 가격조사 대상이 아닙니다.",
    "밤재배업": "밤은 KAMIS 일일 가격조사 대상 63개 품목에 포함되지 않습니다.",
    "수실류재배업": "대추·잣은 미취급이며, 호두는 '수입(1kg)' 소매만 있어 "
                    "국내 임가의 출하 의사결정 근거로 쓰기 어렵습니다.",
    "조경재업": "조경수는 화훼공판장 등 별도 유통경로로 KAMIS에서 다루지 않습니다.",
    "기타재배업": "더덕·도라지 등은 KAMIS 일일 가격조사 대상이 아닙니다.",
}

# 대응 품목이 조사 품목과 완전히 일치하지 않는 경우의 주의 문구
ITEM_CAVEAT: dict[str, str] = {
    "단감": "떫은감(곶감·건시용)은 KAMIS 미취급이라 같은 감류인 단감 시세를 참고치로 제시합니다. "
            "품종·용도가 달라 실제 떫은감 시세와는 차이가 있을 수 있습니다.",
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
    "느타리버섯": {"수확기": list(range(1, 13)), "출하가능": list(range(1, 13)), "저장성": "하(연중 재배)"},
    "새송이버섯": {"수확기": list(range(1, 13)), "출하가능": list(range(1, 13)), "저장성": "중"},
    "팽이버섯":   {"수확기": list(range(1, 13)), "출하가능": list(range(1, 13)), "저장성": "중"},
    "고사리":     {"수확기": [4, 5], "출하가능": list(range(1, 13)), "저장성": "상(건나물)"},
    "도라지":     {"수확기": [10, 11], "출하가능": [10, 11, 12, 1, 2, 3], "저장성": "중"},
    "더덕":       {"수확기": [10, 11], "출하가능": [10, 11, 12, 1, 2, 3], "저장성": "중"},
}

# 월별 가격지수를 산출하기 위해 요구하는 최소 관측 개월 수
MIN_MONTHS_FOR_INDEX = 8


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


def price_index(kamis: pd.DataFrame, item: str, grade: str = "상품") -> pd.DataFrame | None:
    """품목의 월별 평균가 및 전월평균 대비 가격지수(100=전체 월 평균) 산출.

    관측 개월이 MIN_MONTHS_FOR_INDEX 미만이면 계절성 판단이 불가하므로 None을 반환한다.
    """
    sub = kamis[kamis["품목"] == item]
    if "등급" in sub.columns and grade in set(sub["등급"]):
        sub = sub[sub["등급"] == grade]
    if sub.empty or sub["월"].nunique() < MIN_MONTHS_FOR_INDEX:
        return None
    m = sub.groupby("월", observed=True)["평균도매가격"].median()
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
            "message": NOT_COVERED_REASON.get(
                sector_label, f"'{sector_label}'은 KAMIS 가격조사 대상이 아닙니다."),
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
        if item in ITEM_CAVEAT:
            rec["주의"] = ITEM_CAVEAT[item]
        pi = price_index(kamis, item) if kamis is not None else None
        if pi is None:
            rec["가격데이터"] = None
            rec["추천월"] = None
            rec["추천근거"] = (
                "KAMIS 가격 데이터 미연결 — 수확 캘린더만 제공" if kamis is None else
                f"관측 개월이 {MIN_MONTHS_FOR_INDEX}개월 미만이라 계절성 판단 불가 — "
                "수확 캘린더만 제공"
            )
        else:
            allowed = set(cal.get("출하가능", list(range(1, 13))))
            cand = pi[pi["월"].isin(allowed)]
            cand = cand if not cand.empty else pi
            best = cand.loc[cand["가격지수"].idxmax()]
            worst = cand.loc[cand["가격지수"].idxmin()]
            base = pi.loc[pi["월"].isin(cal.get("수확기", [])), "가격지수"]
            gain = float(best["가격지수"] - base.mean()) if not base.empty else 0.0

            # 저장성이 낮고 연중 재배하는 품목은 '출하 이연'이 성립하지 않는다.
            # 이 경우 조절 대상은 출하 시점이 아니라 생산(입상·접종) 시점이다.
            year_round = len(cal.get("수확기", [])) >= 12
            low_storage = str(cal.get("저장성", "")).startswith("하")
            rec["전략유형"] = "생산시기 조절" if (year_round or low_storage) else "출하 이연"

            rec["가격데이터"] = pi.to_dict("records")
            rec["추천월"] = int(best["월"])
            rec["추천월_가격지수"] = round(float(best["가격지수"]), 1)
            rec["최저월"] = int(worst["월"])
            rec["최저월_가격지수"] = round(float(worst["가격지수"]), 1)
            rec["최고최저_격차_pct"] = round(
                float(best["가격지수"] - worst["가격지수"]), 1)
            rec["수확기대비_가격이득_pct"] = round(gain, 1)

            if rec["전략유형"] == "생산시기 조절":
                rec["추천근거"] = (
                    f"{int(best['월'])}월 도매가지수가 {best['가격지수']:.0f}(전체 월 평균=100)으로 최고, "
                    f"{int(worst['월'])}월이 {worst['가격지수']:.0f}으로 최저입니다. "
                    f"저장성이 낮아 출하를 미룰 수는 없으므로, 종균 접종·입상 시기를 조절해 "
                    f"수확이 {int(best['월'])}월에 집중되도록 하는 편이 유리합니다 "
                    f"(월간 최대 격차 {rec['최고최저_격차_pct']:.1f}%p)."
                )
            else:
                rec["추천근거"] = (
                    f"출하 가능 기간 중 {int(best['월'])}월 도매가지수가 "
                    f"{best['가격지수']:.0f}(전체 월 평균=100)으로 최고. "
                    f"수확기 즉시 출하 대비 약 {gain:+.1f}%p 유리합니다."
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
