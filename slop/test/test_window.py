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

class TestWindow(slop.test.TestCase):

    def setup_method(self, method):
        self.root = slop.test.new_repository()
        self.window = slop.Window(slop.Repository(self.root))

    def teardown_method(self, method):
        self.window.destroy()

    def test_refresh(self):
        self.window._page.refresh()

    def test_closing_the_task_shown_returns_to_the_dashboard(self):
        # Nothing runs in the terminals of a window never shown, so this
        # is the path that closes without asking anything.
        assert not self.window._page.is_running()
        self.window.lookup_action("close-task").activate(None)
        assert self.window._page is None
        assert not self.window._tasks

    def test_closing_a_task_is_disabled_on_the_dashboard(self):
        assert self.window.lookup_action("close-task").get_enabled()
        self.window._show_dashboard()
        assert not self.window.lookup_action("close-task").get_enabled()

    def test_quitting_asks_nothing_without_tasks(self):
        self.window.close_task(str(self.root))
        # False lets the close go ahead, no question asked.
        assert self.window._on_close_request(self.window) is False

    def test_a_change_is_selected(self):
        assert self.window._page._file_sidebar.get_selected_change() is not None

    def test_selecting_shows_a_diff(self):
        sidebar = self.window._page._file_sidebar
        model = sidebar._selection.get_model()
        buffer = self.window._page._diff_view.get_buffer()
        for i in range(model.get_n_items()):
            sidebar._selection.set_selected(i)
            assert buffer.get_text(*buffer.get_bounds(), False)

    def test_selecting_nothing_clears_the_diff(self):
        self.window._page._file_sidebar._selection.unselect_all()
        buffer = self.window._page._diff_view.get_buffer()
        assert buffer.get_text(*buffer.get_bounds(), False) == ""

    def test_diff_view_position_matches_the_gutter(self):
        sidebar = self.window._page._file_sidebar
        model = sidebar._selection.get_model()
        view = self.window._page._diff_view
        buffer = view.get_buffer()
        for i in range(model.get_n_items()):
            sidebar._selection.set_selected(i)
            for j, line in enumerate(view._lines):
                if line.new is None: continue
                # Column one is the first character of the code, which
                # follows the diff marker and the space after it, both
                # of which the cursor reports as column one too.
                for offset in (1, 2):
                    buffer.place_cursor(buffer.get_iter_at_line_offset(j, offset)[1])
                    assert view.get_position() == (line.new, 1)

    def test_diff_view_line_numbers_match(self):
        sidebar = self.window._page._file_sidebar
        sidebar.select_change(sidebar.get_selected_change())
        buffer = self.window._page._diff_view.get_buffer()
        for gutter in (self.window._page._diff_view._old_gutter,
                       self.window._page._diff_view._new_gutter):
            assert len(gutter.lines) == buffer.get_line_count()
