# Repository Guidelines

## Project Structure & Module Organization

`data/sources.yaml` is the canonical, multi-document YAML database; do not substitute the root-level `sources.yaml`. Verification history and research backlog live in `data/audit-log.yaml` and `data/queue.yaml`. Python 3.13+ tooling and its colocated tests are under `scripts/`; new records start from `templates/resource-entry.yaml`. `docs/index.html` is the GitHub Pages UI. `guides/resources-guide.md`, `docs/events.json`, and `docs/{apple,google,outlook}/` are generated publishing artifacts. `output/` and `distribution/` are local generated directories and are gitignored.

## Setup, Validation, and Generation

Run commands from the repository root:

```bash
python3 -m venv scripts/venv
source scripts/venv/bin/activate
python -m pip install -r scripts/requirements.txt
python scripts/audit_check.py --validate
python scripts/validate_schedules.py
python -m unittest discover -s scripts -p 'test_*.py'
python scripts/generate_calendar.py --json
python scripts/generate_guides.py
```

The two validation commands check schema values and schedule parsing. Tests cover calendar parsing and update posts. Calendar generation writes ignored files to `output/`; add `--publish` only when intentionally refreshing tracked files in `docs/`.

## Coding Style & Data Conventions

Use four-space Python indentation, `snake_case` names, `PascalCase` test classes, and `UPPER_CASE` constants. Type hints and short docstrings are encouraged; no formatter or linter is configured. In YAML, use two-space indentation, unique kebab-case IDs, snake-case keys, and ISO dates (`YYYY-MM-DD`). Treat controlled vocabularies in `scripts/utils.py` as authoritative. Use `dates`—never year-suffixed keys such as `dates_2026`—and include the year. Preserve deterministic generation. Retain closed resources with `status: CLOSED`; do not delete their history.

## Testing Guidelines

Tests use standard-library `unittest`. Name files `test_*.py`, classes `Test...`, and methods `test_...`. Add focused regression cases for parser, calendar, or publishing changes. There is no coverage threshold; run both validations and the full discovery command before submitting.

## Commit & Pull Request Guidelines

Follow history with imperative, sentence-case subjects such as `Fix platform selection ternary` or scoped forms like `CI: regenerate calendar feeds weekly`; use `closes #N` when applicable. PRs should summarize impact, list affected resource IDs and official verification sources/dates, report validation commands, and call out generated diffs. Link issues and include screenshots for `docs/index.html` UI changes.

## Data Safety & Publishing

Only store public resource facts from official sources. Never commit participant/client PII, case notes, credentials, or private contact details. Preserve HTML escaping, keyboard access, and screen-reader behavior in UI changes. When published feeds change, add a concise update with `python scripts/add_update_post.py --text "..."`.
