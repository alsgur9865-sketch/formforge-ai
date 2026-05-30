# Handoff: FormForge AI — "Fight Card" UI System (6 screens)

## Overview
FormForge AI is a home-fitness form coach built on an **adversarial multi-agent** idea: the user uploads a workout video, two AI coaches with opposing personalities **debate the form live**, a Head Coach (Mediator) issues a **consensus ruling**, and the user's **feedback re-forges the coaches' personas** over time. The whole product is presented through one ownable visual metaphor — a **boxing fight card**: two corners, rounds with a bell, a referee's scorecard, a tale-of-the-tape, and an official "timesheet" for observability.

This bundle covers all six core screens of the product flow.

## About the Design Files
The files in this bundle are **design references created in HTML/CSS/vanilla JS** — prototypes that demonstrate the intended look, layout, copy, and interactions. **They are not production code to copy directly.** The task is to **recreate these designs in the target codebase's environment** using its established patterns and component library.

> Implementation note from the team: production is planned in **Streamlit (Python) + custom CSS**, with **1-second polling** for "live" updates (not websockets). The designs were intentionally built to be reproducible with Streamlit primitives (columns, containers, cards, metrics, progress bars, segmented buttons, expanders) plus custom CSS. If you implement in another stack (React/Vue/etc.), keep the same layout/token system and treat the polling cadence as the refresh model for the live debate view.

## Fidelity
**High-fidelity (hifi).** Final colors, typography, spacing, and interactions are specified. Recreate the UI faithfully using the codebase's libraries. Exact hex/px values are listed under **Design Tokens** and per-screen below.

---

## Design Tokens (shared across all 6 screens)

### Color — ink / surfaces (dark screens)
| Token | Hex | Use |
|---|---|---|
| ink | `#111219` (trace screen uses `#0E0F16`) | page background |
| ink2 | `#171922` (`#141622`) | header strip, panels, inset fields |
| panel | `#1A1D28` | right sidebars |
| line | `#2A2D3A` | hairline borders/dividers |
| line2 | `#373B4C` | stronger borders, ticks |
| hi | `#ECEAE2` | primary text (warm off-white) |
| mid | `#9A988C` | secondary text |
| dim | `#67655B` | tertiary/labels |

### Color — coaches & accents (identity — do not change)
| Token | Hex | Meaning |
|---|---|---|
| **enc** (Encourager) | `#37B36A` green; soft `#8FE0B0`; chip text on green uses `#1C8C4E`/white | "Green corner" — warm PT |
| **scr** (Scrutinizer) | `#E8415C` red; soft `#F79DAC` | "Red corner" — physiology PhD |
| **gold** (Mediator/official) | `#C9A24B`; light `#E2C57A` | Head Coach, judge, stamps, MCP highlight |
| **ember** (forge/CTA) | `#E2672E` | re-forge spark, primary buttons, eyebrows |
| **slate** (analysis) | `#6E7486` | PoseExtractor / "before" week / non-persona data |

### Color — paper (cream "scorecard / corner note" material)
Used for the referee's-decision document and the "corner instruction" note — creates material contrast against the dark stage.
| Token | Hex |
|---|---|
| bone (paper) | `#EAE3D2` (consensus doc uses `#ECE5D3`) |
| bone-ink (text on paper) | `#2A2519` |
| bone secondary text | `#4A4327` / `#7A6E4C` |
| paper rule/border | `#D2C7AB` / `#D8CFB8` |
| paper top edge | `gold #C9A24B` (3px) |

### Typography (Google Fonts)
- **Display / headings / fighter names:** `Saira Condensed` (700–900), UPPERCASE, letter-spacing `.01em–.16em`, tight line-height `.82–.9`. This is the signature "fight poster" type.
- **Body / paragraphs:** `Archivo` (400–700).
- **Labels / data / records / mono UI:** `JetBrains Mono` (400–700), letter-spacing `.04em–.18em`, frequently UPPERCASE. The **Phoenix Trace screen uses JetBrains Mono as its base font** (dev-dashboard tone).

Representative sizes: hero H1 `Saira Condensed 900 / 50–66px`; section headers `Saira 800 / 16–18px / tracking .14em`; fighter/coach names `Saira 700 / 16–22px`; body `Archivo 14–15px / line-height 1.5`; mono labels `10–12px`.

### Spacing / radius / misc
- Page horizontal padding: `40–50px`. Screen-section gaps: `16–26px`.
- Border radius: cards/bars `3–6px` (sharp, editorial — NOT pill-rounded); avatars `8–14px`; chips/segments `2–4px`; circular seals/sparks `50%`.
- Header strip: `border-bottom: 3px solid #ECEAE2`, background = subtle 135° hatch `repeating-linear-gradient(135deg, rgba(255,255,255,.018) 0 2px, transparent 2px 8px)` over ink2.
- Shadows: bars `0 1px 3px rgba(0,0,0,.4)`; raised cards `0 16–18px 34–40px rgba(0,0,0,.4)`; MCP glow `0 0 12px rgba(201,162,75,.45)`.
- Fixed canvas sizes (each screen is a fixed-width design, letterboxed in ink): widths all **1440px**; heights per screen listed below.

### Recurring chrome (every screen)
- **Top strip:** left = FormForge mark (22px hammer/spark SVG in a white rounded square) + mono context label; center = `Saira 800` gold screen title; right = mono record id. All three one line (`white-space:nowrap`).
- **Footer:** mono `10.5px` dim, top border `1px line`, on ink2. Always contains the **medical disclaimer**: `⚕ FOR INFORMATION ONLY — NOT MEDICAL ADVICE.` + a second clause. **This disclaimer is required on every analysis screen.**
- **Back-link:** absolute bottom-right pill `← Concepts` → `../FormForge Concepts.html`.

### The FormForge mark (SVG)
A struck spark/forge glyph used everywhere (recolor stroke per context):
```html
<svg viewBox="0 0 24 24" fill="none"><path d="M3 14l6-2 2-6 3 9 2-3 5 2" stroke="#36D17C" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="19" cy="6" r="2" fill="#DD5A28"/></svg>
```

---

## Screens / Views (product flow order)

### 1. Weigh-In — Upload / Start  · `screens/upload-fightcard.html` · 1440×920
- **Purpose:** user submits a workout video and registers the "bout."
- **Layout:** strip; then a 2-column main grid `1.36fr / 1fr`.
  - **Left (form):** eyebrow `SUBMIT YOUR TAPE` (ember mono) → H1 "Step into the ring." (Saira 900, 54px) → **drop zone** (full-width, `2px dashed line2`, radius 6, ember radial glow on hover, 54px ember up-arrow in a circle, title "Drop your workout video", sub "MP4 / MOV · a side angle reads form best", ember text link "or watch a sample bout →") → **Weight class** label + 3 selectable cards in a `repeat(3,1fr)` grid (Squat / Deadlift / Push-up; selected card gets `gold` border + tinted bg + gold check tick top-right) → **Medical corner notes (optional)** field: a bordered container holding removable red chips (e.g. "Prior lower-back injury ✕") + a text input → **CTA row** at bottom: primary `Send to the corners →` (ember, Saira 800) + ghost `Try a sample bout`.
  - **Right (sidebar, panel bg):** header `TONIGHT'S CARD`; two coach mini-cards (Encourager green-left-border / Scrutinizer red-left-border, each: avatar + name + one-line role); then `HOW THE BOUT RUNS` 3 numbered steps (ember numerals): 1 PoseExtractor analyzes · 2 The corners debate · 3 The Head Coach rules.
- **Interactions:** weight-class cards are click-to-select (single). Notes input: Enter adds a chip; chip ✕ removes it. Drop zone, both CTAs, and "sample" link all navigate to `screens/debate-fightcard.html` (in production: trigger upload → analysis pipeline).

### 2. The Live Debate (HERO) · `screens/debate-fightcard.html` · 1440×1180
- **Purpose:** the headline screen — watch the two coaches argue across rounds, then converge.
- **Layout (top→bottom):**
  - **Fight poster header:** small top row (`FormForge AI · Form Debate` left, `RECORD №048 · LIVE` gold right). Big **matchup**: `THE ENCOURAGER` (right-aligned, green-soft) — circular bone **VS** medallion — `THE SCRUTINIZER` (left-aligned, red-soft), each ~62px Saira 800 with a mono sub-label (corner + credential). Then a centered **bout-meta** mono row: `SQUAT / SIDE ANGLE / 3 REPS / FORM 65 / 🔔 ROUND 2 OF 3`.
  - **Tale of the Tape:** centered header `— TALE OF THE TAPE —`; rows in a `1fr 230px 1fr` grid (left value right-aligned, center mono label, right value left-aligned), dotted row dividers. Rows: Experience / Coaching style / Read on this set / Severity called (left = gold MODERATE, right = red HIGH).
  - **Rounds:** each round = a centered tab medallion (`🔔 Round N` + mono caption) over a 2px rule, then a `1fr 1fr` **bout** grid with a center divider. Left = Encourager corner (`● GREEN` chip), right = Scrutinizer corner (`RED ●` chip + `SEV · HIGH` outline badge). Round 2 cards show a dashed `↩ Counters the …corner` stamp. Body copy 14.5px, key phrases bold/colored.
  - **Referee's Decision (cream scorecard):** `0 -2px 0 gold` top edge; title `Referee's Decision` (Saira 800, one line) + `UNANIMOUS` chip + recall note (`⟲ Recalled Record №041 · Apr 18 — recurring`). Body `1fr 168px`: left = ruling sentence + two priority actions (number stroke-outlined in gold, title + rationale tagging which corner backed it); right = **circular OFFICIAL stamp** (SVG `textPath` ring reading `· OFFICIAL · THE MEDIATOR · HEAD COACH` + check mark) over a `Head Coach` signature.
- **Motion:** on load, rounds and the verdict reveal staggered (`translateY(12px)→0`, opacity, delays r1 `.15s`, r2 `.75s`, verdict `1.45s`). Replay button re-triggers.

### 3. Official Decision — Consensus · `screens/consensus-fightcard.html` · 1440×880
- **Purpose:** the Head Coach's full ruling (this is screen 2's scorecard, expanded to a full document).
- **Layout:** dark strip (matchup mini-line center) → full **cream document** (`gold` inset top edge, faint dotted paper grain).
  - **dhead:** eyebrow `HEAD COACH'S RULING` (gold) + H1 `THE DECISION.` (Saira 900, 64px); right = `UNANIMOUS` dark chip + `CONVERGED · 2 ROUNDS`.
  - **Convergence row** (`1fr 132px 1fr`): left Encourager corner card + right Scrutinizer corner card (white cards on the cream, colored left/right borders, each with corner chip + name + italic one-line position), with a center **Head Coach seal** (dark circle, gold balance icon, gold→`HEAD COACH` label) and a green→gold→red gradient connector line behind it.
  - **Ruling** paragraph (Archivo 21px), key phrase in gold.
  - **Body grid `1.5fr / 1fr`:** left = `⚖ THE RULING · PRIORITY ACTIONS` with two acts (huge gold stroke-outlined numerals 01/02 + title + rationale tagging the backing corner) and the **OFFICIAL stamp + "The Mediator / Head Coach" signature**; right = `⟲ PRIOR RECORD ON FILE` callout (`MCP · query_past_debates`, Record №041, Apr 18, recurring red chip) + `DECISION BASIS` agreement bars (Lean is the risk 96 gold / Reduce load 88 red / Cue, don't stop 64 green).
- **Motion (convergence):** on load the two corner cards slide inward from ±40px + fade in (transition `.7s`), suggesting the positions converging onto the Head Coach. A JS fallback removes the `intro` class after 900ms so the resting (visible) state is guaranteed.

### 4. Score the Corners — Feedback · `screens/feedback-fightcard.html` · 1440×880 · **interactive**
- **Purpose:** the user judges each coach; the scores tune persona for the next bout.
- **Layout:** strip → centered body (max-width 1080) → eyebrow `YOU'RE THE JUDGE` + H1 "Score the corners." + lede → **three rows** (`300px / 1fr` grid, colored left border per coach):
  - Encourager (`AFFECTS · WARMTH`): segmented `Too warm | Just right | Too cold` (3-col), each option has a tiny mono sub-caption; selected fills with green.
  - Scrutinizer (`AFFECTS · HARSHNESS`): segmented `Too harsh | Just right | Too soft`; selected fills red. **Default selected = "Too harsh"** (this drives the evolution story).
  - Mediator (`HEAD COACH · OVERALL CALL`): **5 star rating** (gold), default 4, with a label `4 / 5 · solid call`.
  - **Notes to the corner** one-line input. **Foot:** hint text + `Submit your card →` (ember).
- **Interactions:** segments are single-select per group; stars set rating on hover/click with a word label per value. **On submit:** `#stage` gets class `sent` → the form/notes hide and a **re-forging banner** appears (ember spark pulse + "Card logged — the corners are re-forging." + link `See how they evolve →` → `screens/evolution-fightcard.html`). Default selections shown above make the static state look populated.

### 5. Between Bouts — Evolution · `screens/evolution-fightcard.html` · 1440×920
- **Purpose:** prove self-improvement — the same flaw, one week apart, gets a different (softer) coach because of the user's feedback.
- **Layout:** strip (`The Scrutinizer · Training Log`, `RECORD №041 → №048`) → hero (eyebrow `BETWEEN BOUTS · SELF-IMPROVEMENT`, H1 "Your corner re-forged itself." with `re-forged` in ember; right lede) → **diptych** (`1fr 226px 1fr`):
  - **Week 1 (before, cold/slate tint):** `WEEK 1` (slate Saira) + `RECORD №041`; a muted quote card (`RED CORNER · WK1`, harsh sample, `HARSHNESS 0.50`); persona stat bars at week-1 values in slate.
  - **Center (catalyst):** dashed vertical connector; a **cream "CORNER INSTRUCTION" note** (`★ "too harsh"` dark pill + sub "Your rating after Record №041"); an **ember spark** circle; `PERSONA RE-FORGED` (Saira, ember).
  - **Week 2 (after, live):** `WEEK 2` + `RECORD №048`; live quote card (`RED CORNER · WK2`, softened sample, `HARSHNESS 0.35`); persona bars with **`wk1` ghost markers** showing the prior value and animated fills: Harshness `0.50→0.35` (▼ green delta, red fill), Caution `0.40→0.55` (▲ ember delta, ember fill).
  - **Result band** (bottom, dark, `border-bottom:3px hi`): `THE RESULT` + Form score `65 → 74` (▲ +9 green) + Forward lean `HIGH → MODERATE` (gold).
- **Motion:** on load the Week-2 fills animate from the Week-1 value to the new value (`width transition .9s`).

### 6. Official Timesheet — Phoenix Trace · `screens/trace-fightcard.html` · 1440×900
- **Purpose:** observability — prove it's a real multi-agent system with MCP introspection (judging criterion: Technological Implementation). **Base font = JetBrains Mono.**
- **Layout:** strip (`◷ Official Timesheet`, `PHOENIX TRACE · RECORD №048`) → **metrics row** (`repeat(4,1fr) 1.3fr`): Total latency `8.4s` (green left border), Spans `10`, Tokens `11.9k`, p50 latency `1.2s`, and a gold-bordered `⟲ MCP INTROSPECTION` metric `2 calls · 0.5s`. → **Gantt** (`248px / 1fr` rows): a time axis (0–8s ticks; 1s = 11.764%), each row = span name (with tree indentation pads + colored square dot) + a track with a positioned bar (left%/width% by time). Spans: PoseExtractor (slate) → Round 1 group → Encourager r1 (green) ‖ Scrutinizer r1 (red) ‖ Convergence Judge (gold) → Round 2 group → Encourager r2 ‖ Scrutinizer r2 ‖ Convergence Judge → Ruling → **The Mediator (ember, wide — label sits inside the bar)** with two nested **MCP bars** (`query_past_debates`, `query_safety_flags`) styled gold with a glow + `MCP` tag + `⟲` prefix. Each bar has a trailing `latency · note` label. → gold **callout**: "This is the proof of 'self-aware'… every span auto-instrumented via Phoenix; nothing is mocked."
- **Interactions:** static (informational dashboard).

### Concept gallery (index) · `FormForge Concepts.html`
Not a product screen — an internal overview that embeds all six screens as scaled live `<iframe>` previews (the iframe scales via its **own** `transform`; previews use a `?still=1` query param that tells each screen to render its final composition without intro animation). Useful as a map of the flow. Three earlier exploration directions (dark-tech, clinical-light, experimental) are linked below the recommended set for context — they are **not** part of the final system.

---

## Interactions & Behavior (summary)
- **Navigation flow:** Weigh-In → (analysis) → Live Debate → Official Decision → Score the Corners → Between Bouts; Trace is reachable as an observability view. Links already wire Weigh-In→Debate, Feedback→Evolution, and every screen→gallery.
- **Live debate cadence:** production updates via **1s polling**; show **stepwise progress** ("Analyzing pose… / Round 1… / Judging convergence… / Mediating…") rather than a spinner — the debate header's pipeline/round indicator conveys "what step we're on."
- **Animations:** debate reveal stagger (`.5–.55s ease`, delays as listed); consensus convergence slide-in (`.7s cubic-bezier(.22,.7,.2,1)`); evolution bar fills (`.9s`); ember spark pulse (`1.6–2.2s` infinite). Provide a non-animated resting state if motion is disabled or the view loads in the background (the prototypes guarantee the final state via fill modes / JS fallbacks / the `?still=1` param).
- **Form states:** weight-class single-select; injury chips add/remove; feedback segments single-select + star rating; submit → "re-forging" confirmation.

## State Management
- **Session/bout:** `exerciseType` (squat|deadlift|pushup), `videoRef`, `injuryFlags[]`, `cameraAngle`.
- **Analysis (PoseExtractor):** `repCount`, `formScore (0–100)`, `safetyFlags[] {severity, issue, repNumbers, rationale}`.
- **Debate:** `rounds[] { encourager {praise, concern, tip, addressesScrutinizer}, scrutinizer {primaryRisk {name, severity, mechanism, evidence}, requiredAction, addressesEncourager} }`, `currentRound`, `converged (bool)` — drives the live view + round indicator.
- **Consensus (Mediator):** `consensus (text)`, `priorityActions[] {title, rationale, backedBy}`, `pastDebateReferences[] {debateId, date, outcome}` (from MCP), `decisionBasis[] {label, agreementPct}`.
- **Feedback:** `encouragerRating (warm|ok|cold)`, `scrutinizerRating (harsh|ok|soft)`, `mediatorStars (1–5)`, `note` → on submit, persists and adjusts persona params.
- **Persona / evolution:** per-coach params e.g. `harshness`, `warmth`, `caution` (0–1); store before/after snapshots per week + the triggering feedback.
- **Trace:** `spans[] {name, agent, startMs, endMs, latency, tokens, status, isMcp}` from Phoenix/OpenInference.
- **Data fetching:** MCP tools `query_past_debates`, `query_similar_safety_flags` (surfaced in Consensus + Trace). Live debate = 1s polling of the run state.

## Design Tokens
All exact values are in the **Design Tokens** section above (colors with hex, type families/sizes, spacing, radius, shadows, fixed canvas sizes).

## Assets
- **Fonts:** Google Fonts — `Saira Condensed`, `Archivo`, `JetBrains Mono` (also `IBM Plex Sans/Mono/Serif` in the earlier "clinical" exploration only). Load via `<link>` or self-host.
- **Icons:** all inline SVG (forge mark, balance/scales, magnifier, sprout, up-arrow, lightning spark, star, check). No external icon set — reproduce with the codebase's icon system or keep as inline SVG. The OFFICIAL stamp is inline SVG using `<textPath>` around a circle.
- **Images:** none. (Real product needs the user's uploaded workout video + a pose/keypoint overlay for PoseExtractor — not part of these mocks; use a placeholder slot.)
- No raster assets are bundled.

## Files
Recommended fight-card system (the deliverable):
- `screens/upload-fightcard.html` — 1. Weigh-In
- `screens/debate-fightcard.html` — 2. The Live Debate (hero)
- `screens/consensus-fightcard.html` — 3. Official Decision
- `screens/feedback-fightcard.html` — 4. Score the Corners (interactive)
- `screens/evolution-fightcard.html` — 5. Between Bouts
- `screens/trace-fightcard.html` — 6. Official Timesheet
- `FormForge Concepts.html` — overview gallery (embeds all six; reference only)

Each screen is self-contained (inline `<style>` + small vanilla `<script>`); open any file directly in a browser to inspect computed styles, exact copy, and behavior.
