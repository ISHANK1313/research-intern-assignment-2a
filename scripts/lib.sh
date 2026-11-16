#!/usr/bin/env bash
# Shared helpers for the pipeline scripts.
#
# Every MFA invocation goes through run_logged() so the exact command line ends
# up in logs/commands.log.  The report and README quote that file, which is why
# it is written to rather than hand-maintained.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/logs}"
COMMAND_LOG="$LOG_DIR/commands.log"

mkdir -p "$LOG_DIR"

log_command() {
    # Append a command line to the commands log with a UTC timestamp.
    local stamp
    stamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf '[%s] %s\n' "$stamp" "$*" >> "$COMMAND_LOG"
}

run_logged() {
    # Run a command, echo it, record it, and tee its output to a log file.
    #   run_logged <logfile> <command...>
    local logfile="$1"
    shift
    echo "+ $*"
    log_command "$@"
    mkdir -p "$(dirname "$logfile")"
    set +e
    "$@" 2>&1 | tee "$logfile"
    local status="${PIPESTATUS[0]}"
    set -e
    return "$status"
}

# Where MFA keeps downloaded models; overridable for reproducibility.
MFA_ROOT="${MFA_ROOT:-$HOME/Documents/MFA}"
