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

class Config:

    """Configuration items of a repository, kept in a JSON file."""

    def __init__(self, repository):
        self.path = repository.git_dir / "sloppie" / "config.json"

    def read_item(self, key, default=None):
        """Return the value of `key`, or `default` if not set."""
        try:
            if not self.path.exists(): return default
            return json.loads(self.path.read_text("utf-8")).get(key, default)
        except (OSError, ValueError) as error:
            # Rather fall back on the default than fail to do the thing
            # the configuration item was needed for.
            print(f"sloppie: {error}", file=sys.stderr)
            return default

    def write_item(self, key, value):
        """Write `value` as the value of `key`."""
        try:
            config = {}
            if self.path.exists():
                config = json.loads(self.path.read_text("utf-8"))
            config[key] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", "utf-8")
        except (OSError, ValueError) as error:
            # The value is lost, but whatever it was set for can go on.
            print(f"sloppie: {error}", file=sys.stderr)
