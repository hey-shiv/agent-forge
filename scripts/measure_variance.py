"""Measure the true run-to-run distribution for one domain.

Written because three repeats was not enough. Three consecutive runs of
`meeting_scheduler` each reached 1.000, which looked like a clean result — and
then a fourth run, executed as a release check in a fresh clone, scored 0.583
with zero gain and three rollbacks. Three samples had produced a confident
claim that a fourth sample contradicted.

So: take a real sample, report the distribution rather than the best-looking
draw, and let the spread be part of the finding.

    python -m scripts.measure_variance --domain meeting_scheduler --repeats 8
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_forge.loop import run_loop  # noqa: E402
from domains.invoice_extraction.domain import InvoiceExtractionDomain  # noqa: E402
from domains.meeting_scheduler.domain import MeetingSchedulerDomain  # noqa: E402
from domains.ticket_routing.domain import TicketRoutingDomain  # noqa: E402

REGISTRY = {
    "ticket_routing": TicketRoutingDomain,
    "invoice_extraction": InvoiceExtractionDomain,
    "meeting_scheduler": MeetingSchedulerDomain,
}

OUT = Path(__file__).resolve().parent.parent / "report" / "variance.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True, choices=sorted(REGISTRY))
    ap.add_argument("--repeats", type=int, default=8)
    ap.add_argument("--rounds", type=int, default=4)
    args = ap.parse_args()

    curves: list[list[float]] = []
    for i in range(args.repeats):
        print(f"\n########## {args.domain} — sample {i + 1}/{args.repeats} ##########")
        history = run_loop(REGISTRY[args.domain](), n_rounds=args.rounds, save=False)
        curves.append([r.metrics["accuracy"] for r in history])

    starts = [c[0] for c in curves]
    bests = [max(c) for c in curves]
    gains = [max(c) - c[0] for c in curves]
    zero_gain = sum(1 for g in gains if g <= 0)

    def block(label: str, xs: list[float]) -> str:
        sd = statistics.stdev(xs) if len(xs) > 1 else 0.0
        return (f"  {label:9} mean {statistics.mean(xs):.3f}  "
                f"median {statistics.median(xs):.3f}  sd {sd:.3f}  "
                f"min {min(xs):.3f}  max {max(xs):.3f}")

    print("\n" + "=" * 72)
    print(f"DISTRIBUTION — {args.domain}, n={args.repeats}")
    print("=" * 72)
    for c in curves:
        print(f"  {[round(v, 3) for v in c]}")
    print()
    print(block("round 0", starts))
    print(block("best", bests))
    print(block("gain", gains))
    print(f"\n  runs with zero or negative gain: {zero_gain}/{args.repeats}")

    OUT.parent.mkdir(exist_ok=True)
    payload = json.loads(OUT.read_text()) if OUT.exists() else {}
    payload[args.domain] = {
        "n": args.repeats,
        "rounds": args.rounds,
        "curves": curves,
        "start_mean": statistics.mean(starts),
        "best_mean": statistics.mean(bests),
        "gain_mean": statistics.mean(gains),
        "gain_sd": statistics.stdev(gains) if len(gains) > 1 else 0.0,
        "gain_min": min(gains),
        "gain_max": max(gains),
        "zero_gain_runs": zero_gain,
        "measured_at": datetime.now().isoformat(timespec="seconds"),
    }
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"\n  saved -> {OUT}")


if __name__ == "__main__":
    main()
