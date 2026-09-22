#!/bin/sh
set -eu

# Initialize a git repository at DIRECTORY with a change of every kind,
# small enough to write the expected output by hand. Used by the test
# suite.

test $# -eq 1 || { echo "Usage: $(basename "$0") DIRECTORY" >&2; exit 1; }
mkdir -p "$1"
cd "$1"

git init --quiet

# Needed for commits, the tests ignoring the global git config.
git config user.email test@test
git config user.name Test
printf 'a\nb\nc\n' > modified.txt
printf 'keep\n' > renamed-from.txt
printf 'gone\naway\n' > deleted-staged.txt
printf 'gone\ntoo\n' > deleted-unstaged.txt
printf 'bin\000\001data\n' > binary.bin
git add --all
git commit --quiet -m init

# Staged
printf 'a\nB\nc\nd\n' > modified.txt
git mv renamed-from.txt renamed-to.txt
git rm --quiet deleted-staged.txt
printf 'bin\000\002data\n' > binary.bin
git add --all

# Unstaged
printf 'a\nB\nc\nd\ne' > modified.txt
rm deleted-unstaged.txt

# Untracked
printf 'new\n' > untracked.txt
