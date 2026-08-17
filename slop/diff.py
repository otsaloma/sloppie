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

from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource
from gi.repository import Pango
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
        self._lines = []
        self._old_gutter = LineNumberGutter("old")
        self._new_gutter = LineNumberGutter("new")
        self._init_properties()
        self._init_gutter()
        self._init_tags()

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
        # The language is that of the file shown, set along with a diff,
        # so that the code is highlighted as the code it is.
        buffer.set_highlight_syntax(True)
        buffer.set_highlight_matching_brackets(False)
        manager = GtkSource.StyleSchemeManager.get_default()
        manager.append_search_path(str(slop.DATA_DIR))
        buffer.set_style_scheme(manager.get_scheme("sloppie"))

    def _init_tags(self):
        """Create the tags that mark up the diff itself."""
        # The highlighting engine is busy with the file's own language,
        # which knows nothing of diffs, so everything that says what the
        # diff says is ours to apply as tags. Tags made here, before the
        # engine has any of its own, take precedence over the engine's.
        buffer = self.get_buffer()
        scheme = buffer.get_style_scheme()
        for kind in ("added", "removed"):
            style = scheme.get_style(f"slop:{kind}-line")
            buffer.create_tag(f"{kind}-line",
                              paragraph_background=style.get_property("line-background"))
            # A character background, which is a different property than
            # the line background above, so that the two stack.
            style = scheme.get_style(f"slop:refine-{kind}")
            buffer.create_tag(f"refine-{kind}",
                              background=style.get_property("background"))
        # The lines of the diff itself are not code, so undo the bold
        # and italic that the language would give the words in them.
        style = scheme.get_style("slop:hunk")
        buffer.create_tag("hunk",
                          foreground=style.get_property("foreground"),
                          paragraph_background=style.get_property("line-background"),
                          weight=Pango.Weight.NORMAL,
                          style=Pango.Style.NORMAL)
        style = scheme.get_style("slop:meta")
        buffer.create_tag("meta",
                          foreground=style.get_property("foreground"),
                          weight=Pango.Weight.NORMAL,
                          style=Pango.Style.NORMAL)

    def _set_language(self, path):
        """Highlight the code as the language that `path` is written in."""
        language = None
        if path is not None:
            # The content type is what identifies a file that goes by
            # name rather than by extension, such as a Makefile.
            content_type = Gio.content_type_guess(path, None)[0]
            manager = GtkSource.LanguageManager.get_default()
            language = manager.guess_language(path, content_type)
        self.get_buffer().set_language(language)

    def _tint(self, lines):
        """Tint whole lines by what they are in the diff."""
        buffer = self.get_buffer()
        tags = {
            "added": "added-line",
            "hunk": "hunk",
            "meta": "meta",
            "nonewline": "meta",
            "removed": "removed-line",
        }
        i = 0
        while i < len(lines):
            # Tint a run of lines of the same kind in one go, there
            # being far fewer runs than there are lines.
            j = i
            while j < len(lines) and lines[j].kind == lines[i].kind: j += 1
            if name := tags.get(lines[i].kind):
                # Ending at the start of the line after the run leaves
                # that line untouched, tags covering no character of it.
                buffer.apply_tag_by_name(name,
                                         buffer.get_iter_at_line(i)[1],
                                         buffer.get_iter_at_line(j)[1])
            i = j

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
                    oldtext, newtext = lines[old].text[1:], lines[new].text[1:]
                    if max(len(oldtext), len(newtext)) > 10000:
                        # Comparing is quadratic in the length of a line
                        # and a pair of lines this long is minified code
                        # or data, where words mean nothing anyway.
                        continue
                    oldspans, newspans = find_spans(oldtext, newtext)
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

    def get_position(self):
        """Return the one-based (line, column) in the new file at the cursor."""
        buffer = self.get_buffer()
        # A selection is returned as its bounds and an empty tuple if
        # there is none. The cursor is at the end of a selection made by
        # dragging, but its start is the interesting end of it.
        bounds = buffer.get_selection_bounds()
        start = (bounds[0] if bounds else
                 buffer.get_iter_at_mark(buffer.get_insert()))
        line = start.get_line()
        if line < len(self._lines) and self._lines[line].new is not None:
            # Column one is the first character after the diff marker,
            # which is where the cursor lands if it is on the marker.
            return self._lines[line].new, max(start.get_line_offset(), 1)
        # Removed lines and headers exist only in the diff, so fall back
        # on the closest line that the new file has, the one after it
        # being where a removal took place.
        for i in [*range(line, len(self._lines)), *reversed(range(line))]:
            if self._lines[i].new is not None:
                return self._lines[i].new, 1
        return None

    def get_selection(self):
        """Return the selected lines of the diff, or ``None`` if none."""
        buffer = self.get_buffer()
        bounds = buffer.get_selection_bounds()
        if not bounds: return None
        start, end = bounds
        # A comment is on whole lines, however much of the first and the
        # last one was actually selected. A line where the selection only
        # ends, at its very start, has nothing of it selected.
        start.set_line_offset(0)
        if not end.starts_line() and not end.ends_line():
            end.forward_to_line_end()
        return buffer.get_text(start, end, False)

    def set_diff(self, lines, path=None, keep_position=False):
        """Show the parsed diff `lines` of `path`, `keep_position` to not scroll to the top."""
        buffer = self.get_buffer()
        text = "\n".join(x.text for x in lines)
        if keep_position and text == buffer.get_text(*buffer.get_bounds(), True):
            # Nothing to redo, and redoing it would only lose the position.
            return
        top = (self.get_line_at_y(self.get_visible_rect().y)[0].get_line()
               if keep_position else 0)
        # Set the language first, so that the text is highlighted as it
        # is inserted rather than all over again right after.
        self._set_language(path)
        buffer.set_text(text)
        self._lines = lines
        # Nothing here can be edited, but the cursor still marks the
        # place that the edit action opens in the editor. With no diff
        # there's no place either, only a caret blinking in the void.
        self.set_cursor_visible(bool(lines))
        self._tint(lines)
        self._refine(lines)
        for gutter in (self._old_gutter, self._new_gutter):
            gutter.set_lines(lines)
        buffer.place_cursor(buffer.get_iter_at_line(
            min(top, buffer.get_line_count() - 1))[1])
        # Line heights are only computed once idle, so scrolling by iter
        # would be off. Scrolling to a mark defers until they are known.
        self.scroll_to_mark(buffer.get_insert(), 0, True, 0, 0)
