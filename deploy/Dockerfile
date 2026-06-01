# 파일 위치: deploy/Dockerfile
# FormForge 메인앱 (Streamlit "Fight Card" UI) — Cloud Run `formforge-app` 서비스 (Day 14 Task 14.3).
#
# 단일 컨테이너 전략: mcp/ 코드를 함께 담아 Mediator 가 컨테이너 안에서 MCP 를
# stdio subprocess 로 실행(P4). 별도 MCP 서비스 불필요 — 코드 무변경.
#
# ⚠️ 빌드 컨텍스트는 **프로젝트 루트** (deploy/ 가 아님). 앱이 agents/·storage/·
#    evals/·ui/·mcp/ 를 모두 import 하므로 함께 COPY 한다.
#
# 빌드/배포 (프로젝트 루트에서, Docker 로컬 불필요 — Cloud Build 가 빌드):
#   gcloud builds submit --config deploy/cloudbuild.yaml .

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    GOOGLE_GENAI_USE_VERTEXAI=True \
    APP_ENV=production

WORKDIR /app

# 1) 시스템 의존성 — opencv/mediapipe 런타임(libGL·libGLESv2·libEGL), 모델 다운로드용 curl
#    mediapipe Tasks(vision) 가 OpenGL ES(libGLESv2.so.2)+EGL(libEGL.so.1) 를 dlopen 하므로
#    libgl1 만으론 부족 → libgles2·libegl1 추가 (없으면 Live 분석에서 OSError: libGLESv2.so.2).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libgles2 libegl1 curl \
    && rm -rf /var/lib/apt/lists/*

# 2) 파이썬 의존성 먼저 (레이어 캐시 — 코드만 바뀌면 재설치 안 함)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 3) 소스 — 앱이 실제로 import 하는 패키지만
COPY agents/ ./agents/
COPY storage/ ./storage/
COPY evals/ ./evals/
COPY ui/ ./ui/
COPY mcp/ ./mcp/
COPY tests/sample_pose_data.json ./tests/sample_pose_data.json

# 4) MediaPipe Pose 모델 (.gitignore — 빌드 시 다운로드). PoseExtractor Stage1 이 사용.
RUN mkdir -p data/models && \
    curl -sSL -o data/models/pose_landmarker_full.task \
      https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task

# Cloud Run 은 PORT(기본 8080) 를 주입 → streamlit 이 그 포트로 listen.
EXPOSE 8080

# shell form: ${PORT} 확장. 격리 iframe(data: URI) 데모라 CORS/XSRF 완화.
CMD streamlit run ui/streamlit_app.py \
      --server.port=${PORT:-8080} --server.address=0.0.0.0 \
      --server.headless=true --server.enableCORS=false \
      --server.enableXsrfProtection=false --browser.gatherUsageStats=false
