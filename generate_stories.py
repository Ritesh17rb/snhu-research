#!/usr/bin/env python3
"""Generate evolution.html and strategy.html narratives for SNHU research using Gemini."""

from __future__ import annotations

import argparse
import csv
import os
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


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def compute_stats(rows: list[dict[str, str]]) -> str:
    years = defaultdict(int)
    fields = defaultdict(int)
    subfields = defaultdict(int)
    topics = defaultdict(int)
    total_citations = 0
    authors_set = set()

    for r in rows:
        years[r["year"]] += 1
        if r["field"]:
            fields[r["field"]] += 1
        if r["subfield"]:
            subfields[r["subfield"]] += 1
        if r["topic"]:
            topics[r["topic"]] += 1
        total_citations += int(r["cited_by_count"] or 0)
        for a in r["authors"].split("|"):
            if a.strip():
                authors_set.add(a.strip())

    field_by_year = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if r["field"] and r["year"]:
            field_by_year[r["year"]][r["field"]] += 1

    lines = [
        f"Total papers: {len(rows)}",
        f"Year range: {min(years)}-{max(years)}",
        f"Total citations: {total_citations}",
        f"Unique authors: {len(authors_set)}",
        "",
        "Papers per year:",
    ]
    for y in sorted(years):
        lines.append(f"  {y}: {years[y]}")

    lines.append("\nTop fields (all time):")
    for f, c in sorted(fields.items(), key=lambda x: -x[1])[:15]:
        lines.append(f"  {f}: {c}")

    lines.append("\nTop subfields:")
    for s, c in sorted(subfields.items(), key=lambda x: -x[1])[:20]:
        lines.append(f"  {s}: {c}")

    lines.append("\nTop topics:")
    for t, c in sorted(topics.items(), key=lambda x: -x[1])[:20]:
        lines.append(f"  {t}: {c}")

    lines.append("\nField distribution by year:")
    for y in sorted(field_by_year):
        top = sorted(field_by_year[y].items(), key=lambda x: -x[1])[:5]
        lines.append(f"  {y}: " + ", ".join(f"{f}({c})" for f, c in top))

    top_cited = sorted(rows, key=lambda r: -int(r["cited_by_count"] or 0))[:20]
    lines.append("\nTop 20 most-cited papers:")
    for r in top_cited:
        lines.append(f"  [{r['cited_by_count']} cites] {r['title'][:100]} ({r['year']}, {r['field']})")

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


def generate_evolution(rows: list[dict[str, str]], output: Path) -> None:
    stats = compute_stats(rows)
    prompt = f"""You are writing a "Field Evolution" analysis for Southern New Hampshire University's (SNHU) research output. This will be displayed as an HTML narrative page.

Here is the complete statistical summary of SNHU's research corpus from OpenAlex:

{stats}

Write a compelling, data-driven narrative in HTML (just the body content, no full page wrapper) that tracks how SNHU's research fields have shifted over time. Structure it as:

1. Key metrics section using this HTML pattern for stat cards:
<div class="stat-grid">
  <div class="stat-card"><div class="number">N</div><div class="label">Label</div></div>
</div>

2. Several "Acts" or sections (use <h2> tags) that tell the story of SNHU's research evolution:
   - How the research portfolio has grown and shifted
   - Which fields emerged, grew, or declined
   - Notable shifts in research focus over the decades
   - The most impactful papers and their role in shaping the institution's direction

3. Use actual numbers and paper titles from the data. Be specific.
4. Use <h2> for main sections, <h3> for subsections, <p> for text, <ul>/<li> for lists.
5. You can use <table> for comparison data.
6. Keep it engaging — written like a research journalism piece, not a dry report.
7. About 1500-2000 words of content."""

    print("Generating evolution narrative...")
    content = generate_with_gemini(prompt)
    content = content.strip()
    if content.startswith("```html"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]

    html = HTML_TEMPLATE.format(
        title="Field Evolution",
        subtitle="How SNHU's research landscape has shifted over time — a data-driven narrative",
        content=content.strip(),
    )
    output.write_text(html, encoding="utf-8")
    print(f"Wrote {output}")


def generate_strategy(rows: list[dict[str, str]], output: Path) -> None:
    stats = compute_stats(rows)
    prompt = f"""You are writing a "Research Strategy" analysis for Southern New Hampshire University (SNHU). This will be displayed as an HTML narrative page.

Here is the complete statistical summary of SNHU's research corpus from OpenAlex:

{stats}

Write a strategic, data-driven analysis in HTML (just the body content, no full page wrapper) that recommends where SNHU should focus its research efforts. Structure it as:

1. Key metrics section using this HTML pattern:
<div class="stat-grid">
  <div class="stat-card"><div class="number">N</div><div class="label">Label</div></div>
</div>

2. Several "Acts" or strategic sections (use <h2> tags):
   - Act I: Priority Bets — rank the top research directions SNHU should invest in, using growth rates, citation impact, and existing strengths
   - Act II: Internal Collaboration — identify cross-department research partnerships that could be productive
   - Act III: White Space Analysis — emerging areas where SNHU has little presence but high potential
   - Act IV: Quality & Impact — recommendations for increasing citation impact and research quality
   - Act V: Five-Point Playbook — distill everything into 5 actionable priorities

3. Use actual numbers, field names, and trends from the data. Be specific.
4. Use <h2> for main sections, <h3> for subsections, <p> for text, <ul>/<li> for lists, <table> where appropriate.
5. Written in a strategic advisory tone — practical recommendations backed by data.
6. About 1500-2000 words of content."""

    print("Generating strategy narrative...")
    content = generate_with_gemini(prompt)
    content = content.strip()
    if content.startswith("```html"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]

    html = HTML_TEMPLATE.format(
        title="Strategy Story",
        subtitle="Data-driven insights on where SNHU should focus next",
        content=content.strip(),
    )
    output.write_text(html, encoding="utf-8")
    print(f"Wrote {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("SNHU/snhu-research.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("SNHU"))
    args = parser.parse_args()

    rows = load_csv(args.csv)
    print(f"Loaded {len(rows)} rows from {args.csv}")

    generate_evolution(rows, args.output_dir / "evolution.html")
    generate_strategy(rows, args.output_dir / "strategy.html")
    print("Done!")


if __name__ == "__main__":
    main()
