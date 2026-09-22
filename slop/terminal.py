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
import re
import shlex
import signal
import time

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import Vte
from contextlib import suppress
from pathlib import Path
from slop import recent
from slop import util

UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"

RESUME_COMMANDS = {
    "agy": rf"agy --conversation={UUID}",
    "claude": rf"claude --resume {UUID}",
    "codex": rf"codex resume {UUID}",
    "pi": rf"pi --session {UUID}",
}

AGENTS = tuple(RESUME_COMMANDS)

def parse_color(color):
    """Return hexadecimal `color` as a `Gdk.RGBA`."""
    rgba = Gdk.RGBA()
    rgba.parse(color)
    return rgba

class Terminal(Vte.Terminal):

    """A terminal running the user's shell in the repository."""

    # The arguments of "file-clicked" are the absolute path of the file
    # and the line and column to go to, the column being 1 if unknown.
    # The argument of "command-finished" is the name of the command that
    # ran in the foreground and has now returned to the prompt. "copied"
    # is emitted when text lands in the clipboard.
    __gsignals__ = {
        "file-clicked": (GObject.SignalFlags.RUN_LAST, None,
                         (GObject.TYPE_STRING,
                          GObject.TYPE_INT,
                          GObject.TYPE_INT)),
        "command-finished": (GObject.SignalFlags.RUN_LAST, None,
                             (GObject.TYPE_STRING,)),
        "copied": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, directory, setup=None):
        GObject.GObject.__init__(self)
        self._directory = directory
        # Shell commands to run once, before the first prompt.
        self._setup = setup
        self._command = None
        self._command_group = None
        self._command_started = None
        self._pid = None
        self._poll_source = None
        self._spawned = False
        self._init_properties()
        self._init_colors()
        self._init_links()
        self._init_shortcuts()
        self._init_poll()
        self.connect("child-exited", self._on_child_exited)
        # A shell per terminal when first shown, as starting all at once
        # would run a repository's direnv initialization — a cloud login,
        # say — three times in parallel.
        self.connect("map", self._on_map)

    def _init_colors(self):
        # The light variant of the OTS palette, as used in Ptyxis.
        self.set_colors(parse_color("#444444"), parse_color("#f2f2f2"), [
            parse_color(x) for x in (
                "#444444", "#c01c28", "#26a269", "#a2734c",
                "#12488b", "#a347ba", "#2aa1b3", "#cfcfcf",
                "#5d5d5d", "#f66151", "#33d17a", "#e9ad0c",
                "#2a7bde", "#c061cb", "#33c7de", "#f2f2f2")])
        self.set_color_cursor(parse_color("#444444"))

    def _init_links(self):
        # TUIs such as pi wrap URLs with real line breaks, leaving regex
        # matching only the first line. OSC 8 carries the full target
        # independently of the text on screen.
        self.set_allow_hyperlink(True)
        # 0x400 is PCRE2_MULTILINE, which VTE demands but doesn't export.
        flags = Vte.REGEX_FLAGS_DEFAULT | 0x400
        # Ending in a character that a sentence can't end in leaves
        # trailing punctuation out.
        url_regex = Vte.Regex.new_for_match(r"https?://\S+[[:alnum:]/]", -1, flags)
        # A path with a ':LINE' suffix, as grep, flake8, pytest and the
        # like print it. The line number keeps off 'and/or' and git's
        # 'a/file', the letter in the file name off clock times.
        file_regex = Vte.Regex.new_for_match(
            r"(?<![[:alnum:]_/.~-])"
            r"[~.]?/?(?:[[:alnum:]_.-]+/)*"
            r"[[:alnum:]_-]*[[:alpha:]][[:alnum:]_.-]*"
            r":[0-9]+(?::[0-9]+)?", -1, flags)
        self._url_tag = self.match_add_regex(url_regex, 0)
        self._file_tag = self.match_add_regex(file_regex, 0)
        for tag in (self._url_tag, self._file_tag):
            self.match_set_cursor_name(tag, "pointer")
        # Capture phase to beat VTE, which would take the click for the
        # start of a selection. Unlike Ptyxis, no Ctrl needed.
        click = Gtk.GestureClick(
            button=1, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self._on_click_pressed)
        self.add_controller(click)
        right = Gtk.GestureClick(
            button=3, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        right.connect("pressed", self._on_right_click_pressed)
        self.add_controller(right)
        group = Gio.SimpleActionGroup()
        open_action = Gio.SimpleAction.new("open", None)
        open_action.connect(
            "activate", lambda *args: self._open_uri(self._link_menu_uri))
        copy_action = Gio.SimpleAction.new("copy", None)
        copy_action.connect(
            "activate", lambda *args: self._copy_uri(self._link_menu_uri))
        group.add_action(open_action)
        group.add_action(copy_action)
        menu = Gio.Menu()
        menu.append("_Open Link", "link.open")
        menu.append("_Copy Link", "link.copy")
        self._link_menu = Gtk.PopoverMenu.new_from_model(menu)
        self._link_menu.set_has_arrow(False)
        self._link_menu.insert_action_group("link", group)
        self._link_menu.set_parent(self)
        self._link_menu_uri = None

    def _check_hyperlink_at(self, x, y):
        """Return the hyperlink URI at (`x`, `y`) if http or https, or ``None``."""
        uri = self.check_hyperlink_at(x, y)
        return uri if uri and uri.startswith(("http://", "https://")) else None

    def _on_click_pressed(self, click, n_press, x, y):
        if n_press != 1: return
        # Prefer the explicit target over the visible text, which may
        # be a label or only the first line of a wrapped URL.
        text, tag = self._check_hyperlink_at(x, y), self._url_tag
        if text is None:
            text, tag = self.check_match_at(x, y)
        if text is None: return
        if tag == self._url_tag:
            self._open_uri(text)
        elif tag == self._file_tag:
            path, line, column = (text.split(":") + ["1"])[:3]
            path = Path(path).expanduser()
            # Wrong for a shell that has cd'd elsewhere.
            if not path.is_absolute():
                path = self._directory / path
            # A lookalike is left to VTE as a plain click.
            if not path.is_file(): return
            self.emit("file-clicked", str(path), int(line), int(column))
        click.set_state(Gtk.EventSequenceState.CLAIMED)

    def _on_right_click_pressed(self, click, n_press, x, y):
        if n_press != 1: return
        uri = self._check_hyperlink_at(x, y)
        if uri is None:
            text, tag = self.check_match_at(x, y)
            if text is not None and tag == self._url_tag:
                uri = text
        if uri is None: return
        click.set_state(Gtk.EventSequenceState.CLAIMED)
        self._popup_link_menu(x, y, uri)

    def _popup_link_menu(self, x, y, uri):
        self._link_menu_uri = uri
        rect = Gdk.Rectangle()
        rect.x, rect.y = int(x), int(y)
        rect.width = rect.height = 1
        self._link_menu.set_pointing_to(rect)
        self._link_menu.popup()

    def _open_uri(self, uri):
        if not uri.startswith(("http://", "https://")): return
        Gtk.UriLauncher(uri=uri).launch(self.get_root(), None, None)

    def _copy_uri(self, uri):
        # Gdk.Clipboard.set_text is a C inline that Python can't call.
        self.get_clipboard().set_content(
            Gdk.ContentProvider.new_for_value(uri))
        self.emit("copied")

    def do_dispose(self):
        # A popover is parented, not a child, so it has to be
        # unparented by hand, lest GTK complain on finalization.
        if self._link_menu is not None:
            self._link_menu.unparent()
            self._link_menu = None
        Vte.Terminal.do_dispose(self)

    def _init_properties(self):
        self.set_hexpand(True)
        self.set_vexpand(True)
        # As Ptyxis does. VTE's own scrolling takes a touchpad's pixel
        # deltas for lines, which sends a nudge flying.
        self.set_enable_fallback_scrolling(False)
        self.set_scroll_unit_is_pixels(True)
        self.set_scrollback_lines(10000)
        self.set_scroll_on_keystroke(True)
        self.set_scroll_on_output(False)
        # Without a list, a missing font leaves fontconfig to substitute
        # its default, which is proportional.
        self.set_font(Pango.FontDescription.from_string(
            "Berkeley Standard Mono, SF Mono, monospace Medium 10"))
        # So that double-clicking selects whole paths and URLs.
        self.set_word_char_exceptions("-./:@_~")

    def _init_poll(self):
        # VTE's shell termprops would say the same right away, but only
        # with shell integration, which we can't count on. Three seconds
        # is thus the shortest command noticed, which suits notifications.
        self._poll_source = GLib.timeout_add_seconds(3, self._on_poll_timeout)

    def close(self):
        """Hang up the shell and stop watching it."""
        # Not on dispose, which never comes, the handlers on the
        # terminal's children and its task referencing it.
        if self._poll_source is not None:
            GLib.source_remove(self._poll_source)
            self._poll_source = None
        if self._pid is None: return
        # Also to the foreground group, which a shell might not pass the
        # SIGHUP on to.
        groups = {self._get_foreground_group(), os.getpgid(self._pid)}
        for group in groups - {None}:
            with suppress(Exception):
                os.killpg(group, signal.SIGHUP)
        self._pid = None

    def _on_poll_timeout(self):
        if (group := self._get_foreground_group()) is None:
            self._command_group = None
            self._command_started = None
            if self._command is not None:
                command, self._command = self._command, None
                if command in AGENTS:
                    self._store_resume_command(command)
                self.emit("command-finished", command)
        else:
            if group != self._command_group:
                self._command_group = group
                self._command_started = time.monotonic()
            if (command := self._get_command_name(group)) is not None:
                self._command = command
        return GLib.SOURCE_CONTINUE

    def _get_command_name(self, group):
        """Return the name of the command running in `group`, if it can be told."""
        # Walk down from the leader rather than scan all of /proc for the
        # group, which measures a hundred times cheaper. That misses the
        # leader's siblings, but a wrapper's agent is always below it.
        commands, todo = [], [group]
        while todo:
            pid = str(todo.pop())
            with suppress(Exception):
                commands.append((Path("/proc") / pid / "comm").read_text("utf-8").strip())
                todo += (Path("/proc") / pid / "task" / pid / "children").read_text("utf-8").split()
        # An agent behind a wrapper is named for the wrapper: codex is a
        # Node script whose leader reads 'MainThread'.
        if agent := next((x for x in commands if x in AGENTS), None):
            return agent
        # The leader can be gone while the group still runs, as at the
        # head of a pipeline.
        return commands[0] if commands else None

    def _store_resume_command(self, command):
        """Record how to get back to the session `command` has just left."""
        column, row = self.get_cursor_position()
        text, length = self.get_text_range_format(
            Vte.Format.TEXT, max(0, row - 50), 0, row, -1)
        if matches := re.findall(RESUME_COMMANDS[command], text):
            recent.set_resume_command(self._directory, matches[-1])

    def _init_shortcuts(self):
        # VTE has no clipboard keybindings. Capture phase to beat VTE's
        # key controller, which would send a plain Ctrl+C and Ctrl+V.
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
        if self.get_has_selection():
            self.copy_clipboard_format(Vte.Format.TEXT)
            self.emit("copied")
        return True

    def _on_paste(self, terminal, args):
        def on_done(clipboard, result, *args):
            try:
                text = clipboard.read_text_finish(result)
            except GLib.Error:
                text = None
            if text is None:
                return self.paste_clipboard()
            if "\n" in text:
                message = ("The clipboard text has line breaks in it. "
                           "Pasting sends it as if typed, and the shell "
                           "may run each line as a command.")
                if not util.confirm(self.get_root(), "Paste multiple lines?",
                                    message, "Paste"):
                    return
            self.paste_text(text)

        self.get_clipboard().read_text_async(None, on_done, None)
        return True

    def _on_map(self, terminal):
        if self._spawned: return
        self._spawn()

    def _spawn(self):
        self._spawned = True
        shell = Vte.get_user_shell() or "/bin/sh"
        argv = [shell]
        if self._setup is not None:
            # Cleared here too, as a shell exited by hand is respawned.
            setup, self._setup = self._setup, None
            argv = [shell, "-c", f"{setup}\nexec {shlex.quote(shell)}"]
        # Made here, rather than by spawning via the terminal, to have the
        # name of its slave end for SLOPPIE_TTY.
        pty = self.pty_new_sync(Vte.PtyFlags.DEFAULT)
        self.set_pty(pty)
        # Note that pygobject keeps child_setup_data, unlike the
        # documented signature, making this ten arguments, not nine.
        # SLOPPIE tells agents that a bell is enough for a notification.
        # SLOPPIE_TTY is where to ring it from a hook, which runs detached
        # with no terminal of its own.
        pty.spawn_async(str(self._directory),
                        argv,
                        ["SLOPPIE=1", f"SLOPPIE_TTY={os.ptsname(pty.get_fd())}"],
                        GLib.SpawnFlags.DEFAULT,
                        None,
                        None,
                        -1,
                        None,
                        self._on_spawn_done,
                        None)

    def _on_spawn_done(self, pty, result, *args):
        try:
            self._pid = pty.spawn_finish(result).child_pid
            # Spawning via the pty, unlike via the terminal, leaves the
            # child unwatched, and "child-exited" is only ever emitted
            # for a watched one.
            self.watch_child(self._pid)
        except GLib.Error as error:
            self._pid = None
            util.show_error(self.get_root(), "Failed to start the shell", error.message)

    def get_selection(self):
        """Return the text selected in the terminal, or ``None`` if none."""
        # VTE keeps the selection after the terminal loses focus.
        if not self.get_has_selection(): return None
        return self.get_text_selected(Vte.Format.TEXT)

    def _get_foreground_group(self):
        """Return the foreground process group, ``None`` if at the prompt."""
        # The foreground group is the shell's own only while the shell
        # waits for a command.
        if self._pid is None: return None
        if (pty := self.get_pty()) is None: return None
        try:
            group = os.tcgetpgrp(pty.get_fd())
        except Exception:
            return None
        return None if group == self._pid else group

    def is_running(self):
        """Return ``True`` if a command runs here, the shell itself aside."""
        # Not from the poll, which can be a few seconds behind.
        return self._get_foreground_group() is not None

    def is_agent_running(self):
        """Return ``True`` if an agent runs here, checked now, not polled."""
        if (group := self._get_foreground_group()) is None: return False
        return self._get_command_name(group) in AGENTS

    def get_command(self):
        """Return the name of the command running, ``None`` if at the prompt."""
        # As of the last poll.
        return self._command

    def get_command_elapsed(self):
        """Return seconds the command running has been, ``None`` if at the prompt."""
        if self._command_started is None: return None
        return time.monotonic() - self._command_started

    def _on_child_exited(self, terminal, status):
        # Respawn, as Ctrl+D is easy to press by accident. Not once the
        # window is gone though, that shell would only be orphaned.
        if self.get_root() is None: return
        self.reset(True, True)
        self._spawn()
