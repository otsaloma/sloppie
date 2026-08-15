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

    __slots__ = ("text", "path", "hunk")

    def __init__(self, text, path=None, hunk=None):
        self.text = text
        # Both None for a comment on the changes as a whole.
        self.path = path
        self.hunk = hunk

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
        return [Comment(x["text"], x.get("path"), x.get("hunk")) for x in items]

    def _write(self):
        """Write the comments of the current branch to file."""
        path = self._get_file()
        try:
            if not self._comments:
                # Leave no file behind once the last comment is gone.
                return path.unlink(missing_ok=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            items = [{"text": x.text, "path": x.path, "hunk": x.hunk}
                     for x in self._comments]
            path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", "utf-8")
        except OSError as error:
            # The comment is still shown, it just won't survive the session.
            print(f"sloppie: {error}", file=sys.stderr)

    def _update_cards(self):
        """Rebuild the cards to match the comments."""
        while child := self._box.get_first_child():
            self._box.remove(child)
        for comment in self._comments:
            # A card is a summary, not a document. A pasted error log
            # would push everything else out of view, so cut it short
            # here. The comment itself is kept and handed on in full.
            text = comment.text
            if len(text) > 400:
                text = text[:400].rstrip() + "..."
            label = Gtk.Label(label=text, xalign=0)
            label.set_wrap(True)
            label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            # Ask for no width at all, so that the text wraps to the
            # width of the sidebar instead of dictating it.
            label.set_max_width_chars(1)
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            card.add_css_class("monospace")
            card.add_css_class("slop-comment-card")
            card.append(label)
            self._box.append(card)
        self._scroller.set_visible(bool(self._comments))
        self._placeholder.set_visible(not self._comments)

    def add_comment(self, text, path=None, hunk=None):
        """Add a comment on `path` and `hunk`, saving it to file."""
        self._comments.append(Comment(text, path, hunk))
        self._write()
        self._update_cards()

    def set_branch(self, branch):
        """Show the comments written against `branch`."""
        if branch == self._branch: return
        self._branch = branch
        self._comments = self._read()
        self._update_cards()
