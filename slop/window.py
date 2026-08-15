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

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from slop.git import parse_diff
from slop.git import SECTIONS

class Window(Gtk.ApplicationWindow):

    def __init__(self, repository=None):
        GObject.GObject.__init__(self)
        self.repository = repository
        # All of these are set once we have a repository, until then the
        # window holds nothing but the open button.
        self.config = None
        self._branch_label = None
        self._comment_sidebar = None
        self._diff_view = None
        self._file_sidebar = None
        self._fingerprint = None
        self._paned = None
        self._right_paned = None
        self._shown_change = None
        self._stack = None
        self._stack_handler = None
        self._terminals = []
        self._toast = None
        self._init_properties()
        if repository is None:
            # Launched from a launcher rather than a terminal, with no
            # directory to fall back on, so ask which repository to open
            # and build the rest of the window once we know.
            return self._init_open_button()
        self._init_repository()

    def _init_open_button(self):
        button = Gtk.Button(label="_Open Repository", use_underline=True)
        button.add_css_class("suggested-action")
        button.set_halign(Gtk.Align.CENTER)
        button.set_valign(Gtk.Align.CENTER)
        button.connect("clicked", self._on_open_clicked)
        self.set_child(button)

    def _on_open_clicked(self, button):
        dialog = Gtk.FileDialog(modal=True, title="Open Repository")
        dialog.select_folder(self, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            file = dialog.select_folder_finish(result)
        except GLib.Error:
            # The user dismissed the dialog.
            return
        try:
            self.repository = slop.Repository(file.get_path())
        except RuntimeError as error:
            # Leave the button be, the user can try another directory.
            return print(f"sloppie: {error}", file=sys.stderr)
        # The open button goes away as the widgets built here take its
        # place as the child of the window.
        self._init_repository()

    def _init_repository(self):
        self.config = slop.Config(self.repository)
        self._comment_sidebar = slop.CommentSidebar(self.repository)
        self._diff_view = slop.DiffView()
        self._file_sidebar = slop.FileSidebar()
        self._terminals = [slop.Terminal(self.repository.root) for i in range(3)]
        self._toast = slop.Toast()
        self._init_actions()
        self._init_widgets()
        self._init_focus_shortcuts()
        self._init_signal_handlers()
        self.load_css()
        self.refresh()

    def _init_actions(self):
        # These are the actions of the file sidebar's context menu, which
        # shows the accelerators added to the shortcut controller below.
        # They start out disabled, being no-ops without a file selected.
        # The shortcuts run in the capture phase, so that they beat the
        # terminal, which would eat them and pass them on to the shell.
        shortcuts = Gtk.ShortcutController(
            propagation_phase=Gtk.PropagationPhase.CAPTURE)
        for name, accelerator, callback in (
                ("stage", "<Control>s", self._on_stage_activate),
                ("unstage", "<Control>u", self._on_unstage_activate),
                ("revert", None, self._on_revert_activate),
                ("trash", None, self._on_trash_activate),
                ("edit", "<Control>e", self._on_edit_activate)):
            action = Gio.SimpleAction(name=name, enabled=False)
            action.connect("activate", callback)
            self.add_action(action)
            if accelerator is None: continue
            shortcuts.add_shortcut(Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string(accelerator),
                action=Gtk.NamedAction.new(f"win.{name}")))
        # Committing is always possible, since an amend can be done even
        # without staged changes. Ctrl+Enter needs the capture phase too,
        # the terminal otherwise passing it on to the shell as a plain Enter.
        action = Gio.SimpleAction(name="commit")
        action.connect("activate", self._on_commit_activate)
        self.add_action(action)
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control>Return"),
            action=Gtk.NamedAction.new("win.commit")))
        # A comment can likewise be written at any time, with no file
        # selected too, being a comment on the changes as a whole.
        action = Gio.SimpleAction(name="add-comment")
        action.connect("activate", self._on_add_comment_activate)
        self.add_action(action)
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control>m"),
            action=Gtk.NamedAction.new("win.add-comment")))
        # Running takes the capture phase too, so that F5 works the same
        # with the focus in a terminal as anywhere else in the window.
        action = Gio.SimpleAction(name="run")
        action.connect("activate", self._on_run_activate)
        self.add_action(action)
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("F5"),
            action=Gtk.NamedAction.new("win.run")))
        action = Gio.SimpleAction(name="configure-run")
        action.connect("activate", self._on_configure_run_activate)
        self.add_action(action)
        # Closing the only window quits the application, so both of the
        # customary accelerators can just close the window.
        for accelerator in ("<Control>w", "<Control>q"):
            shortcuts.add_shortcut(Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string(accelerator),
                action=Gtk.NamedAction.new("window.close")))
        self.add_controller(shortcuts)
        # This is the toggle in the header bar menu, which starts out in
        # whatever state it was left in for this repository.
        wrap = self.config.read_item("wrap-lines", True)
        self._diff_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR
                                      if wrap else
                                      Gtk.WrapMode.NONE)
        action = Gio.SimpleAction.new_stateful(
            "wrap-lines", None, GLib.Variant.new_boolean(wrap))
        action.connect("change-state", self._on_wrap_lines_change_state)
        self.add_action(action)
        action = Gio.SimpleAction(name="about")
        action.connect("activate", self._on_about_activate)
        self.add_action(action)

    def _init_focus_shortcuts(self):
        # Alt accelerators that only move focus, matching the mnemonics
        # underlined in the sidebar section titles and the stack
        # switcher when Alt is held. They run in the capture phase, so
        # that they beat both those mnemonics, which would move focus
        # elsewhere, and the terminal, which would eat them.
        action = Gio.SimpleAction(name="focus", parameter_type=GLib.VariantType("s"))
        action.connect("activate", self._on_focus_activate)
        self.add_action(action)
        shortcuts = Gtk.ShortcutController(
            propagation_phase=Gtk.PropagationPhase.CAPTURE)
        for target, accelerator in (("staged", "<Alt>s"),
                                    ("unstaged", "<Alt>u"),
                                    ("untracked", "<Alt>n"),
                                    ("diff", "<Alt>d"),
                                    ("terminal", "<Alt>t")):
            shortcuts.add_shortcut(Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string(accelerator),
                action=Gtk.NamedAction.new("win.focus"),
                arguments=GLib.Variant("s", target)))
        self.add_controller(shortcuts)

    def _init_properties(self):
        geometry = Gdk.Display.get_default().get_monitors()[0].get_geometry()
        self.set_default_size(round(0.7 * geometry.width), round(0.8 * geometry.height))
        self.set_title("Sloppie")

    def _init_signal_handlers(self):
        self._file_sidebar.connect("change-selected", self._on_change_selected)
        # Clicking the stack switcher only switches the stack and leaves
        # focus on the switcher button, so focus the view shown here.
        self._stack_handler = self._stack.connect(
            "notify::visible-child", lambda *args: self._focus_stack_view())
        # Poll instead of watching the working tree, which would mean a
        # watch on each of possibly very many directories. A poll costs
        # one git command that skips ignored files, such as node_modules.
        source = GLib.timeout_add_seconds(3, self._on_poll_timeout)
        self.connect("destroy", lambda *args: GLib.source_remove(source))

    def _init_widgets(self):
        header = Gtk.HeaderBar()
        # The icon theme has no commit icon, a save icon being the
        # closest thing.
        commit = Gtk.Button(action_name="win.commit",
                            icon_name="object-select-symbolic",
                            tooltip_text="Commit (Ctrl+Enter)")
        header.pack_start(commit)
        # The repository and the branch at the left end, styled like a
        # window title and subtitle, but left-aligned and ellipsized to
        # fit whatever space is left over by the rest of the header bar.
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("slop-header-title")
        # Center the two lines together, the box being given the full
        # height of the header bar, which they don't fill.
        box.set_valign(Gtk.Align.CENTER)
        # Claim all the width that the rest of the header bar leaves.
        box.set_hexpand(True)
        title = Gtk.Label(label=self.repository.root.name, xalign=0)
        title.add_css_class("title")
        self._branch_label = Gtk.Label(xalign=0)
        for label in (title, self._branch_label):
            label.set_ellipsize(Pango.EllipsizeMode.END)
            # The header bar keeps the stack switcher centered only as
            # long as what's packed at the start fits left of center, so
            # ask for no width at all. Expanding above still gives these
            # all the space that is actually free, ellipsizing the rest.
            label.set_max_width_chars(1)
            box.append(label)
        header.pack_start(box)
        switcher = Gtk.StackSwitcher()
        header.set_title_widget(switcher)
        menu = Gio.Menu()
        menu.append("Configure Run Command…", "win.configure-run")
        menu.append("Wrap Lines", "win.wrap-lines")
        section = Gio.Menu()
        section.append("About Sloppie", "win.about")
        menu.append_section(None, section)
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic",
                                       menu_model=menu,
                                       primary=True))
        # Packed after the menu, which puts it left of the menu, the
        # header bar filling its end from the right inwards.
        header.pack_end(Gtk.Button(action_name="win.add-comment",
                                   icon_name="chat-message-new-symbolic",
                                   tooltip_text="Add Comment (Ctrl+M)"))
        header.pack_end(Gtk.Button(action_name="win.run",
                                   icon_name="media-playback-start-symbolic",
                                   tooltip_text="Run (F5)"))
        self.set_titlebar(header)
        diff_scroller = Gtk.ScrolledWindow()
        diff_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        diff_scroller.set_child(self._diff_view)
        self._stack = Gtk.Stack()
        # The mnemonics only show the underline when Alt is held, the
        # focus shortcuts of the window do the actual moving of focus.
        self._stack.add_titled(diff_scroller, "diff", "_Diff").set_use_underline(True)
        # Only the first terminal is spelled out, the rest are numbered
        # and narrowed by CSS: [ Diff | Terminal | 2 | 3 ].
        for i, terminal in enumerate(self._terminals, start=1):
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.set_child(terminal)
            title = "_Terminal" if i == 1 else str(i)
            page = self._stack.add_titled(scroller, f"terminal-{i}", title)
            page.set_use_underline(True)
        switcher.set_stack(self._stack)
        # The switcher builds a button per page in the order added, but
        # hands out no reference to them, so walk its children instead.
        for button in list(switcher)[2:]:
            button.add_css_class("slop-narrow-tab")
        # Files | diff or terminal | comments, with the middle
        # getting the extra space and the sidebars always visible.
        # Sidebar widths are set dynamically in do_size_allocate.
        self._right_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._right_paned.set_start_child(self._stack)
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
        overlay = Gtk.Overlay()
        overlay.set_child(self._paned)
        overlay.add_overlay(self._toast)
        self.set_child(overlay)

    def do_size_allocate(self, width, height, baseline):
        if self._paned is None:
            # Nothing but the open button until a repository is chosen.
            return Gtk.ApplicationWindow.do_size_allocate(self, width, height, baseline)
        # Keep both sidebars at a sixth of the window width, the middle
        # getting the rest, minus the two one pixel paned handles.
        sidebar = round(width / 6)
        self._paned.set_position(sidebar)
        Gtk.ApplicationWindow.do_size_allocate(self, width, height, baseline)
        # The right paned shifts its own position by the change in its
        # width, so it can only be set once it has been allocated the
        # width that follows from the left paned position set above.
        self._right_paned.set_position(width - 2 * sidebar - 2)

    def load_css(self):
        css = (slop.DATA_DIR / "sloppie.css").read_text("utf-8")
        provider = Gtk.CssProvider()
        provider.load_from_string(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _on_change_selected(self, sidebar, change, by_user):
        # The sidebar and the diff view belong together, so picking a
        # file should show its diff, even if the terminal was shown.
        # A reload reselecting a file should not steal the terminal.
        if by_user and change is not None:
            self._show_diff_view()
        # Allow only the operations that apply to the file selected.
        # Staged changes are reverted by unstaging them first.
        section = change.section if change is not None else None
        self.lookup_action("stage").set_enabled(section in ("unstaged", "untracked"))
        self.lookup_action("unstage").set_enabled(section == "staged")
        self.lookup_action("revert").set_enabled(section == "unstaged")
        self.lookup_action("trash").set_enabled(section == "untracked")
        self.lookup_action("edit").set_enabled(section is not None)
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
        except RuntimeError as error:
            print(f"sloppie: {error}", file=sys.stderr)
            return self._diff_view.set_diff([])
        self._diff_view.set_diff(parse_diff(text), keep_position=same)

    def _apply(self, operation, change):
        """Run `operation` on `change`, reload and return ``True`` if done."""
        success = True
        try:
            operation(change)
        except (GLib.Error, RuntimeError) as error:
            print(f"sloppie: {error}", file=sys.stderr)
            success = False
        self.refresh()
        return success

    def _confirm(self, message, detail, label):
        """Return ``True`` if the user chooses `label`."""
        dialog = Gtk.AlertDialog(modal=True,
                                 message=message,
                                 detail=detail,
                                 buttons=["Cancel", label],
                                 cancel_button=0,
                                 default_button=0)

        # AlertDialog only has an asynchronous API, so run a nested main
        # loop to be able to return the response to the caller. Having
        # cancel_button set, dismissing gives us that instead of an error.
        loop = GLib.MainLoop()
        response = 0
        def on_done(dialog, result):
            nonlocal response
            response = dialog.choose_finish(result)
            loop.quit()
        dialog.choose(self, None, on_done)
        loop.run()
        return response == 1

    def _on_stage_activate(self, *args):
        self._apply(self.repository.stage,
                    self._file_sidebar.get_selected_change())

    def _on_unstage_activate(self, *args):
        self._apply(self.repository.unstage,
                    self._file_sidebar.get_selected_change())

    def _on_revert_activate(self, *args):
        change = self._file_sidebar.get_selected_change()
        if self._confirm(f"Revert changes in {change.name}?",
                         "The changes will be permanently lost.",
                         "Revert"):
            if self._apply(self.repository.revert, change):
                self._toast.flash(f"Reverted file {change.name}")

    def _on_trash_activate(self, *args):
        change = self._file_sidebar.get_selected_change()
        if self._confirm(f"Move {change.name} to the trash?",
                         "The file can be restored from the trash.",
                         "Trash"):
            if self._apply(self.repository.trash, change):
                self._toast.flash(f"Trashed file {change.name}")

    def _on_edit_activate(self, *args):
        change = self._file_sidebar.get_selected_change()
        command = ["emacs", str(self.repository.root / change.path)]
        if position := self._diff_view.get_position():
            # Emacs takes the position to visit as '+LINE:COLUMN'
            # preceding the file that it applies to.
            command.insert(1, "+{:d}:{:d}".format(*position))
        try:
            # Give emacs a session of its own, so that it neither dies
            # along with sloppie nor takes signals meant for sloppie.
            subprocess.Popen(command, start_new_session=True)
        except OSError as error:
            print(f"sloppie: {error}", file=sys.stderr)

    def _on_commit_activate(self, *args):
        dialog = slop.CommitDialog(self, self.repository)
        dialog.connect("committed", self._on_committed)
        dialog.present()

    def _on_add_comment_activate(self, *args):
        dialog = slop.CommentDialog(self)
        # The comment lands in the sidebar in plain sight, so it needs
        # no toast to say that it was added.
        dialog.connect("added", lambda dialog, text:
                       self._comment_sidebar.add_comment(text))
        dialog.present()

    def _on_run_activate(self, *args):
        if command := self.config.read_item("run-command"):
            return self._run(command)
        # Nothing to run yet, so ask what to run and then run that.
        dialog = slop.RunDialog(self, self.config)
        dialog.connect("saved", lambda dialog, command: self._run(command))
        dialog.present()

    def _on_configure_run_activate(self, *args):
        slop.RunDialog(self, self.config).present()

    def _run(self, command):
        try:
            # Run via the shell, so that the command can be anything
            # that would work in a terminal, and give it a session of
            # its own, so that it neither dies along with sloppie nor
            # takes signals meant for sloppie.
            subprocess.Popen(["sh", "-c", command],
                             cwd=str(self.repository.root),
                             start_new_session=True)
        except OSError as error:
            return print(f"sloppie: {error}", file=sys.stderr)
        # The command runs out of sight, so say that it was started.
        self._toast.flash(f"Running '{command}'")

    def _on_committed(self, dialog):
        self._toast.flash("Committed changes")
        self.refresh()

    def _on_focus_activate(self, action, target):
        target = target.get_string()
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
            shown = self._stack.get_visible_child_name()
            target = (names[(names.index(shown) + 1) % len(names)]
                      if shown in names else names[0])
        # Set the visible child even if unchanged, in which case no
        # notification follows and focus needs to be moved here.
        self._stack.set_visible_child_name(target)
        self._focus_stack_view()

    def _show_diff_view(self):
        # Focus belongs to the sidebar here, so block the handler that
        # would move it along to the view shown.
        with GObject.signal_handler_block(self._stack, self._stack_handler):
            self._stack.set_visible_child_name("diff")

    def _focus_stack_view(self):
        # Focus the view itself, not the scroller around it.
        self._stack.get_visible_child().get_child().grab_focus()

    def _on_wrap_lines_change_state(self, action, state):
        action.set_state(state)
        wrap = state.get_boolean()
        self._diff_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR
                                      if wrap else
                                      Gtk.WrapMode.NONE)
        self.config.write_item("wrap-lines", wrap)

    def _on_about_activate(self, *args):
        slop.AboutDialog(self).present()

    def _on_poll_timeout(self):
        try:
            fingerprint = self.repository.get_fingerprint()
        except RuntimeError as error:
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
        except RuntimeError as error:
            print(f"sloppie: {error}", file=sys.stderr)
            return
        self._branch_label.set_text(branch)
        # Comments are written against a branch, so switching branch
        # puts the ones shown aside and brings back any of the new one.
        self._comment_sidebar.set_branch(branch)
        self._file_sidebar.set_changes(changes)
