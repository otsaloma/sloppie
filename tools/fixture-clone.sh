#!/bin/sh
set -eu

# Clone this repository to DIRECTORY, which must not exist, and give
# the clone changes of every kind we render, in amounts and shapes that
# match real use. Used as a repository to look at sloppie against.

test $# -eq 1 || { echo "Usage: $(basename "$0") DIRECTORY" >&2; exit 1; }
ROOT=$(cd "$(dirname "$0")/.." && pwd)
git clone --quiet "$ROOT" "$1"
cd "$1"

# Staged
sed -i 's/_parse_numstat/_parse_counts/g' slop/git.py
sed -i "s/\"/'/g" slop/sidebar.py
cat > slop/hunks.py <<'EOF'
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

# Unstaged
sed -i 's/_diff_view/_diff/g' slop/window.py
sed -i 's/\bstats\b/numstat/g' slop/git.py
rm Makefile

# Untracked
cat > notes.md <<'EOF'
# Notes
EOF
printf '\000\001\002\003binary\n' > untracked.bin
cat > slop/test/test_hunks.py <<'EOF'
import slop.test

class TestHunks(slop.test.TestCase):
    def test_group_hunks(self):
        assert slop.group_hunks([]) == []
EOF

# Comments
BRANCH=$(git branch --show-current)
mkdir -p ".git/sloppie"
cat > ".git/sloppie/comments.json" <<EOF
[{
  "text": "Rename the module to something less generic.",
  "branch": "$BRANCH",
  "path": null,
  "hunk": null
}, {
  "text": "Splitting a diff into hunks belongs in git.py next to parse_diff, which is the only place that knows what a hunk line looks like. A module of its own for one function is one file too many.",
  "branch": "$BRANCH",
  "path": null,
  "hunk": null
}, {
  "text": "The quote style reformat is unrelated to the rest of the changes here, please pull it out into a commit of its own so that the actual change is reviewable.",
  "branch": "$BRANCH",
  "path": null,
  "hunk": null
}, {
  "text": "The tests cover the empty case only, add one with two hunks and one with a rename header between them.",
  "branch": "hunks",
  "path": null,
  "hunk": null
}, {
  "text": "Leave rename detection out of this, it needs the numstat parsing reworked first.",
  "branch": "hunks",
  "path": null,
  "hunk": null
}]
EOF
