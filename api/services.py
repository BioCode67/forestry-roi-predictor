"""모델 로딩과 예측 로직. FastAPI 라우트에서 얇게 호출한다."""
from __future__ import annotations

import json
import math
import os
import sys
from functools import lru_cache

import numpy as np
import pandas as pd
import xgboost as xgb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from preprocess import CATEGORICALS, FALLBACK_CODEBOOK, add_derived_features, parse_codebook  # noqa: E402
from preprocess_cost import CODEBOOK as COST_CODEBOOK  # noqa: E402
from preprocess_cost import add_derived_cost_features  # noqa: E402
from explain import explain as shap_explain  # noqa: E402
from explain import neighbors as find_neighbors  # noqa: E402
from explain import prescribe as make_prescription  # noqa: E402
from shipping import load_kamis, recommend  # noqa: E402

MODEL_DIR = os.path.join(ROOT, "models")
DATA_DIR = os.path.join(ROOT, "data")


# ---------------------------------------------------------------------------
# 로딩 (프로세스 수명 동안 1회)
# ---------------------------------------------------------------------------
def _sanitize(o):
    """NaN·Inf를 None으로 바꾼다. 둘 다 유효한 JSON 값이 아니라 응답 직렬화에서 터진다."""
    if isinstance(o, dict):
        return {k: _sanitize(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_sanitize(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def _json(path: str):
    p = os.path.join(MODEL_DIR, path)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return _sanitize(json.load(f))


def _booster(name: str) -> xgb.Booster | None:
    # 배포본은 같은 모델을 UBJSON으로 담습니다. 내용은 같고 용량이 30% 작습니다.
    p = os.path.join(MODEL_DIR, name)
    ubj = os.path.splitext(p)[0] + ".ubj"
    if os.path.exists(ubj):
        p = ubj
    elif not os.path.exists(p):
        return None
    b = xgb.Booster()
    b.load_model(p)
    # 서빙은 CPU로 충분하다. 다만 무료 등급은 CPU 지분이 0.1개인데 xgboost는
    # 호스트가 보고하는 코어 수만큼 스레드를 띄운다. 그러면 실제로 쓸 수 있는
    # 몫을 여럿이 나눠 갖느라 오히려 느려진다. 한 개로 묶어 둔다.
    b.set_param({"device": "cpu", "nthread": 1})
    return b


def model_ready(name: str) -> bool:
    """모델 파일이 놓여 있는지만 봅니다. 적재는 하지 않습니다."""
    base = os.path.join(MODEL_DIR, name)
    return os.path.exists(base) or os.path.exists(os.path.splitext(base)[0] + ".ubj")


class _Registry(dict):
    """부스터는 실제로 쓸 때 올린다.

    XGBoost는 8MB짜리 모델을 메모리에 30MB 넘게 펼친다. 다섯 개를 미리 다 올리면
    166MB다. 무료 호스팅의 512MB 한도에서 이건 감당하기 어렵다. 그런데 방문자
    대부분은 첫 화면만 보고, 첫 화면은 두 개만 쓴다. 그래서 처음 꺼낼 때 올린다.
    """

    _LAZY = {
        "model_a": "best_xgboost_roi.json",
        "model_b": "best_xgboost_cost.json",
        "model_panel": "best_xgboost_panel.json",
        "quantile_a": "quantile_roi.json",
        "quantile_b": "quantile_cost.json",
    }

    def __missing__(self, key):
        if key not in self._LAZY:
            raise KeyError(key)
        b = _booster(self._LAZY[key])
        self[key] = b          # 없으면 None을 넣어 두어 매번 다시 찾지 않게 한다
        return b


@lru_cache(maxsize=1)
def registry() -> dict:
    """산출물 적재. 부스터만 지연 적재하고 나머지는 작아서 미리 읽는다."""
    reg = _Registry({
        "schema_a": _json("feature_schema.json"),
        "metrics_a": _json("metrics_summary.json"),
        "schema_b": _json("feature_schema_cost.json"),
        "metrics_b": _json("metrics_cost.json"),
        "metrics_q": _json("metrics_quantile.json"),
        "insights": _json("insights.json"),
        "production": _json("production_insights.json"),
        "management": _json("management_insights.json"),
        "subsidy": _json("subsidy_programs.json"),
        "sector_profile": _json("sector_profile.json"),
        "item_profile": _json("item_cost_profile.json"),
        "region": _json("region_stats.json"),
        "weather_region": _json("weather_region.json"),
        "portfolio": _json("portfolio.json"),
        "audit_split": _json("audit_split.json"),
        "schema_panel": _json("feature_schema_panel.json"),
        "metrics_panel": _json("metrics_panel.json"),
    })
    try:
        reg["codebook"] = parse_codebook()
    except Exception:  # noqa: BLE001
        reg["codebook"] = dict(FALLBACK_CODEBOOK)
    reg["cost_codebook"] = COST_CODEBOOK

    p = os.path.join(DATA_DIR, "processed_forestry_data.parquet")
    reg["df_a"] = pd.read_parquet(p) if os.path.exists(p) else None
    p = os.path.join(DATA_DIR, "processed_cost_data.parquet")
    reg["df_b"] = pd.read_parquet(p) if os.path.exists(p) else None
    try:
        reg["kamis"] = load_kamis()
    except Exception:  # noqa: BLE001
        reg["kamis"] = None
    return reg


def inv_transform(z, kind: str):
    return np.sign(z) * np.expm1(np.abs(z)) if kind == "signed_log" else z


# ---------------------------------------------------------------------------
# Model A — 임가 단위
# ---------------------------------------------------------------------------
def build_row_a(vals: dict, schema: dict) -> pd.DataFrame:
    row = add_derived_features(pd.DataFrame([vals]))
    X = row.reindex(columns=schema["features"])
    for c in schema["categorical"]:
        X[c] = pd.Categorical(
            X[c].astype("Int64").fillna(-1).to_numpy(dtype="int64"),
            categories=schema["categories"][c])
    for c in schema["numeric"]:
        X[c] = pd.to_numeric(X[c], errors="coerce").astype("float64")
    return X.replace([np.inf, -np.inf], np.nan)


def build_row_panel(vals: dict, schema: dict) -> pd.DataFrame:
    """작년 자료를 붙인 행. 파생 규칙은 학습 때와 같아야 한다."""
    v = dict(vals)
    prev_roi = float(v["직전_ROI"])
    prev_cost = float(v.get("직전_경영비") or v["임업경영비"])
    v["직전_ROI_절사"] = min(max(prev_roi, -100.0), 600.0)
    v["직전_log경영비"] = float(np.log1p(max(prev_cost, 0.0)))
    v["경영비_증감율"] = ((float(v["임업경영비"]) - prev_cost) / prev_cost
                     if prev_cost else np.nan)
    v["직전_ROI_부호"] = float(np.sign(prev_roi))

    row = add_derived_features(pd.DataFrame([v]))
    for k in ("직전_ROI_절사", "직전_log경영비", "경영비_증감율", "직전_ROI_부호"):
        row[k] = v[k]
    X = row.reindex(columns=schema["features"])
    for c in schema["categorical"]:
        X[c] = pd.Categorical(X[c].astype("Int64").fillna(-1).to_numpy(dtype="int64"))
    for c in X.columns:
        if c not in schema["categorical"]:
            X[c] = pd.to_numeric(X[c], errors="coerce").astype("float64")
    return X.replace([np.inf, -np.inf], np.nan)


def _has_panel(vals: dict) -> bool:
    """작년 ROI를 받았고 패널 모델이 준비되어 있는가."""
    reg = registry()
    return (vals.get("직전_ROI") is not None
            and reg["model_panel"] is not None
            and reg.get("schema_panel") is not None)


def predict_a(vals: dict) -> dict:
    reg = registry()
    if reg["model_a"] is None:
        raise RuntimeError("Model A가 학습되지 않았습니다.")

    # 작년 자료가 있으면 패널 모델을 쓴다. 설명력이 네 배 높다.
    used = "기본"
    if _has_panel(vals):
        try:
            Xp = build_row_panel(vals, reg["schema_panel"])
            roi = float(reg["model_panel"].predict(
                xgb.DMatrix(Xp, enable_categorical=True))[0])
            used = "패널"
        except Exception:  # noqa: BLE001 — 어긋나면 조용히 기본 모델로 되돌린다
            used = "기본"

    schema = reg["schema_a"]
    X = build_row_a(vals, schema)
    kind = schema.get("target_transform", "none")
    if used == "기본":
        roi = float(inv_transform(
            reg["model_a"].predict(xgb.DMatrix(X, enable_categorical=True))[0], kind))

    band = None
    if reg["quantile_a"] is not None:
        pred = reg["quantile_a"].predict(xgb.DMatrix(X, enable_categorical=True))
        pred = np.sort(np.atleast_2d(pred), axis=1)[0]
        band = [float(inv_transform(v, "none")) for v in pred]

    cost = float(vals.get("임업경영비") or 0)
    baseline = _baseline_a(vals)
    mp = reg.get("metrics_panel") or {}
    return {
        "roi": roi,
        "band": band,
        "model": used,
        "model_note": (
            "작년 실적을 반영한 예측입니다. 같은 조건에서 설명력(R²)이 0.06에서 0.28로 "
            "네 배 높습니다." if used == "패널" else
            "작년 실적을 입력하시면 훨씬 정확하게 계산할 수 있습니다."),
        "model_r2": (mp.get("임가단위_5회평균", {}).get("패널 변수 추가", {}).get("R2")
                     if used == "패널" else
                     (reg["metrics_a"] or {}).get("optuna_xgboost", {}).get("test", {}).get("R2")),
        "coverage": (reg["metrics_q"] or {}).get("roi", {}).get("coverage_80pct"),
        "income": roi / 100.0 * cost,
        "revenue": cost + roi / 100.0 * cost,
        "cost": cost,
        "baseline_roi": baseline,
        "baseline_income": None if baseline is None else baseline / 100.0 * cost,
    }


def _baseline_a(vals: dict) -> float | None:
    """산림청 현행 방식 — 지역별x업종별 단순 평균."""
    df = registry()["df_a"]
    if df is None:
        return None
    g = df[(df["지역별"] == vals["지역별"]) & (df["업종별"] == vals["업종별"])]["ROI"]
    if len(g) < 5:
        g = df[df["업종별"] == vals["업종별"]]["ROI"]
    return float(g.mean()) if len(g) else float(df["ROI"].mean())


def response_curve_a(vals: dict, lo_mult=0.2, hi_mult=2.5, n=36) -> list[dict]:
    base = float(vals.get("임업경영비") or 0)
    if base <= 0:
        return []
    grid = np.unique(np.clip(
        np.concatenate([np.linspace(max(base * lo_mult, 1e6), base * hi_mult, n), [base]]),
        1e5, 5e8))
    reg = registry()
    schema = reg["schema_a"]
    kind = schema.get("target_transform", "none")
    rows = []
    frames = [build_row_a(dict(vals, 임업경영비=float(c)), schema) for c in grid]
    X = pd.concat(frames, ignore_index=True)
    for c in schema["categorical"]:
        X[c] = pd.Categorical(X[c].astype("int64"), categories=schema["categories"][c])
    preds = inv_transform(
        reg["model_a"].predict(xgb.DMatrix(X, enable_categorical=True)), kind)
    for c, r in zip(grid, preds):
        rows.append({"cost": float(c), "roi": float(r), "income": float(r) / 100 * float(c)})
    return rows


def sector_simulation(vals: dict) -> list[dict]:
    reg = registry()
    out = []
    for code, label in reg["codebook"]["업종별"].items():
        r = predict_a(dict(vals, 업종별=int(code)))
        out.append({"sector": label, "roi": r["roi"]})
    return sorted(out, key=lambda x: -x["roi"])


def peer_distribution(sector_code: int, bins: int = 36) -> dict:
    df = registry()["df_a"]
    if df is None:
        return {}
    peer = df[df["업종별"] == sector_code]["ROI"]
    if peer.empty:
        return {}
    counts, edges = np.histogram(peer, bins=bins)
    return {
        "n": int(len(peer)),
        "bins": [float((edges[i] + edges[i + 1]) / 2) for i in range(len(counts))],
        "counts": [int(c) for c in counts],
        "values": [float(v) for v in peer.to_numpy()],
    }


def percentile_in_peer(sector_code: int, roi: float) -> float | None:
    df = registry()["df_a"]
    if df is None:
        return None
    peer = df[df["업종별"] == sector_code]["ROI"]
    return float((peer < roi).mean() * 100) if len(peer) else None


# ---------------------------------------------------------------------------
# Model B — 품목 단위
# ---------------------------------------------------------------------------
def build_row_b(item: str, overrides: dict, schema: dict) -> pd.DataFrame:
    base = {k: (np.nan if v is None else v)
            for k, v in schema["item_medians"].get(item, schema["train_medians"]).items()}
    base.update(overrides)
    base["품목"] = item
    row = add_derived_cost_features(pd.DataFrame([base]))
    X = row.reindex(columns=schema["features"])
    for c in schema["categorical"]:
        v = schema["item_map"].get(item, -1) if c == "품목" else X[c].iloc[0]
        X[c] = pd.Categorical(
            pd.Series([v]).astype("Int64").fillna(-1).to_numpy(dtype="int64"),
            categories=schema["categories"][c])
    for c in schema["numeric"]:
        X[c] = pd.to_numeric(X[c], errors="coerce").astype("float64")
    return X.replace([np.inf, -np.inf], np.nan)


def predict_b(item: str, overrides: dict) -> dict:
    reg = registry()
    if reg["model_b"] is None:
        raise RuntimeError("Model B가 학습되지 않았습니다.")
    schema = reg["schema_b"]
    X = build_row_b(item, overrides, schema)
    kind = schema.get("target_transform", "none")
    roi = float(inv_transform(
        reg["model_b"].predict(xgb.DMatrix(X, enable_categorical=True))[0], kind))
    cost = float(overrides.get("경영비") or 0)

    df = reg["df_b"]
    peer_med = lead_med = None
    if df is not None:
        p = df[df["품목"] == item]
        if len(p):
            peer_med = float(p["ROI"].median())
            lead = p[p["경영수준별"] == 1]
            if len(lead):
                lead_med = float(lead["ROI"].median())
    return {
        "roi": roi, "income": roi / 100.0 * cost, "cost": cost,
        "peer_median": peer_med, "leader_median": lead_med,
        "unit": "만본" if "표고" in item else "ha",
    }


def cost_structure(item: str, overrides: dict) -> dict:
    """귀 임가 비목 구성 vs 선도임가 중앙값."""
    reg = registry()
    schema, df = reg["schema_b"], reg["df_b"]
    if schema is None or df is None:
        return {}
    ratios = ["노동비_비중", "비료비_비중", "농약비_비중", "감가상각비_비중", "위탁영농비_비중"]
    labels = ["노동비", "비료비", "농약비", "감가상각비", "위탁영농비"]
    X = build_row_b(item, overrides, schema)
    lead = df[(df["품목"] == item) & (df["경영수준별"] == 1)]
    out = []
    for lab, col in zip(labels, ratios):
        mine = float(X[col].iloc[0]) * 100 if col in X.columns and pd.notna(X[col].iloc[0]) else None
        theirs = float(lead[col].median()) * 100 if col in lead.columns and len(lead) else None
        out.append({"item": lab, "mine": mine, "leader": theirs,
                    "gap": None if (mine is None or theirs is None) else mine - theirs})
    return {"rows": out, "leader_n": int(len(lead))}


def item_roi_distribution() -> list[dict]:
    df = registry()["df_b"]
    if df is None:
        return []
    return [{"item": it, "values": [float(v) for v in g["ROI"].to_numpy()],
             "median": float(g["ROI"].median()), "n": int(len(g))}
            for it, g in df.groupby("품목", observed=True)]


def response_curve_b(item: str, overrides: dict, n=30) -> list[dict]:
    base = float(overrides.get("경영비") or 0)
    if base <= 0:
        return []
    reg = registry()
    schema = reg["schema_b"]
    kind = schema.get("target_transform", "none")
    grid = np.linspace(max(base * 0.3, 1e5), base * 2.0, n)
    rows = []
    for c in grid:
        X = build_row_b(item, dict(overrides, 경영비=float(c)), schema)
        r = float(inv_transform(
            reg["model_b"].predict(xgb.DMatrix(X, enable_categorical=True))[0], kind))
        rows.append({"cost": float(c), "roi": r, "income": r / 100 * float(c)})
    return rows


# ---------------------------------------------------------------------------
def explain_a(vals: dict) -> dict:
    """예측 하나를 항목별로 분해합니다 (TreeSHAP)."""
    reg = registry()
    if reg["model_a"] is None:
        raise RuntimeError("Model A가 학습되지 않았습니다.")
    X = build_row_a(vals, reg["schema_a"])
    return shap_explain(reg["model_a"], X, reg["schema_a"]["features"])


def prescribe_a(vals: dict, target: float | None = None) -> dict:
    """목표 수익률에 닿는 최소 변경을 찾습니다."""
    reg = registry()
    if target is None:
        # 목표를 주지 않으면 같은 업종의 중앙값을 기본 목표로 둡니다.
        # 상위 25%는 대다수 임가에게 한 번에 닿기 어려운 수준이라 처방이 비게 됩니다.
        df = reg["df_a"]
        peer = df[df["업종별"] == vals["업종별"]]["ROI"] if df is not None else None
        target = float(peer.median()) if peer is not None and len(peer) else 100.0
    return make_prescription(lambda v: predict_a(v)["roi"], vals, float(target),
                             reg["codebook"])


def neighbors_a(vals: dict) -> dict:
    return find_neighbors(registry()["df_a"], vals)


def shipping_for(sector_label: str) -> dict:
    reg = registry()
    return recommend(sector_label, reg["kamis"])
