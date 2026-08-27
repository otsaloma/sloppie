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

from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from pathlib import Path
from slop import recent
from slop import subtask

NOTHING = "···"

class TaskRow(Gtk.ListBoxRow):

    """One repository in the dashboard, open as a task or only recent."""

    # A tall 'rich-list' row, which is the welcome screen's list of
    # recent repositories broken up into a row per repository, a
    # repository and the subtasks forked from it sharing a frame.

    def __init__(self, path, task, parent=None):
        GObject.GObject.__init__(self)
        self.path = path
        self.task = task
        # The repository this was forked from, which makes it a subtask
        # and decides which buttons it gets.
        self.parent = parent
        self._add = None
        self._comments = None
        self._dismiss = None
        self._lines_added = None
        self._lines_removed = None
        self._nothing = None
        self._running = None
        self._title = None
        self._trash = None
        if task is None:
            # Not open, hence nothing to tell about it beyond where it
            # is, and dimmed to set it apart from the ones that are.
            self.add_css_class("slop-task-recent")
        self._init_widgets()
        self.update()

    def _init_widgets(self):
        # A grid, so that the command lines up under the name and the
        # diff under the path, with the buttons spanning both rows.
        grid = Gtk.Grid(column_spacing=9, row_spacing=9)
        grid.set_margin_start(9)
        if self.task:
            # With one row only, the buttons are the tallest thing in it
            # and their own padding gives the name the same air that
            # these margins would, only twice over.
            grid.set_margin_bottom(9)
            grid.set_margin_top(9)
        # What says which task this is: a repository and the branch it
        # has checked out, or, for a subtask, its branch alone.
        self._title = Gtk.Label(label=self._get_title(), xalign=0)
        self._title.add_css_class("slop-task-name")
        grid.attach(self._title, 0, 0, 1, 1)
        # Long paths give way rather than widen the whole window.
        directory = Gtk.Label(label=self._get_directory(), xalign=1, hexpand=True)
        directory.add_css_class("monospace")
        directory.add_css_class("slop-task-path")
        directory.set_ellipsize(Pango.EllipsizeMode.START)
        directory.set_max_width_chars(1)
        grid.attach(directory, 1, 0, 1, 1)
        self._init_widgets_buttons(grid)
        if self.task:
            self._init_widgets_status(grid)
        self.set_child(grid)

    def _init_widgets_buttons(self, grid):
        # Packed against the end of the row, so that a row with only the
        # one button has it where the last of two is, rather than each
        # button in a column of its own with gaps where a row has none.
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                      halign=Gtk.Align.END,
                      valign=Gtk.Align.CENTER)

        box.add_css_class("slop-task-buttons")

        # First, what can be done with the repository: only one of one's
        # own is forked, a subtask being forked off one already and not
        # forked further itself; and trashing takes the directory with
        # it, hence subtasks alone, those being the copies that Sloppie
        # made in the first place. Every row has the one or the other.
        if self.parent is None:
            self._add = self._new_button("media-playlist-shuffle-symbolic",
                                         "Add Subtask",
                                         self._on_add_subtask_clicked)
            box.append(self._add)
        else:
            self._trash = self._new_button("user-trash-symbolic",
                                           "Trash",
                                           self._on_trash_clicked)
            box.append(self._trash)
        # Last, at the very end of the row: closing an open task, but
        # clearing one that is only recent, there being nothing left to
        # close. A subtask has no clearing, only trashing: clearing it
        # would leave the copy on disk with nothing pointing at it.
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
        # Only recent means only the one row to span: where the
        # repository is, there being no state to tell about a task that
        # isn't open.
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
        # What is running and for how long as one, the time telling a
        # busy agent from a stuck one. One label, so that the status
        # boxes the two of them together; aligned to the start, so that
        # the box is around the text and not the whole column.
        self._running = Gtk.Label(halign=Gtk.Align.START, xalign=0)
        self._running.add_css_class("monospace")
        grid.attach(self._running, 0, 1, 1, 1)
        # What waits to be dealt with: the comments written and not yet
        # sent, and the diff as two labels, so that each half can have
        # the color that it has in the file sidebar as well.
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
        # Stands in for all three when there is none of them to show,
        # so that the row is never blank on one side.
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
        # One subtask is one branch, so its directory name and its branch
        # say the same thing twice: 'project.feature-blah / feature-blah'.
        # The branch alone then, which for a subtask not open is the
        # directory name with the name of the repository it was forked
        # from taken off the front.
        if self.parent is not None:
            prefix = f"{self.parent.name}."
            return branch or (self.path.name[len(prefix):]
                              if self.path.name.startswith(prefix) else
                              self.path.name)
        # A repository has any number of branches, so name both, with
        # thin spaces around the slash, the two being the one name.
        if branch is None: return self.path.name
        return f"{self.path.name}\u2009/\u2009{branch}"

    def update(self):
        """Update the card to match the state of the task."""
        # A recent repository is not open and so has no state at all,
        # its card having been given its dashes once and for all.
        if self.task is None: return
        self._title.set_label(self._get_title())
        # NOTHING rather than a blank where there is nothing to say, so
        # that a card of an open task always has both of its rows.
        running = " ".join(x for x in (self.task.command, self.task.elapsed) if x)
        self._running.set_label(running or NOTHING)
        # Nothing running is no status to box, leaving the dash dimmed
        # like the rest of what a card has nothing to say about.
        status = f"slop-task-{self.task.status}" if running else "slop-task-none"
        for css in ("slop-task-none", "slop-task-waiting", "slop-task-working"):
            self._running.remove_css_class(css)
        self._running.add_css_class(status)
        # Hide what has no number rather than blank it: a blank label
        # still takes its share of the spacing between them, and the
        # comments have a box drawn around them to show empty.
        for label, value, text in ((self._comments, self.task.comments, "{}"),
                                   (self._lines_added, self.task.lines_added, "+{}"),
                                   (self._lines_removed, self.task.lines_removed, "−{}")):
            label.set_label(text.format(value))
            label.set_visible(bool(value))
        self._nothing.set_visible(not (self.task.comments or
                                       self.task.lines_added or
                                       self.task.lines_removed))

    def _on_close_clicked(self, button):
        self.get_ancestor(Dashboard).emit("close-task", str(self.path))

    def _on_clear_clicked(self, button):
        # Only recent, so there is no task for the window to close, only
        # a row and a line in the list of recent ones to drop.
        self.get_ancestor(Dashboard).clear(self)

    def _on_add_subtask_clicked(self, button):
        popover = SubtaskPopover(self.path)
        popover.set_parent(button)
        # A popover set on a widget is a child of it and stays one, so
        # take it off again once dismissed, or every click would leave
        # another of them hanging off the button.
        popover.connect("closed", lambda popover: popover.unparent())
        popover.connect("forked", self._on_subtask_forked)
        popover.popup()

    def _on_subtask_forked(self, popover, branch):
        self.get_ancestor(Dashboard).emit("add-subtask", str(self.path), branch)

    def _on_trash_clicked(self, button):
        self.get_ancestor(Dashboard).emit("trash-task", str(self.path))

class SubtaskPopover(Gtk.Popover):

    """Where the branch of a subtask to be forked is typed."""

    # The argument of "forked" is the branch name, checked here and so
    # good as far as the repository can say before the copy is begun.
    __gsignals__ = {
        "forked": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, path):
        GObject.GObject.__init__(self)
        self.path = path
        self._entry = None
        self._error = None
        self._init_widgets()
        # A popover focuses its first focusable child, but only once it
        # has one to focus, which is after it has been shown.
        self.connect("map", lambda *args: self._entry.grab_focus())

    def _init_widgets(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        # Monospace, a branch name being of a kind with what is typed at
        # a prompt, and wide enough for one of some length.
        self._entry = Gtk.Entry(placeholder_text="branch-name", width_chars=48)
        self._entry.add_css_class("monospace")
        self._entry.connect("activate", self._on_activate)
        box.append(self._entry)
        # Says why Enter did nothing, and takes up no room at all until
        # there is something for it to say.
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
        # Caught here rather than after a minute of copying, the name
        # being the one thing that can be told to be wrong beforehand.
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
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        box.set_margin_start(9)
        box.append(Gtk.Spinner(spinning=True, valign=Gtk.Align.CENTER))
        # Named as it will be once it is a subtask, so that the row
        # merely loses its spinner rather than changes into something
        # else once the copy is done.
        name = Gtk.Label(label=branch, xalign=0)
        name.add_css_class("slop-task-name")
        box.append(name)
        # A copy of a repository with a virtualenv or a node_modules in
        # it is gigabytes and takes its time, so say what the wait is.
        status = Gtk.Label(label="Copying...", xalign=1, hexpand=True)
        status.add_css_class("monospace")
        status.add_css_class("slop-task-path")
        box.append(status)
        self.set_child(box)

    def update(self):
        # Nothing here changes until the copy is done, at which point
        # the row is replaced by one of the subtask itself.
        pass

class TaskGroup(Gtk.Frame):

    """One repository and the subtasks forked from it, as rows of one frame."""

    def __init__(self, rows):
        GObject.GObject.__init__(self)
        self.add_css_class("slop-task-card")
        # A line between the rows, which is what tells the repository
        # and the subtasks forked from it apart within the one frame.
        self._listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                    show_separators=True)

        # 'rich-list' gives the tall rows and the padding around them.
        self._listbox.add_css_class("rich-list")
        self._listbox.connect("row-activated", self._on_row_activated)
        for row in rows:
            self._listbox.append(row)
        self.set_child(self._listbox)
        # Clip the rows to the rounded corners of the frame, which they
        # would otherwise square off when hovered.
        self.set_overflow(Gtk.Overflow.HIDDEN)

    def _on_row_activated(self, listbox, row):
        # A subtask still being copied is no repository yet and so
        # nothing that a task can be opened on.
        if not isinstance(row, TaskRow): return
        self.get_ancestor(Dashboard).emit("open-task", str(row.path))

    def get_rows(self):
        """Return the rows of the group, in the order shown."""
        return list(self._listbox)

    def remove(self, row):
        """Drop `row`, and return ``True`` if the group is left empty."""
        self._listbox.remove(row)
        return self._listbox.get_first_child() is None

    def update(self):
        for row in self._listbox:
            row.update()

class Dashboard(Gtk.Box):

    """The page of cards: the tasks open and the repositories recently opened."""

    # The path of the repository is the identity of a task, the window
    # holding the tasks themselves and doing the opening and closing.
    __gsignals__ = {
        "open-task": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "close-task": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "add-subtask": (GObject.SignalFlags.RUN_LAST, None, (str, str)),
        "trash-task": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self):
        GObject.GObject.__init__(self,
                                 orientation=Gtk.Orientation.VERTICAL,
                                 spacing=24)

        self._box = None
        # Subtasks being copied, by the directory they are copied to,
        # which is where they will be once there is anything there.
        self._pending = {}
        self._tasks = []
        self._init_widgets()
        self._init_shortcuts()

    def _init_widgets(self):
        self.set_halign(Gtk.Align.CENTER)
        # Start from the top rather than the middle, so that the cards
        # grow downwards from where they are instead of the whole lot
        # shifting up and down as tasks come and go.
        self.set_valign(Gtk.Align.START)
        self.set_margin_bottom(48)
        self.set_margin_top(36)
        # Only found once the icon has been installed, but that's fine,
        # a missing icon just leaves an empty space above the button.
        self.append(Gtk.Image(icon_name="io.otsaloma.sloppie", pixel_size=128))
        button = Gtk.Button(label="_Open Repository", use_underline=True)
        button.add_css_class("suggested-action")
        button.set_halign(Gtk.Align.CENTER)
        button.connect("clicked", self._on_open_clicked)
        self.append(button)
        # A card per repository, each its own frame, rather than one
        # list of them all, the cards being separate things to act on.
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        # Keep the list from growing past the window with many
        # repositories, but let a short list stay short.
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_height(True)
        scroller.set_child(self._box)
        self.append(scroller)

    def _init_shortcuts(self):
        # Alt+1 to Alt+9 open the first nine rows, counted from the top
        # across the groups. Nothing says which row is which number:
        # mnemonics would need one printed by every name, which is noise
        # once one knows they are there and can count to nine. The scope
        # hands the shortcuts to the window, so that they work wherever
        # the focus is, but only while the dashboard is the mapped page
        # of the stack, never while a task and its terminals are shown.
        shortcuts = Gtk.ShortcutController(scope=Gtk.ShortcutScope.MANAGED)
        for i in range(1, 10):
            shortcuts.add_shortcut(Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string(f"<Alt>{i}"),
                action=Gtk.CallbackAction.new(
                    lambda widget, args, i=i: self.activate_row(i))))
        self.add_controller(shortcuts)

    def activate_row(self, number):
        """Activate the `number`th row, as though clicked."""
        # A subtask still being copied is no row to open and no row to
        # count either, the numbers being those of the tasks.
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
        self.emit("open-task", file.get_path())

    def set_tasks(self, tasks):
        """Rebuild the cards for `tasks` and the repositories recently opened."""
        self._tasks = list(tasks)
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
        # Most recent first, which is also the order the groups of the
        # repositories not open are shown in.
        listed = recent.list_repositories()
        rank = {path: i for i, path in enumerate(listed)}
        paths = list(open_tasks) + [x for x in listed if x not in open_tasks]
        # A subtask whose parent has since been forgotten stands on its
        # own rather than vanish along with it.
        parents = recent.list_parents()
        parents = {x: y for x, y in parents.items() if x in paths and y in paths}
        groups = {}
        for path in paths:
            groups.setdefault(parents.get(path, path), []).append(path)
        for path in sorted(groups, key=lambda x: self._sort_key(x, groups, open_tasks, rank)):
            # The repository itself first, then the subtasks forked from
            # it, by name, which is the branch with the slashes taken out.
            members = sorted(groups[path],
                             key=lambda x: (x != path, x.name.casefold()))
            rows = [TaskRow(x, open_tasks.get(x), parents.get(x)) for x in members]
            # Last in the group, a subtask still being copied having no
            # repository to be told anything about and no place among
            # the ones that have until it does.
            rows += [PendingRow(x, branch) for x, (parent, branch)
                     in self._pending.items() if parent == path]
            self._box.append(TaskGroup(rows))

    def _sort_key(self, path, groups, open_tasks, rank):
        """Return the key that orders the group of `path` among the rest."""
        # A group is open if any one of its rows is, an open subtask
        # bringing along the repository it was forked from, closed or
        # not. The open ones come first and stay put as they are worked
        # on, hence by name; the rest are a history, hence most recent
        # first, of whichever of their rows was opened last.
        if any(x in open_tasks for x in groups[path]):
            return (0, path.name.casefold(), 0)
        return (1, "", min(rank.get(x, len(rank)) for x in groups[path]))

    def clear(self, row):
        """Drop the repository of `row` from the ones recently opened."""
        recent.remove_repository(row.path)
        group = row.get_ancestor(TaskGroup)
        if group.remove(row):
            # The last row gone takes the frame around it with it.
            self._box.remove(group)

    def update(self):
        """Update the cards to match the state of the tasks."""
        # Update in place rather than rebuild, the cards changing as
        # often as the tasks are polled and a rebuild taking away
        # whatever the user was hovering over or had focused.
        for group in self._box:
            group.update()

    def focus(self):
        # The first row, or the open button with no cards at all.
        if (group := self._box.get_first_child()) is not None:
            return group.get_child().get_first_child().grab_focus()
        self.get_first_child().get_next_sibling().grab_focus()
