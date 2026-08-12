#!/bin/bash
# -*- coding: utf-8-unix -*-

# Clone this repository under /tmp, give the clone changes of every
# kind we render and launch sloppie against it. The clone is thrown
# away and made anew on each run, so it can be freely messed with.

set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
TEST=/tmp/sloppie-test

rm -rf "$TEST"
git clone --quiet "$ROOT" "$TEST"
cd "$TEST"

# Staged: a rename spread over a file, a quote style reformat touching
# nearly every line, an addition, a deletion, a rename and a binary
# file, which has no line counts to show in the sidebar.
sed -i 's/_parse_numstat/_parse_counts/g' slop/git.py
sed -i "s/\"/'/g" slop/sidebar.py
cat > slop/hunks.py <<'EOF'
# -*- coding: utf-8 -*-

def group_hunks(lines):
    """Split diff `lines` into a list of hunks."""
    hunks = []
    for line in lines:
        if line.kind == "hunk":
            hunks.append([])
        if hunks:
            hunks[-1].append(line)
    return hunks
EOF
git rm --quiet slop/comments.py
git mv AUTHORS.md AUTHORS.txt
printf '\000\001\002\003binary\n' > staged.bin
git add --all

# Unstaged: a rename spread over a file, a deletion and a second rename
# in a file that is already staged, which lands it in two sections at
# once, with a different diff in each.
sed -i 's/_diff_view/_diff/g' slop/window.py
sed -i 's/\bstats\b/numstat/g' slop/git.py
rm Makefile

# Untracked: a file, a binary file and a file in a subdirectory.
cat > notes.md <<'EOF'
# Notes

Nothing here yet.
EOF
printf '\000\001\002\003binary\n' > untracked.bin
cat > slop/test/test_hunks.py <<'EOF'
# -*- coding: utf-8 -*-

import slop.test

class TestHunks(slop.test.TestCase):

    def test_group_hunks(self):
        assert slop.group_hunks([]) == []
EOF

echo "Launching against $TEST"
exec "$ROOT/bin/sloppie" "$TEST"
