"""Proposes the next AgentSpec from a round's metrics and failure modes.

Two properties matter more than the wording of the prompt here, and both were
added after watching an early run get steadily *worse*:

1. The improver sees the full history of what has already been tried and what
   it did to the score. Without it, it re-proposes ideas it has already tried
   and undoes changes that worked — in one observed run it instructed the
   agent to stop calling its lookup tool, and accuracy fell for two rounds.

2. The caller can mark the previous attempt as a regression, which is passed
   in explicitly so the model is told "that made things worse, do something
   different" rather than being left to infer it.
"""

from __future__ import annotations

import json

from . import llm
from .spec import AgentSpec, RoundResult

_SYSTEM = """You improve agent architectures based on evaluation results.

You will be given the current agent spec, the history of changes already tried \
with their scores, and the failure modes from the most recent round.

Rules:
- Propose exactly ONE targeted change. Do not rewrite everything.
- Do not repeat a change that has already been tried and did not help.
- Address the LARGEST failure cluster, not the easiest one.
- Some failures cannot be fixed by prompt wording. A failure mode about missing \
a second issue in a multi-part input usually means the orchestration is wrong: \
consider "planner-executor". A failure mode about a tool not being called \
usually means the prompt must require that tool, or orchestration must be \
"react-loop" so tools are reachable at all.
- Never instruct the agent to stop using a tool that the task depends on.

Output a JSON object with keys:
  system_prompt: string - the full new system prompt
  orchestration: one of "single-shot", "react-loop", "planner-executor"
  memory_notes: array of short strings
  change_summary: one sentence naming what you changed and which failure it targets

Respond with ONLY the JSON object. No markdown fences, no commentary."""


def _history_block(history: list[RoundResult], summaries: list[str]) -> str:
    if not history:
        return "No previous rounds."
    lines = []
    for i, (r, s) in enumerate(zip(history, summaries)):
        lines.append(
            f"round {i} (v{r.agent_spec.version}, {r.agent_spec.orchestration}): "
            f"accuracy={r.metrics.get('accuracy')} "
            f"tool_calls={r.metrics.get('tool_calls')} "
            f"failures={json.dumps(r.failure_modes)}\n"
            f"    change that produced it: {s}"
        )
    return "\n".join(lines)


def _stuck_cluster(history: list[RoundResult], lookback: int = 2) -> str | None:
    """Name a failure cluster that has survived the last `lookback` rounds.

    Motivation, from a real run: the generator opened with planner-executor on
    the scheduling domain and scored 0.333. Over the next three rounds the
    improver rewrote prompts each time and never touched orchestration — the
    score went 0.333, 0.250, 0.167, 0.250. It was editing wording inside an
    architecture that could not work. Meanwhile sibling runs that happened to
    open with react-loop or single-shot scored 0.917 and 1.000.

    So: when the same cluster survives repeated prompt edits, that is evidence
    the architecture is wrong, and the improver is told so explicitly.
    """
    if len(history) < lookback:
        return None
    recent = history[-lookback:]
    if not all(r.failure_modes for r in recent):
        return None

    common = set(recent[0].failure_modes)
    for r in recent[1:]:
        common &= set(r.failure_modes)
    if not common:
        return None

    # the persistent cluster that costs the most in the latest round
    latest = recent[-1].failure_modes
    return max(common, key=lambda k: latest.get(k, 0))


def improve(
    round_result: RoundResult,
    history: list[RoundResult] | None = None,
    summaries: list[str] | None = None,
    regressed: bool = False,
) -> tuple[AgentSpec, str]:
    spec = round_result.agent_spec
    history = history or []
    summaries = summaries or []

    regression_note = ""
    if regressed:
        regression_note = (
            "\nIMPORTANT: the most recent change made the score WORSE. It has been "
            "rolled back and you are now editing the best-scoring spec so far. "
            "Do not retry that idea — try a different lever.\n"
        )

    stuck = _stuck_cluster(history)
    if stuck:
        others = [o for o in ("single-shot", "react-loop", "planner-executor")
                  if o != spec.orchestration]
        regression_note += (
            f"\nESCALATE: the failure cluster '{stuck}' has now survived several "
            f"rounds of prompt editing. Repeated wording changes are not fixing "
            f"it, which is evidence the ARCHITECTURE is wrong rather than the "
            f"prompt. For this proposal you must change `orchestration` to one of "
            f"{others} and explain which failure that targets. Do not merely "
            f"reword the system prompt again.\n"
        )

    prompt = (
        f"History of what has been tried:\n{_history_block(history, summaries)}\n"
        f"{regression_note}\n"
        f"Current (best-so-far) spec you are editing:\n"
        f"  orchestration: {spec.orchestration}\n"
        f"  memory_notes: {spec.memory_notes}\n"
        f"  system_prompt:\n{spec.system_prompt}\n\n"
        f"Most recent metrics: {json.dumps(round_result.metrics)}\n"
        f"Most recent failure modes: {json.dumps(round_result.failure_modes)}\n"
    )

    # Budget note: at reasoning_effort="medium" this call was observed spending
    # its ENTIRE 4000-token budget on hidden reasoning and returning an empty
    # string. Low effort plus a wider budget is both cheaper and more reliable.
    data, _usage = llm.complete_json(
        _SYSTEM, prompt, max_completion_tokens=8000, reasoning_effort="low"
    )

    new_spec = AgentSpec(
        system_prompt=data["system_prompt"],
        tools=spec.tools,
        orchestration=data["orchestration"],
        memory_notes=data.get("memory_notes", []),
        version=spec.version + 1,
    )
    return new_spec, data.get("change_summary", "")
