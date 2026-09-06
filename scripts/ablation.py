"""ABLATION — does the improver actually cause the improvement?

The problem this answers
------------------------
Agent Forge reports a gain as `best_round - round_0`. But the model is
non-deterministic and round 0 alone varies by up to 0.33 on the same domain.
Best-of-N rises with N even when nothing is learning: sample the same agent four
times and the maximum of those four draws will usually exceed the first draw,
purely from noise.

So "gain +0.104" does not, on its own, establish that the improver did anything.
Every number in the results table is compatible with a system that improves
nothing and simply benefits from being sampled four times.

The design
----------
Two conditions, identical in every respect except one:

  TREATMENT   generate v0, then N rounds WITH the improver (normal behaviour)
  CONTROL     generate v0, then N rounds re-running THE SAME SPEC, no improver

Both report `best_round - round_0`. Both pay exactly the same number of agent
runs, and both take a best-of-N. The only difference is whether the spec is
rewritten between rounds.

CONTROL therefore measures the gain attributable to noise plus best-of-N
selection. TREATMENT measures noise + selection + improvement. The difference
between them is the improver's real contribution.

If TREATMENT does not beat CONTROL, the honest conclusion is that the loop is
an expensive random search, and we would rather find that ourselves than have a
judge find it.

    python -m scripts.ablation --domain meeting_scheduler --repeats 8
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_forge import generator  # noqa: E402
from agent_forge.loop import PARALLEL_TASKS, run_loop  # noqa: E402
from domains.invoice_extraction.domain import InvoiceExtractionDomain  # noqa: E402
from domains.meeting_scheduler.domain import MeetingSchedulerDomain  # noqa: E402
from domains.ticket_routing.domain import TicketRoutingDomain  # noqa: E402

REGISTRY = {
    "ticket_routing": TicketRoutingDomain,
    "invoice_extraction": InvoiceExtractionDomain,
    "meeting_scheduler": MeetingSchedulerDomain,
}

OUT = Path(__file__).resolve().parent.parent / "report" / "ablation.json"


def run_control(domain, n_rounds: int) -> list[float]:
    """CONTROL arm: generate one spec, then re-run it unchanged for n_rounds.

    Deliberately mirrors run_loop's structure — same generator, same task
    concurrency, same number of agent executions — minus the improve step.
    """
    spec = generator.generate(domain.goal, domain.tools)
    curve = []
    for _ in range(n_rounds):
        with ThreadPoolExecutor(max_workers=PARALLEL_TASKS) as pool:
            traces = list(pool.map(lambda t: domain.run(spec, t), domain.tasks()))
        metrics, _failures = domain.score(traces)
        curve.append(metrics["accuracy"])
    return curve


def summarise(curves: list[list[float]]) -> dict:
    starts = [c[0] for c in curves]
    bests = [max(c) for c in curves]
    gains = [max(c) - c[0] for c in curves]
    return {
        "curves": curves,
        "start_mean": statistics.mean(starts),
        "best_mean": statistics.mean(bests),
        "gain_mean": statistics.mean(gains),
        "gain_sd": statistics.stdev(gains) if len(gains) > 1 else 0.0,
        "gain_min": min(gains),
        "gain_max": max(gains),
        "zero_gain_runs": sum(1 for g in gains if g <= 0),
        "n": len(curves),
    }


def welch_t(a: list[float], b: list[float]) -> tuple[float, str]:
    """Welch's t statistic for two independent samples of unequal variance.

    Reported with an explicitly coarse verdict rather than a p-value: at n=8 per
    arm this is a directional signal, not a significance test, and dressing it up
    as one would be exactly the overclaiming this project is trying to avoid.
    """
    if len(a) < 2 or len(b) < 2:
        return 0.0, "insufficient samples"
    ma, mb = statistics.mean(a), statistics.mean(b)
    va, vb = statistics.variance(a), statistics.variance(b)
    se = (va / len(a) + vb / len(b)) ** 0.5
    if se == 0:
        return 0.0, "no variance in either arm"
    t = (ma - mb) / se
    if abs(t) >= 2.5:
        verdict = "clear separation"
    elif abs(t) >= 1.5:
        verdict = "suggestive, not conclusive"
    else:
        verdict = "indistinguishable at this sample size"
    return t, verdict


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True, choices=sorted(REGISTRY))
    ap.add_argument("--repeats", type=int, default=8)
    ap.add_argument("--rounds", type=int, default=4)
    args = ap.parse_args()

    treat_curves, ctrl_curves = [], []

    for i in range(args.repeats):
        print(f"\n===== {args.domain}  sample {i+1}/{args.repeats}  [TREATMENT] =====")
        history = run_loop(REGISTRY[args.domain](), n_rounds=args.rounds, save=False)
        treat_curves.append([r.metrics["accuracy"] for r in history])

        print(f"\n===== {args.domain}  sample {i+1}/{args.repeats}  [CONTROL] =====")
        curve = run_control(REGISTRY[args.domain](), args.rounds)
        ctrl_curves.append(curve)
        print(f"    control curve (spec unchanged): {[round(v,3) for v in curve]}")

    treat = summarise(treat_curves)
    ctrl = summarise(ctrl_curves)
    t, verdict = welch_t(
        [max(c) - c[0] for c in treat_curves],
        [max(c) - c[0] for c in ctrl_curves],
    )

    print("\n" + "=" * 74)
    print(f"ABLATION — {args.domain}   (n={args.repeats} per arm, {args.rounds} rounds)")
    print("=" * 74)
    print(f"\n  {'':12} {'round 0':>9} {'best':>9} {'gain':>9} {'sd':>7} {'zero-gain':>11}")
    for label, s in (("TREATMENT", treat), ("CONTROL", ctrl)):
        print(f"  {label:12} {s['start_mean']:9.3f} {s['best_mean']:9.3f} "
              f"{s['gain_mean']:+9.3f} {s['gain_sd']:7.3f} "
              f"{s['zero_gain_runs']:>7}/{s['n']}")

    delta = treat["gain_mean"] - ctrl["gain_mean"]
    print(f"\n  improver's contribution : {delta:+.3f}")
    print(f"  Welch t                 : {t:+.2f}  ({verdict})")
    print("\n  CONTROL is the same spec re-run and best-of-N selected — it is the")
    print("  gain obtainable with no learning at all. Anything TREATMENT scores")
    print("  above it is what the improver actually contributed.")

    payload = json.loads(OUT.read_text()) if OUT.exists() else {}
    payload[args.domain] = {
        "rounds": args.rounds,
        "treatment": treat,
        "control": ctrl,
        "improver_contribution": delta,
        "welch_t": t,
        "verdict": verdict,
        "measured_at": datetime.now().isoformat(timespec="seconds"),
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"\n  saved -> {OUT}")


if __name__ == "__main__":
    main()
