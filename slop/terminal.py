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

import os
import slop

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import Vte
from pathlib import Path

def parse_color(color):
    """Return hexadecimal `color` as a `Gdk.RGBA`."""
    rgba = Gdk.RGBA()
    rgba.parse(color)
    return rgba

class Terminal(Vte.Terminal):

    """A terminal running the user's shell in the repository."""

    def __init__(self, directory):
        GObject.GObject.__init__(self)
        self._directory = directory
        self._pid = None
        self._spawned = False
        self._init_properties()
        self._init_colors()
        self._init_shortcuts()
        self.connect("child-exited", self._on_child_exited)
        # Wait for the terminal to be shown before starting a shell. A
        # stack maps only the page on screen, so this is the first switch
        # to this terminal. Starting all the shells at once would run a
        # repository's direnv initialization — a cloud login, say — three
        # times in parallel, whereas one at a time lets the later shells
        # find the work of the first one already done.
        self.connect("map", self._on_map)

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
        # Leave scrolling to the scrolled window around us and give it
        # pixels to work with, as Ptyxis does. VTE's own scrolling takes
        # a touchpad's pixel-sized deltas for lines and multiplies them
        # by a tenth of the terminal height, which sends a nudge flying.
        self.set_enable_fallback_scrolling(False)
        self.set_scroll_unit_is_pixels(True)
        self.set_font(Pango.FontDescription.from_string(
            "Berkeley Standard Mono Medium 10"))

    def _init_shortcuts(self):
        # VTE has the clipboard API, but no keybindings for it, those
        # being left to the application; only middle-click pasting the
        # primary selection comes for free. Ctrl+Shift+C and Ctrl+Shift+V
        # are what GNOME's terminals use. They need the capture phase to
        # beat VTE's own key controller, which is in the bubble phase and
        # would send them to the shell as a plain Ctrl+C, interrupting
        # the running command, and Ctrl+V, readline's quoted-insert.
        shortcuts = Gtk.ShortcutController(
            propagation_phase=Gtk.PropagationPhase.CAPTURE)
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control><Shift>c"),
            action=Gtk.CallbackAction.new(self._on_copy)))
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control><Shift>v"),
            action=Gtk.CallbackAction.new(self._on_paste)))
        self.add_controller(shortcuts)

    def _on_copy(self, terminal, args):
        self.copy_clipboard_format(Vte.Format.TEXT)
        return True

    def _on_paste(self, terminal, args):
        self.paste_clipboard()
        return True

    def _on_map(self, terminal):
        # Switching back and forth maps the terminal again and again,
        # but only the first time is there no shell yet.
        if self._spawned: return
        self._spawn()

    def _spawn(self):
        self._spawned = True
        # Fall back to sh if the user has no shell in the passwd database.
        shell = Vte.get_user_shell() or "/bin/sh"
        # Note that pygobject keeps child_setup_data, unlike the
        # documented signature, making this eleven arguments, not ten.
        self.spawn_async(Vte.PtyFlags.DEFAULT,
                         str(self._directory),
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
        self._pid = pid if error is None else None
        if error is None: return
        # Without a shell the terminal is a blank box, so say why. The
        # window is there by now, this being called from the main loop,
        # long after the terminal was made and put in it.
        slop.util.show_error(self.get_root(), "Failed to start the shell", error.message)

    def get_foreground_commands(self):
        """Return the names of the commands running, empty if at the prompt."""
        # VTE's shell termprops would tell us this, but only with shell
        # integration that emits them, which we can't count on. The pty
        # knows all the same: its foreground process group is the
        # shell's own only while the shell waits for a command.
        if self._pid is None: return []
        if (pty := self.get_pty()) is None: return []
        try:
            group = os.tcgetpgrp(pty.get_fd())
        except Exception:
            return []
        if group == self._pid: return []
        # The whole group, not merely its leader, a command often being
        # a wrapper with the real thing as its child. codex, to name
        # one, is a Node script that spawns a binary of its own, and
        # its own name reads 'MainThread', that being Node's main thread.
        commands = []
        for path in Path("/proc").glob("[0-9]*"):
            try:
                # The fields of stat are separated by spaces, but the
                # second one is the command in parentheses and can
                # contain anything, spaces and parentheses included, so
                # only look past the last parenthesis, where the group
                # is the third field.
                stat = (path / "stat").read_text("utf-8")
                if int(stat[stat.rindex(")") + 2:].split()[2]) != group: continue
                commands.append((path / "comm").read_text("utf-8").strip())
            except Exception:
                # A process can be gone by the time we look at it.
                continue
        return commands

    def _on_child_exited(self, terminal, status):
        # Ctrl+D at the prompt exits the shell, which is easy to do by
        # accident and would leave a dead terminal behind, so start a
        # new shell to keep the terminal usable. Not once the window is
        # gone though, that shell would only be orphaned.
        if self.get_root() is None: return
        # Clear the screen and the scrollback so that the new shell
        # starts fresh instead of below the dead shell's output.
        self.reset(True, True)
        self._spawn()
