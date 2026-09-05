# BUILD PROMPT — Agent Forge (Syndicate hackathon, Track 1)

Copy everything below the line into your AI of choice.

---

# TASK

Build a complete, working, demoable project called **Agent Forge** for a hackathon
submission. You have roughly 18 hours of wall time. Prioritise a shippable
end-to-end result over completeness. Write real, runnable code — no pseudocode,
no placeholders, no `TODO` stubs in anything you claim is finished.

## 1. What the hackathon asks for

This is **Track 1: Automated Agent Engineering** of the Syndicate hackathon.
The literal brief:

> Build a system that can design, test, and improve specialized agents for tasks
> it has never seen before. Given only a goal, available tools, and a way to
> evaluate success, your system should:
> - Generate an agent architecture
> - Run the agent
> - Analyze where it fails
> - Iteratively improve its prompts, tools, memory, or orchestration strategy
>
> Strong submissions should demonstrate this across multiple distinct domains and
> show measurable improvements in: Accuracy, Reliability, Cost, Speed.

Read that carefully, because it constrains the design:

- **The deliverable is the factory, not the agent.** You are building the thing
  that *produces* agents. The agents are disposable output.
- **"Tasks it has never seen before"** means nothing task-specific may be
  hardcoded in the system. Everything task-specific arrives at runtime through
  three inputs: a goal string, a list of tool descriptions, and an eval function.
  If a judge hands it a brand-new task spec, it must produce a working agent.
- **"Multiple distinct domains"** is how you *prove* you didn't hardcode. The
  domains must differ in shape, not just topic — different output types,
  different metric families.
- **Four scoring axes**, not one. Accuracy, reliability (does it work every
  time / does it crash), cost (tokens), speed (latency). Track all four per
  round. A change that gains accuracy while tripling cost is a trade-off, and
  showing you *know* that is worth points.

## 2. Hard constraints

**Model access.** The only available models are:
- `gpt-5-nano` (chat)
- `text-embedding-3-small`, `text-embedding-ada-002` (embeddings)

`gpt-5`, `gpt-5-mini` and `gpt-5-codex` are **not accessible** — do not write
code that calls them. Read `OPENAI_API_KEY` from a `.env` file via
`python-dotenv`. Never hardcode the key. Add `.env` to `.gitignore` **before**
writing the key to disk.

**Python 3.10+, in a virtualenv.** Dependencies: `openai`, `python-dotenv`,
`numpy`. Keep it minimal.

## 3. CRITICAL: traps that will cost you hours if you don't know them

These were all discovered the expensive way. Take them as given.

### 3a. `gpt-5-nano` is a REASONING model

`max_completion_tokens` is a **single budget shared by hidden reasoning tokens
AND visible output**. Measured behaviour:

```
max_completion_tokens=16   -> content: ''      (16 reasoning tokens, 0 output)
max_completion_tokens=2000 -> content: '{...}' (320 reasoning + 20 output)
```

If the budget is too small you get an **empty string and NO error** — the API
treats it as success. Always use a generous budget (4000–8000) and **raise a
clear exception when the returned text is empty**, naming the reasoning-token
count, or you will lose an hour to a silent failure.

### 3b. `temperature` is rejected

`gpt-5-nano` accepts only the default temperature. Passing `temperature=0.7`
returns a 400. Do not pass it at all.

### 3c. `reasoning_effort` is a hint, not a switch

`reasoning_effort="low"` measured 0 reasoning tokens on a trivial request but
still spent 320 on a real one. It *reduces* hidden spend; it does not eliminate
it. Never size a token budget assuming zero.

Also: `reasoning_effort="medium"` on a long improver prompt consumed the entire
4000-token budget on reasoning and returned empty. Use `"low"` with a wide
budget for structured JSON output.

### 3d. Your eval sets MUST have headroom — this is the #1 design mistake

If round 0 already scores 0.97, the improver has nothing to win and can only
make things worse. Your improvement curve will be noise around a ceiling and the
submission will be unconvincing.

Two specific mistakes that cause this:

1. **Writing a goal that is secretly a spec sheet.** If the goal says "return
   dates in ISO 8601 format, use null for missing fields, take the final amount
   payable" — you have solved the task in the prompt. Round 0 scores ~0.98.
   The goal must be a bare statement of *intent* ("pull out the vendor, date and
   total, return JSON"). The conventions are what the system must **discover
   from failures**. That is literally what Track 1 is asking for.

2. **Annotating away the difficulty.** Writing a test document containing
   `03/04/2026 (dd/mm/yyyy)` hands over the answer. Remove the annotation and
   make the ambiguity resolvable by an inferable rule instead (e.g. GBP/EUR/INR
   invoices are day-first, USD invoices are month-first). Now the system has to
   notice that date errors correlate with currency and encode the rule itself —
   which is a genuinely impressive thing to show in a demo.

**Before running the full loop, always measure a naive baseline.** If a trivial
approach already scores >0.85, redesign the eval set. Do this check first, every
time — it takes two minutes and saves an hour.

### 3e. Semantic retrieval is a BAD domain choice here

`text-embedding-3-small` is very strong. An attempt at a "rewrite the vague query
to retrieve the right doc" domain scored **11/12 with no rewriting at all**, even
with deliberately near-duplicate distractor documents and buried decisive
details. There was no headroom and the domain proved nothing. Do not spend time
on this. Pick domains where a *small chat model* is weak — multi-step reasoning,
constraint satisfaction, strict schema adherence with conflicting evidence.

### 3f. The improver WILL wander unless you constrain it

Observed on a real run without safeguards: accuracy went 0.889 → 0.833 → 0.778.
The improver instructed the agent to stop calling its lookup tool; tool calls
fell 7 → 5 → 4 and accuracy followed. Each change was made from the previous
already-degraded spec, so damage compounded.

You **must** implement all three of:

1. **History** — pass every previous round's change summary, metrics and failure
   modes into the improver prompt, so it doesn't retry ideas or undo wins.
2. **Keep-best-so-far with rollback** — if a round scores below the best seen,
   discard that spec and make the next proposal from the best one instead.
3. **An explicit regression signal** — tell the improver in words: "your last
   change made it worse, it has been rolled back, try a different lever."

This is honest hill-climbing, it is standard practice, and it is also a genuine
feature to demo (my runs caught and rejected 4 regressions).

## 4. Architecture to build

```
agent_forge/
  spec.py       AgentSpec, RunTrace, RoundResult, Domain protocol
  llm.py        OpenAI wrapper: usage accounting, empty-output guard, JSON parsing
  generator.py  goal + tools            -> initial AgentSpec
  runtime.py    AgentSpec + one task    -> RunTrace
  improver.py   RoundResult + history   -> next AgentSpec
  loop.py       orchestrates rounds, rollback, saves runs/*.json
domains/
  <domain_name>/domain.py   implements the Domain protocol
runs/           per-run JSON logs
report/         generated HTML report with charts
```

**`AgentSpec`** is the thing being optimised. It must contain at minimum:
`system_prompt: str`, `tools: list[ToolSpec]`, `orchestration: str`,
`memory_notes: list[str]`, `version: int`. These map onto the four levers the
brief names (prompts, tools, memory, orchestration).

**`orchestration`** must be a *real* variable, not a label. Implement at least:
- `single-shot` — one call, tools unavailable
- `react-loop` — tool-calling loop until the model stops requesting tools
- `planner-executor` — a plain-text planning call first, then execution with tools

They must genuinely differ in behaviour, so that the improver can fix a class of
failure that no prompt edit could fix. That contrast is the strongest single
thing you can show a judge.

**`Domain` protocol** — this is the seam that makes the system general:

```python
class Domain(Protocol):
    name: str
    goal: str                 # bare statement of intent — see 3d
    tools: list[ToolSpec]
    def tasks(self) -> list[dict]: ...
    def run(self, spec: AgentSpec, task: dict) -> RunTrace: ...
    def score(self, traces: list[RunTrace]) -> tuple[dict[str, float], dict[str, int]]: ...
```

`score` returns `(metrics, failure_modes)`. **`failure_modes` is the most
important return value in the whole system.** It must be a dict of
*named, actionable* clusters — `{"missed_second_issue_in_multi_issue_ticket": 3,
"billing_refunds_confusion_no_lookup_called": 2}` — not a count of wrong
answers. "Accuracy is 0.7" tells the improver nothing. A named cluster tells it
what to change. Anyone can loop; diagnosis is the actual contribution.

`run` must **never raise**. Catch everything and return a `RunTrace` with the
error recorded — a crashed agent is a reliability data point, not a reason to
abort the round.

Run tasks concurrently (`ThreadPoolExecutor`, ~6 workers). Rounds are otherwise
dominated by serial latency.

## 5. Domains to build

Build **three**, differing in shape:

| Domain | Shape | Output | Metric family |
|---|---|---|---|
| Ticket routing | classification | a label | accuracy |
| Invoice extraction | structured extraction | a JSON record | field-level accuracy |
| Third — your choice | reasoning / constraints | free-form | task-specific |

For the third, pick something `gpt-5-nano` is genuinely bad at. Good candidates:
multi-constraint scheduling, multi-hop arithmetic word problems with distractors,
or resolving conflicting evidence across several documents.

**Design each eval set so failures cluster into nameable modes.** Concretely, for
ticket routing use three kinds of item:
- `clear` — unambiguous from the text
- `needs_lookup` — items whose correct label depends on information only a tool
  can supply. Write these with **near-identical wording and different gold
  labels**, so guessing from sentiment cannot beat chance and the tool must be
  called.
- `multi_issue` — items raising two problems, so any single label is wrong. This
  is unfixable by prompt wording and forces an orchestration change.

That structure is what produces a compelling demo: the system solves the easy
cluster with a prompt edit, plateaus, then has to restructure the agent.

Keep eval sets at 15–25 items. Small enough to iterate fast, large enough that
one item isn't a huge percentage swing.

## 6. Deliverables

1. **Working code**, runnable as `python -m scripts.run_all`.
2. **`runs/*.json`** — one per domain, logging every round: spec version,
   orchestration, full system prompt, change summary, metrics, failure modes,
   whether the round was kept or rolled back.
3. **An HTML report** generated from those JSON files: one improvement curve per
   domain, cost and latency per round, and — most importantly — the improver's
   own stated reason for each change annotated on the curve. A chart with the
   reasoning attached is an argument; a bare chart is not.
4. **README.md** — what it is, how to run it, the architecture, and an honest
   results table.
5. **A generality demo**: a script that takes a brand-new domain the system has
   never seen and runs the full loop on it, unattended, proving nothing is
   hardcoded. This is the single most persuasive artifact you can produce.
6. **A 3-minute demo script** (what to say, what to show, in order).

## 7. Working style

- Verify every claim by running it. Never report a number you haven't seen.
- After each domain, run the loop and paste the actual output before moving on.
- If a domain shows no headroom, say so plainly and redesign it — do not ship a
  flat curve and describe it as an improvement.
- Prefer one convincing curve and a finished submission over three mediocre
  curves and no writeup.
- Track wall-clock time. At the 12-hour mark, stop building and start shipping.

## 8. Success criteria

The submission is strong if a judge can see:
- One domain with a clear, explained improvement curve driven by named failure
  diagnoses
- At least one improvement that changed **orchestration**, not just wording
- The system running on a domain it was never tuned for
- All four axes (accuracy, reliability, cost, speed) tracked per round
- Honest reporting, including regressions that were caught and rolled back

Begin by setting up the project skeleton and `llm.py`, then prove one end-to-end
round works before building anything else.
