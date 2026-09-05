"""Run Agent Forge across every registered domain.

    python -m scripts.run_all                      # 5 rounds, 1 repeat
    python -m scripts.run_all --rounds 4 --repeats 3

Why --repeats exists: gpt-5-nano is non-deterministic and its temperature
cannot be pinned to 0 (the model rejects the parameter). Two runs of the same
domain produced round-0 accuracies of 0.800 and 0.867, and best-of-run of 0.933
and 0.893. A single curve is therefore a sample, not a measurement. Reporting
the mean and the full range across repeats is the honest way to state what this
system achieves — and run-to-run spread is itself a reliability result.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_forge import llm  # noqa: E402
from agent_forge.loop import run_loop  # noqa: E402
from domains.invoice_extraction.domain import InvoiceExtractionDomain  # noqa: E402
from domains.meeting_scheduler.domain import MeetingSchedulerDomain  # noqa: E402
from domains.ticket_routing.domain import TicketRoutingDomain  # noqa: E402

DOMAINS = [TicketRoutingDomain, InvoiceExtractionDomain, MeetingSchedulerDomain]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()

    results: dict[str, list[dict]] = {}

    for domain_cls in DOMAINS:
        for repeat in range(args.repeats):
            domain = domain_cls()
            if args.repeats > 1:
                print(f"\n########## {domain.name} — repeat {repeat + 1}"
                      f"/{args.repeats} ##########")
            history = run_loop(domain, n_rounds=args.rounds)
            curve = [r.metrics["accuracy"] for r in history]
            results.setdefault(domain.name, []).append(
                {"curve": curve, "start": curve[0], "best": max(curve)}
            )

    print("\n" + "=" * 72)
    print("SUMMARY" + (f"  (mean of {args.repeats} repeats)" if args.repeats > 1 else ""))
    print("=" * 72)

    for name, runs in results.items():
        starts = [r["start"] for r in runs]
        bests = [r["best"] for r in runs]
        print(f"\n  {name}")
        for r in runs:
            print(f"      curve {[round(v, 3) for v in r['curve']]}")
        if len(runs) > 1:
            print(f"      round 0 : mean {statistics.mean(starts):.3f}  "
                  f"range {min(starts):.3f}-{max(starts):.3f}")
            print(f"      best    : mean {statistics.mean(bests):.3f}  "
                  f"range {min(bests):.3f}-{max(bests):.3f}")
            print(f"      gain    : mean "
                  f"{statistics.mean(bests) - statistics.mean(starts):+.3f}")
        else:
            print(f"      round 0 {starts[0]:.3f}  best {bests[0]:.3f}  "
                  f"gain {bests[0] - starts[0]:+.3f}")

    print(f"\n  forge overhead: {llm.session_usage.as_dict()}")


if __name__ == "__main__":
    main()
