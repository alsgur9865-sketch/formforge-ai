<!--
사용법 (MIN 전용 — 제출 시 이 주석은 빼고 칸별로 복붙):
  Devpost 프로젝트 페이지의 각 칸(Inspiration / What it does / ...)에 아래 같은 제목 섹션을 그대로 붙이세요.
  "Built With" 의 필수 wording 은 룰 충족용이니 토씨 바꾸지 말 것.
  영상 링크는 업로드 후 채우기 (지금은 TODO).
-->

# FormForge AI — Devpost Submission Draft

**Tagline:** Two AI coaches argue about your workout form in real time — and learn *your* taste over time.

- **Live demo:** https://formforge-app-988838927510.us-central1.run.app
- **Repo:** https://github.com/alsgur9865-sketch/formforge-ai
- **Demo video:** _TODO — 업로드 후 링크_ (제약: ≤3분 · YouTube/Vimeo 공개 · 영어 자막 필수 — 아래 내부 체크리스트)
- **Hackathon / Track:** Google Cloud Rapid Agent Hackathon — **Arize Track**

<!-- ⛔ 아래 "내부 체크리스트" 섹션은 MIN 전용 — Devpost 폼/페이지에 절대 붙이지 말 것 -->

## ⛔ 내부 체크리스트 (Devpost에 붙이지 말 것) — 공식 룰 대조 2026-06-05

> 출처: rapid-agent.devpost.com/rules (2026-06-05 확인). **마감: 2026-06-11 14:00 PDT = 2026-06-12 06:00 KST.**

**데모 영상 — 공식 제약 (필수):**
- ⏱ **최대 3분** — 3분 넘는 부분은 심사 제외. 핵심을 3분 안에 압축.
- 📺 **YouTube 또는 Vimeo**, **공개(public)** 호스팅.
- 🗣 **영어 또는 영어 자막 필수** — 한국어 내레이션이면 **영어 자막 반드시** 삽입.
- 🚫 타사 로고·광고·후원 표시 금지. 플랫폼에서 **실제 작동하는 모습** 포함.
- 원본·미공개 영상, 모든 IP 권리 준수.

**Stage One = Pass/Fail 게이트 (하나라도 빠지면 심사 진입 자체 실패):**
- [x] Hosted Project URL — Cloud Run `https://formforge-app-988838927510.us-central1.run.app`
- [x] 공개 repo + 라이선스 **상단 노출** — GitHub + MIT (GitHub About 표시 최종 확인)
- [x] Text Description (기능·기술·데이터소스·findings/learnings) — **이 문서 본문**
- [ ] **3분 데모 영상** (위 제약 준수) — ⚠️ **유일한 미완**
- [ ] Devpost 폼 제출 + **트랙 = Arize** 선택
- [x] 필수 기술 — Agent Builder(ADK) + Gemini + **Arize Phoenix MCP** + 전부 Google Cloud (경쟁 클라우드·타 AI 없음)

---

## Inspiration

Most AI form-check apps give you a single, confident verdict — and confidence is exactly the problem. Real coaching is a *negotiation* between encouragement and rigor: a good PT keeps you motivated, while a sharp physiologist won't let a dangerous habit slide. We wanted that tension to be *visible*, not flattened into one bland answer.

And we wanted to prove a harder claim: that an agent can genuinely **learn an individual user's coaching style** — not just say it does, but show it with numbers.

## What it does

You upload a short workout video. FormForge runs a **multi-agent debate**:

- **The Encourager** (warm certified PT, 10 years) finds what you did well and proposes one next step.
- **The Scrutinizer** (rigorous exercise physiologist, PhD) hunts for injury risk and biomechanical flaws, grounded in measured joint angles and tempo.
- The two **debate in real time** — agreeing, pushing back, standing their ground.
- **The Mediator** (Head Coach) synthesizes both sides *with your past training context*, retrieved at runtime through the **Arize Phoenix MCP** server, into a balanced verdict with prioritized action items.

Then you react (`too harsh`, `too soft`, `perfect`, or free text). An **LLM-as-a-Judge** evaluates the debate and the personas **evolve bidirectionally**. Over time, the two coaches become *your* personal critic pair.

## How we built it

Built with **Google ADK** (the official open-source framework of Google Cloud Agent Builder) and deployed on **Cloud Run** (an Agent Builder-supported runtime), powered by **Gemini 2.5 Pro / 2.5 Flash and Gemini 3.5 Flash**, with the **Arize Phoenix MCP** partner server for agent self-introspection.

- **Orchestration:** ADK hierarchical multi-agent (parallel debate rounds + convergence detection + mediator synthesis).
- **Multi-modal × multi-agent:** one video, multiple lenses — a **2-stage PoseExtractor** uses **MediaPipe** to *measure* joint angles/tempo and **Gemini 2.5 Pro** to *interpret* them, so the LLM never fabricates precise numbers (no false precision).
- **Self-introspection (MCP):** a custom **FastMCP** server wraps the Phoenix REST API + Firestore; the Mediator autonomously calls `query_past_debates` and `query_similar_safety_flags` to pull the user's own history.
- **Observability:** Arize Phoenix Cloud auto-instruments every agent — the full debate, the convergence judge, and the MCP tool calls all show up as a traced tree.
- **Self-improvement, measured:** we built a **Phoenix Datasets & Experiments** pipeline that runs the *same* set of debate scenarios under the baseline persona (v1) vs. the evolved persona (v3) and scores them with two evaluators.
- **Stack:** Firestore (1s polling UI), Vertex AI Vector Search (`multimodalembedding-001`), Streamlit, Cloud Storage.

## Accomplishments that we're proud of

**We didn't *claim* personalization — we *measured* it.** Using Phoenix Experiments on a fixed dataset, holding everything constant and changing only the persona version (after 3 rounds of user feedback):

| Metric | v1 baseline | v3 personalized | |
|---|---|---|---|
| **Preference alignment** (matches *this* user's style) | 0.62 | **0.795** | **+28%** ↑ |
| **Debate quality** (coverage / evidence / actionability) | 0.75 | 0.765 | held ✓ |

The coaching became *yours* — **without degrading its substance.** The whole comparison lives in Phoenix, timestamped and reproducible.

We also shipped a genuinely adversarial agent pair (not a single prompt wearing two hats), runtime trace introspection via MCP, and a full video→pose→debate→consensus pipeline verified end-to-end on Cloud Run.

## Challenges we ran into

- **A package-shadowing trap:** our project `mcp/` folder silently shadowed the PyPI `mcp` package, quietly killing the Mediator's MCP introspection. Fixed with import-path hardening so it can't break in any context (local / thread / container).
- **Bugs that only appeared on Cloud Run:** missing GLES libs for MediaPipe, MCP `stdout` pollution corrupting the JSON-RPC channel, and a Phoenix `401` that traced to two things — the auth header needed `Bearer` (not `api_key`) and the collector endpoint needed the space path. Each was invisible locally.
- **Avoiding false precision:** letting an LLM "eyeball" joint angles produces confident nonsense, so we split measurement (MediaPipe) from interpretation (Gemini).

## What we learned

Observability isn't a dashboard you bolt on at the end — it's how you *debug agents at all*. Phoenix traces were how we found the silently-dying MCP path. And evals turn "it feels better" into "it's 28% better, here's the experiment" — which is the difference between a claim and a result.

## What's next

- Bad-form detection across more lifts (deadlift, bench, overhead press) with larger labeled eval datasets.
- Online evals + continuous persona tuning from live feedback.
- Reference architecture: the adversarial-pair + self-improvement loop generalizes well beyond fitness.

## Built With

`google-adk` · `gemini-2.5-pro` · `gemini-2.5-flash` · `gemini-3.5-flash` · `google-cloud-run` · `vertex-ai-vector-search` · `arize-phoenix` · `model-context-protocol` · `fastmcp` · `mediapipe` · `firestore` · `cloud-storage` · `streamlit` · `python`

## Medical Disclaimer

This tool provides **informational analysis only**. It is **not medical advice**. If you experience pain, injury, or persistent discomfort during exercise, consult a qualified healthcare or fitness professional before continuing.
