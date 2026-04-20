#!/usr/bin/env python3
"""Live validation harness: parse 16 RSS feeds and diff against ground-truth manifests.

Run from scripts/paragraphos:
    PYTHONPATH=. ../../.venv/bin/python tests/validate_feeds.py

Phases:
    1. Manifest generation — parse all 16 feeds.
    2. Ground-truth diff — compare against raw/transcripts/<slug>/episodes.json.
    3. Transcript cross-check — for one-a-lage + immocation, verify each .md
       has a matching manifest entry (and vice versa).

Tolerated difference: new episodes that appeared AFTER the reference was
recorded — feeds are live.
Flagged: missing episodes, null mp3_url, broken pub_date, wrong episode_number.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent.parent  # scripts/paragraphos/
sys.path.insert(0, str(HERE))

REPO_ROOT = HERE.parent.parent
TRANSCRIPTS_ROOT = REPO_ROOT / "raw" / "transcripts"

from core.rss import build_manifest  # noqa: E402

# Feed list (copied from raw/transcripts/podcast_downloader.py to avoid importing it,
# since that file sits under raw/ and has side-effect imports).
FEEDS: List[Tuple[str, str]] = [
    ("one-a-lage",             "https://1alage.podigee.io/feed/mp3"),
    ("immocation",             "https://immocation.podigee.io/feed/mp3"),
    ("limmo",                  "https://haufe-immobilienpodcast.podigee.io/feed/mp3"),
    ("hausverwalter-inside",   "https://divmpodcast.libsyn.com/rss"),
    ("immobileros",            "https://immobileros.podigee.io/feed/mp3"),
    ("real-estate-pioneers",   "https://feeds.buzzsprout.com/1997738.rss"),
    ("dmrex",                  "https://feeds.buzzsprout.com/2078041.rss"),
    ("grundgedanken",          "https://gvh.podcaster.de/grundeigentuemerverband.rss"),
    ("faz-finanzen-immobilien","https://fazfinanzen.podigee.io/feed/mp3"),
    ("lagebericht",            "https://feeds.acast.com/public/shows/61e97e498ad1d30012c50117"),
    ("immopreneur",            "https://anchor.fm/s/10204d0b4/podcast/rss"),
    ("denkmalimmobilien",      "https://denkmalimmobilien-marcelkeller.podigee.io/feed/mp3"),
    ("beyond-buildings",       "https://letscast.fm/podcasts/beyond-buildings-der-podcast-fuer-die-immobilienwelt-im-wandel-0bcfcb5f/feed"),
    ("immokaiser",             "https://immokaiser.podigee.io/feed/mp3"),
    ("vermieter-probleme",     "https://16qkrph.podcaster.de/Vermietershop-de.rss"),
    ("gluecklich-wohnen",      "https://buwog.podigee.io/feed/mp3"),
]


@dataclass
class FeedResult:
    slug: str
    ok: bool
    parsed_count: int = 0
    reference_count: int = 0
    missing_in_parsed: List[str] = field(default_factory=list)  # in ref, not parsed
    new_in_parsed: List[str] = field(default_factory=list)      # in parsed, not ref
    null_mp3: int = 0
    missing_pubdate: int = 0
    wrong_ep_num_format: int = 0
    duplicate_guids: int = 0
    errors: List[str] = field(default_factory=list)


def load_reference(slug: str) -> List[Dict]:
    p = TRANSCRIPTS_ROOT / slug / "episodes.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def validate_feed(slug: str, url: str) -> FeedResult:
    r = FeedResult(slug=slug, ok=False)
    try:
        parsed = build_manifest(url, timeout=60.0)
    except Exception as e:
        r.errors.append(f"parse error: {e}")
        return r
    r.parsed_count = len(parsed)
    reference = load_reference(slug)
    r.reference_count = len(reference)

    for ep in parsed:
        if not ep.get("mp3_url"):
            r.null_mp3 += 1
        if not ep.get("pubDate"):
            r.missing_pubdate += 1
        en = ep.get("episode_number", "")
        # Format spec: decimal digits, zero-padded to at least 4 chars.
        # Real feeds report 5-digit numbers too (e.g. immocation 10003+),
        # and the reference manifest preserves them verbatim.
        if not (isinstance(en, str) and en.isdigit() and len(en) >= 4):
            r.wrong_ep_num_format += 1

    # Duplicate GUIDs
    guids = [e["guid"] for e in parsed]
    r.duplicate_guids = len(guids) - len(set(guids))

    # Diff GUIDs against reference
    ref_guids = {e["guid"] for e in reference}
    parsed_guids = set(guids)
    r.missing_in_parsed = sorted(list(ref_guids - parsed_guids))
    r.new_in_parsed = sorted(list(parsed_guids - ref_guids))

    # Accept: new-in-parsed is OK (feed is live); missing-in-parsed is not.
    # Numeric tolerance: ±5% of reference count
    tolerance_ok = True
    if r.reference_count > 0:
        delta_pct = abs(r.parsed_count - r.reference_count) / r.reference_count
        if r.parsed_count < r.reference_count:
            # Missing episodes: any miss is a problem
            tolerance_ok = len(r.missing_in_parsed) == 0
        else:
            tolerance_ok = delta_pct <= 0.5  # generous upper bound; truly new episodes

    r.ok = (
        r.parsed_count > 0
        and r.null_mp3 == 0
        and r.missing_pubdate == 0
        and r.wrong_ep_num_format == 0
        and r.duplicate_guids == 0
        and not r.missing_in_parsed
        and not r.errors
        and tolerance_ok
    )
    return r


def format_result(r: FeedResult) -> str:
    badge = "✅" if r.ok else "❌"
    line = (f"{badge} {r.slug:25s} parsed={r.parsed_count:4d}  "
            f"ref={r.reference_count:4d}  "
            f"Δnew={len(r.new_in_parsed):3d}  Δmiss={len(r.missing_in_parsed):3d}")
    flags = []
    if r.null_mp3: flags.append(f"null_mp3={r.null_mp3}")
    if r.missing_pubdate: flags.append(f"missing_pubdate={r.missing_pubdate}")
    if r.wrong_ep_num_format: flags.append(f"wrong_ep_num={r.wrong_ep_num_format}")
    if r.duplicate_guids: flags.append(f"dup_guids={r.duplicate_guids}")
    if r.errors: flags.append(f"errors={r.errors}")
    if flags:
        line += "  [" + ", ".join(flags) + "]"
    return line


def phase1_and_2() -> List[FeedResult]:
    print("=" * 80)
    print("Phase 1 & 2 — parse feeds, diff against ground truth")
    print("=" * 80)
    results = []
    for slug, url in FEEDS:
        r = validate_feed(slug, url)
        results.append(r)
        print(format_result(r))
    return results


def phase3_transcript_crosscheck(results: List[FeedResult]) -> None:
    print()
    print("=" * 80)
    print("Phase 3 — transcript ↔ manifest cross-check (one-a-lage, immocation)")
    print("=" * 80)
    by_slug = {r.slug: r for r in results}

    for slug in ("one-a-lage", "immocation"):
        show_dir = TRANSCRIPTS_ROOT / slug
        md_files = [p for p in show_dir.glob("*.md") if p.name != "index.md"]
        reference = load_reference(slug)
        # Reference filename key is YYYY-MM-DD_<ep-num>_<sanitized-title>
        # For cross-check we match by GUID (robust) — parse each .md frontmatter.
        md_guids: Dict[str, Path] = {}
        for md in md_files:
            text = md.read_text(encoding="utf-8", errors="ignore")
            # Quick frontmatter scan (not full YAML parse)
            if text.startswith("---"):
                end = text.find("\n---", 3)
                fm = text[3:end] if end != -1 else ""
                for line in fm.splitlines():
                    if line.strip().startswith("guid:"):
                        g = line.split(":", 1)[1].strip().strip('"').strip("'")
                        md_guids[g] = md
                        break
        ref_guids = {e["guid"] for e in reference}
        parsed_result = by_slug.get(slug)
        parsed_guids = set()
        if parsed_result:
            # recompute parsed guids from a fresh parse for this slug
            try:
                parsed = build_manifest(next(u for s, u in FEEDS if s == slug), timeout=60)
                parsed_guids = {e["guid"] for e in parsed}
            except Exception:
                pass

        # Orphans: .md whose GUID is not in the (parsed or ref) manifest
        all_known = ref_guids | parsed_guids
        orphans = [p for g, p in md_guids.items() if g not in all_known]
        # Gaps: ref GUIDs with no .md
        gaps = [g for g in ref_guids if g not in md_guids]

        print(f"\n  {slug}: .md files with GUID frontmatter = {len(md_guids)}, "
              f"ref = {len(ref_guids)}")
        print(f"    orphans (md without manifest entry): {len(orphans)}")
        if orphans[:5]:
            for p in orphans[:5]:
                print(f"      - {p.name}")
        print(f"    gaps (manifest entry without .md): {len(gaps)}")
        if gaps[:5]:
            for g in gaps[:5]:
                print(f"      - guid={g}")


def main() -> int:
    results = phase1_and_2()
    phase3_transcript_crosscheck(results)

    print()
    ok_count = sum(1 for r in results if r.ok)
    print(f"Summary: {ok_count}/{len(results)} feeds passed all criteria.")
    if ok_count < len(results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
