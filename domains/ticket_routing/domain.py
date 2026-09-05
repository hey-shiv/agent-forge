"""Domain 1 — route support tickets to the right team.

The eval set is deliberately built with three kinds of item so that failures
cluster into *nameable* modes rather than looking like uniform noise:

  clear         unambiguous from the text alone
  needs_lookup  billing vs refunds turns on whether a charge already posted,
                which is only knowable by calling lookup_customer. These items
                share near-identical wording with DIFFERENT gold labels, so
                guessing from sentiment cannot beat chance.
  multi_issue   the ticket raises two separate problems, so any single label
                is wrong — unfixable by prompt wording, fixable only by
                changing orchestration

That structure is the point. An improver that can only edit prompts will
plateau once `needs_lookup` is solved; getting past that requires it to notice
the third cluster and restructure the agent.
"""

from __future__ import annotations

import re

from agent_forge.runtime import run_agent
from agent_forge.spec import AgentSpec, RunTrace, ToolSpec

QUEUES = ["billing", "technical", "account", "refunds"]

GOAL = (
    "Route each incoming customer support ticket to a team: billing, technical, "
    "account, or refunds. Reply with only the team name(s). If a ticket raises "
    "more than one distinct issue, reply with the team names separated by a comma.\n\n"
    "Company policy for payment-related tickets: if a charge has ALREADY POSTED "
    "to the customer, it goes to refunds. If no charge has posted yet, it goes to "
    "billing. Ticket text alone does not reveal whether a charge posted."
)

TOOLS = [
    ToolSpec(
        "lookup_customer",
        "Given a customer email address, return their recent charge status. "
        "Use this when it matters whether a payment has already been taken.",
    ),
]

# email -> charge status, consulted by the lookup_customer tool
_CUSTOMER_DB = {
    "ana@example.com": "charge of $49.00 POSTED on 2026-08-28",
    "raj@example.com": "no charge posted; subscription renews 2026-09-14",
    "mei@example.com": "charge of $12.00 POSTED on 2026-09-01",
    "tom@example.com": "no charge posted; card authorisation pending",
    "sara@example.com": "charge of $99.00 POSTED on 2026-08-30",
    "luc@example.com": "no charge posted; trial ends 2026-09-20",
}


def lookup_customer(email: str) -> str:
    email = (email or "").strip().lower()
    for known, status in _CUSTOMER_DB.items():
        if known in email:
            return f"{known}: {status}"
    return "no customer found for that address"


TASKS: list[dict] = [
    # --- clear ---
    {"id": "c1", "kind": "clear", "text": "The app crashes every time I open the reports tab on Android.", "gold": ["technical"]},
    {"id": "c2", "kind": "clear", "text": "I can't log in, it says my password is wrong but I just reset it.", "gold": ["account"]},
    {"id": "c3", "kind": "clear", "text": "Please change the email address on my profile to a new one.", "gold": ["account"]},
    {"id": "c4", "kind": "clear", "text": "Charts render blank in Safari but work fine in Chrome.", "gold": ["technical"]},
    {"id": "c5", "kind": "clear", "text": "Can you send me a copy of my invoice for August?", "gold": ["billing"]},
    {"id": "c6", "kind": "clear", "text": "My two-factor authentication codes are never accepted.", "gold": ["account"]},
    {"id": "c7", "kind": "clear", "text": "Exports time out after about thirty seconds on large datasets.", "gold": ["technical"]},
    {"id": "c8", "kind": "clear", "text": "I want to upgrade from the Starter plan to the Pro plan.", "gold": ["billing"]},

    # --- needs_lookup ---
    # Near-identical wording ON PURPOSE. The correct queue depends only on
    # whether a charge has already posted, which the text never says.
    {"id": "n1", "kind": "needs_lookup", "text": "I don't want to pay for this month. ana@example.com", "gold": ["refunds"]},
    {"id": "n2", "kind": "needs_lookup", "text": "I don't want to pay for this month. raj@example.com", "gold": ["billing"]},
    {"id": "n3", "kind": "needs_lookup", "text": "Please sort out this payment for me. mei@example.com", "gold": ["refunds"]},
    {"id": "n4", "kind": "needs_lookup", "text": "Please sort out this payment for me. tom@example.com", "gold": ["billing"]},
    {"id": "n5", "kind": "needs_lookup", "text": "I need this subscription payment dealt with. sara@example.com", "gold": ["refunds"]},
    {"id": "n6", "kind": "needs_lookup", "text": "I need this subscription payment dealt with. luc@example.com", "gold": ["billing"]},

    # --- multi_issue: two genuine problems in one ticket ---
    {"id": "m1", "kind": "multi_issue", "text": "The dashboard won't load, and separately I need to update the card on file.", "gold": ["technical", "billing"]},
    {"id": "m2", "kind": "multi_issue", "text": "I can't sign in, and I also want a refund for last month's charge (mei@example.com).", "gold": ["account", "refunds"]},
    {"id": "m3", "kind": "multi_issue", "text": "Exports are failing. Also please change my account email address.", "gold": ["technical", "account"]},
    {"id": "m4", "kind": "multi_issue", "text": "Send me August's invoice, and the mobile app keeps logging me out.", "gold": ["billing", "technical"]},
]


class TicketRoutingDomain:
    name = "ticket_routing"
    goal = GOAL
    tools = TOOLS

    def tasks(self) -> list[dict]:
        return TASKS

    def run(self, agent_spec: AgentSpec, task: dict) -> RunTrace:
        trace = run_agent(
            agent_spec,
            task_id=task["id"],
            task_input=task["text"],
            tool_impls={"lookup_customer": lookup_customer},
            response_format_hint=(
                "Reply with ONLY team names from this list: "
                "billing, technical, account, refunds. "
                "Separate multiple teams with a comma. No explanation."
            ),
        )
        trace.input = task
        return trace

    @staticmethod
    def _parse(output: str) -> list[str]:
        return [q for q in QUEUES if re.search(rf"\b{q}\b", (output or "").lower())]

    def score(self, traces: list[RunTrace]) -> tuple[dict[str, float], dict[str, int]]:
        by_id = {t["id"]: t for t in TASKS}
        correct = 0
        errors = 0
        failure_modes: dict[str, int] = {}

        for tr in traces:
            task = by_id[tr.task_id]
            gold = set(task["gold"])
            got = set(self._parse(tr.output))

            if tr.error:
                errors += 1
                failure_modes["agent_crashed"] = failure_modes.get("agent_crashed", 0) + 1
                continue

            if got == gold:
                correct += 1
                continue

            # Name the failure so the improver has something actionable.
            if not got:
                mode = "no_valid_label_returned"
            elif task["kind"] == "multi_issue" and len(got) < len(gold):
                mode = "missed_second_issue_in_multi_issue_ticket"
            elif task["kind"] == "needs_lookup":
                used_lookup = any(c["tool"] == "lookup_customer" for c in tr.tool_calls)
                mode = (
                    "billing_refunds_confusion_despite_lookup"
                    if used_lookup
                    else "billing_refunds_confusion_no_lookup_called"
                )
            else:
                mode = f"wrong_label_on_{task['kind']}_ticket"

            failure_modes[mode] = failure_modes.get(mode, 0) + 1

        n = len(traces) or 1
        metrics = {
            "accuracy": round(correct / n, 4),
            "reliability": round((n - errors) / n, 4),
            "avg_latency_s": round(sum(t.latency_s for t in traces) / n, 3),
            "total_cost_usd": round(sum(t.cost_usd for t in traces), 6),
            "tool_calls": sum(len(t.tool_calls) for t in traces),
        }
        return metrics, failure_modes
