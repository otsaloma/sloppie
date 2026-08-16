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

import json
import sys

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango

class Comment:

    """One review comment, on the changes as a whole or on a hunk."""

    __slots__ = ("text", "path", "hunk", "sent")

    def __init__(self, text, path=None, hunk=None, sent=False):
        self.text = text
        # Both None for a comment on the changes as a whole.
        self.path = path
        self.hunk = hunk
        # True once handed to an agent, which is a fact worth keeping,
        # a comment being no less permanent for having been sent.
        self.sent = sent

    def serialize(self):
        """Return the comment as text to be handed to an agent."""
        parts = []
        if self.path is not None:
            # A hunk always comes with the path of the file it's from.
            parts.append(f"In `{self.path}` regarding:"
                         if self.hunk is not None else
                         f"In `{self.path}`:")
        if self.hunk is not None:
            parts.append("```\n" + self.hunk.strip("\n") + "\n```")
        parts.append(self.text)
        return "\n\n".join(parts)

class CommentDialog(Gtk.Window):

    """Text of a new or existing review comment."""

    __gsignals__ = {
        "deleted": (GObject.SignalFlags.RUN_LAST, None, ()),
        "saved": (GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_STRING,)),
        "sent": (GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_STRING,)),
    }

    def __init__(self, parent, branch, text=""):
        GObject.GObject.__init__(self)
        self._branch = branch
        # Text given means an existing comment being edited.
        self._text = text
        self._button = Gtk.Button(label="_Save" if text else "_Add",
                                  use_underline=True)
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
        # being what tells apart one set of comments from another.
        verb = "Edit" if self._text else "Add"
        self.set_title(f"{verb} Comment on {self._branch}")
        self.set_transient_for(parent)

    def _init_widgets(self):
        header = Gtk.HeaderBar()
        header.set_show_title_buttons(False)
        # A title of our own in place of the window title, so that it
        # can be shown in red on main or master, where comments are
        # most likely written against the wrong branch.
        title = Gtk.Label(label=self.get_title())
        title.add_css_class("title")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        if self._branch in ("main", "master"):
            title.add_css_class("slop-title-warning")
        header.set_title_widget(title)
        cancel = Gtk.Button(label="_Cancel", use_underline=True)
        cancel.connect("clicked", lambda *args: self.close())
        header.pack_start(cancel)
        if self._text:
            # Only an existing comment is there to be deleted.
            delete = Gtk.Button(icon_name="user-trash-symbolic",
                                tooltip_text="Delete Comment")
            delete.connect("clicked", lambda *args: self._delete())
            header.pack_start(delete)
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

    def _delete(self):
        """Have the comment deleted if confirmed."""
        # A comment can be a lot of writing and there's no undo.
        dialog = Gtk.AlertDialog(modal=True,
                                 message="Delete comment?",
                                 detail="The comment will be permanently lost.",
                                 buttons=["Cancel", "Delete"],
                                 cancel_button=0,
                                 default_button=0)

        def on_done(dialog, result):
            # Having cancel_button set, dismissing gives us that
            # instead of an error.
            if dialog.choose_finish(result) != 1: return
            self.emit("deleted")
            self.close()
        dialog.choose(self, None, on_done)

class CommentSidebar(Gtk.Box):

    """Review comments on the changes, kept until an agent handles them."""

    def __init__(self, repository):
        GObject.GObject.__init__(self, orientation=Gtk.Orientation.VERTICAL)
        self.repository = repository
        self._branch = None
        self._box = None
        self._comments = []
        self._placeholder = None
        self._scroller = None
        self._init_widgets()

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

    def _get_file(self):
        """Return the path of the file the comments are kept in."""
        # Comments outlive the session, but not the branch they were
        # written against, the changes they comment on being gone once
        # the branch is merged or abandoned.
        return (self.repository.git_dir /
                "sloppie" / "comments" / f"{self._branch}.json")

    def _read(self):
        """Return the comments of the current branch, read from file."""
        path = self._get_file()
        try:
            if not path.exists(): return []
            items = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError) as error:
            # Rather show no comments than fail to open the repository.
            print(f"sloppie: {error}", file=sys.stderr)
            return []
        return [Comment(x["text"], x.get("path"), x.get("hunk"), x.get("sent", False))
                for x in items]

    def _write(self):
        """Write the comments of the current branch to file."""
        path = self._get_file()
        try:
            if not self._comments:
                # Leave no file behind once the last comment is gone.
                return path.unlink(missing_ok=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            items = [{"text": x.text, "path": x.path, "hunk": x.hunk, "sent": x.sent}
                     for x in self._comments]
            path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", "utf-8")
        except OSError as error:
            # The comment is still shown, it just won't survive the session.
            print(f"sloppie: {error}", file=sys.stderr)

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
        for comment in self._comments:
            self._box.append(self._init_card(comment))
        self._scroller.set_visible(bool(self._comments))
        self._placeholder.set_visible(not self._comments)

    def _edit_comment(self, comment):
        """Let the user rewrite, send or delete `comment`."""
        dialog = CommentDialog(self.get_root(), self._branch, comment.text)

        def on_saved(dialog, text):
            comment.text = text
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
        dialog.connect("sent", on_sent)
        dialog.connect("deleted", on_deleted)
        dialog.present()

    def _send_comment(self, comment):
        """Hand `comment` to the agent, marking it sent if that worked."""
        # A comment that didn't go stays as it was, so that the user can
        # start the agent and send it again.
        if not self.get_root().send_to_agent(comment.serialize()): return
        comment.sent = True
        self._write()
        self._update_cards()

    def send_all_comments(self):
        """Hand all the comments to the agent as one message."""
        if not self._comments: return
        # A rule between comments, so that the agent can tell where one
        # ends and the next begins, comments being prose of any shape.
        text = "\n---\n".join(x.serialize() for x in self._comments)
        if not self.get_root().send_to_agent(text): return
        for comment in self._comments:
            comment.sent = True
        self._write()
        self._update_cards()

    def delete_sent_comments(self):
        """Remove the comments that have been sent to the agent."""
        if not any(x.sent for x in self._comments): return
        self._comments = [x for x in self._comments if not x.sent]
        self._write()
        self._update_cards()

    def new_comment(self):
        """Let the user write a comment on the changes as a whole."""
        dialog = CommentDialog(self.get_root(), self._branch)
        # The comment lands in the sidebar in plain sight, so it needs
        # no toast to say that it was added.
        dialog.connect("saved", lambda dialog, text: self.add_comment(text))
        dialog.connect("sent", lambda dialog, text:
                       self._send_comment(self.add_comment(text)))
        dialog.present()

    def add_comment(self, text, path=None, hunk=None):
        """Add and return a comment on `path` and `hunk`, saving it to file."""
        comment = Comment(text, path, hunk)
        self._comments.append(comment)
        self._write()
        self._update_cards()
        return comment

    def set_branch(self, branch):
        """Show the comments written against `branch`."""
        if branch == self._branch: return
        self._branch = branch
        self._comments = self._read()
        self._update_cards()
