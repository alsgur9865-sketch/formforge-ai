# 파일 위치: evals/persona_experiment.py
"""
Persona Evolution Experiment — Self-Improvement Loop 를 "숫자로" 증명 (Arize 트랙 ⭐⭐⭐).

무엇을 증명하나:
  우리 앱의 self-improvement loop(P3)는 사용자 피드백으로 두 코치의 페르소나를
  진화시킨다. 이 스크립트는 그게 "진짜로 작동한다"를 Phoenix 의 간판 기능
  **Datasets & Experiments** 에 측정값으로 박제한다 (말 → 증거).

핵심 설계 — "정직한 dual-metric":
  self-improvement loop 가 바꾸는 건 톤(warmth/harshness/detail)이지 실력이 아니다.
  그래서 "토론 품질이 올랐다"고 주장하면 인과가 약하고 cherry-pick 으로 보인다.
  대신 같은 데이터셋에 페르소나 버전만 바꿔(v1 baseline vs v3 personalized) 두 가지를 잰다:

    1. preference_alignment  — "이 토론이 *이 사용자가 원한 스타일*에 얼마나 맞나" (0~1).
       v1 → v3 로 **크게 상승**해야 한다 (헤드라인: "당신만의 코치가 됐다").
    2. debate_quality        — 기존 llm_judge(coverage/evidence/actionability, 0~1).
       v1 ≈ v3 로 **유지**돼야 한다 (가드레일: "톤 맞추느라 실력은 안 깎였다").

  = "Made it yours, without making it worse." 두 숫자가 Phoenix Experiments 탭에
    v1 vs v3 로 나란히 찍힌다 = 다른 팀엔 없는 장면.

진화 시나리오 (재현 가능 — 결정론):
  타깃 사용자 = "Scrutinizer 가 너무 가혹하다 + 더 구체적으로 원함 + 더 따뜻하게".
  실제 피드백 루프(feedback_handler.apply_persona_adjustment)를 3회 적용한 상태가 v3.
    encourager: too_cold(+warmth) , scrutinizer: too_harsh(-harshness) , free_text 더 구체적으로(+detail)

실행:
  ./venv/Scripts/python.exe evals/persona_experiment.py --smoke   # 1 예제 × 2버전 (검증, ~2-4분)
  ./venv/Scripts/python.exe evals/persona_experiment.py           # 4 예제 × 2버전 (본 실행, ~10-15분)
  ./venv/Scripts/python.exe evals/persona_experiment.py --n 6     # 데이터셋 크기 지정

전제: .env 의 PHOENIX_API_KEY + (Vertex/Gemini 인증). Phoenix Cloud space endpoint 자동 보정.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# 스크립트 직접 실행 시 프로젝트 루트를 sys.path 에. append(insert 아님) — 루트 mcp/ 가
# PyPI mcp 패키지를 shadow 하지 않게 (orchestrator.py 와 동일 가드). 단 이 스크립트는
# run_debate 만 쓰고 mediator/mcp 체인은 안 타므로 shadow 위험은 실질적으로 없음.
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.append(_ROOT)

from evals.feedback_handler import apply_persona_adjustment  # noqa: E402
from evals.llm_judge import judge_debate  # noqa: E402


# ===========================================================================
# 1) 페르소나 버전 — v1 baseline → v3 personalized (결정론적, 재현 가능)
# ===========================================================================

# v1 = 앱 기본값 (orchestrator/debate 의 builder 기본 파라미터와 동일).
V1_PERSONA: dict[str, Any] = {
    "encourager": {"warmth": 0.70, "detail": 0.60},
    "scrutinizer": {"harshness": 0.70, "detail": 0.80},
}

# 타깃 사용자가 원하는 코칭 스타일 — preference_alignment judge 의 채점 기준.
TARGET_STYLE = (
    "이 사용자는 (1) 가혹하지 않고 부드럽게 지적하며, (2) 매우 구체적이고 상세하게 "
    "설명하고, (3) 따뜻하게 격려하는 코칭을 원한다. 즉 덜 날카롭고, 더 자세하고, 더 따뜻하게."
)


def evolve_persona(v1: dict[str, Any], rounds: int = 3) -> dict[str, Any]:
    """
    실제 self-improvement loop(apply_persona_adjustment)를 rounds 회 적용해 v3 생성.

    타깃 사용자의 피드백을 매 라운드 동일하게 준다:
      - encourager: too_cold  → warmth +0.10/round (더 따뜻하게)
      - scrutinizer: too_harsh → harshness -0.15/round (덜 가혹하게)
      - free_text "더 구체적으로" → detail +0.10/round (실루프에선 LLM judge 의 detail_delta;
        여기선 재현성을 위해 결정론적으로 동일 적용)
    """
    state = {
        "encourager": dict(v1["encourager"]),
        "scrutinizer": dict(v1["scrutinizer"]),
    }
    for _ in range(rounds):
        # warmth / harshness — 결정론 룩업 (judge_result=None → detail 은 보존)
        state = apply_persona_adjustment(
            current_state=state,
            encourager_rating="too_cold",
            scrutinizer_rating="too_harsh",
            judge_result=None,
        )
        # detail — free_text 신호를 결정론적으로 반영
        state["encourager"]["detail"] = round(min(1.0, state["encourager"]["detail"] + 0.10), 4)
        state["scrutinizer"]["detail"] = round(min(1.0, state["scrutinizer"]["detail"] + 0.10), 4)
    return state


V3_PERSONA: dict[str, Any] = evolve_persona(V1_PERSONA, rounds=3)


# ===========================================================================
# 2) 데이터셋 — 토론 시나리오 (정상 → 명백한 결함 스펙트럼)
# ===========================================================================

_USER_CTX = {
    "user_id": "persona_eval_user",
    "injury_history": ["lower_back_strain_2025"],
    "experience_level": "intermediate",
}


def _rep(n: int, depth: int, knee: str, back_bottom: int, down: float, up: float) -> dict[str, Any]:
    return {
        "rep_number": n,
        "depth_degrees": depth,
        "knee_alignment": knee,
        "back_angle_at_bottom": back_bottom,
        "back_angle_at_top": 88,
        "tempo": {"down_sec": down, "up_sec": up, "pause_sec": 0.0},
        "bar_path_deviation_cm": 1.6,
    }


def _scenario(
    name: str, form_score: int, reps: list[dict[str, Any]], safety_flags: list[dict[str, Any]]
) -> dict[str, Any]:
    """create_dataset 용 example — input/output/metadata."""
    pose_data = {
        "exercise_type": "squat",
        "rep_count": len(reps),
        "duration_seconds": round(len(reps) * 4.5, 1),
        "reps": reps,
        "overall_metrics": {
            "depth_consistency": 0.85,
            "tempo_consistency": 0.75,
            "form_score_0_100": form_score,
        },
        "safety_flags": safety_flags,
    }
    return {
        "input": {"pose_data": pose_data, "user_context": _USER_CTX},
        "output": {"reference": "고정 정답 없음 — preference_alignment + debate_quality judge 로 평가"},
        "metadata": {"scenario": name, "form_score": form_score, "target_style": TARGET_STYLE},
    }


def build_dataset_examples(n: int) -> list[dict[str, Any]]:
    """정상→결함 스펙트럼 시나리오. n 으로 개수 제한 (smoke=1)."""
    all_scenarios = [
        # 1) 거의 완벽
        _scenario(
            "near_perfect", 88,
            [_rep(i, 96, "neutral", 44, 1.6, 1.1) for i in range(1, 4)],
            [{"severity": "low", "issue": "minor_tempo_drift"}],
        ),
        # 2) 보통 (무릎 외반 medium)
        _scenario(
            "moderate_valgus", 73,
            [_rep(i, 92, "valgus_2deg_left" if i % 2 else "neutral", 42, 2.0, 1.4) for i in range(1, 6)],
            [
                {"severity": "medium", "issue": "knee_valgus_left", "rep_numbers": [1, 3, 5]},
                {"severity": "low", "issue": "tempo_inconsistency"},
            ],
        ),
        # 3) 결함 — 과도한 전방 기울기 (요추 위험)
        _scenario(
            "forward_lean", 52,
            [_rep(i, 95, "neutral", 28, 2.4, 1.8) for i in range(1, 5)],
            [{"severity": "high", "issue": "excessive_forward_lean", "rep_numbers": [1, 2, 3, 4]}],
        ),
        # 4) 결함 — 얕은 깊이 + 무릎 외반
        _scenario(
            "shallow_and_valgus", 45,
            [_rep(i, 128, "valgus_6deg_both", 50, 1.1, 0.9) for i in range(1, 5)],
            [
                {"severity": "high", "issue": "insufficient_depth", "rep_numbers": [1, 2, 3, 4]},
                {"severity": "medium", "issue": "knee_valgus_both", "rep_numbers": [1, 2, 3, 4]},
            ],
        ),
    ]
    return all_scenarios[: max(1, n)]


# ===========================================================================
# 3) Task — persona vN 으로 실제 토론을 돌려 두 코치 텍스트를 반환
# ===========================================================================

# 실험은 진짜 토론을 돌린다. 속도/비용을 위해 라운드는 2 로 제한(톤은 라운드1에 이미 드러남).
_EXPERIMENT_MAX_ROUNDS = 2


def make_debate_task(persona_state: dict[str, Any]):
    """주어진 페르소나 버전으로 토론을 실행하는 async task 를 만든다 (closure)."""

    async def _task(input: dict[str, Any]) -> dict[str, Any]:
        # lazy import — cv2/mediapipe 등 무거운 체인 회피 + mcp shadow 안전.
        from agents.debate import run_debate

        pose_data = input["pose_data"]
        user_context = input.get("user_context", _USER_CTX)

        result = await run_debate(
            pose_data=pose_data,
            user_context=user_context,
            persona_state=persona_state,
            max_rounds=_EXPERIMENT_MAX_ROUNDS,
            debate_id=None,  # Firestore 미연동 (실험은 순수 토론만)
        )
        last = result.last_round
        return {
            "encourager_text": (last.encourager_raw if last else "") or "",
            "scrutinizer_text": (last.scrutinizer_raw if last else "") or "",
            "rounds": len(result.rounds),
            "converged": result.converged,
            "persona_state": persona_state,
        }

    return _task


# ===========================================================================
# 4) Evaluators — preference_alignment(신규) + debate_quality(기존 재활용)
# ===========================================================================

_PREF_MODEL = "gemini-3.5-flash"   # 품질 judge 와 동일 — Gemini 3 family 시그널 + 검증됨
_PREF_LOCATION = "global"          # Gemini 3 는 Vertex global 엔드포인트만 서빙(세션 11)

_pref_client: genai.Client | None = None


def _get_pref_client() -> genai.Client:
    global _pref_client
    if _pref_client is not None:
        return _pref_client
    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in ("true", "1", "yes")
    if use_vertex:
        _pref_client = genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=_PREF_LOCATION,
        )
    else:
        _pref_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    return _pref_client


class _PrefScore(BaseModel):
    alignment_score: float = Field(ge=0.0, le=1.0, description="0.0~1.0 — 타깃 스타일에 얼마나 부합하는가.")
    reasoning: str = Field(description="왜 이 점수인지 한국어 한 문장.")


_PREF_INSTRUCTION = """\
You score how well a workout-form debate matches a SPECIFIC user's preferred coaching style.

You receive:
- target_style: the coaching style THIS user wants.
- encourager_argument / scrutinizer_argument: the two coaches' actual outputs (JSON).

Score 0.0~1.0 = how well the two coaches' TONE & STYLE match target_style
(gentleness vs harshness, level of specificity/detail, warmth/encouragement).
This is about STYLE FIT to the user, NOT about whether the advice is objectively correct.
Output JSON only. `reasoning` must be ONE Korean sentence.
"""


async def preference_alignment(output: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    """타깃 사용자 스타일에 대한 부합도 (헤드라인 지표). v1<v3 으로 상승해야 함."""
    target_style = (metadata or {}).get("target_style", TARGET_STYLE)
    payload = {
        "target_style": target_style,
        "encourager_argument": output.get("encourager_text", ""),
        "scrutinizer_argument": output.get("scrutinizer_text", ""),
    }
    client = _get_pref_client()
    response = await client.aio.models.generate_content(
        model=_PREF_MODEL,
        contents=[types.Content(role="user", parts=[types.Part(text=json.dumps(payload, ensure_ascii=False))])],
        config=types.GenerateContentConfig(
            system_instruction=_PREF_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=_PrefScore,
            temperature=0.1,
        ),
    )
    parsed = (
        response.parsed
        if isinstance(getattr(response, "parsed", None), _PrefScore)
        else _PrefScore.model_validate(json.loads(response.text or "{}"))
    )
    label = "aligned" if parsed.alignment_score >= 0.6 else "misaligned"
    return {"score": parsed.alignment_score, "label": label, "explanation": parsed.reasoning}


async def debate_quality(output: dict[str, Any]) -> dict[str, Any]:
    """기존 llm_judge 재활용 — coverage/evidence/actionability (가드레일 지표). v1≈v3 유지."""
    neutral_feedback = {
        "encourager_rating": "perfect",
        "scrutinizer_rating": "perfect",
        "mediator_rating": 3,
        "free_text": "",
    }
    result, _latency = await judge_debate(
        encourager_text=output.get("encourager_text", ""),
        scrutinizer_text=output.get("scrutinizer_text", ""),
        mediator_text="",  # 실험은 Mediator 미실행 — 두 코치 토론 품질만 평가
        user_feedback=neutral_feedback,
        persona_state=output.get("persona_state", {}),
    )
    score = result.debate_quality_score
    label = "good" if score >= 0.6 else "fair"
    return {"score": score, "label": label, "explanation": result.reasoning}


# ===========================================================================
# 5) Phoenix 클라이언트 + 실험 실행
# ===========================================================================

def _phoenix_base_url() -> str:
    """
    Phoenix Cloud base_url = `scheme://host/s/<space_id>`.

    .env 의 PHOENIX_COLLECTOR_ENDPOINT 경로가 손상돼도(예: 줄바꿈 누락으로
    `.../s/alsgur9865PHOENIX_PROJECT_NAME=formforge-prod` 처럼 다음 변수가 붙은 경우)
    견고하게 동작하도록, env 에서는 scheme+host 만 추출하고 space id 는 별도로 조립한다.
    space id 는 PHOENIX_SPACE_ID env, 없으면 알려진 기본값(alsgur9865).
    """
    raw = (os.getenv("PHOENIX_COLLECTOR_ENDPOINT") or "").strip()
    m = re.match(r"https?://[^/\s]+", raw)
    host = m.group(0) if m else "https://app.phoenix.arize.com"
    space = os.getenv("PHOENIX_SPACE_ID", "alsgur9865")
    return f"{host}/s/{space}"


def _experiment_means(exp: dict[str, Any]) -> dict[str, float]:
    """RanExperiment 의 evaluation_runs 에서 evaluator 별 평균 score 추출 (방어적)."""
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for run in exp.get("evaluation_runs", []) or []:
        if getattr(run, "error", None) or getattr(run, "result", None) is None:
            continue
        res = run.result
        items = res if isinstance(res, list) else [res]
        for it in items:
            if not isinstance(it, dict):
                continue
            score = it.get("score")
            name = it.get("name") or getattr(run, "name", "?")
            if isinstance(score, (int, float)):
                sums[name] = sums.get(name, 0.0) + float(score)
                counts[name] = counts.get(name, 0) + 1
    return {k: sums[k] / counts[k] for k in sums if counts[k]}


async def run(n: int, *, dry_run: bool = False) -> None:
    from phoenix.client import AsyncClient
    from phoenix.client.experiments import async_run_experiment

    base_url = _phoenix_base_url()
    api_key = os.getenv("PHOENIX_API_KEY")
    if not api_key:
        print("❌ PHOENIX_API_KEY 없음 — .env 확인 (Phoenix Cloud 기록 불가).", file=sys.stderr)
        raise SystemExit(2)

    print(f"🔗 Phoenix: {base_url}")
    print(f"🧬 v1 baseline   : {json.dumps(V1_PERSONA, ensure_ascii=False)}")
    print(f"🧬 v3 personalized: {json.dumps(V3_PERSONA, ensure_ascii=False)}")

    client = AsyncClient(base_url=base_url, api_key=api_key)

    examples = build_dataset_examples(n)
    ds_name = f"formforge-persona-eval-{int(time.time())}"
    print(f"\n📦 데이터셋 생성: {ds_name} ({len(examples)} 예제)")
    dataset = await client.datasets.create_dataset(
        name=ds_name,
        examples=examples,
        dataset_description="페르소나 진화(v1 vs v3) 비교용 스쿼트 토론 시나리오 — 정상→결함 스펙트럼.",
    )

    evaluators = {"preference_alignment": preference_alignment, "debate_quality": debate_quality}

    # --- 실험 1: v1 baseline ---
    print("\n🏃 실험 v1 (baseline) 실행 중 — 진짜 토론을 돌립니다, 시간 걸립니다...")
    exp_v1 = await async_run_experiment(
        dataset=dataset,
        task=make_debate_task(V1_PERSONA),
        evaluators=evaluators,
        experiment_name="persona-v1-baseline",
        experiment_description="진화 전 기본 페르소나(warmth0.7/harsh0.7).",
        experiment_metadata={"persona": V1_PERSONA},
        client=client,
        concurrency=2,
        timeout=300,
        dry_run=dry_run,
        print_summary=True,
    )

    # --- 실험 2: v3 personalized ---
    print("\n🏃 실험 v3 (personalized) 실행 중...")
    exp_v3 = await async_run_experiment(
        dataset=dataset,
        task=make_debate_task(V3_PERSONA),
        evaluators=evaluators,
        experiment_name="persona-v3-personalized",
        experiment_description="피드백 3회 진화 후 페르소나(따뜻+부드럽+구체적).",
        experiment_metadata={"persona": V3_PERSONA},
        client=client,
        concurrency=2,
        timeout=300,
        dry_run=dry_run,
        print_summary=True,
    )

    # --- 최종 dual-metric 표 ---
    m1, m3 = _experiment_means(exp_v1), _experiment_means(exp_v3)

    def _fmt(d: dict[str, float], k: str) -> str:
        return f"{d[k]:.3f}" if k in d else "  -  "

    print("\n" + "=" * 64)
    print("📊 PERSONA EVOLUTION — dual-metric (같은 데이터셋, 페르소나만 v1→v3)")
    print("=" * 64)
    print(f"{'metric':<24}{'v1 baseline':>14}{'v3 personalized':>18}")
    print("-" * 64)
    for key, headline in (("preference_alignment", "↑ 상승 기대"), ("debate_quality", "≈ 유지 기대")):
        print(f"{key:<24}{_fmt(m1, key):>14}{_fmt(m3, key):>18}   ({headline})")
    print("=" * 64)
    if "preference_alignment" in m1 and "preference_alignment" in m3:
        delta = m3["preference_alignment"] - m1["preference_alignment"]
        print(f"➡️  preference_alignment Δ = {delta:+.3f}  "
              f"({'✅ 진화가 사용자 취향에 더 맞음' if delta > 0 else '⚠️ 상승 안 함 — 시나리오/루브릭 점검'})")
    print(f"\n🔬 Phoenix Experiments 탭에서 두 실험을 나란히 비교하세요: {base_url}")
    print(f"   experiment ids: v1={exp_v1.get('experiment_id')} / v3={exp_v3.get('experiment_id')}")
    print("\n⚠️ 의료 면책: 정보 제공용. 의학 조언 아님. 부상·통증 시 전문가 상담.")


# ===========================================================================
# CLI
# ===========================================================================

if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    # Vertex 미사용 시 google-genai 가 GOOGLE_API_KEY 를 보므로 GEMINI_API_KEY 폴백.
    if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

    argv = sys.argv[1:]
    n = 4
    if "--smoke" in argv:
        n = 1
    if "--n" in argv:
        i = argv.index("--n")
        if i + 1 < len(argv):
            n = max(1, int(argv[i + 1]))

    asyncio.run(run(n=n, dry_run=False))
