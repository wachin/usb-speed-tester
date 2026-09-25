#!/usr/bin/env python3
"""Rasterise the SVG diagrams of USB Speed Tester into PNG files.

The application shows the diagrams as PNG on purpose: a PNG carries its own
glyphs, so the labels can never shift, reflow or disappear because a font is
missing on the machine that runs the program. The SVG files remain the
editable source of truth; run this script after touching them.

Usage
-----
    python3 tools/svg_to_png.py                   # every SVG, 2x -> assets/png
    python3 tools/svg_to_png.py --scale 3         # sharper, larger files
    python3 tools/svg_to_png.py --scale 1         # one pixel per layout pixel
    python3 tools/svg_to_png.py usb3-ss-logo.svg  # only the named diagrams
    python3 tools/svg_to_png.py --list            # show what would be written
    python3 tools/svg_to_png.py --clean           # delete generated PNGs first

Files are written as ``<name>.png`` for scale 1 and ``<name>@2x.png``,
``<name>@3x.png`` ... otherwise. The application understands that suffix and
picks the variant that matches the screen's device pixel ratio.
"""

from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_INPUT = os.path.join(REPO_ROOT, "assets", "svg")
DEFAULT_OUTPUT = os.path.join(REPO_ROOT, "assets", "png")

EXIT_OK = 0
EXIT_FAILURE = 1


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="svg_to_png.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="SVG files (or bare names) to convert; default: every .svg in --indir",
    )
    parser.add_argument("--indir", default=DEFAULT_INPUT,
                        help="directory holding the SVG sources")
    parser.add_argument("--outdir", default=DEFAULT_OUTPUT,
                        help="directory for the generated PNGs")
    parser.add_argument("--scale", type=float, default=2.0,
                        help="pixel multiplier, 2 keeps HiDPI screens sharp (default: 2)")
    parser.add_argument("--clean", action="store_true",
                        help="delete the PNGs in --outdir before converting")
    parser.add_argument("--list", action="store_true",
                        help="only list the conversions that would happen")
    return parser.parse_args(argv)


def output_name(stem: str, scale: float) -> str:
    """``logo`` at scale 2 -> ``logo@2x.png``; at scale 1 -> ``logo.png``."""
    if abs(scale - 1.0) < 0.001:
        return f"{stem}.png"
    return f"{stem}@{scale:g}x.png"


def collect_sources(files, indir):
    """Resolve the requested files, or every .svg in *indir* when none given."""
    if not files:
        if not os.path.isdir(indir):
            return []
        return [
            os.path.join(indir, name)
            for name in sorted(os.listdir(indir))
            if name.lower().endswith(".svg")
        ]
    resolved = []
    for item in files:
        for candidate in (item, os.path.join(indir, item)):
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
    """Rasterise one SVG; returns ``(width, height)`` of the written PNG."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        raise ValueError("not a readable SVG file")

    size = renderer.defaultSize()
    if not size.isValid() or size.width() <= 0 or size.height() <= 0:
        raise ValueError("the SVG has no usable width/height")

    width = max(1, round(size.width() * scale))
    height = max(1, round(size.height() * scale))

    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()

    if not image.save(png_path, "PNG"):
        raise OSError(f"could not write {png_path}")
    return width, height


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.scale <= 0:
        print("error: --scale must be greater than zero", file=sys.stderr)
        return EXIT_FAILURE

    sources = collect_sources(args.files, args.indir)
    if not sources:
        print(f"error: no SVG files found in {args.indir}", file=sys.stderr)
        return EXIT_FAILURE

    planned = []
    for source in sources:
        stem = os.path.splitext(os.path.basename(source))[0]
        planned.append((source, os.path.join(args.outdir, output_name(stem, args.scale))))

    if args.list:
        print(f"Input : {args.indir}")
        print(f"Output: {args.outdir}  (scale {args.scale:g}x)")
        for source, target in planned:
            print(f"  {os.path.basename(source):<28} -> {os.path.basename(target)}")
        return EXIT_OK

    if args.clean and os.path.isdir(args.outdir):
        removed = 0
        for name in os.listdir(args.outdir):
            if name.lower().endswith(".png"):
                os.remove(os.path.join(args.outdir, name))
                removed += 1
        print(f"Removed {removed} stale PNG file(s) from {args.outdir}")

    os.makedirs(args.outdir, exist_ok=True)
    # Keep the reference alive: a collected QGuiApplication leaves QtSvg
    # without a font database and the labels disappear from the PNGs.
    application = qt_application()
    assert application is not None

    failures = 0
    print(f"Converting {len(planned)} diagram(s) at {args.scale:g}x")
    print(f"  from {args.indir}")
    print(f"  to   {args.outdir}")
    for source, target in planned:
        label = os.path.basename(source)
        if not os.path.isfile(source):
            print(f"  [missing] {label}")
            failures += 1
            continue
        try:
            width, height = render(source, target, args.scale)
        except Exception as exc:  # noqa: BLE001 - reported to the user
            print(f"  [failed ] {label}: {exc}")
            failures += 1
            continue
        kib = os.path.getsize(target) / 1024
        print(f"  [ok     ] {label} -> {os.path.basename(target)}"
              f"  ({width}x{height}, {kib:.0f} KiB)")

    if failures:
        print(f"\n{failures} diagram(s) could not be converted.", file=sys.stderr)
        return EXIT_FAILURE
    print("\nDone. Run the application again to see the new PNGs.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
