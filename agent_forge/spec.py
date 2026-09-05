"""Core data structures shared across the generate -> run -> analyze -> improve loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    name: str
    description: str


@dataclass
class AgentSpec:
    """An agent architecture: what the generator produces and the improver edits."""

    system_prompt: str
    tools: list[ToolSpec]
    orchestration: str  # "single-shot" | "react-loop" | "planner-executor"
    memory_notes: list[str] = field(default_factory=list)
    version: int = 0


@dataclass
class RunTrace:
    task_id: str
    input: Any
    output: Any
    tool_calls: list[dict] = field(default_factory=list)
    latency_s: float = 0.0
    cost_usd: float = 0.0
    error: str | None = None


@dataclass
class RoundResult:
    agent_spec: AgentSpec
    traces: list[RunTrace]
    metrics: dict[str, float]
    failure_modes: dict[str, int]


class Domain(Protocol):
    """A domain plugs into the loop by implementing this interface."""

    name: str
    goal: str
    tools: list[ToolSpec]

    def tasks(self) -> list[Any]:
        """Return the eval task set."""
        ...

    def run(self, agent_spec: AgentSpec, task: Any) -> RunTrace:
        """Execute one task under the given agent spec. Must never raise."""
        ...

    def score(self, traces: list[RunTrace]) -> tuple[dict[str, float], dict[str, int]]:
        """Return (metrics, named failure-mode counts) for a batch of traces."""
        ...
