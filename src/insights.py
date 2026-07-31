"""
Phase 2-C — 임산물생산비조사 심화 분석 (기술통계 계층)

Model A/B가 '얼마를 벌 수 있는가'를 예측한다면, 본 모듈은
**'어떻게 하면 더 벌 수 있는가'** 에 대한 정량 근거를 원데이터에서 직접 추출한다.

  ① 품질 등급별 단가 격차       — 밤(특대/대/중/소)
  ② 1차 가공 단계별 부가가치     — 떫은감(생감→반건시→건시→감말랭이), 대추(생/건), 표고(생/건)
  ③ 수령(樹齡)별 수익성 곡선     — 밤·대추·떫은감의 갱신·개식 의사결정 근거
  ④ 선도임가 vs 이외임가 격차   — 「경영수준별」 코드를 활용한 벤치마크
  ⑤ 지역×품목 수익성 지도

주의: 본 계층의 산출물은 **기술통계**이며 예측 모델의 설명변수로 사용하지 않는다.
평가액·수량은 사후(ex-post) 실적이므로 Model B에서는 전면 배제되어 있다.

산출: models/insights.json, reports/figures/insight_*.png
"""
from __future__ import annotations

import glob
import json
import os
import re

import matplotlib

matplotlib.use("Agg")
import koreanize_matplotlib  # noqa: F401
import matplotlib.pyplot as plt

plt.rcParams["axes.unicode_minus"] = False  # NanumGothic에 U+2212 글리프 없음
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "data", "임산물생산비조사")
MODEL_DIR = os.path.join(ROOT, "models")
FIG_DIR = os.path.join(ROOT, "reports", "figures")
OUT = os.path.join(MODEL_DIR, "insights.json")
os.makedirs(FIG_DIR, exist_ok=True)

GREEN, GREY, AMBER, RED = "#2E7D32", "#90A4AE", "#EF6C00", "#C62828"

# 품목별 (등급/가공형태 표시명, 수량 컬럼, 평가액 컬럼)
GRADE_SPECS: dict[str, list[tuple[str, str, str]]] = {
    "밤": [
        ("특대", "특대수량_단위당", "특대평가액_단위당"),
        ("대", "대수량_단위당", "대평가액_단위당"),
        ("중", "중수량_단위당", "중평가액_단위당"),
        ("소", "소수량_단위당", "소평가액_단위당"),
    ],
    "떫은감": [
        ("생감", "생감수량_단위당", "생감기준평가액_단위당"),
        ("반건시", "반건시수량_단위당", "반건시(생감기준)평가액_단위당"),
        ("건시", "건시수량_단위당", "건시(생감기준)평가액_단위당"),
        ("감말랭이", "감말랭이수량_단위당", "감말랭이(생감기준)평가액_단위당"),
    ],
    "대추": [
        ("생대추", "생대추수량_단위당", "생대추평가액_단위당"),
        ("건대추", "건대추_소계수량_단위당", "건대추_소계평가액_단위당"),
    ],
    "표고 노지": [
        ("생표고", "생표고_소계수량_단위당", "생표고_소계(생표고기준)평가액_단위당"),
        ("건표고", "건표고_소계(생표고기준)수량_단위당", "건표고_소계(생표고기준)평가액_단위당"),
    ],
}

GRADE_KIND = {"밤": "품질 등급", "떫은감": "가공 단계", "대추": "가공 형태", "표고 노지": "가공 형태"}

# 밤만이 '동일 산물의 품질 등급'이다. 나머지는 가공 형태 구분이며 수량 기준(원물/가공품)이
# 서로 달라 단가를 직접 비교하면 건조 감모율이 반영되지 않는다. 등급 전환 시뮬레이션은
# 밤에 대해서만 수행하고, 가공 품목은 단가 제시에 그친다.
QUALITY_GRADE_ITEMS = {"밤"}

# 「경영수준별」 코드가 연도별로 다르게 배포되어 있다 (2020~2022: 5/6, 2023~2024: 1/2).
LEVEL_HARMONIZE = {5: 1, 6: 2}


def norm(c: str) -> str:
    c = str(c).strip().replace("▣", "").strip()
    c = re.sub(r"(지출액|수량|시간|면적)[0-9]$", r"\1", c)
    c = re.sub(r"_(ha당|만본당)$", "_단위당", c)
    return c.replace(" ", "")


ITEM_RE = re.compile(r"^(\d{4})_(.+?)_\d{8}_\d+\.csv$")


def load_raw() -> pd.DataFrame:
    """정제 전 원자료를 적재한다 (평가액·수량 컬럼이 필요하므로 Model B 산출물은 못 씀)."""
    frames = []
    for p in sorted(glob.glob(os.path.join(SRC_DIR, "**", "*.csv"), recursive=True)):
        m = ITEM_RE.match(os.path.basename(p))
        if not m:
            continue
        for enc in ("cp949", "euc-kr", "utf-8-sig"):
            try:
                df = pd.read_csv(p, encoding=enc)
                break
            except Exception:  # noqa: BLE001
                continue
        else:
            continue
        df.columns = [norm(c) for c in df.columns]
        df = df.loc[:, ~df.columns.duplicated()]
        df = pd.concat([
            df,
            pd.DataFrame({"품목": m.group(2).replace("_", " "),
                          "조사연도": int(m.group(1))}, index=df.index),
        ], axis=1)
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True, sort=False)
    if "경영수준별" in raw.columns:
        raw["경영수준별"] = pd.to_numeric(raw["경영수준별"], errors="coerce").replace(LEVEL_HARMONIZE)
    return raw


def num(df: pd.DataFrame, c: str) -> pd.Series:
    if c not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[c], errors="coerce")


def robust_median(s: pd.Series) -> float | None:
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    s = s[s > 0]
    if len(s) < 20:
        return None
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    s = s[(s >= q1 - 1.5 * (q3 - q1)) & (s <= q3 + 1.5 * (q3 - q1))]
    return float(s.median()) if len(s) else None


# ---------------------------------------------------------------------------
# ① · ② 등급/가공 단계별 단가
# ---------------------------------------------------------------------------
def grade_unit_price(raw: pd.DataFrame) -> dict:
    out: dict = {}
    for item, specs in GRADE_SPECS.items():
        sub = raw[raw["품목"] == item]
        if sub.empty:
            continue
        rows = []
        qty_total = sum(num(sub, q).fillna(0) for _, q, _ in specs)
        n_sub = len(sub)
        for name, qcol, vcol in specs:
            q, v = num(sub, qcol), num(sub, vcol)
            if q.notna().sum() < 20 or v.notna().sum() < 20:
                continue
            price = robust_median(v / q.replace(0, np.nan))
            if price is None:
                continue
            produces = q > 0
            # 물량 비중은 '해당 산물을 실제로 생산하는 임가' 안에서의 중앙값이다.
            # 가공 형태는 임가마다 택일하는 경우가 많아 구분 간 합이 100%가 되지 않는다.
            share = robust_median((q[produces] / qty_total[produces].replace(0, np.nan)) * 100)
            rows.append({
                "구분": name,
                "단가_원per단위수량": round(price, 1),
                "생산임가_비율_pct": round(float(produces.mean()) * 100, 1),
                "생산임가내_물량비중_pct": round(share, 1) if share is not None else None,
                "표본": int(produces.sum()),
            })
        if len(rows) < 2:
            continue
        ordered = sorted(rows, key=lambda r: -r["단가_원per단위수량"])
        top, bottom = ordered[0], ordered[-1]
        out[item] = {
            "종류": GRADE_KIND.get(item, "구분"),
            "단위": "만본당" if "표고" in item else "ha당",
            "등급": rows,
            "최고_최저_단가배수": round(top["단가_원per단위수량"] / bottom["단가_원per단위수량"], 2)
            if bottom["단가_원per단위수량"] else None,
            "직접비교_가능": item in QUALITY_GRADE_ITEMS,
            "주석": (
                "동일 산물의 품질 등급이므로 단가를 직접 비교할 수 있다."
                if item in QUALITY_GRADE_ITEMS else
                "가공 형태 구분이며 수량 기준(원물/가공품)이 서로 달라 "
                "건조 감모율이 반영되지 않았다. 단가 수준의 참고치로만 해석한다."
            ),
        }
    return out


def simulate_grade_shift(raw: pd.DataFrame, insights: dict) -> dict:
    """품질 등급 구성이 개선될 때의 단위면적당 수취액 증가분.

    동일 산물의 등급 간 이동이므로 물량 보존이 성립하는 밤에 대해서만 수행한다.
    가공 형태 구분(떫은감·대추·표고)은 원물 대비 건조 감모가 발생해
    단순 물량 전환 가정이 성립하지 않으므로 제외한다.
    """
    sim = {}
    for item, info in insights.items():
        if item not in QUALITY_GRADE_ITEMS:
            continue
        rows = sorted(info["등급"], key=lambda r: -r["단가_원per단위수량"])
        if len(rows) < 2:
            continue
        sub = raw[raw["품목"] == item]
        total_qty = robust_median(
            sum(num(sub, q).fillna(0) for _, q, _ in GRADE_SPECS[item]).replace(0, np.nan)
        )
        if not total_qty:
            continue
        # 최하위 등급 물량의 10%p를 바로 위 등급으로 전환 (물량 보존)
        gain_per_kg = rows[-2]["단가_원per단위수량"] - rows[-1]["단가_원per단위수량"]
        shifted = total_qty * 0.10
        sim[item] = {
            "총수량_중앙값": round(total_qty, 1),
            "전환_시나리오": f"{rows[-1]['구분']} → {rows[-2]['구분']} 물량 10%p 전환",
            "단가차_원": round(gain_per_kg, 1),
            "수취액_증가_원per단위면적": round(gain_per_kg * shifted, 0),
            "가정": "물량 보존(동일 산물의 등급 간 이동). 선별·전정 등 품질관리 강화 시나리오.",
        }
    return sim


def plot_grade(insights: dict) -> str:
    items = [i for i in insights if len(insights[i]["등급"]) >= 2]
    if not items:
        return ""
    fig, axes = plt.subplots(1, len(items), figsize=(4.4 * len(items), 4.2))
    axes = np.atleast_1d(axes)
    for ax, item in zip(axes, items):
        rows = insights[item]["등급"]
        names = [r["구분"] for r in rows]
        prices = [r["단가_원per단위수량"] for r in rows]
        hi = int(np.argmax(prices))
        bars = ax.bar(names, prices, color=[GREEN if i == hi else GREY for i in range(len(rows))])
        for b, r in zip(bars, rows):
            lbl = f"{r['단가_원per단위수량']:,.0f}원"
            if r["생산임가_비율_pct"] is not None:
                lbl += f"\n생산 {r['생산임가_비율_pct']:.0f}%"
            ax.text(b.get_x() + b.get_width() / 2, r["단가_원per단위수량"], lbl,
                    ha="center", va="bottom", fontsize=8.5)
        ax.set_title(f"{item} — {insights[item]['종류']}별 단가", fontsize=11, fontweight="bold")
        ax.set_ylabel("단가 (원 / 수량단위)")
        ax.grid(axis="y", alpha=0.3)
        ax.margins(y=0.2)
    fig.suptitle("임산물 품질 등급·가공 형태별 단가 — 임산물생산비조사 원데이터\n"
                 "(막대 아래 '생산 N%' = 해당 형태를 실제 생산하는 임가 비율)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "insight_grade_price.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
# ③ 수령별 수익성 곡선
# ---------------------------------------------------------------------------
AGE_BINS = [0, 10, 15, 20, 25, 30, 40, 200]
AGE_LABELS = ["10년 이하", "11~15년", "16~20년", "21~25년", "26~30년", "31~40년", "40년 초과"]


def tree_age_curve(raw: pd.DataFrame) -> dict:
    out = {}
    for item in ["밤", "대추", "떫은감"]:
        sub = raw[raw["품목"] == item].copy()
        if "수령" not in sub.columns:
            continue
        sub["수령"] = num(sub, "수령")
        sub["소득"], sub["경영비"] = num(sub, "소득"), num(sub, "경영비")
        sub = sub[(sub["경영비"] > 0) & sub["수령"].between(1, 200)]
        if len(sub) < 100:
            continue
        sub["ROI"] = sub["소득"] / sub["경영비"] * 100
        q1, q3 = sub["ROI"].quantile([0.25, 0.75])
        sub = sub[sub["ROI"].between(q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1))]
        sub["수령구간"] = pd.cut(sub["수령"], AGE_BINS, labels=AGE_LABELS)
        g = sub.groupby("수령구간", observed=True).agg(
            ROI중앙값=("ROI", "median"), 표본=("ROI", "size")).round(1)
        g = g[g["표본"] >= 20]
        if g.empty:
            continue
        out[item] = {
            "구간": g.reset_index().to_dict("records"),
            "최고구간": str(g["ROI중앙값"].idxmax()),
            "최고ROI": float(g["ROI중앙값"].max()),
            "최저구간": str(g["ROI중앙값"].idxmin()),
            "최저ROI": float(g["ROI중앙값"].min()),
        }
    return out


def plot_age(curves: dict) -> str:
    if not curves:
        return ""
    fig, ax = plt.subplots(figsize=(9, 4.8))
    colors = [GREEN, AMBER, "#1565C0"]
    for (item, info), col in zip(curves.items(), colors):
        d = pd.DataFrame(info["구간"])
        ax.plot(d["수령구간"].astype(str), d["ROI중앙값"], "o-", lw=2.5, ms=7,
                color=col, label=f"{item} (n={d['표본'].sum():,})")
    ax.set_xlabel("수령 (樹齡)")
    ax.set_ylabel("단위면적당 ROI 중앙값 (%)")
    ax.set_title("수령별 수익성 곡선 — 갱신·개식 의사결정 근거", fontweight="bold")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "insight_tree_age.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
# ④ 선도임가 vs 이외임가
# ---------------------------------------------------------------------------
RATIO_SPEC = [
    ("노동비", "노동비_단위당"), ("비료비", "비료비_단위당"), ("농약비", "농약비_단위당"),
    ("감가상각비", "감가상각비_단위당"), ("위탁영농비", "위탁영농비_단위당"),
]


def leader_gap(raw: pd.DataFrame) -> dict:
    out = {}
    for item in GRADE_SPECS:
        sub = raw[raw["품목"] == item].copy()
        if "경영수준별" not in sub.columns:
            continue
        sub["경영수준별"] = num(sub, "경영수준별")
        sub["소득"], sub["경영비"] = num(sub, "소득"), num(sub, "경영비")
        sub = sub[(sub["경영비"] > 0) & sub["경영수준별"].isin([1, 2])]
        if len(sub) < 100:
            continue
        sub["ROI"] = sub["소득"] / sub["경영비"] * 100
        q1, q3 = sub["ROI"].quantile([0.25, 0.75])
        sub = sub[sub["ROI"].between(q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1))]

        rec: dict = {"표본": {"선도임가": int((sub["경영수준별"] == 1).sum()),
                            "이외임가": int((sub["경영수준별"] == 2).sum())}}
        for lvl, name in [(1, "선도임가"), (2, "이외임가")]:
            g = sub[sub["경영수준별"] == lvl]
            r = {"ROI중앙값": round(float(g["ROI"].median()), 1),
                 "경영비중앙값": round(float(g["경영비"].median()), 0)}
            for label, col in RATIO_SPEC:
                v = robust_median(num(g, col) / g["경영비"].replace(0, np.nan) * 100)
                if v is not None:
                    r[f"{label}_비중pct"] = round(v, 1)
            hours = num(g, "총노동시간_합계_단위당")
            hm = robust_median(hours)
            if hm is not None:
                r["총노동시간"] = round(hm, 0)
            rec[name] = r
        if "선도임가" in rec and "이외임가" in rec:
            rec["ROI격차_pp"] = round(rec["선도임가"]["ROI중앙값"] - rec["이외임가"]["ROI중앙값"], 1)
            rec["해석_유의"] = (
                "「선도임가」는 조사에서 성과를 기준으로 선정된 집단이므로 ROI 격차의 크기 자체는 "
                "부분적으로 정의상 내생적이다. 실무적으로 활용할 부분은 격차의 크기가 아니라 "
                "아래 비목 구성비·노동시간의 구조적 차이다."
            )
        out[item] = rec
    return out


def plot_leader(gaps: dict) -> str:
    items = list(gaps)
    if not items:
        return ""
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    x = np.arange(len(items))
    lead = [gaps[i]["선도임가"]["ROI중앙값"] for i in items]
    rest = [gaps[i]["이외임가"]["ROI중앙값"] for i in items]
    axes[0].bar(x - 0.2, lead, 0.4, label="선도임가", color=GREEN)
    axes[0].bar(x + 0.2, rest, 0.4, label="이외임가", color=GREY)
    for xi, (a, b) in enumerate(zip(lead, rest)):
        axes[0].text(xi, max(a, b), f"  격차 {a - b:+.0f}%p", ha="center", va="bottom",
                     fontsize=9, fontweight="bold", color=RED)
    axes[0].set_xticks(x, items)
    axes[0].set_ylabel("ROI 중앙값 (%)")
    axes[0].set_title("경영수준별 수익성 격차", fontweight="bold")
    axes[0].legend()
    axes[0].grid(axis="y", alpha=0.3)
    axes[0].margins(y=0.15)

    labels = [lab for lab, _ in RATIO_SPEC]
    w = 0.8 / max(len(items), 1)
    for k, item in enumerate(items):
        d = [gaps[item]["선도임가"].get(f"{lab}_비중pct", 0)
             - gaps[item]["이외임가"].get(f"{lab}_비중pct", 0) for lab in labels]
        axes[1].bar(np.arange(len(labels)) + k * w - 0.4 + w / 2, d, w, label=item)
    axes[1].axhline(0, color="#444", lw=1)
    axes[1].set_xticks(np.arange(len(labels)), labels)
    axes[1].set_ylabel("선도임가 − 이외임가 (%p)")
    axes[1].set_title("비목 구성비 차이 (양수 = 선도임가가 더 많이 지출)", fontweight="bold")
    axes[1].legend(fontsize=8)
    axes[1].grid(axis="y", alpha=0.3)

    fig.tight_layout()
    p = os.path.join(FIG_DIR, "insight_leader_gap.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
# ⑤ 지역 × 품목 수익성
# ---------------------------------------------------------------------------
REGION = {31: "경기", 32: "강원", 33: "충북", 34: "충남", 35: "전북", 36: "전남",
          37: "경북", 38: "경남", 39: "제주", 49: "특·광역시", 99: "기타"}


def region_matrix(raw: pd.DataFrame) -> tuple[dict, str]:
    d = raw.copy()
    d["소득"], d["경영비"] = num(d, "소득"), num(d, "경영비")
    d["지역별"] = num(d, "지역별")
    d = d[(d["경영비"] > 0) & d["지역별"].isin(REGION)]
    d["ROI"] = d["소득"] / d["경영비"] * 100
    q1, q3 = d["ROI"].quantile([0.25, 0.75])
    d = d[d["ROI"].between(q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1))]
    d["지역"] = d["지역별"].map(REGION)

    piv = d.pivot_table(index="지역", columns="품목", values="ROI", aggfunc="median")
    cnt = d.pivot_table(index="지역", columns="품목", values="ROI", aggfunc="size")
    piv = piv.where(cnt >= 15)
    piv = piv.dropna(how="all").dropna(axis=1, how="all")

    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    im = ax.imshow(piv.to_numpy(dtype=float), cmap="RdYlGn", aspect="auto")
    ax.set_xticks(range(len(piv.columns)), piv.columns)
    ax.set_yticks(range(len(piv.index)), piv.index)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.iloc[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v:,.0f}", ha="center", va="center", fontsize=9,
                        color="#111", fontweight="bold")
    fig.colorbar(im, ax=ax, label="ROI 중앙값 (%)")
    ax.set_title("지역 × 품목 수익성 지도 (표본 15건 이상)", fontweight="bold")
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "insight_region_item.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)

    best = {c: {"지역": str(piv[c].idxmax()), "ROI": round(float(piv[c].max()), 1)}
            for c in piv.columns if piv[c].notna().any()}
    return {"matrix": piv.round(1).to_dict(), "품목별_최적지역": best}, p


# ---------------------------------------------------------------------------
def main() -> None:
    raw = load_raw()
    print(f"[load] 원자료 {len(raw):,}행 · 품목 {raw['품목'].nunique()}종")

    grades = grade_unit_price(raw)
    sim = simulate_grade_shift(raw, grades)
    ages = tree_age_curve(raw)
    gaps = leader_gap(raw)
    region, fig_region = region_matrix(raw)

    result = {
        "등급별_단가": grades,
        "등급전환_시뮬레이션": sim,
        "수령별_수익성": ages,
        "선도임가_격차": gaps,
        "지역x품목": region,
        "figures": {
            k: os.path.relpath(v, ROOT) for k, v in {
                "grade_price": plot_grade(grades),
                "tree_age": plot_age(ages),
                "leader_gap": plot_leader(gaps),
                "region_item": fig_region,
            }.items() if v
        },
        "note": "본 계층은 기술통계이며 예측 모델의 설명변수로 사용하지 않는다. "
                "평가액·수량은 사후 실적이므로 Model B에서는 전면 배제되어 있다.",
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("\n① 등급/가공 단계별 단가")
    for item, info in grades.items():
        line = " · ".join(f"{r['구분']} {r['단가_원per단위수량']:,.0f}원" for r in info["등급"])
        print(f"  {item:8s} {line}  (최고/최저 {info['최고_최저_단가배수']}배)")
    print("\n② 등급 전환 시뮬레이션")
    for item, s in sim.items():
        print(f"  {item:8s} {s['전환_시나리오']} → {s['수취액_증가_원per단위면적']:+,.0f}원")
    print("\n③ 수령별 최고/최저 구간")
    for item, a in ages.items():
        print(f"  {item:8s} 최고 {a['최고구간']} {a['최고ROI']:,.0f}% / "
              f"최저 {a['최저구간']} {a['최저ROI']:,.0f}%")
    print("\n④ 선도임가 ROI 격차")
    for item, g in gaps.items():
        print(f"  {item:8s} {g.get('ROI격차_pp', 0):+.1f}%p "
              f"(선도 {g['선도임가']['ROI중앙값']:,.0f}% vs 이외 {g['이외임가']['ROI중앙값']:,.0f}%)")
    print(f"\n[saved] {OUT}")


if __name__ == "__main__":
    main()
