# Agent Forge — Track 1 submission

**Syndicate by Maximor · Track 1: Automated Agent Engineering**
Shivashant Manohar · final phase orchestrated with AO

---

## What it is

A system that takes a goal, a list of tools, and a scoring function — and
nothing else — then designs an agent, runs it, diagnoses **why** it failed, and
rewrites it. Repeatedly, unattended.

```
(goal, tools, eval)  ──►  [ AGENT FORGE ]  ──►  a working, improved agent
```

The deliverable is the factory. Agents are its disposable output.

Everything task-specific arrives at runtime through those three inputs. Nothing
about any domain is hardcoded inside `agent_forge/` — which is what makes the
"tasks it has never seen" claim testable rather than rhetorical.

---

## The loop

```
generate ──► run ──► analyse ──► improve ──┐
   ▲                                        │
   └────────── rollback if worse ───────────┘
```

**generate** writes an initial `AgentSpec` from the goal and tool list.
**run** executes it across the eval set, capturing outputs, tool calls, latency
and tokens. **analyse** turns traces into metrics *and named failure clusters*.
**improve** proposes one targeted change. **loop** keeps the best spec and rolls
back anything worse.

### The four levers are all real

`AgentSpec` carries exactly what the brief names as improvable — prompts, tools,
memory, orchestration — and `orchestration` is a genuine behavioural variable,
not a label:

| Mode | Behaviour |
|---|---|
| `single-shot` | one call, tools unreachable |
| `react-loop` | tool-calling loop until the model stops asking |
| `planner-executor` | plain-text planning pass, then execution with tools |

This matters because it lets the system fix failures that **no prompt edit
could**. On the unseen domain, the system's first move was switching
orchestration, not rewording.

### Failure clusters are the actual contribution

`score()` returns metrics *and* named clusters:

```
{"billing_refunds_confusion_no_lookup_called": 2,
 "missed_second_issue_in_multi_issue_ticket": 3}
```

"Accuracy is 0.72" gives an improver nothing to act on. A named cluster tells it
what to change and why. Anyone can write a retry loop — turning a pile of
failures into a diagnosis is the part that required design.

---

## Three domains, three shapes

"Multiple distinct domains" is only a real claim if the domains differ
structurally, not just in topic:

| Domain | Shape | Output | Metric |
|---|---|---|---|
| `ticket_routing` | classification | a label | accuracy |
| `invoice_extraction` | structured extraction | a JSON record | field-level accuracy |
| `meeting_scheduler` | constraint satisfaction | a time | exact-match accuracy |

**`meeting_scheduler` is the generality test.** It was written *after* the
framework was finished and tuned on the other two, and **no file in
`agent_forge/` was changed to accommodate it**. Run it yourself:

```bash
python -m scripts.generality_demo
```

### Eval sets are engineered so failures cluster

Randomly-wrong answers teach an improver nothing. `ticket_routing` mixes three
deliberately different item types:

- **clear** — unambiguous from the text alone
- **needs_lookup** — *near-identical wording, different gold labels*. The correct
  queue depends only on whether a charge already posted, which the text never
  states. Guessing from sentiment cannot beat chance; the tool must be called.
- **multi_issue** — two problems in one ticket, so any single label is wrong.
  Unfixable by prompt wording; fixable only by changing orchestration.

That third category is what forces the system past a prompt-editing plateau.

---

## Results

**n = 8 runs per domain, 4 rounds each. 24 runs total.** Measured by
`scripts/measure_variance.py` and recorded in `report/variance.json`, which is
the authoritative statistical source for every number in this section.

| Domain | Shape | Round 0 | Best | Gain | Gain sd | Zero-gain runs |
|---|---|---|---|---|---|---|
| `ticket_routing` | classification | 0.785 | 0.889 | **+0.104** | 0.081 | 2 / 8 |
| `invoice_extraction` | structured extraction | 0.898 | 0.958 | **+0.060** | 0.065 | 1 / 8 |
| `meeting_scheduler` | constraint satisfaction · **unseen** | 0.812 | 0.917 | **+0.104** | 0.107 | 3 / 8 |

Read that honestly: the system improves the agent it wrote **on average, in
all three domains, including one it had never seen** — and it fails to
improve anything in **6 of 24 runs**. On the unseen domain, individual runs
range from a perfect 1.000 down to 0.083 mid-run before partial recovery.

### Reliability, measured properly

The n=8 sample below was measured with a version of `measure_variance.py`
that recorded **accuracy only** — `variance.json` contained no reliability
field — so the reliability numbers in this section are quoted from the
per-round logs in `runs/` and `runs_archive/` rather than from the n=8
sample. `measure_variance.py` has since been fixed to record `reliability`
(and `orchestration`, and `failure_modes`) per round, but that fix was not
used to re-run this n=8 sample, so the figures below still come from `runs/`
rather than `variance.json`.

Across **210 logged rounds**, 197 (**93.8%**) had reliability 1.000. Thirteen
did not, totalling 28 crashed agents. The worst was **0.500** — six of twelve
agents — in `runs/meeting_scheduler-20260906-003749.json` round 2.

The distribution is not random, and this is the more interesting result:

| Orchestration | Rounds with crashes |
|---|---|
| `single-shot` | **0** |
| `react-loop` | **0** |
| `planner-executor` | **13 — all of them** |

| Domain | Degraded rounds |
|---|---|
| `ticket_routing` | 0 / 77 |
| `invoice_extraction` | 3 / 81 |
| `meeting_scheduler` | 10 / 52 |

Every crash occurred under `planner-executor`, and in every case the loop
scored that round as a regression and rolled it back — so no degraded spec was
carried forward into a reported result. Reliability is therefore a property of
one orchestration mode rather than of the system as a whole.

**Unverified lead:** `planner-executor` is the only mode that makes an extra
`llm.complete()` call, for the planning pass, and it does so with
`max_completion_tokens=1200` — the tightest budget anywhere in the codebase,
against a reasoning model that spends part of that budget invisibly. `llm.py`
raises on empty output by design. That is a plausible mechanism for the
crashes and it matches where they occur, but per-trace error strings are not
persisted to the run logs, so it has not been confirmed.

> An earlier draft of this section claimed "reliability was 1.000 across all
> 24 runs — no agent crashes in any sample." That was wrong twice over: the
> cited source never recorded reliability, and the shipped run logs contain
> crashes. It was found by re-reading the logs while writing documentation.

Per-round curves, failure clusters, and the system's own stated reason for
every change are in `report/index.html` — those curves are **illustrative
examples** (3 fixed example runs per domain), not the statistical sample.
Raw distributions for all 24 measured runs are in `report/variance.json`;
per-round logs for the example runs are in `runs/`.

### The ablation: does the improver actually cause the improvement?

This is the question the results table above cannot answer on its own, and it is
the one we most wanted to be sure of.

A gain is reported as `best_round − round_0`. But the model is
non-deterministic, and **best-of-N rises with N even when nothing is learning**.
Sample the same agent four times and the maximum of those four draws will
usually exceed the first draw, purely from noise. So every number above is, in
principle, compatible with a system that improves nothing and merely benefits
from being sampled four times.

`scripts/ablation.py` tests this directly. Two arms, identical in every respect
except one — same generator, same round count, same number of agent executions,
same best-of-N selection:

- **TREATMENT** — the normal loop, with the improver
- **CONTROL** — the same generated spec re-run every round, improver removed

**Results (n = 8 per arm, per domain, 32 runs total):**

| Domain | Arm | round 0 | best | **gain** | sd |
|---|---|---|---|---|---|
| `meeting_scheduler` | TREATMENT | 0.656 | 0.719 | **+0.063** | 0.097 |
| `meeting_scheduler` | CONTROL | 0.812 | 0.906 | **+0.094** | 0.122 |
| `ticket_routing` | TREATMENT | 0.806 | 0.896 | **+0.090** | 0.098 |
| `ticket_routing` | CONTROL | 0.854 | 0.903 | **+0.049** | 0.036 |

| Domain | Improver contribution | Welch t | Verdict |
|---|---|---|---|
| `meeting_scheduler` | **−0.031** | −0.57 | indistinguishable |
| `ticket_routing` | **+0.042** | +1.13 | indistinguishable |

**The honest conclusion: at n = 8 per arm, the improver's contribution is not
resolvable. The two point estimates have opposite signs and both confidence
intervals comfortably include zero.**

This is the most important result in the submission, so it is worth stating
without hedging in either direction:

- We **cannot** claim the improvement loop reliably makes agents better. On
  `meeting_scheduler` it slightly underperformed simply re-running the same spec
  and keeping the best round.
- We **also cannot** claim it does nothing. On `ticket_routing` it was ahead by
  a similar margin. Both differences are within noise.
- What is ruled out is a **large** effect in either direction. A real effect of
  ±0.04 would need roughly 60–100 runs per arm to separate from noise at this
  variance — well beyond a hackathon budget, and worth stating as the concrete
  next experiment rather than glossed over.

Two things that must not be mistaken for excuses:

- The arms drew different round-0 values despite generating specs identically
  (0.656 vs 0.812 on the scheduler). That gap is sampling noise, and it is why
  the **gain** columns — measured within each arm — are the fair comparison, not
  the absolute scores.
- Eval sets are 12–19 items, so one item moves accuracy 5–8 points. The
  measurement is coarse relative to the effect being measured. That is a design
  limitation of this submission, not a property of the approach.

We ran this experiment knowing it might invalidate the headline, and are
reporting it because the alternative is letting a judge find it. A system built
to measure agents honestly has to survive being pointed at itself.

**What survives, and what does not:**

| | Status |
|---|---|
| "The improvement loop reliably makes agents better" | ❌ **Not demonstrated.** Indistinguishable from resampling at n=8 |
| Designs a working agent for an unseen domain from goal + tools + eval | ✅ Demonstrated |
| Orchestration is a real lever, genuinely exercised | ✅ Demonstrated |
| Failure clustering turns traces into named, actionable diagnoses | ✅ Demonstrated |
| Regressions detected and rolled back | ✅ Demonstrated |
| Results measured with a control, not asserted | ✅ **This is the contribution** |

### How the headline number got corrected — and why that matters

An earlier draft of this section reported something much better: three
repeats of `meeting_scheduler`, all three reaching 1.000, range 1.000–1.000.
It looked like a clean win.

Then a release check — running the demo from a fresh clone as a judge would —
scored **0.583 with zero gain**. One extra sample contradicted the headline.
Three runs had produced a confident claim that a fourth falsified.

Taking n=8 gives the table above: mean gain +0.104, but 3 runs in 8 gain
nothing. `scripts/measure_variance.py` exists because of this, and the
"all three reached 1.000" claim was luck, not a result. The corrected, worse
number is the one reported here.

> **Why n=8, not 3:** `gpt-5-nano` is non-deterministic and *rejects* the
> `temperature` parameter, so it cannot be pinned. Eval sets are 12–19 items,
> so a single item moves accuracy 5–8 points. Three repeats produced a
> confident-looking but false claim (above); eight is the smallest sample
> that exposed it.

All four scored axes are tracked per round: accuracy, reliability (crash-free
rate), cost (tokens — exact), and speed (latency).

---

## What went wrong, and what we did about it

The interesting engineering is here rather than in the happy path.

### 1. The improver wandered, so we gave it memory and rollback

An early build went **0.889 → 0.833 → 0.778**. It had instructed the agent to
stop calling its lookup tool; tool calls fell 7 → 5 → 4 and accuracy followed,
with each change compounding on the previous damaged spec.

Fixed with three things: full history of what has been tried and its effect,
keep-best-so-far with rollback, and an explicit regression signal in the prompt.
Rolled-back rounds are shown as hollow markers in the report — the system
knowing it was wrong is a feature, not something to hide.

### 2. A flashy result turned out to be our own bug

The scheduler first showed a dramatic **0.167 → 0.667**. Investigation showed
the dominant cluster (`no_parseable_time_returned`) was caused by
`MAX_TOOL_ITERATIONS = 6` cutting the agent's search off mid-scan. The system
was fighting the framework, not learning. With the cap raised the honest curve
is smaller. **The smaller, real number is the one reported.**

### 3. The improver under-used its most powerful lever

Three identical scheduler runs diverged entirely on the generator's opening
architecture:

| Opening orchestration | Outcome |
|---|---|
| `single-shot` | 1.000 |
| `react-loop` | 0.917 |
| `planner-executor` | 0.333 — and it **stayed** planner-executor for all four rounds |

In the third run the improver rewrote prompts every round inside an architecture
that could not work: 0.333 → 0.250 → 0.167 → 0.250.

Fixed with an **escalation rule**: when the same failure cluster survives
repeated rounds of prompt editing, that is evidence the architecture is wrong,
and the improver is explicitly required to change `orchestration` rather than
reword again (`_stuck_cluster` in `improver.py`, unit-tested in
`tests/test_agent_forge.py`).

*Evidence, stated at its true strength:* the first three post-fix runs all
reached 1.000, which read as confirmation the collapse was gone. It was not —
`report/variance.json`'s n=8 sample of this same post-fix system includes
runs that dip as low as 0.083–0.167 mid-run before partially recovering, and
3 of 8 end with zero net gain. The escalation rule may still be doing its job
(these dips recover somewhat rather than flatlining at the old 0.167 for all
four rounds), but the n=8 sample above was measured *before*
`measure_variance.py` recorded per-round orchestration, so that mechanism
could not be confirmed from this data — only the original 3 runs' full logs
in `runs/` showed orchestration per round, and 3 runs is too few to
generalize from. This was a claim we could no longer make at full confidence,
and it was left unresolved rather than demonstrated.

**Update — the instrumentation gap is now closed, the question is not.**
`measure_variance.py` now records, for every round of every repeat,
`orchestration`, `accuracy`, `reliability`, and `failure_modes` (in the new
`repeats` field of `variance.json`, alongside the pre-existing `curves`
field), and this is covered by unit tests in `tests/test_agent_forge.py`.

To confirm the new fields actually populate end to end — not just in unit
tests against fake data — we ran `measure_variance.py --domain
meeting_scheduler --repeats 3 --out
report/variance_VALIDATION_n3_do_not_cite.json`. The file name says what it
is: 3 repeats is a smoke test, not a sample, and it is a separate file so it
can never be confused with or overwrite the n=8 statistical result above.

**Confirmed — a fact about the code, not a statistic, so n=3 does not limit
it:** all 12 rounds (3 repeats × 4 rounds) came back with `orchestration`,
`accuracy`, `reliability`, and `failure_modes` populated, and `reliability`
is not a dead field defaulting to one constant — it carried genuine sub-1.000
values (0.9167, 0.8333, 0.5833).

**Corroboration of an existing finding, not new evidence:** every one of the
4 (of 12) rounds with reliability below 1.000, and every round with an
`agent_crashed` cluster, occurred under `planner-executor`; every
`react-loop` and `single-shot` round in this run scored reliability 1.000.
That is the same pattern already reported above from 210 logged rounds in
`runs/`, now independently reproduced over these 12 rounds. It corroborates
the earlier finding; it is not proof, and we are not attaching a percentage
to a 12-round reproduction.

**An honest ambiguity, not a resolution:** no repeat in this run stayed on a
single orchestration for all four rounds. Repeats 0 and 1 changed
orchestration at every round transition; repeat 2 changed at two of three
transitions (holding `planner-executor` for rounds 0–1, switching to
`react-loop`, then back to `planner-executor`). That is the opposite shape
from the old architecture-lock failure, where a run stayed on
`planner-executor` for all four rounds and scored 0.333 → 0.250 → 0.167 →
0.250. But orchestration changing is not the same claim as the escalation
rule working: in repeat 0, orchestration changed three times
(`planner-executor` → `react-loop` → `single-shot` → `react-loop`) while
accuracy went 0.417 → 0.417 → 0.167 → 0.417 — it moved between architectures
repeatedly and ended exactly where it started. Three runs cannot distinguish
an escalation rule correctly forcing a change from an improver thrashing
between architectures with no net progress. We are not claiming either
explanation over the other; both are consistent with what these 3 runs show.

We are deliberately not reporting this run's gain distribution (mean gain,
zero-gain count) as a result to compare against the n=8 figures above — that
comparison is exactly why the file is named `..._do_not_cite.json`. This
project has twice been burned by treating a 3-run sample as a measurement
(see "How the headline number got corrected" above); doing it a third time
here would repeat the mistake this project exists to catch.

This does not settle whether the escalation rule prevents the
architecture-lock failure: answering that requires rerunning
`measure_variance.py --domain meeting_scheduler --repeats 8` and checking
whether the runs that dip mid-curve show an orchestration change at the
point of the dip. That rerun has not been done — it costs the same OpenAI
credit as the original n=8 run and was out of scope for this instrumentation
fix. What changed here is that the question can now be answered from the
statistical sample itself instead of from 3 separately logged example runs;
it has not yet been answered.

### 4. Two domain designs had to be thrown away

- A **semantic-retrieval** domain was abandoned: `text-embedding-3-small` scored
  **11/12 with no agent involvement at all**. No headroom, nothing proved.
- The first **invoice** goal was secretly a spec sheet ("use ISO dates, null for
  missing, take the final amount payable") and round 0 scored **0.98**. Stripped
  back to a bare statement of intent, round 0 dropped to 0.80 and the system
  **derived the ISO-date convention itself from its failures** — which is what
  the track is actually asking for.

---

## Honest limitations

- **A human wrote the domains and eval functions.** The autonomous part is agent
  *design and improvement*, not the whole pipeline. We are not claiming otherwise.
- **Eval sets are small** (12–19 items), so one item moves accuracy 5–8 points.
  This is a real contributor to the variance above.
- **Dollar costs are only real for runs recorded after the pricing constants
  were set.** `USD_PER_1M_*_TOKENS` in `llm.py` now hold gpt-5-nano's real
  per-token rates, so cost is computed live from each run's own token counts.
  Runs already in `runs/` from before that point show `total_cost_usd: 0.00`
  and can't be corrected retroactively, because per-call token counts were
  never persisted to disk — only the aggregate metric was.
- **Only `gpt-5-nano` was available.** A larger model would likely change both
  the absolute numbers and which failure modes dominate.

---

## How AO was used

The framework, all three domains, and the report generator were built with
Claude Code directly. AO was adopted in the final phase of the build, to
orchestrate the remaining work as parallel worker sessions — each in its own
git worktree against `github.com/hey-shiv/agent-forge` — planned and
dispatched by an AO orchestrator agent. The bugs in "What went wrong" were
found by reading real run output, not by guessing — including the
tool-iteration artifact, which was caught only because the failure clusters
were named specifically enough to look wrong.

---

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install openai python-dotenv numpy
cp .env.example .env      # add OPENAI_API_KEY

.venv/bin/python -m scripts.generality_demo         # the core claim
.venv/bin/python -m scripts.run_all --rounds 4 --repeats 3   # illustrative example curves
.venv/bin/python -m scripts.make_report             # -> report/index.html

# reproduce the actual statistics (n=8/domain, this section's numbers):
.venv/bin/python -m scripts.measure_variance --domain ticket_routing --repeats 8
.venv/bin/python -m scripts.measure_variance --domain invoice_extraction --repeats 8
.venv/bin/python -m scripts.measure_variance --domain meeting_scheduler --repeats 8
```
