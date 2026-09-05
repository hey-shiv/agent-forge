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

Reliability was 1.000 across all 24 runs — no agent crashes in any sample.

Per-round curves, failure clusters, and the system's own stated reason for
every change are in `report/index.html` — those curves are **illustrative
examples** (3 fixed example runs per domain), not the statistical sample.
Raw distributions for all 24 measured runs are in `report/variance.json`;
per-round logs for the example runs are in `runs/`.

### How this number got corrected — and why that matters

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
four rounds), but `measure_variance.py` does not record per-round
orchestration, so that mechanism can't be confirmed from this data — only
the original 3 runs' full logs in `runs/` show orchestration per round, and 3
runs is too few to generalize from. This is a claim we can no longer make at
full confidence; treat it as unresolved rather than demonstrated.

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
- **Cost is reported in tokens, not dollars.** `USD_PER_1M_*_TOKENS` are left at
  zero rather than guessing OpenAI's prices; fill them in and every figure
  populates. Token counts are exact.
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
