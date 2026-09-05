# Syndicate by Maximor — Track Decision

Date: 2026-09-02

## Decision: Track 1 — Automated Agent Engineering

## Why (based on resume + project history review)
- Strongest work is rigorous ML/research engineering: cover-song retrieval on
  Da-TACOS with MAP/MRR/Recall@k metrics, controlled ablations, failure
  analysis, bootstrap confidence intervals. This is the exact muscle Track 1
  needs: generate an agent, run it, diagnose failures, iterate, measure
  improvement.
- Hands-on agentic-system reps already exist in
  `~/Desktop/agenticai-projects`: RAG from scratch, legal AI assistant,
  research agent, multimodal RAG, agentic RAG + real-time tool use.
- No finance/accounting domain background — Track 2 (Autonomous Office of
  the CFO) would feel bolted-on rather than authentic.

## Project concept sketch
Build a meta-system: given a goal + tool list + eval harness, it scaffolds
an agent, runs it against 2-3 different domains (reuse retrieval-eval
instincts — precision/recall-style metrics), and iterates on
prompts/tools/orchestration when it fails, logging measurable improvement
(accuracy, reliability, cost, speed) across iterations.

Candidate domains to test across (leverage existing infra/data):
- Audio/retrieval task (Da-TACOS / cover-song pipeline)
- RAG/legal task (agenticai-projects/02-legal-ai-assistant)
- A coding or research-agent task (agenticai-projects/03-research-agent)

## AO requirement
Must use AO (aoagents.dev) throughout the build — mention usage in the
final demo video/submission. AO session count matters for review.

## Key links
- Notion (submission guidelines): https://maaztwts.notion.site/Syndicate-3cc32902e4a38075bfa9f03149ef150d
- Discord: https://discord.gg/Sy3EwRBQX3
- Hackathon pass: https://aoagents.dev/hackathons/syndicate/pass/

## Next steps (not yet done)
- [ ] Generate hackathon pass, post on X/LinkedIn tagging AO
- [ ] Join Discord
- [ ] Scaffold architecture for the meta-agent system
- [ ] Pick final 2-3 eval domains and build eval harnesses
