"""GENERALITY DEMO — the core Track 1 claim, tested directly.

Track 1 asks for a system that designs agents "for tasks it has never seen
before." That claim is only credible if the system can be pointed at a domain it
was never tuned on and still work, with no code changes anywhere in agent_forge/.

This script does exactly that. `meeting_scheduler` is a constraint-satisfaction
task written after the framework was finished and tuned on two unrelated
domains. Nothing in agent_forge/ knows it exists. The only things handed over
are the three inputs the brief names:

    a goal string, a list of tool descriptions, and a scoring function

Run it and watch the system design an agent from scratch, run it, name its own
failure modes, and rewrite itself to fix them.

    python -m scripts.generality_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_forge import llm  # noqa: E402
from agent_forge.loop import run_loop  # noqa: E402
from domains.meeting_scheduler.domain import MeetingSchedulerDomain  # noqa: E402

BAR = "=" * 72


def main() -> None:
    domain = MeetingSchedulerDomain()

    print(BAR)
    print("GENERALITY DEMO — a domain the system has never seen")
    print(BAR)
    print(f"\ndomain : {domain.name}")
    print(f"shape  : constraint satisfaction (vs classification / extraction)")
    print(f"tasks  : {len(domain.tasks())}")
    print("\nThe system receives ONLY these three things:\n")
    print("  1. GOAL")
    for line in domain.goal.split("\n"):
        print(f"       {line}")
    print("\n  2. TOOLS")
    for tool in domain.tools:
        print(f"       {tool.name}: {tool.description[:66]}...")
    print("\n  3. An eval function (domain.score)")
    print("\nNo prompt, no architecture, no orchestration choice is supplied.")
    print("Everything below is the system's own work.\n")
    print(BAR)

    history = run_loop(domain, n_rounds=5)

    curve = [r.metrics["accuracy"] for r in history]
    best_idx = max(range(len(curve)), key=lambda i: curve[i])
    best = history[best_idx]

    print("\n" + BAR)
    print("RESULT")
    print(BAR)
    print(f"\n  accuracy by round : {curve}")
    print(f"  round 0           : {curve[0]:.3f}")
    print(f"  best (round {best_idx})     : {curve[best_idx]:.3f}")
    print(f"  gain              : {curve[best_idx] - curve[0]:+.3f}")
    print(f"  rolled back       : "
          f"{sum(1 for i, r in enumerate(history) if curve[i] < max(curve[:i+1]))}")
    print(f"\n  architecture the system chose : {best.agent_spec.orchestration}")
    print(f"  spec version at best          : v{best.agent_spec.version}")
    print(f"\n  forge overhead : {llm.session_usage.as_dict()}")
    print("\n  The agent that produced the best score, written entirely by the")
    print("  system, from the goal above:\n")
    for line in best.agent_spec.system_prompt.split("\n"):
        print(f"    | {line}")
    print()


if __name__ == "__main__":
    main()
