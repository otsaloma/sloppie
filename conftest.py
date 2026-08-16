# -*- coding: utf-8 -*-

import os
import tempfile

# Keep tests from writing to the real data directory, where opening a
# repository would leave the scratch repositories of tests in the list
# of recent ones. GLib reads this only once, so set it before any use.
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="sloppie-data-")

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
