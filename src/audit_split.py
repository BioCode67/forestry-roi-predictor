"""
분할 감사 — 같은 임가가 학습과 시험에 동시에 들어가 있는가

임가경제조사는 패널입니다. 임가번호 2,168개가 4,438개 행에 나타나므로 같은 임가가
평균 2년씩 관측됩니다. 그런데 현재 파이프라인은 행 단위 무작위 분할을 씁니다.

임가번호 자체는 설명변수에 없습니다. 그러나 지역·업종·임지규모·경영비·자본·연초보유의
조합은 사실상 한 임가를 특정하는 지문에 가깝습니다. 같은 임가가 양쪽에 있으면 모델은
"이 임가의 ROI는 대략 이만큼"을 외워 두었다가 다른 해에 그대로 꺼내 쓸 수 있습니다.
그러면 시험 성적은 실제 일반화 능력보다 좋게 나옵니다.

이 스크립트는 답을 냅니다.
  ① 행 단위 분할에서 임가가 실제로 얼마나 겹치는가
  ② 같은 하이퍼파라미터로 임가 단위 분할(GroupShuffleSplit)을 하면 성능이 얼마나 떨어지는가

떨어진다면 그 값이 정직한 숫자입니다.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "processed_forestry_data.parquet")
METRICS = os.path.join(ROOT, "models", "metrics_summary.json")
OUT = os.path.join(ROOT, "models", "audit_split.json")
SEED = 42
GROUP = "임가번호"


def to_cat(X: pd.DataFrame, cats) -> pd.DataFrame:
    X = X.copy()
    for c in cats:
        x = X[c]
        if str(x.dtype) != "category":
            X[c] = pd.Categorical(x.astype("Int64").fillna(-1).to_numpy(dtype="int64"))
    return X


def scores(y, p):
    return {"R2": float(r2_score(y, p)),
            "RMSE": float(np.sqrt(mean_squared_error(y, p))),
            "MAE": float(mean_absolute_error(y, p))}


def fit_eval(X, y, tr, te, params, n_est):
    d_tr = xgb.DMatrix(X.iloc[tr], y.iloc[tr], enable_categorical=True)
    d_te = xgb.DMatrix(X.iloc[te], y.iloc[te], enable_categorical=True)
    b = xgb.train(params, d_tr, num_boost_round=n_est)
    return scores(y.iloc[te], b.predict(d_te))


def group_baseline(df, tr, te, target="ROI"):
    """산림청 방식(지역×업종 평균)도 같은 분할에서 다시 잰다."""
    a, b = df.iloc[tr], df.iloc[te]
    grand = a[target].mean()
    g2 = a.groupby(["지역별", "업종별"], observed=True)[target].mean()
    g1 = a.groupby(["업종별"], observed=True)[target].mean()
    p = pd.Series(list(zip(b["지역별"], b["업종별"])), index=b.index).map(g2)
    p = p.fillna(b["업종별"].map(g1)).fillna(grand)
    return scores(b[target], p.to_numpy(dtype=float))


def main() -> None:
    df = pd.read_parquet(DATA).reset_index(drop=True)
    meta = json.load(open(METRICS, encoding="utf-8"))
    feats = meta["dataset"]["features"]
    cats = [c for c in feats if str(df[c].dtype) == "category"
            or c in ("연령별", "지역별", "전/겸업별", "업종별", "가구원수별",
                     "임지규모별", "지역x업종")]
    X = to_cat(df[feats], cats)
    y = df["ROI"].astype("float64")
    g = df[GROUP]

    print(f"행 {len(df):,} · 임가 {g.nunique():,} · 임가당 평균 {len(df)/g.nunique():.2f}년\n")

    # ── ① 현행(행 단위) 분할에서 임가가 얼마나 새는가 ──
    i_tr, i_tmp = train_test_split(df.index, test_size=0.2, random_state=SEED)
    i_va, i_te = train_test_split(i_tmp, test_size=0.5, random_state=SEED)
    tr_g, te_g = set(g[i_tr]), set(g[i_te])
    overlap = tr_g & te_g
    leak_rows = int(g[i_te].isin(overlap).sum())
    print("[현행 행 단위 분할]")
    print(f"  시험셋 {len(i_te)}행 중 학습셋에도 있는 임가의 행: "
          f"{leak_rows}행 ({leak_rows/len(i_te)*100:.1f}%)")
    print(f"  겹친 임가 {len(overlap)}곳\n")

    params = dict(meta["optuna_xgboost"]["best_params"])
    params["device"] = "cuda:0"
    n_est = meta["optuna_xgboost"]["n_estimators"]

    row_pos = {v: i for i, v in enumerate(df.index)}
    tr_pos = [row_pos[i] for i in i_tr]
    te_pos = [row_pos[i] for i in i_te]
    row_xgb = fit_eval(X, y, tr_pos, te_pos, params, n_est)
    row_base = group_baseline(df, tr_pos, te_pos)

    # ── ② 임가 단위 분할 — 같은 임가는 한쪽에만 ──
    gss = GroupShuffleSplit(n_splits=5, test_size=0.1, random_state=SEED)
    gx, gb = [], []
    for k, (a, b_) in enumerate(gss.split(X, y, groups=g)):
        assert not (set(g.iloc[a]) & set(g.iloc[b_])), "그룹이 샜다"
        gx.append(fit_eval(X, y, a, b_, params, n_est))
        gb.append(group_baseline(df, a, b_))
        print(f"  fold{k+1}  XGB R² {gx[-1]['R2']:+.4f}  |  베이스라인 R² {gb[-1]['R2']:+.4f}")

    def avg(rs):
        return {k: float(np.mean([r[k] for r in rs])) for k in rs[0]}

    grp_xgb, grp_base = avg(gx), avg(gb)
    sd = float(np.std([r["R2"] for r in gx]))

    print("\n" + "=" * 62)
    print(f"{'분할 방식':22s} {'XGB R²':>10s} {'베이스라인':>10s} {'개선 배수':>10s}")
    print("-" * 62)
    print(f"{'행 단위 (현행)':20s} {row_xgb['R2']:>10.4f} {row_base['R2']:>10.4f} "
          f"{row_xgb['R2']/row_base['R2']:>9.2f}배")
    print(f"{'임가 단위 (5회 평균)':18s} {grp_xgb['R2']:>10.4f} {grp_base['R2']:>10.4f} "
          f"{grp_xgb['R2']/grp_base['R2']:>9.2f}배")
    print("=" * 62)
    drop = row_xgb["R2"] - grp_xgb["R2"]
    print(f"\n임가 단위로 바꾸면 R²가 {drop:+.4f} 변합니다 (fold 간 표준편차 {sd:.4f}).")
    if drop > 2 * sd:
        print("→ 행 단위 분할이 성능을 부풀리고 있었습니다. 임가 단위 값이 정직한 숫자입니다.")
    else:
        print("→ 차이가 fold 변동 범위 안입니다. 임가 누출의 영향은 크지 않습니다.")

    json.dump({
        "질문": "패널 자료에서 행 단위 무작위 분할이 성능을 부풀렸는가",
        "행수": int(len(df)), "임가수": int(g.nunique()),
        "행단위_시험셋_임가중복_비율_pct": round(leak_rows / len(i_te) * 100, 1),
        "행단위": {"xgboost": row_xgb, "baseline": row_base},
        "임가단위_5회평균": {"xgboost": grp_xgb, "baseline": grp_base,
                       "R2_fold별": [r["R2"] for r in gx], "R2_표준편차": sd},
        "R2_차이": drop,
        "판정": ("행 단위 분할이 성능을 부풀림 — 임가 단위 값을 채택"
               if drop > 2 * sd else "차이가 fold 변동 범위 내 — 영향 제한적"),
        "주의": "임가번호는 설명변수에 없다. 다만 지역·업종·규모·경영비·자본의 조합이 "
              "사실상 임가를 특정하므로 같은 임가가 양쪽에 있으면 외워서 맞힐 수 있다.",
    }, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n[saved] {OUT}")


if __name__ == "__main__":
    main()
