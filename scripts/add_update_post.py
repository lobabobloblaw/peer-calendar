"""Add a dated post to the Updates section of docs/index.html.

Two modes:

  Curated (humans/agents shipping a change):
    python add_update_post.py --text "August web-verification pass: ..."

  Auto (CI, after feed regeneration publishes changes):
    python add_update_post.py --auto --before /tmp/events-before.json --after ../docs/events.json

Rules (see CLAUDE.md data flow):
- At most one auto-post per day: auto mode skips if the list's top entry
  already carries today's date. Curated posts always insert, and a curated
  post earlier in the day is what blocks that day's auto-post.
- Posts are plain <li> entries matching the hand-maintained list's format.
"""
import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

INDEX_HTML = Path(__file__).parent.parent / "docs" / "index.html"
LIST_ANCHOR = '<ul class="updates-list">'
LI_INDENT = " " * 24

MAX_NAMES = 3


def today_label(now: datetime | None = None) -> str:
    """Date label matching existing entries: 'Aug 6', 'Jul 24' (no year)."""
    now = now or datetime.now()
    return f"{now.strftime('%b')} {now.day}"


def top_post_date(index_text: str) -> str | None:
    """Date label of the newest post, or None if the list is empty."""
    after = index_text.split(LIST_ANCHOR, 1)[1]
    m = re.search(r'<span class="update-date">([^<]+)</span>', after)
    return m.group(1) if m else None


def insert_post(index_path: Path, text: str, now: datetime | None = None) -> None:
    """Insert one <li> at the top of the updates list. Always inserts."""
    escaped = html.escape(text, quote=False)
    li = f'{LI_INDENT}<li><span class="update-date">{today_label(now)}</span> {escaped}</li>\n'
    content = index_path.read_text(encoding="utf-8")
    if LIST_ANCHOR not in content:
        print(f"Error: {LIST_ANCHOR} not found in {index_path}", file=sys.stderr)
        sys.exit(1)
    content = content.replace(LIST_ANCHOR, LIST_ANCHOR + "\n" + li.rstrip("\n"), 1)
    # The newline that already followed the anchor now terminates the new
    # <li>, so the previous top entry stays on its own line.
    index_path.write_text(content, encoding="utf-8")
    print(f"Posted: {li.strip()[:100]}")


def load_feed(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    events = data if isinstance(data, list) else data.get("events", [])
    return {e.get("id"): e for e in events if isinstance(e, dict) and e.get("id")}


def summarize(before: dict, after: dict) -> str:
    """One-line summary of entry-level changes between two events.json feeds."""

    def names(ids) -> list[str]:
        return sorted(after[i].get("title") or i for i in ids)

    def render(label: str, titles: list[str]) -> str:
        if not titles:
            return ""
        shown = titles[:MAX_NAMES]
        suffix = f", and {len(titles) - MAX_NAMES} more" if len(titles) > MAX_NAMES else ""
        return f"{label}: {', '.join(shown)}{suffix}"

    added = names(set(after) - set(before))
    removed_ids = set(before) - set(after)
    removed = sorted(before[i].get("title") or i for i in removed_ids)
    changed = sum(
        1 for i in set(before) & set(after) if before[i] != after[i]
    )

    parts = [p for p in (render("New", added), render("Removed", removed)) if p]
    if changed:
        parts.append(f"Updated data for {changed} resource{'s' if changed != 1 else ''}")
    if not parts:
        return "Calendar feeds refreshed"
    total = len(after)
    return "; ".join(parts) + f". Calendar now at {total} resources"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--text", help="Curated post text (always inserts)")
    mode.add_argument("--auto", action="store_true", help="Summarize events.json diff; skip if already posted today")
    parser.add_argument("--before", type=Path, help="events.json before regeneration (auto mode)")
    parser.add_argument("--after", type=Path, help="events.json after regeneration (auto mode)")
    parser.add_argument("--index", type=Path, default=INDEX_HTML, help="Path to index.html")
    args = parser.parse_args()

    if args.text is not None:
        insert_post(args.index, args.text)
        return

    for flag in ("before", "after"):
        if getattr(args, flag) is None:
            parser.error(f"--auto requires --{flag}")

    index_text = args.index.read_text(encoding="utf-8")
    if LIST_ANCHOR not in index_text:
        print(f"Error: {LIST_ANCHOR} not found in {args.index}", file=sys.stderr)
        sys.exit(1)
    if top_post_date(index_text) == today_label():
        print("Already posted today - skipping auto-post")
        return

    summary = summarize(load_feed(args.before), load_feed(args.after))
    insert_post(args.index, summary)


if __name__ == "__main__":
    main()
