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

from argparse import ArgumentParser
from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Gtk

class Application(Gtk.Application):

    def __init__(self):
        GObject.GObject.__init__(self)
        self._window = None
        self.set_application_id("io.otsaloma.sloppie")
        self.set_flags(Gio.ApplicationFlags.HANDLES_OPEN)
        self.connect("activate", self._on_activate)
        self.connect("open", self._on_open)

    def do_local_command_line(self, arguments):
        try:
            args = self._parse_arguments(arguments[1:])
        except SystemExit as error:
            # argparse exits for help, version and errors;
            # let GApplication exit.
            return True, arguments, error.code
        forwarded = [arguments[0]]
        if args.path is not None:
            try:
                repository = slop.Repository(args.path)
            except Exception as error:
                print(f"sloppie: {error}", file=sys.stderr)
                return True, arguments, 1
            forwarded.append(str(repository.root))
        return Gtk.Application.do_local_command_line(self, forwarded)

    def _on_activate(self, app):
        if self._window is None:
            self._window = slop.Window()
            self.add_window(self._window)
        self._window.present()

    def _on_open(self, app, files, n_files, hint):
        self.activate()
        for file in files:
            self._window.open_task(file.get_path())

    def _parse_arguments(self, args):
        parser = ArgumentParser(usage="sloppie [OPTION...] [PATH]")
        parser.add_argument("path",
                            nargs="?",
                            default=None,
                            help="path of the git repository")

        parser.add_argument("--version",
                            action="version",
                            version=f"sloppie {slop.__version__}")

        return parser.parse_args(args)
