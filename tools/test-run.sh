#!/bin/sh
set -eu

# Launch sloppie against a clone with changes of every kind we render,
# thrown away when the run ends. Not under /tmp, which is not recorded
# as recently opened and from which GLib refuses to trash. A directory
# around the clone, as subtasks are forked as its siblings.
#
# XDG_DATA_HOME is not set to keep the clone out of the real list of
# recent repositories: the terminals inherit it, and claude started in
# one would install itself under a directory thrown away on the next
# run. The clone is skipped in the list once gone.

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$HOME/.cache/sloppie/test-run
TEST=$WORK/sloppie

cleanup() {
    rm -rf "$WORK"
}

trap cleanup 0
cleanup
"$ROOT/tools/fixture-clone.sh" "$TEST"
echo "Launching against $TEST"
"$ROOT/bin/sloppie" "$TEST"
