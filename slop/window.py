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
from slop import recent
from slop.git import DiffLine
from slop.git import parse_diff
from slop.git import SECTIONS

class Window(Gtk.ApplicationWindow):

    def __init__(self, repository=None):
        GObject.GObject.__init__(self)
        self.repository = repository
        # All of these are set once we have a repository, until then the
        # window holds nothing but the open button.
        self.config = None
        self._branch = None
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
        self.load_css()
        if repository is None:
            # Launched from a launcher rather than a terminal, with no
            # directory to fall back on, so ask which repository to open
            # and build the rest of the window once we know.
            return self._init_open_view()
        self._init_repository()

    def _init_open_view(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_bottom(200)
        button = Gtk.Button(label="_Open Repository", use_underline=True)
        button.add_css_class("suggested-action")
        button.set_halign(Gtk.Align.CENTER)
        button.connect("clicked", self._on_open_clicked)
        box.append(button)
        paths = recent.list_repositories()
        if paths:
            box.append(self._init_recent_list(paths))
        self.set_child(box)

    def _init_recent_list(self, paths):
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                              show_separators=True)
        # 'rich-list' gives the tall rows and the spacing between the
        # widgets in them, the frame below the rounded border.
        listbox.add_css_class("rich-list")
        listbox.add_css_class("slop-recent-list")
        # The rows are built here in the order of the paths given, so
        # the row activated tells which of them to open.
        listbox.connect("row-activated", lambda listbox, row:
                        self._open_repository(paths[row.get_index()]))
        for path in paths:
            # The name of the repository, followed by the directory
            # that holds it, which together make up the full path.
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            row.append(Gtk.Label(label=path.name))
            label = Gtk.Label(label=str(path.parent), xalign=1)
            label.add_css_class("slop-recent-path")
            # Long paths give way rather than widen the whole window.
            label.set_ellipsize(Pango.EllipsizeMode.START)
            label.set_max_width_chars(1)
            label.set_hexpand(True)
            row.append(label)
            listbox.append(row)
        # Keep the list from growing past the window with many
        # repositories, but let a short list stay short.
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_height(True)
        scroller.set_child(listbox)
        frame = Gtk.Frame(child=scroller)
        # Clip the rows to the rounded corners of the frame, which they
        # would otherwise square off when hovered.
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        return frame

    def _on_open_clicked(self, button):
        dialog = Gtk.FileDialog(modal=True, title="Open Repository")
        dialog.select_folder(self, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            file = dialog.select_folder_finish(result)
        except Exception:
            # The user dismissed the dialog.
            return
        self._open_repository(file.get_path())

    def _open_repository(self, path):
        try:
            self.repository = slop.Repository(path)
        except Exception as error:
            # Leave the open view be, the user can try another directory.
            return slop.util.show_error(self, f"Failed to open {path}", error)
        # The open view goes away as the widgets built here take its
        # place as the child of the window.
        self._init_repository()

    def _init_repository(self):
        recent.add_repository(self.repository.root)
        self.config = slop.Config(self.repository)
        self._comment_sidebar = slop.CommentSidebar(self.repository)
        self._diff_view = slop.DiffView()
        self._file_sidebar = slop.FileSidebar()
        self._terminals = [slop.Terminal(self.repository.root) for i in range(3)]
        self._toast = slop.Toast()
        self._init_actions()
        self._init_widgets()
        self._init_focus_shortcuts()
        self._init_tab_shortcuts()
        self._init_signal_handlers()
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
                ("trash", None, self._on_trash_activate)):
            action = Gio.SimpleAction(name=name, enabled=False)
            action.connect("activate", callback)
            self.add_action(action)
            if accelerator is None: continue
            shortcuts.add_shortcut(Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string(accelerator),
                action=Gtk.NamedAction.new(f"win.{name}")))
        # Editing works without a file selected too, opening the whole
        # repository in dired, from where any file can be reached.
        action = Gio.SimpleAction(name="edit")
        action.connect("activate", self._on_edit_activate)
        self.add_action(action)
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control>e"),
            action=Gtk.NamedAction.new("win.edit")))
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
        # The two bulk operations on the comments, which do nothing when
        # there are no comments, or none of them sent, to operate on.
        action = Gio.SimpleAction(name="send-comments")
        action.connect("activate", self._on_send_comments_activate)
        self.add_action(action)
        action = Gio.SimpleAction(name="delete-sent-comments")
        action.connect("activate", self._on_delete_sent_comments_activate)
        self.add_action(action)
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
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Shift>F5"),
            action=Gtk.NamedAction.new("win.configure-run")))
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
        action = Gio.SimpleAction(name="configure")
        action.connect("activate", self._on_configure_activate)
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

    def _init_tab_shortcuts(self):
        # The customary accelerators to step through the tabs of the
        # stack, left and right: [ Diff | Terminal | 2 | 3 ], wrapping
        # around at either end. Capture phase again, so that the
        # terminal doesn't eat them.
        action = Gio.SimpleAction(name="switch-tab", parameter_type=GLib.VariantType("i"))
        action.connect("activate", self._on_switch_tab_activate)
        self.add_action(action)
        shortcuts = Gtk.ShortcutController(
            propagation_phase=Gtk.PropagationPhase.CAPTURE)
        for step, accelerator in ((-1, "<Control>Page_Up"),
                                  (+1, "<Control>Page_Down")):
            shortcuts.add_shortcut(Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string(accelerator),
                action=Gtk.NamedAction.new("win.switch-tab"),
                arguments=GLib.Variant("i", step)))
        self.add_controller(shortcuts)

    def _init_properties(self):
        geometry = Gdk.Display.get_default().get_monitors()[0].get_geometry()
        self.set_default_size(round(0.7 * geometry.width), round(0.85 * geometry.height))
        self.set_title("Sloppie")

    def _init_signal_handlers(self):
        self._file_sidebar.connect("change-selected", self._on_change_selected)
        for terminal in self._terminals:
            terminal.connect("file-clicked", self._on_file_clicked)
        # Clicking the stack switcher only switches the stack and leaves
        # focus on the switcher button, so focus the view shown here.
        self._stack_handler = self._stack.connect(
            "notify::visible-child", lambda *args: self._focus_stack_view())
        # Looking at a tab is seeing to whatever rang there.
        self._stack.connect("notify::visible-child", lambda *args:
                            self._stack.get_page(self._stack.get_visible_child())
                            .set_needs_attention(False))
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
        menu.append("Wrap Lines", "win.wrap-lines")
        menu.append("Configure", "win.configure")
        menu.append("About Sloppie", "win.about")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic",
                                       menu_model=menu,
                                       primary=True))
        # Packed after the menu, which puts it left of the menu, the
        # header bar filling its end from the right inwards. The three
        # comment buttons are joined into one group, they being the ones
        # that belong together and act on the comment sidebar.
        comments = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        comments.append(Gtk.Button(action_name="win.add-comment",
                                   icon_name="chat-message-new-symbolic",
                                   tooltip_text="Add Comment (Ctrl+M)"))
        comments.append(Gtk.Button(action_name="win.send-comments",
                                   icon_name="send-to-symbolic",
                                   tooltip_text="Send All Comments"))
        comments.append(Gtk.Button(action_name="win.delete-sent-comments",
                                   icon_name="user-trash-symbolic",
                                   tooltip_text="Delete Sent Comments"))
        header.pack_end(comments)
        header.pack_end(Gtk.Button(action_name="win.run",
                                   icon_name="media-playback-start-symbolic",
                                   tooltip_text="Run (F5) / Configure (Shift+F5)"))
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
            terminal.connect("bell", self._on_terminal_bell, page, i)
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
            slop.util.show_error(self, f"Failed to diff {change.name}", error)
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
            slop.util.show_error(self, message, error)
            success = False
        self.refresh()
        return success

    def _on_stage_activate(self, *args):
        change = self._file_sidebar.get_selected_change()
        self._apply(self.repository.stage, change,
                    f"Failed to stage {change.name}")

    def _on_unstage_activate(self, *args):
        change = self._file_sidebar.get_selected_change()
        self._apply(self.repository.unstage, change,
                    f"Failed to unstage {change.name}")

    def _on_revert_activate(self, *args):
        change = self._file_sidebar.get_selected_change()
        if slop.util.confirm(self, f"Revert changes in {change.name}?",
                             "The changes will be permanently lost.",
                             "Revert"):
            if self._apply(self.repository.revert, change,
                           f"Failed to revert {change.name}"):
                self._toast.flash(f"Reverted file {change.name}")

    def _on_trash_activate(self, *args):
        change = self._file_sidebar.get_selected_change()
        if slop.util.confirm(self, f"Move {change.name} to the trash?",
                             "The file can be restored from the trash.",
                             "Trash"):
            if self._apply(self.repository.trash, change,
                           f"Failed to trash {change.name}"):
                self._toast.flash(f"Trashed file {change.name}")

    def _on_edit_activate(self, *args):
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
            slop.util.show_error(self, "Failed to start emacs", error)

    def _on_commit_activate(self, *args):
        dialog = slop.CommitDialog(self, self.repository)
        dialog.connect("committed", self._on_committed)
        dialog.present()

    def _on_add_comment_activate(self, *args):
        # A selection in the terminal on screen means a comment on that
        # piece of the agent's output, which belongs to no file. The
        # terminal being what the user is reading, it wins over whatever
        # was left selected in the diff view.
        view = self._get_shown_view()
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

    def _on_send_comments_activate(self, *args):
        self._comment_sidebar.send_all_comments()

    def _on_delete_sent_comments_activate(self, *args):
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
        self._stack.set_visible_child_name("terminal-1")
        self._focus_stack_view()
        # Paste rather than feed the text, which is to say as bracketed
        # paste, where the agent takes it for text and not for keys
        # pressed, and where VTE strips the control characters that a
        # hunk could otherwise smuggle in.
        terminal.paste_text(text)
        return True

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
        except Exception as error:
            return slop.util.show_error(self, f"Failed to run {command}", error)
        # The command runs out of sight, so say that it was started.
        self._toast.flash(f"Running {command}")

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

    def _on_switch_tab_activate(self, action, step):
        names = ["diff"] + [f"terminal-{i+1}" for i in range(len(self._terminals))]
        index = names.index(self._stack.get_visible_child_name()) + step.get_int32()
        self._stack.set_visible_child_name(names[index % len(names)])
        self._focus_stack_view()

    def _on_terminal_bell(self, terminal, page, index):
        # A bell means that whatever runs in the terminal wants
        # attention: an agent done with its turn, a build finished. The
        # switcher marks the tab with a dot, but only as long as it's not
        # the tab on screen, so don't mark the one being looked at, which
        # would leave a mark to appear on switching away from it.
        if page.get_child() is not self._stack.get_visible_child():
            page.set_needs_attention(True)
        # Sitting at this very terminal, the user has seen it all
        # happen, so skip the notification rather than pop one up on top
        # of what it's about.
        if self.is_active() and self.get_focus() is terminal: return
        # The dot is no use when the window is behind others, so also
        # send a desktop notification. It carries our application id,
        # which is how GNOME shows it under Sloppie's name and icon and,
        # when clicked, raises a Sloppie window. Include the repository
        # in the id, so that a second bell replaces the notification of
        # the first, but another window's bells keep their own.
        notification = Gio.Notification.new(self.repository.root.name)
        notification.set_body("Agent wants something")
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
        self.get_application().send_notification(
            f"{self.repository.root}-terminal-{index}", notification)

    def _show_diff_view(self):
        # Focus belongs to the sidebar here, so block the handler that
        # would move it along to the view shown.
        with GObject.signal_handler_block(self._stack, self._stack_handler):
            self._stack.set_visible_child_name("diff")

    def _get_shown_view(self):
        """Return the view shown in the stack, the diff view or a terminal."""
        # Each page of the stack is a scroller wrapping the actual view.
        return self._stack.get_visible_child().get_child()

    def _focus_stack_view(self):
        # Focus the view itself, not the scroller around it.
        self._get_shown_view().grab_focus()

    def _on_wrap_lines_change_state(self, action, state):
        action.set_state(state)
        wrap = state.get_boolean()
        self._diff_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR
                                      if wrap else
                                      Gtk.WrapMode.NONE)
        self.config.write_item("wrap-lines", wrap)

    def _on_configure_activate(self, *args):
        # Give emacs an existing file to edit, so that it starts from
        # valid JSON rather than an empty buffer in a directory that it
        # would have to offer to create.
        if not self.config.path.exists():
            self.config.path.parent.mkdir(parents=True, exist_ok=True)
            self.config.path.write_text("{}\n", "utf-8")
        self._edit(str(self.config.path))

    def _on_about_activate(self, *args):
        slop.AboutDialog(self).present()

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
        self._branch = branch
        self._branch_label.set_text(branch)
        # Comments are written against a branch, so switching branch
        # puts the ones shown aside and brings back any of the new one.
        self._comment_sidebar.set_branch(branch)
        self._file_sidebar.set_changes(changes)
