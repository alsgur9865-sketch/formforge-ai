# FormForge AI — Day-by-Day Task Checklist

> 이 문서는 Claude Code가 따라갈 step-by-step 실행 계획입니다.
> 각 Task는 명확한 입력·출력·검증 방법(Acceptance Criteria)을 가집니다.
> 사용자는 "TASKS.md의 Day N Task X 진행해줘"라고 Claude Code에 지시하면 됩니다.

---

## 📅 전체 일정 (15일, 2026-05-28 → 2026-06-12)

| Phase | Day | 핵심 목표 |
|---|---|---|
| **Foundation** | 1-2 | 환경 셋업, 자동 계측 hello world |
| **Skeleton** | 3-4 | 두 에이전트 + Pose Extractor 기본 |
| **Multi-modal Core** | 5-7 | Gemini 비디오 분석 완성 |
| **Adversarial Debate** | 8-9 | 토론 로직 + Mediator |
| **Memory** | 10-11 | Firestore + Vector Search |
| **Introspection** | 12 | ⭐ Phoenix MCP introspection |
| **Self-Improvement** | 13 | ⭐⭐ LLM-as-a-Judge + persona evolution |
| **UI + Deploy** | 14 | Streamlit + Cloud Run |
| **Submit** | 15 | 영상 + Devpost |

---

## DAY 1 — Foundation (오늘, 5/28)

### Task 1.1 — GCP 계정 + $100 크레딧 신청

**작업자**: 사용자 (Claude Code 아님 — 사용자가 직접 브라우저에서)

**Steps**:
1. https://cloud.google.com/free 에서 새 GCP 프로젝트 생성 (이름: `formforge-prod`)
2. 결제 계정 연결 (free trial 활성화)
3. Devpost 페이지(https://rapid-agent.devpost.com)에서 $100 크레딧 신청 폼 작성 (마감 6/4)
4. APIs 활성화:
   - Vertex AI API
   - Firestore API
   - Cloud Storage API
   - Cloud Run API
5. 서비스 계정 생성:
   - 이름: `formforge-sa`
   - 권한: `Vertex AI User`, `Firestore User`, `Storage Object Admin`, `Cloud Run Invoker`
   - JSON 키 다운로드 → 프로젝트 root에 `service-account.json`로 저장

**검증**: `gcloud auth list` 명령으로 서비스 계정 인증 확인.

### Task 1.2 — Arize Phoenix Cloud 가입

**작업자**: 사용자

**Steps**:
1. https://app.phoenix.arize.com 가입 (Google 계정으로 가능)
2. New Project → `formforge-prod` 생성
3. Settings → API Keys → 새 키 발급 → 안전한 곳에 저장

**검증**: Phoenix Cloud 대시보드 좌측에 `formforge-prod` 프로젝트가 보임.

### Task 1.3 — 로컬 프로젝트 셋업

**작업자**: Claude Code (사용자가 지시)

**Claude Code에게 줄 지시문**:
> CLAUDE.md를 읽고, 프로젝트 디렉토리 구조 섹션에 따라 빈 디렉토리·파일을 만들어줘.
> `.gitignore`, `requirements.txt`, `.env.example`, `README.md` 초기 버전 생성.

**`requirements.txt` 명시 내용** (Claude Code가 그대로 생성):

```
google-adk>=1.0.0
google-genai>=1.0.0
google-cloud-firestore>=2.18.0
google-cloud-storage>=2.18.0
google-cloud-aiplatform>=1.70.0
mediapipe>=0.10.18
numpy>=1.26.0
opencv-python>=4.10.0
scipy>=1.13.0
arize-phoenix-otel>=0.6.0
openinference-instrumentation-google-adk>=0.1.0
mcp>=1.0.0
fastmcp>=2.0.0
streamlit>=1.39.0
streamlit-autorefresh>=1.0.1
python-dotenv>=1.0.0
pydantic>=2.9.0
pytest>=8.0.0
```

**산출물**:
- 모든 디렉토리 생성
- 빈 `__init__.py` 파일들
- `.gitignore` (Python + secrets)
- `requirements.txt`
- `.env.example`
- 영어로 작성된 `README.md` skeleton

**검증**: `ls -R` 했을 때 CLAUDE.md 디렉토리 구조와 일치.

### Task 1.4 — Hello World (자동 계측 작동 확인) ⭐ Day 1 핵심

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> CLAUDE.md와 ARCHITECTURE.md 7.2 섹션을 참고해서, Phoenix 자동 계측이 작동하는 최소 ADK 에이전트 hello world를 만들어줘.
> 파일 위치: `agents/hello_world.py`
> 실행: `python agents/hello_world.py`
> 기대 결과:
>   1. 터미널에 에이전트 응답 출력
>   2. Phoenix Cloud `formforge-prod` 프로젝트에 trace 1개 표시

**Acceptance Criteria**:
- [ ] 코드 실행 시 에러 없이 완료
- [ ] Phoenix Cloud 대시보드에서 trace 확인됨
- [ ] trace에 model name, input, output이 모두 보임

### Task 1.5 — GitHub repo 생성

**작업자**: 사용자

**Steps**:
1. github.com에서 새 repo: `formforge-ai` (Public)
2. Add a license: **MIT** 체크 (Devpost 요구사항)
3. About 섹션에 `MIT License` 자동 표시 확인
4. 로컬에서 `git init && git remote add origin ...` 후 첫 commit

**검증**: Repo 첫 페이지 우측 About에 "MIT License" 표시.

### Task 1.6 — MediaPipe 스모크 테스트 ⭐ Day 5 작업 전에 필수

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> MediaPipe Pose가 정상 동작하는지 한 영상으로 검증.
> 파일: `agents/pose_mediapipe.py` (skeleton)
> `mediapipe.solutions.pose`로 샘플 영상(스쿼트) 프레임별 33 키포인트 추출 → JSON으로 저장.
> 무릎·엉덩이·발목 각도 계산해서 출력.

**Acceptance Criteria**:
- [ ] 30초 영상 분석 5초 이내
- [ ] 각 rep의 무릎 각도 시계열이 합리적 (스쿼트면 90도 근처에서 최저점)
- [ ] 키포인트 confidence가 너무 낮으면 명확한 경고

> 💡 이 테스트가 실패하면 Day 5-7 multi-modal core가 무너집니다. 지금 검증해야 안전.

---

## DAY 2 — Foundation 마무리 + Firestore·Vector Search 셋업

### Task 2.1 — Firestore 초기화

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> ARCHITECTURE.md 3.1 컬렉션 구조에 따라 Firestore 셋업.
> 파일: `storage/firestore_client.py`
> 함수:
>   - `init_firestore()`: 클라이언트 초기화
>   - `create_user(user_id, profile)`: users 컬렉션에 문서 생성
>   - `get_user_persona_state(user_id)`: 기본값 반환 (warmth=0.5, harshness=0.5, detail=0.5)
> 검증용 스크립트: `tests/test_firestore.py`

**Acceptance Criteria**:
- [ ] `python tests/test_firestore.py` 실행 시 더미 사용자가 Firestore에 생성됨
- [ ] GCP 콘솔 Firestore 탭에서 `users/test_user_001` 문서 확인 가능

### Task 2.2 — Vertex AI Vector Search 인덱스 생성

**작업자**: Claude Code + 사용자 (인덱스 생성은 30분~1시간 걸림)

**Claude Code에게 줄 지시문**:
> ARCHITECTURE.md 4.1을 참조해서 Vector Search 인덱스 생성 스크립트 작성.
> 파일: `storage/vector_search_setup.py`
> 인덱스 이름: `formforge-debates-index`
> 차원: 1408, 거리: cosine, 업데이트: streaming
> 실행 후 인덱스 ID + 엔드포인트 ID를 `.env`에 저장하라는 안내 출력.

**Acceptance Criteria**:
- [ ] GCP 콘솔 Vertex AI > Vector Search에 인덱스 생성됨
- [ ] 인덱스 status가 `Ready` (인덱스 deploy까지 30분~1시간 대기)
- [ ] `.env`에 `VECTOR_SEARCH_INDEX_ID`, `VECTOR_SEARCH_ENDPOINT_ID` 설정

### Task 2.3 — Cloud Storage 버킷 + 샘플 영상

**작업자**: 사용자

**Steps**:
1. `gsutil mb gs://formforge-videos-{your-project-id}` (버킷 생성)
2. 본인 운동 영상 3개 촬영 (스쿼트, 데드리프트, 푸시업 — 각 30초 이내)
3. `gsutil cp` 명령으로 `data/sample_videos/`에 업로드

**참고**: 영상 촬영 시 정면 + 옆면 두 각도로 찍으면 더 좋은 분석. 의류 노출 적당히 (관절 보이게).

**Acceptance Criteria**:
- [ ] `gsutil ls gs://formforge-videos-{your-project-id}/` 에서 영상 3개 확인

---

## DAY 3-4 — Agent Skeleton

### Task 3.1 — PoseExtractor Agent

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> ARCHITECTURE.md 2.1 명세대로 PoseExtractor를 만들어줘.
> 파일: `agents/pose_extractor.py`
> 모델: gemini-2.5-flash
> 입력 비디오는 Cloud Storage URI 또는 로컬 파일 둘 다 받게.
> 출력은 명세 JSON 스키마 정확히 따라가게 (`response_mime_type="application/json"`).
> Phoenix 자동 계측이 활성화되어 있는지 확인.

**Acceptance Criteria**:
- [ ] 샘플 스쿼트 영상으로 실행 → 명세 스키마의 JSON 출력
- [ ] `rep_count`가 실제 영상의 rep과 ±1 이내
- [ ] `safety_flags`에 적어도 1개 이상 항목
- [ ] Phoenix Cloud에 trace 1개 생성, video URI가 input으로 기록됨

### Task 3.2 — Encourager Agent

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> ARCHITECTURE.md 2.2 명세대로 The Encourager를 만들어줘.
> 파일: `agents/encourager.py`
> 페르소나 prompt는 명세를 그대로 사용, `{warmth_level}` `{detail_level}` placeholder는 함수 인자로 받음.
> 입력은 pose_data + user_context.
> 출력은 명세 JSON 스키마.
> debate_round=1일 때는 scrutinizer_previous_argument=None.

**Acceptance Criteria**:
- [ ] Task 3.1의 출력을 입력으로 받아 응답 생성
- [ ] `praise` 필드에 구체적 metric 인용 (예: "5 reps 모두 깊이 일관성")
- [ ] `concern_one`은 정확히 1개 (여러 개 아님)
- [ ] tone이 명백히 warm (테스트로 prompt 후 사용자 검토)

### Task 3.3 — Scrutinizer Agent

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> ARCHITECTURE.md 2.3 명세대로 The Scrutinizer를 만들어줘.
> 파일: `agents/scrutinizer.py`
> 동일한 PoseExtractor 출력에 대해 Encourager와 명백히 다른 톤·관점.
> `primary_risk`는 가장 심각한 안전 위험 1개.

**Acceptance Criteria**:
- [ ] 같은 입력으로 Encourager와 명백히 다른 응답 (사용자 비교 확인)
- [ ] `primary_risk`에 biomechanical mechanism 명시
- [ ] tone이 명백히 critical
- [ ] medical advice 직접 주지 않음 ("consult a professional" 언급)

### Task 4.1 — Orchestrator (Mediator 없이) — 2 Phase 분리

**작업자**: Claude Code

**📐 설계 변경 메모 (세션 5)**:
당초 SequentialAgent 명시했으나 실측 latency variance(48s) 로 인해 Round 1 은 ParallelAgent 로 전환.
의미상도 Round 1 은 두 에이전트 독립 첫 인상이라 병렬이 옳음. Day 8 Round 2+ 도입 시
SequentialAgent / custom debate loop 로 전환 + ADK 의 ParallelAgent deprecation 대응 (Workflow 전환).
또한 PoseExtractor 는 영상 dependency 로 Day 5 Task 5.1 에서 합류하므로 Task 4.1 은 2 phase 로 분리.

#### Phase 1 — Encourager + Scrutinizer 2 에이전트 (Day 4, 사전 완료)

**Claude Code 지시문**:
> ParallelAgent 로 Encourager · Scrutinizer 동시 호출. sample_pose_data.json 으로 검증.
> 파일: `agents/orchestrator.py`, `tests/test_orchestrator.py`

**Phase 1 Acceptance Criteria**:
- [✓] 1개 pose_data 입력 → 2개 에이전트 응답 dict 반환
- [✓] Phoenix Cloud 1개 trace 에 parent (parallel) + 2개 child span 표시
- [✓] Latency P50 30s / hard fail 45s (Gemini Pro 2x 병렬 ±30% variance 분리 임계값)
- [✓] persona_state 우선순위 가드 (`_resolve_persona_state`) + 통합 경로 정적 검증

#### Phase 2 — PoseExtractor 합류 (Day 5)

**Claude Code 지시문**:
> Task 5.1 의 2-stage PoseExtractor 완성 후 orchestrator 에 prepend.
> Pipeline: PoseExtractor → (Encourager ∥ Scrutinizer).
> SequentialAgent 로 PoseExtractor 의 출력을 두 코치 입력으로 흘리고, 두 코치는 내부 ParallelAgent.

**Phase 2 Acceptance Criteria**:
- [ ] 1개 영상 입력 → 3개 에이전트 응답을 dict로 반환
- [ ] Phoenix Cloud에서 1개 trace에 3개 child span이 보임
- [ ] 총 latency 45초 이내 (PoseExtractor ~10s + ParallelAgent ~30s)

### Task 4.2 — 단위 테스트

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> 위 4개 모듈에 대한 pytest 테스트 작성.
> 파일: `tests/test_agents.py`
> 외부 API 호출은 mock 처리 (gemini, phoenix 모두).
> CI 없이 로컬 `pytest -v` 실행 가능.

---

## DAY 5-7 — Multi-modal Core (Gemini 비디오 분석 정확도 끌어올리기)

### Task 5.1 — 2-stage PoseExtractor 완성 (MediaPipe + Gemini)

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> ARCHITECTURE.md 2.1의 2-stage 파이프라인 완성.
>
> **Stage 1 (MediaPipe, `agents/pose_mediapipe.py`)**:
>   - mediapipe.solutions.pose로 비디오 → 프레임별 33 키포인트
>   - NumPy로 각도 계산: knee (대퇴-경골), hip (척추-대퇴), back angle (수직 기준)
>   - rep counting: 무릎 각도 신호의 peak detection (`scipy.signal.find_peaks`)
>   - tempo: rep별 down/pause/up 구간 자동 분리
>   - 키포인트 confidence 평균 < 0.5 시 명확한 에러 코드
>
> **Stage 2 (Gemini Flash, `agents/pose_extractor.py`)**:
>   - 입력: Stage 1 메트릭 dict + 비디오 thumbnail 4-6장
>   - 역할: safety_flags severity 판단 + 운동 유형 검증 + 자연어 설명
>   - LLM이 정량 수치 재측정 금지 (Stage 1 결과 신뢰)
>
> 영상 길이 제한 (30초 max), 화질 미달 시 명확한 에러 메시지.

**참고 자료**: ARCHITECTURE.md 2.1 + MediaPipe Pose 문서 (https://developers.google.com/mediapipe/solutions/vision/pose_landmarker)

**Acceptance Criteria**:
- [ ] 3개 샘플 영상(스쿼트, 데드리프트, 푸시업) 모두 정확히 분석
- [ ] 각 분석 시간 10초 이내 (MediaPipe 5초 + Gemini 5초)
- [ ] rep count 오차 ±1 이내
- [ ] safety_flags가 명백한 폼 결함을 잡아냄
- [ ] LLM이 직접 측정한 각도 수치를 출력하지 않음 (코드 측정값만 사용)

### Task 6.1 — 부상 위험 데이터셋 큐레이션

**작업자**: 사용자 + Claude Code

**Steps**:
1. 사용자가 일부러 잘못된 자세 영상 3개 추가 촬영 (각 운동마다 명백한 결함 의도)
2. Claude Code가 PoseExtractor로 분석 → safety_flags가 정확히 검출되는지 확인
3. 안 잡히는 경우 prompt 보강

**Acceptance Criteria**:
- [ ] 의도한 결함이 모두 `safety_flags`에 검출됨
- [ ] 거짓 양성(false positive) 최소화

### Task 7.1 — 멀티모달 임베딩 생성 + Vector Search 첫 저장

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> ARCHITECTURE.md 4.2-4.3 따라 `storage/vector_search.py` 완성.
> 비디오 + 합의 텍스트를 multimodalembedding-001로 임베딩 후 Vector Search에 streaming upsert.
> 사용자 ID와 exercise_type을 metadata로 저장.

**Acceptance Criteria**:
- [ ] 첫 임베딩 저장 후 콘솔에서 인덱스 size 증가 확인
- [ ] `search_similar_debates()` 호출 시 본인이 저장한 항목이 최상위로 검색됨

---

## DAY 8-9 — Adversarial Debate Logic + Mediator

### Task 8.1 — Multi-round 토론 로직 + 합의 감지

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> 두 에이전트가 라운드 2 이상 진행하도록 orchestrator 수정.
> 라운드 N>1 일 때:
>   - Encourager는 `scrutinizer_previous_argument`를 받음 → `addresses_scrutinizer` 필드에 동의/반박 명시
>   - Scrutinizer도 동일 (`addresses_encourager`)
>
> **합의 감지 알고리즘** (Mediator 호출 전 orchestrator가 판단):
>   1. Encourager의 `concern_one`과 Scrutinizer의 `primary_risk.name` 추출
>   2. `gemini-2.5-flash`로 둘이 같은 issue를 가리키는지 분류 (간단 LLM call, 1-2초)
>     - 입력: 두 텍스트 + "Are these two coaches focused on the same primary issue? Yes/No + reason"
>     - 출력: `{"converged": bool, "shared_issue": str|null}`
>   3. `converged: true` → 즉시 라운드 종료, Mediator 호출
>   4. 그렇지 않으면 다음 라운드 진행
>   5. `MAX_DEBATE_ROUNDS` (.env, 기본 3) 도달 시 강제 종료

**참고**: ARCHITECTURE.md 섹션 2.2-2.3 라운드 N+1 prompt 패턴.

**Acceptance Criteria**:
- [ ] 일반적인 영상은 2 라운드 안에 합의 (`converged: true`)
- [ ] 명백히 불일치하는 입력(예: 부상 영상)은 3 라운드까지 가도 의견 차이 유지
- [ ] 라운드별 메시지가 Phoenix trace에 명확히 구분됨
- [ ] 합의 판정 LLM call도 trace에 별도 span으로 기록

### Task 8.2 — Firestore에 라운드 메시지 push (Streamlit 폴링 UI 준비)

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> orchestrator가 각 라운드 종료 시 Firestore `debates/{debate_id}.rounds` 배열에 push.
> 각 push 후 `updated_at` timestamp 갱신 (폴링 측 변경 감지에 사용).
>
> ⚠️ **Firestore `on_snapshot()` 콜백 사용 금지** — Streamlit rerun 모델과 충돌.
> Streamlit 측은 `streamlit-autorefresh`로 1초마다 polling. ARCHITECTURE.md 3.2 패턴 참조.

**Acceptance Criteria**:
- [ ] 라운드 1 끝 → Firestore에 rounds[0] 즉시 생성
- [ ] 라운드 2 끝 → rounds[1] 추가
- [ ] GCP 콘솔에서 실시간으로 array 늘어남 확인
- [ ] `updated_at` 필드가 매 라운드마다 새 timestamp

### Task 9.1 — Mediator Agent + Phoenix MCP introspection (스켈레톤)

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> ARCHITECTURE.md 2.4 명세대로 Mediator 작성.
> 단, Phoenix MCP 통합은 Day 12에 추가하므로 지금은 mock으로 `query_past_debates`를 placeholder로 두기.
> 합의안 + priority_actions + disclaimer 출력.

**Acceptance Criteria**:
- [ ] 두 에이전트 토론 + pose_data 받아서 합의안 생성
- [ ] disclaimer 필드 누락 없음 (P5 절대원칙)
- [ ] Encourager의 actionable_tip과 Scrutinizer의 required_action을 둘 다 반영

### Task 9.2 — End-to-end 첫 dry run

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> `python agents/orchestrator.py --video data/sample_videos/squat_001.mp4` 명령으로 전체 파이프라인 실행.
> 출력은 콘솔 + Firestore에 debate 문서 저장.
> Phoenix Cloud trace 확인.

**Acceptance Criteria**:
- [ ] 영상 → PoseExtractor → 2 에이전트 토론 → Mediator → Firestore + Phoenix 까지 모두 동작
- [ ] 총 시간 60초 이내

---

## 🚨 마일스톤 체크포인트 — 6/5 (Day 9 종료) End-to-End Skeleton 마감

이 시점까지 **반드시** 동작해야 하는 것:
- [ ] 사용자 영상 1개로 MediaPipe → Gemini → Encourager → Scrutinizer → Mediator → Firestore + Phoenix trace 까지 일관 동작
- [ ] 명세 JSON 스키마 전부 통과
- [ ] 의료 면책 (P5) 출력

**미달 시 즉시 컷 우선순위** (TASKS.md 마지막 가이드와 동일):
1. ✂️ Vertex AI Vector Search → Firestore 단순 조회로 대체
2. ✂️ Multi-round 토론 → 1 라운드 + Mediator만
3. ✂️ Self-improvement loop의 before/after 시각화 → 텍스트 비교 표만

**컷 금지** (P1-P5는 절대):
- Phoenix 자동 계측, 두 에이전트, 사용자 피드백 반영, Phoenix MCP introspection, 의료 면책

End-to-end가 안 되면 그 다음 Day는 새 기능 추가 금지, **정확도·UI·영상에만 집중**.

---

## DAY 10-11 — Memory (Firestore CRUD + Vector Search 검색)

### Task 10.1 — Firestore CRUD 완성

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> `storage/firestore_client.py` 완성. ARCHITECTURE.md 3.1 모든 컬렉션의 CRUD 함수.
> 트랜잭션이 필요한 경우(persona_state 업데이트) batch 처리.

### Task 11.1 — Vector Search 통합 + Mediator의 사용

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> Mediator가 `vector_search.search_similar_debates()`를 호출해서 과거 합의 패턴을 컨텍스트로 받게.
> 단, 이건 Phoenix MCP introspection과는 별개의 layer (벡터 검색 vs trace 쿼리는 다른 정보).

**Acceptance Criteria**:
- [ ] 같은 사용자가 비슷한 운동을 다시 업로드하면 Mediator 출력의 `past_debate_references` 채워짐

---

## DAY 12 — ⭐ Phoenix MCP Introspection (1등 결정 요소)

### Task 12.1 — 커스텀 MCP wrapper server 작성

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> ARCHITECTURE.md 5.2 대로 커스텀 MCP server 작성.
> 파일: `mcp/phoenix_mcp_server.py`
> SDK: Python `mcp` 패키지 (FastMCP)
>
> 노출 tool 2개:
>   - `query_past_debates(user_id, exercise_type, limit=5)` → Phoenix REST API로 사용자 trace 검색 + Firestore consensus 데이터 join
>   - `query_similar_safety_flags(safety_flag_name, limit=10)` → Vector Search + Phoenix trace 조합
>
> 로컬 dev: stdio transport로 subprocess 실행
> 환경변수 `PHOENIX_MCP_TRANSPORT=stdio|http`로 전환 가능하게

**참고**: ARCHITECTURE.md 5번 + Phoenix REST API 문서 (https://arize-phoenix.readthedocs.io/)

**Acceptance Criteria**:
- [ ] MCP server를 stdio로 실행 → 도구 2개가 list 됨
- [ ] `query_past_debates("user_001", "squat")` → JSON 결과 반환
- [ ] Phoenix REST API 호출 실패 시 fallback (Firestore 단독 조회 + 경고 trace)

### Task 12.2 — ADK Mediator에 MCP tool 연결

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> Task 12.1의 MCP server를 ADK의 tool 시스템으로 Mediator에 노출.
> Mediator의 system prompt 업데이트해서 도구 사용을 명시.
> Gemini가 자동으로 도구를 호출하는지 trace로 검증.

**Acceptance Criteria**:
- [ ] Mediator 응답 trace에 MCP tool call이 명시적으로 보임 (Phoenix span 트리에 표시)
- [ ] 호출 결과가 Mediator의 최종 응답에 반영됨
- [ ] `past_debate_references`에 실제 trace ID가 채워짐

### Task 12.3 — MCP server Cloud Run 배포 준비

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> ARCHITECTURE.md 5.3대로 MCP server의 HTTP transport 모드 추가.
> 파일: `mcp/Dockerfile` (메인 앱과 별도 컨테이너).
> Day 14에 `cd mcp && gcloud run deploy formforge-mcp --source .` 실행 예정.
>
> Fallback 로직: 메인 앱에서 MCP 호출 실패 시 Firestore 직접 조회 + Phoenix에 경고 span 기록.

**Acceptance Criteria**:
- [ ] `docker build mcp/` → 컨테이너 빌드 성공
- [ ] 컨테이너 실행 시 HTTP MCP endpoint 노출
- [ ] 메인 앱에서 `MCP_SERVER_URL=http://localhost:8765`로 호출 성공
- [ ] MCP 다운 시뮬레이션 → Fallback 동작, 앱은 죽지 않음

---

## DAY 13 — ⭐⭐ Self-Improvement Loop (1등 결정 요소)

### Task 13.1 — 사용자 피드백 수집 UI 셋업

**작업자**: Claude Code (UI 부분은 Day 14 Streamlit에서)

지금은 backend 함수만:
**Claude Code에게 줄 지시문**:
> `evals/feedback_handler.py` 작성. ARCHITECTURE.md 6.2 알고리즘 + 6.1의 양방향 피드백 옵션 그대로.
> 사용자가 피드백을 POST하면 → Firestore 저장 → LLM-as-a-Judge 호출 → 페르소나 state 업데이트.
>
> 피드백 enum (반드시 ARCHITECTURE.md 6.1과 일치):
>   - Encourager: `too_warm` | `perfect` | `too_cold`
>   - Scrutinizer: `too_harsh` | `perfect` | `too_soft`
>   - Mediator: int 1-5

### Task 13.2 — LLM-as-a-Judge 구현

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> `evals/llm_judge.py` 작성. ARCHITECTURE.md 6.3 prompt 템플릿 사용.
> **모델은 `gemini-3.5-flash` (stable)** — 시스템 전체에서 Gemini 3 family를 한 곳 명시적으로 채택해 "최신 모델 활용" 시그널 확보 (DEVPOST/README의 Built With에 명기).
> 결과를 Phoenix에 eval로 logging.

**Acceptance Criteria**:
- [ ] 피드백 "too_harsh" 1번 → scrutinizer.harshness 0.5 → 0.35
- [ ] 피드백 "too_soft" 1번 → scrutinizer.harshness 0.5 → 0.6 (양방향 검증)
- [ ] 피드백 "perfect" → 변화 없음 (anchor)
- [ ] 다음 토론에서 Scrutinizer 톤 명백히 부드러워짐/날카로워짐 (사용자 검증)
- [ ] Phoenix Cloud의 evals 탭에 결과 표시

### Task 13.3 — Before/After 시각화 (데모 영상용)

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> "2주 시뮬레이션" 기능. 같은 영상을 2번 분석 (피드백 사이클 후) → 두 결과를 나란히 보여주는 비교 화면 생성.
> 파일: `ui/components/before_after_view.py`
> 데모 영상에서 self-improvement loop 증명용.

**Acceptance Criteria**:
- [ ] 사용자가 피드백 후 다시 분석 → 톤 변화가 시각적으로 명백
- [ ] 두 결과를 옆에 놓고 비교 가능

---

## DAY 14 — UI 완성 + Cloud Run 배포

### Task 14.1 — Streamlit 메인 앱

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> `ui/streamlit_app.py` 메인 앱.
> 화면 구성:
>   1. 영상 업로드 (drag & drop)
>   2. 운동 타입 선택 (squat/deadlift/pushup)
>   3. "Start Debate" 버튼 → orchestrator 호출
>   4. **두 코치 카드 좌우 배치** (Encourager 좌, Scrutinizer 우)
>   5. `streamlit-autorefresh`로 Firestore 문서 1초 폴링 → 라운드 메시지 표시 (⚠️ `on_snapshot()` 콜백 금지 — ARCHITECTURE.md 3.2 참조)
>   6. Mediator 합의 카드 (하단 중앙)
>   7. Phoenix trace 시각화 (사이드바, ARCHITECTURE.md 9번 영상 시나리오)
>   8. 피드백 폼 (3개 라디오 + 자유 텍스트)
> 디자인 키: 5초 안에 "두 코치 토론"임을 알 수 있게.

### Task 14.2 — 데모 페이지 (피드백 전후 비교)

**작업자**: Claude Code

`ui/components/before_after_view.py`를 메인 앱에 통합.

### Task 14.3 — Cloud Run 배포 (메인 앱 + MCP server 2개 서비스)

**작업자**: Claude Code + 사용자

**Claude Code에게 줄 지시문**:
> 2개 Cloud Run 서비스 배포 (ARCHITECTURE.md 5.3 참조):
>
> **(1) 메인 앱** (`deploy/Dockerfile` — Python 3.11 slim + Streamlit + MediaPipe + 의존성)
>   - 명령: `gcloud run deploy formforge-ai --source . --region us-central1 --allow-unauthenticated --min-instances=1 --memory=2Gi --timeout=300`
>   - `--min-instances=1`: 콜드 스타트 제거 (소량 비용 발생, 데모 안정성 우선)
>
> **(2) MCP server** (Task 12.3의 `mcp/Dockerfile`)
>   - 명령: `cd mcp && gcloud run deploy formforge-mcp --source . --region us-central1 --no-allow-unauthenticated`
>   - 메인 앱에서 `MCP_SERVER_URL` 환경변수로 접근
>
> 환경 변수는 Secret Manager로 안전하게 (Phoenix API key, GCP service account JSON 등).

**Acceptance Criteria**:
- [ ] 메인 앱 공개 URL 발급 (예: `https://formforge-ai-xxx.run.app`)
- [ ] MCP server 내부 URL 발급 (메인 앱만 접근 가능)
- [ ] 다른 컴퓨터에서 접속해도 정상 동작
- [ ] 첫 응답 latency: 콜드 스타트 ~0초 (min-instances=1 효과) + 분석 60초 이내
- [ ] MCP server 다운 시뮬레이션 → 메인 앱은 fallback 모드로 계속 동작

---

## DAY 15 — Demo Video + GitHub + Devpost 제출 (6/11 안에 완료)

### Task 15.1 — 본인 영상 촬영 (반나절)

**작업자**: 사용자

**Steps**:
1. 본인 운동 영상 3-5개 촬영 (다양한 운동·자세)
2. 의도적으로 일부 잘못된 자세 1-2개 포함 (데모용)
3. Cloud Storage 업로드

### Task 15.2 — 3분 데모 영상 제작

**작업자**: 사용자

**스토리보드**: ARCHITECTURE.md 9번 표 따라 정확히.

**촬영 도구**: OBS Studio (무료) + iMovie/Premiere Pro

**Acceptance Criteria**:
- [ ] 3분 이내 (3분 1초도 잘림)
- [ ] 영어 자막 (또는 영어 내레이션)
- [ ] YouTube unlisted로 업로드, Devpost에 링크
- [ ] ARCHITECTURE.md 9번 표의 모든 시각화 포함

### Task 15.3 — GitHub README 완성

**작업자**: Claude Code

**Claude Code에게 줄 지시문**:
> 영어 README 완성.
> 섹션: Project Title, Demo Video, Live URL, **Hackathon Compliance**, What it does, Tech Stack, Architecture diagram (ASCII), Setup, License (MIT).
> CLAUDE.md, ARCHITECTURE.md, TASKS.md 링크 포함.
>
> **🚨 "Hackathon Compliance" 섹션 필수 포함 (룰 충족 증명)**:
> ```markdown
> ## Hackathon Compliance — Google Cloud Rapid Agent Hackathon
>
> - **Agent Builder**: Built with Google ADK (the official open-source Agent Development Kit of Google Cloud Agent Builder), deployed on Cloud Run (an Agent Builder-supported runtime).
> - **Powered by Gemini**: `gemini-2.5-pro` (multimodal video — Encourager/Scrutinizer/Mediator/PoseExtractor Stage 2), `gemini-2.5-flash` (auxiliary), `gemini-3.5-flash` (LLM-as-a-Judge).
> - **Partner MCP**: Arize Phoenix MCP — custom `mcp/phoenix_mcp_server.py` (FastMCP) wrapping Phoenix REST API + Firestore + Vector Search; the Mediator agent calls `query_past_debates` and `query_similar_safety_flags` for self-introspection.
> - **Track**: Arize.
> ```

**Acceptance Criteria**:
- [ ] About 섹션에 MIT License 자동 표시 (GitHub UI)
- [ ] README 5분 이내에 readable
- [ ] Live URL과 영상 링크가 최상단에
- [ ] **"Hackathon Compliance" 섹션이 최상단 3블록 내 위치** (심사위원 5초 확인용)

### Task 15.4 — Devpost 제출 페이지 작성

**작업자**: 사용자

**Steps**:
1. https://rapid-agent.devpost.com 에서 "Submit" 페이지
2. 입력 항목:
   - Project name: **FormForge AI**
   - Tagline: *Two AI coaches debate your workout form in real-time, then learn from your feedback.*
   - Inspiration, What it does, How we built it, Challenges, What we learned, What's next
   - Built With: Google ADK (the official open-source framework of Google Cloud Agent Builder), Gemini 2.5 Pro, Gemini 2.5 Flash, Gemini 3.5 Flash, Arize Phoenix, Arize Phoenix MCP (custom FastMCP server), Firestore, Vertex AI Vector Search, Streamlit, Cloud Run
   - **Track 선택**: Arize
   - **첫 문단에 룰 충족 한 줄 명시**: "Built with **Google Cloud Agent Builder** (via Google ADK + Cloud Run), powered by **Gemini** (2.5 Pro / 2.5 Flash / 3.5 Flash), integrating the **Arize Phoenix MCP** partner server."
   - 영상 URL, GitHub URL, Live URL

**마감**: 2026-06-12 06:00 KST (반드시 그 전에)

---

## 🆘 막혔을 때 가이드

### 에러 패턴별 대응

| 에러 | 원인 비유 | 1차 대응 |
|---|---|---|
| `phoenix.connection_error` | 전화 끊김 | API key, endpoint URL 재확인 |
| `ADK agent timeout` | 식당 주문이 너무 늦음 | model을 flash로 다운그레이드 |
| `Firestore PermissionDenied` | 문 잠김 | 서비스 계정 권한 재확인 |
| `Vertex AI quota exceeded` | 한도 초과 | GCP 콘솔에서 quota 확인, region 변경 |
| `Cloud Run deploy fail` | 짐 너무 큼 | Dockerfile 경량화, requirements.txt 정리 |

### 일정 지연 시 우선순위

만약 시간이 부족하면 **이 순서로 cut**:
1. ✂️ Cut: Vertex AI Vector Search (Mediator에서 빼고 Firestore만)
2. ✂️ Cut: Multi-round 토론 (1 라운드 + Mediator만)
3. ❌ **절대 cut 금지**:
   - Phoenix 자동 계측 (P1)
   - 두 에이전트 (P2)
   - Self-improvement loop (P3)
   - Phoenix MCP introspection (P4)
   - 면책 (P5)

---

## ✅ 최종 체크리스트 (6/11 제출 전)

- [ ] Live URL 동작 (다른 사람도 접속 가능)
- [ ] GitHub repo MIT 라이선스 표시
- [ ] 3분 영상 YouTube unlisted 업로드
- [ ] 데모 영상에 ARCHITECTURE.md 9번 표 모든 항목 포함
- [ ] Devpost 모든 필드 작성
- [ ] **Track: Arize 선택**
- [ ] 영어 자막/내레이션
- [ ] 면책 모든 곳에 표시
- [ ] Phoenix Cloud trace가 데모 영상에 보임
- [ ] Phoenix MCP tool call이 trace에 보임
- [ ] Self-improvement loop가 데모에서 증명됨

이 모두 완료되면 Arize 트랙 1등 후보입니다. 🚀
