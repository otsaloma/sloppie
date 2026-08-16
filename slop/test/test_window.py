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

from gi.repository import Gtk
from pathlib import Path
from slop import recent

class TestOpenView(slop.test.TestCase):

    def setup_method(self, method):
        # The source repository, the scratch ones of the other tests
        # living under /tmp, which is deliberately not recorded.
        self.root = Path(__file__).parents[2]
        recent.add_repository(self.root)
        # Without a repository the window shows the open button and the
        # recently opened repositories, the one just added at the top.
        self.window = slop.Window()

    def teardown_method(self, method):
        self.window.destroy()

    def test_activating_a_recent_row_opens_it(self):
        listbox = self._find_listbox(self.window.get_child())
        listbox.emit("row-activated", listbox.get_row_at_index(0))
        assert self.window.repository.root == self.root

    def _find_listbox(self, widget):
        if isinstance(widget, Gtk.ListBox): return widget
        for child in widget:
            if found := self._find_listbox(child):
                return found

class TestWindow(slop.test.TestCase):

    def setup_method(self, method):
        self.root = slop.test.new_repository()
        self.window = slop.Window(slop.Repository(self.root))

    def teardown_method(self, method):
        self.window.destroy()

    def test_refresh(self):
        self.window.refresh()

    def test_a_change_is_selected(self):
        assert self.window._file_sidebar.get_selected_change() is not None

    def test_selecting_shows_a_diff(self):
        sidebar = self.window._file_sidebar
        model = sidebar._selection.get_model()
        buffer = self.window._diff_view.get_buffer()
        for i in range(model.get_n_items()):
            sidebar._selection.set_selected(i)
            assert buffer.get_text(*buffer.get_bounds(), False)

    def test_selecting_nothing_clears_the_diff(self):
        self.window._file_sidebar._selection.unselect_all()
        buffer = self.window._diff_view.get_buffer()
        assert buffer.get_text(*buffer.get_bounds(), False) == ""

    def test_diff_view_position_matches_the_gutter(self):
        sidebar = self.window._file_sidebar
        model = sidebar._selection.get_model()
        view = self.window._diff_view
        buffer = view.get_buffer()
        for i in range(model.get_n_items()):
            sidebar._selection.set_selected(i)
            for j, line in enumerate(view._lines):
                if line.new is None: continue
                buffer.place_cursor(buffer.get_iter_at_line_offset(j, 1)[1])
                assert view.get_position() == (line.new, 1)

    def test_diff_view_line_numbers_match(self):
        sidebar = self.window._file_sidebar
        sidebar.select_change(sidebar.get_selected_change())
        buffer = self.window._diff_view.get_buffer()
        for gutter in (self.window._diff_view._old_gutter,
                       self.window._diff_view._new_gutter):
            assert len(gutter.lines) == buffer.get_line_count()
