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
import time

from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from pathlib import Path
from slop import github
from slop import recent
from slop import subtask

NOTHING = "···"

class TaskRow(Gtk.ListBoxRow):

    """One repository in the dashboard, open as a task or only recent."""

    def __init__(self, path, task, parent=None):
        GObject.GObject.__init__(self)
        self.path = path
        self.task = task
        # The repository forked from, set only for a subtask.
        self.parent = parent
        self._comments = None
        self._dismiss = None
        self._lines_added = None
        self._lines_removed = None
        self._nothing = None
        self._pull_request = None
        self._running = None
        self._title = None
        # Packed by TaskGroup beside the row, outside the frame.
        self.tag = Gtk.Box()
        if task is None:
            self.add_css_class("slop-task-recent")
        self._init_widgets()
        self.update()

    def _init_widgets(self):
        grid = Gtk.Grid(column_spacing=9, row_spacing=9)
        grid.set_margin_start(9)
        if self.task:
            # With one row only, the padding of the buttons suffices.
            grid.set_margin_bottom(9)
            grid.set_margin_top(9)
        self._title = Gtk.Label(label=self._get_title(), xalign=0)
        self._title.add_css_class("slop-task-name")
        grid.attach(self._title, 0, 0, 1, 1)
        directory = Gtk.Label(label=self._get_directory(), xalign=1, hexpand=True)
        directory.add_css_class("monospace")
        directory.add_css_class("slop-task-path")
        directory.set_ellipsize(Pango.EllipsizeMode.START)
        # Long paths give way rather than widen the whole window.
        directory.set_max_width_chars(1)
        grid.attach(directory, 1, 0, 1, 1)
        self._init_widgets_buttons(grid)
        if self.task:
            self._init_widgets_status(grid)
        self.set_child(grid)
        self._pull_request = Gtk.LinkButton(uri="",
                                            valign=Gtk.Align.CENTER,
                                            visible=False)

        self._pull_request.add_css_class("monospace")
        self._pull_request.add_css_class("slop-task-pull-request")
        self.tag.append(self._pull_request)

    def _init_widgets_buttons(self, grid):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                      halign=Gtk.Align.END,
                      valign=Gtk.Align.CENTER)

        box.add_css_class("slop-task-buttons")

        # Subtasks are not forked further, and only subtasks, the copies
        # that Sloppie made, are trashed.
        if self.parent is None:
            box.append(self._new_button("media-playlist-shuffle-symbolic",
                                        "Add Subtask",
                                        self._on_add_subtask_clicked))
        else:
            box.append(self._new_button("user-trash-symbolic",
                                        "Trash",
                                        self._on_trash_clicked))
        # Clearing a subtask would leave the copy on disk with nothing
        # pointing at it.
        if self.task is not None:
            self._dismiss = self._new_button("window-close-symbolic",
                                             "Close",
                                             self._on_close_clicked)
        elif self.parent is None:
            self._dismiss = self._new_button("view-conceal-symbolic",
                                             "Clear",
                                             self._on_clear_clicked)
        if self._dismiss is not None:
            box.append(self._dismiss)
        grid.attach(box, 2, 0, 1, 2 if self.task else 1)

    def _new_button(self, icon_name, tooltip_text, callback):
        button = Gtk.Button(icon_name=icon_name,
                            tooltip_text=tooltip_text,
                            valign=Gtk.Align.CENTER)

        button.add_css_class("flat")
        button.add_css_class("slop-task-button")
        button.connect("clicked", callback)
        return button

    def _init_widgets_status(self, grid):
        # Aligned to the start, so that the status box is around the
        # text and not the whole column.
        self._running = Gtk.Label(halign=Gtk.Align.START, xalign=0)
        self._running.add_css_class("monospace")
        grid.attach(self._running, 0, 1, 1, 1)
        pending = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                          spacing=6,
                          halign=Gtk.Align.END)

        self._lines_added = Gtk.Label(visible=False)
        self._lines_added.add_css_class("monospace")
        self._lines_added.add_css_class("slop-task-lines-added")
        pending.append(self._lines_added)
        self._lines_removed = Gtk.Label(visible=False)
        self._lines_removed.add_css_class("monospace")
        self._lines_removed.add_css_class("slop-task-lines-removed")
        pending.append(self._lines_removed)
        self._comments = Gtk.Label(visible=False)
        self._comments.add_css_class("monospace")
        self._comments.add_css_class("slop-task-comments")
        pending.append(self._comments)
        self._nothing = Gtk.Label(label=NOTHING, visible=False)
        self._nothing.add_css_class("monospace")
        self._nothing.add_css_class("slop-task-none")
        pending.append(self._nothing)
        grid.attach(pending, 1, 1, 1, 1)

    def _get_directory(self):
        """Return the directory holding the repository, home as a tilde."""
        directory = self.path.parent
        if not directory.is_relative_to(Path.home()):
            return str(directory)
        return str(Path("~") / directory.relative_to(Path.home()))

    def _get_title(self):
        """Return the name to show for the repository or subtask."""
        branch = self.task.branch if self.task else None
        # A subtask's directory name repeats its branch, so the branch
        # alone, for a subtask not open taken from the directory name.
        if self.parent is not None:
            prefix = f"{self.parent.name}."
            return branch or (self.path.name[len(prefix):]
                              if self.path.name.startswith(prefix) else
                              self.path.name)
        if branch is None: return self.path.name
        return f"{self.path.name}\u2009/\u2009{branch}"

    def update(self):
        """Update the card to match the state of the task."""
        if self.task is None: return
        self._title.set_label(self._get_title())
        running = " ".join(x for x in (self.task.command, self.task.elapsed) if x)
        self._running.set_label(running or NOTHING)
        status = f"slop-task-{self.task.status}" if running else "slop-task-none"
        for css in ("slop-task-none", "slop-task-waiting", "slop-task-working"):
            self._running.remove_css_class(css)
        self._running.add_css_class(status)
        # Hide rather than blank, as a blank still takes spacing, and the
        # comments have a box drawn around them.
        for label, value, text in ((self._comments, self.task.comments, "{}"),
                                   (self._lines_added, self.task.lines_added, "+{}"),
                                   (self._lines_removed, self.task.lines_removed, "−{}")):
            label.set_label(text.format(value))
            label.set_visible(bool(value))
        self._nothing.set_visible(not (self.task.comments or
                                       self.task.lines_added or
                                       self.task.lines_removed))

    def set_pull_request(self, index):
        """Show what became of this branch, per the pull requests `index`."""
        pull_request = self._find_pull_request(index)
        if pull_request is not None:
            self._pull_request.set_label(pull_request[0])
            self._pull_request.set_uri(pull_request[1])
        self._pull_request.set_visible(pull_request is not None)

    def _find_pull_request(self, index):
        # Without a task there is no branch, only a subtask's directory
        # name to match against.
        if self.task is not None:
            return index.get(self.task.branch)
        root = self.parent or self.path
        return next((y for x, y in index.items()
                     if subtask.get_directory(root, x).name == self.path.name), None)

    def _on_close_clicked(self, button):
        self.get_ancestor(Dashboard).emit("close-task", self.path)

    def _on_clear_clicked(self, button):
        self.get_ancestor(Dashboard).clear(self)

    def _on_add_subtask_clicked(self, button):
        popover = SubtaskPopover(self.path)
        popover.set_parent(button)
        # Or every click would leave another popover on the button.
        popover.connect("closed", lambda popover: popover.unparent())
        popover.connect("forked", self._on_subtask_forked)
        popover.popup()

    def _on_subtask_forked(self, popover, branch):
        self.get_ancestor(Dashboard).emit("add-subtask", self.path, branch)

    def _on_trash_clicked(self, button):
        self.get_ancestor(Dashboard).emit("trash-task", self.path)

class SubtaskPopover(Gtk.Popover):

    """Where the branch of a subtask to be forked is typed."""

    __gsignals__ = {
        "forked": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, path):
        GObject.GObject.__init__(self)
        self.path = path
        self._entry = None
        self._error = None
        self._init_widgets()
        # Focus can only be grabbed once shown.
        self.connect("map", lambda *args: self._entry.grab_focus())

    def _init_widgets(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        self._entry = Gtk.Entry(placeholder_text="branch-name", width_chars=48)
        self._entry.add_css_class("monospace")
        self._entry.connect("activate", self._on_activate)
        box.append(self._entry)
        self._error = Gtk.Label(xalign=0,
                                visible=False,
                                wrap=True,
                                max_width_chars=48)

        self._error.add_css_class("error")
        box.append(self._error)
        button = Gtk.Button(label="_Add Subtask", use_underline=True)
        button.add_css_class("suggested-action")
        button.connect("clicked", self._on_activate)
        box.append(button)
        self.set_child(box)

    def _on_activate(self, widget):
        branch = self._entry.get_text().strip()
        try:
            repository = slop.Repository(self.path)
        except Exception as error:
            return self._show_error(str(error))
        if (error := subtask.get_error(repository, branch)) is not None:
            return self._show_error(error)
        self.popdown()
        self.emit("forked", branch)

    def _show_error(self, message):
        self._error.set_label(message)
        self._error.set_visible(True)

class PendingRow(Gtk.ListBoxRow):

    """A subtask being copied, which is not yet a task to be opened."""

    def __init__(self, path, branch):
        GObject.GObject.__init__(self)
        self.path = path
        # Empty, but packed by TaskGroup beside every row.
        self.tag = Gtk.Box()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        box.set_margin_start(9)
        box.append(Gtk.Spinner(spinning=True, valign=Gtk.Align.CENTER))
        name = Gtk.Label(label=branch, xalign=0)
        name.add_css_class("slop-task-name")
        box.append(name)
        status = Gtk.Label(label="Copying...", xalign=1, hexpand=True)
        status.add_css_class("monospace")
        status.add_css_class("slop-task-path")
        box.append(status)
        self.set_child(box)

    def update(self):
        pass

    def set_pull_request(self, index):
        pass

class TaskGroup(Gtk.Box):

    """One repository and the subtasks forked from it, as rows of one frame."""

    def __init__(self, rows, tag_group, root):
        GObject.GObject.__init__(self,
                                 orientation=Gtk.Orientation.HORIZONTAL,
                                 spacing=9)

        self.root = root
        # As wide as the column of tags on the other side, so that the
        # frames stay centered in the window.
        blank = Gtk.Box()
        tag_group.add_widget(blank)
        self.append(blank)
        frame = Gtk.Frame(hexpand=True)
        frame.add_css_class("slop-task-card")
        self._listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                    show_separators=True)

        self._listbox.add_css_class("rich-list")
        self._listbox.connect("row-activated", self._on_row_activated)
        frame.set_child(self._listbox)
        # Or hovered rows would square off the rounded corners.
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        self.append(frame)
        # Each tag is kept the height of its row by a size group. No
        # spacing, as a separator is a border within the row above, not
        # a gap between rows.
        self._tags = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        tag_group.add_widget(self._tags)
        for row in rows:
            self._listbox.append(row)
            size_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.VERTICAL)
            size_group.add_widget(row)
            size_group.add_widget(row.tag)
            self._tags.append(row.tag)
        self.append(self._tags)

    def _on_row_activated(self, listbox, row):
        if not isinstance(row, TaskRow): return
        self.get_ancestor(Dashboard).emit("open-task", row.path)

    def get_rows(self):
        """Return the rows of the group, in the order shown."""
        return list(self._listbox)

    def remove(self, row):
        """Drop `row`, and return ``True`` if the group is left empty."""
        self._listbox.remove(row)
        self._tags.remove(row.tag)
        return self._listbox.get_first_child() is None

    def update(self):
        for row in self._listbox:
            row.update()

    def set_pull_requests(self, index):
        """Show what became of the branch of each row, per `index`."""
        for row in self._listbox:
            row.set_pull_request(index)

class Dashboard(Gtk.Box):

    """The page of cards: the tasks open and the repositories recently opened."""

    __gsignals__ = {
        "open-task": (GObject.SignalFlags.RUN_LAST, None, (object,)),
        "close-task": (GObject.SignalFlags.RUN_LAST, None, (object,)),
        "add-subtask": (GObject.SignalFlags.RUN_LAST, None, (object, str)),
        "trash-task": (GObject.SignalFlags.RUN_LAST, None, (object,)),
    }

    def __init__(self):
        GObject.GObject.__init__(self,
                                 orientation=Gtk.Orientation.VERTICAL,
                                 spacing=24)

        self._box = None
        self._open_button = None
        # Parent and branch of subtasks being copied, by the directory
        # copied to.
        self._pending = {}
        # By repository path, kept across rebuilds of the cards.
        self._pull_requests = {}
        self._pull_requests_asked = {}
        self._tasks = []
        self._trashing = set()
        self._init_widgets()
        self._init_shortcuts()
        # Asked on turning to the dashboard, not polled.
        self.connect("map", lambda *args: self.refresh_pull_requests())

    def _init_widgets(self):
        self.set_halign(Gtk.Align.CENTER)
        # Not centered vertically, or the cards would shift up and down
        # as tasks come and go.
        self.set_valign(Gtk.Align.START)
        self.set_margin_bottom(48)
        self.set_margin_top(36)
        self.append(Gtk.Image(icon_name="io.otsaloma.sloppie", pixel_size=128))
        self._open_button = Gtk.Button(label="_Open Repository", use_underline=True)
        self._open_button.add_css_class("suggested-action")
        self._open_button.set_halign(Gtk.Align.CENTER)
        self._open_button.connect("clicked", self._on_open_clicked)
        self.append(self._open_button)
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_height(True)
        scroller.set_child(self._box)
        self.append(scroller)

    def _init_shortcuts(self):
        # Not mnemonics, which would need a number printed by every name.
        # The managed scope hands these to the window, so that they work
        # wherever the focus is, but only while the dashboard is mapped.
        shortcuts = Gtk.ShortcutController(scope=Gtk.ShortcutScope.MANAGED)
        for i in range(1, 10):
            shortcuts.add_shortcut(Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string(f"<Alt>{i}"),
                action=Gtk.CallbackAction.new(
                    lambda widget, args, i=i: self.activate_row(i))))
        self.add_controller(shortcuts)

    def activate_row(self, number):
        """Activate the `number`th row, as though clicked."""
        rows = [row for group in self._box for row in group.get_rows()
                if isinstance(row, TaskRow)]

        if number > len(rows): return False
        return rows[number-1].activate()

    def _on_open_clicked(self, button):
        dialog = Gtk.FileDialog(modal=True, title="Open Repository")
        directory = Path.home() / "Source"
        if directory.is_dir():
            dialog.set_initial_folder(Gio.File.new_for_path(str(directory)))
        dialog.select_folder(self.get_root(), None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            file = dialog.select_folder_finish(result)
        except Exception:
            # The user dismissed the dialog.
            return
        self.emit("open-task", Path(file.get_path()))

    def set_tasks(self, tasks, trashing=()):
        """Rebuild the cards, disabling repositories being trashed."""
        self._tasks = list(tasks)
        self._trashing = set(trashing)
        self._rebuild()

    def add_pending(self, path, parent, branch):
        """Show a subtask for `branch` being copied to `path`."""
        self._pending[path] = (parent, branch)
        self._rebuild()

    def remove_pending(self, path):
        """Drop the subtask being copied to `path`, done or failed."""
        self._pending.pop(path, None)
        self._rebuild()

    def _rebuild(self):
        while group := self._box.get_first_child():
            self._box.remove(group)
        open_tasks = {x.repository.root: x for x in self._tasks}
        listed = recent.list_repositories()
        rank = {path: i for i, path in enumerate(listed)}
        paths = list(open_tasks) + [x for x in listed if x not in open_tasks]
        # Made anew, a size group holding on to every widget ever added.
        tag_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        # A subtask whose parent has since been forgotten stands on its
        # own rather than vanish along with it.
        parents = recent.list_parents()
        parents = {x: y for x, y in parents.items() if x in paths and y in paths}
        groups = {}
        for path in paths:
            groups.setdefault(parents.get(path, path), []).append(path)
        for path in sorted(groups, key=lambda x: self._sort_key(x, groups, open_tasks, rank)):
            members = sorted(groups[path],
                             key=lambda x: (x != path, x.name.casefold()))
            rows = [TaskRow(x, open_tasks.get(x), parents.get(x)) for x in members]
            for row in rows:
                row.set_sensitive(row.path not in self._trashing)
            rows += [PendingRow(x, branch) for x, (parent, branch)
                     in self._pending.items() if parent == path]
            group = TaskGroup(rows, tag_group, path)
            group.set_pull_requests(self._pull_requests.get(path, {}))
            self._box.append(group)
        if self.get_mapped():
            self.refresh_pull_requests()

    def _sort_key(self, path, groups, open_tasks, rank):
        """Return the key that orders the group of `path` among the rest."""
        # Open groups first, by name so that they stay put as they are
        # worked on; the rest most recent first.
        if any(x in open_tasks for x in groups[path]):
            return (0, path.name.casefold(), 0)
        return (1, "", min(rank.get(x, len(rank)) for x in groups[path]))

    def refresh_pull_requests(self):
        """Ask GitHub about each repository listed, at most once a minute."""
        now = time.monotonic()
        for group in self._box:
            # If no subtasks and the repository (first row) not open,
            # we have no known branch and cannot find PRs.
            rows = group.get_rows()
            if len(rows) == 1 and rows[0].task is None: continue
            asked = self._pull_requests_asked.get(group.root)
            if asked is not None and now - asked < 60: continue
            # Recorded before the answer, so that failures are limited
            # to once a minute too.
            self._pull_requests_asked[group.root] = now
            github.list_pull_requests(
                group.root, lambda items, root=group.root:
                self._on_pull_requests_listed(root, items))

    def _on_pull_requests_listed(self, root, items):
        if items is None: return
        self._pull_requests[root] = github.index_pull_requests(items)
        for group in self._box:
            if group.root == root:
                group.set_pull_requests(self._pull_requests[root])

    def clear(self, row):
        """Drop the repository of `row` from the ones recently opened."""
        recent.remove_repository(row.path)
        group = row.get_ancestor(TaskGroup)
        if group.remove(row):
            self._box.remove(group)

    def update(self):
        """Update the cards to match the state of the tasks."""
        # In place, as a rebuild would lose hover and focus.
        for group in self._box:
            group.update()

    def focus(self):
        if (group := self._box.get_first_child()) is not None:
            return group.get_rows()[0].grab_focus()
        self._open_button.grab_focus()
