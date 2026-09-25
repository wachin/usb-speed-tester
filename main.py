#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# USB Speed Tester - analyse, benchmark and diagnose USB storage devices.
# Copyright (C) 2026 Washington Indacochea Delgado <linuxfrontier@proton.me>
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program.  If not, see <https://www.gnu.org/licenses/>.
"""
USB Speed Tester - PyQt6 Application
Bus analysis, benchmarking, and diagnostics for USB storage devices.
All code and comments in English. Spanish translations via QTranslator.
"""

import argparse
import sys
import os
import subprocess
import tempfile
import shutil
import re
import json
import signal
from dataclasses import dataclass, field
from typing import Optional, List

import psutil
import pyudev
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QCheckBox, QTextEdit, QTextBrowser, QProgressBar,
    QTabWidget, QGroupBox, QLabel, QLineEdit, QMessageBox,
    QHeaderView, QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QSplitter, QFrame, QSizePolicy, QFileDialog,
    QToolButton, QMenu, QDialog, QDialogButtonBox,
)
from PyQt6.QtCore import (
    QThread, pyqtSignal, pyqtSlot, QObject, QCoreApplication,
    QTranslator, QLocale, QLibraryInfo, QTimer, Qt, QUrl,
)
from PyQt6.QtGui import (
    QFont, QTextCursor, QIcon, QAction, QImage, QPainter, QTextDocument,
    QTextImageFormat,
)

try:  # QtSvg is used only as a fallback image loader for the SVG diagrams.
    from PyQt6.QtSvg import QSvgRenderer
except ImportError:  # pragma: no cover - depends on how PyQt6 was packaged
    QSvgRenderer = None


# ─── Asset paths ────────────────────────────────────────
# The program can run from a source checkout, from a self-contained install or
# from a system-wide location such as /usr/share/usb-speed-tester, so the data
# directory is looked up instead of assumed to sit next to this file.
PACKAGE_NAME = "usb-speed-tester"


def _data_dir_candidates() -> List[str]:
    """Directories that may hold assets/, tutorial/ and translations/."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.environ.get("USB_SPEED_TESTER_DATA", ""),
        os.path.join(here, "share", PACKAGE_NAME),
        here,
        os.path.join(sys.prefix, "share", PACKAGE_NAME),
        os.path.join("/usr/local/share", PACKAGE_NAME),
        os.path.join("/usr/share", PACKAGE_NAME),
    ]
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            yield candidate


def _find_data_dir() -> str:
    """First candidate that actually contains the bundled data."""
    for candidate in _data_dir_candidates():
        if os.path.isdir(os.path.join(candidate, "tutorial")):
            return candidate
    return os.path.dirname(os.path.abspath(__file__))


DATA_DIR = _find_data_dir()
APP_DIR = DATA_DIR                      # kept for backwards compatibility
ASSETS_DIR = os.path.join(DATA_DIR, "assets")
DIAGRAMS_SVG_DIR = os.path.join(ASSETS_DIR, "svg")
ICON_DIR = os.path.join(ASSETS_DIR, "icon")
TUTORIAL_DIR = os.path.join(DATA_DIR, "tutorial")
TRANSLATIONS_DIR = os.path.join(DATA_DIR, "translations")


def find_tool(name: str, *fallbacks: str) -> str:
    """Locate an external command, preferring PATH over absolute fallbacks.

    Distributions do not all agree on where hdparm, smartctl or pkexec live
    (``/sbin`` versus ``/usr/sbin``, merged-/usr or not), so the PATH is asked
    first and the historical locations are only a last resort.
    """
    found = shutil.which(name)
    if found:
        return found
    for fallback in fallbacks:
        if os.path.exists(fallback):
            return fallback
    return fallbacks[-1] if fallbacks else name

ICON_NAME = "usb-speed-tester"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
TUTORIAL_IMAGE_WIDTH = 480        # the tutorial shows the diagrams smaller
DEFAULT_LANGUAGE = "EN"

# ─── Application metadata (shown in the About box) ──────
APP_NAME = "USB Speed Tester"
APP_VERSION = "1.0.0"
COPYRIGHT = "© 2026 Washington Indacochea Delgado"
AUTHOR = "Washington Indacochea Delgado"
EMAIL = "linuxfrontier@proton.me"
WEBSITE = "https://github.com/wachin/usb-speed-tester"
LICENSE_NAME = "GPL-3.0"


def ui_language() -> str:
    """Two-letter code used to pick the tutorial and the About text.

    Falls back to English when there is no matching ``tutorial/<CODE>`` folder,
    so the Spanish tutorial appears as soon as the system locale is Spanish.
    """
    try:
        name = QLocale.system().name() or DEFAULT_LANGUAGE
    except Exception:
        name = DEFAULT_LANGUAGE
    code = name.split("_")[0].upper()
    if os.path.isdir(os.path.join(TUTORIAL_DIR, code)):
        return code
    return DEFAULT_LANGUAGE


def tutorial_dir(language: str = "") -> str:
    """Folder that holds the tutorial markdown and its images."""
    language = language or ui_language()
    folder = os.path.join(TUTORIAL_DIR, language)
    if os.path.isdir(folder):
        return folder
    return os.path.join(TUTORIAL_DIR, DEFAULT_LANGUAGE)


def app_icon() -> QIcon:
    """Application icon, built from the PNGs generated by tools/svg_to_png.py."""
    icon = QIcon()
    for size in ICON_SIZES:
        path = os.path.join(ICON_DIR, f"{ICON_NAME}-{size}.png")
        if os.path.exists(path):
            icon.addFile(path)
    if icon.isNull():                      # no PNG yet: use the vector source
        vector = os.path.join(ICON_DIR, f"{ICON_NAME}.svg")
        if os.path.exists(vector):
            icon.addFile(vector)
    return icon


# ─── About box text (English / Spanish) ─────────────────
ABOUT_STRINGS = {
    "EN": {
        "description": (
            "A desktop application that analyses, benchmarks and diagnoses USB "
            "storage devices on Linux, and explains every result in plain "
            "language — including how to recognise a real SuperSpeed port."
        ),
        "technologies": (
            "Python 3 · PyQt6 (Qt 6) · pyudev · psutil<br>"
            "System tools: lsusb (usbutils) · hdparm · dd (coreutils) · "
            "fio · smartctl (smartmontools) · pkexec (polkit)"
        ),
        "version": "Version",
        "copyright": "Copyright",
        "email": "Email",
        "license": "License",
        "website": "Website",
        "technologies_label": "Technologies used",
    },
    "ES": {
        "description": (
            "Aplicación de escritorio que analiza, mide y diagnostica "
            "dispositivos de almacenamiento USB en Linux, y explica cada "
            "resultado en lenguaje claro, incluido cómo reconocer un puerto "
            "SuperSpeed de verdad."
        ),
        "technologies": (
            "Python 3 · PyQt6 (Qt 6) · pyudev · psutil<br>"
            "Herramientas del sistema: lsusb (usbutils) · hdparm · "
            "dd (coreutils) · fio · smartctl (smartmontools) · pkexec (polkit)"
        ),
        "version": "Versión",
        "copyright": "Copyright",
        "email": "Correo",
        "license": "Licencia",
        "website": "Página web",
        "technologies_label": "Tecnologías usadas",
    },
}


def about_html(language: str) -> str:
    """Rich text for the About box, in the language of the tutorial folder."""
    text = ABOUT_STRINGS.get(language, ABOUT_STRINGS[DEFAULT_LANGUAGE])
    return f"""
    <h2 style="margin:0 0 2px 0;">{APP_NAME}</h2>
    <p style="margin:0 0 10px 0; color:#5b6675;">{text['version']} {APP_VERSION}</p>
    <p style="margin:0 0 12px 0;">{text['description']}</p>
    <p style="margin:0 0 4px 0;"><b>{text['technologies_label']}</b><br>
       <span style="color:#4a5563;">{text['technologies']}</span></p>
    <hr>
    <p style="margin:4px 0;"><b>{text['copyright']}:</b> {COPYRIGHT}</p>
    <p style="margin:4px 0;"><b>{text['email']}:</b>
       <a href="mailto:{EMAIL}">{EMAIL}</a></p>
    <p style="margin:4px 0;"><b>{text['license']}:</b> {LICENSE_NAME}</p>
    <p style="margin:4px 0;"><b>{text['website']}:</b>
       <a href="{WEBSITE}">{WEBSITE}</a></p>
    """


# ─── i18n ───────────────────────────────────────────────
class TranslationManager:
    """Installs the application translation that matches the system locale.

    Two details matter here:

    * ``QCoreApplication.installTranslator()`` does **not** take ownership of
      the translator, so every QTranslator keeps the application as its parent.
      A local variable would be garbage collected and the UI would silently
      fall back to English.
    * The locale is tried full first (``es_EC``) and then by language (``es``),
      so one ``usbtester_es.qm`` covers every Spanish-speaking region.
    """

    _translators: List[QTranslator] = []

    @classmethod
    def install(cls, app: QApplication) -> bool:
        locale = QLocale.system().name() or DEFAULT_LANGUAGE
        names = list(dict.fromkeys([locale, locale.split("_")[0]]))

        found = False
        for name in names:
            if cls._load(app, os.path.join(TRANSLATIONS_DIR, f"usbtester_{name}.qm")):
                found = True
                break

        # Qt's own strings: standard dialog buttons, QMessageBox, file dialogs.
        qt_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        for name in names:
            cls._load(app, os.path.join(qt_dir, f"qtbase_{name}.qm"))
        return found

    @classmethod
    def _load(cls, app: QApplication, path: str) -> bool:
        if not os.path.exists(path):
            return False
        translator = QTranslator(app)          # parented, so it stays alive
        if not translator.load(path):
            return False
        app.installTranslator(translator)
        cls._translators.append(translator)
        return True


# ─── Data Model ─────────────────────────────────────────
@dataclass
class USBDevice:
    device_node: str
    vendor: str
    product: str
    size_gb: float
    mount_point: Optional[str]
    bus_speed: str
    bus_type: str
    device_id: str

    def display_name(self) -> str:
        return (
            f"{self.device_node} - {self.vendor} {self.product} "
            f"[{self.size_gb:.1f} GB]"
        )


# ─── Workers ────────────────────────────────────────────
class BaseTestWorker(QThread):
    """Base worker for running tests in background threads."""

    finished = pyqtSignal(str, str)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)

    def __init__(self, device: USBDevice, parent=None):
        super().__init__(parent)
        self.device = device
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _emit_progress(self, percent: int, message: str):
        self.progress.emit(percent, message)

    def _emit_finished(self, device_id: str, output: str):
        self.finished.emit(device_id, output)

    def _emit_error(self, message: str):
        self.error.emit(message)


class BusAnalysisWorker(BaseTestWorker):
    """Runs lsusb -t and parses bus topology/speed."""

    def run(self):
        try:
            self._emit_progress(0, self.tr("Running lsusb -t..."))
            result = subprocess.run(
                [find_tool("lsusb", "/usr/bin/lsusb"), "-t"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            output = result.stdout + result.stderr
            parsed = self._parse_lsusb(output)
            full_output = output + "\n\n" + self.tr("Parsed Analysis") + ":\n" + parsed
            self._emit_progress(100, self.tr("Bus analysis complete"))
            self._emit_finished(self.device.device_node, full_output)
        except subprocess.TimeoutExpired:
            self._emit_error(self.tr("lsusb timed out"))
        except Exception as e:
            self._emit_error(f"lsusb: {e}")

    def _parse_lsusb(self, output: str) -> str:
        lines = output.strip().split("\n")
        result = []
        current_speed = None
        for line in lines:
            stripped = line.strip()
            speed_match = re.search(r',\s*(\d+M)', stripped)
            if speed_match:
                current_speed = speed_match.group(1)
            if "Mass Storage" in stripped or "Storage" in stripped:
                result.append(f"  {stripped}  [Speed: {current_speed or '?'}]")
        return "\n".join(result) if result else self.tr("No mass storage devices found")


class ReadBenchmarkWorker(BaseTestWorker):
    """Runs hdparm -tT via pkexec for cached and physical reads."""

    def run(self):
        try:
            self._emit_progress(0, self.tr("Running hdparm -tT (requires root)..."))
            result = subprocess.run(
                [find_tool("pkexec", "/usr/bin/pkexec"),
                 find_tool("hdparm", "/usr/sbin/hdparm", "/sbin/hdparm"),
                 "-tT", self.device.device_node],
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = result.stdout + result.stderr
            if "NOT_IOCTLABLE" in output:
                output += "\n" + self.tr("Warning: Device not accessible via ioctl. "
                                         "Try unmounting first or checking permissions.")
            self._emit_progress(100, self.tr("Read benchmark complete"))
            self._emit_finished(self.device.device_node, output)
        except FileNotFoundError:
            self._emit_error(self.tr("pkexec not found. Install PolicyKit."))
        except subprocess.TimeoutExpired:
            self._emit_error(self.tr("hdparm timed out"))
        except Exception as e:
            self._emit_error(f"hdparm: {e}")


class WriteBenchmarkWorker(BaseTestWorker):
    """Writes a 1 GB file via dd, checks disk space first."""

    def run(self):
        if not self.device.mount_point:
            self._emit_error(self.tr("Device has no mount point"))
            return
        try:
            usage = psutil.disk_usage(self.device.mount_point)
            free_gb = usage.free / (1024 ** 3)
            if free_gb < 1.5:
                self._emit_error(
                    self.tr("Insufficient space: %.1f GB free, need 1.5 GB") % free_gb
                )
                return

            self._emit_progress(0, self.tr("Writing 1 GB test file with dd..."))
            test_file = os.path.join(self.device.mount_point, ".usb_test_tmp")
            dd_proc = subprocess.Popen(
                [
                    find_tool("dd", "/usr/bin/dd", "/bin/dd"),
                    "if=/dev/zero", f"of={test_file}",
                    "bs=1M", "count=1024", "status=progress", "conv=fdatasync",
                ],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
            )
            last_percent = 0
            while True:
                if self._cancelled:
                    dd_proc.send_signal(signal.SIGINT)
                    break
                line = dd_proc.stderr.readline()
                if not line and dd_proc.poll() is not None:
                    break
                if line:
                    mb_match = re.search(r'(\d+)\s+bytes', line)
                    if mb_match:
                        bytes_done = int(mb_match.group(1))
                        percent = min(int(bytes_done / (1024 ** 3) * 100), 100)
                        if percent > last_percent + 5:
                            last_percent = percent
                            self._emit_progress(percent, self.tr("Writing... %d%%") % percent)
            dd_proc.wait(timeout=120)
            try:
                os.remove(test_file)
            except OSError:
                pass
            self._emit_progress(100, self.tr("Write benchmark complete"))
            self._emit_finished(self.device.device_node, "")
        except FileNotFoundError:
            self._emit_error(self.tr("dd not found"))
        except subprocess.TimeoutExpired:
            self._emit_error(self.tr("dd timed out"))
        except PermissionError:
            self._emit_error(self.tr("Permission denied writing to device"))
        except Exception as e:
            self._emit_error(f"dd: {e}")


class FioBenchmarkWorker(BaseTestWorker):
    """Runs fio sequential + 4K random tests with JSON output."""

    def run(self):
        if not self.device.mount_point:
            self._emit_error(self.tr("Device has no mount point"))
            return
        try:
            self._emit_progress(0, self.tr("Running fio benchmark..."))
            test_file = os.path.join(self.device.mount_point, ".fio_test_tmp")
            test_size = 256
            jobs = [
                {"name": "seqread", "rw": "read", "bs": "1M", "size": f"{test_size}M"},
                {"name": "seqwrite", "rw": "write", "bs": "1M", "size": f"{test_size}M"},
                {"name": "randread4k", "rw": "randread", "bs": "4k", "size": f"{test_size}M"},
                {"name": "randwrite4k", "rw": "randwrite", "bs": "4k", "size": f"{test_size}M"},
            ]
            all_results = []
            for i, job in enumerate(jobs):
                if self._cancelled:
                    break
                self._emit_progress(
                    int(i / len(jobs) * 100),
                    self.tr("fio: %s...") % job["name"],
                )
                cmd = [
                    find_tool("fio", "/usr/bin/fio"),
                    f"--name={job['name']}",
                    f"--rw={job['rw']}",
                    f"--bs={job['bs']}",
                    f"--size={job['size']}",
                    f"--numjobs=1",
                    f"--filename={test_file}",
                    "--direct=0",
                    "--group_reporting",
                    "--output-format=json",
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300
                )
                try:
                    data = json.loads(result.stdout)
                    job_result = data["jobs"][0]
                    all_results.append({
                        "job": job["name"],
                        "read": job_result.get("read", {}),
                        "write": job_result.get("write", {}),
                    })
                except (json.JSONDecodeError, KeyError, IndexError):
                    all_results.append({
                        "job": job["name"],
                        "raw_stdout": result.stdout[:500],
                        "raw_stderr": result.stderr[:500],
                    })
            try:
                os.remove(test_file)
            except OSError:
                pass
            parsed = self._format_fio_results(all_results)
            self._emit_progress(100, self.tr("fio benchmark complete"))
            self._emit_finished(self.device.device_node, parsed)
        except FileNotFoundError:
            self._emit_error(self.tr("fio not found"))
        except subprocess.TimeoutExpired:
            self._emit_error(self.tr("fio timed out"))
        except Exception as e:
            self._emit_error(f"fio: {e}")

    def _format_fio_results(self, results: list) -> str:
        lines = []
        for r in results:
            lines.append(f"=== {r['job']} ===")
            for direction in ("read", "write"):
                if direction in r and r[direction]:
                    d = r[direction]
                    bw = d.get("bw", 0)
                    iops = d.get("iops", 0)
                    lat = d.get("lat_ns", {}).get("mean", 0)
                    bw_mb = bw / 1024 if bw else 0
                    lines.append(
                        f"  {direction}: {bw_mb:.1f} MB/s, "
                        f"{iops:.0f} IOPS, latency {lat:.1f} ns"
                    )
            if "raw_stdout" in r:
                lines.append(f"  Raw: {r['raw_stdout'][:200]}")
        return "\n".join(lines)


class SmartHealthWorker(BaseTestWorker):
    """Runs smartctl -a via pkexec for device health diagnostics."""

    def run(self):
        try:
            self._emit_progress(0, self.tr("Running smartctl -a (requires root)..."))
            result = subprocess.run(
                [find_tool("pkexec", "/usr/bin/pkexec"),
                 find_tool("smartctl", "/usr/sbin/smartctl", "/sbin/smartctl"),
                 "-a", self.device.device_node],
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout + result.stderr
            if "smartctl" in output.lower() and "not supported" in output.lower():
                output += "\n" + self.tr("Note: SMART not supported on this device "
                                         "(typical for USB flash drives).")
            self._emit_progress(100, self.tr("SMART read complete"))
            self._emit_finished(self.device.device_node, output)
        except FileNotFoundError:
            self._emit_error(self.tr("pkexec not found"))
        except subprocess.TimeoutExpired:
            self._emit_error(self.tr("smartctl timed out"))
        except Exception as e:
            self._emit_error(f"smartctl: {e}")


class CombinedRootWorker(BaseTestWorker):
    """Runs both hdparm and smartctl in a single pkexec call."""

    def run(self):
        try:
            self._emit_progress(0, self.tr("Running hdparm + smartctl (requires root)..."))
            script = (
                f"{find_tool('hdparm', '/usr/sbin/hdparm', '/sbin/hdparm')}"
                f" -tT {self.device.device_node}\n"
                f"{find_tool('smartctl', '/usr/sbin/smartctl', '/sbin/smartctl')}"
                f" -a {self.device.device_node}"
            )
            result = subprocess.run(
                [find_tool("pkexec", "/usr/bin/pkexec"),
                 find_tool("bash", "/usr/bin/bash", "/bin/bash"),
                 "-c", script],
                capture_output=True,
                text=True,
                timeout=90,
            )
            output = result.stdout + result.stderr
            if "NOT_IOCTLABLE" in output:
                output += "\n" + self.tr("Warning: hdparm - device not accessible via ioctl.")
            if "smartctl" in output.lower() and "not supported" in output.lower():
                output += "\n" + self.tr("Note: SMART not supported on this device "
                                         "(typical for USB flash drives).")
            self._emit_progress(100, self.tr("Root tests complete"))
            self._emit_finished(self.device.device_node, output)
        except FileNotFoundError:
            self._emit_error(self.tr("pkexec not found. Install PolicyKit."))
        except subprocess.TimeoutExpired:
            self._emit_error(self.tr("Combined root tests timed out"))
        except Exception as e:
            self._emit_error(f"Combined root tests: {e}")


# ─── Hotplug Monitor ────────────────────────────────────
class DeviceMonitor(QThread):
    """Monitors USB hotplug events via pyudev."""

    device_added = pyqtSignal(object)
    device_removed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._context = pyudev.Context()
        self._monitor = pyudev.Monitor.from_netlink(self._context)
        self._monitor.filter_by(subsystem="block", device_type="partition")

    def run(self):
        observer = pyudev.MonitorObserver(
            self._monitor, self._on_event, name="monitor-observer"
        )
        observer.start()
        while self._running:
            QThread.msleep(500)
        observer.stop()

    def _on_event(self, action, device):
        if action == "add":
            dev = self._make_device(device)
            if dev:
                self.device_added.emit(dev)
        elif action == "remove":
            devnode = device.device_node or ""
            if devnode:
                self.device_removed.emit(devnode)

    def _make_device(self, device) -> Optional[USBDevice]:
        disk_node = re.sub(r"\d+$", "", device.device_node or "")
        if not disk_node:
            return None
        vendor = device.get("ID_VENDOR", "Unknown").strip()
        model = device.get("ID_MODEL", "").strip()
        product = f"{vendor} {model}".strip()
        size_bytes = int(device.get("SIZE", 0))
        size_gb = size_bytes / (1024 ** 3)
        mount_point = self._get_mount_point(disk_node)
        bus_speed, bus_type = self._get_speed(device)
        return USBDevice(
            device_node=disk_node,
            vendor=vendor,
            product=product,
            size_gb=size_gb,
            mount_point=mount_point,
            bus_speed=bus_speed,
            bus_type=bus_type,
            device_id=device.get("DEVPATH", "").split("/")[-1],
        )

    def _get_mount_point(self, disk_node: str) -> Optional[str]:
        for partition in psutil.disk_partitions():
            if partition.device.startswith(disk_node):
                return partition.mountpoint
        return None

    def _get_speed(self, device) -> tuple:
        sys_path = f"/sys/class/block/{device.device_node}"
        try:
            with open(f"{sys_path}/device/uevent") as f:
                for line in f:
                    if line.startswith("MODALIAS="):
                        modalias = line.strip().split("=", 1)[1]
                        if "usb" in modalias.lower():
                            break
        except Exception:
            pass
        try:
            with open(f"{sys_path}/device/speed") as f:
                speed = f.read().strip()
                if speed == "5000":
                    return "5000M", "USB 3.2 Gen 2"
                elif speed == "480":
                    return "480M", "USB 2.0"
                elif speed == "12":
                    return "12M", "USB 1.1"
        except Exception:
            pass
        try:
            with open(f"{sys_path}/device/max_speed") as f:
                speed = f.read().strip()
                if speed == "5000":
                    return "5000M", "USB 3.2 Gen 2"
                elif speed == "480":
                    return "480M", "USB 2.0"
        except Exception:
            pass
        return "Unknown", "Unknown"

    def stop(self):
        self._running = False


# ─── Rich Analysis View (Markdown + diagrams) ───────────
def load_diagram_image(path: str, scale: float = 1.0, file_scale: float = 1.0):
    """Decode a diagram into ``(QImage, logical_width, logical_height)``.

    The image is returned at *scale* times the layout size so it stays sharp on
    HiDPI screens, while the logical size stays what the document layout uses.

    * A ``.svg`` source is rasterised on the fly at that resolution.
    * A raster file authored at *file_scale* (a ``name@2x.png`` variant) is
      smoothly resampled only when its resolution differs from *scale*.

    ``QSvgRenderer`` is preferred over the Qt SVG image-format plugin because
    the latter is not guaranteed to be installed.
    """
    if not path or not os.path.exists(path):
        return QImage(), 0.0, 0.0

    if path.lower().endswith(".svg") and QSvgRenderer is not None:
        renderer = QSvgRenderer(path)
        if renderer.isValid():
            size = renderer.defaultSize()
            if size.isValid() and size.width() > 0 and size.height() > 0:
                width, height = float(size.width()), float(size.height())
                image = QImage(
                    max(1, round(width * scale)),
                    max(1, round(height * scale)),
                    QImage.Format.Format_ARGB32_Premultiplied,
                )
                image.fill(Qt.GlobalColor.transparent)
                painter = QPainter(image)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                renderer.render(painter)
                painter.end()
                return image, width, height

    image = QImage(path)
    if image.isNull():
        return QImage(), 0.0, 0.0
    file_scale = file_scale if file_scale > 0 else 1.0
    width = image.width() / file_scale
    height = image.height() / file_scale
    wanted = (max(1, round(width * scale)), max(1, round(height * scale)))
    if wanted != (image.width(), image.height()):
        image = image.scaled(
            wanted[0], wanted[1],
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return image, width, height


class AnalysisDocument(QTextDocument):
    """Text document that resolves the relative image paths used in Markdown.

    ``QTextBrowser`` on its own does not paint our diagrams, so the resource
    loader lives on the document; every decoded image is cached, at a
    resolution that follows the screen's device pixel ratio.

    The Markdown refers to the generated PNGs (``assets/png/name.png``). When
    several ``name@2x.png`` / ``name@3x.png`` variants exist, the smallest one
    that still covers the screen's pixel ratio is used — otherwise the image
    would be blown up and look soft. If no raster exists at all, the SVG source
    of the same name is rasterised instead.
    """

    _VARIANT_RE = re.compile(r"^(?P<stem>.+?)@(?P<scale>\d+(?:\.\d+)?)x$")

    def __init__(self, base_dir: str, parent=None, render_scale: float = 1.0):
        super().__init__(parent)
        self._base_dir = base_dir
        self._render_scale = max(1.0, float(render_scale))
        self._images: dict = {}
        self._logical: dict = {}
        self._variant_cache: dict = {}
        self.setBaseUrl(QUrl.fromLocalFile(base_dir + os.sep))

    def set_render_scale(self, scale: float) -> bool:
        """Follow a device-pixel-ratio change; True if the cache was dropped."""
        scale = max(1.0, float(scale))
        if abs(scale - self._render_scale) < 0.01:
            return False
        self._render_scale = scale
        self._images.clear()
        self._logical.clear()
        return True

    def _local_path(self, name) -> str:
        """Turn a document URL (absolute or relative) into a filesystem path."""
        text = name.toString() if isinstance(name, QUrl) else str(name)
        if text.startswith("file:"):
            path = QUrl(text).toLocalFile()
        elif text.startswith("/"):
            path = text
        else:
            path = os.path.join(self._base_dir, text)
        return os.path.normpath(path)

    def _variants(self, directory: str) -> dict:
        """``{stem: {scale: path}}`` for the ``stem@Nx.ext`` files in a folder."""
        if directory not in self._variant_cache:
            index: dict = {}
            try:
                names = os.listdir(directory)
            except OSError:
                names = []
            for name in names:
                stem, _ext = os.path.splitext(name)
                match = self._VARIANT_RE.match(stem)
                if match:
                    index.setdefault(match.group("stem"), {})[
                        float(match.group("scale"))
                    ] = os.path.join(directory, name)
                else:
                    index.setdefault(stem, {})[1.0] = os.path.join(directory, name)
            self._variant_cache[directory] = index
        return self._variant_cache[directory]

    def _resolve(self, path: str):
        """Pick the file to use for *path*; ``(file, file_scale)`` or ``None``."""
        directory, filename = os.path.split(path)
        stem, _ext = os.path.splitext(filename)
        variants = self._variants(directory).get(stem, {})
        if variants:
            available = sorted(variants)
            wide_enough = [s for s in available if s >= self._render_scale]
            scale = min(wide_enough) if wide_enough else max(available)
            return variants[scale], scale
        vector = os.path.join(DIAGRAMS_SVG_DIR, stem + ".svg")
        if os.path.exists(vector):
            return vector, 0.0
        return None, 0.0

    def image(self, name) -> QImage:
        """Return the decoded image for *name*, reading the file only once."""
        path = self._local_path(name)
        if path not in self._images:
            source, file_scale = self._resolve(path)
            if source is None:
                self._images[path] = QImage()
                self._logical[path] = (0.0, 0.0)
            else:
                image, width, height = load_diagram_image(
                    source, self._render_scale, file_scale
                )
                self._images[path] = image
                self._logical[path] = (width, height)
        return self._images[path]

    def logical_size(self, name):
        """Size of *name* in layout units (independent of the render scale)."""
        self.image(name)
        return self._logical.get(self._local_path(name), (0.0, 0.0))

    def loadResource(self, type_, name):
        if type_ == QTextDocument.ResourceType.ImageResource.value:
            image = self.image(name)
            if not image.isNull():
                return image
        return super().loadResource(type_, name)


class AnalysisView(QTextBrowser):
    """Read-only view that renders Markdown, including the tutorial images.

    Supports headings, lists, quotes, tables and images. Images are scaled to
    fit the viewport, or capped at *image_max_width* when one is given, so the
    tutorial can show its diagrams a little smaller than the full pane width.
    """

    def __init__(self, base_dir: str = APP_DIR, image_max_width: int = 0, parent=None):
        super().__init__(parent)
        self._markdown = ""
        self._fitting = False
        self._base_dir = base_dir
        self._image_max_width = image_max_width
        self._analysis_document = AnalysisDocument(
            base_dir, self, render_scale=self._screen_scale()
        )
        self.setDocument(self._analysis_document)
        self.setOpenExternalLinks(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFont(QFont("SansSerif", 10))

    @staticmethod
    def _screen_scale() -> float:
        """Device pixel ratio of the screen, so SVG diagrams stay sharp."""
        screen = QApplication.primaryScreen()
        return float(screen.devicePixelRatio()) if screen else 1.0

    # ── content ──────────────────────────────────────────
    def clear_analysis(self):
        """Drop the rendered Markdown and start a fresh document."""
        self._markdown = ""
        self._analysis_document.clear()
        self._analysis_document.setBaseUrl(QUrl.fromLocalFile(self._base_dir + os.sep))

    def set_markdown(self, text: str):
        """Replace the whole content, e.g. when loading the tutorial."""
        self._markdown = text
        self._analysis_document.setMarkdown(text)
        self._fit_images()
        self.verticalScrollBar().setValue(0)

    def append_markdown(self, text: str):
        """Append a Markdown block and re-render, keeping the reading position."""
        had_content = bool(self._markdown.strip())
        self._markdown = f"{self._markdown}\n\n{text}" if had_content else text
        scroll = self.verticalScrollBar()
        previous = scroll.value()
        was_at_bottom = previous >= scroll.maximum() - 4
        self._analysis_document.setMarkdown(self._markdown)
        self._fit_images()
        if not had_content:
            scroll.setValue(0)
        elif was_at_bottom:
            scroll.setValue(scroll.maximum())
        else:
            scroll.setValue(min(previous, scroll.maximum()))

    def markdown(self) -> str:
        return self._markdown

    # ── layout ───────────────────────────────────────────
    def showEvent(self, event):
        super().showEvent(event)
        self._fit_images()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_images()

    def _fit_images(self):
        """Scale every diagram so it never overflows the viewport width."""
        if self._fitting:
            return
        self._fitting = True
        try:
            if self._analysis_document.set_render_scale(self.devicePixelRatioF()):
                # Screen changed: re-rasterise the SVGs at the new pixel ratio.
                self._analysis_document.setMarkdown(self._markdown)
            available = max(self.viewport().width() - 30, 160)
            if self._image_max_width:
                available = min(available, self._image_max_width)
            cursor = QTextCursor(self._analysis_document)
            cursor.beginEditBlock()
            block = self._analysis_document.begin()
            while block.isValid():
                fragment = block.begin()
                while not fragment.atEnd():
                    piece = fragment.fragment()
                    if piece.isValid() and piece.charFormat().isImageFormat():
                        image_format = piece.charFormat().toImageFormat()
                        width, height = self._analysis_document.logical_size(
                            image_format.name()
                        )
                        if width > 0:
                            target_width = min(width, available)
                            target_height = height * target_width / width
                            if (abs(image_format.width() - target_width) > 0.5
                                    or abs(image_format.height() - target_height) > 0.5):
                                scaled = QTextImageFormat()
                                scaled.setName(image_format.name())
                                scaled.setWidth(target_width)
                                scaled.setHeight(target_height)
                                cursor.setPosition(piece.position())
                                cursor.setPosition(
                                    piece.position() + piece.length(),
                                    QTextCursor.MoveMode.KeepAnchor,
                                )
                                cursor.mergeCharFormat(scaled)
                    fragment += 1
                block = block.next()
            cursor.endEditBlock()
        finally:
            self._fitting = False


# ─── About dialog ───────────────────────────────────────
class AboutDialog(QDialog):
    """About box with the application icon on the left and the credits right.

    The e-mail address and the website are real links: ``setOpenExternalLinks``
    hands them to the desktop, so ``mailto:`` opens the system mail client and
    ``https://`` opens the default browser.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("About %s") % APP_NAME)
        self.setWindowIcon(app_icon())
        self.setModal(True)

        language = ui_language()

        icon_label = QLabel()
        icon_label.setPixmap(app_icon().pixmap(160, 160))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedWidth(190)
        icon_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        text_label = QLabel(about_html(language))
        text_label.setWordWrap(True)
        text_label.setTextFormat(Qt.TextFormat.RichText)
        text_label.setOpenExternalLinks(True)
        text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        text_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        text_label.setMinimumWidth(400)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)

        columns = QHBoxLayout()
        columns.setSpacing(18)
        columns.addWidget(icon_label)
        columns.addWidget(separator)
        columns.addWidget(text_label, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 14)
        layout.setSpacing(16)
        layout.addLayout(columns)
        layout.addWidget(buttons)


# ─── Main Window ────────────────────────────────────────
class MainWindow(QMainWindow):
    """Main application window for USB speed testing."""

    def __init__(self):
        super().__init__()
        self.devices: List[USBDevice] = []
        self.monitor = DeviceMonitor()
        self.active_worker: Optional[QThread] = None
        self._init_ui()
        self._connect_signals()
        self._refresh_devices()

    def _init_ui(self):
        self.setWindowTitle(self.tr(APP_NAME))
        self.setWindowIcon(app_icon())
        self.setMinimumSize(900, 700)
        self.resize(1100, 800)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Device selector
        device_layout = QHBoxLayout()
        device_layout.addWidget(QLabel(self.tr("Device:")))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(400)
        device_layout.addWidget(self.device_combo)
        self.refresh_btn = QPushButton(self.tr("Refresh"))
        self.refresh_btn.clicked.connect(self._refresh_devices)
        device_layout.addWidget(self.refresh_btn)
        layout.addLayout(device_layout)

        # Test selection: a collapsible panel so the checkboxes stay out of the
        # way until they are needed, with the About menu next to it.
        selectors = QHBoxLayout()
        self.tests_toggle = QToolButton()
        self.tests_toggle.setCheckable(True)
        self.tests_toggle.setChecked(False)
        self.tests_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.tests_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.tests_toggle.setAutoRaise(True)
        self.tests_toggle.toggled.connect(self._toggle_tests_panel)
        selectors.addWidget(self.tests_toggle)
        selectors.addStretch(1)

        self.about_button = QToolButton()
        self.about_button.setText(self.tr("About"))
        self.about_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.about_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        about_menu = QMenu(self.about_button)
        about_menu.addAction(self.tr("About %s...") % APP_NAME, self._show_about)
        about_menu.addAction(self.tr("About Qt..."), self._show_about_qt)
        self.about_button.setMenu(about_menu)
        selectors.addWidget(self.about_button)
        layout.addLayout(selectors)

        self.tests_panel = QWidget()
        test_layout = QVBoxLayout(self.tests_panel)
        test_layout.setContentsMargins(26, 0, 0, 0)
        test_layout.setSpacing(4)
        self.cb_bus = QCheckBox(self.tr("Bus Analysis (lsusb -t)"))
        self.cb_bus.setChecked(True)
        self.cb_read = QCheckBox(self.tr("Read Benchmark (hdparm -tT)"))
        self.cb_read.setChecked(True)
        self.cb_write = QCheckBox(self.tr("Write Benchmark (dd 1GB)"))
        self.cb_write.setChecked(True)
        self.cb_fio = QCheckBox(self.tr("Fio Benchmark (4K + Sequential)"))
        self.cb_fio.setChecked(True)
        self.cb_smart = QCheckBox(self.tr("SMART Health (smartctl -a)"))
        self.cb_smart.setChecked(True)
        self.test_checkboxes = (
            self.cb_bus, self.cb_read, self.cb_write, self.cb_fio, self.cb_smart,
        )
        for box in self.test_checkboxes:
            test_layout.addWidget(box)
            box.toggled.connect(self._update_tests_summary)
        self.tests_panel.setVisible(False)
        layout.addWidget(self.tests_panel)
        self._update_tests_summary()

        # Run button
        self.run_btn = QPushButton(self.tr("Run Selected Tests"))
        self.run_btn.clicked.connect(self._run_tests)
        layout.addWidget(self.run_btn)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        # Output tabs
        self.tabs = QTabWidget()
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Monospace", 9))
        self.analysis_edit = QTextEdit()
        self.analysis_edit.setReadOnly(True)
        self.analysis_edit.setFont(QFont("SansSerif", 10))
        self.explanations_view = AnalysisView(
            base_dir=tutorial_dir(), image_max_width=TUTORIAL_IMAGE_WIDTH
        )
        self.tabs.addTab(self.log_edit, self.tr("Technical Log"))
        self.tabs.addTab(self.analysis_edit, self.tr("User Analysis"))
        self.tabs.addTab(self.explanations_view, self.tr("Explanations"))
        layout.addWidget(self.tabs)

        # Status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage(self.tr("Ready"))

        self._load_tutorial()

    def _toggle_tests_panel(self, expanded: bool):
        """Show or hide the test checkboxes."""
        self.tests_panel.setVisible(expanded)
        self.tests_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    def _update_tests_summary(self):
        """Keep the collapsed label informative about the current selection."""
        enabled = sum(1 for box in self.test_checkboxes if box.isChecked())
        self.tests_toggle.setText(
            self.tr("Select tests (%d of %d enabled)")
            % (enabled, len(self.test_checkboxes))
        )

    def _show_about(self):
        AboutDialog(self).exec()

    def _show_about_qt(self):
        QMessageBox.aboutQt(self, self.tr("About Qt"))

    def _load_tutorial(self):
        """Load the tutorial Markdown for the current language into its tab."""
        path = os.path.join(tutorial_dir(), "tutorial.md")
        try:
            with open(path, encoding="utf-8") as handle:
                markdown = handle.read()
        except OSError as exc:
            markdown = self.tr("The tutorial could not be loaded: %s") % exc
        self.explanations_view.set_markdown(markdown)

    def _connect_signals(self):
        self.monitor.device_added.connect(self._on_device_added)
        self.monitor.device_removed.connect(self._on_device_removed)

    def _connect_worker(self, worker: BaseTestWorker):
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_test_finished)
        worker.error.connect(self._on_test_error)

    @pyqtSlot()
    def _refresh_devices(self):
        self.devices = self._detect_usb_devices()
        self.device_combo.clear()
        for dev in self.devices:
            self.device_combo.addItem(dev.display_name(), dev)
        self.status_bar.showMessage(
            self.tr("%d USB device(s) detected") % len(self.devices)
        )

    def _detect_usb_devices(self) -> List[USBDevice]:
        devices = []
        context = pyudev.Context()
        for device in context.list_devices(subsystem="block", DEVTYPE="partition"):
            if device.get("ID_BUS") != "usb":
                continue
            disk_node = re.sub(r"\d+$", "", device.device_node or "")
            if not disk_node:
                continue
            size_str = device.get("ID_FS_SIZE") or device.get("ID_PART_ENTRY_SIZE", "0")
            if "ID_PART_ENTRY_SIZE" in device:
                size_bytes = int(device.get("ID_PART_ENTRY_SIZE", "0")) * 512
            else:
                size_bytes = int(size_str)
            size_gb = size_bytes / (1024 ** 3)
            vendor = device.get("ID_VENDOR", "Unknown").strip()
            model = device.get("ID_MODEL", "").strip()
            product = model if model else vendor
            mount_point = self._get_mount_point(disk_node)
            bus_speed, bus_type = self._get_speed(disk_node)
            device_id = device.get("DEVPATH", "").split("/")[-1]
            dev = USBDevice(
                device_node=disk_node,
                vendor=vendor,
                product=product,
                size_gb=size_gb,
                mount_point=mount_point,
                bus_speed=bus_speed,
                bus_type=bus_type,
                device_id=device_id,
            )
            if dev not in devices:
                devices.append(dev)
        return devices

    def _get_mount_point(self, disk_node: str) -> Optional[str]:
        for partition in psutil.disk_partitions():
            if partition.device.startswith(disk_node):
                return partition.mountpoint
        return None

    def _get_speed(self, disk_node: str) -> tuple:
        try:
            block_name = disk_node.replace('/dev/', '')
            with open(f"/sys/block/{block_name}/device/speed") as f:
                speed = int(f.read().strip())
                if speed == 5000:
                    return "5000M", "USB 3.2 Gen 2"
                elif speed == 480:
                    return "480M", "USB 2.0"
                elif speed == 12:
                    return "12M", "USB 1.1"
        except Exception:
            pass
        try:
            block_name = disk_node.replace('/dev/', '')
            with open(f"/sys/block/{block_name}/device/max_speed") as f:
                speed = int(f.read().strip())
                if speed == 5000:
                    return "5000M", "USB 3.2 Gen 2"
                elif speed == 480:
                    return "480M", "USB 2.0"
        except Exception:
            pass
        try:
            context = pyudev.Context()
            for device in context.list_devices(subsystem="block", DEVTYPE="disk"):
                if device.device_node == disk_node:
                    for parent in device.ancestors:
                        if parent.subsystem == "usb" and parent.device_type == "usb_device":
                            path = parent.get("ID_PATH_WITH_USB_REVISION", "")
                            if "usbv3" in path or "usb3" in path:
                                return "5000M", "USB 3.2 Gen 1"
                            elif "usbv2" in path or "usb2" in path:
                                return "480M", "USB 2.0"
                            elif "usbv1" in path or "usb1" in path:
                                return "12M", "USB 1.1"
                            rev = parent.get("ID_USB_REVISION", "")
                            if rev in ("0300", "3.0", "3.1", "3.2"):
                                return "5000M", "USB 3.2 Gen 1"
                            elif rev in ("0200", "2.0", "2.1"):
                                return "480M", "USB 2.0"
                            elif rev in ("0100", "1.0", "1.1"):
                                return "12M", "USB 1.1"
        except Exception:
            pass
        return "Unknown", "Unknown"

    def _on_device_added(self, device: USBDevice):
        if not any(d.device_node == device.device_node for d in self.devices):
            self.devices.append(device)
            self.device_combo.addItem(device.display_name(), device)
            self.status_bar.showMessage(
                self.tr("Device added: %s") % device.display_name()
            )

    def _on_device_removed(self, devnode: str):
        self.devices = [d for d in self.devices if d.device_node != devnode]
        self.device_combo.clear()
        for dev in self.devices:
            self.device_combo.addItem(dev.display_name(), dev)
        self.status_bar.showMessage(
            self.tr("Device removed: %s") % devnode
        )

    @pyqtSlot(int, str)
    def _on_progress(self, percent: int, message: str):
        self.progress.setValue(percent)
        self.status_bar.showMessage(message)

    @pyqtSlot(str, str)
    def _on_test_finished(self, device_id: str, output: str):
        self.active_worker = None
        self.run_btn.setEnabled(True)
        self.progress.setValue(100)
        self.status_bar.showMessage(self.tr("Test complete"))
        self.log_edit.append(f"\n--- {self.tr('Result for')} {device_id} ---\n{output}")
        self._update_analysis(output)

    @pyqtSlot(str)
    def _on_test_error(self, message: str):
        self.active_worker = None
        self.run_btn.setEnabled(True)
        self.status_bar.showMessage(self.tr("Error"))
        QMessageBox.warning(self, self.tr("Test Error"), message)
        self.log_edit.append(f"\n--- {self.tr('Error')} ---\n{message}")

    def _run_tests(self):
        if self.active_worker:
            return
        device = self.device_combo.currentData()
        if not device:
            QMessageBox.information(self, self.tr("No Device"),
                                    self.tr("Please select a USB device"))
            return
        self.log_edit.clear()
        self.analysis_edit.clear()
        self.progress.setValue(0)
        tests = []
        if self.cb_bus.isChecked():
            tests.append(BusAnalysisWorker(device))
        
        # Combine hdparm + smartctl into single pkexec call if both selected
        read_checked = self.cb_read.isChecked()
        smart_checked = self.cb_smart.isChecked()
        if read_checked and smart_checked:
            tests.append(CombinedRootWorker(device))
        else:
            if read_checked:
                tests.append(ReadBenchmarkWorker(device))
            if smart_checked:
                tests.append(SmartHealthWorker(device))
        
        if self.cb_write.isChecked():
            tests.append(WriteBenchmarkWorker(device))
        if self.cb_fio.isChecked():
            tests.append(FioBenchmarkWorker(device))
        self._run_next_test(device, tests, 0)

    def _run_next_test(self, device: USBDevice, tests: list, index: int):
        if index >= len(tests):
            self.active_worker = None
            self.run_btn.setEnabled(True)
            self.progress.setValue(100)
            self.status_bar.showMessage(self.tr("All tests complete"))
            return
        worker = tests[index]
        self.active_worker = worker
        self._connect_worker(worker)
        worker.finished.connect(
            lambda did, out, idx=index, t=tests, d=device: self._run_next_test(d, t, idx + 1)
        )
        worker.error.connect(
            lambda msg, idx=index, t=tests, d=device: self._run_next_test(d, t, idx + 1)
        )
        worker.start()

    def _update_analysis(self, output: str):
        analysis = self._interpret_output(output)
        current = self.analysis_edit.toPlainText()
        self.analysis_edit.setText(current + "\n" + analysis)

    def _interpret_output(self, output: str) -> str:
        lines = []
        out_lower = output.lower()
        
        # hdparm analysis
        if "timing cached reads" in out_lower and "timing buffered disk reads" in out_lower:
            cached_match = re.search(r'Timing cached reads:.*?(\d+(?:\.\d+)?)\s*MB/s', output)
            real_match = re.search(r'Timing buffered disk reads:.*?(\d+(?:\.\d+)?)\s*MB/s', output)
            if cached_match and real_match:
                cached_val = float(cached_match.group(1))
                real_val = float(real_match.group(1))
                if real_val < 40:
                    lines.append(self.tr("Physical read speed is %.1f MB/s — typical for USB 2.0. "
                                         "If this is a USB 3.0 device, check the port/cable.") % real_val)
                elif real_val < 100:
                    lines.append(self.tr("Physical read speed is %.1f MB/s — consistent with USB 3.0 "
                                         "but limited by the flash chip (common for consumer drives).") % real_val)
                else:
                    lines.append(self.tr("Excellent physical read speed: %.1f MB/s — high-end USB 3.x device.") % real_val)

        # fio analysis
        if "seqread" in out_lower or "randread4k" in out_lower or "randwrite4k" in out_lower:
            read_bw = re.search(r'seqread.*?read:\s*([\d.]+)\s*MB/s', output, re.DOTALL)
            write_bw = re.search(r'seqwrite.*?write:\s*([\d.]+)\s*MB/s', output, re.DOTALL)
            rand_read_iops = re.search(r'randread4k.*?read:.*?(\d+)\s*IOPS', output, re.DOTALL)
            rand_write_iops = re.search(r'randwrite4k.*?write:.*?(\d+)\s*IOPS', output, re.DOTALL)
            
            if read_bw:
                bw = float(read_bw.group(1))
                if bw > 100:
                    lines.append(self.tr("Sequential read: %.1f MB/s — good USB 3.x performance.") % bw)
                elif bw > 30:
                    lines.append(self.tr("Sequential read: %.1f MB/s — USB 2.0 speeds detected.") % bw)
            if write_bw:
                bw = float(write_bw.group(1))
                lines.append(self.tr("Sequential write: %.1f MB/s — typical for USB flash (no DRAM cache).") % bw)
            if rand_read_iops:
                iops = int(rand_read_iops.group(1))
                if iops < 1000:
                    lines.append(self.tr("Random 4K read: %d IOPS — low, flash controller bottleneck.") % iops)
                else:
                    lines.append(self.tr("Random 4K read: %d IOPS — decent.") % iops)
            if rand_write_iops:
                iops = int(rand_write_iops.group(1))
                if iops < 500:
                    lines.append(self.tr("Random 4K write: %d IOPS — very low, typical for cheap flash.") % iops)
                else:
                    lines.append(self.tr("Random 4K write: %d IOPS — acceptable.") % iops)

        # smartctl analysis
        if "smartctl" in out_lower:
            if "unknown usb bridge" in out_lower or "not supported" in out_lower:
                lines.append(self.tr("SMART not supported via USB bridge — normal for flash drives. "
                                     "Use vendor tools for health info."))
            elif "reallocated" in out_lower or "pending" in out_lower:
                lines.append(self.tr("Warning: Reallocated/pending sectors — backup data immediately."))
            elif "passed" in out_lower or "healthy" in out_lower:
                lines.append(self.tr("SMART health check passed."))

        # lsusb analysis
        if "mass storage" in out_lower:
            if "5000M" in output:
                lines.append(self.tr("USB 3.x link negotiated (5000M) — device connected at SuperSpeed."))
            elif "480M" in output:
                lines.append(self.tr("USB 2.0 link only (480M) — check port, cable, or device compatibility."))
            else:
                lines.append(self.tr("USB mass storage detected but link speed unknown."))

        if not lines:
            lines.append(self.tr("No specific analysis available. Check the Technical Log for details."))
        return "\n".join(lines)

    def closeEvent(self, event):
        self.monitor.stop()
        if self.active_worker:
            self.active_worker.cancel()
            self.active_worker.wait(3000)
        event.accept()


# ─── Application Entry ──────────────────────────────────
def main(argv=None):
    """Application entry point."""
    argv = list(sys.argv if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog=PACKAGE_NAME,
        description=f"{APP_NAME} - analyse, benchmark and diagnose USB "
                    "storage devices on Linux.",
    )
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {APP_VERSION}")
    parser.parse_args(argv[1:])

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setDesktopFileName("io.github.wachin.USBSpeedTester")
    app.setWindowIcon(app_icon())
    TranslationManager.install(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
