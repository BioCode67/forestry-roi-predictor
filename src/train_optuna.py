"""
Phase 2 — CUDA XGBoost + Optuna 하이퍼파라미터 최적화 및 3종 모델 벤치마크

  a) 산림청 베이스라인 : 지역별×업종별 단순 그룹 평균 (현행 통계 공표 방식 모사)
  b) 다중 선형회귀     : 전통적 통계 모델
  c) Optuna-XGBoost    : 제안 모델 (tree_method='hist', device='cuda', 2×RTX A6000 병렬)

탐색 목적함수는 학습셋 5-fold 교차검증 OOF RMSE로, 단일 검증셋 과적합을 방지한다.
산출: models/best_xgboost_roi.json, models/metrics_summary.json,
      models/feature_schema.json, models/sector_profile.json, reports/figures/*.png
"""
from __future__ import annotations

import itertools
import json
import os
import threading
import warnings

import matplotlib

matplotlib.use("Agg")
import koreanize_matplotlib  # noqa: F401  (한글 폰트 등록)
import matplotlib.pyplot as plt
import numpy as np
import optuna
import pandas as pd
import xgboost as xgb
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from preprocess import feature_columns

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "processed_forestry_data.parquet")
MODEL_DIR = os.path.join(ROOT, "models")
FIG_DIR = os.path.join(ROOT, "reports", "figures")
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

SEED = 42
N_TRIALS = int(os.environ.get("N_TRIALS", 300))
N_FOLDS = 5
TARGET = "ROI"

# --- 다중 GPU 워커 할당 ------------------------------------------------------
N_GPU = int(os.environ.get("N_GPU", 2))
N_JOBS = int(os.environ.get("N_JOBS", N_GPU * 3))
_gpu_counter = itertools.count()
_local = threading.local()


def worker_device() -> str:
    """Optuna 워커 스레드마다 GPU를 라운드로빈 고정 배정."""
    if not hasattr(_local, "device"):
        _local.device = f"cuda:{next(_gpu_counter) % N_GPU}"
    return _local.device


# ---------------------------------------------------------------------------
def metrics(y_true, y_pred) -> dict[str, float]:
    return {
        "R2": float(r2_score(y_true, y_pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "MAE": float(mean_absolute_error(y_true, y_pred)),
    }


# ROI는 좌측 -100%로 절단되고 우측 꼬리가 긴 분포 → 부호보존 로그변환을 선택지로 둔다
def fwd(y, kind):
    return np.sign(y) * np.log1p(np.abs(y)) if kind == "signed_log" else y


def inv(z, kind):
    return np.sign(z) * (np.expm1(np.abs(z))) if kind == "signed_log" else z


def to_cat(X, cats):
    X = X.copy()
    for c in cats:
        # XGBoost 범주형은 numpy 정수 카테고리만 허용
        X[c] = pd.Categorical(X[c].astype("Int64").fillna(-1).to_numpy(dtype="int64"))
    return X


def load_splits():
    df = pd.read_parquet(DATA)
    cats, nums = feature_columns(df)
    feats = cats + nums

    X = to_cat(df[feats], cats)
    y = df[TARGET].astype("float64")

    # 80 / 10 / 10 (seed 42)
    X_tr, X_tmp, y_tr, y_tmp, i_tr, i_tmp = train_test_split(
        X, y, df.index, test_size=0.2, random_state=SEED
    )
    X_va, X_te, y_va, y_te, i_va, i_te = train_test_split(
        X_tmp, y_tmp, i_tmp, test_size=0.5, random_state=SEED
    )
    return df, feats, cats, nums, (X_tr, y_tr, i_tr), (X_va, y_va, i_va), (X_te, y_te, i_te)


# ---------------------------------------------------------------------------
# (a) 산림청 베이스라인 — 지역별×업종별 단순 평균
# ---------------------------------------------------------------------------
def forest_service_baseline(df, idx_tr):
    tr = df.loc[idx_tr]
    grand = tr[TARGET].mean()
    g2 = tr.groupby(["지역별", "업종별"], observed=True)[TARGET].mean()
    g1 = tr.groupby(["업종별"], observed=True)[TARGET].mean()

    def predict(idx):
        sub = df.loc[idx]
        p = pd.Series(list(zip(sub["지역별"], sub["업종별"])), index=sub.index).map(g2)
        p = p.fillna(sub["업종별"].map(g1)).fillna(grand)
        return p.to_numpy(dtype=float)

    return predict, {
        "grand_mean_ROI_pct": float(grand),
        "n_groups": int(g2.notna().sum()),
        "note": "학습셋(80%)의 지역별×업종별 단순 산술평균을 그대로 예측값으로 사용",
    }


# ---------------------------------------------------------------------------
# (b) 다중 선형회귀
# ---------------------------------------------------------------------------
def build_linear(cats, nums):
    return Pipeline([
        ("prep", ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore"), cats),
            ("num", StandardScaler(), nums),
        ])),
        ("lr", LinearRegression()),
    ])


def as_plain(X, cats):
    X = X.copy()
    for c in cats:
        X[c] = X[c].astype("int64")
    return X.astype("float64").replace([np.inf, -np.inf], np.nan).fillna(0.0)


# ---------------------------------------------------------------------------
# (c) Optuna-tuned XGBoost (CUDA, 5-fold CV objective)
# ---------------------------------------------------------------------------
def objective_factory(X_tr, y_tr):
    folds = list(KFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED).split(X_tr))
    y_arr = y_tr.to_numpy()

    def objective(trial: optuna.Trial) -> float:
        tkind = trial.suggest_categorical("target_transform", ["none", "signed_log"])
        params = {
            "objective": "reg:squarederror",
            "eval_metric": "rmse",
            "tree_method": "hist",
            "device": worker_device(),
            "seed": SEED,
            "nthread": 4,
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.3, log=True),
            "max_depth": trial.suggest_int("max_depth", 2, 10),
            "min_child_weight": trial.suggest_float("min_child_weight", 1e-2, 100.0, log=True),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
            "colsample_bylevel": trial.suggest_float("colsample_bylevel", 0.3, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 50.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 200.0, log=True),
            "gamma": trial.suggest_float("gamma", 1e-8, 20.0, log=True),
            "max_cat_to_onehot": trial.suggest_int("max_cat_to_onehot", 1, 12),
            "max_delta_step": trial.suggest_float("max_delta_step", 0.0, 10.0),
        }
        n_rounds = trial.suggest_int("n_estimators", 200, 3000)

        oof = np.zeros(len(X_tr), dtype=float)
        iters = []
        for tr_i, va_i in folds:
            dtr = xgb.QuantileDMatrix(
                X_tr.iloc[tr_i], label=fwd(y_arr[tr_i], tkind), enable_categorical=True
            )
            dva = xgb.QuantileDMatrix(
                X_tr.iloc[va_i], label=fwd(y_arr[va_i], tkind),
                enable_categorical=True, ref=dtr,
            )
            bst = xgb.train(
                params, dtr, num_boost_round=n_rounds,
                evals=[(dva, "v")], early_stopping_rounds=100, verbose_eval=False,
            )
            iters.append(bst.best_iteration + 1)
            oof[va_i] = inv(
                bst.predict(dva, iteration_range=(0, bst.best_iteration + 1)), tkind
            )

        trial.set_user_attr("mean_best_iteration", int(np.mean(iters)))
        trial.set_user_attr("oof_r2", float(r2_score(y_arr, oof)))
        return float(np.sqrt(mean_squared_error(y_arr, oof)))

    return objective


# ---------------------------------------------------------------------------
# 시각화
# ---------------------------------------------------------------------------
LABELS = ["산림청 단순평균\n(현행 베이스라인)", "다중 선형회귀", "Optuna-XGBoost\n(제안 모델)"]
KEYS = ["forest_service_baseline", "linear_regression", "optuna_xgboost"]


def plot_benchmark(summary: dict) -> str:
    n_test = summary["dataset"]["test"]
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2))
    for ax, m, better in zip(axes, ["R2", "RMSE", "MAE"], ["↑ 높을수록 우수", "↓ 낮을수록 우수", "↓ 낮을수록 우수"]):
        vals = [summary[k]["test"][m] for k in KEYS]
        bars = ax.bar(LABELS, vals, color=["#B0BEC5", "#78909C", "#2E7D32"])
        ax.set_title(f"{m}  ({better})", fontsize=11)
        ax.axhline(0, color="#444", lw=0.8)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v,
                    f"{v:.4f}" if m == "R2" else f"{v:,.1f}",
                    ha="center", va="bottom" if v >= 0 else "top",
                    fontsize=10, fontweight="bold")
        ax.tick_params(axis="x", labelsize=8.5)
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle(f"임가 ROI(%) 예측 모델 성능 비교 — Test set n={n_test}",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "benchmark_comparison.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def plot_importance(booster, feats) -> str:
    gain = booster.get_score(importance_type="gain")
    s = pd.Series({f: gain.get(f, 0.0) for f in feats}).sort_values().tail(15)
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    ax.barh(s.index, s.to_numpy(), color="#2E7D32")
    ax.set_xlabel("Gain (평균 분기 이득)")
    ax.set_title("XGBoost Feature Importance — 임가 ROI 결정요인 상위 15개", fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "feature_importance.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def plot_shap(booster, X_sample, feats):
    import shap

    booster.set_param({"device": "cuda:0"})
    expl = shap.TreeExplainer(booster)
    sv = expl.shap_values(xgb.DMatrix(X_sample, enable_categorical=True))
    Xn = as_plain(X_sample, [c for c in feats if str(X_sample[c].dtype) == "category"])
    plt.figure()
    shap.summary_plot(sv, Xn, feature_names=feats, show=False, max_display=15)
    plt.title("SHAP Summary — 변수별 ROI 기여도", fontweight="bold")
    p = os.path.join(FIG_DIR, "shap_summary.png")
    plt.savefig(p, dpi=150, bbox_inches="tight")
    plt.close("all")
    rank = dict(sorted(zip(feats, np.abs(sv).mean(axis=0).tolist()), key=lambda kv: -kv[1]))
    return p, {k: float(v) for k, v in rank.items()}


def plot_pred_vs_actual(y_te, preds: dict) -> str:
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.4), sharey=True, sharex=True)
    for ax, (name, p) in zip(axes, preds.items()):
        ax.scatter(y_te, p, s=12, alpha=0.45, color="#2E7D32")
        lo, hi = float(min(y_te.min(), p.min())), float(max(y_te.max(), p.max()))
        ax.plot([lo, hi], [lo, hi], "--", color="#C62828", lw=1)
        ax.set_title(f"{name}  (R²={r2_score(y_te, p):.4f})", fontsize=11)
        ax.set_xlabel("실측 ROI (%)")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("예측 ROI (%)")
    fig.suptitle("실측 대비 예측 산점도 (Test set)", fontsize=13, fontweight="bold")
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "pred_vs_actual.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def plot_sector_profile(df) -> str:
    prof = (df.groupby("업종별_라벨", observed=True)["ROI"]
              .agg(["median", "mean", "size"]).sort_values("median"))
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    ax.barh(prof.index, prof["median"], color="#33691E")
    ax.set_xlabel("임업 ROI 중앙값 (%)")
    ax.set_title("업종별 임업 ROI 프로파일 (2019~2023 통합, IQR 정제 후)", fontweight="bold")
    for i, (m, n) in enumerate(zip(prof["median"], prof["size"])):
        ax.text(m, i, f"  {m:.1f}%  (n={n})", va="center", fontsize=9)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "sector_roi_profile.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


# ---------------------------------------------------------------------------
def main() -> None:
    df, feats, cats, nums, (X_tr, y_tr, i_tr), (X_va, y_va, i_va), (X_te, y_te, i_te) = load_splits()
    print(f"[split] train={len(X_tr)} valid={len(X_va)} test={len(X_te)} features={len(feats)}")
    print(f"[gpu]   n_gpu={N_GPU} n_jobs={N_JOBS} trials={N_TRIALS} folds={N_FOLDS}")

    summary: dict = {
        "dataset": {
            "rows": int(len(df)), "train": int(len(X_tr)),
            "valid": int(len(X_va)), "test": int(len(X_te)),
            "target": TARGET, "target_unit": "%",
            "target_definition": "ROI(%) = 임업소득 / 임업경영비 × 100",
            "n_features": len(feats), "features": feats, "seed": SEED,
            "roi_train_mean": float(y_tr.mean()), "roi_train_std": float(y_tr.std()),
        }
    }
    preds: dict[str, np.ndarray] = {}

    # (a) 산림청 베이스라인
    fs_predict, fs_info = forest_service_baseline(df, i_tr)
    preds["산림청 단순평균"] = fs_predict(i_te)
    summary["forest_service_baseline"] = {
        "test": metrics(y_te, preds["산림청 단순평균"]),
        "valid": metrics(y_va, fs_predict(i_va)),
        "info": fs_info,
    }
    print("[a] 산림청 단순평균 :", summary["forest_service_baseline"]["test"])

    # (b) 선형회귀 — train+valid 학습
    Xl, yl = pd.concat([X_tr, X_va]), pd.concat([y_tr, y_va])
    lin = build_linear(cats, nums).fit(as_plain(Xl, cats), yl)
    preds["다중 선형회귀"] = lin.predict(as_plain(X_te, cats))
    summary["linear_regression"] = {
        "test": metrics(y_te, preds["다중 선형회귀"]),
        "valid": metrics(y_va, lin.predict(as_plain(X_va, cats))),
    }
    print("[b] 다중 선형회귀  :", summary["linear_regression"]["test"])

    # (c) Optuna XGBoost — 5-fold CV objective, 다중 GPU 병렬
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=SEED, multivariate=True, n_startup_trials=40),
        pruner=optuna.pruners.NopPruner(),
        study_name="forestry_roi_xgb",
    )
    study.optimize(objective_factory(X_tr, y_tr), n_trials=N_TRIALS, n_jobs=N_JOBS)

    bp = dict(study.best_params)
    tkind = bp.pop("target_transform")
    bp.pop("n_estimators")
    n_rounds = int(study.best_trial.user_attrs["mean_best_iteration"])
    print(f"[c] Optuna best CV-RMSE={study.best_value:.4f} "
          f"(OOF R²={study.best_trial.user_attrs['oof_r2']:.4f}) trials={len(study.trials)}")

    params = {
        "objective": "reg:squarederror", "eval_metric": "rmse",
        "tree_method": "hist", "device": "cuda:0", "seed": SEED, **bp,
    }
    # 최종 모델은 train+valid 전체(90%)로 재학습, 라운드 수는 CV에서 얻은 평균 최적값 사용
    dfull = xgb.QuantileDMatrix(Xl, label=fwd(yl.to_numpy(), tkind), enable_categorical=True)
    booster = xgb.train(params, dfull, num_boost_round=max(n_rounds, 50), verbose_eval=False)

    dte = xgb.DMatrix(X_te, enable_categorical=True)
    preds["Optuna-XGBoost"] = inv(booster.predict(dte), tkind)
    summary["optuna_xgboost"] = {
        "test": metrics(y_te, preds["Optuna-XGBoost"]),
        "cv_oof": {"RMSE": float(study.best_value),
                   "R2": float(study.best_trial.user_attrs["oof_r2"])},
        "best_params": params,
        "target_transform": tkind,
        "n_estimators": int(max(n_rounds, 50)),
        "n_trials": len(study.trials),
        "n_folds": N_FOLDS,
        "gpus_used": N_GPU,
    }
    print("[c] Optuna-XGBoost :", summary["optuna_xgboost"]["test"])

    b, x = summary["forest_service_baseline"]["test"], summary["optuna_xgboost"]["test"]
    summary["improvement_vs_baseline"] = {
        "R2_delta": x["R2"] - b["R2"],
        "R2_ratio": (x["R2"] / b["R2"]) if b["R2"] > 0 else None,
        "RMSE_reduction_pct": (b["RMSE"] - x["RMSE"]) / b["RMSE"] * 100,
        "MAE_reduction_pct": (b["MAE"] - x["MAE"]) / b["MAE"] * 100,
    }

    # 시각화
    figs = {
        "benchmark": plot_benchmark(summary),
        "importance": plot_importance(booster, feats),
        "pred_vs_actual": plot_pred_vs_actual(y_te, preds),
        "sector_profile": plot_sector_profile(df),
    }
    try:
        sp, rank = plot_shap(booster, X_te, feats)
        figs["shap"] = sp
        summary["shap_mean_abs"] = rank
    except Exception as e:  # noqa: BLE001
        print(f"[warn] SHAP 생략: {e}")
    summary["figures"] = {k: os.path.relpath(v, ROOT) for k, v in figs.items()}
    summary["feature_importance_gain"] = {
        k: float(v) for k, v in sorted(
            booster.get_score(importance_type="gain").items(), key=lambda kv: -kv[1])
    }

    # 업종별 ROI 프로파일 (대시보드 경영 개선 추천용)
    prof = (df.groupby("업종별_라벨", observed=True)
              .agg(ROI_중앙값=("ROI", "median"), ROI_평균=("ROI", "mean"),
                   ROI_상위25=("ROI", lambda s: s.quantile(0.75)),
                   임업경영비_중앙값=("임업경영비", "median"), n=("ROI", "size")).round(2))
    prof.to_json(os.path.join(MODEL_DIR, "sector_profile.json"), force_ascii=False, indent=2)

    booster.save_model(os.path.join(MODEL_DIR, "best_xgboost_roi.json"))
    with open(os.path.join(MODEL_DIR, "feature_schema.json"), "w", encoding="utf-8") as f:
        json.dump({
            "features": feats, "categorical": cats, "numeric": nums,
            "categories": {c: sorted(int(v) for v in X_tr[c].cat.categories) for c in cats},
            "target_transform": tkind,
            "train_medians": {c: float(pd.to_numeric(Xl[c], errors="coerce").median())
                              for c in nums},
        }, f, ensure_ascii=False, indent=2)
    with open(os.path.join(MODEL_DIR, "metrics_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n=== 최종 벤치마크 (Test, n=%d) ===" % len(X_te))
    for k, label in zip(KEYS, ["산림청 단순평균", "다중 선형회귀", "Optuna-XGBoost"]):
        m = summary[k]["test"]
        print(f"  {label:16s} R2={m['R2']:+.4f}  RMSE={m['RMSE']:8.2f}  MAE={m['MAE']:8.2f}")
    imp = summary["improvement_vs_baseline"]
    print(f"  → 베이스라인 대비 RMSE {imp['RMSE_reduction_pct']:.1f}% ↓, "
          f"MAE {imp['MAE_reduction_pct']:.1f}% ↓")


if __name__ == "__main__":
    main()
