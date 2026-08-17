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

import sys

from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Pango

# The error dialog currently shown, if any.
error_dialog = None

def confirm(parent, message, detail, label):
    """Return ``True`` if the user chooses `label`."""
    dialog = Gtk.AlertDialog(modal=True,
                             message=message,
                             detail=detail,
                             buttons=["Cancel", label],
                             cancel_button=0,
                             default_button=0)

    # AlertDialog only has an asynchronous API, so run a nested main
    # loop to be able to return the response to the caller. Having
    # cancel_button set, dismissing gives us that instead of an error.
    loop = GLib.MainLoop()
    response = 0
    def on_done(dialog, result):
        nonlocal response
        response = dialog.choose_finish(result)
        loop.quit()
    dialog.choose(parent, None, on_done)
    loop.run()
    return response == 1

def show_error(parent, message, error):
    """Show `error` under `message` in a dialog on top of `parent`."""
    global error_dialog
    # Errors can arrive in bursts, e.g. from reloading the repository,
    # which would leave dialogs stacked on top of one another, each one
    # hiding the ones below. The first says enough, skip the rest.
    if error_dialog is not None and error_dialog.get_visible(): return
    # Print as well, so that a whole session's errors can be reviewed
    # when running sloppie from a terminal.
    print(f"sloppie: {error}", file=sys.stderr)
    dialog = Gtk.Window(modal=True, title="Error", transient_for=parent)
    header = Gtk.HeaderBar()
    header.set_show_title_buttons(False)
    close = Gtk.Button(label="_Close", use_underline=True)
    close.connect("clicked", lambda *args: dialog.close())
    header.pack_end(close)
    dialog.set_titlebar(header)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.set_margin_top(18)
    box.set_margin_end(18)
    box.set_margin_bottom(18)
    box.set_margin_start(18)
    summary = Gtk.Label(label=message, xalign=0, wrap=True)
    summary.add_css_class("heading")
    box.append(summary)
    # The output of git is written for a terminal: monospace, so that
    # it lines up as intended, and selectable, so that it can be taken
    # elsewhere. Width is capped by the label, height by the scroller,
    # both of which the dialog shrinks below for a short error.
    output = Gtk.Label(label=str(error),
                       xalign=0,
                       yalign=0,
                       wrap=True,
                       wrap_mode=Pango.WrapMode.WORD_CHAR,
                       max_width_chars=64,
                       selectable=True)

    output.add_css_class("monospace")
    scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                  vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                                  propagate_natural_width=True,
                                  propagate_natural_height=True,
                                  max_content_height=400)

    scroller.set_child(output)
    box.append(scroller)
    dialog.set_child(box)
    shortcuts = Gtk.ShortcutController()
    shortcuts.add_shortcut(Gtk.Shortcut(
        trigger=Gtk.ShortcutTrigger.parse_string("Escape"),
        action=Gtk.NamedAction.new("window.close")))
    dialog.add_controller(shortcuts)
    # Dismissing is the only thing to do here, so start with the close
    # button focused rather than the selectable label.
    dialog.set_focus(close)
    error_dialog = dialog
    dialog.present()
