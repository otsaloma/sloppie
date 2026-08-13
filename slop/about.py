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

from gi.repository import GObject
from gi.repository import Gtk

class AboutDialog(Gtk.AboutDialog):

    def __init__(self, parent):
        GObject.GObject.__init__(self)
        self.set_authors(("Osmo Salomaa <otsaloma@iki.fi>",))
        self.set_comments("Review slop like it's 2026")
        self.set_copyright("Copyright © 2026 Osmo Salomaa")
        self.set_license_type(Gtk.License.GPL_3_0)
        self.set_logo_icon_name("io.otsaloma.sloppie")
        self.set_modal(True)
        self.set_program_name("Sloppie")
        self.set_title("About Sloppie")
        self.set_transient_for(parent)
        self.set_version(slop.__version__)
        self.set_website("https://github.com/otsaloma/sloppie")
        self.set_website_label("https://github.com/otsaloma/sloppie")
