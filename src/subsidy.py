"""
Phase 2-G — 산림청 보조금 세부사업 연계 (자부담 기준 실효 ROI)

출처: 산림청 「보조금 세부사업 정보」 (2021-10-21 공개, 공공데이터)
      상세사업명 · 국고비율 · 시군구비율 · 자부담비율 · 사후관리기간

왜 필요한가
-----------
예측 모델은 '투입한 경영비 대비 얼마를 버는가'를 답한다. 그런데 임가가 실제로
부담하는 돈은 총 투입액이 아니라 **자부담액**이다. 보조사업을 활용하면 같은
규모의 투자를 자부담 20~40%만으로 집행할 수 있고, 이때 **자기 자금 기준 수익률**은
보조율만큼 지렛대가 걸린다.

    실효 ROI = (임업소득) / (자부담액) × 100
             = 예측 ROI ÷ 자부담비율

이 계층은 예측 모델과 정책을 직접 잇는다. 임가에게는 "어떤 사업을 쓰면 내 돈
얼마로 이만큼 벌 수 있는가", 정책 담당자에게는 "보조율을 몇 %로 두면 임가의
투자 유인이 생기는가"를 같은 식으로 보여준다.

주의: 지렛대는 수익률만 키우지 않는다. 사후관리기간 동안 처분·용도변경이
제한되고, 사업 실패 시 자부담액 전액이 손실이며 보조금 환수 가능성도 있다.
산출물에 이를 함께 기록한다.

산출: models/subsidy_programs.json
"""
from __future__ import annotations

import glob
import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
MODEL_DIR = os.path.join(ROOT, "models")
OUT = os.path.join(MODEL_DIR, "subsidy_programs.json")

# 사업 성격 분류 — 임가의 의사결정 맥락이 서로 다르다
CATEGORY_RULES = [
    ("생산기반", ["생산단지", "생산기반", "복합경영단지", "산림작물"]),
    ("유통·가공", ["유통", "가공", "상품화", "판매촉진", "물류"]),
    ("수출", ["수출", "해외", "국제박람회", "바이어", "안테나숍", "검역", "인증", "보험",
              "식품위생", "포장디자인", "관상식물"]),
    ("목재·목질", ["목재", "목공", "팰릿", "펠릿"]),
]

# 임가경제조사 업종 ↔ 직접 활용 가능성이 높은 사업 성격
SECTOR_TO_CATEGORY = {
    "밤재배업": ["생산기반", "유통·가공", "수출"],
    "떫은감재배업": ["생산기반", "유통·가공", "수출"],
    "수실류재배업": ["생산기반", "유통·가공", "수출"],
    "버섯재배업": ["생산기반", "유통·가공"],
    "채취업": ["생산기반", "유통·가공"],
    "기타재배업": ["생산기반", "유통·가공"],
    "조경재업": ["유통·가공", "수출"],
    "육림/목재생산업": ["목재·목질", "생산기반"],
}


def categorize(name: str) -> str:
    for cat, keys in CATEGORY_RULES:
        if any(k in name for k in keys):
            return cat
    return "기타"


def find_file() -> str | None:
    cands = glob.glob(os.path.join(DATA_DIR, "**", "*보조금*.csv"), recursive=True)
    return cands[0] if cands else None


def load() -> pd.DataFrame | None:
    path = find_file()
    if not path:
        return None
    for enc in ("cp949", "euc-kr", "utf-8-sig", "utf-8"):
        try:
            d = pd.read_csv(path, encoding=enc)
            break
        except Exception:  # noqa: BLE001
            continue
    else:
        return None

    d.columns = [str(c).strip() for c in d.columns]
    for c in ["국고비율", "시군구비율", "자부담비율", "사후관리기간"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")

    if "사용여부" in d.columns:
        n_off = int((d["사용여부"].astype(str).str.upper() != "Y").sum())
        d = d[d["사용여부"].astype(str).str.upper() == "Y"].copy()
        d.attrs["폐지_제외"] = n_off

    d["분류"] = d["상세사업명"].astype(str).map(categorize)
    d["보조율"] = d["국고비율"].fillna(0) + d["시군구비율"].fillna(0)
    # 자부담이 0이면 지렛대가 무한대로 발산하므로 별도 표기한다
    d["지렛대배수"] = (100.0 / d["자부담비율"]).where(d["자부담비율"] > 0)
    return d


def effective_roi(predicted_roi_pct: float, self_pay_pct: float) -> float | None:
    """자부담 기준 실효 ROI(%). 자부담이 0이면 정의되지 않는다."""
    if self_pay_pct is None or self_pay_pct <= 0:
        return None
    return predicted_roi_pct * (100.0 / self_pay_pct)


def build() -> dict:
    d = load()
    if d is None:
        return {}

    programs = []
    for _, r in d.sort_values(["분류", "자부담비율"]).iterrows():
        programs.append({
            "사업명": str(r["상세사업명"]).strip(),
            "분류": r["분류"],
            "국고비율": None if pd.isna(r.get("국고비율")) else int(r["국고비율"]),
            "시군구비율": None if pd.isna(r.get("시군구비율")) else int(r["시군구비율"]),
            "자부담비율": None if pd.isna(r.get("자부담비율")) else int(r["자부담비율"]),
            "보조율": None if pd.isna(r.get("보조율")) else int(r["보조율"]),
            "지렛대배수": None if pd.isna(r.get("지렛대배수")) else round(float(r["지렛대배수"]), 2),
            "사후관리기간_년": None if pd.isna(r.get("사후관리기간")) else int(r["사후관리기간"]),
        })

    by_cat = {}
    for cat, g in d.groupby("분류", observed=True):
        valid = g[g["자부담비율"] > 0]
        by_cat[cat] = {
            "사업수": int(len(g)),
            "자부담_최저_pct": int(g["자부담비율"].min()),
            "자부담_중앙_pct": float(g["자부담비율"].median()),
            "최대_지렛대배수": round(float(valid["지렛대배수"].max()), 2) if len(valid) else None,
            "대표사업_최저자부담": str(g.loc[g["자부담비율"].idxmin(), "상세사업명"]).strip(),
        }

    return {
        "출처": "산림청 「보조금 세부사업 정보」 (2021-10-21 공개)",
        "사업수": int(len(d)),
        "제외_폐지사업": int(d.attrs.get("폐지_제외", 0)),
        "사업목록": programs,
        "분류별_요약": by_cat,
        "업종별_관련분류": SECTOR_TO_CATEGORY,
        "실효ROI_정의": "실효 ROI(%) = 예측 ROI(%) ÷ (자부담비율/100). "
                        "임가가 실제로 부담하는 자기 자금 기준 수익률이다.",
        "유의": "보조율이 높을수록 자기 자금 기준 수익률은 커지지만 위험도 함께 커진다. "
                "사후관리기간 동안 처분·용도변경이 제한되고, 사업이 실패하면 자부담액은 "
                "전액 손실이며 보조금 환수 대상이 될 수 있다. 실효 ROI는 성공을 전제한 "
                "상한선으로 읽어야 한다.",
        "기준시점": "2021-10-21 공개본. 보조율은 연도·지자체별로 달라질 수 있으므로 "
                    "실제 신청 시 산림청·관할 지자체 공고를 확인해야 한다.",
    }


def main() -> None:
    res = build()
    if not res:
        print("보조금 세부사업 CSV를 찾지 못했습니다.")
        return
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

    print(f"사업 {res['사업수']}건 (폐지 {res['제외_폐지사업']}건 제외)\n")
    print(f"{'분류':10s} {'사업수':>4s} {'최저자부담':>7s} {'중앙자부담':>7s} {'최대지렛대':>7s}  대표사업")
    for cat, v in sorted(res["분류별_요약"].items(),
                         key=lambda kv: kv[1]["자부담_최저_pct"]):
        lev = f"{v['최대_지렛대배수']:.1f}배" if v["최대_지렛대배수"] else "-"
        print(f"{cat:10s} {v['사업수']:>4d} {v['자부담_최저_pct']:>6d}% "
              f"{v['자부담_중앙_pct']:>6.0f}% {lev:>8s}  {v['대표사업_최저자부담']}")

    print("\n예시 — 예측 ROI 50%인 임가가 보조사업을 활용할 경우의 실효 ROI")
    for sp in [60, 40, 30, 20]:
        print(f"  자부담 {sp:>2d}% → 실효 ROI {effective_roi(50, sp):>6.1f}% "
              f"(지렛대 {100/sp:.1f}배)")
    print(f"\n[saved] {OUT}")


if __name__ == "__main__":
    main()
