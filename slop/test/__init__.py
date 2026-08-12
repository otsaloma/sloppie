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
    def git(*args):
        subprocess.run(["git", "-c", "user.email=test@test",
                        "-c", "user.name=Test", *args],
                       cwd=str(root),
                       check=True,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)

    git("init", "-q")
    (root / "modified.txt").write_text("a\nb\nc\n", "utf-8")
    (root / "renamed-from.txt").write_text("keep\n", "utf-8")
    (root / "binary.bin").write_bytes(b"bin\x00\x01data\n")
    git("add", "-A")
    git("commit", "-qm", "init")
    # Staged: a modification, a rename and a binary change.
    (root / "modified.txt").write_text("a\nB\nc\nd\n", "utf-8")
    git("mv", "renamed-from.txt", "renamed-to.txt")
    (root / "binary.bin").write_bytes(b"bin\x00\x02data\n")
    git("add", "-A")
    # Unstaged: a further modification, without a trailing newline.
    (root / "modified.txt").write_text("a\nB\nc\nd\ne", "utf-8")
    # Untracked: a new file.
    (root / "untracked.txt").write_text("new\n", "utf-8")
    return root

class TestCase:

    def setUp(self):
        self.setup_method(None)

    def setup_method(self, method):
        pass

    def tearDown(self):
        self.teardown_method(None)

    def teardown_method(self, method):
        pass

    def test___init__(self):
        # Make sure that setup_method is always run.
        pass
