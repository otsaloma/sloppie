#!/bin/sh
set -eu

# Initialize a git repository at DIRECTORY in the middle of a merge that
# conflicted. Used by the test suite.

test $# -eq 1 || { echo "Usage: $(basename "$0") DIRECTORY" >&2; exit 1; }
mkdir -p "$1"
cd "$1"

git init --quiet --initial-branch=main

# Needed for commits, the tests ignoring the global git config.
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

# Leaves conflict.txt unmerged and added-by-other.txt staged.
git merge other >/dev/null 2>&1 || true
