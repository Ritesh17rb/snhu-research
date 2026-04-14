#!/usr/bin/env python3
"""Fetch SNHU research papers from OpenAlex and produce an embedumap-ready CSV.

By default, also fetches broader OpenAlex papers from the same fields to
create a "SNHU vs full universe" comparison dataset.
"""

from __future__ import annotations

import argparse
import csv
import time
from collections import Counter
from pathlib import Path

import httpx

OPENALEX_API = "https://api.openalex.org/works"
SNHU_INSTITUTION_ID = "I33308869"
MAILTO = "ritesh@example.com"

FIELDNAMES = [
    "openalex_id", "doi", "title", "abstract", "year", "type",
    "cited_by_count", "domain", "field", "subfield", "topic",
    "keywords", "authors", "oa_status", "source", "is_snhu",
]


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


def build_row(work: dict) -> tuple[dict[str, str], str | None] | None:
    """Extract a CSV row and the OpenAlex field ID (if any) from a work."""
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
    field_obj = primary_topic.get("field") or {}
    field = field_obj.get("display_name", "")
    field_id = field_obj.get("id")
    domain = (primary_topic.get("domain") or {}).get("display_name", "")

    keywords_list = work.get("keywords") or []
    keywords = "|".join(k.get("display_name", "") for k in keywords_list[:10] if k.get("display_name"))

    authorships = work.get("authorships") or []
    oa = work.get("open_access") or {}

    row = {
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
        "is_snhu": "",
    }
    return row, field_id


def fetch_works(filter_str: str, per_page: int = 200, max_rows: int | None = None) -> list[tuple[dict[str, str], str | None]]:
    """Fetch works from OpenAlex matching filter_str. Returns (row, field_id) pairs."""
    results_list: list[tuple[dict[str, str], str | None]] = []
    cursor = "*"
    page = 0

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        while cursor:
            page += 1
            params = {
                "filter": filter_str,
                "per_page": per_page,
                "cursor": cursor,
                "mailto": MAILTO,
            }
            print(f"  Page {page} (cursor={cursor[:20]}...) — {len(results_list)} rows so far")
            resp = client.get(OPENALEX_API, params=params)
            resp.raise_for_status()
            data = resp.json()

            works = data.get("results", [])
            if not works:
                break

            for work in works:
                result = build_row(work)
                if result:
                    results_list.append(result)
                    if max_rows and len(results_list) >= max_rows:
                        return results_list

            cursor = data.get("meta", {}).get("next_cursor")
            time.sleep(0.2)

    return results_list


def top_field_ids(results: list[tuple[dict[str, str], str | None]], n: int = 5) -> list[str]:
    """Return the top N OpenAlex field IDs by paper count."""
    field_counts: Counter[str] = Counter()
    for _row, field_id in results:
        if field_id:
            field_counts[field_id] += 1
    return [fid for fid, _count in field_counts.most_common(n)]


def write_csv(rows: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("SNHU/snhu-research.csv"))
    parser.add_argument("--no-universe", action="store_true", help="Skip fetching broader universe papers.")
    parser.add_argument("--universe-per-field", type=int, default=500, help="Max broader papers per field.")
    parser.add_argument("--top-fields", type=int, default=5, help="Number of top fields to fetch universe for.")
    args = parser.parse_args()

    print("Fetching SNHU works from OpenAlex...")
    snhu_results = fetch_works(f"authorships.institutions.id:{SNHU_INSTITUTION_ID}")
    snhu_ids = set()
    snhu_rows: list[dict[str, str]] = []
    for row, _fid in snhu_results:
        row["is_snhu"] = "SNHU"
        snhu_rows.append(row)
        snhu_ids.add(row["openalex_id"])
    print(f"  Got {len(snhu_rows)} SNHU papers")

    fields = Counter(r["field"] for r in snhu_rows if r["field"])
    print("\nTop SNHU fields:")
    for f, c in fields.most_common(10):
        print(f"  {f}: {c}")

    all_rows = list(snhu_rows)

    if not args.no_universe:
        field_ids = top_field_ids(snhu_results, n=args.top_fields)
        print(f"\nFetching universe papers for {len(field_ids)} fields...")
        for fid in field_ids:
            short_id = fid.split("/")[-1] if "/" in fid else fid
            filter_str = f"primary_topic.field.id:{short_id},publication_year:>1999"
            print(f"\n  Field {short_id}:")
            universe_results = fetch_works(filter_str, max_rows=args.universe_per_field)
            added = 0
            for row, _field_id in universe_results:
                if row["openalex_id"] not in snhu_ids:
                    row["is_snhu"] = "Other"
                    all_rows.append(row)
                    snhu_ids.add(row["openalex_id"])
                    added += 1
            print(f"  Added {added} universe papers for field {short_id}")

    all_rows.sort(key=lambda r: (-int(r["year"]), r["title"]))
    write_csv(all_rows, args.output)

    snhu_count = sum(1 for r in all_rows if r["is_snhu"] == "SNHU")
    other_count = sum(1 for r in all_rows if r["is_snhu"] == "Other")
    print(f"\nWrote {len(all_rows)} rows to {args.output} ({snhu_count} SNHU, {other_count} Other)")


if __name__ == "__main__":
    main()
