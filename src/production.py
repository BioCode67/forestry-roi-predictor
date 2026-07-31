"""
Phase 2-E — 임산물생산조사 분석 (전 품목 지역별 단가·생산 구조)

출처: 산림청 국가승인통계 「임산물생산조사」 전품목 (2022~2024, 통계청 MDIS)
      시도/시군구 × 대분류·중분류·소분류 × 생산량 · 단가 · 생산금액

이 조사가 메우는 공백
---------------------
KAMIS 일일 가격조사는 63개 품목만 다루며 임산물 중에는 단감·버섯 3종뿐이다.
밤·대추·떫은감·표고·산나물·약용식물의 가격 정보가 통째로 비어 있었는데,
「임산물생산조사」는 **전 임산물의 시군구별 실측 단가**를 담고 있어
임업통계만으로 가격 계층을 완성할 수 있다.

다만 연 단위 조사이므로 **월별 계절성은 산출되지 않는다.**
계절성은 KAMIS(월별), 가격 수준·지역 격차·추세는 본 조사가 담당하도록 역할을 나눈다.

산출: models/production_insights.json, reports/figures/prod_*.png
"""
from __future__ import annotations

import glob
import json
import os

import matplotlib

matplotlib.use("Agg")
import koreanize_matplotlib  # noqa: F401
import matplotlib.pyplot as plt

plt.rcParams["axes.unicode_minus"] = False

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "data", "임산물생산조사")
MODEL_DIR = os.path.join(ROOT, "models")
FIG_DIR = os.path.join(ROOT, "reports", "figures")
OUT = os.path.join(MODEL_DIR, "production_insights.json")
os.makedirs(FIG_DIR, exist_ok=True)

GREEN, GREY, AMBER, RED, BLUE = "#2E7D32", "#90A4AE", "#EF6C00", "#C62828", "#1565C0"

# 임가경제조사 '업종별' ↔ 임산물생산조사 '소분류' 매핑
SECTOR_TO_PRODUCTS: dict[str, list[str]] = {
    "밤재배업": ["밤"],
    "떫은감재배업": ["떫은감"],
    "수실류재배업": ["대추", "호두", "잣", "은행", "복분자", "산딸기", "오미자"],
    "버섯재배업": ["생표고", "건표고", "표고자목용", "느타리", "목이버섯", "송이", "능이"],
    "채취업": ["고사리", "두릅", "취나물", "더덕", "도라지", "산마늘", "곰취"],
    "조경재업": ["조경수"],
    "육림/목재생산업": ["순임목", "용재"],
    "기타재배업": ["더덕", "도라지", "산양삼", "헛개나무"],
}

# 단가 단위가 품목군마다 달라 직접 비교하면 안 되는 대분류
NON_WEIGHT_UNIT = {"순임목", "용재", "조경재", "양묘", "조림", "토석", "연료", "농용자재"}

# '시도/청'에는 지자체와 국유림 관리기관이 섞여 있다. 국유림은 생산 기반과
# 경영 주체가 달라 임가의 지역 선택 근거가 될 수 없으므로 지역 비교에서 제외한다.
NATIONAL_FOREST_ORGS = {
    "동부지방산림청", "남부지방산림청", "북부지방산림청", "서부지방산림청", "중부지방산림청",
    "국립산림과학원", "국립산림품종관리센터", "국립수목원",
}

# 연도별로 행정구역 명칭이 바뀌어 같은 지역이 둘로 쪼개진다 (2023년 강원·전북 특별자치도 전환)
SIDO_CANON = {
    "강원특별자치도": "강원", "강원도": "강원",
    "전북특별자치도": "전북", "전라북도": "전북",
    "경기도": "경기", "충청북도": "충북", "충청남도": "충남", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
    "세종특별자치시": "세종", "서울특별시": "서울", "부산광역시": "부산",
    "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
    "대전광역시": "대전", "울산광역시": "울산",
}

# 가공 전후 대응 (원물 → 가공품). 건조 감모가 있어 단가 배수를 그대로
# '부가가치 배수'로 읽으면 안 되며, 감모율을 함께 표기한다.
PROCESSING_PAIRS = [
    ("생표고", "건표고", 0.125),  # 생표고 8kg → 건표고 1kg (통상 건조수율)
]


def load() -> pd.DataFrame:
    frames = []
    for f in sorted(glob.glob(os.path.join(SRC_DIR, "*.csv"))):
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
        print(f"[load] {os.path.basename(f)[:30]}  rows={len(d):,}")
    df = pd.concat(frames, ignore_index=True)

    for c in ["생산량", "단가", "생산금액"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["시도/청", "시도/관리소", "시군구", "대분류", "중분류", "소분류"]:
        df[c] = df[c].astype(str).str.strip()

    before = len(df)
    df = df[(df["생산량"] > 0) & (df["단가"] > 0) & (df["생산금액"] > 0)]
    print(f"[clean] 생산량·단가 유효 {len(df):,} / {before:,}")

    df["국유림"] = df["시도/청"].isin(NATIONAL_FOREST_ORGS)
    df["시도"] = df["시도/청"].map(SIDO_CANON)
    n_org = int(df["국유림"].sum())
    n_unmapped = int(df["시도"].isna().sum() - n_org)
    print(f"[clean] 국유림 관리기관 {n_org:,}행 (지역 비교에서 제외) · "
          f"미매핑 시도 {max(n_unmapped, 0):,}행")
    return df


# ---------------------------------------------------------------------------
# ① 품목별 전국 단가 추이
# ---------------------------------------------------------------------------
def price_trend(df: pd.DataFrame, min_regions: int = 20) -> dict:
    out = {}
    for item, g in df.groupby("소분류", observed=True):
        if g["시군구"].nunique() < min_regions or g["대분류"].iloc[0] in NON_WEIGHT_UNIT:
            continue
        # 단가는 물량 가중평균이 실태에 가깝다
        rows = []
        for year, gy in g.groupby("연도", observed=True):
            w = gy["생산금액"].sum() / gy["생산량"].sum()
            rows.append({"연도": int(year), "가중평균단가": round(float(w), 1),
                         "중앙단가": round(float(gy["단가"].median()), 1),
                         "생산량": int(gy["생산량"].sum()),
                         "생산금액": int(gy["생산금액"].sum()),
                         "시군구수": int(gy["시군구"].nunique())})
        rows.sort(key=lambda r: r["연도"])
        if len(rows) < 2:
            continue
        first, last = rows[0], rows[-1]
        out[item] = {
            "대분류": g["대분류"].iloc[0],
            "연도별": rows,
            "단가_변화율_pct": round((last["가중평균단가"] / first["가중평균단가"] - 1) * 100, 1),
            "생산량_변화율_pct": round((last["생산량"] / first["생산량"] - 1) * 100, 1)
            if first["생산량"] else None,
            "최신_생산금액": last["생산금액"],
        }
    return out


# ---------------------------------------------------------------------------
# ② 지역별 단가 프리미엄
# ---------------------------------------------------------------------------
def regional_premium(df: pd.DataFrame, items: list[str], min_obs: int = 5) -> dict:
    out = {}
    latest = df[(df["연도"] == df["연도"].max()) & df["시도"].notna()]
    for item in items:
        g = latest[latest["소분류"] == item]
        if g.empty or g["대분류"].iloc[0] in NON_WEIGHT_UNIT:
            continue
        nat = g["생산금액"].sum() / g["생산량"].sum()
        rows = []
        for sido, gs in g.groupby("시도", observed=True):
            if len(gs) < min_obs or gs["생산량"].sum() <= 0:
                continue
            w = gs["생산금액"].sum() / gs["생산량"].sum()
            rows.append({"시도": sido, "가중평균단가": round(float(w), 1),
                         "전국대비_pct": round(float(w / nat - 1) * 100, 1),
                         "생산량": int(gs["생산량"].sum()), "관측": int(len(gs))})
        if len(rows) < 3:
            continue
        rows.sort(key=lambda r: -r["가중평균단가"])
        out[item] = {
            "전국_가중평균단가": round(float(nat), 1),
            "연도": int(latest["연도"].iloc[0]),
            "지역": rows,
            "최고지역": rows[0]["시도"], "최고단가": rows[0]["가중평균단가"],
            "최저지역": rows[-1]["시도"], "최저단가": rows[-1]["가중평균단가"],
            "지역격차_배": round(rows[0]["가중평균단가"] / rows[-1]["가중평균단가"], 2)
            if rows[-1]["가중평균단가"] else None,
        }
    return out


# ---------------------------------------------------------------------------
# ③ 지역 특화도 (Location Quotient)
# ---------------------------------------------------------------------------
def specialization(df: pd.DataFrame, items: list[str], top_n: int = 5) -> dict:
    """LQ = (지역 내 해당 품목 생산금액 비중) / (전국 해당 품목 생산금액 비중)

    LQ > 1 이면 그 지역이 해당 품목에 상대적으로 특화되어 있다는 뜻이다.
    """
    latest = df[(df["연도"] == df["연도"].max()) & df["시도"].notna()]
    total_all = latest["생산금액"].sum()
    out = {}
    for item in items:
        g = latest[latest["소분류"] == item]
        if g.empty:
            continue
        nat_share = g["생산금액"].sum() / total_all
        if nat_share <= 0:
            continue
        rows = []
        for sido, gs in latest.groupby("시도", observed=True):
            denom = gs["생산금액"].sum()
            if denom <= 0:
                continue
            num = gs.loc[gs["소분류"] == item, "생산금액"].sum()
            if num <= 0:
                continue
            rows.append({"시도": sido, "LQ": round(float((num / denom) / nat_share), 2),
                         "생산금액": int(num),
                         "전국비중_pct": round(float(num / g["생산금액"].sum()) * 100, 1)})
        rows.sort(key=lambda r: -r["LQ"])
        if rows:
            out[item] = {"연도": int(latest["연도"].iloc[0]), "상위지역": rows[:top_n]}
    return out


# ---------------------------------------------------------------------------
# ④ 가공 부가가치
# ---------------------------------------------------------------------------
def processing_value(trends: dict) -> dict:
    out = {}
    for raw, processed, yield_rate in PROCESSING_PAIRS:
        if raw not in trends or processed not in trends:
            continue
        pr = trends[raw]["연도별"][-1]["가중평균단가"]
        pp = trends[processed]["연도별"][-1]["가중평균단가"]
        # 원물 1kg 기준 환산: 가공품 단가 × 건조수율
        per_raw_kg = pp * yield_rate
        ratio = pp / pr if pr else None
        breakeven = 1.0 / yield_rate
        out[f"{raw}→{processed}"] = {
            "원물_단가": round(pr, 1),
            "가공품_단가": round(pp, 1),
            "단가_배수": round(ratio, 2) if ratio else None,
            "건조수율": yield_rate,
            "손익분기_배수": round(breakeven, 2),
            "원물1kg당_가공수취액": round(per_raw_kg, 1),
            "원물직판대비_pct": round((per_raw_kg / pr - 1) * 100, 1) if pr else None,
            "판정": ("가공이 유리" if ratio and ratio > breakeven else "원물 직판이 유리"),
            "해석": (
                f"{raw} {breakeven:.1f}kg가 {processed} 1kg이 되므로, 단가 배수가 "
                f"{breakeven:.1f}배를 넘어야 가공이 이득이다. 실제 배수는 "
                f"{ratio:.2f}배로 " + ("이를 넘는다." if ratio and ratio > breakeven
                                       else "이에 미치지 못한다.")
            ) if ratio else None,
            "주의": "건조수율은 통상값이며 실제 수율·가공비·설비투자·저장 이점은 "
                    "반영하지 않았다. 수취액 비교의 방향성만 참고한다.",
        }
    return out


# ---------------------------------------------------------------------------
# 시각화
# ---------------------------------------------------------------------------
FOCUS = ["밤", "떫은감", "대추", "생표고", "건표고", "고사리", "더덕", "도라지", "호두", "잣"]


def plot_trend(trends: dict) -> str:
    items = [i for i in FOCUS if i in trends]
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.6))
    ax = axes[0]
    for i, item in enumerate(items):
        d = pd.DataFrame(trends[item]["연도별"])
        base = d["가중평균단가"].iloc[0]
        ax.plot(d["연도"], d["가중평균단가"] / base * 100, "o-", lw=2, label=item)
    ax.axhline(100, color="#888", ls="--", lw=1)
    ax.set_xticks(sorted({y for i in items for y in
                          [r["연도"] for r in trends[i]["연도별"]]}))
    ax.set_ylabel("단가 지수 (첫 연도 = 100)")
    ax.set_title("주요 임산물 단가 추이", fontweight="bold")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)

    ax = axes[1]
    ch = sorted(((i, trends[i]["단가_변화율_pct"]) for i in items), key=lambda kv: kv[1])
    ax.barh([c[0] for c in ch], [c[1] for c in ch],
            color=[RED if c[1] < 0 else GREEN for c in ch])
    ax.axvline(0, color="#444", lw=1)
    ax.set_xlabel("단가 변화율 (%)")
    ax.set_title("첫 연도 대비 최신 연도 단가 변화", fontweight="bold")
    ax.grid(axis="x", alpha=0.3)

    fig.suptitle("임산물생산조사 — 전국 물량가중 단가", fontsize=13, fontweight="bold")
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "prod_price_trend.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def plot_regional(prem: dict) -> str:
    items = [i for i in FOCUS if i in prem][:6]
    if not items:
        return ""
    n = len(items)
    fig, axes = plt.subplots(2, (n + 1) // 2, figsize=(4.6 * ((n + 1) // 2), 8))
    axes = np.atleast_1d(axes).ravel()
    for ax, item in zip(axes, items):
        rows = prem[item]["지역"][:8]
        names = [r["시도"] for r in rows]
        vals = [r["전국대비_pct"] for r in rows]
        ax.barh(names, vals, color=[GREEN if v >= 0 else RED for v in vals])
        ax.axvline(0, color="#444", lw=1)
        ax.invert_yaxis()
        ax.set_title(f"{item} (전국 {prem[item]['전국_가중평균단가']:,.0f}원)", fontsize=10,
                     fontweight="bold")
        ax.set_xlabel("전국 평균 대비 (%)")
        ax.grid(axis="x", alpha=0.3)
    for ax in axes[len(items):]:
        ax.axis("off")
    fig.suptitle(f"시도별 단가 프리미엄 — {prem[items[0]]['연도']}년",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "prod_regional_premium.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def plot_market(trends: dict) -> str:
    items = [i for i in FOCUS if i in trends]
    d = pd.DataFrame([{"품목": i, "생산금액": trends[i]["최신_생산금액"] / 1e8,
                       "생산량변화": trends[i]["생산량_변화율_pct"] or 0}
                      for i in items]).sort_values("생산금액")
    fig, ax = plt.subplots(figsize=(9, 4.8))
    bars = ax.barh(d["품목"], d["생산금액"],
                   color=[GREEN if v >= 0 else RED for v in d["생산량변화"]])
    for b, (amt, ch) in zip(bars, zip(d["생산금액"], d["생산량변화"])):
        ax.text(amt, b.get_y() + b.get_height() / 2,
                f"  {amt:,.0f}억  (생산량 {ch:+.0f}%)", va="center", fontsize=9)
    ax.set_xlabel("최신 연도 생산금액 (억원)")
    ax.set_title("품목별 시장 규모와 생산량 증감 (녹색=증가, 적색=감소)", fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    ax.margins(x=0.25)
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "prod_market_size.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
def main() -> None:
    df = load()
    trends = price_trend(df)
    prem = regional_premium(df, FOCUS)
    spec = specialization(df, FOCUS)
    proc = processing_value(trends)

    # 업종별 대표 단가 (대시보드에서 임가경제조사 업종과 연결)
    sector_price = {}
    for sector, prods in SECTOR_TO_PRODUCTS.items():
        avail = [p for p in prods if p in trends]
        if not avail:
            continue
        sector_price[sector] = {
            p: {"최신단가": trends[p]["연도별"][-1]["가중평균단가"],
                "단가변화_pct": trends[p]["단가_변화율_pct"],
                "생산량변화_pct": trends[p]["생산량_변화율_pct"]}
            for p in avail
        }

    result = {
        "출처": "산림청 국가승인통계 「임산물생산조사」 전품목 (통계청 MDIS)",
        "연도": sorted(int(y) for y in df["연도"].unique()),
        "관측": int(len(df)),
        "품목수": int(df["소분류"].nunique()),
        "단가추이": trends,
        "지역단가프리미엄": prem,
        "지역특화도_LQ": spec,
        "가공부가가치": proc,
        "업종별_대표단가": sector_price,
        "figures": {k: os.path.relpath(v, ROOT) for k, v in {
            "price_trend": plot_trend(trends),
            "regional_premium": plot_regional(prem),
            "market_size": plot_market(trends),
        }.items() if v},
        "주의": "연 단위 조사이므로 월별 계절성은 산출되지 않는다. "
                "계절성은 KAMIS 월별 도매가가, 가격 수준·지역 격차·추세는 본 조사가 담당한다. "
                "순임목·용재·조경재·양묘 등은 단가 단위가 중량 기준이 아니어서 비교에서 제외했다. "
                "지방산림청·국립산림과학원 등 국유림 관리기관은 생산 기반과 경영 주체가 달라 "
                "지역 비교에서 제외했고, 2023년 강원·전북 특별자치도 전환으로 갈라진 명칭은 통합했다.",
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n분석 품목 {len(trends)}종 · 관측 {len(df):,}행")
    print("\n① 주요 품목 단가 추이 (물량가중, 원)")
    for i in FOCUS:
        if i in trends:
            t = trends[i]
            yrs = " → ".join(f"{r['가중평균단가']:,.0f}" for r in t["연도별"])
            print(f"  {i:6s} {yrs}  ({t['단가_변화율_pct']:+.1f}%) "
                  f"생산량 {t['생산량_변화율_pct']:+.1f}%")
    print("\n② 지역 단가 격차 (최신연도)")
    for i in FOCUS:
        if i in prem:
            p = prem[i]
            print(f"  {i:6s} 최고 {p['최고지역']} {p['최고단가']:,.0f}원 / "
                  f"최저 {p['최저지역']} {p['최저단가']:,.0f}원 ({p['지역격차_배']}배)")
    print("\n③ 가공 부가가치")
    for k, v in proc.items():
        print(f"  {k}: 단가 {v['단가_배수']}배 vs 손익분기 {v['손익분기_배수']}배 "
              f"→ {v['판정']} (원물 1kg당 {v['원물1kg당_가공수취액']:,.0f}원, "
              f"직판 대비 {v['원물직판대비_pct']:+.1f}%)")
    print("\n④ 지역 특화도 (LQ 상위)")
    for i in FOCUS:
        if i in spec and spec[i]["상위지역"]:
            t = spec[i]["상위지역"][0]
            print(f"  {i:6s} {t['시도']} LQ={t['LQ']} (전국 생산금액의 {t['전국비중_pct']:.1f}%)")
    print(f"\n[saved] {OUT}")


if __name__ == "__main__":
    main()
