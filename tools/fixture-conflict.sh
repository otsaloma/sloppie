#!/bin/sh
set -eu

# Initialize a git repository at DIRECTORY stopped in the middle of a
# merge that conflicted, git reporting a file left unmerged unlike any
# other. Used as a scratch repository of the test suite.

test $# -eq 1 || { echo "Usage: $(basename "$0") DIRECTORY" >&2; exit 1; }
mkdir -p "$1"
cd "$1"

git init --quiet --initial-branch=main

# Give the repository an identity of its own, so that commits made
# here and by the code under test work without a global git config.
git config user.email test@test
git config user.name Test
printf 'one\ntwo\nthree\n' > conflict.txt
git add --all
git commit --quiet -m init

git checkout --quiet -b other
printf 'one\nOTHER\nthree\n' > conflict.txt
printf 'from other\n' > added-by-other.txt
git add --all
git commit --quiet -m other

git checkout --quiet main
printf 'one\nMAIN\nthree\n' > conflict.txt
git commit --quiet -am main

# Both branches rewrote the same line, which leaves conflict.txt
# unmerged and added-by-other.txt staged, the merge being unfinished.
git merge other >/dev/null 2>&1 || true
