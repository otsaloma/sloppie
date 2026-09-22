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
import slop
import slop.test

from slop.comments import Comment

class TestCommentSidebar(slop.test.TestCase):

    def setup_method(self, method):
        # Two sidebars on the one file, as a repository and a subtask
        # forked from it are.
        self.repository = slop.Repository(slop.test.new_repository())
        self.mine = slop.CommentSidebar(self.repository)
        self.mine.set_branch("master")
        self.theirs = slop.CommentSidebar(self.repository)
        self.theirs.set_branch("feature")

    def test_a_comment_is_written(self):
        self.mine.add_comment("hello")
        assert [x["text"] for x in self._read()] == ["hello"]

    def test_adding_keeps_what_the_other_wrote(self):
        # 'theirs' was made before this and so knows nothing of it.
        self.mine.add_comment("mine")
        self.theirs.add_comment("theirs")
        assert sorted(x["text"] for x in self._read()) == ["mine", "theirs"]

    def test_deleting_keeps_what_the_other_wrote(self):
        comment = self.mine.add_comment("mine")
        self.theirs.add_comment("theirs")
        self.mine._remove([comment.uid])
        assert [x["text"] for x in self._read()] == ["theirs"]

    def test_editing_keeps_what_the_other_wrote(self):
        comment = self.mine.add_comment("mine")
        self.theirs.add_comment("theirs")
        self.mine._modify([comment.uid], text="edited")
        assert sorted(x["text"] for x in self._read()) == ["edited", "theirs"]

    def test_deleting_sent_comments_keeps_what_the_other_wrote(self):
        comment = self.mine.add_comment("mine")
        self.mine._modify([comment.uid], sent=True)
        self.theirs.add_comment("theirs")
        self.mine.delete_sent_comments()
        assert [x["text"] for x in self._read()] == ["theirs"]

    def test_only_the_current_branch_is_counted(self):
        comment = self.mine.add_comment("mine")
        self.theirs.add_comment("theirs")
        assert self.mine.count_unsent() == 1
        self.mine._modify([comment.uid], sent=True)
        assert self.mine.count_unsent() == 0

    def test_a_comment_keeps_its_identity_across_a_reread(self):
        comment = self.mine.add_comment("mine")
        assert slop.CommentSidebar(self.repository)._read()[0].uid == comment.uid

    def test_a_comment_written_before_uids_gets_one(self):
        # As written by older versions.
        path = self.repository.git_common_dir / "sloppie" / "comments.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([{"text": "old", "branch": "master"}]), "utf-8")
        sidebar = slop.CommentSidebar(self.repository)
        comment = sidebar._read()[0]
        assert comment.uid
        sidebar._modify([comment.uid], text="new")
        assert self._read()[0]["uid"] == comment.uid
        assert self._read()[0]["text"] == "new"

    def test_the_file_goes_with_the_last_comment(self):
        comment = self.mine.add_comment("mine")
        self.mine._remove([comment.uid])
        assert not (self.repository.git_common_dir / "sloppie" / "comments.json").exists()

    def test_comment_starting_with_exclamation_mark_is_prefixed(self):
        comment = Comment(text="!ls\nhello\n!world")
        assert comment.serialize() == "...!ls\nhello\n...!world"

    def _read(self):
        """Return the comments as they are on file."""
        path = self.repository.git_common_dir / "sloppie" / "comments.json"
        return json.loads(path.read_text("utf-8"))
