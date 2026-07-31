# 임가 맞춤형 ROI 예측 & 최적 출하시기 추천 시스템

**2026년 임업통계 활용 경진대회 — 데이터 분석 부문 출품작**

산림청 국가승인통계 「임가경제조사」 총괄 마이크로데이터(2019~2023, 통계청 MDIS)를
기계학습으로 재가공하여, 전국·업종 평균에 머물던 임업 통계를 **개별 임가 단위의
수익성 예측·경영 진단 도구**로 전환한다.

---

## 결과 요약

| 모델 | R² | RMSE (%p) | MAE (%p) |
|---|---:|---:|---:|
| 산림청 단순평균 (현행) | *`models/metrics_summary.json` 참조* | | |
| 다중 선형회귀 | | | |
| **Optuna-XGBoost (제안)** | | | |

정확한 수치는 학습 후 자동 생성되는 [`data_analysis_report.md`](data_analysis_report.md) 4-1절 참조.

---

## 실행

```bash
pip install -r requirements.txt

python src/preprocess.py      # 전처리 → data/processed_forestry_data.parquet
python src/train_optuna.py    # CUDA XGBoost + Optuna 튜닝, 3종 모델 벤치마크
python src/make_report.py     # 공모전 [붙임3] 양식 보고서 생성
streamlit run app.py          # 대시보드 (기본 http://localhost:8501)
```

환경변수로 탐색 규모를 조절한다.

```bash
N_TRIALS=300 N_GPU=2 N_JOBS=6 python src/train_optuna.py
```

### (선택) KAMIS 가격 데이터 연계

출하시기 추천을 가격 기반으로 활성화하려면 KAMIS OpenAPI 키가 필요하다.

```bash
python scripts/fetch_kamis.py --cert-key <KEY> --cert-id <ID> --start 2019 --end 2023
```

`data/kamis/kamis_monthly.csv` 가 생성되면 대시보드가 자동 인식한다.
키가 없으면 수확 캘린더만 표시되며, **가상의 가격을 생성하지 않는다.**

---

## 구조

```
forestry-roi-predictor/
├── app.py                     Streamlit 대시보드
├── data_analysis_report.md    공모전 [붙임3] 결과보고서 (자동 생성)
├── src/
│   ├── preprocess.py          적재·스키마 표준화·정제·파생변수
│   ├── train_optuna.py        3종 벤치마크 + CUDA XGBoost 튜닝
│   ├── shipping.py            임업통계 × KAMIS 융복합 출하시기
│   └── make_report.py         보고서 자동 생성
├── scripts/fetch_kamis.py     KAMIS OpenAPI 수집기
├── models/                    학습 산출물 (모델·지표·스키마)
├── reports/figures/           벤치마크·중요도·SHAP 그림
└── data/
    ├── 총괄_.../              MDIS 원자료 (2019~2023 CSV + 파일설계서)
    └── kamis/                 KAMIS 월별 도매가격 (선택)
```

---

## 방법론 요지

- **목표변수** : 임업 ROI(%) = 임업소득 ÷ 임업경영비 × 100
- **정보 누출 통제** : `임업총수입`, `임업소득` 및 이를 포함하는 합계항목
  (`임가소득`, `경상소득`, `임가순소득`, `임가처분가능소득`, `임가경제잉여`) 전면 제외.
  `임업경영비`는 분모이나 분자를 결정하지 않는 **사전 의사결정 변수**이므로 유지.
- **정제** : 임업 미영위 임가 제외 후 ROI 1.5×IQR, 경영비·임업외소득 3.0×IQR 규칙 적용.
- **탐색** : Optuna TPE, 목적함수는 학습셋 5-fold 교차검증 OOF RMSE.
  워커 스레드를 GPU에 라운드로빈 배정해 RTX A6000 2장 병렬 활용.
- **평가** : 학습에 한 번도 쓰이지 않은 Test 10%로 R²·RMSE·MAE 산출.

---

## 데이터 출처

| 구분 | 제공기관 | 데이터명 |
|---|---|---|
| 임업통계(필수) | 통계청 MDIS / 산림청·한국임업진흥원 | 임가경제조사 총괄(제공) 마이크로데이터 2019~2023 |
| 임업통계(필수) | 한국임업진흥원 | 2023년 임가경제조사 총괄 파일설계서 |
| 공공데이터(선택) | 한국농수산식품유통공사 | KAMIS 품목별 월별 도매가격 |
