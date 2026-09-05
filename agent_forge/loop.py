"""The generate -> run -> analyse -> improve loop. Domain-agnostic.

Everything needed for the Track 1 scoring axes is recorded per round:
accuracy, reliability, cost and speed — plus the improver's own stated reason
for each change, which is what turns a chart into an argument.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from . import generator, improver
from .spec import Domain, RoundResult

RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"
PARALLEL_TASKS = 6


def run_loop(domain: Domain, n_rounds: int = 3, save: bool = True) -> list[RoundResult]:
    print(f"\n=== {domain.name} — generating initial architecture ===")
    spec = generator.generate(domain.goal, domain.tools)
    print(f"    v0: orchestration={spec.orchestration}, "
          f"{len(spec.memory_notes)} memory notes")

    history: list[RoundResult] = []
    summaries: list[str] = []
    log: list[dict] = []
    change_summary = "initial architecture"

    # Hill-climbing with rollback. A proposal that scores worse than the best
    # seen so far is discarded and the next proposal is made from the best spec
    # instead. Without this the loop wanders: an early run lost 11 points of
    # accuracy over three rounds because each change was made from the previous
    # (already degraded) spec.
    best_spec = spec
    best_score = float("-inf")
    regressed = False

    for round_idx in range(n_rounds):
        tasks = domain.tasks()
        t0 = time.time()

        # Tasks are independent, so run them concurrently — otherwise a
        # 19-task round at ~3s each dominates the whole loop's wall time.
        with ThreadPoolExecutor(max_workers=PARALLEL_TASKS) as pool:
            traces = list(pool.map(lambda t: domain.run(spec, t), tasks))

        metrics, failure_modes = domain.score(traces)
        metrics["round_wall_s"] = round(time.time() - t0, 2)

        result = RoundResult(
            agent_spec=spec, traces=traces, metrics=metrics, failure_modes=failure_modes
        )
        history.append(result)
        summaries.append(change_summary)

        score = metrics.get("accuracy", 0.0)
        kept = score >= best_score
        if kept:
            best_score, best_spec = score, spec
            regressed = False
        else:
            regressed = True

        print(f"\n--- round {round_idx} (spec v{spec.version}) ---")
        print(f"    change:  {change_summary}")
        print(f"    metrics: {metrics}")
        print(f"    failures: {failure_modes or 'none'}")
        if not kept:
            print(f"    REGRESSION ({score} < best {best_score}) — rolling back "
                  f"to v{best_spec.version}")

        log.append(
            {
                "round": round_idx,
                "spec_version": spec.version,
                "orchestration": spec.orchestration,
                "system_prompt": spec.system_prompt,
                "memory_notes": spec.memory_notes,
                "change_summary": change_summary,
                "metrics": metrics,
                "failure_modes": failure_modes,
                "kept": kept,
                "best_score_so_far": best_score,
            }
        )

        if round_idx < n_rounds - 1:
            # On a regression the improver edits the BEST spec, not the one that
            # just lost points — otherwise damage compounds round over round.
            basis = result
            if regressed:
                basis = replace(result, agent_spec=best_spec)

            try:
                spec, change_summary = improver.improve(
                    basis, history=history, summaries=summaries, regressed=regressed
                )
                print(f"    -> v{spec.version}: {change_summary}")
            except Exception as exc:
                print(f"    -> improver failed ({exc}); continuing from best spec")
                spec, change_summary = best_spec, f"improver failed: {exc}"

    if save:
        RUNS_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = RUNS_DIR / f"{domain.name}-{stamp}.json"
        path.write_text(json.dumps({"domain": domain.name, "rounds": log}, indent=2))
        print(f"\n    saved -> {path}")

    return history
