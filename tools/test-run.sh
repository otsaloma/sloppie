#!/bin/sh
set -eu

# Clone this repository under the cache directory, give the clone
# changes of every kind we render and launch sloppie against it. The
# clone is thrown away and made anew on each run, so it can be freely
# messed with. Not under /tmp: repositories there are deliberately not
# recorded as recently opened, so subtasks forked in the run would show
# up ungrouped, and GLib keeps the trash under the home directory and
# refuses to trash across a filesystem boundary, tmpfs to ext4.
# Subtasks are forked as siblings of the clone, hence a directory of
# its own around it, that being what is thrown away.
#
# Nothing here sets XDG_DATA_HOME to keep the clone out of the real
# list of recently opened repositories: the terminals of the run
# inherit the environment of sloppie, and claude, started in one of
# them, would install itself under a directory thrown away on the next
# run and leave ~/.local/bin/claude pointing there. The clone is left
# among the real ones instead, where it is skipped once thrown away,
# its '.git' being gone.

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$HOME/.cache/sloppie/test-run
TEST=$WORK/sloppie

rm -rf "$WORK"
"$ROOT/tools/fixture-clone.sh" "$TEST"

echo "Launching against $TEST"
exec "$ROOT/bin/sloppie" "$TEST"
