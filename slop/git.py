# -*- coding: utf-8 -*-

# Copyright (C) 2026 Osmo Salomaa
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import re
import subprocess

from gi.repository import GObject
from pathlib import Path

# Sections in the order they are shown in the sidebar.
SECTIONS = ["staged", "unstaged", "untracked"]
SECTION_TITLES = {"staged": "Staged", "unstaged": "Unstaged", "untracked": "Untracked"}

class DiffLine:

    """One line of a unified diff, with the line numbers it maps to."""

    __slots__ = ("kind", "old", "new", "text")

    def __init__(self, kind, old, new, text):
        # kind is one of: meta, hunk, context, added, removed, nonewline.
        self.kind = kind
        self.old = old
        self.new = new
        self.text = text

class FileChange(GObject.Object):

    """One file changed in one section, as listed in the sidebar."""

    def __init__(self, section, path, status, old_path, added, removed):
        GObject.GObject.__init__(self)
        self.section = section
        self.path = path
        # Single letter as given by git: A, M, D, R, C, T, U.
        self.status = status
        # Set only for renames and copies, needed to diff them as such.
        self.old_path = old_path
        # None for binary files, which have no line counts.
        self.added = added
        self.removed = removed

    @property
    def name(self):
        return Path(self.path).name

    @property
    def directory(self):
        parent = str(Path(self.path).parent)
        return "" if parent == "." else parent

def parse_diff(text):
    """Parse unified diff `text` into a list of `DiffLine`."""
    lines = []
    old = new = 0
    for line in text.split("\n"):
        if match := re.match(r"^@@+ (?:[-+][0-9,]+ )+@@", line):
            # Take the last two ranges, so that combined diffs
            # of a merge conflict are handled as old vs. new.
            ranges = re.findall(r"[-+](\d+)(?:,\d+)?", match.group(0))
            old, new = int(ranges[-2]), int(ranges[-1])
            lines.append(DiffLine("hunk", None, None, line))
        elif not lines or lines[-1].kind == "meta":
            # Everything before the first hunk is a header.
            lines.append(DiffLine("meta", None, None, line))
        elif line.startswith("\\"):
            lines.append(DiffLine("nonewline", None, None, line))
        elif line.startswith("-"):
            lines.append(DiffLine("removed", old, None, line))
            old += 1
        elif line.startswith("+"):
            lines.append(DiffLine("added", None, new, line))
            new += 1
        elif line.startswith(" ") or not line:
            lines.append(DiffLine("context", old, new, line))
            old += 1
            new += 1
        else:
            # A second file's header in a multi-file diff.
            lines.append(DiffLine("meta", None, None, line))
    while lines and not lines[-1].text:
        # Drop the trailing newline of the diff itself.
        lines.pop()
    return lines

class Repository:

    def __init__(self, path="."):
        self.root = Path(self._git(
            "rev-parse", "--show-toplevel", cwd=path).strip())

    def _git(self, *args, cwd=None, ok_codes=(0,)):
        # Suppress external diff drivers and color, which would both
        # render the output unparseable. Everything else is left to
        # the user's git configuration, so that what we show matches
        # what 'git diff' shows in a terminal.
        command = ["git", "--no-pager", "-c", "color.ui=never", *args]
        process = subprocess.run(command,
                                 cwd=str(cwd or self.root),
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)

        if process.returncode not in ok_codes:
            error = process.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"{' '.join(command)}: {error}")
        return process.stdout.decode("utf-8", errors="replace")

    def _parse_numstat(self, output):
        # Records are 'added\tremoved\tpath\0', except for renames and
        # copies, where the path is empty and followed by the old and
        # the new path as two more fields. Binary files have '-' counts.
        stats = {}
        fields = output.split("\0")
        i = 0
        while i < len(fields):
            if not fields[i]:
                i += 1
                continue
            added, removed, path = fields[i].split("\t", 2)
            i += 1
            if not path:
                path = fields[i+1]
                i += 2
            binary = added == "-"
            stats[path] = (None, None) if binary else (int(added), int(removed))
        return stats

    def _parse_name_status(self, output):
        # Records are 'status\0path\0', except for renames and copies,
        # where the status is followed by the old and the new path.
        statuses = {}
        fields = [x for x in output.split("\0") if x]
        i = 0
        while i < len(fields):
            status = fields[i]
            i += 1
            if status[0] in ("R", "C"):
                statuses[fields[i+1]] = (status[0], fields[i])
                i += 2
            else:
                statuses[fields[i]] = (status[0], None)
                i += 1
        return statuses

    def _diff(self, *args, **kwargs):
        # External diff drivers would render the output unparseable.
        return self._git("diff", "--no-ext-diff", *args, **kwargs)

    def _list_diff_changes(self, section, *args):
        stats = self._parse_numstat(self._diff(*args, "--numstat", "-z"))
        statuses = self._parse_name_status(self._diff(*args, "--name-status", "-z"))
        return [FileChange(section, path, *statuses.get(path, ("M", None)), *stats[path])
                for path in sorted(stats)]

    def _list_untracked_changes(self):
        changes = []
        output = self._git("ls-files", "--others", "--exclude-standard", "-z")
        for path in sorted(x for x in output.split("\0") if x):
            # There is no cheaper way to get a line count for an
            # untracked file that agrees with git on what is binary.
            stats = self._parse_numstat(self._diff(
                "--no-index", "--numstat", "-z", "--", "/dev/null", path,
                ok_codes=(0, 1)))
            counts = stats.get(path, (None, None))
            changes.append(FileChange("untracked", path, "A", None, *counts))
        return changes

    def list_changes(self):
        """Return changed files in all sections."""
        return {
            "staged": self._list_diff_changes("staged", "--cached"),
            "unstaged": self._list_diff_changes("unstaged"),
            "untracked": self._list_untracked_changes(),
        }

    def get_diff(self, change):
        """Return the unified diff of `change` as text."""
        if change.section == "untracked":
            # An untracked file has nothing to diff against, but git can
            # still render it as an addition against an empty file.
            return self._diff("--no-index", "--", "/dev/null", change.path,
                              ok_codes=(0, 1))
        args = ["--cached"] if change.section == "staged" else []
        # Renames and copies are only detected as such when git is given
        # both paths; with the new path alone it looks like a new file.
        paths = [change.old_path, change.path] if change.old_path else [change.path]
        return self._diff(*args, "--", *paths)
