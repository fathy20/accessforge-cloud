#!/usr/bin/env bash
# Executable baseline gate.
#
# Run this BEFORE a repository move and AGAIN after it. If both runs report the
# same numbers, the move preserved behaviour; if they differ, it did not. That
# is the whole purpose — this is a comparison instrument, not a quality system.
#
#   scripts/baseline.sh              # everything
#   scripts/baseline.sh --no-docker  # skip the two docker gates
#
# Every gate here is a command the project already uses (package.json scripts,
# pyproject.toml, docs/deploy/docker.md). Nothing is invented for this script.
#
# SIDE EFFECTS: none beyond a docker image-layer cache write. It never runs
# `compose down`, never removes a volume, never touches a database, and never
# runs a migration. It does not start containers.

set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2
ROOT="$(pwd)"

RUN_DOCKER=1
[ "${1:-}" = "--no-docker" ] && RUN_DOCKER=0

LOG_DIR="${TMPDIR:-/tmp}/redsea-baseline.$$"
mkdir -p "$LOG_DIR"

pass_backend=""; pass_fe_test=""; pass_fe_build=""; pass_cfg=""; pass_build=""
overall=0

# Run a gate, capture its log, remember its exit status.
gate() {
  local key="$1" label="$2"; shift 2
  printf '%-16s ... ' "$label"
  if "$@" > "$LOG_DIR/$key.log" 2>&1; then
    printf 'ok\n'; return 0
  else
    printf 'FAILED\n'; overall=1; return 1
  fi
}

echo "REDSEA baseline"
echo "root: $ROOT"
echo "git:  $(git rev-parse --short HEAD 2>/dev/null || echo 'n/a')"
echo

# --- backend -----------------------------------------------------------------
if gate backend "backend tests" python -m pytest backend/tests -q -p no:cacheprovider; then
  pass_backend="PASS ($(grep -oE '[0-9]+ passed' "$LOG_DIR/backend.log" | tail -1 | grep -oE '[0-9]+'))"
else
  pass_backend="FAIL"
fi

# --- frontend ----------------------------------------------------------------
if gate fe_test "frontend tests" npm test; then
  pass_fe_test="PASS ($(grep -oE 'Tests +[0-9]+ passed' "$LOG_DIR/fe_test.log" | tail -1 | grep -oE '[0-9]+' | tail -1))"
else
  pass_fe_test="FAIL"
fi

if gate fe_build "frontend build" npm run build; then
  pass_fe_build="PASS"
else
  pass_fe_build="FAIL"
fi

# --- docker ------------------------------------------------------------------
if [ "$RUN_DOCKER" = 1 ]; then
  if gate cfg "compose config" docker compose config -q; then
    pass_cfg="PASS ($(docker compose config --format json 2>/dev/null | python -c 'import sys,json;print(json.load(sys.stdin).get("name"))' 2>/dev/null || echo '?'))"
  else
    pass_cfg="FAIL"
  fi

  if gate build "docker build" docker compose build; then
    pass_build="PASS"
  else
    pass_build="FAIL"
  fi
else
  pass_cfg="SKIPPED"; pass_build="SKIPPED"
fi

# --- informational, NOT a gate -----------------------------------------------
# `npm run lint` exists but does not pass today: 3,027 problems, almost all
# `Delete CR` from CRLF line endings. Recorded so the number is visible and a
# change in it is noticed; deliberately excluded from OVERALL so the baseline
# is not red from the outset. There is no `typecheck` script, so none is run.
lint_count="$(npm run lint 2>&1 | grep -oE '[0-9]+ problems' | tail -1 || true)"
[ -z "$lint_count" ] && lint_count="n/a"

cat <<EOF

BASELINE RESULT
backend tests   : $pass_backend
frontend tests  : $pass_fe_test
frontend build  : $pass_fe_build
compose config  : $pass_cfg
docker build    : $pass_build

lint (not gated): $lint_count

OVERALL         : $([ $overall -eq 0 ] && echo PASS || echo FAIL)

logs: $LOG_DIR
EOF

exit $overall
