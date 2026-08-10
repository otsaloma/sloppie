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

import slop.test

from slop.git import parse_diff

class TestParseDiff(slop.test.TestCase):

    def test_line_numbers(self):
        lines = parse_diff("\n".join((
            "@@ -10,4 +20,4 @@ def main():",
            " context",
            "-removed",
            "+added",
            " tail",
        )))
        assert [(x.kind, x.old, x.new) for x in lines] == [
            ("hunk", None, None),
            ("context", 10, 20),
            ("removed", 11, None),
            ("added", None, 21),
            ("context", 12, 22),
        ]

    def test_header_is_meta(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/x",
            "index 1234567..89abcde 100644",
            "--- a/x",
            "+++ b/x",
            "@@ -1 +1 @@",
            "-a",
            "+b",
        )))
        assert [x.kind for x in lines[:4]] == ["meta"] * 4

    def test_no_newline_at_end_of_file(self):
        lines = parse_diff("\n".join((
            "@@ -1 +1 @@",
            "-a",
            "+b",
            "\\ No newline at end of file",
        )))
        assert lines[-1].kind == "nonewline"
        assert lines[-1].old is None
        assert lines[-1].new is None

    def test_binary(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/x",
            "index 1234567..89abcde 100644",
            "Binary files a/x and b/x differ",
        )))
        assert [x.kind for x in lines] == ["meta"] * 3

    def test_empty(self):
        assert parse_diff("") == []

class TestRepository(slop.test.TestCase):

    def setup_method(self, method):
        self.root = slop.test.new_repository()
        self.repository = slop.Repository(self.root)
        self.changes = self.repository.list_changes()

    def get_change(self, section, path):
        for change in self.changes[section]:
            if change.path == path:
                return change
        raise AssertionError(f"{path} not found in {section}")

    def test_root(self):
        assert self.repository.root == self.root.resolve()

    def test_staged(self):
        assert sorted(x.path for x in self.changes["staged"]) == [
            "binary.bin", "modified.txt", "renamed-to.txt"]

    def test_unstaged(self):
        assert [x.path for x in self.changes["unstaged"]] == ["modified.txt"]

    def test_untracked(self):
        assert [x.path for x in self.changes["untracked"]] == ["untracked.txt"]

    def test_binary_has_no_counts(self):
        change = self.get_change("staged", "binary.bin")
        assert change.added is None
        assert change.removed is None

    def test_rename_keeps_old_path(self):
        change = self.get_change("staged", "renamed-to.txt")
        assert change.status == "R"
        assert change.old_path == "renamed-from.txt"

    def test_rename_diff_is_a_rename(self):
        change = self.get_change("staged", "renamed-to.txt")
        # Without the old path git would report this as a new file.
        assert "rename from renamed-from.txt" in self.repository.get_diff(change)

    def test_counts(self):
        change = self.get_change("staged", "modified.txt")
        assert (change.added, change.removed) == (2, 1)

    def test_untracked_diff_is_an_addition(self):
        change = self.get_change("untracked", "untracked.txt")
        lines = parse_diff(self.repository.get_diff(change))
        assert [x.text for x in lines if x.kind == "added"] == ["+new"]

    def test_unstaged_diff_differs_from_staged(self):
        staged = self.repository.get_diff(self.get_change("staged", "modified.txt"))
        unstaged = self.repository.get_diff(self.get_change("unstaged", "modified.txt"))
        assert staged != unstaged
        assert "No newline at end of file" in unstaged

    def test_not_a_repository(self):
        try:
            slop.Repository("/")
        except RuntimeError:
            return
        raise AssertionError("expected RuntimeError")
