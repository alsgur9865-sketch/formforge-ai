# 파일 위치: storage/cloud_storage_client.py
"""
Cloud Storage 영상 업로드/다운로드 헬퍼.

용도:
  - 사용자가 Streamlit에서 운동 영상 업로드 → GCS 버킷 저장
  - PoseExtractor가 GCS URI로 비디오 읽기 (Gemini Vision은 gs:// URI 직접 지원)
  - 샘플 영상 일괄 업로드 (CLI)

버킷 명명 규칙:
  formforge-videos-{project-id}

ARCHITECTURE.md 흐름:
  Streamlit upload → gs://formforge-videos-.../debates/{debate_id}/{filename}
  → debates 문서의 video_uri 필드에 저장
  → PoseExtractor / Encourager / Scrutinizer가 같은 URI 참조
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import BinaryIO

from dotenv import load_dotenv
from google.cloud import storage

load_dotenv()

# ---------------------------------------------------------------------------
# 환경 변수
# ---------------------------------------------------------------------------

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
DEFAULT_BUCKET_NAME = f"formforge-videos-{PROJECT_ID}" if PROJECT_ID else None
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

# ---------------------------------------------------------------------------
# 싱글톤 클라이언트
# ---------------------------------------------------------------------------

_client: storage.Client | None = None


def _gcs_client() -> storage.Client:
    """GCS 클라이언트 싱글톤. service-account 자동 사용."""
    global _client
    if _client is not None:
        return _client

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials_path and os.path.exists(credentials_path):
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(credentials_path)
        _client = storage.Client(project=PROJECT_ID, credentials=creds)
    else:
        _client = storage.Client(project=PROJECT_ID)

    return _client


# ---------------------------------------------------------------------------
# 버킷 관리
# ---------------------------------------------------------------------------

def ensure_bucket(bucket_name: str | None = None, location: str = "us-central1") -> storage.Bucket:
    """버킷이 없으면 생성. 있으면 그대로 반환. idempotent."""
    if bucket_name is None:
        if not DEFAULT_BUCKET_NAME:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT가 .env에 없어 버킷 이름을 만들 수 없음.")
        bucket_name = DEFAULT_BUCKET_NAME

    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    if bucket.exists():
        return bucket

    bucket.storage_class = "STANDARD"
    bucket = client.create_bucket(bucket, location=location)
    return bucket


# ---------------------------------------------------------------------------
# 업로드 (Streamlit / CLI 양쪽 사용)
# ---------------------------------------------------------------------------

def upload_video_file(
    local_path: str | Path,
    debate_id: str | None = None,
    bucket_name: str | None = None,
    content_type: str = "video/mp4",
) -> str:
    """
    로컬 파일 경로에서 GCS로 업로드.

    저장 경로 규칙:
      gs://{bucket}/debates/{debate_id}/{original_filename}
      debate_id 없으면 새 UUID 사용.

    반환: gs:// URI (Gemini Vision이 직접 입력으로 받음)
    """
    local_path = Path(local_path)
    if not local_path.exists():
        raise FileNotFoundError(f"파일 없음: {local_path}")

    if local_path.suffix.lower() not in ALLOWED_VIDEO_EXTENSIONS:
        raise ValueError(
            f"지원하지 않는 영상 확장자: {local_path.suffix}. "
            f"허용: {sorted(ALLOWED_VIDEO_EXTENSIONS)}"
        )

    bucket = ensure_bucket(bucket_name)
    debate_id = debate_id or str(uuid.uuid4())
    blob_path = f"debates/{debate_id}/{local_path.name}"

    blob = bucket.blob(blob_path)
    blob.upload_from_filename(str(local_path), content_type=content_type)

    return f"gs://{bucket.name}/{blob_path}"


def upload_video_stream(
    file_stream: BinaryIO,
    filename: str,
    debate_id: str | None = None,
    bucket_name: str | None = None,
    content_type: str = "video/mp4",
) -> str:
    """
    Streamlit `st.file_uploader` 같은 in-memory 스트림에서 GCS로 업로드.

    반환: gs:// URI
    """
    suffix = Path(filename).suffix.lower()
    if suffix and suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise ValueError(
            f"지원하지 않는 영상 확장자: {suffix}. "
            f"허용: {sorted(ALLOWED_VIDEO_EXTENSIONS)}"
        )

    bucket = ensure_bucket(bucket_name)
    debate_id = debate_id or str(uuid.uuid4())
    blob_path = f"debates/{debate_id}/{filename}"

    blob = bucket.blob(blob_path)
    blob.upload_from_file(file_stream, content_type=content_type, rewind=True)

    return f"gs://{bucket.name}/{blob_path}"


# ---------------------------------------------------------------------------
# 다운로드 / signed URL
# ---------------------------------------------------------------------------

def download_to_local(gs_uri: str, local_path: str | Path) -> Path:
    """gs:// URI → 로컬 파일. MediaPipe Stage 1이 로컬 파일 필요."""
    if not gs_uri.startswith("gs://"):
        raise ValueError(f"gs:// URI가 아님: {gs_uri}")

    no_scheme = gs_uri[5:]
    bucket_name, _, blob_path = no_scheme.partition("/")

    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(str(local_path))
    return local_path


def get_signed_url(gs_uri: str, expires_minutes: int = 60) -> str:
    """Streamlit이 비디오 재생용으로 쓸 시간제한 URL."""
    if not gs_uri.startswith("gs://"):
        raise ValueError(f"gs:// URI가 아님: {gs_uri}")

    no_scheme = gs_uri[5:]
    bucket_name, _, blob_path = no_scheme.partition("/")

    from datetime import timedelta
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=expires_minutes),
        method="GET",
    )


# ---------------------------------------------------------------------------
# CLI — 샘플 영상 일괄 업로드
# ---------------------------------------------------------------------------

def _cli_upload(local_path: str) -> None:
    """
    터미널에서 한 영상을 sample/ prefix로 업로드.

    실행:
        python storage/cloud_storage_client.py data/sample_videos/squat_demo.mp4
    """
    p = Path(local_path)
    if not p.exists():
        print(f"❌  파일 없음: {p}", file=sys.stderr)
        sys.exit(1)

    bucket = ensure_bucket()
    blob_path = f"samples/{p.name}"
    blob = bucket.blob(blob_path)
    blob.upload_from_filename(str(p))

    uri = f"gs://{bucket.name}/{blob_path}"
    print(f"✅  업로드 완료: {uri}")
    print(f"   GCP 콘솔: https://console.cloud.google.com/storage/browser/{bucket.name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python storage/cloud_storage_client.py <local_video_path>")
        print("       (버킷이 없으면 자동 생성됩니다)")
        sys.exit(1)
    _cli_upload(sys.argv[1])
