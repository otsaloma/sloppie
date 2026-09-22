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

import hashlib
import re
import slop
import textwrap
import time
import uuid

from contextlib import suppress
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from slop import util

def dedent_hunk(hunk):
    return textwrap.dedent(hunk.strip("\n"))

def derive_uid(item):
    """Return the uid of `item`, which was written before there were uids."""
    # Derived from the contents, so that every read gives the same uid:
    # a repository and its subtasks share the file, and each can read it
    # before any writes it back with uids in place.
    text = repr(sorted((str(x), str(y)) for x, y in item.items()))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:32]

class Comment:

    """One review comment, on the changes as a whole or on a hunk."""

    __slots__ = ("uid", "branch", "created_at", "path", "hunk", "text", "sent")

    def __init__(self, uid=None, branch=None, created_at=None,
                 path=None, hunk=None, text="", sent=False):

        self.uid = uid or uuid.uuid4().hex
        self.branch = branch
        self.created_at = int(time.time()) if created_at is None else created_at
        # Both None for a comment on the changes as a whole.
        self.path = path
        self.hunk = hunk
        self.text = text
        self.sent = sent

    def to_dict(self):
        """Return the comment serialized as a dictionary."""
        return {attr: getattr(self, attr) for attr in self.__slots__}

    @classmethod
    def from_dict(cls, data):
        """Return a comment reconstructed from dictionary `data`."""
        return cls(uid=data.get("uid") or derive_uid(data),
                   branch=data.get("branch"),
                   created_at=data.get("created_at", 0),
                   path=data.get("path"),
                   hunk=data.get("hunk"),
                   text=data["text"],
                   sent=data.get("sent", False))

    def serialize(self):
        """Return the comment as text to be handed to an agent."""
        parts = []
        if self.path is not None:
            parts.append(f"{self.path}:")
        if self.hunk is not None:
            # Fenced, as agents read Markdown, where lines starting with
            # '+' or '-' are list items. An indented code block would lose
            # its indentation on the way into an agent's prompt.
            parts.append("```\n{}\n```".format(dedent_hunk(self.hunk)))
        # Agents take a line starting with '!' for a shell command to run.
        parts.append(re.sub(r"^!", "...!", self.text, flags=re.MULTILINE))
        return "\n\n".join(parts)

class CommentDialog(Gtk.Window):

    """Text of a new or existing review comment."""

    __gsignals__ = {
        "deleted": (GObject.SignalFlags.RUN_LAST, None, ()),
        "moved": (GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_STRING,)),
        "saved": (GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_STRING,)),
        "sent": (GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_STRING,)),
    }

    def __init__(self, parent, branch, current,
                 text="", path=None, hunk=None, sent=False):

        GObject.GObject.__init__(self)
        self._branch = branch
        # Text given means an existing comment being edited.
        self._text = text
        self._sent = sent
        self._path = path
        self._hunk = None if hunk is None else dedent_hunk(hunk)
        self._button = Gtk.Button(label="_Save" if text else "_Add",
                                  use_underline=True)
        self._move = None if not text else Gtk.Button(
            icon_name="object-flip-vertical-symbolic",
            tooltip_text=("Move off Current Branch" if branch == current else
                          "Move to Current Branch"))
        self._send = Gtk.Button(icon_name="send-to-symbolic",
                                tooltip_text="Send to Agent")
        self._view = Gtk.TextView()
        self._init_properties(parent)
        self._init_widgets()
        self._init_signal_handlers()

    def _init_properties(self, parent):
        self.set_default_size(600, 300)
        self.set_modal(True)
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
            clipped = [x[:100] + "..." if len(x) > 100 else x for x in lines[:20]]
            if len(lines) > 20:
                clipped.append("...")
            text = GLib.markup_escape_text("\n".join(clipped))
            parts.append(f"<tt>{text}</tt>")
        return "\n\n".join(parts) or None

    def _init_widgets(self):
        header = Gtk.HeaderBar()
        header.set_show_title_buttons(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_valign(Gtk.Align.CENTER)
        title = Gtk.Label(label=self.get_title())
        title.add_css_class("title")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(title)
        if subtitle := self._get_subtitle():
            label = Gtk.Label(label=subtitle)
            label.add_css_class("subtitle")
            # The end of a path, the file name, says the most.
            label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            box.append(label)
        if tooltip := self._get_tooltip():
            box.set_tooltip_markup(tooltip)
        header.set_title_widget(box)
        cancel = Gtk.Button(label="_Cancel", use_underline=True)
        cancel.connect("clicked", lambda *args: self.close())
        header.pack_start(cancel)
        if self._text:
            delete = Gtk.Button(icon_name="user-trash-symbolic",
                                tooltip_text="Delete Comment")
            delete.connect("clicked", lambda *args: self._delete())
            header.pack_start(delete)
        if self._move is not None:
            header.pack_start(self._move)
        self._button.add_css_class("suggested-action")
        header.pack_end(self._button)
        # pack_end fills from the right, so this goes left of the above.
        header.pack_end(self._send)
        self.set_titlebar(header)
        self._view.add_css_class("monospace")
        self._view.add_css_class("slop-comment-view")
        self._view.set_top_margin(12)
        self._view.set_right_margin(12)
        self._view.set_bottom_margin(12)
        self._view.set_left_margin(12)
        self._view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._view.get_buffer().set_text(self._text)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self._view)
        self.set_child(scroller)
        self.set_focus(self._view)

    def _init_signal_handlers(self):
        self._button.connect("clicked", lambda *args: self._save())
        self._send.connect("clicked", lambda *args: self._send_to_agent())
        if self._move is not None:
            self._move.connect("clicked", self._on_move_clicked)
        buffer = self._view.get_buffer()
        buffer.connect("changed", lambda *args: self._update_button())
        self._update_button()
        # Capture phase to beat the text view, which takes Ctrl+Enter.
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
        enabled = bool(self._get_text())
        for button in (self._button, self._send, self._move):
            if button is not None:
                button.set_sensitive(enabled)

    def _save(self):
        # Ctrl+Enter bypasses the insensitive button.
        if not self._get_text(): return
        self.emit("saved", self._get_text())
        self.close()

    def _send_to_agent(self):
        # Saved too, also if there turns out to be no agent.
        self.emit("sent", self._get_text())
        self.close()

    def _on_move_clicked(self, button):
        """Have the comment moved onto or off the current branch."""
        self.emit("moved", self._get_text())
        self.close()

    def _delete(self):
        """Have the comment deleted, asking first unless it has been sent."""
        if self._sent or util.confirm(self, "Delete comment?",
                                      "The comment will be permanently lost.",
                                      "Delete", destructive=True):
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
        self._comments = self._read()

    def _init_widgets(self):
        self.add_css_class("slop-comment-sidebar")
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._scroller = Gtk.ScrolledWindow()
        self._scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroller.set_vexpand(True)
        self._scroller.set_child(self._box)
        self._scroller.set_visible(False)
        self.append(self._scroller)
        self._placeholder = Gtk.Label(label="No comments")
        self._placeholder.add_css_class("dim-label")
        self._placeholder.set_vexpand(True)
        self.append(self._placeholder)

    def count_unsent(self):
        """Return how many comments of the current branch wait to be sent."""
        return sum(x.branch == self._branch and not x.sent for x in self._comments)

    def _get_task(self):
        """Return the task this sidebar belongs to."""
        return self.get_ancestor(slop.TaskPage)

    def _get_file(self):
        """Return the path of the file the comments are kept in."""
        # One file for all branches, work commented on in one go often
        # being split over branches.
        return self.repository.git_common_dir / "sloppie" / "comments.json"

    def _read(self):
        """Return the comments of all branches, read from file."""
        return [Comment.from_dict(x)
                for x in util.read_json(self._get_file(), [])]

    def _modify(self, uids, **fields):
        """Set `fields` on the comments in `uids`, keeping what others wrote."""
        # Read afresh, as the subtasks forked from this repository write
        # the same file.
        comments = self._read()
        for comment in comments:
            if comment.uid not in uids: continue
            for name, value in fields.items():
                setattr(comment, name, value)
        self._write(comments)

    def _remove(self, uids):
        """Drop the comments in `uids`, keeping what others wrote."""
        self._write([x for x in self._read() if x.uid not in uids])

    def _write(self, comments):
        """Take `comments` as the comments of all branches, writing them to file."""
        self._comments = comments
        path = self._get_file()
        if comments:
            util.write_json([x.to_dict() for x in comments], path)
        else:
            with suppress(Exception):
                path.unlink(missing_ok=True)
        self._update_cards()

    def _init_card(self, comment):
        """Return a card showing `comment`."""
        text = comment.text
        if len(text) > 400:
            text = text[:400].rstrip() + "..."
        label = Gtk.Label(label=text, xalign=0)
        if comment.sent:
            label.add_css_class("slop-comment-sent")
        if comment.branch != self._branch:
            label.add_css_class("dim-label")
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        # Ask for no width at all, so that the text wraps to the
        # width of the sidebar instead of dictating it.
        label.set_max_width_chars(1)
        card = Gtk.Button(child=label)
        card.add_css_class("monospace")
        card.add_css_class("slop-comment-card")
        card.connect("clicked", lambda *args: self._edit_comment(comment))
        return card

    def _update_cards(self):
        """Rebuild the cards to match the comments."""
        while child := self._box.get_first_child():
            self._box.remove(child)
        comments = sorted(self._comments, key=lambda x: -x.created_at)
        mine = [x for x in comments if x.branch == self._branch]
        others = [x for x in comments if x.branch != self._branch]
        for comment in mine:
            self._box.append(self._init_card(comment))
        if others:
            label = Gtk.Label(label="Other Branches", xalign=0.5)
            label.add_css_class("dim-label")
            label.set_margin_top(6)
            self._box.append(label)
        for comment in others:
            self._box.append(self._init_card(comment))
        self._scroller.set_visible(bool(self._comments))
        self._placeholder.set_visible(not self._comments)

    def _edit_comment(self, comment):
        """Let the user rewrite, send or delete `comment`."""
        dialog = CommentDialog(self.get_root(), comment.branch, self._branch,
                               comment.text, comment.path, comment.hunk,
                               comment.sent)

        def on_saved(dialog, text):
            self._modify([comment.uid], text=text)

        def on_moved(dialog, text):
            branch = (None if comment.branch == self._branch else self._branch)
            self._modify([comment.uid], text=text, branch=branch)

        def on_sent(dialog, text):
            self._modify([comment.uid], text=text)
            # Send the reread comment, which has the edited text.
            if (saved := self._find(comment.uid)) is not None:
                self._send_comment(saved)

        def on_deleted(dialog):
            self._remove([comment.uid])
        dialog.connect("saved", on_saved)
        dialog.connect("moved", on_moved)
        dialog.connect("sent", on_sent)
        dialog.connect("deleted", on_deleted)
        dialog.present()

    def _find(self, uid):
        """Return the comment known by `uid`, if there still is one."""
        return next((x for x in self._comments if x.uid == uid), None)

    def _send_comment(self, comment):
        """Hand `comment` to the agent, marking it sent if that worked."""
        if not self._get_task().send_to_agent(comment.serialize()): return
        self._modify([comment.uid], sent=True)

    def send_unsent_comments(self):
        """Hand the comments of the current branch not yet sent to the agent."""
        # Oldest first, the agent reading them as one message.
        comments = sorted((x for x in self._comments
                           if x.branch == self._branch and not x.sent),
                          key=lambda x: x.created_at)
        if not comments: return
        parts = [x.serialize() for x in comments]
        if len(parts) > 1:
            # Headings rather than rules, as a pasted hunk could well
            # hold a line of dashes.
            parts = [f"# COMMENT {i}\n\n{x}"
                     for i, x in enumerate(parts, start=1)]
        text = "\n\n".join(parts)
        if not self._get_task().send_to_agent(text): return
        self._modify([x.uid for x in comments], sent=True)

    def delete_sent_comments(self):
        """Remove the comments of the current branch that have been sent."""
        uids = [x.uid for x in self._comments
                if x.sent and x.branch == self._branch]
        if not uids: return
        self._remove(uids)

    def new_comment(self, path=None, hunk=None):
        """Let the user write a comment on `path` and `hunk`, or on the changes."""
        dialog = CommentDialog(self.get_root(), self._branch, self._branch,
                               path=path, hunk=hunk)
        dialog.connect("saved", lambda dialog, text:
                       self.add_comment(text, path, hunk))
        dialog.connect("sent", lambda dialog, text:
                       self._send_comment(self.add_comment(text, path, hunk)))
        dialog.present()

    def add_comment(self, text, path=None, hunk=None):
        """Add and return a comment on `path` and `hunk`, saving it to file."""
        comment = Comment(branch=self._branch, path=path, hunk=hunk, text=text)
        # Read afresh, as in _modify.
        self._write([*self._read(), comment])
        return comment

    def set_branch(self, branch):
        """Show the comments written against `branch` first."""
        if branch == self._branch: return
        self._branch = branch
        self._update_cards()
