#!/usr/bin/env python3
"""Generate map-aware evolution.html and strategy.html narratives for SNHU research.

Reads the embedded JSON payload from map.html to get UMAP coordinates, cluster
assignments, and field labels, then computes spatial statistics and feeds them
to Gemini for rich, NIE-style narratives.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)

GEMINI_MODEL = "gemini-2.5-flash"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — SNHU Research</title>
<style>
  :root {{
    --bg: #0b1220;
    --surface: rgba(30, 41, 59, 0.8);
    --text: #e2e8f0;
    --muted: #94a3b8;
    --accent: #60a5fa;
    --accent2: #a78bfa;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.7;
    min-height: 100vh;
  }}
  .container {{
    max-width: 820px;
    margin: 0 auto;
    padding: 3rem 1.5rem;
  }}
  h1 {{
    font-size: 2.2rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }}
  .subtitle {{
    color: var(--muted);
    font-size: 1rem;
    margin-bottom: 2.5rem;
  }}
  h2 {{
    font-size: 1.4rem;
    font-weight: 600;
    color: var(--accent);
    margin-top: 2.5rem;
    margin-bottom: 1rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid rgba(96, 165, 250, 0.2);
  }}
  h3 {{
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--text);
    margin-top: 1.8rem;
    margin-bottom: 0.6rem;
  }}
  p {{
    margin-bottom: 1rem;
    color: var(--text);
  }}
  ul, ol {{
    margin-bottom: 1rem;
    padding-left: 1.5rem;
  }}
  li {{
    margin-bottom: 0.5rem;
    color: var(--text);
  }}
  strong {{ color: #f1f5f9; }}
  em {{ color: var(--muted); }}
  blockquote {{
    border-left: 3px solid var(--accent);
    padding: 0.8rem 1.2rem;
    margin: 1.5rem 0;
    background: var(--surface);
    border-radius: 0 8px 8px 0;
    font-style: italic;
    color: var(--muted);
  }}
  .stat-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 1rem;
    margin: 1.5rem 0;
  }}
  .stat-card {{
    background: var(--surface);
    border: 1px solid rgba(96, 165, 250, 0.15);
    border-radius: 12px;
    padding: 1.2rem;
    text-align: center;
    backdrop-filter: blur(10px);
  }}
  .stat-card .number {{
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--accent);
  }}
  .stat-card .label {{
    font-size: 0.85rem;
    color: var(--muted);
    margin-top: 0.3rem;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
  }}
  th, td {{
    padding: 0.6rem 0.8rem;
    text-align: left;
    border-bottom: 1px solid rgba(96, 165, 250, 0.1);
  }}
  th {{
    color: var(--accent);
    font-weight: 600;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  td {{ color: var(--text); font-size: 0.95rem; }}
  .back-link {{
    display: inline-block;
    margin-bottom: 2rem;
    color: var(--accent);
    text-decoration: none;
    font-size: 0.9rem;
  }}
  .back-link:hover {{ text-decoration: underline; }}
  .footer {{
    margin-top: 3rem;
    padding-top: 1.5rem;
    border-top: 1px solid rgba(96, 165, 250, 0.1);
    color: var(--muted);
    font-size: 0.85rem;
    text-align: center;
  }}
</style>
</head>
<body>
<div class="container">
  <a href="index.html" class="back-link">&larr; Back to SNHU Research</a>
  <h1>{title}</h1>
  <p class="subtitle">{subtitle}</p>
  {content}
  <div class="footer">Generated with embedumap &amp; Gemini</div>
</div>
</body>
</html>"""


def load_map_payload(map_path: Path) -> dict:
    html = map_path.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="data-json" type="application/json">(.*?)</script>',
        html, re.DOTALL,
    )
    if not match:
        raise SystemExit(f"Could not find data-json in {map_path}")
    return json.loads(match.group(1))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _centroid(rows: list[dict]) -> tuple[float, float]:
    if not rows:
        return (0.0, 0.0)
    cx = sum(r["x"] for r in rows) / len(rows)
    cy = sum(r["y"] for r in rows) / len(rows)
    return (cx, cy)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def compute_map_stats(payload: dict, csv_rows: list[dict[str, str]]) -> str:
    """Compute spatial statistics from the map payload for story generation."""

    rows = payload["rows"]
    axis_labels = payload.get("axisLabels", {})

    csv_by_id = {}
    for cr in csv_rows:
        csv_by_id[int(cr.get("_row_index", -1)) if "_row_index" in cr else -1] = cr

    snhu_rows = [r for r in rows if r["colors"].get("is_snhu") == "SNHU"]
    other_rows = [r for r in rows if r["colors"].get("is_snhu") == "Other"]

    lines = [
        f"Total papers on map: {len(rows)}",
        f"SNHU papers: {len(snhu_rows)}",
        f"Other (universe) papers: {len(other_rows)}",
        f"X-axis meaning: {axis_labels.get('x', 'unknown')}",
        f"Y-axis meaning: {axis_labels.get('y', 'unknown')}",
    ]

    # Field distribution for SNHU vs Other
    snhu_fields = defaultdict(int)
    other_fields = defaultdict(int)
    for r in snhu_rows:
        f = r["colors"].get("field", "")
        if f:
            snhu_fields[f] += 1
    for r in other_rows:
        f = r["colors"].get("field", "")
        if f:
            other_fields[f] += 1

    all_fields = sorted(set(snhu_fields) | set(other_fields), key=lambda f: -(snhu_fields.get(f, 0) + other_fields.get(f, 0)))

    lines.append("\nField distribution (SNHU vs Other):")
    for f in all_fields[:15]:
        s = snhu_fields.get(f, 0)
        o = other_fields.get(f, 0)
        total = s + o
        snhu_pct = round(100 * s / total, 1) if total else 0
        lines.append(f"  {f}: SNHU={s} ({snhu_pct}%), Other={o}, Total={total}")

    # Gap analysis: where SNHU is most underweight vs universe
    lines.append("\nGap analysis (SNHU underweight vs universe):")
    snhu_total = len(snhu_rows)
    other_total = len(other_rows)
    gaps = []
    for f in all_fields:
        snhu_share = snhu_fields.get(f, 0) / snhu_total if snhu_total else 0
        other_share = other_fields.get(f, 0) / other_total if other_total else 0
        gap = other_share - snhu_share
        gaps.append((f, gap, snhu_share, other_share))
    gaps.sort(key=lambda x: -x[1])
    for f, gap, ss, os in gaps[:10]:
        lines.append(f"  {f}: gap={gap:+.1%}, SNHU share={ss:.1%}, Universe share={os:.1%}")

    # Cluster distribution
    clusters = defaultdict(lambda: {"snhu": 0, "other": 0, "total": 0})
    for r in rows:
        cl = r.get("clusterLabel", f"Cluster {r.get('clusterId', '?')}")
        is_snhu = r["colors"].get("is_snhu") == "SNHU"
        clusters[cl]["snhu" if is_snhu else "other"] += 1
        clusters[cl]["total"] += 1

    lines.append("\nCluster distribution:")
    for cl, counts in sorted(clusters.items(), key=lambda x: -x[1]["total"]):
        s = counts["snhu"]
        o = counts["other"]
        t = counts["total"]
        lines.append(f"  {cl}: SNHU={s}, Other={o}, Total={t}")

    # Field centroids per year (SNHU only)
    field_year_rows = defaultdict(lambda: defaultdict(list))
    for r in snhu_rows:
        f = r["colors"].get("field", "")
        y = r["colors"].get("year", "")
        if f and y:
            field_year_rows[f][y].append(r)

    lines.append("\nSNHU field centroid positions by year (UMAP x, y):")
    top_snhu_fields = sorted(snhu_fields, key=lambda f: -snhu_fields[f])[:8]
    field_movements = {}
    for f in top_snhu_fields:
        years_sorted = sorted(field_year_rows[f].keys())
        if len(years_sorted) < 2:
            continue
        centroids = {}
        for y in years_sorted:
            c = _centroid(field_year_rows[f][y])
            centroids[y] = c
        first_c = centroids[years_sorted[0]]
        last_c = centroids[years_sorted[-1]]
        total_shift = _dist(first_c, last_c)
        field_movements[f] = total_shift
        lines.append(f"  {f} ({years_sorted[0]}-{years_sorted[-1]}): shift={total_shift:.2f} map units")
        for y in years_sorted:
            cx, cy = centroids[y]
            n = len(field_year_rows[f][y])
            lines.append(f"    {y}: ({cx:.2f}, {cy:.2f}) n={n}")

    # Cluster share changes over time for SNHU
    lines.append("\nSNHU cluster share by year (top fields):")
    for f in top_snhu_fields[:5]:
        years_sorted = sorted(field_year_rows[f].keys())
        if len(years_sorted) < 2:
            continue
        lines.append(f"  {f}:")
        for y in [years_sorted[0], years_sorted[-1]]:
            year_rows = field_year_rows[f][y]
            cl_counts = defaultdict(int)
            for r in year_rows:
                cl_counts[r.get("clusterLabel", "?")] += 1
            total = len(year_rows)
            top_cls = sorted(cl_counts.items(), key=lambda x: -x[1])[:3]
            parts = ", ".join(f"{c}={n} ({100*n/total:.0f}%)" for c, n in top_cls)
            lines.append(f"    {y} (n={total}): {parts}")

    # SNHU vs Other centroid distance per cluster (white space proxy)
    lines.append("\nWhite space analysis (clusters where SNHU is thin but universe is present):")
    whitespace = []
    for cl, counts in clusters.items():
        if 0 < counts["snhu"] <= 10 and counts["other"] >= 20:
            cl_snhu = [r for r in snhu_rows if r.get("clusterLabel", "") == cl]
            cl_other = [r for r in other_rows if r.get("clusterLabel", "") == cl]
            snhu_c = _centroid(cl_snhu)
            other_c = _centroid(cl_other)
            dist = _dist(snhu_c, other_c)
            whitespace.append((cl, counts["snhu"], counts["other"], dist))

    whitespace.sort(key=lambda x: x[3])
    for cl, s, o, d in whitespace[:10]:
        lines.append(f"  {cl}: SNHU={s}, Other={o}, proximity={d:.2f}")

    # Top cited papers (from CSV)
    lines.append("\nTop 20 most-cited SNHU papers:")
    snhu_csv = [r for r in csv_rows if r.get("is_snhu") == "SNHU"]
    top_cited = sorted(snhu_csv, key=lambda r: -int(r.get("cited_by_count", 0) or 0))[:20]
    for r in top_cited:
        lines.append(f"  [{r.get('cited_by_count', 0)} cites] {r.get('title', '')[:100]} ({r.get('year', '')}, {r.get('field', '')})")

    # Author analysis for collaboration suggestions
    lines.append("\nTop SNHU authors by paper count:")
    author_counts = defaultdict(lambda: {"count": 0, "fields": set(), "subfields": set()})
    for r in snhu_csv:
        for a in (r.get("authors", "") or "").split("|"):
            a = a.strip()
            if a:
                author_counts[a]["count"] += 1
                if r.get("field"):
                    author_counts[a]["fields"].add(r["field"])
                if r.get("subfield"):
                    author_counts[a]["subfields"].add(r["subfield"])
    top_authors = sorted(author_counts.items(), key=lambda x: -x[1]["count"])[:20]
    for name, info in top_authors:
        fields = ", ".join(sorted(info["fields"]))
        lines.append(f"  {name}: {info['count']} papers, fields: {fields}")

    # Year-over-year SNHU growth
    lines.append("\nSNHU papers per year:")
    year_counts = defaultdict(int)
    for r in snhu_csv:
        y = r.get("year", "")
        if y:
            year_counts[y] += 1
    for y in sorted(year_counts):
        lines.append(f"  {y}: {year_counts[y]}")

    # Field growth rates
    lines.append("\nField growth rates (recent 3 years vs prior 3 years, SNHU):")
    recent_years = sorted(year_counts.keys())[-3:]
    prior_years = sorted(year_counts.keys())[-6:-3]
    for f in top_snhu_fields[:10]:
        recent = sum(1 for r in snhu_csv if r.get("field") == f and r.get("year") in recent_years)
        prior = sum(1 for r in snhu_csv if r.get("field") == f and r.get("year") in prior_years)
        growth = ((recent - prior) / prior * 100) if prior else float("inf")
        lines.append(f"  {f}: recent={recent}, prior={prior}, growth={growth:+.0f}%")

    # Subfield and topic details
    lines.append("\nTop SNHU subfields:")
    subfield_counts = defaultdict(int)
    for r in snhu_csv:
        sf = r.get("subfield", "")
        if sf:
            subfield_counts[sf] += 1
    for sf, c in sorted(subfield_counts.items(), key=lambda x: -x[1])[:20]:
        lines.append(f"  {sf}: {c}")

    lines.append("\nTop SNHU topics:")
    topic_counts = defaultdict(int)
    for r in snhu_csv:
        t = r.get("topic", "")
        if t:
            topic_counts[t] += 1
    for t, c in sorted(topic_counts.items(), key=lambda x: -x[1])[:20]:
        lines.append(f"  {t}: {c}")

    # Citation stats
    total_cites = sum(int(r.get("cited_by_count", 0) or 0) for r in snhu_csv)
    lines.append(f"\nTotal SNHU citations: {total_cites:,}")
    unique_authors = set()
    for r in snhu_csv:
        for a in (r.get("authors", "") or "").split("|"):
            if a.strip():
                unique_authors.add(a.strip())
    lines.append(f"Unique SNHU authors: {len(unique_authors)}")

    return "\n".join(lines)


def generate_with_gemini(prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("Missing GEMINI_API_KEY in .env")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return response.text


def strip_code_fences(content: str) -> str:
    content = content.strip()
    if content.startswith("```html"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def generate_evolution(stats: str, output: Path) -> None:
    prompt = f"""You are writing a "Research Evolution" analysis for Southern New Hampshire University (SNHU).
This will be displayed as an HTML narrative page. You have access to UMAP map data showing how SNHU's
research fields are positioned in semantic embedding space, plus comparison data against a broader
OpenAlex research universe.

Here is the complete spatial and statistical analysis of SNHU's research:

{stats}

Write a compelling, map-aware narrative in HTML (just the body content, no full page wrapper). Follow
the style of the NIE research evolution page — use the UMAP space as a storytelling device. Structure:

1. Opening stat cards using this pattern:
<div class="stat-grid">
  <div class="stat-card"><div class="number">N</div><div class="label">Label</div></div>
</div>
Include: total SNHU papers, year range, biggest mover (field with largest centroid shift), and most visible trend.

2. "What the axes mean" section — explain what movement along the x and y axes means in plain English
using the axis labels provided. Make it clear that these are inferred semantic poles, not official labels.

3. "Who moved farthest" — rank fields by centroid shift distance. Use the actual map-unit numbers.

4. Three "Acts" telling the story of specific field movements:
   - Each act focuses on one or two fields
   - Reference actual centroid positions, cluster share changes, and representative papers
   - Explain what the spatial movement MEANS (e.g., "moving toward X means becoming more computational")
   - Include specific numbers: cluster shares, year-over-year changes, citation counts
   - Contrast early vs recent representative paper titles

5. Use narrative, journalistic tone — like the NIE evolution page. Phrases like "the field walks across
the map" or "quietly replaces the tenants while staying on the same block."

6. End with a caveat section acknowledging limitations (sample size, inferred axes, etc.)

7. Use <h2> for main sections, <h3> for subsections, <p> for text, <ul>/<li> for lists, <table> where helpful.
8. Use <blockquote> for key insights or pull quotes.
9. About 1500-2500 words of content.
10. Be specific with data — use actual numbers, titles, percentages from the stats."""

    print("Generating evolution narrative...")
    content = generate_with_gemini(prompt)
    html = HTML_TEMPLATE.format(
        title="Research Evolution",
        subtitle="How SNHU's research landscape has shifted in embedding space — a map-aware narrative",
        content=strip_code_fences(content),
    )
    output.write_text(html, encoding="utf-8")
    print(f"Wrote {output}")


def generate_strategy(stats: str, output: Path) -> None:
    prompt = f"""You are writing a "Research Strategy" analysis for Southern New Hampshire University (SNHU).
This will be displayed as an HTML narrative page. You have access to UMAP map data showing where SNHU
papers sit relative to a broader OpenAlex universe, plus gap analysis, cluster data, and author information.

Here is the complete spatial and statistical analysis:

{stats}

Write a strategic, map-aware analysis in HTML (just the body content, no full page wrapper). Follow
the style of the NIE strategy story — use the embedding space as the basis for strategic recommendations.

Structure as six acts:

1. Opening stat cards:
<div class="stat-grid">
  <div class="stat-card"><div class="number">N</div><div class="label">Label</div></div>
</div>
Include: OpenAlex papers, SNHU papers, priority bets count, and a key metric.

2. Opening quote/insight — a one-sentence strategic thesis like "Don't chase the emptiest parts of the map.
Own the thin edges that are already touching SNHU."

3. **Act I: The Hinge Points** — 3-4 strategic bets ranked by:
   - How underweight SNHU is (gap analysis)
   - How much that area is growing
   - Citation impact
   Each bet should reference the cluster data, gap percentages, and specific topics/subfields.

4. **Act II: Collaboration Inside SNHU** — identify 2-3 cross-field research partnerships based on
   the author data and field overlaps. Frame as "put these researchers in a room" suggestions.

5. **Act III: The Real White Space** — use the white-space analysis data to identify lightly populated,
   rising areas adjacent to SNHU's current work. Reference proximity scores and paper counts.
   Key insight: "pure emptiness is often noise; the better signal is a thin, recent strip close to where SNHU already sits."

6. **Act IV: Making Quality Compound** — recommendations for research infrastructure, reproducibility,
   and institutional support.

7. **Act V: The Playbook** — distill into 4-5 actionable priorities. Each should be one sentence
   with a concrete action.

Use narrative, strategic advisory tone. Be specific with data — reference actual cluster names, gap
percentages, growth rates, author names, and paper titles from the stats.

Use <h2> for acts, <h3> for subsections, <p> for text, <ul>/<li> for lists, <table> for comparisons,
<blockquote> for key strategic insights.
About 1500-2500 words of content."""

    print("Generating strategy narrative...")
    content = generate_with_gemini(prompt)
    html = HTML_TEMPLATE.format(
        title="Strategy Story",
        subtitle="Where SNHU can matter next — data-driven insights from the research map",
        content=strip_code_fences(content),
    )
    output.write_text(html, encoding="utf-8")
    print(f"Wrote {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("SNHU/snhu-research.csv"))
    parser.add_argument("--map", type=Path, default=Path("SNHU/map.html"))
    parser.add_argument("--output-dir", type=Path, default=Path("SNHU"))
    args = parser.parse_args()

    csv_rows = load_csv(args.csv)
    print(f"Loaded {len(csv_rows)} CSV rows from {args.csv}")

    payload = load_map_payload(args.map)
    print(f"Loaded map payload with {len(payload['rows'])} rows from {args.map}")

    stats = compute_map_stats(payload, csv_rows)
    print(f"Computed stats ({len(stats)} chars)")

    generate_evolution(stats, args.output_dir / "evolution.html")
    generate_strategy(stats, args.output_dir / "strategy.html")
    print("Done!")


if __name__ == "__main__":
    main()
