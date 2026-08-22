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

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from pathlib import Path
from slop import recent

NOTHING = "···"

class TaskCard(Gtk.Frame):

    """One repository in the dashboard, open as a task or only recent."""

    # A frame around a one row 'rich-list', which is the welcome screen's
    # list of recent repositories broken up into a card per repository:
    # the same tall rows and hover, but each in a frame of its own.

    def __init__(self, path, task):
        GObject.GObject.__init__(self)
        self.path = path
        self.task = task
        self._close = None
        self._comments = None
        self._lines_added = None
        self._lines_removed = None
        self._listbox = None
        self._nothing = None
        self._row = None
        self._running = None
        self._title = None
        self.add_css_class("slop-task-card")
        if task is None:
            # Not open, hence nothing to tell about it beyond where it
            # is, and dimmed to set it apart from the ones that are.
            self.add_css_class("slop-task-recent")
        self._init_widgets()
        self.update()

    def _init_widgets(self):
        # A grid, so that the command lines up under the name and the
        # diff under the path, with the close button spanning both rows.
        grid = Gtk.Grid(column_spacing=9, row_spacing=9)
        grid.set_margin_bottom(9)
        grid.set_margin_start(9)
        grid.set_margin_top(9)
        # The name and the branch as one, which together say which task
        # this is, one repository having several of them after part two.
        self._title = Gtk.Label(label=self.path.name, xalign=0)
        self._title.add_css_class("slop-task-name")
        grid.attach(self._title, 0, 0, 1, 1)
        # Long paths give way rather than widen the whole window.
        directory = Gtk.Label(label=self._get_directory(), xalign=1, hexpand=True)
        directory.add_css_class("monospace")
        directory.add_css_class("slop-task-path")
        directory.set_ellipsize(Pango.EllipsizeMode.START)
        directory.set_max_width_chars(1)
        grid.attach(directory, 1, 0, 1, 1)
        # Closing an open task, but forgetting one that is only recent,
        # there being nothing else to be rid of it than this.
        self._close = Gtk.Button(
            icon_name="window-close-symbolic",
            tooltip_text="Close" if self.task else "Forget",
            valign=Gtk.Align.CENTER)

        self._close.add_css_class("flat")
        self._close.add_css_class("slop-task-close")
        self._close.connect("clicked", self._on_close_clicked)
        grid.attach(self._close, 2, 0, 1, 2)
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
        # which is not the same as having nothing to show at all, as a
        # repository that is only recent has.
        self._nothing = Gtk.Label(label=NOTHING, visible=False)
        self._nothing.add_css_class("monospace")
        self._nothing.add_css_class("slop-task-none")
        pending.append(self._nothing)
        grid.attach(pending, 1, 1, 1, 1)
        self._row = Gtk.ListBoxRow(child=grid)
        self._listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        # 'rich-list' gives the tall row and the padding around it.
        self._listbox.add_css_class("rich-list")
        self._listbox.connect("row-activated", self._on_row_activated)
        self._listbox.append(self._row)
        self.set_child(self._listbox)
        # Clip the row to the rounded corners of the frame, which it
        # would otherwise square off when hovered.
        self.set_overflow(Gtk.Overflow.HIDDEN)
        if self.task is None:
            # Nothing to update later either, so the em dashes that
            # stand in for what an open task would show are set here.
            self._running.set_label(NOTHING)
            self._running.add_css_class("slop-task-none")
            self._nothing.set_visible(True)

    def _get_directory(self):
        """Return the directory holding the repository, home as a tilde."""
        directory = self.path.parent
        if not directory.is_relative_to(Path.home()):
            return str(directory)
        return str(Path("~") / directory.relative_to(Path.home()))

    def update(self):
        """Update the card to match the state of the task."""
        # A recent repository is not open and so has no state at all,
        # its card having been given its dashes once and for all.
        if self.task is None: return
        # Thin spaces around the slash, the two being one name.
        self._title.set_label(f"{self.path.name}\u2009/\u2009{self.task.branch}"
                              if self.task.branch else self.path.name)
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

    def _on_row_activated(self, listbox, row):
        self.get_ancestor(Dashboard).emit("open-task", str(self.path))

    def _on_close_clicked(self, button):
        dashboard = self.get_ancestor(Dashboard)
        if self.task is None:
            # Only recent, so there is no task for the window to close,
            # only a card and a line in the list of recent ones to drop.
            return dashboard.forget(self)
        dashboard.emit("close-task", str(self.path))

class Dashboard(Gtk.Box):

    """The page of cards: the tasks open and the repositories recently opened."""

    # The path of the repository is the identity of a task, the window
    # holding the tasks themselves and doing the opening and closing.
    __gsignals__ = {
        "open-task": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "close-task": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self):
        GObject.GObject.__init__(self,
                                 orientation=Gtk.Orientation.VERTICAL,
                                 spacing=24)

        self._box = None
        self._init_widgets()

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

    def _on_open_clicked(self, button):
        dialog = Gtk.FileDialog(modal=True, title="Open Repository")
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
        while card := self._box.get_first_child():
            self._box.remove(card)
        # The tasks open first, in the order given, and the repositories
        # only recently opened below them, most recent first.
        for task in tasks:
            self._box.append(TaskCard(task.repository.root, task))
        roots = [x.repository.root for x in tasks]
        for path in recent.list_repositories():
            if path in roots: continue
            self._box.append(TaskCard(path, None))

    def forget(self, card):
        """Drop the repository of `card` from the ones recently opened."""
        recent.remove_repository(card.path)
        self._box.remove(card)

    def update(self):
        """Update the cards to match the state of the tasks."""
        # Update in place rather than rebuild, the cards changing as
        # often as the tasks are polled and a rebuild taking away
        # whatever the user was hovering over or had focused.
        for card in self._box:
            card.update()

    def focus(self):
        # The first card, or the open button with no cards at all.
        if (card := self._box.get_first_child()) is not None:
            return card.grab_focus()
        self.get_first_child().get_next_sibling().grab_focus()
