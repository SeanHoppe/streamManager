#!/usr/bin/env bash
# POC Alt 3 + Alt 5 parallel orchestrator.
#
# Track A (Alt 3): tools/cassette_record_safety.py — record 5 safety-
#   priority cassettes to tests/cassettes/safety/p{1..5}-*.json.
# Track B (Alt 5): tools/path_d_verify.py — verify PR #214 merged +
#   emit Tier-3 soak command (DOES NOT fire soak; main thread owns).
#
# Tracks are file/actor/gate disjoint per docs/poc/next-steps.md;
# safe to fan out concurrently. This orchestrator launches both
# in the background, waits, then exits with the WORST exit code
# from either track (max(rcA, rcB)).
#
# Default mode is --dry-run. Pass --live to record real cassettes
# (requires `claude` CLI on PATH; synthetic creds only — script
# itself refuses real-shape AWS key ids).
#
# Per feedback_subagent_long_task_abandonment.md: this orchestrator
# does NOT spawn the Tier-3 soak — it only emits the command. The
# main thread fires the soak separately.

set -u  # error on undefined vars; do NOT use -e (we want full exit-code capture)

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

DRY_RUN=1
JSON_OUT=0
ALLOW_OVERWRITE=0
CASSETTE_OUT="tests/cassettes/safety"
SOAK_TIER=3
CLI_POOL_SIZE=2
PR_NUMBER=214

usage() {
  cat <<EOF
Usage: $0 [options]

  --dry-run            Default. Track A writes synthetic envelopes; no CLI call.
  --live               Track A records real engine.evaluate decisions.
  --allow-overwrite    Pass through to Track A; clobber existing cassette files.
  --out DIR            Cassette output directory (default: ${CASSETTE_OUT}).
  --soak-tier N        Tier for Track B emitted soak command (default: ${SOAK_TIER}).
  --cli-pool-size N    Soak --cli-pool-size value (default: ${CLI_POOL_SIZE}, min 2).
  --pr N               PR number Track B verifies (default: ${PR_NUMBER}).
  --json               Track B emits JSON status.
  -h, --help           Show this help.

Exit:
  0 — both tracks succeeded.
  2 — at least one track failed (worst rc returned).
  3 — credential-shape violation OR git/gh prerequisite missing.
EOF
}

while (( $# > 0 )); do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --live)    DRY_RUN=0; shift ;;
    --allow-overwrite) ALLOW_OVERWRITE=1; shift ;;
    --out) CASSETTE_OUT="$2"; shift 2 ;;
    --soak-tier) SOAK_TIER="$2"; shift 2 ;;
    --cli-pool-size) CLI_POOL_SIZE="$2"; shift 2 ;;
    --pr) PR_NUMBER="$2"; shift 2 ;;
    --json) JSON_OUT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[orch] unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if (( CLI_POOL_SIZE < 2 )); then
  echo "[orch] REFUSE: --cli-pool-size must be >= 2 (feedback_soak_cli_pool_flag.md)" >&2
  exit 2
fi

LOG_DIR="${REPO_ROOT}/tmp/poc_orch"
mkdir -p "${LOG_DIR}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_A="${LOG_DIR}/track_a_${TS}.log"
LOG_B="${LOG_DIR}/track_b_${TS}.log"

# Track A args.
A_ARGS=( --out "${CASSETTE_OUT}" --cli-pool-size "${CLI_POOL_SIZE}" )
if (( DRY_RUN == 1 )); then A_ARGS+=( --dry-run ); fi
if (( ALLOW_OVERWRITE == 1 )); then A_ARGS+=( --allow-overwrite ); fi

# Track B args.
B_ARGS=( --soak-tier "${SOAK_TIER}" --cli-pool-size "${CLI_POOL_SIZE}" --pr "${PR_NUMBER}" )
if (( JSON_OUT == 1 )); then B_ARGS+=( --json ); fi

echo "[orch] ts=${TS} dry_run=${DRY_RUN} live=$((1 - DRY_RUN))"
echo "[orch] Track A log: ${LOG_A}"
echo "[orch] Track B log: ${LOG_B}"

# Fan out.
python tools/cassette_record_safety.py "${A_ARGS[@]}" >"${LOG_A}" 2>&1 &
PID_A=$!
python tools/path_d_verify.py "${B_ARGS[@]}" >"${LOG_B}" 2>&1 &
PID_B=$!

# Wait independently so both rcs are captured.
wait "${PID_A}"; RC_A=$?
wait "${PID_B}"; RC_B=$?

echo "[orch] Track A rc=${RC_A}"
echo "[orch] Track B rc=${RC_B}"

# Summarize.
echo "----- Track A output -----"
cat "${LOG_A}"
echo "----- Track B output -----"
cat "${LOG_B}"

if (( RC_A > RC_B )); then exit "${RC_A}"; else exit "${RC_B}"; fi
