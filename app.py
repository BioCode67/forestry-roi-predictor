"""
임가 맞춤형 ROI 예측 & 최적 출하시기 추천 대시보드
2026년 임업통계 활용 경진대회 — 데이터 분석 부문

실행: streamlit run app.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import xgboost as xgb
from plotly.subplots import make_subplots

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

from preprocess import (  # noqa: E402
    AGE_MIDPOINT, CATEGORICALS, FALLBACK_CODEBOOK, add_derived_features, parse_codebook,
)
from preprocess_cost import CODEBOOK as COST_CODEBOOK  # noqa: E402
from preprocess_cost import add_derived_cost_features  # noqa: E402
from shipping import HARVEST_CALENDAR, SECTOR_TO_ITEMS, load_kamis, recommend  # noqa: E402

MODEL_DIR = os.path.join(ROOT, "models")
DATA = os.path.join(ROOT, "data", "processed_forestry_data.parquet")
FIG_DIR = os.path.join(ROOT, "reports", "figures")

GREEN = "#2E7D32"
GREY = "#90A4AE"
AMBER = "#EF6C00"

st.set_page_config(page_title="임가 ROI 예측 대시보드", page_icon="🌲", layout="wide")


# ---------------------------------------------------------------------------
# 로딩
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def load_model():
    p = os.path.join(MODEL_DIR, "best_xgboost_roi.json")
    if not os.path.exists(p):
        return None, None, None
    bst = xgb.Booster()
    bst.load_model(p)
    bst.set_param({"device": "cpu"})  # 서빙은 CPU로 충분 (GPU는 학습 전용)
    with open(os.path.join(MODEL_DIR, "feature_schema.json"), encoding="utf-8") as f:
        schema = json.load(f)
    with open(os.path.join(MODEL_DIR, "metrics_summary.json"), encoding="utf-8") as f:
        metrics = json.load(f)
    return bst, schema, metrics


@st.cache_data(show_spinner=False)
def load_data():
    return pd.read_parquet(DATA) if os.path.exists(DATA) else None


@st.cache_resource(show_spinner=False)
def load_cost_model():
    """Model B — 임산물생산비조사 기반 품목별 ROI 모델 (없으면 None)."""
    p = os.path.join(MODEL_DIR, "best_xgboost_cost.json")
    sp = os.path.join(MODEL_DIR, "feature_schema_cost.json")
    mp = os.path.join(MODEL_DIR, "metrics_cost.json")
    if not all(os.path.exists(x) for x in (p, sp, mp)):
        return None, None, None
    b = xgb.Booster()
    b.load_model(p)
    b.set_param({"device": "cpu"})
    with open(sp, encoding="utf-8") as f:
        s = json.load(f)
    with open(mp, encoding="utf-8") as f:
        m = json.load(f)
    return b, s, m


@st.cache_data(show_spinner=False)
def load_cost_data():
    p = os.path.join(ROOT, "data", "processed_cost_data.parquet")
    return pd.read_parquet(p) if os.path.exists(p) else None


@st.cache_data(show_spinner=False)
def load_insights():
    p = os.path.join(MODEL_DIR, "insights.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def load_codebook():
    try:
        return parse_codebook()
    except Exception:  # noqa: BLE001
        return dict(FALLBACK_CODEBOOK)


@st.cache_data(show_spinner=False)
def load_prices():
    try:
        return load_kamis()
    except Exception:  # noqa: BLE001
        return None


def inv_transform(z, kind):
    return np.sign(z) * np.expm1(np.abs(z)) if kind == "signed_log" else z


# ---------------------------------------------------------------------------
def build_input_frame(vals: dict, schema: dict) -> pd.DataFrame:
    """입력 폼 → 학습과 동일한 파생변수를 가진 1행 피처 프레임."""
    row = pd.DataFrame([vals])
    row = add_derived_features(row)
    X = row.reindex(columns=schema["features"])
    for c in schema["categorical"]:
        X[c] = pd.Categorical(
            X[c].astype("Int64").fillna(-1).to_numpy(dtype="int64"),
            categories=schema["categories"][c],
        )
    for c in schema["numeric"]:
        X[c] = pd.to_numeric(X[c], errors="coerce").astype("float64")
    return X.replace([np.inf, -np.inf], np.nan)


def predict_roi(bst, schema, X) -> float:
    d = xgb.DMatrix(X, enable_categorical=True)
    return float(inv_transform(bst.predict(d)[0], schema.get("target_transform", "none")))


# ---------------------------------------------------------------------------
# 사이드바 — 임가 제원 입력
# ---------------------------------------------------------------------------
bst, schema, metrics = load_model()
df = load_data()
codebook = load_codebook()
kamis = load_prices()

st.sidebar.title("🌲 임가 제원 입력")
if bst is None:
    st.sidebar.error("학습된 모델이 없습니다.\n`python src/train_optuna.py` 를 먼저 실행하세요.")
    st.stop()

inv_cb = {k: {v: code for code, v in codebook.get(k, {}).items()} for k in CATEGORICALS}


def pick(label: str, key: str) -> int:
    opts = list(codebook.get(key, {}).values())
    sel = st.sidebar.selectbox(label, opts, key=f"sel_{key}")
    return int(inv_cb[key][sel])


st.sidebar.caption("임가경제조사 코드 체계와 동일한 구분입니다.")
v_region = pick("지역", "지역별")
v_sector = pick("영림 업종", "업종별")
v_scale = pick("임지 규모", "임지규모별")
v_type = pick("전업/겸업 구분", "전/겸업별")
v_age = pick("경영주 연령대", "연령별")
v_members = pick("가구원 수", "가구원수별")

st.sidebar.markdown("---")
st.sidebar.subheader("경영 규모 (원)")
v_cost = st.sidebar.number_input(
    "연간 임업경영비", min_value=0, max_value=500_000_000,
    value=15_000_000, step=1_000_000, format="%d",
    help="종묘·비료·농약·고용노력·감가상각 등 임업 생산에 투입하는 연간 비용",
)
v_offfarm = st.sidebar.number_input(
    "임업외소득", min_value=-100_000_000, max_value=500_000_000,
    value=8_000_000, step=1_000_000, format="%d",
)
v_capital = st.sidebar.number_input(
    "기초 자본(순재산)", min_value=0, max_value=5_000_000_000,
    value=400_000_000, step=10_000_000, format="%d",
)
v_cash = st.sidebar.number_input(
    "연초 보유 현금", min_value=0, max_value=1_000_000_000,
    value=3_000_000, step=1_000_000, format="%d",
)
v_year = st.sidebar.select_slider(
    "기준 연도", options=[2019, 2020, 2021, 2022, 2023], value=2023
)

form_vals = {
    "연령별": v_age, "지역별": v_region, "전/겸업별": v_type, "업종별": v_sector,
    "가구원수별": v_members, "임지규모별": v_scale,
    "임업경영비": float(v_cost), "임업외소득": float(v_offfarm),
    "기초_자본(순재산)": float(v_capital), "연초보유": float(v_cash),
    "조사연도": float(v_year),
}
sector_label = codebook["업종별"][v_sector]
region_label = codebook["지역별"][v_region]

# ---------------------------------------------------------------------------
# 헤더
# ---------------------------------------------------------------------------
st.title("임가 맞춤형 ROI 예측 & 최적 출하시기 추천")
st.caption(
    "산림청 국가승인통계 「임가경제조사」 총괄 마이크로데이터(2019~2023, 통계청 MDIS) "
    "기반 CUDA XGBoost 예측 모델 · 2026년 임업통계 활용 경진대회 데이터 분석 부문"
)

X = build_input_frame(form_vals, schema)
roi = predict_roi(bst, schema, X)
est_income = roi / 100.0 * v_cost
est_revenue = v_cost + est_income

# 산림청 현행 방식(지역×업종 단순평균) 값
base_roi = np.nan
if df is not None:
    g = df[(df["지역별"] == v_region) & (df["업종별"] == v_sector)]["ROI"]
    if len(g) < 5:
        g = df[df["업종별"] == v_sector]["ROI"]
    base_roi = float(g.mean()) if len(g) else float(df["ROI"].mean())

c1, c2, c3, c4 = st.columns(4)
c1.metric("예측 임업 ROI", f"{roi:,.1f} %",
          delta=f"{roi - base_roi:+.1f}%p vs 지역·업종 평균" if np.isfinite(base_roi) else None)
c2.metric("예상 임업소득", f"{est_income:,.0f} 원")
c3.metric("예상 임업총수입", f"{est_revenue:,.0f} 원")
c4.metric("투입 임업경영비", f"{v_cost:,.0f} 원")

if np.isfinite(base_roi):
    gap = est_income - base_roi / 100.0 * v_cost
    if abs(gap) > 1_000:
        st.info(
            f"**{region_label} · {sector_label}** 조건에서 현행 산림청 단순평균 방식은 "
            f"ROI {base_roi:,.1f}%(임업소득 {base_roi/100*v_cost:,.0f}원)로 일괄 안내하지만, "
            f"본 모델은 귀 임가 고유 특성을 반영해 **{roi:,.1f}%({est_income:,.0f}원)** 로 예측합니다. "
            f"차이는 **{gap:+,.0f}원**입니다."
        )

tab1, tab5, tab6, tab2, tab3, tab4 = st.tabs(
    ["📈 예측 & 경영 진단", "🌰 품목별 정밀 진단", "💡 수익 개선 인사이트",
     "🚚 최적 출하시기", "🏆 모델 성능 비교", "📊 데이터·방법론"]
)

# ---------------------------------------------------------------------------
# TAB 1 — 예측 & 경영 진단
# ---------------------------------------------------------------------------
with tab1:
    left, right = st.columns([3, 2])

    with left:
        st.subheader("임업경영비 투입 수준별 ROI 반응곡선")
        st.caption("다른 조건을 고정하고 경영비만 변화시켰을 때 모델이 예측하는 ROI·임업소득")
        grid = np.unique(np.clip(
            np.concatenate([np.linspace(max(v_cost * 0.2, 1e6), v_cost * 2.5, 40), [v_cost]]),
            1e5, 5e8,
        ))
        rows = []
        for c in grid:
            vv = dict(form_vals, 임업경영비=float(c))
            r = predict_roi(bst, schema, build_input_frame(vv, schema))
            rows.append({"경영비": c, "ROI": r, "임업소득": r / 100 * c})
        curve = pd.DataFrame(rows)
        best = curve.loc[curve["임업소득"].idxmax()]

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=curve["경영비"], y=curve["ROI"], name="예측 ROI (%)",
                                 line=dict(color=GREEN, width=3)), secondary_y=False)
        fig.add_trace(go.Scatter(x=curve["경영비"], y=curve["임업소득"], name="예상 임업소득 (원)",
                                 line=dict(color=AMBER, width=2, dash="dot")), secondary_y=True)
        fig.add_vline(x=v_cost, line_dash="dash", line_color="#555",
                      annotation_text="현재 투입", annotation_position="top")
        fig.add_vline(x=float(best["경영비"]), line_dash="dot", line_color=AMBER,
                      annotation_text="소득 최대점", annotation_position="bottom")
        fig.update_xaxes(title="연간 임업경영비 (원)")
        fig.update_yaxes(title="예측 ROI (%)", secondary_y=False)
        fig.update_yaxes(title="예상 임업소득 (원)", secondary_y=True)
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10),
                          legend=dict(orientation="h", y=1.12))
        st.plotly_chart(fig, width="stretch")

        delta_income = float(best["임업소득"]) - est_income
        if delta_income > 100_000 and abs(best["경영비"] - v_cost) > 500_000:
            direction = "증액" if best["경영비"] > v_cost else "감축"
            st.success(
                f"**경영비 최적화 제안** — 현재 {v_cost:,.0f}원 → "
                f"**{best['경영비']:,.0f}원**으로 {direction} 시 "
                f"예상 임업소득이 **{delta_income:+,.0f}원** 개선됩니다 "
                f"(ROI {roi:,.1f}% → {best['ROI']:,.1f}%)."
            )
        else:
            st.success("**경영비 최적화 제안** — 현재 투입 수준이 예측 소득 최대 구간에 근접합니다.")

    with right:
        st.subheader("동일 조건 임가 분포 내 위치")
        if df is not None:
            peer = df[(df["업종별"] == v_sector)]
            pct = float((peer["ROI"] < roi).mean() * 100) if len(peer) else np.nan
            fig2 = go.Figure()
            fig2.add_trace(go.Histogram(x=peer["ROI"], nbinsx=40, marker_color=GREY,
                                        name=f"{sector_label} 임가 (n={len(peer)})"))
            fig2.add_vline(x=roi, line_color=GREEN, line_width=3,
                           annotation_text=f"귀 임가 {roi:,.0f}%")
            fig2.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10),
                               xaxis_title="임업 ROI (%)", yaxis_title="임가 수",
                               showlegend=False)
            st.plotly_chart(fig2, width="stretch")
            if np.isfinite(pct):
                st.metric(f"{sector_label} 내 백분위", f"상위 {100 - pct:,.0f}%")

        st.subheader("업종 전환 시뮬레이션")
        sims = []
        for code, label in codebook["업종별"].items():
            vv = dict(form_vals, 업종별=int(code))
            sims.append({"업종": label,
                         "예측 ROI(%)": predict_roi(bst, schema, build_input_frame(vv, schema))})
        sim = pd.DataFrame(sims).sort_values("예측 ROI(%)", ascending=False)
        sim["현재"] = sim["업종"] == sector_label
        fig3 = go.Figure(go.Bar(
            x=sim["예측 ROI(%)"], y=sim["업종"], orientation="h",
            marker_color=[GREEN if c else GREY for c in sim["현재"]],
            text=[f"{v:,.0f}%" for v in sim["예측 ROI(%)"]], textposition="outside",
        ))
        fig3.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10),
                           xaxis_title="동일 제원 가정 시 예측 ROI (%)",
                           yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig3, width="stretch")
        st.caption("동일한 지역·규모·자본 조건을 유지한 채 업종만 바꿨을 때의 모델 예측값입니다.")

# ---------------------------------------------------------------------------
# TAB 5 — 품목별 정밀 진단 (Model B: 임산물생산비조사)
# ---------------------------------------------------------------------------
cost_bst, cost_schema, cost_metrics = load_cost_model()
cost_df = load_cost_data()

RATIO_LABELS = {
    "노동비_비중": "노동비", "비료비_비중": "비료비", "농약비_비중": "농약비",
    "감가상각비_비중": "감가상각비", "위탁영농비_비중": "위탁영농비",
}


def build_cost_row(item: str, overrides: dict, schema: dict) -> pd.DataFrame:
    """품목 중앙값을 기준선으로 두고, 사용자가 지정한 항목만 덮어쓴 1행 피처."""
    base = dict(schema["item_medians"].get(item, schema["train_medians"]))
    base = {k: (np.nan if v is None else v) for k, v in base.items()}
    base.update(overrides)
    base["품목"] = item
    row = pd.DataFrame([base])
    row = add_derived_cost_features(row)
    X = row.reindex(columns=schema["features"])
    for c in schema["categorical"]:
        v = X[c].iloc[0]
        if c == "품목":
            v = schema["item_map"].get(item, -1)
        X[c] = pd.Categorical(
            pd.Series([v]).astype("Int64").fillna(-1).to_numpy(dtype="int64"),
            categories=schema["categories"][c],
        )
    for c in schema["numeric"]:
        X[c] = pd.to_numeric(X[c], errors="coerce").astype("float64")
    return X.replace([np.inf, -np.inf], np.nan)


def predict_cost_roi(X) -> float:
    z = cost_bst.predict(xgb.DMatrix(X, enable_categorical=True))[0]
    return float(inv_transform(z, cost_schema.get("target_transform", "none")))


with tab5:
    if cost_bst is None:
        st.info(
            "품목별 모델이 아직 학습되지 않았습니다.\n\n"
            "```bash\npython src/preprocess_cost.py\npython src/train_cost.py\n```"
        )
    else:
        st.caption(
            "산림청 국가승인통계 **「임산물생산비조사」** 마이크로데이터 기반 "
            "품목 단위 정밀 모델입니다. 임가경제조사가 임가 전체의 종합 수익성을 다루는 데 비해, "
            "본 모델은 **비목별 지출과 작업 공정별 노동 배분**까지 반영합니다."
        )
        items = list(cost_schema["item_map"].keys())
        ic1, ic2, ic3, ic4 = st.columns(4)
        c_item = ic1.selectbox("품목", items, index=items.index("밤") if "밤" in items else 0)
        c_region = ic2.selectbox(
            "지역", list(COST_CODEBOOK["지역별"].values()), index=6, key="cost_region")
        c_level = ic3.selectbox("경영수준", list(COST_CODEBOOK["경영수준별"].values()))
        c_scale = ic4.selectbox("재배규모", list(COST_CODEBOOK["규모별"].values()))

        unit = "만본" if "표고" in c_item else "ha"
        base_med = cost_schema["item_medians"].get(c_item, {})

        st.markdown(f"**투입 계획 ({unit}당)**")
        p1, p2, p3, p4 = st.columns(4)

        def med(key, fallback):
            v = base_med.get(key)
            return float(v) if v is not None and np.isfinite(v) else float(fallback)

        c_cost = p1.number_input(f"경영비 (원/{unit})", min_value=0.0,
                                 value=med("경영비", 5e6), step=100_000.0, format="%.0f")
        c_fert = p2.number_input(f"비료비 (원/{unit})", min_value=0.0,
                                 value=med("비료비_단위당", 3e5), step=50_000.0, format="%.0f")
        c_pest = p3.number_input(f"농약비 (원/{unit})", min_value=0.0,
                                 value=med("농약비_단위당", 2e5), step=50_000.0, format="%.0f")
        c_hours = p4.number_input(f"총 노동시간 ({unit}당)", min_value=0.0,
                                  value=med("총노동시간_합계_단위당", 500.0), step=10.0, format="%.0f")

        inv_cost_cb = {k: {v: c for c, v in d.items()} for k, d in COST_CODEBOOK.items()}
        overrides = {
            "지역별": inv_cost_cb["지역별"][c_region],
            "경영수준별": inv_cost_cb["경영수준별"][c_level],
            "규모별": inv_cost_cb["규모별"][c_scale],
            "경영비": c_cost, "비료비_단위당": c_fert, "농약비_단위당": c_pest,
            "총노동시간_합계_단위당": c_hours,
        }
        Xc = build_cost_row(c_item, overrides, cost_schema)
        roi_c = predict_cost_roi(Xc)
        income_c = roi_c / 100.0 * c_cost

        peer = cost_df[cost_df["품목"] == c_item] if cost_df is not None else None
        lead = peer[peer["경영수준별"] == 1] if peer is not None else None

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(f"예측 ROI ({unit}당)", f"{roi_c:,.1f} %")
        m2.metric(f"예상 소득 (원/{unit})", f"{income_c:,.0f}")
        if peer is not None and len(peer):
            m3.metric(f"{c_item} 전체 중앙값", f"{peer['ROI'].median():,.1f} %",
                      delta=f"{roi_c - peer['ROI'].median():+.1f}%p")
        if lead is not None and len(lead):
            m4.metric("선도임가 중앙값", f"{lead['ROI'].median():,.1f} %",
                      delta=f"{roi_c - lead['ROI'].median():+.1f}%p")

        st.markdown("---")
        g1, g2 = st.columns(2)

        with g1:
            st.subheader("비목 구성 — 선도임가 대비")
            if lead is not None and len(lead):
                ratio_cols = [c for c in RATIO_LABELS if c in Xc.columns and c in lead.columns]
                mine = [float(Xc[c].iloc[0]) * 100 for c in ratio_cols]
                theirs = [float(lead[c].median()) * 100 for c in ratio_cols]
                names = [RATIO_LABELS[c] for c in ratio_cols]
                f = go.Figure()
                f.add_trace(go.Bar(x=names, y=mine, name="귀 임가", marker_color=GREEN))
                f.add_trace(go.Bar(x=names, y=theirs, name="선도임가 중앙값",
                                   marker_color=GREY))
                f.update_layout(barmode="group", height=340, yaxis_title="경영비 대비 비중 (%)",
                                margin=dict(l=10, r=10, t=20, b=10),
                                legend=dict(orientation="h", y=1.15))
                st.plotly_chart(f, width="stretch")

                diffs = [(RATIO_LABELS[c], (float(Xc[c].iloc[0]) - float(lead[c].median())) * 100)
                         for c in ratio_cols if np.isfinite(float(Xc[c].iloc[0]))]
                over = sorted(diffs, key=lambda kv: -kv[1])[:2]
                if over and over[0][1] > 2:
                    st.warning(
                        "**비목 과다 투입 신호** — "
                        + ", ".join(f"{n} +{d:.1f}%p" for n, d in over if d > 2)
                        + " 만큼 선도임가보다 비중이 높습니다. 해당 비목의 절감 여지를 검토하세요."
                    )

        with g2:
            st.subheader("품목별 ROI 분포")
            if cost_df is not None:
                f2 = go.Figure()
                for it in cost_df["품목"].unique():
                    f2.add_trace(go.Box(
                        y=cost_df.loc[cost_df["품목"] == it, "ROI"], name=it,
                        boxpoints=False,
                        marker_color=GREEN if it == c_item else GREY))
                f2.add_hline(y=roi_c, line_color=AMBER, line_dash="dash",
                             annotation_text=f"귀 임가 예측 {roi_c:,.0f}%")
                f2.update_layout(height=340, showlegend=False,
                                 yaxis_title=f"단위면적당 ROI (%)",
                                 margin=dict(l=10, r=10, t=20, b=10))
                st.plotly_chart(f2, width="stretch")
                st.caption(
                    "밤·대추·떫은감은 ha당, 표고(노지)는 만본당 기준. "
                    "ROI는 비율 지표이므로 품목 간 비교가 가능합니다."
                )

        st.subheader("경영비 반응곡선")
        cg = np.linspace(max(c_cost * 0.3, 1e5), c_cost * 2.0, 30)
        cr = []
        for cv in cg:
            Xt = build_cost_row(c_item, dict(overrides, 경영비=float(cv)), cost_schema)
            r = predict_cost_roi(Xt)
            cr.append({"경영비": cv, "ROI": r, "소득": r / 100 * cv})
        cc = pd.DataFrame(cr)
        cbest = cc.loc[cc["소득"].idxmax()]
        f3 = make_subplots(specs=[[{"secondary_y": True}]])
        f3.add_trace(go.Scatter(x=cc["경영비"], y=cc["ROI"], name="예측 ROI (%)",
                                line=dict(color=GREEN, width=3)), secondary_y=False)
        f3.add_trace(go.Scatter(x=cc["경영비"], y=cc["소득"], name=f"예상 소득 (원/{unit})",
                                line=dict(color=AMBER, width=2, dash="dot")), secondary_y=True)
        f3.add_vline(x=c_cost, line_dash="dash", line_color="#555", annotation_text="현재")
        f3.update_xaxes(title=f"경영비 (원/{unit})")
        f3.update_yaxes(title="예측 ROI (%)", secondary_y=False)
        f3.update_yaxes(title=f"예상 소득 (원/{unit})", secondary_y=True)
        f3.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10),
                         legend=dict(orientation="h", y=1.12))
        st.plotly_chart(f3, width="stretch")
        if float(cbest["소득"]) - income_c > 10_000:
            st.success(
                f"**최적 투입 제안** — 경영비 {c_cost:,.0f} → **{cbest['경영비']:,.0f}원/{unit}** 조정 시 "
                f"예상 소득이 {float(cbest['소득']) - income_c:+,.0f}원/{unit} 개선됩니다."
            )

        with st.expander("Model B 성능 및 품목별 정확도"):
            cm = cost_metrics
            rows = [{"모델": lab, "R²": round(cm[k]["test"]["R2"], 4),
                     "RMSE": round(cm[k]["test"]["RMSE"], 2),
                     "MAE": round(cm[k]["test"]["MAE"], 2)}
                    for k, lab in [("forest_service_baseline", "산림청 단순평균(품목×지역)"),
                                   ("linear_regression", "다중 선형회귀"),
                                   ("optuna_xgboost", "Optuna-XGBoost")] if k in cm]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            if cm.get("per_item_test"):
                st.dataframe(
                    pd.DataFrame(cm["per_item_test"]).T.round(3).reset_index(names="품목"),
                    width="stretch", hide_index=True)
            ci = os.path.join(FIG_DIR, "cost_feature_importance.png")
            if os.path.exists(ci):
                st.image(ci, width="stretch")


# ---------------------------------------------------------------------------
# TAB 6 — 수익 개선 인사이트 (기술통계 계층)
# ---------------------------------------------------------------------------
insights = load_insights()

with tab6:
    if insights is None:
        st.info("`python src/insights.py` 를 실행하면 인사이트가 생성됩니다.")
    else:
        st.caption(
            "예측 모델이 *얼마를 벌 수 있는가* 에 답한다면, 이 탭은 "
            "**어떻게 하면 더 벌 수 있는가** 에 대한 정량 근거를 「임산물생산비조사」 "
            "원데이터에서 직접 추출한 결과입니다. 기술통계 계층이며 예측 모델의 "
            "설명변수로는 사용하지 않습니다."
        )

        # --- ① 품질 등급 단가 ------------------------------------------------
        st.subheader("① 품질 등급·가공 형태별 단가 격차")
        grades = insights.get("등급별_단가", {})
        gsel = st.radio("품목", list(grades), horizontal=True, key="grade_item")
        if gsel:
            info = grades[gsel]
            rows = info["등급"]
            gc1, gc2 = st.columns([3, 2])
            with gc1:
                f = go.Figure(go.Bar(
                    x=[r["구분"] for r in rows],
                    y=[r["단가_원per단위수량"] for r in rows],
                    marker_color=[GREEN if i == 0 else GREY for i in range(len(rows))],
                    text=[f"{r['단가_원per단위수량']:,.0f}원" for r in rows],
                    textposition="outside",
                ))
                f.update_layout(height=330, yaxis_title="단가 (원 / 수량단위)",
                                margin=dict(l=10, r=10, t=20, b=10))
                st.plotly_chart(f, width="stretch")
            with gc2:
                st.dataframe(
                    pd.DataFrame(rows).rename(columns={
                        "단가_원per단위수량": "단가(원)", "구성비_pct": "구성비(%)"}),
                    width="stretch", hide_index=True)
                if info.get("직접비교_가능"):
                    st.metric("최고 / 최저 단가 배수", f"{info['최고_최저_단가배수']:,.2f} 배")
                st.caption(info.get("주석", ""))

            sim = insights.get("등급전환_시뮬레이션", {}).get(gsel)
            if sim:
                st.success(
                    f"**품질 개선 효과** — {sim['전환_시나리오']} 시 "
                    f"단위면적당 수취액 **{sim['수취액_증가_원per단위면적']:+,.0f}원** 증가 "
                    f"(등급 간 단가차 {sim['단가차_원']:,.0f}원 × 전환 물량). "
                    f"선별·전정 등 품질관리 강화의 경제적 가치입니다."
                )
            elif not info.get("직접비교_가능"):
                st.info(
                    "가공 형태 구분은 원물과 가공품의 수량 기준이 달라 건조 감모율이 "
                    "반영되지 않으므로, 물량 전환 시뮬레이션은 수행하지 않습니다."
                )

        st.markdown("---")

        # --- ③ 수령별 수익성 ------------------------------------------------
        st.subheader("② 수령(樹齡)별 수익성 곡선 — 갱신·개식 판단 근거")
        ages = insights.get("수령별_수익성", {})
        if ages:
            f2 = go.Figure()
            palette = [GREEN, AMBER, "#1565C0"]
            for (item, info), col in zip(ages.items(), palette):
                d = pd.DataFrame(info["구간"])
                f2.add_trace(go.Scatter(
                    x=d["수령구간"].astype(str), y=d["ROI중앙값"], mode="lines+markers",
                    name=f"{item} (n={int(d['표본'].sum()):,})",
                    line=dict(color=col, width=3), marker=dict(size=9)))
            f2.add_hline(y=0, line_dash="dash", line_color="#888")
            f2.update_layout(height=380, xaxis_title="수령", yaxis_title="ROI 중앙값 (%)",
                             margin=dict(l=10, r=10, t=20, b=10),
                             legend=dict(orientation="h", y=1.12))
            st.plotly_chart(f2, width="stretch")

            acols = st.columns(len(ages))
            for col, (item, info) in zip(acols, ages.items()):
                col.metric(f"{item} 최고 수익 구간", info["최고구간"],
                           delta=f"{info['최고ROI']:,.0f}% (최저 {info['최저구간']} "
                                 f"{info['최저ROI']:,.0f}%)")
            st.caption(
                "수령 구간별 ROI 중앙값입니다. 수익성이 정점을 지나 하락하는 구간은 "
                "갱신·개식 또는 수형 개선을 검토할 시점을 시사합니다."
            )

        st.markdown("---")

        # --- ④ 선도임가 격차 ------------------------------------------------
        st.subheader("③ 선도임가 벤치마크 — 비목 구조의 차이")
        gaps = insights.get("선도임가_격차", {})
        if gaps:
            lsel = st.selectbox("품목", list(gaps), key="leader_item")
            g = gaps[lsel]
            labels = ["노동비", "비료비", "농약비", "감가상각비", "위탁영농비"]
            lead = [g["선도임가"].get(f"{x}_비중pct") for x in labels]
            rest = [g["이외임가"].get(f"{x}_비중pct") for x in labels]

            lc1, lc2 = st.columns([3, 2])
            with lc1:
                f3 = go.Figure()
                f3.add_trace(go.Bar(x=labels, y=lead, name="선도임가", marker_color=GREEN))
                f3.add_trace(go.Bar(x=labels, y=rest, name="이외임가", marker_color=GREY))
                f3.update_layout(barmode="group", height=340,
                                 yaxis_title="경영비 대비 비중 (%)",
                                 margin=dict(l=10, r=10, t=20, b=10),
                                 legend=dict(orientation="h", y=1.15))
                st.plotly_chart(f3, width="stretch")
            with lc2:
                st.dataframe(pd.DataFrame({
                    "비목": labels,
                    "선도임가(%)": lead,
                    "이외임가(%)": rest,
                    "차이(%p)": [None if (a is None or b is None) else round(a - b, 1)
                                for a, b in zip(lead, rest)],
                }), width="stretch", hide_index=True)
                st.metric("총 노동시간 (선도 / 이외)",
                          f"{g['선도임가'].get('총노동시간', 0):,.0f} / "
                          f"{g['이외임가'].get('총노동시간', 0):,.0f} 시간")
            if g.get("해석_유의"):
                st.warning("**해석 유의** — " + g["해석_유의"])

        st.markdown("---")

        # --- ⑤ 지역 × 품목 ---------------------------------------------------
        st.subheader("④ 지역 × 품목 수익성 지도")
        rm = insights.get("지역x품목", {})
        if rm.get("matrix"):
            mat = pd.DataFrame(rm["matrix"])
            f4 = go.Figure(go.Heatmap(
                z=mat.to_numpy(dtype=float), x=list(mat.columns), y=list(mat.index),
                colorscale="RdYlGn", colorbar=dict(title="ROI 중앙값(%)"),
                text=mat.to_numpy(dtype=float), texttemplate="%{text:,.0f}",
                hovertemplate="%{y} · %{x}<br>ROI %{z:,.1f}%<extra></extra>"))
            f4.update_layout(height=420, margin=dict(l=10, r=10, t=20, b=10))
            st.plotly_chart(f4, width="stretch")
            best = rm.get("품목별_최적지역", {})
            if best:
                st.dataframe(
                    pd.DataFrame([{"품목": k, "최고 수익 지역": v["지역"],
                                   "ROI 중앙값(%)": v["ROI"]} for k, v in best.items()]),
                    width="stretch", hide_index=True)
            st.caption("표본 15건 이상인 조합만 표시합니다.")


# ---------------------------------------------------------------------------
# TAB 2 — 최적 출하시기
# ---------------------------------------------------------------------------
with tab2:
    st.subheader(f"{sector_label} — 출하시기 추천")
    rec = recommend(sector_label, kamis)

    if rec["status"] == "not_applicable":
        st.warning(rec["message"])
    else:
        if rec["status"] == "no_price_data":
            st.warning(
                "⚠️ **KAMIS 도매가격 데이터 미연결** — 현재는 산림청 표준 수확·출하 캘린더만 "
                "표시합니다. 가격 기반 최적월 추천을 켜려면 아래를 실행하세요.\n\n"
                "```bash\npython scripts/fetch_kamis.py --cert-key <KEY> --cert-id <ID>\n```\n"
                "산출된 `data/kamis/kamis_monthly.csv` 를 인식하면 자동 활성화됩니다."
            )

        for item in rec["items"]:
            with st.container(border=True):
                a, b = st.columns([2, 3])
                with a:
                    st.markdown(f"### {item['품목']}")
                    st.write(f"**수확기** · {', '.join(f'{m}월' for m in item['수확기'])}")
                    st.write(f"**출하 가능** · {', '.join(f'{m}월' for m in item['출하가능월'])}")
                    st.write(f"**저장성** · {item['저장성']}")
                    if item.get("추천월"):
                        st.metric("추천 출하월", f"{item['추천월']}월",
                                  delta=f"수확기 대비 {item['수확기대비_가격이득_pct']:+.1f}%p")
                    st.caption(item["추천근거"])
                with b:
                    months = list(range(1, 13))
                    if item.get("가격데이터"):
                        pi = pd.DataFrame(item["가격데이터"])
                        colors = [GREEN if m == item["추천월"] else GREY for m in pi["월"]]
                        f = go.Figure(go.Bar(x=pi["월"], y=pi["가격지수"], marker_color=colors))
                        f.add_hline(y=100, line_dash="dash", line_color="#555",
                                    annotation_text="연평균 = 100")
                        f.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10),
                                        xaxis=dict(title="월", tickmode="linear", dtick=1),
                                        yaxis_title="KAMIS 도매가 지수")
                    else:
                        harvest = set(item["수확기"])
                        ship = set(item["출하가능월"])
                        f = go.Figure(go.Bar(
                            x=months,
                            y=[2 if m in harvest else (1 if m in ship else 0) for m in months],
                            marker_color=[GREEN if m in harvest else
                                          (AMBER if m in ship else "#ECEFF1") for m in months],
                        ))
                        f.update_layout(
                            height=260, margin=dict(l=10, r=10, t=10, b=10),
                            xaxis=dict(title="월", tickmode="linear", dtick=1),
                            yaxis=dict(title="", tickvals=[0, 1, 2],
                                       ticktext=["-", "출하가능", "수확기"]),
                        )
                    st.plotly_chart(f, width="stretch")

    with st.expander("업종 ↔ KAMIS 품목 매핑 및 캘린더 근거"):
        st.dataframe(pd.DataFrame([
            {"업종": s, "KAMIS 대응 품목": ", ".join(i) if i else "해당 없음",
             "수확기": ", ".join(
                 f"{it}:{'·'.join(str(m) for m in HARVEST_CALENDAR[it]['수확기'])}월"
                 for it in i if it in HARVEST_CALENDAR) or "-"}
            for s, i in SECTOR_TO_ITEMS.items()
        ]), width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# TAB 3 — 모델 성능 비교
# ---------------------------------------------------------------------------
with tab3:
    st.subheader("3종 모델 벤치마크 (Test set)")
    rows, keys = [], [
        ("forest_service_baseline", "① 산림청 단순평균 (현행)"),
        ("linear_regression", "② 다중 선형회귀"),
        ("optuna_xgboost", "③ Optuna-XGBoost (제안)"),
    ]
    for k, label in keys:
        m = metrics[k]["test"]
        rows.append({"모델": label, "R²": round(m["R2"], 4),
                     "RMSE (%p)": round(m["RMSE"], 2), "MAE (%p)": round(m["MAE"], 2)})
    perf = pd.DataFrame(rows)
    st.dataframe(perf, width="stretch", hide_index=True)

    imp = metrics.get("improvement_vs_baseline", {})
    d1, d2, d3 = st.columns(3)
    d1.metric("R² 개선", f"{imp.get('R2_delta', 0):+.4f}")
    d2.metric("RMSE 감소", f"{imp.get('RMSE_reduction_pct', 0):.1f} %")
    d3.metric("MAE 감소", f"{imp.get('MAE_reduction_pct', 0):.1f} %")

    fig4 = make_subplots(rows=1, cols=3, subplot_titles=("R² (↑)", "RMSE (↓)", "MAE (↓)"))
    for i, col in enumerate(["R²", "RMSE (%p)", "MAE (%p)"], start=1):
        fig4.add_trace(go.Bar(x=perf["모델"], y=perf[col], marker_color=[GREY, "#607D8B", GREEN],
                              text=[f"{v:,.3f}" if col == "R²" else f"{v:,.1f}" for v in perf[col]],
                              textposition="outside", showlegend=False), row=1, col=i)
    fig4.update_layout(height=380, margin=dict(l=10, r=10, t=50, b=80))
    fig4.update_xaxes(tickangle=-20, tickfont=dict(size=9))
    st.plotly_chart(fig4, width="stretch")

    st.subheader("변수 중요도")
    cc1, cc2 = st.columns(2)
    fi = os.path.join(FIG_DIR, "feature_importance.png")
    sh = os.path.join(FIG_DIR, "shap_summary.png")
    if os.path.exists(fi):
        cc1.image(fi, width="stretch")
    if os.path.exists(sh):
        cc2.image(sh, width="stretch")

    with st.expander("최적 하이퍼파라미터 (Optuna)"):
        ox = metrics["optuna_xgboost"]
        st.write(f"탐색 시행 {ox.get('n_trials')}회 · {ox.get('n_folds')}-fold CV · "
                 f"GPU {ox.get('gpus_used')}장 · 목표변수 변환 `{ox.get('target_transform')}`")
        st.json(ox["best_params"])

# ---------------------------------------------------------------------------
# TAB 4 — 데이터·방법론
# ---------------------------------------------------------------------------
with tab4:
    ds = metrics["dataset"]
    st.subheader("사용 데이터")
    st.markdown(
        f"""
| 항목 | 내용 |
|---|---|
| 필수 임업통계 | 산림청 국가승인통계 **「임가경제조사」 총괄(제공) 마이크로데이터** |
| 제공기관 | 통계청 MDIS(마이크로데이터 통합서비스) / 산림청 · 한국임업진흥원 |
| 대상 연도 | 2019 ~ 2023 (5개년) |
| 원시 표본 | 5,940 임가-연도 |
| 분석 표본 | **{ds['rows']:,}** 임가-연도 (임업 미영위 450건 제외, IQR 이상치 1,052건 제거) |
| 융복합 공공데이터 | KAMIS 농수산물유통정보 월별 도매가격 (출하시기 모듈) |
| 목표변수 | {ds.get('target_definition', 'ROI(%) = 임업소득 ÷ 임업경영비 × 100')} |
| 설명변수 | {ds.get('n_features', len(ds['features']))}개 (범주형 6 + 수치·파생 {ds.get('n_features', len(ds['features'])) - 6}) |
| 분할 | Train {ds['train']:,} / Valid {ds['valid']:,} / Test {ds['test']:,} (seed {ds['seed']}) |
"""
    )
    st.subheader("업종별 ROI 프로파일")
    sp = os.path.join(FIG_DIR, "sector_roi_profile.png")
    if os.path.exists(sp):
        st.image(sp, width="stretch")

    st.subheader("정보 누출 통제")
    st.markdown(
        "ROI = 임업소득 / 임업경영비 이고 임업소득 = 임업총수입 − 임업경영비 이므로, "
        "**임업총수입·임업소득 및 이를 포함하는 합계항목**(임가소득, 경상소득, 임가순소득, "
        "임가처분가능소득, 임가경제잉여)은 설명변수에서 전면 제외했습니다. "
        "임업경영비는 분모이지만 분자인 임업총수입을 결정하지 않으므로, "
        "임가가 영농계획 시점에 스스로 정하는 **사전(ex-ante) 의사결정 변수**로서 사용합니다."
    )

    with st.expander("현재 입력값으로 생성된 피처 벡터"):
        st.dataframe(X.T.rename(columns={0: "값"}), width="stretch")

st.markdown("---")
st.caption(
    "2026년 임업통계 활용 경진대회 · 데이터 분석 부문 출품작 | "
    "모델: Optuna 튜닝 XGBoost (CUDA, NVIDIA RTX A6000 ×2) | "
    f"학습 데이터: 임가경제조사 총괄 마이크로데이터 {ds['rows']:,}건"
)
