"""Domain 3 — constraint satisfaction: find the earliest valid meeting slot.

This is the GENERALITY domain. It was written after the system was already
built and tuned on ticket routing and invoice extraction, and nothing in
agent_forge/ was changed to accommodate it. It exists to test the Track 1
claim directly: given only a goal, a tool list and an eval function for a task
the system has never seen, does it still produce a working agent and improve it?

A third distinct SHAPE:

  ticket_routing      classification          output: a label
  invoice_extraction  structured extraction   output: a JSON record
  meeting_scheduler   constraint satisfaction output: a time

Constraint satisfaction is chosen deliberately because small models are weak at
it. Holding four attendees' busy blocks in mind while scanning for the earliest
gap that fits a duration is exactly the kind of multi-condition bookkeeping that
gpt-5-nano gets wrong — which is what produces the headroom an improver needs.
"""

from __future__ import annotations

import re

from agent_forge.runtime import run_agent
from agent_forge.spec import AgentSpec, RunTrace, ToolSpec

GOAL = (
    "Find a meeting time. You are given several attendees, the times each of them "
    "is already busy, how long the meeting needs to be, and the working hours the "
    "meeting must fall inside. Reply with the start time of the meeting in 24-hour "
    "HH:MM format."
)

TOOLS = [
    ToolSpec(
        "check_slot",
        "Check whether a proposed meeting slot works. Input format: "
        "'<task_id> <HH:MM>' e.g. 's3 14:30'. Returns whether every attendee is "
        "free for the full duration at that start time, and if not, who is busy.",
    ),
]


def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


TASKS: list[dict] = [
    {
        "id": "s1", "duration": 60, "hours": ["09:00", "17:00"],
        "busy": {"Ana": [["09:00", "10:00"], ["11:00", "12:30"]],
                 "Ben": [["09:00", "11:00"]],
                 "Cara": [["12:00", "13:00"]]},
        "gold": "13:00",
    },
    {
        "id": "s2", "duration": 30, "hours": ["09:00", "17:00"],
        "busy": {"Dev": [["09:00", "09:30"], ["10:00", "10:30"]],
                 "Eli": [["09:30", "10:00"], ["10:30", "11:00"]]},
        "gold": "11:00",
    },
    {
        "id": "s3", "duration": 90, "hours": ["10:00", "18:00"],
        "busy": {"Fay": [["10:00", "11:30"], ["13:00", "14:00"]],
                 "Gus": [["11:30", "12:30"]],
                 "Hana": [["14:00", "15:00"]]},
        "gold": "15:00",
    },
    {
        "id": "s4", "duration": 45, "hours": ["08:00", "16:00"],
        "busy": {"Ivy": [["08:00", "09:00"]],
                 "Jon": [["09:00", "09:30"], ["10:15", "11:00"]],
                 "Kim": [["09:30", "10:15"]]},
        "gold": "11:00",
    },
    {
        "id": "s5", "duration": 60, "hours": ["09:00", "17:00"],
        "busy": {"Lea": [["09:00", "12:00"]],
                 "Max": [["12:00", "14:00"]],
                 "Nia": [["14:00", "15:00"]],
                 "Omar": [["15:00", "15:30"]]},
        "gold": "15:30",
    },
    {
        "id": "s6", "duration": 30, "hours": ["13:00", "18:00"],
        "busy": {"Pia": [["13:00", "14:00"], ["14:30", "15:00"]],
                 "Quin": [["14:00", "14:30"], ["15:00", "15:30"]]},
        "gold": "15:30",
    },
    {
        "id": "s7", "duration": 120, "hours": ["09:00", "18:00"],
        "busy": {"Rex": [["09:00", "10:00"], ["12:00", "13:00"]],
                 "Sara": [["10:00", "11:00"]],
                 "Tom": [["13:00", "14:00"]]},
        "gold": "14:00",
    },
    {
        "id": "s8", "duration": 60, "hours": ["10:00", "16:00"],
        "busy": {"Uma": [["10:00", "11:00"], ["11:30", "12:00"]],
                 "Vik": [["12:00", "13:30"]],
                 "Wes": [["13:30", "14:00"]]},
        "gold": "14:00",
    },
    {
        "id": "s9", "duration": 45, "hours": ["09:00", "13:00"],
        "busy": {"Xia": [["09:00", "09:45"]],
                 "Yves": [["09:45", "10:30"], ["11:00", "11:30"]],
                 "Zoe": [["10:30", "11:00"]]},
        "gold": "11:30",
    },
    {
        "id": "s10", "duration": 30, "hours": ["09:00", "12:00"],
        "busy": {"Abe": [["09:00", "10:00"], ["10:30", "11:00"]],
                 "Bea": [["10:00", "10:30"], ["11:00", "11:15"]]},
        "gold": "11:15",
    },
    {
        "id": "s11", "duration": 60, "hours": ["08:00", "17:00"],
        "busy": {"Cal": [["08:00", "10:30"]],
                 "Dot": [["10:30", "11:00"], ["11:30", "12:00"]],
                 "Eve": [["11:00", "11:30"]]},
        "gold": "12:00",
    },
    {
        "id": "s12", "duration": 90, "hours": ["09:00", "17:00"],
        "busy": {"Fin": [["09:00", "10:00"]],
                 "Gia": [["10:00", "11:00"], ["12:00", "12:30"]],
                 "Hugo": [["11:00", "12:00"]]},
        "gold": "12:30",
    },
]

_BY_ID = {t["id"]: t for t in TASKS}


def _conflicts(task: dict, start_min: int) -> list[str]:
    """Return the names of attendees busy during [start, start+duration)."""
    end_min = start_min + task["duration"]
    clashing = []
    for person, blocks in task["busy"].items():
        for b_start, b_end in blocks:
            if start_min < _to_min(b_end) and end_min > _to_min(b_start):
                clashing.append(person)
                break
    return clashing


def check_slot(argument: str) -> str:
    """Tool implementation. Input: '<task_id> <HH:MM>'."""
    match = re.match(r"\s*(\S+)\s+(\d{1,2}:\d{2})\s*$", argument or "")
    if not match:
        return "Could not parse. Use the format '<task_id> <HH:MM>', e.g. 's3 14:30'."

    task_id, hhmm = match.group(1), match.group(2)
    task = _BY_ID.get(task_id)
    if task is None:
        return f"Unknown task id {task_id!r}."

    start = _to_min(hhmm)
    open_min, close_min = _to_min(task["hours"][0]), _to_min(task["hours"][1])
    if start < open_min or start + task["duration"] > close_min:
        return (
            f"{hhmm} is outside working hours "
            f"{task['hours'][0]}-{task['hours'][1]} for a "
            f"{task['duration']}-minute meeting."
        )

    clashing = _conflicts(task, start)
    if clashing:
        return f"{hhmm} does not work: {', '.join(sorted(clashing))} busy."
    return f"{hhmm} works: all attendees free for {task['duration']} minutes."


def _render(task: dict) -> str:
    lines = [
        f"Task id: {task['id']}",
        f"Meeting duration: {task['duration']} minutes",
        f"Working hours: {task['hours'][0]} to {task['hours'][1]}",
        "Existing commitments:",
    ]
    for person, blocks in task["busy"].items():
        spans = ", ".join(f"{a}-{b}" for a, b in blocks)
        lines.append(f"  {person}: {spans}")
    return "\n".join(lines)


_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")


class MeetingSchedulerDomain:
    name = "meeting_scheduler"
    goal = GOAL
    tools = TOOLS

    def tasks(self) -> list[dict]:
        return TASKS

    def run(self, agent_spec: AgentSpec, task: dict) -> RunTrace:
        return run_agent(
            agent_spec,
            task_id=task["id"],
            task_input=_render(task),
            tool_impls={"check_slot": check_slot},
            response_format_hint="Reply with ONLY the start time in HH:MM format.",
        )

    @staticmethod
    def _parse(output: str) -> str | None:
        matches = _TIME.findall(output or "")
        if not matches:
            return None
        h, m = matches[-1]  # the final time mentioned is the answer
        return f"{int(h):02d}:{m}"

    def score(self, traces: list[RunTrace]) -> tuple[dict[str, float], dict[str, int]]:
        correct = errors = 0
        failure_modes: dict[str, int] = {}

        def bump(mode: str) -> None:
            failure_modes[mode] = failure_modes.get(mode, 0) + 1

        for tr in traces:
            task = _BY_ID[tr.task_id]

            if tr.error:
                errors += 1
                bump("agent_crashed")
                continue

            answer = self._parse(tr.output)
            if answer is None:
                bump("no_parseable_time_returned")
                continue

            if answer == task["gold"]:
                correct += 1
                continue

            # Distinguish "invalid" from "valid but not earliest" — they call for
            # completely different fixes, so they must not share a cluster.
            start = _to_min(answer)
            open_min = _to_min(task["hours"][0])
            close_min = _to_min(task["hours"][1])

            if start < open_min or start + task["duration"] > close_min:
                bump("slot_outside_working_hours")
            elif _conflicts(task, start):
                used_tool = any(c["tool"] == "check_slot" for c in tr.tool_calls)
                bump(
                    "slot_conflicts_with_busy_block_despite_checking"
                    if used_tool
                    else "slot_conflicts_with_busy_block_no_check_called"
                )
            else:
                bump("valid_slot_but_not_the_earliest")

        n = len(traces) or 1
        metrics = {
            "accuracy": round(correct / n, 4),
            "reliability": round((n - errors) / n, 4),
            "avg_latency_s": round(sum(t.latency_s for t in traces) / n, 3),
            "total_cost_usd": round(sum(t.cost_usd for t in traces), 6),
            "tool_calls": sum(len(t.tool_calls) for t in traces),
        }
        return metrics, failure_modes
