# Hugging Face Spaces (Docker SDK) 배포용
#
# 학습은 A6000 두 장으로 하지만 서빙은 CPU로 충분합니다. 나무 445그루를 한 행에
# 대해 평가하는 일이라 수 밀리초면 끝납니다. 그래서 xgboost도 CPU 판본을 씁니다.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# xgboost가 libgomp를 필요로 합니다. slim 이미지에는 없습니다.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app

COPY --chown=user requirements-deploy.txt ./
RUN pip install --user -r requirements-deploy.txt

# 무거운 것부터 넣어야 코드만 고쳤을 때 계층이 다시 안 쌓입니다.
COPY --chown=user models/    ./models/
# 원자료 전체(40MB)는 넣지 않습니다. 서빙에 필요한 것은 전처리 산출물과
# 코드북용 파일설계서뿐입니다.
COPY --chown=user data/processed_forestry_data.parquet data/processed_cost_data.parquet ./data/
COPY --chown=user data/codebook/ ./data/codebook/
COPY --chown=user web/dist/  ./web/dist/
COPY --chown=user src/       ./src/
COPY --chown=user api/       ./api/

EXPOSE 7860
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
