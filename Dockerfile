# ===== Vit_S Python AI 워커 이미지 (FastAPI health + Redis Stream 워커) =====
# 한 이미지로 health(uvicorn)·워커 여러 개를 굴린다. 프로세스 구분은 compose 의 command 로 한다.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Seoul

# tzdata: KST 로그 정합 / curl: 컨테이너 헬스체크용
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata curl \
    && rm -rf /var/lib/apt/lists/*

# 의존성 먼저 복사 → 레이어 캐시(소스만 바뀌면 재설치 안 함)
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app

# 비루트 실행
RUN useradd -r -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
# 기본 프로세스 = health API. 워커는 compose 에서 command 로 덮어쓴다.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
