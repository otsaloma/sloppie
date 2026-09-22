# AGENTS.md

## Scope

Sloppie is intended to be used only by me. That means we can tailor it
to my preferences, including hard-code things like fonts in code. We
don't need config files, preferences dialogs, user interface
translations, none of that. We're targeting only Linux + GNOME + Wayland
— it's the same system you're running on. Design-wise we want to follow
GNOME/Adwaita look and feel (but avoid using the Adwaita library). We
don't need to support dark mode.

## Keybindings

The terminal makes every keybinding a conflict: VTE handles key presses
on the focused terminal and forwards them to the shell, which stops
propagation before the window's shortcuts get a turn. We therefore add
the window's shortcut controllers in the capture phase, where they run
before the terminal sees anything, meaning the shell never gets those
keys. Copy and paste are the exception: being terminal actions, they are
shortcuts on the terminal itself, in the capture phase too, VTE's own
key controller being in the bubble phase. When adding a keybinding,
always consider what it does in the shell; in readline and in the tty
line discipline (`stty -a`); and avoid taking over anything important.
Document what you do take below.

| Keys          | Sloppie      | Shell action disabled                           |
| ------------- | ------------ | ----------------------------------------------- |
| Ctrl+E        | Edit file    | readline end-of-line: cursor to end of line     |
| Ctrl+Enter    | Commit       | readline accept-line: same as a plain Enter     |
| Ctrl+M        | Add comment  | tty ^M: same as a plain Enter, Return unharmed  |
| Ctrl+PageDown | Next tab     | nothing in readline or tty; TUI apps lose it    |
| Ctrl+PageUp   | Previous tab | nothing in readline or tty; TUI apps lose it    |
| Ctrl+Q        | Quit         | tty XON: resume output stopped by Ctrl+S        |
| Ctrl+S        | Stage file   | tty XOFF: stop output until Ctrl+Q              |
| Ctrl+U        | Unstage file | readline unix-line-discard: erase to line start |
| Ctrl+W        | Close task   | readline unix-word-rubout: erase preceding word |
| Shift+Ctrl+C  | Copy         | tty ^C: interrupt, plain Ctrl+C unharmed        |
| Shift+Ctrl+R  | Resume agent | readline reverse-search, plain Ctrl+R unharmed  |
| Shift+Ctrl+V  | Paste        | readline quoted-insert, plain Ctrl+V unharmed   |
| F4            | Dashboard    | nothing in readline or tty; TUI apps lose F4    |
| F5            | Run command  | nothing in readline or tty; TUI apps lose F5    |
| Shift+F5      | Set command  | same as F5: nothing in readline or tty          |
| F10           | Main menu    | nothing in readline or tty; TUI apps lose F10   |

F10 is not ours: GtkWindow handles it (`handle-menubar-accel`, true by
default) and pops up the menu button that has `primary` set, which the
hamburger in the header bar does.

When unsure what to do about VTE keybindings and other behaviour: check
how does it work in Ptyxis. That's what I use as my regular terminal and
we want this embedded VTE to work as similar as possible to Ptyxis.

## GTK Documentation

Documentation for GTK and associated libraries is available as GIR files
under `/usr/share/gir-1.0`. Grep those for any symbols you need. Make
sure you can access that GIR documentation; abort if not. Never guess
how the API works, always check from the documentation. Keep in mind
that we use Python and some of the documentation has been written for C.
You'll need adapt what you see there, for example:

- `GTK_ALIGN_CENTER` → `Gtk.Align.CENTER`
- `gtk_box_new(...)` → `Gtk.Box(...)`
- `gtk_widget_show(widget)` → `widget.show()`

## Validation, Testing

After making changes to Python code, always at minimum run `flake8 ...`
and `pytest ...` against all changed files. After bigger changes, or if
you suspect your changes affect other modules, use `make check` and
`make test` to run the full validation and test suites.

## Running the GUI

Run a brief GUI check with diagnostics enabled: `G_ENABLE_DIAGNOSTIC=1
timeout 5 bin/sloppie PATH 2>&1`. Exit 124 is expected on timeout. Use
`pytest -s` to expose GTK/GLib warnings in tests, and
`G_DEBUG=fatal-warnings` to stop on warnings when debugging.

`PATH` is any path in a git repository; initialize a scratch repository
if you need particular changes to look at, including an empty one for
the placeholder states.

Standalone scripts must import slop from this checkout, not an installed
copy. Set `PYTHONPATH` or `sys.path` accordingly; verify `slop.__file__`
if unsure.

## Screenshots

For unattended screenshots, render the app's own widgets to PNG using
`Gtk.WidgetPaintable`, `Gtk.Snapshot` and the widget's native renderer
(`render_texture`, then `save_to_png`). This avoids Wayland screenshot
permissions.

Use a standalone script running the app and its GTK main loop; capture
after the target window is visible and has rendered. Capture dialogs
separately.

Run under `dbus-run-session` so it gets its own instance rather than
forwarding to a running Sloppie. The same recipe works for measuring
widget allocations, e.g. to check the size of a sidebar.
