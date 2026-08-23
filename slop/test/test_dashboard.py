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
import slop.test
import time

from pathlib import Path
from slop import recent

class TestDashboard(slop.test.TestCase):

    def setup_method(self, method):
        # Start from an empty list, the file being shared by the whole
        # run, so that the rows are the ones the test itself puts there
        # and not those left behind by the tests before it.
        recent.PATH.unlink(missing_ok=True)
        # The source repository, the scratch ones of the other tests
        # living under /tmp, which is deliberately not recorded.
        self.root = Path(__file__).parents[2]
        recent.add_repository(self.root)
        # Without a repository the window starts on the dashboard, which
        # lists the recently opened ones, the one just added at the top.
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
        self.window.close_task(str(self.root))
        assert self.window._page is None
        assert not self.window._tasks
        assert self._get_row(0).task is None

    def test_closing_a_task_stops_its_poll(self):
        self._activate_row(0)
        task = self.window._page
        self.window.close_task(str(self.root))
        assert task._poll_source is None

    def test_clearing_a_recent_repository_drops_its_row(self):
        self._get_row(0)._dismiss.emit("clicked")
        assert self.root not in recent.list_repositories()
        assert not [x for x in self._get_rows() if x.path == self.root]

    def test_a_subtask_is_grouped_under_its_parent(self):
        path = self._record_subtask(self.root)
        self.window._update_dashboard()
        # Both rows of the one group, the repository first and the
        # subtask under it, and only the subtask knowing where it came
        # from, which is what gives it a trash button in place of a fork.
        assert [x.path for x in self._get_group(0)] == [self.root, path]
        assert self._get_row(0).parent is None
        assert self._get_row(1).parent == self.root

    def test_a_subtask_of_a_forgotten_parent_stands_on_its_own(self):
        path = self._record_subtask(Path("/nonexistent/repository"))
        self.window._update_dashboard()
        # A group of its own, rather than gone along with the parent.
        assert len(list(self.window._dashboard._box)) == 2
        assert [x.path for x in self._get_group(1)] == [path]
        assert self._get_row(1).parent is None

    def test_an_open_subtask_brings_its_parent_along(self):
        path = self._record_subtask(self.root)
        other = slop.test.new_repository()
        self.window.open_task(str(other))
        self.window.open_task(str(path))
        self.window._show_dashboard()
        # The group is open because the subtask is, so it sorts among
        # the open ones by the name of the repository it was forked
        # from, ahead of the scratch repository opened before it.
        assert [x.path for x in self._get_group(0)] == [self.root, path]
        assert self._get_row(0).task is None
        assert self._get_row(1).task is not None

    def _record_subtask(self, parent):
        """Record a scratch repository as a subtask forked from `parent`."""
        # Written straight to the file, add_repository deliberately not
        # recording the scratch repositories under /tmp at all.
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
        # The list box holding the row is the group's, not the row's.
        row.get_parent().emit("row-activated", row)
