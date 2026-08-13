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

import difflib
import re
import slop

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource
from itertools import accumulate

def find_spans(a, b):
    """Return the character spans that differ between `a` and `b`."""
    # Compare word by word rather than character by character, which
    # would match stray letters shared by two unrelated words and
    # leave the differences scattered over the whole line.
    atokens = re.findall(r"\w+|\W", a)
    btokens = re.findall(r"\w+|\W", b)
    matcher = difflib.SequenceMatcher(None, atokens, btokens)
    if matcher.ratio() < 0.5:
        # Too little in common for the parts that match to mean anything.
        return [], []
    aends = list(accumulate(map(len, atokens), initial=0))
    bends = list(accumulate(map(len, btokens), initial=0))
    aspans, bspans = [], []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal": continue
        # Deletions are empty on one side and insertions on the other.
        if i1 != i2: aspans.append((aends[i1], aends[i2]))
        if j1 != j2: bspans.append((bends[j1], bends[j2]))
    return aspans, bspans

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
        self.add_css_class("monospace")
        self.add_css_class("slop-diff-view")
        self.set_editable(False)
        self.set_cursor_visible(False)
        self.set_show_line_numbers(False)
        self.set_highlight_current_line(False)
        self.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        buffer = self.get_buffer()
        language = GtkSource.LanguageManager.get_default().get_language("diff")
        buffer.set_language(language)
        buffer.set_highlight_syntax(True)
        buffer.set_highlight_matching_brackets(False)
        # The diff language spec tells added and removed lines apart,
        # our style scheme tints them a whole line wide.
        manager = GtkSource.StyleSchemeManager.get_default()
        manager.append_search_path(str(slop.DATA_DIR))
        scheme = manager.get_scheme("sloppie")
        buffer.set_style_scheme(scheme)
        # The word level tints are ours to apply, so they need tags. The
        # scheme sets these as character backgrounds, which is a
        # different property than the whole line paragraph background
        # that the highlighting engine sets, so the two stack.
        for kind in ("added", "removed"):
            style = scheme.get_style(f"slop:refine-{kind}")
            buffer.create_tag(f"refine-{kind}",
                              background=style.get_property("background"))

    def _refine(self, lines):
        """Tint the words that differ between paired changed lines."""
        i = 0
        while i < len(lines):
            if lines[i].kind != "removed":
                i += 1
                continue
            # Pair a run of removed lines with the run of added lines
            # right after it, but only when the two runs are of equal
            # length, which is when the pairing is unambiguous.
            j = i
            while j < len(lines) and lines[j].kind == "removed": j += 1
            k = j
            while k < len(lines) and lines[k].kind == "added": k += 1
            if j - i == k - j:
                for old, new in zip(range(i, j), range(j, k)):
                    # Skip the leading '-' and '+', which always differ.
                    oldspans, newspans = find_spans(
                        lines[old].text[1:], lines[new].text[1:])
                    self._tag(old, oldspans, "refine-removed")
                    self._tag(new, newspans, "refine-added")
            i = k

    def _tag(self, line, spans, name):
        buffer = self.get_buffer()
        for start, end in spans:
            # The spans skipped the leading marker, the buffer has it.
            buffer.apply_tag_by_name(
                name,
                buffer.get_iter_at_line_offset(line, start + 1)[1],
                buffer.get_iter_at_line_offset(line, end + 1)[1])

    def set_diff(self, lines, keep_position=False):
        """Show the parsed diff `lines`, `keep_position` to not scroll to the top."""
        buffer = self.get_buffer()
        text = "\n".join(x.text for x in lines)
        if keep_position and text == buffer.get_text(*buffer.get_bounds(), True):
            # Nothing to redo, and redoing it would only lose the position.
            return
        top = (self.get_line_at_y(self.get_visible_rect().y)[0].get_line()
               if keep_position else 0)
        buffer.set_text(text)
        self._refine(lines)
        for gutter in (self._old_gutter, self._new_gutter):
            gutter.set_lines(lines)
        buffer.place_cursor(buffer.get_iter_at_line(
            min(top, buffer.get_line_count() - 1))[1])
        # Line heights are only computed once idle, so scrolling by iter
        # would be off. Scrolling to a mark defers until they are known.
        self.scroll_to_mark(buffer.get_insert(), 0, True, 0, 0)
