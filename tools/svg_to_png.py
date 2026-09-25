#!/usr/bin/env python3
"""Regenerate every PNG that USB Speed Tester ships, from its SVG source.

What it writes
--------------
1. ``tutorial/<LANG>/*.png`` — the diagrams shown in the *Explanations* tab.
   Every language folder found under ``tutorial/`` gets its own copy, right
   next to its ``tutorial.md``, because the tutorial links them with a
   relative path.
2. ``assets/icon/<name>-<size>.png`` — the fixed-size application icons built
   from ``assets/icon/<name>.svg``.

Why PNG and not SVG
-------------------
A PNG carries its own glyphs, so the labels can never shift, reflow or
disappear because a font is missing on the machine that runs the program. The
SVG files remain the editable source of truth: change them and run this script
again.

Usage
-----
    python3 tools/svg_to_png.py                  # everything, 1x + 2x for HiDPI
    python3 tools/svg_to_png.py --list           # show what would be written
    python3 tools/svg_to_png.py --scales 1,2,3   # add even sharper variants
    python3 tools/svg_to_png.py usb3-ss-logo.svg # only the named diagrams
    python3 tools/svg_to_png.py --clean          # drop generated PNGs first
    python3 tools/svg_to_png.py --no-icon        # diagrams only

Diagram files are named ``<name>.png`` at scale 1 and ``<name>@2x.png``,
``<name>@3x.png`` ... otherwise. The application asks for the plain name and
picks the variant that matches the screen's device pixel ratio, so always keep
scale 1 in ``--scales`` (it is the one the tutorial links to).
"""

from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIAGRAMS = os.path.join(REPO_ROOT, "assets", "svg")
DEFAULT_ICONS = os.path.join(REPO_ROOT, "assets", "icon")
DEFAULT_TUTORIAL = os.path.join(REPO_ROOT, "tutorial")
DEFAULT_SCALES = (1.0, 2.0)
DEFAULT_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

EXIT_OK = 0
EXIT_FAILURE = 1


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="svg_to_png.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "files", nargs="*",
        help="SVG files (or bare names) to convert; default: every diagram",
    )
    parser.add_argument("--diagrams", default=DEFAULT_DIAGRAMS,
                        help="directory holding the diagram SVG sources")
    parser.add_argument("--icons", default=DEFAULT_ICONS,
                        help="directory holding the icon SVG sources")
    parser.add_argument("--tutorial", default=DEFAULT_TUTORIAL,
                        help="folder whose <LANG> sub-folders receive the diagrams")
    parser.add_argument("--scales", default=",".join(f"{s:g}" for s in DEFAULT_SCALES),
                        help="comma-separated pixel multipliers for the diagrams "
                             "(default: 1,2)")
    parser.add_argument("--icon-sizes", default=",".join(str(s) for s in DEFAULT_ICON_SIZES),
                        help="comma-separated icon sizes in pixels")
    parser.add_argument("--no-icon", action="store_true",
                        help="skip the application icon")
    parser.add_argument("--clean", action="store_true",
                        help="delete the generated PNGs before converting")
    parser.add_argument("--list", action="store_true",
                        help="only list the conversions that would happen")
    return parser.parse_args(argv)


def parse_numbers(text: str, what: str) -> list:
    values = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            value = float(chunk)
        except ValueError:
            raise SystemExit(f"error: {what} must be numbers, got {chunk!r}")
        if value <= 0:
            raise SystemExit(f"error: {what} must be greater than zero")
        values.append(value)
    if not values:
        raise SystemExit(f"error: no {what} given")
    return values


def scaled_name(stem: str, scale: float) -> str:
    """``logo`` at scale 2 -> ``logo@2x.png``; at scale 1 -> ``logo.png``."""
    if abs(scale - 1.0) < 0.001:
        return f"{stem}.png"
    return f"{stem}@{scale:g}x.png"


def language_dirs(tutorial_root: str) -> list:
    """Existing ``tutorial/<LANG>`` folders, in alphabetical order."""
    if not os.path.isdir(tutorial_root):
        return []
    return [
        os.path.join(tutorial_root, name)
        for name in sorted(os.listdir(tutorial_root))
        if os.path.isdir(os.path.join(tutorial_root, name))
    ]


def svg_sources(files, folder):
    """Resolve the requested files, or every .svg in *folder* when none given."""
    if not files:
        if not os.path.isdir(folder):
            return []
        return [
            os.path.join(folder, name)
            for name in sorted(os.listdir(folder))
            if name.lower().endswith(".svg")
        ]
    resolved = []
    for item in files:
        for candidate in (item, os.path.join(folder, item)):
            if os.path.isfile(candidate):
                resolved.append(candidate)
                break
        else:
            resolved.append(item)  # kept so the caller reports it as missing
    return resolved


def qt_application():
    """Create the QGuiApplication QtSvg needs to lay text out.

    Rendering happens offscreen when there is no display, so the script also
    works over SSH or inside CI.
    """
    from PyQt6.QtGui import QGuiApplication

    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance()
    return app if app is not None else QGuiApplication(sys.argv[:1])


def render(svg_path: str, png_path: str, scale: float) -> tuple:
    """Rasterise one SVG; returns the ``(width, height)`` of the written PNG."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        raise ValueError("not a readable SVG file")

    size = renderer.defaultSize()
    if not size.isValid() or size.width() <= 0 or size.height() <= 0:
        raise ValueError("the SVG has no usable width/height")

    image = QImage(max(1, round(size.width() * scale)),
                   max(1, round(size.height() * scale)),
                   QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()

    if not image.save(png_path, "PNG"):
        raise OSError(f"could not write {png_path}")
    return image.width(), image.height()


def clean_pngs(folder: str) -> int:
    """Delete the generated PNGs in *folder*, never the markdown sources."""
    removed = 0
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if name.lower().endswith(".png"):
                os.remove(os.path.join(folder, name))
                removed += 1
    return removed


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    scales = parse_numbers(args.scales, "--scales")
    icon_sizes = parse_numbers(args.icon_sizes, "--icon-sizes")

    diagrams = svg_sources(args.files, args.diagrams)
    icons = [] if args.no_icon else svg_sources(None, args.icons)
    targets = language_dirs(args.tutorial)

    # (source, destination, scale) for every diagram copy
    jobs = []
    for source in diagrams:
        stem = os.path.splitext(os.path.basename(source))[0]
        for folder in targets:
            for scale in scales:
                jobs.append((source, os.path.join(folder, scaled_name(stem, scale)), scale))
    icon_jobs = []
    for source in icons:
        stem = os.path.splitext(os.path.basename(source))[0]
        for size in icon_sizes:
            icon_jobs.append(
                (source, os.path.join(args.icons, f"{stem}-{int(size)}.png"), size)
            )

    if args.list:
        print(f"Diagrams : {args.diagrams}")
        print(f"Tutorial : {args.tutorial}")
        for folder in targets:
            print(f"           -> {os.path.relpath(folder, REPO_ROOT)}")
        for source, target, scale in jobs:
            print(f"  {os.path.basename(source):<26} -> "
                  f"{os.path.relpath(target, REPO_ROOT)}  ({scale:g}x)")
        if icon_jobs:
            print(f"Icons    : {args.icons}")
            for source, target, size in icon_jobs:
                print(f"  {os.path.basename(source):<26} -> "
                      f"{os.path.relpath(target, REPO_ROOT)}")
        return EXIT_OK

    if not jobs and not icon_jobs:
        print("error: nothing to convert (no SVG sources or no tutorial folders)",
              file=sys.stderr)
        return EXIT_FAILURE

    if args.clean:
        total = 0
        for folder in targets:
            total += clean_pngs(folder)
        if not args.no_icon:
            total += clean_pngs(args.icons)
        print(f"Removed {total} generated PNG file(s)")

    # Keep the reference alive: a collected QGuiApplication leaves QtSvg
    # without a font database and the labels disappear from the PNGs.
    application = qt_application()
    assert application is not None

    failures = 0
    if jobs:
        print(f"Diagrams: {len(diagrams)} source(s) x {len(scales)} scale(s) "
              f"x {len(targets)} language folder(s)")
        if not targets:
            print("  (no tutorial/<LANG> folder found - nothing to write)")
        for source, target, scale in jobs:
            if not os.path.isfile(source):
                print(f"  [missing] {os.path.basename(source)}")
                failures += 1
                continue
            label = f"{os.path.basename(source)} @{scale:g}x"
            try:
                width, height = render(source, target, scale)
            except Exception as exc:  # noqa: BLE001 - reported to the user
                print(f"  [failed ] {label}: {exc}")
                failures += 1
                continue
            kib = os.path.getsize(target) / 1024
            print(f"  [ok     ] {label:<28} -> "
                  f"{os.path.relpath(target, REPO_ROOT):<34} ({width}x{height}, {kib:.0f} KiB)")

    if icon_jobs:
        print(f"Icons: {len(icons)} source(s) x {len(icon_sizes)} size(s)")
        for source, target, size in icon_jobs:
            try:
                width, height = render(source, target, size / 256.0)
            except Exception as exc:  # noqa: BLE001 - reported to the user
                print(f"  [failed ] {os.path.basename(source)}: {exc}")
                failures += 1
                continue
            kib = os.path.getsize(target) / 1024
            print(f"  [ok     ] {os.path.basename(target):<34} ({width}x{height}, {kib:.0f} KiB)")

    if failures:
        print(f"\n{failures} image(s) could not be converted.", file=sys.stderr)
        return EXIT_FAILURE
    print("\nDone. Run the application again to see the new images.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
