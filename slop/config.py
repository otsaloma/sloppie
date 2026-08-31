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

from slop import util

# Every configuration item there is and the value it has when not set,
# so that the file offered for editing can hold them all, there being no
# user interface for any of them beyond that file.
DEFAULTS = {
    "run-command": None,
    "setup-command": None,
    "wrap-lines": True,
}

class Config:

    """Configuration items of a repository, kept in a JSON file."""

    def __init__(self, repository):
        self.path = repository.git_dir / "sloppie" / "config.json"

    def read_item(self, key):
        """Return the value of `key`, or its default if not set."""
        return util.read_json(self.path, {}).get(key, DEFAULTS[key])

    def write_item(self, key, value):
        """Write `value` as the value of `key`."""
        # Read and write the whole file, it being a handful of items
        # that all go together, written one at a time as they change.
        config = util.read_json(self.path, {})
        config[key] = value
        util.write_json(config, self.path)

    def write_as_full(self):
        """Write the file with the default value of every item not set."""
        # Keys of a file no longer known here are kept, they being the
        # user's to remove and not worth losing to a version of sloppie
        # that happens to predate one of them.
        config = {**DEFAULTS, **util.read_json(self.path, {})}
        util.write_json(config, self.path)
