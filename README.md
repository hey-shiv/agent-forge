# Agent Forge

**Syndicate by Maximor — Track 1: Automated Agent Engineering**

A system that designs a specialised agent from nothing but a goal, a tool list
and a scoring function; runs it; clusters its failures into named modes; and
rewrites the agent to attack the largest cluster. Then repeats.

The deliverable is the **factory**, not the agent. Agents are its disposable
output, regenerated per task.

```
(goal, tools, eval)  ──►  [ AGENT FORGE ]  ──►  a working, improved agent
```

---

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install openai python-dotenv numpy
cp .env.example .env          # then paste your OPENAI_API_KEY into it

.venv/bin/python -m scripts.run_all --rounds 4 --repeats 3
.venv/bin/python -m scripts.make_report        # -> report/index.html
```

The single most important script:

```bash
.venv/bin/python -m scripts.generality_demo
```

That runs the whole loop on a domain the framework has never seen, with no code
changes anywhere in `agent_forge/`. It is the direct test of the Track 1 claim.

---

## How it works

```
  generate ──► run ──► analyse ──► improve ──┐
     ▲                                        │
     └────────────────────────────────────────┘
            (rollback if the score got worse)
```

| Stage | File | What it does |
|---|---|---|
| **generate** | `agent_forge/generator.py` | Reads the goal + tool descriptions, writes an initial `AgentSpec` — system prompt, orchestration mode, memory notes |
| **run** | `agent_forge/runtime.py` | Executes that spec against every eval task, capturing output, tool calls, latency, tokens |
| **analyse** | each domain's `score()` | Turns traces into metrics **and named failure clusters** |
| **improve** | `agent_forge/improver.py` | Given metrics, failure clusters and the full history of what's been tried, proposes one targeted change |
| **loop** | `agent_forge/loop.py` | Orchestrates rounds, keeps the best spec, rolls back regressions, writes `runs/*.json` |

### The four levers

`AgentSpec` carries exactly the four things the brief names as improvable:

```python
system_prompt: str          # prompts
tools: list[ToolSpec]       # tools
memory_notes: list[str]     # memory
orchestration: str          # orchestration strategy
```

`orchestration` is a **real variable, not a label**. The three modes genuinely
differ in `runtime.py`:

- `single-shot` — one call, tools unreachable
- `react-loop` — tool-calling loop until the model stops asking
- `planner-executor` — a plain-text planning pass, then execution with tools

This matters because it lets the system fix a class of failure that no prompt
edit could. In the generality demo the system's **first** move was switching
orchestration, not rewording a prompt.

### Why failure clusters are the core idea

`score()` returns `(metrics, failure_modes)`. The second value is the one that
makes the loop work:

```python
{"missed_second_issue_in_multi_issue_ticket": 3,
 "billing_refunds_confusion_no_lookup_called": 2}
```

"Accuracy is 0.72" tells an improver nothing actionable. A *named* cluster tells
it what to change. Anyone can write a retry loop; diagnosis is the contribution.

---

## Adding a domain

A domain is the only thing you write. Nothing in `agent_forge/` changes.

```python
class MyDomain:
    name = "my_domain"
    goal = "A bare statement of intent — NOT a spec sheet."
    tools = [ToolSpec("my_tool", "what it does")]

    def tasks(self) -> list[dict]: ...
    def run(self, spec: AgentSpec, task: dict) -> RunTrace: ...
    def score(self, traces) -> tuple[dict[str, float], dict[str, int]]: ...
```

**The goal must be a statement of intent, not a specification.** An early
version of the invoice goal spelled out "use ISO dates, null for missing
fields, take the final amount payable" — round 0 immediately scored 0.98 and
the improver had nothing left to win. Stripping it back to *"pull out the
vendor, date and total"* dropped round 0 to 0.80 and let the system **derive**
the ISO-date convention from its own failures. That derivation is the thing
Track 1 is actually asking for.

Before trusting a new domain, measure a naive baseline. If something trivial
already scores above ~0.85, the eval set has no headroom and will prove nothing.

---

## The three domains

Chosen to differ in **shape**, not just topic — that's what makes "multiple
distinct domains" a real claim rather than a restatement.

| Domain | Shape | Output | Metric |
|---|---|---|---|
| `ticket_routing` | classification | a label | accuracy |
| `invoice_extraction` | structured extraction | a JSON record | field-level accuracy |
| `meeting_scheduler` | constraint satisfaction | a time | exact-match accuracy |

`meeting_scheduler` was written **after** the framework was finished and tuned
on the other two. It is the generality test.

### Results — n = 8 runs per domain, 4 rounds each (`report/variance.json`)

| Domain | Round 0 | Best | Gain | Gain sd | Zero-gain runs |
|---|---|---|---|---|---|
| `ticket_routing` | 0.785 | 0.889 | **+0.104** | 0.081 | 2 / 8 |
| `invoice_extraction` | 0.898 | 0.958 | **+0.060** | 0.065 | 1 / 8 |
| `meeting_scheduler` *(unseen)* | 0.812 | 0.917 | **+0.104** | 0.107 | 3 / 8 |

On average the system improves the agent it wrote in all three domains,
including one it had never seen — and it fails to improve anything in **6 of
24 runs**. Reliability was 1.000 across all 24 runs (no crashes). Raw
per-run curves are in `report/variance.json`; see `SUBMISSION.md` for how this
number was arrived at.

Each eval set is built so failures cluster into nameable modes. In
`ticket_routing`, for example:

- `clear` — unambiguous from the text
- `needs_lookup` — **near-identical wording, different gold labels**, resolvable
  only by calling the lookup tool, so guessing from sentiment cannot beat chance
- `multi_issue` — two problems in one ticket, so any single label is wrong;
  unfixable by prompt wording, fixable only by changing orchestration

---

## Things that are true and inconvenient

Reported here rather than buried, because they affect how the numbers should be read.

**Single runs are noisy — noisier than we first believed.** `gpt-5-nano` is
non-deterministic and rejects the `temperature` parameter, so it cannot be
pinned. An earlier draft reported 3 repeats of the unseen domain, all reaching
1.000. A later run scored 0.583 with zero gain, contradicting that. The
`report/index.html` curves below are illustrative examples (3 per domain,
kept fixed at that count); the actual distribution — mean gain, spread, and
the 6-of-24 zero-gain rate — is measured at n=8 per domain in
`scripts/measure_variance.py` and recorded in `report/variance.json`.

**One early "result" was our own bug.** The scheduler first showed a dramatic
0.167 → 0.667 climb. Investigation showed the dominant failure cluster
(`no_parseable_time_returned`) was caused by `MAX_TOOL_ITERATIONS = 6` cutting
off the agent's search mid-scan — the system was fighting the framework, not
learning. With the cap raised to 14 the honest curve is 0.833 → 1.000. The
smaller, real number is the one reported.

**Dollar costs are only real for runs recorded after the pricing constants
were set.** `USD_PER_1M_*_TOKENS` in `llm.py` now hold gpt-5-nano's real
per-token rates, so cost is computed live from each run's own token counts.
Runs already in `runs/` from before that point show `total_cost_usd: 0.00`
and can't be corrected retroactively, because per-call token counts were
never persisted to disk — only the aggregate metric was. Token totals
printed at the end of a run are exact throughout.

**The available model is small.** Only `gpt-5-nano` and two embedding models are
reachable on the grant key. Domain design had to account for this: an early
semantic-retrieval domain was abandoned because `text-embedding-3-small` scored
11/12 with no agent involvement at all — no headroom, nothing proved.

---

## Working with `gpt-5-nano`

Three behaviours that cost real debugging time, handled in `llm.py`:

1. **It is a reasoning model.** `max_completion_tokens` is a single budget
   shared by hidden reasoning tokens *and* visible output. A 16-token budget
   produced 16 reasoning tokens and an **empty string with no error**. `llm.py`
   raises a clear exception instead of returning empty text.
2. **`temperature` is rejected** — any value but the default returns a 400.
3. **`reasoning_effort` is a hint, not a switch.** `"low"` measured 0 reasoning
   tokens on a trivial call and 320 on a real one. Never size a budget assuming
   zero. At `"medium"` the improver consumed its entire 4000-token budget on
   reasoning and returned nothing.

---

## Layout

```
agent_forge/       the factory — domain-agnostic
  spec.py          AgentSpec, RunTrace, RoundResult, Domain protocol
  llm.py           OpenAI wrapper, usage accounting, empty-output guard
  generator.py     goal + tools -> initial AgentSpec
  runtime.py       AgentSpec + task -> RunTrace  (the three orchestration modes)
  improver.py      failures + history -> next AgentSpec
  loop.py          rounds, keep-best, rollback, run logging
domains/           one folder per domain; the only thing you write
runs/              per-run JSON logs, one per domain per run
report/            generated HTML report
scripts/
  run_all.py         every domain, with --repeats for variance
  generality_demo.py the unseen-domain proof
  make_report.py     runs/*.json -> report/index.html
```

---

## Built with AO

The framework design, all three domains, the failure-cluster taxonomy, the
rollback mechanism, and the diagnosis of every issue in the "inconvenient"
section above were built with Claude Code directly. AO was adopted in the
final phase of the hackathon, to orchestrate the remaining work as parallel
worker sessions — each in its own git worktree against
`github.com/hey-shiv/agent-forge` — planned and dispatched by an AO
orchestrator agent.
