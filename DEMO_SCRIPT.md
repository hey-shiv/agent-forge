# Demo video script — 3 minutes

Record in this order. Times are cumulative. Everything below is real output —
nothing is staged, so if a live run gives slightly different numbers, say the
numbers you actually see. Judges can tell.

**Setup before recording:** terminal at a readable font size,
`report/index.html` already open in a second tab, and one AO session visible so
the AO-usage requirement is evidenced on camera.

---

## 0:00 – 0:25 · The problem

> "Track 1 asks for a system that designs agents for tasks it has never seen.
> So the deliverable isn't an agent — it's the factory that makes them.
>
> Agent Forge takes three inputs and nothing else: a goal, a list of tools, and
> a way to score success. From those it writes an agent, runs it, works out
> *why* it failed, and rewrites it. Then does it again."

**Show:** the diagram at the top of the README, or just the three-input line.

---

## 0:25 – 1:05 · The mechanism, on a domain it knows

**Show:** `report/index.html`, scrolled to `ticket_routing`.

> "Here it is on support-ticket routing. Round zero, it writes an agent from
> scratch — around 0.78.
>
> Now the important part. It doesn't just see a single accuracy number. It clusters
> the failures into *named* modes."

**Point at the failure-cluster chips in the table.**

> "`billing_refunds_confusion_no_lookup_called` — it's not calling the tool it
> needs. That's a diagnosis, not a score. And because it's specific, the fix can
> be specific."

**Point at the "Change the system made, and why" column.**

> "That column is the system's own words for what it changed and which failure
> it was targeting. Diagnosis, targeted fix, measured gain — that's the loop."

---

## 1:05 – 1:35 · It knows when it's wrong

**Show:** a hollow, dashed marker on the curve.

> "These hollow points are rounds where the change made things *worse*. The
> system detects that, throws the change away, and makes its next proposal from
> the best version instead of the damaged one.
>
> That mattered. An early build without this went 0.889 down to 0.778 across
> three rounds — it told the agent to stop using its own lookup tool and then
> kept building on that mistake."

---

## 1:35 – 2:30 · The generality proof — **the centrepiece**

**Show:** run `python -m scripts.generality_demo` live in the terminal.

> "Everything so far could have been tuned by hand. So here's the real test.
>
> This is a scheduling domain — find the earliest meeting slot that works for
> everyone. Constraint satisfaction, a completely different shape from
> classification or extraction. I wrote it *after* the framework was finished,
> and I changed nothing inside `agent_forge`. It gets the same three inputs."

**Let it run. When round 0 → round 1 appears:**

> "Look at its first move. It didn't reword a prompt — it changed the
> *orchestration*, from planner-executor to a react loop. That's the system
> deciding the architecture was wrong, not the wording."

**At the end:**

> "It had never seen this domain, and it improved its own agent unattended.
> On a good draw it reaches a perfect 1.0 — though as I'll say in a moment,
> not every run does."

**Show:** the final block printing the system prompt it wrote.

> "And that agent was written entirely by the system, from a one-sentence goal."

---

## 2:30 – 2:55 · Honesty section — *do not cut this*

> "Now the part I most want you to hear.
>
> I first reported three runs of that unseen domain, all reaching a perfect 1.0.
> Then I did a release check from a clean clone, and it scored 0.58 with zero
> improvement. One extra sample destroyed my headline.
>
> So I took eight runs per domain. The real numbers are: mean gain of about
> ten points on the unseen domain, ten on ticket routing, six on invoices — and
> **six runs out of twenty-four improve nothing at all**.
>
> That's a worse result than what I had before. It's also the true one. A system
> whose whole job is measuring agents honestly has no business reporting its own
> performance from a lucky sample."

**Show:** the results table in `SUBMISSION.md`, or `report/variance.json`.

> "There's a second one like that. The scheduler originally showed a dramatic
> 0.17 to 0.67 climb — and most of it turned out to be the system fighting a bug
> in my own framework, a tool-iteration cap cutting its search off. I fixed the
> cap; the honest curve is smaller. That's the one in the report."

---

## 2:55 – 3:05 · Close

> "Three domains, three different shapes, one unchanged system. It improves on
> all three on average, it catches its own regressions, and it works on a task
> it was never built for — measured over twenty-four runs, not a lucky one.
>
> Built end to end in AO."

---

## Things to have on screen at some point

- [ ] `report/index.html` — curves, failure clusters, the "why" column
- [ ] A live `generality_demo` run
- [ ] The system prompt the system wrote for the unseen domain
- [ ] An AO session (the AO-usage requirement)

## Do not

- Do not claim the system is autonomous *end to end* — a human wrote the domains
  and eval functions. The claim is that the **agent design and improvement** is
  autonomous. Overclaiming is the fastest way to lose credibility in Q&A.
- Cost figures are real only for runs recorded after pricing was set in
  `llm.py`; older logs show $0.00. Say so if the number is on screen.
- Do not read the whole generated system prompt aloud — show it, summarise it.
