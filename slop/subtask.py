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

import shlex
import shutil

from gi.repository import Gio

# The git half of forking, run in the first terminal of the new task
# rather than out of sight: it is quick, but it can fail, and a fetch
# can want a password, all of which the user should see and be able to
# answer where it happens. The default branch is whichever of main and
# master the repository has, asked of the local branches alone, so that
# a repository with no remote is no different from one with. Nothing
# aborts on a failed pull: a subtask branched off a base a few commits
# stale is worth having, one not made at all is not. Without a default
# branch nothing is done at all, get_error having refused the fork long
# before this, so that only a branch deleted in between lands here. The
# tracing is turned on only once the branch has been worked out, that
# being a pipeline in a subshell and so three lines of noise to trace,
# and it leaves with the shell that ran the setup, the interactive one
# that replaces it starting untraced. Nothing calls exit either: the
# terminal starts a new shell in place of one that exits and clears the
# screen as it does, which would wipe whatever was said about why.
SETUP = """\
export GIT_TERMINAL_PROMPT=0
default=$(git branch --list main master --format='%(refname:short)' | head -1)
if [ -z "$default" ]; then
    echo "sloppie: no main or master branch, leaving the copy alone"
else
    set -x
    git switch --discard-changes "$default"
    git pull
    git switch -c {branch}
    # Silenced through its own stderr, tracing being written there, or
    # turning the tracing off would be one more line of it.
    { set +x; } 2>/dev/null
fi
if [ -f .envrc ]; then
    set -x
    direnv allow
    { set +x; } 2>/dev/null
fi
"""

def get_directory(root, branch):
    """Return the directory a subtask of `root` for `branch` goes in."""
    # A branch name may have slashes in it, 'fix/crash' and the like, a
    # directory name may not have them at all, so dashes stand in.
    return root.parent / f"{root.name}.{branch.replace('/', '-')}"

def get_error(repository, branch):
    """Return what stands in the way of forking `branch`, or ``None``."""
    branch = branch.strip()
    if not branch:
        return "Enter a branch name"
    # Caught before the copy rather than after it: a subtask is forked
    # off the default branch, so without one there is nothing to fork
    # off and no name that would make the forking work.
    if repository.get_default_branch() is None:
        return "No main or master branch to fork off"
    if not repository.is_valid_branch_name(branch):
        return f"{branch} is not a valid branch name"
    if repository.has_branch(branch):
        return f"Branch {branch} already exists"
    directory = get_directory(repository.root, branch)
    if directory.exists():
        return f"{directory.name} already exists"
    return None

def fork(repository, branch, callback):
    """Copy `repository` for `branch`, then call `callback(path, error)`."""
    # The copy alone, the git half of it being the terminal's to run
    # once there is a repository for a task to be opened on at all.
    root = repository.root
    directory = get_directory(root, branch)
    # Copied to a name of its own and moved into place only once whole,
    # so that a copy cut short — the disk filling up, sloppie quitting —
    # leaves something plainly unfinished rather than what looks for all
    # the world like a subtask.
    partial = directory.with_name(f".{directory.name}.part")
    shutil.rmtree(partial, ignore_errors=True)

    def on_copied(process, result):
        try:
            ok, stdout, stderr = process.communicate_utf8_finish(result)
            if not process.get_successful():
                # What cp said, rather than the bare exit status that
                # waiting on it would give: a copy fails for reasons the
                # user can do something about, a full disk above all.
                raise RuntimeError(stderr.strip() or "Failed to copy the repository")
            _finish(repository, partial, directory)
        except Exception as error:
            shutil.rmtree(partial, ignore_errors=True)
            return callback(directory, error)
        callback(directory, None)
    try:
        # cp rather than shutil.copytree, which is slower and neither
        # preserves everything nor makes a reflink of what it copies.
        # Reflinks cost nothing to ask for and are ignored by the file
        # systems that have no such thing, ext4 among them.
        process = Gio.Subprocess.new(
            ["cp", "--archive", "--reflink=auto", str(root), str(partial)],
            Gio.SubprocessFlags.STDERR_PIPE)
    except Exception as error:
        return callback(directory, error)
    process.communicate_utf8_async(None, None, on_copied)

def _finish(repository, partial, directory):
    """Make the finished copy at `partial` a subtask at `directory`."""
    # A repository copied mid-command has the lock of that command in
    # it, which would leave the copy unable to run any git command at
    # all. The command itself is the original's and unharmed.
    (partial / ".git" / "index.lock").unlink(missing_ok=True)
    # Sloppie's own state is shared with the repository forked from,
    # comments especially, which are written against a branch and are
    # worth keeping once the subtask that they were written in is gone.
    # The link is absolute, a relative one being read from the directory
    # holding the link and not from the one it is written in.
    shared = repository.git_dir / "sloppie"
    shared.mkdir(parents=True, exist_ok=True)
    link = partial / ".git" / "sloppie"
    if link.is_symlink():
        # rmtree refuses a symlink, and would leave it to be tripped
        # over by the linking below.
        link.unlink()
    else:
        shutil.rmtree(link, ignore_errors=True)
    link.symlink_to(shared, target_is_directory=True)
    partial.rename(directory)

def trash(directory):
    """Move the subtask at `directory` to the trash."""
    # Trashing is a rename into the trash directory, so .git/sloppie
    # goes along as the symlink it is and the comments and configuration
    # of the repository forked from are left where they are. Note that
    # trashing is not supported on all file systems, /tmp and the like
    # being system internal mounts to GLib.
    Gio.File.new_for_path(str(directory)).trash(None)

def get_setup_command(branch):
    """Return the shell commands that make the copy a subtask of `branch`."""
    # Substituted by hand rather than by str.format, which would take
    # the braces that shell writes freely for fields of its own.
    return SETUP.replace("{branch}", shlex.quote(branch))
