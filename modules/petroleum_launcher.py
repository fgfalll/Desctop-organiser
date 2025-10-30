"""MODULE_MANIFEST_START
{
  "name": "petroleum_launcher",
  "version": "1.0.0",
  "description": "Petroleum program launcher with automation capabilities and multi-monitor support",
  "author": "Desktop Organizer Team",
  "category": "Utility",
  "menu_text": "Petroleum Program Launcher...",
  "main_class": "PetroleumLauncherWidget",
  "dependencies": [
    "pywin32>=227"
  ],
  "python_version": "3.8+",
  "permissions": [
    "file_system_read",
    "file_system_write",
    "process_control",
    "system_info"
  ]
}
MODULE_MANIFEST_END"""

import sys
import os
import json
import logging
import subprocess
import threading
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import zipfile
import tempfile
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QTextEdit, QSplitter,
    QGroupBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QLineEdit, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox, QProgressBar, QFrame,
    QScrollArea, QGridLayout, QDialog, QDialogButtonBox,
    QFormLayout, QSpinBox, QDoubleSpinBox, QSlider, QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, pyqtSlot, QEvent
from PyQt5.QtGui import QIcon, QFont, QPixmap

# Try to import Windows-specific modules
try:
    import win32api
    import win32con
    import win32gui
    import win32process
    import winreg
    import re
    WINDOWS_SUPPORT = True
except ImportError:
    WINDOWS_SUPPORT = False
    print("Warning: pywin32 not available. Some features may be limited.")

# Set up logging
logger = logging.getLogger('PetroleumLauncher')


# Petroleum program configuration adapted from program_install.py
PETROLEUM_PROGRAM_CONFIG = {
    "petrel": {
        "display_name": "Petrel Platform",
        "target_version": "latest",
        "identity": {
            "expected_product_names": ["Petrel", "Petrel Platform", "Schlumberger Petrel"],
            "expected_descriptions": ["Petrel Setup", "Petrel Platform Installer", "Petrel E&P Software Platform"],
            "installer_patterns": ["Petrel*Setup*.exe", "SLB.Petrel*.exe", "PetrelPlatformInstaller.exe"],
        },
        "check_method": {
            "type": "registry",
            "keys": [
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"Petrel.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"Petrel.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\Schlumberger\Petrel", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\Schlumberger\Petrel", "check_existence": True},
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Petrel.exe", "check_existence": True},
            ],
        },
    },
    "pipesim": {
        "display_name": "PIPESIM",
        "target_version": "latest",
        "identity": {
            "expected_product_names": ["Pipesim", "Schlumberger PIPESIM"],
            "expected_descriptions": ["Pipesim Setup", "PIPESIM *", "PIPESIM Suite"],
            "installer_patterns": ["setup.exe", "PIPESIM*.exe", "SLB.PIPESIM*.exe"],
        },
        "check_method": {
            "type": "registry",
            "keys": [
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"PIPESIM .*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"PIPESIM .*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\Schlumberger\PIPESIM", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\Schlumberger\PIPESIM", "check_existence": True},
            ],
        },
    },
    "olga": {
        "display_name": "OLGA",
        "target_version": "latest",
        "identity": {
            "expected_product_names": ["OLGA", "Schlumberger OLGA", "OLGA Multiphase Flow Simulator"],
            "expected_descriptions": ["OLGA Setup", "OLGA Installer", "olga"],
            "installer_patterns": ["Setup-OLGA*.exe", "OLGA*Setup*.exe", "SLB.OLGA*.exe"],
        },
        "check_method": {
            "type": "registry",
            "keys": [
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r".*OLGA.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r".*OLGA.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\Schlumberger\OLGA", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\Schlumberger\OLGA", "check_existence": True},
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\OLGA.exe", "check_existence": True},
            ],
        },
    },
    "techlog": {
        "display_name": "Techlog",
        "target_version": "latest",
        "identity": {
            "expected_product_names": ["Techlog", "Schlumberger Techlog", "Techlog Wellbore Software"],
            "expected_descriptions": ["Techlog Setup", "install Techlog", "Techlog"],
            "installer_patterns": ["Install Techlog*", "Techlog*Setup*.exe", "SLB.Techlog*.exe"],
        },
        "check_method": {
            "type": "registry",
            "keys": [
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"Techlog.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"Techlog.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\Schlumberger\Techlog", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\Schlumberger\Techlog", "check_existence": True},
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Techlog.exe", "check_existence": True},
            ],
        },
    },
    "eclipse": {
        "display_name": "Eclipse Reservoir Simulator",
        "target_version": "latest",
        "identity": {
            "expected_product_names": ["Eclipse", "Eclipse Simulation", "Schlumberger Eclipse"],
            "expected_descriptions": ["Eclipse Setup", "Eclipse Simulation Installer", "Schlumberger Eclipse Reservoir Simulator"],
            "installer_patterns": ["Eclipse*.exe", "Eclipse*Setup*.exe", "SLB.Eclipse*.exe"],
        },
        "check_method": {
            "type": "registry",
            "keys": [
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r".*Eclipse.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r".*Eclipse.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\Schlumberger\Eclipse", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\Schlumberger\Eclipse", "check_existence": True},
            ],
        },
    },
}


class WindowsUtils:
    """Windows utility functions adapted from program_install.py"""

    @staticmethod
    def _reg_read_string(hive: int, key_path: str, value_name: Optional[str] = None) -> Optional[str]:
        """Read a string value from the Windows Registry."""
        if not WINDOWS_SUPPORT:
            return None

        try:
            with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                if value_name:
                    reg_type, value = winreg.QueryValueEx(key, value_name)
                    if reg_type in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                        return str(value).strip()
                    else:
                        logger.debug(f"Reg value '{value_name}' at '{key_path}' is not a string type (Type: {reg_type}).")
                        return None
                else:
                    # Read the default value
                    reg_type, value = winreg.QueryValueEx(key, None)
                    if reg_type in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                        return str(value).strip()
                    else:
                        return None
        except FileNotFoundError:
            logger.debug(f"Reg value '{value_name}' not found at '{key_path}'.")
            return None
        except OSError as e:
            logger.warning(f"OS Error reading reg value '{value_name}' at '{key_path}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading reg value '{value_name}' at '{key_path}': {e}")
            return None

    @staticmethod
    def check_registry(check_config: List[Dict]) -> Tuple[bool, Optional[str]]:
        """Check registry based on a list of rules. Returns (found, version_string)."""
        if not WINDOWS_SUPPORT:
            return False, None

        hkey_map = {'HKLM': winreg.HKEY_LOCAL_MACHINE, 'HKCU': winreg.HKEY_CURRENT_USER}
        found_globally = False
        first_found_version: Optional[str] = None

        for rule in check_config:
            key_path: Optional[str] = rule.get("path")
            base_hive_str: str = rule.get("hive", "HKLM")
            base_hive: int = hkey_map.get(base_hive_str, winreg.HKEY_LOCAL_MACHINE)

            match_value: Optional[str] = rule.get("match_value")
            match_pattern: Optional[str] = rule.get("match_pattern")
            check_existence: bool = rule.get("check_existence", False)
            get_value: Optional[str] = rule.get("get_value")

            if not key_path:
                logger.warning(f"Skipping invalid registry rule (no path): {rule}")
                continue

            logger.debug(f"Checking Reg Rule: Hive={base_hive_str}, Path='{key_path}', Match='{match_value}/{match_pattern}', Exist={check_existence}, Get='{get_value}'")

            try:
                if check_existence:
                    try:
                        with winreg.OpenKey(base_hive, key_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
                            logger.debug(f"Reg Check SUCCESS (Existence): Key '{key_path}' exists.")
                            found_globally = True
                            found_version = WindowsUtils._reg_read_string(base_hive, key_path, get_value)
                            if found_version and first_found_version is None:
                                first_found_version = found_version
                                logger.debug(f"  -> Retrieved version: '{found_version}'")
                    except FileNotFoundError:
                        logger.debug(f"Reg Check FAIL (Existence): Key '{key_path}' not found.")
                        continue

                elif match_value and match_pattern:
                    try:
                        with winreg.OpenKey(base_hive, key_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                            subkey_index = 0
                            while True:
                                try:
                                    subkey_name = winreg.EnumKey(key, subkey_index)
                                    subkey_full_path = f"{key_path}\\{subkey_name}"
                                    logger.debug(f"  Checking subkey: '{subkey_full_path}'")
                                    value_to_match = WindowsUtils._reg_read_string(base_hive, subkey_full_path, match_value)

                                    if value_to_match:
                                        logger.debug(f"    Value '{match_value}' = '{value_to_match}'")
                                        if re.match(match_pattern, value_to_match, re.IGNORECASE):
                                            logger.debug(f"Reg Check SUCCESS (Match): Pattern '{match_pattern}' matched '{value_to_match}' in '{subkey_full_path}'.")
                                            found_globally = True
                                            found_version = WindowsUtils._reg_read_string(base_hive, subkey_full_path, get_value)
                                            if found_version and first_found_version is None:
                                                first_found_version = found_version
                                                logger.debug(f"    -> Retrieved version: '{found_version}'")
                                    subkey_index += 1
                                except OSError:
                                    break
                                except Exception as subkey_e:
                                    logger.warning(f"Error processing subkey {subkey_name} under {key_path}: {subkey_e}")
                                    subkey_index += 1
                    except FileNotFoundError:
                        logger.debug(f"Reg Check: Base path '{key_path}' for subkey iteration not found.")
                        continue

            except Exception as e:
                logger.error(f"Unexpected error during registry check for rule {rule}: {e}")

        return found_globally, first_found_version

    @staticmethod
    def find_executable_path(program_key: str) -> Optional[str]:
        """Find the executable path for a program using App Paths registry entries."""
        if not WINDOWS_SUPPORT:
            return None

        app_paths_to_check = [
            f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{program_key}.exe",
            f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{program_key}.EXE"
        ]

        for app_path in app_paths_to_check:
            for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                try:
                    with winreg.OpenKey(hive, app_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                        # Try to read the default value first
                        try:
                            reg_type, value = winreg.QueryValueEx(key, None)
                            if reg_type == winreg.REG_SZ:
                                path = str(value).strip()
                                if os.path.exists(path):
                                    logger.debug(f"Found executable via App Paths: {path}")
                                    return path
                        except FileNotFoundError:
                            pass

                        # Try reading the "Path" value
                        try:
                            reg_type, value = winreg.QueryValueEx(key, "Path")
                            if reg_type == winreg.REG_SZ:
                                path = str(value).strip()
                                exe_path = os.path.join(path, f"{program_key}.exe")
                                if os.path.exists(exe_path):
                                    logger.debug(f"Found executable via App Paths Path: {exe_path}")
                                    return exe_path
                        except FileNotFoundError:
                            pass

                except FileNotFoundError:
                    continue
                except Exception as e:
                    logger.debug(f"Error checking App Path {app_path} in hive {hive}: {e}")
                    continue

        return None

    @staticmethod
    def check_path_exists(path_pattern: str) -> bool:
        """Check if a path exists, supporting environment variables."""
        if not WINDOWS_SUPPORT:
            return False

        try:
            # Expand environment variables
            expanded_path = os.path.expandvars(path_pattern)
            return os.path.exists(expanded_path)
        except Exception as e:
            logger.error(f"Error checking path '{path_pattern}': {e}")
            return False


@dataclass
class ProgramInfo:
    """Information about a detected petroleum program"""
    name: str
    display_name: str
    executable_path: str
    version: str
    install_path: str
    detected: bool = False
    last_check: str = ""
    install_error: Optional[str] = None


@dataclass
class AutomationStep:
    """Single step in an automation workflow"""
    step_type: str  # "launch_program", "open_file", "wait", "run_command"
    program_name: str = ""
    file_path: str = ""
    command: str = ""
    parameters: Dict[str, Any] = None
    wait_time: int = 0
    window_position: Dict[str, int] = None
    description: str = ""

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if self.window_position is None:
            self.window_position = {}


@dataclass
class Workflow:
    """Complete automation workflow"""
    name: str
    description: str
    steps: List[AutomationStep]
    created_date: str
    modified_date: str
    author: str = ""
    version: str = "1.0"

    def __post_init__(self):
        if not self.created_date:
            self.created_date = datetime.now().isoformat()
        if not self.modified_date:
            self.modified_date = datetime.now().isoformat()


class WindowManager:
    """Manages multi-monitor detection and window positioning"""

    def __init__(self):
        self.monitors = []
        self.primary_monitor = None
        self.detect_monitors()

    def detect_monitors(self) -> List[Dict[str, Any]]:
        """Detect connected monitors and their properties"""
        self.monitors = []

        if not WINDOWS_SUPPORT:
            # Fallback for non-Windows systems
            self.monitors.append({
                'index': 0,
                'is_primary': True,
                'left': 0,
                'top': 0,
                'width': 1920,
                'height': 1080,
                'dpi': 96
            })
            self.primary_monitor = self.monitors[0]
            return self.monitors

        try:
            # Get monitor information
            monitor_info = win32api.GetMonitorInfo(win32api.MonitorFromPoint((0, 0)))

            # Get all monitors
            def callback(hmonitor, hdc, rect, data):
                info = win32api.GetMonitorInfo(hmonitor)
                monitor = {
                    'index': len(self.monitors),
                    'is_primary': info['flags'] & win32api.MONITORINFOF_PRIMARY != 0,
                    'left': info['Monitor'][0],
                    'top': info['Monitor'][1],
                    'width': info['Monitor'][2] - info['Monitor'][0],
                    'height': info['Monitor'][3] - info['Monitor'][1],
                    'work_left': info['Work'][0],
                    'work_top': info['Work'][1],
                    'work_width': info['Work'][2] - info['Work'][0],
                    'work_height': info['Work'][3] - info['Work'][1]
                }

                if monitor['is_primary']:
                    self.primary_monitor = monitor

                self.monitors.append(monitor)
                return True

            win32api.EnumDisplayMonitors(None, None, callback, None)

        except Exception as e:
            logger.error(f"Error detecting monitors: {e}")
            # Fallback to single monitor
            self.monitors.append({
                'index': 0,
                'is_primary': True,
                'left': 0,
                'top': 0,
                'width': 1920,
                'height': 1080,
                'dpi': 96
            })
            self.primary_monitor = self.monitors[0]

        return self.monitors

    def get_optimal_position(self, program_name: str = "", prefer_secondary: bool = False) -> Dict[str, int]:
        """Get optimal window position for a program"""
        if len(self.monitors) == 1:
            # Single monitor setup
            monitor = self.monitors[0]
            return {
                'left': monitor['work_left'] + 50,
                'top': monitor['work_top'] + 50,
                'width': min(1200, monitor['work_width'] - 100),
                'height': min(800, monitor['work_height'] - 100)
            }

        # Multi-monitor setup
        if prefer_secondary and len(self.monitors) > 1:
            # Use secondary monitor
            monitor = next((m for m in self.monitors if not m['is_primary']), self.monitors[0])
        else:
            # Use primary monitor
            monitor = self.primary_monitor or self.monitors[0]

        return {
            'left': monitor['work_left'] + 50,
            'top': monitor['work_top'] + 50,
            'width': min(1200, monitor['work_width'] - 100),
            'height': min(800, monitor['work_height'] - 100)
        }

    def get_monitor_info(self) -> List[Dict[str, Any]]:
        """Get information about all detected monitors"""
        return self.monitors.copy()


class AutomationEngine(QThread):
    """Executes automation workflows"""

    progress_updated = pyqtSignal(int, str)
    step_completed = pyqtSignal(int, str, bool)
    workflow_completed = pyqtSignal(bool, str)

    def __init__(self, workflow: Workflow, main_widget=None):
        super().__init__()
        self.workflow = workflow
        self.main_widget = main_widget
        self.current_step = 0
        self.is_running = False
        self.window_manager = WindowManager()

    def run(self):
        """Execute the automation workflow"""
        self.is_running = True
        self.current_step = 0

        try:
            for i, step in enumerate(self.workflow.steps):
                if not self.is_running:
                    break

                self.current_step = i
                progress = int((i / len(self.workflow.steps)) * 100)
                self.progress_updated.emit(progress, f"Executing: {step.description}")

                success = self._execute_step(step)
                self.step_completed.emit(i, step.description, success)

                if not success:
                    self.workflow_completed.emit(False, f"Step failed: {step.description}")
                    return

            self.workflow_completed.emit(True, "Workflow completed successfully")

        except Exception as e:
            logger.error(f"Error executing workflow: {e}")
            self.workflow_completed.emit(False, f"Error: {str(e)}")

        self.is_running = False

    def _execute_step(self, step: AutomationStep) -> bool:
        """Execute a single automation step"""
        try:
            if step.step_type == "launch_program":
                return self._launch_program(step)
            elif step.step_type == "open_file":
                return self._open_file(step)
            elif step.step_type == "wait":
                return self._wait(step)
            elif step.step_type == "run_command":
                return self._run_command(step)
            else:
                logger.warning(f"Unknown step type: {step.step_type}")
                return True

        except Exception as e:
            logger.error(f"Error executing step {step.step_type}: {e}")
            return False

    def _launch_program(self, step: AutomationStep) -> bool:
        """Launch a program with optional parameters"""
        try:
            # Get the main widget to access program detection results
            if not self.main_widget or not hasattr(self.main_widget, 'detected_programs'):
                logger.error("Cannot access program information for launching")
                return False

            program_info = self.main_widget.detected_programs.get(step.program_name)
            if not program_info:
                logger.error(f"Program not found: {step.program_name}")
                return False

            if not program_info.detected:
                logger.error(f"Program not installed: {program_info.display_name}")
                return False

            if not program_info.executable_path:
                logger.error(f"No executable path for: {program_info.display_name}")
                return False

            if not os.path.exists(program_info.executable_path):
                logger.error(f"Executable not found: {program_info.executable_path}")
                return False

            # Build launch command
            launch_args = [program_info.executable_path]

            # Add any parameters from the step
            if hasattr(step, 'parameters') and step.parameters:
                # Add command line parameters
                for param_key, param_value in step.parameters.items():
                    if param_key.startswith('cmd_'):
                        launch_args.append(str(param_value))

            # Handle file opening
            if step.file_path:
                if os.path.exists(step.file_path):
                    launch_args.append(step.file_path)
                else:
                    logger.warning(f"File not found for launch: {step.file_path}")

            # Launch the program
            logger.info(f"Launching {program_info.display_name}: {' '.join(launch_args)}")

            # Set window position if specified and on Windows
            if step.window_position and WINDOWS_SUPPORT:
                # This is a placeholder - actual window positioning would be more complex
                # and might require finding the process window after launch
                logger.debug(f"Window position requested: {step.window_position}")

            # Launch the process
            process = subprocess.Popen(
                launch_args,
                cwd=program_info.install_path if program_info.install_path else None,
                shell=False
            )

            # Give the process time to start
            time.sleep(2)

            # Check if process is still running
            if process.poll() is None:
                logger.info(f"Successfully launched {program_info.display_name} (PID: {process.pid})")
                return True
            else:
                logger.error(f"Program exited immediately: {program_info.display_name} (Exit code: {process.returncode})")
                return False

        except Exception as e:
            logger.error(f"Error launching program {step.program_name}: {e}")
            return False

    def _open_file(self, step: AutomationStep) -> bool:
        """Open a file with the default or specified program"""
        if not os.path.exists(step.file_path):
            logger.error(f"File not found: {step.file_path}")
            return False

        try:
            if WINDOWS_SUPPORT:
                os.startfile(step.file_path)
            else:
                opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
                subprocess.call([opener, step.file_path])
            return True
        except Exception as e:
            logger.error(f"Error opening file {step.file_path}: {e}")
            return False

    def _wait(self, step: AutomationStep) -> bool:
        """Wait for specified time"""
        self.msleep(step.wait_time * 1000)
        return True

    def _run_command(self, step: AutomationStep) -> bool:
        """Execute a system command"""
        try:
            result = subprocess.run(
                step.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=step.parameters.get('timeout', 30)
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.error(f"Command timeout: {step.command}")
            return False
        except Exception as e:
            logger.error(f"Error running command: {e}")
            return False

    def stop(self):
        """Stop the automation execution"""
        self.is_running = False


class PetroleumLauncherWidget(QWidget):
    """Main widget for the Petroleum Program Launcher module"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.window_manager = WindowManager()
        self.detected_programs: Dict[str, ProgramInfo] = {}
        self.workflows: Dict[str, Workflow] = {}
        self.automation_engine: Optional[AutomationEngine] = None

        # Initialize UI first
        self.initUI()

        # Apply responsive scaling
        self.apply_responsive_scaling()

        # Load saved data after UI is created
        self.load_configuration()

        # Detect programs after UI is ready
        QTimer.singleShot(1000, self.detect_programs)

    def initUI(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)

        # Create main splitter
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # Left panel - Programs and Workflows
        left_panel = self.create_left_panel()
        splitter.addWidget(left_panel)

        # Right panel - Details and Controls
        right_panel = self.create_right_panel()
        splitter.addWidget(right_panel)

        # Set splitter proportions
        splitter.setSizes([400, 600])

        # Set window properties
        self.setWindowTitle("Petroleum Program Launcher")
        # Remove fixed size to allow auto-scaling, use minimum size instead
        self.setMinimumSize(800, 600)

        # Enable auto-scaling
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Calculate initial scale based on parent window size
        if self.parent():
            parent_size = self.parent().size()
            self.resize(parent_size.width() - 50, parent_size.height() - 100)
        else:
            self.resize(1000, 700)

        # Status bar at bottom
        status_layout = QHBoxLayout()

        self.status_label = QLabel("Ready")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        self.monitor_info_label = QLabel(self.get_monitor_status_text())
        status_layout.addWidget(self.monitor_info_label)

        layout.addLayout(status_layout)

        # Set stretch factors for responsive layout
        splitter.setStretchFactor(0, 1)  # Left panel
        splitter.setStretchFactor(1, 2)  # Right panel

        # Store original splitter sizes for proportional resizing
        self.splitter_original_sizes = [400, 600]
        self.splitter = splitter  # Store reference for resize handling

    def create_left_panel(self) -> QWidget:
        """Create the left panel with programs and workflows"""
        left_panel = QWidget()
        layout = QVBoxLayout(left_panel)

        # Tab widget for Programs and Workflows
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Programs tab
        programs_tab = self.create_programs_tab()
        self.tab_widget.addTab(programs_tab, "Programs")

        # Workflows tab
        workflows_tab = self.create_workflows_tab()
        self.tab_widget.addTab(workflows_tab, "Workflows")

        return left_panel

    def create_programs_tab(self) -> QWidget:
        """Create the programs tab"""
        programs_tab = QWidget()
        layout = QVBoxLayout(programs_tab)

        # Refresh button
        refresh_btn = QPushButton("Refresh Programs")
        refresh_btn.clicked.connect(self.detect_programs)
        layout.addWidget(refresh_btn)

        # Programs tree
        self.programs_tree = QTreeWidget()
        self.programs_tree.setHeaderLabels(["Program", "Version", "Status"])
        self.programs_tree.itemDoubleClicked.connect(self.on_program_double_click)

        # Set column widths for better responsive behavior
        self.programs_tree.setColumnWidth(0, 150)  # Program name
        self.programs_tree.setColumnWidth(1, 100)  # Version
        self.programs_tree.setColumnWidth(2, 80)   # Status

        # Set size policy for responsiveness
        self.programs_tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.programs_tree.header().setStretchLastSection(True)

        layout.addWidget(self.programs_tree)

        # Launch selected button
        launch_btn = QPushButton("Launch Selected")
        launch_btn.clicked.connect(self.launch_selected_program)
        layout.addWidget(launch_btn)

        return programs_tab

    def create_workflows_tab(self) -> QWidget:
        """Create the workflows tab"""
        workflows_tab = QWidget()
        layout = QVBoxLayout(workflows_tab)

        # Workflow buttons
        buttons_layout = QHBoxLayout()

        new_workflow_btn = QPushButton("New Workflow")
        new_workflow_btn.clicked.connect(self.create_new_workflow)
        buttons_layout.addWidget(new_workflow_btn)

        import_workflow_btn = QPushButton("Import Package")
        import_workflow_btn.clicked.connect(self.import_package)
        buttons_layout.addWidget(import_workflow_btn)

        layout.addLayout(buttons_layout)

        # Workflows list
        self.workflows_tree = QTreeWidget()
        self.workflows_tree.setHeaderLabels(["Workflow", "Description", "Modified"])
        self.workflows_tree.itemDoubleClicked.connect(self.on_workflow_double_click)

        # Set column widths for better responsive behavior
        self.workflows_tree.setColumnWidth(0, 200)  # Workflow name
        self.workflows_tree.setColumnWidth(1, 250)  # Description
        self.workflows_tree.setColumnWidth(2, 100)  # Modified date

        # Set size policy for responsiveness
        self.workflows_tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.workflows_tree.header().setStretchLastSection(True)

        layout.addWidget(self.workflows_tree)

        # Workflow actions
        workflow_actions_layout = QHBoxLayout()

        run_workflow_btn = QPushButton("Run Workflow")
        run_workflow_btn.clicked.connect(self.run_selected_workflow)
        workflow_actions_layout.addWidget(run_workflow_btn)

        edit_workflow_btn = QPushButton("Edit Workflow")
        edit_workflow_btn.clicked.connect(self.edit_selected_workflow)
        workflow_actions_layout.addWidget(edit_workflow_btn)

        export_workflow_btn = QPushButton("Export Package")
        export_workflow_btn.clicked.connect(self.export_workflow_package)
        workflow_actions_layout.addWidget(export_workflow_btn)

        layout.addLayout(workflow_actions_layout)

        return workflows_tab

    def create_right_panel(self) -> QWidget:
        """Create the right panel with details and controls"""
        right_panel = QWidget()
        layout = QVBoxLayout(right_panel)

        # Details group
        details_group = QGroupBox("Details")
        details_layout = QVBoxLayout(details_group)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        details_layout.addWidget(self.details_text)

        layout.addWidget(details_group)

        # Progress group (for automation execution)
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        progress_layout.addWidget(self.progress_label)

        # Stop automation button
        self.stop_automation_btn = QPushButton("Stop Automation")
        self.stop_automation_btn.setVisible(False)
        self.stop_automation_btn.clicked.connect(self.stop_automation)
        progress_layout.addWidget(self.stop_automation_btn)

        layout.addWidget(progress_group)

        # Settings group
        settings_group = QGroupBox("Settings")
        settings_layout = QFormLayout(settings_group)

        self.monitor_combo = QComboBox()
        self.monitor_combo.addItem("Primary Monitor")
        if len(self.window_manager.monitors) > 1:
            self.monitor_combo.addItem("Secondary Monitor")
        self.monitor_combo.currentIndexChanged.connect(self.on_settings_changed)
        settings_layout.addRow("Default Monitor:", self.monitor_combo)

        self.window_position_check = QCheckBox("Remember window positions")
        self.window_position_check.toggled.connect(self.on_settings_changed)
        settings_layout.addRow("", self.window_position_check)

        save_settings_btn = QPushButton("Save Settings")
        save_settings_btn.clicked.connect(self.save_configuration)
        settings_layout.addRow("", save_settings_btn)

        layout.addWidget(settings_group)

        return right_panel

    def apply_responsive_scaling(self):
        """Apply responsive scaling to UI elements"""
        try:
            # Calculate scale factor based on screen DPI and window size
            screen = self.screen() if hasattr(self, 'screen') else None
            if screen:
                dpi = screen.logicalDotsPerInch()
                scale_factor = dpi / 96.0  # 96 is standard DPI
            else:
                scale_factor = 1.0

            # Apply minimum scale factor for readability
            scale_factor = max(scale_factor, 0.8)
            scale_factor = min(scale_factor, 1.5)  # Cap at 1.5x for usability

            # Create a base font with scaling
            base_font = QFont()
            base_font.setPointSize(int(9 * scale_factor))

            # Apply to main widgets
            if hasattr(self, 'tab_widget'):
                self.tab_widget.setFont(base_font)
            if hasattr(self, 'programs_tree'):
                self.programs_tree.setFont(base_font)
                # Scale header font
                header = self.programs_tree.header()
                header_font = base_font
                header_font.setBold(True)
                header.setFont(header_font)
            if hasattr(self, 'workflows_tree'):
                self.workflows_tree.setFont(base_font)
                # Scale header font
                header = self.workflows_tree.header()
                header_font = base_font
                header_font.setBold(True)
                header.setFont(header_font)

            # Scale labels
            label_font = base_font
            if hasattr(self, 'status_label'):
                self.status_label.setFont(label_font)
            if hasattr(self, 'monitor_info_label'):
                self.monitor_info_label.setFont(label_font)

            # Scale buttons
            button_font = base_font
            for button in self.findChildren(QPushButton):
                button.setFont(button_font)

            # Scale group box titles
            group_font = base_font
            group_font.setBold(True)
            for group_box in self.findChildren(QGroupBox):
                group_box.setFont(group_font)

        except Exception as e:
            logger.warning(f"Error applying responsive scaling: {e}")

    def on_settings_changed(self):
        """Handle settings changes"""
        # Mark that settings need to be saved
        if hasattr(self, 'status_label'):
            self.status_label.setText("Settings changed - click Save Settings to persist")

    def get_monitor_status_text(self) -> str:
        """Get monitor status text for status bar"""
        monitor_count = len(self.window_manager.monitors)
        if monitor_count == 1:
            monitor = self.window_manager.monitors[0]
            return f"1 Monitor: {monitor['width']}x{monitor['height']}"
        else:
            return f"{monitor_count} Monitors detected"

    def detect_programs(self):
        """Detect installed petroleum programs"""
        self.status_label.setText("Detecting programs...")

        # Create a separate thread for program detection
        detection_thread = threading.Thread(target=self._detect_programs_worker)
        detection_thread.start()

    def _detect_programs_worker(self):
        """Worker method for program detection"""
        try:
            logger.info("Starting petroleum program detection...")

            # Iterate through all configured petroleum programs
            for program_key, config in PETROLEUM_PROGRAM_CONFIG.items():
                logger.info(f"Checking {config['display_name']}...")

                program_info = ProgramInfo(
                    name=program_key,
                    display_name=config['display_name'],
                    executable_path="",
                    version="",
                    install_path="",
                    detected=False,
                    last_check=datetime.now().isoformat()
                )

                # Check installation status using the configured method
                check_method = config.get('check_method', {})
                check_type = check_method.get('type', 'registry')

                is_installed = False
                found_version = None
                executable_path = None

                try:
                    if check_type == 'registry':
                        check_keys = check_method.get('keys', [])
                        is_installed, found_version = WindowsUtils.check_registry(check_keys)

                        # If installed, try to find executable path
                        if is_installed:
                            executable_path = WindowsUtils.find_executable_path(program_key)

                    elif check_type == 'path':
                        paths_to_check = check_method.get('paths', [])
                        is_installed = any(WindowsUtils.check_path_exists(p) for p in paths_to_check)

                        if is_installed and paths_to_check:
                            # Use the first existing path as install location
                            for path in paths_to_check:
                                expanded_path = os.path.expandvars(path)
                                if os.path.exists(expanded_path):
                                    program_info.install_path = expanded_path
                                    break

                    # Update program info with detection results
                    program_info.detected = is_installed
                    program_info.version = found_version or ""
                    program_info.executable_path = executable_path or ""

                    logger.info(f"{config['display_name']}: {'Installed' if is_installed else 'Not Found'}" +
                               (f" (v{found_version})" if found_version else ""))

                except Exception as e:
                    logger.error(f"Error checking {config['display_name']}: {e}")
                    program_info.detected = False
                    program_info.install_error = str(e)

                # Store the program info
                self.detected_programs[program_key] = program_info

            # Update UI on main thread
            QTimer.singleShot(100, self.update_programs_ui)
            logger.info("Petroleum program detection completed")

        except Exception as e:
            logger.error(f"Error in program detection worker: {e}")
            QTimer.singleShot(100, lambda: self.status_label.setText("Error detecting programs"))

    def update_programs_ui(self):
        """Update the programs tree widget with detected programs"""
        # Safety check - make sure the UI is initialized
        if not hasattr(self, 'programs_tree'):
            return

        self.programs_tree.clear()

        for program_name, program_info in self.detected_programs.items():
            item = QTreeWidgetItem(self.programs_tree)
            item.setText(0, program_info.display_name)
            item.setText(1, program_info.version or "Unknown")

            if program_info.detected:
                item.setText(2, "Installed")
                item.setIcon(0, self.get_style_icon("✓"))
            else:
                item.setText(2, "Not Found")
                item.setIcon(0, self.get_style_icon("✗"))

            item.setData(0, Qt.UserRole, program_name)

        self.programs_tree.resizeColumnToContents(0)
        self.programs_tree.resizeColumnToContents(1)

        if hasattr(self, 'status_label'):
            self.status_label.setText(f"Found {len([p for p in self.detected_programs.values() if p.detected])} programs")

    def get_style_icon(self, symbol: str) -> QIcon:
        """Create a simple icon with text"""
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)

        # For now, just return an empty icon
        # In a real implementation, you might want to create proper icons
        return QIcon(pixmap)

    def on_program_double_click(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on a program"""
        program_name = item.data(0, Qt.UserRole)
        if program_name and program_name in self.detected_programs:
            self.show_program_details(self.detected_programs[program_name])

    def show_program_details(self, program: ProgramInfo):
        """Show details for a program"""
        details = f"""
<h3>{program.display_name}</h3>
<p><b>Status:</b> {'Installed' if program.detected else 'Not Found'}</p>
<p><b>Version:</b> {program.version or 'Unknown'}</p>
<p><b>Executable:</b> {program.executable_path or 'Not detected'}</p>
<p><b>Install Path:</b> {program.install_path or 'Not detected'}</p>
<p><b>Last Check:</b> {program.last_check}</p>
        """

        self.details_text.setHtml(details)

    def launch_selected_program(self):
        """Launch the selected program"""
        current_item = self.programs_tree.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a program to launch")
            return

        program_name = current_item.data(0, Qt.UserRole)
        if program_name and program_name in self.detected_programs:
            program = self.detected_programs[program_name]
            if program.detected and program.executable_path:
                self.launch_program(program)
            else:
                QMessageBox.warning(self, "Program Not Available",
                                  f"{program.display_name} is not properly installed or detected")

    def launch_program(self, program: ProgramInfo):
        """Launch a specific program"""
        try:
            if not program.detected:
                QMessageBox.warning(self, "Program Not Available",
                                  f"{program.display_name} is not properly installed or detected")
                return

            if not program.executable_path:
                QMessageBox.warning(self, "No Executable",
                                  f"No executable path found for {program.display_name}")
                return

            if not os.path.exists(program.executable_path):
                QMessageBox.warning(self, "Executable Not Found",
                                  f"Executable file not found:\n{program.executable_path}")
                return

            # Get window position
            position = self.window_manager.get_optimal_position(
                program.name,
                prefer_secondary=(self.monitor_combo.currentIndex() == 1)
            )

            # Launch the program
            logger.info(f"Launching {program.display_name} from {program.executable_path}")

            # Build launch command
            launch_args = [program.executable_path]

            # Launch the process
            process = subprocess.Popen(
                launch_args,
                cwd=program.install_path if program.install_path else None,
                shell=False
            )

            # Check if process started successfully
            if process.poll() is None:
                self.status_label.setText(f"Launched {program.display_name} (PID: {process.pid})")
                logger.info(f"Successfully launched {program.display_name} (PID: {process.pid})")

                # Store position if enabled
                if self.window_position_check.isChecked():
                    # Save position for future use (placeholder for window positioning)
                    logger.debug(f"Storing window position: {position}")

                # Optionally implement window positioning here
                if WINDOWS_SUPPORT and position:
                    # This would require more complex logic to find and position the window
                    # after it's created, which is beyond the scope of this basic implementation
                    pass

            else:
                error_msg = f"{program.display_name} exited immediately (Exit code: {process.returncode})"
                logger.error(error_msg)
                QMessageBox.warning(self, "Launch Failed", error_msg)

        except Exception as e:
            logger.error(f"Error launching {program.display_name}: {e}")
            QMessageBox.critical(self, "Launch Error", f"Failed to launch {program.display_name}: {e}")

    def create_new_workflow(self):
        """Create a new automation workflow"""
        dialog = WorkflowBuilderDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            workflow = dialog.workflow

            # Avoid name conflicts
            original_name = workflow.name
            counter = 1
            while workflow.name in self.workflows:
                workflow.name = f"{original_name} ({counter})"
                counter += 1

            self.workflows[workflow.name] = workflow
            self.save_configuration()
            self.update_workflows_ui()

            QMessageBox.information(self, "Workflow Created", f"Workflow '{workflow.name}' has been created successfully")

    def edit_selected_workflow(self):
        """Edit the selected workflow"""
        current_item = self.workflows_tree.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a workflow to edit")
            return

        workflow_name = current_item.data(0, Qt.UserRole)
        if workflow_name and workflow_name in self.workflows:
            # Create a copy of the workflow for editing
            import copy
            workflow_copy = copy.deepcopy(self.workflows[workflow_name])

            dialog = WorkflowBuilderDialog(self, workflow_copy)
            if dialog.exec_() == QDialog.Accepted:
                # Update the workflow
                self.workflows[workflow_name] = dialog.workflow
                self.save_configuration()
                self.update_workflows_ui()

                QMessageBox.information(self, "Workflow Updated", f"Workflow '{workflow_name}' has been updated successfully")

    def run_selected_workflow(self):
        """Run the selected automation workflow"""
        current_item = self.workflows_tree.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a workflow to run")
            return

        workflow_name = current_item.data(0, Qt.UserRole)
        if workflow_name and workflow_name in self.workflows:
            self.run_workflow(self.workflows[workflow_name])

    def run_workflow(self, workflow: Workflow):
        """Run an automation workflow"""
        if self.automation_engine and self.automation_engine.isRunning():
            QMessageBox.warning(self, "Already Running", "Another workflow is currently running")
            return

        self.automation_engine = AutomationEngine(workflow, self)
        self.automation_engine.progress_updated.connect(self.on_workflow_progress)
        self.automation_engine.step_completed.connect(self.on_workflow_step_completed)
        self.automation_engine.workflow_completed.connect(self.on_workflow_completed)

        # Show progress UI
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText("Starting workflow...")
        self.stop_automation_btn.setVisible(True)

        # Start the workflow
        self.automation_engine.start()

    def on_workflow_progress(self, progress: int, message: str):
        """Handle workflow progress updates"""
        self.progress_bar.setValue(progress)
        self.progress_label.setText(message)
        self.status_label.setText(f"Workflow: {message}")

    def on_workflow_step_completed(self, step_index: int, description: str, success: bool):
        """Handle workflow step completion"""
        status = "✓" if success else "✗"
        self.status_label.setText(f"Step {step_index + 1}: {status} {description}")

    def on_workflow_completed(self, success: bool, message: str):
        """Handle workflow completion"""
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.stop_automation_btn.setVisible(False)

        if success:
            QMessageBox.information(self, "Workflow Complete", message)
        else:
            QMessageBox.warning(self, "Workflow Failed", message)

        self.status_label.setText("Ready")

    def stop_automation(self):
        """Stop the currently running automation"""
        if self.automation_engine:
            self.automation_engine.stop()
            self.status_label.setText("Stopping workflow...")

    def on_workflow_double_click(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on a workflow"""
        workflow_name = item.data(0, Qt.UserRole)
        if workflow_name and workflow_name in self.workflows:
            self.show_workflow_details(self.workflows[workflow_name])

    def show_workflow_details(self, workflow: Workflow):
        """Show details for a workflow"""
        steps_html = ""
        for i, step in enumerate(workflow.steps, 1):
            steps_html += f"<p><b>{i}.</b> {step.description} ({step.step_type})</p>"

        details = f"""
<h3>{workflow.name}</h3>
<p><b>Description:</b> {workflow.description}</p>
<p><b>Author:</b> {workflow.author}</p>
<p><b>Version:</b> {workflow.version}</p>
<p><b>Created:</b> {workflow.created_date}</p>
<p><b>Modified:</b> {workflow.modified_date}</p>
<p><b>Steps:</b> {len(workflow.steps)}</p>
<hr>
<h4>Steps:</h4>
{steps_html}
        """

        self.details_text.setHtml(details)

    def export_workflow_package(self):
        """Export workflow as a package"""
        current_item = self.workflows_tree.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a workflow to export")
            return

        workflow_name = current_item.data(0, Qt.UserRole)
        if workflow_name and workflow_name in self.workflows:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                f"Export {workflow_name}",
                f"{workflow_name}.petrolpkg",
                "Petroleum Package (*.petrolpkg)"
            )

            if filename:
                self.export_package(self.workflows[workflow_name], filename)

    def export_package(self, workflow: Workflow, filename: str):
        """Export a workflow to a package file"""
        try:
            with zipfile.ZipFile(filename, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Add workflow configuration
                workflow_data = asdict(workflow)
                # Convert steps to serializable format
                workflow_data['steps'] = [asdict(step) for step in workflow.steps]

                zip_file.writestr('workflow.json', json.dumps(workflow_data, indent=2))

                # Add metadata
                metadata = {
                    'package_version': '1.0',
                    'created_date': datetime.now().isoformat(),
                    'creator': 'Petroleum Launcher',
                    'workflow_name': workflow.name,
                    'workflow_version': workflow.version
                }
                zip_file.writestr('metadata.json', json.dumps(metadata, indent=2))

                # Add any referenced files (placeholder for future implementation)
                for step in workflow.steps:
                    if step.file_path and os.path.exists(step.file_path):
                        try:
                            zip_file.write(step.file_path, f"files/{os.path.basename(step.file_path)}")
                        except Exception as e:
                            logger.warning(f"Could not add file {step.file_path} to package: {e}")

            QMessageBox.information(self, "Export Complete", f"Workflow exported to {filename}")

        except Exception as e:
            logger.error(f"Error exporting package: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to export package: {e}")

    def import_package(self):
        """Import a workflow from a package file"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import Workflow Package",
            "",
            "Petroleum Package (*.petrolpkg)"
        )

        if filename:
            self.import_workflow_package(filename)

    def import_workflow_package(self, filename: str):
        """Import a workflow from a package file"""
        try:
            with zipfile.ZipFile(filename, 'r') as zip_file:
                # Read metadata
                if 'metadata.json' in zip_file.namelist():
                    metadata = json.loads(zip_file.read('metadata.json').decode('utf-8'))
                else:
                    metadata = {}

                # Read workflow
                if 'workflow.json' not in zip_file.namelist():
                    raise ValueError("Invalid package: workflow.json not found")

                workflow_data = json.loads(zip_file.read('workflow.json').decode('utf-8'))

                # Convert to Workflow object
                steps = [AutomationStep(**step_data) for step_data in workflow_data['steps']]
                workflow = Workflow(
                    name=workflow_data['name'],
                    description=workflow_data['description'],
                    steps=steps,
                    created_date=workflow_data.get('created_date', datetime.now().isoformat()),
                    modified_date=datetime.now().isoformat(),
                    author=workflow_data.get('author', metadata.get('creator', 'Imported')),
                    version=workflow_data.get('version', metadata.get('workflow_version', '1.0'))
                )

                # Add to workflows (avoid name conflicts)
                original_name = workflow.name
                counter = 1
                while workflow.name in self.workflows:
                    workflow.name = f"{original_name} ({counter})"
                    counter += 1

                self.workflows[workflow.name] = workflow
                self.save_configuration()
                self.update_workflows_ui()

                QMessageBox.information(self, "Import Complete", f"Workflow '{workflow.name}' imported successfully")

        except Exception as e:
            logger.error(f"Error importing package: {e}")
            QMessageBox.critical(self, "Import Error", f"Failed to import package: {e}")

    def update_workflows_ui(self):
        """Update the workflows tree widget"""
        # Safety check - make sure the UI is initialized
        if not hasattr(self, 'workflows_tree'):
            return

        self.workflows_tree.clear()

        for workflow_name, workflow in self.workflows.items():
            item = QTreeWidgetItem(self.workflows_tree)
            item.setText(0, workflow.name)
            item.setText(1, workflow.description)
            item.setText(2, workflow.modified_date[:10])  # Show date only
            item.setData(0, Qt.UserRole, workflow_name)

        self.workflows_tree.resizeColumnToContents(0)
        self.workflows_tree.resizeColumnToContents(1)

    def load_configuration(self):
        """Load saved configuration data"""
        try:
            # Try to get settings from main application
            if hasattr(self.main_window, 'settings'):
                settings = self.main_window.settings
                module_settings = settings.get('petroleum_launcher', {})

                # Load workflows
                workflows_data = module_settings.get('workflows', {})
                for workflow_name, workflow_dict in workflows_data.items():
                    try:
                        # Reconstruct steps
                        steps = []
                        for step_data in workflow_dict.get('steps', []):
                            step = AutomationStep(**step_data)
                            steps.append(step)

                        workflow = Workflow(
                            name=workflow_dict['name'],
                            description=workflow_dict['description'],
                            steps=steps,
                            created_date=workflow_dict.get('created_date', datetime.now().isoformat()),
                            modified_date=workflow_dict.get('modified_date', datetime.now().isoformat()),
                            author=workflow_dict.get('author', 'User'),
                            version=workflow_dict.get('version', '1.0')
                        )
                        self.workflows[workflow_name] = workflow

                    except Exception as e:
                        logger.error(f"Error loading workflow '{workflow_name}': {e}")

                # Load UI settings
                ui_settings = module_settings.get('ui_settings', {})
                self.monitor_combo.setCurrentIndex(ui_settings.get('default_monitor', 0))
                self.window_position_check.setChecked(ui_settings.get('remember_positions', False))

                logger.info(f"Loaded {len(self.workflows)} workflows from configuration")

            else:
                # No main window settings available, use default
                logger.info("No main application settings available, using defaults")

        except Exception as e:
            logger.error(f"Error loading configuration: {e}")

        # Always create example workflow if no workflows exist
        if not self.workflows:
            example_workflow = Workflow(
                name="Example Workflow",
                description="An example automation workflow",
                steps=[
                    AutomationStep(
                        step_type="wait",
                        wait_time=3,
                        description="Wait 3 seconds (example step)"
                    )
                ],
                created_date=datetime.now().isoformat(),
                modified_date=datetime.now().isoformat(),
                author="System",
                version="1.0"
            )
            self.workflows["Example Workflow"] = example_workflow

        self.update_workflows_ui()

    def save_configuration(self):
        """Save configuration data"""
        try:
            if hasattr(self.main_window, 'settings'):
                # Prepare workflows data
                workflows_data = {}
                for workflow_name, workflow in self.workflows.items():
                    workflows_data[workflow_name] = {
                        'name': workflow.name,
                        'description': workflow.description,
                        'steps': [asdict(step) for step in workflow.steps],
                        'created_date': workflow.created_date,
                        'modified_date': workflow.modified_date,
                        'author': workflow.author,
                        'version': workflow.version
                    }

                # Prepare UI settings
                ui_settings = {
                    'default_monitor': self.monitor_combo.currentIndex(),
                    'remember_positions': self.window_position_check.isChecked()
                }

                # Update module settings in main application
                if 'petroleum_launcher' not in self.main_window.settings:
                    self.main_window.settings['petroleum_launcher'] = {}

                self.main_window.settings['petroleum_launcher']['workflows'] = workflows_data
                self.main_window.settings['petroleum_launcher']['ui_settings'] = ui_settings

                # Trigger save in main application
                if hasattr(self.main_window, 'save_settings'):
                    self.main_window.save_settings()

                logger.info(f"Saved {len(self.workflows)} workflows to configuration")

            else:
                # Fallback: save to local file
                self.save_to_local_file()

        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            # Try fallback method
            try:
                self.save_to_local_file()
            except Exception as fallback_error:
                logger.error(f"Fallback save also failed: {fallback_error}")

    def save_to_local_file(self):
        """Save configuration to a local file (fallback method)"""
        try:
            config_dir = Path.home() / ".desktop_organizer"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_file = config_dir / "petroleum_launcher_config.json"

            config_data = {
                'workflows': {
                    workflow_name: {
                        'name': workflow.name,
                        'description': workflow.description,
                        'steps': [asdict(step) for step in workflow.steps],
                        'created_date': workflow.created_date,
                        'modified_date': workflow.modified_date,
                        'author': workflow.author,
                        'version': workflow.version
                    }
                    for workflow_name, workflow in self.workflows.items()
                },
                'ui_settings': {
                    'default_monitor': self.monitor_combo.currentIndex(),
                    'remember_positions': self.window_position_check.isChecked()
                },
                'last_saved': datetime.now().isoformat()
            }

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved configuration to local file: {config_file}")

        except Exception as e:
            logger.error(f"Error saving to local file: {e}")
            raise

    def resizeEvent(self, event):
        """Handle window resize events for auto-scaling"""
        super().resizeEvent(event)

        # Adjust splitter sizes proportionally
        if hasattr(self, 'splitter_original_sizes'):
            total_width = event.size().width()
            total_original = sum(self.splitter_original_sizes)

            if total_original > 0:
                # Calculate proportional sizes
                left_size = int(total_width * (self.splitter_original_sizes[0] / total_original))
                right_size = total_width - left_size - (self.splitter.handleWidth() if hasattr(self.splitter, 'handleWidth') else 5)

                # Ensure minimum sizes
                left_size = max(left_size, 200)
                right_size = max(right_size, 300)

                if hasattr(self, 'splitter'):
                    self.splitter.setSizes([left_size, right_size])

        # Reapply scaling on resize (throttled)
        if hasattr(self, '_last_resize_time'):
            current_time = QTimer.remainingTime if hasattr(QTimer, 'remainingTime') else lambda: 0
            # Only reapply scaling if it's been more than 500ms since last resize
            pass
        else:
            self._last_resize_time = True

        # Apply scaling on resize (with throttling)
        if not hasattr(self, '_resize_timer'):
            self._resize_timer = QTimer()
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self.apply_responsive_scaling)

        self._resize_timer.start(200)  # 200ms delay

    def closeEvent(self, event):
        """Handle widget close event"""
        # Stop any running automation
        if self.automation_engine and self.automation_engine.isRunning():
            self.automation_engine.stop()
            self.automation_engine.wait()

        # Save configuration
        self.save_configuration()

        event.accept()


class WorkflowBuilderDialog(QDialog):
    """Dialog for building and editing automation workflows"""

    def __init__(self, parent=None, workflow: Optional[Workflow] = None):
        super().__init__(parent)
        self.parent_widget = parent
        self.workflow = workflow or Workflow(
            name="New Workflow",
            description="",
            steps=[],
            created_date=datetime.now().isoformat(),
            modified_date=datetime.now().isoformat(),
            author="User",
            version="1.0"
        )

        self.initUI()

    def initUI(self):
        """Initialize the workflow builder UI"""
        self.setWindowTitle(f"Workflow Builder - {self.workflow.name}")
        self.setModal(True)
        self.setMinimumSize(600, 500)

        # Calculate initial size based on parent
        if self.parent_widget:
            parent_size = self.parent_widget.size()
            dialog_width = min(parent_size.width() - 100, 900)
            dialog_height = min(parent_size.height() - 100, 700)
            self.resize(dialog_width, dialog_height)
        else:
            self.resize(800, 600)

        # Enable auto-scaling
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)

        # Apply responsive scaling after UI is built
        QTimer.singleShot(100, self.apply_dialog_scaling)

        # Workflow info
        info_group = QGroupBox("Workflow Information")
        info_layout = QFormLayout(info_group)

        self.name_edit = QLineEdit(self.workflow.name)
        self.name_edit.textChanged.connect(self.update_window_title)
        info_layout.addRow("Name:", self.name_edit)

        self.description_edit = QLineEdit(self.workflow.description)
        info_layout.addRow("Description:", self.description_edit)

        self.author_edit = QLineEdit(self.workflow.author)
        info_layout.addRow("Author:", self.author_edit)

        layout.addWidget(info_group)

        # Steps
        steps_group = QGroupBox("Automation Steps")
        steps_layout = QVBoxLayout(steps_group)

        # Step buttons
        step_buttons_layout = QHBoxLayout()

        add_step_btn = QPushButton("Add Step")
        add_step_btn.clicked.connect(self.add_step)
        step_buttons_layout.addWidget(add_step_btn)

        remove_step_btn = QPushButton("Remove Step")
        remove_step_btn.clicked.connect(self.remove_step)
        step_buttons_layout.addWidget(remove_step_btn)

        move_up_btn = QPushButton("Move Up")
        move_up_btn.clicked.connect(self.move_step_up)
        step_buttons_layout.addWidget(move_up_btn)

        move_down_btn = QPushButton("Move Down")
        move_down_btn.clicked.connect(self.move_step_down)
        step_buttons_layout.addWidget(move_down_btn)

        step_buttons_layout.addStretch()

        steps_layout.addLayout(step_buttons_layout)

        # Steps table
        self.steps_table = QTableWidget()
        self.steps_table.setColumnCount(4)
        self.steps_table.setHorizontalHeaderLabels(["Type", "Program/File", "Description", "Parameters"])
        self.steps_table.horizontalHeader().setStretchLastSection(True)

        # Set initial column widths for better responsiveness
        self.steps_table.setColumnWidth(0, 120)  # Type
        self.steps_table.setColumnWidth(1, 150)  # Program/File
        self.steps_table.setColumnWidth(2, 200)  # Description

        # Set size policy for responsiveness
        self.steps_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.steps_table.itemSelectionChanged.connect(self.on_step_selected)
        self.steps_table.itemChanged.connect(self.on_step_item_changed)
        steps_layout.addWidget(self.steps_table)

        layout.addWidget(steps_group)

        # Step details
        details_group = QGroupBox("Step Details")
        details_layout = QFormLayout(details_group)

        self.step_type_combo = QComboBox()
        self.step_type_combo.addItems([
            "launch_program", "open_file", "wait", "run_command"
        ])
        self.step_type_combo.currentTextChanged.connect(self.on_step_type_changed)
        details_layout.addRow("Step Type:", self.step_type_combo)

        self.program_combo = QComboBox()
        self.program_combo.addItem("Select Program...")
        if self.parent_widget and hasattr(self.parent_widget, 'detected_programs'):
            for program_name, program_info in self.parent_widget.detected_programs.items():
                if program_info.detected:
                    self.program_combo.addItem(program_info.display_name, program_name)
        details_layout.addRow("Program:", self.program_combo)

        self.file_path_edit = QLineEdit()
        file_browse_btn = QPushButton("Browse...")
        file_browse_btn.clicked.connect(self.browse_file)
        file_path_layout = QHBoxLayout()
        file_path_layout.addWidget(self.file_path_edit)
        file_path_layout.addWidget(file_browse_btn)
        details_layout.addRow("File Path:", file_path_layout)

        self.description_edit2 = QLineEdit()
        details_layout.addRow("Description:", self.description_edit2)

        self.wait_time_spin = QSpinBox()
        self.wait_time_spin.setRange(1, 3600)
        self.wait_time_spin.setSuffix(" seconds")
        details_layout.addRow("Wait Time:", self.wait_time_spin)

        self.command_edit = QLineEdit()
        details_layout.addRow("Command:", self.command_edit)

        # Window positioning
        position_group = QGroupBox("Window Position")
        position_layout = QGridLayout(position_group)

        self.use_position_check = QCheckBox("Set Window Position")
        position_layout.addWidget(self.use_position_check, 0, 0, 1, 2)

        self.pos_left_spin = QSpinBox()
        self.pos_left_spin.setRange(0, 10000)
        position_layout.addWidget(QLabel("Left:"), 1, 0)
        position_layout.addWidget(self.pos_left_spin, 1, 1)

        self.pos_top_spin = QSpinBox()
        self.pos_top_spin.setRange(0, 10000)
        position_layout.addWidget(QLabel("Top:"), 1, 2)
        position_layout.addWidget(self.pos_top_spin, 1, 3)

        self.pos_width_spin = QSpinBox()
        self.pos_width_spin.setRange(100, 4000)
        position_layout.addWidget(QLabel("Width:"), 2, 0)
        position_layout.addWidget(self.pos_width_spin, 2, 1)

        self.pos_height_spin = QSpinBox()
        self.pos_height_spin.setRange(100, 4000)
        position_layout.addWidget(QLabel("Height:"), 2, 2)
        position_layout.addWidget(self.pos_height_spin, 2, 3)

        details_layout.addRow(position_group)

        layout.addWidget(details_group)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept_workflow)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Load existing workflow steps
        self.load_workflow_steps()
        self.update_steps_table()
        self.on_step_type_changed()

    def update_window_title(self):
        """Update window title when workflow name changes"""
        self.setWindowTitle(f"Workflow Builder - {self.name_edit.text()}")

    def load_workflow_steps(self):
        """Load existing workflow steps"""
        # This is already done in the constructor
        pass

    def update_steps_table(self):
        """Update the steps table with current workflow steps"""
        self.steps_table.setRowCount(len(self.workflow.steps))

        for row, step in enumerate(self.workflow.steps):
            # Step type
            type_item = QTableWidgetItem(step.step_type)
            self.steps_table.setItem(row, 0, type_item)

            # Program/File/Command
            if step.step_type == "launch_program":
                target = step.program_name or ""
            elif step.step_type == "open_file":
                target = os.path.basename(step.file_path) if step.file_path else ""
            elif step.step_type == "run_command":
                target = step.command
            else:
                target = ""

            target_item = QTableWidgetItem(target)
            self.steps_table.setItem(row, 1, target_item)

            # Description
            desc_item = QTableWidgetItem(step.description)
            self.steps_table.setItem(row, 2, desc_item)

            # Parameters
            params = []
            if step.step_type == "wait" and step.wait_time:
                params.append(f"{step.wait_time}s")
            elif step.parameters:
                for key, value in step.parameters.items():
                    params.append(f"{key}={value}")

            params_item = QTableWidgetItem(", ".join(params))
            self.steps_table.setItem(row, 3, params_item)

        self.steps_table.resizeColumnsToContents()

    def on_step_selected(self):
        """Handle step selection"""
        current_row = self.steps_table.currentRow()
        if 0 <= current_row < len(self.workflow.steps):
            step = self.workflow.steps[current_row]
            self.load_step_details(step)

    def load_step_details(self, step: AutomationStep):
        """Load step details into the form"""
        self.step_type_combo.setCurrentText(step.step_type)
        self.description_edit2.setText(step.description)

        if step.step_type == "launch_program":
            self.program_combo.setCurrentText(step.program_name)
        elif step.step_type == "open_file":
            self.file_path_edit.setText(step.file_path or "")
        elif step.step_type == "wait":
            self.wait_time_spin.setValue(step.wait_time)
        elif step.step_type == "run_command":
            self.command_edit.setText(step.command or "")

        # Window position
        if step.window_position:
            self.use_position_check.setChecked(True)
            self.pos_left_spin.setValue(step.window_position.get('left', 0))
            self.pos_top_spin.setValue(step.window_position.get('top', 0))
            self.pos_width_spin.setValue(step.window_position.get('width', 800))
            self.pos_height_spin.setValue(step.window_position.get('height', 600))
        else:
            self.use_position_check.setChecked(False)

        self.on_step_type_changed()

    def on_step_type_changed(self):
        """Handle step type change"""
        step_type = self.step_type_combo.currentText()

        # Show/hide relevant fields
        self.program_combo.setVisible(step_type == "launch_program")
        self.file_path_edit.setVisible(step_type in ["open_file"])
        self.wait_time_spin.setVisible(step_type == "wait")
        self.command_edit.setVisible(step_type == "run_command")

    def add_step(self):
        """Add a new step"""
        step = AutomationStep(
            step_type="wait",
            description="New step",
            wait_time=5
        )
        self.workflow.steps.append(step)
        self.update_steps_table()

        # Select the new step
        self.steps_table.selectRow(len(self.workflow.steps) - 1)
        self.on_step_selected()

    def remove_step(self):
        """Remove the selected step"""
        current_row = self.steps_table.currentRow()
        if 0 <= current_row < len(self.workflow.steps):
            del self.workflow.steps[current_row]
            self.update_steps_table()

    def move_step_up(self):
        """Move the selected step up"""
        current_row = self.steps_table.currentRow()
        if 0 < current_row < len(self.workflow.steps):
            # Swap steps
            self.workflow.steps[current_row], self.workflow.steps[current_row - 1] = \
                self.workflow.steps[current_row - 1], self.workflow.steps[current_row]
            self.update_steps_table()
            self.steps_table.selectRow(current_row - 1)

    def move_step_down(self):
        """Move the selected step down"""
        current_row = self.steps_table.currentRow()
        if 0 <= current_row < len(self.workflow.steps) - 1:
            # Swap steps
            self.workflow.steps[current_row], self.workflow.steps[current_row + 1] = \
                self.workflow.steps[current_row + 1], self.workflow.steps[current_row]
            self.update_steps_table()
            self.steps_table.selectRow(current_row + 1)

    def browse_file(self):
        """Browse for a file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File",
            "",
            "All Files (*.*)"
        )
        if file_path:
            self.file_path_edit.setText(file_path)

    def on_step_item_changed(self, item):
        """Handle item change in steps table"""
        if item.column() == 2:  # Description column
            current_row = item.row()
            if 0 <= current_row < len(self.workflow.steps):
                self.workflow.steps[current_row].description = item.text()

    def save_current_step(self):
        """Save the current step details"""
        current_row = self.steps_table.currentRow()
        if 0 <= current_row < len(self.workflow.steps):
            step = self.workflow.steps[current_row]

            step.step_type = self.step_type_combo.currentText()
            step.description = self.description_edit2.text()

            if step.step_type == "launch_program":
                program_data = self.program_combo.currentData()
                step.program_name = program_data if program_data else ""
            elif step.step_type == "open_file":
                step.file_path = self.file_path_edit.text()
            elif step.step_type == "wait":
                step.wait_time = self.wait_time_spin.value()
            elif step.step_type == "run_command":
                step.command = self.command_edit.text()

            # Window position
            if self.use_position_check.isChecked():
                step.window_position = {
                    'left': self.pos_left_spin.value(),
                    'top': self.pos_top_spin.value(),
                    'width': self.pos_width_spin.value(),
                    'height': self.pos_height_spin.value()
                }
            else:
                step.window_position = {}

            self.update_steps_table()

    def accept_workflow(self):
        """Accept and save the workflow"""
        # Save current step
        self.save_current_step()

        # Update workflow info
        self.workflow.name = self.name_edit.text() or "Untitled Workflow"
        self.workflow.description = self.description_edit.text()
        self.workflow.author = self.author_edit.text()
        self.workflow.modified_date = datetime.now().isoformat()

        # Validate workflow
        if not self.workflow.steps:
            QMessageBox.warning(self, "Invalid Workflow", "Workflow must have at least one step")
            return

        # Accept the dialog
        self.accept()

    def apply_dialog_scaling(self):
        """Apply responsive scaling to dialog elements"""
        try:
            # Calculate scale factor based on screen DPI and window size
            screen = self.screen() if hasattr(self, 'screen') else None
            if screen:
                dpi = screen.logicalDotsPerInch()
                scale_factor = dpi / 96.0  # 96 is standard DPI
            else:
                scale_factor = 1.0

            # Apply minimum scale factor for readability
            scale_factor = max(scale_factor, 0.8)
            scale_factor = min(scale_factor, 1.5)  # Cap at 1.5x for usability

            # Create base fonts with scaling
            base_font = QFont()
            base_font.setPointSize(int(9 * scale_factor))
            title_font = QFont()
            title_font.setPointSize(int(10 * scale_factor))
            title_font.setBold(True)

            # Apply to main widgets
            if hasattr(self, 'steps_table'):
                self.steps_table.setFont(base_font)
                # Scale header font
                header = self.steps_table.horizontalHeader()
                header.setFont(title_font)

            # Scale labels and form elements
            for label in self.findChildren(QLabel):
                label.setFont(base_font)

            # Scale buttons
            for button in self.findChildren(QPushButton):
                button.setFont(base_font)

            # Scale combo boxes and line edits
            for combo in self.findChildren(QComboBox):
                combo.setFont(base_font)
            for line_edit in self.findChildren(QLineEdit):
                line_edit.setFont(base_font)
            for spin_box in self.findChildren(QSpinBox):
                spin_box.setFont(base_font)

            # Scale group box titles
            for group_box in self.findChildren(QGroupBox):
                group_box.setTitleFont(title_font)

        except Exception as e:
            logger.warning(f"Error applying dialog scaling: {e}")


if __name__ == "__main__":
    # Standalone testing
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = PetroleumLauncherWidget()
    window.show()
    sys.exit(app.exec_())