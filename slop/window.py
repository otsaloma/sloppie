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
        self._title_label = None
        self._init_properties()
        self.load_css()
        self._init_actions()
        self._init_focus_shortcuts()
        self._init_tab_shortcuts()
        self._init_header()
        self._init_widgets()
        # Launched from a launcher rather than a terminal, with no
        # directory to fall back on, the dashboard is where to start,
        # being the one place to open a repository from.
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
        # No switcher for this one: the dashboard is how the user moves
        # between the tasks, and the only way back to it is the button
        # in the header bar.
        self._stack = Gtk.Stack()
        self._stack.add_named(self._dashboard, "dashboard")
        self.set_child(self._stack)
        self._update_dashboard()
        # A window gone takes its tasks with it, which have to be told,
        # a task outliving the widget tree it was part of.
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
            # Leave the dashboard be, the user can try another directory.
            return slop.util.show_error(self, f"Failed to open {path}", error)
        for task in self._tasks:
            # Already open, and a repository is only ever open once, any
            # path inside it having led to the same root.
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
            return slop.util.show_error(self, f"Failed to open {path}", error)
        directory = subtask.get_directory(repository.root, branch)

        def on_forked(directory, error):
            self._dashboard.remove_pending(directory)
            if error is not None:
                return slop.util.show_error(
                    self, f"Failed to fork {branch}", error)
            recent.add_repository(directory, parent=repository.root)
            # The git half of the forking is the terminal's to run, so
            # that it can be watched and answered, and the task lands on
            # that terminal, which is where the user was headed anyway.
            self.open_task(str(directory), subtask.get_setup_command(branch))

        # A copy takes long enough to need saying that it is happening,
        # a repository of any size being gigabytes of virtualenv and
        # node_modules before anything that git knows about.
        self._dashboard.add_pending(directory, repository.root, branch)
        subtask.fork(repository, branch, on_forked)

    def close_task(self, path):
        """Close the task for the repository at `path`."""
        for task in list(self._tasks):
            if str(task.repository.root) != path: continue
            shown = task is self._page
            self._tasks.remove(task)
            if self._last_task is task:
                self._last_task = None
            # Out of the window first, so that the shells hung up below
            # are not taken for a shell that exited on its own and
            # started afresh, which only happens while there is a window.
            self._stack.remove(task)
            task.close()
            self._update_dashboard()
            # Closing the task on screen leaves nothing to look at, and
            # the stack would fall back on a page of its own choosing.
            if shown:
                self._show_dashboard()
            return

    def _update_dashboard(self):
        # Latest opened first, that being the one most likely worked on
        # and the one the user would look for at the top of the list.
        self._dashboard.set_tasks(list(reversed(self._tasks)))

    def _show_task(self, task):
        self._stack.set_visible_child(task)
        # Turning to a task is seeing whatever rang in the view it shows.
        task.seen()
        task.focus_shown_view()
        self._sync_header()

    def _show_dashboard(self):
        # Remember which task to zoom back in to.
        if self._page is not None:
            self._last_task = self._page
        self._stack.set_visible_child(self._dashboard)
        self._dashboard.focus()
        self._sync_header()

    def _on_close_task_activate(self, *args):
        """Close the task shown, asking first if something runs in it."""
        page = self._page
        if not page.is_running() or slop.util.confirm(
                self,
                f"Close {page.repository.root.name}?",
                "Whatever is running in its terminals will be stopped.",
                "Close"):
            self.close_task(str(page.repository.root))

    def _on_close_request(self, window):
        """Ask before quitting with tasks open, and stop if told to."""
        # Reached from Ctrl+Q, from the header bar's close button and
        # from the window manager, which all mean the same thing here,
        # the application having the one window.
        if not self._tasks: return False
        count = len(self._tasks)
        return not slop.util.confirm(
            self, "Quit Sloppie?",
            f"{count} task is open and will be closed." if count == 1 else
            f"{count} tasks are open and will be closed.",
            "Quit")

    def _on_task_changed(self, task):
        # The header bar only ever shows the task on screen, but the
        # dashboard shows them all, and so needs every one of these.
        self._dashboard.update()
        self._sync_attention()
        if task is self._page:
            self._sync_header()

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
        # Closing one task, which is what there is to close, the window
        # holding all of them. Disabled on the dashboard, where there is
        # no task shown to be the one meant.
        action = Gio.SimpleAction(name="close-task", enabled=False)
        action.connect("activate", self._on_close_task_activate)
        self.add_action(action)
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control>w"),
            action=Gtk.NamedAction.new("win.close-task")))
        # Quitting, the application having the one window. Closing that
        # window is the same thing and asks the same question, so leave
        # both to it rather than have an action of our own.
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control>q"),
            action=Gtk.NamedAction.new("window.close")))
        # This is the toggle in the header bar menu, whose state follows
        # the task shown, being read from its repository's config.
        action = Gio.SimpleAction.new_stateful(
            "wrap-lines", None, GLib.Variant.new_boolean(True))
        action.set_enabled(False)
        action.connect("change-state", self._on_wrap_lines_change_state)
        self.add_action(action)
        # Zooming out to the dashboard and back in to the task last
        # looked at. A stateful action without a parameter toggles on
        # activation, which gives the button and F4 the same behaviour.
        action = Gio.SimpleAction.new_stateful(
            "dashboard", None, GLib.Variant.new_boolean(True))
        action.connect("change-state", self._on_dashboard_change_state)
        self.add_action(action)
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("F4"),
            action=Gtk.NamedAction.new("win.dashboard")))
        self.add_controller(shortcuts)
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
        # Zooming out to the dashboard, far left, where it stays on the
        # dashboard too, that being what zooms back in. The dot is the
        # one the stack switcher puts on a tab that rang, here for the
        # terminals of every task, whose tabs are out of sight.
        self._attention_dot = Gtk.Box(halign=Gtk.Align.END,
                                      valign=Gtk.Align.START,
                                      visible=False)

        self._attention_dot.add_css_class("slop-attention-dot")
        overlay = Gtk.Overlay(child=Gtk.Image(icon_name="view-grid-symbolic"))
        overlay.add_overlay(self._attention_dot)
        header.pack_start(Gtk.ToggleButton(action_name="win.dashboard",
                                           child=overlay,
                                           tooltip_text="Dashboard (F4)"))

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
        self._task_widgets.append(box)
        # The switcher takes the title's place while a task is shown,
        # the dashboard leaving it empty for the header bar to fall back
        # on the window title, which it centers.
        self._header = header
        self._switcher = Gtk.StackSwitcher()
        header.set_title_widget(self._switcher)
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
        page = self._page
        # Without a task there is nothing to commit, run or comment on,
        # and no stack for the switcher to switch, so leave the header
        # bar with nothing but the dashboard button, the title and the
        # menu.
        for widget in self._task_widgets:
            widget.set_visible(page is not None)
        # Empty on the dashboard, which leaves the header bar to center
        # the window title in the switcher's place.
        self._header.set_title_widget(self._switcher if page else None)
        self.lookup_action("dashboard").set_state(
            GLib.Variant.new_boolean(page is None))
        for name in ("add-comment", "close-task", "commit", "configure",
                     "configure-run", "delete-sent-comments", "edit", "focus",
                     "run", "send-comments", "switch-tab", "wrap-lines"):
            self.lookup_action(name).set_enabled(page is not None)
        # Allow only the file operations that apply to the file
        # selected. Staged changes are reverted by unstaging them first.
        section = page.get_selected_section() if page else None
        self.lookup_action("stage").set_enabled(section in ("unstaged", "untracked"))
        self.lookup_action("unstage").set_enabled(section == "staged")
        self.lookup_action("revert").set_enabled(section == "unstaged")
        self.lookup_action("trash").set_enabled(section == "untracked")
        self._sync_attention()
        if page is None: return
        self._title_label.set_label(page.repository.root.name)
        self._branch_label.set_label(page.branch or "")
        # The switcher is the window's, the stack the task's, so point
        # the one at the other for as long as this task is shown.
        self._switcher.set_stack(page.stack)
        # The switcher builds a button per page in the order of the
        # stack, but hands out no reference to them, so walk its
        # children instead: [ Diff | Terminal | 2 | 3 ].
        for button in list(self._switcher)[2:]:
            button.add_css_class("slop-narrow-tab")
        # The wrap toggle is per task, so take the state from the task
        # shown. Set it without going through the handler, which would
        # write the config right back.
        self.lookup_action("wrap-lines").set_state(
            GLib.Variant.new_boolean(page.wrap_lines))

    def _sync_attention(self):
        # A terminal that rang is marked on its tab, but only the tabs
        # of the task shown are in sight, so mark the way to the rest:
        # the dashboard, where the card says which task it was.
        self._attention_dot.set_visible(
            any(x.get_attention() for x in self._tasks))

    def _on_dashboard_change_state(self, action, state):
        if state.get_boolean():
            return self._show_dashboard()
        if not self._tasks:
            # Nothing to zoom in to, so stay where we are.
            return
        # Back to the task last shown, or to the latest opened if that
        # one has since been closed.
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

    def _on_about_activate(self, *args):
        slop.AboutDialog(self).present()
