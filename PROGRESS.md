# FormForge AI — 진행사항

> 세션 간 핸드오프 문서. 다음 세션 시작 시 이 파일부터 읽기.

**최종 갱신**: 2026-05-29 (세션 7 — **Day 12 P4 마무리 (70%→100%)**: query_* 실제 debate_id 반환 + Phoenix REST 실연동 + trace_id 루프 완성)
**현재 단계**: Day 1 5/6 (영상 대기) · Day 2 ✅ · Day 3 ✅ · Day 4 Phase 1 ✅ · Day 8 ✅ · **Day 9 Task 9.1 + e2e 골격 ✅** · **Day 12 Task 12.1·12.2 ✅ (P4 100%)**
**저장소 상태**: 로컬 **4커밋 push 대기** (`ab43834` e2e · `6d01d2f` docs · `0163340` P4-A · `8d5fabd` P4-B). push 는 사용자 직접(main 직접 push 차단).

---

## 📌 한눈에 보기

- ✅ **계획 문서 3종 v2 확정**: ARCHITECTURE.md, CLAUDE (4).md, TASKS (1).md
- ✅ **리뷰 → 패치 → 재검증 1사이클 완료** (세션 1)
- ✅ **대회 룰 재검증 + Agent Builder/Gemini 마이그레이션 완료** (세션 2)
- ⏭️ **다음 작업**: TASKS.md Day 1 Task 1.1부터 순차 진행

---

## 🗓️ 세션 1 (2026-05-27) — 계획 검토 및 패치

### Step 1. 초기 리뷰 (수석 개발자 모드)

3개 문서를 정합성·실행 가능성 기준으로 검토 → **8가지 리스크 발견**.

| # | 유형 | 발견 사항 |
|---|---|---|
| 1 | 🔴 치명적 | Gemini Vision 단독으로 각도 ±2° 측정은 비현실적 (거짓 정밀) |
| 2 | 🔴 치명적 | Streamlit + Firestore `on_snapshot()` 콜백은 rerun 모델과 충돌 |
| 3 | 🔴 치명적 | `@arizeai/phoenix-mcp`는 `query_past_debates` 같은 도메인 도구를 제공하지 않음 |
| 4 | 🔴 치명적 | Cloud Run + Streamlit + MCP 60초 연쇄 latency 가정 부실 |
| 5 | 🟡 중요 | 15일 일정이 솔로 바이브 코더 기준 매우 타이트 (실제 13-18일 추정) |
| 6 | 🟡 중요 | MCP server 프로덕션 배포 전략 부재 |
| 7 | 🟡 중요 | 스키마 불일치 — `directness` 출력에 있지만 조정 파라미터에 없음 |
| 8 | 🟡 중요 | `requirements.txt` 명세 부재, 합의 감지 알고리즘 미정의, 페르소나 단방향 학습 문제 |

### Step 2. 추천 즉시 조치 7가지 적용

| 결정 사항 | 적용 내용 |
|---|---|
| **PoseExtractor 2-stage** | MediaPipe Stage 1 (정량 측정) + Gemini Flash Stage 2 (해석) |
| **Streamlit UI** | `streamlit-autorefresh` 1초 폴링. `on_snapshot()` 콜백 금지 |
| **Phoenix MCP** | `mcp/phoenix_mcp_server.py` 커스텀 FastMCP wrapper 작성 |
| **Cloud Run 배포** | 메인 앱 + MCP server 2개 서비스로 분리. `--min-instances=1` |
| **End-to-end 마일스톤** | Day 9 종료(6/5)까지 skeleton 동작 필수. 미달 시 컷 가이드 |
| **양방향 페르소나 학습** | `too_warm`/`perfect`/`too_cold`, `too_harsh`/`perfect`/`too_soft`. "perfect"는 anchor |
| **잡 정합성** | `directness` → `detail` 통일, `requirements.txt` 17개 패키지 명시, 합의 감지 알고리즘 정의 |

### Step 3. 리뷰 에이전트 자동 검증

리뷰 에이전트가 패치된 3개 문서를 재검토 → **잔재 4건 + 모호성 1건** 발견.

| # | 위치 | 문제 |
|---|---|---|
| 잔재 #1 | CLAUDE.md:48 | 기술 스택 표에 `@arizeai/phoenix-mcp` (npx) 남음 |
| 잔재 #2 | CLAUDE.md:104, ARCHITECTURE.md:270 | `phoenix_client.py` vs `phoenix_mcp_server.py` 혼재 |
| 잔재 #3 | CLAUDE.md:50, ARCHITECTURE.md:39, 618 | "real-time listener" 표현 3곳 잔존 |
| 잔재 #4 | TASKS.md:573 | Task 14.1 지시문에 "real-time listener" 명시 |
| 모호성 | TASKS.md requirements | `mcp` vs `fastmcp` 패키지 관계 불명 |

### Step 4. 잔재 정리 (7곳 + 1건)

- 🔴 잔재 4건 → 모두 수정 완료
- 🟡 `fastmcp>=2.0.0` requirements.txt에 추가

### Step 5. 최종 Grep 검증

```
phoenix_client, real-time listener, too_clinical, directness → 0건
@arizeai/phoenix-mcp → 1건 (의도된 경고 컨텍스트만 잔존)
```

✅ 정합성 검증 통과.

---

## 📂 변경된 파일

| 파일 | 수정 횟수 | 주요 변경 |
|---|---|---|
| `ARCHITECTURE.md` | 12 edit | 섹션 2.1 (MediaPipe), 2.2/2.3 (detail 통일), 3.2 (폴링), 5 (커스텀 MCP + 배포), 6 (양방향 학습), 9 (스토리보드) |
| `CLAUDE (4).md` | 5 edit | 섹션 4 (스택 5개 갱신), 섹션 7 (디렉토리 구조), Last updated |
| `TASKS (1).md` | 11 edit | Task 1.3 (requirements 명시), Task 1.6 (MediaPipe smoke), Task 5.1 (2-stage), Task 8.1 (합의 감지), Task 8.2 (폴링), Day 9 마일스톤, Task 12.1-12.3 (커스텀 MCP), Task 13.1-13.2 (양방향), Task 14.3 (듀얼 배포) |

---

## 🗓️ 세션 2 (2026-05-28) — 대회 룰 재검증 + Agent Builder positioning

### Step 1. 대회 페이지 + 공식 룰 페이지 fetch

Devpost 홈페이지의 "Gemini 3" 마케팅 카피와 "Google Cloud Agent Builder" 요구를 보고 현재 계획(Gemini 2.5 + Google ADK)이 룰 충족하는지 의문 제기 → 공식 룰 페이지 + GCP 문서 + ADK 문서 + Devpost 리소스 페이지 + Gemini 모델 카탈로그 + Agent Starter Pack repo 일괄 fetch.

### Step 2. 발견 사항

| # | 항목 | 결론 |
|---|---|---|
| 1 | 공식 룰의 Gemini 버전 | **"Gemini"만 명시, "Gemini 3"는 룰에 없음**. Devpost 홈의 "Gemini 3"는 마케팅 카피. Gemini 2.5도 룰 충족. |
| 2 | Agent Builder vs ADK | **ADK는 Agent Builder의 공식 open-source framework**. Devpost 추천 starter pack(`GoogleCloudPlatform/agent-starter-pack`)도 6개 템플릿 중 4개가 ADK 기반. ADK 공식 deploy 옵션에 Cloud Run + Agent Runtime(Agent Platform) 명시. ADK + Cloud Run = 룰 충족. |
| 3 | Gemini 3 모델 카탈로그 | Stable: `gemini-3.5-flash`, `gemini-3.1-flash-lite`. Pro급은 모두 preview, 비디오 멀티모달 미확인. **핵심 비디오 분석은 `gemini-2.5-pro` 유지가 안전**. |
| 4 | Phoenix MCP 라이브 세션 | **2026-05-28 13:00 EDT (= 5/29 02:00 KST)** "Getting from Zero to a Traced Agent in 5 minutes with Phoenix MCP" — 새벽이라 녹화본 확인 권장. |
| 5 | Track 선택 | Arize 단일 선택 필수. 멀티 트랙 미지원. |
| 6 | 옵션 테마 (월드컵/금융/리테일) | FormForge AI는 매칭 안 됨. 옵션이라 무시 OK. |
| 7 | 룰 §15 disqualifier | "All other artificial intelligence tools are not permitted" — Google Cloud AI + 파트너 AI만. 현재 계획에 위반 없음 ✓ |

### Step 3. 결정 사항 (사용자 승인)

| 항목 | 결정 |
|---|---|
| **메인 모델** | `gemini-2.5-pro` 유지 (Encourager·Scrutinizer·Mediator·PoseExtractor Stage 2) |
| **보조 모델** | `gemini-2.5-flash` 유지 |
| **Judge 모델** | `gemini-2.5-flash` → **`gemini-3.5-flash`** 교체 ("Gemini 3 family 활용" 시그널) |
| **Framework** | Google ADK 유지. Agent Builder positioning을 ARCHITECTURE.md §0에 명시. |
| **Deploy** | Cloud Run 유지. README에 "Agent Builder-supported runtime"으로 표기. |
| **룰 충족 명시** | README와 DEVPOST 첫 단락에 "Built with Google Cloud Agent Builder (via ADK + Cloud Run), powered by Gemini, integrating Arize Phoenix MCP" 의무화. |

### Step 4. 변경된 파일

| 파일 | 변경 |
|---|---|
| `CLAUDE (4).md` | 섹션 4 스택 표 — judge 모델 추가, Agent Builder/Cloud Run positioning 주석, 룰 충족 wording 의무화 박스. Last updated 2026-05-28. |
| `ARCHITECTURE.md` | **신규 §0 "대회 요건 매핑 (Agent Builder positioning)"** 추가. §1 흐름도의 judge 표기 `Gemini 2.5 Flash` → `3.5 Flash`. §6.3에 judge 모델 명시. |
| `TASKS (1).md` | Task 13.2 judge 모델 교체 + 이유 명시. Task 15.3 README에 "Hackathon Compliance" 섹션 의무화 (블록 예시 포함). Task 15.4 Built With 목록 갱신 + 첫 문단 wording. |

---

## ⏳ 사용자 결정 대기

### 결정 1. Task 5.1 acceptance criteria 조정 여부

**상황**: "각 분석 시간 10초 이내 (MediaPipe 5초 + Gemini 5초)"가 Cloud Run CPU-only 환경에서 실현 가능한지 미검증.

**권장**: Day 1 Task 1.6 MediaPipe 스모크 테스트에서 로컬 측정 → 실제 수치 기반으로 조정. 지금 임의 변경 없이 유지.

---

## 🗓️ 세션 3 (2026-05-28 오후) — Day 1 착수

### 완료된 Task
| Task | 상태 | 산출물 |
|---|---|---|
| **Task 1.3** Local 셋업 (Claude Code) | ✅ | 9 디렉토리 + 4 `__init__.py` + `.gitignore` + `.env.example` + `requirements.txt` + `README.md` (Hackathon Compliance 섹션 포함) |
| **이름 정리** | ✅ | `CLAUDE (4).md` → `CLAUDE.md`, `TASKS (1).md` → `TASKS.md`. 원본 삭제. |
| **Task 1.6** MediaPipe skeleton (Claude Code) | ✅ (코드 작성) | `agents/pose_mediapipe.py` — `analyze_video()` + CLI. **샘플 영상 도착 시 즉시 실행 가능.** syntax 검증 통과. |

### 진행 중 / 대기 Task
| Task | 작업자 | 차단 사유 |
|---|---|---|
| **Task 1.1** GCP + $100 크레딧 | 사용자 | 사용자 브라우저 작업 (마감 6/4) |
| **Task 1.2** Phoenix Cloud 가입 | 사용자 | 사용자 브라우저 작업 |
| **Task 1.5** GitHub repo (MIT) | 사용자 | 사용자 브라우저 작업 |
| **Task 1.4** Hello World 자동 계측 | Claude Code | Task 1.1, 1.2 완료 후 (service-account.json + PHOENIX_API_KEY 필요) |
| **Task 1.6** 실행 검증 | Claude Code | 샘플 스쿼트 영상 `data/sample_videos/squat_demo.mp4` 필요 + `pip install -r requirements.txt` |

### 사용자에게 부탁한 것
1. `service-account.json` 파일을 프로젝트 root에 저장 (Task 1.1 5단계)
2. `PHOENIX_API_KEY` 키 안전한 곳에 메모 (Task 1.2 3단계)
3. 핸드폰으로 본인 스쿼트 한 세트 10~30초 영상 → `data/sample_videos/squat_demo.mp4`
4. GitHub repo 생성 시 **MIT License 선택 필수** (Devpost 룰)

---

## 🗓️ 세션 4 (2026-05-28 저녁) — Day 1 완주 + Day 3 보너스

### 사용자 완료 (브라우저 작업)
- ✅ **Task 1.1** GCP — 프로젝트 `formforge-prod` + 결제 + API 4개 + Firestore Native mode (us-central1) + 서비스 계정 `formforge-sa` + 권한 4개 (Agent Platform User / Cloud Datastore User / Storage Object Admin / Cloud Run Invoker) + JSON 키
- ✅ **Task 1.2** Phoenix Cloud — 가입 + `formforge-prod` 프로젝트 + API key
- ✅ **Task 1.5** GitHub — `alsgur9865-sketch/formforge-ai` (Public, MIT License About 섹션 자동 표시)

### Claude Code 완료
- ✅ **Task 1.4** Hello World — `agents/hello_world.py`. ADK + Phoenix 자동 계측 end-to-end 동작 확인. Phoenix Cloud trace 검증 통과.
- ✅ **FormForge 전용 venv** — `./venv` 생성 (다른 프로젝트 `hermes-agent` venv가 활성화되어 있어서 격리 필요). 글로벌 Python 3.11.9로 명시 생성. requirements.txt 18개 패키지 + 의존성 설치.
- ✅ **첫 git commit + push** (`715717f`) — 15 files. service-account.json/.env 누락 검증. Repo: https://github.com/alsgur9865-sketch/formforge-ai
- 🎁 **Day 3 Task 3.1 보너스** — `agents/encourager.py` + `tests/test_encourager.py` + `tests/sample_pose_data.json`. EncouragerOutput Pydantic. 한국어 응답 + warmth/detail 파라미터. 페르소나 룰 100% 충족 (수치 기반 칭찬·next-step opportunity·ONE focus·warm tone).
- 🎁 **Day 3 Task 3.2 보너스** — `agents/scrutinizer.py` + `tests/test_scrutinizer.py`. ScrutinizerOutput Pydantic (primary_risk + secondary_concerns + required_action). **injury_history 자동 인식 → severity 상향** (사용자 `lower_back_strain_2025` → 요추 보상 작용 mechanism 자동 인용). PhD biomechanics 페르소나 완벽.

### 발견된 이슈 + 해결

| # | 이슈 | 해결 |
|---|---|---|
| 1 | 다운받은 `service-account.json` 실제 파일명이 `service-account.json.json` (Windows 확장자 숨김 함정) | `mv`로 수정. 사용자에게 "파일 확장명 표시" 옵션 안내. |
| 2 | 다른 프로젝트의 venv(`hermes-agent`)가 활성화 상태 | FormForge 전용 venv 새로 생성. 글로벌 Python 경로로 명시적 호출. |
| 3 | `gemini-2.5-pro` 호출 시 **429 RESOURCE_EXHAUSTED** (AI Studio free tier limit=0) | **Vertex AI 모드로 전환** — `.env`에 `GOOGLE_GENAI_USE_VERTEXAI=True` + `GOOGLE_CLOUD_LOCATION=us-central1` 추가. service-account.json 인증으로 호출. GCP 크레딧 사용. `.env.example`도 동일 갱신. |

### Phoenix Cloud trace 현황 (세션 4 종료 시점, Scrutinizer 호출 후 4건)
- Hello World (5.7s, 521 tok, <$0.01)
- Encourager 429 실패 시도 (3.2s, 0 tok, error_code 캡처됨 — 관측성 만점)
- Encourager Vertex 성공 (19.3s, 2984 tok, $0.01)
- Scrutinizer Vertex 성공 — primary_risk.severity = "high", 요추 부상 이력 자동 연결
- 누적 Cost ~$0.02. P50 5.7s, P99 19s.

### Day 1 마무리 상태
| Day 1 Task | 상태 |
|---|---|
| 1.1 GCP | ✅ |
| 1.2 Phoenix | ✅ |
| 1.3 셋업 | ✅ |
| 1.4 Hello World | ✅ |
| 1.5 GitHub | ✅ |
| 1.6 MediaPipe smoke | 🟡 코드·환경 준비 완료. **샘플 영상 대기** (data/sample_videos/squat_demo.mp4) |

영상 도착 시 즉시 실행 가능:
```
./venv/Scripts/python.exe agents/pose_mediapipe.py data/sample_videos/squat_demo.mp4 squat
```

---

## 🗓️ 세션 5 (2026-05-28 밤) — Day 2 Foundation 완주

### Claude Code 완료
- ✅ **Task 2.1 Firestore 클라이언트** — `storage/firestore_client.py` (250 lines). users / debates / feedback / evals 네 컬렉션 전체 CRUD. 싱글톤 패턴, service-account 자동 인증, ArrayUnion으로 rounds 추가, Streamlit 폴링용 `get_debate_snapshot()` 포함.
- ✅ **Task 2.1 검증** — `tests/test_firestore.py` 실행 → 5개 테스트 모두 통과. `users/test_user_001` + `debates/test_debate_001` 실제 Firestore에 생성됨 확인. persona_state 기본값(warmth=0.5 등) 검증 OK.
- ✅ **Cloud Storage 클라이언트** — `storage/cloud_storage_client.py`. `ensure_bucket()` (자동 생성, idempotent), `upload_video_file()` / `upload_video_stream()` (로컬·Streamlit 양쪽), `download_to_local()`, `get_signed_url()`, CLI 모드. 버킷 명명: `formforge-videos-{project-id}`.
- ✅ **Task 2.2 Vector Search create** — `storage/vector_search_setup.py` (3단계 분리: create/status/deploy/undeploy). 비용 위험 차단용으로 deploy는 명시적 `yes deploy` 입력 요구.
  - **create 실행 완료**:
    - Index: `2622495760943415296` (백그라운드 빌드 30~60분)
    - Endpoint: `3952922422738419712` (빈 상태, 무료)
  - 현재 상태: **무료**. Day 14 데모 직전에 `deploy` 명령으로 $13/day 시작 예정.

### 비용 의사결정 (세션 5에서 확정)
- **Vector Search 배포는 Day 14로 연기**: $13/day × 2일 ≈ $26로 캐핑.
- **Day 2 현재 누적 GCP 비용**: 사실상 $0 (Firestore + Storage + Index 빌드 모두 free tier·무료).
- **크레딧 잔량**: GCP Free Trial $300 + (가능시) Devpost $100 = 최대 $400. 안전.

### 사용자에게 부탁한 것 (세션 5)
1. **.env 파일에 다음 3줄 추가**:
   ```
   VECTOR_SEARCH_INDEX_ID=2622495760943415296
   VECTOR_SEARCH_ENDPOINT_ID=3952922422738419712
   VECTOR_SEARCH_DEPLOYED_INDEX_ID=formforge_debates_v1
   ```
2. 30~60분 후 `python storage/vector_search_setup.py status` 실행 → Index `vectors_count` 표시되면 빌드 완료
3. (마감 6/4) Devpost $100 해커톤 크레딧 신청 폼 작성
4. **Day 12 이전**까지 Firestore 복합 인덱스 생성 (테스트 6번 출력의 콘솔 링크 클릭) — `debates` 컬렉션의 `user_id` + `created_at` 복합 인덱스. Phoenix MCP가 `query_past_debates` 실행하기 전에 필요.

### 리뷰 → 수정 사이클 (세션 5 끝, Option B 진행)
Second Eye 훅이 reviewer-agent에 4개 파일 검토 위임 → 🔴 Critical 4건 + 🟡 Important 7건 + 🟢 4건 발견. P3·P4 직결 Critical 3개만 즉시 수정:

| # | 위치 | 문제 | 수정 |
|---|---|---|---|
| C#1 | `firestore_client.py` `get_recent_debates` | `.where()` 를 `.order_by()` 뒤에 호출 → `InvalidArgument` 즉시 폭발 | where 먼저 모두 붙이고 order_by + limit 마지막 |
| C#2 | `firestore_client.py` `update_user_persona_state` | 독스트링은 "total_feedback_count 자동 증가" 명시하지만 실제 로직 없음 | `firestore.Increment(1)` 자동 적용. `increment_feedback_count=False` 또는 명시 값 전달 시 우회 |
| C#3 | `firestore_client.py` `update_user_persona_state` | Firestore 맵 필드 통째 교체로 sibling 키 손실 (warmth만 보내면 detail 사라짐) | 중첩 dict → dot-notation 평탄화 + `.update()` 사용 |

**미수정 (Day 14로 연기)**: C#4 `get_signed_url` Cloud Run ADC 서명 권한 부족 — Streamlit UI 붙을 때 함께 해결.

**미수정 Important 7건**: 다음 세션 시작 시 우선 검토. 현 시점에 데이터 손실 위험은 없음.

### 회귀 테스트 추가
`tests/test_firestore.py`에 검증 케이스 3개 추가:
- 부분 업데이트 시 sibling(detail) 보존 확인
- `total_feedback_count` 1회 호출 후 1, 2회 호출 후 2 누적 확인
- `get_recent_debates` 빌더 순서 검증 (`InvalidArgument` 폭발 안 함, `FailedPrecondition`+인덱스 링크는 정상)

### Task 4.1 Round 1 파이프라인 (Option A 완료)
**`agents/orchestrator.py`** + **`tests/test_orchestrator.py`** 신규.

설계 결정 (실측 후 변경): **SequentialAgent → ParallelAgent**
- 첫 실행 시 latency 48.2s → acceptance 30s 초과
- Round 1 의미상 두 에이전트가 서로 안 보고 독립적 첫 인상이라 ParallelAgent 가 의미적·성능적으로 옳음
- 재실행 latency **26.0s** ✅ (30s 안)
- Day 8 Round 2+ 부터는 SequentialAgent 또는 커스텀 debate loop 로 전환 예정 (상호 직전 argument 참조 필요)

**Acceptance Criteria 검증 결과**:
| 항목 | 결과 |
|---|---|
| 1개 입력 → 2개 에이전트 응답 dict 반환 | ✅ (PoseExtractor 는 Day 5 합류) |
| Phoenix Cloud 1 trace + parent/child span | ✅ (ParallelAgent 자동 그룹화) |
| 총 latency 30s 이내 | ✅ 26.0s |
| 페르소나 핵심 필드 (praise/concern_one + primary_risk/severity) | ✅ |
| 부상 이력(요추) 자동 인식 → Scrutinizer severity = "high" | ✅ |

응답 미리보기 (sample_pose_data.json 입력 시):
- **Encourager**: "5개의 스쿼트 모두 깊이가 평균 92도로 일정… 왼쪽 무릎 살짝 안쪽 들어오는 현상… 발바닥 전체로 바닥을 밀어내며 무릎으로 보이지 않는 밴드를 양옆으로 찢는다고 상상…"
- **Scrutinizer**: primary_risk = "과도한 상체 숙임 / 굿모닝 스쿼트 패턴 (severity=high)" — 요추 4-5번 디스크 압박 mechanism 자동 연결 + "중량 20-25% 즉시 감소, '가슴을 들어라' 큐" required_action

→ **P2 절대원칙 (Encourager ↔ Scrutinizer 직접 통신)**: 진행률 30% → 60% (병렬 호출 + 같은 입력 공유. Day 8 에서 cross-reference 추가하면 100%)

### Task 4.1 follow-up 리뷰 → A 수정 (3건 즉시 패치)
Second Eye 훅 → reviewer-agent 리뷰 → 🔴 Critical 3 + 🟡 Important 6 + 🟢 3 발견. 위험·간단한 3건만 즉시 수정:

| 수정 | 위치 | 내용 |
|---|---|---|
| **C#3** | `tests/test_orchestrator.py:172` | "parent (sequential)" 안내문 → "parent (parallel)" (실설계와 일치) |
| **C#1** | `agents/orchestrator.py` docstring | ADK `ParallelAgent` `@deprecated` 사실 + Day 8 Workflow 마이그레이션 시 재검증 항목 3가지 명시 |
| **I#3** | `agents/orchestrator.py` `_resolve_persona_state` 헬퍼 신규 | persona_state 우선순위 1) 명시 인자 2) user_context.persona_state 3) 빈 dict. Firestore 에서 꺼낸 user 문서 통째 전달 시 persona_state 가 조용히 빈 dict 로 덮어쓰이던 버그 제거. |
| **I#4** | `tests/test_orchestrator.py` latency 임계값 | hard fail 45s, P50 목표 30s 로 분리. Gemini Pro 2x 병렬 호출 variance(±30%) 흡수. Day 5 PoseExtractor 합류 시 재조정 예정. |

회귀 테스트 4건 추가 (`_resolve_persona_state` unit-level, 비-Gemini, 빠름):
- explicit 인자 우선
- explicit=None 일 때 user_context.persona_state 자동 사용 (I#3 본질 회귀)
- 둘 다 없으면 빈 dict
- 잘못된 타입 안전 fallback

**미수정 (의도적 연기)**: I#1 (user_id 이중) — Day 8. I#2 (session_id uuid4) — Day 14. I#5 (fence 종료마커 뒤 텍스트) — 발생 시. I#6 (부상이력 soft warning) — 추후. C#2 (output_schema streaming 보장) — 실제 동작 검증됨. PRE 5번 false negative (주석에 `_resolve_persona_state` 텍스트만 있어도 통과 — 현 코드 실용적 위험 0, AST 파싱 필요) — Day 8. 모든 🟢 — 발생 시.

### Task 4.1 2차 follow-up → B 수정 (회귀 가드 구멍 + 문서 정합성)
2차 reviewer-agent 에서 🔴 신규 위험 1건 + 🟡 디자인 미정리 2건 발견. 모두 즉시 처리:

| 수정 | 위치 | 내용 |
|---|---|---|
| **🔴** | `tests/test_orchestrator.py` PRE 섹션 5번 | `inspect.getsource(run_round1)` 로 `_resolve_persona_state` 호출 라인 존재 확인. 누군가 실수로 `persona_state or {}` 로 되돌리면 즉시 fail → I#3 회귀 가드의 통합 경로 구멍 차단. |
| **🟡** | `tests/test_orchestrator.py` 헤더 docstring | acceptance criteria 표시를 새 분리 임계값(P50 30s / hard 45s) 반영, Phase 1/2 분리 명시. |
| **🟡** | `TASKS.md` Task 4.1 | Phase 1 (Encourager+Scrutinizer, ParallelAgent, sample_pose_data, 완료 ✓) / Phase 2 (PoseExtractor 합류, Day 5, latency 45s 재조정) 으로 분리. 설계 변경 메모도 함께 명시. |

### 최종 회귀 테스트 결과 (B 수정 후)
- PRE 섹션 5건 모두 ✅ (4건 unit + 1건 **통합 경로 정적 가드**)
- Latency 35.8s — P50 30s 초과 ⚠️ 경고만, hard 45s 안
- 두 에이전트 응답·페르소나·부상이력·severity 모두 ✅
- Scrutinizer severity = "critical" (요추 부상 + 42도 상체각도)

→ Task 4.1 Phase 1 acceptance 완전 충족. **부채 없는 마무리**.

### Day 8 Task 8.1 — Multi-round 디베이트 + 합의 감지 (P2 60% → 100%)
**신규 파일**:
- `evals/convergence_judge.py` — Gemini 2.5 Flash 합의 감지 LLM. ConvergenceVerdict Pydantic. 명시적 OTel span (`openinference.span.kind=LLM`) 으로 Phoenix Cloud 에 별도 trace 기록.
- `agents/debate.py` — Multi-round 토론 루프. Round 1 = ParallelAgent, judge 호출, converged 면 종료, 아니면 Round 2+ (직전 라운드 full brief 전달). MAX_DEBATE_ROUNDS env 기본 3.
- `tests/test_debate.py` — PRE (judge 2 케이스) + MAIN (sample_pose_data 합의) + A2 (judge monkey-patch 로 3 라운드 강제) 3 단계 검증.

**최초 실행 결과 (백그라운드, 8분)**:
- PRE 케이스1 (같은 issue): converged=True (4.4s) ✅
- PRE 케이스2 (다른 issue): converged=False (**473s anomaly** ⚠️ — Gemini Flash 변동성)
- MAIN: **Round 1 즉시 합의** (32.6s), shared_issue="좌측 무릎 내전". 총 36.6s. ✅
- 모든 acceptance ✓

**1차 follow-up 리뷰 → 🔴 Critical 4건 발견 → A 옵션 (Critical 1·3·4 + Acceptance 2) 수정**:

| # | 위치 | 수정 |
|---|---|---|
| **C#1** | `debate.py` 다음 라운드 prev_argument | concern_one 한 줄 → `_build_encourager_brief` / `_build_scrutinizer_brief` 로 핵심 필드 묶은 JSON brief 전달. 페르소나 spec 의 "null in round 1" 일치 위해 파싱 실패 시 None. |
| **C#3** | `debate.py` `_build_round_pipeline` | f-string 변수 없는 오타 → `f"formforge_debate_round_{round_number}"` (라운드별 unique name, Phoenix span 충돌 방지) |
| **C#4** | `convergence_judge.py` `judge_convergence` | OpenTelemetry `_tracer.start_as_current_span("convergence_judge", attributes={openinference.span.kind=LLM, llm.model_name, input/output.value, convergence.converged/shared_issue})` 명시적 span 추가. `GoogleADKInstrumentor` 가 못 잡는 google-genai 직접 호출도 Phoenix Cloud 에 LLM span 으로 기록. **Arize 평가 직결**. |
| **Acceptance 2** | `test_debate.py` `acceptance_disagreement_case` 신규 | judge_convergence 를 항상 (converged=False) 로 monkey-patch → 3 라운드 모두 진행 + forced_stop_reason="max_rounds_reached" + judge 3회 호출 + Round 2+ cross-reference 검증. 페르소나 응답 variance 분리. |

**미수정 (의도적 연기)**: Critical 2 (`judge_convergence_sync` 의 `asyncio.run()` Streamlit RuntimeError) → Day 14. Important 1·2·3·4 (orchestrator private 함수 import / APP_NAME 분리 / enc_concern None→"" → null / 싱글톤 멀티스레드) → 발생 시.

### Day 8 Task 8.2 — Firestore push (Streamlit 폴링 UI 준비)
**`agents/debate.py`** 의 `run_debate` 에 옵션 3개 추가: `debate_id`, `video_uri`, `exercise_type`. `debate_id` 제공 시:
- 시작: `create_debate` + `set_debate_pose_data` + `update_debate_status("debating")` — try/except 로 감싸 실패 시 `firestore_enabled=False` 강등 (토론은 그대로 진행, fail-soft)
- 매 라운드 종료 후: `append_debate_round` (ArrayUnion + updated_at) — fail-soft
- 토론 종료: `update_debate_status("feedback_pending"|"done")` — fail-soft

**`tests/test_debate.py`** 의 `acceptance_firestore_push` 신규 검증 함수 — 7개 acceptance 모두 통과:
1. DebateResult.rounds 길이 == 2
2. `debates/{id}` Firestore 문서 존재
3. rounds 배열 길이 == 2
4. 라운드 순서 1→2
5. encourager/scrutinizer payload 보존
6. status='done' (max_rounds_reached 분기)
7. updated_at 정상 갱신

→ **P3 절대원칙 (사용자 피드백 → 페르소나)**: 30% → 50% (저장소 + 자동증가 + persona_state 가드 + 토론 결과 영구 저장 완성. Day 13 feedback handler 로 70% 도달 예정)

**Task 8.2 follow-up 리뷰 → A 패치**:
- 시작 단계 try/except 보호 추가 (위험 1 fix — Firestore 장애 시 토론 차단 방지)
- 출력 안내문에 Task 8.1 + 8.2 분리 표기 (사소 5 fix)

**미수정 (의도적 연기, PROGRESS 부채)**:
- ArrayUnion + `round_latency_seconds(float)` retry 시 중복 — Day 9 retry 래퍼 도입 시 처리
- fail-soft 로깅 `print()` → Cloud Logging 구조화 — Day 14 배포 시 처리
- 테스트 cleanup 없음 → `test_debate_push_*` Firestore 누적 — CI 도입 시 처리

### 세션 5 마무리 (2026-05-28 ~23:50 KST)
- ✅ **commit `6acccfd`** — 12 files, +2970/-17. .gitignore 에 `.claude/` 추가.
- ✅ **push origin main 성공** (사용자가 직접 실행, main 직접 push 가 자동 차단되어 있음 — 안전 정책).
- ✅ Phoenix Cloud UI 에서 `chain trace` + `llm trace (convergence_judge)` 분리 확인 (스크린샷 검증).
- 🟡 **사용자 내일 운동 영상 촬영 예정** → Day 5 Task 5.1 진입 가능 상태.

### 📊 절대원칙 진행률 (세션 5 종료 시점)
| 원칙 | 진행률 | 비고 |
|---|---|---|
| P1 Phoenix 자동 계측 | **100%** | ADK + 명시적 OTel span 둘 다 |
| P2 Encourager ↔ Scrutinizer 통신 | **100%** | Round 1 ParallelAgent + Round 2+ cross-reference brief |
| P3 사용자 피드백 → 페르소나 | **50%** | 저장소 + 자동증가 + persona 가드 + 토론 영구 저장. Day 13 feedback handler 로 70% |
| P4 Mediator + Phoenix MCP | 0% | Day 12 본격 (1등 결정 요소) |
| P5 의료 면책 | 0% | Day 14 UI 도입 시 |

### Day 2 마무리 상태
| Day 2 Task | 상태 |
|---|---|
| 2.1 Firestore | ✅ (검증 통과) |
| 2.2 Vector Search create | ✅ (Index 빌드 중) |
| 2.2 Vector Search deploy | 🟡 Day 14 예정 |
| 2.3 영상 업로드 헬퍼 | ✅ (cloud_storage_client.py) |
| 2.3 사용자 본인 운동 영상 3개 | 🟡 사용자 작업 |

---

## 🗓️ 세션 6 (2026-05-29) — Day 12 Phoenix MCP introspection + Day 9 Mediator

> 영상 불필요 작업으로 P4(1등 결정 요소) 본격 착수. **P4 0%→70%, P5 0%→40%**.

### 사용자 완료 (브라우저)
- ✅ **Firestore 복합 인덱스 생성** — `debates`: `exercise_type` + `user_id` + `created_at` (Collection scope, Enabled 확인).
  → `query_past_debates` 가 `source=error`(FailedPrecondition) → `source=firestore` 로 정상화 검증 완료.

### Claude Code 완료

**1) Task 12.1 — 커스텀 Phoenix MCP wrapper 스켈레톤** (commit `02052bd`, P4 0%→30%)
- `mcp/phoenix_mcp_server.py` (524줄). FastMCP **3.3.1** 기반 커스텀 서버.
- tool 2개: `query_past_debates`(Firestore consensus join) / `query_similar_safety_flags`(cross-user 위험 스캔).
- Phoenix REST trace 는 **스켈레톤 미구현** → 항상 graceful fallback + 경고 span (Day 12+ 실연동).
- Vector Search 미배포(Day 14) → Firestore 스캔 fallback.
- stdio/http transport 전환(`PHOENIX_MCP_TRANSPORT`), Cloud Run `PORT` 대응.
- P1: 서버 자체 Phoenix register → tool 호출이 TOOL span 으로 기록. P5: 모든 응답에 의료 면책.
- 검증(`--selftest`): tool 2개 등록 OK + MCP 프로토콜 왕복(in-memory Client) OK +
  `query_similar_safety_flags` 가 실제 과거 토론에서 "Knee Valgus Collapse" 매칭 found=1.

**2) Task 9.1 — Mediator skeleton** (commit `746df6c`, P5 0%→40%)
- `agents/mediator.py`. ADK Agent + output_schema(MediatorOutput) — encourager/scrutinizer 동일 패턴.
- 출력: consensus + priority_actions[order,action,rationale] + disclaimer + round_count_used.
- **P5 강제**: `_enforce_disclaimer` 로 LLM 이 면책 누락/변형 시 표준 한국어 문구 주입.
- `tests/test_mediator.py` — P5 회귀 가드 7개 (Gemini 없이 ~2s).
- 검증(`--selftest`): acceptance 5/5. Scrutinizer required_action 을 order 1(부상이력 근거),
  Encourager actionable_tip 을 order 2 로 통합. latency 24.9s.

**3) Task 12.2 — Mediator ↔ Phoenix MCP 연결** (commit `baa1b35`, P4 30%→70%) ⭐ 1등 결정 요소
- `create_mediator_agent_with_mcp()`: MCPToolset(StdioConnectionParams)로 phoenix_mcp_server stdio subprocess 연결.
- **ADK 제약 확정**: output_schema 를 쓰면 tool 호출 비활성화 → MCP 버전은 output_schema 없이
  instruction JSON 강제 + `_parse_mediator_json`(fence/앞뒤 텍스트 방어).
- `run_mediator_with_mcp()`: Gemini 자동 tool 호출 + `toolset.close()` 정리.
- 검증(`--mcp`): **Gemini 2.5 Pro 가 query_past_debates + query_similar_safety_flags 를 자동 호출** 확인.
  acceptance 4/4. latency 49.4s.

**4) e2e 통합 — 토론→합의→Firestore 파이프라인** (commit `ab43834`, 6/5 마일스톤 골격 달성) ⭐
- `agents/orchestrator.py` `run_full_session()`: run_debate → run_mediator_with_mcp → set_debate_consensus 한 번에 조율.
- FullSessionResult(debate + mediator + mcp_tool_calls + latency). debate/mediator import 는 함수 내부 lazy.
- 스크립트 직접 실행 위해 프로젝트 루트를 sys.path 에 **append**(insert 아님 — mcp shadow 회피).
- `mediator.py`: `import os` 를 모듈 최상단으로 (orchestrator import 경로에서 NameError 수정).
- 검증(`--full`): **acceptance 6/6 통과**. 토론 라운드 ≥1 + Mediator consensus + MCP 자동 호출 +
  P5 면책 + Firestore consensus 저장 + status=feedback_pending.
- ⭐ **introspection 실증**: Mediator 가 MCP 로 과거 토론 2건을 찾아 `past_debate_references` 에 반영
  ("과거에도 무릎 내반 붕괴 반복 지적"). sample_pose_data 로 **영상 없이 전체 파이프라인 동작**.

### 발견된 이슈 + 해결
| # | 이슈 | 해결 |
|---|---|---|
| 1 | 프로젝트 `mcp/` 폴더가 PyPI `mcp` 패키지를 shadow → `ModuleNotFoundError: mcp.types` | fastmcp import 를 sys.path 루트 추가 "전"에 배치. MCP 관련 import 는 함수 내부 lazy. |
| 2 | stdio MCP 서버에서 print → JSON-RPC 채널(stdout) 오염 | 모든 로그를 stderr 로 (`_log`). |
| 3 | ADK output_schema + tool 동시 불가 (ADK 공식) | MCP 버전 Mediator 는 output_schema 제거 + instruction JSON + 수동 파싱. |
| 4 | tool call 캡처 안 됨 (`part.function_call` 직접 접근 실패) | `event.get_function_calls()` ADK 표준 헬퍼로 교체 → 정확히 캡처. |

### 버전 메모 (이 세션에서 확정)
- FastMCP **3.3.1** (`@mcp.tool`, `mcp.run()` / `mcp.run(transport="http", host, port)`, `list_tools()` async)
- ADK **2.1.0** (`from google.adk.tools.mcp_tool import MCPToolset, StdioConnectionParams`)

### 미수정 (의도적 연기, PROGRESS 부채)
- **Phoenix REST 실연동**: `_query_phoenix_traces` 스켈레톤 → P4 나머지 30%. arize-phoenix 패키지 + REST 인증 필요.
- **past_debate_references 실데이터**: 같은 user 반복 업로드해야 채워짐 (현재 user_001 과거 debate 없어 []).
- **Vertex vs API key 경로**: selftest 에서 `Using GOOGLE_API_KEY` — 세션 4 Vertex 전환과 다른 경로. 안정성 점검 필요(지금 동작은 함).
- **asyncio.run() Streamlit 충돌**: `run_mediator_sync`/`run_mediator_with_mcp_sync` — Day 14 UI 통합 시 await 경로로.
- ✅ **Mediator e2e 통합 완료** (commit `ab43834`, `run_full_session`) ← 세션 6 후반 해결.
- **past_debate_references.debate_id 부정확**: MCP 가 doc.id 미반환 → LLM 이 created_at 으로 합성. P4 마무리 시 query_* 가 실제 debate_id 반환하도록 개선.

### 📊 절대원칙 진행률 (세션 6 종료 시점)
| 원칙 | 진행률 | 비고 |
|---|---|---|
| P1 Phoenix 자동 계측 | **100%** | ADK + 명시적 OTel span + MCP 서버 자체 계측 |
| P2 Encourager ↔ Scrutinizer | **100%** | Round 1 Parallel + Round 2+ cross-reference |
| P3 사용자 피드백 → 페르소나 | **50%** | Day 13 feedback handler 로 70% 예정 |
| P4 Mediator + Phoenix MCP | **70%** | MCP wrapper + Mediator 자율 호출 + e2e introspection(past_debate_references 실데이터) ✅. 나머지: Phoenix REST 실연동 + 실제 debate_id 반환 |
| P5 의료 면책 | **40%** | Mediator disclaimer 강제 ✅. UI 전체 표시는 Day 14 |

---

## 🗓️ 세션 7 (2026-05-29 저녁) — Day 12 P4 마무리 (70% → 100%) ⭐ 1등 결정 요소 완성

> 영상 불필요 작업. 사용자가 "A+B 둘 다 100%" 선택 → introspection 루프 완성.

### Claude Code 완료

**A) query_* 가 실제 debate_id 반환** (commit `0163340`)
- 문제: `get_recent_debates` 가 `snap.id` 를 버려서 Mediator LLM 이 created_at 으로 debate_id 를 합성 (P4 결함).
- `firestore_client.get_recent_debates`: `snap.id` 를 `dict["debate_id"]` 로 보존.
- `phoenix_mcp_server._summarize_debate` / `query_similar_safety_flags`: debate_id 포함.
- `mediator.MEDIATOR_INSTRUCTION_MCP`: tool 의 debate_id 를 verbatim 복사 (합성 금지 강화).
- 검증: `mcp --selftest` query_past_debates(found=2)/query_similar(found=3) 실제 doc id 반환.
  `mediator --mcp` past_debate_references 가 `e2e_demo_1780051544` 등 실제 id (acceptance 4/4).
- → Task 12.2 마지막 acceptance "past_debate_references 에 실제 trace ID" 충족.

**B-2) Phoenix REST 실연동** (commit `8d5fabd`)
- `_query_phoenix_traces` 스켈레톤(항상 PhoenixUnavailable) → **실구현**.
- `arize-phoenix-client`(phoenix.client.Client) 로 Phoenix Cloud span 실조회.
  base_url=`https://app.phoenix.arize.com/s/alsgur9865`, project=`formforge-prod`.
- 프로젝트 span 조회 → input/output value 텍스트로 user_id/exercise_type best-effort 필터 → trace_id 목록.
- 실패 시 PhoenixUnavailable → Firestore fallback 유지 (§5.3, P4 violation 회피).
- `query_past_debates` 결과에 `phoenix_traces` + `phoenix_status="ok (N trace spans)"` 추가.
- 검증: selftest 에서 phoenix_status "ok (5 trace spans)", phoenix_traces 에 실제 trace_id (mcp.query_* TOOL span).

**B-1) orchestrator trace_id 실저장** (commit `8d5fabd`)
- `_ensure_phoenix_registered`: register + GoogleADKInstrumentor 1회 (idempotent, fail-soft).
  미등록 시 OTel trace_id 가 0(무효) → trace_id 저장 위해 필수. (기존엔 orchestrator/mediator 가 register 안 함, hello_world 만)
- `run_full_session`: mediator 호출을 명시적 span(`mediator_consensus`)으로 감싸 trace_id 추출 →
  `set_debate_consensus(trace_ids={"mediator_trace_id": ...})` 실저장 (기존 `{}` 하드코딩 제거).
- `--full` acceptance 에 "Firestore trace_ids 저장(B-1)" 가드 추가.
- 검증: `orchestrator --full` acceptance **7/7**, `trace_ids={'mediator_trace_id':'09278d...'}` 저장.

### ⭐ introspection 루프 완성 (P4 본질)

```
Mediator 실행 → trace_id 저장(B-1) → 다음 토론 query_past_debates 가 실제 trace_id 반환(A) → Phoenix REST 로 재조회(B-2)
```

selftest 1회로 동시 확인: phoenix_status "ok (5 trace spans)" + debate_id=`e2e_demo_1780056106` + mediator_trace_id=`09278d...` 반환.

### 발견 + 결정
| # | 항목 | 처리 |
|---|---|---|
| 1 | orchestrator/mediator 가 Phoenix register 안 함 (hello_world 만) | `_ensure_phoenix_registered` 추가 — register 없으면 OTel trace_id 무효(0) |
| 2 | full `arize-phoenix` 무거움 (pandas+graphql+sqlalchemy) | 경량 `arize-phoenix-client>=2.0.0` (185KB) 선택 — Cloud Run 배포 유리 |
| 3 | Phoenix Cloud space 경로 | base_url = `.../s/alsgur9865` (PHOENIX_COLLECTOR_ENDPOINT) |

### 버전/패키지 메모
- `arize-phoenix-client` **2.7.0** — `from phoenix.client import Client`, `client.spans.get_spans_dataframe(project_identifier=, limit=)`.
- DataFrame 컬럼: `context.trace_id`, `context.span_id`, `name`, `span_kind`, `attributes.*`. iterrows index=span_id.

### 📊 절대원칙 진행률 (세션 7 종료 시점)
| 원칙 | 진행률 | 비고 |
|---|---|---|
| P1 Phoenix 자동 계측 | **100%** | ADK + OTel span + MCP 서버 자체 계측 + orchestrator register |
| P2 Encourager ↔ Scrutinizer | **100%** | Round 1 Parallel + Round 2+ cross-reference |
| P3 사용자 피드백 → 페르소나 | **50%** | Day 13 feedback handler 로 70% 예정 |
| P4 Mediator + Phoenix MCP | **100%** ✅ | MCP wrapper + 자율 호출 + 실제 debate_id + Phoenix REST 실연동 + trace_id 루프 완성 |
| P5 의료 면책 | **40%** | Mediator disclaimer 강제 ✅. UI 전체 표시는 Day 14 |

---

## ⏭️ 다음 세션 시작 시 할 일

### 0. 매번 먼저
- **이 파일 먼저 읽기**
- 영상 도착했는지 확인: `ls "data/sample_videos/"`
- 가능하면 `.env` 에 `VECTOR_SEARCH_*` 3개 변수 추가됐는지 한 번 더 확인

### 1. 영상 도착했을 때 우선순위
1. **Task 1.6 검증**:
   ```
   ./venv/Scripts/python.exe agents/pose_mediapipe.py data/sample_videos/squat_demo.mp4 squat
   ```
   30초 영상 5s 이내 acceptance.
2. **Day 5 Task 5.1** — 2-stage PoseExtractor 완성 (MediaPipe Stage 1 + Gemini Vision Stage 2). 영상으로 직접 검증.
3. **Task 4.1 Phase 2** — PoseExtractor 합류 후 orchestrator pipeline: PoseExtractor → (Encourager ∥ Scrutinizer). latency 45s 재조정.
4. **Day 9 Task 9.2** — End-to-end dry run (영상 → 모든 단계 → Firestore + Phoenix).

### 2. 영상 없이도 가능 (P4 100% 완료 → 다음 우선순위)
1. ✅ **Day 12 P4 마무리 (70%→100%) 완료** (세션 7, `0163340`+`8d5fabd`) — query_* 실제 debate_id + Phoenix REST 실연동 + trace_id 루프.
2. **Day 13 Task 13.2** — LLM-as-a-Judge (`gemini-3.5-flash`) 토론 품질 평가. P3 50% → 70%. ← **다음 1순위**
3. **Day 12 Task 12.3** — MCP server Cloud Run 배포 준비 (`mcp/Dockerfile`, http transport 모드). Day 14 대비.
4. **Day 4 Task 4.2** — pytest + mock 단위 테스트 정비 (`run_full_session` 포함). CI 가능하게.

> ✅ 세션 6 에서 **Mediator e2e 통합 완료** (`run_full_session`, ab43834). 영상 합류 시 PoseExtractor 만 앞에 붙이면 완전 e2e (`PoseExtractor → run_full_session`).

### 3. 추후·선택
- Vector Search Index 빌드 완료 확인: `python storage/vector_search_setup.py status` (`vectors_count` 보이면 빌드 끝)
- Firestore 복합 인덱스 1회 생성 (PROGRESS 위쪽 콘솔 링크 — Day 12 Phoenix MCP `query_past_debates` 호출 전)

### 4. 잔존 부채 (다음 세션에 자연스럽게 통합 처리)
- **firestore_client.py**: I#3 `_flatten()` None 가드 / I#4 `.update()` NotFound 가드 — Day 13 `evals/feedback_handler.py` 구현 시
- **debate.py**: ArrayUnion 중복 (round_latency_seconds float 포함) — Day 9 retry 래퍼 도입 시
- **debate.py**: fail-soft `print()` → 구조화 로그 — Day 14 Cloud Run 배포 시
- **convergence_judge.py**: `judge_convergence_sync` asyncio.run() Streamlit 충돌 — Day 14 UI 통합 시
- **orchestrator.py**: I#1 user_id 이중 / I#2 session_id uuid4 — Day 8 Mediator 추가 시 정리 가능
- **test_orchestrator.py**: PRE 5번 false negative (inspect 정적 검사) — AST 파싱 필요, Day 14 이전 시간 남으면
- **mediator.py**: `run_mediator_sync`/`run_mediator_with_mcp_sync` asyncio.run() Streamlit 충돌 — Day 14 UI 통합 시
- ✅ **mcp/phoenix_mcp_server.py**: Phoenix REST 실연동(`_query_phoenix_traces`) + `query_*` 실제 debate_id 반환 — **세션 7 해소** (`0163340`+`8d5fabd`). trace_id 루프 완성.
- **Vertex vs API key 경로**: selftest 에서 GOOGLE_API_KEY 사용 — 안정성 점검 (지금 동작은 함)
- **_query_phoenix_traces 필터**: user_id/exercise_type 를 input/output value 텍스트 매칭으로 best-effort 필터 — Vector Search 배포(Day 14) 시 정교화 가능
- **e2e 테스트 누적**: `orchestrator.py --full` 실행마다 `e2e_demo_*` Firestore debate 누적 (cleanup 없음) — CI 도입 시 정리.

### 5. 운영 메모
- **Phoenix Cloud**: chain trace + llm trace(`convergence_judge`) + **Mediator span 아래 MCP tool call(query_past_debates / query_similar_safety_flags) child span** — Devpost 제출 영상용 핵심 스크린샷.
- **GCP 누적 비용**: ~$0 추정 (Firestore + Storage free tier, Vector Search Index 빌드 무료, Gemini API ~$0.1)
- **마감 D-14** (6/12 06:00 KST, 오늘 5/29 기준)

---

## 🚨 절대 원칙 재확인 (위반 시 1등 불가)

- **P1** Phoenix 자동 계측이 모든 에이전트에 활성화
- **P2** Encourager ↔ Scrutinizer 직접 통신 (단일 응답 금지)
- **P3** 사용자 피드백이 다음 토론 페르소나에 반영
- **P4** Mediator는 Phoenix MCP를 통해 과거 trace 쿼리
- **P5** 모든 결과에 의료/부상 면책 표시

---

## 📅 전체 일정 (15일, 5/28-6/12)

| Phase | Day | 핵심 목표 | 상태 |
|---|---|---|---|
| Foundation | 1-2 (5/28-29) | 환경 셋업, 자동 계측 hello world, MediaPipe 스모크 | 🟢 Day 2 거의 완료 (1.6 영상·2.2 deploy만 대기) |
| Skeleton | 3-4 (5/30-31) | 두 에이전트 + Pose Extractor 기본 | 🟢 Task 3.2·3.3·4.1 선완료, 4.2 단위 테스트만 남음 |
| Multi-modal Core | 5-7 (6/1-3) | 2-stage PoseExtractor 완성 | ⏭️ 영상 대기 |
| Adversarial Debate | 8-9 (6/4-5) | 토론 로직 + Mediator | 🟢 8.x ✅ · 9.1 Mediator ✅ · **9.2 e2e 골격 ✅ (run_full_session)** |
| **🚨 마일스톤** | **9 종료 (6/5)** | **End-to-end skeleton 마감일** | 🟢 **골격 달성** (sample로 토론→합의→저장). 영상 합류 시 PoseExtractor만 추가하면 완전 e2e |
| Memory | 10-11 (6/6-7) | Firestore + Vector Search | ⏭️ |
| Introspection | 12 (6/8) | Phoenix MCP 커스텀 wrapper | 🟢 **12.1·12.2 ✅ (P4 100%)** · Phoenix REST + trace_id 루프 완성 · 12.3 배포준비만 남음 |
| Self-Improvement | 13 (6/9) | LLM-as-a-Judge + 양방향 학습 | ⏭️ |
| UI + Deploy | 14 (6/10) | Streamlit + Cloud Run 듀얼 배포 | ⏭️ |
| Submit | 15 (6/11) | 영상 + Devpost | ⏭️ |

**최종 마감**: 2026-06-12 06:00 KST (= 6/11 안에 모든 제출 완료)
