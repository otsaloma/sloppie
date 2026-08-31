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

class ShortcutsWindow(Gtk.ShortcutsWindow):

    """A window listing the keyboard shortcuts."""

    # Deprecated as of GTK 4.18 and to be removed in GTK 5, the
    # replacement being AdwShortcutsDialog, which we don't have.

    def __init__(self, parent):
        GObject.GObject.__init__(self)
        self.set_modal(True)
        self.set_title("Keyboard Shortcuts")
        self.set_transient_for(parent)
        self._init_section()

    def _init_section(self):
        # The one section, which keeps the plain title in the header
        # bar: a second one would turn that into a dropdown to switch
        # between them, hiding half the shortcuts behind it. The groups
        # are laid out as columns, seventeen lines being what fits them
        # all on one page rather than spilling onto a second.
        section = Gtk.ShortcutsSection(max_height=17, title="Shortcuts")
        for title, shortcuts in (
                ("Dashboard", (
                    ("<Alt>1...9", "Open Task"),
                )),
                ("Files", (
                    ("<Control>e", "Edit File"),
                    ("<Control>s", "Stage File"),
                    ("<Control>u", "Unstage File"),
                )),
                ("Changes", (
                    ("<Control>Return", "Commit"),
                    ("<Control>m", "Add Comment"),
                    ("F5", "Run Command"),
                    ("<Shift>F5", "Set Command"),
                )),
                ("Focus", (
                    ("<Alt>s", "Staged Files"),
                    ("<Alt>u", "Unstaged Files"),
                    ("<Alt>n", "Untracked Files"),
                    ("<Alt>d", "Diff"),
                    ("<Alt>t", "Terminal"),
                )),
                ("Tabs", (
                    ("<Control>Page_Down", "Next Tab"),
                    ("<Control>Page_Up", "Previous Tab"),
                )),
                ("Terminal", (
                    ("<Shift><Control>c", "Copy"),
                    ("<Shift><Control>v", "Paste"),
                    ("<Shift><Control>r", "Resume Agent"),
                )),
                ("Window", (
                    # A toggle, so this is the way back from the
                    # dashboard too, the tasks being what it zooms in to.
                    ("F4", "Dashboard"),
                    ("F10", "Main Menu"),
                    ("<Control>w", "Close Task"),
                    ("<Control>q", "Quit"),
                ))):
            group = Gtk.ShortcutsGroup(title=title)
            for accelerator, shortcut_title in shortcuts:
                group.add_shortcut(Gtk.ShortcutsShortcut(
                    accelerator=accelerator, title=shortcut_title))
            section.add_group(group)
        self.add_section(section)
