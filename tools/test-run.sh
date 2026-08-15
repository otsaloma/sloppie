#!/bin/sh
set -eu

# Clone this repository under /tmp, give the clone changes of every
# kind we render and launch sloppie against it. The clone is thrown
# away and made anew on each run, so it can be freely messed with.

ROOT=$(cd "$(dirname "$0")/.." && pwd)
TEST=/tmp/sloppie-test

rm -rf "$TEST"
"$ROOT/tools/fixture-clone.sh" "$TEST"

echo "Launching against $TEST"
exec "$ROOT/bin/sloppie" "$TEST"
