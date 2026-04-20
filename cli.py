"""Headless CLI — used for dev/testing before UI lands.

Run from scripts/paragraphos:
    PYTHONPATH=. ../../.venv/bin/python cli.py add "<podcast name or URL>"
    PYTHONPATH=. ../../.venv/bin/python cli.py list
    PYTHONPATH=. ../../.venv/bin/python cli.py check [--limit N] [--show SLUG]
    PYTHONPATH=. ../../.venv/bin/python cli.py import-feeds    # bulk-import 16 real-estate feeds
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from core.discovery import find_rss_from_url, search_itunes
from core.library import LibraryIndex
from core.models import Settings, Show, Watchlist
from core.paths import migrate_from_legacy, user_data_dir
from core.pipeline import PipelineContext, process_episode
from core.prompt_gen import suggest_whisper_prompt
from core.rss import build_manifest, feed_metadata
from core.state import EpisodeStatus, StateStore

PKG = Path(__file__).resolve().parent
_legacy = PKG / "data"
migrate_from_legacy(_legacy)
DATA = user_data_dir()


def _settings() -> Settings:
    return Settings.load(DATA / "settings.yaml")


def _watchlist() -> Watchlist:
    return Watchlist.load(DATA / "watchlist.yaml")


def _state() -> StateStore:
    s = StateStore(DATA / "state.sqlite")
    s.init_schema()
    return s


def cmd_add(args: argparse.Namespace) -> int:
    inp = args.name_or_url.strip()
    if inp.startswith("http"):
        rss = find_rss_from_url(inp) or inp
    else:
        matches = search_itunes(inp)
        if not matches:
            print("no matches")
            return 2
        for i, m in enumerate(matches[:5]):
            print(f"[{i}] {m.title} — {m.author}  ({m.feed_url})")
        choice = input("pick index: ").strip()
        rss = matches[int(choice)].feed_url

    meta = feed_metadata(rss)
    manifest = build_manifest(rss)
    slug_default = meta["title"].lower().replace(" ", "-")
    slug = input(f"slug [{slug_default}]: ").strip() or slug_default

    prompt = suggest_whisper_prompt(
        title=meta["title"],
        author=meta["author"],
        episodes=[
            {"title": e["title"], "description": e["description"]} for e in manifest[-20:]
        ],  # most-recent 20
    )
    print(f"suggested prompt:\n  {prompt}")
    custom = input("override prompt (enter to keep): ").strip()
    if custom:
        prompt = custom

    wl = _watchlist()
    if any(s.slug == slug for s in wl.shows):
        print(f"show {slug!r} already in watchlist")
        return 3
    wl.shows.append(Show(slug=slug, title=meta["title"], rss=rss, whisper_prompt=prompt))
    wl.save(DATA / "watchlist.yaml")

    state = _state()
    for ep in manifest:
        state.upsert_episode(
            show_slug=slug,
            guid=ep["guid"],
            title=ep["title"],
            pub_date=ep["pubDate"],
            mp3_url=ep["mp3_url"],
        )
    print(f"added '{slug}' with {len(manifest)} episodes")
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    wl = _watchlist()
    if not wl.shows:
        print("(empty)")
        return 0
    for s in wl.shows:
        print(f"  [{'✓' if s.enabled else ' '}] {s.slug:25s} {s.title}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    settings = _settings()
    wl = _watchlist()
    state = _state()
    state.recover_in_flight()
    out_root = Path(settings.output_root).expanduser()
    lib = LibraryIndex(out_root)
    lib.scan()

    targets = [s for s in wl.shows if s.enabled and (not args.show or s.slug == args.show)]
    if not targets:
        print("no enabled shows match")
        return 0

    for show in targets:
        print(f"\n# {show.slug}")
        try:
            manifest = build_manifest(show.rss, timeout=60)
        except Exception as e:
            print(f"  feed error: {e}")
            continue
        for ep in manifest:
            state.upsert_episode(
                show_slug=show.slug,
                guid=ep["guid"],
                title=ep["title"],
                pub_date=ep["pubDate"],
                mp3_url=ep["mp3_url"],
            )
        # Map guid → episode_number so we can feed it into slug building
        ep_num_map = {e["guid"]: e["episode_number"] for e in manifest}

        pending = state.list_by_status(show.slug, EpisodeStatus.PENDING)
        if args.limit:
            pending = pending[-args.limit :]  # newest pending (list ordered by pub_date asc)
        if not pending:
            print("  no pending")
            continue

        ctx = PipelineContext(
            state=state,
            library=lib,
            output_root=out_root,
            whisper_prompt=show.whisper_prompt,
            retention_days=settings.mp3_retention_days,
            delete_mp3_after=settings.delete_mp3_after_transcribe,
        )
        for ep in pending:
            r = process_episode(ep["guid"], ctx, episode_number=ep_num_map.get(ep["guid"], "0000"))
            print(f"  [{r.action:11s}] {ep['title'][:70]} — {r.detail[:60]}")
    return 0


def cmd_import_feeds(args: argparse.Namespace) -> int:
    """Bulk-import the 16 real-estate feeds hard-coded in
    raw/transcripts/podcast_downloader.py, using each show's existing
    whisper_prompt from scripts/transcribe.py's SHOWS dict if available.
    """
    from scripts_legacy_shows import SHOWS_PROMPTS  # populated lazily below

    feeds = [
        ("one-a-lage", "https://1alage.podigee.io/feed/mp3"),
        ("immocation", "https://immocation.podigee.io/feed/mp3"),
        ("limmo", "https://haufe-immobilienpodcast.podigee.io/feed/mp3"),
        ("hausverwalter-inside", "https://divmpodcast.libsyn.com/rss"),
        ("immobileros", "https://immobileros.podigee.io/feed/mp3"),
        ("real-estate-pioneers", "https://feeds.buzzsprout.com/1997738.rss"),
        ("dmrex", "https://feeds.buzzsprout.com/2078041.rss"),
        ("grundgedanken", "https://gvh.podcaster.de/grundeigentuemerverband.rss"),
        ("faz-finanzen-immobilien", "https://fazfinanzen.podigee.io/feed/mp3"),
        ("lagebericht", "https://feeds.acast.com/public/shows/61e97e498ad1d30012c50117"),
        ("immopreneur", "https://anchor.fm/s/10204d0b4/podcast/rss"),
        ("denkmalimmobilien", "https://denkmalimmobilien-marcelkeller.podigee.io/feed/mp3"),
        (
            "beyond-buildings",
            "https://letscast.fm/podcasts/beyond-buildings-der-podcast-fuer-die-immobilienwelt-im-wandel-0bcfcb5f/feed",
        ),
        ("immokaiser", "https://immokaiser.podigee.io/feed/mp3"),
        ("vermieter-probleme", "https://16qkrph.podcaster.de/Vermietershop-de.rss"),
        ("gluecklich-wohnen", "https://buwog.podigee.io/feed/mp3"),
    ]
    wl = _watchlist()
    state = _state()
    existing = {s.slug for s in wl.shows}
    for slug, rss in feeds:
        if slug in existing:
            print(f"skip {slug} (already in watchlist)")
            continue
        try:
            meta = feed_metadata(rss)
            manifest = build_manifest(rss, timeout=60)
        except Exception as e:
            print(f"! {slug}: {e}")
            continue
        prompt = SHOWS_PROMPTS.get(slug, "")
        wl.shows.append(
            Show(slug=slug, title=meta["title"] or slug, rss=rss, whisper_prompt=prompt)
        )
        for ep in manifest:
            state.upsert_episode(
                show_slug=slug,
                guid=ep["guid"],
                title=ep["title"],
                pub_date=ep["pubDate"],
                mp3_url=ep["mp3_url"],
            )
        print(f"+ {slug}: {len(manifest)} episodes")
    wl.save(DATA / "watchlist.yaml")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add")
    a.add_argument("name_or_url")
    a.set_defaults(fn=cmd_add)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    c = sub.add_parser("check")
    c.add_argument("--limit", type=int, default=0)
    c.add_argument("--show", type=str, default=None)
    c.set_defaults(fn=cmd_check)
    sub.add_parser("import-feeds").set_defaults(fn=cmd_import_feeds)

    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
