"""
Hugging Face Spaces 배포 — 서빙에 필요한 것만 골라 올립니다.

저장소 전체를 올리면 원자료 40MB와 학습 코드까지 따라갑니다. 서빙에 쓰이지 않는
것들이라 빌드만 느려집니다. 그래서 필요한 파일만 임시 폴더에 모아 올립니다.

모델은 UBJSON으로 바꿔 담습니다. 내용은 같고 용량이 30% 작아, 12MB짜리 파일이
8MB가 되어 LFS를 쓸 필요가 없어집니다.

준비:
    pip install huggingface_hub
    export HF_TOKEN=hf_xxx          # Settings → Access Tokens → Write

실행:
    python src/deploy_hf.py                      # 처음 배포
    python src/deploy_hf.py --space 사용자/이름   # Space 지정
    python src/deploy_hf.py --message "차트 수정"  # 이후 갱신

프런트엔드를 고쳤다면 먼저 빌드해야 합니다.
    cd web && npx vite build
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SPACE = "forestry-roi-predictor"

# 서빙에 실제로 쓰이는 것만. 원자료·학습 스크립트·도표 원본은 뺍니다.
COPY_DIRS = ["api", "web/dist", "data/codebook"]
COPY_FILES = [
    "Dockerfile", "requirements-deploy.txt",
    "data/processed_forestry_data.parquet",
    "data/processed_cost_data.parquet",
    "src/__init__.py",
]
# 모델은 UBJSON으로 변환해 담을 것 / 그대로 담을 것
MODELS_BIN = ["best_xgboost_roi", "best_xgboost_cost", "best_xgboost_panel",
              "quantile_roi", "quantile_cost"]
MODELS_JSON = [
    "feature_schema.json", "feature_schema_cost.json", "feature_schema_panel.json",
    "metrics_summary.json", "metrics_cost.json", "metrics_quantile.json",
    "metrics_panel.json", "audit_split.json",
    "insights.json", "production_insights.json", "management_insights.json",
    "subsidy_programs.json", "sector_profile.json", "item_cost_profile.json",
    "region_stats.json", "weather_region.json", "portfolio.json",
]

CARD = """---
title: 우리 산 수익 계산기
emoji: 🌲
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: 임업통계 마이크로데이터로 임가별 수익률을 예측하고 처방합니다
---

# 우리 산 수익 계산기

**2026년 임업통계 활용 경진대회 · 데이터 분석 부문 — 팀 임과 함께**

산림청 국가승인통계 마이크로데이터로 학습한 임가별 수익률 예측 모델과,
그 예측을 임가가 쓸 수 있는 행동으로 바꾸는 분석 계층을 담은 웹 서비스입니다.

## 무엇이 다른가

현행 통계 환류는 집단 평균입니다. 그런데 임가경제조사 4,438개 표본의 ROI는
평균 155.5%에 표준편차 216.7%p로, **표준편차가 평균보다 큽니다.**
지역별×업종별 평균을 그대로 예측값으로 쓰면 설명력(R²)이 0.0428에 그칩니다.

이 서비스는 임가의 조건을 받아 그 임가의 값을 계산합니다.

| 모델 | Test R² | 비고 |
|---|---|---|
| 산림청 방식 (집단 평균) | 0.0428 | 지역×업종 71개 집단 평균 |
| 선형회귀 | 0.1295 | 동일 피처 |
| Optuna XGBoost | **0.1736** | 베이스라인 대비 4.05배 |
| 품목별 정밀 진단 (Model B) | **0.6243** | 베이스라인 대비 5.95배 |
| 패널 구조 활용 | **0.2798** | 작년 실적 반영 시, 10.2배 |

## 주요 기능

- **예측** — 점추정이 아니라 P10~P90 구간으로. 실측 포함률 78.2% / 76.5% (명목 80%)
- **설명** — TreeSHAP로 "왜 이 숫자인지" 변수별 기여 분해
- **처방** — 반사실 탐색으로 "무엇을 얼마나 바꾸면 어떻게 되는지"
- **비교** — 조건이 비슷한 실제 임가들의 분포
- **전략** — 출하 시기(KAMIS 시세), 작목 조합 위험분산, 보조사업 지렛대

## 이 분석에서 지킨 것

**성능보다 정직을 택했습니다.** Model B는 1차 학습에서 R² 0.9102가 나왔습니다.
검증해 보니 총생산액·부가가치·등급별 수량이 피처에 남아 있었습니다. 타깃을 그대로
담은 변수들입니다. 제거하고 재학습하니 최고 상관이 0.885에서 0.344로 내려가고
R²는 0.6243이 되었습니다. **그 0.62가 실제로 쓸 수 있는 숫자입니다.**

기상 결합이 예측력을 거의 못 올린 것, Model A의 설명력이 낮은 것, 표고류 표본이
적어 R²가 음수인 것도 모두 화면과 보고서에 그대로 적었습니다.

## 활용 데이터

**임업통계 (필수)** — 임가경제조사 2019~2023 · 임산물생산비조사 2018~2024 ·
임산물생산조사 2022~2024 · 임업경영실태조사 2018·2020 (통계청 MDIS)

**공공데이터** — KAMIS 도매가격(aT) · 기상청 ASOS · 산림사업 보조금 목록(산림청) ·
행정구역 경계(국토교통부)

## 기술

FastAPI · Vue 3 · Apache ECharts · XGBoost(CUDA 학습 / CPU 서빙) · Optuna

분석 코드 전체: https://github.com/BioCode67/forestry-roi-predictor
"""


def src_deps() -> list[str]:
    """api가 실제로 부르는 src 모듈을 따라갑니다.

    목록을 손으로 관리하면 새 모듈을 추가할 때마다 빠뜨립니다. 그러면 배포는
    성공하는데 컨테이너가 ModuleNotFoundError로 죽습니다.
    """
    import ast

    src = os.path.join(ROOT, "src")
    local = {f[:-3] for f in os.listdir(src) if f.endswith(".py")}

    def imports(path):
        tree = ast.parse(open(path, encoding="utf-8").read())
        out = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                out |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                out.add(n.module.split(".")[0])
        return out & local

    need, seen = set(), set()
    stack = [os.path.join(ROOT, "api", f)
             for f in os.listdir(os.path.join(ROOT, "api")) if f.endswith(".py")]
    while stack:
        p = stack.pop()
        if p in seen or not os.path.exists(p):
            continue
        seen.add(p)
        for m in imports(p):
            if m not in need:
                need.add(m)
                stack.append(os.path.join(src, m + ".py"))
    return sorted(need)


def stage(dst: str) -> None:
    import xgboost as xgb

    for d in COPY_DIRS:
        src = os.path.join(ROOT, d)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst, d),
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in COPY_FILES:
        src = os.path.join(ROOT, f)
        if os.path.exists(src):
            os.makedirs(os.path.dirname(os.path.join(dst, f)), exist_ok=True)
            shutil.copy2(src, os.path.join(dst, f))

    deps = src_deps()
    print(f"  src 모듈 {len(deps)}개 — {', '.join(deps)}")
    for m in deps:
        src = os.path.join(ROOT, "src", m + ".py")
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dst, "src", m + ".py"))

    md = os.path.join(dst, "models")
    os.makedirs(md, exist_ok=True)
    for name in MODELS_BIN:
        src = os.path.join(ROOT, "models", f"{name}.json")
        if not os.path.exists(src):
            continue
        b = xgb.Booster()
        b.load_model(src)
        b.save_model(os.path.join(md, f"{name}.ubj"))
    for f in MODELS_JSON:
        src = os.path.join(ROOT, "models", f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(md, f))

    with open(os.path.join(dst, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(CARD)

    total = sum(os.path.getsize(os.path.join(r, f))
                for r, _, fs in os.walk(dst) for f in fs)
    big = [(os.path.relpath(os.path.join(r, f), dst),
            os.path.getsize(os.path.join(r, f)) / 1e6)
           for r, _, fs in os.walk(dst) for f in fs
           if os.path.getsize(os.path.join(r, f)) > 10e6]
    print(f"  올릴 용량 {total/1e6:.1f}MB")
    if big:
        print("  [주의] 10MB 초과 — LFS가 필요합니다:")
        for p, s in big:
            print(f"    {p} {s:.1f}MB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", default=None, help="사용자명/Space이름")
    ap.add_argument("--message", default="갱신")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="올리지 않고 구성만 확인")
    a = ap.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token and not a.dry_run:
        sys.exit("HF_TOKEN 환경변수가 없습니다. "
                 "huggingface.co → Settings → Access Tokens에서 Write 토큰을 만드세요.")

    dist = os.path.join(ROOT, "web", "dist", "index.html")
    if not os.path.exists(dist):
        sys.exit("web/dist가 없습니다. 먼저 `cd web && npx vite build`를 실행하세요.")

    tmp = tempfile.mkdtemp(prefix="hfdeploy-")
    try:
        print(f"[1/3] 배포본 구성 → {tmp}")
        stage(tmp)
        if a.dry_run:
            print("\n[dry-run] 여기까지입니다.")
            for r, _, fs in os.walk(tmp):
                rel = os.path.relpath(r, tmp)
                if rel.count(os.sep) < 2:
                    print(f"  {rel}/  ({len(fs)}개)")
            return

        from huggingface_hub import HfApi
        api = HfApi(token=token)
        space = a.space or f"{api.whoami()['name']}/{DEFAULT_SPACE}"

        print(f"[2/3] Space 확인 — {space}")
        api.create_repo(repo_id=space, repo_type="space", space_sdk="docker",
                        private=a.private, exist_ok=True)

        print("[3/3] 업로드")
        api.upload_folder(folder_path=tmp, repo_id=space, repo_type="space",
                          commit_message=a.message)
        url = f"https://huggingface.co/spaces/{space}"
        print(f"\n완료 — {url}")
        print(f"직접 주소: https://{space.replace('/', '-').lower()}.hf.space")
        print("\n첫 빌드는 3~6분 걸립니다. 위 주소의 Logs 탭에서 진행 상황을 볼 수 있습니다.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
