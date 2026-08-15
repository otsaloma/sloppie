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

import atexit
import shutil
import subprocess
import tempfile

from pathlib import Path

def new_repository():
    """Create a scratch repository with a change of each kind."""
    root = Path(tempfile.mkdtemp(prefix="sloppie-"))
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    script = Path(__file__).parents[2] / "tools" / "fixture-minimal.sh"
    subprocess.run([str(script), str(root)], check=True)
    return root

class TestCase:

    def setup_method(self, method):
        pass

    def teardown_method(self, method):
        pass

    def test___init__(self):
        # Make sure that setup_method is always run.
        pass
