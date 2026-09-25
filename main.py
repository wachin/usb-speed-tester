#!/usr/bin/env python3
"""
USB Speed Tester - PyQt6 Application
Bus analysis, benchmarking, and diagnostics for USB storage devices.
All code and comments in English. Spanish translations via QTranslator.
"""

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
    QComboBox, QPushButton, QCheckBox, QTextEdit, QProgressBar,
    QTabWidget, QGroupBox, QLabel, QLineEdit, QMessageBox,
    QHeaderView, QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QSplitter, QFrame, QSizePolicy, QFileDialog,
)
from PyQt6.QtCore import (
    QThread, pyqtSignal, pyqtSlot, QObject, QCoreApplication,
    QTranslator, QLocale, QLibraryInfo, QTimer, Qt,
)
from PyQt6.QtGui import QFont, QTextCursor, QIcon, QAction


# ─── i18n ───────────────────────────────────────────────
class TranslationManager:
    """Manages application translations via QTranslator."""

    @staticmethod
    def install(app: QApplication) -> bool:
        translator = QTranslator()
        locale = QLocale.system().name()
        qm_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "translations",
            f"usbtester_{locale}.qm",
        )
        if os.path.exists(qm_path) and translator.load(qm_path):
            app.installTranslator(translator)
            return True
        return False


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
                ["/usr/bin/lsusb", "-t"],
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
                ["pkexec", "/sbin/hdparm", "-tT", self.device.device_node],
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
                    "/bin/dd", "if=/dev/zero", f"of={test_file}",
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
                    "/usr/bin/fio",
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
                ["pkexec", "/sbin/smartctl", "-a", self.device.device_node],
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
        self.setWindowTitle(self.tr("USB Speed Tester"))
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

        # Test selection
        test_group = QGroupBox(self.tr("Select Tests"))
        test_layout = QVBoxLayout()
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
        test_layout.addWidget(self.cb_bus)
        test_layout.addWidget(self.cb_read)
        test_layout.addWidget(self.cb_write)
        test_layout.addWidget(self.cb_fio)
        test_layout.addWidget(self.cb_smart)
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)

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
        self.tabs.addTab(self.log_edit, self.tr("Technical Log"))
        self.tabs.addTab(self.analysis_edit, self.tr("User Analysis"))
        layout.addWidget(self.tabs)

        # Status bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage(self.tr("Ready"))

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
        if self.cb_read.isChecked():
            tests.append(ReadBenchmarkWorker(device))
        if self.cb_write.isChecked():
            tests.append(WriteBenchmarkWorker(device))
        if self.cb_fio.isChecked():
            tests.append(FioBenchmarkWorker(device))
        if self.cb_smart.isChecked():
            tests.append(SmartHealthWorker(device))
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
        if "hdparm" in output.lower():
            cached_match = re.search(r'Timing buffered.*?\((\d+)\s*MB/s', output)
            cached = cached_match.group(1) if cached_match else None
            real_match = re.search(r'Timing buffered.*?(\d+)\s*MB/s', output)
            real_speed = real_match.group(1) if real_match else None
            if cached and real_speed:
                cached_val = int(cached)
                real_val = int(real_speed)
                if real_val < cached_val * 0.5:
                    lines.append(self.tr("Write speed is much slower than cached read. "
                                         "The flash chip is limiting write throughput. "
                                         "This is normal for USB flash drives."))
                else:
                    lines.append(self.tr("Write speed is reasonable compared to cached read."))
        if "smartctl" in output.lower():
            if "reallocated" in output.lower():
                lines.append(self.tr("Warning: Reallocated sectors detected. "
                                     "The device is degrading. Backup your data."))
            if "pending" in output.lower():
                lines.append(self.tr("Warning: Pending sectors detected. "
                                     "The drive may be failing soon."))
        if "fio" in output.lower():
            iops_match = re.search(r'(\d+)\s*IOPS', output)
            if iops_match:
                iops = int(iops_match.group(1))
                if iops < 1000:
                    lines.append(self.tr("Low IOPS detected (%d). "
                                         "The flash controller may be slow or the USB bus is bottlenecked.") % iops)
                else:
                    lines.append(self.tr("Good IOPS performance."))
        if "lsusb" in output.lower():
            if "5000M" in output:
                lines.append(self.tr("USB 3.x speed negotiated successfully."))
            elif "480M" in output:
                lines.append(self.tr("USB 2.0 speed detected. "
                                     "Check cable/port for USB 3.x compatibility."))
        if not lines:
            lines.append(self.tr("No specific analysis available. "
                                 "Check the Technical Log for details."))
        return "\n".join(lines)

    def closeEvent(self, event):
        self.monitor.stop()
        if self.active_worker:
            self.active_worker.cancel()
            self.active_worker.wait(3000)
        event.accept()


# ─── Application Entry ──────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("USB Speed Tester")
    TranslationManager.install(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
