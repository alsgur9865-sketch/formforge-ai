# 파일 위치: mcp/phoenix_mcp_server.py
"""
커스텀 Phoenix MCP wrapper server — Day 12 Task 12.1 (스켈레톤, P4 0% → 30%).

ARCHITECTURE.md §5.2 명세 구현. FastMCP(2.x) 기반 thin wrapper 서버.

노출 tool 2개 (Mediator 가 자체 trace introspection 용으로 호출):
  - query_past_debates(user_id, exercise_type, limit=5)
      → 이 사용자의 과거 토론 합의 패턴 조회.
        [실동작] Firestore `get_recent_debates()` join.
        [스켈레톤] Phoenix REST trace 쿼리는 미구현 → 호출 시 graceful fallback
                   (Firestore 단독 조회 + 경고 span). Day 12+ 에 실연동 예정.
  - query_similar_safety_flags(safety_flag_name, limit=10)
      → 비슷한 안전 플래그가 과거에 어떻게 해결됐는지 cross-user 조회.
        [스켈레톤] Vertex AI Vector Search 는 Day 14 배포 → Firestore 스캔 fallback.

절대원칙:
  - P4: Mediator 가 이 서버를 도구로 호출 → 과거 trace 쿼리 (Task 12.2 에서 ADK 연결).
  - P1: 서버 자체도 Phoenix 자동 계측 등록 → tool 호출이 Phoenix Cloud 에 TOOL span 으로 기록.
  - P5: tool 응답에도 의료 면책 문구 포함.

Fallback 철학 (§5.3): Phoenix REST 도달 불가 시 Firestore 단독 조회 + 경고 trace.
  → Live URL 안정성 확보 (P4 violation 회피).

Transport (ARCHITECTURE.md §5.3):
  PHOENIX_MCP_TRANSPORT=stdio  (기본, 로컬 dev — ADK 가 subprocess 로 실행)
  PHOENIX_MCP_TRANSPORT=http   (Cloud Run prod — Day 14 별도 서비스 배포)

⚠️ stdio 모드에서 stdout 은 MCP JSON-RPC 통신 채널입니다.
   따라서 이 파일의 모든 로그/경고는 반드시 stderr 로만 출력합니다. (print(..., file=sys.stderr))

검증:
  python mcp/phoenix_mcp_server.py --selftest   # tool 2개 등록 + impl 직접 호출 (stdout OK)
  python mcp/phoenix_mcp_server.py              # stdio MCP 서버 기동
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 0단계: .env 로드.
#   ⚠️ 주의: 프로젝트 루트(_PROJECT_ROOT)를 sys.path 에 넣는 작업은 "여기서 하지 않음".
#   우리 프로젝트 폴더 이름이 `mcp/` 인데, 이는 PyPI 의 `mcp` 패키지와 이름이 같다.
#   루트를 path 최상단에 먼저 넣으면 fastmcp 내부의 `import mcp.types` 가 우리 폴더를
#   가리켜 `ModuleNotFoundError: No module named 'mcp.types'` 로 터진다.
#   → 해결: fastmcp(→ 진짜 mcp 패키지) import 를 먼저 끝낸 뒤(2단계) 루트를 path 에 추가.
#   load_dotenv 는 파일 "경로"만 쓰므로 sys.path 와 무관 → 여기서 해도 안전.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_PROJECT_ROOT / ".env")


def _log(msg: str) -> None:
    """stdio 통신 채널(stdout) 오염 방지 — 모든 로그는 stderr 로."""
    print(f"[phoenix-mcp] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# 1단계: Phoenix 자동 계측 등록 (fail-soft)
#         API key 없거나 register 실패해도 서버·tool 은 정상 동작.
#         성공 시 tool 호출이 Phoenix Cloud 에 TOOL span 으로 송출됨 (P1).
# ---------------------------------------------------------------------------
_PHOENIX_READY = False
try:
    _api_key = os.getenv("PHOENIX_API_KEY")
    if _api_key:
        import contextlib
        import io as _io

        from phoenix.otel import register  # noqa: E402

        _endpoint = os.getenv(
            "PHOENIX_COLLECTOR_ENDPOINT", "https://app.phoenix.arize.com"
        )
        # ⚠️ register() 는 stdout 에 "OpenTelemetry Tracing Details" 박스를 출력 →
        #    stdio MCP 서버의 JSON-RPC 채널(stdout) 오염 → P4 깨짐. stdout 을 버린다.
        with contextlib.redirect_stdout(_io.StringIO()):
            register(
                project_name=os.getenv("PHOENIX_PROJECT_NAME", "formforge-prod"),
                endpoint=_endpoint.rstrip("/") + "/v1/traces",
                headers={"authorization": f"Bearer {_api_key}"},
            )
        _PHOENIX_READY = True
        _log("Phoenix 계측 등록 완료 — tool 호출이 Phoenix Cloud 에 기록됩니다.")
    else:
        _log("PHOENIX_API_KEY 없음 — 자체 trace 송출 비활성 (tool 은 정상 동작).")
except Exception as exc:  # noqa: BLE001 — 계측 실패가 서버를 죽이면 안 됨
    _log(f"Phoenix register 실패 (무시하고 계속): {exc}")

# OTel tracer — register 됐으면 Phoenix Cloud 로, 아니면 no-op.
from opentelemetry import trace  # noqa: E402

_tracer = trace.get_tracer("formforge.mcp.phoenix")


# ---------------------------------------------------------------------------
# 2단계: 의존 모듈
#   fastmcp(→ mcp.types) import 는 반드시 sys.path 에 프로젝트 루트를 넣기 "전"에.
#   (0단계 주석 참조 — mcp/ 폴더가 PyPI mcp 패키지를 shadow 하는 문제 회피)
# ---------------------------------------------------------------------------
from fastmcp import FastMCP  # noqa: E402

# 진짜 mcp 패키지가 sys.modules 에 캐시된 뒤이므로, 이제 루트를 path 에 넣어도 안전.
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from storage import firestore_client  # noqa: E402

    _FIRESTORE_IMPORTED = True
except Exception as exc:  # noqa: BLE001
    firestore_client = None  # type: ignore[assignment]
    _FIRESTORE_IMPORTED = False
    _log(f"storage.firestore_client import 실패: {exc}")


# P5 절대원칙 — 모든 결과에 의료 면책. (Mediator 가 영어 JSON 을 다루므로 영어 문구)
MEDICAL_DISCLAIMER = (
    "Informational only. Not medical advice. "
    "Consult a qualified professional for pain or injury."
)


# ---------------------------------------------------------------------------
# 내부 예외 — Phoenix REST 미가용 신호 (스켈레톤 단계)
# ---------------------------------------------------------------------------
class PhoenixUnavailable(RuntimeError):
    """Phoenix REST trace 쿼리 불가 → 상위에서 Firestore fallback 유도."""


def _notna(value: Any) -> bool:
    """pandas NaN/None best-effort 체크 (pandas import 없이). NaN 은 자기 자신과 != 다."""
    if value is None:
        return False
    try:
        return value == value  # noqa: PLR0124 — NaN == NaN → False 트릭
    except Exception:  # noqa: BLE001
        return True


def _query_phoenix_traces(
    user_id: str, exercise_type: str | None, limit: int
) -> list[dict[str, Any]]:
    """
    Phoenix Cloud REST API 로 사용자 관련 trace span 을 조회 (P4 introspection 실연동).

    arize-phoenix-client(phoenix.client.Client) 로 프로젝트 span 을 가져온 뒤,
    input/output value 텍스트에 user_id / exercise_type 단서가 있는 span 만 best-effort
    로 추려 trace_id 목록을 반환한다. (우리 span 은 user_id 를 별도 attribute 로 일관
    기록하지 않으므로 서버 필터 대신 클라이언트 측 텍스트 매칭을 쓴다.)

    실패 시 PhoenixUnavailable 을 던져 상위 tool 이 Firestore 단독 fallback + 경고 span
    을 타게 한다 (§5.3, P4 violation 회피). 실패 케이스:
      - Phoenix 미등록 (_PHOENIX_READY=False, API key 없음/register 실패)
      - phoenix.client 미설치 (arize-phoenix-client)
      - 네트워크/인증/프로젝트 없음 등 조회 예외
    """
    if not _PHOENIX_READY:
        raise PhoenixUnavailable("Phoenix 미등록 (PHOENIX_API_KEY 없음 / register 실패)")

    try:
        from phoenix.client import Client  # noqa: E402
    except ImportError as exc:
        raise PhoenixUnavailable(
            f"phoenix.client 미설치 (arize-phoenix-client): {exc}"
        ) from exc

    base_url = (
        os.getenv("PHOENIX_COLLECTOR_ENDPOINT") or "https://app.phoenix.arize.com"
    ).rstrip("/")
    api_key = os.getenv("PHOENIX_API_KEY")
    project = os.getenv("PHOENIX_PROJECT_NAME", "formforge-prod")

    try:
        client = Client(base_url=base_url, api_key=api_key)
        df = client.spans.get_spans_dataframe(
            project_identifier=project, limit=max(limit * 10, 50)
        )
    except Exception as exc:  # noqa: BLE001 — 네트워크/인증/프로젝트 없음 등
        raise PhoenixUnavailable(
            f"Phoenix REST 조회 실패: {type(exc).__name__}: {exc}"
        ) from exc

    if df is None or getattr(df, "empty", True):
        return []

    needle_user = (user_id or "").lower()
    needle_ex = (exercise_type or "").lower()
    traces: list[dict[str, Any]] = []
    # iterrows: index = context.span_id, row = pandas Series (컬럼 라벨로 접근)
    for span_id, row in df.iterrows():
        blob = ""
        for col in ("attributes.input.value", "attributes.output.value"):
            v = row.get(col)
            if isinstance(v, str):
                blob += v.lower()
        # 도메인 필터: user_id 또는 exercise_type 단서가 있는 span 만 채택.
        if needle_user and needle_user in blob:
            pass
        elif needle_ex and needle_ex in blob:
            pass
        else:
            continue
        tid = row.get("context.trace_id")
        name = row.get("name")
        kind = row.get("span_kind")
        traces.append(
            {
                "trace_id": str(tid) if _notna(tid) else None,
                "span_id": str(span_id),
                "span_name": str(name) if _notna(name) else None,
                "span_kind": str(kind) if _notna(kind) else None,
            }
        )
        if len(traces) >= limit:
            break
    return traces


# ---------------------------------------------------------------------------
# 직렬화 헬퍼 — Firestore 타임스탬프/문서를 JSON 안전 형태로
# ---------------------------------------------------------------------------
def _iso(value: Any) -> str | None:
    """Firestore DatetimeWithNanoseconds → ISO 문자열. 그 외는 str 또는 None."""
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:  # noqa: BLE001
            return str(value)
    return str(value)


def _extract_scrutinizer_risk(round_data: dict[str, Any]) -> str | None:
    """한 라운드 dict 에서 Scrutinizer 의 primary_risk 이름을 best-effort 추출."""
    if not isinstance(round_data, dict):
        return None
    scrut = round_data.get("scrutinizer") or {}
    if not isinstance(scrut, dict):
        return None
    primary = scrut.get("primary_risk")
    if isinstance(primary, dict):
        return primary.get("name") or primary.get("description")
    if isinstance(primary, str):
        return primary
    return None


def _summarize_debate(doc: dict[str, Any]) -> dict[str, Any]:
    """debate 문서 → Mediator 가 읽기 좋은 요약. consensus 미생성이면 None 유지."""
    rounds = doc.get("rounds") or []
    last_risk = None
    if rounds:
        last_risk = _extract_scrutinizer_risk(rounds[-1])
    return {
        "debate_id": doc.get("debate_id"),  # get_recent_debates 가 주입한 실제 doc id
        "exercise_type": doc.get("exercise_type"),
        "status": doc.get("status"),
        "created_at": _iso(doc.get("created_at")),
        "rounds_count": len(rounds),
        "consensus": doc.get("consensus"),  # None = 아직 Mediator 미실행
        "last_scrutinizer_risk": last_risk,
        "trace_ids": doc.get("trace_ids") or {},
    }


# ---------------------------------------------------------------------------
# 핵심 로직 (impl) — @mcp.tool 과 분리해서 selftest 가 직접 호출 가능하게
# ---------------------------------------------------------------------------
def _query_past_debates_impl(
    user_id: str, exercise_type: str | None = None, limit: int = 5
) -> dict[str, Any]:
    with _tracer.start_as_current_span(
        "mcp.query_past_debates",
        attributes={
            "openinference.span.kind": "TOOL",
            "tool.name": "query_past_debates",
            "input.value": json.dumps(
                {"user_id": user_id, "exercise_type": exercise_type, "limit": limit},
                ensure_ascii=False,
            ),
            "input.mime_type": "application/json",
        },
    ) as span:
        # 1) Phoenix REST trace 조회 (introspection 실연동). 실패 시 Firestore fallback.
        phoenix_status: str
        phoenix_traces: list[dict[str, Any]] = []
        try:
            phoenix_traces = _query_phoenix_traces(user_id, exercise_type, limit)
            phoenix_status = f"ok ({len(phoenix_traces)} trace spans)"
            span.set_attribute("phoenix.fallback", False)
            span.set_attribute("phoenix.traces_found", len(phoenix_traces))
        except PhoenixUnavailable as exc:
            phoenix_status = f"unavailable → firestore_fallback ({exc})"
            span.set_attribute("phoenix.fallback", True)
            span.add_event("phoenix_unavailable", {"reason": str(exc)})

        # 2) Firestore join (실동작)
        debates: list[dict[str, Any]] = []
        source = "firestore"
        if not _FIRESTORE_IMPORTED or firestore_client is None:
            source = "error"
            result = {
                "user_id": user_id,
                "exercise_type": exercise_type,
                "found": 0,
                "source": source,
                "phoenix_status": phoenix_status,
                "error": "firestore_client 사용 불가 (import 실패)",
                "past_debates": [],
                "disclaimer": MEDICAL_DISCLAIMER,
            }
            span.set_attribute("output.value", json.dumps(result, ensure_ascii=False))
            span.set_attribute("debates.found", 0)
            return result

        try:
            raw = firestore_client.get_recent_debates(user_id, exercise_type, limit)
            debates = [_summarize_debate(d) for d in raw]
        except Exception as exc:  # noqa: BLE001 — 인덱스 미생성/권한 등
            source = "error"
            result = {
                "user_id": user_id,
                "exercise_type": exercise_type,
                "found": 0,
                "source": source,
                "phoenix_status": phoenix_status,
                "error": f"{type(exc).__name__}: {exc}",
                "hint": "복합 인덱스(user_id+exercise_type+created_at) 미생성일 수 있음",
                "phoenix_traces": phoenix_traces,  # Firestore 실패해도 Phoenix trace 는 살림
                "past_debates": [],
                "disclaimer": MEDICAL_DISCLAIMER,
            }
            span.set_attribute("output.value", json.dumps(result, ensure_ascii=False)[:4000])
            span.set_attribute("debates.found", 0)
            span.add_event("firestore_query_failed", {"error": str(exc)})
            return result

        result = {
            "user_id": user_id,
            "exercise_type": exercise_type,
            "found": len(debates),
            "source": source,
            "phoenix_status": phoenix_status,
            "phoenix_traces": phoenix_traces,  # Phoenix REST 로 가져온 실제 trace span
            "past_debates": debates,
            "disclaimer": MEDICAL_DISCLAIMER,
        }
        span.set_attribute("output.value", json.dumps(result, ensure_ascii=False)[:4000])
        span.set_attribute("output.mime_type", "application/json")
        span.set_attribute("debates.found", len(debates))
        return result


def _query_similar_safety_flags_impl(
    safety_flag_name: str, limit: int = 10
) -> dict[str, Any]:
    with _tracer.start_as_current_span(
        "mcp.query_similar_safety_flags",
        attributes={
            "openinference.span.kind": "TOOL",
            "tool.name": "query_similar_safety_flags",
            "input.value": json.dumps(
                {"safety_flag_name": safety_flag_name, "limit": limit},
                ensure_ascii=False,
            ),
            "input.mime_type": "application/json",
        },
    ) as span:
        # Vector Search 는 Day 14 배포 → 항상 Firestore 스캔 fallback
        vector_search_status = "not_deployed_until_day14"
        span.set_attribute("vector_search.deployed", False)
        span.set_attribute("phoenix.fallback", True)

        matches: list[dict[str, Any]] = []
        source = "firestore_scan_fallback"

        if not _FIRESTORE_IMPORTED or firestore_client is None:
            result = {
                "safety_flag_name": safety_flag_name,
                "found": 0,
                "source": "error",
                "vector_search_status": vector_search_status,
                "error": "firestore_client 사용 불가 (import 실패)",
                "similar_flags": [],
                "disclaimer": MEDICAL_DISCLAIMER,
            }
            span.set_attribute("output.value", json.dumps(result, ensure_ascii=False))
            span.set_attribute("flags.found", 0)
            return result

        try:
            db = firestore_client.init_firestore()
            from google.cloud import firestore as _fs  # noqa: E402

            # cross-user 최근 토론을 넉넉히 스캔 후 클라이언트 필터 (스켈레톤).
            # Day 14: 이 블록을 Vector Search 유사도 검색으로 교체.
            scan_n = max(limit * 4, 20)
            q = (
                db.collection("debates")
                .order_by("created_at", direction=_fs.Query.DESCENDING)
                .limit(scan_n)
            )
            needle = safety_flag_name.strip().lower()
            for snap in q.stream():
                doc = snap.to_dict() or {}
                for round_data in doc.get("rounds") or []:
                    risk = _extract_scrutinizer_risk(round_data)
                    if risk and needle in risk.lower():
                        matches.append(
                            {
                                "debate_id": snap.id,  # 실제 doc id (LLM 합성 방지)
                                "exercise_type": doc.get("exercise_type"),
                                "matched_risk": risk,
                                "consensus": doc.get("consensus"),
                                "created_at": _iso(doc.get("created_at")),
                                "trace_ids": doc.get("trace_ids") or {},
                            }
                        )
                        break  # 한 토론당 1회 매칭
                if len(matches) >= limit:
                    break
        except Exception as exc:  # noqa: BLE001
            result = {
                "safety_flag_name": safety_flag_name,
                "found": 0,
                "source": "error",
                "vector_search_status": vector_search_status,
                "error": f"{type(exc).__name__}: {exc}",
                "similar_flags": [],
                "disclaimer": MEDICAL_DISCLAIMER,
            }
            span.set_attribute("output.value", json.dumps(result, ensure_ascii=False)[:4000])
            span.set_attribute("flags.found", 0)
            span.add_event("firestore_scan_failed", {"error": str(exc)})
            return result

        result = {
            "safety_flag_name": safety_flag_name,
            "found": len(matches),
            "source": source,
            "vector_search_status": vector_search_status,
            "similar_flags": matches,
            "disclaimer": MEDICAL_DISCLAIMER,
        }
        span.set_attribute("output.value", json.dumps(result, ensure_ascii=False)[:4000])
        span.set_attribute("output.mime_type", "application/json")
        span.set_attribute("flags.found", len(matches))
        return result


# ---------------------------------------------------------------------------
# 3단계: FastMCP 서버 + tool 등록 (impl 위임 wrapper)
# ---------------------------------------------------------------------------
mcp = FastMCP("formforge-phoenix-mcp")


@mcp.tool
def query_past_debates(
    user_id: str, exercise_type: str | None = None, limit: int = 5
) -> dict[str, Any]:
    """Retrieve past debate consensus patterns for this user.

    Use this to check whether similar consensus was reached for this user before,
    so the Mediator can stay consistent with prior recommendations.

    Args:
        user_id: The user whose past debates to retrieve.
        exercise_type: Optional filter (e.g. "squat"). Omit to include all.
        limit: Max number of past debates to return (default 5).

    Returns:
        JSON with found count, source, phoenix_status, and a list of past debate
        summaries (consensus, last scrutinizer risk, trace_ids).
    """
    return _query_past_debates_impl(user_id, exercise_type, limit)


@mcp.tool
def query_similar_safety_flags(
    safety_flag_name: str, limit: int = 10
) -> dict[str, Any]:
    """Find how similar safety flags were resolved across all users.

    Use this when a risky pattern is detected to learn how the same biomechanical
    risk was handled in prior debates.

    Args:
        safety_flag_name: The risk/flag name to search for (e.g. "knee valgus").
        limit: Max number of matches to return (default 10).

    Returns:
        JSON with found count, source, vector_search_status, and matching flags.
    """
    return _query_similar_safety_flags_impl(safety_flag_name, limit)


# ---------------------------------------------------------------------------
# 4단계: 실행 — selftest / stdio / http transport 분기
# ---------------------------------------------------------------------------
def _run_selftest() -> int:
    """tool 등록 확인 + impl 직접 호출 (stdio 가 아니므로 stdout 출력 OK)."""
    print("=== Phoenix MCP server selftest ===")
    print(f"Phoenix 계측: {'ON' if _PHOENIX_READY else 'OFF (key 없음/실패)'}")
    print(f"Firestore import: {'OK' if _FIRESTORE_IMPORTED else 'FAIL'}")

    # 등록된 tool 목록 (FastMCP 3.x: list_tools() 는 async).
    # 반환형이 버전마다 list[Tool] / dict / ListToolsResult 로 갈리므로 normalize.
    tool_names: list[str] = []
    try:
        import asyncio

        raw = asyncio.run(mcp.list_tools())
        if isinstance(raw, dict):
            items = list(raw.values())
        elif hasattr(raw, "tools"):
            items = raw.tools
        else:
            items = list(raw)
        tool_names = sorted(getattr(t, "name", str(t)) for t in items)
        print(f"등록된 tools ({len(tool_names)}): {tool_names}")
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ list_tools() 확인 실패 (무시): {exc}")

    print("\n--- query_past_debates('user_001', 'squat', 5) ---")
    r1 = _query_past_debates_impl("user_001", "squat", 5)
    print(json.dumps(r1, ensure_ascii=False, indent=2))

    print("\n--- query_similar_safety_flags('knee valgus', 10) ---")
    r2 = _query_similar_safety_flags_impl("knee valgus", 10)
    print(json.dumps(r2, ensure_ascii=False, indent=2))

    # MCP 프로토콜 왕복 (in-memory client) — 실제 클라이언트가 tool 을 list 하고
    # call 할 수 있는지 검증. Task 12.2(ADK Mediator 연결) 전 서버 동작 보증.
    protocol_ok = False
    try:
        import asyncio

        from fastmcp import Client

        async def _roundtrip() -> list[str]:
            async with Client(mcp) as client:
                listed = await client.list_tools()
                names = sorted(t.name for t in listed)
                # 한 tool 을 실제 호출해 프로토콜 왕복까지 확인
                await client.call_tool(
                    "query_similar_safety_flags",
                    {"safety_flag_name": "knee valgus", "limit": 3},
                )
                return names

        proto_names = asyncio.run(_roundtrip())
        protocol_ok = {
            "query_past_debates",
            "query_similar_safety_flags",
        }.issubset(set(proto_names))
        print(f"\nMCP 프로토콜 왕복 tools: {proto_names}")
    except Exception as exc:  # noqa: BLE001
        print(f"\n⚠️ MCP 프로토콜 왕복 실패: {exc}")

    # acceptance (Task 12.1):
    #   1) tool 2개 등록 (list 됨)
    #   2) query_past_debates / query_similar_safety_flags 모두 dict 반환
    #   3) 두 응답 모두 의료 면책(P5) 포함
    tools_ok = {"query_past_debates", "query_similar_safety_flags"}.issubset(
        set(tool_names)
    )
    ok = (
        tools_ok
        and protocol_ok
        and isinstance(r1, dict)
        and isinstance(r2, dict)
        and "disclaimer" in r1
        and "disclaimer" in r2
    )
    print(f"\n  tool 2개 등록: {'OK' if tools_ok else 'FAIL'}")
    print(f"  MCP 프로토콜 왕복: {'OK' if protocol_ok else 'FAIL'}")
    print(f"{'✅ selftest 통과' if ok else '❌ selftest 실패'}")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_run_selftest())

    transport = os.getenv("PHOENIX_MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "http":
        host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
        # Cloud Run 은 PORT 를 주입 → 우선 사용. 없으면 MCP_SERVER_PORT, 기본 8080.
        port = int(os.getenv("PORT") or os.getenv("MCP_SERVER_PORT") or "8080")
        _log(f"HTTP transport 기동: {host}:{port}")
        mcp.run(transport="http", host=host, port=port)
    else:
        _log("STDIO transport 기동 (로컬 dev / ADK subprocess).")
        mcp.run()
