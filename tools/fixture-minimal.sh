#!/bin/sh
set -eu

# Initialize a minimal git repository at DIRECTORY, with a change of
# every kind, but small enough that the expected output of each can be
# written out by hand. Used as the scratch repository of the test suite.

test $# -eq 1 || { echo "Usage: $(basename "$0") DIRECTORY" >&2; exit 1; }
mkdir -p "$1"
cd "$1"

git init --quiet

# Give the repository an identity of its own, so that commits made
# here and by the code under test work without a global git config.
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
