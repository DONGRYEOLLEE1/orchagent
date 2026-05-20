#!/usr/bin/env bash
# Diff captured baselines for plan §1.5.
# Usage: ./infra/scripts/diff_baseline.sh <task_id>
#
# Compares *_before.* and *_after.* under _workspace/baselines/<task_id>/.
# Reports pytest/vitest pass-count deltas and exits non-zero on regression.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

usage() {
  echo "Usage: $0 <task_id>" >&2
  exit 64
}

[[ $# -ge 1 ]] || usage
TASK_ID="$1"
DIR="$ROOT_DIR/_workspace/baselines/$TASK_ID"

[[ -d "$DIR" ]] || { echo "[diff_baseline] missing dir: $DIR" >&2; exit 2; }

color() { printf "\033[%sm%s\033[0m\n" "$1" "$2"; }
log() { color "1;36" "[diff_baseline] $1"; }
ok() { color "1;32" "[diff_baseline] OK $1"; }
fail() { color "1;31" "[diff_baseline] FAIL $1"; }

regression=0

# Count passes from a pytest log: lines like "...... passed" or summary "X passed"
pytest_pass_count() {
  local f="$1"
  [[ -f "$f" ]] || { echo "0"; return; }
  # Prefer pytest summary line, fallback to dot-PASSED count.
  local n
  n="$(grep -oE '[0-9]+ passed' "$f" | tail -1 | awk '{print $1}')"
  echo "${n:-0}"
}

vitest_pass_count() {
  local f="$1"
  [[ -f "$f" ]] || { echo "0"; return; }
  local n
  n="$(grep -oE '[Tt]ests?[[:space:]]+[0-9]+[[:space:]]+passed' "$f" | tail -1 | awk '{print $(NF-1)}')"
  if [[ -z "$n" ]]; then
    n="$(grep -oE '[0-9]+ passed' "$f" | tail -1 | awk '{print $1}')"
  fi
  echo "${n:-0}"
}

compare_count() {
  local label="$1" before_n="$2" after_n="$3"
  log "$label : before=$before_n after=$after_n"
  if (( after_n < before_n )); then
    fail "$label regression (pass count decreased)"
    regression=1
  else
    ok "$label not regressed"
  fi
}

# pytest
B="$DIR/pytest_before.log"; A="$DIR/pytest_after.log"
[[ -f "$B" && -f "$A" ]] && compare_count "pytest" "$(pytest_pass_count "$B")" "$(pytest_pass_count "$A")"

# vitest
B="$DIR/vitest_before.log"; A="$DIR/vitest_after.log"
[[ -f "$B" && -f "$A" ]] && compare_count "vitest" "$(vitest_pass_count "$B")" "$(vitest_pass_count "$A")"

# node --test (handles both '# pass N' and the newer 'ℹ pass N' summary format)
B="$DIR/nodetest_before.log"; A="$DIR/nodetest_after.log"
if [[ -f "$B" && -f "$A" ]]; then
  nodetest_pass() {
    grep -oE '(# pass [0-9]+|pass [0-9]+)' "$1" | awk '{print $NF}' | tail -1
  }
  bf="$(nodetest_pass "$B")"
  af="$(nodetest_pass "$A")"
  compare_count "nodetest" "${bf:-0}" "${af:-0}"
fi

# JSON snapshots — only flag when both sides exist
shopt -s nullglob
for before in "$DIR"/*_before.json; do
  name="$(basename "$before" _before.json)"
  after="$DIR/${name}_after.json"
  [[ -f "$after" ]] || continue
  log "json diff: $name"
  if diff -q "$before" "$after" >/dev/null 2>&1; then
    ok "$name JSON identical"
  else
    fail "$name JSON differs"
    diff -u "$before" "$after" | head -30 || true
    regression=1
  fi
done

# Lint summary — parse "N errors, M warnings" and only fail when errors > 0.
# Build log — search for explicit error/fail markers, ignoring "0 errors".
for kind in lint build; do
  A="$DIR/${kind}_after.log"
  [[ -f "$A" ]] || continue
  if [[ "$kind" == "lint" ]]; then
    err_count="$(grep -oE '[0-9]+ errors?' "$A" | awk '{print $1}' | tail -1)"
    err_count="${err_count:-0}"
    if (( err_count > 0 )); then
      fail "lint reports $err_count error(s)"
      regression=1
    else
      ok "lint reports 0 errors"
    fi
  else
    # build log: ignore '0 errors' / 'no errors' phrases when scanning.
    if grep -viE 'no errors|0 errors' "$A" | grep -qiE '\b(error|failed|fatal)\b'; then
      fail "build after-log contains error/fail markers"
      regression=1
    else
      ok "build after-log clean"
    fi
  fi
done

if (( regression == 0 )); then
  ok "no regression detected"
  exit 0
else
  fail "regression detected — investigate before merging"
  exit 1
fi
