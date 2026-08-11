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
import sys

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from slop.git import parse_diff
from slop.git import SECTION_TITLES

class Window(Gtk.ApplicationWindow):

    def __init__(self, repository):
        GObject.GObject.__init__(self)
        self.repository = repository
        self._comment_sidebar = slop.CommentSidebar()
        self._diff_view = slop.DiffView()
        self._file_sidebar = slop.FileSidebar()
        self._terminal = slop.Terminal(repository.root)
        self._fingerprint = None
        self._init_properties()
        self._init_widgets()
        self._init_signal_handlers()
        self.load_css()
        self.refresh()

    def _init_properties(self):
        self.set_default_size(1400, 900)
        self.set_title("Slop Central")

    def _init_signal_handlers(self):
        self._file_sidebar.connect("change-selected", self._on_change_selected)
        # Poll instead of watching the working tree, which would mean a
        # watch on each of possibly very many directories. A poll costs
        # one git command that skips ignored files, such as node_modules.
        source = GLib.timeout_add_seconds(3, self._on_poll_timeout)
        self.connect("destroy", lambda *args: GLib.source_remove(source))

    def _init_widgets(self):
        header = Gtk.HeaderBar()
        switcher = Gtk.StackSwitcher()
        header.set_title_widget(switcher)
        self.set_titlebar(header)
        diff_scroller = Gtk.ScrolledWindow()
        diff_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        diff_scroller.set_child(self._diff_view)
        terminal_scroller = Gtk.ScrolledWindow()
        terminal_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        terminal_scroller.set_child(self._terminal)
        stack = Gtk.Stack()
        stack.add_titled(diff_scroller, "diff", "Diff")
        stack.add_titled(terminal_scroller, "terminal", "Terminal")
        switcher.set_stack(stack)
        # Files | diff or terminal | comments, with the middle
        # getting the extra space and the sidebars always visible.
        # Both sidebars are 280 wide by default, the middle getting the
        # rest of the default window width, minus the two paned handles.
        right = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        right.set_start_child(stack)
        right.set_resize_start_child(True)
        right.set_shrink_start_child(False)
        right.set_end_child(self._comment_sidebar)
        right.set_resize_end_child(False)
        right.set_shrink_end_child(False)
        right.set_position(1400 - 280 - 280 - 2)
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_start_child(self._file_sidebar)
        paned.set_resize_start_child(False)
        paned.set_shrink_start_child(False)
        paned.set_end_child(right)
        paned.set_resize_end_child(True)
        paned.set_shrink_end_child(False)
        paned.set_position(280)
        self.set_child(paned)

    def load_css(self):
        css = (slop.DATA_DIR / "slop-central.css").read_text("utf-8")
        provider = Gtk.CssProvider()
        provider.load_from_string(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _on_change_selected(self, sidebar, change):
        self._comment_sidebar.set_change(change)
        if change is None:
            self.set_title("Slop Central")
            return self._diff_view.set_diff([])
        # The same file can be listed in two sections at once.
        section = SECTION_TITLES[change.section]
        self.set_title(f"{change.path} — {section}")
        try:
            text = self.repository.get_diff(change)
        except RuntimeError as error:
            print(f"slop-central: {error}", file=sys.stderr)
            return self._diff_view.set_diff([])
        self._diff_view.set_diff(parse_diff(text))

    def _on_poll_timeout(self):
        try:
            fingerprint = self.repository.get_fingerprint()
        except RuntimeError as error:
            print(f"slop-central: {error}", file=sys.stderr)
            return GLib.SOURCE_CONTINUE
        if fingerprint != self._fingerprint:
            self.refresh()
        return GLib.SOURCE_CONTINUE

    def refresh(self):
        """Reload the list of changed files from git."""
        try:
            # Take the fingerprint first, so that a change made while
            # we're reloading is caught by the next poll, not missed.
            self._fingerprint = self.repository.get_fingerprint()
            changes = self.repository.list_changes()
        except RuntimeError as error:
            print(f"slop-central: {error}", file=sys.stderr)
            return
        self._file_sidebar.set_changes(changes)
