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

import json
import shutil
import slop.dashboard
import slop.test
import time

from contextlib import contextmanager
from gi.repository import Gio
from gi.repository import GLib
from pathlib import Path
from slop import recent
from unittest.mock import patch

class TestDashboard(slop.test.TestCase):

    def setup_method(self, method):
        # The file is shared by the whole run.
        recent.PATH.unlink(missing_ok=True)
        # Not a scratch repository, those under /tmp are not recorded.
        self.root = Path(__file__).parents[2]
        recent.add_repository(self.root)
        self.window = slop.Window()

    def teardown_method(self, method):
        self.window.destroy()

    def test_a_recent_repository_is_listed(self):
        assert self._get_row(0).path == self.root
        assert self._get_row(0).task is None

    def test_activating_a_row_opens_it(self):
        self._activate_row(0)
        assert self.window._page.repository.root == self.root

    def test_an_open_task_is_listed_first_and_undimmed(self):
        self._activate_row(0)
        assert self._get_row(0).path == self.root
        assert self._get_row(0).task is not None
        assert not self._get_row(0).has_css_class("slop-task-recent")

    def test_activating_an_open_task_shows_it_again(self):
        self._activate_row(0)
        task = self.window._page
        self.window._show_dashboard()
        self._activate_row(0)
        assert self.window._page is task
        assert len(self.window._tasks) == 1

    def test_closing_a_task_returns_to_the_dashboard(self):
        self._activate_row(0)
        self.window.close_task(self.root)
        assert self.window._page is None
        assert not self.window._tasks
        assert self._get_row(0).task is None

    def test_closing_a_task_stops_its_poll(self):
        self._activate_row(0)
        task = self.window._page
        self.window.close_task(self.root)
        assert task._poll_source is None

    def test_clearing_a_recent_repository_drops_its_row(self):
        self._get_row(0)._dismiss.emit("clicked")
        assert self.root not in recent.list_repositories()
        assert not [x for x in self._get_rows() if x.path == self.root]

    def test_a_subtask_is_grouped_under_its_parent(self):
        path = self._record_subtask(self.root)
        self.window._update_dashboard()
        assert [x.path for x in self._get_group(0)] == [self.root, path]
        assert self._get_row(0).parent is None
        assert self._get_row(1).parent == self.root

    def test_a_subtask_of_a_forgotten_parent_stands_on_its_own(self):
        path = self._record_subtask(Path("/nonexistent/repository"))
        self.window._update_dashboard()
        assert len(list(self.window._dashboard._box)) == 2
        assert [x.path for x in self._get_group(1)] == [path]
        assert self._get_row(1).parent is None

    def test_an_open_subtask_brings_its_parent_along(self):
        path = self._record_subtask(self.root)
        other = slop.test.new_repository()
        self.window.open_task(other)
        self.window.open_task(path)
        self.window._show_dashboard()
        # Open by way of the subtask, the group sorts by the name of the
        # repository, ahead of the scratch repository opened before it.
        assert [x.path for x in self._get_group(0)] == [self.root, path]
        assert self._get_row(0).task is None
        assert self._get_row(1).task is not None

    def test_a_valid_branch_is_forked(self):
        popover = slop.dashboard.SubtaskPopover(self.root)
        forked = []
        popover.connect("forked", lambda popover, branch: forked.append(branch))
        popover._entry.set_text("  feature/new  ")
        popover._entry.emit("activate")
        assert forked == ["feature/new"]

    def test_an_invalid_branch_says_why(self):
        popover = slop.dashboard.SubtaskPopover(self.root)
        forked = []
        popover.connect("forked", lambda popover, branch: forked.append(branch))
        popover._entry.set_text("feature..new")
        popover._entry.emit("activate")
        assert not forked
        assert popover._error.get_visible()
        assert "not a valid" in popover._error.get_label()

    def test_a_pending_subtask_is_shown_under_its_parent(self):
        path = self.root.with_name(f"{self.root.name}.wip")
        self.window._dashboard.add_pending(path, self.root, "wip")
        assert [x.path for x in self._get_group(0)] == [self.root, path]
        row = self._get_row(1)
        assert isinstance(row, slop.dashboard.PendingRow)
        row.get_parent().emit("row-activated", row)
        assert self.window._page is None
        self.window._dashboard.remove_pending(path)
        assert [x.path for x in self._get_group(0)] == [self.root]

    def test_trashing_a_subtask_drops_it(self):
        path = self._record_subtask(self.root)
        self.window._update_dashboard()
        with self._trash_to(shutil.rmtree) as trashed:
            self.window.trash_task(path)
        assert trashed == [str(path)]
        assert not path.exists()
        assert path not in recent.list_repositories()
        assert [x.path for x in self._get_group(0)] == [self.root]

    def test_trashing_an_open_subtask_closes_it_first(self):
        path = self._record_subtask(self.root)
        self.window.open_task(path)
        with self._trash_to(shutil.rmtree):
            self.window.trash_task(path)
        assert not self.window._tasks
        assert self.window._page is None

    def test_a_subtask_that_would_not_go_stays(self):
        path = self._record_subtask(self.root)
        self.window._update_dashboard()
        def refuse(path):
            raise RuntimeError("Trashing on system internal mounts")
        with self._trash_to(refuse):
            self.window.trash_task(path)
        assert path.exists()
        assert path in recent.list_repositories()
        assert [x.path for x in self._get_group(0)] == [self.root, path]

    def test_teardown_runs_in_the_subtask_before_trashing(self):
        path = self._record_subtask(self.root)
        (path / "venv").mkdir()
        (path / "venv" / "dependency").touch()
        slop.Config(slop.Repository(path)).write_item(
            "teardown-command", "rm -rf venv")
        self.window.open_task(path)
        def move(path):
            assert not self.window._tasks
            assert not (path / "venv").exists()
            assert (path / ".git").is_dir()
            shutil.rmtree(path)
        with self._trash_to(move) as trashed:
            self.window.trash_task(path)
            self._wait_for_trash(path)
        assert trashed == [str(path)]
        assert path not in recent.list_repositories()

    def test_failed_teardown_keeps_the_subtask_and_shows_output(self):
        path = self._record_subtask(self.root)
        slop.Config(slop.Repository(path)).write_item(
            "teardown-command", "echo cleanup-failed >&2; exit 1")
        with self._trash_to(shutil.rmtree) as trashed, \
                patch("slop.util.show_error") as show_error:
            self.window.trash_task(path)
            self._wait_for_trash(path)
        assert not trashed
        assert path.exists()
        assert path in recent.list_repositories()
        assert "cleanup-failed" in str(show_error.call_args.args[2])
        assert self._get_row(1).get_sensitive()

    def test_teardown_cannot_be_started_twice_or_reopened(self):
        path = self._record_subtask(self.root)
        slop.Config(slop.Repository(path)).write_item("teardown-command", "true")
        with self._trash_to(shutil.rmtree) as trashed:
            self.window.trash_task(path)
            assert path in self.window._trashing
            assert not self._get_row(1).get_sensitive()
            self.window.trash_task(path)
            self.window.open_task(path)
            assert not self.window._tasks
            self._wait_for_trash(path)
        assert trashed == [str(path)]

    def _wait_for_trash(self, path):
        deadline = time.monotonic() + 5
        while path in self.window._trashing:
            assert time.monotonic() < deadline
            GLib.MainContext.default().iteration(False)
            time.sleep(0.001)

    @contextmanager
    def _trash_to(self, action):
        """Run the body with Gio.File.trash replaced by `action`."""
        # GLib refuses to trash from /tmp, a system internal mount.
        trashed = []
        def trash(file, cancellable):
            path = file.get_path()
            trashed.append(path)
            action(Path(path))
        with patch.object(Gio.File, "trash", trash):
            yield trashed

    def _record_subtask(self, parent):
        """Record a scratch repository as a subtask forked from `parent`."""
        # Written directly, as add_repository skips /tmp.
        path = slop.test.new_repository()
        items = json.loads(recent.PATH.read_text("utf-8"))
        items.append({"path": str(path),
                      "time": round(time.time()) - 1,
                      "parent": str(parent)})

        recent.PATH.write_text(json.dumps(items), "utf-8")
        return path

    def _get_group(self, index):
        """Return the rows of the group at `index`."""
        return list(list(self.window._dashboard._box)[index]._listbox)

    def _get_rows(self):
        """Return the rows of all the groups, in the order shown."""
        return [row for group in self.window._dashboard._box
                for row in group._listbox]

    def _get_row(self, index):
        return self._get_rows()[index]

    def _activate_row(self, index):
        row = self._get_row(index)
        row.get_parent().emit("row-activated", row)
