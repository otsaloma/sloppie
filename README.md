# Sloppie

TODO: Intro

<img src="data/screenshot-1.png" alt="screenshot" width="1466">
<img src="data/screenshot-2.png" alt="screenshot" width="1466">

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
