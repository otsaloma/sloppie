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
import subprocess
import sys

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from slop import recent
from slop.git import DiffLine
from slop.git import parse_diff
from slop.git import SECTIONS

class TaskLayout(Gtk.OverlayLayout):

    """Layout that keeps the two sidebars of a task at a sixth each."""

    # A layout manager rather than TaskPage.do_size_allocate: a widget
    # that has a layout manager, as Gtk.Overlay does, never has its own
    # size_allocate called, GTK handing the whole job to the manager.

    def do_allocate(self, task, width, height, baseline):
        # Keep both sidebars at a sixth of the window width, the middle
        # getting the rest, minus the two one pixel paned handles.
        sidebar = round(width / 6)
        task._paned.set_position(sidebar)
        Gtk.OverlayLayout.do_allocate(self, task, width, height, baseline)
        # The right paned shifts its own position by the change in its
        # width, so it can only be set once it has been allocated the
        # width that follows from the left paned position set above.
        task._right_paned.set_position(width - 2 * sidebar - 2)

class TaskPage(Gtk.Overlay):

    """One task worked on: a repository, its diff, terminals and comments."""

    # Emitted when anything the window shows on behalf of the task
    # changes: the branch in the header bar, the file selection that
    # decides which of the window's actions apply.
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, repository):
        GObject.GObject.__init__(self)
        self.repository = repository
        self.branch = None
        self.config = slop.Config(repository)
        # The state of the window's wrap toggle while this task is the
        # one shown, starting out as it was left for this repository.
        self.wrap_lines = self.config.read_item("wrap-lines", True)
        # The stack of views, which the window's switcher is pointed at
        # for as long as this is the task shown.
        self.stack = None
        self._comment_sidebar = slop.CommentSidebar(repository)
        self._diff_view = slop.DiffView()
        self._file_sidebar = slop.FileSidebar()
        self._fingerprint = None
        self._paned = None
        self._right_paned = None
        self._shown_change = None
        self._stack_handler = None
        self._terminals = [slop.Terminal(repository.root) for i in range(3)]
        self._toast = slop.Toast()
        recent.add_repository(repository.root)
        self._init_widgets()
        self._init_signal_handlers()
        self.refresh()
        # Sloppie is started to begin a new task, and that work starts at
        # the terminal, so land there rather than on the diff view, which
        # is the first tab and would otherwise be the one shown.
        self.stack.set_visible_child_name("terminal-1")

    def _init_widgets(self):
        diff_scroller = Gtk.ScrolledWindow()
        diff_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        diff_scroller.set_child(self._diff_view)
        self.stack = Gtk.Stack()
        # The mnemonics only show the underline when Alt is held, the
        # focus shortcuts of the window do the actual moving of focus.
        self.stack.add_titled(diff_scroller, "diff", "_Diff").set_use_underline(True)
        # Only the first terminal is spelled out, the rest are numbered
        # and narrowed by CSS: [ Diff | Terminal | 2 | 3 ].
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
        # Files | diff or terminal | comments, with the middle
        # getting the extra space and the sidebars always visible.
        # Sidebar widths are set dynamically in do_size_allocate.
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
        # Clicking the stack switcher only switches the stack and leaves
        # focus on the switcher button, so focus the view shown here.
        self._stack_handler = self.stack.connect(
            "notify::visible-child", lambda *args: self.focus_shown_view())
        # Looking at a tab is seeing to whatever rang there.
        self.stack.connect("notify::visible-child", lambda *args:
                           self.stack.get_page(self.stack.get_visible_child())
                           .set_needs_attention(False))
        # Poll instead of watching the working tree, which would mean a
        # watch on each of possibly very many directories. A poll costs
        # one git command that skips ignored files, such as node_modules.
        source = GLib.timeout_add_seconds(3, self._on_poll_timeout)
        self.connect("destroy", lambda *args: GLib.source_remove(source))

    def get_selected_section(self):
        """Return the section of the file selected, if any."""
        change = self._file_sidebar.get_selected_change()
        return change.section if change is not None else None

    def _on_change_selected(self, sidebar, change, by_user):
        # The sidebar and the diff view belong together, so picking a
        # file should show its diff, even if the terminal was shown.
        # A reload reselecting a file should not steal the terminal.
        if by_user and change is not None:
            self._show_diff_view()
        # Let the window enable only the actions that apply to the file
        # selected. Staged changes are reverted by unstaging them first.
        self.emit("changed")
        # A refresh reselects the file selected, which lands here just
        # like the user picking a file. Only the latter should send the
        # diff view back to the top, the former should stay put.
        previous, self._shown_change = self._shown_change, change
        same = (change is not None and previous is not None and
                change.section == previous.section and
                change.path == previous.path)
        if change is None:
            return self._diff_view.set_diff([])
        try:
            text = self.repository.get_diff(change)
        except Exception as error:
            slop.util.show_error(self.get_root(), f"Failed to diff {change.name}", error)
            return self._diff_view.set_diff([])
        if len(text) > 2 * 1024 * 1024:
            # Rendering takes a second or so per megabyte of diff, and
            # a diff this big is not going to be read line by line
            # anyway, so say that instead of freezing to render it.
            return self._diff_view.set_diff(
                [DiffLine("meta", None, None, "Large diffs are not rendered")])
        self._diff_view.set_diff(parse_diff(text), change.path, keep_position=same)

    def _apply(self, operation, change, message):
        """Run `operation` on `change`, reload and return ``True`` if done."""
        success = True
        try:
            operation(change)
        except Exception as error:
            slop.util.show_error(self.get_root(), message, error)
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
        if slop.util.confirm(self.get_root(), f"Revert changes in {change.name}?",
                             "The changes will be permanently lost.",
                             "Revert"):
            if self._apply(self.repository.revert, change,
                           f"Failed to revert {change.name}"):
                self._toast.flash(f"Reverted file {change.name}")

    def trash(self):
        change = self._file_sidebar.get_selected_change()
        if slop.util.confirm(self.get_root(), f"Move {change.name} to the trash?",
                             "The file can be restored from the trash.",
                             "Trash"):
            if self._apply(self.repository.trash, change,
                           f"Failed to trash {change.name}"):
                self._toast.flash(f"Trashed file {change.name}")

    def edit(self):
        # Without a file selected, edit the repository root, which lands
        # emacs in dired, from where any file can be opened.
        change = self._file_sidebar.get_selected_change()
        if change is None:
            return self._edit(str(self.repository.root))
        arguments = [str(self.repository.root / change.path)]
        if position := self._diff_view.get_position():
            # Emacs takes the position to visit as '+LINE:COLUMN'
            # preceding the file that it applies to.
            arguments.insert(0, "+{:d}:{:d}".format(*position))
        self._edit(*arguments)

    def _on_file_clicked(self, terminal, path, line, column):
        self._edit(f"+{line:d}:{column:d}", path)

    def _edit(self, *arguments):
        try:
            # Give emacs a session of its own, so that it neither dies
            # along with sloppie nor takes signals meant for sloppie.
            subprocess.Popen(["emacs", *arguments], start_new_session=True)
        except Exception as error:
            slop.util.show_error(self.get_root(), "Failed to start emacs", error)

    def commit(self):
        dialog = slop.CommitDialog(self.get_root(), self.repository)
        dialog.connect("committed", self._on_committed)
        dialog.present()

    def add_comment(self):
        # A selection in the terminal on screen means a comment on that
        # piece of the agent's output, which belongs to no file. The
        # terminal being what the user is reading, it wins over whatever
        # was left selected in the diff view.
        view = self.get_shown_view()
        if isinstance(view, slop.Terminal):
            if (hunk := view.get_selection()) is not None:
                return self._comment_sidebar.new_comment(hunk=hunk)
        # A selection in the diff view means a comment on that piece of
        # code, in the file whose diff is shown. Without one the comment
        # is on the changes as a whole.
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
        # Pasting into a shell prompt would leave whatever the comment
        # happens to contain there to be run, so hand the text over only
        # to an agent that is actually running and waiting for a prompt.
        terminal = self._terminals[0]
        commands = terminal.get_foreground_commands()
        if not any(x in ("claude", "codex") for x in commands):
            self._toast.flash("No agent running in the terminal")
            return False
        # Show the terminal, the paste being there to be read and sent
        # by the user, who presses Enter, which we deliberately don't.
        self.stack.set_visible_child_name("terminal-1")
        self.focus_shown_view()
        # Paste rather than feed the text, which is to say as bracketed
        # paste, where the agent takes it for text and not for keys
        # pressed, and where VTE strips the control characters that a
        # hunk could otherwise smuggle in.
        terminal.paste_text(text)
        return True

    def run(self):
        if command := self.config.read_item("run-command"):
            return self._run(command)
        # Nothing to run yet, so ask what to run and then run that.
        dialog = slop.RunDialog(self.get_root(), self.config)
        dialog.connect("saved", lambda dialog, command: self._run(command))
        dialog.present()

    def configure_run(self):
        slop.RunDialog(self.get_root(), self.config).present()

    def _run(self, command):
        try:
            # Run via the shell, so that the command can be anything
            # that would work in a terminal, and give it a session of
            # its own, so that it neither dies along with sloppie nor
            # takes signals meant for sloppie.
            subprocess.Popen(["sh", "-c", command],
                             cwd=str(self.repository.root),
                             start_new_session=True)
        except Exception as error:
            return slop.util.show_error(
                self.get_root(), f"Failed to run {command}", error)
        # The command runs out of sight, so say that it was started.
        self._toast.flash(f"Running {command}")

    def _on_committed(self, dialog):
        self._toast.flash("Committed changes")
        self.refresh()

    def focus(self, target):
        """Move focus to `target`: a sidebar section, the diff or a terminal."""
        if target in SECTIONS:
            # Show the diff of the file focused, also when it was the
            # one selected already and no selection change follows.
            if self._file_sidebar.focus_section(target):
                self._show_diff_view()
            return
        if target == "terminal":
            # Cycle through the terminals, so that repeated presses take
            # the user from the diff view to the first one and on.
            names = [f"terminal-{i+1}" for i in range(len(self._terminals))]
            shown = self.stack.get_visible_child_name()
            target = (names[(names.index(shown) + 1) % len(names)]
                      if shown in names else names[0])
        # Set the visible child even if unchanged, in which case no
        # notification follows and focus needs to be moved here.
        self.stack.set_visible_child_name(target)
        self.focus_shown_view()

    def switch_tab(self, step):
        """Step `step` tabs right in the stack, wrapping around."""
        names = ["diff"] + [f"terminal-{i+1}" for i in range(len(self._terminals))]
        index = names.index(self.stack.get_visible_child_name()) + step
        self.stack.set_visible_child_name(names[index % len(names)])
        self.focus_shown_view()

    def _on_terminal_bell(self, terminal, page, index):
        # A bell means that whatever runs in the terminal wants
        # attention: an agent done with its turn, a build finished.
        self._alert_terminal(terminal, page, index, "Agent wants something")

    def _on_terminal_command_finished(self, terminal, command, page, index):
        # A command that ran long enough to be noticed at all is one that
        # the user has likely walked away from: a test run, an eval, a
        # training job. Whether it succeeded is between the command and
        # the shell, we only know that the terminal is at the prompt.
        self._alert_terminal(terminal, page, index, f"{command} finished")

    def _alert_terminal(self, terminal, page, index, body):
        window = self.get_root()
        # The switcher marks the tab with a dot, but only as long as it's
        # not the tab on screen, so don't mark the one being looked at,
        # which would leave a mark to appear on switching away from it.
        if page.get_child() is not self.stack.get_visible_child():
            page.set_needs_attention(True)
        # Sitting at this very terminal, the user has seen it all
        # happen, so skip the notification rather than pop one up on top
        # of what it's about.
        if window.is_active() and window.get_focus() is terminal: return
        # The dot is no use when the window is behind others, so also
        # send a desktop notification. It carries our application id,
        # which is how GNOME shows it under Sloppie's name and icon and,
        # when clicked, raises a Sloppie window. Include the repository
        # in the id, so that a second alert replaces the notification of
        # the first, but another window's alerts keep their own.
        notification = Gio.Notification.new(self.repository.root.name)
        notification.set_body(body)
        # The application id gets us a small icon in the header of the
        # notification, an icon of our own gets the big one beside the
        # text, the same as notify-send's --icon. Give it the same icon,
        # there being nothing better to say than that this is Sloppie.
        notification.set_icon(Gio.ThemedIcon.new("io.otsaloma.sloppie"))
        # Of the four priorities, only two do anything in GNOME Shell:
        # HIGH differs from NORMAL by queue order alone, LOW is never
        # shown as a banner. URGENT is the one that gets through Do Not
        # Disturb and a fullscreen window, at the price of a banner that
        # stays on screen until dismissed, there being no way to have
        # one that is both urgent and transient.
        notification.set_priority(Gio.NotificationPriority.URGENT)
        window.get_application().send_notification(
            f"{self.repository.root}-terminal-{index}", notification)

    def _show_diff_view(self):
        # Focus belongs to the sidebar here, so block the handler that
        # would move it along to the view shown.
        with GObject.signal_handler_block(self.stack, self._stack_handler):
            self.stack.set_visible_child_name("diff")

    def get_shown_view(self):
        """Return the view shown in the stack, the diff view or a terminal."""
        # Each page of the stack is a scroller wrapping the actual view.
        return self.stack.get_visible_child().get_child()

    def focus_shown_view(self):
        # Focus the view itself, not the scroller around it.
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
        # Give emacs an existing file to edit, so that it starts from
        # valid JSON rather than an empty buffer in a directory that it
        # would have to offer to create.
        if not self.config.path.exists():
            self.config.path.parent.mkdir(parents=True, exist_ok=True)
            self.config.path.write_text("{}\n", "utf-8")
        self._edit(str(self.config.path))

    def _on_poll_timeout(self):
        try:
            fingerprint = self.repository.get_fingerprint()
        except Exception as error:
            # No dialog here, nor anywhere else reached from this poll:
            # a repository gone bad would keep raising the same error
            # every few seconds, for as long as the window is open.
            print(f"sloppie: {error}", file=sys.stderr)
            return GLib.SOURCE_CONTINUE
        if fingerprint != self._fingerprint:
            self.refresh()
        return GLib.SOURCE_CONTINUE

    def refresh(self):
        """Reload the list of changed files from git."""
        try:
            # Take the fingerprint first, so that a change made while
            # we're reloading is caught by the next poll, not missed.
            self._fingerprint = self.repository.get_fingerprint()
            changes = self.repository.list_changes()
            branch = self.repository.get_branch()
        except Exception as error:
            # Reached from the poll too, hence no dialog, see above.
            print(f"sloppie: {error}", file=sys.stderr)
            return
        self.branch = branch
        # Comments are written against a branch, so switching branch
        # puts the ones shown aside and brings back any of the new one.
        self._comment_sidebar.set_branch(branch)
        self._file_sidebar.set_changes(changes)
        self.emit("changed")
