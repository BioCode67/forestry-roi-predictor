"""
임업통계 임가 수익성 분석 플랫폼 — FastAPI 백엔드

실행
    uvicorn api.main:app --reload --port 8000          # 개발
    uvicorn api.main:app --host 0.0.0.0 --port 8000    # 배포

프런트엔드(web/dist)가 빌드되어 있으면 같은 포트에서 정적 서빙한다.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import services as svc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "web", "dist")

app = FastAPI(
    title="임업통계 임가 수익성 분석 API",
    description="2026년 임업통계 활용 경진대회 · 데이터 분석 부문",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)


# ---------------------------------------------------------------------------
class FarmInput(BaseModel):
    연령별: int = Field(4, ge=1, le=5)
    지역별: int = 32
    전겸업별: int = Field(1, ge=1, le=3, alias="전/겸업별")
    업종별: int = Field(3, ge=1, le=8)
    가구원수별: int = Field(2, ge=1, le=5)
    임지규모별: int = Field(3, ge=1, le=5)
    임업경영비: float = 15_000_000
    임업외소득: float = 8_000_000
    기초자본: float = Field(400_000_000, alias="기초_자본(순재산)")
    연초보유: float = 3_000_000
    조사연도: float = 2023

    model_config = {"populate_by_name": True}

    def to_vals(self) -> dict:
        return {
            "연령별": self.연령별, "지역별": self.지역별, "전/겸업별": self.전겸업별,
            "업종별": self.업종별, "가구원수별": self.가구원수별,
            "임지규모별": self.임지규모별, "임업경영비": float(self.임업경영비),
            "임업외소득": float(self.임업외소득),
            "기초_자본(순재산)": float(self.기초자본),
            "연초보유": float(self.연초보유), "조사연도": float(self.조사연도),
        }


class ItemInput(BaseModel):
    품목: str = "밤"
    지역별: int = 37
    경영수준별: int = 2
    규모별: int = 1
    경영비: float = 5_000_000
    비료비: float | None = None
    농약비: float | None = None
    총노동시간: float | None = None

    def to_overrides(self) -> dict:
        o = {"지역별": self.지역별, "경영수준별": self.경영수준별,
             "규모별": self.규모별, "경영비": float(self.경영비)}
        if self.비료비 is not None:
            o["비료비_단위당"] = float(self.비료비)
        if self.농약비 is not None:
            o["농약비_단위당"] = float(self.농약비)
        if self.총노동시간 is not None:
            o["총노동시간_합계_단위당"] = float(self.총노동시간)
        return o


# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    reg = svc.registry()
    return {
        "status": "ok",
        "models": {
            "model_a": reg["model_a"] is not None,
            "model_b": reg["model_b"] is not None,
            "quantile_a": reg["quantile_a"] is not None,
            "quantile_b": reg["quantile_b"] is not None,
        },
        "datasets": {
            "insights": reg["insights"] is not None,
            "production": reg["production"] is not None,
            "management": reg["management"] is not None,
            "subsidy": reg["subsidy"] is not None,
            "kamis": reg["kamis"] is not None,
        },
    }


@app.get("/api/meta")
def meta():
    """코드북·모델 성능 등 프런트 초기화에 필요한 메타데이터."""
    reg = svc.registry()
    ma, mb = reg["metrics_a"], reg["metrics_b"]

    def bench(m):
        if not m:
            return None
        return {
            "dataset": m.get("dataset"),
            "rows": [
                {"key": k, "label": lab, **m[k]["test"]}
                for k, lab in [("forest_service_baseline", "산림청 단순평균"),
                               ("linear_regression", "다중 선형회귀"),
                               ("optuna_xgboost", "Optuna-XGBoost")]
                if k in m
            ],
            "improvement": m.get("improvement_vs_baseline"),
            "cv_oof": m.get("optuna_xgboost", {}).get("cv_oof"),
            "importance": list(m.get("feature_importance_gain", {}).items())[:15],
            "per_item": m.get("per_item_test"),
        }

    return {
        "codebook": {k: {str(c): v for c, v in d.items()}
                     for k, d in reg["codebook"].items()},
        "cost_codebook": {k: {str(c): v for c, v in d.items()}
                          for k, d in reg["cost_codebook"].items()},
        "items": list((reg["schema_b"] or {}).get("item_map", {}).keys()),
        "item_medians": (reg["schema_b"] or {}).get("item_medians", {}),
        "benchmark_a": bench(ma),
        "benchmark_b": bench(mb),
        "quantile": reg["metrics_q"],
    }


@app.post("/api/predict")
def predict(inp: FarmInput):
    try:
        vals = inp.to_vals()
        res = svc.predict_a(vals)
        res["curve"] = svc.response_curve_a(vals)
        res["sectors"] = svc.sector_simulation(vals)
        res["percentile"] = svc.percentile_in_peer(inp.업종별, res["roi"])
        res["peer"] = svc.peer_distribution(inp.업종별)
        return res
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.post("/api/predict/item")
def predict_item(inp: ItemInput):
    try:
        ov = inp.to_overrides()
        res = svc.predict_b(inp.품목, ov)
        res["curve"] = svc.response_curve_b(inp.품목, ov)
        res["structure"] = svc.cost_structure(inp.품목, ov)
        return res
    except RuntimeError as e:
        raise HTTPException(503, str(e))


class AdviceInput(FarmInput):
    목표: float | None = None


@app.post("/api/advice")
def advice(inp: AdviceInput):
    """왜 이 숫자인지 · 무엇을 바꿔야 하는지 · 누구를 보면 되는지."""
    try:
        vals = inp.to_vals()
        return {
            "explain": svc.explain_a(vals),
            "prescribe": svc.prescribe_a(vals, inp.목표),
            "neighbors": svc.neighbors_a(vals),
        }
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.get("/api/item/distribution")
def item_distribution():
    return svc.item_roi_distribution()


@app.get("/api/shipping/{sector}")
def shipping(sector: str):
    return svc.shipping_for(sector)


def _need(v, name: str):
    if v is None:
        raise HTTPException(404, f"{name} 산출물이 없습니다. 해당 스크립트를 먼저 실행하세요.")
    return v


@app.get("/api/insights")
def insights():
    return _need(svc.registry()["insights"], "insights")


@app.get("/api/production")
def production():
    return _need(svc.registry()["production"], "production")


@app.get("/api/management")
def management():
    return _need(svc.registry()["management"], "management")


@app.get("/api/subsidy")
def subsidy():
    return _need(svc.registry()["subsidy"], "subsidy")


@app.get("/api/portfolio")
def portfolio():
    """작목 조합의 위험 분산 효과 — 평균·분산 접근."""
    return _need(svc.registry()["portfolio"], "portfolio")


@app.get("/api/region")
def region():
    """시군구 단위 품목별 단가 — 지도 시각화용."""
    return _need(svc.registry()["region"], "region_stats")


# ---------------------------------------------------------------------------
# 정적 프런트엔드 (빌드되어 있을 때만)
# ---------------------------------------------------------------------------
if os.path.isdir(DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        target = os.path.join(DIST, full_path)
        if full_path and os.path.isfile(target):
            return FileResponse(target)
        return FileResponse(os.path.join(DIST, "index.html"))
