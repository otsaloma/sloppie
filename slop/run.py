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

class RunDialog(Gtk.Window):

    """Command run by the run button, kept in the configuration."""

    __gsignals__ = {
        "saved": (GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_STRING,)),
    }

    def __init__(self, parent, config):
        GObject.GObject.__init__(self)
        self.config = config
        self._button = Gtk.Button(label="_Save", use_underline=True)
        self._view = Gtk.TextView()
        self._init_properties(parent)
        self._init_widgets()
        self._init_signal_handlers()

    def _init_properties(self, parent):
        self.set_default_size(600, 300)
        self.set_modal(True)
        self.set_title("Configure Run Command")
        self.set_transient_for(parent)

    def _init_widgets(self):
        header = Gtk.HeaderBar()
        header.set_show_title_buttons(False)
        cancel = Gtk.Button(label="_Cancel", use_underline=True)
        cancel.connect("clicked", lambda *args: self.close())
        header.pack_start(cancel)
        self._button.add_css_class("suggested-action")
        header.pack_end(self._button)
        self.set_titlebar(header)
        self._view.add_css_class("monospace")
        self._view.add_css_class("slop-run-view")
        self._view.set_top_margin(12)
        self._view.set_right_margin(12)
        self._view.set_bottom_margin(12)
        self._view.set_left_margin(12)
        # A command is a single line, but a long one can be wrapped
        # rather than run off the edge of the view.
        self._view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        buffer = self._view.get_buffer()
        buffer.set_text(self.config.read_item("run-command", ""))
        # Start with the whole command selected, so that typing replaces
        # it, this usually being either a first or a fresh command.
        buffer.select_range(*buffer.get_bounds())
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self._view)
        self.set_child(scroller)
        # Typing is the only thing to do here, so start with the text
        # view focused rather than the cancel button in the header.
        self.set_focus(self._view)

    def _init_signal_handlers(self):
        self._button.connect("clicked", lambda *args: self._save())
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
        # An empty command is nothing to run.
        self._button.set_sensitive(bool(self._get_text()))

    def _save(self):
        # Reachable with nothing typed by way of Ctrl+Enter, which,
        # unlike the button, cannot be made insensitive.
        if not self._get_text(): return
        self.config.write_item("run-command", self._get_text())
        self.emit("saved", self._get_text())
        self.close()
