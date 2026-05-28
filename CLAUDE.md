# FormForge AI — Project Constitution

> 이 파일은 Claude Code가 매번 자동 참조하는 프로젝트 헌법입니다.
> 짧고 압축적으로 유지하세요. 디테일은 ARCHITECTURE.md, 작업 순서는 TASKS.md를 참조합니다.

---

## 0. 프로젝트 정체성

- **프로젝트명**: FormForge AI
- **부제 (영어 공식)**: *Adversarial Multi-Agent Workout Form Coach with Self-Improving Critique Loop*
- **해커톤**: Google Cloud Rapid Agent Hackathon — **Arize 트랙**
- **마감**: 2026-06-12 06:00 KST
- **개발자**: 1인 바이브 코더 (한국 거주)
- **목표**: Arize 트랙 1등 ($5,000)
- **저장소 라이선스**: MIT (Devpost 요구사항: GitHub About 섹션에 자동 표시)

## 1. 한 줄 핵심

> 두 AI 코치(격려파 vs 회의파)가 사용자의 운동 영상을 보고 **실시간으로 토론**합니다. 사용자 피드백으로 두 코치의 토론 패턴이 학습되어 시간이 지나면서 **사용자만의 critic**이 됩니다.

## 2. 차별화 (5가지 — 이 다섯 가지가 1등을 결정)

1. Single-agent form 분석 시장 vs **Adversarial Pair (Encourager vs Scrutinizer)**
2. 정적 일회성 응답 vs **두 에이전트 실시간 토론 → Mediator 합의**
3. 단순 prompt 튜닝 vs **Phoenix MCP로 trace 자체 introspection** (런타임)
4. Multi-modal 일회 호출 vs **Multi-modal × Multi-agent** (두 에이전트가 같은 영상을 다른 관점으로)
5. 일방향 피드백 vs **Self-improvement loop** (사용자 피드백 → LLM-as-a-Judge 평가 → 페르소나 진화)

## 3. 에이전트 페르소나 (절대 변경 금지)

| Agent | Persona | Tone | 핵심 역할 |
|---|---|---|---|
| **The Encourager** | 친절한 PT (10년 경력) | 따뜻·동기부여 | 좋은 점 발견·점진적 개선 제안 |
| **The Scrutinizer** | 까다로운 운동생리학자 (PhD) | 직설·근거 기반 | 부상 위험·생체역학 결함 가차없이 지적 |
| **The Mediator** | Head Coach (사용자 컨텍스트 보유) | 균형·통합 | 두 입장 합의 + 사용자 부상이력 반영 |
| **The PoseExtractor** | 백엔드 분석가 (페르소나 없음) | — | Gemini Vision으로 자세·각도·템포 JSON 추출 |

## 4. 기술 스택 (절대 변경 금지)

| Layer | Tech | 버전·노트 |
|---|---|---|
| Agent Runtime | **Google ADK** (Python) | hierarchical multi-agent + A2A 네이티브. **ADK = Google Cloud Agent Builder 생태계의 공식 open-source framework** (Devpost 추천 starter pack도 ADK 기반) |
| Models (primary) | **Gemini 2.5 Pro** (`gemini-2.5-pro`, multi-modal vision/audio/video) | for Encourager·Scrutinizer·Mediator·PoseExtractor Stage 2. Stable + video 입력 확정. |
| Models (fast) | **Gemini 2.5 Flash** (`gemini-2.5-flash`) | for PoseExtractor Stage 2 보조·간단 분류 작업 |
| Models (eval) | **Gemini 3.5 Flash** (`gemini-3.5-flash`) | for LLM-as-a-Judge. "최신 Gemini 3 family 활용" 시그널 — 심사 마케팅 점수용. Stable. |
| Pose Extraction | **MediaPipe Pose** | PoseExtractor Stage 1, 정량 키포인트·각도·tempo 정확 계산 |
| Observability | **Arize Phoenix Cloud** (free tier) | `https://app.phoenix.arize.com` |
| MCP | **커스텀 `mcp/phoenix_mcp_server.py`** (Python FastMCP) | Phoenix REST API + Firestore + Vector Search wrap, Mediator가 자체 trace 쿼리 |
| Auto-instrumentation | `openinference-instrumentation-google-adk` | 자동 trace 전송 |
| DB (primary) | **Firestore** | 1초 폴링(`streamlit-autorefresh`)으로 토론 UI 업데이트. `on_snapshot()` 콜백 금지 |
| Vector Search | **Vertex AI Vector Search** | 영상 임베딩 검색 |
| Embedding | **`multimodalembedding-001`** (Vertex AI) | 비디오·텍스트 통합 임베딩 |
| Frontend | **Streamlit** | 1인 데모 최단 경로 |
| Deploy | **Cloud Run** | serverless, free tier. **Cloud Run = Agent Builder 권장 deploy target** (ADK 공식 deploy 옵션 중 하나) |
| Storage | **Cloud Storage** | 업로드 영상 |

> ⚠️ MongoDB·Postgres·Redis·LangChain·CrewAI·다른 클라우드 사용 금지. 이 스택이 Arize 트랙 + Google 심사위원 호감을 동시 충족하는 유일 조합.
> ⚠️ **공식 룰 충족 wording 필수** (Devpost 룰 §2): "Build a functional agent—powered by Gemini and Google Cloud Agent Builder". README와 DEVPOST 제출란에 반드시 "Built with Google ADK (the official open-source framework of Google Cloud Agent Builder) and deployed on Cloud Run (an Agent Builder-supported runtime), powered by Gemini 2.5 Pro / Flash and Gemini 3.5 Flash." 형태로 명시.
> 📐 **PoseExtractor는 2-stage**: MediaPipe(정량 측정) → Gemini(해석·판단). LLM이 직접 각도 측정하지 않음 (거짓 정밀 방지).
> 📐 **Streamlit UI는 폴링 방식**: `streamlit-autorefresh`로 1초 폴링. Firestore `on_snapshot()` 콜백 사용 금지 (rerun 모델과 충돌).
> 📐 **Phoenix MCP는 커스텀 wrapper**: `mcp/phoenix_mcp_server.py`가 Phoenix REST API + Firestore + Vector Search를 wrap. 별도 Cloud Run 서비스로 배포.

## 5. 사용자(개발자) 작업 4대 규칙

Claude Code가 이 사용자와 작업할 때 반드시 지킬 4가지:

1. **완성형 코드 우선**: "나머지는 동일" 금지. 매번 전체 파일 제공.
2. **정확한 파일 위치**: 코드 블록 상단에 절대 경로 명시 (예: `# 파일 위치: agents/encourager.py`).
3. **쉬운 디버깅**: 에러 시 초보자도 이해할 비유 + 즉시 적용 가능한 수정 코드.
4. **소크라테스 모드**: 요구사항이 모호하거나 더 효율적인 방식이 있으면 코드 짜기 전에 역질문.

## 6. 절대 원칙 (위반 시 작업 중단)

이 5가지 중 하나라도 빠지면 1등 못 합니다:

- [P1] **Phoenix 자동 계측이 모든 에이전트에 활성화**되어야 함
- [P2] **Encourager와 Scrutinizer는 반드시 서로 통신**해야 함 (단일 응답 금지)
- [P3] **사용자 피드백이 다음 토론 페르소나에 반영**되어야 함 (self-improvement loop 증명)
- [P4] **Mediator는 반드시 Phoenix MCP를 통해 과거 trace를 쿼리**해야 함 (introspection)
- [P5] **의료/부상 면책 표시 필수**: 모든 결과에 "정보 제공용. 의학 조언 아님. 부상·통증 시 전문가 상담." 명시

## 7. 디렉토리 구조 (변경 금지)

```
formforge-ai/
├── CLAUDE.md                  # 이 파일 (헌법)
├── ARCHITECTURE.md            # 시스템 설계 상세
├── TASKS.md                   # Day 1~15 작업 체크리스트
├── README.md                  # 영어, 데모 URL, 영상 링크, 설치 가이드
├── LICENSE                    # MIT
├── .env.example               # 비밀 키 제외 템플릿
├── .gitignore
├── requirements.txt
│
├── agents/
│   ├── __init__.py
│   ├── pose_extractor.py      # Gemini Vision으로 자세 JSON 추출
│   ├── encourager.py          # The Encourager (격려파)
│   ├── scrutinizer.py         # The Scrutinizer (회의파)
│   ├── mediator.py            # The Mediator (Phoenix MCP introspection 포함)
│   └── orchestrator.py        # ADK로 4 에이전트 조율
│
├── mcp/
│   ├── __init__.py
│   └── phoenix_mcp_server.py  # 커스텀 MCP server (FastMCP) — query_past_debates, query_similar_safety_flags 노출
│
├── evals/
│   ├── __init__.py
│   ├── llm_judge.py           # LLM-as-a-Judge (토론 품질 평가)
│   └── feedback_handler.py    # 사용자 피드백 → 페르소나 조정
│
├── storage/
│   ├── __init__.py
│   ├── firestore_client.py    # Firestore CRUD
│   └── vector_search.py       # Vertex AI Vector Search
│
├── ui/
│   ├── streamlit_app.py       # 메인 UI
│   ├── components/
│   │   ├── debate_view.py     # 두 에이전트 토론 라이브 뷰
│   │   ├── trace_view.py      # Phoenix trace 시각화
│   │   └── feedback_form.py   # 피드백 입력
│   └── styles.css
│
├── data/
│   └── sample_videos/         # 테스트용 운동 영상 (스쿼트, 데드리프트, 푸시업)
│
├── deploy/
│   ├── Dockerfile             # Cloud Run 배포
│   └── cloudbuild.yaml
│
├── tests/
│   ├── test_agents.py
│   └── test_orchestrator.py
│
└── docs/
    ├── DEMO_STORYBOARD.md     # 3분 영상 시나리오
    └── DEVPOST_SUBMISSION.md  # 제출 양식 초안
```

## 8. 환경 변수 (`.env`)

```bash
# Google Cloud
GOOGLE_CLOUD_PROJECT=         # 예: formforge-prod
GOOGLE_APPLICATION_CREDENTIALS=./service-account.json
GEMINI_API_KEY=               # AI Studio에서 발급

# Vertex AI
VERTEX_AI_LOCATION=us-central1
VECTOR_SEARCH_INDEX_ID=
VECTOR_SEARCH_ENDPOINT_ID=

# Arize Phoenix
PHOENIX_API_KEY=              # https://app.phoenix.arize.com 에서 발급
PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com
PHOENIX_PROJECT_NAME=formforge-prod

# Firestore
FIRESTORE_DATABASE=(default)

# App
APP_ENV=development           # development | production
MAX_DEBATE_ROUNDS=3
```

## 9. 외부 참고 링크 (코드 작성 시 의존)

- ADK 문서: https://google.github.io/adk-docs
- Phoenix Cloud: https://app.phoenix.arize.com
- Phoenix MCP: https://github.com/Arize-ai/phoenix-mcp
- Arize Gemini Hackathon Example: https://github.com/Arize-ai/gemini-hackathon
- Gemini API (multi-modal): https://ai.google.dev/gemini-api/docs/vision
- Vertex AI Vector Search: https://cloud.google.com/vertex-ai/docs/vector-search
- Firestore Python: https://firebase.google.com/docs/firestore/quickstart#python
- Streamlit: https://docs.streamlit.io
- 해커톤 Devpost: https://rapid-agent.devpost.com

## 10. 평가 기준 매핑 (이 사양 → 심사 점수)

| 심사 기준 | 우리 구현 |
|---|---|
| **Technological Implementation** | ADK multi-agent + A2A + Phoenix MCP introspection + 자동 계측 |
| **Design** | Streamlit 두 코치 토론 라이브 시각화 + trace 차트 + 피드백 UI |
| **Potential Impact** | 글로벌 홈피트니스 + 부상 예방 + 1인 트레이너 한계 극복 + Reference architecture로 일반화 가능 |
| **Quality of the Idea** | Adversarial Pair + Self-improvement loop + Multi-modal × Multi-agent (이 조합은 검색에서 발견된 사례 없음) |

## 11. Claude Code 사용 팁

이 사용자에게 작업할 때:

- 매 응답 시작에 **현재 어느 Day·어느 Task를 진행 중인지** 명확히 (예: "TASKS.md Day 3, Task 3.2 진행")
- 새 파일 생성 시 **항상 절대 경로** 명시
- 에러 메시지를 받으면 **에러 원인을 비유로 설명** → 수정 코드
- 모호한 요구사항에서는 **2-3 선택지를 만들고 사용자에게 물어보기** (소크라테스 모드)
- Phoenix Cloud 대시보드 URL을 자주 언급해서 사용자가 trace 확인하도록 유도

---

**Last updated**: 2026-05-28 (대회 룰 재검증 — Agent Builder positioning 명시, judge 모델 `gemini-3.5-flash`로 교체, README/DEVPOST wording 의무화)
**Next update**: 사용자가 Day 7 (multi-modal core) 완료 후 점검
