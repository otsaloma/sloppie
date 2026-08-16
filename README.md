# Sloppie

Sloppie is a development environment that combines a coding agent
running in a terminal, a git diff viewer and a code-review like
mechanism to pass comments on the diff async to the coding agent.
Sloppie runs on Linux, fitting best in GNOME + Wayland environment.

<img src="data/screenshot-1.png" alt="screenshot" width="1429">
<img src="data/screenshot-2.png" alt="screenshot" width="1429">

Sloppie is hard-coded to its author's preferences and not generic or
configurable. If you like the concept and want to use Sloppie, instead
of installing and using it directly, you'd likely want to clone the
repository, ask a coding agent to customize the font, colors, editor
etc. to your preferences and use that clone instead.

## Installing

Sloppie requires Git, Python ≥3.10, PyGObject ≥3.42, GTK 4.x,
GtkSourceView 5.x and VTE ≥0.76. On Debian/Ubuntu you can install the
dependencies with the following command.

    sudo apt install gir1.2-gtk-4.0 \
                     gir1.2-gtksource-5 \
                     gir1.2-vte-3.91 \
                     git \
                     make \
                     python3 \
                     python3-gi

Then, to install Sloppie, run command

    sudo make PREFIX=/usr/local install
