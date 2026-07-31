"""
Phase 2-F — 임업경영실태조사 분석 (판로·출하시기·인증의 경제적 가치)

출처: 산림청 국가승인통계 「임업경영실태조사」 (통계청 MDIS)
      밤나무재배업(2020) · 떫은감나무재배업(2020) · 버섯재배업(2020) · 임업경영인(2018)

이 조사만이 담고 있는 것
-----------------------
임가경제조사·임산물생산비조사는 '얼마를 투입해 얼마를 벌었나'를 기록하지만,
**임가가 실제로 선택한 경영 행동**은 담지 않는다. 본 조사에는 그것이 있다.

  · 출하시기 구성 (수확~추석 / 추석연휴 / 추석후~12월 / 1월~설 / 설 이후)
  · 판매처 구성 (농협·산림조합·수집상·가공업체·도소매상·직거래)
  · 저장 경험 및 저온저장고 보유
  · 친환경·GAP·지리적표시제 등 공식인증
  · 원물 판매 대 가공 판매

따라서 KAMIS 없이도 **임업통계만으로 출하시기의 가격 효과**를 추정할 수 있다.

추정 방법
---------
임가별로 관측되는 것은 '연간 총 판매수입 ÷ 총 판매량 = 평균 단가' 하나뿐이고,
시기별 단가는 직접 관측되지 않는다. 대신 임가마다 출하시기 구성비(합 100%)가
다르므로, 절편 없는 가중 최소제곱으로

    단가_i = Σ_k β_k · (시기 k 출하비율_i) + ε_i

를 추정하면 β_k 가 해당 시기의 평균 단가로 해석된다. 구성비의 합이 100%로
고정되어 있어 절편을 두지 않는다. 판매처 구성에도 같은 방법을 적용한다.

주의: 관측연구이므로 인과가 아니다. 저장 설비를 갖춘 임가가 애초에 규모·품질이
다를 수 있어, 추정된 시기별 단가 차이에는 선택효과가 섞여 있다. 이를 명시한다.

산출: models/management_insights.json, reports/figures/mgmt_*.png
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

plt.rcParams["axes.unicode_minus"] = False

import numpy as np
import pandas as pd
from scipy.optimize import nnls

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "data", "임업경영실태조사")
MODEL_DIR = os.path.join(ROOT, "models")
FIG_DIR = os.path.join(ROOT, "reports", "figures")
OUT = os.path.join(MODEL_DIR, "management_insights.json")
os.makedirs(FIG_DIR, exist_ok=True)

GREEN, GREY, AMBER, RED, BLUE = "#2E7D32", "#90A4AE", "#EF6C00", "#C62828", "#1565C0"

# 단위: 판매수입은 만원, 판매량은 kg. 파일설계서에 단위 표기가 없어
# 생산조사의 물량가중 단가(밤 2022년 2,429원/kg)와 대조해 확정했다.
REVENUE_UNIT_WON = 10_000

SHIP_ORDER = ["수확 ~ 추석 이전", "추석 연휴 판매", "추석이후 ~ 12월 31일",
              "1월 1일~설 이전", "설 이후"]
SHIP_SHORT = {"수확 ~ 추석 이전": "수확~추석", "추석 연휴 판매": "추석연휴",
              "추석이후 ~ 12월 31일": "추석후~12월", "1월 1일~설 이전": "1월~설",
              "설 이후": "설 이후"}
CHANNELS = ["농협", "산림조합", "수집상", "가공업체", "도소매상", "직거래", "기타"]

MIN_OBS = 25          # 계열별 최소 관측 수
UNIT_PRICE_BOUNDS = (200, 100_000)   # 원/kg — 단위 오기입 방어
MIN_SHARE_PCT = 3.0   # 평균 구성비가 이보다 낮은 계열은 식별이 불안정해 보고하지 않는다
N_BOOTSTRAP = 400     # 계수 신뢰구간 추정용 부트스트랩 반복


def load_one(path: str) -> tuple[str, int, pd.DataFrame]:
    name = os.path.basename(os.path.dirname(path)).split("_")[0]
    year = int(os.path.basename(path)[:4])
    for enc in ("cp949", "euc-kr", "utf-8-sig"):
        try:
            d = pd.read_csv(path, encoding=enc)
            break
        except Exception:  # noqa: BLE001
            continue
    else:
        raise RuntimeError(f"{path} 읽기 실패")
    d.columns = [str(c).strip() for c in d.columns]
    return name, year, d


def load_all() -> dict[str, tuple[int, pd.DataFrame]]:
    out = {}
    for p in sorted(glob.glob(os.path.join(SRC_DIR, "*", "2*.csv"))):
        name, year, d = load_one(p)
        out[name] = (year, d)
        print(f"[load] {name:16s} {year}  rows={len(d):,}  cols={d.shape[1]}")
    return out


def num(d: pd.DataFrame, c: str) -> pd.Series:
    return pd.to_numeric(d[c], errors="coerce") if c in d.columns else pd.Series(
        np.nan, index=d.index)


def unit_price(d: pd.DataFrame, rev: str, qty: str) -> pd.Series:
    r, q = num(d, rev), num(d, qty)
    p = (r * REVENUE_UNIT_WON) / q.replace(0, np.nan)
    lo, hi = UNIT_PRICE_BOUNDS
    return p.where((p >= lo) & (p <= hi))


# ---------------------------------------------------------------------------
# 구성비 → 계열별 단가 (절편 없는 가중 최소제곱)
# ---------------------------------------------------------------------------
def composition_price(price: pd.Series, shares: pd.DataFrame,
                      weights: pd.Series | None = None,
                      labels: list[str] | None = None) -> dict | None:
    """단가 = Σ β_k · 구성비_k 를 절편 없이 추정한다.

    구성비 합이 100%로 고정되어 있어 절편을 두면 식별되지 않는다.
    물량을 가중치로 주어 대규모 임가의 실제 거래가 더 반영되도록 한다.
    """
    X = shares.apply(pd.to_numeric, errors="coerce")
    keep = price.notna() & X.notna().all(axis=1) & (X.sum(axis=1) > 0)
    if keep.sum() < MIN_OBS:
        return None
    X = X[keep] / 100.0
    y = price[keep].to_numpy(dtype=float)
    w = (weights[keep].to_numpy(dtype=float) if weights is not None
         else np.ones(keep.sum()))
    w = np.where(np.isfinite(w) & (w > 0), w, np.nan)
    w = np.nan_to_num(w, nan=np.nanmedian(w) if np.isfinite(np.nanmedian(w)) else 1.0)
    sw = np.sqrt(w)

    Xa = X.to_numpy(dtype=float)
    A = Xa * sw[:, None]
    b = y * sw

    # 평균 구성비가 지나치게 낮은 계열은 계수가 소수 관측에 좌우되어 식별이 불안정하다
    mean_share = Xa.mean(axis=0) * 100
    used = mean_share >= MIN_SHARE_PCT
    if used.sum() < 2:
        return None

    # 단가는 음수가 될 수 없다. 비제약 최소제곱은 공선성이 있을 때 음수 계수를
    # 내놓으므로 비음수 최소제곱(NNLS)으로 추정한다.
    beta, _ = nnls(A[:, used], b)

    pred = A[:, used] @ beta
    ss_res = float(((b - pred) ** 2).sum())
    ss_tot = float((b ** 2).sum())

    # 부트스트랩으로 계수 불확실성을 함께 보고한다
    rng = np.random.default_rng(42)
    n = A.shape[0]
    boots = np.empty((N_BOOTSTRAP, int(used.sum())))
    for i in range(N_BOOTSTRAP):
        idx = rng.integers(0, n, n)
        try:
            boots[i], _ = nnls(A[idx][:, used], b[idx])
        except Exception:  # noqa: BLE001
            boots[i] = np.nan
    lo = np.nanpercentile(boots, 5, axis=0)
    hi = np.nanpercentile(boots, 95, axis=0)

    names = labels or list(shares.columns)
    coef, ci, shares_out = {}, {}, {}
    j = 0
    dropped, at_bound = [], []
    for i, nm in enumerate(names):
        if used[i]:
            coef[nm] = round(float(beta[j]), 1)
            ci[nm] = [round(float(lo[j]), 1), round(float(hi[j]), 1)]
            shares_out[nm] = round(float(mean_share[i]), 1)
            # NNLS가 0 경계에 붙은 계수는 '단가가 0원'이 아니라
            # 다른 계열과의 공선성 때문에 자료로 식별되지 않았다는 뜻이다.
            if beta[j] <= 1e-6:
                at_bound.append(nm)
            j += 1
        else:
            dropped.append(f"{nm}(평균비중 {mean_share[i]:.1f}%)")
    return {
        "계열단가": coef,
        "신뢰구간_90pct": ci,
        "표본": int(keep.sum()),
        "설명력_uncentered_R2": round(1 - ss_res / ss_tot, 3) if ss_tot else None,
        "평균구성비_pct": shares_out,
        "제외계열": dropped,
        "식별불가계열": at_bound,
        "추정": "비음수 최소제곱(NNLS), 물량가중, 절편 없음. "
                f"평균 구성비 {MIN_SHARE_PCT}% 미만 계열은 식별 불안정으로 제외. "
                + (f"{', '.join(at_bound)}은(는) 계수가 0 경계에 붙어 자료로 식별되지 "
                   "않았다(단가가 0원이라는 뜻이 아니다)." if at_bound else ""),
    }


# ---------------------------------------------------------------------------
def analyze_crop(name: str, year: int, d: pd.DataFrame, crop_word: str) -> dict:
    """밤·떫은감처럼 출하시기 문항이 있는 재배업 분석."""
    res: dict = {"조사연도": year, "표본": int(len(d))}

    price = unit_price(d, "판매수입_원물", "판매량_원물")
    qty = num(d, "판매량_원물")
    res["원물단가_원per_kg"] = {
        "중앙값": round(float(price.median()), 0) if price.notna().any() else None,
        "사분위": [round(float(price.quantile(q)), 0) for q in (0.25, 0.75)]
        if price.notna().any() else None,
        "유효표본": int(price.notna().sum()),
    }

    # --- ① 출하시기별 단가 ------------------------------------------------
    ship_cols = [c for c in d.columns if "출하시기" in c]
    if ship_cols:
        order = [c for lab in SHIP_ORDER for c in ship_cols if c.endswith(lab)]
        labels = [SHIP_SHORT[lab] for lab in SHIP_ORDER
                  for c in ship_cols if c.endswith(lab)]
        est = composition_price(price, d[order], qty, labels)
        if est:
            vals = {k: v for k, v in est["계열단가"].items()
                    if k not in est.get("식별불가계열", [])}
            if len(vals) < 2:
                vals = est["계열단가"]
            best = max(vals, key=vals.get)
            worst = min(vals, key=vals.get)
            est["최고시기"], est["최고단가"] = best, vals[best]
            est["최저시기"], est["최저단가"] = worst, vals[worst]
            est["격차_배"] = (round(vals[best] / vals[worst], 2)
                            if vals[worst] else None)
            est["주의"] = (
                "출하시기 문항은 저장 경험이 있는 임가만 응답하므로 표본이 선택적이다. "
                "추정치에는 저장 가능한 임가의 규모·품질 차이가 섞여 있어 인과효과가 아니다."
            )
            res["출하시기별_단가"] = est

    # --- ② 판매처별 단가 --------------------------------------------------
    ch_cols = [c for c in d.columns if "판매처 비율" in c]
    if ch_cols:
        order, labels = [], []
        for ch in CHANNELS:
            hit = [c for c in ch_cols if c.endswith(ch)]
            if hit:
                order.append(hit[0])
                labels.append(ch)
        est = composition_price(price, d[order], qty, labels)
        if est:
            vals = {k: v for k, v in est["계열단가"].items()
                    if k not in est.get("식별불가계열", [])}
            if len(vals) < 2:
                vals = est["계열단가"]
            est["최고판매처"] = max(vals, key=vals.get)
            est["최저판매처"] = min(vals, key=vals.get)
            est["격차_배"] = (round(vals[est["최고판매처"]] / vals[est["최저판매처"]], 2)
                            if vals[est["최저판매처"]] else None)
            res["판매처별_단가"] = est

    # --- ③ 저장 경험 유무 -------------------------------------------------
    if "저장경험" in d.columns:
        s = num(d, "저장경험")
        groups = {}
        for code, label in [(1, "저장경험 있음"), (2, "저장경험 없음")]:
            m = (s == code) & price.notna()
            if m.sum() >= MIN_OBS:
                groups[label] = {
                    "표본": int(m.sum()),
                    "단가중앙값": round(float(price[m].median()), 0),
                    "판매량중앙값": round(float(qty[m].median()), 0),
                }
        if len(groups) == 2:
            a, b = groups["저장경험 있음"], groups["저장경험 없음"]
            groups["단가차_pct"] = round(
                (a["단가중앙값"] / b["단가중앙값"] - 1) * 100, 1) if b["단가중앙값"] else None
            groups["주의"] = (
                "저장 설비·자금 여력이 있는 임가가 애초에 규모와 품질이 다를 수 있다. "
                "단가차는 저장의 순효과가 아니라 상관관계다."
            )
            res["저장경험별_단가"] = groups

    # --- ④ 공식인증 프리미엄 ----------------------------------------------
    cert_col = next((c for c in d.columns if "공식인증 인증여부" in c), None)
    if cert_col:
        s = num(d, cert_col)
        g = {}
        for code, label in [(1, "인증 보유"), (2, "인증 없음")]:
            m = (s == code) & price.notna()
            if m.sum() >= MIN_OBS:
                g[label] = {"표본": int(m.sum()),
                            "단가중앙값": round(float(price[m].median()), 0)}
        if len(g) == 2:
            g["프리미엄_pct"] = round(
                (g["인증 보유"]["단가중앙값"] / g["인증 없음"]["단가중앙값"] - 1) * 100, 1)
            res["공식인증_프리미엄"] = g

    # --- ⑤ 가공 판매 병행 여부 --------------------------------------------
    proc_rev = num(d, "판매수입_가공")
    raw_rev = num(d, "판매수입_원물")
    both = (proc_rev > 0) & (raw_rev > 0)
    only_raw = (proc_rev.fillna(0) == 0) & (raw_rev > 0)
    if both.sum() >= MIN_OBS and only_raw.sum() >= MIN_OBS:
        tot = (proc_rev.fillna(0) + raw_rev.fillna(0)) * REVENUE_UNIT_WON
        res["가공병행_효과"] = {
            "가공 병행": {"표본": int(both.sum()),
                       "임업총수입_중앙값": round(float(tot[both].median()), 0)},
            "원물만": {"표본": int(only_raw.sum()),
                    "임업총수입_중앙값": round(float(tot[only_raw].median()), 0)},
        }
        a = res["가공병행_효과"]["가공 병행"]["임업총수입_중앙값"]
        b = res["가공병행_효과"]["원물만"]["임업총수입_중앙값"]
        res["가공병행_효과"]["수입차_pct"] = round((a / b - 1) * 100, 1) if b else None

    return res


def analyze_manager(d: pd.DataFrame, year: int) -> dict:
    """임업경영인 조사 — 정책자금 수혜와 경영 성과."""
    res: dict = {"조사연도": year, "표본": int(len(d))}
    # 임업총수입·비용합계는 구간 코드(1~9)로 저장되어 있고 실제 금액은
    # '(대푯값)' 접두 컬럼에 만원 단위로 들어 있다. 코드 컬럼을 그대로 쓰면
    # ROI가 무의미한 값이 된다.
    rev = num(d, "(대푯값)임업총수입")
    cost = num(d, "(대푯값)비용합계")
    res["금액단위"] = "만원 (구간 대푯값)"
    m = (rev > 0) & (cost > 0)
    if m.sum() >= MIN_OBS:
        roi = (rev[m] - cost[m]) / cost[m] * 100
        q1, q3 = roi.quantile([0.25, 0.75])
        roi = roi[(roi >= q1 - 1.5 * (q3 - q1)) & (roi <= q3 + 1.5 * (q3 - q1))]
        res["ROI_pct"] = {"표본": int(len(roi)), "중앙값": round(float(roi.median()), 1),
                          "사분위": [round(float(roi.quantile(0.25)), 1),
                                   round(float(roi.quantile(0.75)), 1)]}

    col = next((c for c in d.columns if "임업정책자금 지원경험" in c), None)
    if col is not None and m.sum() >= MIN_OBS:
        s = num(d, col)
        g = {}
        for code, label in [(1, "정책자금 수혜"), (2, "미수혜")]:
            sel = (s == code) & m
            if sel.sum() >= MIN_OBS:
                r = (rev[sel] - cost[sel]) / cost[sel] * 100
                g[label] = {"표본": int(sel.sum()),
                            "ROI중앙값": round(float(r.median()), 1),
                            "임업총수입_중앙값": round(float(rev[sel].median()), 0)}
        if len(g) == 2:
            g["주의"] = ("정책자금은 신청·심사를 거치므로 수혜 임가가 애초에 "
                        "경영 의지와 규모에서 다르다. 선택편의가 있어 정책 효과가 아니다.")
            res["정책자금_수혜별"] = g
    return res


# ---------------------------------------------------------------------------
# 시각화
# ---------------------------------------------------------------------------
def plot_shipping(results: dict) -> str:
    crops = [k for k, v in results.items() if "출하시기별_단가" in v]
    if not crops:
        return ""
    fig, axes = plt.subplots(1, len(crops), figsize=(6.2 * len(crops), 4.4))
    axes = np.atleast_1d(axes)
    for ax, crop in zip(axes, crops):
        est = results[crop]["출하시기별_단가"]
        vals = est["계열단가"]
        names = [n for n in [SHIP_SHORT[s] for s in SHIP_ORDER] if n in vals]
        v = [vals[n] for n in names]
        hi = int(np.argmax(v))
        bars = ax.bar(names, v, color=[GREEN if i == hi else GREY for i in range(len(v))])
        for b, val, nm in zip(bars, v, names):
            ax.text(b.get_x() + b.get_width() / 2, val,
                    f"{val:,.0f}원\n(출하 {est['평균구성비_pct'].get(nm, 0):.0f}%)",
                    ha="center", va="bottom", fontsize=8.5)
        ax.set_title(f"{crop} — 출하시기별 추정 단가 (n={est['표본']})",
                     fontsize=11, fontweight="bold")
        ax.set_ylabel("원/kg")
        ax.grid(axis="y", alpha=0.3)
        ax.margins(y=0.22)
        ax.tick_params(axis="x", labelsize=9)
    fig.suptitle("임업경영실태조사 — 출하시기 구성비 회귀로 추정한 시기별 단가",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "mgmt_shipping_price.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def plot_channel(results: dict) -> str:
    crops = [k for k, v in results.items() if "판매처별_단가" in v]
    if not crops:
        return ""
    fig, axes = plt.subplots(1, len(crops), figsize=(5.8 * len(crops), 4.4))
    axes = np.atleast_1d(axes)
    for ax, crop in zip(axes, crops):
        est = results[crop]["판매처별_단가"]
        vals = est["계열단가"]
        items = sorted(vals.items(), key=lambda kv: kv[1])
        names = [k for k, _ in items]
        v = [x for _, x in items]
        ax.barh(names, v, color=[GREEN if i == len(v) - 1 else GREY for i in range(len(v))])
        for i, (nm, val) in enumerate(items):
            ax.text(val, i, f"  {val:,.0f}원 (비중 {est['평균구성비_pct'].get(nm, 0):.0f}%)",
                    va="center", fontsize=8.5)
        ax.set_title(f"{crop} — 판매처별 추정 단가 (n={est['표본']})",
                     fontsize=11, fontweight="bold")
        ax.set_xlabel("원/kg")
        ax.grid(axis="x", alpha=0.3)
        ax.margins(x=0.35)
    fig.suptitle("판매처 구성비 회귀로 추정한 채널별 수취 단가", fontsize=13, fontweight="bold")
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "mgmt_channel_price.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
def main() -> None:
    data = load_all()
    results: dict = {}

    for key, crop_word in [("밤나무재배업", "밤"), ("떫은감나무재배업", "떫은감"),
                           ("버섯재배업", "버섯")]:
        if key not in data:
            continue
        year, d = data[key]
        if key == "버섯재배업":
            # 버섯은 판매 항목이 생표고/건표고/톱밥배지로 나뉘어 컬럼명이 다르다
            rev = next((c for c in d.columns if re.match(r"생표고 판매 수입_원물$", c)), None)
            qty = next((c for c in d.columns if re.match(r"생표고 판매량_원물$", c)), None)
            if rev and qty:
                d = d.rename(columns={rev: "판매수입_원물", qty: "판매량_원물"})
        results[crop_word] = analyze_crop(key, year, d, crop_word)

    if "임업경영인" in data:
        y, d = data["임업경영인"]
        results["임업경영인"] = analyze_manager(d, y)

    figs = {k: v for k, v in {
        "shipping": plot_shipping(results),
        "channel": plot_channel(results),
    }.items() if v}

    out = {
        "출처": "산림청 국가승인통계 「임업경영실태조사」 (통계청 MDIS)",
        "품목별": results,
        "figures": {k: os.path.relpath(v, ROOT) for k, v in figs.items()},
        "추정방법": (
            "임가별로 관측되는 것은 연간 총 판매수입÷총 판매량인 평균 단가뿐이고 "
            "시기별·채널별 단가는 직접 관측되지 않는다. 임가마다 구성비가 다르다는 점을 이용해 "
            "단가 = Σ β_k · 구성비_k 를 절편 없이 물량가중 최소제곱으로 추정했다. "
            "구성비 합이 100%로 고정되어 절편은 식별되지 않는다."
        ),
        "단위근거": (
            "판매수입은 만원, 판매량은 kg. 파일설계서에 단위 표기가 없어 "
            "임산물생산조사의 밤 물량가중 단가(2022년 2,429원/kg)와 대조해 확정했다."
        ),
        "해석주의": (
            "관측연구이므로 인과가 아니다. 저장 설비·인증·정책자금은 모두 "
            "임가가 선택한 결과이며, 선택할 수 있었던 임가가 애초에 규모·자본·의지에서 "
            "다르다. 추정된 격차에는 선택효과가 섞여 있다."
        ),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    for crop, r in results.items():
        print(f"\n=== {crop} (n={r['표본']:,}, {r['조사연도']}년) ===")
        if "원물단가_원per_kg" in r and r["원물단가_원per_kg"]["중앙값"]:
            print(f"  원물 단가 중앙값 {r['원물단가_원per_kg']['중앙값']:,.0f}원/kg")
        if "출하시기별_단가" in r:
            e = r["출하시기별_단가"]
            print(f"  출하시기별 단가 (n={e['표본']}): "
                  + " · ".join(f"{k} {v:,.0f}" for k, v in e["계열단가"].items()))
            print(f"    최고 {e['최고시기']} {e['최고단가']:,.0f}원 / "
                  f"최저 {e['최저시기']} {e['최저단가']:,.0f}원 ({e['격차_배']}배)")
        if "판매처별_단가" in r:
            e = r["판매처별_단가"]
            print(f"  판매처별 단가 (n={e['표본']}): "
                  + " · ".join(f"{k} {v:,.0f}" for k, v in
                               sorted(e["계열단가"].items(), key=lambda kv: -kv[1])))
        if "저장경험별_단가" in r:
            e = r["저장경험별_단가"]
            print(f"  저장경험 있음 {e['저장경험 있음']['단가중앙값']:,.0f}원 vs "
                  f"없음 {e['저장경험 없음']['단가중앙값']:,.0f}원 ({e['단가차_pct']:+.1f}%)")
        if "공식인증_프리미엄" in r:
            e = r["공식인증_프리미엄"]
            print(f"  인증 보유 {e['인증 보유']['단가중앙값']:,.0f}원 vs "
                  f"없음 {e['인증 없음']['단가중앙값']:,.0f}원 ({e['프리미엄_pct']:+.1f}%)")
        if "정책자금_수혜별" in r:
            e = r["정책자금_수혜별"]
            print("  정책자금: " + " | ".join(
                f"{k} ROI {v['ROI중앙값']:,.1f}%" for k, v in e.items() if isinstance(v, dict)))

    print(f"\n[saved] {OUT}")


if __name__ == "__main__":
    main()
