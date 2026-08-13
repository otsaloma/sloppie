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

from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

class Toast(Gtk.Box):

    """Transient notification overlaid on the window content."""

    def __init__(self):
        GObject.GObject.__init__(self, orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.add_css_class("slop-toast")
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.END)
        self.set_visible(False)
        self._hide_id = None
        self._label = Gtk.Label()
        self.append(self._label)
        button = Gtk.Button.new_from_icon_name("window-close-symbolic")
        button.add_css_class("flat")
        button.add_css_class("circular")
        button.connect("clicked", self._hide)
        self.append(button)

    def flash(self, text, duration=3):
        """Show `text` in the toast for `duration` seconds."""
        if self._hide_id is not None:
            GLib.source_remove(self._hide_id)
        self._label.set_text(text)
        self.set_visible(True)
        self._hide_id = GLib.timeout_add_seconds(duration, self._hide)

    def _hide(self, *args):
        """Hide the toast, cancelling any pending timeout."""
        if self._hide_id is not None:
            # Also removable while being dispatched by the timeout itself.
            GLib.source_remove(self._hide_id)
            self._hide_id = None
        self.set_visible(False)
        return GLib.SOURCE_REMOVE
