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

from slop import recent
from slop import subtask
from slop import util
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango

class Window(Gtk.ApplicationWindow):

    """The shell around the tasks: a header bar and the task shown."""

    def __init__(self, repository=None):
        GObject.GObject.__init__(self)
        self._attention_dot = None
        self._branch_label = None
        self._dashboard = None
        self._header = None
        self._last_task = None
        self._stack = None
        self._switcher = None
        self._task_widgets = []
        self._tasks = []
        self._title_box = None
        self._title_label = None
        self._trashing = set()
        self._init_properties()
        self.load_css()
        self._init_actions()
        self._init_focus_shortcuts()
        self._init_tab_shortcuts()
        self._init_header()
        self._init_widgets()
        if repository is not None:
            self._open_task(repository)
        self._sync_header()

    def _init_widgets(self):
        self._dashboard = slop.Dashboard()
        self._dashboard.connect("open-task", lambda dashboard, path:
                                self.open_task(path))
        self._dashboard.connect("close-task", lambda dashboard, path:
                                self.close_task(path))
        self._dashboard.connect("add-subtask", lambda dashboard, path, branch:
                                self.add_subtask(path, branch))
        self._dashboard.connect("trash-task", lambda dashboard, path:
                                self._on_trash_task(path))
        self._stack = Gtk.Stack()
        self._stack.add_named(self._dashboard, "dashboard")
        self.set_child(self._stack)
        self._update_dashboard()
        self.connect("close-request", self._on_close_request)
        self.connect("destroy", self._on_destroy)

    def _on_destroy(self, window):
        for task in self._tasks:
            task.close()

    @property
    def _page(self):
        """Return the task shown, or ``None`` on the dashboard."""
        child = self._stack.get_visible_child()
        return child if isinstance(child, slop.TaskPage) else None

    def open_task(self, path, setup=None):
        """Show the task for the repository at `path`, opening it if needed."""
        try:
            repository = slop.Repository(path)
        except Exception as error:
            return util.show_error(self, f"Failed to open {path}", error)
        if repository.root in self._trashing: return
        for task in self._tasks:
            if task.repository.root == repository.root:
                return self._show_task(task)
        self._open_task(repository, setup)

    def _open_task(self, repository, setup=None):
        task = slop.TaskPage(repository, setup)
        task.connect("changed", self._on_task_changed)
        self._tasks.append(task)
        self._stack.add_named(task, str(repository.root))
        self._update_dashboard()
        self._show_task(task)

    def add_subtask(self, path, branch):
        """Fork the repository at `path` into a subtask for `branch`."""
        try:
            repository = slop.Repository(path)
        except Exception as error:
            return util.show_error(self, f"Failed to open {path}", error)
        directory = subtask.get_directory(repository.root, branch)

        def on_forked(directory, error):
            self._dashboard.remove_pending(directory)
            if error is not None:
                return util.show_error(
                    self, f"Failed to fork {branch}", error)
            recent.add_repository(directory, parent=repository.root)
            setup = subtask.get_setup_command(
                branch, slop.Config(repository).read_item("setup-command"))
            self.open_task(directory, setup)

        self._dashboard.add_pending(directory, repository.root, branch)
        subtask.fork(repository, branch, on_forked)

    def _on_trash_task(self, path):
        """Ask before moving the subtask at `path` to the trash."""
        if util.confirm(self, f"Move {path.name} to the trash?",
                        "The subtask and the work on its branch can only "
                        "be had back from the trash. Anything deleted by the "
                        "teardown command cannot be restored.",
                        "Trash", destructive=True):
            self.trash_task(path)

    def trash_task(self, path):
        """Move the subtask at `path` to the trash, closing it first."""
        if path in self._trashing: return
        try:
            command = slop.Config(slop.Repository(path)).read_item("teardown-command")
        except Exception as error:
            return util.show_error(
                self, f"Failed to trash {path.name}", error)

        def on_trashed(path, error):
            self._trashing.remove(path)
            if error is None:
                recent.remove_repository(path)
            self._update_dashboard()
            if error is not None:
                util.show_error(self, f"Failed to trash {path.name}", error)

        self._trashing.add(path)
        self.close_task(path)
        self._update_dashboard()
        subtask.trash(path, command, on_trashed)

    def close_task(self, path):
        """Close the task for the repository at `path`."""
        for task in list(self._tasks):
            if task.repository.root != path: continue
            shown = task is self._page
            self._tasks.remove(task)
            if self._last_task is task:
                self._last_task = None
            # Out of the window first, or the terminals would start new
            # shells in place of the ones hung up below.
            self._stack.remove(task)
            task.close()
            self._update_dashboard()
            # Else the stack would show a page of its own choosing.
            if shown:
                self._show_dashboard()
            return

    def _update_dashboard(self):
        self._dashboard.set_tasks(self._tasks, self._trashing)

    def _show_task(self, task):
        self._stack.set_visible_child(task)
        task.seen()
        task.focus_shown_view()
        self._sync_header()

    def _show_dashboard(self):
        if self._page is not None:
            self._last_task = self._page
        self._stack.set_visible_child(self._dashboard)
        self._dashboard.focus()
        self._sync_header()

    def _on_close_task_activate(self, *args):
        """Close the task shown, asking first if something runs in it."""
        page = self._page
        if not page.is_running() or util.confirm(
                self,
                f"Close {page.repository.root.name}?",
                "Whatever is running in its terminals will be stopped.",
                "Close", destructive=True):
            self.close_task(page.repository.root)

    def _on_close_request(self, window):
        """Ask before quitting with tasks open, and stop if told to."""
        if not self._tasks: return False
        count = len(self._tasks)
        return not util.confirm(
            self, "Quit Sloppie?",
            f"{count} task is open and will be closed." if count == 1 else
            f"{count} tasks are open and will be closed.",
            "Quit", destructive=True)

    def _on_task_changed(self, task):
        self._dashboard.update()
        self._sync_attention()
        if task is self._page:
            self._sync_header()

    def _init_actions(self):
        # The actions of the task shown, each performed by the method of
        # the same name. Capture phase to beat the terminal.
        shortcuts = Gtk.ShortcutController(
            propagation_phase=Gtk.PropagationPhase.CAPTURE)
        for name, accelerator in (
                ("stage", "<Control>s"),
                ("unstage", "<Control>u"),
                ("revert", None),
                ("trash", None),
                ("edit", "<Control>e"),
                ("commit", "<Control>Return"),
                ("add-comment", "<Control>m"),
                ("send-comments", None),
                ("delete-sent-comments", None),
                ("run", "F5"),
                ("configure-run", "<Shift>F5"),
                ("resume-agent", "<Shift><Control>r"),
                ("configure", None)):
            action = Gio.SimpleAction(name=name, enabled=False)
            action.connect("activate", self._on_task_action, name.replace("-", "_"))
            self.add_action(action)
            if accelerator is None: continue
            shortcuts.add_shortcut(Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string(accelerator),
                action=Gtk.NamedAction.new(f"win.{name}")))
        action = Gio.SimpleAction(name="close-task", enabled=False)
        action.connect("activate", self._on_close_task_activate)
        self.add_action(action)
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control>w"),
            action=Gtk.NamedAction.new("win.close-task")))
        # Quitting is closing the one window, which asks first.
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control>q"),
            action=Gtk.NamedAction.new("window.close")))
        action = Gio.SimpleAction.new_stateful(
            "wrap-lines", None, GLib.Variant.new_boolean(True))
        action.set_enabled(False)
        action.connect("change-state", self._on_wrap_lines_change_state)
        self.add_action(action)
        # A stateful action without a parameter toggles on activation.
        action = Gio.SimpleAction.new_stateful(
            "dashboard", None, GLib.Variant.new_boolean(True))
        action.connect("change-state", self._on_dashboard_change_state)
        self.add_action(action)
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("F4"),
            action=Gtk.NamedAction.new("win.dashboard")))
        self.add_controller(shortcuts)
        action = Gio.SimpleAction(name="shortcuts")
        action.connect("activate", self._on_shortcuts_activate)
        self.add_action(action)
        action = Gio.SimpleAction(name="about")
        action.connect("activate", self._on_about_activate)
        self.add_action(action)

    def _on_task_action(self, action, target, method):
        getattr(self._page, method)()

    def _init_focus_shortcuts(self):
        # Matching the mnemonics of the sidebar and the stack switcher.
        # Capture phase to beat both those mnemonics and the terminal.
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
        # The dot the stack switcher puts on a tab that rang, here for
        # the tabs of all tasks.
        self._attention_dot = Gtk.Box(halign=Gtk.Align.END,
                                      valign=Gtk.Align.START,
                                      visible=False)

        self._attention_dot.add_css_class("slop-attention-dot")
        overlay = Gtk.Overlay(child=Gtk.Image(icon_name="view-grid-symbolic"))
        overlay.add_overlay(self._attention_dot)
        # Not a toggle, which would look stuck pressed on the dashboard.
        button = Gtk.Button(action_name="win.dashboard",
                            child=overlay,
                            tooltip_text="Dashboard (F4)")
        # Header bar buttons are flat only if they have the "image-button"
        # class, which GTK adds by itself for an icon or an image child,
        # but not for the overlay we need for the dot.
        button.add_css_class("image-button")
        header.pack_start(button)

        commit = Gtk.Button(action_name="win.commit",
                            icon_name="object-select-symbolic",
                            tooltip_text="Commit (Ctrl+Enter)")
        header.pack_start(commit)
        self._task_widgets.append(commit)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("slop-header-title")
        box.set_valign(Gtk.Align.CENTER)
        box.set_hexpand(True)
        self._title_label = Gtk.Label(xalign=0)
        self._title_label.add_css_class("title")
        self._branch_label = Gtk.Label(xalign=0)
        for label in (self._title_label, self._branch_label):
            label.set_ellipsize(Pango.EllipsizeMode.END)
            # The header bar keeps the stack switcher centered only as
            # long as what's packed at the start fits left of center, so
            # ask for no width at all. Expanding above still gives these
            # all the space that is actually free.
            label.set_max_width_chars(1)
            box.append(label)
        header.pack_start(box)
        self._task_widgets.append(box)
        self._header = header
        self._switcher = Gtk.StackSwitcher()
        self._title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._title_box.append(self._switcher)
        self._title_box.append(Gtk.Button(
            action_name="win.resume-agent",
            icon_name="view-refresh-symbolic",
            tooltip_text="Resume Agent (Shift+Ctrl+R)"))
        header.set_title_widget(self._title_box)
        menu = Gio.Menu()
        menu.append("Wrap Lines", "win.wrap-lines")
        menu.append("Configure", "win.configure")
        menu.append("Keyboard Shortcuts", "win.shortcuts")
        menu.append("About Sloppie", "win.about")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic",
                                       menu_model=menu,
                                       primary=True))
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
        page = self._page
        for widget in self._task_widgets:
            widget.set_visible(page is not None)
        # None shows the window title in its place.
        self._header.set_title_widget(self._title_box if page else None)
        self.lookup_action("dashboard").set_state(
            GLib.Variant.new_boolean(page is None))
        for name in ("add-comment", "close-task", "commit", "configure",
                     "configure-run", "delete-sent-comments", "edit", "focus",
                     "resume-agent", "run", "send-comments", "switch-tab",
                     "wrap-lines"):
            self.lookup_action(name).set_enabled(page is not None)
        # Staged changes are reverted by unstaging them first.
        section = page.get_selected_section() if page else None
        self.lookup_action("stage").set_enabled(section in ("unstaged", "untracked"))
        self.lookup_action("unstage").set_enabled(section == "staged")
        self.lookup_action("revert").set_enabled(section == "unstaged")
        self.lookup_action("trash").set_enabled(section == "untracked")
        self._sync_attention()
        self.set_title(f"{page.repository.root.name} — Sloppie"
                       if page else "Sloppie")
        if page is None: return
        self._title_label.set_label(page.repository.root.name)
        self._branch_label.set_label(page.branch or "")
        self._switcher.set_stack(page.stack)
        # The switcher hands out no reference to its buttons, so walk
        # its children: [ Diff | Terminal | 2 | 3 ].
        for button in list(self._switcher)[2:]:
            button.add_css_class("slop-narrow-tab")
        # Not through the handler, which would write the config back.
        self.lookup_action("wrap-lines").set_state(
            GLib.Variant.new_boolean(page.wrap_lines))

    def _sync_attention(self):
        self._attention_dot.set_visible(
            any(x.get_attention() for x in self._tasks))

    def _on_dashboard_change_state(self, action, state):
        if state.get_boolean():
            return self._show_dashboard()
        if not self._tasks:
            # Nothing to zoom in to, so ask GitHub again, as turning to
            # the dashboard would.
            return self._dashboard.refresh_pull_requests()
        self._show_task(self._last_task if self._last_task in self._tasks
                        else self._tasks[-1])

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

    def _on_shortcuts_activate(self, *args):
        slop.ShortcutsWindow(self).present()

    def _on_about_activate(self, *args):
        slop.AboutDialog(self).present()
