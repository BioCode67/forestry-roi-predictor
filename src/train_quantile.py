"""
Phase 2-D — 분위수 회귀로 ROI 예측구간 산출

임가 ROI는 기상·병충해·시장가격 등 관측되지 않는 요인의 영향을 크게 받는,
본질적으로 잡음이 큰 변수다. 점추정(平均)만 제시하면 "45%를 번다"로 오독되기 쉽다.
본 모듈은 XGBoost의 분위수 손실(`reg:quantileerror`)로 P10·P50·P90을 학습해
**"중앙값 45%, 하위 10% 12% ~ 상위 10% 88%"** 형태의 구간 예측을 제공한다.

탐색 비용을 아끼기 위해 각 모델(A/B)의 Optuna 최적 하이퍼파라미터를 재사용하고,
분위수 손실로만 바꿔 재학습한다. 평가지표는 예측구간이 실제로 명목 수준을
지키는지 보는 **구간 포함률(coverage)** 과 **핀볼 손실(pinball loss)** 이다.

산출: models/quantile_{roi,cost}_p{10,50,90}.json, models/metrics_quantile.json
"""
from __future__ import annotations

import json
import os
import warnings

import matplotlib

matplotlib.use("Agg")
import koreanize_matplotlib  # noqa: F401
import matplotlib.pyplot as plt

plt.rcParams["axes.unicode_minus"] = False

import numpy as np
import pandas as pd
import xgboost as xgb

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(ROOT, "models")
FIG_DIR = os.path.join(ROOT, "reports", "figures")
os.makedirs(FIG_DIR, exist_ok=True)

QUANTILES = [0.10, 0.50, 0.90]
# 분위수 손실은 목표변수 스케일에 직접 작용하므로 로그변환을 적용하지 않는다
# (변환 공간의 분위수는 역변환해도 원공간 분위수와 일치하지만, 해석을 단순히 하기 위해
#  원공간에서 직접 학습한다).


def pinball(y, pred, q) -> float:
    d = y - pred
    return float(np.mean(np.maximum(q * d, (q - 1) * d)))


def train_one(model_key: str, loader, best_params: dict, n_rounds: int) -> dict:
    """model_key: 'roi'(Model A) 또는 'cost'(Model B)"""
    X_tr, y_tr, X_va, y_va, X_te, y_te, feats = loader()

    Xl = pd.concat([X_tr, X_va])
    yl = pd.concat([y_tr, y_va])

    params = {k: v for k, v in best_params.items()
              if k not in ("objective", "eval_metric", "quantile_alpha")}
    params.update({
        "objective": "reg:quantileerror",
        "quantile_alpha": QUANTILES,
        "tree_method": "hist",
        "device": "cuda:0",
    })

    dfull = xgb.QuantileDMatrix(Xl, label=yl.to_numpy(), enable_categorical=True)
    booster = xgb.train(params, dfull, num_boost_round=n_rounds, verbose_eval=False)

    pred = booster.predict(xgb.DMatrix(X_te, enable_categorical=True))
    if pred.ndim == 1:  # 단일 분위수로 축약된 경우 방어
        pred = pred.reshape(-1, 1)
    # 분위수 교차(quantile crossing) 방지 — 행별 정렬
    pred = np.sort(pred, axis=1)

    y = y_te.to_numpy()
    p10, p50, p90 = pred[:, 0], pred[:, 1], pred[:, 2]
    res = {
        "quantiles": QUANTILES,
        "n_test": int(len(y)),
        "coverage_80pct": float(np.mean((y >= p10) & (y <= p90))),
        "coverage_below_p10": float(np.mean(y < p10)),
        "coverage_above_p90": float(np.mean(y > p90)),
        "median_interval_width": float(np.median(p90 - p10)),
        "pinball": {f"P{int(q*100)}": pinball(y, pred[:, i], q)
                    for i, q in enumerate(QUANTILES)},
        "p50_mae": float(np.mean(np.abs(y - p50))),
        "n_estimators": n_rounds,
    }

    booster.save_model(os.path.join(MODEL_DIR, f"quantile_{model_key}.json"))
    plot_intervals(model_key, y, p10, p50, p90, res)
    return res


def plot_intervals(key: str, y, p10, p50, p90, res) -> str:
    order = np.argsort(p50)
    n = min(len(y), 300)
    idx = order[np.linspace(0, len(order) - 1, n).astype(int)]

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4))
    ax = axes[0]
    ax.fill_between(range(n), p10[idx], p90[idx], color="#A5D6A7", alpha=0.7,
                    label="P10~P90 예측구간")
    ax.plot(range(n), p50[idx], color="#2E7D32", lw=2, label="P50 (중앙값 예측)")
    ax.scatter(range(n), y[idx], s=9, color="#37474F", alpha=0.55, label="실측")
    ax.set_xlabel("임가 (P50 예측값 오름차순 정렬)")
    ax.set_ylabel("ROI (%)")
    ax.set_title(f"예측구간과 실측 — 구간 포함률 {res['coverage_80pct']*100:.1f}% "
                 f"(명목 80%)", fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)

    ax = axes[1]
    width = p90 - p10
    ax.hist(width, bins=40, color="#2E7D32", alpha=0.85)
    ax.axvline(res["median_interval_width"], color="#C62828", ls="--", lw=2,
               label=f"중앙값 {res['median_interval_width']:,.0f}%p")
    ax.set_xlabel("예측구간 폭 (P90 − P10, %p)")
    ax.set_ylabel("임가 수")
    ax.set_title("불확실성 폭 분포", fontweight="bold")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle(f"{'Model A — 임가경제조사' if key == 'roi' else 'Model B — 임산물생산비조사'}"
                 " 분위수 회귀 예측구간", fontsize=13, fontweight="bold")
    fig.tight_layout()
    p = os.path.join(FIG_DIR, f"quantile_{key}.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
def loader_a():
    from train_optuna import load_splits
    df, feats, cats, nums, (X_tr, y_tr, _), (X_va, y_va, _), (X_te, y_te, _) = load_splits()
    return X_tr, y_tr, X_va, y_va, X_te, y_te, feats


def loader_b():
    from train_cost import load_splits
    (df, feats, cats, nums, item_map,
     (X_tr, y_tr, _), (X_va, y_va, _), (X_te, y_te, _)) = load_splits()
    return X_tr, y_tr, X_va, y_va, X_te, y_te, feats


def main() -> None:
    out: dict = {}
    specs = [
        ("roi", loader_a, "metrics_summary.json", "Model A (임가경제조사)"),
        ("cost", loader_b, "metrics_cost.json", "Model B (임산물생산비조사)"),
    ]
    for key, loader, metrics_file, label in specs:
        mp = os.path.join(MODEL_DIR, metrics_file)
        if not os.path.exists(mp):
            print(f"[skip] {label}: {metrics_file} 없음 (본 모델 학습을 먼저 실행)")
            continue
        with open(mp, encoding="utf-8") as f:
            m = json.load(f)
        bp = m["optuna_xgboost"]["best_params"]
        n_rounds = int(m["optuna_xgboost"]["n_estimators"])
        print(f"[train] {label} — 분위수 {QUANTILES}, rounds={n_rounds}")
        res = train_one(key, loader, bp, n_rounds)
        res["label"] = label
        out[key] = res
        print(f"        구간 포함률 {res['coverage_80pct']*100:.1f}% (명목 80%) · "
              f"구간폭 중앙값 {res['median_interval_width']:,.1f}%p · "
              f"P50 MAE {res['p50_mae']:,.2f}")

    if out:
        out["note"] = (
            "구간 포함률(coverage)은 실측값이 P10~P90 구간에 들어간 비율이며 명목 수준은 80%다. "
            "이 값이 80%에 가까우면 예측구간이 신뢰할 만하다는 뜻이다. "
            "점추정만 제시하면 잡음이 큰 ROI를 확정값처럼 오독하기 쉬우므로, "
            "대시보드는 중앙값과 함께 구간을 제시한다."
        )
        with open(os.path.join(MODEL_DIR, "metrics_quantile.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\n[saved] {MODEL_DIR}/metrics_quantile.json")


if __name__ == "__main__":
    main()
