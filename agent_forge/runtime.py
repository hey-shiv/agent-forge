"""Executes an AgentSpec against one task.

This is what makes `orchestration` a real variable rather than a label: each
mode below genuinely changes how many model calls happen and whether tools are
reachable. The improver can therefore fix a class of failure that no amount of
prompt editing would fix.

  single-shot      one call, no tools. Cheapest, fastest, blindest.
  react-loop       tool-calling loop until the model stops asking for tools.
  planner-executor plan first in plain text, then execute with tools. Helps
                   when a task has several parts that a single pass conflates.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from . import llm
from .spec import AgentSpec, RunTrace

# A search-style task (scan candidate slots until one fits) needs many more
# tool round-trips than a lookup-style task. At 6 the scheduler domain ran out
# of iterations mid-search and returned nothing, which surfaced as a
# "no_parseable_time_returned" cluster that no prompt change could fix.
MAX_TOOL_ITERATIONS = 14


def _openai_tools(spec: AgentSpec, impls: dict[str, Callable]) -> list[dict]:
    """Expose only the tools the spec declares AND the domain implements."""
    out = []
    for tool in spec.tools:
        if tool.name not in impls:
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "input": {
                                "type": "string",
                                "description": "Argument for this tool.",
                            }
                        },
                        "required": ["input"],
                    },
                },
            }
        )
    return out


def _memory_block(spec: AgentSpec) -> str:
    if not spec.memory_notes:
        return ""
    notes = "\n".join(f"- {n}" for n in spec.memory_notes)
    return f"\n\nKeep track of the following as you work:\n{notes}"


def run_agent(
    spec: AgentSpec,
    task_id: str,
    task_input: str,
    tool_impls: dict[str, Callable[[str], str]] | None = None,
    response_format_hint: str = "",
) -> RunTrace:
    """Run one task under `spec`. Never raises — a crashed agent is a data
    point (a reliability failure), not a reason to abort the whole round."""
    tool_impls = tool_impls or {}
    client = llm._get_client()
    system = spec.system_prompt + _memory_block(spec)
    if response_format_hint:
        system += f"\n\n{response_format_hint}"

    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    tool_calls_made: list[dict] = []
    t0 = time.time()
    in_tok = out_tok = 0

    try:
        if spec.orchestration == "planner-executor":
            plan = llm.complete(
                system,
                f"Task:\n{task_input}\n\nWrite a short plan. Do not solve it yet.",
                max_completion_tokens=1200,
            )
            in_tok += plan.usage.input_tokens
            out_tok += plan.usage.output_tokens
            messages.append({"role": "assistant", "content": f"Plan:\n{plan.text}"})

        messages.append({"role": "user", "content": task_input})

        use_tools = spec.orchestration in ("react-loop", "planner-executor")
        tools = _openai_tools(spec, tool_impls) if use_tools else []

        final_text = ""
        for _ in range(MAX_TOOL_ITERATIONS if use_tools else 1):
            kwargs: dict[str, Any] = {
                "model": llm.DEFAULT_MODEL,
                "messages": messages,
                "max_completion_tokens": 2500,
                "reasoning_effort": "low",
            }
            if tools:
                kwargs["tools"] = tools

            resp = client.chat.completions.create(**kwargs)
            usage = resp.usage
            in_tok += usage.prompt_tokens
            out_tok += usage.completion_tokens

            choice = resp.choices[0].message
            requested = getattr(choice, "tool_calls", None)

            if not requested:
                final_text = choice.content or ""
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": choice.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in requested
                    ],
                }
            )

            for tc in requested:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                arg = args.get("input", "")

                try:
                    result = str(tool_impls[name](arg))
                except Exception as exc:  # a bad tool call is a failure mode
                    result = f"ERROR: {exc}"

                tool_calls_made.append({"tool": name, "input": arg, "result": result[:200]})
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result}
                )

        return RunTrace(
            task_id=task_id,
            input=task_input,
            output=final_text.strip(),
            tool_calls=tool_calls_made,
            latency_s=time.time() - t0,
            cost_usd=(
                in_tok / 1_000_000 * llm.USD_PER_1M_INPUT_TOKENS
                + out_tok / 1_000_000 * llm.USD_PER_1M_OUTPUT_TOKENS
            ),
            error=None,
        )

    except Exception as exc:
        return RunTrace(
            task_id=task_id,
            input=task_input,
            output="",
            tool_calls=tool_calls_made,
            latency_s=time.time() - t0,
            cost_usd=0.0,
            error=f"{type(exc).__name__}: {exc}",
        )
