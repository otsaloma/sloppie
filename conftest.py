# -*- coding: utf-8 -*-

import os
import tempfile

# Keep tests out of the real list of recent repositories. GLib reads
# this only once, so set it before any use.
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="sloppie-data-")

# Ignore the user's git configuration, which would change what git
# outputs, e.g. 'diff.renames' and 'core.excludesfile'.
os.environ["GIT_CONFIG_GLOBAL"] = "/dev/null"
os.environ["GIT_CONFIG_SYSTEM"] = "/dev/null"

# Avoid segfaults with GTK 4.22 under Wayland: destroying a window
# whose focus is in a text entry, with no other window left, and then
# showing a new window crashes in GTK's Wayland text-input code when
# a late input-method event arrives for the freed widget. The simple
# input method bypasses the Wayland text-input protocol entirely.
os.environ["GTK_IM_MODULE"] = "gtk-im-context-simple"

def pytest_configure(config):
    # Silence the shitload of warnings about GTK deprecations.
    # We'll probably clear these only once bumping the major GTK version.
    config.addinivalue_line("filterwarnings", r"ignore:Gtk\..* is deprecated:DeprecationWarning")
    config.addinivalue_line("filterwarnings", r"ignore::gi.PyGIDeprecationWarning")
    # Silence warnings about PyGObject internal asyncio integration.
    config.addinivalue_line("filterwarnings", r"ignore:'asyncio\..* is deprecated:DeprecationWarning")
