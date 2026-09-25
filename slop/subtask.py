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

# The git half of forking, run in the first terminal of the new task,
# where a failure or a password prompt can be seen and answered. A
# failed pull aborts nothing: a base a few commits stale is better than
# no subtask. Nothing calls exit, as the terminal would respawn the
# shell and clear the screen of whatever was said about why.
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
    return root.parent / f"{root.name}.{branch.replace('/', '-')}"

def get_error(repository, branch):
    """Return what stands in the way of forking `branch`, or ``None``."""
    branch = branch.strip()
    if not branch:
        return "Enter a branch name"
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
    root = repository.root
    directory = get_directory(root, branch)
    # Moved into place only once whole, so that a copy cut short doesn't
    # look like a subtask.
    partial = directory.with_name(f".{directory.name}.part")
    shutil.rmtree(partial, ignore_errors=True)

    def on_copied(process, result):
        try:
            ok, stdout, stderr = process.communicate_utf8_finish(result)
            if not process.get_successful():
                raise RuntimeError(stderr.strip() or "Failed to copy the repository")
            _finish(repository, partial, directory)
        except Exception as error:
            shutil.rmtree(partial, ignore_errors=True)
            return callback(directory, error)
        callback(directory, None)
    try:
        # cp rather than shutil.copytree, which is slower and neither
        # preserves everything nor makes reflinks.
        process = Gio.Subprocess.new(
            ["cp", "--archive", "--reflink=auto", str(root), str(partial)],
            Gio.SubprocessFlags.STDERR_PIPE)
    except Exception as error:
        return callback(directory, error)
    process.communicate_utf8_async(None, None, on_copied)

def _finish(repository, partial, directory):
    """Make the finished copy at `partial` a subtask at `directory`."""
    # A repository copied mid-command has the lock of that command in
    # it, which would block every git command in the copy.
    (partial / ".git" / "index.lock").unlink(missing_ok=True)
    # Share comments and configuration with the repository forked from,
    # so that they outlive the subtask.
    shared = repository.git_common_dir / "sloppie"
    shared.mkdir(parents=True, exist_ok=True)
    link = partial / ".git" / "sloppie"
    if link.is_symlink():
        # rmtree refuses a symlink.
        link.unlink()
    else:
        shutil.rmtree(link, ignore_errors=True)
    link.symlink_to(shared, target_is_directory=True)
    partial.rename(directory)

def trash(directory, command, callback):
    """Run teardown, trash `directory`, then call `callback(directory, error)`."""
    def move_to_trash():
        try:
            # A rename, so .git/sloppie goes as a symlink, leaving the
            # shared state be. Not supported on internal mounts like /tmp.
            Gio.File.new_for_path(str(directory)).trash(None)
        except Exception as error:
            return callback(directory, error)
        callback(directory, None)

    def on_torn_down(process, result):
        try:
            ok, stdout, stderr = process.communicate_utf8_finish(result)
            if not process.get_successful():
                detail = stdout.strip()
                raise RuntimeError("Teardown command failed" +
                                   (f":\n{detail}" if detail else ""))
        except Exception as error:
            return callback(directory, error)
        move_to_trash()

    if not command:
        return move_to_trash()
    try:
        launcher = Gio.SubprocessLauncher(
            flags=Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)
        launcher.set_cwd(str(directory))
        process = launcher.spawnv(["/bin/sh", "-c", command])
    except Exception as error:
        return callback(directory, error)
    process.communicate_utf8_async(None, None, on_torn_down)

def get_setup_command(branch, command=None):
    """Return the shell commands that make the copy a subtask of `branch`."""
    # Not str.format, which would take the braces of the shell.
    setup = SETUP.replace("{branch}", shlex.quote(branch))
    if command:
        # Last, so that it can count on the branch and on direnv.
        setup += f"set -x\n{command}\n{{ set +x; }} 2>/dev/null\n"
    return setup
