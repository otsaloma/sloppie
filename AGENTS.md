# AGENTS.md

## Scope

Sloppie is intended to be used only by me. That means we can tailor it
to my preferences, including hard-code things like fonts in code. We
don't need config files, preferences dialogs, user interface
translations, none of that. We're targeting only Linux + GNOME + Wayland
— it's the same system you're running on. Design-wise we want to follow
GNOME/Adwaita look and feel (but not use the Adwaita library).

## Keybindings

The terminal makes every keybinding a conflict: VTE handles key presses
on the focused terminal and forwards them to the shell, which stops
propagation before the window's shortcuts get a turn. We therefore add
the window's shortcut controllers in the capture phase, where they run
before the terminal sees anything, meaning the shell never gets those
keys. When adding a keybinding, always consider what it does in the
shell; in readline and in the tty line discipline (`stty -a`); and avoid
taking over anything important. Document what you do take below.

| Keys       | Sloppie      | Shell action disabled                           |
| ---------- | ------------ | ----------------------------------------------- |
| Ctrl+E     | Edit file    | readline end-of-line: cursor to end of line     |
| Ctrl+Enter | Commit       | readline accept-line: same as a plain Enter     |
| Ctrl+M     | Add comment  | tty ^M: same as a plain Enter, Return unharmed  |
| Ctrl+Q     | Close window | tty XON: resume output stopped by Ctrl+S        |
| Ctrl+S     | Stage file   | tty XOFF: stop output until Ctrl+Q              |
| Ctrl+U     | Unstage file | readline unix-line-discard: erase to line start |
| Ctrl+W     | Close window | readline unix-word-rubout: erase preceding word |
| F5         | Run command  | nothing in readline or tty; TUI apps lose F5    |

## GTK Documentation

Documentation for GTK and associated libraries is available as GIR files
under `/usr/share/gir-1.0`. Grep those for any symbols you need.

- `/usr/share/gir-1.0/Gdk-4.0.gir`
- `/usr/share/gir-1.0/Gio-2.0.gir`
- `/usr/share/gir-1.0/GLibUnix-2.0.gir`
- `/usr/share/gir-1.0/GObject-2.0.gir`
- `/usr/share/gir-1.0/Gtk-4.0.gir` etc.

Make sure you can access that GIR documentation; abort if not. Never
guess how the API works, always check from the documentation. Keep in
mind that we use Python and some of the documentation has been written
for C. You'll need adapt what you see there, for example:

- `GTK_ALIGN_CENTER` → `Gtk.Align.CENTER`
- `gtk_box_new(...)` → `Gtk.Box(...)`
- `gtk_widget_show(widget)` → `widget.show()`

## Validation, Testing

After making changes to Python code, always at minimum run `flake8 ...`
and `pytest ...` against all changed files. After making changes to
GtkBuilder `.ui` files, run `gtk4-builder-tool validate ...`. After
bigger changes, or if you suspect your changes affect other modules, use
`make check` and `make test` to run the full validation and test suites.

## Running the GUI

You can run the GUI as `timeout --signal=TERM 5 bin/sloppie PATH` so it
self-terminates (exit 124) instead of blocking; the console output is
then captured for inspection. `PATH` is any path in a git repository;
initialize a scratch repository if you need particular changes to look
at, including an empty one for the placeholder states.

To see all warnings, set `G_ENABLE_DIAGNOSTIC=1` (forces GTK to emit
deprecation warnings) and read stderr (`2>&1`). GTK/GLib warnings go
through the GLib log system, not Python `warnings`, so `pytest` needs
`-s` to show them. Use `G_DEBUG=fatal-warnings` to turn a warning into a
fatal error (with traceback) when tracking down its source.

## Screenshots

Screenshot tools that grab the screen, such as `grim` or `import`, are
not available, but the window can render itself to PNG. Run a standalone
script that creates `slop.Application([path])` and connects to
"activate" — after the application's own handler, so that
`app.get_windows()[0]` is there — then in a `GLib.timeout_add` callback
(~1500 ms) render the window to PNG and quit the application:

```python
paintable = Gtk.WidgetPaintable(widget=window)
snapshot = Gtk.Snapshot()
paintable.snapshot(snapshot, paintable.get_intrinsic_width(), paintable.get_intrinsic_height())
texture = window.get_native().get_renderer().render_texture(snapshot.to_node())
texture.save_to_png(path)
```

This captures the window content, including the header bar, regardless
of the Wayland compositor. Note that a standalone script doesn't get the
`sys.path` manipulation that `bin/sloppie` does, so add the source repo
to `sys.path` before importing `slop`. The same recipe works for
measuring widget allocations, e.g. to check the size of a sidebar.
