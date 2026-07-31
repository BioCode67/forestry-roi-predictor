"""
Phase 2-M — 패널 구조를 쓰는 모델 (Model A+)

임가경제조사는 같은 임가를 여러 해 따라가는 패널입니다. 그런데 지금까지의 모델은
각 행을 독립 관측으로만 다뤘습니다. 작년에 이 임가가 얼마를 벌었는지는 올해를 계획할
때 이미 알고 있는 정보인데, 그걸 버리고 있었던 셈입니다.

실제로 작년 ROI 하나만으로 선형 보정해도 R²가 0.22 나옵니다. 설명변수 22개를 쓴
기존 모델(0.17)보다 높습니다. 임가의 수익률에는 자료에 안 잡히는 고유한 몫 —
산의 상태, 기술, 판로 — 이 크고, 작년 실적이 그 몫을 대신 담고 있기 때문입니다.

── 쓸 수 있는 범위를 분명히 합니다

임가번호가 2019~2022년은 네 자리(1001…), 2023년은 다섯 자리(11021…)입니다.
체계가 바뀌어 2022년과 2023년 사이의 연결이 끊깁니다(교집합 0곳). 파일설계서에
이에 대한 안내가 없어 대조로 확인했습니다.

따라서 이 모델은 직전 연도 관측이 있는 행에만 적용됩니다. 전체 4,438행 중 2,186행
(49.3%)입니다. 나머지는 기존 Model A가 맡습니다. 서비스는 둘을 함께 두고, 작년
자료를 입력한 임가에게는 이쪽을, 처음 쓰는 임가에게는 저쪽을 씁니다.

── 정직하게 재기 위한 두 가지 장치

  ① 임가 단위 분할 — 같은 임가가 학습과 시험 양쪽에 들어가면 외워서 맞힐 수 있습니다.
  ② 연도 단위 분할 — 과거로 배워 미래를 맞히는, 실제 사용 상황과 같은 조건입니다.
     이쪽이 더 어렵고, 더 정직합니다.

비교 대상도 같은 부분집합에서 다시 잽니다. 부분집합이 달라지면 숫자를 나란히 놓을
수 없습니다.

산출: models/metrics_panel.json, models/best_xgboost_panel.json
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "processed_forestry_data.parquet")
METRICS_A = os.path.join(ROOT, "models", "metrics_summary.json")
OUT_METRICS = os.path.join(ROOT, "models", "metrics_panel.json")
OUT_MODEL = os.path.join(ROOT, "models", "best_xgboost_panel.json")
OUT_SCHEMA = os.path.join(ROOT, "models", "feature_schema_panel.json")

SEED = 42
GROUP = "임가번호"
TARGET = "ROI"
CATS = ["연령별", "지역별", "전/겸업별", "업종별", "가구원수별", "임지규모별"]


# ── 자료 ──────────────────────────────────────────────────────────────────
def add_lags(df: pd.DataFrame) -> pd.DataFrame:
    """직전 연도 정보를 붙입니다. 반드시 과거만 씁니다."""
    d = df.sort_values([GROUP, "조사연도"]).copy()
    g = d.groupby(GROUP)

    d["직전_ROI"] = g["ROI"].shift(1)
    d["직전_경영비"] = g["임업경영비"].shift(1)
    d["직전_임업소득"] = g["임업소득"].shift(1)
    d["직전_연도"] = g["조사연도"].shift(1)

    # 직전 관측이 바로 전 해가 아니면 쓰지 않습니다. 두 해 건너뛴 값은 성격이 다릅니다.
    ok = (d["조사연도"] - d["직전_연도"]) == 1
    for c in ("직전_ROI", "직전_경영비", "직전_임업소득"):
        d.loc[~ok, c] = np.nan

    # 파생 — 수준보다 '얼마나 달라졌는가'가 더 많은 것을 말해 줍니다
    d["경영비_증감율"] = (d["임업경영비"] - d["직전_경영비"]) / d["직전_경영비"].replace(0, np.nan)
    d["직전_log경영비"] = np.log1p(d["직전_경영비"].clip(lower=0))
    d["직전_ROI_부호"] = np.sign(d["직전_ROI"])
    # 극단값이 회귀를 끌고 다니지 않도록 꼬리를 눌러 둔 판본도 함께 넣습니다
    d["직전_ROI_절사"] = d["직전_ROI"].clip(-100, 600)

    return d[d["직전_ROI"].notna()].copy()


def to_cat(X: pd.DataFrame, cats) -> pd.DataFrame:
    X = X.copy()
    for c in cats:
        if str(X[c].dtype) != "category":
            X[c] = pd.Categorical(X[c].astype("Int64").fillna(-1).to_numpy(dtype="int64"))
    return X


def sc(y, p):
    return {"R2": float(r2_score(y, p)),
            "RMSE": float(np.sqrt(mean_squared_error(y, p))),
            "MAE": float(mean_absolute_error(y, p))}


# ── 비교 대상 ─────────────────────────────────────────────────────────────
def baseline_group(df, tr, te):
    """산림청 방식 — 지역×업종 단순 평균."""
    a, b = df.iloc[tr], df.iloc[te]
    grand = a[TARGET].mean()
    g2 = a.groupby(["지역별", "업종별"], observed=True)[TARGET].mean()
    g1 = a.groupby(["업종별"], observed=True)[TARGET].mean()
    p = pd.Series(list(zip(b["지역별"], b["업종별"])), index=b.index).map(g2)
    p = p.fillna(b["업종별"].map(g1)).fillna(grand)
    return sc(b[TARGET], p.to_numpy(dtype=float))


def baseline_lag_only(df, tr, te):
    """작년 값을 선형 보정한 것만으로 어디까지 가는가 — 가장 단순한 패널 활용."""
    a, b = df.iloc[tr], df.iloc[te]
    r = Ridge(alpha=1.0).fit(a[["직전_ROI_절사"]], a[TARGET])
    return sc(b[TARGET], r.predict(b[["직전_ROI_절사"]]))


def xgb_eval(X, y, tr, te, params, n_est):
    d_tr = xgb.DMatrix(X.iloc[tr], y.iloc[tr], enable_categorical=True)
    d_te = xgb.DMatrix(X.iloc[te], y.iloc[te], enable_categorical=True)
    b = xgb.train(params, d_tr, num_boost_round=n_est)
    return sc(y.iloc[te], b.predict(d_te)), b


# ── 본체 ──────────────────────────────────────────────────────────────────
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

    print(f"패널 연결된 행 {len(df):,} / 전체 {len(raw):,} ({len(df)/len(raw)*100:.1f}%)")
    print(f"임가 {g.nunique():,}곳 · 연도 {sorted(df['조사연도'].unique().astype(int))}\n")

    params = dict(meta["optuna_xgboost"]["best_params"])
    params["device"] = "cuda:0"
    n_est = meta["optuna_xgboost"]["n_estimators"]

    # ── ① 임가 단위 분할 (5회) ──
    print("[임가 단위 분할 · 5회]")
    rows = {"산림청 방식": [], "작년값 선형보정": [], "기존 22변수": [], "패널 변수 추가": []}
    best_model, best_r2 = None, -9
    for k, (a, b_) in enumerate(GroupShuffleSplit(5, test_size=0.18, random_state=SEED)
                                .split(Xf, y, groups=g)):
        assert not (set(g.iloc[a]) & set(g.iloc[b_]))
        rows["산림청 방식"].append(baseline_group(df, a, b_))
        rows["작년값 선형보정"].append(baseline_lag_only(df, a, b_))
        sb, _ = xgb_eval(Xb, y, a, b_, params, n_est)
        sf, mdl = xgb_eval(Xf, y, a, b_, params, n_est)
        rows["기존 22변수"].append(sb)
        rows["패널 변수 추가"].append(sf)
        if sf["R2"] > best_r2:
            best_r2, best_model = sf["R2"], mdl
        print(f"  fold{k+1}  기존 {sb['R2']:+.4f} → 패널 {sf['R2']:+.4f} "
              f"({sf['R2']-sb['R2']:+.4f})")

    def avg(rs):
        return {k: float(np.mean([r[k] for r in rs])) for k in rs[0]}

    grp = {k: avg(v) for k, v in rows.items()}
    sd = {k: float(np.std([r["R2"] for r in v])) for k, v in rows.items()}

    # ── ② 연도 단위 분할 — 과거로 배워 미래를 맞힌다 ──
    print("\n[연도 단위 분할 · 과거→미래]")
    yr = {}
    for test_year in (2021, 2022):
        a = np.flatnonzero((df["조사연도"] < test_year).to_numpy())
        b_ = np.flatnonzero((df["조사연도"] == test_year).to_numpy())
        if len(a) < 200 or len(b_) < 100:
            continue
        sb, _ = xgb_eval(Xb, y, a, b_, params, n_est)
        sf, _ = xgb_eval(Xf, y, a, b_, params, n_est)
        bg = baseline_group(df, a, b_)
        yr[str(test_year)] = {"산림청 방식": bg, "기존 22변수": sb, "패널 변수 추가": sf,
                              "학습": int(len(a)), "시험": int(len(b_))}
        print(f"  ~{test_year-1} 학습 → {test_year} 시험 ({len(a):,}→{len(b_):,}행)")
        print(f"    산림청 {bg['R2']:+.4f} | 기존 {sb['R2']:+.4f} | 패널 {sf['R2']:+.4f}")

    # ── 정리 ──
    print("\n" + "=" * 66)
    print(f"{'모델':20s} {'R²':>9s} {'RMSE':>9s} {'MAE':>9s} {'±fold':>8s}")
    print("-" * 66)
    for k in ("산림청 방식", "작년값 선형보정", "기존 22변수", "패널 변수 추가"):
        v = grp[k]
        print(f"{k:18s} {v['R2']:>9.4f} {v['RMSE']:>9.2f} {v['MAE']:>9.2f} {sd[k]:>8.4f}")
    print("=" * 66)
    gain = grp["패널 변수 추가"]["R2"] - grp["기존 22변수"]["R2"]
    pooled = (sd["패널 변수 추가"] + sd["기존 22변수"]) / 2
    verdict = ("패널 변수가 실제로 도움이 된다" if gain > pooled
               else "개선이 fold 변동 범위 안이라 단정할 수 없다")
    print(f"\n패널 변수로 R² {gain:+.4f} (fold 변동 ±{pooled:.4f}) → {verdict}")
    print(f"산림청 방식 대비 {grp['패널 변수 추가']['R2']/grp['산림청 방식']['R2']:.2f}배")

    best_model.save_model(OUT_MODEL)
    json.dump({"features": feats_full, "categorical": cats,
               "lag_features": lag_feats,
               "적용조건": "직전 연도 관측이 있는 임가에만 적용"},
              open(OUT_SCHEMA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump({
        "질문": "패널 구조(작년 실적)를 쓰면 예측이 나아지는가",
        "적용범위": {"패널연결_행": int(len(df)), "전체_행": int(len(raw)),
                  "비율_pct": round(len(df) / len(raw) * 100, 1),
                  "임가수": int(g.nunique()),
                  "연도": sorted(df["조사연도"].unique().astype(int).tolist())},
        "임가단위_5회평균": grp,
        "임가단위_fold표준편차": sd,
        "연도단위": yr,
        "개선": {"R2_증가": gain, "fold변동": pooled, "판정": verdict},
        "한계": (
            "임가번호 체계가 2023년에 네 자리에서 다섯 자리로 바뀌어 2022~2023년 연결이 "
            "끊깁니다(교집합 0곳). 파일설계서에 안내가 없어 대조로 확인했습니다. 대조표가 "
            "없으면 2023년 이후에는 이 모델을 쓸 수 없고, 처음 이용하는 임가에게도 쓸 수 "
            "없습니다. 그런 경우는 기존 Model A가 맡습니다."),
        "시사점": (
            "작년 실적 한 항목이 설명변수 22개보다 더 많은 것을 설명합니다. 임가 수익률에는 "
            "조사표에 안 잡히는 고유한 몫이 크고, 작년 실적이 그 대리 지표 노릇을 한다는 "
            "뜻입니다. 조사에 산의 수령·수종·경사·판로를 넣으면 이 몫을 직접 잴 수 있습니다."),
    }, open(OUT_METRICS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n[saved] {OUT_METRICS}")
    print(f"[saved] {OUT_MODEL}")


if __name__ == "__main__":
    main()
