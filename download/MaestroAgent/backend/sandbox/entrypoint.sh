#!/bin/sh
# MaestroAgent sandbox entrypoint.
#
# The container stays alive (sleep infinity) so the engine can
# `docker exec` individual commands into it. We do nothing else
# here — the engine manages the command lifecycle.

set -e

# If the first arg is a known command (not "sleep"), exec it directly.
# This lets users do: docker run maestroagent/sandbox pytest
if [ "$1" != "sleep" ] && [ "$1" != "infinity" ]; then
    exec "$@"
fi

# Default: sleep forever, waiting for exec commands.
exec sleep infinity
