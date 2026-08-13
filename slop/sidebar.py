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

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Graphene
from gi.repository import Gtk
from gi.repository import Pango
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
        # The actions are those of the window, found by way of the popover
        # being parented to a widget in the window's widget hierarchy.
        model = Gio.Menu()
        model.append("Stage", "win.stage")
        model.append("Unstage", "win.unstage")
        model.append("Revert", "win.revert")
        model.append("Trash", "win.trash")
        model.append("Edit", "win.edit")
        self._menu = Gtk.PopoverMenu(menu_model=model, has_arrow=False)
        self._menu.set_parent(self)

    def do_dispose(self):
        # A popover is parented, not a child, so it has to be
        # unparented by hand, lest GTK complain on finalization.
        if self._menu is not None:
            self._menu.unparent()
            self._menu = None
        Gtk.Box.do_dispose(self)

    def _on_header_setup(self, factory, header):
        label = Gtk.Label()
        label.set_xalign(0)
        label.add_css_class("slop-file-section")
        header.set_child(label)

    def _on_header_bind(self, factory, header):
        change = header.get_item()
        # The mnemonics only show the underline when Alt is held, the
        # focus shortcuts of the window do the actual moving of focus.
        title = {"staged": "_Staged",
                 "unstaged": "_Unstaged",
                 "untracked": "U_ntracked"}[change.section]
        header.get_child().set_text_with_mnemonic(title)

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
            # Line up the baselines of the smaller labels with the name.
            child.set_valign(Gtk.Align.BASELINE_CENTER)
            box.append(child)
        gesture = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        gesture.connect("pressed", self._on_item_right_click, item)
        box.add_controller(gesture)
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
        # Binary files have no line counts to show. Zeros are left out too,
        # they'd only be noise on a row that has nothing added or removed.
        added.set_text(f"+{change.added}" if change.added else "")
        removed.set_text("bin" if change.removed is None else
                         f"−{change.removed}" if change.removed else "")
        for label in (added, removed):
            # Hide rather than blank, so that the box spacing of an empty
            # label doesn't look like trailing space on the row.
            label.set_visible(bool(label.get_text()))

    def _on_item_right_click(self, gesture, n_press, x, y, item):
        # Act on the file clicked, not the one selected before. Rows are
        # recycled, so the item's position is only known now.
        self._selection.set_selected(item.get_position())
        found, point = item.get_child().compute_point(
            self, Graphene.Point().init(x, y))
        if not found: return
        rectangle = Gdk.Rectangle()
        rectangle.x = round(point.x)
        rectangle.y = round(point.y)
        rectangle.width = rectangle.height = 1
        self._menu.set_pointing_to(rectangle)
        self._menu.popup()

    def _on_selected_item_changed(self, *args, **kwargs):
        self.emit("change-selected", self._selection.get_selected_item())

    def focus_section(self, section):
        """Move focus to the first file of `section`, if any."""
        if not self._stores[section].get_n_items(): return
        position = sum(self._stores[x].get_n_items()
                       for x in SECTIONS[:SECTIONS.index(section)])
        # scroll_to only grabs focus if the list has focus already.
        self._list_view.grab_focus()
        self._list_view.scroll_to(position,
                                  Gtk.ListScrollFlags.FOCUS |
                                  Gtk.ListScrollFlags.SELECT,
                                  None)

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
