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

from gi.repository import GObject
from gi.repository import Gtk

class CommentSidebar(Gtk.Box):

    """Review comments on the selected file. Not implemented yet."""

    def __init__(self):
        GObject.GObject.__init__(self, orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("slop-comment-sidebar")
        self._placeholder = Gtk.Label(label="No comments")
        self._placeholder.add_css_class("dim-label")
        self._placeholder.set_vexpand(True)
        self.append(self._placeholder)

    def set_change(self, change):
        """Show the comments on `change`."""
        pass
