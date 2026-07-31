"""
소스코드 별첨 꾸리기 — docs/임과함께_분석코드_별첨.zip

요강 붙임3 유의사항: "프로그래밍 등 이용 분석 사례의 경우, 코드 소스 등
분석 결과물 필수 첨부(분량 외 별첨)"

두 가지를 지킵니다.

  ① 원자료는 넣지 않습니다.
     임가경제조사·임산물생산비조사 등은 통계청 MDIS에서 이용 목적을 밝히고
     받는 자료입니다. 이용 약관상 제3자에게 다시 배포할 수 없습니다. 심사위원도
     같은 경로로 받으실 수 있으므로 받는 방법만 적어 둡니다. 규정을 어기면서
     편의를 챙길 이유가 없습니다.

  ② 학습된 부스터 파일도 넣지 않습니다.
     다섯 개를 합치면 43MB라 접수 시스템에 올리기 부담스럽습니다. 대신 성능
     지표와 하이퍼파라미터, 분석 산출물 JSON을 모두 넣어 결과를 대조할 수
     있게 하고, 원본은 공개 저장소를 안내합니다.

실행: python src/make_code_package.py
"""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "임과함께_분석코드_별첨.zip")
REPO = "https://github.com/BioCode67/forestry-roi-predictor"
SITE = "https://forestry-roi-predictor.onrender.com"

DIRS = [
    ("src", "src", (".py",)),
    ("api", "api", (".py",)),
    ("web/src", "web/src", None),
    ("web/public", "web/public", (".md",)),          # 사진 출처 표기만
    ("docs/figures", "결과물/도표", (".png",)),
]
FILES = [
    "requirements.txt", "requirements-deploy.txt",
    "Dockerfile", "render.yaml", ".dockerignore",
    "web/package.json", "web/vite.config.js", "web/index.html",
    ".github/workflows/keepalive.yml",
]
# 결과 대조용 JSON — 용량이 작고 심사에서 바로 확인할 수 있는 것들
RESULT_JSON = [
    "metrics_summary.json", "metrics_cost.json", "metrics_quantile.json",
    "metrics_panel.json", "audit_split.json",
    "feature_schema.json", "feature_schema_cost.json", "feature_schema_panel.json",
    "insights.json", "production_insights.json", "management_insights.json",
    "subsidy_programs.json", "sector_profile.json", "item_cost_profile.json",
    "region_stats.json", "weather_region.json", "portfolio.json",
]

README = f"""# 임업통계 마이크로데이터 기반 임가 맞춤형 수익성 예측 시스템 — 분석 코드

2026년 임업통계 활용 경진대회 · 데이터 분석 부문 · 팀 **임과 함께**

요강 붙임3의 "코드 소스 등 분석 결과물 필수 첨부(분량 외 별첨)"에 따른 제출물입니다.

- 웹 서비스 : {SITE}
- 코드 저장소 : {REPO}

---

## 1. 먼저 알려드릴 두 가지

**원자료는 이 압축에 들어 있지 않습니다.** 임가경제조사·임산물생산비조사 등은
통계청 MDIS에서 이용 목적을 밝히고 받는 자료이고, 약관상 제3자에게 다시 배포할 수
없습니다. 받으시는 방법은 아래 3절에 적었습니다.

**학습된 모델 파일(43MB)도 뺐습니다.** 대신 성능 지표·하이퍼파라미터·분석 산출물을
`결과물/` 에 모두 넣어 결과를 대조하실 수 있게 했고, 모델 원본은 위 저장소에 있습니다.

---

## 2. 폴더 구성

```
src/                     분석 스크립트
  preprocess.py            임가경제조사 전처리 (Model A)
  preprocess_cost.py       임산물생산비조사 전처리 (Model B) — 누수 차단 규칙
  train_optuna.py          Model A 학습 · 3종 벤치마크
  train_cost.py            Model B 학습 · 3종 벤치마크
  train_quantile.py        분위수 회귀 (P10/P50/P90)
  train_panel.py           패널 구조 활용 모델
  audit_split.py           분할 감사 — 행 단위 분할이 성능을 부풀렸는가
  explain.py               TreeSHAP 설명 · 반사실 처방 · 유사 임가 탐색
  portfolio.py             작목 조합 위험 분산 (평균-분산)
  insights.py              등급 전환 · 수령별 수익성 · 선도임가 비교
  production.py            지역 단가 · 특화도(LQ) · 가공 손익분기
  management.py            임업경영실태조사 — 출하 시기·판로
  subsidy.py               보조사업 자부담률 기반 실효 ROI
  region_map.py            시군구 단위 단가 지도
  weather.py, weather_sgg.py, kma_client.py   기상청 결합
  kamis_client.py, shipping.py                KAMIS 시세 · 출하 시기
  make_figures.py          제출본 도표 생성
  make_docx.py             제출본 문서 생성
  make_report.py           분석 보고서 생성

api/                     FastAPI 서빙
web/src/                 Vue 3 프런트엔드
결과물/
  지표/                    성능 지표 · 하이퍼파라미터 · 분석 산출물 (JSON)
  도표/                    제출본 도표 원본 (PNG, 200dpi)
```

---

## 3. 재현 방법

### 3-1. 원자료 내려받기

통계청 마이크로데이터 통합서비스(MDIS) <https://mdis.kostat.go.kr> 에서 아래를
내려받아 `data/` 아래에 둡니다. 파일설계서(xlsx)도 함께 받아야 코드북이 풀립니다.

| 통계 | 연도 | 비고 |
|---|---|---|
| 임가경제조사 (총괄) | 2019~2023 | Model A |
| 임산물생산비조사 | 2018~2024 | 밤·대추·떫은감·표고(노지/톱밥) |
| 임산물생산조사 | 2022~2024 | 전품목 |
| 임업경영실태조사 | 2018·2020 | |

공공데이터는 아래에서 받습니다.

| 데이터 | 제공 | 비고 |
|---|---|---|
| KAMIS 도매가격 | 한국농수산식품유통공사 | API 키 필요 |
| 종관기상관측(ASOS) | 기상청 API 허브 | API 키 필요 |

API 키는 코드에 넣지 않았습니다. 환경변수 `KAMIS_KEY`, `KAMIS_ID`, `KMA_KEY` 로 넘깁니다.

### 3-2. 실행 순서

```bash
pip install -r requirements.txt

python src/preprocess.py          # 임가경제조사 전처리
python src/preprocess_cost.py     # 임산물생산비조사 전처리
python src/train_optuna.py        # Model A 학습 + 벤치마크
python src/train_cost.py          # Model B 학습 + 벤치마크
python src/train_quantile.py      # 예측구간
python src/train_panel.py         # 패널 모델
python src/audit_split.py         # 분할 감사
python src/insights.py && python src/production.py && python src/management.py
python src/subsidy.py && python src/region_map.py && python src/portfolio.py
python src/make_figures.py        # 도표

uvicorn api.main:app --reload     # 웹 서비스 (web/dist 빌드 후)
```

seed는 42로 고정했습니다. 학습은 NVIDIA A6000 두 장에서 CUDA로 돌렸고
(`tree_method='hist'`, `device='cuda'`), 서빙은 CPU로 충분합니다.

---

## 4. 주요 결과

| 모델 | Test R² | 베이스라인 대비 |
|---|---|---|
| 산림청 방식 (지역×업종 평균) | 0.0428 | — |
| 선형회귀 | 0.1295 | 3.02배 |
| **Model A** (임가경제조사, Optuna XGBoost) | **0.1736** | **4.05배** |
| **Model B** (임산물생산비조사) | **0.6243** | **5.95배** |
| **패널 구조 활용** (직전 연도 실적 결합) | **0.2798** | **10.2배** |

예측구간(P10~P90) 실측 포함률 : Model A 78.2%, Model B 76.5% (명목 80%)

### 이 분석에서 지킨 것

**성능보다 정직을 택했습니다.** Model B는 1차 학습에서 R² 0.9102가 나왔습니다.
검증해 보니 총생산액·부가가치·등급별 수량이 피처에 남아 있었습니다. 타깃을 그대로
담은 변수들입니다. 제거하고 재학습하니 최고 상관이 0.885에서 0.344로 내려가고
R²는 0.6243이 되었습니다. 그 0.62가 실제로 쓸 수 있는 숫자입니다.
(`src/preprocess_cost.py` 의 `LEAKY_PATTERNS`)

패널 자료를 행 단위로 무작위 분할한 것이 성능을 부풀렸는지도 따로 확인했습니다.
시험셋의 66.9%가 학습셋과 임가를 공유하고 있었으나, 임가 단위로 다시 나눠 재보니
R² 0.1755 → 0.1574로 fold 간 표준편차(0.0321) 안이었습니다. (`src/audit_split.py`)

기상 결합이 예측력을 거의 못 올린 것, Model A의 설명력이 낮은 것, 표고류 표본이
적어 품목별 R²가 음수인 것도 모두 보고서에 그대로 적었습니다.

---

## 5. 개발 환경

Python 3.11 · XGBoost 3.2.0 (CUDA) · Optuna · scikit-learn · pandas · NumPy · SciPy
FastAPI · Pydantic · Vue 3 · Vite · Apache ECharts
"""

DATA_NOTE = """# 원자료에 대하여

이 압축에는 마이크로데이터 원자료가 들어 있지 않습니다.

임가경제조사, 임산물생산비조사, 임산물생산조사, 임업경영실태조사는 통계청
마이크로데이터 통합서비스(MDIS)에서 이용 목적을 밝히고 받는 자료입니다.
이용 약관상 제3자에게 다시 배포할 수 없습니다.

심사위원께서도 같은 경로로 받으실 수 있습니다.

    https://mdis.kostat.go.kr

받으신 파일을 `data/` 아래에 두고 README의 실행 순서를 따르시면 같은 결과가
나옵니다. 전처리 코드가 인코딩(CP949/UTF-8)과 구분자를 자동으로 판별하고,
연도마다 다른 컬럼명과 코드 체계도 정규화합니다.

전처리 산출물(`data/processed_*.parquet`)은 원자료를 가공한 것이라 역시 넣지
않았습니다. 위 실행 순서의 첫 두 단계로 다시 만들어집니다.
"""


def copy_tree(src: str, dst: str, exts=None) -> int:
    n = 0
    for r, ds, fs in os.walk(src):
        ds[:] = [d for d in ds if d not in ("__pycache__", "node_modules", ".git")]
        for f in fs:
            if exts and not f.endswith(exts):
                continue
            if f.endswith((".pyc", ".DS_Store")):
                continue
            rel = os.path.relpath(os.path.join(r, f), src)
            out = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copy2(os.path.join(r, f), out)
            n += 1
    return n


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="codepkg-")
    base = os.path.join(tmp, "임과함께_분석코드")
    try:
        total = 0
        for src, dst, exts in DIRS:
            s = os.path.join(ROOT, src)
            if os.path.isdir(s):
                n = copy_tree(s, os.path.join(base, dst), exts)
                total += n
                print(f"  {dst:20s} {n:3d}개")

        for f in FILES:
            s = os.path.join(ROOT, f)
            if os.path.exists(s):
                d = os.path.join(base, f)
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(s, d)
                total += 1

        jd = os.path.join(base, "결과물", "지표")
        os.makedirs(jd, exist_ok=True)
        n = 0
        for f in RESULT_JSON:
            s = os.path.join(ROOT, "models", f)
            if os.path.exists(s):
                shutil.copy2(s, os.path.join(jd, f))
                n += 1
        print(f"  {'결과물/지표':20s} {n:3d}개")
        total += n

        for name, text in (("README.md", README), ("원자료_안내.md", DATA_NOTE)):
            with open(os.path.join(base, name), "w", encoding="utf-8") as fh:
                fh.write(text)

        with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
            for r, _, fs in os.walk(base):
                for f in sorted(fs):
                    p = os.path.join(r, f)
                    z.write(p, os.path.relpath(p, tmp))

        print(f"\n[saved] {OUT}")
        print(f"  파일 {total + 2}개 · {os.path.getsize(OUT)/1e6:.1f} MB")
        print("  원자료와 학습된 부스터는 넣지 않았습니다 (약관·용량)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
