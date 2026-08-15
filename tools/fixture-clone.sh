#!/bin/bash
# -*- coding: utf-8-unix -*-

# Clone this repository to DIRECTORY, which must not exist, and give
# the clone changes of every kind we render, in amounts and shapes that
# match real use. Used as a repository to look at sloppie against.

set -eu

test $# -eq 1 || { echo "Usage: $(basename "$0") DIRECTORY" >&2; exit 1; }
ROOT=$(cd "$(dirname "$0")/.." && pwd)
git clone --quiet "$ROOT" "$1"
cd "$1"

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

# Comments: a short one, a couple of long ones that wrap over several
# lines and a pasted error log that is cut short on its card, all of
# them on the changes as a whole.
mkdir -p ".git/sloppie/comments"
cat > ".git/sloppie/comments/$(git branch --show-current).json" <<'EOF'
[{
  "text": "Rename the module to something less generic.",
  "path": null,
  "hunk": null
}, {
  "text": "Splitting a diff into hunks belongs in git.py next to parse_diff, which is the only place that knows what a hunk line looks like. A module of its own for one function is one file too many.",
  "path": null,
  "hunk": null
}, {
  "text": "The quote style reformat is unrelated to the rest of the changes here, please pull it out into a commit of its own so that the actual change is reviewable.",
  "path": null,
  "hunk": null
}, {
  "text": "This comes up every other run now, please look into it:\n\nTraceback (most recent call last):\n  File \"slop/window.py\", line 317, in _on_change_selected\n    text = self.repository.get_diff(change)\n  File \"slop/git.py\", line 237, in get_diff\n    return self._diff(*args, \"--\", *self._paths(change))\n  File \"slop/git.py\", line 122, in _git\n    raise RuntimeError(f\"{' '.join(command)}: {error}\")\nRuntimeError: git --no-pager -c color.ui=never diff --no-ext-diff -- slop/git.py: fatal: bad revision",
  "path": null,
  "hunk": null
}]
EOF
