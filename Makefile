# -*- coding: utf-8-unix -*-

# Installation directories without DESTDIR.
PREFIX  = /usr/local
BINDIR  = $(PREFIX)/bin
DATADIR = $(PREFIX)/share
LIBDIR  = $(DATADIR)/sloppie

check:
	flake8 bin/sloppie
	flake8 bin/sloppie.in
	flake8 conftest.py
	flake8 slop

clean:
	rm -rf build
	rm -rf dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +

install:
	@echo "INSTALLING PYTHON PACKAGE..."
	mkdir -p $(DESTDIR)$(LIBDIR)
	cp -R slop $(DESTDIR)$(LIBDIR)
	find $(DESTDIR)$(LIBDIR)/slop -type d -name __pycache__ -prune -exec rm -rf {} +
	find $(DESTDIR)$(LIBDIR)/slop -type d -name test -prune -exec rm -rf {} +
	sed "s|^DATA_DIR = .*$$|DATA_DIR = Path('$(LIBDIR)/data')|" slop/__init__.py > $(DESTDIR)$(LIBDIR)/slop/__init__.py
	grep -qF "$(LIBDIR)/data" $(DESTDIR)$(LIBDIR)/slop/__init__.py
	@echo "INSTALLING DATA FILES..."
	mkdir -p $(DESTDIR)$(LIBDIR)/data
	cp data/sloppie.css $(DESTDIR)$(LIBDIR)/data
	cp data/sloppie.xml $(DESTDIR)$(LIBDIR)/data
	@echo "INSTALLING LAUNCHER..."
	mkdir -p $(DESTDIR)$(BINDIR)
	sed "s|%LIBDIR%|$(LIBDIR)|" bin/sloppie.in > $(DESTDIR)$(BINDIR)/sloppie
	grep -qF "$(LIBDIR)" $(DESTDIR)$(BINDIR)/sloppie
	chmod +x $(DESTDIR)$(BINDIR)/sloppie
	@echo "INSTALLING ICON..."
	mkdir -p $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps
	cp -f data/io.otsaloma.sloppie.svg $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps
	@echo "INSTALLING DESKTOP FILE..."
	mkdir -p $(DESTDIR)$(DATADIR)/applications
	cp -f data/io.otsaloma.sloppie.desktop $(DESTDIR)$(DATADIR)/applications
	test -z "$(DESTDIR)" && update-desktop-database "$(DATADIR)/applications" || true

test:
	pytest -xs slop

.PHONY: check clean install test
