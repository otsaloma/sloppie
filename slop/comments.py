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
import textwrap
import time

from contextlib import suppress
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango

def dedent_hunk(hunk):
    return textwrap.dedent(hunk.strip("\n"))

class Comment:

    """One review comment, on the changes as a whole or on a hunk."""

    __slots__ = ("text", "branch", "path", "hunk", "sent", "created_at")

    def __init__(self, text, branch, path=None, hunk=None, sent=False,
                 created_at=None):
        self.text = text
        # The branch the comment was written against, which is not
        # necessarily the one it ends up handled on, one round of review
        # often fanning out into several branches.
        self.branch = branch
        # Both None for a comment on the changes as a whole.
        self.path = path
        self.hunk = hunk
        # True once handed to an agent, which is a fact worth keeping,
        # a comment being no less permanent for having been sent.
        self.sent = sent
        # Unix timestamp of writing, by which the comments are sorted,
        # the latest being the one most likely to still be in mind.
        self.created_at = int(time.time()) if created_at is None else created_at

    def serialize(self):
        """Return the comment as text to be handed to an agent."""
        parts = []
        if self.path is not None:
            parts.append(f"{self.path}:")
        if self.hunk is not None:
            parts.append(dedent_hunk(self.hunk))
        parts.append(self.text)
        return "\n\n".join(parts)

class CommentDialog(Gtk.Window):

    """Text of a new or existing review comment."""

    __gsignals__ = {
        "deleted": (GObject.SignalFlags.RUN_LAST, None, ()),
        "moved": (GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_STRING,)),
        "saved": (GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_STRING,)),
        "sent": (GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_STRING,)),
    }

    def __init__(self, parent, branch, current, text="", path=None, hunk=None):
        GObject.GObject.__init__(self)
        self._branch = branch
        # Text given means an existing comment being edited.
        self._text = text
        # Both None for a comment on the changes as a whole. The hunk is
        # here only to be shown, so keep it as shown, dedented the same
        # way as when handed to an agent.
        self._path = path
        self._hunk = None if hunk is None else dedent_hunk(hunk)
        self._button = Gtk.Button(label="_Save" if text else "_Add",
                                  use_underline=True)
        # Moving goes both ways, as the up and down arrows say: a comment
        # of another branch to the current one, to be handled along with
        # the work at hand, and one of the current branch off it, to be
        # left for whichever branch it turns out to belong to. Only an
        # existing comment is there to be moved.
        self._move = None if not text else Gtk.Button(
            icon_name="object-flip-vertical-symbolic",
            tooltip_text=("Move off Current Branch" if branch == current else
                          "Move to Current Branch"))
        # The icon theme has no up arrow that would fit a header bar,
        # a send icon being the closest thing.
        self._send = Gtk.Button(icon_name="send-to-symbolic",
                                tooltip_text="Send to Agent")
        self._view = Gtk.TextView()
        self._init_properties(parent)
        self._init_widgets()
        self._init_signal_handlers()

    def _init_properties(self, parent):
        self.set_default_size(600, 300)
        self.set_modal(True)
        # Comments are written against a branch, so say which one, that
        # being what tells apart one set of comments from another. A
        # comment moved off its branch has none to name.
        verb = "Edit" if self._text else "Add"
        self.set_title(f"{verb} Comment on {self._branch}"
                       if self._branch else f"{verb} Comment")
        self.set_transient_for(parent)

    def _get_subtitle(self):
        """Return a line saying what the comment is on, if not the changes."""
        parts = []
        if self._hunk is not None:
            count = len(self._hunk.split("\n"))
            parts.append(f"{count} line" if count == 1 else f"{count} lines")
        if self._path is not None:
            parts.append(f"in {self._path}" if parts else self._path)
        return f"Regarding {' '.join(parts)}" if parts else None

    def _get_tooltip(self):
        """Return markup showing the file and hunk the comment is on."""
        parts = []
        if self._path is not None:
            parts.append(GLib.markup_escape_text(self._path))
        if self._hunk is not None:
            lines = self._hunk.split("\n")
            # A tooltip is a glance, not a document, so show only the
            # first lines of the hunk and only the start of each line.
            clipped = [x[:100] + "..." if len(x) > 100 else x for x in lines[:20]]
            if len(lines) > 20:
                clipped.append("...")
            text = GLib.markup_escape_text("\n".join(clipped))
            # Monospace, the hunk being code, where alignment matters.
            parts.append(f"<tt>{text}</tt>")
        return "\n\n".join(parts) or None

    def _init_widgets(self):
        header = Gtk.HeaderBar()
        header.set_show_title_buttons(False)
        # A title of our own in place of the window title, so that a
        # second line can be put under it.
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # Center the lines together, the box being given the full height
        # of the header bar, which they don't fill.
        box.set_valign(Gtk.Align.CENTER)
        title = Gtk.Label(label=self.get_title())
        title.add_css_class("title")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(title)
        if subtitle := self._get_subtitle():
            # A comment on a piece of code says which one, there being
            # nothing else to tell it apart from a comment on the changes.
            label = Gtk.Label(label=subtitle)
            label.add_css_class("subtitle")
            # Ellipsize in the middle, the end of a path being the file
            # name, which is the part that says the most.
            label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            box.append(label)
        if tooltip := self._get_tooltip():
            # The title says only what the comment is on, in brief, the
            # file and the hunk in full being a hover away.
            box.set_tooltip_markup(tooltip)
        header.set_title_widget(box)
        cancel = Gtk.Button(label="_Cancel", use_underline=True)
        cancel.connect("clicked", lambda *args: self.close())
        header.pack_start(cancel)
        if self._text:
            # Only an existing comment is there to be deleted.
            delete = Gtk.Button(icon_name="user-trash-symbolic",
                                tooltip_text="Delete Comment")
            delete.connect("clicked", lambda *args: self._delete())
            header.pack_start(delete)
        if self._move is not None:
            header.pack_start(self._move)
        self._button.add_css_class("suggested-action")
        header.pack_end(self._button)
        # Packed after the save button, which puts it left of it, the
        # header bar filling its end from the right inwards.
        header.pack_end(self._send)
        self.set_titlebar(header)
        self._view.add_css_class("monospace")
        self._view.add_css_class("slop-comment-view")
        self._view.set_top_margin(12)
        self._view.set_right_margin(12)
        self._view.set_bottom_margin(12)
        self._view.set_left_margin(12)
        # Comments are prose, not code, so they are not to be broken
        # into lines by hand, but wrapped to whatever width there is.
        self._view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._view.get_buffer().set_text(self._text)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self._view)
        self.set_child(scroller)
        # Typing is the only thing to do here, so start with the text
        # view focused rather than the cancel button in the header.
        self.set_focus(self._view)

    def _init_signal_handlers(self):
        self._button.connect("clicked", lambda *args: self._save())
        self._send.connect("clicked", lambda *args: self._send_to_agent())
        if self._move is not None:
            self._move.connect("clicked", lambda *args: self._move_to_current())
        buffer = self._view.get_buffer()
        buffer.connect("changed", lambda *args: self._update_button())
        self._update_button()
        # The text view takes Enter for a newline and would take Ctrl+Enter
        # too, hence the capture phase, where these run before it.
        shortcuts = Gtk.ShortcutController(
            propagation_phase=Gtk.PropagationPhase.CAPTURE)
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control>Return"),
            action=Gtk.CallbackAction.new(lambda *args: self._save() or True)))
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("Escape"),
            action=Gtk.NamedAction.new("window.close")))
        self.add_controller(shortcuts)

    def _get_text(self):
        buffer = self._view.get_buffer()
        return buffer.get_text(*buffer.get_bounds(), False).strip()

    def _update_button(self):
        # An empty comment is no comment at all.
        self._button.set_sensitive(bool(self._get_text()))
        self._send.set_sensitive(bool(self._get_text()))
        if self._move is not None:
            self._move.set_sensitive(bool(self._get_text()))

    def _save(self):
        # Reachable with nothing typed by way of Ctrl+Enter, which,
        # unlike the button, cannot be made insensitive.
        if not self._get_text(): return
        self.emit("saved", self._get_text())
        self.close()

    def _send_to_agent(self):
        # Sending is saving too, the comment being kept either way,
        # also if there turns out to be no agent to send it to.
        self.emit("sent", self._get_text())
        self.close()

    def _move_to_current(self):
        """Have the comment moved to the current branch."""
        # Moving is saving too, the text being kept as edited, the same
        # as when sending.
        self.emit("moved", self._get_text())
        self.close()

    def _delete(self):
        """Have the comment deleted if confirmed."""
        # A comment can be a lot of writing and there's no undo.
        if not slop.util.confirm(self, "Delete comment?",
                                 "The comment will be permanently lost.",
                                 "Delete"): return
        self.emit("deleted")
        self.close()

class CommentSidebar(Gtk.Box):

    """Review comments on the changes, kept until an agent handles them."""

    def __init__(self, repository):
        GObject.GObject.__init__(self, orientation=Gtk.Orientation.VERTICAL)
        self.repository = repository
        self._branch = None
        self._box = None
        self._placeholder = None
        self._scroller = None
        self._init_widgets()
        # Read once, the file holding the comments of all branches. The
        # cards wait for the branch, which says how they are grouped.
        self._comments = self._read()

    def _init_widgets(self):
        self.add_css_class("slop-comment-sidebar")
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._scroller = Gtk.ScrolledWindow()
        self._scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroller.set_vexpand(True)
        self._scroller.set_child(self._box)
        # The list starts out empty, hence the placeholder instead.
        self._scroller.set_visible(False)
        self.append(self._scroller)
        self._placeholder = Gtk.Label(label="No comments")
        self._placeholder.add_css_class("dim-label")
        self._placeholder.set_vexpand(True)
        self.append(self._placeholder)

    def _get_task(self):
        """Return the task this sidebar belongs to."""
        # The task, not the window, the window holding several of them
        # and only this one's terminals being the agent to send to.
        return self.get_ancestor(slop.TaskPage)

    def _get_file(self):
        """Return the path of the file the comments are kept in."""
        # One file for the whole repository rather than one per branch:
        # comments outlive the branch they were written against, work
        # commented on in one go often being split over branches.
        return self.repository.git_dir / "sloppie" / "comments.json"

    def _read(self):
        """Return the comments of all branches, read from file."""
        items = slop.util.read_json(self._get_file(), [])
        return [Comment(x["text"], x.get("branch"), x.get("path"),
                        x.get("hunk"), x.get("sent", False),
                        x.get("created_at", 0))
                for x in items]

    def _write(self):
        """Write the comments of all branches to file."""
        path = self._get_file()
        if not self._comments:
            # Leave no file behind once the last comment is gone.
            with suppress(Exception):
                path.unlink(missing_ok=True)
            return
        items = [{"text": x.text, "branch": x.branch, "path": x.path,
                  "hunk": x.hunk, "sent": x.sent,
                  "created_at": x.created_at}
                 for x in self._comments]
        slop.util.write_json(items, path)

    def _init_card(self, comment):
        """Return a card showing `comment`."""
        # A card is a summary, not a document. A pasted error log
        # would push everything else out of view, so cut it short
        # here. The comment itself is kept and handed on in full.
        text = comment.text
        if len(text) > 400:
            text = text[:400].rstrip() + "..."
        label = Gtk.Label(label=text, xalign=0)
        if comment.sent:
            # A sent comment is done with, as far as the user is
            # concerned, but stays around to be resent or deleted.
            label.add_css_class("slop-comment-sent")
        if comment.branch != self._branch:
            # Not part of the work at hand, hence dimmed, but in sight
            # and there to be acted on, one comment at a time.
            label.add_css_class("dim-label")
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        # Ask for no width at all, so that the text wraps to the
        # width of the sidebar instead of dictating it.
        label.set_max_width_chars(1)
        # A button, so that the whole card opens the comment for editing
        # and deleting, that being all there is to do with a card.
        card = Gtk.Button(child=label)
        card.add_css_class("monospace")
        card.add_css_class("slop-comment-card")
        card.connect("clicked", lambda *args: self._edit_comment(comment))
        return card

    def _update_cards(self):
        """Rebuild the cards to match the comments."""
        while child := self._box.get_first_child():
            self._box.remove(child)
        # Latest first, the comment just written being the one the user
        # is most likely to look at, edit or delete next.
        comments = sorted(self._comments, key=lambda x: -x.created_at)
        mine = [x for x in comments if x.branch == self._branch]
        others = [x for x in comments if x.branch != self._branch]
        for comment in mine:
            self._box.append(self._init_card(comment))
        if others:
            # A heading, so that comments of another branch or of none
            # are told apart from those of the work at hand at a glance.
            label = Gtk.Label(label="Other Branches", xalign=0.5)
            label.add_css_class("dim-label")
            # Closer to the comments below than to those above, the
            # heading belonging to the group it introduces.
            label.set_margin_top(6)
            self._box.append(label)
        for comment in others:
            self._box.append(self._init_card(comment))
        self._scroller.set_visible(bool(self._comments))
        self._placeholder.set_visible(not self._comments)

    def _edit_comment(self, comment):
        """Let the user rewrite, send or delete `comment`."""
        # The branch of the comment, not the current one, that being
        # what the comment was written against and still says.
        dialog = CommentDialog(self.get_root(), comment.branch, self._branch,
                               comment.text, comment.path, comment.hunk)

        def on_saved(dialog, text):
            comment.text = text
            self._write()
            self._update_cards()

        def on_moved(dialog, text):
            comment.text = text
            # Off the current branch if on it, onto it if not, there
            # being only these two places for a comment to be.
            comment.branch = (None if comment.branch == self._branch
                              else self._branch)
            self._write()
            self._update_cards()

        def on_sent(dialog, text):
            comment.text = text
            self._write()
            self._update_cards()
            self._send_comment(comment)

        def on_deleted(dialog):
            self._comments.remove(comment)
            self._write()
            self._update_cards()
        dialog.connect("saved", on_saved)
        dialog.connect("moved", on_moved)
        dialog.connect("sent", on_sent)
        dialog.connect("deleted", on_deleted)
        dialog.present()

    def _send_comment(self, comment):
        """Hand `comment` to the agent, marking it sent if that worked."""
        # A comment that didn't go stays as it was, so that the user can
        # start the agent and send it again.
        if not self._get_task().send_to_agent(comment.serialize()): return
        comment.sent = True
        self._write()
        self._update_cards()

    def send_unsent_comments(self):
        """Hand the comments of the current branch not yet sent to the agent."""
        # Only the current branch's, the comments of another branch
        # being for other work. A sent comment is likewise done with.
        # Either is only ever sent one at a time, from its own dialog,
        # sending being deliberate at that point.
        # Oldest first, unlike the sidebar, the agent reading the
        # comments as one message, in the order they were written.
        comments = sorted((x for x in self._comments
                           if x.branch == self._branch and not x.sent),
                          key=lambda x: x.created_at)
        if not comments: return
        parts = [x.serialize() for x in comments]
        if len(parts) > 1:
            # A heading above each comment, so that the agent can tell
            # where one ends and the next begins, comments being prose of
            # any shape. A heading rather than a rule, a pasted hunk
            # being far more likely to hold a line of dashes than this.
            parts = [f"# COMMENT {i}\n\n{x}"
                     for i, x in enumerate(parts, start=1)]
        text = "\n\n".join(parts)
        if not self._get_task().send_to_agent(text): return
        for comment in comments:
            comment.sent = True
        self._write()
        self._update_cards()

    def delete_sent_comments(self):
        """Remove the comments of the current branch that have been sent."""
        # Only the current branch's, as with sending, the comments of
        # another branch being deleted one at a time, from their dialog.
        keep = [x for x in self._comments
                if not x.sent or x.branch != self._branch]
        if len(keep) == len(self._comments): return
        self._comments = keep
        self._write()
        self._update_cards()

    def new_comment(self, path=None, hunk=None):
        """Let the user write a comment on `path` and `hunk`, or on the changes."""
        dialog = CommentDialog(self.get_root(), self._branch, self._branch,
                               path=path, hunk=hunk)
        # The comment lands in the sidebar in plain sight, so it needs
        # no toast to say that it was added.
        dialog.connect("saved", lambda dialog, text:
                       self.add_comment(text, path, hunk))
        dialog.connect("sent", lambda dialog, text:
                       self._send_comment(self.add_comment(text, path, hunk)))
        dialog.present()

    def add_comment(self, text, path=None, hunk=None):
        """Add and return a comment on `path` and `hunk`, saving it to file."""
        comment = Comment(text, self._branch, path, hunk)
        self._comments.append(comment)
        self._write()
        self._update_cards()
        return comment

    def set_branch(self, branch):
        """Show the comments written against `branch` first."""
        if branch == self._branch: return
        self._branch = branch
        self._update_cards()
