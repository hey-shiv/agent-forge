"""Tests for the parts of Agent Forge that must be right regardless of what any
model returns: the escalation rule, the scoring contracts, and the failure-mode
taxonomy. None of these call an API.

    .venv/bin/python -m pytest tests/ -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_forge.improver import _stuck_cluster
from agent_forge.spec import AgentSpec, RoundResult, RunTrace, ToolSpec
from domains.meeting_scheduler.domain import (
    MeetingSchedulerDomain,
    TASKS as SCHED_TASKS,
    _conflicts,
    _to_min,
    check_slot,
)
from domains.ticket_routing.domain import TASKS as TICKET_TASKS, TicketRoutingDomain
from scripts.measure_variance import build_summary, round_detail


def _spec(orch: str = "react-loop") -> AgentSpec:
    return AgentSpec(system_prompt="p", tools=[ToolSpec("t", "d")], orchestration=orch)


def _round(failures: dict, accuracy: float = 0.5) -> RoundResult:
    return RoundResult(
        agent_spec=_spec(), traces=[], metrics={"accuracy": accuracy},
        failure_modes=failures,
    )


# --------------------------------------------------------------------------
# escalation rule
# --------------------------------------------------------------------------

def test_stuck_cluster_detects_a_persistent_failure():
    history = [_round({"bad_thing": 4}), _round({"bad_thing": 3, "other": 1})]
    assert _stuck_cluster(history) == "bad_thing"


def test_stuck_cluster_is_silent_when_the_failure_changed():
    history = [_round({"bad_thing": 4}), _round({"different_thing": 3})]
    assert _stuck_cluster(history) is None


def test_stuck_cluster_is_silent_on_a_clean_round():
    history = [_round({"bad_thing": 4}), _round({})]
    assert _stuck_cluster(history) is None


def test_stuck_cluster_needs_enough_history():
    assert _stuck_cluster([_round({"bad_thing": 4})]) is None
    assert _stuck_cluster([]) is None


def test_stuck_cluster_picks_the_costliest_persistent_one():
    history = [
        _round({"minor": 1, "major": 5}),
        _round({"minor": 2, "major": 6}),
    ]
    assert _stuck_cluster(history) == "major"


# --------------------------------------------------------------------------
# ticket routing scoring
# --------------------------------------------------------------------------

def _ticket_trace(task_id: str, output: str, tool_calls=None, error=None) -> RunTrace:
    return RunTrace(task_id=task_id, input={}, output=output,
                    tool_calls=tool_calls or [], error=error)


def test_ticket_exact_match_scores_correct():
    domain = TicketRoutingDomain()
    metrics, failures = domain.score([_ticket_trace("c1", "technical")])
    assert metrics["accuracy"] == 1.0
    assert failures == {}


def test_ticket_multi_issue_needs_both_labels():
    domain = TicketRoutingDomain()
    # m1's gold is ["technical", "billing"] — one label alone is wrong
    metrics, failures = domain.score([_ticket_trace("m1", "technical")])
    assert metrics["accuracy"] == 0.0
    assert failures == {"missed_second_issue_in_multi_issue_ticket": 1}


def test_ticket_lookup_failure_distinguishes_tool_use():
    domain = TicketRoutingDomain()
    # n1's gold is refunds; answering "billing" is wrong either way, but WHY
    # differs depending on whether the tool was consulted.
    without = domain.score([_ticket_trace("n1", "billing")])[1]
    assert without == {"billing_refunds_confusion_no_lookup_called": 1}

    with_tool = domain.score(
        [_ticket_trace("n1", "billing",
                       tool_calls=[{"tool": "lookup_customer", "input": "x", "result": "y"}])]
    )[1]
    assert with_tool == {"billing_refunds_confusion_despite_lookup": 1}


def test_ticket_crash_counts_against_reliability_not_just_accuracy():
    domain = TicketRoutingDomain()
    metrics, failures = domain.score([_ticket_trace("c1", "", error="boom")])
    assert metrics["reliability"] == 0.0
    assert failures == {"agent_crashed": 1}


def test_every_ticket_gold_label_is_a_known_queue():
    from domains.ticket_routing.domain import QUEUES
    for task in TICKET_TASKS:
        for label in task["gold"]:
            assert label in QUEUES, f"{task['id']} has unknown label {label!r}"


def test_needs_lookup_items_are_genuinely_ambiguous():
    """The needs_lookup design only works if wording alone cannot decide the
    answer. Assert that at least one pair shares text but differs in gold."""
    lookups = [t for t in TICKET_TASKS if t["kind"] == "needs_lookup"]
    by_text: dict[str, set[str]] = {}
    for t in lookups:
        stem = t["text"].split(".")[0]
        by_text.setdefault(stem, set()).add(tuple(t["gold"]))
    ambiguous = [k for k, v in by_text.items() if len(v) > 1]
    assert ambiguous, "no needs_lookup pair shares wording with differing labels"


# --------------------------------------------------------------------------
# scheduler domain
# --------------------------------------------------------------------------

def test_every_scheduler_gold_is_the_true_earliest_slot():
    """Brute-force check that the labels are correct — an eval set with wrong
    labels silently caps the achievable score."""
    for task in SCHED_TASKS:
        open_m = _to_min(task["hours"][0])
        close_m = _to_min(task["hours"][1])
        earliest = next(
            (s for s in range(open_m, close_m - task["duration"] + 1, 5)
             if not _conflicts(task, s)),
            None,
        )
        assert earliest is not None, f"{task['id']} has no valid slot"
        assert f"{earliest // 60:02d}:{earliest % 60:02d}" == task["gold"], task["id"]


def test_check_slot_accepts_a_valid_slot():
    task = SCHED_TASKS[0]
    assert "works" in check_slot(f"{task['id']} {task['gold']}")


def test_check_slot_rejects_a_conflicting_slot():
    # s1: Ana is busy 09:00-10:00
    assert "does not work" in check_slot("s1 09:00")


def test_check_slot_rejects_out_of_hours():
    assert "outside working hours" in check_slot("s1 16:45")


def test_check_slot_handles_garbage_input():
    assert "Could not parse" in check_slot("nonsense")
    assert "Unknown task id" in check_slot("s999 10:00")


def test_scheduler_separates_invalid_from_merely_late():
    domain = MeetingSchedulerDomain()

    # s1 gold is 13:00. 09:00 conflicts; 14:00 is valid but not earliest.
    conflicting = domain.score(
        [RunTrace(task_id="s1", input={}, output="09:00")]
    )[1]
    assert conflicting == {"slot_conflicts_with_busy_block_no_check_called": 1}

    late = domain.score([RunTrace(task_id="s1", input={}, output="14:00")])[1]
    assert late == {"valid_slot_but_not_the_earliest": 1}


def test_scheduler_parses_the_final_time_mentioned():
    domain = MeetingSchedulerDomain()
    trace = RunTrace(task_id="s1", input={},
                     output="I checked 09:00 and 11:00, the answer is 13:00")
    assert domain.score([trace])[0]["accuracy"] == 1.0


# --------------------------------------------------------------------------
# measure_variance: per-round orchestration/reliability recording
# --------------------------------------------------------------------------

def _round_with_orch(orch: str, accuracy: float, reliability: float,
                      failures: dict | None = None) -> RoundResult:
    return RoundResult(
        agent_spec=_spec(orch), traces=[],
        metrics={"accuracy": accuracy, "reliability": reliability},
        failure_modes=failures or {},
    )


def test_round_detail_records_orchestration_accuracy_reliability_and_failures():
    history = [
        _round_with_orch("planner-executor", 0.333, 1.0, {"stuck_thing": 3}),
        _round_with_orch("react-loop", 0.75, 0.5, {}),
    ]
    detail = round_detail(history)
    assert detail == [
        {"round": 0, "orchestration": "planner-executor", "accuracy": 0.333,
         "reliability": 1.0, "failure_modes": {"stuck_thing": 3}},
        {"round": 1, "orchestration": "react-loop", "accuracy": 0.75,
         "reliability": 0.5, "failure_modes": {}},
    ]


def test_round_detail_is_empty_for_empty_history():
    assert round_detail([]) == []


def test_build_summary_keeps_existing_top_level_shape():
    """Nothing downstream should break: the pre-existing summary keys must
    still be present with their original meaning, accuracy-only "curves"
    included, alongside the new per-round "repeats" field."""
    curves = [[0.5, 0.75], [0.6, 0.6]]
    detail = [round_detail([_round_with_orch("single-shot", 0.5, 1.0)]),
              round_detail([_round_with_orch("react-loop", 0.6, 1.0)])]
    summary = build_summary("ticket_routing", repeats=2, rounds=2,
                             curves=curves, repeats_detail=detail)

    for key in ("n", "rounds", "curves", "start_mean", "best_mean",
                "gain_mean", "gain_sd", "gain_min", "gain_max",
                "zero_gain_runs", "measured_at"):
        assert key in summary, f"missing pre-existing key {key!r}"
    assert summary["curves"] == curves
    assert summary["n"] == 2
    assert summary["start_mean"] == 0.55
    assert summary["gain_min"] == 0.0
    assert summary["zero_gain_runs"] == 1


def test_build_summary_adds_per_round_orchestration_and_reliability():
    curves = [[0.333, 0.75]]
    detail = [round_detail([
        _round_with_orch("planner-executor", 0.333, 1.0, {"stuck": 2}),
        _round_with_orch("react-loop", 0.75, 1.0, {}),
    ])]
    summary = build_summary("meeting_scheduler", repeats=1, rounds=2,
                             curves=curves, repeats_detail=detail)

    assert summary["repeats"] == detail
    assert summary["repeats"][0][0]["orchestration"] == "planner-executor"
    assert summary["repeats"][0][1]["orchestration"] == "react-loop"
    assert summary["repeats"][0][0]["reliability"] == 1.0
