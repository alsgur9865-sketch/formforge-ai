# FormForge AI — 진행사항

> 세션 간 핸드오프 문서. 다음 세션 시작 시 이 파일부터 읽기.

**최종 갱신**: 2026-05-28
**현재 단계**: 계획 문서 v3 확정 (대회 룰 재검증 완료). Day 1 작업 착수 가능 상태.

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

## ⏭️ 다음 세션 시작 시 할 일

1. **이 파일 먼저 읽기**
2. **사용자 Task 1.1/1.2/1.5 완료 여부 확인**
3. 완료 시: Task 1.4 (Hello World) 즉시 진행 → Phoenix Cloud trace 1개 확인
4. 샘플 영상 + 패키지 설치 완료 시: Task 1.6 실행 검증 (`python agents/pose_mediapipe.py data/sample_videos/squat_demo.mp4`)
5. **(선택) 5/29 02:00 KST Phoenix MCP 5분 라이브 세션 녹화 시청** — 트랙 이해도 +

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
| Foundation | 1-2 (5/28-29) | 환경 셋업, 자동 계측 hello world, MediaPipe 스모크 | ⏭️ |
| Skeleton | 3-4 (5/30-31) | 두 에이전트 + Pose Extractor 기본 | ⏭️ |
| Multi-modal Core | 5-7 (6/1-3) | 2-stage PoseExtractor 완성 | ⏭️ |
| Adversarial Debate | 8-9 (6/4-5) | 토론 로직 + Mediator | ⏭️ |
| **🚨 마일스톤** | **9 종료 (6/5)** | **End-to-end skeleton 마감일** | ⏭️ |
| Memory | 10-11 (6/6-7) | Firestore + Vector Search | ⏭️ |
| Introspection | 12 (6/8) | Phoenix MCP 커스텀 wrapper | ⏭️ |
| Self-Improvement | 13 (6/9) | LLM-as-a-Judge + 양방향 학습 | ⏭️ |
| UI + Deploy | 14 (6/10) | Streamlit + Cloud Run 듀얼 배포 | ⏭️ |
| Submit | 15 (6/11) | 영상 + Devpost | ⏭️ |

**최종 마감**: 2026-06-12 06:00 KST (= 6/11 안에 모든 제출 완료)
