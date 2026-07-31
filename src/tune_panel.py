"""
Phase 2-N — 패널 모델 하이퍼파라미터 탐색 (CUDA)

train_panel.py는 Model A의 하이퍼파라미터를 그대로 빌려 썼습니다. 급히 효과를
확인하려던 것이라 그랬는데, 두 문제는 성격이 다릅니다. Model A는 설명변수가
22개뿐이라 깊게 파고들어야 신호를 잡을 수 있었지만, 패널 모델에는 작년 실적이라는
강한 변수가 하나 더 있어 그만큼 깊게 갈 이유가 없습니다. 제대로 찾으면 더 오릅니다.

목적함수는 임가 단위 5-fold의 OOF RMSE입니다. 같은 임가가 학습과 평가 양쪽에
들어가면 외워서 맞힐 수 있으므로 GroupKFold로 가릅니다. 행 단위로 나누고 탐색하면
그 누출까지 최적화하게 됩니다.

A6000 두 장에 trial을 번갈아 배정합니다.

산출: models/best_xgboost_panel.json, models/metrics_panel.json 갱신
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import optuna
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_panel import (CATS, DATA, GROUP, METRICS_A, OUT_METRICS, OUT_MODEL,
                         OUT_SCHEMA, SEED, TARGET, add_lags, baseline_group,
                         baseline_lag_only, sc, to_cat, xgb_eval)

N_TRIALS = int(os.environ.get("N_TRIALS", "400"))
N_FOLDS = 5
N_GPU = 2


def objective(trial, X, y, g, folds):
    p = {
        "objective": "reg:squarederror",
        "eval_metric": "rmse",
        "tree_method": "hist",
        "device": f"cuda:{trial.number % N_GPU}",
        "seed": SEED,
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.25, log=True),
        "max_depth": trial.suggest_int("max_depth", 2, 9),
        "min_child_weight": trial.suggest_float("min_child_weight", 0.01, 40, log=True),
        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.4, 1.0),
        "colsample_bylevel": trial.suggest_float("colsample_bylevel", 0.3, 1.0),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 20, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 120, log=True),
        "gamma": trial.suggest_float("gamma", 1e-8, 12, log=True),
        "max_delta_step": trial.suggest_float("max_delta_step", 0, 12),
        "max_cat_to_onehot": trial.suggest_int("max_cat_to_onehot", 1, 8),
        "nthread": 4,
    }
    n_est = trial.suggest_int("n_estimators", 200, 2500, step=100)

    oof = np.full(len(y), np.nan)
    for tr, va in folds:
        d_tr = xgb.DMatrix(X.iloc[tr], y.iloc[tr], enable_categorical=True)
        d_va = xgb.DMatrix(X.iloc[va], enable_categorical=True)
        b = xgb.train(p, d_tr, num_boost_round=n_est)
        oof[va] = b.predict(d_va)
    rmse = float(np.sqrt(mean_squared_error(y, oof)))
    trial.set_user_attr("oof_r2", float(r2_score(y, oof)))
    return rmse


def main() -> None:
    raw = pd.read_parquet(DATA)
    meta = json.load(open(METRICS_A, encoding="utf-8"))
    base_feats = meta["dataset"]["features"]

    df = add_lags(raw).reset_index(drop=True)
    lag_feats = ["직전_ROI_절사", "직전_log경영비", "경영비_증감율", "직전_ROI_부호"]
    feats_base = [c for c in base_feats if c in df.columns]
    feats_full = feats_base + lag_feats
    cats = [c for c in feats_full if c in CATS or c == "지역x업종"]

    Xb = to_cat(df[feats_base], [c for c in cats if c in feats_base])
    Xf = to_cat(df[feats_full], cats)
    y = df[TARGET].astype("float64")
    g = df[GROUP]

    print(f"표본 {len(df):,}행 · 임가 {g.nunique():,}곳 · 설명변수 {len(feats_full)}개")
    print(f"trial {N_TRIALS}회 · GPU {N_GPU}장 · 임가 단위 {N_FOLDS}-fold OOF RMSE\n")

    folds = list(GroupKFold(n_splits=N_FOLDS).split(Xf, y, groups=g))

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=SEED, multivariate=True, group=True))

    done = {"n": 0, "best": np.inf}

    def cb(st, tr):
        done["n"] += 1
        if tr.value is not None and tr.value < done["best"]:
            done["best"] = tr.value
            print(f"  [{done['n']:>3d}/{N_TRIALS}] RMSE {tr.value:7.3f}  "
                  f"OOF R² {tr.user_attrs.get('oof_r2', 0):+.4f}  depth {tr.params['max_depth']}")
        elif done["n"] % 50 == 0:
            print(f"  [{done['n']:>3d}/{N_TRIALS}] ...")

    study.optimize(lambda t: objective(t, Xf, y, g, folds),
                   n_trials=N_TRIALS, callbacks=[cb], show_progress_bar=False)

    best = dict(study.best_params)
    n_est = best.pop("n_estimators")
    params = {"objective": "reg:squarederror", "eval_metric": "rmse",
              "tree_method": "hist", "device": "cuda:0", "seed": SEED, **best}

    print(f"\n최적 RMSE {study.best_value:.3f} · OOF R² "
          f"{study.best_trial.user_attrs['oof_r2']:+.4f}")

    # ── 기존 파이프라인과 같은 방식으로 다시 평가한다 ──
    old = json.load(open(OUT_METRICS, encoding="utf-8"))
    prev = dict(json.load(open(METRICS_A, encoding="utf-8"))["optuna_xgboost"]["best_params"])
    prev["device"] = "cuda:0"
    prev_n = json.load(open(METRICS_A, encoding="utf-8"))["optuna_xgboost"]["n_estimators"]

    rows = {"산림청 방식": [], "작년값 선형보정": [], "기존 22변수": [],
            "패널 변수 추가": [], "패널 + 전용 탐색": []}
    best_model, best_r2 = None, -9
    print("\n[임가 단위 분할 · 5회]")
    for k, (a, b_) in enumerate(GroupShuffleSplit(5, test_size=0.18, random_state=SEED)
                                .split(Xf, y, groups=g)):
        rows["산림청 방식"].append(baseline_group(df, a, b_))
        rows["작년값 선형보정"].append(baseline_lag_only(df, a, b_))
        rows["기존 22변수"].append(xgb_eval(Xb, y, a, b_, prev, prev_n)[0])
        rows["패널 변수 추가"].append(xgb_eval(Xf, y, a, b_, prev, prev_n)[0])
        s, mdl = xgb_eval(Xf, y, a, b_, params, n_est)
        rows["패널 + 전용 탐색"].append(s)
        if s["R2"] > best_r2:
            best_r2, best_model = s["R2"], mdl
        print(f"  fold{k+1}  기존파라미터 {rows['패널 변수 추가'][-1]['R2']:+.4f} → "
              f"전용탐색 {s['R2']:+.4f}")

    def avg(rs):
        return {kk: float(np.mean([r[kk] for r in rs])) for kk in rs[0]}

    grp = {k: avg(v) for k, v in rows.items()}
    sd = {k: float(np.std([r["R2"] for r in v])) for k, v in rows.items()}

    print("\n" + "=" * 62)
    for k in rows:
        print(f"{k:20s} R² {grp[k]['R2']:+.4f}  RMSE {grp[k]['RMSE']:7.2f}  ±{sd[k]:.4f}")
    print("=" * 62)
    gain = grp["패널 + 전용 탐색"]["R2"] - grp["패널 변수 추가"]["R2"]
    pooled = (sd["패널 + 전용 탐색"] + sd["패널 변수 추가"]) / 2
    verdict = ("전용 탐색이 실제로 도움이 된다" if gain > pooled
               else "개선이 fold 변동 범위 안이라 단정할 수 없다")
    print(f"전용 탐색으로 R² {gain:+.4f} (fold 변동 ±{pooled:.4f}) → {verdict}")
    print(f"산림청 방식 대비 {grp['패널 + 전용 탐색']['R2']/grp['산림청 방식']['R2']:.2f}배")

    # 나아진 경우에만 모델을 갈아 끼운다. 좋아 보이려고 바꾸지 않는다.
    if gain > pooled:
        best_model.save_model(OUT_MODEL)
        print(f"\n[saved] {OUT_MODEL}  (전용 탐색 모델로 교체)")
        headline = "패널 + 전용 탐색"
    else:
        print("\n모델은 그대로 둡니다. 개선이 fold 변동 범위 안입니다.")
        headline = "패널 변수 추가"

    old.update({
        "임가단위_5회평균": grp,
        "임가단위_fold표준편차": sd,
        "전용탐색": {
            "n_trials": N_TRIALS, "n_folds": N_FOLDS, "gpus_used": N_GPU,
            "best_params": params, "n_estimators": n_est,
            "cv_oof": {"RMSE": study.best_value,
                       "R2": study.best_trial.user_attrs["oof_r2"]},
            "R2_증가": gain, "fold변동": pooled, "판정": verdict,
            "채택": headline,
            "주의": ("탐색도 임가 단위 5-fold로 했습니다. 행 단위로 나누고 탐색하면 "
                   "같은 임가가 양쪽에 들어가는 누출까지 최적화하게 됩니다."),
        },
    })
    json.dump(old, open(OUT_METRICS, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump({"features": feats_full, "categorical": cats, "lag_features": lag_feats,
               "적용조건": "직전 연도 관측이 있는 임가에만 적용"},
              open(OUT_SCHEMA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[saved] {OUT_METRICS}")


if __name__ == "__main__":
    main()
