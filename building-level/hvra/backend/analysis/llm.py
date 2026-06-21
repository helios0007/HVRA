"""
Stage 3 — Building Interpreter and Stage 4b — Retrofit Recommender.

Both stages run LLM calls in parallel with asyncio.gather() per room.

Stage 3 per room:
    Input : room JSON (without ai_outputs)
    Output: diagnosis (str) + key_factors (list[str])
    Updates room_problems.json in place.

Stage 4b per room:
    Input : room context + eligible strategy library entries
    Output: shortlist (list of 3 ranked strategy objects)
    Writes shortlist.json (all rooms).

MODEL: claude-sonnet-4-20250514
SOURCE: HVRA_build_reference_4.md §Architecture Notes — LLM call structure.
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

# ── LLM provider selection ──────────────────────────────────────────────────────
# Set in backend/.env:
#   LLM_PROVIDER=anthropic   (default — Claude API, needs ANTHROPIC_API_KEY)
#   LLM_PROVIDER=ollama      (local model — needs `ollama serve` running)
#   OLLAMA_MODEL=llama3.1:8b (any pulled model; qwen2.5:7b is good at JSON)
#   OLLAMA_URL=http://localhost:11434

def llm_provider() -> str:
    return os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()


def _ollama_url() -> str:
    return os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")


def _ollama_model() -> str:
    return os.environ.get("OLLAMA_MODEL", "llama3.1:8b")


def _facades_for_llm(facades: list[dict]) -> list[dict]:
    """
    Strip geometry-only fields from facade records before sending to the LLM.
    These exist for the 3D viewer (highlighting / section diagrams) and only
    bloat the prompt — wall_layers alone can triple the room JSON size.
    """
    drop = {"wall_id", "window_ids", "wall_layers", "wall_thickness_mm"}
    return [{k: v for k, v in f.items() if k not in drop} for f in facades]


# Rate-limit handling: max parallel LLM calls + retry with backoff on 429
_MAX_CONCURRENT_CALLS = 3
_MAX_RETRIES = 5


async def _create_with_retry(client, sem: "asyncio.Semaphore", **kwargs):
    """
    client.messages.create wrapped in a concurrency semaphore and
    exponential-backoff retry for rate-limit (429) / overloaded (529) errors.
    """
    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with sem:
                return await client.messages.create(**kwargs)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            retryable = status in (429, 529) or "rate_limit" in str(exc).lower()
            if retryable and attempt < _MAX_RETRIES:
                delay = min(60, 10 * (2 ** attempt))
                logger.warning(
                    "LLM rate-limited (attempt %d/%d) — retrying in %ds",
                    attempt + 1, _MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
                continue
            raise


def _ollama_format_schema(system: str):
    """
    [ollama-fix] Pick the Ollama structured-output JSON Schema for the call from
    the stage's system prompt. Returns a schema dict (grammar-constrains the model
    to exactly these keys) or "json" as a safe fallback for unknown prompts.
    """
    if "shortlist" in system:  # Stage 4b — Retrofit Recommender
        return {
            "type": "object",
            "properties": {
                "shortlist": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "strategy_id": {"type": "string"},
                            "rank": {"type": "integer"},
                            "justification": {"type": "string"},
                            "delta_T_expected_C": {"type": "number"},
                            "cost_eur_m2": {"type": "number"},
                            "carbon_kgCO2_m2": {"type": "number"},
                            "feasibility_note": {"type": "string"},
                            "literature_source": {"type": "string"},
                        },
                        "required": [
                            "strategy_id", "rank", "justification",
                            "delta_T_expected_C", "cost_eur_m2", "carbon_kgCO2_m2",
                            "feasibility_note", "literature_source",
                        ],
                    },
                }
            },
            "required": ["shortlist"],
        }
    if "key_factors" in system:  # Stage 3 — Building Interpreter
        return {
            "type": "object",
            "properties": {
                "diagnosis": {"type": "string"},
                "key_factors": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["diagnosis", "key_factors"],
        }
    return "json"


def _ollama_user_reminder(system: str) -> str:
    """
    [ollama-fix] A terminal user-turn reminder. Structured outputs guarantee the
    *keys*, but small local models then satisfy the schema lazily (e.g. diagnosis
    = "moderate", copied from risk_level). This pushes them to fill each field
    with substance specific to THIS room. Stage-aware so each stage gets the right
    instruction.
    """
    if "shortlist" in system:  # Stage 4b
        return (
            "\n\n---\nFor each shortlisted strategy write a justification of 1-2 full "
            "sentences referencing THIS room's orientation, WWR, floor and occupant, "
            "and a concrete feasibility_note. Pick strategy_ids only from "
            "eligible_strategies. Do not echo input keys or invent data."
        )
    if "key_factors" in system:  # Stage 3
        return (
            "\n\n---\nWrite the diagnosis as 3-5 FULL SENTENCES naming this room's "
            "façade orientation, floor level, ventilation, occupant vulnerability and "
            "the applied UHI. key_factors: 2-4 short phrases. Do not answer with a "
            "single word and do not echo input keys."
        )
    return (
        "\n\n---\nReturn ONLY the JSON object matching the schema in the system "
        "instructions — describe THIS input, do not echo input fields or invent data."
    )


async def _ollama_chat(sem: "asyncio.Semaphore", system: str, user: str, max_tokens: int) -> str:
    """
    Call a local Ollama model via /api/chat. format="json" forces valid JSON
    output. httpx is available because the anthropic package depends on it.
    """
    import httpx

    # [ollama-fix] Under the bare format="json" mode, local models (qwen2.5:7b,
    # llama3.1:8b) *continue* the large input JSON — echoing its fields and even
    # inventing weather/date data — instead of following the system schema, so
    # diagnosis/shortlist come back empty (0/12 rooms). Fix: use Ollama structured
    # outputs — pass the concrete JSON Schema as `format` so decoding is grammar-
    # constrained to exactly the requested keys (extra/hallucinated keys become
    # impossible). The schema is chosen from the system prompt's stage. Verified
    # 0/12 → full output with qwen2.5:7b. Affects only the Ollama branch.
    fmt = _ollama_format_schema(system)
    user_steered = user + _ollama_user_reminder(system)

    payload = {
        "model": _ollama_model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_steered},
        ],
        "stream": False,
        "format": fmt,
        "options": {"num_predict": max_tokens, "temperature": 0.2},
    }
    try:
        async with sem:
            async with httpx.AsyncClient(timeout=600.0) as http:
                resp = await http.post(f"{_ollama_url()}/api/chat", json=payload)
                resp.raise_for_status()
                return resp.json()["message"]["content"]
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Ollama not reachable at {_ollama_url()} — is Ollama running? "
            f"Install from ollama.com, then: ollama pull {_ollama_model()}"
        ) from exc


async def _chat(client, sem: "asyncio.Semaphore", system: str, user: str, max_tokens: int) -> str:
    """Provider-agnostic chat call. client=None means Ollama."""
    if client is not None:
        response = await _create_with_retry(
            client, sem,
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text.strip()
    return (await _ollama_chat(sem, system, user, max_tokens)).strip()

# ── System prompts ──────────────────────────────────────────────────────────────

_STAGE3_SYSTEM = """\
You are a building health diagnostician for the HVRA (Heat Vulnerability Retrofit Assistant) system.

Your role: translate computed building performance data into a plain-language heat risk assessment \
for one specific room.

Rules:
- Read the provided room JSON carefully. Write about THIS room's specific conditions.
- Name the actual problems: façade orientation, WWR, ventilation situation, floor level, \
  occupant vulnerability, nocturnal recovery outcome, UHI contribution.
- Do NOT invent numbers. Every temperature, score, and flag you mention must appear in the JSON.
- Do NOT add information not present in the JSON. Do NOT speculate.
- Write in clear English readable by a housing officer or municipal official — not academic jargon.
- diagnosis must be 3–5 sentences, specific to this room. Name the room, orientation, risk level.
- key_factors must be 2–4 short phrases (5 words or fewer each) listing the dominant risk drivers.

Return ONLY valid JSON — no markdown, no code fences, no commentary:
{
  "diagnosis": "<3-5 sentence paragraph specific to this room>",
  "key_factors": ["<factor 1>", "<factor 2>", "<factor 3>"]
}"""

_STAGE4B_SYSTEM = """\
You are a retrofit strategy recommender for the HVRA (Heat Vulnerability Retrofit Assistant) system.

Your role: select and rank the top 3 retrofit strategies from the eligible set that best address \
the specific heat risk problems diagnosed in this room.

Reasoning order:
1. FIT first — which strategies directly address the diagnosed problems in this specific room?
2. Then rank by health impact per euro within the eligible set.
3. Flag any beneficial strategy combinations (e.g. shading + night purge together).
4. If occupant.age_bracket is 75+ and AC_access is false: weight low-cost and low-disruption \
   strategies higher, even if their delta_T is slightly lower.

Number constraints — you MUST respect these:
- delta_T_expected_C must be a value within [delta_T_min, delta_T_max] from the strategy data.
- cost_eur_m2 must be within [cost_eur_m2_min, cost_eur_m2_max] from the strategy data.
- carbon_kgCO2_m2 must match the value in the strategy data exactly.
- Never invent, extrapolate, or approximate values outside the provided ranges.

Justification rules:
- Each justification must reference THIS room's specific data: orientation, WWR, floor, \
  occupant condition. No generic text.
- For phase_change_materials: explicitly state it shifts peak timing, not magnitude.
- feasibility_note must flag permit requirements, structural checks, or disruption risks.

Shading alternates rule:
- external_shading_louvers, operable_external_sunscreen, and window_external_shutters all \
  solve the SAME problem (solar gain through glazing) by different physical means. They are \
  budget/operability alternates of each other, NOT independent strategies.
- Include AT MOST ONE of these three in your top-3 shortlist, whichever best fits this room \
  (the other two will be attached automatically as alternates — do not list them separately).

Return ONLY valid JSON — no markdown, no code fences, no commentary:
{
  "shortlist": [
    {
      "strategy_id": "<id from eligible_strategies>",
      "rank": 1,
      "justification": "<specific to this room — names orientation, WWR, occupant, key_factors>",
      "delta_T_expected_C": <number within strategy delta_T range>,
      "cost_eur_m2": <number within strategy cost range>,
      "carbon_kgCO2_m2": <number from strategy data>,
      "feasibility_note": "<permits, structural checks, disruption level>",
      "literature_source": "<from strategy data>"
    },
    { "rank": 2, ... },
    { "rank": 3, ... }
  ]
}"""


# ── Public entry point ──────────────────────────────────────────────────────────

async def run_llm_stages(
    pipeline_result: dict[str, Any],
    job_dir: str,
    api_key: str,
    strategy_library: list[dict],
) -> dict[str, Any]:
    """
    Run Stage 3 (Building Interpreter) and Stage 4b (Retrofit Recommender)
    for all rooms in parallel.

    Updates pipeline_result["rooms"] in place with diagnosis, key_factors, shortlist.
    Re-writes room_problems.json and writes shortlist.json.

    Parameters
    ----------
    pipeline_result : dict
        Return value of run_pipeline().
    job_dir : str
        Job output directory (where room_problems.json etc. live).
    api_key : str
        Anthropic API key.
    strategy_library : list[dict]
        Full strategy library (loaded from strategy_library.json).
    """
    room_jsons = pipeline_result.get("rooms", [])
    if not room_jsons:
        return pipeline_result

    provider = llm_provider()
    if provider == "ollama":
        client = None  # _chat() routes to the local Ollama server
        sem = asyncio.Semaphore(int(os.environ.get("OLLAMA_CONCURRENCY", "1")))
        logger.info("LLM provider: ollama (%s at %s)", _ollama_model(), _ollama_url())
    else:
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            pipeline_result.setdefault("warnings", []).append(
                "anthropic package not installed — Stage 3 and 4b skipped. "
                "Run: pip install anthropic"
            )
            return pipeline_result
        client = AsyncAnthropic(api_key=api_key)
        sem = asyncio.Semaphore(_MAX_CONCURRENT_CALLS)
        logger.info("LLM provider: anthropic (%s)", MODEL)

    lib_index = {s["id"]: s for s in strategy_library}
    llm_warnings: list[str] = []

    # ── Stage 3: all rooms in parallel (throttled) ─────────────────────────────
    logger.info("Stage 3: running Building Interpreter for %d rooms in parallel", len(room_jsons))
    stage3_results = await asyncio.gather(
        *[_call_stage3(room, client, sem) for room in room_jsons],
        return_exceptions=True,
    )
    stage3_failures = 0
    for room, result in zip(room_jsons, stage3_results):
        if isinstance(result, Exception):
            logger.error("Stage 3 failed for %s: %s", room["room_id"], result)
            stage3_failures += 1
        else:
            room["ai_outputs"]["diagnosis"] = result.get("diagnosis", "")
            room["ai_outputs"]["key_factors"] = result.get("key_factors", [])
    if stage3_failures:
        llm_warnings.append(
            f"Stage 3 (diagnosis) failed for {stage3_failures}/{len(room_jsons)} rooms — "
            "check logs and ANTHROPIC_API_KEY."
        )
    logger.info(
        "Stage 3 complete: %d/%d rooms succeeded",
        len(room_jsons) - stage3_failures, len(room_jsons),
    )

    # ── Stage 4b: all rooms in parallel ────────────────────────────────────────
    logger.info("Stage 4b: running Retrofit Recommender for %d rooms in parallel", len(room_jsons))
    stage4b_results = await asyncio.gather(
        *[_call_stage4b(room, lib_index, client, sem) for room in room_jsons],
        return_exceptions=True,
    )
    stage4b_failures = 0
    for room, result in zip(room_jsons, stage4b_results):
        if isinstance(result, Exception):
            logger.error("Stage 4b failed for %s: %s", room["room_id"], result)
            stage4b_failures += 1
        else:
            room["ai_outputs"]["shortlist"] = result.get("shortlist", [])
    if stage4b_failures:
        llm_warnings.append(
            f"Stage 4b (shortlist) failed for {stage4b_failures}/{len(room_jsons)} rooms — "
            "check logs and ANTHROPIC_API_KEY."
        )
    logger.info(
        "Stage 4b complete: %d/%d rooms succeeded",
        len(room_jsons) - stage4b_failures, len(room_jsons),
    )

    # ── Write updated output files ──────────────────────────────────────────────
    from .scoring import write_room_problems_json
    write_room_problems_json(room_jsons, job_dir)
    shortlist_path = _write_shortlist_json(room_jsons, job_dir)

    pipeline_result["rooms"] = room_jsons
    pipeline_result["files"]["shortlist"] = shortlist_path
    pipeline_result.setdefault("warnings", []).extend(llm_warnings)
    return pipeline_result


# ── Internal: Stage 3 ──────────────────────────────────────────────────────────

async def _call_stage3(room: dict, client, sem: "asyncio.Semaphore") -> dict:
    """
    Call the LLM for Stage 3 (Building Interpreter) for one room.
    Returns {"diagnosis": str, "key_factors": list[str]}.
    Raises on LLM error or schema validation failure.
    """
    # Strip ai_outputs — those are the fields we are generating
    room_for_llm = {k: v for k, v in room.items() if k != "ai_outputs"}
    if "facades" in room_for_llm:
        room_for_llm["facades"] = _facades_for_llm(room_for_llm["facades"])

    text = await _chat(
        client, sem,
        system=_STAGE3_SYSTEM,
        user=json.dumps(room_for_llm, ensure_ascii=False),
        max_tokens=1024,
    )
    parsed = _parse_json_response(
        text, context=f"Stage3/{room['room_id']}", expected_keys={"diagnosis", "key_factors"}
    )

    # Schema validation
    if not isinstance(parsed.get("diagnosis"), str) or not parsed["diagnosis"].strip():
        raise ValueError(f"Stage 3 missing or empty 'diagnosis' field: {parsed}")
    if not isinstance(parsed.get("key_factors"), list) or not parsed["key_factors"]:
        raise ValueError(f"Stage 3 missing or empty 'key_factors' field: {parsed}")

    return {
        "diagnosis": parsed["diagnosis"].strip(),
        "key_factors": [str(f).strip() for f in parsed["key_factors"][:4]],
    }


# ── Internal: Stage 4b ─────────────────────────────────────────────────────────

async def _call_stage4b(room: dict, lib_index: dict, client, sem: "asyncio.Semaphore") -> dict:
    """
    Call the LLM for Stage 4b (Retrofit Recommender) for one room.
    Returns {"shortlist": list[dict]}.
    Raises on LLM error or schema validation failure.
    """
    eligible_ids: list[str] = room.get("ai_outputs", {}).get("eligible_strategies", [])
    eligible_strategies = [lib_index[sid] for sid in eligible_ids if sid in lib_index]

    if not eligible_strategies:
        logger.warning(
            "Stage 4b: room %s has no eligible strategies — shortlist will be empty",
            room["room_id"],
        )
        return {"shortlist": []}

    # Build condensed room context — everything the LLM needs, nothing it doesn't
    room_context = {
        "room_id":       room["room_id"],
        "room_name":     room["room_name"],
        "room_type":     room["room_type"],
        "floor":         room["floor"],
        "area_m2":       room["area_m2"],
        "facades":       _facades_for_llm(room["facades"]),
        "ventilation":   room["ventilation"],
        "envelope":      room["envelope"],
        "thermal_scores": room["thermal_scores"],
        "occupant":      room["occupant"],
        "building":      room["building"],
        "composite_score": room["composite_score"],
        # Stage 3 outputs give the LLM narrative context for justifications
        "diagnosis":     room.get("ai_outputs", {}).get("diagnosis", ""),
        "key_factors":   room.get("ai_outputs", {}).get("key_factors", []),
    }

    user_content = json.dumps(
        {"room": room_context, "eligible_strategies": eligible_strategies},
        ensure_ascii=False,
    )

    text = await _chat(
        client, sem,
        system=_STAGE4B_SYSTEM,
        user=user_content,
        max_tokens=2048,
    )
    parsed = _parse_json_response(
        text, context=f"Stage4b/{room['room_id']}", expected_keys={"shortlist"}
    )

    if not isinstance(parsed.get("shortlist"), list):
        raise ValueError(f"Stage 4b missing 'shortlist' list: {parsed}")

    shortlist = _validate_shortlist(parsed["shortlist"], eligible_ids, lib_index)

    # Attach deterministic shading alternates (louvers / sunscreen / shutters
    # are interchangeable solutions to the same problem — not independently
    # ranked, but offered as budget-ordered options alongside whichever one
    # the LLM picked).
    income_category = room.get("occupant", {}).get("income_category", "medium")
    for item in shortlist:
        alternates = _attach_shading_alternates(item, eligible_ids, lib_index, income_category)
        if alternates:
            item["alternates"] = alternates

    return {"shortlist": shortlist}


# ── Internal: helpers ──────────────────────────────────────────────────────────

def _parse_json_response(text: str, context: str = "", expected_keys: set | None = None) -> dict:
    """
    Parse JSON from an LLM response.
    Strips markdown code fences if present (e.g. ```json ... ```).
    Raises json.JSONDecodeError on failure.

    expected_keys: if given and the top-level object has none of these keys,
    unwrap common wrapper shapes a model may add on its own (e.g. Ollama's
    smaller models sometimes emit {"status": "success", "result": {...}}
    instead of the requested schema directly) — checks "result", "data",
    "response" for an inner object that DOES have the expected keys.
    """
    stripped = text.strip()

    # Strip markdown code fences: ```json\n...\n```  or  ```\n...\n```
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Drop first line (```json or ```) and last line (```)
        inner_lines = lines[1:] if len(lines) > 1 else lines
        if inner_lines and inner_lines[-1].strip() == "```":
            inner_lines = inner_lines[:-1]
        stripped = "\n".join(inner_lines).strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse error [%s]: %s\nRaw text: %s", context, exc, text[:500])
        raise

    if expected_keys and isinstance(parsed, dict) and not (expected_keys & parsed.keys()):
        for wrapper_key in ("result", "data", "response"):
            inner = parsed.get(wrapper_key)
            if isinstance(inner, dict) and (expected_keys & inner.keys()):
                logger.info(
                    "Stage response wrapped under '%s' key [%s] — unwrapping", wrapper_key, context
                )
                return inner

    return parsed


def _validate_shortlist(
    shortlist: list,
    eligible_ids: list[str],
    lib_index: dict,
) -> list[dict]:
    """
    Validate and clean the Stage 4b shortlist:
    - Filter out strategy_ids not in the eligible set (hallucination guard)
    - Ensure numeric fields stay within library ranges
    - Re-number ranks 1, 2, 3 sequentially
    - Keep at most 3 items

    SOURCE: HVRA_build_reference_4.md §Stage 4b — LLM constraints.
    """
    required_keys = {
        "strategy_id", "rank", "justification",
        "delta_T_expected_C", "cost_eur_m2", "carbon_kgCO2_m2",
        "feasibility_note", "literature_source",
    }
    eligible_set = set(eligible_ids)
    validated: list[dict] = []
    seen_shading_alt = False

    for item in shortlist:
        if not isinstance(item, dict):
            continue
        sid = item.get("strategy_id", "")
        if sid not in eligible_set:
            logger.warning("Stage 4b returned non-eligible strategy_id '%s' — filtered out", sid)
            continue
        if not required_keys.issubset(item.keys()):
            missing = required_keys - item.keys()
            logger.warning("Stage 4b item for '%s' missing keys %s — skipping", sid, missing)
            continue

        # Safety net for weaker/local models that ignore the "pick at most
        # one shading alternate" instruction: keep only the first one seen.
        if sid in SHADING_ALTERNATE_GROUP:
            if seen_shading_alt:
                logger.info(
                    "Stage 4b returned a second shading alternate '%s' — "
                    "dropped, will be offered as an alternate instead", sid
                )
                continue
            seen_shading_alt = True

        strategy = lib_index.get(sid, {})

        # Clamp numeric fields to library ranges
        item["delta_T_expected_C"] = _clamp(
            float(item["delta_T_expected_C"]),
            strategy.get("delta_T_min", 0),
            strategy.get("delta_T_max", 10),
        )
        item["cost_eur_m2"] = _clamp(
            float(item["cost_eur_m2"]),
            strategy.get("cost_eur_m2_min", 0),
            strategy.get("cost_eur_m2_max", 9999),
        )
        item["carbon_kgCO2_m2"] = strategy.get(
            "carbon_kgCO2_m2", float(item.get("carbon_kgCO2_m2", 0))
        )

        validated.append(item)
        if len(validated) == 3:
            break

    # Re-number ranks sequentially
    for i, item in enumerate(validated, start=1):
        item["rank"] = i

    return validated


# Strategies that all address the same problem (solar gain via shading) through
# different physical means — interchangeable depending on budget/operability
# preference rather than independently rankable. When one is shortlisted, the
# others (if eligible for this room) are attached as "alternates" rather than
# competing for a separate shortlist slot.
SHADING_ALTERNATE_GROUP = {
    "external_shading_louvers", "operable_external_sunscreen", "window_external_shutters",
}


def _attach_shading_alternates(
    shortlisted: dict,
    eligible_ids: list[str],
    lib_index: dict,
    income_category: str,
) -> list[dict]:
    """
    For a shortlisted shading strategy, return the other eligible members of
    SHADING_ALTERNATE_GROUP as budget-ordered alternates.

    Ordering depends on income_category (proxy for budget sensitivity):
      low    → cheapest first (cost_eur_m2_min ascending)
      medium → balanced (delta_T per euro descending — best value)
      high   → best performance first (delta_T_max descending)

    Deterministic, computed from strategy_library.json — not LLM-generated —
    so the figures stay exactly within the library's sourced ranges.
    """
    sid = shortlisted.get("strategy_id")
    if sid not in SHADING_ALTERNATE_GROUP:
        return []

    other_ids = [
        s for s in SHADING_ALTERNATE_GROUP
        if s != sid and s in eligible_ids and s in lib_index
    ]
    if not other_ids:
        return []

    def sort_key(other_id: str):
        s = lib_index[other_id]
        cost_min = s.get("cost_eur_m2_min", 0)
        cost_max = s.get("cost_eur_m2_max", cost_min)
        dt_max = s.get("delta_T_max", 0)
        cost_mid = (cost_min + cost_max) / 2 or 1
        if income_category == "low":
            return cost_min
        if income_category == "high":
            return -dt_max
        return -(dt_max / cost_mid)   # medium / unknown: best ΔT per euro first

    other_ids.sort(key=sort_key)

    alternates = []
    for oid in other_ids:
        s = lib_index[oid]
        alternates.append({
            "strategy_id": oid,
            "name": s.get("name", oid),
            "delta_T_min": s.get("delta_T_min"),
            "delta_T_max": s.get("delta_T_max"),
            "cost_eur_m2_min": s.get("cost_eur_m2_min"),
            "cost_eur_m2_max": s.get("cost_eur_m2_max"),
            "carbon_kgCO2_m2": s.get("carbon_kgCO2_m2"),
            "literature_source": s.get("literature_source"),
        })
    return alternates


def _clamp(value: float, lo: float, hi: float) -> float:
    return round(max(lo, min(hi, value)), 2)


def _write_shortlist_json(room_jsons: list[dict], job_dir: str) -> str:
    """
    Write shortlist.json — per-room top-3 strategies.
    SOURCE: HVRA_build_reference_4.md §Pipeline — shortlist.json produced by Stage 4b.
    """
    shortlist_data = [
        {
            "room_id":        r["room_id"],
            "ifc_global_id":  r.get("ifc_global_id", ""),
            "room_name":      r["room_name"],
            "composite_score": r["composite_score"],
            "risk_level":     r["thermal_scores"]["risk_level"],
            "shortlist":      r.get("ai_outputs", {}).get("shortlist", []),
        }
        for r in room_jsons
    ]
    os.makedirs(job_dir, exist_ok=True)
    path = os.path.join(job_dir, "shortlist.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(shortlist_data, f, indent=2, ensure_ascii=False)
    logger.info("shortlist.json written: %d rooms → %s", len(shortlist_data), path)
    return path
