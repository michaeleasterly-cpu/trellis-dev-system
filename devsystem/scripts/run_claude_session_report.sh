#!/usr/bin/env bash
# D0c — Operator wrapper for the portable Claude session/cost report.
# Manual invocation only: no Docker, no railway up, no Anthropic API,
# no memstore writes, no DB writes, no daemon. See
# devsystem/docs/CLAUDE_SESSION_OBSERVABILITY.md.template (or the
# rendered copy in your consumer repo).
#
# The portable dev-system version has no project-specific default
# input directory — pass --input-dir explicitly:
#
#     ./devsystem/scripts/run_claude_session_report.sh \
#         --input-dir ~/.claude/projects/<your-project>/
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$HERE/claude_session_report.py" "$@"
