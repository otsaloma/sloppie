# AGENTS.md

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
