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
from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from slop.git import parse_diff
from slop.git import SECTION_TITLES

class Window(Gtk.ApplicationWindow):

    def __init__(self, repository):
        GObject.GObject.__init__(self)
        self.repository = repository
        self._comment_sidebar = slop.CommentSidebar()
        self._diff_view = slop.DiffView()
        self._file_sidebar = slop.FileSidebar()
        self._title_label = Gtk.Label()
        self._init_properties()
        self._init_widgets()
        self._init_signal_handlers()
        self._init_actions()
        self.load_css()
        self.refresh()

    def _init_actions(self):
        action = Gio.SimpleAction.new("refresh", None)
        action.connect("activate", lambda *args: self.refresh())
        self.add_action(action)

    def _init_properties(self):
        self.set_default_size(1400, 900)
        self.set_title("Slop Review")

    def _init_signal_handlers(self):
        self._file_sidebar.connect("change-selected", self._on_change_selected)

    def _init_widgets(self):
        header = Gtk.HeaderBar()
        self._title_label.add_css_class("title")
        self._title_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        header.set_title_widget(self._title_label)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh.set_tooltip_text("Reload changes from git (Ctrl+R)")
        refresh.connect("clicked", lambda *args: self.refresh())
        header.pack_start(refresh)
        self.set_titlebar(header)
        diff_scroller = Gtk.ScrolledWindow()
        diff_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        diff_scroller.set_child(self._diff_view)
        # Files | diff | comments, with the diff getting the extra space.
        right = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        right.set_start_child(diff_scroller)
        right.set_resize_start_child(True)
        right.set_shrink_start_child(False)
        right.set_end_child(self._comment_sidebar)
        right.set_resize_end_child(False)
        right.set_shrink_end_child(False)
        right.set_position(880)
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
        css = (slop.DATA_DIR / "slop-review.css").read_text("utf-8")
        provider = Gtk.CssProvider()
        provider.load_from_string(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _on_change_selected(self, sidebar, change):
        self._comment_sidebar.set_change(change)
        if change is None:
            self._title_label.set_text("Slop Review")
            return self._diff_view.set_diff([])
        # The same file can be listed in two sections at once.
        section = SECTION_TITLES[change.section]
        self._title_label.set_text(f"{change.path} — {section}")
        try:
            text = self.repository.get_diff(change)
        except RuntimeError as error:
            print(f"slop-review: {error}", file=sys.stderr)
            return self._diff_view.set_diff([])
        self._diff_view.set_diff(parse_diff(text))

    def refresh(self):
        """Reload the list of changed files from git."""
        try:
            changes = self.repository.list_changes()
        except RuntimeError as error:
            print(f"slop-review: {error}", file=sys.stderr)
            return
        self._file_sidebar.set_changes(changes)
