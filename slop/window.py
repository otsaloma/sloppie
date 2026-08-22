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

from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from slop import recent

class Window(Gtk.ApplicationWindow):

    """The shell around the tasks: a header bar and the task shown."""

    def __init__(self, repository=None):
        GObject.GObject.__init__(self)
        self._branch_label = None
        self._page = None
        self._switcher = None
        self._task_widgets = []
        self._title_label = None
        self._init_properties()
        self.load_css()
        self._init_actions()
        self._init_focus_shortcuts()
        self._init_tab_shortcuts()
        self._init_header()
        if repository is None:
            # Launched from a launcher rather than a terminal, with no
            # directory to fall back on, so ask which repository to open
            # and build the rest of the window once we know.
            self._init_open_view()
        else:
            self._open_task(repository)
        self._sync_header()

    def _init_open_view(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_bottom(200)
        # Only found once the icon has been installed, but that's fine,
        # a missing icon just leaves an empty space above the button.
        image = Gtk.Image(icon_name="io.otsaloma.sloppie", pixel_size=128)
        box.append(image)
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
        for i, path in enumerate(paths, start=1):
            # The number and name of the repository, followed by the
            # directory that holds it, which together make up the full
            # path. The number is a label of its own, so that it can be
            # dimmed and be a mnemonic without the name interfering.
            # The spacing between these comes from the CSS, 'rich-list'
            # setting a border-spacing that beats the box's own spacing.
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            mnemonic = i <= 9
            number = Gtk.Label(label=f"_{i}." if mnemonic else f"{i}.",
                               use_underline=mnemonic)
            number.add_css_class("dim-label")
            box.append(number)
            box.append(Gtk.Label(label=path.name))
            path_label = Gtk.Label(label=str(path.parent), xalign=1)
            path_label.add_css_class("slop-recent-path")
            # Long paths give way rather than widen the whole window.
            path_label.set_ellipsize(Pango.EllipsizeMode.START)
            path_label.set_max_width_chars(1)
            path_label.set_hexpand(True)
            box.append(path_label)
            row = Gtk.ListBoxRow(child=box)
            if mnemonic:
                # Alt+N activates the row, as though clicked.
                number.set_mnemonic_widget(row)
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
            repository = slop.Repository(path)
        except Exception as error:
            # Leave the open view be, the user can try another directory.
            return slop.util.show_error(self, f"Failed to open {path}", error)
        # The open view goes away as the task takes its place as the
        # child of the window.
        self._open_task(repository)
        self._sync_header()

    def _open_task(self, repository):
        self._page = slop.TaskPage(repository)
        self._page.connect("changed", lambda page: self._sync_header())
        self.set_child(self._page)
        # The switcher is the window's, the stack the task's, so point
        # the one at the other for as long as this task is shown.
        self._switcher.set_stack(self._page.stack)
        # The switcher builds a button per page in the order of the
        # stack, but hands out no reference to them, so walk its
        # children instead: [ Diff | Terminal | 2 | 3 ].
        for button in list(self._switcher)[2:]:
            button.add_css_class("slop-narrow-tab")
        # The wrap toggle is per task, so take the state from the task
        # shown. Set it without going through the handler, which would
        # write the config right back.
        self.lookup_action("wrap-lines").set_state(
            GLib.Variant.new_boolean(self._page.wrap_lines))

    def _init_actions(self):
        # These are the actions of the file sidebar's context menu, which
        # shows the accelerators added to the shortcut controller below.
        # They start out disabled, being no-ops without a file selected.
        # The shortcuts run in the capture phase, so that they beat the
        # terminal, which would eat them and pass them on to the shell.
        shortcuts = Gtk.ShortcutController(
            propagation_phase=Gtk.PropagationPhase.CAPTURE)
        for name, accelerator, method in (
                ("stage", "<Control>s", "stage"),
                ("unstage", "<Control>u", "unstage"),
                ("revert", None, "revert"),
                ("trash", None, "trash")):
            action = Gio.SimpleAction(name=name, enabled=False)
            action.connect("activate", self._on_task_action, method)
            self.add_action(action)
            if accelerator is None: continue
            shortcuts.add_shortcut(Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string(accelerator),
                action=Gtk.NamedAction.new(f"win.{name}")))
        # Everything else the task can do is always possible while there
        # is a task: editing works without a file selected too, opening
        # the whole repository in dired; an amend can be committed even
        # without staged changes; a comment can be written at any time,
        # with no file selected too, being a comment on the changes as a
        # whole. Ctrl+Enter, Ctrl+M and F5 need the capture phase, the
        # terminal otherwise passing them on to the shell.
        for name, accelerator, method in (
                ("edit", "<Control>e", "edit"),
                ("commit", "<Control>Return", "commit"),
                ("add-comment", "<Control>m", "add_comment"),
                ("send-comments", None, "send_comments"),
                ("delete-sent-comments", None, "delete_sent_comments"),
                ("run", "F5", "run"),
                ("configure-run", "<Shift>F5", "configure_run"),
                ("configure", None, "configure")):
            action = Gio.SimpleAction(name=name, enabled=False)
            action.connect("activate", self._on_task_action, method)
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
        # This is the toggle in the header bar menu, whose state follows
        # the task shown, being read from its repository's config.
        action = Gio.SimpleAction.new_stateful(
            "wrap-lines", None, GLib.Variant.new_boolean(True))
        action.set_enabled(False)
        action.connect("change-state", self._on_wrap_lines_change_state)
        self.add_action(action)
        action = Gio.SimpleAction(name="about")
        action.connect("activate", self._on_about_activate)
        self.add_action(action)

    def _on_task_action(self, action, target, method):
        # Every action but the window's own is the shown task's to
        # perform, the window only holding them for the header bar and
        # the accelerators.
        getattr(self._page, method)()

    def _init_focus_shortcuts(self):
        # Alt accelerators that only move focus, matching the mnemonics
        # underlined in the sidebar section titles and the stack
        # switcher when Alt is held. They run in the capture phase, so
        # that they beat both those mnemonics, which would move focus
        # elsewhere, and the terminal, which would eat them.
        action = Gio.SimpleAction(name="focus",
                                  parameter_type=GLib.VariantType("s"),
                                  enabled=False)
        action.connect("activate", lambda action, target:
                       self._page.focus(target.get_string()))
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
        action = Gio.SimpleAction(name="switch-tab",
                                  parameter_type=GLib.VariantType("i"),
                                  enabled=False)
        action.connect("activate", lambda action, step:
                       self._page.switch_tab(step.get_int32()))
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

    def _init_header(self):
        header = Gtk.HeaderBar()
        # The icon theme has no commit icon, a save icon being the
        # closest thing.
        commit = Gtk.Button(action_name="win.commit",
                            icon_name="object-select-symbolic",
                            tooltip_text="Commit (Ctrl+Enter)")
        header.pack_start(commit)
        self._task_widgets.append(commit)
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
        self._title_label = Gtk.Label(xalign=0)
        self._title_label.add_css_class("title")
        self._branch_label = Gtk.Label(xalign=0)
        for label in (self._title_label, self._branch_label):
            label.set_ellipsize(Pango.EllipsizeMode.END)
            # The header bar keeps the stack switcher centered only as
            # long as what's packed at the start fits left of center, so
            # ask for no width at all. Expanding above still gives these
            # all the space that is actually free, ellipsizing the rest.
            label.set_max_width_chars(1)
            box.append(label)
        header.pack_start(box)
        self._switcher = Gtk.StackSwitcher()
        header.set_title_widget(self._switcher)
        self._task_widgets.append(self._switcher)
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
                                   tooltip_text="Send Unsent Comments"))
        comments.append(Gtk.Button(action_name="win.delete-sent-comments",
                                   icon_name="user-trash-symbolic",
                                   tooltip_text="Delete Sent Comments"))
        header.pack_end(comments)
        self._task_widgets.append(comments)
        run = Gtk.Button(action_name="win.run",
                         icon_name="media-playback-start-symbolic",
                         tooltip_text="Run (F5) / Configure (Shift+F5)")
        header.pack_end(run)
        self._task_widgets.append(run)
        self.set_titlebar(header)

    def _sync_header(self):
        """Update the header bar and the actions for the task shown."""
        # Without a task there is nothing to commit, run or comment on,
        # and no stack for the switcher to switch, so leave the header
        # bar with nothing but the title and the menu.
        for widget in self._task_widgets:
            widget.set_visible(self._page is not None)
        self._title_label.set_label(
            self._page.repository.root.name if self._page else "Sloppie")
        self._branch_label.set_label(
            self._page.branch or "" if self._page else "")
        self._branch_label.set_visible(self._page is not None)
        for name in ("add-comment", "commit", "configure", "configure-run",
                     "delete-sent-comments", "edit", "focus", "run",
                     "send-comments", "switch-tab", "wrap-lines"):
            self.lookup_action(name).set_enabled(self._page is not None)
        # Allow only the file operations that apply to the file
        # selected. Staged changes are reverted by unstaging them first.
        section = self._page.get_selected_section() if self._page else None
        self.lookup_action("stage").set_enabled(section in ("unstaged", "untracked"))
        self.lookup_action("unstage").set_enabled(section == "staged")
        self.lookup_action("revert").set_enabled(section == "unstaged")
        self.lookup_action("trash").set_enabled(section == "untracked")

    def load_css(self):
        css = (slop.DATA_DIR / "sloppie.css").read_text("utf-8")
        provider = Gtk.CssProvider()
        provider.load_from_string(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _on_wrap_lines_change_state(self, action, state):
        action.set_state(state)
        self._page.set_wrap_lines(state.get_boolean())

    def _on_about_activate(self, *args):
        slop.AboutDialog(self).present()
