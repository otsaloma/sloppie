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
from slop.git import parse_diff
from slop.git import SECTIONS

class Window(Gtk.ApplicationWindow):

    def __init__(self, repository):
        GObject.GObject.__init__(self)
        self.repository = repository
        self._comment_sidebar = slop.CommentSidebar()
        self._diff_view = slop.DiffView()
        self._file_sidebar = slop.FileSidebar()
        self._terminal = slop.Terminal(repository.root)
        self._toast = slop.Toast()
        self._fingerprint = None
        self._shown_change = None
        self._init_properties()
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
        shortcuts = Gtk.ShortcutController(scope=Gtk.ShortcutScope.GLOBAL)
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
        # Closing the only window quits the application, so both of the
        # customary accelerators can just close the window.
        for accelerator in ("<Control>w", "<Control>q"):
            shortcuts.add_shortcut(Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string(accelerator),
                action=Gtk.NamedAction.new("window.close")))
        self.add_controller(shortcuts)
        # This is the toggle in the header bar menu, which starts out
        # in whatever state the diff view was created in.
        wrap = self._diff_view.get_wrap_mode() != Gtk.WrapMode.NONE
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
        switcher = Gtk.StackSwitcher()
        header.set_title_widget(switcher)
        menu = Gio.Menu()
        menu.append("Wrap Lines", "win.wrap-lines")
        section = Gio.Menu()
        section.append("About Sloppie", "win.about")
        menu.append_section(None, section)
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic",
                                       menu_model=menu,
                                       primary=True))
        self.set_titlebar(header)
        diff_scroller = Gtk.ScrolledWindow()
        diff_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        diff_scroller.set_child(self._diff_view)
        terminal_scroller = Gtk.ScrolledWindow()
        terminal_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        terminal_scroller.set_child(self._terminal)
        self._stack = Gtk.Stack()
        # The mnemonics only show the underline when Alt is held, the
        # focus shortcuts of the window do the actual moving of focus.
        for child, name, title in ((diff_scroller, "diff", "_Diff"),
                                   (terminal_scroller, "terminal", "_Terminal")):
            page = self._stack.add_titled(child, name, title)
            page.set_use_underline(True)
        switcher.set_stack(self._stack)
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
        self._comment_sidebar.set_change(change)
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
        path = self.repository.root / change.path
        try:
            # Give emacs a session of its own, so that it neither dies
            # along with sloppie nor takes signals meant for sloppie.
            subprocess.Popen(["emacs", str(path)], start_new_session=True)
        except OSError as error:
            print(f"sloppie: {error}", file=sys.stderr)

    def _on_focus_activate(self, action, target):
        target = target.get_string()
        if target in SECTIONS:
            # Show the diff of the file focused, also when it was the
            # one selected already and no selection change follows.
            if self._file_sidebar.focus_section(target):
                self._show_diff_view()
            return
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
        widget = (self._diff_view
                  if self._stack.get_visible_child_name() == "diff" else
                  self._terminal)
        widget.grab_focus()

    def _on_wrap_lines_change_state(self, action, state):
        action.set_state(state)
        self._diff_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR
                                      if state.get_boolean() else
                                      Gtk.WrapMode.NONE)

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
        except RuntimeError as error:
            print(f"sloppie: {error}", file=sys.stderr)
            return
        self._file_sidebar.set_changes(changes)
