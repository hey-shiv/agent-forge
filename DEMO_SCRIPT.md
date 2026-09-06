# Demo video script — ~3:25

*(Target 3:25; like the previous cut, it will likely run a little over in
practice — that's fine. The ablation section is still the single most
differentiating thing you have. The AO segment is now a real segment, not a
closing line — if you must cut further, cut from the mechanism or regression
sections, not from honesty/ablation or the AO segment.)*

Record in this order. Times are cumulative. Everything below is real output —
nothing is staged, so if a live run gives slightly different numbers, say the
numbers you actually see. Judges can tell.

**Setup before recording:**

- Terminal at a readable font size, `report/index.html` already open in a
  second tab.
- The AO desktop app open to the sessions view *before* you start recording —
  that's the AO-usage evidence on screen from the first frame, not cut in
  later.
- `generality_demo` runs the scheduler against a non-deterministic model, and
  `report/variance.json` shows 3 of 8 scheduler runs gain nothing at all. A
  live take can land on a flat curve. Run it once in a second terminal before
  recording so you know what you're going to get, or shoot two takes and pick
  one. If the take you use is flat, say so on camera — the script below
  already sets that up at 1:00-1:50, so a flat take doesn't break anything.
- Have `git worktree list`, `git log --oneline --graph --all | head -20`, and
  `gh pr list --state all` ready to run for the AO segment at 2:30 — run each
  once beforehand so you're not waiting on them live.

---

## 0:00 – 0:20 · The problem

> "Track 1 asks for a system that designs agents for tasks it has never seen.
> So the deliverable isn't an agent — it's the factory that makes them.
>
> Agent Forge takes three inputs and nothing else: a goal, a list of tools,
> and a way to score success. From those it writes an agent, runs it, works
> out *why* it failed, and rewrites it."

**Show:** the diagram at the top of the README, or just the three-input line.

---

## 0:20 – 0:45 · The mechanism, and named failure clusters

**Show:** `report/index.html`, scrolled to `ticket_routing`.

> "Ticket routing, round zero: an agent written from scratch, scoring around
> 0.78. The important part is what happens next — it doesn't just see that
> number, it clusters the failures into *named* modes."

**Point at a failure-cluster chip.**

> "`billing_refunds_confusion_no_lookup_called` — it's not calling the tool it
> needs. That's a diagnosis, not a score, and because it's specific, the fix
> can be specific."

**Point at the "Change the system made, and why" column.**

> "That's the system's own account of what it changed and which failure it
> was aiming at. Diagnosis, targeted fix, measured gain — that's the loop, and
> you'll see it run again in a minute on a domain I built after the fact."

---

## 0:45 – 1:00 · It knows when it's wrong

**Show:** a hollow, dashed marker on the curve.

> "These hollow points are rounds where the change made things worse. The
> system detects that itself, throws the change away, and builds its next
> proposal from the best version, not the damaged one. That's a regression
> caught, not a regression hidden — more on why that distinction matters in a
> minute."

---

## 1:00 – 1:50 · The generality proof — the centrepiece

**Show:** run `python -m scripts.generality_demo` live in the terminal (or
the pre-recorded take — see setup notes above).

> "Everything so far could have been tuned by hand. So here's the real test.
>
> This is a scheduling domain — find the earliest meeting slot that works for
> everyone. Constraint satisfaction, a completely different shape from
> classification or extraction. I wrote it *after* the framework was
> finished, and I changed nothing inside `agent_forge`. It gets the same
> three inputs ticket routing did."

**Let it run. When round 0 → round 1 appears:**

> "Look at its first move. It didn't reword a prompt — it changed the
> *orchestration*, from planner-executor to a react loop. That's the same
> 'change and why' column from a minute ago, deciding the architecture itself
> was wrong, not the wording."

**At the end:**

> "It had never seen this domain, and it designed and ran that agent
> unattended. On a good draw it reaches a perfect 1.0. Not every run does —
> three of the eight runs I measured on this domain gain nothing at all — and
> whether the rewriting is what got it there is a question I actually tested,
> coming up next."

**Show:** the final block printing the system prompt it wrote.

> "That agent, prompt and all, was written entirely by the system, from a
> one-sentence goal."

---

## 1:50 – 2:30 · Honesty section — *the strongest part; do not cut*

> "Now the part I most want you to hear.
>
> I first reported three runs of that unseen domain, all reaching a perfect
> 1.0. Then a release check from a clean clone scored 0.58 with zero
> improvement. One extra sample destroyed my headline.
>
> So I measured eight runs per domain — 24 total, in `report/variance.json`.
> The real numbers: mean gain of about ten points on the unseen domain, ten on
> ticket routing, six on invoices — and **six runs out of twenty-four improve
> nothing at all**. The curves on screen in `report/index.html` are
> illustrative examples, not the statistics; the statistics are in that file.
>
> There's a second one like this. The scheduler originally showed a dramatic
> 0.17 to 0.67 climb, and most of it turned out to be the system fighting a
> bug in my own framework — a tool-iteration cap cutting its search off. I
> fixed the cap; the honest curve is smaller. That's the one in the report."

**Show:** the ablation table in `SUBMISSION.md`.

> "And then I went one further, because there's a hole in every number I just
> gave you. 'Best round minus round zero' goes up with the number of rounds
> even if nothing is learning — you're just sampling more times and keeping the
> luckiest.
>
> So I built a control. Same generated agent, re-run four times, take the best,
> improver switched off entirely. That measures the gain you get from noise
> alone.
>
> On the scheduling domain my improver came out **0.03 behind** that control.
> On ticket routing, **0.04 ahead**. Neither is significant — opposite signs,
> both intervals include zero.
>
> So I can't tell you my improvement loop beats simply re-running the agent.
> At this sample size, that's undetermined. It'd take sixty to a hundred runs
> per arm to settle it.
>
> That result is in the submission, in a table, near the top — not a footnote.
> Because a system built to measure agents honestly has to survive being
> pointed at itself. And if I don't run that experiment, I don't actually know
> whether my project works. A judge shouldn't have to be the one to ask."

---

## 2:30 – 3:10 · Building this with AO — the audit layer, not the code

**Show:** terminal, `git worktree list`.

> "One thing to be honest about here, since a quarter of this score is AO
> usage, and the earlier cut of this video gave that about two seconds.
>
> Claude Code wrote the framework, the three domains, and the report
> generator — everything I've shown you so far. AO came in for the final
> phase: one orchestrator session planning what was left, and dispatching it
> to worker sessions, each running in its own isolated git worktree against
> this repo."

**Show:** `git log --oneline --graph --all | head -20` — three branches
merging into `main`.

> "Three worker sessions landed changes — you can see the merges here. And I
> didn't send them out to write features. I sent them to audit what I'd
> already written, because a project whose whole pitch is 'measure yourself
> honestly' has to survive someone else checking its homework."

**Show:** `gh pr list --state all` — two merged pull requests on GitHub.

> "Here's the one that matters most. Pull request one is titled 'docs: correct
> AO's role to the final orchestration phase.' That worker session read my own
> submission, found a sentence overstating what AO had actually done on this
> project, and corrected it. The line I just said to you — 'AO came in for the
> final phase' — exists because an AO session caught me overclaiming about AO
> itself.
>
> Another worker session did something less dramatic and just as necessary:
> it went through the README and the submission and reconciled every headline
> number back to `report/variance.json`, the one file I'd already named as
> the statistical source of truth — so a number quoted in prose can't quietly
> drift from the number that was actually measured.
>
> That's the AO story here: not a second code generator — a second set of
> eyes, running as parallel sessions whose job was to check whether the
> honesty this project claims actually holds, including about itself."

---

## 3:10 – 3:25 · Close

> "Three domains, three different shapes, one unchanged system. It designs a
> working agent for a task it was never built for, from one sentence and a
> tool description. It exercises orchestration as a real lever, not just
> wording. It names its own failure modes and catches its own regressions.
>
> What I can't yet tell you is whether the improvement loop beats resampling.
> I measured that, and at my sample size it's undetermined. That's the next
> experiment, and it's specified in the submission.
>
> Built with Claude Code. Finished with AO — including the session that
> caught me overstating what AO itself had done."

---

## Things to have on screen at some point

- [ ] `report/index.html` — curves, failure clusters, the "why" column
- [ ] A live (or pre-recorded) `generality_demo` run
- [ ] The system prompt the system wrote for the unseen domain
- [ ] `git worktree list` — the AO worker worktrees
- [ ] `git log --oneline --graph --all` — three worker branches merged into main
- [ ] `gh pr list --state all` — two merged pull requests
- [ ] The AO desktop app, open to the sessions view

## Do not

- Do not claim the system is autonomous *end to end* — a human wrote the domains
  and eval functions. The claim is that the **agent design and improvement** is
  autonomous. Overclaiming is the fastest way to lose credibility in Q&A.
- Cost figures are real only for runs recorded after pricing was set in
  `llm.py`; older logs show $0.00. Say so if the number is on screen.
- Do not read the whole generated system prompt aloud — show it, summarise it.
- Do not say "it improves agents" as a flat claim anywhere. The ablation does not
  support it. Say "it designs working agents for unseen domains, and whether the
  improvement loop beats resampling is undetermined at my sample size." That
  phrasing is both true and stronger — it shows you know the difference.
- Do not overstate what AO did. Claude Code built the framework, the three
  domains, and the report generator. AO was adopted for the final phase and
  ran the audit and reconciliation sessions described at 2:30 — it did not
  design the agents, write the domains, or build the report generator. Say
  exactly that if asked.
