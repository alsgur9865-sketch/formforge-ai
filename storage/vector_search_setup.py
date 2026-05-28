# 파일 위치: storage/vector_search_setup.py
"""
Vertex AI Vector Search 인덱스 + 엔드포인트 관리 스크립트.

ARCHITECTURE.md §4.1 명세:
  - 인덱스 이름: formforge-debates-index
  - 차원: 1408 (multimodalembedding-001 통합 차원)
  - 거리: cosine
  - 업데이트: streaming

3단계 분리 (비용 안전):
  python storage/vector_search_setup.py create     # 무료 (Day 2 ~ Day 13)
  python storage/vector_search_setup.py deploy     # $13/day 시작 (Day 14)
  python storage/vector_search_setup.py undeploy   # 과금 중지 (Day 16)
  python storage/vector_search_setup.py status     # 현재 상태 확인 (언제든)

각 명령은 idempotent — 여러 번 실행해도 안전.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 환경 변수
# ---------------------------------------------------------------------------

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("VERTEX_AI_LOCATION", "us-central1")

if not PROJECT_ID:
    print("❌  .env의 GOOGLE_CLOUD_PROJECT가 비어 있습니다.", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

INDEX_DISPLAY_NAME = "formforge-debates-index"
ENDPOINT_DISPLAY_NAME = "formforge-debates-endpoint"
DEPLOYED_INDEX_ID = "formforge_debates_v1"

DIMENSIONS = 1408
DISTANCE = "COSINE_DISTANCE"
APPROX_NEIGHBORS = 150


# ---------------------------------------------------------------------------
# 출력 헬퍼
# ---------------------------------------------------------------------------

def _info(msg: str) -> None:
    print(f"ℹ️   {msg}")


def _ok(msg: str) -> None:
    print(f"✅  {msg}")


def _warn(msg: str) -> None:
    print(f"⚠️   {msg}")


def _err(msg: str) -> None:
    print(f"❌  {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 공통 — Vertex AI 초기화
# ---------------------------------------------------------------------------

def _init_vertex():
    from google.cloud import aiplatform
    aiplatform.init(project=PROJECT_ID, location=LOCATION)
    return aiplatform


def _find_index(aiplatform):
    """display_name으로 인덱스 검색. 없으면 None."""
    existing = aiplatform.MatchingEngineIndex.list(
        filter=f'display_name="{INDEX_DISPLAY_NAME}"'
    )
    return existing[0] if existing else None


def _find_endpoint(aiplatform):
    """display_name으로 엔드포인트 검색. 없으면 None."""
    existing = aiplatform.MatchingEngineIndexEndpoint.list(
        filter=f'display_name="{ENDPOINT_DISPLAY_NAME}"'
    )
    return existing[0] if existing else None


# ---------------------------------------------------------------------------
# Command: create — Index + Endpoint 생성 (무료)
# ---------------------------------------------------------------------------

def cmd_create() -> int:
    """
    Index + Endpoint 생성. 둘 다 무료. idempotent.

    실행 시점: Day 2 (또는 deploy 이전 언제든)
    """
    print()
    print("=" * 60)
    print("  CREATE — Index + Endpoint 생성 (무료)")
    print("=" * 60)
    print()
    print(f"Project: {PROJECT_ID}")
    print(f"Location: {LOCATION}")
    print()

    aiplatform = _init_vertex()

    # ---- Index ----
    print("[1/2] Index")
    index = _find_index(aiplatform)
    if index:
        _ok(f"기존 Index 재사용: {index.resource_name}")
    else:
        _info(f"Index 생성 중: {INDEX_DISPLAY_NAME}")
        _info("  (이 호출은 즉시 반환, 백그라운드 빌드 30분~1시간)")
        index = aiplatform.MatchingEngineIndex.create_tree_ah_index(
            display_name=INDEX_DISPLAY_NAME,
            dimensions=DIMENSIONS,
            approximate_neighbors_count=APPROX_NEIGHBORS,
            distance_measure_type=DISTANCE,
            leaf_node_embedding_count=500,
            leaf_nodes_to_search_percent=7,
            description="FormForge AI — debate consensus + safety flag embeddings",
            index_update_method="STREAM_UPDATE",
        )
        _ok(f"Index 생성 요청 완료: {index.resource_name}")

    index_id = index.resource_name.split("/")[-1]
    print()

    # ---- Endpoint ----
    print("[2/2] Endpoint")
    endpoint = _find_endpoint(aiplatform)
    if endpoint:
        _ok(f"기존 Endpoint 재사용: {endpoint.resource_name}")
    else:
        _info(f"Endpoint 생성 중: {ENDPOINT_DISPLAY_NAME}")
        endpoint = aiplatform.MatchingEngineIndexEndpoint.create(
            display_name=ENDPOINT_DISPLAY_NAME,
            public_endpoint_enabled=True,
            description="FormForge AI — public endpoint for debate similarity search",
        )
        _ok(f"Endpoint 생성 완료: {endpoint.resource_name}")

    endpoint_id = endpoint.resource_name.split("/")[-1]
    print()

    # ---- .env 안내 ----
    print("=" * 60)
    print("  📋 .env 파일에 다음 두 줄 추가하세요:")
    print("=" * 60)
    print()
    print(f"VECTOR_SEARCH_INDEX_ID={index_id}")
    print(f"VECTOR_SEARCH_ENDPOINT_ID={endpoint_id}")
    print(f"VECTOR_SEARCH_DEPLOYED_INDEX_ID={DEPLOYED_INDEX_ID}")
    print()
    print("=" * 60)
    print()
    print("💰 비용 안내:")
    print("   현재 상태(Index + Endpoint만 존재): 무료")
    print("   Day 14 데모 직전에 'deploy' 명령으로 배포 (~$13/day 시작)")
    print()
    print("📌 다음 확인:")
    print(f"   python storage/vector_search_setup.py status")
    print(f"   Index 빌드 완료까지 30~60분 대기 후 status 명령 재실행")
    return 0


# ---------------------------------------------------------------------------
# Command: status — 현재 상태 확인 (언제든 무료)
# ---------------------------------------------------------------------------

def cmd_status() -> int:
    print()
    print("=" * 60)
    print("  STATUS — Vector Search 리소스 현황")
    print("=" * 60)
    print()

    aiplatform = _init_vertex()

    # Index
    index = _find_index(aiplatform)
    if not index:
        _warn(f"Index 없음. 먼저 'create' 명령 실행 필요.")
    else:
        index_id = index.resource_name.split("/")[-1]
        print(f"📦 Index:    {INDEX_DISPLAY_NAME}")
        print(f"   ID:       {index_id}")
        try:
            stats = index.gca_resource.index_stats
            print(f"   Vectors:  {stats.vectors_count}")
            print(f"   Shards:   {stats.shards_count}")
        except Exception:
            print(f"   Stats:    (아직 빌드 중 — 30~60분 대기)")
        try:
            create_time = index.create_time
            print(f"   Created:  {create_time}")
        except Exception:
            pass

    print()

    # Endpoint
    endpoint = _find_endpoint(aiplatform)
    if not endpoint:
        _warn(f"Endpoint 없음. 먼저 'create' 명령 실행 필요.")
    else:
        endpoint_id = endpoint.resource_name.split("/")[-1]
        print(f"🌐 Endpoint: {ENDPOINT_DISPLAY_NAME}")
        print(f"   ID:       {endpoint_id}")
        deployed = endpoint.deployed_indexes
        if deployed:
            print(f"   Deployed: 🟢 {len(deployed)}개 인덱스 배포됨 (과금 중!)")
            for d in deployed:
                print(f"     - {d.id} (deployed_at={d.create_time})")
        else:
            print(f"   Deployed: 🔵 없음 (무료 상태)")

    print()
    print("=" * 60)
    return 0


# ---------------------------------------------------------------------------
# Command: deploy — Index를 Endpoint에 배포 (과금 시작!)
# ---------------------------------------------------------------------------

def cmd_deploy() -> int:
    print()
    print("=" * 60)
    print("  ⚠️   DEPLOY — Index 배포 (과금 시작 ~$13/day)")
    print("=" * 60)
    print()

    # 명시적 확인
    answer = input("정말 배포하시겠습니까? 'yes deploy' 입력 시에만 진행: ").strip()
    if answer != "yes deploy":
        _info("취소됨.")
        return 0

    aiplatform = _init_vertex()
    index = _find_index(aiplatform)
    endpoint = _find_endpoint(aiplatform)

    if not index or not endpoint:
        _err("Index 또는 Endpoint가 없습니다. 'create' 먼저 실행.")
        return 1

    # 이미 배포됐는지 확인
    for d in endpoint.deployed_indexes:
        if d.id == DEPLOYED_INDEX_ID:
            _ok(f"이미 배포됨: {DEPLOYED_INDEX_ID}")
            return 0

    _info(f"배포 시작 (20~40분 소요, 호출 동안 동기 블록)...")
    try:
        endpoint.deploy_index(
            index=index,
            deployed_index_id=DEPLOYED_INDEX_ID,
            display_name="FormForge Debates Deployed v1",
            min_replica_count=1,
            max_replica_count=2,
        )
        _ok("배포 완료. 🔴 이 시점부터 시간당 과금이 시작됩니다.")
        _info("데모 끝나면 'undeploy' 명령으로 과금 중지.")
    except Exception as e:
        _err(f"배포 실패: {e}")
        _warn("Index 빌드가 안 끝났을 가능성. status 명령으로 vectors_count 확인.")
        return 1

    return 0


# ---------------------------------------------------------------------------
# Command: undeploy — 배포 해제 (과금 중지)
# ---------------------------------------------------------------------------

def cmd_undeploy() -> int:
    print()
    print("=" * 60)
    print("  UNDEPLOY — 배포 해제 (과금 중지)")
    print("=" * 60)
    print()

    aiplatform = _init_vertex()
    endpoint = _find_endpoint(aiplatform)
    if not endpoint:
        _err("Endpoint 없음.")
        return 1

    target = None
    for d in endpoint.deployed_indexes:
        if d.id == DEPLOYED_INDEX_ID:
            target = d
            break

    if not target:
        _ok(f"배포된 인덱스가 없습니다. 이미 과금 중지 상태.")
        return 0

    _info(f"배포 해제 중: {DEPLOYED_INDEX_ID} (5~10분 소요)...")
    try:
        endpoint.undeploy_index(deployed_index_id=DEPLOYED_INDEX_ID)
        _ok("배포 해제 완료. 과금이 중지되었습니다.")
    except Exception as e:
        _err(f"배포 해제 실패: {e}")
        return 1

    return 0


# ---------------------------------------------------------------------------
# 메인 디스패처
# ---------------------------------------------------------------------------

USAGE = """\
Usage: python storage/vector_search_setup.py <command>

Commands:
  create      Index + Endpoint 생성 (무료, idempotent)
  status      현재 상태 확인 (무료)
  deploy      Index를 Endpoint에 배포 (~$13/day 시작!)
  undeploy    배포 해제 (과금 중지)

권장 순서:
  Day 2~13:  create  →  (Index 빌드 30~60분 대기)
  Day 14:    deploy  (데모 직전)
  Day 16:    undeploy (데모 종료 후)
"""


def main() -> int:
    if len(sys.argv) < 2:
        print(USAGE)
        return 1

    cmd = sys.argv[1].lower()
    dispatch = {
        "create": cmd_create,
        "status": cmd_status,
        "deploy": cmd_deploy,
        "undeploy": cmd_undeploy,
    }
    if cmd not in dispatch:
        _err(f"알 수 없는 명령: {cmd}")
        print()
        print(USAGE)
        return 1
    return dispatch[cmd]()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n중단됨.", file=sys.stderr)
        raise SystemExit(130)
