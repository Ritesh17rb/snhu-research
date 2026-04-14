#!/usr/bin/env python3
"""Fetch SNHU research papers from OpenAlex and produce an embedumap-ready CSV."""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import httpx

OPENALEX_API = "https://api.openalex.org/works"
SNHU_INSTITUTION_ID = "I33308869"
MAILTO = "ritesh@example.com"


def invert_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    if not inverted_index:
        return ""
    length = max(pos for positions in inverted_index.values() for pos in positions) + 1
    words = [""] * length
    for word, positions in inverted_index.items():
        for pos in positions:
            if pos < length:
                words[pos] = word
    return " ".join(words)


def extract_authors(authorships: list[dict]) -> str:
    names = []
    for a in authorships:
        author = a.get("author", {})
        name = author.get("display_name", "")
        if name:
            names.append(name)
    return "|".join(names)


def extract_source(locations: list[dict]) -> str:
    for loc in locations:
        source = loc.get("source")
        if source and source.get("display_name"):
            return source["display_name"]
    return ""


def build_row(work: dict) -> dict[str, str] | None:
    abstract = invert_abstract(work.get("abstract_inverted_index"))
    if not abstract or len(abstract) < 100:
        return None

    year = work.get("publication_year")
    if not year or year < 2000:
        return None

    title = work.get("title") or ""
    if not title:
        return None

    primary_topic = work.get("primary_topic") or {}
    topic_name = primary_topic.get("display_name", "")
    subfield = (primary_topic.get("subfield") or {}).get("display_name", "")
    field = (primary_topic.get("field") or {}).get("display_name", "")
    domain = (primary_topic.get("domain") or {}).get("display_name", "")

    keywords_list = work.get("keywords") or []
    keywords = "|".join(k.get("display_name", "") for k in keywords_list[:10] if k.get("display_name"))

    authorships = work.get("authorships") or []
    oa = work.get("open_access") or {}

    return {
        "openalex_id": work.get("id", ""),
        "doi": work.get("doi") or "",
        "title": title,
        "abstract": abstract,
        "year": str(year),
        "type": work.get("type", ""),
        "cited_by_count": str(work.get("cited_by_count", 0)),
        "domain": domain,
        "field": field,
        "subfield": subfield,
        "topic": topic_name,
        "keywords": keywords,
        "authors": extract_authors(authorships),
        "oa_status": oa.get("oa_status", ""),
        "source": extract_source(work.get("locations") or []),
    }


def fetch_all_works(per_page: int = 200) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    cursor = "*"
    page = 0

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        while cursor:
            page += 1
            params = {
                "filter": f"authorships.institutions.id:{SNHU_INSTITUTION_ID}",
                "per_page": per_page,
                "cursor": cursor,
                "mailto": MAILTO,
            }
            print(f"  Page {page} (cursor={cursor[:20]}...) — {len(rows)} rows so far")
            resp = client.get(OPENALEX_API, params=params)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if not results:
                break

            for work in results:
                row = build_row(work)
                if row:
                    rows.append(row)

            cursor = data.get("meta", {}).get("next_cursor")
            time.sleep(0.2)

    return rows


def write_csv(rows: list[dict[str, str]], output: Path) -> None:
    fieldnames = [
        "openalex_id", "doi", "title", "abstract", "year", "type",
        "cited_by_count", "domain", "field", "subfield", "topic",
        "keywords", "authors", "oa_status", "source",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("SNHU/snhu-research.csv"))
    args = parser.parse_args()

    print("Fetching SNHU works from OpenAlex...")
    rows = fetch_all_works()
    rows.sort(key=lambda r: (-int(r["year"]), r["title"]))
    write_csv(rows, args.output)
    print(f"Wrote {len(rows)} rows to {args.output}")

    fields = {}
    for r in rows:
        f = r["field"] or "Unknown"
        fields[f] = fields.get(f, 0) + 1
    print("\nTop fields:")
    for f, c in sorted(fields.items(), key=lambda x: -x[1])[:15]:
        print(f"  {f}: {c}")


if __name__ == "__main__":
    main()
