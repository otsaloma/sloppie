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

class TestRecent(slop.test.TestCase):

    def setup_method(self, method):
        # The source repository, the scratch ones of the other tests
        # living under /tmp, which is deliberately not recorded.
        self.root = Path(__file__).parents[2]
        recent.add_repository(self.root)

    def test_the_repository_added_is_first(self):
        assert recent.list_repositories()[0] == self.root

    def test_adding_again_does_not_duplicate(self):
        recent.add_repository(self.root)
        paths = recent.list_repositories()
        assert paths.count(self.root) == 1

    def test_the_repository_removed_is_gone(self):
        recent.remove_repository(self.root)
        assert self.root not in recent.list_repositories()

    def test_old_repositories_are_forgotten(self):
        items = json.loads(recent.PATH.read_text("utf-8"))
        for item in items:
            item["time"] = round(time.time() - 15 * 86400)
        recent.PATH.write_text(json.dumps(items), "utf-8")
        assert recent.list_repositories() == []

    def test_removed_repositories_are_skipped(self):
        path = Path("/nonexistent/repository")
        recent.add_repository(path)
        assert path not in recent.list_repositories()

    def test_temporary_repositories_are_not_recorded(self):
        path = slop.test.new_repository()
        recent.add_repository(path)
        assert path not in recent.list_repositories()

    def test_a_repository_has_no_parent(self):
        assert self.root not in recent.list_parents()

    def test_a_subtask_has_the_parent_it_was_forked_from(self):
        path = Path("/nonexistent/repository.feature")
        recent.add_repository(path, parent=self.root)
        assert recent.list_parents()[path] == self.root

    def test_reopening_a_subtask_keeps_its_parent(self):
        path = Path("/nonexistent/repository.feature")
        recent.add_repository(path, parent=self.root)
        recent.add_repository(path)
        assert recent.list_parents()[path] == self.root
