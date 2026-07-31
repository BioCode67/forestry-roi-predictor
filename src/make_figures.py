"""
제출용 도표 생성 — docs/figures/*.png

신청서 본문(10쪽)에 넣을 그림을 한자리에서 만듭니다. 화면 캡처와 달리 인쇄와
흑백 복사를 견뎌야 하므로, 색에만 의존하지 않고 수치를 함께 찍습니다.
"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "models")
OUT = os.path.join(ROOT, "docs", "figures")
os.makedirs(OUT, exist_ok=True)

# 한글 폰트 — 없으면 축 이름이 전부 네모로 나옵니다.
# 컨테이너에는 시스템 폰트가 없어 ~/.fonts를 matplotlib에 직접 등록합니다.
import glob
for f in glob.glob(os.path.expanduser("~/.fonts/*.ttf")) + glob.glob("/usr/share/fonts/**/*.ttf", recursive=True):
    try:
        fm.fontManager.addfont(f)
    except Exception:  # noqa: BLE001
        pass
_names = {f.name for f in fm.fontManager.ttflist}
for cand in ("NanumGothic", "NanumBarunGothic", "Malgun Gothic", "AppleGothic"):
    if cand in _names:
        plt.rcParams["font.family"] = cand
        break
else:
    print("[warn] 한글 폰트를 찾지 못했습니다 — 라벨이 네모로 나옵니다")
plt.rcParams.update({
    "axes.unicode_minus": False,
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.22,
    "axes.edgecolor": "#c2cacf",
    "axes.labelcolor": "#14181a",
    "text.color": "#14181a",
    "xtick.color": "#4b565c",
    "ytick.color": "#4b565c",
    "font.size": 10.5,
})

FOREST, AMBER, ROSE, SKY, GREY = "#2e7d4f", "#d97706", "#be123c", "#0284c7", "#94a3b8"


def J(name):
    with open(os.path.join(MODELS, name), encoding="utf-8") as f:
        return json.load(f)


def save(fig, name, credit=True):
    if credit:
        stamp(fig)
    p = os.path.join(OUT, name)
    fig.savefig(p, facecolor="white")
    plt.close(fig)
    print("  ", name)


def bare(ax, grid="y", left=False):
    """축 장식을 최대한 걷어낸다. 남는 건 데이터와 눈금 숫자뿐이다."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_visible(left)
    ax.spines["bottom"].set_color("#dbe2e6")
    ax.tick_params(length=0, pad=6)
    if grid != "none":
        ax.grid(axis=grid, color="#eceff1", linestyle="-", linewidth=0.9)
    ax.set_axisbelow(True)


def stamp(fig, text="자료: 산림청 국가승인통계 마이크로데이터  |  팀 임과 함께"):
    """출처를 도표 안에 박아 둔다. 문서에서 잘려 나가도 근거가 따라다닌다."""
    fig.text(0.995, 0.005, text, ha="right", va="top", fontsize=7.4,
             color="#a3adb3", transform=fig.transFigure)


# ── 그림 1. 3모델 성능 비교 ────────────────────────────────────────────────
def fig_benchmark():
    a, b = J("metrics_summary.json"), J("metrics_cost.json")
    names = ["산림청 방식\n(집단 평균)", "선형회귀", "Optuna XGBoost"]
    A = [a["forest_service_baseline"]["test"]["R2"],
         a["linear_regression"]["test"]["R2"], a["optuna_xgboost"]["test"]["R2"]]
    B = [b["forest_service_baseline"]["test"]["R2"],
         b["linear_regression"]["test"]["R2"], b["optuna_xgboost"]["test"]["R2"]]

    fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.9))
    for ax, vals, title, sub in zip(
            axes, [A, B],
            ["Model A — 임가경제조사 (n=4,438)", "Model B — 임산물생산비조사 (n=4,712)"],
            [f"베이스라인 대비 {A[2]/A[0]:.2f}배", f"베이스라인 대비 {B[2]/B[0]:.2f}배"]):
        cols = [GREY, GREY, FOREST]
        bars = ax.bar(names, vals, color=cols, width=0.55, zorder=3)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + max(vals) * 0.035,
                    f"{v:.4f}", ha="center", fontsize=10.5, fontweight="bold")
        ax.set_ylim(0, max(vals) * 1.28)
        ax.set_ylabel("Test R²")
        ax.set_title(f"{title}\n{sub}", fontsize=11, pad=11)
        bare(ax)
    fig.suptitle("동일 분할·동일 지표에서의 3종 모델 비교", fontsize=12.5,
                 fontweight="bold", y=1.045)
    save(fig, "fig01_benchmark.png")


# ── 그림 2. 데이터 누수 적발 ──────────────────────────────────────────────
def fig_leakage():
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.9))

    ax = axes[0]
    bars = ax.bar(["누수 피처 포함\n(1차 학습)", "누수 제거 후\n(최종)"], [0.9102, 0.6243],
                  color=[ROSE, FOREST], width=0.5, zorder=3)
    for bar, v in zip(bars, [0.9102, 0.6243]):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.03, f"{v:.4f}",
                ha="center", fontsize=11.5, fontweight="bold")
    ax.annotate("", xy=(1, 0.66), xytext=(0, 0.94),
                arrowprops=dict(arrowstyle="->", lw=1.8, color="#4b565c",
                                connectionstyle="arc3,rad=-.25"))
    ax.text(0.5, 1.04, "R² -0.286", ha="center", fontsize=11, color="#4b565c")
    ax.set_ylim(0, 1.18)
    ax.set_ylabel("Test R²")
    ax.set_title("성능은 내려갔지만 신뢰는 올라갔다", fontsize=11, pad=10)
    bare(ax)

    ax = axes[1]
    bars = ax.barh(["제거 전 최고 상관\n(건표고_소계수량)", "제거 후 최고 상관\n(노동비 비중)"],
                   [0.885, 0.344], color=[ROSE, FOREST], height=0.46, zorder=3)
    for bar, v in zip(bars, [0.885, 0.344]):
        ax.text(v + 0.025, bar.get_y() + bar.get_height() / 2, f"{v:.3f}",
                va="center", fontsize=11.5, fontweight="bold")
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("설명변수와 타깃(ROI)의 상관계수")
    ax.set_title("타깃을 그대로 담고 있던 변수를 제거", fontsize=11, pad=10)
    ax.invert_yaxis()
    bare(ax, grid="x")

    fig.suptitle("데이터 누수(Leakage) 자체 적발 및 교정 경위", fontsize=12.5,
                 fontweight="bold", y=1.045)
    save(fig, "fig02_leakage.png")


# ── 그림 3. 예측구간 신뢰도 ───────────────────────────────────────────────
def fig_coverage():
    q = J("metrics_quantile.json")
    fig, ax = plt.subplots(figsize=(7.4, 3.5))
    labels = ["Model A\n(임가경제조사)", "Model B\n(임산물생산비조사)"]
    cov = [q["roi"]["coverage_80pct"] * 100, q["cost"]["coverage_80pct"] * 100]
    bars = ax.bar(labels, cov, color=FOREST, width=0.42, zorder=3)
    ax.axhline(80, color=AMBER, linestyle="--", lw=1.8, zorder=4)
    ax.text(1.52, 80, "명목 80%", color=AMBER, va="center", fontsize=10.5,
            fontweight="bold")
    for bar, v in zip(bars, cov):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 1.6, f"{v:.1f}%",
                ha="center", fontsize=11.5, fontweight="bold")
    ax.set_ylim(0, 100)
    ax.set_ylabel("실측값이 P10~P90 안에 든 비율")
    ax.set_xlim(-0.6, 1.9)
    bare(ax)
    ax.set_title("분위수 회귀 예측구간의 실제 포함률\n"
                 "점추정만 제시하면 잡음이 큰 ROI를 확정값처럼 오독하기 쉽다",
                 fontsize=11.5, fontweight="bold", pad=12)
    save(fig, "fig03_coverage.png")


# ── 그림 4. 작목 위험-수익 지도 ───────────────────────────────────────────
def fig_portfolio():
    p = J("portfolio.json")
    fig, ax = plt.subplots(figsize=(7.6, 4.5))
    ax.scatter([d["vol"] for d in p["표본"]], [d["ret"] for d in p["표본"]],
               s=7, color=GREY, alpha=0.35, zorder=2, label="가능한 작목 조합 6,000가지")

    fr = p["효율선"]
    knee = int(np.argmin([d["vol"] for d in fr]))
    up = fr[knee:]
    lo = fr[:knee + 1]
    ax.plot([d["vol"] for d in lo], [d["ret"] for d in lo],
            color=GREY, lw=1.4, ls="--", zorder=3)
    ax.plot([d["vol"] for d in up], [d["ret"] for d in up],
            color=FOREST, lw=2.6, marker="o", ms=4.2, mfc="white",
            mec=FOREST, zorder=4, label="효율적 투자선")

    for r in p["품목"]:
        ax.scatter(r["연도변동_pct"], r["기대수익_pct"], s=78, color=AMBER,
                   edgecolor="white", lw=1.6, zorder=5)
        ax.annotate(r["품목"], (r["연도변동_pct"], r["기대수익_pct"]),
                    textcoords="offset points", xytext=(9, -3), fontsize=10)
    b = p["최고효율"]
    ax.scatter(b["연도변동_pct"], b["기대수익_pct"], s=160, marker="*",
               color=FOREST, edgecolor="white", lw=1.2, zorder=6)
    # 효율선 위에 겹치지 않도록 아래쪽 빈 곳으로 빼고, 점구름 위에서도 읽히게 흰 바탕을 깐다
    ax.annotate(f"최적 조합\n효율 {b['효율']}", (b["연도변동_pct"], b["기대수익_pct"]),
                textcoords="offset points", xytext=(26, -30), fontsize=9.5,
                color=FOREST, fontweight="bold", ha="center", zorder=7,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=FOREST, lw=0.9, alpha=0.95),
                arrowprops=dict(arrowstyle="-", lw=1.1, color=FOREST))

    ax.scatter([], [], s=78, color=AMBER, edgecolor="white", label="단일 작목")
    ax.set_xlabel("연도 간 변동성 σ (%p) — 작을수록 안정")
    ax.set_ylabel("기대 수익률 (%)")
    ax.legend(frameon=False, fontsize=9.5, loc="lower right")
    bare(ax, grid="both")
    ax.set_title("작목 조합의 위험–수익 지도 (평균–분산 접근)",
                 fontsize=11.5, fontweight="bold", pad=11)
    save(fig, "fig04_portfolio.png")


# ── 그림 5. 두 종류의 위험 ────────────────────────────────────────────────
def fig_risk_split():
    p = J("portfolio.json")
    rows = sorted(p["품목"], key=lambda r: -r["임가격차_pct"])
    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(8.2, 3.9))
    w = 0.36
    b1 = ax.bar(x - w / 2, [r["연도변동_pct"] for r in rows], w, color=FOREST,
                label="연도 효과 (작목을 섞으면 줄어듦)", zorder=3)
    b2 = ax.bar(x + w / 2, [r["임가격차_pct"] for r in rows], w, color=AMBER,
                label="임가 효과 (작목을 섞어도 줄지 않음)", zorder=3)
    for bars in (b1, b2):
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 3,
                    f"{bar.get_height():.0f}", ha="center", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels([r["품목"] for r in rows])
    ax.set_ylabel("표준편차 σ (%p)")
    ax.legend(frameon=False, fontsize=9.5)
    bare(ax)
    ratio = p["최고효율"]["임가격차_pct"] / p["최고효율"]["연도변동_pct"]
    ax.set_title(f"수익 분산의 원천 분해 — 임가 효과가 연도 효과의 {ratio:.0f}배\n"
                 "'무엇을 심을까'보다 '어떻게 할까'가 훨씬 크게 작용한다",
                 fontsize=11.5, fontweight="bold", pad=11)
    save(fig, "fig05_risk_split.png")


# ── 그림 6. 등급 전환 및 수령별 수익성 ────────────────────────────────────
def fig_insight():
    ins = J("insights.json")
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.9))

    ax = axes[0]
    g = ins["등급별_단가"]["밤"]["등급"]
    vals = [r["단가_원per단위수량"] for r in g]
    hi = int(np.argmax(vals))
    bars = ax.bar([r["구분"] for r in g], vals,
                  color=[FOREST if i == hi else GREY for i in range(len(g))],
                  width=0.55, zorder=3)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v + max(vals) * 0.03,
                f"{v:,.0f}", ha="center", fontsize=9.5)
    ax.set_ylabel("kg당 단가 (원)")
    sim = ins["등급전환_시뮬레이션"]["밤"]
    ax.set_title(f"밤 등급별 단가 — 최고/최저 {ins['등급별_단가']['밤']['최고_최저_단가배수']:.2f}배\n"
                 f"{sim['전환_시나리오']} 시 ha당 +{sim['수취액_증가_원per단위면적']:,.0f}원",
                 fontsize=10.5, pad=10)
    bare(ax)

    ax = axes[1]
    for i, (k, v) in enumerate(ins["수령별_수익성"].items()):
        xs = [r["수령구간"] for r in v["구간"]]
        ys = [r["ROI중앙값"] for r in v["구간"]]
        ax.plot(xs, ys, marker="o", ms=5, lw=2.2, label=k,
                color=[FOREST, AMBER, SKY][i % 3], zorder=3)
    ax.axhline(0, color="#c2cacf", lw=1, ls="--")
    ax.set_ylabel("ROI 중앙값 (%)")
    ax.legend(frameon=False, fontsize=9.5)
    ax.tick_params(axis="x", labelrotation=20)
    ax.set_title("수령 구간별 수익성 — 갱신 판단 근거", fontsize=10.5, pad=10)
    bare(ax)

    fig.suptitle("품질 관리·임목 갱신의 수익 기여 (임산물생산비조사)",
                 fontsize=12.5, fontweight="bold", y=1.045)
    save(fig, "fig06_insight.png")


# ── 그림 7. 파이프라인 구조도 ─────────────────────────────────────────────
def fig_pipeline():
    fig, ax = plt.subplots(figsize=(10.6, 4.6))
    ax.set_xlim(0, 100); ax.set_ylim(0, 64); ax.axis("off")

    def box(x, y, w, h, title, body, fc="#f4f7f8", ec="#c2cacf", tc="#14181a"):
        ax.add_patch(plt.Rectangle((x, y), w, h, facecolor=fc, edgecolor=ec,
                                   lw=1.2, zorder=2, joinstyle="round"))
        ax.text(x + w / 2, y + h - 4.2, title, ha="center", fontsize=9.8,
                fontweight="bold", color=tc, zorder=3)
        ax.text(x + w / 2, y + h / 2 - 2.6, body, ha="center", va="center",
                fontsize=8.2, color="#4b565c", zorder=3, linespacing=1.6)

    def arrow(x1, y1, x2, y2):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", lw=1.5, color="#6b767d"))

    ax.text(50, 61, "산림청 국가승인통계 마이크로데이터 (통계청 MDIS) + 공공 API",
            ha="center", fontsize=10.5, fontweight="bold")

    box(1, 42, 22, 16, "① 원자료 적재",
        "임가경제조사 2019~2023\n임산물생산비조사 2018~2024\n임산물생산조사 2022~2024\n임업경영실태조사 2018·2020")
    box(26, 42, 22, 16, "② 전처리",
        "CP949·구분자 자동판별\n파일설계서 코드북 파싱\n연도별 스키마 정규화\n품목별 IQR 이상치 제거")
    box(51, 42, 22, 16, "③ 누수 통제",
        "타깃 구성요소 정규식 차단\n사후(ex-post) 변수 제거\n상관 감사 0.885 → 0.344", fc="#fdf3e7", ec=AMBER)
    box(76, 42, 23, 16, "④ 파생변수",
        "ha당 경영비·자본\n로그 변환·비율 지표\n지역×업종 교차범주")

    box(76, 21, 23, 16, "⑤ 모델 학습",
        "XGBoost (CUDA, A6000×2)\nOptuna TPE 300/200 trial\n5-fold CV OOF RMSE 목적")
    box(51, 21, 22, 16, "⑥ 3종 벤치마크",
        "집단평균 · 선형회귀 · XGB\n동일 분할·동일 지표\nModel A ×4.05 / B ×5.95")
    box(26, 21, 22, 16, "⑦ 불확실성",
        "분위수 회귀 P10/P50/P90\n구간 포함률 78.2% / 76.5%\n(명목 80%)")
    box(1, 21, 22, 16, "⑧ 설명·처방",
        "TreeSHAP 기여 분해\n반사실(counterfactual) 탐색\n유사 임가 최근접 탐색", fc="#eef5f1", ec=FOREST)

    box(15, 2, 32, 14, "⑨ 분석 계층",
        "등급 전환 시뮬레이션 · 수령별 수익성\n지역 특화도(LQ) · 가공 손익분기\n작목 조합 위험분산 · 보조사업 지렛대")
    box(52, 2, 32, 14, "⑩ 서비스",
        "FastAPI + Vue 3 웹 애플리케이션\n임가 조건 입력 → 즉시 재계산\n쉬운 말 UI · 근거·한계 병기", fc="#eef5f1", ec=FOREST)

    for x in (23, 48, 73):          # 1행: 왼→오
        arrow(x, 50, x + 3, 50)
    arrow(87.5, 42, 87.5, 37.4)     # 1행 끝에서 2행으로 꺾임
    for x in (76, 51, 26):          # 2행: 오→왼
        arrow(x, 29, x - 3, 29)
    arrow(12, 21, 12, 16.4)         # 2행 끝에서 3행으로 꺾임
    arrow(47, 9, 52, 9)

    ax.set_title("분석 파이프라인 전 과정", fontsize=12.5,
                 fontweight="bold", y=1.0)
    save(fig, "fig07_pipeline.png")


# ── 그림 8. 활용 데이터 규모 ──────────────────────────────────────────────
def fig_data():
    rows = [
        ("임가경제조사\n2019~2023", 4438, "임업통계"),
        ("임산물생산비조사\n2018~2024", 4712, "임업통계"),
        ("임산물생산조사\n2022~2024", 196579, "임업통계"),
        ("임업경영실태조사\n2018·2020", 1200, "임업통계"),
        ("KAMIS 도매가격\n(aT)", 3650, "공공"),
        ("기상청 ASOS\n2019~2024", 1380, "공공"),
        ("보조사업 목록\n(산림청)", 42, "공공"),
    ]
    fig, ax = plt.subplots(figsize=(8.4, 4.2))
    y = np.arange(len(rows))[::-1]
    cols = [FOREST if r[2] == "임업통계" else SKY for r in rows]
    bars = ax.barh(y, [r[1] for r in rows], color=cols, height=0.58, zorder=3)
    ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rows], fontsize=9.5)
    ax.set_xscale("log")
    ax.set_xlabel("관측 수 (로그 눈금)")
    for bar, r in zip(bars, rows):
        ax.text(r[1] * 1.15, bar.get_y() + bar.get_height() / 2, f"{r[1]:,}",
                va="center", fontsize=9.5, fontweight="bold")
    ax.set_xlim(10, 1_500_000)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=FOREST, label="임업통계 (필수)"),
                       Patch(color=SKY, label="공공데이터 융복합")],
              frameon=False, fontsize=9.5, loc="lower right")
    bare(ax, grid="x")
    ax.set_title("활용 데이터 구성 — 임업통계 4종 + 공공데이터 3종",
                 fontsize=11.5, fontweight="bold", pad=11)
    save(fig, "fig08_data.png")




# ══════════════════════════════════════════════════════════════════════════
# 추가 도표 — 본문을 읽어 나가는 동안 눈이 쉬어 갈 곳을 만든다
# ══════════════════════════════════════════════════════════════════════════

# ── 그림 9. ROI 분포 — 평균이 대표값이 아니다 ─────────────────────────────
def fig_distribution():
    import pandas as pd
    df = pd.read_parquet(os.path.join(ROOT, "data", "processed_forestry_data.parquet"))
    roi = df["ROI"].dropna()
    roi = roi[(roi > -200) & (roi < 900)]

    fig, ax = plt.subplots(figsize=(9.2, 3.9))
    ax.hist(roi, bins=70, color=mixhex(FOREST, 0.72), edgecolor="white", linewidth=0.4, zorder=3)
    mean, med = roi.mean(), roi.median()
    for v, c, lab, off in [(mean, ROSE, f"평균 {mean:.0f}%", 14), (med, SKY, f"중앙값 {med:.0f}%", -68)]:
        ax.axvline(v, color=c, lw=2, ls="--", zorder=4)
        ax.annotate(lab, (v, ax.get_ylim()[1] * 0.86), xytext=(off, 0),
                    textcoords="offset points", color=c, fontsize=10.5, fontweight="bold")
    lo, hi = roi.quantile(0.1), roi.quantile(0.9)
    ax.axvspan(lo, hi, color=AMBER, alpha=0.08, zorder=1)
    ax.annotate(f"임가의 80%가 이 사이\n{lo:.0f}% ~ {hi:.0f}%",
                ((lo + hi) / 2, ax.get_ylim()[1] * 0.55), ha="center", fontsize=9.5,
                color="#8a5300", zorder=5)
    ax.set_xlabel("ROI (임업소득 ÷ 임업경영비, %)")
    ax.set_ylabel("임가 수")
    bare(ax)
    ax.set_title("임가 ROI 분포 — 평균은 대표값이 아니다\n"
                 "표준편차(216.7%p)가 평균(155.5%)보다 크다. "
                 "'평균 155%'를 그대로 전달하면 임가는 이를 보장값으로 읽는다",
                 fontsize=11.5, fontweight="bold", pad=12, loc="left")
    save(fig, "fig09_distribution.png")


def mixhex(hex_color, alpha):
    """흰 바탕과 섞어 옅은 색을 만든다 (인쇄에서 투명도는 신뢰할 수 없다)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    f = lambda c: int(c * alpha + 255 * (1 - alpha))  # noqa: E731
    return f"#{f(r):02x}{f(g):02x}{f(b):02x}"


# ── 그림 10. 품목별 성능 — 잘 안 되는 곳도 그대로 ─────────────────────────
def fig_per_item():
    b = J("metrics_cost.json")
    rows = sorted(b["per_item_test"].items(), key=lambda kv: -kv[1]["R2"])
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10.4, 3.7),
                                  gridspec_kw={"width_ratios": [1.5, 1]})

    names = [k for k, _ in rows]
    r2 = [v["R2"] for _, v in rows]
    cols = [FOREST if v > 0.3 else (AMBER if v > 0 else ROSE) for v in r2]
    bars = ax.bar(names, r2, color=cols, width=0.5, zorder=3)
    for bar, v in zip(bars, r2):
        ax.text(bar.get_x() + bar.get_width() / 2, v + (0.03 if v >= 0 else -0.07),
                f"{v:.3f}", ha="center", fontsize=10, fontweight="bold",
                va="bottom" if v >= 0 else "top")
    ax.axhline(0, color="#8b969c", lw=1)
    ax.set_ylim(-0.16, 0.78)
    ax.set_ylabel("Test R²")
    ax.set_title("품목별 예측 성능", fontsize=10.5, pad=9, loc="left")
    bare(ax)

    n = [v["n"] for _, v in rows]
    b2 = ax2.barh(names[::-1], n[::-1], color=GREY, height=0.5, zorder=3)
    for bar, v in zip(b2, n[::-1]):
        ax2.text(v + 4, bar.get_y() + bar.get_height() / 2, f"{v}건",
                 va="center", fontsize=9.5)
    ax2.set_xlim(0, max(n) * 1.28)
    ax2.set_title("테스트셋 표본 수", fontsize=10.5, pad=9, loc="left")
    bare(ax2, grid="x")

    fig.suptitle("품목별 성능은 표본 수를 그대로 따라간다 — 잘 안 되는 품목도 감추지 않았다",
                 fontsize=11.5, fontweight="bold", y=1.03, x=0.008, ha="left")
    save(fig, "fig10_per_item.png")


# ── 그림 11. 지역×품목 수익성 히트맵 ──────────────────────────────────────
def fig_heatmap():
    m = J("insights.json")["지역x품목"]["matrix"]
    items = list(m.keys())
    regions = sorted({r for it in items for r in m[it]})
    grid = np.array([[m[it].get(r) if m[it].get(r) is not None else np.nan
                      for it in items] for r in regions], dtype=float)

    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("roi", ["#f4dbe0", "#f7f6f2", "#bcdcc9", FOREST])
    cmap.set_bad("#f2f4f5")
    im = ax.imshow(grid, cmap=cmap, aspect="auto")
    ax.set_xticks(range(len(items))); ax.set_xticklabels(items)
    ax.set_yticks(range(len(regions))); ax.set_yticklabels(regions)
    for i in range(len(regions)):
        for j in range(len(items)):
            v = grid[i, j]
            if np.isnan(v):
                continue
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=9,
                    color="white" if v > 130 else "#22292d",
                    fontweight="bold" if v > 130 else "normal")
    ax.set_xticks(np.arange(-.5, len(items), 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(regions), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="minor", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    cb = fig.colorbar(im, ax=ax, shrink=0.72, pad=0.02)
    cb.set_label("ROI 중앙값 (%)", fontsize=9.5)
    cb.outline.set_visible(False)
    ax.set_title("어느 지역에서 무엇이 잘 되는가 — 지역×품목 수익성\n"
                 "조사 임가 15곳 이상인 조합만 표시. 회색은 자료가 적어 판단할 수 없는 칸",
                 fontsize=11.5, fontweight="bold", pad=12, loc="left")
    save(fig, "fig11_heatmap.png")


# ── 그림 12. 사례 연구 — SHAP 분해와 반사실 처방 ──────────────────────────
CASE_SHAP = [("경영비", -63.53), ("임지 규모", -41.53), ("작목", 31.09),
             ("전업 여부", 22.05), ("지역", 15.38), ("기준 연도", -11.98),
             ("경영주 연세", 6.03), ("일손", 3.56), ("재산", -2.56)]
CASE_BASE, CASE_PRED = 152.71, 111.04
CASE_CF = [(1500, 111.0), (900, 170.7), (750, 195.9), (600, 190.7)]


def fig_case():
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10.6, 4.0),
                                  gridspec_kw={"width_ratios": [1.15, 1]})

    rows = sorted(CASE_SHAP, key=lambda r: abs(r[1]))
    vals = [r[1] for r in rows]
    cols = [FOREST if v >= 0 else ROSE for v in vals]
    bars = ax.barh([r[0] for r in rows], vals, color=cols, height=0.62, zorder=3)
    for bar, v in zip(bars, vals):
        ax.text(v + (2.5 if v >= 0 else -2.5), bar.get_y() + bar.get_height() / 2,
                f"{v:+.1f}", va="center", ha="left" if v >= 0 else "right",
                fontsize=9.5, fontweight="bold")
    ax.axvline(0, color="#8b969c", lw=1)
    ax.set_xlim(-82, 48)
    ax.set_xlabel("예측 ROI에 대한 기여 (%p)")
    ax.set_title(f"① 왜 이 숫자인가 — 전체 평균 {CASE_BASE:.0f}% → 이 임가 {CASE_PRED:.0f}%",
                 fontsize=10.3, pad=9, loc="left")
    bare(ax, grid="x")

    x = [c[0] for c in CASE_CF]
    y = [c[1] for c in CASE_CF]
    order = np.argsort(x)
    ax2.plot(np.array(x)[order], np.array(y)[order], marker="o", ms=7, lw=2.6,
             color=FOREST, mfc="white", mec=FOREST, mew=2, zorder=4)
    ax2.axhline(152.3, color=AMBER, ls="--", lw=1.8, zorder=3)
    ax2.text(600, 152.3, "같은 조건 임가의 중앙값 152%", color=AMBER, fontsize=9,
             va="bottom", ha="left", fontweight="bold")
    ax2.scatter([1500], [111.0], s=140, color=ROSE, zorder=5, edgecolor="white", lw=1.6)
    ax2.annotate("지금", (1500, 111.0), xytext=(-12, 10), textcoords="offset points",
                 fontsize=9.5, color=ROSE, fontweight="bold", ha="right")
    ax2.scatter([750], [195.9], s=180, marker="*", color=FOREST, zorder=5,
                edgecolor="white", lw=1.2)
    ax2.annotate("권고 지점", (750, 195.9), xytext=(12, -6), textcoords="offset points",
                 fontsize=9.5, color=FOREST, fontweight="bold")
    ax2.set_ylim(98, 212)
    ax2.set_xlabel("한 해 임업경영비 (만원)")
    ax2.set_ylabel("예측 ROI (%)")
    ax2.set_title("② 무엇을 바꾸면 되는가 — 반사실 탐색", fontsize=10.3, pad=9, loc="left")
    bare(ax2, grid="both")

    fig.suptitle("사례 — 충남 5~10ha 밤 재배 임가(60대, 임업주업, 경영비 1,500만원)",
                 fontsize=11.5, fontweight="bold", y=1.035, x=0.008, ha="left")
    save(fig, "fig12_case.png")


# ── 그림 13. 지역 단가 프리미엄 ───────────────────────────────────────────
def fig_premium():
    d = J("production_insights.json")["지역단가프리미엄"]["밤"]
    rows = sorted(d["지역"], key=lambda r: r["전국대비_pct"])[-9:]
    fig, ax = plt.subplots(figsize=(8.4, 3.8))
    vals = [r["전국대비_pct"] for r in rows]
    cols = [FOREST if v >= 0 else ROSE for v in vals]
    bars = ax.barh([r["시도"] for r in rows], vals, color=cols, height=0.6, zorder=3)
    for bar, r in zip(bars, rows):
        v = r["전국대비_pct"]
        ax.text(v + (1.2 if v >= 0 else -1.2), bar.get_y() + bar.get_height() / 2,
                f"{v:+.1f}%  ({r['가중평균단가']:,.0f}원/kg)",
                va="center", ha="left" if v >= 0 else "right", fontsize=9.3)
    ax.axvline(0, color="#8b969c", lw=1)
    ax.set_xlim(min(vals) - 10, max(vals) + 22)
    ax.set_xlabel(f"전국 가중평균단가({d['전국_가중평균단가']:,.0f}원/kg) 대비 (%)")
    bare(ax, grid="x")
    ax.set_title(f"같은 밤이라도 지역에 따라 kg당 값이 다르다 ({d['연도']}년)\n"
                 "임산물생산조사 시군구 단위 집계 — 출하처 선택과 물류 판단의 근거",
                 fontsize=11.5, fontweight="bold", pad=12, loc="left")
    save(fig, "fig13_premium.png")


# ── 그림 14. 패널 구조 활용 — 작년 실적이 가진 힘 ─────────────────────────
def fig_panel():
    d = J("metrics_panel.json")
    g = d["임가단위_5회평균"]
    sd = d["임가단위_fold표준편차"]
    order = ["산림청 방식", "기존 22변수", "작년값 선형보정", "패널 변수 추가"]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10.6, 3.9),
                                  gridspec_kw={"width_ratios": [1.25, 1]})

    vals = [g[k]["R2"] for k in order]
    errs = [sd[k] for k in order]
    cols = [GREY, GREY, AMBER, FOREST]
    bars = ax.bar(order, vals, yerr=errs, color=cols, width=0.52, zorder=3,
                  error_kw=dict(ecolor="#7c878d", capsize=4, lw=1.2))
    for bar, v, e in zip(bars, vals, errs):
        ax.text(bar.get_x() + bar.get_width() / 2, v + e + 0.012, f"{v:.4f}",
                ha="center", fontsize=10.5, fontweight="bold")
    ax.set_ylim(0, max(vals) * 1.42)
    ax.set_ylabel("Test R²  (임가 단위 분할 5회 평균)")
    ax.tick_params(axis="x", labelrotation=8)
    ax.set_title("① 작년 실적 한 항목이 설명변수 22개보다 많은 것을 설명한다",
                 fontsize=10.3, pad=9, loc="left")
    bare(ax)

    yr = d["연도단위"]
    years = sorted(yr)
    x = np.arange(len(years))
    w = 0.26
    for i, (k, c) in enumerate([("산림청 방식", GREY), ("기존 22변수", SKY),
                                ("패널 변수 추가", FOREST)]):
        v = [yr[t][k]["R2"] for t in years]
        b = ax2.bar(x + (i - 1) * w, v, w, color=c, label=k, zorder=3)
        for bb, vv in zip(b, v):
            ax2.text(bb.get_x() + bb.get_width() / 2, vv + 0.008, f"{vv:.2f}",
                     ha="center", fontsize=8.6)
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"{t}년 시험\n(~{int(t)-1} 학습)" for t in years], fontsize=9.5)
    ax2.set_ylabel("Test R²")
    ax2.legend(frameon=False, fontsize=8.8, loc="upper left")
    ax2.set_ylim(0, 0.42)
    ax2.set_title("② 과거로 배워 미래를 맞히는 조건에서도 앞선다",
                  fontsize=10.3, pad=9, loc="left")
    bare(ax2)

    fig.suptitle("패널 구조 활용 — 같은 임가의 작년 실적을 쓰면 예측이 크게 나아진다",
                 fontsize=11.8, fontweight="bold", y=1.035, x=0.008, ha="left")
    save(fig, "fig14_panel.png")


# ── 그림 15. 분할 감사 ────────────────────────────────────────────────────
def fig_audit():
    a = J("audit_split.json")
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10.2, 3.5),
                                  gridspec_kw={"width_ratios": [1, 1.25]})

    frac = a["행단위_시험셋_임가중복_비율_pct"]
    ax.barh([""], [frac], color=ROSE, height=0.44, zorder=3)
    ax.barh([""], [100 - frac], left=[frac], color=mixhex(FOREST, 0.45), height=0.44, zorder=3)
    ax.text(frac / 2, 0, f"{frac:.1f}%", ha="center", va="center", color="white",
            fontsize=12, fontweight="bold")
    ax.text(frac + (100 - frac) / 2, 0, f"{100-frac:.1f}%", ha="center", va="center",
            fontsize=11, color="#22292d")
    ax.set_xlim(0, 100)
    ax.set_yticks([])
    ax.set_xlabel("시험셋 444행의 구성 (%)")
    ax.set_title("① 시험셋의 66.9%가 학습셋과 임가를 공유하고 있었다",
                 fontsize=10.2, pad=9, loc="left")
    ax.text(0, -0.62, "붉은색: 학습셋에도 있는 임가        연한 초록: 시험셋에만 있는 임가",
            fontsize=8.8, color="#6b767d", transform=ax.get_yaxis_transform())
    bare(ax, grid="none")

    row, grp = a["행단위"]["xgboost"]["R2"], a["임가단위_5회평균"]["xgboost"]["R2"]
    gsd = a["임가단위_5회평균"]["R2_표준편차"]
    bars = ax2.bar(["행 단위 분할\n(현행)", "임가 단위 분할\n(엄격)"], [row, grp],
                   yerr=[0, gsd], color=[GREY, FOREST], width=0.44, zorder=3,
                   error_kw=dict(ecolor="#7c878d", capsize=5, lw=1.2))
    for bar, v in zip(bars, [row, grp]):
        ax2.text(bar.get_x() + bar.get_width() / 2, v + gsd + 0.006, f"{v:.4f}",
                 ha="center", fontsize=11, fontweight="bold")
    ax2.set_ylim(0, 0.26)
    ax2.set_ylabel("Test R²")
    ax2.set_title(f"② 그런데도 차이는 {row-grp:+.4f} — fold 변동(±{gsd:.4f}) 안이다",
                  fontsize=10.2, pad=9, loc="left")
    bare(ax2)

    fig.suptitle("분할 감사 — 패널 자료를 행 단위로 나눈 것이 성능을 부풀렸는가",
                 fontsize=11.8, fontweight="bold", y=1.04, x=0.008, ha="left")
    save(fig, "fig15_audit.png")


if __name__ == "__main__":
    print("[figures]")
    fig_benchmark()
    fig_leakage()
    fig_coverage()
    fig_portfolio()
    fig_risk_split()
    fig_insight()
    fig_pipeline()
    fig_data()
    fig_distribution()
    fig_per_item()
    fig_heatmap()
    fig_case()
    fig_premium()
    fig_panel()
    fig_audit()
    print(f"→ {OUT}")
