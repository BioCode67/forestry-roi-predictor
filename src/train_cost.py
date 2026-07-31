"""
Phase 2-B — 임산물생산비조사 기반 품목별 ROI 예측 모델 (CUDA XGBoost + Optuna)

Model A(임가경제조사)가 '임가 단위 종합 수익성'을 예측한다면,
Model B(본 스크립트)는 '품목 단위 단위면적당 투입-산출 구조'를 학습해
비목별 지출·공정별 노동 배분까지 반영한 정밀 경영 진단을 제공한다.

벤치마크 3종은 Model A와 동일한 설계:
  a) 산림청 베이스라인 : 품목별×지역별 단순 그룹 평균
  b) 다중 선형회귀
  c) Optuna-XGBoost (5-fold CV 목적함수, GPU 병렬)

산출: models/best_xgboost_cost.json, models/metrics_cost.json,
      models/feature_schema_cost.json, reports/figures/cost_*.png
"""
from __future__ import annotations

import json
import os
import warnings

import matplotlib

matplotlib.use("Agg")
import koreanize_matplotlib  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import optuna
import pandas as pd
import xgboost as xgb
from sklearn.metrics import r2_score
from sklearn.model_selection import KFold, train_test_split

from preprocess_cost import CATEGORICALS, TARGET, feature_columns
from train_optuna import (
    FIG_DIR, MODEL_DIR, N_FOLDS, SEED, as_plain, build_linear, fwd, inv, metrics, worker_device,
)

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "processed_cost_data.parquet")
N_TRIALS = int(os.environ.get("N_TRIALS_COST", os.environ.get("N_TRIALS", 200)))
N_GPU = int(os.environ.get("N_GPU", 2))
N_JOBS = int(os.environ.get("N_JOBS", N_GPU * 3))


def to_cat(X: pd.DataFrame, cats: list[str], mapping: dict | None = None) -> pd.DataFrame:
    """범주형을 정수 코드 카테고리로 변환. '품목'은 문자열이므로 사전으로 정수화."""
    X = X.copy()
    for c in cats:
        if X[c].dtype == object:
            codes = mapping[c] if mapping else {v: i for i, v in enumerate(sorted(X[c].dropna().unique()))}
            X[c] = X[c].map(codes)
        X[c] = pd.Categorical(
            pd.to_numeric(X[c], errors="coerce").astype("Int64").fillna(-1).to_numpy(dtype="int64")
        )
    return X


def load_splits():
    df = pd.read_parquet(DATA)
    cats, nums = feature_columns(df)
    feats = cats + nums

    item_map = {v: i for i, v in enumerate(sorted(df["품목"].dropna().unique()))}
    X = to_cat(df[feats], cats, {"품목": item_map})
    y = df[TARGET].astype("float64")

    X_tr, X_tmp, y_tr, y_tmp, i_tr, i_tmp = train_test_split(
        X, y, df.index, test_size=0.2, random_state=SEED, stratify=df["품목"]
    )
    X_va, X_te, y_va, y_te, i_va, i_te = train_test_split(
        X_tmp, y_tmp, i_tmp, test_size=0.5, random_state=SEED
    )
    return (df, feats, cats, nums, item_map,
            (X_tr, y_tr, i_tr), (X_va, y_va, i_va), (X_te, y_te, i_te))


def baseline(df, idx_tr):
    """산림청 현행 공표 방식: 품목별×지역별 단순 산술평균."""
    tr = df.loc[idx_tr]
    grand = tr[TARGET].mean()
    g2 = tr.groupby(["품목", "지역별"], observed=True)[TARGET].mean()
    g1 = tr.groupby(["품목"], observed=True)[TARGET].mean()

    def predict(idx):
        sub = df.loc[idx]
        p = pd.Series(list(zip(sub["품목"], sub["지역별"])), index=sub.index).map(g2)
        return p.fillna(sub["품목"].map(g1)).fillna(grand).to_numpy(dtype=float)

    return predict, {"grand_mean_ROI_pct": float(grand),
                     "note": "학습셋의 품목별×지역별 단순 산술평균"}


def objective_factory(X_tr, y_tr):
    folds = list(KFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED).split(X_tr))
    y_arr = y_tr.to_numpy()

    def objective(trial: optuna.Trial) -> float:
        tkind = trial.suggest_categorical("target_transform", ["none", "signed_log"])
        params = {
            "objective": "reg:squarederror", "eval_metric": "rmse",
            "tree_method": "hist", "device": worker_device(), "seed": SEED, "nthread": 4,
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.3, log=True),
            "max_depth": trial.suggest_int("max_depth", 2, 12),
            "min_child_weight": trial.suggest_float("min_child_weight", 1e-2, 100.0, log=True),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.2, 1.0),
            "colsample_bylevel": trial.suggest_float("colsample_bylevel", 0.2, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 50.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 200.0, log=True),
            "gamma": trial.suggest_float("gamma", 1e-8, 20.0, log=True),
            "max_cat_to_onehot": trial.suggest_int("max_cat_to_onehot", 1, 12),
            "max_delta_step": trial.suggest_float("max_delta_step", 0.0, 10.0),
        }
        n_rounds = trial.suggest_int("n_estimators", 200, 3000)

        oof = np.zeros(len(X_tr))
        iters = []
        for tr_i, va_i in folds:
            dtr = xgb.QuantileDMatrix(X_tr.iloc[tr_i], label=fwd(y_arr[tr_i], tkind),
                                      enable_categorical=True)
            dva = xgb.QuantileDMatrix(X_tr.iloc[va_i], label=fwd(y_arr[va_i], tkind),
                                      enable_categorical=True, ref=dtr)
            bst = xgb.train(params, dtr, num_boost_round=n_rounds, evals=[(dva, "v")],
                            early_stopping_rounds=100, verbose_eval=False)
            iters.append(bst.best_iteration + 1)
            oof[va_i] = inv(bst.predict(dva, iteration_range=(0, bst.best_iteration + 1)), tkind)

        trial.set_user_attr("mean_best_iteration", int(np.mean(iters)))
        trial.set_user_attr("oof_r2", float(r2_score(y_arr, oof)))
        return float(np.sqrt(np.mean((oof - y_arr) ** 2)))

    return objective


def plot_benchmark(summary) -> str:
    labels = ["산림청 단순평균\n(품목×지역)", "다중 선형회귀", "Optuna-XGBoost\n(제안)"]
    keys = ["forest_service_baseline", "linear_regression", "optuna_xgboost"]
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2))
    for ax, m, tag in zip(axes, ["R2", "RMSE", "MAE"], ["↑ 우수", "↓ 우수", "↓ 우수"]):
        vals = [summary[k]["test"][m] for k in keys]
        bars = ax.bar(labels, vals, color=["#B0BEC5", "#78909C", "#1B5E20"])
        ax.set_title(f"{m} ({tag})", fontsize=11)
        ax.axhline(0, color="#444", lw=0.8)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v,
                    f"{v:.4f}" if m == "R2" else f"{v:,.1f}",
                    ha="center", va="bottom" if v >= 0 else "top", fontsize=10, fontweight="bold")
        ax.tick_params(axis="x", labelsize=8.5)
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle(f"품목별 단위면적당 ROI 예측 성능 — 임산물생산비조사 (Test n={summary['dataset']['test']})",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "cost_benchmark.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def plot_importance(booster, feats) -> str:
    gain = booster.get_score(importance_type="gain")
    s = pd.Series({f: gain.get(f, 0.0) for f in feats}).sort_values().tail(20)
    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.barh(s.index, s.to_numpy(), color="#1B5E20")
    ax.set_xlabel("Gain")
    ax.set_title("품목별 ROI 결정요인 상위 20개 — 비목·공정 단위", fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "cost_feature_importance.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def plot_item_roi(df) -> str:
    fig, ax = plt.subplots(figsize=(9, 4.6))
    items = df.groupby("품목", observed=True)[TARGET].median().sort_values()
    data = [df.loc[df["품목"] == i, TARGET].to_numpy() for i in items.index]
    bp = ax.boxplot(data, orientation="horizontal", tick_labels=list(items.index),
                    showfliers=False, patch_artist=True,
                    medianprops=dict(color="#C62828", lw=2))
    for patch in bp["boxes"]:
        patch.set_facecolor("#A5D6A7")
    ax.set_xlabel("단위면적당 ROI (%)  = 소득 ÷ 경영비 × 100")
    ax.set_title("품목별 ROI 분포 — 임산물생산비조사 (IQR 정제 후)", fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "cost_item_roi.png")
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def main() -> None:
    (df, feats, cats, nums, item_map,
     (X_tr, y_tr, i_tr), (X_va, y_va, i_va), (X_te, y_te, i_te)) = load_splits()
    print(f"[split] train={len(X_tr)} valid={len(X_va)} test={len(X_te)} features={len(feats)}")
    print(f"[gpu]   n_gpu={N_GPU} n_jobs={N_JOBS} trials={N_TRIALS} folds={N_FOLDS}")

    summary = {"dataset": {
        "rows": int(len(df)), "train": int(len(X_tr)), "valid": int(len(X_va)),
        "test": int(len(X_te)), "target": TARGET,
        "target_definition": "단위면적당 ROI(%) = 소득 ÷ 경영비 × 100",
        "unit_note": "밤·대추·떫은감은 ha당, 표고(노지)는 만본당 기준. ROI는 비율이므로 품목 간 비교 가능.",
        "n_features": len(feats), "seed": SEED,
        "items": df["품목"].value_counts().to_dict(),
        "source": "산림청 국가승인통계 임산물생산비조사 마이크로데이터 (통계청 MDIS)",
    }}

    fs_predict, fs_info = baseline(df, i_tr)
    summary["forest_service_baseline"] = {"test": metrics(y_te, fs_predict(i_te)), "info": fs_info}
    print("[a] 산림청 단순평균 :", summary["forest_service_baseline"]["test"])

    Xl, yl = pd.concat([X_tr, X_va]), pd.concat([y_tr, y_va])
    lin = build_linear(cats, nums).fit(as_plain(Xl, cats), yl)
    summary["linear_regression"] = {"test": metrics(y_te, lin.predict(as_plain(X_te, cats)))}
    print("[b] 다중 선형회귀  :", summary["linear_regression"]["test"])

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=SEED, multivariate=True, n_startup_trials=30),
        study_name="forestry_cost_roi_xgb",
    )
    study.optimize(objective_factory(X_tr, y_tr), n_trials=N_TRIALS, n_jobs=N_JOBS)

    bp = dict(study.best_params)
    tkind = bp.pop("target_transform")
    bp.pop("n_estimators")
    n_rounds = int(study.best_trial.user_attrs["mean_best_iteration"])
    print(f"[c] Optuna best CV-RMSE={study.best_value:.4f} "
          f"(OOF R²={study.best_trial.user_attrs['oof_r2']:.4f})")

    params = {"objective": "reg:squarederror", "eval_metric": "rmse",
              "tree_method": "hist", "device": "cuda:0", "seed": SEED, **bp}
    dfull = xgb.QuantileDMatrix(Xl, label=fwd(yl.to_numpy(), tkind), enable_categorical=True)
    booster = xgb.train(params, dfull, num_boost_round=max(n_rounds, 50), verbose_eval=False)

    pred = inv(booster.predict(xgb.DMatrix(X_te, enable_categorical=True)), tkind)
    summary["optuna_xgboost"] = {
        "test": metrics(y_te, pred),
        "cv_oof": {"RMSE": float(study.best_value),
                   "R2": float(study.best_trial.user_attrs["oof_r2"])},
        "best_params": params, "target_transform": tkind,
        "n_estimators": int(max(n_rounds, 50)), "n_trials": len(study.trials),
        "n_folds": N_FOLDS, "gpus_used": N_GPU,
    }
    print("[c] Optuna-XGBoost :", summary["optuna_xgboost"]["test"])

    b, x = summary["forest_service_baseline"]["test"], summary["optuna_xgboost"]["test"]
    summary["improvement_vs_baseline"] = {
        "R2_delta": x["R2"] - b["R2"],
        "RMSE_reduction_pct": (b["RMSE"] - x["RMSE"]) / b["RMSE"] * 100,
        "MAE_reduction_pct": (b["MAE"] - x["MAE"]) / b["MAE"] * 100,
    }

    # 품목별 Test 성능 분해
    te = df.loc[i_te].assign(_pred=pred, _true=y_te.to_numpy())
    summary["per_item_test"] = {
        item: metrics(g["_true"], g["_pred"]) | {"n": int(len(g))}
        for item, g in te.groupby("품목", observed=True) if len(g) >= 10
    }

    summary["figures"] = {
        "benchmark": os.path.relpath(plot_benchmark(summary), ROOT),
        "importance": os.path.relpath(plot_importance(booster, feats), ROOT),
        "item_roi": os.path.relpath(plot_item_roi(df), ROOT),
    }
    summary["feature_importance_gain"] = {
        k: float(v) for k, v in sorted(booster.get_score(importance_type="gain").items(),
                                       key=lambda kv: -kv[1])
    }

    # 품목별 비목 구조 프로파일 (대시보드 진단용)
    ratio_cols = [c for c in ["노동비_비중", "비료비_비중", "농약비_비중", "감가상각비_비중",
                              "위탁영농비_비중", "자가노동비율", "수확선별_노동비중",
                              "재배관리_노동비중"] if c in df.columns]
    prof = df.groupby("품목", observed=True)[ratio_cols + [TARGET, "경영비"]].median().round(4)
    prof.to_json(os.path.join(MODEL_DIR, "item_cost_profile.json"), force_ascii=False, indent=2)

    booster.save_model(os.path.join(MODEL_DIR, "best_xgboost_cost.json"))
    with open(os.path.join(MODEL_DIR, "feature_schema_cost.json"), "w", encoding="utf-8") as f:
        json.dump({
            "features": feats, "categorical": cats, "numeric": nums,
            "item_map": item_map, "target_transform": tkind,
            "categories": {c: sorted(int(v) for v in X_tr[c].cat.categories) for c in cats},
            "train_medians": {c: (None if pd.isna(v) else float(v))
                              for c, v in Xl[nums].median().items()},
            "item_medians": {
                item: {c: (None if pd.isna(v) else float(v)) for c, v in g[nums].median().items()}
                for item, g in df.groupby("품목", observed=True)
            },
        }, f, ensure_ascii=False, indent=2)
    with open(os.path.join(MODEL_DIR, "metrics_cost.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n=== Model B 벤치마크 (Test) ===")
    for k, label in [("forest_service_baseline", "산림청 단순평균"),
                     ("linear_regression", "다중 선형회귀"),
                     ("optuna_xgboost", "Optuna-XGBoost")]:
        m = summary[k]["test"]
        print(f"  {label:16s} R2={m['R2']:+.4f}  RMSE={m['RMSE']:8.2f}  MAE={m['MAE']:8.2f}")
    print("\n품목별 Test R²:",
          {k: round(v["R2"], 3) for k, v in summary["per_item_test"].items()})


if __name__ == "__main__":
    main()
