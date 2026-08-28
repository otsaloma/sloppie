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
    # One request for the whole repository rather than one per branch:
    # a repository and the subtasks forked from it are all one and the
    # same repository to GitHub, so one answer covers the whole group.
    # Never waited on either, gh going over the network, hence the
    # callback, which is given None for anything that went wrong.
    launcher = Gio.SubprocessLauncher(
        flags=Gio.SubprocessFlags.STDOUT_PIPE |
        Gio.SubprocessFlags.STDERR_SILENCE)

    # gh works out which repository this is from the remotes of the
    # directory it runs in, a subtask's being its parent's.
    launcher.set_cwd(str(root))

    def on_listed(process, result):
        try:
            ok, stdout, stderr = process.communicate_utf8_finish(result)
            # A repository with no GitHub remote, gh not logged in, the
            # network down: none of them say that a branch has no pull
            # request, only that we are none the wiser.
            callback(json.loads(stdout) if process.get_successful() else None)
        except Exception:
            callback(None)
    try:
        # gh lists the newest created first, so the limit is a horizon:
        # the hundred pull requests opened last. Repository-wide that is
        # a week in a busy team repository, which would lose a subtask
        # forked a fortnight ago, hence one's own alone, of which a
        # hundred is months anywhere. A pull request opened by somebody
        # else on a branch checked out here is thus not found, which is
        # the price of asking once per repository rather than per branch.
        process = launcher.spawnv(
            ["gh", "pr", "list",
             "--author", "@me",
             "--state",  "all",
             "--limit",  "100",
             "--json",   "headRefName,number,state,url"])
    except Exception:
        # No gh installed, which is as much of an answer as a repository
        # that is not on GitHub, and just as fine.
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
    # A branch reused after a merge has more than one pull request, of
    # which the open one is the one being worked on. Failing that the
    # newest, which is the first that gh lists.
    item = min(items, key=lambda x: x["state"] != "OPEN")
    # An open one is named by its number, there being one to go back to
    # and comment on; the others by what became of them, which is what
    # one wants to know of a branch done with.
    if item["state"] == "MERGED": return "merged", item["url"]
    if item["state"] == "CLOSED": return "closed", item["url"]
    return f"#{item['number']}", item["url"]
