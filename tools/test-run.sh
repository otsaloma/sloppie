#!/bin/sh
set -eu

# Clone this repository under the cache directory, give the clone
# changes of every kind we render and launch sloppie against it. The
# clone is thrown away and made anew on each run, so it can be freely
# messed with. Not under /tmp: repositories there are deliberately not
# recorded as recently opened, so subtasks forked in the run would show
# up ungrouped, and trashing is not supported on tmpfs at all. Subtasks
# are forked as siblings of the clone, hence a directory of its own
# around it, that being what is thrown away.

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$HOME/.cache/sloppie/test-run
TEST=$WORK/sloppie

rm -rf "$WORK"
"$ROOT/tools/fixture-clone.sh" "$TEST"

# Keep the list of recently opened repositories to the run alone, so
# that the clone and its subtasks stay out of the real dashboard.
rm -rf /tmp/sloppie-test-data
export XDG_DATA_HOME=/tmp/sloppie-test-data

echo "Launching against $TEST"
exec "$ROOT/bin/sloppie" "$TEST"
