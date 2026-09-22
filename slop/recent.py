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

import time

from gi.repository import GLib
from pathlib import Path
from slop import util

# Recently opened repositories, across all of them, hence outside any.
PATH = Path(GLib.get_user_data_dir()) / "sloppie" / "recent.json"

def _read():
    """Return recorded repositories as items, most recent first."""
    items = util.read_json(PATH, [])
    cutoff = time.time() - 14 * 86400
    items = [x for x in items if x.get("time", 0) > cutoff]
    items.sort(key=lambda x: x["time"], reverse=True)
    return items

def list_repositories():
    """Return the paths of recently opened repositories, most recent first."""
    paths = [Path(x["path"]) for x in _read()]
    # '.git' is a file in a worktree or a submodule.
    return [x for x in paths if (x / ".git").exists()]

def list_parents():
    """Return the repository each subtask was forked from, by path."""
    # Not checked for existence, the caller pairs these with the paths
    # of list_repositories.
    return {Path(x["path"]): Path(x["parent"])
            for x in _read() if x.get("parent")}

def get_resume_command(path):
    """Return the command to resume the last agent session in `path`."""
    return next((x.get("resume") for x in _read()
                 if x["path"] == str(path)), None)

def set_resume_command(path, command):
    """Record `command` as the way back to the agent session left in `path`."""
    items = _read()
    for item in items:
        if item["path"] != str(path): continue
        item["resume"] = command
        return util.write_json(items, PATH)

def remove_repository(path):
    """Forget `path` as a recently opened repository."""
    items = [x for x in _read() if x["path"] != str(path)]
    util.write_json(items, PATH)

def add_repository(path, parent=None):
    """Record `path` as the most recently opened repository."""
    # Scratch repositories, the tests' included, are never returned to.
    if Path(path).is_relative_to("/tmp"): return
    items = _read()
    previous = next((x for x in items if x["path"] == str(path)), {})
    # Only forking gives a parent, keep it across the later openings.
    if parent is None:
        parent = previous.get("parent")
    items = [x for x in items if x["path"] != str(path)]
    item = {"path": str(path), "time": round(time.time())}
    if parent is not None:
        item["parent"] = str(parent)
    if resume := previous.get("resume"):
        item["resume"] = resume
    items.insert(0, item)
    util.write_json(items, PATH)
