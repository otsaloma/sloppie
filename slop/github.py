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

from gi.repository import Gio

def list_pull_requests(root, callback):
    """List the pull requests of the repository at `root`, then call `callback`."""
    # One request per repository, not per branch, the subtasks forked
    # from a repository being the same repository to GitHub. The
    # callback is given None for anything that went wrong.
    launcher = Gio.SubprocessLauncher(
        flags=Gio.SubprocessFlags.STDOUT_PIPE |
        Gio.SubprocessFlags.STDERR_SILENCE)

    launcher.set_cwd(str(root))

    def on_listed(process, result):
        try:
            ok, stdout, stderr = process.communicate_utf8_finish(result)
            callback(json.loads(stdout) if process.get_successful() else None)
        except Exception:
            callback(None)
    try:
        # gh lists the newest first, so the limit is a horizon. Only
        # one's own, as a hundred of all can be a week in a busy team
        # repository. A pull request by somebody else on a branch
        # checked out here is thus not found.
        process = launcher.spawnv(
            ["gh", "pr", "list",
             "--author", "@me",
             "--state",  "all",
             "--limit",  "100",
             "--json",   "headRefName,number,state,url"])
    except Exception:
        return callback(None)
    process.communicate_utf8_async(None, None, on_listed)

def index_pull_requests(items):
    """Return the tag and the link to show for `items`, by branch."""
    branches = {}
    for item in items:
        branches.setdefault(item["headRefName"], []).append(item)
    return {x: parse_pull_request(y) for x, y in branches.items()}

def parse_pull_request(items):
    """Return the tag and the link to show for `items` of one branch."""
    # A branch reused after a merge has several: prefer the open one,
    # else the newest, which gh lists first.
    item = min(items, key=lambda x: x["state"] != "OPEN")
    if item["state"] == "MERGED": return "merged", item["url"]
    if item["state"] == "CLOSED": return "closed", item["url"]
    return f"#{item['number']}", item["url"]
