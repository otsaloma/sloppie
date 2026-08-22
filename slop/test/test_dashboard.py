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

from pathlib import Path
from slop import recent

class TestDashboard(slop.test.TestCase):

    def setup_method(self, method):
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
        assert self._get_card(0).path == self.root
        assert self._get_card(0).task is None

    def test_activating_a_card_opens_it(self):
        self._activate_card(0)
        assert self.window._page.repository.root == self.root

    def test_an_open_task_is_listed_first_and_undimmed(self):
        self._activate_card(0)
        assert self._get_card(0).path == self.root
        assert self._get_card(0).task is not None
        assert not self._get_card(0).has_css_class("slop-task-recent")

    def test_activating_an_open_task_shows_it_again(self):
        self._activate_card(0)
        task = self.window._page
        self.window._show_dashboard()
        self._activate_card(0)
        assert self.window._page is task
        assert len(self.window._tasks) == 1

    def test_closing_a_task_returns_to_the_dashboard(self):
        self._activate_card(0)
        self.window.close_task(str(self.root))
        assert self.window._page is None
        assert not self.window._tasks
        assert self._get_card(0).task is None

    def test_closing_a_task_stops_its_poll(self):
        self._activate_card(0)
        task = self.window._page
        self.window.close_task(str(self.root))
        assert task._poll_source is None

    def test_forgetting_a_recent_repository_drops_its_card(self):
        self._get_card(0)._close.emit("clicked")
        assert self.root not in recent.list_repositories()
        assert not [x for x in self.window._dashboard._box if x.path == self.root]

    def _get_card(self, index):
        return list(self.window._dashboard._box)[index]

    def _activate_card(self, index):
        card = self._get_card(index)
        card._listbox.emit("row-activated", card._row)
