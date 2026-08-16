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
import time

from gi.repository import GLib
from pathlib import Path

# Recently opened repositories, kept as a JSON file of path and time
# objects, outside any repository, this being a list across them all.
PATH = Path(GLib.get_user_data_dir()) / "sloppie" / "recent.json"

def _read():
    """Return recorded repositories as items, most recent first."""
    try:
        if not PATH.exists(): return []
        items = json.loads(PATH.read_text("utf-8"))
        # Forget repositories not opened in the last two weeks, the list
        # being of what one is working on, not of everything ever opened.
        cutoff = time.time() - 14 * 86400
        items = [x for x in items if x["time"] > cutoff]
        items.sort(key=lambda x: x["time"], reverse=True)
        return items
    except (KeyError, OSError, TypeError, ValueError) as error:
        # Rather start over with an empty list than fail to open a
        # repository on account of the list of recent ones.
        print(f"sloppie: {error}", file=sys.stderr)
        return []

def list_repositories():
    """Return the paths of recently opened repositories, most recent first."""
    paths = [Path(x["path"]) for x in _read()]
    # Skip repositories since moved or removed. '.git' is a directory
    # in a normal repository, but a file in a worktree or a submodule.
    return [x for x in paths if (x / ".git").exists()]

def add_repository(path):
    """Record `path` as the most recently opened repository."""
    # Scratch repositories under /tmp come and go and are never returned
    # to, be they made by hand for a quick look or by the tests.
    if Path(path).is_relative_to("/tmp"): return
    items = [x for x in _read() if x["path"] != str(path)]
    items.insert(0, {"path": str(path), "time": round(time.time())})
    try:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", "utf-8")
    except OSError as error:
        # The repository is missing from the list, nothing more.
        print(f"sloppie: {error}", file=sys.stderr)
