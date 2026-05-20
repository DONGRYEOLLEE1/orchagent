#!/usr/bin/env bash
# Capture refactoring baseline for plan §1.2 / §1.5.
# Usage: ./infra/scripts/capture_baseline.sh <task_id> [before|after] [--with-build]
#
# Outputs land in _workspace/baselines/<task_id>/ with suffix _<phase>.{log,json}.
# Optional --with-build runs `npm run build` (slow).
# API-response and openapi snapshots are skipped gracefully when backend dev is unreachable.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat >&2 <<EOF
Usage: $0 <task_id> [before|after] [--with-build]

Examples:
  $0 phase0 before
  $0 1.1 after --with-build
EOF
  exit 64
}

[[ $# -ge 1 ]] || usage

TASK_ID="$1"
PHASE="${2:-before}"
WITH_BUILD="0"
case "${3:-}" in
  --with-build) WITH_BUILD="1" ;;
  "") : ;;
  *) usage ;;
esac

case "$PHASE" in
  before|after) : ;;
  *) usage ;;
esac

OUT_DIR="$ROOT_DIR/_workspace/baselines/$TASK_ID"
mkdir -p "$OUT_DIR"

color() { printf "\033[%sm%s\033[0m\n" "$1" "$2"; }
log() { color "1;36" "[capture_baseline] $1"; }
warn() { color "1;33" "[capture_baseline] $1"; }
err() { color "1;31" "[capture_baseline] $1" >&2; }

log "task_id=$TASK_ID phase=$PHASE with_build=$WITH_BUILD"
log "output dir: $OUT_DIR"

# -----------------------------------------------------------------------------
# Backend pytest
# -----------------------------------------------------------------------------
if [[ -d apps/backend ]]; then
  log "backend pytest (PYTHONPATH=. per CI yaml convention)"
  (cd apps/backend && PYTHONPATH=. uv run pytest tests/ -v --tb=line) \
    > "$OUT_DIR/pytest_${PHASE}.log" 2>&1 || warn "pytest exited non-zero (see log)"
else
  warn "apps/backend missing — skipping pytest"
fi

# -----------------------------------------------------------------------------
# Frontend lint / vitest / node test
# -----------------------------------------------------------------------------
if [[ -d apps/frontend ]]; then
  log "frontend lint"
  (cd apps/frontend && npm run lint) \
    > "$OUT_DIR/lint_${PHASE}.log" 2>&1 || warn "lint exited non-zero"

  log "frontend vitest"
  (cd apps/frontend && npm run test -- --run) \
    > "$OUT_DIR/vitest_${PHASE}.log" 2>&1 || warn "vitest exited non-zero"

  log "frontend node --test chat-stream"
  if [[ -f apps/frontend/src/lib/chat-stream.test.mjs ]]; then
    (cd apps/frontend && node --test src/lib/chat-stream.test.mjs) \
      > "$OUT_DIR/nodetest_${PHASE}.log" 2>&1 || warn "node --test exited non-zero"
  else
    warn "chat-stream.test.mjs not found — skipping"
  fi

  if [[ "$WITH_BUILD" == "1" ]]; then
    log "frontend build (slow)"
    (cd apps/frontend && npm run build) \
      > "$OUT_DIR/build_${PHASE}.log" 2>&1 || warn "build exited non-zero"
  fi
else
  warn "apps/frontend missing — skipping lint/vitest/build"
fi

# -----------------------------------------------------------------------------
# Backend dev API snapshot (best-effort)
# -----------------------------------------------------------------------------
BACKEND_HOST="${BACKEND_BASE_URL:-http://localhost:8002}"
COOKIE_JAR="${COOKIE_JAR:-${ROOT_DIR}/_workspace/baselines/.cookies}"

probe_backend() {
  curl -sS -o /dev/null -w "%{http_code}" --max-time 3 "$BACKEND_HOST/api/health" 2>/dev/null || true
}

CODE="$(probe_backend)"
if [[ "$CODE" == "200" || "$CODE" == "204" ]]; then
  log "backend dev reachable at $BACKEND_HOST — capturing snapshots"

  for path in "threads" "dashboard/summary" "users/me/memory/settings"; do
    name="$(echo "$path" | tr '/' '_')"
    if [[ -f "$COOKIE_JAR" ]]; then
      curl -sS -b "$COOKIE_JAR" "$BACKEND_HOST/api/$path" \
        > "$OUT_DIR/${name}_${PHASE}.json" 2>"$OUT_DIR/${name}_${PHASE}.err" \
        || warn "snapshot $path failed (see ${name}_${PHASE}.err)"
    else
      curl -sS "$BACKEND_HOST/api/$path" \
        > "$OUT_DIR/${name}_${PHASE}.json" 2>"$OUT_DIR/${name}_${PHASE}.err" \
        || warn "snapshot $path failed (see ${name}_${PHASE}.err)"
    fi
  done

  log "openapi snapshot"
  curl -sS "$BACKEND_HOST/openapi.json" > "$OUT_DIR/openapi_${PHASE}.json" \
    2>"$OUT_DIR/openapi_${PHASE}.err" \
    || warn "openapi snapshot failed (see openapi_${PHASE}.err)"
else
  warn "backend dev unreachable (HTTP=$CODE) — skipping API snapshots."
  warn "  Tip: start the dev stack via ./infra/scripts/start-dev.sh and re-run with phase=$PHASE."
fi

log "done. Inspect: $OUT_DIR"
