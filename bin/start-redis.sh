#!/usr/bin/env bash
# Self-healing redis launcher.
#
# Kubernetes container restarts wipe /usr (only /app persists), so any
# apt-installed redis-server disappears across restarts. This wrapper:
#   1. Checks for /usr/bin/redis-server.
#   2. If missing, re-installs the apt package (silent, quick).
#   3. Execs redis-server with whatever args supervisor passes.
#
# This keeps the supervisor program stable: it always invokes this script,
# which always ends up running redis-server, regardless of how /usr was
# wiped.
set -u
LOG_PREFIX="[start-redis]"

if ! command -v redis-server >/dev/null 2>&1; then
  echo "$LOG_PREFIX redis-server missing — installing via apt"
  # `apt-get update` is needed because the container's apt cache is also
  # ephemeral. Run quietly; surface errors to supervisor's err log.
  apt-get update -qq 2>&1 | sed "s/^/$LOG_PREFIX apt: /"
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends redis-server 2>&1 \
    | sed "s/^/$LOG_PREFIX apt: /"
fi

if ! command -v redis-server >/dev/null 2>&1; then
  echo "$LOG_PREFIX FATAL: redis-server still missing after install attempt" >&2
  exit 1
fi

echo "$LOG_PREFIX starting: $(which redis-server) $*"
exec redis-server "$@"
