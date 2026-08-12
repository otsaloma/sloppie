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

__version__ = "0.1"

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
gi.require_version("Pango", "1.0")
gi.require_version("Vte", "3.91")

from pathlib import Path

# Default to the source directory, overwritten when installing.
DATA_DIR = Path(__file__).parent.parent.joinpath("data").resolve()

from slop.git import DiffLine
from slop.git import FileChange
from slop.git import Repository
from slop.diff import DiffView
from slop.sidebar import FileSidebar
from slop.comments import CommentSidebar
from slop.terminal import Terminal
from slop.window import Window
from slop.app import Application

def main(args):
    global app
    app = Application(args)
    raise SystemExit(app.run())
