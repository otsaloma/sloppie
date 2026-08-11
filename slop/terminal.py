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

import sys

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Pango
from gi.repository import Vte

def parse_color(color):
    """Return hexadecimal `color` as a `Gdk.RGBA`."""
    rgba = Gdk.RGBA()
    rgba.parse(color)
    return rgba

class Terminal(Vte.Terminal):

    """A terminal running the user's shell in the repository."""

    def __init__(self, directory):
        GObject.GObject.__init__(self)
        self._init_properties()
        self._init_colors()
        self._spawn(directory)

    def _init_colors(self):
        # The light variant of the OTS palette, as used in Ptyxis. Only
        # the sixteen standard colors are given, VTE keeps its own
        # defaults for the color cube and the grayscale ramp.
        self.set_colors(parse_color("#444444"), parse_color("#fafafa"), [
            parse_color(x) for x in (
                "#444444", "#c01c28", "#26a269", "#a2734c",
                "#12488b", "#a347ba", "#2aa1b3", "#cfcfcf",
                "#5d5d5d", "#f66151", "#33d17a", "#e9ad0c",
                "#2a7bde", "#c061cb", "#33c7de", "#fafafa")])
        self.set_color_cursor(parse_color("#444444"))

    def _init_properties(self):
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_font(Pango.FontDescription.from_string(
            "Berkeley Standard Mono Medium 10"))

    def _spawn(self, directory):
        # Fall back to sh if the user has no shell in the passwd database.
        shell = Vte.get_user_shell() or "/bin/sh"
        # Note that pygobject keeps child_setup_data, unlike the
        # documented signature, making this eleven arguments, not ten.
        self.spawn_async(Vte.PtyFlags.DEFAULT,
                         str(directory),
                         [shell],
                         None,
                         GLib.SpawnFlags.DEFAULT,
                         None,
                         None,
                         -1,
                         None,
                         self._on_spawn_done,
                         None)

    def _on_spawn_done(self, terminal, pid, error, *args):
        if error is None: return
        # Without a shell the terminal is a blank box, so say why.
        print(f"slop-review: {error.message}", file=sys.stderr)
