"""LLM access for agent_forge's generator and improver.

Backed by OpenAI (the hackathon credits from AI Grants India). The model,
gpt-5-nano, is a *reasoning* model, which changes three things versus a
classic chat model — all three are handled here so callers don't have to
think about them:

1. `max_completion_tokens` is a single budget shared by the model's hidden
   reasoning tokens AND its visible output. Set it too low and the model
   spends the whole budget thinking and returns an EMPTY STRING with no
   error. Measured: a 16-token budget produced 16 reasoning tokens and no
   output at all. The default here is deliberately generous.

2. `reasoning_effort` is a budget hint, not a switch. On a trivial request
   ("echo this JSON") "low" measured 0 reasoning tokens; on a real generation
   request it still spent 320. So it *reduces* hidden spend, it does not
   eliminate it — never size `max_completion_tokens` assuming zero.

3. `temperature` is rejected outright — only the default is supported. Do
   not pass it.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

DEFAULT_MODEL = os.environ.get("AGENT_FORGE_MODEL", "gpt-5-nano")

# gpt-5-nano standard API pricing, from OpenAI's official pricing page
# (developers.openai.com/api/docs/pricing), checked 2026-09-06.
#
# NOTE: a run's cost is computed live from its own token counts as it executes,
# so only runs recorded AFTER this constant was set carry real dollar figures.
# Runs in runs/ from before then stored total_cost_usd = 0.00 and cannot be
# corrected retroactively — the per-call token counts were never persisted.
USD_PER_1M_INPUT_TOKENS = 0.05
USD_PER_1M_OUTPUT_TOKENS = 0.40

_client = None
_tracing = None


def _init_tracing() -> str:
    """Optional Neatlogs tracing, enabled only when NEATLOGS_API_KEY is set.

    Every model call in this project goes through `complete()` below, so
    initialising once instruments the whole system: each generator and improver
    call, with its prompt, reply and token usage, lands in the Neatlogs
    dashboard where a round's failure analysis can be inspected call by call.

    Initialised lazily rather than at import, so merely importing this module —
    as the test suite does — costs no network call.

    Every failure path here is swallowed on purpose. Tracing is observability,
    not functionality: a missing package, an expired key or a network problem at
    the sponsor's end must never take down a run — least of all on a judge's
    machine, where the key will simply be absent.
    """
    global _tracing
    if _tracing is not None:
        return _tracing

    # Opt-IN, not opt-out. The SDK writes a full JSON trace of every call to
    # stdout, which during a measurement run produced a 23 MB log that buried
    # the actual results — and, worse, printed the API key in plaintext into it.
    # Tracing is therefore off unless explicitly requested, so that measurement
    # scripts stay clean and no key can leak into a log that gets shared.
    if os.environ.get("NEATLOGS_TRACE", "").lower() not in ("1", "true", "yes"):
        _tracing = "off (set NEATLOGS_TRACE=1 to enable)"
        return _tracing

    api_key = os.environ.get("NEATLOGS_API_KEY")
    if not api_key:
        _tracing = "disabled (no NEATLOGS_API_KEY)"
        return _tracing

    try:
        import neatlogs

        neatlogs.init(api_key=api_key, tags=["agent-forge", "syndicate", DEFAULT_MODEL])
        _tracing = "enabled"
    except Exception as exc:  # noqa: BLE001 - see docstring
        _tracing = f"unavailable ({type(exc).__name__})"
    return _tracing


def tracing_status() -> str:
    return _init_tracing()


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not found. Copy .env.example to .env and fill it in."
            )
        # Start tracing before the client exists so instrumentation catches
        # every call, including the very first one.
        _init_tracing()
        _client = OpenAI(api_key=api_key)
    return _client


@dataclass
class Usage:
    """Token and latency accounting — the raw material for Track 1's cost and
    speed metrics."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    seconds: float = 0.0

    def add(self, other: "Usage") -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.reasoning_tokens += other.reasoning_tokens
        self.seconds += other.seconds

    @property
    def usd(self) -> float:
        return (
            self.input_tokens / 1_000_000 * USD_PER_1M_INPUT_TOKENS
            + self.output_tokens / 1_000_000 * USD_PER_1M_OUTPUT_TOKENS
        )

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "seconds": round(self.seconds, 2),
            "usd": round(self.usd, 6),
        }


# Running total across the whole process, so a loop can report cost per round.
session_usage = Usage()


@dataclass
class Completion:
    text: str
    usage: Usage = field(default_factory=Usage)


def complete(
    system: str,
    prompt: str,
    model: str | None = None,
    max_completion_tokens: int = 4000,
    reasoning_effort: str = "low",
) -> Completion:
    """One chat completion. Returns text plus its usage record."""
    client = _get_client()
    t0 = time.time()

    resp = client.chat.completions.create(
        model=model or DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=max_completion_tokens,
        reasoning_effort=reasoning_effort,
        # No temperature — gpt-5-nano rejects any value but the default.
    )

    elapsed = time.time() - t0
    u = resp.usage
    reasoning = 0
    if u.completion_tokens_details is not None:
        reasoning = u.completion_tokens_details.reasoning_tokens or 0

    usage = Usage(
        calls=1,
        input_tokens=u.prompt_tokens,
        output_tokens=u.completion_tokens,
        reasoning_tokens=reasoning,
        seconds=elapsed,
    )
    session_usage.add(usage)

    text = resp.choices[0].message.content or ""

    if not text.strip():
        raise RuntimeError(
            f"Model returned empty text. It spent {reasoning} tokens on reasoning "
            f"against a budget of {max_completion_tokens}. Raise "
            f"max_completion_tokens or lower reasoning_effort."
        )

    return Completion(text=text, usage=usage)


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def complete_json(
    system: str,
    prompt: str,
    model: str | None = None,
    max_completion_tokens: int = 4000,
    reasoning_effort: str = "low",
    retries: int = 2,
) -> tuple[dict, Usage]:
    """Same as `complete`, but parses the reply as JSON.

    Small models wrap JSON in markdown fences even when told not to, so the
    fences are stripped before parsing, and a parse failure is retried with a
    blunter instruction rather than crashing the whole run.
    """
    total = Usage()
    last_error = ""
    attempt_prompt = prompt

    for _attempt in range(retries + 1):
        result = complete(
            system,
            attempt_prompt,
            model=model,
            max_completion_tokens=max_completion_tokens,
            reasoning_effort=reasoning_effort,
        )
        total.add(result.usage)

        cleaned = _FENCE.sub("", result.text).strip()
        try:
            return json.loads(cleaned), total
        except json.JSONDecodeError as exc:
            last_error = str(exc)
            attempt_prompt = (
                f"{prompt}\n\nYour previous reply could not be parsed as JSON "
                f"({last_error}). Return ONLY a raw JSON object. No markdown "
                f"fences, no commentary."
            )

    raise ValueError(f"Could not get valid JSON after {retries + 1} attempts: {last_error}")
