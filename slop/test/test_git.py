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

from slop.git import FileChange
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

    def test_header_is_dropped(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/x",
            "index 1234567..89abcde 100644",
            "--- a/x",
            "+++ b/x",
            "@@ -1 +1 @@",
            "-a",
            "+b",
        )))
        assert [x.kind for x in lines] == ["hunk", "removed", "added"]

    def test_mode_change_is_described(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/x",
            "old mode 100644",
            "new mode 100755",
        )))
        assert [x.text for x in lines] == ["Permissions changed from 644 to 755"]

    def test_rename_is_described(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/y",
            "similarity index 100%",
            "rename from x",
            "rename to y",
        )))
        assert [x.text for x in lines] == ["Renamed from x to y"]

    def test_rename_with_changes_is_described(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/y",
            "similarity index 90%",
            "rename from x",
            "rename to y",
            "old mode 100644",
            "new mode 100755",
            "index 1234567..89abcde",
            "--- a/x",
            "+++ b/y",
            "@@ -1 +1 @@",
            "-a",
            "+b",
        )))
        assert [x.text for x in lines] == [
            "Renamed from x to y",
            "Permissions changed from 644 to 755",
            "@@ -1 +1 @@",
            "-a",
            "+b",
        ]

    def test_copy_is_described(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/y",
            "similarity index 100%",
            "copy from x",
            "copy to y",
        )))
        assert [x.text for x in lines] == ["Copied from x to y"]

    def test_empty_file_added_is_described(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/x",
            "new file mode 100644",
            "index 0000000..e69de29",
        )))
        assert [x.text for x in lines] == ["Empty file added"]

    def test_empty_file_deleted_is_described(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/x",
            "deleted file mode 100644",
            "index e69de29..0000000",
        )))
        assert [x.text for x in lines] == ["Empty file deleted"]

    def test_file_added_is_not_described(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/x",
            "new file mode 100644",
            "index 0000000..89abcde",
            "--- /dev/null",
            "+++ b/x",
            "@@ -0,0 +1 @@",
            "+a",
        )))
        assert [x.text for x in lines] == ["@@ -0,0 +1 @@", "+a"]

    def test_second_file_header_is_dropped(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/x",
            "--- a/x",
            "+++ b/x",
            "@@ -1 +1 @@",
            "-a",
            "+b",
            "diff --git a/y b/y",
            "--- a/y",
            "+++ b/y",
            "@@ -1 +1 @@",
            "-c",
            "+d",
        )))
        assert [x.kind for x in lines] == ["hunk", "removed", "added"] * 2

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

    def test_binary_changed(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/x",
            "index 1234567..89abcde 100644",
            "Binary files a/x and b/x differ",
        )))
        assert [x.text for x in lines] == ["Binary file changed"]

    def test_binary_added(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/x",
            "new file mode 100644",
            "index 0000000..89abcde",
            "Binary files /dev/null and b/x differ",
        )))
        assert [x.text for x in lines] == ["Binary file added"]

    def test_binary_deleted(self):
        lines = parse_diff("\n".join((
            "diff --git a/x b/x",
            "deleted file mode 100644",
            "index 1234567..0000000",
            "Binary files a/x and /dev/null differ",
        )))
        assert [x.text for x in lines] == ["Binary file deleted"]

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
            "binary.bin", "deleted-staged.txt", "modified.txt", "renamed-to.txt"]

    def test_unstaged(self):
        assert [x.path for x in self.changes["unstaged"]] == [
            "deleted-unstaged.txt", "modified.txt"]

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

    def test_deletion_status(self):
        assert self.get_change("staged", "deleted-staged.txt").status == "D"
        assert self.get_change("unstaged", "deleted-unstaged.txt").status == "D"

    def test_deletion_counts(self):
        change = self.get_change("staged", "deleted-staged.txt")
        assert (change.added, change.removed) == (0, 2)

    def test_deletion_diff_is_all_removals(self):
        # A deletion has hunks like any other change, so its header says
        # nothing that the hunks don't and is dropped whole.
        change = self.get_change("staged", "deleted-staged.txt")
        lines = parse_diff(self.repository.get_diff(change))
        assert [x.kind for x in lines] == ["hunk", "removed", "removed"]
        assert [x.text for x in lines[1:]] == ["-gone", "-away"]

    def test_deletion_line_numbers(self):
        # Nothing of a deleted file is left to number as new.
        change = self.get_change("unstaged", "deleted-unstaged.txt")
        lines = parse_diff(self.repository.get_diff(change))
        assert [(x.old, x.new) for x in lines[1:]] == [(1, None), (2, None)]

    def test_stage_deletion(self):
        # 'git add' of a path that is gone stages its removal.
        self.repository.stage(self.get_change("unstaged", "deleted-unstaged.txt"))
        changes = self.repository.list_changes()
        assert "deleted-unstaged.txt" not in [x.path for x in changes["unstaged"]]
        assert [x.status for x in changes["staged"]
                if x.path == "deleted-unstaged.txt"] == ["D"]

    def test_unstage_deletion(self):
        # The file stays gone, only the deletion leaves the index.
        self.repository.unstage(self.get_change("staged", "deleted-staged.txt"))
        changes = self.repository.list_changes()
        assert "deleted-staged.txt" not in [x.path for x in changes["staged"]]
        assert [x.status for x in changes["unstaged"]
                if x.path == "deleted-staged.txt"] == ["D"]

    def test_revert_deletion(self):
        # Reverting a deletion is the one revert that brings a file back.
        self.repository.revert(self.get_change("unstaged", "deleted-unstaged.txt"))
        assert (self.root / "deleted-unstaged.txt").read_text() == "gone\ntoo\n"
        assert "deleted-unstaged.txt" not in [
            x.path for x in self.repository.list_changes()["unstaged"]]

    def test_untracked_diff_is_an_addition(self):
        change = self.get_change("untracked", "untracked.txt")
        lines = parse_diff(self.repository.get_diff(change))
        assert [x.text for x in lines if x.kind == "added"] == ["+new"]

    def test_unstaged_diff_differs_from_staged(self):
        staged = self.repository.get_diff(self.get_change("staged", "modified.txt"))
        unstaged = self.repository.get_diff(self.get_change("unstaged", "modified.txt"))
        assert staged != unstaged
        assert "No newline at end of file" in unstaged

    def test_stage(self):
        self.repository.stage(self.get_change("unstaged", "modified.txt"))
        assert "modified.txt" not in [
            x.path for x in self.repository.list_changes()["unstaged"]]

    def test_stage_untracked(self):
        self.repository.stage(self.get_change("untracked", "untracked.txt"))
        changes = self.repository.list_changes()
        assert not changes["untracked"]
        assert "untracked.txt" in [x.path for x in changes["staged"]]

    def test_unstage(self):
        self.repository.unstage(self.get_change("staged", "modified.txt"))
        assert "modified.txt" not in [
            x.path for x in self.repository.list_changes()["staged"]]

    def test_unstage_rename(self):
        # Both halves of the rename need to leave the index.
        self.repository.unstage(self.get_change("staged", "renamed-to.txt"))
        changes = self.repository.list_changes()
        assert "renamed-to.txt" not in [x.path for x in changes["staged"]]
        assert "renamed-to.txt" in [x.path for x in changes["untracked"]]

    def test_revert(self):
        self.repository.revert(self.get_change("unstaged", "modified.txt"))
        assert "modified.txt" not in [
            x.path for x in self.repository.list_changes()["unstaged"]]

    def test_has_staged_changes(self):
        assert self.repository.has_staged_changes()
        self.repository.commit("Add a thing")
        assert not self.repository.has_staged_changes()

    def test_commit(self):
        self.repository.commit("Add a thing")
        assert not self.repository.list_changes()["staged"]
        assert self.repository.get_last_message() == "Add a thing"

    def test_commit_amend(self):
        self.repository.commit("Add a thing")
        self.repository.commit("Add a thing, amended", amend=True)
        assert self.repository.get_last_message() == "Add a thing, amended"
        # Amending rewrites the commit rather than adding one.
        assert self.repository._git("rev-list", "--count", "HEAD").strip() == "2"

    def test_commit_nothing_staged(self):
        self.repository.commit("Add a thing")
        try:
            self.repository.commit("Add a thing again")
        except RuntimeError as error:
            # Explained by git on stdout, stderr being empty.
            assert "no changes added to commit" in str(error)
            return
        raise AssertionError("expected RuntimeError")

    def test_not_a_repository(self):
        try:
            slop.Repository("/")
        except RuntimeError:
            return
        raise AssertionError("expected RuntimeError")

class TestConflict(slop.test.TestCase):

    def setup_method(self, method):
        self.root = slop.test.new_repository("conflict")
        self.repository = slop.Repository(self.root)
        self.changes = self.repository.list_changes()

    def get_change(self, section, path):
        for change in self.changes[section]:
            if change.path == path:
                return change
        raise AssertionError(f"{path} not found in {section}")

    def test_sections(self):
        assert [x.path for x in self.changes["staged"]] == [
            "added-by-other.txt", "conflict.txt"]
        assert [x.path for x in self.changes["unstaged"]] == ["conflict.txt"]
        assert not self.changes["untracked"]

    def test_unmerged_status(self):
        # An unmerged file is listed as modified as well, which says
        # nothing of the conflict and must not be what shows.
        assert self.get_change("staged", "conflict.txt").status == "U"
        assert self.get_change("unstaged", "conflict.txt").status == "U"

    def test_merged_file_is_staged(self):
        # The half of the merge that went cleanly is staged as usual.
        assert self.get_change("staged", "added-by-other.txt").status == "A"

    def test_staged_diff_is_described(self):
        # There is no diff to show of an unmerged file, so the reason
        # has to be said in its place, rather than showing nothing.
        change = self.get_change("staged", "conflict.txt")
        lines = parse_diff(self.repository.get_diff(change))
        assert [x.text for x in lines] == ["Unmerged file with conflicts to resolve"]

    def test_unstaged_diff_shows_the_whole_file(self):
        # A conflict comes as a combined diff, which has two columns of
        # markers rather than one, and has the conflict markers among
        # its lines. All of the file is to be there and nothing else.
        change = self.get_change("unstaged", "conflict.txt")
        lines = parse_diff(self.repository.get_diff(change))
        assert lines[0].kind == "hunk"
        assert lines[0].text.startswith("@@@ ")
        assert [x.text[2:] for x in lines[1:]] == (
            self.root / "conflict.txt").read_text().rstrip("\n").split("\n")

    def test_commit_is_refused(self):
        # git will not commit with a path left unmerged, which needs to
        # arrive as an error rather than as a commit that never was.
        try:
            self.repository.commit("Merge other")
        except RuntimeError as error:
            assert "unmerged files" in str(error)
            return
        raise AssertionError("expected RuntimeError")

class TestGetFingerprint(slop.test.TestCase):

    def setup_method(self, method):
        self.root = slop.test.new_repository()
        self.repository = slop.Repository(self.root)
        self.fingerprint = self.repository.get_fingerprint()

    def assert_changed(self):
        assert self.repository.get_fingerprint() != self.fingerprint

    def assert_status_unchanged(self, function):
        # Run `function` and check that it left the status as it was, so
        # that the fingerprint has only the modification times to go by.
        before = self.repository._git("status", "--porcelain")
        function()
        assert self.repository._git("status", "--porcelain") == before

    def test_nothing_changed(self):
        # A fingerprint that changed on its own would have the window
        # reload on every poll, for as long as it is open.
        assert self.repository.get_fingerprint() == self.fingerprint

    def test_tracked_file_edited(self):
        # A file that is already modified stays modified, so nothing of
        # the status says that it was edited again.
        path = self.root / "modified.txt"
        self.assert_status_unchanged(lambda: path.write_text("a\nB\nc\nd\nE"))
        self.assert_changed()

    def test_untracked_file_edited(self):
        path = self.root / "untracked.txt"
        self.assert_status_unchanged(lambda: path.write_text("newer\n"))
        self.assert_changed()

    def test_renamed_file_edited(self):
        # The record of a rename carries the old path as one more field,
        # past which the walk needs to find the new path, that being the
        # one that exists to have a modification time.
        self.assert_status_unchanged((self.root / "renamed-to.txt").touch)
        self.assert_changed()

    def test_file_added(self):
        (self.root / "added.txt").write_text("new\n")
        self.assert_changed()

    def test_file_edited_in_an_untracked_directory(self):
        # An untracked directory is reported as the directory alone
        # unless all the untracked files are asked for by name. Editing
        # a file leaves the modification time of its directory alone,
        # so the directory is no substitute for the files in it.
        (self.root / "sub").mkdir()
        path = self.root / "sub" / "a.txt"
        path.write_text("a\n")
        self.fingerprint = self.repository.get_fingerprint()
        self.assert_status_unchanged(lambda: path.write_text("aa\n"))
        self.assert_changed()

    def test_file_deleted(self):
        (self.root / "untracked.txt").unlink()
        self.assert_changed()

    def test_file_staged(self):
        self.repository.stage(FileChange("untracked", "untracked.txt",
                                         "A", None, 1, 0))
        self.assert_changed()

    def test_file_unstaged(self):
        self.repository.unstage(FileChange("staged", "modified.txt",
                                           "M", None, 2, 1))
        self.assert_changed()

    def test_committed(self):
        self.repository.commit("Add a thing")
        self.assert_changed()

    def test_branch_switched(self):
        # Nothing about the files changes, only the branch they are on,
        # which is what the status header is included for.
        self.repository._git("checkout", "--quiet", "-b", "other")
        self.assert_changed()

    def test_ignored_file(self):
        # Ignored files are not listed and thus not watched either,
        # without which build output alone would keep the window
        # reloading.
        (self.root / ".gitignore").write_text("*.log\n")
        self.repository._git("add", "--", ".gitignore")
        self.fingerprint = self.repository.get_fingerprint()
        (self.root / "ignored.log").write_text("noise\n")
        assert self.repository.get_fingerprint() == self.fingerprint
