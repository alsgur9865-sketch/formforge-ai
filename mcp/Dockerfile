# 파일 위치: mcp/Dockerfile
# FormForge Phoenix MCP server — Cloud Run `formforge-mcp` 서비스 (Task 12.3).
#
# ⚠️ 빌드 컨텍스트는 **프로젝트 루트** (mcp/ 가 아님).
#    phoenix_mcp_server.py 가 `from storage import firestore_client` 로 루트의
#    storage/ 를 import 하므로, mcp/ 와 storage/ 를 함께 COPY 해야 한다.
#    → TASKS 의 `cd mcp && gcloud run deploy --source .` 대신 루트에서 빌드한다.
#
# 빌드/배포 (프로젝트 루트에서 실행):
#   # Cloud Run (Day 14, Docker 로컬 불필요 — Cloud Build 가 빌드):
#   gcloud builds submit --config mcp/cloudbuild.yaml .
#
#   # 로컬 검증 (Docker 설치 시):
#   docker build -f mcp/Dockerfile -t formforge-mcp .
#   docker run -p 8080:8080 --env-file .env formforge-mcp

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    PHOENIX_MCP_TRANSPORT=http

WORKDIR /app

# 1) 의존성 먼저 설치 (레이어 캐시 — 코드만 바뀌면 재설치 안 함)
COPY mcp/requirements-mcp.txt ./mcp/requirements-mcp.txt
RUN pip install --no-cache-dir -r mcp/requirements-mcp.txt

# 2) 소스 — MCP server 가 실제로 import 하는 것만 (mcp/ + storage/)
COPY mcp/ ./mcp/
COPY storage/ ./storage/

# Cloud Run 은 PORT(기본 8080) 를 주입 → server 가 os.getenv("PORT") 우선 사용.
EXPOSE 8080

# PHOENIX_MCP_TRANSPORT=http (위 ENV) → mcp.run(transport="http", host=0.0.0.0, port=$PORT)
CMD ["python", "mcp/phoenix_mcp_server.py"]
