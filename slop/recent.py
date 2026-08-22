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
import time

from gi.repository import GLib
from pathlib import Path

# Recently opened repositories, kept as a JSON file of path and time
# objects, outside any repository, this being a list across them all.
PATH = Path(GLib.get_user_data_dir()) / "sloppie" / "recent.json"

def _read():
    """Return recorded repositories as items, most recent first."""
    items = slop.util.read_json(PATH, [])
    # Forget repositories not opened in the last two weeks, the list
    # being of what one is working on, not of everything ever opened.
    cutoff = time.time() - 14 * 86400
    items = [x for x in items if x.get("time", 0) > cutoff]
    items.sort(key=lambda x: x["time"], reverse=True)
    return items

def list_repositories():
    """Return the paths of recently opened repositories, most recent first."""
    paths = [Path(x["path"]) for x in _read()]
    # Skip repositories since moved or removed. '.git' is a directory
    # in a normal repository, but a file in a worktree or a submodule.
    return [x for x in paths if (x / ".git").exists()]

def remove_repository(path):
    """Forget `path` as a recently opened repository."""
    items = [x for x in _read() if x["path"] != str(path)]
    slop.util.write_json(items, PATH)

def add_repository(path):
    """Record `path` as the most recently opened repository."""
    # Scratch repositories under /tmp come and go and are never returned
    # to, be they made by hand for a quick look or by the tests.
    if Path(path).is_relative_to("/tmp"): return
    items = [x for x in _read() if x["path"] != str(path)]
    items.insert(0, {"path": str(path), "time": round(time.time())})
    slop.util.write_json(items, PATH)
