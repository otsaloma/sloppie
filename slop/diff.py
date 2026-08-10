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

import slop

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource

class LineNumberGutter(GtkSource.GutterRendererText):

    """Gutter column showing either the old or the new line numbers."""

    def __init__(self, attribute):
        GObject.GObject.__init__(self)
        # "old" or "new" of slop.DiffLine.
        self.attribute = attribute
        self.lines = []
        self.set_xalign(1)
        self.set_xpad(6)

    def do_query_data(self, lines, line):
        number = None
        if line < len(self.lines):
            number = getattr(self.lines[line], self.attribute)
        self.set_text("" if number is None else str(number), -1)

    def set_lines(self, lines):
        self.lines = lines
        numbers = [getattr(x, self.attribute) or 0 for x in lines]
        # Keep the width constant regardless of which lines are visible.
        width = self.measure(str(max(numbers, default=0)))[0]
        self.set_size_request(width + 2 * self.get_xpad(), -1)
        self.queue_draw()

class DiffView(GtkSource.View):

    """Unified diff of a single file."""

    def __init__(self):
        GObject.GObject.__init__(self)
        self._old_gutter = LineNumberGutter("old")
        self._new_gutter = LineNumberGutter("new")
        self._init_properties()
        self._init_gutter()

    def _init_gutter(self):
        gutter = self.get_gutter(Gtk.TextWindowType.LEFT)
        # Ascending position means left to right.
        gutter.insert(self._old_gutter, 0)
        gutter.insert(self._new_gutter, 1)

    def _init_properties(self):
        self.add_css_class("slop-diff-view")
        self.set_editable(False)
        self.set_cursor_visible(False)
        self.set_show_line_numbers(False)
        self.set_highlight_current_line(False)
        self.set_wrap_mode(Gtk.WrapMode.NONE)
        buffer = self.get_buffer()
        language = GtkSource.LanguageManager.get_default().get_language("diff")
        buffer.set_language(language)
        buffer.set_highlight_syntax(True)
        buffer.set_highlight_matching_brackets(False)
        # The diff language spec tells added and removed lines apart,
        # our style scheme tints them a whole line wide.
        manager = GtkSource.StyleSchemeManager.get_default()
        manager.append_search_path(str(slop.DATA_DIR))
        buffer.set_style_scheme(manager.get_scheme("slop-review"))

    def set_diff(self, lines):
        """Show the parsed diff `lines`."""
        buffer = self.get_buffer()
        buffer.set_text("\n".join(x.text for x in lines))
        for gutter in (self._old_gutter, self._new_gutter):
            gutter.set_lines(lines)
        buffer.place_cursor(buffer.get_start_iter())
