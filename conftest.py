# -*- coding: utf-8 -*-

import os
import tempfile

# Keep tests from writing to the real data directory, where opening a
# repository would leave the scratch repositories of tests in the list
# of recent ones. GLib reads this only once, so set it before any use.
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="sloppie-data-")

# Run git against the scratch repositories alone, ignoring the global
# and system configuration, which would otherwise decide part of what
# git outputs and thus what the tests see: 'diff.renames' whether the
# rename of the fixture is found as one, 'core.excludesfile' whether
# its untracked file is listed at all. The repository configuration is
# the fixture's own and is set by it. Inherited by the fixture scripts
# and the code under test alike, both being subprocesses of pytest.
os.environ["GIT_CONFIG_GLOBAL"] = "/dev/null"
os.environ["GIT_CONFIG_SYSTEM"] = "/dev/null"

# Avoid segfaults with GTK 4.22 under Wayland: destroying a window
# whose focus is in a text entry, with no other window left, and then
# showing a new window crashes in GTK's Wayland text-input code when
# a late input-method event arrives for the freed widget. Tests create
# and destroy windows like that constantly; the app itself keeps its
# main window alive and is not affected. The simple input method
# bypasses the Wayland text-input protocol entirely.
os.environ["GTK_IM_MODULE"] = "gtk-im-context-simple"

def pytest_configure(config):
    # Silence the shitload of warnings about GTK deprecations.
    # We'll probably clear these only once bumping the major GTK version.
    config.addinivalue_line("filterwarnings", r"ignore:Gtk\..* is deprecated:DeprecationWarning")
    config.addinivalue_line("filterwarnings", r"ignore::gi.PyGIDeprecationWarning")
    # Silence warnings about PyGObject internal asyncio integration.
    config.addinivalue_line("filterwarnings", r"ignore:'asyncio\..* is deprecated:DeprecationWarning")
