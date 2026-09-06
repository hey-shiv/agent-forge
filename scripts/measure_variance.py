"""Measure the true run-to-run distribution for one domain.

Written because three repeats was not enough. Three consecutive runs of
`meeting_scheduler` each reached 1.000, which looked like a clean result — and
then a fourth run, executed as a release check in a fresh clone, scored 0.583
with zero gain and three rollbacks. Three samples had produced a confident
claim that a fourth sample contradicted.

So: take a real sample, report the distribution rather than the best-looking
draw, and let the spread be part of the finding.

    python -m scripts.measure_variance --domain meeting_scheduler --repeats 8

Per-round orchestration, reliability, and failure clusters are also recorded
(in the "repeats" field, alongside the accuracy-only "curves" field kept for
backward compatibility). This exists to answer a question that was previously
unresolved: whether the improver's escalation rule (`_stuck_cluster` in
improver.py, which forces an orchestration change once a failure cluster
survives repeated prompt edits) is actually firing when a run dips, or
whether those dips are ordinary bad proposals that keep-best-so-far then
absorbed. Without per-round orchestration on the statistical (n=8) sample,
that question could only be answered by re-reading a handful of separately
logged example runs — not the sample the headline numbers come from.
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


def round_detail(history: list) -> list[dict]:
    """Per-round orchestration/accuracy/reliability/failure_modes for one repeat.

    Pulled out of main() so it can be unit-tested against fake RoundResults
    without calling the OpenAI API.
    """
    return [
        {
            "round": round_idx,
            "orchestration": r.agent_spec.orchestration,
            "accuracy": r.metrics.get("accuracy", 0.0),
            "reliability": r.metrics.get("reliability"),
            "failure_modes": r.failure_modes,
        }
        for round_idx, r in enumerate(history)
    ]


def build_summary(domain: str, repeats: int, rounds: int,
                   curves: list[list[float]], repeats_detail: list[list[dict]]) -> dict:
    """The dict stored at payload[domain] in variance.json.

    Kept separate from main() so the summary shape — including the
    backward-compatible accuracy-only "curves" field alongside the new
    per-round "repeats" field — can be unit-tested directly.
    """
    starts = [c[0] for c in curves]
    bests = [max(c) for c in curves]
    gains = [max(c) - c[0] for c in curves]
    zero_gain = sum(1 for g in gains if g <= 0)
    return {
        "n": repeats,
        "rounds": rounds,
        "curves": curves,
        "start_mean": statistics.mean(starts),
        "best_mean": statistics.mean(bests),
        "gain_mean": statistics.mean(gains),
        "gain_sd": statistics.stdev(gains) if len(gains) > 1 else 0.0,
        "gain_min": min(gains),
        "gain_max": max(gains),
        "zero_gain_runs": zero_gain,
        "measured_at": datetime.now().isoformat(timespec="seconds"),
        # Per-round orchestration/accuracy/reliability/failure_modes for every
        # repeat, so the escalation-rule question can be checked directly
        # against the statistical sample instead of a handful of example runs.
        "repeats": repeats_detail,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True, choices=sorted(REGISTRY))
    ap.add_argument("--repeats", type=int, default=8)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--out", type=Path, default=OUT,
                     help="Where to write the JSON (default: report/variance.json). "
                          "Use a different path for validation runs so the "
                          "statistical n=8 file is never overwritten.")
    args = ap.parse_args()

    curves: list[list[float]] = []
    repeats_detail: list[list[dict]] = []
    for i in range(args.repeats):
        print(f"\n########## {args.domain} — sample {i + 1}/{args.repeats} ##########")
        history = run_loop(REGISTRY[args.domain](), n_rounds=args.rounds, save=False)
        curves.append([r.metrics["accuracy"] for r in history])
        repeats_detail.append(round_detail(history))

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

    out = args.out
    out.parent.mkdir(exist_ok=True, parents=True)
    payload = json.loads(out.read_text()) if out.exists() else {}
    payload[args.domain] = build_summary(
        args.domain, args.repeats, args.rounds, curves, repeats_detail
    )
    out.write_text(json.dumps(payload, indent=2))
    print(f"\n  saved -> {out}")


if __name__ == "__main__":
    main()
