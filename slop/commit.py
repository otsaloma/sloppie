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
import sys

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import GtkSource

class CommitDialog(Gtk.Window):

    """Message to commit the staged changes with."""

    __gsignals__ = {
        "committed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, parent, repository):
        GObject.GObject.__init__(self)
        self.repository = repository
        self._amend = Gtk.Switch()
        self._button = Gtk.Button(label="C_ommit", use_underline=True)
        # A source view for the sake of the right margin line, which a
        # plain text view has no way to draw.
        self._view = GtkSource.View()
        # The message typed, kept while showing the one amended.
        self._typed = ""
        try:
            self._staged = repository.has_staged_changes()
        except Exception as error:
            # Let the commit fail and explain itself, rather than block
            # it here on the grounds of a check that didn't work. No
            # dialog either, this dialog not being presented yet and
            # thus about to cover anything shown on top of the window.
            print(f"sloppie: {error}", file=sys.stderr)
            self._staged = True
        self._init_properties(parent)
        self._init_widgets()
        self._init_signal_handlers()

    def _init_properties(self, parent):
        self.set_default_size(600, 400)
        self.set_modal(True)
        self.set_title("Commit")
        self.set_transient_for(parent)

    def _init_widgets(self):
        header = Gtk.HeaderBar()
        header.set_show_title_buttons(False)
        cancel = Gtk.Button(label="_Cancel", use_underline=True)
        cancel.connect("clicked", lambda *args: self.close())
        header.pack_start(cancel)
        self._button.add_css_class("suggested-action")
        header.pack_end(self._button)
        # Amending rewrites the previous commit, its message shown here
        # for editing in place of whatever was typed.
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.append(Gtk.Label(label="_Amend",
                             use_underline=True,
                             mnemonic_widget=self._amend))
        box.append(self._amend)
        header.pack_end(box)
        self.set_titlebar(header)
        self._view.add_css_class("monospace")
        self._view.add_css_class("slop-commit-view")
        # Margins rather than CSS padding, which would leave the right
        # margin line short of the edges, being drawn only where the
        # text is.
        self._view.set_top_margin(12)
        self._view.set_right_margin(12)
        self._view.set_bottom_margin(12)
        self._view.set_left_margin(12)
        self._view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        # Commit messages are conventionally wrapped at 72 characters.
        self._view.set_show_right_margin(True)
        self._view.set_right_margin_position(72)
        # The margin line takes its color from the style scheme, without
        # which, as buffers are by default, it is not drawn at all.
        manager = GtkSource.StyleSchemeManager.get_default()
        self._view.get_buffer().set_style_scheme(manager.get_scheme("Adwaita"))
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self._view)
        self.set_child(scroller)
        if not self._staged:
            # Say why the commit button is insensitive in place of the
            # message, there being no message to write.
            self._view.get_buffer().set_text("# Nothing is staged!")

    def _init_signal_handlers(self):
        self._button.connect("clicked", lambda *args: self._commit())
        self._amend.connect("notify::active", self._on_amend_notify)
        buffer = self._view.get_buffer()
        buffer.connect("changed", lambda *args: self._update_button())
        self._update_button()
        # The text view takes Enter for a newline and would take Ctrl+Enter
        # too, hence the capture phase, where these run before it.
        shortcuts = Gtk.ShortcutController(
            propagation_phase=Gtk.PropagationPhase.CAPTURE)
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control>Return"),
            action=Gtk.CallbackAction.new(lambda *args: self._commit() or True)))
        shortcuts.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("Escape"),
            action=Gtk.NamedAction.new("window.close")))
        self.add_controller(shortcuts)

    def _get_message(self):
        buffer = self._view.get_buffer()
        return buffer.get_text(*buffer.get_bounds(), False).strip()

    def _update_button(self):
        # An empty message would only abort the commit and with nothing
        # staged there is nothing to commit, amending being the
        # exception, as it can rewrite the previous commit alone.
        self._button.set_sensitive(bool(self._get_message()) and
                                   (self._staged or self._amend.get_active()))

    def _on_amend_notify(self, *args):
        buffer = self._view.get_buffer()
        if self._amend.get_active():
            try:
                message = self.repository.get_last_message()
            except Exception as error:
                # Nothing to amend before the first commit is made.
                slop.util.show_error(self, "Failed to read the previous commit", error)
                return self._amend.set_active(False)
            self._typed = self._get_message()
            buffer.set_text(message)
        else:
            buffer.set_text(self._typed)
        # Amending is a commit of its own, with nothing staged too.
        self._update_button()

    def _commit(self):
        try:
            self.repository.commit(self._get_message(),
                                   amend=self._amend.get_active())
        except Exception as error:
            # Leave the dialog be, so that the message is not lost.
            return slop.util.show_error(self, "Failed to commit", error)
        self.emit("committed")
        self.close()
