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

from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from slop.git import SECTION_TITLES
from slop.git import SECTIONS

class FileSidebar(Gtk.Box):

    """List of changed files, grouped into staged, unstaged and untracked."""

    __gsignals__ = {
        "change-selected": (GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_PYOBJECT,)),
    }

    def __init__(self):
        GObject.GObject.__init__(self, orientation=Gtk.Orientation.VERTICAL)
        # One store per section: GtkFlattenListModel makes each of the
        # models it flattens a section, which GtkListView then gives a
        # header. Empty sections contribute no items and no header.
        self._stores = {x: Gio.ListStore(item_type=slop.FileChange) for x in SECTIONS}
        sections = Gio.ListStore(item_type=Gio.ListModel)
        for section in SECTIONS:
            sections.append(self._stores[section])
        self._selection = Gtk.SingleSelection(model=Gtk.FlattenListModel(model=sections))
        self._selection.set_autoselect(False)
        self._selection.set_can_unselect(True)
        self._list_view = Gtk.ListView(model=self._selection)
        self._init_widgets()
        self._selection.connect("notify::selected-item", self._on_selected_item_changed)

    def _init_widgets(self):
        self.add_css_class("slop-file-sidebar")
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_item_setup)
        factory.connect("bind", self._on_item_bind)
        self._list_view.set_factory(factory)
        headers = Gtk.SignalListItemFactory()
        headers.connect("setup", self._on_header_setup)
        headers.connect("bind", self._on_header_bind)
        self._list_view.set_header_factory(headers)
        self._scroller = Gtk.ScrolledWindow()
        self._scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._scroller.set_vexpand(True)
        self._scroller.set_child(self._list_view)
        # The list starts out empty, hence the placeholder instead.
        self._scroller.set_visible(False)
        self.append(self._scroller)
        self._placeholder = Gtk.Label(label="No changes")
        self._placeholder.add_css_class("dim-label")
        self._placeholder.set_vexpand(True)
        self.append(self._placeholder)

    def _on_header_setup(self, factory, header):
        label = Gtk.Label()
        label.set_xalign(0)
        label.add_css_class("slop-file-section")
        header.set_child(label)

    def _on_header_bind(self, factory, header):
        change = header.get_item()
        title = SECTION_TITLES[change.section]
        header.get_child().set_text(f"{title} ({header.get_n_items()})")

    def _on_item_setup(self, factory, item):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.add_css_class("slop-file-row")
        status = Gtk.Label()
        status.set_xalign(0.5)
        status.set_width_chars(1)
        status.add_css_class("monospace")
        status.add_css_class("slop-file-status")
        name = Gtk.Label()
        name.set_xalign(0)
        name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        directory = Gtk.Label()
        directory.set_xalign(0)
        directory.set_hexpand(True)
        directory.set_ellipsize(Pango.EllipsizeMode.START)
        directory.add_css_class("slop-file-directory")
        added = Gtk.Label()
        added.set_xalign(1)
        added.add_css_class("monospace")
        added.add_css_class("slop-file-added")
        removed = Gtk.Label()
        removed.set_xalign(1)
        removed.add_css_class("monospace")
        removed.add_css_class("slop-file-removed")
        for child in (status, name, directory, added, removed):
            box.append(child)
        item.set_child(box)

    def _on_item_bind(self, factory, item):
        change = item.get_item()
        box = item.get_child()
        status = box.get_first_child()
        name = status.get_next_sibling()
        directory = name.get_next_sibling()
        added = directory.get_next_sibling()
        removed = added.get_next_sibling()
        status.set_text(change.status)
        name.set_text(change.name)
        name.set_tooltip_text(change.path)
        directory.set_text(change.directory)
        # Binary files have no line counts to show.
        added.set_text("" if change.added is None else f"+{change.added}")
        removed.set_text("bin" if change.removed is None else f"−{change.removed}")
        for label, count in ((added, change.added), (removed, change.removed)):
            # Dim zeros, which would otherwise shout on nearly every row.
            method = label.add_css_class if count == 0 else label.remove_css_class
            method("slop-file-zero")

    def _on_selected_item_changed(self, *args, **kwargs):
        self.emit("change-selected", self._selection.get_selected_item())

    def get_selected_change(self):
        return self._selection.get_selected_item()

    def set_changes(self, changes):
        """Show `changes`, keeping the selected file selected if still there."""
        selected = self.get_selected_change()
        for section in SECTIONS:
            self._stores[section].splice(
                0, self._stores[section].get_n_items(), changes[section])
        empty = not self._selection.get_model().get_n_items()
        self._scroller.set_visible(not empty)
        self._placeholder.set_visible(empty)
        self.select_change(selected)

    def select_change(self, change):
        """Select the item matching `change`, or the first item."""
        model = self._selection.get_model()
        for i in range(model.get_n_items()):
            item = model.get_item(i)
            if (change is not None and
                item.section == change.section and
                item.path == change.path):
                return self._selection.set_selected(i)
        self._selection.set_selected(0 if model.get_n_items() else Gtk.INVALID_LIST_POSITION)
