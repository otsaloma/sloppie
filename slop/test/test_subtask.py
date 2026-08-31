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

import shutil
import slop
import slop.test

from gi.repository import GLib
from slop import subtask

class TestSubtask(slop.test.TestCase):

    def setup_method(self, method):
        self.repository = slop.Repository(slop.test.new_repository())

    def test_slashes_become_dashes_in_the_directory(self):
        directory = subtask.get_directory(self.repository.root, "fix/crash")
        assert directory.name == f"{self.repository.root.name}.fix-crash"
        assert directory.parent == self.repository.root.parent

    def test_an_empty_branch_is_refused(self):
        assert subtask.get_error(self.repository, "  ") == "Enter a branch name"

    def test_an_invalid_branch_is_refused(self):
        assert "not a valid" in subtask.get_error(self.repository, "feature..x")

    def test_an_existing_branch_is_refused(self):
        branch = self.repository.get_branch()
        assert "already exists" in subtask.get_error(self.repository, branch)

    def test_an_existing_directory_is_refused(self):
        subtask.get_directory(self.repository.root, "taken").mkdir()
        assert "already exists" in subtask.get_error(self.repository, "taken")

    def test_a_new_branch_is_accepted(self):
        assert subtask.get_error(self.repository, "feature/new") is None

    def test_a_repository_without_a_default_branch_is_refused(self):
        # Refused here rather than found out after a minute of copying,
        # there being nothing to fork off and no name that would help.
        self.repository._git("branch", "--move", "trunk")
        assert self.repository.get_default_branch() is None
        assert subtask.get_error(self.repository, "feature") == \
            "No main or master branch to fork off"

    def test_forking_copies_the_repository(self):
        directory = self._fork("feature")
        # The whole of the working tree, git directory included, the
        # copy being a repository of its own from the very start.
        assert (directory / ".git").is_dir()
        assert (directory / "modified.txt").is_file()
        assert slop.Repository(directory).root == directory

    def test_forking_shares_the_sloppie_directory(self):
        directory = self._fork("feature")
        link = directory / ".git" / "sloppie"
        # Shared rather than copied, so that comments written in the
        # subtask outlive it, they being written against a branch.
        assert link.is_symlink()
        assert link.resolve() == (self.repository.git_dir / "sloppie").resolve()

    def test_forking_leaves_no_index_lock(self):
        # As copying a repository mid-command would, which would leave
        # the copy unable to run any git command at all.
        (self.repository.git_dir / "index.lock").write_text("", "utf-8")
        directory = self._fork("feature")
        assert not (directory / ".git" / "index.lock").exists()

    def test_forking_leaves_nothing_behind_on_failure(self):
        # Nothing left to copy, which is as good a failure as any.
        shutil.rmtree(self.repository.root)
        directory, error = self._fork("feature", expect_error=True)
        assert error is not None
        # Neither the subtask nor the half-copy it would have been made
        # from, which would look like a subtask at the next start.
        assert not directory.exists()
        assert not directory.with_name(f".{directory.name}.part").exists()

    def test_the_setup_command_creates_the_branch(self):
        command = subtask.get_setup_command("fix/crash")
        assert "git switch -c fix/crash" in command
        # A prompt would block a terminal that nobody is watching yet.
        assert "GIT_TERMINAL_PROMPT=0" in command

    def test_the_setup_command_quotes_the_branch(self):
        # git takes as a branch name a great deal that a shell would
        # rather run: '$', ';' and '&' are all allowed in one.
        branch = "fix-$(id);x"
        assert self.repository.is_valid_branch_name(branch)
        command = subtask.get_setup_command(branch)
        assert "git switch -c 'fix-$(id);x'" in command

    def test_the_setup_command_ends_with_the_configured_one(self):
        command = subtask.get_setup_command("feature", "tools/setup.sh")
        assert command.rstrip().endswith("{ set +x; } 2>/dev/null")
        # After the branch is made and after direnv is allowed, both of
        # which whatever is set up here can count on having happened.
        assert command.index("tools/setup.sh") > command.index("direnv allow")

    def _fork(self, branch, expect_error=False):
        """Fork `branch` and return where it went, waiting for the copy."""
        # The copy runs as a subprocess and reports back through the
        # main loop, which the tests otherwise have no need to run.
        loop = GLib.MainLoop()
        result = []
        def on_forked(directory, error):
            result.extend((directory, error))
            loop.quit()
        subtask.fork(self.repository, branch, on_forked)
        loop.run()
        directory, error = result
        if expect_error:
            return directory, error
        assert error is None
        return directory
