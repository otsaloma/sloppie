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

    def __init__(self, args):
        GObject.GObject.__init__(self)
        self.set_application_id("io.otsaloma.sloppie")
        self.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        self.connect("activate", self._on_activate, args)

    def _on_activate(self, app, args):
        args = self._parse_arguments(args)
        repository = None
        if args.path is not None:
            try:
                repository = slop.Repository(args.path)
            except Exception as error:
                # Nothing to show without a repository, so fail like git does.
                print(f"sloppie: {error}", file=sys.stderr)
                raise SystemExit(1)
        # Without a path the window asks for a repository itself.
        window = slop.Window(repository)
        self.add_window(window)
        window.present()

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
