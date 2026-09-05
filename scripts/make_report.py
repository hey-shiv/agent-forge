"""Generate report/index.html from runs/*.json.

The report is the submission artifact: it has to show not just that a number
went up, but WHY it went up. So every round on every curve carries the
improver's own stated reason and the failure cluster it was targeting. A chart
with the reasoning attached is an argument; a bare chart is decoration.

    python -m scripts.make_report
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"
REPORT_DIR = ROOT / "report"

# Categorical slots 1 and 2 from the validated reference palette.
# Verified with validate_palette.js: all six checks PASS in both modes.
SERIES = [
    {"light": "#2a78d6", "dark": "#3987e5"},   # slot 1 blue
    {"light": "#eb6834", "dark": "#d95926"},   # slot 2 orange
]

W, H = 560, 250
PAD_L, PAD_R, PAD_T, PAD_B = 52, 20, 22, 42


REPEATS = 3


def recent_runs_per_domain() -> list[dict]:
    """The REPEATS most recent runs per domain.

    Deliberately not "the single latest run": gpt-5-nano cannot be pinned to a
    fixed temperature, and repeated runs of the same domain produced round-0
    accuracies spanning 0.722 to 1.000. Reporting one curve would be reporting a
    sample as though it were a measurement.
    """
    by_domain: dict[str, list[Path]] = {}
    for path in sorted(RUNS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        domain = data.get("domain")
        if domain:
            by_domain.setdefault(domain, []).append(path)

    out = []
    for domain, paths in sorted(by_domain.items()):
        chosen = paths[-REPEATS:]
        runs = [json.loads(p.read_text()) | {"_file": p.name} for p in chosen]
        out.append({"domain": domain, "runs": runs})
    return out


def curve_of(run: dict) -> list[float]:
    return [r["metrics"].get("accuracy", 0.0) for r in run["rounds"]]


def esc(text) -> str:
    return html.escape(str(text))


def line_chart(rounds: list[dict], idx: int) -> str:
    """Single-series accuracy curve. One series, so no legend box — the figure
    title names it. Rolled-back rounds are drawn hollow, which is a secondary
    (non-color) encoding of the same fact the table states."""
    n = len(rounds)
    if n == 0:
        return "<p>No rounds.</p>"

    values = [r["metrics"].get("accuracy", 0.0) for r in rounds]
    lo = max(0.0, min(values) - 0.12)
    hi = min(1.0, max(values) + 0.08)
    if hi - lo < 0.15:
        hi = min(1.0, lo + 0.15)

    plot_w = W - PAD_L - PAD_R
    plot_h = H - PAD_T - PAD_B

    def px(i: int) -> float:
        return PAD_L + (plot_w * i / max(n - 1, 1))

    def py(v: float) -> float:
        return PAD_T + plot_h * (1 - (v - lo) / (hi - lo))

    parts: list[str] = []

    # recessive gridlines + y labels
    for t in range(5):
        v = lo + (hi - lo) * t / 4
        y = py(v)
        parts.append(
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
            f'stroke="var(--grid)" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{PAD_L - 10}" y="{y + 4:.1f}" text-anchor="end" '
            f'class="tick">{v:.2f}</text>'
        )

    # x labels
    for i in range(n):
        parts.append(
            f'<text x="{px(i):.1f}" y="{H - PAD_B + 20}" text-anchor="middle" '
            f'class="tick">R{i}</text>'
        )

    colour = f"var(--series-{idx + 1})"
    points = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(values))
    parts.append(
        f'<polyline points="{points}" fill="none" stroke="{colour}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
    )

    best = max(values)
    for i, v in enumerate(values):
        kept = rounds[i].get("kept", True)
        cx, cy = px(i), py(v)
        # 2px surface ring so overlapping marks stay separable
        if kept:
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5.5" fill="{colour}" '
                f'stroke="var(--surface)" stroke-width="2"/>'
            )
        else:
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="var(--surface)" '
                f'stroke="{colour}" stroke-width="2" stroke-dasharray="2.5 2"/>'
            )
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="14" fill="transparent">'
            f"<title>Round {i} — accuracy {v:.3f}"
            f"{'' if kept else ' (rolled back)'}</title></circle>"
        )
        # Label only the best point. Round 0 sits hard against the y-axis where
        # any label collides with the tick text, and the "Round 0" stat tile
        # directly above the chart already carries that number — so labelling
        # it here was both colliding and redundant.
        if v == best:
            parts.append(
                f'<text x="{cx:.1f}" y="{cy - 13:.1f}" text-anchor="middle" '
                f'class="pt">{v:.3f}</text>'
            )

    return (
        f'<svg viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="Accuracy by round; hollow markers are rounds that were '
        f'rolled back.">{"".join(parts)}</svg>'
    )


def latency_chart(rounds: list[dict], idx: int) -> str:
    """Speed is one of the four scored axes and moves opposite to accuracy here,
    so it gets its own frame rather than a second y-axis."""
    vals = [r["metrics"].get("avg_latency_s", 0.0) for r in rounds]
    if not vals or max(vals) == 0:
        return ""
    n = len(vals)
    w, h = 560, 120
    pl, pr, pt, pb = 52, 20, 14, 30
    plot_w, plot_h = w - pl - pr, h - pt - pb
    hi = max(vals) * 1.2
    band = plot_w / n
    bw = min(band * 0.55, 40)
    colour = f"var(--series-{idx + 1})"

    parts = [
        f'<line x1="{pl}" y1="{pt + plot_h}" x2="{w - pr}" y2="{pt + plot_h}" '
        f'stroke="var(--grid)" stroke-width="1"/>'
    ]
    for i, v in enumerate(vals):
        bh = plot_h * (v / hi)
        x = pl + band * i + (band - bw) / 2
        y = pt + plot_h - bh
        # 4px rounded data-end, anchored to the baseline
        parts.append(
            f'<path d="M{x:.1f},{pt + plot_h:.1f} L{x:.1f},{y + 4:.1f} '
            f'Q{x:.1f},{y:.1f} {x + 4:.1f},{y:.1f} L{x + bw - 4:.1f},{y:.1f} '
            f'Q{x + bw:.1f},{y:.1f} {x + bw:.1f},{y + 4:.1f} '
            f'L{x + bw:.1f},{pt + plot_h:.1f} Z" fill="{colour}" opacity="0.85">'
            f"<title>Round {i} — {v:.2f}s average</title></path>"
        )
        parts.append(
            f'<text x="{x + bw / 2:.1f}" y="{pt + plot_h + 18:.1f}" '
            f'text-anchor="middle" class="tick">R{i}</text>'
        )
        parts.append(
            f'<text x="{x + bw / 2:.1f}" y="{y - 5:.1f}" text-anchor="middle" '
            f'class="pt">{v:.1f}s</text>'
        )

    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Average latency per '
        f'task by round, in seconds.">{"".join(parts)}</svg>'
    )


def failure_chips(failure_modes: dict) -> str:
    if not failure_modes:
        return '<span class="chip none">none</span>'
    items = sorted(failure_modes.items(), key=lambda kv: -kv[1])
    return "".join(
        f'<span class="chip">{esc(k)} <b>{v}</b></span>' for k, v in items
    )


def multi_curve_chart(runs: list[dict], idx: int) -> str:
    """All repeats of one domain on shared axes, so the spread is visible rather
    than hidden behind an average."""
    curves = [curve_of(r) for r in runs]
    if not curves:
        return ""
    n = max(len(c) for c in curves)
    flat = [v for c in curves for v in c]
    lo = max(0.0, min(flat) - 0.10)
    hi = min(1.0, max(flat) + 0.06)
    if hi - lo < 0.2:
        hi = min(1.0, lo + 0.2)

    plot_w, plot_h = W - PAD_L - PAD_R, H - PAD_T - PAD_B

    def px(i): return PAD_L + (plot_w * i / max(n - 1, 1))
    def py(v): return PAD_T + plot_h * (1 - (v - lo) / (hi - lo))

    parts = []
    for t in range(5):
        v = lo + (hi - lo) * t / 4
        y = py(v)
        parts.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W-PAD_R}" y2="{y:.1f}" '
                     f'stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{PAD_L-10}" y="{y+4:.1f}" text-anchor="end" '
                     f'class="tick">{v:.2f}</text>')
    for i in range(n):
        parts.append(f'<text x="{px(i):.1f}" y="{H-PAD_B+20}" text-anchor="middle" '
                     f'class="tick">R{i}</text>')

    colour = f"var(--series-{idx+1})"
    for ci, curve in enumerate(curves):
        pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(curve))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{colour}" '
                     f'stroke-width="2" stroke-linejoin="round" opacity="0.72"/>')
        for i, v in enumerate(curve):
            kept = runs[ci]["rounds"][i].get("kept", True)
            cx, cy = px(i), py(v)
            if kept:
                parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4.5" '
                             f'fill="{colour}" stroke="var(--surface)" stroke-width="2"/>')
            else:
                parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" '
                             f'fill="var(--surface)" stroke="{colour}" stroke-width="2" '
                             f'stroke-dasharray="2.5 2"/>')
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="13" fill="transparent">'
                         f'<title>repeat {ci+1}, round {i} — {v:.3f}'
                         f'{"" if kept else " (rolled back)"}</title></circle>')

    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Accuracy by round '
            f'for {len(curves)} repeat runs on shared axes.">{"".join(parts)}</svg>')


def domain_section(group: dict, idx: int) -> str:
    name = group["domain"]
    runs = group["runs"]
    curves = [curve_of(r) for r in runs]
    starts = [c[0] for c in curves]
    bests = [max(c) for c in curves]
    gains = [max(c) - c[0] for c in curves]
    mean = lambda xs: sum(xs) / len(xs)

    # The detail table shows the run with the largest headroom — the one where
    # the loop had something to actually do.
    detail_i = max(range(len(runs)), key=lambda i: gains[i])
    run = runs[detail_i]
    rounds = run["rounds"]
    rollbacks = sum(1 for r in rounds if not r.get("kept", True))

    rows = []
    for i, r in enumerate(rounds):
        m = r["metrics"]
        kept = r.get("kept", True)
        rows.append(
            f"<tr class=\"{'' if kept else 'rolled'}\">"
            f'<td class="num">{i}</td>'
            f'<td class="num">v{r.get("spec_version", "-")}</td>'
            f'<td><code>{esc(r.get("orchestration", "-"))}</code></td>'
            f'<td class="num">{m.get("accuracy", 0):.3f}</td>'
            f'<td class="num">{m.get("reliability", 0):.2f}</td>'
            f'<td class="num">{m.get("avg_latency_s", 0):.2f}s</td>'
            f'<td class="chips">{failure_chips(r.get("failure_modes", {}))}</td>'
            f'<td class="why">{esc(r.get("change_summary", ""))}'
            f'{"" if kept else " <em>— rolled back</em>"}</td>'
            "</tr>"
        )

    return f"""
    <section class="domain">
      <h2>{esc(name)}</h2>

      <div class="tiles">
        <div class="tile"><span class="label">Round 0 mean</span>
          <span class="value">{mean(starts):.3f}</span>
          <span class="range">{min(starts):.3f}–{max(starts):.3f}</span></div>
        <div class="tile accent"><span class="label">Best mean</span>
          <span class="value">{mean(bests):.3f}</span>
          <span class="range">{min(bests):.3f}–{max(bests):.3f}</span></div>
        <div class="tile"><span class="label">Gain mean</span>
          <span class="value">{mean(gains):+.3f}</span>
          <span class="range">{min(gains):+.3f}–{max(gains):+.3f}</span></div>
        <div class="tile"><span class="label">Repeats</span>
          <span class="value">{len(runs)}</span></div>
      </div>

      <figure>
        {multi_curve_chart(runs, idx)}
        <figcaption>All {len(runs)} repeat runs on shared axes. Hollow, dashed
        markers are rounds whose change scored worse than the best so far and was
        discarded. The spread between curves is real: this model cannot be pinned
        to a fixed temperature, so round 0 alone varies by
        {max(starts) - min(starts):.3f} across identical runs.</figcaption>
      </figure>

      <h3>Detail — the repeat with the most headroom</h3>

      <figure>
        {latency_chart(rounds, idx)}
        <figcaption>Average latency per task, for the run tabulated below. Shown
        separately rather than on a second axis: accuracy and speed move
        independently and a shared frame would imply a relationship the data does
        not support.</figcaption>
      </figure>

      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Round</th><th>Spec</th><th>Orchestration</th><th>Accuracy</th>
            <th>Reliab.</th><th>Latency</th><th>Failure clusters</th>
            <th>Change the system made, and why</th>
          </tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>
      </div>
      <p class="src">detail run: <code>runs/{esc(run["_file"])}</code>
        &nbsp;·&nbsp; {rollbacks} round(s) rolled back</p>
    </section>
    """


SHAPES = {
    "ticket_routing": "classification",
    "invoice_extraction": "structured extraction",
    "meeting_scheduler": "constraint satisfaction &nbsp;<b>· unseen</b>",
}


def build() -> Path:
    groups = recent_runs_per_domain()
    if not groups:
        sys.exit("No runs found. Run `python -m scripts.run_all` first.")

    sections = "".join(domain_section(g, i) for i, g in enumerate(groups))

    rows = []
    for g in groups:
        curves = [curve_of(r) for r in g["runs"]]
        starts = [c[0] for c in curves]
        bests = [max(c) for c in curves]
        gains = [max(c) - c[0] for c in curves]
        m = lambda xs: sum(xs) / len(xs)
        rows.append(
            f"<tr><td>{esc(g['domain'])}</td>"
            f"<td class='shape'>{SHAPES.get(g['domain'], '—')}</td>"
            f"<td class='num'>{m(starts):.3f}</td>"
            f"<td class='num'>{m(bests):.3f}</td>"
            f"<td class='num'>{m(gains):+.3f}</td>"
            f"<td class='num'>{min(gains):+.3f} – {max(gains):+.3f}</td>"
            f"<td class='num'>{len(g['runs'])}</td></tr>"
        )
    overview = "".join(rows)

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Forge — Results</title>
<style>
  :root {{
    --surface:  #fcfcfb;
    --page:     #f4f4f2;
    --ink:      #0b0b0b;
    --ink-2:    #52514e;
    --ink-3:    #78776f;
    --rule:     #e2e2dd;
    --grid:     #e8e8e3;
    --series-1: {SERIES[0]["light"]};
    --series-2: {SERIES[1]["light"]};
    --font: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --surface: #1a1a19; --page: #121211; --ink: #ffffff;
      --ink-2: #c3c2b7; --ink-3: #8f8e85; --rule: #33332f; --grid: #2b2b28;
      --series-1: {SERIES[0]["dark"]}; --series-2: {SERIES[1]["dark"]};
    }}
  }}
  :root[data-theme="dark"] {{
    --surface: #1a1a19; --page: #121211; --ink: #ffffff;
    --ink-2: #c3c2b7; --ink-3: #8f8e85; --rule: #33332f; --grid: #2b2b28;
    --series-1: {SERIES[0]["dark"]}; --series-2: {SERIES[1]["dark"]};
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background: var(--page); color: var(--ink);
         font-family: var(--font); font-size:15px; line-height:1.6; }}
  .wrap {{ max-width: 1000px; margin:0 auto; padding: 56px 24px 100px; }}
  header {{ margin-bottom: 44px; }}
  h1 {{ font-size: 32px; line-height:1.15; margin:0 0 10px; letter-spacing:-0.02em; }}
  .sub {{ color: var(--ink-2); margin:0; max-width: 62ch; }}
  h2 {{ font-size: 22px; margin: 0 0 20px; letter-spacing:-0.01em; }}
  section.domain {{ background: var(--surface); border:1px solid var(--rule);
                    border-radius:10px; padding:26px; margin-bottom:30px; }}
  .tiles {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:24px; }}
  .tile {{ background: var(--page); border:1px solid var(--rule);
           border-radius:8px; padding:11px 15px; min-width:104px; }}
  .tile .label {{ display:block; font-size:10.5px; letter-spacing:0.09em;
                  text-transform:uppercase; color: var(--ink-3); }}
  .tile .value {{ display:block; font-family: var(--mono); font-size:21px;
                  font-variant-numeric: tabular-nums; margin-top:3px; }}
  .tile.accent .value {{ color: var(--series-1); }}
  .tile .range {{ display:block; font-family: var(--mono); font-size:10.5px;
                  color: var(--ink-3); font-variant-numeric: tabular-nums; }}
  td.shape {{ font-size:12.5px; }}
  h3 {{ font-size:15px; margin:26px 0 14px; color: var(--ink-2);
        letter-spacing:-0.005em; }}
  figure {{ margin: 0 0 26px; }}
  svg {{ display:block; width:100%; height:auto; overflow:visible; }}
  figcaption {{ font-size:13px; color: var(--ink-3); margin-top:8px; max-width:66ch; }}
  .tick {{ font-family: var(--mono); font-size:10.5px; fill: var(--ink-3); }}
  .pt   {{ font-family: var(--mono); font-size:11px; fill: var(--ink-2); }}
  .table-wrap {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; min-width:1180px; }}
  th {{ text-align:left; font-size:10.5px; letter-spacing:0.08em;
        text-transform:uppercase; color: var(--ink-3); font-weight:600;
        padding:0 12px 9px 0; border-bottom:1px solid var(--ink); }}
  td {{ padding:11px 12px 11px 0; border-bottom:1px solid var(--rule);
        vertical-align:top; color: var(--ink-2); }}
  td.num {{ font-family: var(--mono); font-variant-numeric: tabular-nums;
            color: var(--ink); white-space:nowrap; }}
  tr.rolled td {{ opacity:0.62; }}
  .why {{ min-width:260px; }}
  .why em {{ color: var(--ink-3); }}
  .chips {{ min-width:330px; }}
  .chip {{ display:inline-block; font-family: var(--mono); font-size:10.5px;
           background: var(--page); border:1px solid var(--rule);
           border-radius:4px; padding:2px 6px; margin:0 4px 4px 0;
           white-space:nowrap; }}
  .chip.none {{ color: var(--ink-3); }}
  code {{ font-family: var(--mono); font-size:0.88em; }}
  .src {{ font-size:11.5px; color: var(--ink-3); margin:14px 0 0; }}
  .overview {{ background: var(--surface); border:1px solid var(--rule);
               border-radius:10px; padding:26px; margin-bottom:30px; }}
  .overview table {{ min-width:0; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Agent Forge — results</h1>
    <p class="sub">A system that designs an agent from a goal and a tool list,
    runs it, clusters its failures into named modes, and rewrites the agent to
    target the largest cluster. Every number below was produced by the loop
    running unattended; rounds that scored worse than the best so far were
    discarded rather than carried forward. Numbers are means over 3 repeat runs with the full range shown, because this model cannot be pinned to a fixed temperature and a single curve is a sample, not a measurement.</p>
  </header>

  <div class="overview">
    <h2>Overview</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Domain</th><th>Shape</th><th>Round 0 mean</th><th>Best mean</th><th>Gain mean</th><th>Gain range</th><th>Repeats</th></tr></thead>
        <tbody>{overview}</tbody>
      </table>
    </div>
  </div>

  {sections}
</div>
</body>
</html>
"""

    REPORT_DIR.mkdir(exist_ok=True)
    out = REPORT_DIR / "index.html"
    out.write_text(doc)
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path}")
