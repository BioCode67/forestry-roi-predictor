# 배포용 이미지 — Render / Fly / Cloud Run 어디서든 같은 방식으로 뜹니다.
#
# 프런트엔드까지 여기서 빌드합니다. 빌드 결과물을 저장소에 넣어 두면 코드와
# 산출물이 조금씩 어긋나기 시작합니다. git push 한 번으로 전부 다시 만들어지는
# 편이 낫습니다.

# ── 1단계: 프런트엔드 ──────────────────────────────────────────────────────
FROM node:20-slim AS web
WORKDIR /build
COPY web/package.json web/package-lock.json* ./
RUN npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build


# ── 2단계: 서빙 ───────────────────────────────────────────────────────────
# 학습은 A6000 두 장으로 하지만 서빙은 CPU로 충분합니다. 나무 445그루를 한 행에
# 대해 평가하는 일이라 수 밀리초면 끝납니다.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# xgboost가 libgomp를 필요로 합니다. slim 이미지에는 없습니다.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-deploy.txt ./
RUN pip install -r requirements-deploy.txt

# 무거운 것부터 넣어야 코드만 고쳤을 때 계층이 다시 안 쌓입니다.
COPY models/ ./models/
# 원자료 전체(40MB)는 넣지 않습니다. 서빙에 필요한 것은 전처리 산출물과
# 코드북용 파일설계서뿐입니다.
COPY data/processed_forestry_data.parquet data/processed_cost_data.parquet ./data/
COPY data/codebook/ ./data/codebook/
# shipping.py가 읽는 KAMIS 월별 도매가(0.5MB). 빼면 출하시기 안내가
# 수확 캘린더 기준으로만 나옵니다.
COPY data/kamis/ ./data/kamis/
COPY src/ ./src/
COPY api/ ./api/
COPY --from=web /build/dist ./web/dist

# 무료 등급은 메모리가 512MB입니다. 부스터는 실제로 쓸 때 올라가지만
# (api/services.py의 _Registry 참고) 동시 요청이 몰리면 한도에 닿을 수 있어
# 작업자는 하나만 두고 동시 처리 수를 제한합니다.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --limit-concurrency 24"]
