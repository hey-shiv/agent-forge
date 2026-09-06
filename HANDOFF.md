# Handoff — what's done, what's left

Written while you were AFK. Everything below marked ⬜ needs you specifically;
everything marked ✅ is finished and verified.

---

## Do these first (they're the only blockers)

⬜ **1. Record the demo video** — [DEMO_SCRIPT.md](DEMO_SCRIPT.md) is a shot-by-shot
script with timings. Have an AO session visible on screen at some point; the
rules say they check for AO usage.

⬜ **2. Submit** — the Notion page linked from the event, plus Discord.

⬜ **3. `git init` and push.** I deliberately did not commit anything — that's
yours to decide. The `.gitignore` is already correct:
- `.env` excluded (your keys)
- `runs/`, `report/` **included** — they're the evidence a judge audits
- pre-kickoff study material excluded

```bash
git init && git add -A && git status      # review before committing
```

⬜ **4. Rotate both API keys after submitting.** They were pasted into a chat
transcript and appeared in a local log (since purged). `.gitignore` covers
`.env`, but rotation is the safe move.

---

## What exists

✅ **The system** — `agent_forge/`: generate → run → analyse → improve, with
history, keep-best rollback, and an escalation rule that forces an orchestration
change when a failure cluster survives repeated prompt edits.

✅ **Three domains, three shapes** — classification, structured extraction, and
constraint satisfaction. The third (`meeting_scheduler`) was written after the
framework was finished and is the generality test.

✅ **Measured honestly at n=8 per domain** — `report/variance.json`. Mean gains
+0.104 / +0.060 / +0.104, with **6 of 24 runs gaining nothing**. That worse,
truer number replaced an earlier lucky-sample claim.

✅ **Ablation — and it came back negative.** `scripts/ablation.py` compares the
improver against a control that re-runs the same spec and takes best-of-N.

| Domain | Improver contribution | Welch t | Verdict |
|---|---|---|---|
| `meeting_scheduler` | −0.031 | −0.57 | indistinguishable |
| `ticket_routing` | +0.042 | +1.13 | indistinguishable |

**At n=8 per arm, we cannot show the improvement loop beats simply re-running
the same agent.** Opposite signs, both intervals include zero. This is written
up prominently in `SUBMISSION.md` rather than buried — read that section before
you record, because the demo script now leads with it.

This is not a failure of the project. It is the project working: a system built
to measure agents honestly, pointed at itself, and reporting what it found. Every
other submission will claim their number went up. You will be the one who
checked whether the number meant anything.

✅ **Neatlogs tracing** (sponsor tool) — opt-in via `NEATLOGS_TRACE=1`. Off by
default because the SDK prints a 23 MB JSON trace to stdout *including the API
key*, which is not something a measurement log should contain.

✅ **18 tests**, ✅ **HTML report**, ✅ **README / SUBMISSION / DEMO_SCRIPT**,
✅ **verified from a clean clone** (fresh venv, install from requirements,
tests, live demo).

---

## Commands

```bash
# the single most persuasive thing to show
.venv/bin/python -m scripts.generality_demo

# with sponsor tracing on
NEATLOGS_TRACE=1 .venv/bin/python -m scripts.generality_demo

# full sweep + regenerate the report
.venv/bin/python -m scripts.run_all --rounds 4 --repeats 3
.venv/bin/python -m scripts.make_report

# the statistics
.venv/bin/python -m scripts.measure_variance --domain meeting_scheduler --repeats 8
.venv/bin/python -m scripts.ablation --domain meeting_scheduler --repeats 8

.venv/bin/python -m pytest tests/ -q
```

---

## If a judge pushes back, the honest answers

**"Is the improvement real or just noise?"**
That's exactly what `scripts/ablation.py` measures — control arm re-runs the
same spec and takes best-of-N, so it captures the gain available with no
learning at all. The difference between the arms is the improver's real
contribution. The number is in `SUBMISSION.md`; quote it as measured, including
if it's weaker than you'd like.

**"Is it really autonomous?"**
The agent *design and improvement* is. A human wrote the domains and eval
functions. Don't claim more than that.

**"Only 12–19 eval items?"**
Correct, and it's why variance is large — one item moves accuracy 5–8 points.
Stated in the limitations section rather than hidden.

**"Why such a small model?"**
`gpt-5-nano` was the only chat model on the grant key. It also can't be pinned
to a fixed temperature, which is the root of the run-to-run spread.
