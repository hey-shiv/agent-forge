"""Produces an initial AgentSpec from a goal + tool list, before any runs happen."""

from __future__ import annotations

from . import llm
from .spec import AgentSpec, ToolSpec

_SYSTEM = """You design agent architectures. Given a goal and a list of available \
tools, output a JSON object with keys:
  system_prompt: string - the system prompt for the agent
  orchestration: one of "single-shot", "react-loop", "planner-executor"
  memory_notes: array of short strings - things the agent should remember/track

Respond with ONLY the JSON object, no prose, no markdown fences."""


def generate(goal: str, tools: list[ToolSpec]) -> AgentSpec:
    tool_desc = "\n".join(f"- {t.name}: {t.description}" for t in tools)
    prompt = f"Goal:\n{goal}\n\nAvailable tools:\n{tool_desc}"

    # Boilerplate structure, not a judgement call — cheap reasoning is fine.
    data, _usage = llm.complete_json(_SYSTEM, prompt, reasoning_effort="low")

    return AgentSpec(
        system_prompt=data["system_prompt"],
        tools=tools,
        orchestration=data["orchestration"],
        memory_notes=data.get("memory_notes", []),
        version=0,
    )
