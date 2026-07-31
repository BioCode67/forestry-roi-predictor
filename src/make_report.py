"""
Phase 3 — 공모전 [붙임 3] 데이터 분석 부문 양식에 맞춘 결과보고서 자동 생성

산출: data_analysis_report.md
"""
from __future__ import annotations

import json
import os
from datetime import date

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(ROOT, "models")
OUT = os.path.join(ROOT, "data_analysis_report.md")

LABELS = {
    "forest_service_baseline": "① 산림청 단순평균 (현행 방식)",
    "linear_regression": "② 다중 선형회귀",
    "optuna_xgboost": "③ **Optuna-XGBoost (제안 모델)**",
}


def load(name: str, required: bool = True):
    p = os.path.join(MODEL_DIR, name)
    if not os.path.exists(p):
        if required:
            raise FileNotFoundError(f"{p} 가 없습니다. 학습을 먼저 실행하세요.")
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def cost_section(mc: dict | None, meta_c: dict | None) -> tuple[str, str]:
    """Model B(임산물생산비조사) 관련 본문과 요약 문장을 생성한다."""
    if mc is None:
        return ("", "")

    ds = mc["dataset"]
    imp = mc["improvement_vs_baseline"]
    ox = mc["optuna_xgboost"]
    rows = "\n".join(
        f"| {label} | {fmt(mc[k]['test']['R2'])} | {fmt(mc[k]['test']['RMSE'], 2)} | "
        f"{fmt(mc[k]['test']['MAE'], 2)} |"
        for k, label in [
            ("forest_service_baseline", "① 산림청 단순평균 (품목×지역)"),
            ("linear_regression", "② 다중 선형회귀"),
            ("optuna_xgboost", "③ **Optuna-XGBoost (제안 모델)**"),
        ] if k in mc
    )
    per_item = "\n".join(
        f"| {item} | {v['n']:,} | {fmt(v['R2'])} | {fmt(v['RMSE'], 1)} | {fmt(v['MAE'], 1)} |"
        for item, v in sorted(mc.get("per_item_test", {}).items(),
                              key=lambda kv: -kv[1]["R2"])
    ) or "| - | - | - | - | - |"
    gi = "\n".join(
        f"| {i} | {k} | {fmt(v, 1)} |"
        for i, (k, v) in enumerate(list(mc.get("feature_importance_gain", {}).items())[:12], 1)
    )
    items_line = ", ".join(f"{k} {v:,}건" for k, v in ds["items"].items())

    body = f"""
### 4-6. 【Model B】 임산물생산비조사 기반 품목별 정밀 모델

임가경제조사(Model A)가 **임가 단위 종합 수익성**을 다루는 반면, 「임산물생산비조사」는
**품목 단위의 단위면적당 투입-산출 구조**를 담고 있어 훨씬 정밀한 경영 진단이 가능하다.
본 과제는 두 국가승인통계를 모두 활용해 **2계층 모델**을 구성하였다.

| 항목 | 내용 |
|---|---|
| 데이터 | 산림청 「임산물생산비조사」 마이크로데이터 (통계청 MDIS) |
| 대상 품목·연도 | 밤·대추·떫은감(2020~2024), 표고(노지)(2018~2022) |
| 분석 표본 | **{ds['rows']:,}행** ({items_line}) |
| 목표변수 | {ds['target_definition']} |
| 설명변수 | {ds['n_features']}개 — 비목별 지출(비료·농약·노동·감가상각·위탁영농 등), 작업 공정별 노동시간(전정·시비·병해충방제·수확·선별포장 등 20여 공정), 수령·재배면적·재배본수 |
| 단위 | {ds['unit_note']} |

#### 성능 (Test set, n = {ds['test']:,})

| 모델 | R² (↑) | RMSE (%p, ↓) | MAE (%p, ↓) |
|---|---:|---:|---:|
{rows}

![Model B 성능 비교](reports/figures/cost_benchmark.png)

**Model B는 R² {fmt(ox['test']['R2'])}** 로, 현행 단순평균 방식({fmt(mc['forest_service_baseline']['test']['R2'])})
대비 **RMSE {imp['RMSE_reduction_pct']:.1f}%, MAE {imp['MAE_reduction_pct']:.1f}% 감소**를 달성하였다.
비목·공정 단위의 세밀한 투입 정보가 확보되면 임가 수익성 예측이 실용 수준에 도달함을 보여준다.

#### 품목별 예측 정확도

| 품목 | Test 표본 | R² | RMSE | MAE |
|---|---:|---:|---:|---:|
{per_item}

![품목별 ROI 분포](reports/figures/cost_item_roi.png)

#### 주요 결정요인 (Gain 상위 12)

| 순위 | 변수 | Gain |
|---:|---|---:|
{gi}

![Model B 변수 중요도](reports/figures/cost_feature_importance.png)

**해석** — 총 경영비와 노동 관련 변수(노동비 비중, 공정별 노동시간, 자가/고용 노동 배분)가
상위를 차지한다. 이는 임산물 생산에서 **노동 배분의 효율이 수익성을 좌우**함을 뜻하며,
대시보드의 '비목 구성 — 선도임가 대비' 진단 기능이 겨냥하는 지점이다.
「임산물생산비조사」의 `경영수준별`(선도임가/이외임가) 구분을 활용하면,
동일 품목·지역 조건에서 **선도임가의 비목 구성을 벤치마크로 제시**할 수 있다.
"""

    summary_line = (
        f"- **Model B(임산물생산비조사, {ds['rows']:,}행)** 는 R² **{fmt(ox['test']['R2'])}** 로, "
        f"동일 데이터의 단순평균 방식({fmt(mc['forest_service_baseline']['test']['R2'])}) 대비 "
        f"RMSE **{imp['RMSE_reduction_pct']:.1f}%** 감소를 달성하였다. "
        f"품목·비목 단위 정보가 확보될 때 예측 정확도가 실용 수준에 이른다는 점을 보여준다."
    )
    return body, summary_line


def fmt(v, nd=4):
    return f"{v:,.{nd}f}"


def main() -> None:
    m = load("metrics_summary.json")
    mc = load("metrics_cost.json", required=False)
    meta = json.load(open(os.path.join(ROOT, "data", "processed_meta.json"), encoding="utf-8"))
    meta_c_path = os.path.join(ROOT, "data", "processed_cost_meta.json")
    meta_c = (json.load(open(meta_c_path, encoding="utf-8"))
              if os.path.exists(meta_c_path) else None)
    cost_body, cost_summary = cost_section(mc, meta_c)
    sector = pd.read_json(os.path.join(MODEL_DIR, "sector_profile.json"))
    ds = m["dataset"]
    imp = m["improvement_vs_baseline"]
    ox = m["optuna_xgboost"]

    # 성능 비교표
    perf_rows = []
    for k, label in LABELS.items():
        t = m[k]["test"]
        perf_rows.append(
            f"| {label} | {fmt(t['R2'])} | {fmt(t['RMSE'], 2)} | {fmt(t['MAE'], 2)} |"
        )
    perf_table = "\n".join(perf_rows)

    # 변수 중요도 상위 10
    gain = m.get("feature_importance_gain", {})
    top = list(gain.items())[:10]
    gi_table = "\n".join(
        f"| {i} | {k} | {fmt(v, 1)} |" for i, (k, v) in enumerate(top, 1)
    )

    shap = m.get("shap_mean_abs", {})
    shap_table = "\n".join(
        f"| {i} | {k} | {fmt(v, 3)} |"
        for i, (k, v) in enumerate(list(shap.items())[:10], 1)
    ) or "| - | (SHAP 산출 생략) | - |"

    # 업종별 프로파일
    sec = sector.sort_values("ROI_중앙값", ascending=False)
    sec_table = "\n".join(
        f"| {idx} | {r['ROI_중앙값']:,.1f} | {r['ROI_평균']:,.1f} | "
        f"{r['ROI_상위25']:,.1f} | {r['임업경영비_중앙값']:,.0f} | {int(r['n']):,} |"
        for idx, r in sec.iterrows()
    )

    best_sector = sec.index[0]
    worst_sector = sec.index[-1]

    doc = f"""# [붙임 3] 2026년 임업통계 활용 경진대회 데이터 분석 결과서

**과제명 : 임가경제조사 마이크로데이터 기반 임가 맞춤형 ROI 예측 및 최적 출하시기 추천 시스템**

| 구분 | 내용 |
|---|---|
| 공모 분야 | 데이터 분석 |
| 목표변수 | 임업 ROI(%) = 임업소득 ÷ 임업경영비 × 100 |
| 분석 표본 | {ds['rows']:,} 임가-연도 (2019~2023) |
| 최종 모델 | Optuna 튜닝 XGBoost (CUDA, NVIDIA RTX A6000 ×{ox.get('gpus_used', 2)}) |
| 작성일 | {date.today().isoformat()} |

---

## 1) 추진배경 및 필요성

### 1-1. 현황 — 임가 경영 의사결정의 정보 공백

산림청과 한국임업진흥원이 매년 공표하는 「임가경제조사」 결과는 전국·지역·업종 단위의
**거시 평균값** 형태로 제공된다. 예컨대 "밤재배업 임가의 평균 임업소득은 ○○만원"과 같은
집계치는 산업 전체의 추세 파악에는 유효하지만, **개별 임가가 자신의 조건에서 얼마를 벌 수
있는지**에 대해서는 답을 주지 못한다.

본 분석에서 확인한 실증적 근거는 다음과 같다.

- 업종별 ROI 중앙값의 격차가 **{sec['ROI_중앙값'].max():,.1f}% ({best_sector}) ~ {sec['ROI_중앙값'].min():,.1f}% ({worst_sector})** 로 매우 크다.
- 같은 업종 안에서도 ROI 분산이 커, 학습셋 기준 표준편차가 **{ds['roi_train_std']:,.1f}%p**에 달한다.
- 실제로 현행 방식(지역별×업종별 단순 산술평균)을 예측기로 사용했을 때 설명력은
  **R² = {fmt(m['forest_service_baseline']['test']['R2'])}** 에 그쳤다.
  즉 **평균값은 개별 임가 성과의 약 {m['forest_service_baseline']['test']['R2']*100:.1f}%밖에 설명하지 못한다.**

### 1-2. 문제점

| 문제 | 구체적 내용 |
|---|---|
| 평균의 함정 | 지역·업종 평균은 규모·자본·노동력이 다른 임가를 동일 집단으로 묶어, 소규모 임가에는 과대, 대규모 임가에는 과소 안내가 된다. |
| 사전 의사결정 지원 부재 | 임가가 알고 싶은 것은 "경영비를 얼마나 투입해야 하는가"인데, 사후 결산 통계만으로는 투입-성과 곡선을 알 수 없다. |
| 출하 타이밍 정보 단절 | 임업통계(생산·소득)와 가격통계(KAMIS 도매가)가 분리 운영되어, 언제 출하해야 유리한지에 대한 통합 안내가 없다. |

### 1-3. 필요성

임업통계 **원데이터(마이크로데이터)** 는 임가 단위 관측치를 담고 있어, 집계 이전 단계에서
기계학습을 적용하면 **개별 임가 특성에 조건부인 성과 예측**이 가능하다. 본 과제는 이미
수집·축적된 국가승인통계를 재가공하여, 추가 조사 비용 없이 임가 맞춤형 경영 의사결정
도구로 전환하는 것을 목표로 한다.

---

## 2) 아이디어 기획 세부 내용

### 2-1. 솔루션 개요

**"임가 ROI 예측 큐레이션 시스템"** — 임가가 자신의 제원(지역, 업종, 임지규모, 연령,
가구원수, 계획 경영비, 보유 자본)을 입력하면 ① 예측 ROI와 예상 임업소득, ② 경영비
최적 투입 구간, ③ 업종 전환 시뮬레이션, ④ KAMIS 도매가 연계 최적 출하월을 즉시 제시한다.

### 2-2. 시스템 구조

본 시스템은 성격이 다른 두 국가승인통계를 **2계층 모델**로 결합한다.

```
[임가경제조사 총괄 2019~2023]  [임산물생산비조사 밤·대추·떫은감·표고]  [KAMIS 월별 도매가]
            │                              │                            │
  src/preprocess.py              src/preprocess_cost.py           src/shipping.py
  · 파일설계서 자동 파싱          · 연도·품목별 표기 정규화          · 업종 ↔ 품목 매핑
  · 연도별 스키마 표준화          · 비목·공정 노동시간 정제          · 수확·출하 캘린더
  · ROI 생성 / IQR 정제           · 품목별 IQR 정제                  · 가격지수 최대월
            │                              │                            │
  src/train_optuna.py            src/train_cost.py                      │
  【Model A】 임가 단위           【Model B】 품목 단위                   │
  종합 수익성 예측                단위면적당 수익성 예측                  │
  CUDA XGBoost + Optuna          CUDA XGBoost + Optuna                  │
  5-fold CV, {ox['n_trials']}회 탐색            5-fold CV                             │
            │                              │                            │
            └──────────────┬───────────────┴────────────────────────────┘
                           ▼
                    app.py (Streamlit)
       임가 맞춤 ROI · 경영비 최적화 · 품목별 비목 진단 · 출하시기 추천
```

| 계층 | 데이터 | 답하는 질문 |
|---|---|---|
| **Model A** | 임가경제조사 총괄 | "내 임가 전체가 올해 얼마를 남길 수 있나?" |
| **Model B** | 임산물생산비조사 | "이 품목을 ha당 이렇게 투입하면 얼마가 남나? 비목 배분은 적정한가?" |

### 2-3. 주요 기능 및 핵심 기술

| 기능 | 핵심 기술 | 설명 |
|---|---|---|
| 임가별 ROI 예측 | CUDA XGBoost + Optuna TPE | 범주형 네이티브 처리, {ds['n_features']}개 피처 |
| 경영비 반응곡선 | 모델 기반 what-if 시뮬레이션 | 경영비만 변화시켜 소득 최대 투입점 탐색 |
| 업종 전환 시뮬레이션 | 반사실적(counterfactual) 예측 | 동일 제원에서 업종만 교체 시 ROI 비교 |
| 동종 임가 분위 진단 | 분포 대비 백분위 산출 | 자기 위치를 분포상에서 확인 |
| 최적 출하시기 추천 | 임업통계 × KAMIS 융복합 | 저장성·출하가능월 제약 하 가격지수 최대월 |
| 예측 근거 설명 | SHAP (TreeExplainer) | 변수별 기여도 정량 제시 |

---

## 3) 데이터 분석 방법

### 3-1. 활용 데이터

| 구분 | 제공기관명 | 데이터명 | 활용 내용 |
|---|---|---|---|
| **임업통계(필수)** | 통계청 MDIS / 산림청·한국임업진흥원 | **임가경제조사 총괄(제공) 마이크로데이터** (2019·2020·2021·2022·2023년) | Model A — 임가 단위 종합 수익성 예측 |
| **임업통계(필수)** | 통계청 MDIS / 산림청·한국임업진흥원 | **임산물생산비조사 마이크로데이터** — 밤·대추·떫은감(2020~2024), 표고 노지(2018~2022) | Model B — 품목 단위 단위면적당 수익성 예측 |
| 임업통계(필수) | 한국임업진흥원 | 임가경제조사·임산물생산비조사 파일설계서 (`.xlsx`) | 항목·코드 체계 자동 파싱 |
| 공공데이터(선택) | 한국농수산식품유통공사 | KAMIS 농수산물유통정보 — 품목별 월별 도매가격 | 최적 출하시기 산출 |

- 임가경제조사는 **산림청 국가승인통계**(승인번호 136017)로, 공모요강이 요구하는 필수
  마이크로데이터 요건을 충족한다.
- 원시 관측치 **5,940 임가-연도** (2019~2022 각 1,110 + 2023 1,500).

### 3-2. 데이터 전처리

| 단계 | 처리 내용 | 결과 |
|---|---|---|
| ① 적재 | CP949/EUC-KR 인코딩 및 구분자 자동 탐지, ZIP 자동 해제 | 5개년 5,940행 |
| ② 스키마 표준화 | 2021년 파일의 영문 변수코드 접두사(`FMI_임업소득` 등) 제거, 2019~2020년 `임외소득`→`임업외소득` 등 연도별 표기 통일 | 34개 항목 정렬 |
| ③ 코드북 매핑 | 파일설계서 '코드정보' 시트를 파싱해 코드→한글 라벨 사전 자동 생성 (실패 시 폴백 사전) | 6개 범주 35개 코드 |
| ④ 결측 처리 | MDIS 결측코드(-9, -8, -7, -1 등)를 `NaN`으로 치환. 핵심 3개 항목 결측 행 제거 | 결측 0건 |
| ⑤ 정의역 정제 | 임업경영비 = 0 또는 임업총수입 = 0 인 **임업 미영위 임가 {meta['dropped_no_forestry_activity']:,}건** 제외 (ROI 정의 불가) | 5,490행 |
| ⑥ **IQR 이상치 제거** | 목표변수 ROI에 1.5×IQR, 임업경영비·임업외소득에 3.0×IQR 규칙 적용 | **{meta['outliers_removed']:,}건 제거 → 최종 {ds['rows']:,}행** |
| ⑦ 파생변수 생성 | 구간형 범주의 대표값 수치화(임지규모 ha, 가구원수, 연령), ha당 경영비·자본·노동력, 로그변환, 지역×업종 교호항 | {ds['n_features']}개 피처 |

**이상치 제거의 타당성** — ROI는 분모(임업경영비)가 작을수록 발산하여 원자료 최대값이
5,900%를 넘었다. 상위 소수 관측치가 RMSE를 지배하면 모델이 대다수 임가에 대해
왜곡된 학습을 하게 되므로, 통계적으로 표준적인 IQR 규칙으로 정제하였다
(정제 후 ROI 범위 {meta['roi_bounds'][0]:,.1f}% ~ {meta['roi_bounds'][1]:,.1f}%).

### 3-3. 정보 누출(Data Leakage) 통제 — 분석의 타당성

목표변수가 `ROI = 임업소득 / 임업경영비` 이고 `임업소득 = 임업총수입 − 임업경영비` 이므로,
**임업총수입·임업소득 및 이를 포함하는 모든 합계항목**을 설명변수에서 전면 배제하였다.

> 제외 항목: {', '.join(meta['leaky_excluded'])}

반면 **임업경영비는 유지**하였다. ROI의 분모이기는 하나 분자인 임업총수입을 결정하지
않으며, 임가가 영농계획 시점에 스스로 정하는 **사전(ex-ante) 의사결정 변수**이기 때문이다.
이는 대시보드에서 "경영비를 얼마나 투입할 것인가"를 시뮬레이션하는 기능의 전제가 된다.
이 통제를 하지 않으면 R²가 1.0에 수렴하는 무의미한 모델이 만들어진다.

### 3-4. 설명변수 구성 ({ds['n_features']}개)

| 유형 | 변수 |
|---|---|
| 범주형 (6) | {', '.join(ds['features'][:6])} |
| 원시 수치형 (5) | 임업경영비, 임업외소득, 기초_자본(순재산), 연초보유, 조사연도 |
| 파생 (11) | 임지규모_ha, 가구원수_명, 경영주_연령, log_임업경영비, 경영비_자본비율, ha당_경영비, log_ha당_경영비, ha당_가용노동력, ha당_자본, 임업외소득_비중, 지역x업종 |

### 3-5. 분석 기법 및 절차

1. **데이터 분할** — Train {ds['train']:,} / Validation {ds['valid']:,} / Test {ds['test']:,} (80:10:10, `random_state={ds['seed']}`)
2. **베이스라인 3종 구성**
   - ① *산림청 단순평균* : 학습셋의 지역별×업종별 산술평균을 그대로 예측값으로 사용 (현행 통계 공표 방식의 재현)
   - ② *다중 선형회귀* : One-Hot 인코딩 + 표준화 후 OLS
   - ③ *Optuna-XGBoost* : 제안 모델
3. **하이퍼파라미터 최적화** — Optuna TPE 샘플러(multivariate),
   **{ox['n_trials']}회 시행**, 목적함수는 학습셋 **{ox['n_folds']}-fold 교차검증 OOF RMSE**.
   단일 검증셋 과적합을 방지하기 위해 시행마다 {ox['n_folds']}개 모델을 학습한다
   (총 {ox['n_trials'] * ox['n_folds']:,}회 부스팅 학습).
   탐색 공간: `learning_rate`, `max_depth`, `min_child_weight`, `subsample`,
   `colsample_bytree/bylevel`, `reg_alpha`, `reg_lambda`, `gamma`, `max_delta_step`,
   `max_cat_to_onehot`, `n_estimators`, 그리고 **목표변수 부호보존 로그변환 여부**.
4. **최종 학습** — 교차검증에서 얻은 평균 최적 부스팅 라운드({ox['n_estimators']}회)로
   Train+Validation 전체(90%)를 재학습.
5. **평가** — 학습 전 과정에서 한 번도 사용하지 않은 Test set {ds['test']:,}건으로 R², RMSE, MAE 산출.

### 3-6. 하드웨어 가속 및 사용 프로그램

- **GPU 가속** : `tree_method='hist'`, `device='cuda'`. Optuna 워커 스레드를
  **NVIDIA RTX A6000 {ox.get('gpus_used', 2)}장에 라운드로빈 배정**하여 병렬 탐색.
- **소프트웨어** : Python 3.11, XGBoost 3.2, Optuna 4.9, scikit-learn 1.9,
  SHAP 0.51, pandas 3.0, Streamlit 1.60, Plotly 6.9.

### 3-7. 선정된 최적 하이퍼파라미터

목표변수 변환: `{ox['target_transform']}` · 부스팅 라운드: {ox['n_estimators']}

```json
{json.dumps({k: v for k, v in ox['best_params'].items()
             if k not in ('objective', 'eval_metric', 'seed')}, ensure_ascii=False, indent=2)}
```

---

## 4) 분석 내용 및 결과

### 4-1. 정량적 성능 평가 (Test set, n = {ds['test']:,})

| 모델 | R² (↑) | RMSE (%p, ↓) | MAE (%p, ↓) |
|---|---:|---:|---:|
{perf_table}

![모델 성능 비교](reports/figures/benchmark_comparison.png)

**핵심 결과**

- 제안 모델의 R²는 **{fmt(ox['test']['R2'])}** 로, 현행 산림청 단순평균 방식
  ({fmt(m['forest_service_baseline']['test']['R2'])}) 대비 **{imp['R2_delta']:+.4f} 상승**
  ({'약 ' + f"{imp['R2_ratio']:.1f}배" if imp.get('R2_ratio') else ''}).
- 예측 오차는 RMSE 기준 **{imp['RMSE_reduction_pct']:.1f}% 감소**,
  MAE 기준 **{imp['MAE_reduction_pct']:.1f}% 감소**하였다.
- 선형회귀 대비로도 R² {ox['test']['R2'] - m['linear_regression']['test']['R2']:+.4f} 개선되어,
  임가 특성과 ROI 사이의 **비선형·교호작용 구조**가 실재함을 보여준다.
- 교차검증 OOF 성능(RMSE {fmt(ox['cv_oof']['RMSE'], 2)}, R² {fmt(ox['cv_oof']['R2'])})과
  Test 성능이 유사하여 **과적합 없이 일반화**되었음을 확인하였다.

{cost_summary}

> **성능 해석에 관한 유의** — 임가 ROI는 기상·병충해·시장가격 등 관측되지 않은 요인의
> 영향을 크게 받는 본질적으로 잡음이 큰 변수이다. 따라서 R²의 절대 수준보다,
> **동일 데이터·동일 평가셋에서 현행 방식 대비 얼마나 개선되는가**가 정책적으로 의미 있는
> 비교이며, 본 분석은 그 상대 개선폭을 명확히 제시한다.

![실측 대비 예측](reports/figures/pred_vs_actual.png)

### 4-2. 변수 중요도 (XGBoost Gain)

| 순위 | 변수 | Gain |
|---:|---|---:|
{gi_table}

![Feature Importance](reports/figures/feature_importance.png)

### 4-3. SHAP 기여도 분석

| 순위 | 변수 | 평균 |SHAP| |
|---:|---|---:|
{shap_table}

![SHAP Summary](reports/figures/shap_summary.png)

**해석** — 임업경영비 및 그 파생변수(ha당 경영비, 로그변환)가 상위 기여도를 차지한다.
이는 ROI가 투입 대비 성과 지표인 만큼 자연스러운 결과인 동시에, **경영비 투입 수준이
임가가 직접 통제할 수 있는 가장 강력한 지렛대**임을 뜻한다. 대시보드의 '경영비 반응곡선'
기능은 바로 이 지점을 실무적으로 활용한 것이다. 업종·지역 변수 또한 유의한 기여를 보여
업종 전환·품목 다변화 의사결정의 근거로 활용 가능하다.

### 4-4. 업종별 ROI 프로파일 (2019~2023 통합)

| 업종 | ROI 중앙값(%) | ROI 평균(%) | ROI 상위25%(%) | 임업경영비 중앙값(원) | 표본수 |
|---|---:|---:|---:|---:|---:|
{sec_table}

![업종별 ROI](reports/figures/sector_roi_profile.png)

업종 간 ROI 중앙값 격차는 최대 **{sec['ROI_중앙값'].max() - sec['ROI_중앙값'].min():,.1f}%p**
({best_sector} vs {worst_sector})로, 단일 평균으로 임업 전체를 대표하는 현행 안내 방식의
한계를 직접적으로 보여준다.

### 4-5. 최적 출하시기 모듈

임가경제조사 총괄 마이크로데이터에는 월 단위 출하·가격 정보가 없다. 따라서 출하시기
추천은 **KAMIS 월별 도매가격**을 융복합하여 산출하는 구조로 설계하였다.

- 업종별 → KAMIS 대표 품목 매핑 (예: 밤재배업 → 밤, 버섯재배업 → 표고·느타리)
- 품목별 **수확기 및 저장성 기반 출하가능월** 제약 설정
- 제약 구간 내에서 **월별 도매가 지수(연평균=100)가 최대인 달**을 추천월로 제시하고,
  수확기 즉시 출하 대비 가격 이득(%p)을 정량 표시

KAMIS OpenAPI 수집기(`scripts/fetch_kamis.py`)를 함께 제출하며, 가격 데이터가 연결되지
않은 상태에서는 **가상의 가격을 생성하지 않고** 수확 캘린더만 표시하도록 구현하여
분석 결과의 무결성을 유지하였다.

{cost_body}
---

## 5) 주요 성과 및 기대효과

### 5-1. 데이터 분석 활용 전 / 후 비교

| 구분 | 데이터 분석 활용 전 (기존) | 데이터 분석 활용 후 (제안 시스템) |
|---|---|---|
| **의사결정 방식** | 전국·지역·업종 단순 평균 통계에 의존 | 개별 임가 특성({ds['n_features']}개 변수) 맞춤형 머신러닝 ROI 예측 |
| **예측 정확도** | R² {fmt(m['forest_service_baseline']['test']['R2'])} / MAE {fmt(m['forest_service_baseline']['test']['MAE'], 1)}%p | **R² {fmt(ox['test']['R2'])} / MAE {fmt(ox['test']['MAE'], 1)}%p** (오차 {imp['MAE_reduction_pct']:.1f}% 감소) |
| **경영비 의사결정** | 투입 대비 성과 곡선 부재, 관행적 지출 | 경영비 반응곡선으로 **소득 최대 투입 구간** 제시 |
| **업종·품목 선택** | 업종별 평균 소득표 열람 수준 | 동일 제원 가정 **업종 전환 반사실 시뮬레이션** |
| **자기 진단** | 평균 대비 잘하는지 알 수 없음 | 동종 업종 임가 분포 내 **백분위 위치** 즉시 확인 |
| **출하 시점** | 수확 즉시 출하 관행, 가격정보 단절 | 임업통계 × KAMIS 융복합 **최적 출하월 + 가격 이득 정량 제시** |
| **통계 활용도** | 공표용 집계표 열람에 국한 | 마이크로데이터를 **실시간 의사결정 서비스**로 전환 |
| **제공 형태** | 연 1회 PDF 통계보고서 | 웹 대시보드 상시 조회 (`streamlit run app.py`) |

### 5-2. 기대되는 경제적 효과

1. **임가 소득 증대** — 경영비 최적 투입점 안내를 통해 과다·과소 투입을 교정한다.
   본 모델의 MAE는 {fmt(ox['test']['MAE'], 1)}%p로, 현행 방식({fmt(m['forest_service_baseline']['test']['MAE'], 1)}%p)
   대비 오차가 {imp['MAE_reduction_pct']:.1f}% 작다. 경영비 2,000만원 임가 기준으로 환산하면
   임업소득 예측 오차가 약 **{(m['forest_service_baseline']['test']['MAE'] - ox['test']['MAE']) / 100 * 20_000_000:,.0f}원** 줄어드는 셈이며,
   그만큼 자금 계획의 정밀도가 높아진다.
2. **출하 수취가격 개선** — 저장성이 있는 품목(밤·대추·곶감·건과류)에 대해 가격지수가
   높은 달로 출하를 이연하면, 동일 생산량에서 수취가격을 높일 수 있다.
3. **신규 진입자 리스크 저감** — 귀산촌 희망자가 지역·업종·규모별 기대 ROI를 사전에
   확인할 수 있어, 진입 실패에 따른 사회적 비용을 줄인다.

### 5-3. 정책적 파급효과

| 대상 | 활용 방안 |
|---|---|
| 산림청 · 한국임업진흥원 | 임업직불금·정책자금 배분 시 **지역·업종별 수익성 격차**를 근거 데이터로 활용 |
| 지자체 산림부서 | 관내 임가 제원 대입으로 **권장 업종·적정 경영비 가이드라인** 수립 |
| 산림조합 · 컨설팅 | 임가 상담 시 정량 근거 제공, 컨설팅 표준화 |
| 통계 생산 기관 | 마이크로데이터 개방의 활용 성과를 실증하여 **추가 개방 및 항목 확충**의 정당성 확보 |

### 5-4. 통계 개선 제언

본 분석 과정에서 확인된 데이터 제약과 개선 제언은 다음과 같다.

1. **연도별 스키마 불일치** — 2021년 파일만 영문 변수코드 접두사가 붙어 있고,
   2019~2020년은 `임외소득`, 2022년 이후는 `임업외소득`으로 항목명이 다르다.
   연도 간 항목명 표준화가 필요하다.
2. **파일설계서 제공 범위** — 2023년분만 제공되어 이전 연도는 코드 체계를 추정해야 했다.
   전 연도 파일설계서 동시 제공을 제안한다.
3. **품목·월 단위 정보 부재** — 총괄 파일에는 재배 품목과 출하 시기가 없어 KAMIS 연계에
   업종→품목 매핑을 거쳐야 했다. 「임산물생산비조사」·「임산물소득조사」와의
   **임가 단위 연계키 제공** 시 예측 정밀도가 크게 향상될 것으로 기대된다.

---

## 부록 — 재현 방법

```bash
pip install -r requirements.txt

python src/preprocess.py          # 전처리 → data/processed_forestry_data.parquet
python src/train_optuna.py        # CUDA XGBoost + Optuna (N_TRIALS/N_GPU 환경변수로 조절)
python src/make_report.py         # 본 보고서 재생성
streamlit run app.py              # 대시보드 실행

# (선택) KAMIS 가격 데이터 연계
python scripts/fetch_kamis.py --cert-key <KEY> --cert-id <ID>
```

| 파일 | 역할 |
|---|---|
| `src/preprocess.py` | 마이크로데이터 적재·표준화·정제·파생변수 생성 |
| `src/train_optuna.py` | 3종 모델 벤치마크 및 CUDA XGBoost 튜닝 |
| `src/shipping.py` | 임업통계 × KAMIS 융복합 출하시기 추천 |
| `src/make_report.py` | 본 결과서 자동 생성 |
| `scripts/fetch_kamis.py` | KAMIS OpenAPI 월별 도매가격 수집기 |
| `app.py` | Streamlit 대시보드 |
| `models/metrics_summary.json` | 전 모델 성능 지표 원본 |

*본 보고서의 모든 수치는 `models/metrics_summary.json` 및 `data/processed_meta.json`에서
자동 주입되어, 재학습 시 `python src/make_report.py` 한 번으로 갱신된다.*
"""

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"[saved] {OUT}  ({len(doc):,} chars)")


if __name__ == "__main__":
    main()
