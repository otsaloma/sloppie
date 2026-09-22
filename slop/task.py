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

import re
import slop
import subprocess
import sys

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from slop import recent
from slop import util
from slop.git import DiffLine
from slop.git import parse_diff
from slop.git import SECTIONS
from slop.terminal import AGENTS
from slop.terminal import RESUME_COMMANDS

def format_elapsed(seconds):
    """Return `seconds` as ``[HH:]MM:SS``, ``None`` staying ``None``."""
    if seconds is None: return None
    hours, seconds = divmod(round(seconds), 3600)
    minutes, seconds = divmod(seconds, 60)
    if hours: return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:d}:{seconds:02d}"

class TaskLayout(Gtk.OverlayLayout):

    """Layout that keeps the two sidebars of a task at a sixth each."""

    # Not TaskPage.do_size_allocate, which GTK never calls on a widget
    # that has a layout manager, as Gtk.Overlay does.

    def do_allocate(self, task, width, height, baseline):
        sidebar = round(width / 6)
        task._paned.set_position(sidebar)
        Gtk.OverlayLayout.do_allocate(self, task, width, height, baseline)
        # The right paned shifts its position by the change in its width,
        # so set it only once allocated. Minus the two 1 px handles.
        task._right_paned.set_position(width - 2 * sidebar - 2)

class TaskPage(Gtk.Overlay):

    """One task worked on: a repository, its diff, terminals and comments."""

    # Emitted when anything the window shows of the task changes.
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, repository, setup=None):
        GObject.GObject.__init__(self)
        self.repository = repository
        self.branch = None
        self.config = slop.Config(repository)
        # What the dashboard shows on this task's card.
        self.command = None
        self.comments = 0
        self.elapsed = None
        self.lines_added = 0
        self.lines_removed = 0
        # 'waiting' or 'working', also a CSS class of the card.
        self.status = "working"
        self.wrap_lines = self.config.read_item("wrap-lines")
        self.stack = None
        self._comment_sidebar = slop.CommentSidebar(repository)
        self._diff_view = slop.DiffView()
        self._file_sidebar = slop.FileSidebar()
        self._fingerprint = None
        self._paned = None
        self._poll_source = None
        self._right_paned = None
        self._shown_change = None
        self._stack_handler = None
        self._terminals = [slop.Terminal(repository.root, setup if i == 0 else None)
                           for i in range(3)]
        self._toast = slop.Toast()
        # Timeouts due to withdraw notifications sent, by terminal index.
        self._withdraw_sources = {}
        recent.add_repository(repository.root)
        self._init_widgets()
        self._init_signal_handlers()
        self.refresh()
        self.stack.set_visible_child_name("terminal-1")

    def _init_widgets(self):
        diff_scroller = Gtk.ScrolledWindow()
        diff_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        diff_scroller.set_child(self._diff_view)
        self.stack = Gtk.Stack()
        # Mnemonics only for the underline, the window's focus shortcuts
        # do the moving of focus.
        self.stack.add_titled(diff_scroller, "diff", "_Diff").set_use_underline(True)
        for i, terminal in enumerate(self._terminals, start=1):
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.set_child(terminal)
            title = "_Terminal" if i == 1 else str(i)
            page = self.stack.add_titled(scroller, f"terminal-{i}", title)
            page.set_use_underline(True)
            terminal.connect("bell", self._on_terminal_bell, page, i)
            terminal.connect("command-finished",
                             self._on_terminal_command_finished, page, i)
            terminal.connect("copied",
                             lambda *args: self._toast.flash("Copied to the clipboard"))
        self._right_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._right_paned.set_start_child(self.stack)
        self._right_paned.set_resize_start_child(True)
        self._right_paned.set_shrink_start_child(False)
        self._right_paned.set_end_child(self._comment_sidebar)
        self._right_paned.set_resize_end_child(False)
        self._right_paned.set_shrink_end_child(False)
        self._paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._paned.set_start_child(self._file_sidebar)
        self._paned.set_resize_start_child(False)
        self._paned.set_shrink_start_child(False)
        self._paned.set_end_child(self._right_paned)
        self._paned.set_resize_end_child(True)
        self._paned.set_shrink_end_child(False)
        self.set_child(self._paned)
        self.add_overlay(self._toast)
        self.set_layout_manager(TaskLayout())
        self._apply_wrap_lines()

    def _init_signal_handlers(self):
        self._file_sidebar.connect("change-selected", self._on_change_selected)
        for terminal in self._terminals:
            terminal.connect("file-clicked", self._on_file_clicked)
        # Clicking the stack switcher leaves focus on the switcher.
        self._stack_handler = self.stack.connect(
            "notify::visible-child", lambda *args: self.focus_shown_view())
        self.stack.connect("notify::visible-child",
                           lambda *args: self.seen())
        # Watching the working tree would need a watch per directory.
        # A poll is one git command that skips ignored files.
        self._poll_source = GLib.timeout_add_seconds(3, self._on_poll_timeout)

    def close(self):
        """Stop polling and hang up the shells, the task being closed."""
        # Not on dispose, which never comes, the handlers on the task's
        # children referencing it back.
        if self._poll_source is not None:
            GLib.source_remove(self._poll_source)
            self._poll_source = None
        for terminal in self._terminals:
            terminal.close()

    def get_selected_section(self):
        """Return the section of the file selected, if any."""
        change = self._file_sidebar.get_selected_change()
        return change.section if change is not None else None

    def _on_change_selected(self, sidebar, change, by_user):
        # A reload reselecting a file should not steal the terminal.
        if by_user and change is not None:
            self._show_diff_view()
        self.emit("changed")
        # A reload reselecting the same file should keep the position.
        previous, self._shown_change = self._shown_change, change
        same = (change is not None and previous is not None and
                change.section == previous.section and
                change.path == previous.path)
        if change is None:
            return self._diff_view.set_diff([])
        try:
            text = self.repository.get_diff(change)
        except Exception as error:
            util.show_error(self.get_root(), f"Failed to diff {change.name}", error)
            return self._diff_view.set_diff([])
        if len(text) > 2 * 1024 * 1024:
            # Rendering takes a second or so per megabyte.
            return self._diff_view.set_diff(
                [DiffLine("meta", None, None, "Large diffs are not rendered")])
        self._diff_view.set_diff(parse_diff(text), change.path, keep_position=same)

    def _apply(self, operation, change, message):
        """Run `operation` on `change`, reload and return ``True`` if done."""
        success = True
        try:
            operation(change)
        except Exception as error:
            util.show_error(self.get_root(), message, error)
            success = False
        self.refresh()
        return success

    def stage(self):
        change = self._file_sidebar.get_selected_change()
        self._apply(self.repository.stage, change,
                    f"Failed to stage {change.name}")

    def unstage(self):
        change = self._file_sidebar.get_selected_change()
        self._apply(self.repository.unstage, change,
                    f"Failed to unstage {change.name}")

    def revert(self):
        change = self._file_sidebar.get_selected_change()
        if util.confirm(self.get_root(), f"Revert changes in {change.name}?",
                        "The changes will be permanently lost.",
                        "Revert", destructive=True):
            if self._apply(self.repository.revert, change,
                           f"Failed to revert {change.name}"):
                self._toast.flash(f"Reverted file {change.name}")

    def trash(self):
        change = self._file_sidebar.get_selected_change()
        if util.confirm(self.get_root(), f"Move {change.name} to the trash?",
                        "The file can be restored from the trash.",
                        "Trash", destructive=True):
            if self._apply(self.repository.trash, change,
                           f"Failed to trash {change.name}"):
                self._toast.flash(f"Trashed file {change.name}")

    def edit(self):
        change = self._file_sidebar.get_selected_change()
        if change is None:
            return self._edit(str(self.repository.root))
        arguments = [str(self.repository.root / change.path)]
        if position := self._diff_view.get_position():
            arguments.insert(0, "+{:d}:{:d}".format(*position))
        self._edit(*arguments)

    def _on_file_clicked(self, terminal, path, line, column):
        self._edit(f"+{line:d}:{column:d}", path)

    def _edit(self, *arguments):
        try:
            # A session of its own, so as to not die along with sloppie.
            subprocess.Popen(["emacs", *arguments], start_new_session=True)
        except Exception as error:
            util.show_error(self.get_root(), "Failed to start emacs", error)

    def commit(self):
        dialog = slop.CommitDialog(self.get_root(), self.repository)
        dialog.connect("committed", self._on_committed)
        dialog.present()

    def add_comment(self):
        # A selection in the terminal shown wins over one left in the
        # diff view.
        view = self.get_shown_view()
        if isinstance(view, slop.Terminal):
            if (hunk := view.get_selection()) is not None:
                return self._comment_sidebar.new_comment(hunk=hunk)
        hunk = self._diff_view.get_selection()
        change = self._file_sidebar.get_selected_change()
        if hunk is None or change is None:
            return self._comment_sidebar.new_comment()
        self._comment_sidebar.new_comment(change.path, hunk)

    def send_comments(self):
        self._comment_sidebar.send_unsent_comments()

    def delete_sent_comments(self):
        self._comment_sidebar.delete_sent_comments()

    def send_to_agent(self, text):
        """Paste `text` into the agent running in the first terminal."""
        # A shell prompt would run whatever the text happens to contain.
        terminal = self._terminals[0]
        if not terminal.is_agent_running():
            self._toast.flash("No agent running in the terminal")
            return False
        # The user presses Enter, deliberately not us.
        self.focus("terminal-1")
        # Bracketed paste, which the agent takes for text, not keys, and
        # from which VTE strips control characters.
        terminal.paste_text(text)
        return True

    def resume_agent(self):
        """Run the command to resume the agent session last quit here."""
        command = recent.get_resume_command(self.repository.root)
        if command is None:
            return self._toast.flash("No agent session to resume")
        if not isinstance(command, str) or not any(
                re.fullmatch(x, command) for x in RESUME_COMMANDS.values()):
            return self._toast.flash("Invalid resume command")
        terminal = self._terminals[0]
        if terminal.is_running():
            return self._toast.flash("Something is running in the terminal")
        self.focus("terminal-1")
        terminal.feed_child(f"{command}\n".encode())

    def run(self):
        if command := self.config.read_item("run-command"):
            return self._run(command)
        dialog = slop.RunDialog(self.get_root(), self.config)
        dialog.connect("saved", lambda dialog, command: self._run(command))
        dialog.present()

    def configure_run(self):
        slop.RunDialog(self.get_root(), self.config).present()

    def _run(self, command):
        try:
            # A session of its own, as in _edit.
            subprocess.Popen(["sh", "-c", command],
                             cwd=str(self.repository.root),
                             start_new_session=True)
        except Exception as error:
            return util.show_error(
                self.get_root(), f"Failed to run {command}", error)
        self._toast.flash(f"Running {command}")

    def _on_committed(self, dialog):
        self._toast.flash("Committed changes")
        self.refresh()

    def focus(self, target):
        """Move focus to `target`: a sidebar section, the diff or a terminal."""
        if target in SECTIONS:
            # Also when the file was selected already and no selection
            # change follows.
            if self._file_sidebar.focus_section(target):
                self._show_diff_view()
            return
        if target == "terminal":
            names = [f"terminal-{i+1}" for i in range(len(self._terminals))]
            shown = self.stack.get_visible_child_name()
            target = (names[(names.index(shown) + 1) % len(names)]
                      if shown in names else names[0])
        # If unchanged, no notification follows to move focus.
        self.stack.set_visible_child_name(target)
        self.focus_shown_view()

    def switch_tab(self, step):
        """Step `step` tabs right in the stack, wrapping around."""
        children = list(self.stack)
        index = children.index(self.stack.get_visible_child()) + step
        self.stack.set_visible_child(children[index % len(children)])
        self.focus_shown_view()

    def _on_terminal_bell(self, terminal, page, index):
        self._alert_terminal(terminal, page, index, "Agent wants something")

    def _on_terminal_command_finished(self, terminal, command, page, index):
        self._alert_terminal(terminal, page, index, f"{command} finished")

    def _alert_terminal(self, terminal, page, index, body):
        window = self.get_root()
        # Mapped means shown, where a mark would be left stale.
        if not terminal.get_mapped():
            page.set_needs_attention(True)
            self._update_status()
            self.emit("changed")
        if window.is_active() and window.get_focus() is terminal: return
        notification = Gio.Notification.new(self.repository.root.name)
        notification.set_body(body)
        # A large body icon alongside GNOME's small application icon.
        notification.set_icon(Gio.ThemedIcon.new("io.otsaloma.sloppie"))
        # URGENT bypasses GNOME's Do Not Disturb and fullscreen suppression;
        # HIGH only changes queue order. Urgent banners stay until dismissed,
        # and GNotification has no transient flag, so withdraw ours below.
        notification.set_priority(Gio.NotificationPriority.URGENT)
        application = window.get_application()
        notification_id = f"{self.repository.root}-terminal-{index}"
        application.send_notification(notification_id, notification)
        if index in self._withdraw_sources:
            # The previous alert's timeout must not cut this one short.
            GLib.source_remove(self._withdraw_sources.pop(index))
        self._withdraw_sources[index] = GLib.timeout_add_seconds(
            3, self._on_withdraw_timeout, application, notification_id, index)

    def _on_withdraw_timeout(self, application, notification_id, index):
        application.withdraw_notification(notification_id)
        del self._withdraw_sources[index]
        return GLib.SOURCE_REMOVE

    def _show_diff_view(self):
        # Leave focus in the sidebar.
        with GObject.signal_handler_block(self.stack, self._stack_handler):
            self.stack.set_visible_child_name("diff")

    def get_shown_view(self):
        """Return the view shown in the stack, the diff view or a terminal."""
        # Each page of the stack is a scroller wrapping the actual view.
        return self.stack.get_visible_child().get_child()

    def focus_shown_view(self):
        self.get_shown_view().grab_focus()

    def set_wrap_lines(self, wrap):
        self.wrap_lines = wrap
        self._apply_wrap_lines()
        self.config.write_item("wrap-lines", wrap)

    def _apply_wrap_lines(self):
        self._diff_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR
                                      if self.wrap_lines else
                                      Gtk.WrapMode.NONE)

    def configure(self):
        # Every key spelled out, rather than an empty buffer.
        self.config.write_as_full()
        self._edit(str(self.config.path))

    def _on_poll_timeout(self):
        self._update_status()
        try:
            fingerprint = self.repository.get_fingerprint()
        except Exception as error:
            # No dialog on the poll, which would repeat it every few seconds.
            print(f"sloppie: {error}", file=sys.stderr)
            return GLib.SOURCE_CONTINUE
        if fingerprint != self._fingerprint:
            self.refresh()
        return GLib.SOURCE_CONTINUE

    def _update_status(self):
        """Work out what the dashboard should say about this task."""
        # An agent that rang is waiting, the bell being the only thing an
        # agent tells us.
        command = self._terminals[0].get_command()
        page = self.stack.get_page(self._terminals[0].get_parent())
        status = ("waiting"
                  if command in AGENTS and page.get_needs_attention() else
                  "working")
        elapsed = format_elapsed(self._terminals[0].get_command_elapsed())
        comments = self._comment_sidebar.count_unsent()
        if (command, comments, elapsed, status) == \
           (self.command, self.comments, self.elapsed, self.status): return
        self.command = command
        self.comments = comments
        self.elapsed = elapsed
        self.status = status
        self.emit("changed")

    def is_running(self):
        """Return ``True`` if a command runs in any of the terminals."""
        return any(x.is_running() for x in self._terminals)

    def get_attention(self):
        """Return ``True`` if any terminal of this task rang unseen."""
        return any(self.stack.get_page(x).get_needs_attention()
                   for x in self.stack)

    def seen(self):
        """Mark whatever the view shown rang about as seen."""
        self.stack.get_page(self.stack.get_visible_child()).set_needs_attention(False)
        self._update_status()
        self.emit("changed")

    def refresh(self):
        """Reload the list of changed files from git."""
        try:
            # First, so that a change made while reloading is caught by
            # the next poll.
            self._fingerprint = self.repository.get_fingerprint()
            changes = self.repository.list_changes()
            branch = self.repository.get_branch()
        except Exception as error:
            # Reached from the poll too, hence no dialog.
            print(f"sloppie: {error}", file=sys.stderr)
            return
        self.branch = branch
        self.lines_added = self.lines_removed = 0
        for change in (x for y in changes.values() for x in y):
            if change.added or change.removed:
                self.lines_added += change.added or 0
                self.lines_removed += change.removed or 0
            elif change.status == "D":
                # A binary file gone, or an empty one.
                self.lines_removed += 1
            else:
                # A binary file changed or a file merely renamed, counted
                # as one to show that there is something.
                self.lines_added += 1
        self._comment_sidebar.set_branch(branch)
        self._file_sidebar.set_changes(changes)
        self.emit("changed")
