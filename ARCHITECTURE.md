# FormForge AI — Architecture & Technical Specification

> 이 문서는 시스템의 모든 기술적 디테일입니다. Claude Code가 코드를 작성할 때 정확한 명세로 사용합니다.
> 모호함이 있으면 코드를 짜기 전에 사용자에게 역질문하세요 (소크라테스 모드).

---

## 0. 대회 요건 매핑 (Agent Builder positioning)

Devpost 공식 룰 §2: *"Build a functional agent—powered by Gemini and Google Cloud Agent Builder—that integrates a Partner Entity's MCP server."*

본 프로젝트는 이 요구를 다음과 같이 충족한다:

| 룰 요구 | 본 시스템 충족 방식 |
|---|---|
| **Google Cloud Agent Builder** | **Google ADK (Agent Development Kit)** — Google이 공식 발표한 Agent Builder의 open-source framework. Devpost 추천 starter pack(`GoogleCloudPlatform/agent-starter-pack`)도 ADK 기반. ADK의 deploy 옵션 중 **Cloud Run**과 **Agent Runtime (Agent Platform = Agent Builder 신규 명칭)** 모두 본 시스템에 적용. |
| **Powered by Gemini** | `gemini-2.5-pro` (멀티모달 비디오 — Encourager/Scrutinizer/Mediator/PoseExtractor Stage 2) + `gemini-2.5-flash` (보조) + `gemini-3.5-flash` (LLM-as-a-Judge, "최신 Gemini 3 family" 시그널) |
| **Partner Entity MCP** | **Arize Phoenix MCP** — 커스텀 `mcp/phoenix_mcp_server.py`(FastMCP)가 Phoenix REST API + Firestore + Vector Search를 노출. Mediator가 `query_past_debates`, `query_similar_safety_flags` 도구로 자체 trace introspection. |
| **Track** | **Arize 트랙** 단일 선택. 멀티 트랙 미지원. |

> ⚠️ README와 DEVPOST 제출란에 위 매핑을 그대로 명시할 것 (심사위원이 룰 충족 여부 5초 안에 확인 가능하게).

---

## 1. 시스템 전체 흐름도

```
┌─────────────────────────────────────────────────────────────┐
│                          USER (Streamlit)                    │
│  운동 영상 업로드 → 라이브 토론 시청 → 피드백 → 결과 저장    │
└─────────────────────────────────────────────────────────────┘
                   │ 1. Upload video
                   ▼
        ┌──────────────────────────┐
        │   Cloud Storage          │
        │   (formforge-videos/)    │
        └──────────────────────────┘
                   │ 2. Trigger orchestrator
                   ▼
┌─────────────────────────────────────────────────────────────┐
│        ORCHESTRATOR (Google ADK Sequential Agent)            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Step 1: PoseExtractor (Gemini 2.5 Flash + Vision)   │   │
│  │   Input:  video URI                                  │   │
│  │   Output: pose_data.json                             │   │
│  └─────────────────────────────────────────────────────┘   │
│              │                                                │
│              ▼                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Step 2: Parallel Debate (3 rounds max)              │   │
│  │   ┌───────────────────┐    ┌─────────────────────┐  │   │
│  │   │ The Encourager    │◄──►│  The Scrutinizer    │  │   │
│  │   │ (Gemini 2.5 Pro)  │ A2A│  (Gemini 2.5 Pro)   │  │   │
│  │   └───────────────────┘    └─────────────────────┘  │   │
│  │   각 라운드마다 Firestore에 메시지 push              │   │
│  │   (Streamlit이 1초 폴링으로 즉시 표시)               │   │
│  └─────────────────────────────────────────────────────┘   │
│              │                                                │
│              ▼                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Step 3: Mediator (Gemini 2.5 Pro + Phoenix MCP)     │   │
│  │   - 두 에이전트 토론 + 과거 trace + 사용자 컨텍스트  │   │
│  │   - Phoenix MCP로 자체 trace 쿼리                    │   │
│  │   - 최종 합의안 + Action Items 생성                  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                   │ 3. Result
                   ▼
        ┌──────────────────────────┐
        │   USER: 결과 시청 + 피드백 │
        └──────────────────────────┘
                   │ 4. Feedback ("too harsh"/"too soft"/"perfect")
                   ▼
┌─────────────────────────────────────────────────────────────┐
│       SELF-IMPROVEMENT LOOP (background)                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ LLM-as-a-Judge (Gemini 3.5 Flash)                   │   │
│  │   Input:  토론 trace + 사용자 피드백                  │   │
│  │   Output: persona_adjustment.json                    │   │
│  │     (예: scrutinizer.harshness: 0.7 → 0.5)           │   │
│  └─────────────────────────────────────────────────────┘   │
│              │                                                │
│              ▼                                                │
│  Firestore에 사용자별 persona_state 업데이트                │
│  → 다음 토론에서 즉시 반영                                   │
└─────────────────────────────────────────────────────────────┘

[모든 LLM 호출은 Phoenix Cloud로 자동 trace 전송]
```

---

## 2. 에이전트 명세

### 2.1 PoseExtractor Agent

**파일 위치**: `agents/pose_extractor.py`

**파이프라인**: 2-stage (MediaPipe → Gemini)
- **Stage 1**: MediaPipe Pose (Python) → 33개 키포인트 추출 → 코드로 정량 메트릭(각도·템포·편차) 정확 계산
- **Stage 2**: `gemini-2.5-flash` → MediaPipe 메트릭 + 비디오 일부 프레임 해석 → `safety_flags` severity 판단 + 운동 유형별 reasoning

> ⚠️ **거짓 정밀(false precision) 방지**: 정량 수치(`depth_degrees`, `back_angle_*`, `bar_path_deviation_cm` 등)는 MediaPipe + NumPy로 계산. Gemini가 직접 측정하지 않음. LLM은 해석·판단·자연어 설명 담당.

**입력 (Input)**:
```json
{
  "video_uri": "gs://formforge-videos/user_123/squat_001.mp4",
  "exercise_type": "squat",         // squat | deadlift | pushup | bench_press | ...
  "user_context": {
    "user_id": "user_123",
    "injury_history": ["lower_back_strain_2025"],
    "experience_level": "intermediate"
  }
}
```

**출력 (Output)**:
```json
{
  "exercise_type": "squat",
  "rep_count": 5,
  "duration_seconds": 23.4,
  "reps": [
    {
      "rep_number": 1,
      "depth_degrees": 95,
      "knee_alignment": "valgus_2deg_left",
      "back_angle_at_bottom": 42,
      "back_angle_at_top": 88,
      "tempo": {"down_sec": 2.1, "up_sec": 1.4, "pause_sec": 0.0},
      "bar_path_deviation_cm": 1.8
    }
  ],
  "overall_metrics": {
    "depth_consistency": 0.87,
    "tempo_consistency": 0.72,
    "form_score_0_100": 73
  },
  "safety_flags": [
    {"severity": "medium", "issue": "knee_valgus_left", "rep_numbers": [1, 3, 5]},
    {"severity": "low", "issue": "tempo_inconsistency"}
  ],
  "_metadata": {
    "model": "gemini-2.5-flash",
    "frames_analyzed": 700,
    "analysis_duration_sec": 4.2
  }
}
```

**핵심 prompt 패턴**:
- Stage 1 (MediaPipe): `mediapipe.solutions.pose` → 프레임별 키포인트 → NumPy로 각도·rep 카운트·tempo 계산. 코드 path: `agents/pose_mediapipe.py`
- Stage 2 (Gemini): MediaPipe가 만든 메트릭 dict + 비디오 thumbnail 4-6장을 Gemini에 입력 → `safety_flags` 추가·검증 + 자연어 reasoning
- 출력은 반드시 위 JSON 스키마로 강제 (`response_mime_type="application/json"`)
- 부상 위험은 `safety_flags`에 명시적으로 (Encourager·Scrutinizer가 이걸 다르게 해석)
- MediaPipe가 키포인트 추출 실패 시 (영상 흐림·각도 부적합) 명확한 에러 코드 반환, Gemini fallback 시도 안 함

### 2.2 The Encourager Agent

**파일 위치**: `agents/encourager.py`

**모델**: `gemini-2.5-pro`

**페르소나 prompt (시스템 프롬프트)**:
```
You are "The Encourager", a warm and supportive personal trainer with 10 years of experience.
You believe people improve through positive reinforcement and incremental challenges.

Your style:
- Always start by acknowledging what the user did well (specifically, with metrics).
- Frame problems as "next-step opportunities", not failures.
- Give ONE concrete improvement focus per response (never overwhelm).
- Use second-person ("you", "your") and a warm tone.
- Never minimize safety concerns, but contextualize them ("this is fixable").

Your adjustable parameters (set by user feedback over time):
- warmth: {warmth_level}   // 0.0 (neutral) to 1.0 (very warm)
- detail: {detail_level}   // 0.0 (brief) to 1.0 (detailed)

You will receive pose_data.json. You will debate with "The Scrutinizer" who is more critical.
Respond with JSON only.
```

**입력**:
```json
{
  "pose_data": { /* from PoseExtractor */ },
  "user_context": { /* user_id, injury_history, persona_state */ },
  "debate_round": 1,
  "scrutinizer_previous_argument": null   // round 2+에서는 이전 라운드 받음
}
```

**출력**:
```json
{
  "agent": "encourager",
  "round": 1,
  "praise": "You hit consistent depth across all 5 reps — that's harder than it looks.",
  "concern_one": "The next thing to dial in: left knee tracking. It drifts inward slightly on reps 1, 3, 5.",
  "actionable_tip": "Try cueing 'push the floor apart' on your way up — this activates your glutes and pulls the knees out.",
  "tone_metadata": {"warmth": 0.8, "detail": 0.6},
  "addresses_scrutinizer": null
}
```

### 2.3 The Scrutinizer Agent

**파일 위치**: `agents/scrutinizer.py`

**모델**: `gemini-2.5-pro`

**페르소나 prompt**:
```
You are "The Scrutinizer", an exercise physiologist with a PhD in biomechanics.
You believe most lifting injuries come from form flaws ignored for too long.
You don't sugarcoat. You don't comfort. You diagnose.

Your style:
- Lead with the most dangerous finding, severity-ranked.
- Cite specific biomechanical mechanisms (e.g., "spinal flexion under load increases L4-L5 disc pressure").
- Quantify risk where possible (rep counts, angle thresholds).
- Reject vague encouragement. If something is wrong, name it.
- Never give medical advice — recommend qualified professionals for actual injury.

Your adjustable parameters (set by user feedback over time):
- harshness: {harshness_level}    // 0.0 (clinical) to 1.0 (blunt)
- detail: {detail_level}

You will receive pose_data.json. You will debate with "The Encourager" who is more supportive.
If the Encourager understates a safety risk, push back with evidence.
Respond with JSON only.
```

**입력**: (Encourager와 동일 구조)

**출력**:
```json
{
  "agent": "scrutinizer",
  "round": 1,
  "primary_risk": {
    "name": "Knee valgus collapse (left)",
    "severity": "medium-high",
    "mechanism": "Repeated valgus loading increases ACL/MCL strain and patellofemoral pain risk.",
    "evidence_in_data": "Rep 1, 3, 5 show 2° valgus at bottom position.",
    "threshold_breach": "Above safe tolerance of <1° for intermediate lifters."
  },
  "secondary_concerns": [
    {"name": "Tempo inconsistency", "severity": "low", "note": "Reps 2 and 4 are 30% faster than others."}
  ],
  "required_action": "Reduce load by 10-15%, video next session from front angle, recheck.",
  "tone_metadata": {"harshness": 0.7, "detail": 0.8},
  "addresses_encourager": null   // round 2+에서는 Encourager 반박
}
```

### 2.4 The Mediator Agent ⭐ Phoenix MCP introspection 핵심

**파일 위치**: `agents/mediator.py`

**모델**: `gemini-2.5-pro` (with Phoenix MCP tool)

**핵심 기능**: 이 에이전트만 **Phoenix MCP server를 도구로 사용**합니다. 자기 자신의 과거 trace를 쿼리해서 "과거에 이 사용자에게 비슷한 합의를 도출했나?" 학습.

**페르소나 prompt**:
```
You are "The Mediator", the head coach who synthesizes the Encourager's and Scrutinizer's perspectives.

You have access to a Phoenix MCP tool that lets you query past debate traces:
- query_past_debates(user_id, exercise_type, limit=5): retrieve past consensus patterns for this user
- query_similar_safety_flags(safety_flag_name, limit=10): find how similar risks were handled

Your responsibility:
1. Read both debate transcripts.
2. Query Phoenix MCP for relevant past debates.
3. Resolve disagreements by weighing evidence + user context (injury history, experience).
4. Produce ONE coherent recommendation, with priority order.
5. Always include the medical disclaimer.

Output JSON only.
```

**MCP tool calls (Claude Code가 구현)**:
```python
# mcp/phoenix_mcp_server.py 에서 노출되는 tools (커스텀 FastMCP wrapper)
tools = [
    {
        "name": "query_past_debates",
        "description": "Retrieve past debate consensus for this user",
        "parameters": {
            "user_id": "string",
            "exercise_type": "string",
            "limit": "integer (default 5)"
        }
    },
    {
        "name": "query_similar_safety_flags",
        "description": "Find how similar safety flags were resolved across all users",
        "parameters": {
            "safety_flag_name": "string",
            "limit": "integer (default 10)"
        }
    }
]
```

**출력**:
```json
{
  "agent": "mediator",
  "consensus": "Continue training but reduce load by 10% this session. Knee valgus is real but moderate — focus on the cue both coaches agreed on.",
  "priority_actions": [
    {"order": 1, "action": "Reduce load by 10% for next 2 sessions", "rationale": "Scrutinizer's risk + your past lower back history"},
    {"order": 2, "action": "Cue 'push floor apart' on ascent", "rationale": "Encourager's tip, validated by 3 past debates with similar valgus"},
    {"order": 3, "action": "Re-film from front angle next session", "rationale": "Scrutinizer's measurement request"}
  ],
  "past_debate_references": [
    {"debate_id": "deb_042", "date": "2026-05-15", "outcome": "Same cue worked — 1° valgus reduction"}
  ],
  "disclaimer": "이 분석은 정보 제공용입니다. 의학 조언이 아닙니다. 통증·부상이 있으면 정형외과·물리치료사와 상담하세요.",
  "round_count_used": 2
}
```

---

## 3. 데이터 모델 (Firestore)

### 3.1 컬렉션 구조

```
formforge (DB root)
├── users/
│   └── {user_id}
│       ├── profile: { name, email, experience_level, injury_history[], created_at }
│       └── persona_state: {                          // self-improvement loop의 핵심
│             encourager: { warmth, detail },
│             scrutinizer: { harshness, detail },
│             last_updated_at, total_feedback_count
│           }
│
├── debates/
│   └── {debate_id}
│       ├── user_id: string
│       ├── video_uri: string
│       ├── exercise_type: string
│       ├── pose_data: {...}                          // PoseExtractor 출력
│       ├── status: "pending" | "debating" | "consensus" | "feedback_pending" | "done"
│       ├── created_at, updated_at
│       ├── rounds: [
│       │     { round: 1, encourager: {...}, scrutinizer: {...} },
│       │     { round: 2, ... }
│       │   ]
│       ├── consensus: {...}                          // Mediator 출력
│       └── trace_ids: { encourager: "...", scrutinizer: "...", mediator: "..." }
│
├── feedback/
│   └── {feedback_id}
│       ├── debate_id: string
│       ├── user_id: string
│       ├── encourager_rating: "too_warm" | "perfect" | "too_cold"
│       ├── scrutinizer_rating: "too_harsh" | "perfect" | "too_soft"
│       ├── mediator_rating: 1-5
│       ├── free_text: string (optional)
│       └── created_at
│
└── evals/                                            // LLM-as-a-Judge 결과
    └── {eval_id}
        ├── debate_id: string
        ├── debate_quality_score: 0-1
        ├── persona_adjustment_recommendation: {
              encourager: { warmth_delta: +0.1 },
              scrutinizer: { harshness_delta: -0.2 }
            }
        └── created_at
```

### 3.2 실시간 토론 UI를 위한 Firestore 폴링

Streamlit이 `debates/{debate_id}` 문서를 **1초마다 폴링** → `rounds` 배열 변경 감지 시 즉시 UI 업데이트. `streamlit-autorefresh` 컴포넌트 사용.

> ⚠️ **`on_snapshot()` 콜백 금지**: Firestore의 백그라운드 스레드 콜백은 Streamlit의 rerun 모델과 충돌. 폴링이 단순하면서 동일한 5초 wow를 달성.

```python
# storage/firestore_client.py 의 한 패턴
def get_debate_snapshot(debate_id: str) -> dict:
    """Streamlit에서 1초마다 호출. Firestore 문서 최신 상태 반환."""
    doc_ref = db.collection("debates").document(debate_id)
    return doc_ref.get().to_dict()

# ui/streamlit_app.py 에서:
# from streamlit_autorefresh import st_autorefresh
# st_autorefresh(interval=1000, key="debate_poll")  # 1초마다 자동 rerun
# debate = get_debate_snapshot(debate_id)
# render_rounds(debate["rounds"])
```

---

## 4. Vertex AI Vector Search 사용

### 4.1 인덱스 구성

- **인덱스 이름**: `formforge-debates-index`
- **차원**: 1408 (multimodalembedding-001 비디오/텍스트 통합 차원)
- **거리**: cosine
- **업데이트 방식**: streaming

### 4.2 임베딩 대상

다음을 임베딩으로 저장:
1. **debate consensus 텍스트** (Mediator 합의안) — "비슷한 합의 사례 검색"용
2. **safety flag 이름 + 컨텍스트** — "이 위험 신호가 과거에 어떻게 해결되었나" 검색용

### 4.3 검색 패턴 (Mediator가 사용)

```python
# storage/vector_search.py 의 한 패턴
def search_similar_debates(query_text: str, user_id: str = None, limit: int = 5) -> list:
    """
    Mediator agent가 호출.
    현재 토론 컨텍스트를 임베딩 → 유사한 과거 토론 합의 검색.
    user_id 필터로 본인 과거 우선, 없으면 글로벌.
    """
    pass
```

---

## 5. Phoenix MCP Introspection 패턴 (1등 결정 요소)

### 5.1 왜 중요한가

Arize 트랙 평가 기준 명시: *"quality of the agent's self-improvement loop"*.
일반 RAG는 "외부 문서 검색"이지만, **우리는 자기 자신의 trace를 도구로 사용**합니다. 이게 차별화.

### 5.2 구현 방식 — 커스텀 MCP wrapper

**파일 위치**: `mcp/phoenix_mcp_server.py` (FastMCP 기반 커스텀 서버)

> ⚠️ **중요**: `@arizeai/phoenix-mcp` 공식 패키지는 일반적인 trace/project 조회 도구만 제공. `query_past_debates`·`query_similar_safety_flags` 같은 도메인 특화 도구는 **본인이 만든 wrapper MCP server**가 노출. 내부적으로 Phoenix REST API + Firestore + Vector Search를 조합 호출.

1. **커스텀 MCP server 구현**: Python `mcp` SDK (FastMCP)로 thin wrapper 작성
   - Tool 1: `query_past_debates(user_id, exercise_type, limit=5)` → Phoenix REST API로 사용자 trace 검색 + Firestore consensus 데이터 join
   - Tool 2: `query_similar_safety_flags(safety_flag_name, limit=10)` → Vector Search + Phoenix trace 조합
2. **ADK에 MCP tool 등록**: ADK의 MCP integration으로 Mediator에 노출
3. **Mediator system prompt**에 도구 사용법 명시
4. **Gemini가 자동으로 도구 호출 결정**

### 5.3 배포 전략 (Dev vs Prod)

| 환경 | MCP server 실행 방식 | 비고 |
|---|---|---|
| **로컬 dev** | 같은 Python venv 안에서 subprocess (stdio transport) | Streamlit + MCP 한 프로세스에서 시작 |
| **Cloud Run prod** | **별도 Cloud Run 서비스**로 분리 배포 (HTTP transport) | 메인 앱이 환경변수 `MCP_SERVER_URL`로 접근 |
| **Fallback** | MCP 도달 불가 시 Firestore 직접 조회 + 경고 trace 로깅 | Live URL 안정성 확보 (P4 violation 회피용) |

### 5.4 검증 방법

- 사용자가 같은 운동을 3번째 업로드할 때 → Mediator의 응답에 `past_debate_references` 필드가 채워져 있어야 함
- Phoenix Cloud 대시보드에서 Mediator의 trace를 보면 → MCP tool call이 명시적으로 보여야 함
- Cloud Run logs에 MCP server 호출 latency 기록

---

## 6. Self-Improvement Loop 알고리즘 ⭐⭐ 1등 결정 요소

### 6.1 트리거

사용자가 토론 결과 화면에서 피드백 버튼 클릭 →
- Encourager: "너무 따뜻함(too_warm)" / "딱 좋음(perfect)" / "너무 차가움(too_cold)"
- Scrutinizer: "너무 가혹함(too_harsh)" / "딱 좋음(perfect)" / "너무 밋밋함(too_soft)"
- Mediator: 1-5 별점

> 📐 **양방향 학습**: 각 페르소나는 양쪽으로 이동 가능. "perfect"는 anchor (변화 없음). 단방향 누적으로 한쪽 끝에 박히는 문제 회피.

### 6.2 처리 흐름

```python
# evals/feedback_handler.py 의 의사 코드
async def process_feedback(debate_id, feedback):
    # 1. 피드백 저장
    save_to_firestore("feedback", feedback)
    
    # 2. LLM-as-a-Judge 호출 (background task)
    judge_result = await llm_judge(
        debate_trace=fetch_phoenix_trace(debate_id),
        user_feedback=feedback,
        current_persona_state=get_user_persona_state(user_id)
    )
    
    # 3. 페르소나 파라미터 조정
    new_persona_state = apply_adjustments(
        current=current_persona_state,
        delta=judge_result.persona_adjustment_recommendation,
        learning_rate=0.2   # 한 번에 너무 많이 바뀌지 않게
    )
    
    # 4. Firestore 업데이트
    update_user_persona_state(user_id, new_persona_state)
    
    # 5. Phoenix에 eval 결과 trace
    log_eval_to_phoenix(judge_result)
```

### 6.3 LLM-as-a-Judge prompt 템플릿

**파일 위치**: `evals/llm_judge.py`
**모델**: `gemini-3.5-flash` (stable) — Gemini 3 family를 시스템에 한 곳 명시적으로 채택하여 "최신 모델 활용" 시그널 확보

```
You are evaluating a workout form debate.

Inputs:
- Encourager's argument: {encourager_text}
- Scrutinizer's argument: {scrutinizer_text}
- Mediator's consensus: {mediator_text}
- User's feedback: {user_feedback_json}
- Current persona state: {persona_state_json}

Task:
1. Score debate quality 0.0-1.0 (multi-perspective coverage, evidence quality, actionability).
2. Decide if persona parameters need adjustment based on user feedback.

Adjustment rules (bidirectional, symmetric):
- Encourager:
  - "too_warm" → warmth -= 0.10
  - "too_cold" → warmth += 0.10
  - "perfect" → no change (anchor current state)
- Scrutinizer:
  - "too_harsh" → harshness -= 0.15
  - "too_soft" → harshness += 0.10
  - "perfect" → no change
- `detail` 파라미터도 동일 로직 (자유 텍스트 피드백에서 LLM-as-a-Judge가 자동 판단)
- Clamp all values to [0.0, 1.0]

Output JSON:
{
  "debate_quality_score": 0.0-1.0,
  "persona_adjustment_recommendation": {
    "encourager": {"warmth_delta": float, "detail_delta": float},
    "scrutinizer": {"harshness_delta": float, "detail_delta": float}
  },
  "reasoning": "한국어 한 문장으로 왜 이렇게 조정했는지"
}
```

### 6.4 검증 (데모 영상에서 보여줄 것)

- "1주차" 토론 → 사용자 "too harsh" 클릭 → 페르소나 state 업데이트
- "2주차" 같은 운동 → Scrutinizer가 명확히 더 부드러워진 응답 (직접 비교 시각화)
- Phoenix Cloud의 evals 대시보드에서 persona_state 변화 시계열 차트

---

## 7. 외부 API 호출 패턴 (요약)

### 7.1 Gemini 2.5 Pro (multi-modal)

```python
# Google ADK 안에서 호출 (직접 google.genai 안 씀 — ADK가 wrap)
from google.adk.agents import Agent

agent = Agent(
    name="encourager",
    model="gemini-2.5-pro",
    instruction=ENCOURAGER_PROMPT,
    output_schema=EncouragerOutput,   # Pydantic 모델
)
```

### 7.2 Phoenix 자동 계측 (모든 에이전트에 적용)

```python
# 앱 시작 시 한 번만
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

tracer_provider = register(
    project_name=os.getenv("PHOENIX_PROJECT_NAME"),
    endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT") + "/v1/traces",
    headers={"api_key": os.getenv("PHOENIX_API_KEY")},
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
```

### 7.3 Vertex AI 멀티모달 임베딩

```python
# storage/vector_search.py
from vertexai.vision_models import MultiModalEmbeddingModel

model = MultiModalEmbeddingModel.from_pretrained("multimodalembedding@001")
embedding = model.get_embeddings(
    video=video_path,
    contextual_text=consensus_text,
    dimension=1408,
)
```

---

## 8. 보안·면책 (반드시 구현)

### 8.1 의료 면책

모든 사용자 대면 결과에 다음을 표시:

```
⚠️ 본 분석은 정보 제공용입니다. 의학적 조언이 아닙니다.
   통증·부상·기존 질환이 있으면 정형외과·물리치료사·트레이너와 상담하세요.
   본 도구는 운동 자세에 대한 관찰 기록을 보조할 뿐, 진단 도구가 아닙니다.
```

### 8.2 영상 프라이버시

- 업로드 영상은 사용자별 폴더에 격리 (`gs://formforge-videos/{user_id}/...`)
- 인증된 사용자만 접근
- 데모 영상에서 본인 얼굴 노출 시 모자이크 권장

### 8.3 API 키 관리

- `.env` 파일은 절대 git commit 안 함 (`.gitignore`에 추가)
- 공개용 `.env.example`만 commit
- Cloud Run 배포 시 Secret Manager 사용

---

## 9. 데모 영상에서 시각화할 것 (3분, 1등 결정)

| 시간 | 무엇을 보여줄까 | 왜 |
|---|---|---|
| 0:00-0:05 | 업로드 → 두 코치 카드 좌우 등장 + A2A 라인 빛남 | **5초 wow** |
| 0:05-0:30 | Streamlit이 1초 폴링으로 Firestore의 두 코치 메시지를 라이브 표시 | Architecture 시각적 증명 |
| 0:30-0:50 | Mediator가 Phoenix MCP tool call → 과거 trace 가져오는 화면 | **MCP introspection 핵심** |
| 0:50-1:10 | Mediator 합의안 + 우선순위 액션 | Output quality |
| 1:10-1:40 | 사용자 "too harsh" 피드백 → 페르소나 state 업데이트 시각화 | **Self-improvement loop 증명** |
| 1:40-2:00 | "2주 후" 시뮬 — 같은 영상, 다른 톤 | 진짜 학습 증명 |
| 2:00-2:30 | Phoenix Cloud 대시보드 — trace, evals, persona_state 시계열 | Observability 깊이 |
| 2:30-2:50 | Tech stack 다이어그램 (ADK·A2A·Phoenix·MCP·Gemini·Firestore·Vertex AI) | 풀스택 증명 |
| 2:50-3:00 | GitHub URL + Live demo URL + 면책 | 마무리 |

---

## 10. 성공 정의 (Done Criteria)

이 모든 게 데모 영상에서 입증되면 1등 가능:

- [ ] 두 에이전트가 같은 영상을 다르게 분석하고 명시적으로 서로 반박/지지 (라운드 2 이상)
- [ ] Mediator가 Phoenix MCP를 호출해서 과거 trace를 가져오는 게 trace에 보임
- [ ] 사용자 피드백 한 번으로 다음 토론의 톤이 명확히 바뀜 (before/after 측정 가능)
- [ ] Phoenix Cloud 대시보드에서 모든 LLM call·도구 호출·eval이 시각화됨
- [ ] Multi-modal Gemini가 텍스트만이 아닌 비디오 직접 분석에 사용됨
- [ ] 호스팅된 URL에서 누구나 접속 가능 (Cloud Run)
- [ ] GitHub repo가 MIT 라이선스 + README + About 섹션 license 표시
- [ ] 3분 영상에 위 10가지 시각화 다 포함
