# Makefile for USB Speed Tester
#
#   make                  regenerate the compiled translations (.qm)
#   sudo make install     install into $(PREFIX), /usr/local by default
#   sudo make uninstall   remove what install put there
#   make clean            drop build leftovers
#   make check            sanity-check the installed layout
#
# Debian packaging drives this file through dh_auto_build/dh_auto_install, so
# the package and a plain "make install" put the same files in the same places.

PREFIX      ?= /usr/local
DESTDIR     ?=
PYTHON      ?= /usr/bin/python3
APPID       := io.github.wachin.USBSpeedTester
BINARY      := usb-speed-tester

BINDIR      := $(DESTDIR)$(PREFIX)/bin
SHAREDIR    := $(DESTDIR)$(PREFIX)/share
DATADIR     := $(SHAREDIR)/$(BINARY)
APPDIR      := $(SHAREDIR)/applications
METAINFODIR := $(SHAREDIR)/metainfo
ICONDIR     := $(SHAREDIR)/icons/hicolor
MANDIR      := $(SHAREDIR)/man/man1
ICON_SIZES  := 16 24 32 48 64 128 256

.PHONY: all translations install uninstall clean check

all: translations

# The .qm files are shipped, so a missing lrelease must not break the build.
translations:
	@if command -v lrelease >/dev/null 2>&1; then \
		echo "lrelease: compiling translations/*.ts"; \
		lrelease translations/*.ts >/dev/null; \
	else \
		echo "lrelease not found - keeping the shipped .qm files"; \
	fi

install:
	install -d $(BINDIR) $(DATADIR) $(APPDIR) $(METAINFODIR) $(MANDIR)
	install -m 0755 main.py $(BINDIR)/$(BINARY)
	cp -r assets tutorial translations $(DATADIR)/
	find $(DATADIR) -name '__pycache__' -type d -prune -exec rm -rf {} +
	find $(DATADIR) -name '*.pyc' -delete
	install -m 0644 data/$(APPID).desktop $(APPDIR)/$(APPID).desktop
	install -m 0644 data/$(APPID).metainfo.xml $(METAINFODIR)/$(APPID).metainfo.xml
	install -m 0644 data/$(BINARY).1 $(MANDIR)/$(BINARY).1
	for size in $(ICON_SIZES); do \
		install -d $(ICONDIR)/$${size}x$${size}/apps; \
		install -m 0644 assets/icon/$(BINARY)-$${size}.png \
			$(ICONDIR)/$${size}x$${size}/apps/$(APPID).png; \
	done

uninstall:
	rm -f $(BINDIR)/$(BINARY)
	rm -rf $(DATADIR)
	rm -f $(APPDIR)/$(APPID).desktop
	rm -f $(METAINFODIR)/$(APPID).metainfo.xml
	rm -f $(MANDIR)/$(BINARY).1
	for size in $(ICON_SIZES); do \
		rm -f $(ICONDIR)/$${size}x$${size}/apps/$(APPID).png; \
	done

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '*.pyc' -delete

# Quick self-test: the layout must be complete enough to start the program.
check:
	$(PYTHON) -c "import ast,sys; ast.parse(open('main.py',encoding='utf-8').read())"
	@for size in $(ICON_SIZES); do \
		test -f assets/icon/$(BINARY)-$${size}.png || { \
			echo "missing icon: assets/icon/$(BINARY)-$${size}.png" >&2; exit 1; }; \
	done
	@for lang in tutorial/*/; do \
		test -f "$$lang/tutorial.md" || { echo "missing $$lang/tutorial.md" >&2; exit 1; }; \
	done
	@echo "layout looks complete"
