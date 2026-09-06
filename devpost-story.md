## Inspiration

Track 1 asks for a system that designs agents for tasks it has never seen. That framing has a consequence people skip past: **the deliverable isn't an agent, it's the factory that makes them.** Any agent it produces is disposable output.

The part I actually wanted to solve was narrower. When an agent scores 0.72, "0.72" tells you nothing you can act on. A human engineer doesn't fix an agent by staring at a number — they read the failures, notice that eleven of them share a property, and change the one thing that property implicates. I wanted to know whether that step, the diagnosis, could be mechanised. Not the retry loop. The *reading of the failures*.

## What it does

Agent Forge takes three inputs and nothing else:

- a **goal** in plain language
- a list of **tools**
- a **scoring function**

From those it writes an agent, runs it across an eval set, clusters the failures into *named* modes, proposes one targeted change, and runs again — keeping the best version and rolling back anything that makes things worse.

Nothing task-specific lives inside `agent_forge/`. Everything about a domain arrives at runtime through those three inputs, which is what makes the "tasks it has never seen" claim testable rather than rhetorical.

The four levers named in the brief are all real. `AgentSpec` carries prompts, tools, memory, and orchestration — and orchestration is a genuine behavioural variable, not a label:

| Mode | Behaviour |
|---|---|
| `single-shot` | one call, tools unreachable |
| `react-loop` | tool-calling loop until the model stops asking |
| `planner-executor` | plain-text planning pass, then execution with tools |

That matters because it lets the system fix failures **no prompt edit could reach**. On the unseen domain, its first move was switching orchestration, not rewording.

## How I built it

Three domains, chosen so they differ *structurally* rather than by topic — "multiple domains" is only a real claim if the shapes differ:

| Domain | Shape | Output | Metric |
|---|---|---|---|
| `ticket_routing` | classification | a label | accuracy |
| `invoice_extraction` | structured extraction | a JSON record | field-level accuracy |
| `meeting_scheduler` | constraint satisfaction | a time | exact-match accuracy |

`meeting_scheduler` is the generality test. I wrote it *after* the framework was finished and tuned on the other two, and **no file in `agent_forge/` was changed to accommodate it.**

The eval sets are engineered so failures cluster rather than scatter — randomly-wrong answers teach an improver nothing. `ticket_routing` mixes three item types on purpose: items solvable from text alone; items with *near-identical wording but different gold labels*, where the answer depends on a fact only a tool call reveals; and multi-issue items where any single label is wrong. That last category cannot be fixed by prompt wording at all, which is what forces the system past a prompt-editing plateau and into changing its own architecture.

Model is `gpt-5-nano` throughout. Tracing is instrumented via Neatlogs behind an opt-in env var. AO was adopted for the final phase of the build to orchestrate remaining work as parallel worker sessions, each in its own git worktree with its own PR.

## Challenges I ran into

**The improver wandered.** An early build went 0.889 → 0.833 → 0.778. It had instructed the agent to *stop calling its lookup tool*; tool calls fell 7 → 5 → 4 and accuracy followed, each change compounding on the previous damaged spec. Fixed with three things: full history of what has been tried and its effect, keep-best-so-far with rollback, and an explicit regression signal.

**A flashy result turned out to be my own bug.** The scheduler first showed a dramatic 0.167 → 0.667 climb. Investigation showed the dominant failure cluster was caused by a `MAX_TOOL_ITERATIONS` cap cutting the agent's search off mid-scan. The system was fighting my framework, not learning. With the cap raised, the honest curve is much smaller. **The smaller, real number is the one I report.**

**The improver under-used its most powerful lever — and I can't prove I fixed it.** Three identical scheduler runs diverged entirely on the generator's opening architecture: `single-shot` reached 1.000, `react-loop` 0.917, and `planner-executor` scored 0.333 and *stayed* planner-executor for all four rounds, rewriting prompts inside an architecture that could not work. So I added an escalation rule — when the same failure cluster survives repeated prompt edits, that is evidence the architecture is wrong, and the improver is explicitly required to change orchestration rather than reword again.

I originally wrote that no comparable collapse occurred afterwards, based on three post-fix runs that all reached 1.000. **Widening to eight runs falsified that.** Two of the eight still dip to 0.083 and 0.167 mid-run, and two end below where they started. The escalation rule did not eliminate the failure it was built for.

I've left this open rather than claiming a fix I can't demonstrate. The measurement script didn't record per-round orchestration, so I genuinely couldn't tell from that data whether those dips were the same architecture-lock failure or ordinary bad proposals that the keep-best-so-far tracking then absorbed.

**Update:** `measure_variance.py` now records orchestration, accuracy, reliability, and failure clusters for every round of every repeat, so the blocker to answering this is gone.

I ran a 3-repeat smoke test against `meeting_scheduler` (`report/variance_VALIDATION_n3_do_not_cite.json`, named so it's never mistaken for a sample) purely to confirm the fields populate end to end. They do, for all 12 rounds, and `reliability` is not a dead field — it carried real sub-1.000 values (0.9167, 0.8333, 0.5833). All four of those degraded rounds, and every `agent_crashed` cluster, occurred under `planner-executor`, while every `react-loop` and `single-shot` round scored 1.000 — the same pattern I'd already reported from 210 logged rounds in `runs/`, now reproduced independently over these 12. That's corroboration, not new proof, and I'm not putting a percentage on 12 rounds.

More interesting: no repeat in this smoke test stayed on one orchestration for all four rounds, which is the opposite shape from the old architecture-lock failure. But I want to be careful here, because this is exactly the kind of thing I've overclaimed before: orchestration *changing* is not the same as the escalation rule *working*. In one repeat, orchestration changed three times — `planner-executor` → `react-loop` → `single-shot` → `react-loop` — while accuracy went 0.417 → 0.417 → 0.167 → 0.417, ending exactly where it started. Three runs can't tell me whether that's the escalation rule doing its job or the improver thrashing between architectures with no net progress. I'm not claiming either one.

The actual question — does the escalation rule fire at the dips in the n=8 sample, or are those dips something else — still needs a fresh `--repeats 8` run against the instrumented script, which hasn't happened yet.

**Two domain designs had to be thrown away.** A semantic-retrieval domain scored 11/12 with no agent involvement at all — no headroom, nothing proved. And my first invoice goal was secretly a spec sheet ("use ISO dates, null for missing…") which scored 0.98 at round zero. Stripped back to a bare statement of intent, round zero fell to 0.80 and the system **derived the ISO-date convention itself from its failures** — which is what the track is actually asking for.

## Accomplishments that I'm proud of

Honestly? Reporting a worse number than I had.

I first measured three runs per domain and the unseen domain hit a perfect 1.000 in all three. Then I did a release check from a clean clone and it scored 0.58 with zero improvement. One extra sample destroyed my headline. So I took eight runs per domain instead.

Here is what is actually true, over **24 runs**:

| Domain | Round 0 (mean) | Best (mean) | Mean gain | Range |
|---|---|---|---|---|
| `meeting_scheduler` — **unseen** | 0.812 | 0.917 | **+0.104** | +0.000 … +0.250 |
| `ticket_routing` | 0.785 | 0.889 | **+0.104** | +0.000 … +0.222 |
| `invoice_extraction` | 0.898 | 0.958 | **+0.060** | +0.000 … +0.200 |

And the number I could most easily have hidden: **6 of 24 runs improve nothing at all.**

That is a worse result than my first draft. It is also the true one. A system whose entire job is measuring agents honestly has no business reporting its own performance from a lucky sample.

## What I learned

That the diagnosis really is the hard part, and it's separable from everything else. Once failures carry *names* — `billing_refunds_confusion_no_lookup_called` rather than "wrong" — a small model can reason about what to change surprisingly well. Most of my engineering effort went into making failures legible, not into the improvement logic that consumes them.

I also learned how easily a single run flatters you. `gpt-5-nano` rejects the `temperature` parameter outright, so it cannot be pinned to zero, and repeated runs of the same domain spanned round-zero accuracies from 0.722 to 1.000. A single curve is a sample, not a measurement.

## What's next

Honest limitations first, because they define the next steps. A human wrote the domains and eval functions — the autonomous part is agent *design and improvement*, not the whole pipeline. Eval sets are small (12–19 items), so one item moves accuracy several points, which is a real contributor to the variance above. And only `gpt-5-nano` was available; a stronger model would likely change both the numbers and which failure modes dominate.

So, in order: re-run `measure_variance.py --repeats 8` on `meeting_scheduler` now that it records per-round orchestration, so the escalation-rule question above can actually be settled instead of left open — the instrumentation is done, the n=8 measurement is not. Then larger eval sets to shrink the noise floor, and letting the system propose *new tools* rather than only rewiring the ones it's given.
