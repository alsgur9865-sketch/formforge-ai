# Design System — FormForge AI

> **"The Diagnostic Freeze-Frame"**
> 시각·UI 결정의 단일 진실원(source of truth). 코드를 짜기 전, UI를 만지기 전 반드시 이 파일을 읽는다.
> 값은 정확한 hex·폰트명·px로 명시 — "modern", "어두운 파랑" 같은 모호한 표현 금지.

---

## 0. Product Context

- **무엇**: 운동 영상을 두 AI 코치(The Encourager · The Scrutinizer)가 실시간 토론하고 The Mediator가 종합하는 폼 코칭 도구. 사용자 피드백으로 페르소나가 진화.
- **누구**: 1차 = **해커톤 심사위원**(3분 데모 영상 + Live URL), 2차 = 홈피트니스 사용자.
- **공간**: Google Cloud Rapid Agent Hackathon — Arize 트랙. Design은 4대 심사 기준 중 하나.
- **타입**: Streamlit 실시간 대시보드(폴링 1s). 데이터 시각화 + 라이브 토론 + 진단 이미지.
- **최적화 대상**: 심사위원 우선(데모 드라마), 단 의료 인접 제품의 **신뢰감 바닥선** 유지.

---

## 1. Aesthetic Direction

- **방향**: The Diagnostic Freeze-Frame — 영웅은 **영상 프레임 위에 스켈레톤 + 플래그된 각도가 얹힌 사용자의 몸**(rep 바닥 순간의 진단 정지화면). 두 코치는 **멈춘 split이 아니라 하나의 격해지는 피드**로 같은 몸을 두고 갈리고, 화면이 그 긴장을 하나의 판결로 닫는다.
- **미감 리믹스**: Linear의 다크 엔지니어링 절제 × 스포츠과학 방송 계기판 × 법정의 검사 vs 변호인 공간 논리. → 진지한 다크 기술 베이스(신뢰) 위에 대립의 드라마(데모 wow).
- **무드**: "어두운 체육관에서 촬영된 한 프레임이 정밀 진단된다." 크립토 대시보드가 아니라 스포츠과학 랩 리포트.
- **장식 레벨**: intentional — 비네트·바닥 그림자·미세 텍스처. 빛나는 카드·보라 그라데이션·장식 blob 금지.
- **핵심 원칙 (절대)**:
  - **색은 의미에 묶인다.** 헤드라인 색은 페르소나 장식(amber/teal)이 아니라 **몸 위 risk(빨강)/good(초록)**. 페르소나 hue는 "누가 말하나"만 표시하는 2차.
  - **대립은 몸 위에서 벌어진다.** Scrutinizer의 지적 = 몸 위 빨간 플래그, Encourager의 칭찬 = 초록 마커. 둘이 같은 신체 지점을 가리킨다.
  - **토론은 시간(피드)이지 공간(고정 split)이 아니다.** Round가 격화되는 단일 스레드.

### Anti-slop (이 시스템에서 금지)
- 보라/바이올렛 그라데이션 액센트 · 아이콘 든 3컬럼 피처 그리드 · 전부 가운데 정렬 · 모든 요소 균일 버블 radius · 그라데이션 CTA 버튼 · 제네릭 히어로 · Inter/Roboto/Arial(아래 폰트 외) · **기본 MediaPipe 드로잉(졸라맨) 포즈 오버레이**.

---

## 2. Typography

폰트가 곧 캐릭터. 셋 다 무료, CSS `@import` 로딩.

| 역할 | 폰트 | weight | 용도 |
|---|---|---|---|
| **Display** | `Cabinet Grotesk` (Fontshare) | 700 / 800 | 워드마크, 섹션 헤드, 판결(VERDICT) 라벨, tale-of-the-tape, 큰 숫자 |
| **Body / UI / Data** | `Geist` (Google Fonts) | 400 / 500 / 600 | 본문, 버블, 버튼, 라벨, 수치(`font-variant-numeric: tabular-nums`) |
| **Mono / Clinical** | `Geist Mono` (Google Fonts) | 400 / 500 | **Scrutinizer 임상 수치, 몸 위 각도 주석, trace span 라벨, 타임코드** |

- **로딩 (Streamlit)**: 앱 상단에서 `st.markdown("<style>@import url(...)</style>", unsafe_allow_html=True)` 1회 주입.
  - Geist · Geist Mono: `https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap`
  - Cabinet Grotesk: `https://api.fontshare.com/v2/css?f[]=cabinet-grotesk@700,800&display=swap`
  - fallback: `'Geist', system-ui, sans-serif` / `'Geist Mono', monospace`.
- **스케일 (16px base)**:
  | level | size | line | weight |
  |---|---|---|---|
  | display | 40px (2.5rem) | 1.02 | 800 |
  | h2 | 28px | 1.1 | 700 |
  | h3 | 20px | 1.2 | 700 |
  | body | 15px | 1.55 | 400/500 |
  | small | 13px | 1.5 | 400 |
  | micro | 11px | — | 500, `text-transform:uppercase; letter-spacing:.10em` (mono) |

---

## 3. Color

**위계**: 다크 베이스 → 몸 위 의미색(1차) → 페르소나 hue(2차) → Mediator 그라데이션(종합).

### Dark (primary 테마)
```
--bg-base:    #0B0E14   /* 순흑 아님. 깊은 블루-차콜 계기판 */
--bg-surface: #141A24   /* 패널 */
--bg-elevated:#1A2230   /* 띄운 면, 중앙 무대 */
--hairline:   #222C3A   /* 1px 보더 */
--strong:     #2E3A4D   /* 강조 보더, 인풋 */
--text:       #E6EAF2   /* 기본 텍스트(쿨 오프화이트) */
--muted:      #8A93A6
--faint:      #586073
```

### 의미색 (PRIMARY — 몸 위 플래그 + 배지)
```
--risk:    #FF5C5C   /* 부상 위험 / Scrutinizer 플래그 / P5 안전 */
--good:    #3DDC84   /* 안전 / 칭찬 / 합격 */
--caution: #FFC24B   /* 주의(tempo 등) */
```

### 페르소나 hue (SECONDARY — 아바타·버블 좌측 보더·이름색만. 면 채움 금지)
```
--enc: #F4A340   /* The Encourager (warm) */
--scr: #34D1C4   /* The Scrutinizer (cool) */
```

### Mediator 종합 (두 색의 *문자 그대로의* 블렌드 — 헤어라인/보더에만)
```
mediator-accent: linear-gradient(90deg, #F4A340, #34D1C4)
```

### 진단 뷰어 (포즈 영웅 — 테마 무관 **항상 다크**, X-ray 라이트박스 컨셉)
```
viewer-bg:      #080B11
body-fill:      linear-gradient(90deg, #161B23, #36404E 48%, #1A2029)  /* 부피감 */
body-rim:       #5A6B7E (opacity .4)   /* 림 라이트 */
track-node:     #D8F6F4   /* 관절 노드 코어 */
track-glow:     #34D1C4 (alpha ~.18)   /* 노드 글로우 */
track-bone:     #9FB6CC (opacity ~.30) /* 미세 연결선 */
```

### Light (리포트 변형 — 진단 뷰어는 다크 유지)
```
--bg-base:#F4F6FB --bg-surface:#FFFFFF --bg-elevated:#FFFFFF
--hairline:#E3E8F0 --strong:#CDD5E0
--text:#10151F --muted:#5C6678 --faint:#9AA3B2
--enc:#C9781A --scr:#0E9E92 --risk:#D8443D --good:#1E9E5A --caution:#C98A12
```
- **다크모드 전략**: 다크가 메인. 라이트는 인쇄/리포트용 보조. 라이트에선 의미색을 한 단계 진하게(대비 확보). **진단 뷰어 프레임만은 두 테마 모두 다크.**

---

## 4. Spacing

- **base**: 4px. 리듬: 8px.
- **density**: comfortable-compact (데이터 밀도 ↑이지만 프리미엄).
- **scale**: `2xs 2 · xs 4 · sm 8 · md 12 · lg 16 · xl 24 · 2xl 32 · 3xl 48 · 4xl 64`

---

## 5. Layout

- **Streamlit wide mode**, max content width ~**1320px**.
- **시그니처 화면 (Debate)**:
  - tale-of-the-tape 헤더: 운동명(Cabinet Grotesk) · set/rep/무게(mono) · tension meter(좌 enc ↔ 우 scr, 바늘) · round pill.
  - 본문 `st.columns([1.05, 0.95])`:
    - **좌 = 진단 프리즈프레임(영웅)** — `st.image(signed_url)` (영상 프레임 위 오버레이, §8 스펙).
    - **우 = 격해지는 토론 피드** — 단일 스레드, Round divider로 격화. 각 발언에 `→ 몸 플래그` 칩.
  - 하단 = **Mediator 판결 카드**(중앙, max 760px, amber→teal 그라데이션 헤어라인) → 체크리스트 + Phoenix MCP 회상 줄 + 면책.
  - **Phoenix trace strip**: 가로 span 워터폴(PoseExtractor→Encourager∥Scrutinizer→Mediator), 브랜드 색. 숨기지 않는 1급 요소.
  - **Calibration row**: too harsh / perfect / too soft + 페르소나 드리프트 표시.
- **Border radius (계층, 균일 버블 금지)**: `panel 12 · card/button 8 · badge/input 6 · status pill 999`. 크리스프 코너 = 엔지니어링.
- **반응형**: 데모는 데스크톱 기준. <900px에서 컬럼을 세로 스택.

---

## 6. Motion (Streamlit rerun-safe)

- 1초 폴링 rerun과 싸우지 않는다. **CSS-only 경량, 무한 애니메이션 금지**(rerun마다 리셋되어 jank).
- 신규 메시지: `fade + translateY(8px→0)`, 200ms ease-out.
- active/강조 상태: **정적 box-shadow**(펄스 X).
- tension meter 바늘: `transition: left 280ms ease-in-out`.
- **duration**: micro 80 · short 180 · medium 280ms. **easing**: enter `ease-out`, move `ease-in-out`.

---

## 7. Streamlit 구현 노트

- 커스텀 CSS는 앱 상단 `st.markdown("<style>…</style>", unsafe_allow_html=True)` 1회 주입(토큰 = CSS 변수).
- 버블/판결/배지 = `st.markdown` HTML 블록 + 토큰 클래스.
- 폴링은 **`streamlit-autorefresh` 1초** (Firestore `on_snapshot()` 콜백 금지 — rerun 모델과 충돌. CLAUDE.md §4 준수).
- 포즈 영웅 = `st.image(signed_url)` (서버사이드 cv2/PIL 렌더 결과, §8).
- 데모 청결: Streamlit 기본 메뉴/푸터 CSS로 숨김(`#MainMenu`, `footer`).

---

## 8. Pose Overlay Render Spec (PRODUCTION — 졸라맨 방지 계약)

> 영웅 비주얼. 서버사이드 cv2/PIL로 **실제 영상 keyframe(rep 바닥) 위에** 그려 GCS 업로드 → signed URL → `st.image`.
> 코드-탐색 실사 결과 경로: `_extract_keyframes()`(존재) + `FrameMetrics`에 관절 좌표 보존(~20줄 추가) + 드로잉 함수 + GCS 업로드 + Firestore `keyframe_urls` 필드.

**절대 규칙: `mp.solutions.drawing_utils.draw_landmarks()` 기본 스타일(초록 선+흰 점) 사용 금지.** 아래 스펙으로 직접 그린다.

- **베이스**: 진짜 영상 프레임 위(빈 배경 금지). 미세 다크 비네트 + 좌하단 타임코드/운동명(Geist Mono, 저대비).
- **스켈레톤 = 트래킹 오버레이**(불투명 막대 아님):
  - 뼈(연결선): 두께 2px, `#9FB6CC` @ opacity ~.30, `cv2.LINE_AA`. 진짜 몸이 비쳐 보이게.
  - 관절 노드: 코어 원 r4 `#D8F6F4` + 글로우 링 r7 `#34D1C4` @ alpha ~.18(레이어드 알파 또는 소프트 블러).
- **플래그 관절 (risk)**: 노드 `#FF5C5C` r6 + 헤일로 r11 @ ~.22. 관절 각도호 `#FF5C5C` 1.6px. 선택: "ideal alignment" 점선(hip→ankle) `#FF5C5C` @ .5.
- **good 마커**: 해당 관절에 링 `#3DDC84` 2px.
- **라벨**: **PIL로 Geist Mono ttf 렌더**(cv2.putText는 폰트 빈약). `KNEE VALGUS 14.2°` → `#FF5C5C`, `DEPTH 92° ✓` → `#3DDC84`. 프레임 크기 비례, 리더선으로 관절 연결.
- **출력**: JPEG/PNG → GCS `debates/{id}/keyframes/rep_{n}.jpg` → signed URL.
- **느낌 목표**: "졸라맨 낙서"가 아니라 "진짜 사람 몸이 모션캡처 트래킹되는 진단 화면". 뼈는 은은하게, **플래그된 각도만 크고 강하게**.

---

## 9. 절대 원칙(P1–P5) → 디자인 책임 매핑

| 헌법 원칙 | 이 시스템에서의 구현 |
|---|---|
| **P1** Phoenix 자동 계측 | Live Agent Trace strip(span 워터폴)을 1급 UI로 노출 |
| **P2** 두 에이전트 통신 | 격해지는 단일 토론 피드 + 발언별 `→ 몸 플래그` 칩 |
| **P3** 피드백 → 페르소나 진화 | Calibration row(too harsh/perfect/too soft) + 페르소나 드리프트 표시 |
| **P4** Mediator의 Phoenix MCP introspection | 판결 카드의 "⟲ 과거 세션 N건 회상" 줄 |
| **P5** 의료/부상 면책 | **모든 결과**에 판결 카드 하단 면책 푸터(muted). 누락 금지 |

---

## 10. Decisions Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-06-05 | 초기 디자인 시스템 생성 (`/design-consultation`) | redesign-ui 브랜치, UI 백지 재설계 |
| 2026-06-05 | 최적화 대상 = 심사위원(데모 드라마), 신뢰감 바닥선 유지 | 해커톤 1등 목표 + 의료 인접 |
| 2026-06-05 | v1 "Debate Control Room"(고정 split + 영상 placeholder) **폐기** | 3대 비판: ①가장 강한 자산(몸)을 묻음 ②멈춘 split이 토론 드라마 죽임 ③amber/teal 클리셰 |
| 2026-06-05 | 방향 전환 → **"The Diagnostic Freeze-Frame"** (몸=영웅, 단일 격해지는 피드, 색=의미) | 첫 원칙 재추론 |
| 2026-06-05 | 코드 실사로 포즈 오버레이 실현성 확인 (YES-with-work) | `_extract_keyframes` 존재, 좌표 보존 ~20줄, 패턴 이미 있음 |
| 2026-06-05 | 몸 렌더 = 부피 있는 실루엣 + 트래킹 오버레이(졸라맨 금지), §8 프로덕션 스펙 박음 | 기본 MediaPipe 드로잉은 싸구려·이해도 저하 |

---

> **다음 단계(구현 시)**: ① DESIGN.md대로 Streamlit CSS 주입 → ② 시그니처 화면 빌드 → ③ 실제 영상으로 §8 포즈 오버레이 렌더 폴리시 → ④ 라이브 앱 시각 리뷰(`/design-review`).
> `design-preview.html`은 방향 합의용 일회 목업 — 구현 후 삭제 가능.
