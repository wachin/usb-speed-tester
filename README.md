# USB Speed Tester

[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/PyQt-6.9+-green?logo=qt&logoColor=white)](https://pypi.org/project/PyQt6/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux-lightgrey?logo=linux&logoColor=white)](https://www.linux.org/)
[![Code Style](https://img.shields.io/badge/Code%20Style-PEP%208-brightgreen)](https://peps.python.org/pep-0008/)

A PyQt6 desktop application for analyzing, benchmarking, and diagnosing USB storage devices on Linux. Provides a graphical interface to run common USB diagnostic commands and interpret their results in plain language.

## Features

| Feature | Description |
|---------|-------------|
| **Dynamic Device Detection** | Lists USB storage devices with vendor, model, size, mount point, and negotiated bus speed |
| **Real-time Hotplug Monitoring** | Uses `pyudev` to detect device insertion/removal without UI freezing |
| **Bus Analysis** | Runs `lsusb -t` to show USB topology and negotiated speed (480M vs 5000M) |
| **Read Benchmark** | Executes `hdparm -tT` (via `pkexec`) for cached and physical read speeds |
| **Write Benchmark** | Writes 1 GB test file with `dd` (with space check via `psutil`) |
| **Advanced fio Benchmark** | Sequential + 4K random read/write with IOPS, latency, and throughput |
| **SMART Health** | Runs `smartctl -a` (via `pkexec`) for device health diagnostics |
| **Dual Output Panels** | Technical Log (raw output) + User Analysis (plain-language interpretation) |
| **Markdown Analysis** | User Analysis is rendered as Markdown/rich text (headings, lists, quotes, tables) |
| **Inline Diagrams** | Explains the `SS` (SuperSpeed) port marking with diagrams that scale to the window |
| **Progress Tracking** | Real-time progress bar for long-running tests |
| **Internationalization** | All UI strings in English with `QTranslator` support for Spanish |

## Screenshots

*(Add screenshots here when available)*

## Requirements

### System Dependencies (Linux)
```bash
# Debian/Ubuntu
sudo apt install python3-pyqt6 python3-pyudev python3-psutil \
    util-linux smartmontools fio policykit-1

# Arch Linux
sudo pacman -S python-pyqt6 python-pyudev python-psutil \
    util-linux smartmontools fio polkit

# Fedora
sudo dnf install python3-pyqt6 python3-pyudev python3-psutil \
    util-linux smartmontools fio polkit
```

### Python Packages
```bash
pip install PyQt6 pyudev psutil
```

## Installation

```bash
git clone https://github.com/yourusername/usb-speed-tester.git
cd usb-speed-tester
# Install Python deps (if not using system packages)
pip install -r requirements.txt
```

## Usage

```bash
python3 main.py
```

1. Select a USB device from the dropdown
2. Choose which tests to run (all enabled by default)
3. Click **Run Selected Tests**
4. View results in the **Technical Log** tab
5. Read plain-language analysis in the **User Analysis** tab

### Test Details

- **Bus Analysis** - No privileges needed. Shows if device negotiated USB 2.0 (480M) or USB 3.x (5000M)
- **Read Benchmark** - Requires root via `pkexec`. Shows cached vs physical read speeds
- **Write Benchmark** - Writes 1 GB file. Checks for 1.5 GB free space first
- **fio Benchmark** - Runs 4 jobs (seq read/write, rand 4K read/write) on 256 MB each
- **SMART Health** - Requires root. May show "not supported" for USB flash drives

## Project Structure

```
usb-speed-tester/
├── main.py              # Complete application (single-file for simplicity)
├── assets/
│   ├── svg/             # Editable vector sources of the diagrams
│   │   ├── usb3-ss-logo.svg      # SS + USB trident SuperSpeed emblem
│   │   ├── usb3-ss-ports.svg     # Two SS ports vs. a USB 2.0 port
│   │   └── usb3-ss-laptop.svg    # SS marking engraved next to a laptop port
│   └── png/             # Generated PNGs actually shown by the application
│       ├── usb3-ss-logo@2x.png
│       ├── usb3-ss-ports@2x.png
│       └── usb3-ss-laptop@2x.png
├── tools/
│   └── svg_to_png.py    # Regenerates assets/png/ from assets/svg/
├── .gitignore
├── LICENSE
├── README.md
└── translations/        # .qm translation files (generated from .ts)
    └── usbtester_es.qm  # Spanish translation example
```

## Diagrams

The **User Analysis** tab embeds three diagrams that explain where the `SS`
(SuperSpeed) marking sits on a laptop or PC. They are drawn as SVG and shipped
as PNG, because a PNG carries its own glyphs: the labels can never shift or
disappear because a font is missing on the machine running the program.

Edit the SVG sources, then regenerate the PNGs:

```bash
python3 tools/svg_to_png.py              # all diagrams, 2x for HiDPI screens
python3 tools/svg_to_png.py --list       # preview without writing anything
python3 tools/svg_to_png.py --scale 3    # even sharper, larger files
python3 tools/svg_to_png.py usb3-ss-logo.svg   # just one diagram
python3 tools/svg_to_png.py --clean      # drop stale PNGs first
```

Files are written as `name.png` for `--scale 1` and `name@2x.png` for larger
scales. At runtime the application picks the smallest variant that still
covers the screen's device pixel ratio, and falls back to the SVG source if no
PNG has been generated yet.

> **Tip:** QtSvg (used both by the converter and by that fallback) does not
> implement every SVG feature. In particular it ignores `<tspan>` elements that
> carry their own `y` coordinate, so a multi-line text block written by Inkscape
> collapses into a single line. Give each line its own `<text>` element.

## Internationalization (i18n)

All UI strings use `QCoreApplication.translate()` (via `self.tr()`). To add Spanish:

```bash
# 1. Extract strings
pylupdate6 main.py -ts translations/usbtester_es.ts

# 2. Edit translations/usbtester_es.ts with Qt Linguist

# 3. Compile
lrelease translations/usbtester_es.ts
```

The app auto-loads `translations/usbtester_<locale>.qm` at startup.

## Architecture

```
MainWindow
├── DeviceMonitor (QThread)     # pyudev hotplug monitoring
├── BusAnalysisWorker (QThread) # lsusb -t
├── ReadBenchmarkWorker (QThread)   # hdparm -tT via pkexec
├── WriteBenchmarkWorker (QThread)  # dd with progress
├── FioBenchmarkWorker (QThread)    # fio JSON output
└── SmartHealthWorker (QThread)     # smartctl -a via pkexec
```

All workers inherit from `BaseTestWorker` which provides:
- `progress` signal (percent, message)
- `finished` signal (device_id, output)
- `error` signal (message)
- Cancellation support

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "pkexec not found" | Install `policykit-1` or `polkit` |
| "hdparm: NOT_IOCTLABLE" | Unmount device first or check permissions |
| "fio timed out" | Reduce test size or increase timeout in code |
| "SMART not supported" | Normal for USB flash drives |
| Device not detected | Check `lsblk` and `lsusb -t` manually |
| Bus speed shows Unknown | Requires udev access to USB device ancestors |

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Acknowledgments

- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - Qt6 Python bindings
- [pyudev](https://pyudev.readthedocs.io/) - Linux device monitoring
- [psutil](https://psutil.readthedocs.io/) - System and process utilities
- [fio](https://fio.readthedocs.io/) - Flexible I/O tester
- [smartmontools](https://www.smartmontools.org/) - SMART monitoring tools