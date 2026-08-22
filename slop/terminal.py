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
import signal
import slop
import time

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import Vte
from contextlib import suppress
from pathlib import Path

# The coding agents known by name: what a terminal is here to run,
# what a comment can be sent to and what has a status worth showing.
AGENTS = ("claude", "codex")

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
    # ran in the foreground and has now returned to the prompt.
    __gsignals__ = {
        "file-clicked": (GObject.SignalFlags.RUN_LAST, None,
                         (GObject.TYPE_STRING,
                          GObject.TYPE_INT,
                          GObject.TYPE_INT)),
        "command-finished": (GObject.SignalFlags.RUN_LAST, None,
                             (GObject.TYPE_STRING,)),
    }

    def __init__(self, directory):
        GObject.GObject.__init__(self)
        self._directory = directory
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
        self.set_colors(parse_color("#444444"), parse_color("#fcfcef"), [
            parse_color(x) for x in (
                "#444444", "#c01c28", "#26a269", "#a2734c",
                "#12488b", "#a347ba", "#2aa1b3", "#cfcfcf",
                "#5d5d5d", "#f66151", "#33d17a", "#e9ad0c",
                "#2a7bde", "#c061cb", "#33c7de", "#fcfcef")])
        self.set_color_cursor(parse_color("#444444"))

    def _init_links(self):
        # VTE finds the matches and shows a hand over them, opening them
        # on click is ours. Ptyxis wants Ctrl held, we don't. The click
        # gesture needs the capture phase to beat VTE, which would take
        # the click for the start of a selection. The flags must include
        # PCRE2_MULTILINE, which VTE demands but doesn't export to
        # Python, hence the bare 0x400.
        flags = Vte.REGEX_FLAGS_DEFAULT | 0x400
        # Requiring a URL to end in a character that a sentence can't end
        # in leaves trailing punctuation out.
        url_regex = Vte.Regex.new_for_match(r"https?://\S+[[:alnum:]/]", -1, flags)
        # A file path with a ':LINE' suffix, as grep, flake8, pytest and
        # the like print it. Anchoring on the line number keeps the hand
        # cursor away from ordinary text that merely has a slash in it,
        # 'and/or' or '3/4', and from git's 'a/file' diff headers, while
        # requiring a letter in the file name keeps it off clock times.
        # A regex can't tell a path from a lookalike, only the filesystem
        # can, but the cursor is VTE's to draw off the regex alone.
        file_regex = Vte.Regex.new_for_match(
            r"(?<![[:alnum:]_/.~-])"
            r"[~.]?/?(?:[[:alnum:]_.-]+/)*"
            r"[[:alnum:]_-]*[[:alpha:]][[:alnum:]_.-]*"
            r":[0-9]+(?::[0-9]+)?", -1, flags)
        self._url_tag = self.match_add_regex(url_regex, 0)
        self._file_tag = self.match_add_regex(file_regex, 0)
        for tag in (self._url_tag, self._file_tag):
            self.match_set_cursor_name(tag, "pointer")
        click = Gtk.GestureClick(
            button=1, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self._on_click_pressed)
        self.add_controller(click)

    def _on_click_pressed(self, click, n_press, x, y):
        # Only the first press of a double-click, which would otherwise
        # open the link twice.
        if n_press != 1: return
        text, tag = self.check_match_at(x, y)
        if text is None: return
        if tag == self._url_tag:
            Gtk.UriLauncher(uri=text).launch(self.get_root(), None, None)
        elif tag == self._file_tag:
            path, line, column = (text.split(":") + ["1"])[:3]
            path = Path(path).expanduser()
            # Relative paths are the repository's own, which is right for
            # the output of the commands run there, but wrong for a shell
            # that has cd'd elsewhere.
            if not path.is_absolute():
                path = self._directory / path
            # A lookalike that isn't a file is left to VTE as a plain
            # click, so that a selection can still start there.
            if not path.is_file(): return
            self.emit("file-clicked", str(path), int(line), int(column))
        # Claim the click so that VTE doesn't get it too and start a
        # selection anchored in the middle of the match.
        click.set_state(Gtk.EventSequenceState.CLAIMED)

    def _init_properties(self):
        self.set_hexpand(True)
        self.set_vexpand(True)
        # Leave scrolling to the scrolled window around us and give it
        # pixels to work with, as Ptyxis does. VTE's own scrolling takes
        # a touchpad's pixel-sized deltas for lines and multiplies them
        # by a tenth of the terminal height, which sends a nudge flying.
        self.set_enable_fallback_scrolling(False)
        self.set_scroll_unit_is_pixels(True)
        self.set_scrollback_lines(10000)
        self.set_scroll_on_keystroke(True)
        self.set_scroll_on_output(False)
        self.set_font(Pango.FontDescription.from_string(
            "Berkeley Standard Mono Medium 10"))

    def _init_poll(self):
        # Watch the foreground command come and go, so that a test run,
        # an eval or a training job finishing can be told about. VTE's
        # shell termprops would say the same, and say it right away, but
        # only with shell integration that emits them, which we can't
        # count on. Three seconds, as the window polls git, is thus also
        # the shortest command that can be noticed at all, which suits
        # us: a command that returns in the blink of an eye is not one
        # worth a notification.
        self._poll_source = GLib.timeout_add_seconds(3, self._on_poll_timeout)

    def close(self):
        """Hang up the shell and stop watching it."""
        # Explicitly rather than when the widget is disposed: a terminal
        # is kept alive by the handlers its own children and its task
        # hold on it, so being taken out of the window is not enough.
        if self._poll_source is not None:
            GLib.source_remove(self._poll_source)
            self._poll_source = None
        if self._pid is None: return
        # SIGHUP as closing a terminal window does, to the shell and to
        # whatever it is running, which has a group of its own and would
        # otherwise be left behind by a shell that doesn't pass it on.
        groups = {self._get_foreground_group(), os.getpgid(self._pid)}
        for group in groups - {None}:
            with suppress(Exception):
                os.killpg(group, signal.SIGHUP)
        self._pid = None

    def _on_poll_timeout(self):
        if (group := self._get_foreground_group()) is None:
            # Back at the prompt, so whatever ran there is done.
            self._command_group = None
            self._command_started = None
            if self._command is not None:
                command, self._command = self._command, None
                self.emit("command-finished", command)
        else:
            if group != self._command_group:
                # A group of its own means a command of its own, which
                # is where the time it has been running starts from.
                self._command_group = group
                self._command_started = time.monotonic()
            if (command := self._get_command_name(group)) is not None:
                self._command = command
        return GLib.SOURCE_CONTINUE

    def _get_command_name(self, group):
        """Return the name of the command running in `group`, if it can be told."""
        # Walk down from the leader rather than scan all of /proc for
        # the group, this being on the poll: a few reads instead of one
        # per process, which measures a hundred times cheaper. It finds
        # the leader's descendants and not its siblings, but a wrapper's
        # agent is always below it, which is what we are here for.
        commands, todo = [], [group]
        while todo:
            pid = str(todo.pop())
            with suppress(Exception):
                commands.append((Path("/proc") / pid / "comm").read_text("utf-8").strip())
                todo += (Path("/proc") / pid / "task" / pid / "children").read_text("utf-8").split()
        # An agent behind a wrapper is named for the wrapper: codex is a
        # Node script whose leader reads 'MainThread', that being Node's
        # main thread. The agent itself runs below it all the same, so
        # take its name over the leader's wherever one of them is there.
        if agent := next((x for x in commands if x in AGENTS), None):
            return agent
        # The leader is the command that the shell started, which is what
        # the user typed, and the first one walked to above. It can be
        # gone while the rest of the group still runs, as at the head of
        # a pipeline, in which case the name from the previous poll is
        # the best we have. A command never named is never told about.
        return commands[0] if commands else None

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
        # Make the pty ourselves, which spawning via the terminal would
        # do for us, to have the name of its slave end for SLOPPIE_TTY.
        pty = self.pty_new_sync(Vte.PtyFlags.DEFAULT)
        self.set_pty(pty)
        # Note that pygobject keeps child_setup_data, unlike the
        # documented signature, making this ten arguments, not nine.
        # The environment given is added to the one inherited, so
        # SLOPPIE tells whatever runs here that it's running in Sloppie
        # and can leave desktop notifications to us — a bell is enough.
        # SLOPPIE_TTY is where to write that bell: an agent rings it from
        # a hook, which runs detached, with no terminal of its own to
        # find, but writing to the slave device works from anywhere.
        pty.spawn_async(str(self._directory),
                        [shell],
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
            # Without a shell the terminal is a blank box, so say why. The
            # window is there by now, this being called from the main loop,
            # long after the terminal was made and put in it.
            slop.util.show_error(self.get_root(), "Failed to start the shell", error.message)

    def get_selection(self):
        """Return the text selected in the terminal, or ``None`` if none."""
        # VTE keeps the selection after the terminal loses focus, so
        # this outlives the click that took focus to a header bar button.
        if not self.get_has_selection(): return None
        return self.get_text_selected(Vte.Format.TEXT)

    def _get_foreground_group(self):
        """Return the foreground process group, ``None`` if at the prompt."""
        # The pty knows what runs in it without any help from the shell:
        # its foreground process group is the shell's own only while the
        # shell waits for a command.
        if self._pid is None: return None
        if (pty := self.get_pty()) is None: return None
        try:
            group = os.tcgetpgrp(pty.get_fd())
        except Exception:
            return None
        return None if group == self._pid else group

    def get_command(self):
        """Return the name of the command running, ``None`` if at the prompt."""
        # Whatever the poll last saw, which is the command that the
        # shell started, not the children it went on to start itself.
        return self._command

    def get_command_elapsed(self):
        """Return seconds the command running has been, ``None`` if at the prompt."""
        if self._command_started is None: return None
        return time.monotonic() - self._command_started

    def get_foreground_commands(self):
        """Return the names of the commands running, empty if at the prompt."""
        if (group := self._get_foreground_group()) is None: return []
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
