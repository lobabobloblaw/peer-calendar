#!/usr/bin/env bash
#
# Every check that guards published data, in the order CI runs them.
#
# Run this before pushing. Nothing here writes to docs/ or guides/: calendar
# generation goes to the gitignored output/ directory, so a run can never
# publish by accident.
#
# Usage:
#   scripts/check_all.sh          # the deterministic checks (about 30 seconds)
#   scripts/check_all.sh --e2e    # also the Playwright browser suite (slower)
#
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

run_e2e=false
for arg in "$@"; do
    case "$arg" in
        --e2e) run_e2e=true ;;
        -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $arg (try --e2e)" >&2; exit 2 ;;
    esac
done

step=0
failed=()
total=6
[ "${1:-}" = "--e2e" ] && total=7

log_dir="$(mktemp -d)"
trap 'rm -rf "$log_dir"' EXIT

# Output is captured and shown only when a check fails: a green run should be
# six lines, not several hundred lines of test chatter.
check() {
    local name="$1"; shift
    step=$((step + 1))
    local log="$log_dir/step-$step.log"
    printf '[%d/%d] %-24s' "$step" "$total" "$name"
    if "$@" >"$log" 2>&1; then
        printf 'ok\n'
    else
        printf 'FAILED\n\n'
        sed 's/^/    /' "$log"
        printf '\n'
        failed+=("$name")
    fi
}

check "Entry schema"          python3 scripts/audit_check.py --validate
check "Schedule strings"      python3 scripts/validate_schedules.py
check "Python tests"          python3 -m unittest discover -s scripts -p 'test_*.py'
# --output is resolved against scripts/, not the working directory, so the
# default is what puts the feed in the repository's own output/ directory.
check "Calendar generation"   python3 scripts/generate_calendar.py --json
check "Web schedule parity"   node scripts/test_web_schedule_parity.mjs --feed output/events.json
check "Deterministic UI"      npm run --silent test:web-contract

if [ "$run_e2e" = true ]; then
    check "Browser accessibility" npm run --silent test:web-e2e
else
    printf '\n    skipping the browser suite; pass --e2e to include it\n'
fi

printf '\n'
if [ ${#failed[@]} -eq 0 ]; then
    printf 'All %d checks passed.\n' "$step"
else
    printf '%d of %d checks failed:\n' "${#failed[@]}" "$step"
    printf '  - %s\n' "${failed[@]}"
    exit 1
fi
