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
    "pywin32>=227",
    "PyAutoGUI>=0.9.53",
    "opencv-python>=4.5.0",
    "Pillow>=8.0.0",
    "numpy>=1.19.0",
    "pynput>=1.7.6"
  ],
  "python_version": "3.8+",
  "permissions": [
    "file_system_read",
    "file_system_write",
    "process_control",
    "system_info",
    "screen_capture"
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
import glob
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import zipfile
import tempfile
import shutil
from datetime import datetime

# Try to import PIL for image handling (needed even without screen recording)
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_SUPPORT = True
except ImportError as e:
    PIL_SUPPORT = False
    print(f"Warning: PIL not available: {e}")

# Try to import screen recording dependencies
try:
    import pyautogui
    import cv2
    import numpy as np
    import threading
    import queue
    from collections import deque
    SCREEN_RECORDING_SUPPORT = True
except ImportError as e:
    SCREEN_RECORDING_SUPPORT = False
    print(f"Warning: Screen recording dependencies not available: {e}")

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QTextEdit, QSplitter,
    QGroupBox, QTabWidget, QTableWidget, QTableWidgetItem, QListWidgetItem, QListWidget,
    QHeaderView, QComboBox, QLineEdit, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox, QFrame,
    QScrollArea, QGridLayout, QDialog, QDialogButtonBox,
    QFormLayout, QSpinBox, QDoubleSpinBox, QSlider, QSizePolicy, QApplication
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, pyqtSlot, QEvent
from PyQt5.QtGui import QIcon, QFont, QPixmap

# Create fallback Image class if PIL is not available
if not PIL_SUPPORT:
    class Image:
        """Fallback Image class for when PIL is not available"""
        @staticmethod
        def new(mode, size, color=0):
            """Create a new image - fallback implementation"""
            return None  # Return None for now

        @staticmethod
        def open(fp):
            """Open an image file - fallback implementation"""
            return None  # Return None for now

        class Draw:
            """Fallback Draw class"""
            def __init__(self, img):
                self.img = img

            def rectangle(self, box, outline=None, width=0):
                pass

        @staticmethod
        def Draw(img):
            return Image.Draw(img)

        class Font:
            """Fallback Font class"""
            def __init__(self, font=None, size=12):
                self.font = font
                self.size = size

        truetype = Font

# Import standard modules that should always be available
import re

# Try to import Windows-specific modules
try:
    import win32api
    import win32con
    import win32gui
    import win32process
    import winreg
    WINDOWS_SUPPORT = True
except ImportError:
    WINDOWS_SUPPORT = False
    print("Warning: pywin32 not available. Some features may be limited.")

# Set up logging
logger = logging.getLogger('PetroleumLauncher')
logger.setLevel(logging.DEBUG)  # Ensure debug messages are visible


class PetroleumProgramConfigManager:
    """Manages external petroleum program configuration files"""

    def __init__(self):
        self.config_dir = None
        self.config_file = None
        self.config = {}
        self.default_config = {}
        self._init_default_config()
        self._setup_config_directory()
        self.load_configuration()

    def _init_default_config(self):
        """Initialize default petroleum program configuration"""
        self.default_config = self.get_default_config()

    def _setup_config_directory(self):
        """Setup the configuration directory in app settings folder"""
        try:
            # Try to find the application settings directory
            import sys

            # Check if we're running within the main application
            for module_name in sys.modules:
                if 'main' in module_name.lower() or 'organizer' in module_name.lower():
                    main_app = sys.modules[module_name]
                    if hasattr(main_app, 'settings'):
                        # Use the main app's settings directory
                        settings_dir = getattr(main_app.settings, 'settings_dir', None)
                        if settings_dir and os.path.exists(settings_dir):
                            self.config_dir = Path(settings_dir) / "petroleum_launcher"
                            self.config_dir.mkdir(exist_ok=True)
                            logger.info(f"Using app settings directory: {self.config_dir}")
                            break

            # Fallback to user profile
            if not self.config_dir:
                self.config_dir = Path.home() / ".DesktopOrganizer" / "PetroleumLauncher"
                self.config_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Using user profile config directory: {self.config_dir}")

            # Set config file path
            self.config_file = self.config_dir / "petroleum_programs.json"

        except Exception as e:
            logger.error(f"Error setting up config directory: {e}")
            # Use current directory as last resort
            self.config_dir = Path(".")
            self.config_file = self.config_dir / "petroleum_programs.json"

    def load_configuration(self):
        """Load configuration from JSON file"""
        try:
            if self.config_file.exists():
                logger.info(f"Loading configuration from: {self.config_file}")
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)

                # Check if it's the exported format with "programs" key
                if "programs" in loaded_config:
                    program_config = loaded_config["programs"]
                elif "metadata" in loaded_config:
                    # Old format with metadata - extract non-metadata keys
                    program_config = {k: v for k, v in loaded_config.items() if k != "metadata"}
                else:
                    # Direct program config
                    program_config = loaded_config

                # Validate and merge with default config
                self.config = self._validate_and_merge_config(program_config)
                logger.info(f"Loaded {len(self.config)} program configurations: {list(self.config.keys())}")
                logger.debug(f"Configuration structure sample: {list(self.config.items())[:1] if self.config else 'No configs'}")

                # If no valid configurations were loaded, fall back to defaults
                if len(self.config) == 0:
                    logger.warning("No valid configurations loaded, falling back to defaults")
                    self.config = self.default_config.copy()
                    self.save_configuration()  # Recreate config file
                    logger.info(f"Recreated config with {len(self.config)} default programs")
            else:
                logger.info("Configuration file not found, using defaults")
                self.config = self.default_config.copy()
                self.save_configuration()  # Create default config file

        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            self.config = self.default_config.copy()

    def save_configuration(self):
        """Save configuration to JSON file"""
        try:
            if not self.config_file.parent.exists():
                self.config_file.parent.mkdir(parents=True, exist_ok=True)

            # Add metadata
            config_with_metadata = {
                "metadata": {
                    "version": "1.0",
                    "created_date": datetime.now().isoformat(),
                    "last_modified": datetime.now().isoformat(),
                    "description": "Petroleum program configuration for Desktop Organizer",
                    "program_count": len(self.config)
                },
                "programs": self.config
            }

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_with_metadata, f, indent=2, ensure_ascii=False)

            logger.info(f"Configuration saved to: {self.config_file}")
            return True

        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False

    def load_configuration_from_file(self, file_path: str) -> bool:
        """Load configuration from a specific JSON file"""
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                logger.error(f"Configuration file not found: {file_path}")
                return False

            logger.info(f"Loading configuration from: {file_path}")
            with open(file_path_obj, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)

            # Check if it's the new format with "programs" key
            if "programs" in loaded_config:
                program_config = loaded_config["programs"]
            elif "metadata" in loaded_config:
                # Old format with metadata
                program_config = {k: v for k, v in loaded_config.items() if k != "metadata"}
            else:
                program_config = loaded_config

            # Validate and merge with default config
            self.config = self._validate_and_merge_config(program_config)

            # Save to proper location
            self.save_configuration()

            # Check if file was in module directory and move it
            if "modules" in str(file_path).lower():
                try:
                    shutil.move(file_path, self.config_file)
                    logger.info(f"Moved configuration to: {self.config_file}")
                except Exception as e:
                    logger.warning(f"Could not move config file: {e}")

            logger.info(f"Successfully loaded {len(self.config)} program configurations")
            return True

        except Exception as e:
            logger.error(f"Error loading configuration from {file_path}: {e}")
            return False

    def _validate_and_merge_config(self, loaded_config: Dict) -> Dict:
        """Validate and merge loaded configuration with defaults"""
        validated_config = {}

        logger.info(f"Validating loaded config with {len(loaded_config)} items: {list(loaded_config.keys())}")
        logger.info(f"Default config has {len(self.default_config)} items: {list(self.default_config.keys())}")

        for program_key, program_data in loaded_config.items():
            # Validate required fields
            if not isinstance(program_data, dict):
                logger.warning(f"Skipping invalid program config for: {program_key}")
                continue

            required_fields = ["display_name"]
            if not all(field in program_data for field in required_fields):
                logger.warning(f"Program {program_key} missing required fields, using defaults if available")
                if program_key in self.default_config:
                    continue  # Use default config

            # Merge with default if program exists in defaults
            if program_key in self.default_config:
                default_program = self.default_config[program_key]
                # Start with default, then override with loaded config
                merged_program = default_program.copy()
                merged_program.update(program_data)
                validated_config[program_key] = merged_program
            else:
                # New program, validate structure
                if "display_name" in program_data:
                    validated_config[program_key] = program_data
                else:
                    logger.warning(f"Skipping program {program_key} - missing display_name")

        logger.info(f"Validation complete. {len(validated_config)} programs validated: {list(validated_config.keys())}")
        return validated_config

    def add_program(self, program_key: str, program_data: Dict) -> bool:
        """Add a new program to the configuration"""
        try:
            if program_key in self.config:
                logger.warning(f"Program {program_key} already exists, updating")

            # Validate program data
            if "display_name" not in program_data:
                logger.error("Program must have a display_name")
                return False

            self.config[program_key] = program_data
            self.save_configuration()
            logger.info(f"Added program: {program_key} - {program_data.get('display_name', 'Unknown')}")
            return True

        except Exception as e:
            logger.error(f"Error adding program: {e}")
            return False

    def remove_program(self, program_key: str) -> bool:
        """Remove a program from the configuration"""
        try:
            if program_key in self.config:
                del self.config[program_key]
                self.save_configuration()
                logger.info(f"Removed program: {program_key}")
                return True
            else:
                logger.warning(f"Program {program_key} not found in configuration")
                return False

        except Exception as e:
            logger.error(f"Error removing program: {e}")
            return False

    def get_config(self) -> Dict:
        """Get the current configuration"""
        return self.config.copy()

    def get_config_file_path(self) -> str:
        """Get the configuration file path"""
        return str(self.config_file)

    def export_configuration(self, file_path: str) -> bool:
        """Export current configuration to a JSON file"""
        try:
            export_path = Path(file_path)
            if not export_path.parent.exists():
                export_path.parent.mkdir(parents=True, exist_ok=True)

            export_data = {
                "metadata": {
                    "version": "1.0",
                    "export_date": datetime.now().isoformat(),
                    "source": "Desktop Organizer Petroleum Launcher",
                    "program_count": len(self.config)
                },
                "programs": self.config
            }

            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Configuration exported to: {export_path}")
            return True

        except Exception as e:
            logger.error(f"Error exporting configuration: {e}")
            return False

    def get_default_config(self) -> Dict:
        """Get the default program configuration - now empty for user-driven configuration"""
        logger.info("Using empty configuration - all programs must be added manually by users")
        return {}
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
                        return None
                else:
                    # Read the default value
                    reg_type, value = winreg.QueryValueEx(key, None)
                    if reg_type in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                        return str(value).strip()
                    else:
                        return None
        except FileNotFoundError:
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
    def find_executable_path(program_key: str, program_config: Dict = None) -> Optional[str]:
        """Find the executable path for a program using multiple detection methods."""
        if not WINDOWS_SUPPORT:
            return None

        logger.debug(f"Searching for executable for program: {program_key}")

        # Method 1: Check App Paths registry entries
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

        # Method 2: Use program configuration to search in common paths
        if program_config and 'executable_info' in program_config:
            exec_info = program_config['executable_info']
            main_executable = exec_info.get('main_executable', '')
            alternative_names = exec_info.get('alternative_names', [])
            common_locations = exec_info.get('common_locations', [])

            # Build list of executables to search for
            exe_names = [main_executable] + alternative_names
            exe_names = [name for name in exe_names if name]  # Remove empty strings

            logger.info(f"Searching {len(exe_names)} executables in {len(common_locations)} common locations")
            logger.info(f"Executables to search: {exe_names}")
            logger.info(f"Common locations: {common_locations}")

            for base_path in common_locations:
                logger.info(f"Checking path: {base_path}")
                # Expand wildcards in path
                if '*' in base_path:
                    matching_paths = glob.glob(base_path)
                    logger.info(f"Found {len(matching_paths)} matching paths for pattern: {base_path}")
                else:
                    matching_paths = [base_path] if os.path.exists(base_path) else []
                    logger.info(f"Path exists: {os.path.exists(base_path)} for {base_path}")

                for path in matching_paths:
                    for exe_name in exe_names:
                        exe_path = os.path.join(path, exe_name)
                        logger.info(f"Checking executable: {exe_path}")
                        if os.path.exists(exe_path):
                            logger.info(f"Found executable via config search: {exe_path}")
                            return exe_path

        # Method 3: Enhanced search using registry uninstall information
        try:
            # Look for the program in uninstall registry to find installation path
            uninstall_paths = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
            ]

            for uninstall_path in uninstall_paths:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, uninstall_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                        subkey_index = 0
                        while True:
                            try:
                                subkey_name = winreg.EnumKey(key, subkey_index)
                                subkey_full_path = f"{uninstall_path}\\{subkey_name}"

                                # Try to read InstallLocation
                                install_location = WindowsUtils._reg_read_string(winreg.HKEY_LOCAL_MACHINE, subkey_full_path, "InstallLocation")
                                if install_location and os.path.exists(install_location):
                                    # Search for executable in install location
                                    for root, dirs, files in os.walk(install_location):
                                        for file in files:
                                            if file.lower().endswith('.exe'):
                                                # Check if this could be the main executable
                                                exe_path = os.path.join(root, file)
                                                if WindowsUtils._is_main_executable(exe_path, program_key):
                                                    logger.debug(f"Found executable via install location search: {exe_path}")
                                                    return exe_path
                                subkey_index += 1
                            except OSError:
                                break
                except FileNotFoundError:
                    continue
        except Exception as e:
            logger.debug(f"Error in registry-based executable search: {e}")

        # Method 4: Environment PATH search (last resort)
        if program_config and 'executable_info' in program_config:
            exe_names = program_config['executable_info'].get('exe_names', [])
            for exe_name in exe_names:
                try:
                    # Check if executable is in system PATH
                    result = subprocess.run(['where', exe_name], capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        exe_path = result.stdout.strip().split('\n')[0]
                        if os.path.exists(exe_path):
                            logger.debug(f"Found executable via PATH search: {exe_path}")
                            return exe_path
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                    continue

        logger.debug(f"Executable not found for program: {program_key}")
        return None

    @staticmethod
    def _is_main_executable(exe_path: str, program_key: str) -> bool:
        """Determine if an executable is likely the main program executable"""
        try:
            exe_name = os.path.basename(exe_path).lower()
            program_key_lower = program_key.lower()

            # Check if exe name contains program key
            if program_key_lower in exe_name:
                return True

            # Common main executable patterns
            main_patterns = ['main.exe', 'app.exe', 'launcher.exe', 'client.exe']
            if any(pattern in exe_name for pattern in main_patterns):
                return True

            # Avoid helper executables
            helper_patterns = ['uninstall', 'setup', 'install', 'config', 'updater', 'helper']
            if any(pattern in exe_name for pattern in helper_patterns):
                return False

            # Check file size - main executables are usually larger
            try:
                file_size = os.path.getsize(exe_path)
                if file_size > 1024 * 1024:  # Larger than 1MB
                    return True
            except OSError:
                pass

            return False
        except Exception:
            return False

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
    step_type: str  # "launch_program", "open_file", "wait", "run_command", "click_button", "screenshot"
    program_name: str = ""
    file_path: str = ""
    command: str = ""
    parameters: Dict[str, Any] = None
    wait_time: int = 0
    window_position: Dict[str, int] = None
    description: str = ""
    button_text: str = ""  # For click_button steps
    button_position: Dict[str, int] = None  # For click_button steps
    screenshot_description: str = ""  # For screenshot steps

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if self.window_position is None:
            self.window_position = {}
        if self.button_position is None:
            self.button_position = {}


@dataclass
class WorkflowStep:
    """Enhanced workflow step for recording-based workflows"""
    step_number: int
    action_type: str  # "click", "input_text", "wait", "launch", "screenshot", "conditional", "loop", "custom_script"
    description: str
    target_element: str
    position: Dict[str, int]
    wait_time: float = 2.0
    optional: bool = False
    screenshot_path: Optional[str] = None
    text_to_input: Optional[str] = None
    program_name: Optional[str] = None
    file_path: Optional[str] = None
    command: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    conditional_logic: Optional[Dict[str, Any]] = None
    loop_logic: Optional[Dict[str, Any]] = None
    script_content: Optional[str] = None
    script_language: Optional[str] = None
    screenshot_description: Optional[str] = None

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if self.position is None:
            self.position = {"x": 0, "y": 0}


@dataclass
class Workflow:
    """Complete automation workflow"""
    name: str
    description: str
    steps: List[Any]  # Can be AutomationStep or WorkflowStep
    created_date: str
    modified_date: str
    author: str = ""
    version: str = "1.0"
    software: str = ""
    category: str = ""
    difficulty: str = ""
    estimated_time: float = 0.0
    tags: List[str] = None
    dependencies: List[str] = None
    variables: Dict[str, Any] = None
    error_handling: bool = False
    retry_count: int = 3
    timeout: int = 60

    def __post_init__(self):
        if not self.created_date:
            self.created_date = datetime.now().isoformat()
        if not self.modified_date:
            self.modified_date = datetime.now().isoformat()
        if self.tags is None:
            self.tags = []
        if self.dependencies is None:
            self.dependencies = []
        if self.variables is None:
            self.variables = {}


@dataclass
class ScreenshotRecord:
    """Record of a screenshot with button information"""
    timestamp: str
    image_path: str
    button_text: str
    button_position: Dict[str, int]
    action_description: str
    window_title: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class AutomationAction:
    """Single automation action recorded from user input"""
    action_type: str  # "click", "double_click", "right_click", "drag", "type", "scroll", "wait", "condition", "branch"
    position: Dict[str, int]
    timestamp: str
    description: str
    screenshot_path: Optional[str] = None
    image_template: Optional[str] = None  # For OpenCV template matching
    text_to_type: Optional[str] = None
    scroll_direction: Optional[str] = None
    scroll_amount: Optional[int] = None
    wait_time: Optional[float] = None
    confidence_threshold: float = 0.8
    petroleum_context: Optional[Dict[str, Any]] = None  # Petroleum software specific context
    conditional_logic: Optional[Dict[str, Any]] = None  # Conditional recording data

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ConditionalAction:
    """Conditional action with decision logic"""
    condition_type: str  # "if_exists", "if_not_exists", "if_text_contains", "if_window_contains", "if_file_exists"
    condition_parameters: Dict[str, Any]
    true_actions: List[AutomationAction]  # Actions to execute if condition is true
    false_actions: List[AutomationAction] = None  # Actions to execute if condition is false (optional)
    description: str = ""
    confidence_threshold: float = 0.8

    def __post_init__(self):
        if self.false_actions is None:
            self.false_actions = []


@dataclass
class WorkflowBranch:
    """Branch point in workflow with multiple paths"""
    branch_id: str
    condition: ConditionalAction
    branch_points: Dict[str, List[AutomationAction]]  # Maps branch names to action lists
    default_branch: str = "true"
    description: str = ""

    def get_actions_for_branch(self, branch_name: str) -> List[AutomationAction]:
        """Get actions for a specific branch"""
        return self.branch_points.get(branch_name, [])


@dataclass
class PetroleumWorkflowTemplate:
    """Pre-built workflow templates for petroleum software"""
    name: str
    software: str  # "petrel", "harmony_enterprise", "kappa", etc.
    description: str
    category: str  # "data_import", "simulation", "analysis", "reporting"
    steps: List[Dict[str, Any]]
    estimated_time: str
    difficulty: str  # "beginner", "intermediate", "advanced"
    prerequisites: List[str]

    def to_workflow(self) -> Workflow:
        """Convert template to workflow"""
        steps = []
        for step_data in self.steps:
            step = AutomationStep(
                step_type=step_data.get('type', 'wait'),
                description=step_data.get('description', ''),
                wait_time=step_data.get('wait_time', 0),
                program_name=step_data.get('program_name', ''),
                file_path=step_data.get('file_path', ''),
                command=step_data.get('command', ''),
                parameters=step_data.get('parameters', {})
            )
            steps.append(step)

        return Workflow(
            name=self.name,
            description=self.description,
            steps=steps,
            created_date=datetime.now().isoformat(),
            modified_date=datetime.now().isoformat(),
            author="System Template",
            version="1.0"
        )


@dataclass
class RecordingSession:
    """Complete recording session with screenshots and automation actions"""
    session_id: str
    start_time: str
    end_time: str
    screenshots: List[ScreenshotRecord]
    automation_actions: List[AutomationAction]
    description: str
    video_path: Optional[str] = None
    generated_script: Optional[str] = None

    def __post_init__(self):
        if not self.start_time:
            self.start_time = datetime.now().isoformat()
        if not self.session_id:
            self.session_id = f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not hasattr(self, 'automation_actions'):
            self.automation_actions = []


# Petroleum software workflow templates
PETROLEUM_WORKFLOW_TEMPLATES = [
    # Petrel Templates
    PetroleumWorkflowTemplate(
        name="Petrel: New Project Setup",
        software="petrel",
        description="Create a new Petrel project with basic settings",
        category="project_setup",
        steps=[
            {"type": "launch_program", "program_name": "petrel", "description": "Launch Petrel"},
            {"type": "wait", "wait_time": 5, "description": "Wait for Petrel to load"},
            {"type": "screenshot", "screenshot_description": "Petrel main window"},
            {"type": "wait", "wait_time": 2, "description": "Prepare for project creation"}
        ],
        estimated_time="2-5 minutes",
        difficulty="beginner",
        prerequisites=["Petrel installed", "Sufficient disk space"]
    ),

    PetroleumWorkflowTemplate(
        name="Petrel: Seismic Data Import",
        software="petrel",
        description="Import seismic data into Petrel project",
        category="data_import",
        steps=[
            {"type": "launch_program", "program_name": "petrel", "description": "Launch Petrel"},
            {"type": "wait", "wait_time": 5, "description": "Wait for Petrel to load"},
            {"type": "screenshot", "screenshot_description": "Ready for seismic import"},
            {"type": "wait", "wait_time": 3, "description": "Navigate to import menu"}
        ],
        estimated_time="5-10 minutes",
        difficulty="intermediate",
        prerequisites=["Petrel project open", "Seismic data files available"]
    ),

    # Harmony Enterprise Templates
    PetroleumWorkflowTemplate(
        name="Harmony: Production Data Analysis",
        software="harmony_enterprise",
        description="Analyze production data using Harmony Enterprise",
        category="analysis",
        steps=[
            {"type": "launch_program", "program_name": "harmony_enterprise", "description": "Launch Harmony Enterprise"},
            {"type": "wait", "wait_time": 4, "description": "Wait for Harmony to load"},
            {"type": "screenshot", "screenshot_description": "Harmony main interface"},
            {"type": "wait", "wait_time": 2, "description": "Prepare for data analysis"}
        ],
        estimated_time="3-8 minutes",
        difficulty="beginner",
        prerequisites=["Harmony Enterprise installed", "Production data available"]
    ),

    # Kappa Templates
    PetroleumWorkflowTemplate(
        name="Kappa: Well Test Analysis Setup",
        software="kappa",
        description="Set up well test analysis in Kappa Saphir",
        category="analysis",
        steps=[
            {"type": "launch_program", "program_name": "kappa", "description": "Launch Kappa Saphir"},
            {"type": "wait", "wait_time": 4, "description": "Wait for Saphir to load"},
            {"type": "screenshot", "screenshot_description": "Saphir analysis window"},
            {"type": "wait", "wait_time": 3, "description": "Prepare for well test setup"}
        ],
        estimated_time="5-15 minutes",
        difficulty="intermediate",
        prerequisites=["Kappa Saphir installed", "Well test data available"]
    ),

    # CMG Templates
    PetroleumWorkflowTemplate(
        name="CMG: Reservoir Simulation Setup",
        software="cmg",
        description="Set up basic reservoir simulation in CMG",
        category="simulation",
        steps=[
            {"type": "launch_program", "program_name": "cmg", "description": "Launch CMG Suite"},
            {"type": "wait", "wait_time": 5, "description": "Wait for CMG to load"},
            {"type": "screenshot", "screenshot_description": "CMG main interface"},
            {"type": "wait", "wait_time": 3, "description": "Prepare for simulation setup"}
        ],
        estimated_time="10-30 minutes",
        difficulty="advanced",
        prerequisites=["CMG Suite installed", "Reservoir model data available"]
    ),

    # TNavigator Templates
    PetroleumWorkflowTemplate(
        name="TNavigator: Model Builder",
        software="tnavigator",
        description="Build reservoir model in TNavigator",
        category="modeling",
        steps=[
            {"type": "launch_program", "program_name": "tnavigator", "description": "Launch TNavigator"},
            {"type": "wait", "wait_time": 4, "description": "Wait for TNavigator to load"},
            {"type": "screenshot", "screenshot_description": "TNavigator main window"},
            {"type": "wait", "wait_time": 2, "description": "Prepare for model building"}
        ],
        estimated_time="15-45 minutes",
        difficulty="advanced",
        prerequisites=["TNavigator installed", "Reservoir data available"]
    ),

    # Petroleum Experts Templates
    PetroleumWorkflowTemplate(
        name="Petroleum Experts: IPM Setup",
        software="petroleum_experts",
        description="Set up IPM for integrated production modeling",
        category="system_integration",
        steps=[
            {"type": "launch_program", "program_name": "petroleum_experts", "description": "Launch IPM"},
            {"type": "wait", "wait_time": 3, "description": "Wait for IPM to load"},
            {"type": "screenshot", "screenshot_description": "IPM workspace"},
            {"type": "wait", "wait_time": 2, "description": "Prepare for system setup"}
        ],
        estimated_time="5-20 minutes",
        difficulty="intermediate",
        prerequisites=["Petroleum Experts IPM installed", "Well data available"]
    )
]


class AutomationRecorder:
    def __init__(self):
        self.is_recording = False
        self.actions = []
        self.current_session = None
        self.last_action_time = 0
        self.action_threshold = 0.1  # Minimum time between actions
        self.listeners = []

        # Template directory for screenshots
        self.temp_dir = Path(tempfile.gettempdir()) / "petroleum_launcher_screenshots"
        self.temp_dir.mkdir(exist_ok=True)
        self.template_dir = self.temp_dir

        # Petroleum software context awareness
        self.petroleum_context = {
            'active_software': None,
            'detected_windows': [],
            'workflow_stage': None,
            'last_menu_actions': [],
            'petroleum_keywords': {
                'Petrel': ['project', 'process', 'grid', 'well', 'surface', 'simulation', 'run', 'calculate'],
                'Harmony': ['case', 'run', 'production', 'analysis', 'report', 'forecast'],
                'Kappa': ['analysis', 'plot', 'calculate', 'model', 'correlation'],
                'CMG': ['run', 'simulation', 'grid', 'results', 'report'],
                'Petroleum Experts': ['ipm', 'prosper', 'gap', 'well', 'model']
            }
        }

    def start_recording(self, session_description: str = "") -> str:
        """Start recording user actions for automation"""
        if not SCREEN_RECORDING_SUPPORT:
            raise ImportError("Screen recording dependencies not available")

        if self.is_recording:
            raise RuntimeError("Recording already in progress")

        session_id = f"automation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.current_session = RecordingSession(
            session_id=session_id,
            start_time=datetime.now().isoformat(),
            end_time="",
            screenshots=[],
            automation_actions=[],
            description=session_description
        )

        self.is_recording = True
        self.actions = []
        self.last_action_time = time.time()

        # Start keyboard and mouse listeners
        self._start_listeners()

        logger.info(f"Started automation recording: {session_id}")
        return session_id

    def stop_recording(self) -> RecordingSession:
        """Stop recording and generate automation script"""
        if not self.is_recording:
            raise RuntimeError("No recording in progress")

        self.is_recording = False

        # Stop listeners
        self._stop_listeners()

        if self.current_session:
            self.current_session.end_time = datetime.now().isoformat()
            self.current_session.automation_actions = self.actions.copy()

            # Generate PyAutoGUI script
            self.current_session.generated_script = self._generate_script()

            completed_session = self.current_session
            self.current_session = None

            logger.info(f"Stopped automation recording: {completed_session.session_id}")
            return completed_session

        raise RuntimeError("No active session to stop")

    def _start_listeners(self):
        """Start keyboard and mouse event listeners"""
        try:
            from pynput import mouse, keyboard

            # Mouse listener
            self.mouse_listener = mouse.Listener(
                on_click=self._on_mouse_click,
                on_scroll=self._on_mouse_scroll,
                on_move=self._on_mouse_move
            )
            self.mouse_listener.start()

            # Keyboard listener
            self.keyboard_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release
            )
            self.keyboard_listener.start()

            logger.info("Started input listeners")

        except ImportError:
            logger.warning("pynput not available, limited recording functionality")
            # Fallback to basic screenshot-based recording

    def _stop_listeners(self):
        """Stop keyboard and mouse event listeners"""
        if self.mouse_listener:
            self.mouse_listener.stop()
            self.mouse_listener = None

        if self.keyboard_listener:
            self.keyboard_listener.stop()
            self.keyboard_listener = None

        logger.info("Stopped input listeners")

    def _on_mouse_click(self, x, y, button, pressed):
        """Handle mouse click events with petroleum context awareness"""
        if not self.is_recording or not pressed:
            return

        current_time = time.time()
        if current_time - self.last_action_time < self.action_threshold:
            return  # Ignore rapid clicks

        try:
            # Update petroleum context
            self._update_petroleum_context(x, y)

            # Capture screenshot at click position
            screenshot = pyautogui.screenshot()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
            screenshot_path = self.template_dir / f"click_{timestamp}.png"
            screenshot.save(screenshot_path)

            # Determine click type
            if button == mouse.Button.left:
                action_type = "click"
                base_description = f"Left click at ({x}, {y})"
            elif button == mouse.Button.right:
                action_type = "right_click"
                base_description = f"Right click at ({x}, {y})"
            elif button == mouse.Button.middle:
                action_type = "middle_click"
                base_description = f"Middle click at ({x}, {y})"
            else:
                return

            # Enhanced description with petroleum context
            description = self._enhance_description_with_context(base_description, x, y, screenshot)

            # Create action with petroleum context
            action = AutomationAction(
                action_type=action_type,
                position={'x': x, 'y': y},
                timestamp=datetime.now().isoformat(),
                description=description,
                screenshot_path=str(screenshot_path),
                image_template=str(screenshot_path),  # Use screenshot as template
                petroleum_context=self.petroleum_context.copy()
            )

            self.actions.append(action)
            self.last_action_time = current_time

            logger.debug(f"Recorded {action_type} at ({x}, {y}) with context: {self.petroleum_context.get('active_software', 'Unknown')}")

        except Exception as e:
            logger.error(f"Error recording mouse click: {e}")

    def _update_petroleum_context(self, x: int, y: int):
        """Update petroleum software context based on current position and active windows"""
        try:
            # Get active window title
            active_window = pyautogui.getActiveWindow()
            window_title = active_window.title if active_window else ""

            # Detect petroleum software from window title
            detected_software = self._detect_petroleum_software(window_title)
            if detected_software:
                self.petroleum_context['active_software'] = detected_software

            # Track detected windows
            if window_title and window_title not in self.petroleum_context['detected_windows']:
                self.petroleum_context['detected_windows'].append(window_title)

            # Update workflow stage based on window content
            self._update_workflow_stage(window_title, x, y)

        except Exception as e:
            logger.error(f"Error updating petroleum context: {e}")

    def _detect_petroleum_software(self, window_title: str) -> Optional[str]:
        """Detect petroleum software from window title"""
        window_title_lower = window_title.lower()

        for software, keywords in self.petroleum_context['petroleum_keywords'].items():
            if software.lower() in window_title_lower:
                return software

        # Check for common petroleum software indicators
        if any(keyword in window_title_lower for keyword in ['petrel', 'harmony', 'kappa', 'cmg', 'prosper', 'gap', 'ipm']):
            if 'petrel' in window_title_lower:
                return 'Petrel'
            elif 'harmony' in window_title_lower:
                return 'Harmony Enterprise'
            elif 'kappa' in window_title_lower:
                return 'Kappa'
            elif 'cmg' in window_title_lower:
                return 'CMG'
            elif any(keyword in window_title_lower for keyword in ['prosper', 'gap', 'ipm']):
                return 'Petroleum Experts'

        return None

    def _update_workflow_stage(self, window_title: str, x: int, y: int):
        """Update workflow stage based on current context"""
        try:
            # Use OCR to read text at cursor position if available
            cursor_text = self._get_text_at_position(x, y).lower()

            # Analyze workflow stage based on window title and cursor text
            window_title_lower = window_title.lower()

            if any(keyword in window_title_lower for keyword in ['project', 'new', 'open']):
                self.petroleum_context['workflow_stage'] = 'project_setup'
            elif any(keyword in window_title_lower for keyword in ['process', 'workflow', 'flow']):
                self.petroleum_context['workflow_stage'] = 'process_building'
            elif any(keyword in window_title_lower for keyword in ['run', 'simulate', 'calculate', 'execute']):
                self.petroleum_context['workflow_stage'] = 'simulation'
            elif any(keyword in window_title_lower for keyword in ['result', 'output', 'report']):
                self.petroleum_context['workflow_stage'] = 'analysis'
            elif any(keyword in cursor_text for keyword in ['ok', 'cancel', 'apply', 'save', 'finish']):
                self.petroleum_context['workflow_stage'] = 'dialog_interaction'
            elif any(keyword in cursor_text for keyword in ['file', 'edit', 'view', 'insert', 'tools']):
                self.petroleum_context['workflow_stage'] = 'menu_navigation'

        except Exception as e:
            logger.error(f"Error updating workflow stage: {e}")

    def _get_text_at_position(self, x: int, y: int) -> str:
        """Get text at the specified screen position using OCR if available"""
        try:
            # This is a placeholder for OCR functionality
            # In a real implementation, you would use pytesseract or similar
            # For now, return empty string
            return ""
        except Exception:
            return ""

    def _enhance_description_with_context(self, base_description: str, x: int, y: int, screenshot) -> str:
        """Enhance action description with petroleum context"""
        enhanced = base_description
        active_software = self.petroleum_context.get('active_software')
        workflow_stage = self.petroleum_context.get('workflow_stage')

        if active_software:
            enhanced += f" ({active_software})"

        if workflow_stage:
            enhanced += f" - {workflow_stage.replace('_', ' ').title()}"

        # Try to identify what was clicked using basic image processing
        click_target = self._identify_click_target(x, y, screenshot)
        if click_target:
            enhanced += f" on '{click_target}'"

        return enhanced

    def _identify_click_target(self, x: int, y: int, screenshot) -> Optional[str]:
        """Identify what was clicked based on position and screenshot"""
        try:
            # This is a simplified implementation
            # In a real implementation, you would use more sophisticated image processing
            # For now, check if click is near common UI elements

            img_width, img_height = screenshot.size
            margin = 50  # pixels from edge

            # Check if click is near title bar (likely window controls)
            if y < margin:
                return "Window Title Bar"

            # Check if click is at bottom (likely status bar or taskbar)
            if y > img_height - margin:
                return "Status Bar"

            # Check if click is on left edge (likely menu or navigation)
            if x < margin:
                return "Navigation Panel"

            # Check if click is on right edge (likely properties or tools panel)
            if x > img_width - margin:
                return "Tools Panel"

            return None

        except Exception:
            return None

    def _on_mouse_scroll(self, x, y, dx, dy):
        """Handle mouse scroll events"""
        if not self.is_recording:
            return

        current_time = time.time()
        if current_time - self.last_action_time < self.action_threshold:
            return

        try:
            action = AutomationAction(
                action_type="scroll",
                position={'x': x, 'y': y},
                timestamp=datetime.now().isoformat(),
                description=f"Scroll at ({x}, {y}) delta: {dx}, {dy}",
                scroll_direction="up" if dy > 0 else "down",
                scroll_amount=int(abs(dy) * 10)
            )

            self.actions.append(action)
            self.last_action_time = current_time

            logger.debug(f"Recorded scroll at ({x}, {y}) delta: {dx}, {dy}")

        except Exception as e:
            logger.error(f"Error recording mouse scroll: {e}")

    def _on_mouse_move(self, x, y):
        """Handle mouse move events (for drag operations)"""
        # We'll implement drag detection later if needed
        pass

    def _on_key_press(self, key):
        """Handle keyboard press events"""
        if not self.is_recording:
            return

        try:
            from pynput import keyboard

            # Check for special keys
            if key == keyboard.Key.esc:
                # Stop recording on ESC
                self.stop_recording()
                return

            # Record typing
            try:
                char = key.char
                if char:
                    self._record_typing(char)
            except AttributeError:
                # Special key - handle as needed
                pass

        except Exception as e:
            logger.error(f"Error recording key press: {e}")

    def _on_key_release(self, key):
        """Handle keyboard release events"""
        pass

    def _record_typing(self, char):
        """Record typed characters"""
        if not self.is_recording:
            return

        current_time = time.time()

        # Check if we should add to existing typing action or create new one
        if (self.actions and
            self.actions[-1].action_type == "type" and
            current_time - self.last_action_time < 1.0):

            # Append to existing typing action
            self.actions[-1].text_to_type += char
            self.actions[-1].description += char
        else:
            # Create new typing action
            action = AutomationAction(
                action_type="type",
                position={'x': 0, 'y': 0},
                timestamp=datetime.now().isoformat(),
                description=f"Type: {char}",
                text_to_type=char
            )
            self.actions.append(action)

        self.last_action_time = current_time

    def _generate_script(self) -> str:
        """Generate PyAutoGUI script from recorded actions"""
        script_lines = [
            "import pyautogui",
            "import time",
            "import cv2",
            "import numpy as np",
            "",
            "def find_and_click(image_path, confidence=0.8):",
            "    \"\"\"Find image on screen and click it\"\"\"",
            "    try:",
            "        location = pyautogui.locateOnScreen(image_path, confidence=confidence)",
            "        if location:",
            "            center = pyautogui.center(location)",
            "            pyautogui.click(center)",
            "            return True",
            "    except Exception as e:",
            "        print(f\"Error finding image {image_path}: {e}\")",
            "    return False",
            "",
            "def main():",
            "    \"\"\"Main automation script\"\"\"",
            "    print(\"Starting automation...\")",
            "    pyautogui.FAILSAFE = True  # Move mouse to corner to stop",
            "    pyautogui.PAUSE = 0.5     # Pause between actions",
            "",
            "    try:"
        ]

        last_timestamp = None
        for i, action in enumerate(self.actions):
            if last_timestamp:
                # Calculate wait time between actions
                try:
                    current_time = datetime.fromisoformat(action.timestamp.replace('Z', '+00:00'))
                    last_time = datetime.fromisoformat(last_timestamp.replace('Z', '+00:00'))
                    wait_seconds = (current_time - last_time).total_seconds()

                    if wait_seconds > 1.0:  # Only add wait if significant
                        script_lines.append(f"        time.sleep({wait_seconds:.1f})")
                except:
                    pass

            if action.action_type == "click":
                if action.image_template:
                    script_lines.append(f"        # Click using image recognition")
                    script_lines.append(f"        if not find_and_click(r'{action.image_template}', confidence={action.confidence_threshold}):")
                    script_lines.append(f"            # Fallback to position click")
                    script_lines.append(f"            pyautogui.click({action.position['x']}, {action.position['y']})")
                else:
                    script_lines.append(f"        pyautogui.click({action.position['x']}, {action.position['y']})")
                script_lines.append(f"        print(\"Clicked at ({action.position['x']}, {action.position['y']})\")")

            elif action.action_type == "right_click":
                script_lines.append(f"        pyautogui.rightClick({action.position['x']}, {action.position['y']})")
                script_lines.append(f"        print(\"Right clicked at ({action.position['x']}, {action.position['y']})\")")

            elif action.action_type == "scroll":
                direction = -1 if action.scroll_direction == "up" else 1
                amount = action.scroll_amount or 10
                script_lines.append(f"        pyautogui.scroll({direction * amount}, x={action.position['x']}, y={action.position['y']})")
                script_lines.append(f"        print(\"Scrolled at ({action.position['x']}, {action.position['y']})\")")

            elif action.action_type == "type" and action.text_to_type:
                # Escape special characters for Python strings
                text = action.text_to_type.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')
                script_lines.append(f"        pyautogui.write(\"{text}\")")
                script_lines.append(f"        print(\"Typed: '{action.text_to_type}'\")")

            elif action.action_type == "wait" and action.wait_time:
                script_lines.append(f"        time.sleep({action.wait_time})")
                script_lines.append(f"        print(\"Waited {action.wait_time} seconds\")")

            last_timestamp = action.timestamp

        script_lines.extend([
            "",
            "    except KeyboardInterrupt:",
            "        print(\"Automation stopped by user\")",
            "    except Exception as e:",
            "        print(f\"Automation error: {e}\")",
            "    finally:",
            "        print(\"Automation completed\")",
            "",
            "if __name__ == \"__main__\":",
            "    main()"
        ])

        return "\n".join(script_lines)

    def get_intelligent_suggestions(self) -> List[Dict[str, Any]]:
        """Generate intelligent suggestions based on recorded actions and petroleum context"""
        suggestions = []

        if not self.actions:
            return suggestions

        # Analyze recorded actions for patterns
        active_software = self.petroleum_context.get('active_software')
        workflow_stages = [action.petroleum_context.get('workflow_stage') if action.petroleum_context else None
                          for action in self.actions]
        workflow_stages = [stage for stage in workflow_stages if stage]

        # Generate software-specific suggestions
        if active_software:
            suggestions.extend(self._get_software_specific_suggestions(active_software))

        # Generate workflow improvement suggestions
        suggestions.extend(self._get_workflow_improvement_suggestions(workflow_stages))

        # Generate optimization suggestions
        suggestions.extend(self._get_optimization_suggestions())

        # Generate error prevention suggestions
        suggestions.extend(self._get_error_prevention_suggestions())

        return suggestions

    def _get_software_specific_suggestions(self, software: str) -> List[Dict[str, Any]]:
        """Get software-specific suggestions"""
        suggestions = []

        if software == 'Petrel':
            suggestions.append({
                'type': 'best_practice',
                'title': 'Petrel Workflow Optimization',
                'description': 'Consider organizing your actions into Petrel processes for better reusability.',
                'priority': 'medium'
            })
            suggestions.append({
                'type': 'automation_tip',
                'title': 'Use Petrel Templates',
                'description': 'Your workflow can be saved as a Petrel template for future projects.',
                'priority': 'high'
            })

        elif software == 'Harmony Enterprise':
            suggestions.append({
                'type': 'best_practice',
                'title': 'Case Management',
                'description': 'Consider creating multiple cases for different scenarios.',
                'priority': 'medium'
            })
            suggestions.append({
                'type': 'automation_tip',
                'title': 'Batch Processing',
                'description': 'Your workflow can be applied to multiple cases automatically.',
                'priority': 'high'
            })

        elif software == 'CMG':
            suggestions.append({
                'type': 'technical_tip',
                'title': 'Simulation Parameters',
                'description': 'Ensure all simulation parameters are properly set before running.',
                'priority': 'high'
            })

        elif software == 'Petroleum Experts':
            suggestions.append({
                'type': 'best_practice',
                'title': 'IPM Integration',
                'description': 'Consider how this workflow integrates with IPM for production optimization.',
                'priority': 'medium'
            })

        return suggestions

    def _get_workflow_improvement_suggestions(self, workflow_stages: List[str]) -> List[Dict[str, Any]]:
        """Get workflow improvement suggestions"""
        suggestions = []

        # Check for common workflow patterns
        if 'project_setup' in workflow_stages and 'simulation' in workflow_stages:
            suggestions.append({
                'type': 'workflow_improvement',
                'title': 'Complete Workflow Detected',
                'description': 'Your recording covers a complete workflow from setup to simulation. This is ideal for automation.',
                'priority': 'high'
            })

        if 'analysis' not in workflow_stages and 'simulation' in workflow_stages:
            suggestions.append({
                'type': 'workflow_improvement',
                'title': 'Add Analysis Steps',
                'description': 'Consider adding result analysis steps to complete your workflow.',
                'priority': 'medium'
            })

        # Check for repetitive actions
        click_actions = [action for action in self.actions if action.action_type == 'click']
        if len(click_actions) > 10:
            suggestions.append({
                'type': 'optimization',
                'title': 'High Number of Clicks',
                'description': 'Your workflow has many clicks. Consider using keyboard shortcuts or menu navigation where possible.',
                'priority': 'low'
            })

        return suggestions

    def _get_optimization_suggestions(self) -> List[Dict[str, Any]]:
        """Get optimization suggestions"""
        suggestions = []

        # Check timing between actions
        if len(self.actions) > 1:
            min_interval = float('inf')
            for i in range(1, len(self.actions)):
                try:
                    current_time = datetime.fromisoformat(self.actions[i].timestamp.replace('Z', '+00:00'))
                    prev_time = datetime.fromisoformat(self.actions[i-1].timestamp.replace('Z', '+00:00'))
                    interval = (current_time - prev_time).total_seconds()
                    min_interval = min(min_interval, interval)
                except:
                    continue

            if min_interval < 0.5:
                suggestions.append({
                    'type': 'timing_optimization',
                    'title': 'Fast Actions Detected',
                    'description': 'Some actions occur very quickly. Consider adding explicit waits for better reliability.',
                    'priority': 'medium'
                })

        # Check for screenshot usage
        actions_with_screenshots = [action for action in self.actions if action.screenshot_path]
        if len(actions_with_screenshots) < len(self.actions) * 0.5:
            suggestions.append({
                'type': 'reliability_improvement',
                'title': 'More Screenshots Recommended',
                'description': 'Consider enabling auto-capture for more reliable automation using image recognition.',
                'priority': 'low'
            })

        return suggestions

    def _get_error_prevention_suggestions(self) -> List[Dict[str, Any]]:
        """Get error prevention suggestions"""
        suggestions = []

        # Check for dialog interactions
        dialog_actions = [action for action in self.actions
                         if action.petroleum_context and
                         action.petroleum_context.get('workflow_stage') == 'dialog_interaction']

        if dialog_actions:
            suggestions.append({
                'type': 'error_prevention',
                'title': 'Dialog Handling',
                'description': 'Your workflow includes dialog interactions. Consider adding error handling for unexpected dialogs.',
                'priority': 'high'
            })

        # Check for data entry
        data_entry_actions = [action for action in self.actions if action.action_type == 'type']
        if data_entry_actions:
            suggestions.append({
                'type': 'data_validation',
                'title': 'Data Entry Validation',
                'description': 'Your workflow includes data entry. Consider adding validation steps to ensure data integrity.',
                'priority': 'medium'
            })

        return suggestions


class ScreenRecorder:
    """Screen recording and screenshot capture functionality"""

    def __init__(self):
        self.is_recording = False
        self.recording_thread = None
        self.video_writer = None
        self.current_session = None
        self.sessions: List[RecordingSession] = []
        self.screenshot_queue = queue.Queue()
        self.temp_dir = Path(tempfile.gettempdir()) / "petroleum_launcher_screenshots"
        self.temp_dir.mkdir(exist_ok=True)
        self.automation_recorder = AutomationRecorder()

    def start_recording(self, session_description: str = "") -> str:
        """Start a new recording session"""
        if not SCREEN_RECORDING_SUPPORT:
            raise ImportError("Screen recording dependencies not available")

        if self.is_recording:
            raise RuntimeError("Recording already in progress")

        session_id = f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.current_session = RecordingSession(
            session_id=session_id,
            start_time=datetime.now().isoformat(),
            end_time="",
            screenshots=[],
            description=session_description
        )

        self.is_recording = True
        self.recording_thread = threading.Thread(target=self._recording_worker)
        self.recording_thread.daemon = True
        self.recording_thread.start()

        logger.info(f"Started recording session: {session_id}")
        return session_id

    def stop_recording(self) -> RecordingSession:
        """Stop current recording and return session data"""
        if not self.is_recording:
            raise RuntimeError("No recording in progress")

        self.is_recording = False

        if self.recording_thread:
            self.recording_thread.join(timeout=5)

        if self.current_session:
            self.current_session.end_time = datetime.now().isoformat()

            # Create video from screenshots if available
            if len(self.current_session.screenshots) > 0:
                self._create_video_from_screenshots()

            self.sessions.append(self.current_session)
            completed_session = self.current_session
            self.current_session = None

            logger.info(f"Stopped recording session: {completed_session.session_id}")
            return completed_session

        raise RuntimeError("No active session to stop")

    def _recording_worker(self):
        """Background worker for recording"""
        try:
            fps = 2  # Capture 2 frames per second for screenshots
            frame_interval = 1.0 / fps

            while self.is_recording:
                start_time = time.time()

                try:
                    # Take screenshot
                    screenshot = pyautogui.screenshot()

                    # Save screenshot
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
                    filename = f"{self.current_session.session_id}_{timestamp}.png"
                    filepath = self.temp_dir / filename
                    screenshot.save(filepath)

                    # Get active window information
                    try:
                        active_window = pyautogui.getActiveWindow()
                        window_title = active_window.title if active_window else ""
                    except:
                        window_title = ""

                    # Check for pending button screenshots
                    try:
                        while not self.screenshot_queue.empty():
                            button_data = self.screenshot_queue.get_nowait()
                            button_filename = f"{self.current_session.session_id}_button_{timestamp}.png"
                            button_filepath = self.temp_dir / button_filename

                            # Add button highlight to screenshot
                            highlighted_screenshot = self._highlight_button(screenshot, button_data)
                            highlighted_screenshot.save(button_filepath)

                            # Create screenshot record
                            record = ScreenshotRecord(
                                timestamp=datetime.now().isoformat(),
                                image_path=str(button_filepath),
                                button_text=button_data.get('text', ''),
                                button_position=button_data.get('position', {}),
                                action_description=button_data.get('action', ''),
                                window_title=window_title
                            )

                            self.current_session.screenshots.append(record)

                    except queue.Empty:
                        pass

                except Exception as e:
                    logger.error(f"Error in recording worker: {e}")

                # Wait for next frame
                elapsed = time.time() - start_time
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)

        except Exception as e:
            logger.error(f"Recording worker error: {e}")
            self.is_recording = False

    def capture_button_screenshot(self, button_text: str, button_position: Dict[str, int], action_description: str = ""):
        """Queue a button screenshot capture"""
        if self.is_recording:
            button_data = {
                'text': button_text,
                'position': button_position,
                'action': action_description,
                'timestamp': datetime.now().isoformat()
            }
            self.screenshot_queue.put(button_data)

    def _highlight_button(self, screenshot, button_data: Dict):
        """Highlight button area on screenshot"""
        if not button_data.get('position'):
            return screenshot

        try:
            # Convert to RGB if necessary
            if screenshot.mode != 'RGB':
                screenshot = screenshot.convert('RGB')

            # Create a draw object
            draw = ImageDraw.Draw(screenshot)

            # Get button position
            pos = button_data['position']
            x1 = pos.get('x', 0)
            y1 = pos.get('y', 0)
            x2 = x1 + pos.get('width', 100)
            y2 = y1 + pos.get('height', 30)

            # Draw red rectangle around button
            draw.rectangle([x1, y1, x2, y2], outline='red', width=3)

            # Add label
            button_text = button_data.get('text', 'Button')
            try:
                # Try to use a larger font
                font = ImageFont.truetype("arial.ttf", 16)
            except:
                font = ImageFont.load_default()

            # Draw text background
            text_bbox = draw.textbbox((x1, y1 - 25), button_text, font=font)
            draw.rectangle(text_bbox, fill='red')
            draw.text((x1, y1 - 25), button_text, fill='white', font=font)

            return screenshot

        except Exception as e:
            logger.error(f"Error highlighting button: {e}")
            return screenshot

    def _create_video_from_screenshots(self):
        """Create MP4 video from screenshots"""
        if not self.current_session or not self.current_session.screenshots:
            return

        try:
            # Get first screenshot for dimensions
            first_screenshot = self.current_session.screenshots[0]
            if not os.path.exists(first_screenshot.image_path):
                return

            # Read first image to get dimensions
            first_image = cv2.imread(first_screenshot.image_path)
            if first_image is None:
                return

            height, width = first_image.shape[:2]

            # Video filename
            video_filename = f"{self.current_session.session_id}.mp4"
            video_path = self.temp_dir / video_filename

            # Create video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            fps = 2  # 2 frames per second
            video_writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))

            # Add all screenshots to video
            for screenshot_record in self.current_session.screenshots:
                if os.path.exists(screenshot_record.image_path):
                    image = cv2.imread(screenshot_record.image_path)
                    if image is not None:
                        # Resize to match dimensions if needed
                        if image.shape[:2] != (height, width):
                            image = cv2.resize(image, (width, height))

                        video_writer.write(image)

            video_writer.release()

            # Store video path
            self.current_session.video_path = str(video_path)
            logger.info(f"Created video: {video_path}")

        except Exception as e:
            logger.error(f"Error creating video: {e}")

    def get_session_list(self) -> List[Dict[str, Any]]:
        """Get list of recording sessions"""
        return [
            {
                'session_id': session.session_id,
                'start_time': session.start_time,
                'end_time': session.end_time,
                'description': session.description,
                'screenshot_count': len(session.screenshots),
                'has_video': bool(session.video_path)
            }
            for session in self.sessions
        ]

    def get_session(self, session_id: str) -> Optional[RecordingSession]:
        """Get a specific recording session"""
        for session in self.sessions:
            if session.session_id == session_id:
                return session
        return None

    def cleanup_old_sessions(self, days: int = 7):
        """Clean up old recording sessions"""
        cutoff_time = datetime.now().timestamp() - (days * 24 * 60 * 60)

        for session in self.sessions[:]:
            try:
                session_time = datetime.fromisoformat(session.start_time).timestamp()
                if session_time < cutoff_time:
                    # Delete files
                    for screenshot in session.screenshots:
                        if os.path.exists(screenshot.image_path):
                            os.remove(screenshot.image_path)

                    if session.video_path and os.path.exists(session.video_path):
                        os.remove(session.video_path)

                    # Remove from list
                    self.sessions.remove(session)
                    logger.info(f"Cleaned up old session: {session.session_id}")

            except Exception as e:
                logger.error(f"Error cleaning up session {session.session_id}: {e}")


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
                'work_left': 0,
                'work_top': 0,
                'work_width': 1920,
                'work_height': 1080,
                'dpi': 96
            })
            self.primary_monitor = self.monitors[0]
            return self.monitors

        try:
            # Get monitor information
            monitor_info = win32api.GetMonitorInfo(win32api.MonitorFromPoint((0, 0)))

            # Get all monitors with improved callback
            try:
                def callback(hmonitor, hdc, rect, data):
                    try:
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
                        logger.debug(f"Detected monitor {monitor['index']}: {monitor['width']}x{monitor['height']} at ({monitor['left']}, {monitor['top']}) - Primary: {monitor['is_primary']}")
                        return True
                    except Exception as e:
                        logger.debug(f"Error processing monitor: {e}")
                        return True

                # Use proper enumeration for all monitors
                win32api.EnumDisplayMonitors(None, None, callback, None)

            except Exception as e:
                logger.error(f"Error enumerating monitors: {e}")
                # Try alternative method
                try:
                    # Fallback: Get monitor at cursor position
                    hmonitor = win32api.MonitorFromPoint((0, 0))
                    info = win32api.GetMonitorInfo(hmonitor)
                    monitor = {
                        'index': 0,
                        'is_primary': True,
                        'left': info['Monitor'][0],
                        'top': info['Monitor'][1],
                        'width': info['Monitor'][2] - info['Monitor'][0],
                        'height': info['Monitor'][3] - info['Monitor'][1],
                        'work_left': info['Work'][0],
                        'work_top': info['Work'][1],
                        'work_width': info['Work'][2] - info['Work'][0],
                        'work_height': info['Work'][3] - info['Work'][1]
                    }
                    self.monitors.append(monitor)
                    self.primary_monitor = monitor
                    logger.info(f"Using fallback monitor detection: {monitor['width']}x{monitor['height']}")
                except Exception as fallback_e:
                    logger.error(f"Fallback monitor detection failed: {fallback_e}")
                    raise e

        except Exception as e:
            logger.error(f"Error detecting monitors: {e}")
            # Fallback to single monitor with work area fields
            self.monitors.append({
                'index': 0,
                'is_primary': True,
                'left': 0,
                'top': 0,
                'width': 1920,
                'height': 1080,
                'work_left': 0,
                'work_top': 0,
                'work_width': 1920,
                'work_height': 1080,
                'dpi': 96
            })
            self.primary_monitor = self.monitors[0]

        return self.monitors

    def get_optimal_position(self, program_name: str = "") -> Dict[str, int]:
        """Get optimal window position for a program"""
        try:
            if len(self.monitors) == 1:
                # Single monitor setup
                monitor = self.monitors[0]
                work_left = monitor.get('work_left', monitor.get('left', 0))
                work_top = monitor.get('work_top', monitor.get('top', 0))
                work_width = monitor.get('work_width', monitor.get('width', 1920))
                work_height = monitor.get('work_height', monitor.get('height', 1080))

                return {
                    'left': work_left + 50,
                    'top': work_top + 50,
                    'width': min(1200, work_width - 100),
                    'height': min(800, work_height - 100)
                }

            # Multi-monitor setup - always use primary monitor for launching
            # Positioning will be handled dynamically by workflows using OpenCV
            monitor = self.primary_monitor or self.monitors[0]

            work_left = monitor.get('work_left', monitor.get('left', 0))
            work_top = monitor.get('work_top', monitor.get('top', 0))
            work_width = monitor.get('work_width', monitor.get('width', 1920))
            work_height = monitor.get('work_height', monitor.get('height', 1080))

            return {
                'left': work_left + 50,
                'top': work_top + 50,
                'width': min(1200, work_width - 100),
                'height': min(800, work_height - 100)
            }
        except Exception as e:
            logger.error(f"Error getting optimal position: {e}")
            # Fallback to safe default position
            return {
                'left': 50,
                'top': 50,
                'width': 1200,
                'height': 800
            }

    def get_monitor_info(self) -> List[Dict[str, Any]]:
        """Get information about all detected monitors"""
        return self.monitors.copy()

    def get_monitor_count(self) -> int:
        """Get the number of detected monitors"""
        return len(self.monitors)

    def detect_monitors_debug(self) -> str:
        """Debug method to get detailed monitor information"""
        try:
            self.detect_monitors()
            info = f"Detected {len(self.monitors)} monitor(s):\n"
            for i, monitor in enumerate(self.monitors):
                info += f"  Monitor {i}: {monitor['width']}x{monitor['height']} at ({monitor['left']}, {monitor['top']})"
                if monitor.get('is_primary'):
                    info += " [PRIMARY]"
                info += "\n"
            return info
        except Exception as e:
            return f"Error detecting monitors: {e}"


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
            elif step.step_type == "click_button":
                return self._click_external_button(step)
            elif step.step_type == "screenshot":
                return self._capture_screenshot(step)
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

            # Capture launch action screenshot if recording is active
            if hasattr(self.main_widget, 'screen_recorder') and self.main_widget.screen_recorder.is_recording:
                try:
                    self.main_widget.capture_button_screenshot(
                        f"Launch {program_info.display_name} (Automation)",
                        None
                    )
                except Exception as e:
                    logger.warning(f"Could not capture launch screenshot: {e}")

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

            # Capture post-launch screenshot if recording is active
            if hasattr(self.main_widget, 'screen_recorder') and self.main_widget.screen_recorder.is_recording:
                try:
                    self.main_widget.capture_button_screenshot(
                        f"{program_info.display_name} Launched (PID: {process.pid})",
                        None
                    )
                except Exception as e:
                    logger.warning(f"Could not capture post-launch screenshot: {e}")

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

        # Capture file opening action if recording is active
        if hasattr(self.main_widget, 'screen_recorder') and self.main_widget.screen_recorder.is_recording:
            try:
                self.main_widget.capture_button_screenshot(
                    f"Opening File: {os.path.basename(step.file_path)} (Automation)",
                    None
                )
            except Exception as e:
                logger.warning(f"Could not capture file open screenshot: {e}")

        try:
            if WINDOWS_SUPPORT:
                os.startfile(step.file_path)
            else:
                opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
                subprocess.call([opener, step.file_path])

            # Capture post-open screenshot if recording is active
            if hasattr(self.main_widget, 'screen_recorder') and self.main_widget.screen_recorder.is_recording:
                try:
                    self.main_widget.capture_button_screenshot(
                        f"File Opened: {os.path.basename(step.file_path)}",
                        None
                    )
                except Exception as e:
                    logger.warning(f"Could not capture post-open screenshot: {e}")

            return True
        except Exception as e:
            logger.error(f"Error opening file {step.file_path}: {e}")
            return False

    def _wait(self, step: AutomationStep) -> bool:
        """Wait for specified time"""
        # Capture wait action if recording is active
        if hasattr(self.main_widget, 'screen_recorder') and self.main_widget.screen_recorder.is_recording:
            try:
                self.main_widget.capture_button_screenshot(
                    f"Waiting {step.wait_time} seconds (Automation)",
                    None
                )
            except Exception as e:
                logger.warning(f"Could not capture wait screenshot: {e}")

        self.msleep(step.wait_time * 1000)

        # Capture post-wait screenshot if recording is active
        if hasattr(self.main_widget, 'screen_recorder') and self.main_widget.screen_recorder.is_recording:
            try:
                self.main_widget.capture_button_screenshot(
                    f"Finished waiting {step.wait_time} seconds",
                    None
                )
            except Exception as e:
                logger.warning(f"Could not capture post-wait screenshot: {e}")

        return True

    def _run_command(self, step: AutomationStep) -> bool:
        """Execute a system command"""
        # Capture command execution if recording is active
        if hasattr(self.main_widget, 'screen_recorder') and self.main_widget.screen_recorder.is_recording:
            try:
                self.main_widget.capture_button_screenshot(
                    f"Running Command: {step.command[:50]}... (Automation)",
                    None
                )
            except Exception as e:
                logger.warning(f"Could not capture command screenshot: {e}")

        try:
            result = subprocess.run(
                step.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=step.parameters.get('timeout', 30)
            )

            # Capture command result if recording is active
            if hasattr(self.main_widget, 'screen_recorder') and self.main_widget.screen_recorder.is_recording:
                try:
                    status = "Success" if result.returncode == 0 else f"Failed (Exit: {result.returncode})"
                    self.main_widget.capture_button_screenshot(
                        f"Command {status}: {step.command[:30]}...",
                        None
                    )
                except Exception as e:
                    logger.warning(f"Could not capture command result screenshot: {e}")

            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.error(f"Command timeout: {step.command}")

            # Capture timeout if recording is active
            if hasattr(self.main_widget, 'screen_recorder') and self.main_widget.screen_recorder.is_recording:
                try:
                    self.main_widget.capture_button_screenshot(
                        f"Command Timeout: {step.command[:30]}...",
                        None
                    )
                except Exception as e:
                    logger.warning(f"Could not capture timeout screenshot: {e}")

            return False
        except Exception as e:
            logger.error(f"Error running command: {e}")

            # Capture error if recording is active
            if hasattr(self.main_widget, 'screen_recorder') and self.main_widget.screen_recorder.is_recording:
                try:
                    self.main_widget.capture_button_screenshot(
                        f"Command Error: {step.command[:30]}...",
                        None
                    )
                except Exception as ex:
                    logger.warning(f"Could not capture error screenshot: {ex}")

            return False

    def _click_external_button(self, step: AutomationStep) -> bool:
        """Click a button in an external application"""
        if not SCREEN_RECORDING_SUPPORT:
            logger.warning("PyAutoGUI not available for external button clicking")
            return False

        try:
            # Capture pre-click screenshot if recording is active
            if hasattr(self.main_widget, 'screen_recorder') and self.main_widget.screen_recorder.is_recording:
                self.main_widget.capture_button_screenshot(
                    f"About to click: {step.button_text or 'external button'}",
                    None
                )

            # Determine button position
            if step.button_position:
                # Use specified position
                x = step.button_position.get('x', 0)
                y = step.button_position.get('y', 0)
            elif step.button_text:
                # Try to find button by text using image recognition (basic)
                x, y = self._find_button_by_text(step.button_text)
                if x is None or y is None:
                    logger.warning(f"Could not find button with text: {step.button_text}")
                    return False
            else:
                logger.error("No button position or text specified")
                return False

            # Move cursor and click
            pyautogui.moveTo(x, y, duration=0.5)
            pyautogui.click()

            # Capture post-click screenshot if recording is active
            if hasattr(self.main_widget, 'screen_recorder') and self.main_widget.screen_recorder.is_recording:
                # Create a button position dict for highlighting
                button_pos = {
                    'x': x - 50,
                    'y': y - 15,
                    'width': 100,
                    'height': 30
                }
                self.main_widget.screen_recorder.capture_button_screenshot(
                    step.button_text or f"Button at ({x}, {y})",
                    button_pos,
                    f"Clicked external button: {step.button_text}"
                )

            logger.info(f"Clicked external button at ({x}, {y}): {step.button_text}")
            return True

        except Exception as e:
            logger.error(f"Error clicking external button: {e}")
            return False

    def _capture_screenshot(self, step: AutomationStep) -> bool:
        """Capture a screenshot with description"""
        if not SCREEN_RECORDING_SUPPORT:
            logger.warning("Screenshot capture not available")
            return False

        try:
            description = step.screenshot_description or step.description or "Screenshot captured"

            # Capture screenshot
            screenshot = pyautogui.screenshot()

            # Save screenshot if recording is active
            if hasattr(self.main_widget, 'screen_recorder') and self.main_widget.screen_recorder.is_recording:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
                filename = f"manual_screenshot_{timestamp}.png"
                filepath = self.main_widget.screen_recorder.temp_dir / filename
                screenshot.save(filepath)

                # Create screenshot record
                record = ScreenshotRecord(
                    timestamp=datetime.now().isoformat(),
                    image_path=str(filepath),
                    button_text="Manual Screenshot",
                    button_position={},
                    action_description=description,
                    window_title=""
                )

                self.main_widget.screen_recorder.current_session.screenshots.append(record)
                logger.info(f"Manual screenshot saved: {filepath}")

            logger.info(f"Captured screenshot: {description}")
            return True

        except Exception as e:
            logger.error(f"Error capturing screenshot: {e}")
            return False

    def _find_button_by_text(self, button_text: str) -> Tuple[Optional[int], Optional[int]]:
        """Find button position by text using basic image recognition"""
        try:
            # Take a screenshot to search in
            screenshot = pyautogui.screenshot()

            # Convert to numpy array for OpenCV processing
            screenshot_array = np.array(screenshot)
            screenshot_gray = cv2.cvtColor(screenshot_array, cv2.COLOR_RGB2GRAY)

            # Try to use OpenCV's template matching (basic implementation)
            # This is a simplified approach - in practice, you'd need more sophisticated OCR
            # or template matching for reliable button detection

            # For now, return center of screen as fallback
            screen_width, screen_height = pyautogui.size()
            center_x = screen_width // 2
            center_y = screen_height // 2

            logger.warning(f"Button text search not fully implemented, using center screen: ({center_x}, {center_y})")
            return center_x, center_y

        except Exception as e:
            logger.error(f"Error finding button by text: {e}")
            return None, None

    def stop(self):
        """Stop the automation execution"""
        self.is_running = False


class PetroleumLauncherWidget(QWidget):
    """Main widget for the Petroleum Program Launcher module"""

    # Signals for thread-safe UI updates
    detection_completed = pyqtSignal()
    detection_status = pyqtSignal(str)
    program_detected = pyqtSignal(str, dict)  # program_key, program_info

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.window_manager = WindowManager()
        self.detected_programs: Dict[str, ProgramInfo] = {}
        self.workflows: Dict[str, Workflow] = {}
        self.automation_engine: Optional[AutomationEngine] = None
        self.screen_recorder = ScreenRecorder()

        # Initialize configuration manager
        self.config_manager = PetroleumProgramConfigManager()

        # Initialize UI first
        self.initUI()

        # Apply responsive scaling
        self.apply_responsive_scaling()

        # Load saved data after UI is created
        self.load_configuration()

        # Connect signals for thread-safe UI updates
        self.detection_completed.connect(self.on_detection_completed)
        self.detection_status.connect(self.on_detection_status)
        self.program_detected.connect(self.on_program_detected)

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

        # Status label with monitor info
        monitor_count = self.window_manager.get_monitor_count()
        self.status_label = QLabel(f"Ready - Detected {monitor_count} monitor(s)")
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

        # Recording tab
        if SCREEN_RECORDING_SUPPORT:
            recording_tab = self.create_recording_tab()
            self.tab_widget.addTab(recording_tab, "Recording")

        # Workflow Studio tab - Integrated creation experience
        if SCREEN_RECORDING_SUPPORT:
            workflow_studio_tab = self.create_workflow_studio_tab()
            self.tab_widget.addTab(workflow_studio_tab, "Workflow Studio")

        return left_panel

    def create_programs_tab(self) -> QWidget:
        """Create the programs tab"""
        programs_tab = QWidget()
        layout = QVBoxLayout(programs_tab)

        # Configuration dropdown menu
        config_dropdown = QComboBox()
        config_dropdown.addItem("⚙️ Configuration Options")
        config_dropdown.setStyleSheet("""
            QComboBox {
                padding: 8px;
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 4px;
                background: white;
                min-width: 200px;
            }
            QComboBox:hover {
                border-color: #007acc;
            }
        """)

        # Configuration menu items
        config_dropdown.addItem("🔄 Refresh Programs")
        config_dropdown.addItem("📂 Load Configuration File")
        config_dropdown.addItem("💾 Save Configuration")
        config_dropdown.addItem("📤 Export Configuration")
        config_dropdown.addItem("➕ Add from Uninstaller Data")
        config_dropdown.addItem("🗑️ Clear All Programs")

        config_dropdown.currentIndexChanged.connect(self.handle_config_action)
        layout.addWidget(config_dropdown)

        # Help message for empty configuration
        self.no_programs_label = QLabel(
            "No programs configured yet. Use the configuration dropdown above to add programs:\n"
            "• 'Add from Uninstaller Data' - Paste uninstaller registry data\n"
            "• 'Load Configuration File' - Import existing configuration"
        )
        self.no_programs_label.setWordWrap(True)
        self.no_programs_label.setStyleSheet("QLabel { color: #666; font-style: italic; padding: 20px; }")
        self.no_programs_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.no_programs_label)

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

        template_btn = QPushButton("Petroleum Templates")
        template_btn.clicked.connect(self.show_petroleum_templates)
        buttons_layout.addWidget(template_btn)

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

    def create_recording_tab(self) -> QWidget:
        """Create the recording tab"""
        recording_tab = QWidget()
        layout = QVBoxLayout(recording_tab)

        # Recording status
        status_group = QGroupBox("Recording Status")
        status_layout = QVBoxLayout(status_group)

        self.recording_status_label = QLabel("Not Recording")
        self.recording_status_label.setStyleSheet("color: red; font-weight: bold;")
        status_layout.addWidget(self.recording_status_label)

        self.recording_session_label = QLabel("No active session")
        status_layout.addWidget(self.recording_session_label)

        layout.addWidget(status_group)

        # Recording controls
        controls_group = QGroupBox("Recording Controls")
        controls_layout = QVBoxLayout(controls_group)

        # Session description
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Session Description:"))
        self.recording_description_edit = QLineEdit()
        self.recording_description_edit.setPlaceholderText("Enter description for this recording session")
        desc_layout.addWidget(self.recording_description_edit)
        controls_layout.addLayout(desc_layout)

        # Recording mode selection
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Recording Mode:"))

        self.recording_mode_combo = QComboBox()
        self.recording_mode_combo.addItems(["Manual Screenshots", "Automation Recording"])
        self.recording_mode_combo.currentTextChanged.connect(self.on_recording_mode_changed)
        mode_layout.addWidget(self.recording_mode_combo)

        controls_layout.addLayout(mode_layout)

        # Control buttons
        buttons_layout = QHBoxLayout()

        self.start_recording_btn = QPushButton("Start Recording")
        self.start_recording_btn.clicked.connect(self.start_recording)
        buttons_layout.addWidget(self.start_recording_btn)

        self.stop_recording_btn = QPushButton("Stop Recording")
        self.stop_recording_btn.clicked.connect(self.stop_recording)
        self.stop_recording_btn.setEnabled(False)
        buttons_layout.addWidget(self.stop_recording_btn)

        self.test_script_btn = QPushButton("Test Script")
        self.test_script_btn.clicked.connect(self.test_automation_script)
        self.test_script_btn.setEnabled(False)
        buttons_layout.addWidget(self.test_script_btn)

        self.export_script_btn = QPushButton("Export Script")
        self.export_script_btn.clicked.connect(self.export_automation_script)
        self.export_script_btn.setEnabled(False)
        buttons_layout.addWidget(self.export_script_btn)

        # Drag and drop recording button
        self.drag_drop_recorder_btn = QPushButton("Drag & Drop Record")
        self.drag_drop_recorder_btn.clicked.connect(self.open_drag_drop_recorder)
        self.drag_drop_recorder_btn.setStyleSheet("QPushButton { background-color: #17a2b8; color: white; font-weight: bold; }")
        buttons_layout.addWidget(self.drag_drop_recorder_btn)

        # Conditional recording button
        self.conditional_recorder_btn = QPushButton("Conditional Logic")
        self.conditional_recorder_btn.clicked.connect(self.open_conditional_recorder)
        self.conditional_recorder_btn.setStyleSheet("QPushButton { background-color: #6f42c1; color: white; font-weight: bold; }")
        buttons_layout.addWidget(self.conditional_recorder_btn)

        controls_layout.addLayout(buttons_layout)

        # Auto-capture buttons setting
        self.auto_capture_check = QCheckBox("Auto-capture screenshots on button clicks")
        self.auto_capture_check.setChecked(True)
        controls_layout.addWidget(self.auto_capture_check)

        layout.addWidget(controls_group)

        # Sessions list
        sessions_group = QGroupBox("Recording Sessions")
        sessions_layout = QVBoxLayout(sessions_group)

        self.sessions_tree = QTreeWidget()
        self.sessions_tree.setHeaderLabels(["Session", "Date", "Screenshots", "Video"])
        self.sessions_tree.itemDoubleClicked.connect(self.on_session_double_click)

        # Set column widths
        self.sessions_tree.setColumnWidth(0, 150)  # Session ID
        self.sessions_tree.setColumnWidth(1, 120)  # Date
        self.sessions_tree.setColumnWidth(2, 80)   # Screenshots
        self.sessions_tree.setColumnWidth(3, 60)   # Video

        self.sessions_tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.sessions_tree.header().setStretchLastSection(True)

        sessions_layout.addWidget(self.sessions_tree)

        # Session actions
        session_actions_layout = QHBoxLayout()

        self.review_session_btn = QPushButton("Review Session")
        self.review_session_btn.clicked.connect(self.review_selected_session)
        session_actions_layout.addWidget(self.review_session_btn)

        self.play_video_btn = QPushButton("Play Video")
        self.play_video_btn.clicked.connect(self.play_session_video)
        session_actions_layout.addWidget(self.play_video_btn)

        self.delete_session_btn = QPushButton("Delete Session")
        self.delete_session_btn.clicked.connect(self.delete_selected_session)
        session_actions_layout.addWidget(self.delete_session_btn)

        self.cleanup_btn = QPushButton("Cleanup Old")
        self.cleanup_btn.clicked.connect(self.cleanup_old_sessions)
        session_actions_layout.addWidget(self.cleanup_btn)

        self.convert_to_workflow_btn = QPushButton("Convert to Workflow")
        self.convert_to_workflow_btn.clicked.connect(self.convert_session_to_workflow)
        session_actions_layout.addWidget(self.convert_to_workflow_btn)

        sessions_layout.addLayout(session_actions_layout)

        layout.addWidget(sessions_group)

        # Update sessions list
        self.update_sessions_ui()

        return recording_tab

    def create_workflow_studio_tab(self) -> QWidget:
        """Create the integrated workflow studio tab"""
        studio_tab = QWidget()
        layout = QVBoxLayout(studio_tab)

        # Header with title and description
        header_layout = QHBoxLayout()

        title_label = QLabel("🎯 Workflow Studio")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # Mode selector
        mode_label = QLabel("Creation Mode:")
        header_layout.addWidget(mode_label)

        self.creation_mode_combo = QComboBox()
        self.creation_mode_combo.addItems([
            "Manual Builder",
            "Screen Recording",
            "Drag & Drop",
            "Conditional Logic",
            "Hybrid Mode"
        ])
        self.creation_mode_combo.currentTextChanged.connect(self.on_creation_mode_changed)
        header_layout.addWidget(self.creation_mode_combo)

        layout.addLayout(header_layout)

        # Description
        desc_label = QLabel(
            "Integrated workflow creation studio. Combine manual building with intelligent recording capabilities "
            "to create powerful, adaptive automation workflows for petroleum software."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #6c757d; font-style: italic; margin-bottom: 15px;")
        layout.addWidget(desc_label)

        # Main content area with splitter
        main_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(main_splitter)

        # Left panel - Creation tools
        left_panel = QWidget()
        left_panel.setMaximumWidth(400)
        left_layout = QVBoxLayout(left_panel)

        # Creation tools group
        tools_group = QGroupBox("Creation Tools")
        tools_layout = QVBoxLayout(tools_group)

        # Recording controls
        recording_controls_layout = QHBoxLayout()
        recording_controls_layout.addWidget(QLabel("Recording:"))

        self.start_studio_recording_btn = QPushButton("Start Recording")
        self.start_studio_recording_btn.clicked.connect(self.start_studio_recording)
        self.start_studio_recording_btn.setStyleSheet("QPushButton { background-color: #28a745; color: white; font-weight: bold; padding: 5px; }")
        recording_controls_layout.addWidget(self.start_studio_recording_btn)

        self.stop_studio_recording_btn = QPushButton("Stop")
        self.stop_studio_recording_btn.clicked.connect(self.stop_studio_recording)
        self.stop_studio_recording_btn.setEnabled(False)
        self.stop_studio_recording_btn.setStyleSheet("QPushButton { background-color: #dc3545; color: white; font-weight: bold; padding: 5px; }")
        recording_controls_layout.addWidget(self.stop_studio_recording_btn)

        tools_layout.addLayout(recording_controls_layout)

        # Advanced recording options
        advanced_layout = QHBoxLayout()

        self.drag_drop_studio_btn = QPushButton("Drag & Drop")
        self.drag_drop_studio_btn.clicked.connect(self.open_studio_drag_drop)
        self.drag_drop_studio_btn.setStyleSheet("QPushButton { background-color: #17a2b8; color: white; font-weight: bold; padding: 5px; }")
        advanced_layout.addWidget(self.drag_drop_studio_btn)

        self.conditional_studio_btn = QPushButton("Conditional")
        self.conditional_studio_btn.clicked.connect(self.open_studio_conditional)
        self.conditional_studio_btn.setStyleSheet("QPushButton { background-color: #6f42c1; color: white; font-weight: bold; padding: 5px; }")
        advanced_layout.addWidget(self.conditional_studio_btn)

        tools_layout.addLayout(advanced_layout)

        # Manual step creation
        manual_group = QGroupBox("Manual Step Creation")
        manual_layout = QVBoxLayout(manual_group)

        # Step type selector
        step_type_layout = QHBoxLayout()
        step_type_layout.addWidget(QLabel("Step Type:"))

        self.studio_step_type_combo = QComboBox()
        self.studio_step_type_combo.addItems([
            "Click", "Input Text", "Wait", "Launch Program",
            "Screenshot", "Conditional", "Loop", "Custom Script"
        ])
        step_type_layout.addWidget(self.studio_step_type_combo)
        manual_layout.addLayout(step_type_layout)

        # Add step button
        self.add_manual_step_btn = QPushButton("+ Add Step")
        self.add_manual_step_btn.clicked.connect(self.add_manual_studio_step)
        self.add_manual_step_btn.setStyleSheet("QPushButton { background-color: #007bff; color: white; font-weight: bold; padding: 8px; }")
        manual_layout.addWidget(self.add_manual_step_btn)

        tools_layout.addWidget(manual_group)
        left_layout.addWidget(tools_group)

        # Workflow preview
        preview_group = QGroupBox("Workflow Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.studio_workflow_list = QListWidget()
        self.studio_workflow_list.setMinimumHeight(200)
        self.studio_workflow_list.itemSelectionChanged.connect(self.on_studio_step_selection_changed)
        preview_layout.addWidget(self.studio_workflow_list)

        # Step actions
        step_actions_layout = QHBoxLayout()

        self.edit_studio_step_btn = QPushButton("Edit")
        self.edit_studio_step_btn.clicked.connect(self.edit_studio_step)
        self.edit_studio_step_btn.setEnabled(False)
        step_actions_layout.addWidget(self.edit_studio_step_btn)

        self.remove_studio_step_btn = QPushButton("Remove")
        self.remove_studio_step_btn.clicked.connect(self.remove_studio_step)
        self.remove_studio_step_btn.setEnabled(False)
        step_actions_layout.addWidget(self.remove_studio_step_btn)

        step_actions_layout.addStretch()
        preview_layout.addLayout(step_actions_layout)

        left_layout.addWidget(preview_group)

        left_panel.setLayout(left_layout)
        main_splitter.addWidget(left_panel)

        # Right panel - Workflow details and configuration
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Workflow configuration
        config_group = QGroupBox("Workflow Configuration")
        config_layout = QFormLayout(config_group)

        self.studio_workflow_name_edit = QLineEdit()
        self.studio_workflow_name_edit.setPlaceholderText("Enter workflow name...")
        config_layout.addRow("Workflow Name:", self.studio_workflow_name_edit)

        self.studio_workflow_desc_edit = QTextEdit()
        self.studio_workflow_desc_edit.setMaximumHeight(60)
        self.studio_workflow_desc_edit.setPlaceholderText("Enter workflow description...")
        config_layout.addRow("Description:", self.studio_workflow_desc_edit)

        # Software selector
        software_layout = QHBoxLayout()
        self.studio_software_combo = QComboBox()
        self.studio_software_combo.addItems([
            "Petrel", "Harmony Enterprise", "Kappa", "CMG",
            "Petroleum Experts", "TNavigator", "Multiple"
        ])
        software_layout.addWidget(self.studio_software_combo)

        self.studio_difficulty_combo = QComboBox()
        self.studio_difficulty_combo.addItems(["Beginner", "Intermediate", "Advanced"])
        software_layout.addWidget(self.studio_difficulty_combo)

        config_layout.addRow("Target Software:", software_layout)

        right_layout.addWidget(config_group)

        # Intelligent suggestions
        suggestions_group = QGroupBox("Intelligent Suggestions")
        suggestions_layout = QVBoxLayout(suggestions_group)

        self.studio_suggestions_list = QListWidget()
        self.studio_suggestions_list.setMaximumHeight(120)
        suggestions_layout.addWidget(self.studio_suggestions_list)

        self.apply_suggestion_btn = QPushButton("Apply Selected Suggestion")
        self.apply_suggestion_btn.clicked.connect(self.apply_studio_suggestion)
        suggestions_layout.addWidget(self.apply_suggestion_btn)

        right_layout.addWidget(suggestions_group)

        # Recording status
        status_group = QGroupBox("Recording Status")
        status_layout = QVBoxLayout(status_group)

        self.studio_status_label = QLabel("Status: Ready to create workflow")
        self.studio_status_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: #f8f9fa; border: 1px solid #dee2e6;")
        status_layout.addWidget(self.studio_status_label)

        self.studio_recording_indicator = QLabel("⏸ Not Recording")
        self.studio_recording_indicator.setStyleSheet("color: #6c757d; font-weight: bold; font-size: 14px; padding: 10px; background-color: #e9ecef; border-radius: 5px; text-align: center;")
        self.studio_recording_indicator.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.studio_recording_indicator)

        right_layout.addWidget(status_group)

        # Workflow actions
        actions_group = QGroupBox("Workflow Actions")
        actions_layout = QVBoxLayout(actions_group)

        actions_buttons_layout1 = QHBoxLayout()

        self.preview_workflow_btn = QPushButton("Preview Workflow")
        self.preview_workflow_btn.clicked.connect(self.preview_studio_workflow)
        actions_buttons_layout1.addWidget(self.preview_workflow_btn)

        self.test_workflow_btn = QPushButton("Test Workflow")
        self.test_workflow_btn.clicked.connect(self.test_studio_workflow)
        actions_buttons_layout1.addWidget(self.test_workflow_btn)

        actions_layout.addLayout(actions_buttons_layout1)

        actions_buttons_layout2 = QHBoxLayout()

        self.save_workflow_btn = QPushButton("💾 Save Workflow")
        self.save_workflow_btn.clicked.connect(self.save_studio_workflow)
        self.save_workflow_btn.setStyleSheet("QPushButton { background-color: #28a745; color: white; font-weight: bold; padding: 8px; }")
        actions_buttons_layout2.addWidget(self.save_workflow_btn)

        self.export_workflow_btn = QPushButton("📤 Export")
        self.export_workflow_btn.clicked.connect(self.export_studio_workflow)
        actions_buttons_layout2.addWidget(self.export_workflow_btn)

        actions_layout.addLayout(actions_buttons_layout2)

        right_layout.addWidget(actions_group)

        right_panel.setLayout(right_layout)
        main_splitter.addWidget(right_panel)

        # Set splitter proportions
        main_splitter.setSizes([400, 600])

        # Initialize studio data
        self.studio_workflow_steps = []
        self.studio_recording_mode = None
        self.studio_active_recorders = {}

        return studio_tab

    # Workflow Studio Methods
    def on_creation_mode_changed(self, mode: str):
        """Handle creation mode change"""
        try:
            self.studio_recording_mode = mode
            self.studio_status_label.setText(f"Status: Mode changed to {mode}")

            # Update UI based on mode
            if mode == "Manual Builder":
                self.start_studio_recording_btn.setEnabled(False)
                self.drag_drop_studio_btn.setEnabled(True)
                self.conditional_studio_btn.setEnabled(True)
                self.add_manual_step_btn.setEnabled(True)
            elif mode == "Screen Recording":
                self.start_studio_recording_btn.setEnabled(True)
                self.drag_drop_studio_btn.setEnabled(False)
                self.conditional_studio_btn.setEnabled(False)
                self.add_manual_step_btn.setEnabled(False)
            elif mode == "Drag & Drop":
                self.start_studio_recording_btn.setEnabled(False)
                self.drag_drop_studio_btn.setEnabled(True)
                self.conditional_studio_btn.setEnabled(False)
                self.add_manual_step_btn.setEnabled(True)
            elif mode == "Conditional Logic":
                self.start_studio_recording_btn.setEnabled(False)
                self.drag_drop_studio_btn.setEnabled(False)
                self.conditional_studio_btn.setEnabled(True)
                self.add_manual_step_btn.setEnabled(True)
            elif mode == "Hybrid Mode":
                self.start_studio_recording_btn.setEnabled(True)
                self.drag_drop_studio_btn.setEnabled(True)
                self.conditional_studio_btn.setEnabled(True)
                self.add_manual_step_btn.setEnabled(True)

            # Generate suggestions based on mode
            self.generate_studio_suggestions(mode)

            logger.info(f"Changed creation mode to: {mode}")

        except Exception as e:
            logger.error(f"Error changing creation mode: {e}")

    def start_studio_recording(self):
        """Start recording in the studio"""
        try:
            if self.studio_recording_mode in ["Screen Recording", "Hybrid Mode"]:
                # Start automation recording
                session_id = self.screen_recorder.automation_recorder.start_recording(
                    f"studio_recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
                self.studio_active_recorders['automation'] = session_id

            # Update UI
            self.start_studio_recording_btn.setEnabled(False)
            self.stop_studio_recording_btn.setEnabled(True)
            self.studio_recording_indicator.setText("🔴 Recording...")
            self.studio_recording_indicator.setStyleSheet("color: #dc3545; font-weight: bold; font-size: 14px; padding: 10px; background-color: #f8d7da; border-radius: 5px; text-align: center;")
            self.studio_status_label.setText("Status: Recording in progress - Perform actions in petroleum software")

            logger.info(f"Started studio recording in mode: {self.studio_recording_mode}")

        except Exception as e:
            logger.error(f"Error starting studio recording: {e}")
            QMessageBox.critical(self, "Recording Error", f"Failed to start recording: {e}")

    def stop_studio_recording(self):
        """Stop recording in the studio"""
        try:
            recorded_steps = []

            # Stop automation recording if active
            if 'automation' in self.studio_active_recorders:
                session = self.screen_recorder.automation_recorder.stop_recording()
                if session and session.automation_actions:
                    # Convert automation actions to workflow steps
                    for i, action in enumerate(session.automation_actions):
                        step = WorkflowStep(
                            step_number=len(self.studio_workflow_steps) + i + 1,
                            action_type=action.action_type,
                            description=action.description,
                            target_element=action.description,
                            position=action.position,
                            wait_time=action.wait_time or 2.0,
                            optional=False,
                            screenshot_path=action.screenshot_path
                        )
                        recorded_steps.append(step)

                del self.studio_active_recorders['automation']

            # Add recorded steps to workflow
            self.studio_workflow_steps.extend(recorded_steps)
            self.update_studio_workflow_list()

            # Update UI
            self.start_studio_recording_btn.setEnabled(True)
            self.stop_studio_recording_btn.setEnabled(False)
            self.studio_recording_indicator.setText("⏸ Not Recording")
            self.studio_recording_indicator.setStyleSheet("color: #6c757d; font-weight: bold; font-size: 14px; padding: 10px; background-color: #e9ecef; border-radius: 5px; text-align: center;")
            self.studio_status_label.setText(f"Status: Recording stopped - {len(recorded_steps)} steps captured")

            # Generate suggestions based on recorded steps
            self.generate_recording_suggestions(recorded_steps)

            logger.info(f"Stopped studio recording - captured {len(recorded_steps)} steps")

        except Exception as e:
            logger.error(f"Error stopping studio recording: {e}")
            QMessageBox.critical(self, "Recording Error", f"Failed to stop recording: {e}")

    def open_studio_drag_drop(self):
        """Open drag-and-drop recorder in studio mode"""
        try:
            dialog = QDialog(self)
            dialog.setWindowTitle("Studio Drag & Drop Recorder")
            dialog.setModal(False)
            dialog.resize(500, 700)

            layout = QVBoxLayout(dialog)

            # Create drag-drop recorder
            recorder = DragDropRecorder(dialog)

            # Connect signal
            recorder.element_captured.connect(lambda element: self.on_studio_element_captured(element, dialog))

            layout.addWidget(recorder)

            # Buttons
            button_layout = QHBoxLayout()

            add_to_workflow_btn = QPushButton("Add to Workflow")
            add_to_workflow_btn.clicked.connect(lambda: self.add_drag_drop_elements_to_workflow(recorder, dialog))
            button_layout.addWidget(add_to_workflow_btn)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.close)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

            dialog.show()
            self.studio_status_label.setText("Status: Drag & Drop recorder opened")

        except Exception as e:
            logger.error(f"Error opening studio drag-drop recorder: {e}")
            QMessageBox.critical(self, "Recorder Error", f"Failed to open drag-drop recorder: {e}")

    def open_studio_conditional(self):
        """Open conditional recorder in studio mode"""
        try:
            dialog = QDialog(self)
            dialog.setWindowTitle("Studio Conditional Logic Recorder")
            dialog.setModal(False)
            dialog.resize(600, 750)

            layout = QVBoxLayout(dialog)

            # Create conditional recorder
            recorder = ConditionalRecorder(dialog)

            # Connect signals
            recorder.condition_detected.connect(lambda condition: self.on_studio_condition_detected(condition, dialog))
            recorder.branch_created.connect(lambda branch: self.on_studio_branch_created(branch, dialog))

            layout.addWidget(recorder)

            # Buttons
            button_layout = QHBoxLayout()

            add_conditions_btn = QPushButton("Add Conditions to Workflow")
            add_conditions_btn.clicked.connect(lambda: self.add_conditional_logic_to_workflow(recorder, dialog))
            button_layout.addWidget(add_conditions_btn)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.close)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

            dialog.show()
            self.studio_status_label.setText("Status: Conditional logic recorder opened")

        except Exception as e:
            logger.error(f"Error opening studio conditional recorder: {e}")
            QMessageBox.critical(self, "Recorder Error", f"Failed to open conditional recorder: {e}")

    def add_manual_studio_step(self):
        """Add a manual step to the workflow"""
        try:
            step_type = self.studio_step_type_combo.currentText()

            # Create step based on type
            if step_type == "Click":
                step = self.create_click_step()
            elif step_type == "Input Text":
                step = self.create_input_text_step()
            elif step_type == "Wait":
                step = self.create_wait_step()
            elif step_type == "Launch Program":
                step = self.create_launch_step()
            elif step_type == "Screenshot":
                step = self.create_screenshot_step()
            elif step_type == "Conditional":
                step = self.create_conditional_step()
            elif step_type == "Loop":
                step = self.create_loop_step()
            elif step_type == "Custom Script":
                step = self.create_custom_script_step()
            else:
                step = WorkflowStep(
                    step_number=len(self.studio_workflow_steps) + 1,
                    action_type="custom",
                    description=f"Custom {step_type} step",
                    target_element="custom",
                    position={"x": 0, "y": 0},
                    wait_time=2.0,
                    optional=False
                )

            self.studio_workflow_steps.append(step)
            self.update_studio_workflow_list()
            self.studio_status_label.setText(f"Status: Added {step_type} step to workflow")

        except Exception as e:
            logger.error(f"Error adding manual step: {e}")
            QMessageBox.warning(self, "Step Error", f"Failed to add step: {e}")

    def create_click_step(self) -> WorkflowStep:
        """Create a click step with user input"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Click Step")
        dialog.setModal(True)
        dialog.resize(400, 300)

        layout = QVBoxLayout(dialog)

        # Description
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        desc_edit = QLineEdit("Click button")
        desc_layout.addWidget(desc_edit)
        layout.addLayout(desc_layout)

        # Position
        pos_layout = QHBoxLayout()
        pos_layout.addWidget(QLabel("Position (x, y):"))
        x_edit = QLineEdit("100")
        y_edit = QLineEdit("100")
        pos_layout.addWidget(x_edit)
        pos_layout.addWidget(y_edit)
        layout.addLayout(pos_layout)

        # Wait time
        wait_layout = QHBoxLayout()
        wait_layout.addWidget(QLabel("Wait time (s):"))
        wait_spin = QDoubleSpinBox()
        wait_spin.setRange(0.1, 60.0)
        wait_spin.setValue(2.0)
        wait_spin.setSingleStep(0.5)
        wait_layout.addWidget(wait_spin)
        layout.addLayout(wait_layout)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("Add")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QDialog.Accepted:
            return WorkflowStep(
                step_number=len(self.studio_workflow_steps) + 1,
                action_type="click",
                description=desc_edit.text(),
                target_element=desc_edit.text(),
                position={"x": int(x_edit.text()), "y": int(y_edit.text())},
                wait_time=wait_spin.value(),
                optional=False
            )
        else:
            return None

    def create_input_text_step(self) -> WorkflowStep:
        """Create an input text step with user input"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Input Text Step")
        dialog.setModal(True)
        dialog.resize(400, 350)

        layout = QVBoxLayout(dialog)

        # Description
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        desc_edit = QLineEdit("Input text")
        desc_layout.addWidget(desc_edit)
        layout.addLayout(desc_layout)

        # Text to input
        text_layout = QHBoxLayout()
        text_layout.addWidget(QLabel("Text to input:"))
        text_edit = QLineEdit()
        text_layout.addWidget(text_edit)
        layout.addLayout(text_layout)

        # Target element
        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Target element:"))
        target_edit = QLineEdit("Text field")
        target_layout.addWidget(target_edit)
        layout.addLayout(target_layout)

        # Wait time
        wait_layout = QHBoxLayout()
        wait_layout.addWidget(QLabel("Wait time (s):"))
        wait_spin = QDoubleSpinBox()
        wait_spin.setRange(0.1, 60.0)
        wait_spin.setValue(2.0)
        wait_spin.setSingleStep(0.5)
        wait_layout.addWidget(wait_spin)
        layout.addLayout(wait_layout)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("Add")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QDialog.Accepted:
            return WorkflowStep(
                step_number=len(self.studio_workflow_steps) + 1,
                action_type="input_text",
                description=desc_edit.text(),
                target_element=target_edit.text(),
                position={"x": 0, "y": 0},
                wait_time=wait_spin.value(),
                optional=False,
                text_to_input=text_edit.text()
            )
        else:
            return None

    def create_wait_step(self) -> WorkflowStep:
        """Create a wait step with user input"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Wait Step")
        dialog.setModal(True)
        dialog.resize(350, 200)

        layout = QVBoxLayout(dialog)

        # Description
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        desc_edit = QLineEdit("Wait for process")
        desc_layout.addWidget(desc_edit)
        layout.addLayout(desc_layout)

        # Wait time
        wait_layout = QHBoxLayout()
        wait_layout.addWidget(QLabel("Wait time (s):"))
        wait_spin = QDoubleSpinBox()
        wait_spin.setRange(0.1, 300.0)
        wait_spin.setValue(5.0)
        wait_spin.setSingleStep(1.0)
        wait_layout.addWidget(wait_spin)
        layout.addLayout(wait_layout)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("Add")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QDialog.Accepted:
            return WorkflowStep(
                step_number=len(self.studio_workflow_steps) + 1,
                action_type="wait",
                description=desc_edit.text(),
                target_element="wait",
                position={"x": 0, "y": 0},
                wait_time=wait_spin.value(),
                optional=False
            )
        else:
            return None

    def create_launch_step(self) -> WorkflowStep:
        """Create a launch program step with user input"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Launch Program Step")
        dialog.setModal(True)
        dialog.resize(450, 400)

        layout = QVBoxLayout(dialog)

        # Description
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        desc_edit = QLineEdit("Launch program")
        desc_layout.addWidget(desc_edit)
        layout.addLayout(desc_layout)

        # Program selection
        program_layout = QHBoxLayout()
        program_layout.addWidget(QLabel("Program:"))
        program_combo = QComboBox()
        program_combo.addItems([prog.name for prog in PETROLEUM_PROGRAMS])
        program_layout.addWidget(program_combo)
        layout.addLayout(program_layout)

        # File path
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("File path (optional):"))
        file_edit = QLineEdit()
        file_layout.addWidget(file_edit)
        layout.addLayout(file_layout)

        # Parameters
        params_layout = QHBoxLayout()
        params_layout.addWidget(QLabel("Parameters (optional):"))
        params_edit = QLineEdit()
        params_layout.addWidget(params_edit)
        layout.addLayout(params_layout)

        # Wait time
        wait_layout = QHBoxLayout()
        wait_layout.addWidget(QLabel("Wait time (s):"))
        wait_spin = QDoubleSpinBox()
        wait_spin.setRange(1.0, 60.0)
        wait_spin.setValue(5.0)
        wait_spin.setSingleStep(1.0)
        wait_layout.addWidget(wait_spin)
        layout.addLayout(wait_layout)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("Add")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QDialog.Accepted:
            return WorkflowStep(
                step_number=len(self.studio_workflow_steps) + 1,
                action_type="launch",
                description=desc_edit.text(),
                target_element=program_combo.currentText(),
                position={"x": 0, "y": 0},
                wait_time=wait_spin.value(),
                optional=False,
                program_name=program_combo.currentText(),
                file_path=file_edit.text(),
                command=program_combo.currentText(),
                parameters={"file": file_edit.text(), "args": params_edit.text()}
            )
        else:
            return None

    def create_screenshot_step(self) -> WorkflowStep:
        """Create a screenshot step with user input"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Screenshot Step")
        dialog.setModal(True)
        dialog.resize(400, 250)

        layout = QVBoxLayout(dialog)

        # Description
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        desc_edit = QLineEdit("Capture screenshot")
        desc_layout.addWidget(desc_edit)
        layout.addLayout(desc_layout)

        # Screenshot description
        screen_desc_layout = QHBoxLayout()
        screen_desc_layout.addWidget(QLabel("Screenshot description:"))
        screen_desc_edit = QLineEdit("Process completed")
        screen_desc_layout.addWidget(screen_desc_edit)
        layout.addLayout(screen_desc_layout)

        # Wait time
        wait_layout = QHBoxLayout()
        wait_layout.addWidget(QLabel("Wait time (s):"))
        wait_spin = QDoubleSpinBox()
        wait_spin.setRange(0.5, 10.0)
        wait_spin.setValue(1.0)
        wait_spin.setSingleStep(0.5)
        wait_layout.addWidget(wait_spin)
        layout.addLayout(wait_layout)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("Add")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QDialog.Accepted:
            return WorkflowStep(
                step_number=len(self.studio_workflow_steps) + 1,
                action_type="screenshot",
                description=desc_edit.text(),
                target_element="screenshot",
                position={"x": 0, "y": 0},
                wait_time=wait_spin.value(),
                optional=False,
                screenshot_description=screen_desc_edit.text()
            )
        else:
            return None

    def create_conditional_step(self) -> WorkflowStep:
        """Create a conditional step with user input"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Conditional Step")
        dialog.setModal(True)
        dialog.resize(500, 400)

        layout = QVBoxLayout(dialog)

        # Description
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        desc_edit = QLineEdit("Conditional logic")
        desc_layout.addWidget(desc_edit)
        layout.addLayout(desc_layout)

        # Condition type
        condition_layout = QHBoxLayout()
        condition_layout.addWidget(QLabel("Condition type:"))
        condition_combo = QComboBox()
        condition_combo.addItems(["if_exists", "if_not_exists", "if_text_contains", "if_window_contains"])
        condition_layout.addWidget(condition_combo)
        layout.addLayout(condition_layout)

        # Condition parameters
        params_layout = QHBoxLayout()
        params_layout.addWidget(QLabel("Condition text:"))
        params_edit = QLineEdit()
        params_layout.addWidget(params_edit)
        layout.addLayout(params_layout)

        # True actions
        true_layout = QVBoxLayout()
        true_layout.addWidget(QLabel("Actions if true:"))
        true_text = QTextEdit()
        true_text.setMaximumHeight(80)
        true_layout.addWidget(true_text)
        layout.addLayout(true_layout)

        # Wait time
        wait_layout = QHBoxLayout()
        wait_layout.addWidget(QLabel("Wait time (s):"))
        wait_spin = QDoubleSpinBox()
        wait_spin.setRange(1.0, 60.0)
        wait_spin.setValue(3.0)
        wait_spin.setSingleStep(1.0)
        wait_layout.addWidget(wait_spin)
        layout.addLayout(wait_layout)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("Add")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QDialog.Accepted:
            return WorkflowStep(
                step_number=len(self.studio_workflow_steps) + 1,
                action_type="conditional",
                description=desc_edit.text(),
                target_element=condition_combo.currentText(),
                position={"x": 0, "y": 0},
                wait_time=wait_spin.value(),
                optional=False,
                conditional_logic={
                    'condition_type': condition_combo.currentText(),
                    'condition_parameters': {'text': params_edit.text()},
                    'true_actions_text': true_text.toPlainText()
                }
            )
        else:
            return None

    def create_loop_step(self) -> WorkflowStep:
        """Create a loop step with user input"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Loop Step")
        dialog.setModal(True)
        dialog.resize(400, 300)

        layout = QVBoxLayout(dialog)

        # Description
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        desc_edit = QLineEdit("Loop actions")
        desc_layout.addWidget(desc_edit)
        layout.addLayout(desc_layout)

        # Loop count
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("Loop count:"))
        count_spin = QSpinBox()
        count_spin.setRange(1, 100)
        count_spin.setValue(3)
        count_layout.addWidget(count_spin)
        layout.addLayout(count_layout)

        # Loop actions
        actions_layout = QVBoxLayout()
        actions_layout.addWidget(QLabel("Loop actions:"))
        actions_text = QTextEdit()
        actions_text.setMaximumHeight(80)
        actions_layout.addWidget(actions_text)
        layout.addLayout(actions_layout)

        # Wait time
        wait_layout = QHBoxLayout()
        wait_layout.addWidget(QLabel("Wait time per iteration (s):"))
        wait_spin = QDoubleSpinBox()
        wait_spin.setRange(0.5, 60.0)
        wait_spin.setValue(2.0)
        wait_spin.setSingleStep(0.5)
        wait_layout.addWidget(wait_spin)
        layout.addLayout(wait_layout)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("Add")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QDialog.Accepted:
            return WorkflowStep(
                step_number=len(self.studio_workflow_steps) + 1,
                action_type="loop",
                description=desc_edit.text(),
                target_element="loop",
                position={"x": 0, "y": 0},
                wait_time=wait_spin.value(),
                optional=False,
                loop_logic={
                    'loop_count': count_spin.value(),
                    'actions_text': actions_text.toPlainText()
                }
            )
        else:
            return None

    def create_custom_script_step(self) -> WorkflowStep:
        """Create a custom script step with user input"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Custom Script Step")
        dialog.setModal(True)
        dialog.resize(500, 400)

        layout = QVBoxLayout(dialog)

        # Description
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        desc_edit = QLineEdit("Custom script")
        desc_layout.addWidget(desc_edit)
        layout.addLayout(desc_layout)

        # Script language
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Language:"))
        lang_combo = QComboBox()
        lang_combo.addItems(["Python", "Batch", "PowerShell", "Shell"])
        lang_layout.addWidget(lang_combo)
        layout.addLayout(lang_layout)

        # Script content
        script_layout = QVBoxLayout()
        script_layout.addWidget(QLabel("Script content:"))
        script_text = QTextEdit()
        script_text.setPlaceholderText("# Enter your script here\nprint('Hello World')")
        script_layout.addWidget(script_text)
        layout.addLayout(script_layout)

        # Wait time
        wait_layout = QHBoxLayout()
        wait_layout.addWidget(QLabel("Wait time (s):"))
        wait_spin = QDoubleSpinBox()
        wait_spin.setRange(1.0, 300.0)
        wait_spin.setValue(5.0)
        wait_spin.setSingleStep(1.0)
        wait_layout.addWidget(wait_spin)
        layout.addLayout(wait_layout)

        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("Add")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QDialog.Accepted:
            return WorkflowStep(
                step_number=len(self.studio_workflow_steps) + 1,
                action_type="custom_script",
                description=desc_edit.text(),
                target_element="custom_script",
                position={"x": 0, "y": 0},
                wait_time=wait_spin.value(),
                optional=False,
                script_content=script_text.toPlainText(),
                script_language=lang_combo.currentText()
            )
        else:
            return None

    def update_studio_workflow_list(self):
        """Update the workflow preview list"""
        self.studio_workflow_list.clear()

        for i, step in enumerate(self.studio_workflow_steps):
            # Create item with step information
            item_text = f"Step {step.step_number}: {step.action_type.title()} - {step.description}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, step)

            # Color code by action type
            if step.action_type in ["click", "double_click", "right_click"]:
                item.setStyleSheet("color: #007bff;")
            elif step.action_type in ["input_text", "type"]:
                item.setStyleSheet("color: #28a745;")
            elif step.action_type == "wait":
                item.setStyleSheet("color: #ffc107;")
            elif step.action_type == "conditional":
                item.setStyleSheet("color: #dc3545; font-weight: bold;")
            elif step.action_type == "loop":
                item.setStyleSheet("color: #6f42c1; font-weight: bold;")
            elif step.action_type == "launch":
                item.setStyleSheet("color: #17a2b8;")
            elif step.action_type == "screenshot":
                item.setStyleSheet("color: #fd7e14;")
            else:
                item.setStyleSheet("color: #6c757d;")

            self.studio_workflow_list.addItem(item)

    def on_studio_step_selection_changed(self):
        """Handle step selection change"""
        has_selection = bool(self.studio_workflow_list.currentItem())
        self.edit_studio_step_btn.setEnabled(has_selection)
        self.remove_studio_step_btn.setEnabled(has_selection)

    def edit_studio_step(self):
        """Edit the selected studio step"""
        current_item = self.studio_workflow_list.currentItem()
        if not current_item:
            return

        step = current_item.data(Qt.UserRole)
        if not step:
            return

        QMessageBox.information(self, "Edit Step", f"Step editing feature coming soon!\n\nStep: {step.description}")

    def remove_studio_step(self):
        """Remove the selected studio step"""
        current_item = self.studio_workflow_list.currentItem()
        if not current_item:
            return

        step = current_item.data(Qt.UserRole)
        if step in self.studio_workflow_steps:
            self.studio_workflow_steps.remove(step)

        self.studio_workflow_list.takeItem(self.studio_workflow_list.row(current_item))

        # Renumber remaining steps
        for i, step in enumerate(self.studio_workflow_steps):
            step.step_number = i + 1

        self.update_studio_workflow_list()
        self.studio_status_label.setText(f"Status: Removed step - {len(self.studio_workflow_steps)} steps remaining")

    def on_studio_element_captured(self, element_info: Dict[str, Any], dialog: QDialog):
        """Handle element captured in studio drag-drop recorder"""
        try:
            # Convert element to workflow step
            step = WorkflowStep(
                step_number=len(self.studio_workflow_steps) + 1,
                action_type=element_info.get('action_type', 'click'),
                description=f"Interact with {element_info['name']}",
                target_element=element_info['name'],
                position=element_info['position'],
                wait_time=2.0,
                optional=False,
                screenshot_path=element_info.get('screenshot')
            )

            logger.info(f"Captured element in studio: {element_info['name']}")

        except Exception as e:
            logger.error(f"Error handling studio element capture: {e}")

    def on_studio_condition_detected(self, condition_data: Dict[str, Any], dialog: QDialog):
        """Handle condition detected in studio conditional recorder"""
        try:
            # Convert condition to workflow step
            step = WorkflowStep(
                step_number=len(self.studio_workflow_steps) + 1,
                action_type='conditional',
                description=f"Conditional: {condition_data.get('description', 'No description')}",
                target_element=condition_data.get('condition_type', 'if_exists'),
                position={'x': 0, 'y': 0},
                wait_time=3.0,
                optional=False,
                conditional_logic={
                    'condition_type': condition_data.get('condition_type'),
                    'condition_parameters': condition_data.get('condition_parameters', {}),
                    'pattern_type': condition_data.get('pattern_type', 'unknown')
                }
            )

            logger.info(f"Detected condition in studio: {condition_data.get('description', 'Unknown')}")

        except Exception as e:
            logger.error(f"Error handling studio condition detection: {e}")

    def on_studio_branch_created(self, branch_data: Dict[str, Any], dialog: QDialog):
        """Handle branch created in studio conditional recorder"""
        try:
            logger.info(f"Created branch in studio: {branch_data.get('branch_id', 'Unknown')}")
            self.studio_status_label.setText(f"Status: Created branch - {branch_data.get('branch_id', 'Unknown')}")

        except Exception as e:
            logger.error(f"Error handling studio branch creation: {e}")

    def add_drag_drop_elements_to_workflow(self, recorder, dialog: QDialog):
        """Add drag-drop elements to the studio workflow"""
        try:
            elements = recorder.get_captured_elements()
            if not elements:
                QMessageBox.warning(dialog, "No Elements", "No elements have been captured.")
                return

            # Convert elements to workflow steps
            for element in elements:
                step = WorkflowStep(
                    step_number=len(self.studio_workflow_steps) + 1,
                    action_type=element.get('action_type', 'click'),
                    description=f"Interact with {element['name']}",
                    target_element=element['name'],
                    position=element['position'],
                    wait_time=2.0,
                    optional=False,
                    screenshot_path=element.get('screenshot')
                )
                self.studio_workflow_steps.append(step)

            self.update_studio_workflow_list()
            dialog.close()
            self.studio_status_label.setText(f"Status: Added {len(elements)} drag-drop elements to workflow")

            QMessageBox.information(self, "Elements Added", f"Successfully added {len(elements)} elements to the workflow!")

        except Exception as e:
            logger.error(f"Error adding drag-drop elements to workflow: {e}")
            QMessageBox.critical(self, "Error", f"Failed to add elements: {e}")

    def add_conditional_logic_to_workflow(self, recorder, dialog: QDialog):
        """Add conditional logic to the studio workflow"""
        try:
            conditions = recorder.get_detected_conditions()
            if not conditions:
                QMessageBox.warning(dialog, "No Conditions", "No conditional logic has been detected.")
                return

            # Convert conditions to workflow steps
            for condition in conditions:
                step = WorkflowStep(
                    step_number=len(self.studio_workflow_steps) + 1,
                    action_type='conditional',
                    description=f"Conditional: {condition.get('description', 'No description')}",
                    target_element=condition.get('condition_type', 'if_exists'),
                    position={'x': 0, 'y': 0},
                    wait_time=3.0,
                    optional=False,
                    conditional_logic={
                        'condition_type': condition.get('condition_type'),
                        'condition_parameters': condition.get('condition_parameters', {}),
                        'pattern_type': condition.get('pattern_type', 'unknown')
                    }
                )
                self.studio_workflow_steps.append(step)

            self.update_studio_workflow_list()
            dialog.close()
            self.studio_status_label.setText(f"Status: Added {len(conditions)} conditional logic steps to workflow")

            QMessageBox.information(self, "Conditions Added", f"Successfully added {len(conditions)} conditional logic steps to the workflow!")

        except Exception as e:
            logger.error(f"Error adding conditional logic to workflow: {e}")
            QMessageBox.critical(self, "Error", f"Failed to add conditions: {e}")

    def generate_studio_suggestions(self, mode: str):
        """Generate suggestions based on creation mode"""
        try:
            self.studio_suggestions_list.clear()

            suggestions = []

            if mode == "Manual Builder":
                suggestions = [
                    {"title": "Use Templates", "description": "Start with petroleum workflow templates for common tasks"},
                    {"title": "Add Error Handling", "description": "Include conditional steps for robust automation"},
                    {"title": "Test Steps", "description": "Test individual steps before combining them"}
                ]
            elif mode == "Screen Recording":
                suggestions = [
                    {"title": "Clear Desktop", "description": "Minimize distractions for better recording"},
                    {"title": "Practice First", "description": "Do a dry run before recording"},
                    {"title": "Use Deliberate Actions", "description": "Click clearly and wait between actions"}
                ]
            elif mode == "Drag & Drop":
                suggestions = [
                    {"title": "Target Key Elements", "description": "Focus on main workflow elements"},
                    {"title": "Group Related Elements", "description": "Capture related UI elements together"},
                    {"title": "Add Manual Steps", "description": "Combine with manual steps for complete workflows"}
                ]
            elif mode == "Conditional Logic":
                suggestions = [
                    {"title": "Think About Scenarios", "description": "Consider different workflow paths"},
                    {"title": "Error Scenarios", "description": "Plan for error conditions and recovery"},
                    {"title": "Validation Points", "description": "Add checks for data and process validation"}
                ]
            elif mode == "Hybrid Mode":
                suggestions = [
                    {"title": "Start with Recording", "description": "Record the main workflow first"},
                    {"title": "Add Logic Later", "description": "Enhance with conditional logic"},
                    {"title": "Combine Methods", "description": "Use all recording methods for best results"}
                ]

            # Add suggestions to list
            for suggestion in suggestions:
                item = QListWidgetItem(f"💡 {suggestion['title']}")
                item.setData(Qt.UserRole, suggestion)
                item.setToolTip(suggestion['description'])
                self.studio_suggestions_list.addItem(item)

        except Exception as e:
            logger.error(f"Error generating studio suggestions: {e}")

    def generate_recording_suggestions(self, steps):
        """Generate suggestions based on recorded steps"""
        try:
            suggestions = []

            if len(steps) > 10:
                suggestions.append({"title": "Consider Breaking Down", "description": "This workflow has many steps. Consider breaking it into smaller workflows."})

            click_steps = [s for s in steps if s.action_type in ["click", "double_click"]]
            if len(click_steps) > len(steps) * 0.7:
                suggestions.append({"title": "Add Waits", "description": "Many clicks detected. Consider adding wait steps for reliability."})

            if not any(s.action_type == "conditional" for s in steps):
                suggestions.append({"title": "Add Error Handling", "description": "No conditional steps found. Consider adding error handling for robust automation."})

            if not any(s.action_type == "screenshot" for s in steps):
                suggestions.append({"title": "Add Screenshots", "description": "No screenshots found. Add screenshots for debugging and verification."})

            # Add suggestions to list
            self.studio_suggestions_list.clear()
            for suggestion in suggestions:
                item = QListWidgetItem(f"💡 {suggestion['title']}")
                item.setData(Qt.UserRole, suggestion)
                item.setToolTip(suggestion['description'])
                self.studio_suggestions_list.addItem(item)

        except Exception as e:
            logger.error(f"Error generating recording suggestions: {e}")

    def apply_studio_suggestion(self):
        """Apply the selected suggestion"""
        try:
            current_item = self.studio_suggestions_list.currentItem()
            if not current_item:
                return

            suggestion = current_item.data(Qt.UserRole)
            if not suggestion:
                return

            QMessageBox.information(self, "Apply Suggestion", f"Suggestion: {suggestion['description']}\n\nThis feature will automatically apply the suggestion to your workflow.")

        except Exception as e:
            logger.error(f"Error applying studio suggestion: {e}")

    def preview_studio_workflow(self):
        """Preview the studio workflow"""
        try:
            if not self.studio_workflow_steps:
                QMessageBox.warning(self, "No Steps", "No workflow steps to preview.")
                return

            # Create preview dialog
            preview_dialog = QDialog(self)
            preview_dialog.setWindowTitle("Workflow Preview")
            preview_dialog.setModal(True)
            preview_dialog.resize(600, 500)

            layout = QVBoxLayout(preview_dialog)

            # Workflow summary
            name = self.studio_workflow_name_edit.text() or "Untitled Workflow"
            desc = self.studio_workflow_desc_edit.toPlainText() or "No description"
            software = self.studio_software_combo.currentText()

            summary_label = QLabel(f"📋 {name}")
            summary_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
            layout.addWidget(summary_label)

            desc_label = QLabel(f"Description: {desc}")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

            info_label = QLabel(f"Target Software: {software} | Steps: {len(self.studio_workflow_steps)}")
            info_label.setStyleSheet("color: #6c757d; font-style: italic; margin-bottom: 10px;")
            layout.addWidget(info_label)

            # Steps list
            steps_group = QGroupBox("Workflow Steps")
            steps_layout = QVBoxLayout(steps_group)

            steps_text = QTextEdit()
            steps_text.setReadOnly(True)

            steps_preview = []
            for step in self.studio_workflow_steps:
                step_preview = f"Step {step.step_number}: {step.action_type.title()}\n"
                step_preview += f"  Description: {step.description}\n"
                step_preview += f"  Target: {step.target_element}\n"
                step_preview += f"  Wait: {step.wait_time}s\n"
                if step.action_type == "conditional" and step.conditional_logic:
                    step_preview += f"  Logic: {step.conditional_logic.get('condition_type', 'Unknown')}\n"
                step_preview += "\n"
                steps_preview.append(step_preview)

            steps_text.setText("".join(steps_preview))
            steps_layout.addWidget(steps_text)

            layout.addWidget(steps_group)

            # Buttons
            button_layout = QHBoxLayout()
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(preview_dialog.accept)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

            preview_dialog.exec_()

        except Exception as e:
            logger.error(f"Error previewing studio workflow: {e}")
            QMessageBox.critical(self, "Preview Error", f"Failed to preview workflow: {e}")

    def test_studio_workflow(self):
        """Test the studio workflow"""
        try:
            if not self.studio_workflow_steps:
                QMessageBox.warning(self, "No Steps", "No workflow steps to test.")
                return

            reply = QMessageBox.question(
                self,
                "Test Workflow",
                f"Are you sure you want to test this workflow with {len(self.studio_workflow_steps)} steps?\n\n"
                "The workflow will be executed in test mode. Make sure your petroleum software is ready.",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                # Create a test workflow
                name = self.studio_workflow_name_edit.text() or "Test Workflow"
                software = self.studio_software_combo.currentText()

                test_workflow = Workflow(
                    name=f"TEST: {name}",
                    description=f"Test execution of workflow: {self.studio_workflow_desc_edit.toPlainText() or 'No description'}",
                    software=software,
                    category="Test",
                    difficulty="Beginner",
                    estimated_time=len(self.studio_workflow_steps) * 2.0,
                    author="Workflow Studio",
                    version="1.0.0",
                    created_date=datetime.now().isoformat(),
                    modified_date=datetime.now().isoformat(),
                    tags=["test", "studio"],
                    steps=self.studio_workflow_steps,
                    dependencies=[],
                    variables={},
                    error_handling=True,
                    retry_count=1,
                    timeout=30
                )

                # Execute workflow
                self.execute_workflow(test_workflow)

        except Exception as e:
            logger.error(f"Error testing studio workflow: {e}")
            QMessageBox.critical(self, "Test Error", f"Failed to test workflow: {e}")

    def save_studio_workflow(self):
        """Save the studio workflow"""
        try:
            if not self.studio_workflow_steps:
                QMessageBox.warning(self, "No Steps", "No workflow steps to save.")
                return

            name = self.studio_workflow_name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "No Name", "Please enter a workflow name.")
                self.studio_workflow_name_edit.setFocus()
                return

            # Create workflow
            workflow = Workflow(
                name=name,
                description=self.studio_workflow_desc_edit.toPlainText().strip() or "Created in Workflow Studio",
                software=self.studio_software_combo.currentText(),
                category="Custom",
                difficulty=self.studio_difficulty_combo.currentText(),
                estimated_time=len(self.studio_workflow_steps) * 2.0,
                author="Workflow Studio",
                version="1.0.0",
                created_date=datetime.now().isoformat(),
                modified_date=datetime.now().isoformat(),
                tags=["studio_created", "custom"],
                steps=self.studio_workflow_steps,
                dependencies=[],
                variables={},
                error_handling=True,
                retry_count=3,
                timeout=60
            )

            # Save workflow
            workflows_dir = Path("workflows")
            workflows_dir.mkdir(exist_ok=True)

            workflow_file = workflows_dir / f"{name.replace(' ', '_').lower()}.json"
            with open(workflow_file, 'w') as f:
                json.dump(asdict(workflow), f, indent=2)

            # Update workflows UI
            self.update_workflows_ui()

            # Show success message
            QMessageBox.information(
                self,
                "Workflow Saved",
                f"Workflow '{name}' has been successfully saved with {len(self.studio_workflow_steps)} steps!\n\n"
                f"The workflow is now available in the Workflows tab."
            )

            self.studio_status_label.setText(f"Status: Workflow '{name}' saved successfully")
            logger.info(f"Saved studio workflow: {name}")

        except Exception as e:
            logger.error(f"Error saving studio workflow: {e}")
            QMessageBox.critical(self, "Save Error", f"Failed to save workflow: {e}")

    def export_studio_workflow(self):
        """Export the studio workflow"""
        try:
            if not self.studio_workflow_steps:
                QMessageBox.warning(self, "No Steps", "No workflow steps to export.")
                return

            # Choose export format
            format_dialog = QDialog(self)
            format_dialog.setWindowTitle("Export Workflow")
            format_dialog.setModal(True)
            format_dialog.resize(400, 300)

            layout = QVBoxLayout(format_dialog)

            layout.addWidget(QLabel("Select export format:"))

            format_combo = QComboBox()
            format_combo.addItems(["JSON Workflow", "Python Script", "Batch File", "Documentation"])
            layout.addWidget(format_combo)

            button_layout = QHBoxLayout()
            export_btn = QPushButton("Export")
            export_btn.clicked.connect(format_dialog.accept)
            cancel_btn = QPushButton("Cancel")
            cancel_btn.clicked.connect(format_dialog.reject)
            button_layout.addWidget(export_btn)
            button_layout.addWidget(cancel_btn)

            layout.addLayout(button_layout)

            if format_dialog.exec_() != QDialog.Accepted:
                return

            export_format = format_combo.currentText()
            name = self.studio_workflow_name_edit.text().strip() or "Exported Workflow"

            if export_format == "JSON Workflow":
                self.export_workflow_as_json(name)
            elif export_format == "Python Script":
                self.export_workflow_as_python(name)
            elif export_format == "Batch File":
                self.export_workflow_as_batch(name)
            elif export_format == "Documentation":
                self.export_workflow_as_documentation(name)

        except Exception as e:
            logger.error(f"Error exporting studio workflow: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to export workflow: {e}")

    def export_workflow_as_json(self, name: str):
        """Export workflow as JSON file"""
        try:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export Workflow as JSON",
                f"{name.replace(' ', '_')}.json",
                "JSON Files (*.json)"
            )

            if filename:
                workflow = Workflow(
                    name=name,
                    description=self.studio_workflow_desc_edit.toPlainText() or "Exported from Workflow Studio",
                    software=self.studio_software_combo.currentText(),
                    category="Exported",
                    difficulty=self.studio_difficulty_combo.currentText(),
                    estimated_time=len(self.studio_workflow_steps) * 2.0,
                    author="Workflow Studio",
                    version="1.0.0",
                    created_date=datetime.now().isoformat(),
                    modified_date=datetime.now().isoformat(),
                    tags=["exported", "studio_created"],
                    steps=self.studio_workflow_steps,
                    dependencies=[],
                    variables={},
                    error_handling=True,
                    retry_count=3,
                    timeout=60
                )

                with open(filename, 'w') as f:
                    json.dump(asdict(workflow), f, indent=2)

                QMessageBox.information(self, "Export Complete", f"Workflow exported to:\n{filename}")

        except Exception as e:
            logger.error(f"Error exporting workflow as JSON: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to export as JSON: {e}")

    def export_workflow_as_python(self, name: str):
        """Export workflow as Python script"""
        try:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export Workflow as Python",
                f"{name.replace(' ', '_')}.py",
                "Python Files (*.py)"
            )

            if filename:
                script_lines = [
                    "#!/usr/bin/env python3",
                    '"""',
                    f'Auto-generated workflow script: {name}',
                    f'Created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                    f'Target Software: {self.studio_software_combo.currentText()}',
                    '"""',
                    "",
                    "import pyautogui",
                    "import time",
                    "import sys",
                    "",
                    "def main():",
                    '    """Main workflow execution function"""',
                    '    print(f"Starting workflow: {name}")',
                    ""
                ]

                for step in self.studio_workflow_steps:
                    script_lines.append(f'    # Step {step.step_number}: {step.description}')

                    if step.action_type == "click":
                        script_lines.append(f'    pyautogui.click({step.position["x"]}, {step.position["y"]})')
                    elif step.action_type == "input_text":
                        script_lines.append(f'    pyautogui.typewrite("{step.text_to_input or ""}")')
                    elif step.action_type == "wait":
                        script_lines.append(f'    time.sleep({step.wait_time})')
                    elif step.action_type == "launch":
                        script_lines.append(f'    # Launch {step.program_name}')
                        script_lines.append(f'    # Add launch command here')
                    elif step.action_type == "screenshot":
                        script_lines.append(f'    pyautogui.screenshot(f"step_{step.step_number}.png")')

                    if step.wait_time > 0 and step.action_type != "wait":
                        script_lines.append(f'    time.sleep({step.wait_time})')

                    script_lines.append("")

                script_lines.extend([
                    '    print("Workflow completed successfully!")',
                    "",
                    "if __name__ == '__main__':",
                    "    try:",
                    "        main()",
                    "    except KeyboardInterrupt:",
                    "        print('Workflow stopped by user')",
                    "    except Exception as e:",
                    "        print(f'Workflow error: {e}')",
                    "        sys.exit(1)"
                ])

                with open(filename, 'w') as f:
                    f.write('\n'.join(script_lines))

                QMessageBox.information(self, "Export Complete", f"Python script exported to:\n{filename}")

        except Exception as e:
            logger.error(f"Error exporting workflow as Python: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to export as Python: {e}")

    def export_workflow_as_batch(self, name: str):
        """Export workflow as batch file"""
        try:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export Workflow as Batch",
                f"{name.replace(' ', '_')}.bat",
                "Batch Files (*.bat)"
            )

            if filename:
                batch_lines = [
                    "@echo off",
                    f"echo Starting workflow: {name}",
                    f"echo Target Software: {self.studio_software_combo.currentText()}",
                    "echo.",
                    "REM Workflow steps would be implemented here",
                    "REM This is a placeholder batch file",
                    "echo.",
                    "echo Workflow completed!",
                    "pause"
                ]

                with open(filename, 'w') as f:
                    f.write('\n'.join(batch_lines))

                QMessageBox.information(self, "Export Complete", f"Batch file exported to:\n{filename}")

        except Exception as e:
            logger.error(f"Error exporting workflow as Batch: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to export as Batch: {e}")

    def export_workflow_as_documentation(self, name: str):
        """Export workflow as documentation"""
        try:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export Workflow Documentation",
                f"{name.replace(' ', '_')}.md",
                "Markdown Files (*.md)"
            )

            if filename:
                doc_lines = [
                    f"# {name}",
                    "",
                    f"**Description:** {self.studio_workflow_desc_edit.toPlainText() or 'No description'}",
                    f"**Target Software:** {self.studio_software_combo.currentText()}",
                    f"**Difficulty:** {self.studio_difficulty_combo.currentText()}",
                    f"**Total Steps:** {len(self.studio_workflow_steps)}",
                    f"**Estimated Time:** {len(self.studio_workflow_steps) * 2.0} minutes",
                    f"**Created:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                    "## Workflow Steps",
                    ""
                ]

                for step in self.studio_workflow_steps:
                    doc_lines.append(f"### Step {step.step_number}: {step.action_type.title()}")
                    doc_lines.append(f"**Description:** {step.description}")
                    doc_lines.append(f"**Target:** {step.target_element}")
                    doc_lines.append(f"**Wait Time:** {step.wait_time} seconds")

                    if step.action_type == "conditional" and step.conditional_logic:
                        doc_lines.append(f"**Condition:** {step.conditional_logic.get('condition_type', 'Unknown')}")

                    doc_lines.append("")

                doc_lines.extend([
                    "## Notes",
                    "- This workflow was created using the Workflow Studio",
                    "- All steps should be tested before production use",
                    "- Ensure target software is properly configured",
                    "",
                    f"Generated by Petroleum Desktop Organizer - Workflow Studio"
                ])

                with open(filename, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(doc_lines))

                QMessageBox.information(self, "Export Complete", f"Documentation exported to:\n{filename}")

        except Exception as e:
            logger.error(f"Error exporting workflow documentation: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to export documentation: {e}")

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

        
        # Settings group
        settings_group = QGroupBox("Settings")
        settings_layout = QFormLayout(settings_group)

        save_settings_btn = QPushButton("Save Configuration")
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
            primary_text = " [PRIMARY]" if monitor.get('is_primary') else ""
            return f"1 Monitor: {monitor['width']}x{monitor['height']}{primary_text}"
        else:
            primary_count = sum(1 for m in self.window_manager.monitors if m.get('is_primary'))
            secondary_count = monitor_count - primary_count
            return f"{monitor_count} Monitors: {primary_count} Primary, {secondary_count} Secondary"

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
            logger.info(f"Starting detection for {len(self.config_manager.config)} programs: {list(self.config_manager.config.keys())}")
            for program_key, config in self.config_manager.config.items():
                logger.info(f"Checking {config['display_name']} (key: {program_key})...")
                logger.debug(f"Config: {config.get('check_method', {})}")

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
                    if not WINDOWS_SUPPORT:
                        logger.warning(f"Windows support not available for {config['display_name']} detection")
                        program_info.detected = False
                        program_info.install_error = "Windows support not available"
                        self.detected_programs[program_key] = program_info
                        continue

                    if check_type == 'registry':
                        check_keys = check_method.get('keys', [])
                        logger.info(f"Checking {config['display_name']} with {len(check_keys)} registry rules")
                        for i, key in enumerate(check_keys):
                            logger.info(f"  Rule {i+1}: {key}")
                        is_installed, found_version = WindowsUtils.check_registry(check_keys)
                        logger.info(f"Registry check result for {config['display_name']}: {is_installed}, version: {found_version}")

                        # If installed, try to find executable path
                        if is_installed:
                            executable_path = WindowsUtils.find_executable_path(program_key, config)
                            logger.debug(f"Found executable path for {config['display_name']}: {executable_path}")

                    elif check_type == 'path':
                        paths_to_check = check_method.get('paths', [])
                        logger.info(f"Checking {config['display_name']} paths: {paths_to_check}")
                        is_installed = any(WindowsUtils.check_path_exists(p) for p in paths_to_check)
                        logger.info(f"Path check result for {config['display_name']}: {is_installed}")

                        if is_installed and paths_to_check:
                            # Use the first existing path as install location
                            for path in paths_to_check:
                                expanded_path = os.path.expandvars(path)
                                if os.path.exists(expanded_path):
                                    program_info.install_path = expanded_path
                                    # Try to find executable path for path-based detection
                                    executable_path = WindowsUtils.find_executable_path(program_key, config)
                                    logger.info(f"Found executable path for {config['display_name']}: {executable_path}")
                                    break

                    # Update program info with detection results
                    program_info.detected = is_installed
                    # Use found version, then configuration version, then unknown
                    if found_version:
                        program_info.version = found_version
                    elif config.get('target_version') and config['target_version'] != 'latest':
                        program_info.version = config['target_version']
                    else:
                        program_info.version = "Unknown"
                    program_info.executable_path = executable_path or ""

                    logger.info(f"{config['display_name']}: {'Installed' if is_installed else 'Not Found'}" +
                               (f" (v{found_version})" if found_version else ""))

                except Exception as e:
                    logger.error(f"Error checking {config['display_name']}: {e}", exc_info=True)
                    program_info.detected = False
                    program_info.install_error = str(e)

                # Store the program info
                self.detected_programs[program_key] = program_info

                # Emit signal for UI update (thread-safe)
                self.program_detected.emit(program_key, asdict(program_info))

            # Signal completion
            self.detection_completed.emit()
            logger.info("Petroleum program detection completed")

        except Exception as e:
            logger.error(f"Error in program detection worker: {e}")
            self.detection_status.emit("Error detecting programs")

    def on_detection_status(self, status_text):
        """Handle detection status updates (thread-safe)"""
        if hasattr(self, 'status_label'):
            self.status_label.setText(status_text)

    def on_program_detected(self, program_key, program_info_dict):
        """Handle individual program detection (thread-safe)"""
        if not hasattr(self, 'programs_tree'):
            return

        # Hide the help message when programs are added
        if hasattr(self, 'no_programs_label'):
            self.no_programs_label.hide()

        # Convert dict back to ProgramInfo
        program_info = ProgramInfo(**program_info_dict)

        # Find existing item or create new one
        for i in range(self.programs_tree.topLevelItemCount()):
            item = self.programs_tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == program_key:
                # Update existing item
                item.setText(0, program_info.display_name)
                item.setText(1, program_info.version or "Unknown")
                if program_info.detected:
                    item.setText(2, "Installed")
                    item.setIcon(0, self.get_style_icon("✓"))
                else:
                    item.setText(2, "Not Found")
                    item.setIcon(0, self.get_style_icon("✗"))
                return

        # Create new item if not found
        item = QTreeWidgetItem(self.programs_tree)
        item.setText(0, program_info.display_name)
        item.setText(1, program_info.version or "Unknown")
        if program_info.detected:
            item.setText(2, "Installed")
            item.setIcon(0, self.get_style_icon("✓"))
        else:
            item.setText(2, "Not Found")
            item.setIcon(0, self.get_style_icon("✗"))
        item.setData(0, Qt.UserRole, program_key)

        self.programs_tree.resizeColumnToContents(0)
        self.programs_tree.resizeColumnToContents(1)

    def on_detection_completed(self):
        """Handle detection completion (thread-safe)"""
        if hasattr(self, 'status_label'):
            self.status_label.setText("Program detection completed")

        # Final column resize
        if hasattr(self, 'programs_tree'):
            self.programs_tree.resizeColumnToContents(0)
            self.programs_tree.resizeColumnToContents(1)
            self.programs_tree.resizeColumnToContents(2)

    def update_programs_ui(self):
        """Update the programs tree widget with detected programs (legacy method)"""
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
            # Capture button screenshot
            self.capture_button_screenshot(f"Launch {program.display_name}", self.sender())

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

            # Get dynamic window position (no hardcoded monitor preferences)
            position = self.window_manager.get_optimal_position(program.name)

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

                # Log position for debugging (positions will be handled dynamically by workflows)
                logger.debug(f"Calculated window position: {position}")

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

    def show_petroleum_templates(self):
        """Show petroleum software workflow templates"""
        dialog = PetroleumTemplateDialog(self, PETROLEUM_WORKFLOW_TEMPLATES, self.detected_programs)
        if dialog.exec_() == QDialog.Accepted:
            selected_template = dialog.get_selected_template()
            if selected_template:
                workflow = selected_template.to_workflow()

                # Avoid name conflicts
                original_name = workflow.name
                counter = 1
                while workflow.name in self.workflows:
                    workflow.name = f"{original_name} ({counter})"
                    counter += 1

                self.workflows[workflow.name] = workflow
                self.save_configuration()
                self.update_workflows_ui()

                QMessageBox.information(self, "Template Applied",
                    f"Template '{original_name}' has been applied successfully!\n\n"
                    f"Estimated time: {selected_template.estimated_time}\n"
                    f"Difficulty: {selected_template.difficulty}\n"
                    f"Prerequisites: {', '.join(selected_template.prerequisites)}")

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
        # Capture button screenshot
        self.capture_button_screenshot(f"Run Workflow: {workflow.name}", self.sender())

        if self.automation_engine and self.automation_engine.isRunning():
            QMessageBox.warning(self, "Already Running", "Another workflow is currently running")
            return

        self.automation_engine = AutomationEngine(workflow, self)
        self.automation_engine.progress_updated.connect(self.on_workflow_progress)
        self.automation_engine.step_completed.connect(self.on_workflow_step_completed)
        self.automation_engine.workflow_completed.connect(self.on_workflow_completed)

        # Workflow started
        self.status_label.setText("Starting workflow...")

        # Start the workflow
        self.automation_engine.start()

    def on_workflow_progress(self, progress: int, message: str):
        """Handle workflow progress updates"""
        self.status_label.setText(f"Workflow: {message}")

    def on_workflow_step_completed(self, step_index: int, description: str, success: bool):
        """Handle workflow step completion"""
        status = "✓" if success else "✗"
        self.status_label.setText(f"Step {step_index + 1}: {status} {description}")

    def on_workflow_completed(self, success: bool, message: str):
        """Handle workflow completion"""
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

    def on_recording_mode_changed(self):
        """Handle recording mode change"""
        mode = self.recording_mode_combo.currentText()

        if mode == "Automation Recording":
            # Show automation recording specific info
            if hasattr(self, 'auto_capture_check'):
                self.auto_capture_check.setVisible(False)
            self.recording_description_edit.setPlaceholderText("Enter description for automation recording")
        else:
            # Show manual screenshot specific info
            if hasattr(self, 'auto_capture_check'):
                self.auto_capture_check.setVisible(True)
            self.recording_description_edit.setPlaceholderText("Enter description for screenshot recording")

    def start_recording(self):
        """Start a recording session"""
        try:
            if not SCREEN_RECORDING_SUPPORT:
                QMessageBox.warning(self, "Recording Not Available",
                                  "Screen recording dependencies are not available. Please install PyAutoGUI and OpenCV.")
                return

            mode = self.recording_mode_combo.currentText()

            # Check if any recording is already in progress
            if (self.screen_recorder.is_recording or
                self.screen_recorder.automation_recorder.is_recording):
                QMessageBox.warning(self, "Already Recording", "A recording session is already in progress")
                return

            description = self.recording_description_edit.text()

            if mode == "Automation Recording":
                # Start automation recording
                session_id = self.screen_recorder.automation_recorder.start_recording(description)
                self.status_label.setText(f"Automation recording started: {session_id}")
                self.status_label.setStyleSheet("color: orange; font-weight: bold;")
            else:
                # Start manual screenshot recording
                session_id = self.screen_recorder.start_recording(description)
                self.status_label.setText(f"Screenshot recording started: {session_id}")
                self.status_label.setStyleSheet("color: green; font-weight: bold;")

            # Update UI
            self.recording_status_label.setText("Recording")
            self.recording_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.recording_session_label.setText(f"Session: {session_id}")
            self.start_recording_btn.setEnabled(False)
            self.stop_recording_btn.setEnabled(True)
            self.recording_description_edit.setEnabled(False)
            self.recording_mode_combo.setEnabled(False)

            # Enable/disable script-specific buttons
            self.test_script_btn.setEnabled(mode == "Automation Recording")
            self.export_script_btn.setEnabled(mode == "Automation Recording")

            # Switch to recording tab to show status
            if hasattr(self, 'tab_widget'):
                self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)  # Recording tab

            # Show mode-specific instructions
            if mode == "Automation Recording":
                QMessageBox.information(self, "Automation Recording Started",
                    "Automation recording has started!\n\n"
                    "• Perform the actions you want to automate\n"
                    "• Mouse clicks, scrolling, and typing will be recorded\n"
                    "• Press ESC key to stop recording\n"
                    "• Templates will be created for image recognition")
            else:
                QMessageBox.information(self, "Screenshot Recording Started",
                    "Screenshot recording has started!\n\n"
                    "• Screenshots will be captured automatically\n"
                    "• Click the 'Stop Recording' button when finished")

            logger.info(f"Started {mode.lower()}: {session_id}")

        except Exception as e:
            logger.error(f"Error starting recording: {e}")
            QMessageBox.critical(self, "Recording Error", f"Failed to start recording: {e}")

    def stop_recording(self):
        """Stop the current recording session"""
        try:
            mode = self.recording_mode_combo.currentText()
            session = None

            if mode == "Automation Recording":
                if not self.screen_recorder.automation_recorder.is_recording:
                    QMessageBox.warning(self, "Not Recording", "No automation recording session is in progress")
                    return

                session = self.screen_recorder.automation_recorder.stop_recording()

                # Add to screen recorder sessions for management
                self.screen_recorder.sessions.append(session)

                self.status_label.setText(f"Automation recording stopped: {session.session_id} ({len(session.automation_actions)} actions)")

                # Show automation summary
                msg = f"Automation recording completed!\n\n"
                msg += f"Session ID: {session.session_id}\n"
                msg += f"Duration: {session.start_time} to {session.end_time}\n"
                msg += f"Actions recorded: {len(session.automation_actions)}\n"
                msg += f"Script generated: Yes\n\n"
                msg += f"Click types captured: {sum(1 for a in session.automation_actions if a.action_type == 'click')}\n"
                msg += f"Keys typed: {sum(1 for a in session.automation_actions if a.action_type == 'type')}\n"
                msg += f"Scrolls: {sum(1 for a in session.automation_actions if a.action_type == 'scroll')}"

                QMessageBox.information(self, "Automation Recording Complete", msg)

            else:
                if not self.screen_recorder.is_recording:
                    QMessageBox.warning(self, "Not Recording", "No screenshot recording session is in progress")
                    return

                session = self.screen_recorder.stop_recording()

                self.status_label.setText(f"Screenshot recording stopped: {session.session_id} ({len(session.screenshots)} screenshots)")

                # Show screenshot summary
                msg = f"Screenshot recording completed!\n\n"
                msg += f"Session ID: {session.session_id}\n"
                msg += f"Duration: {session.start_time} to {session.end_time}\n"
                msg += f"Screenshots captured: {len(session.screenshots)}\n"
                msg += f"Video created: {'Yes' if session.video_path else 'No'}"

                QMessageBox.information(self, "Screenshot Recording Complete", msg)

            # Update UI
            self.recording_status_label.setText("Not Recording")
            self.recording_status_label.setStyleSheet("color: red; font-weight: bold;")
            self.recording_session_label.setText("No active session")
            self.start_recording_btn.setEnabled(True)
            self.stop_recording_btn.setEnabled(False)
            self.recording_description_edit.setEnabled(True)
            self.recording_description_edit.clear()
            self.recording_mode_combo.setEnabled(True)

            # Update sessions list
            self.update_sessions_ui()

        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            QMessageBox.critical(self, "Recording Error", f"Failed to stop recording: {e}")

    def test_automation_script(self):
        """Test the generated automation script"""
        current_item = self.sessions_tree.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a session to test")
            return

        session_id = current_item.data(0, Qt.UserRole)
        session = self.screen_recorder.get_session(session_id)

        if not session or not session.generated_script:
            QMessageBox.warning(self, "No Script", "This session doesn't have a generated script")
            return

        reply = QMessageBox.question(
            self, "Test Automation Script",
            "This will run the generated automation script.\n\n"
            "• Move mouse to top-left corner to stop\n"
            "• The script will perform the recorded actions\n\n"
            "Do you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._run_automation_script(session.generated_script)

    def _run_automation_script(self, script_content: str):
        """Run an automation script in a separate process"""
        try:
            # Create temporary script file
            script_file = self.screen_recorder.temp_dir / f"test_script_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"

            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(script_content)

            # Run script in separate process
            process = subprocess.Popen(
                [sys.executable, str(script_file)],
                cwd=self.screen_recorder.temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Show status
            self.status_label.setText("Running automation script...")

            # Monitor process (non-blocking)
            def check_process():
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    if process.returncode == 0:
                        QMessageBox.information(self, "Script Complete",
                                              f"Automation script completed successfully!\n\nOutput:\n{stdout}")
                    else:
                        QMessageBox.warning(self, "Script Failed",
                                         f"Automation script failed!\n\nError:\n{stderr}")
                    self.status_label.setText("Ready")
                else:
                    # Still running, check again in 1 second
                    QTimer.singleShot(1000, check_process)

            QTimer.singleShot(1000, check_process)

        except Exception as e:
            logger.error(f"Error running automation script: {e}")
            QMessageBox.critical(self, "Script Error", f"Failed to run automation script: {e}")

    def export_automation_script(self):
        """Export the generated automation script"""
        current_item = self.sessions_tree.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a session to export")
            return

        session_id = current_item.data(0, Qt.UserRole)
        session = self.screen_recorder.get_session(session_id)

        if not session or not session.generated_script:
            QMessageBox.warning(self, "No Script", "This session doesn't have a generated script")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            f"Export Automation Script - {session.session_id}",
            f"{session.session_id}_automation.py",
            "Python Files (*.py)"
        )

        if filename:
            try:
                # Copy template images to script directory
                script_dir = Path(filename).parent
                templates_dir = script_dir / "templates"
                templates_dir.mkdir(exist_ok=True)

                for action in session.automation_actions:
                    if action.image_template and os.path.exists(action.image_template):
                        template_name = os.path.basename(action.image_template)
                        shutil.copy2(action.image_template, templates_dir / template_name)

                # Update script paths to relative template paths
                updated_script = session.generated_script.replace(
                    str(self.screen_recorder.automation_recorder.template_dir),
                    str(templates_dir)
                )

                # Write script file
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(updated_script)

                QMessageBox.information(self, "Export Complete",
                                      f"Automation script exported to:\n{filename}\n\n"
                                      f"Template images copied to:\n{templates_dir}")

            except Exception as e:
                logger.error(f"Error exporting automation script: {e}")
                QMessageBox.critical(self, "Export Error", f"Failed to export automation script: {e}")

    def open_drag_drop_recorder(self):
        """Open the drag-and-drop recorder dialog"""
        try:
            # Create drag-and-drop recorder dialog
            recorder_dialog = QDialog(self)
            recorder_dialog.setWindowTitle("Drag & Drop Element Recorder")
            recorder_dialog.setModal(False)  # Non-modal to allow interaction with other applications
            recorder_dialog.resize(500, 700)

            layout = QVBoxLayout(recorder_dialog)

            # Create the drag-drop recorder widget
            self.drag_drop_recorder = DragDropRecorder(recorder_dialog)

            # Connect element captured signal
            self.drag_drop_recorder.element_captured.connect(self.on_drag_drop_element_captured)

            layout.addWidget(self.drag_drop_recorder)

            # Dialog buttons
            button_layout = QHBoxLayout()

            create_workflow_btn = QPushButton("Create Workflow from Elements")
            create_workflow_btn.clicked.connect(lambda: self.create_workflow_from_drag_drop_elements(recorder_dialog))
            button_layout.addWidget(create_workflow_btn)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(recorder_dialog.close)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

            # Show the dialog
            recorder_dialog.show()

            logger.info("Opened drag-and-drop recorder")

        except Exception as e:
            logger.error(f"Error opening drag-drop recorder: {e}")
            QMessageBox.critical(self, "Recorder Error", f"Failed to open drag-and-drop recorder: {e}")

    def on_drag_drop_element_captured(self, element_info: Dict[str, Any]):
        """Handle when an element is captured via drag-and-drop"""
        try:
            logger.info(f"Captured element via drag-and-drop: {element_info['name']} ({element_info['type']})")

            # Update status
            if hasattr(self, 'status_label'):
                self.status_label.setText(f"Captured element: {element_info['name']}")

        except Exception as e:
            logger.error(f"Error handling drag-drop element capture: {e}")

    def create_workflow_from_drag_drop_elements(self, recorder_dialog: QDialog):
        """Create a workflow from captured drag-and-drop elements"""
        try:
            if not hasattr(self, 'drag_drop_recorder'):
                QMessageBox.warning(self, "No Recorder", "Drag-drop recorder not available.")
                return

            captured_elements = self.drag_drop_recorder.get_captured_elements()
            if not captured_elements:
                QMessageBox.warning(self, "No Elements", "No elements have been captured. Please capture some elements first.")
                return

            # Create a new recording session from drag-drop elements
            session_id = f"dragdrop_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Convert drag-drop elements to workflow steps
            workflow_steps = []
            for i, element in enumerate(captured_elements):
                step = WorkflowStep(
                    step_number=i + 1,
                    action_type=element.get('action_type', 'click'),
                    description=element.get('description', f"Interact with {element['name']}"),
                    target_element=element['name'],
                    position=element['position'],
                    wait_time=2.0,
                    optional=False,
                    screenshot_path=element.get('screenshot')
                )
                workflow_steps.append(step)

            # Create workflow
            software_list = list(set([elem.get('software') for elem in captured_elements if elem.get('software')]))
            software_name = ", ".join(software_list) if software_list else "Unknown Software"

            workflow = Workflow(
                name=f"Drag & Drop Workflow {len(captured_elements)} Elements",
                description=f"Workflow created from {len(captured_elements)} drag-and-drop captured elements from {software_name}.",
                software=software_name,
                category="Drag & Drop",
                difficulty="Beginner",
                estimated_time=len(workflow_steps) * 2.0,
                author="Drag & Drop Recorder",
                version="1.0.0",
                created_date=datetime.now().isoformat(),
                modified_date=datetime.now().isoformat(),
                tags=["drag_drop", "visual", "captured"],
                steps=workflow_steps,
                dependencies=[],
                variables={},
                error_handling=True,
                retry_count=3,
                timeout=30
            )

            # Save workflow
            workflows_dir = Path("workflows")
            workflows_dir.mkdir(exist_ok=True)

            workflow_file = workflows_dir / f"dragdrop_workflow_{session_id}.json"
            with open(workflow_file, 'w') as f:
                json.dump(asdict(workflow), f, indent=2)

            # Close the recorder dialog
            recorder_dialog.close()

            # Refresh workflows UI
            self.update_workflows_ui()

            # Show success message
            QMessageBox.information(
                self,
                "Workflow Created",
                f"Successfully created workflow '{workflow.name}' with {len(workflow_steps)} steps!\n\n"
                f"The workflow has been saved and is available in the Workflows tab."
            )

            logger.info(f"Created workflow from drag-drop elements: {workflow.name}")

        except Exception as e:
            logger.error(f"Error creating workflow from drag-drop elements: {e}")
            QMessageBox.critical(self, "Workflow Creation Error", f"Failed to create workflow: {e}")

    def open_conditional_recorder(self):
        """Open the conditional logic recorder dialog"""
        try:
            # Create conditional recorder dialog
            recorder_dialog = QDialog(self)
            recorder_dialog.setWindowTitle("Conditional Logic Recorder")
            recorder_dialog.setModal(False)  # Non-modal to allow interaction with other applications
            recorder_dialog.resize(600, 750)

            layout = QVBoxLayout(recorder_dialog)

            # Create the conditional recorder widget
            self.conditional_recorder = ConditionalRecorder(recorder_dialog)

            # Connect signals
            self.conditional_recorder.condition_detected.connect(self.on_conditional_detected)
            self.conditional_recorder.branch_created.connect(self.on_branch_created)

            layout.addWidget(self.conditional_recorder)

            # Dialog buttons
            button_layout = QHBoxLayout()

            analyze_recording_btn = QPushButton("Analyze Recording")
            analyze_recording_btn.clicked.connect(lambda: self.analyze_conditional_recording(recorder_dialog))
            button_layout.addWidget(analyze_recording_btn)

            create_workflow_btn = QPushButton("Create Conditional Workflow")
            create_workflow_btn.clicked.connect(lambda: self.create_conditional_workflow(recorder_dialog))
            button_layout.addWidget(create_workflow_btn)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(recorder_dialog.close)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

            # Show the dialog
            recorder_dialog.show()

            logger.info("Opened conditional logic recorder")

        except Exception as e:
            logger.error(f"Error opening conditional recorder: {e}")
            QMessageBox.critical(self, "Recorder Error", f"Failed to open conditional recorder: {e}")

    def on_conditional_detected(self, condition_data: Dict[str, Any]):
        """Handle when a condition is detected"""
        try:
            logger.info(f"Detected conditional logic: {condition_data.get('pattern_type', 'Unknown')} - {condition_data.get('description', 'No description')}")

            # Update status
            if hasattr(self, 'status_label'):
                self.status_label.setText(f"Detected condition: {condition_data.get('description', 'Unknown pattern')}")

        except Exception as e:
            logger.error(f"Error handling conditional detection: {e}")

    def on_branch_created(self, branch_data: Dict[str, Any]):
        """Handle when a workflow branch is created"""
        try:
            logger.info(f"Created workflow branch: {branch_data.get('branch_id', 'Unknown')}")

            # Update status
            if hasattr(self, 'status_label'):
                self.status_label.setText(f"Created branch: {branch_data.get('branch_id', 'Unknown')}")

        except Exception as e:
            logger.error(f"Error handling branch creation: {e}")

    def analyze_conditional_recording(self, recorder_dialog: QDialog):
        """Analyze a conditional recording session"""
        try:
            if not hasattr(self, 'conditional_recorder'):
                QMessageBox.warning(self, "No Recorder", "Conditional recorder not available.")
                return

            detected_conditions = self.conditional_recorder.get_detected_conditions()
            if not detected_conditions:
                QMessageBox.information(self, "No Conditions", "No conditional logic has been detected yet. Start recording and perform actions with decision points.")
                return

            # Show analysis results
            analysis_dialog = QDialog(self)
            analysis_dialog.setWindowTitle("Conditional Logic Analysis")
            analysis_dialog.setModal(True)
            analysis_dialog.resize(600, 500)

            layout = QVBoxLayout(analysis_dialog)

            # Summary
            summary_label = QLabel(f"Detected {len(detected_conditions)} conditional logic patterns:")
            summary_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
            layout.addWidget(summary_label)

            # Patterns breakdown
            patterns_text = QTextEdit()
            patterns_text.setReadOnly(True)

            analysis_lines = ["Conditional Logic Analysis:\n"]
            pattern_counts = {}

            for condition in detected_conditions:
                pattern_type = condition.get('pattern_type', 'unknown')
                pattern_counts[pattern_type] = pattern_counts.get(pattern_type, 0) + 1

                analysis_lines.append(f"\n🔀 {pattern_type.title()}: {condition.get('description', 'No description')}")
                analysis_lines.append(f"   Condition: {condition.get('condition_type', 'Unknown')}")
                analysis_lines.append(f"   Parameters: {condition.get('condition_parameters', {})}")

            analysis_lines.append(f"\nSummary:")
            for pattern_type, count in pattern_counts.items():
                analysis_lines.append(f"• {pattern_type.title()}: {count} pattern(s)")

            patterns_text.setText("\n".join(analysis_lines))
            layout.addWidget(patterns_text)

            # Recommendations
            recommendations = self.generate_conditional_recommendations(detected_conditions)
            if recommendations:
                rec_label = QLabel("Recommendations:")
                rec_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
                layout.addWidget(rec_label)

                rec_text = QTextEdit()
                rec_text.setReadOnly(True)
                rec_text.setMaximumHeight(100)
                rec_text.setText("\n".join(f"• {rec}" for rec in recommendations))
                layout.addWidget(rec_text)

            # Buttons
            button_layout = QHBoxLayout()
            ok_btn = QPushButton("OK")
            ok_btn.clicked.connect(analysis_dialog.accept)
            button_layout.addWidget(ok_btn)

            layout.addLayout(button_layout)

            analysis_dialog.exec_()

        except Exception as e:
            logger.error(f"Error analyzing conditional recording: {e}")
            QMessageBox.critical(self, "Analysis Error", f"Failed to analyze conditional recording: {e}")

    def generate_conditional_recommendations(self, conditions: List[Dict[str, Any]]) -> List[str]:
        """Generate recommendations based on detected conditions"""
        recommendations = []

        if not conditions:
            return recommendations

        pattern_types = [cond.get('pattern_type', 'unknown') for cond in conditions]

        if 'error_handling' in pattern_types:
            recommendations.append("Error handling patterns detected - these will make your workflows more robust and reliable.")

        if 'retry_logic' in pattern_types:
            recommendations.append("Retry logic found - workflows will automatically retry failed operations.")

        if 'file_existence' in pattern_types:
            recommendations.append("File validation detected - workflows will check for required files before processing.")

        if 'wait_for_condition' in pattern_types:
            recommendations.append("Wait conditions detected - workflows will wait for specific states before proceeding.")

        if len(conditions) > 5:
            recommendations.append("Complex conditional logic detected - consider breaking into smaller, manageable workflows.")

        recommendations.append("All detected conditions will be converted to intelligent workflow steps with proper error handling.")

        return recommendations

    def create_conditional_workflow(self, recorder_dialog: QDialog):
        """Create a workflow from detected conditional logic"""
        try:
            if not hasattr(self, 'conditional_recorder'):
                QMessageBox.warning(self, "No Recorder", "Conditional recorder not available.")
                return

            detected_conditions = self.conditional_recorder.get_detected_conditions()
            if not detected_conditions:
                QMessageBox.warning(self, "No Conditions", "No conditional logic has been detected. Record some actions with decision points first.")
                return

            # Convert conditions to workflow steps
            workflow_steps = []
            step_counter = 1

            for condition in detected_conditions:
                # Add a conditional step
                conditional_step = WorkflowStep(
                    step_number=step_counter,
                    action_type='conditional',
                    description=f"Conditional Logic: {condition.get('description', 'No description')}",
                    target_element=condition.get('condition_type', 'if_exists'),
                    position=condition.get('trigger_action', {}).get('position', {'x': 0, 'y': 0}),
                    wait_time=2.0,
                    optional=False,
                    conditional_logic={
                        'condition_type': condition.get('condition_type'),
                        'condition_parameters': condition.get('condition_parameters', {}),
                        'true_actions_text': condition.get('true_actions_text', ''),
                        'false_actions_text': condition.get('false_actions_text', ''),
                        'pattern_type': condition.get('pattern_type', 'unknown')
                    }
                )
                workflow_steps.append(conditional_step)
                step_counter += 1

                # Add handling actions if specified
                if 'true_actions_text' in condition and condition['true_actions_text']:
                    action_step = WorkflowStep(
                        step_number=step_counter,
                        action_type='execute_actions',
                        description=f"Execute True Branch Actions: {condition['true_actions_text']}",
                        target_element='conditional_true_branch',
                        position={'x': 0, 'y': 0},
                        wait_time=3.0,
                        optional=False
                    )
                    workflow_steps.append(action_step)
                    step_counter += 1

            # Create workflow
            workflow = Workflow(
                name=f"Conditional Logic Workflow {len(detected_conditions)} Conditions",
                description=f"Intelligent workflow with {len(detected_conditions)} conditional logic points. Includes error handling and decision making.",
                software="Multiple",
                category="Conditional Logic",
                difficulty="Advanced",
                estimated_time=len(workflow_steps) * 3.0,
                author="Conditional Logic Recorder",
                version="1.0.0",
                created_date=datetime.now().isoformat(),
                modified_date=datetime.now().isoformat(),
                tags=["conditional", "intelligent", "error_handling", "decision_logic"],
                steps=workflow_steps,
                dependencies=[],
                variables={},
                error_handling=True,
                retry_count=5,
                timeout=60
            )

            # Save workflow
            workflows_dir = Path("workflows")
            workflows_dir.mkdir(exist_ok=True)

            workflow_id = f"conditional_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            workflow_file = workflows_dir / f"{workflow_id}.json"
            with open(workflow_file, 'w') as f:
                json.dump(asdict(workflow), f, indent=2)

            # Close the recorder dialog
            recorder_dialog.close()

            # Refresh workflows UI
            self.update_workflows_ui()

            # Show success message
            QMessageBox.information(
                self,
                "Conditional Workflow Created",
                f"Successfully created intelligent workflow '{workflow.name}' with {len(workflow_steps)} steps!\n\n"
                f"Conditional Features:\n"
                f"• {len(detected_conditions)} decision points\n"
                f"• Error handling and retry logic\n"
                f"• Intelligent path selection\n"
                f"• Robust failure recovery\n\n"
                f"The workflow is available in the Workflows tab and ready for execution."
            )

            logger.info(f"Created conditional workflow: {workflow.name}")

        except Exception as e:
            logger.error(f"Error creating conditional workflow: {e}")
            QMessageBox.critical(self, "Workflow Creation Error", f"Failed to create conditional workflow: {e}")

    def update_sessions_ui(self):
        """Update the sessions tree widget"""
        if not hasattr(self, 'sessions_tree'):
            return

        self.sessions_tree.clear()

        sessions = self.screen_recorder.get_session_list()
        for session_data in sessions:
            item = QTreeWidgetItem(self.sessions_tree)
            item.setText(0, session_data['session_id'])
            item.setText(1, session_data['start_time'][:19].replace('T', ' '))  # Format datetime
            item.setText(2, str(session_data['screenshot_count']))
            item.setText(3, "Yes" if session_data['has_video'] else "No")
            item.setData(0, Qt.UserRole, session_data['session_id'])

        self.sessions_tree.resizeColumnToContents(0)
        self.sessions_tree.resizeColumnToContents(1)
        self.sessions_tree.resizeColumnToContents(2)

    def on_session_double_click(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on a session"""
        session_id = item.data(0, Qt.UserRole)
        if session_id:
            self.review_session(session_id)

    def review_selected_session(self):
        """Review the selected recording session"""
        current_item = self.sessions_tree.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a session to review")
            return

        session_id = current_item.data(0, Qt.UserRole)
        if session_id:
            self.review_session(session_id)

    def review_session(self, session_id: str):
        """Review a recording session"""
        session = self.screen_recorder.get_session(session_id)
        if not session:
            QMessageBox.warning(self, "Session Not Found", f"Session {session_id} not found")
            return

        dialog = RecordingReviewDialog(self, session)
        dialog.exec_()

    def play_session_video(self):
        """Play video for the selected session"""
        current_item = self.sessions_tree.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a session to play")
            return

        session_id = current_item.data(0, Qt.UserRole)
        session = self.screen_recorder.get_session(session_id)

        if not session or not session.video_path:
            QMessageBox.warning(self, "No Video", "This session doesn't have a video")
            return

        if not os.path.exists(session.video_path):
            QMessageBox.warning(self, "Video Not Found", f"Video file not found:\n{session.video_path}")
            return

        try:
            # Use system default video player
            if sys.platform == 'win32':
                os.startfile(session.video_path)
            elif sys.platform == 'darwin':
                subprocess.call(['open', session.video_path])
            else:
                subprocess.call(['xdg-open', session.video_path])

            self.status_label.setText(f"Playing video: {session_id}")

        except Exception as e:
            logger.error(f"Error playing video: {e}")
            QMessageBox.critical(self, "Playback Error", f"Failed to play video: {e}")

    def delete_selected_session(self):
        """Delete the selected recording session"""
        current_item = self.sessions_tree.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a session to delete")
            return

        session_id = current_item.data(0, Qt.UserRole)

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete session {session_id}?\n\n"
            "This will permanently delete all screenshots and video files.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.delete_session(session_id)

    def delete_session(self, session_id: str):
        """Delete a recording session"""
        try:
            session = self.screen_recorder.get_session(session_id)
            if not session:
                return

            # Delete files
            for screenshot in session.screenshots:
                if os.path.exists(screenshot.image_path):
                    os.remove(screenshot.image_path)

            if session.video_path and os.path.exists(session.video_path):
                os.remove(session.video_path)

            # Remove from recorder
            self.screen_recorder.sessions = [
                s for s in self.screen_recorder.sessions if s.session_id != session_id
            ]

            # Update UI
            self.update_sessions_ui()
            self.status_label.setText(f"Deleted session: {session_id}")

            QMessageBox.information(self, "Session Deleted", f"Session {session_id} has been deleted")

        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            QMessageBox.critical(self, "Delete Error", f"Failed to delete session: {e}")

    def cleanup_old_sessions(self):
        """Clean up old recording sessions"""
        try:
            # Ask for confirmation and days
            dialog = CleanupDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                days = dialog.get_days()
                self.screen_recorder.cleanup_old_sessions(days)
                self.update_sessions_ui()
                self.status_label.setText(f"Cleaned up sessions older than {days} days")

        except Exception as e:
            logger.error(f"Error cleaning up sessions: {e}")
            QMessageBox.critical(self, "Cleanup Error", f"Failed to cleanup sessions: {e}")

    def convert_session_to_workflow(self):
        """Convert selected recording session to workflow"""
        try:
            # Get selected session
            current_item = self.sessions_tree.currentItem()
            if not current_item:
                QMessageBox.warning(self, "No Session Selected", "Please select a recording session to convert to a workflow.")
                return

            session_id = current_item.text(0)
            session = self.screen_recorder.get_session(session_id)
            if not session:
                QMessageBox.warning(self, "Session Not Found", f"Recording session '{session_id}' not found.")
                return

            # Check if session has screenshots
            if not session.screenshots:
                QMessageBox.warning(self, "No Data", "The selected session does not contain any screenshots to analyze.")
                return

            # Launch the workflow conversion wizard
            wizard = WorkflowConversionWizard(self, [session])
            wizard.exec_()

            # Refresh workflows list if conversion was successful
            if wizard.result() == QDialog.Accepted:
                self.update_workflows_ui()
                self.status_label.setText("Successfully converted recording to workflow")

        except Exception as e:
            logger.error(f"Error converting session to workflow: {e}")
            QMessageBox.critical(self, "Conversion Error", f"Failed to convert session to workflow: {e}")

    def capture_button_screenshot(self, button_text: str, button_widget=None):
        """Capture screenshot when a button is clicked"""
        if not self.auto_capture_check.isChecked():
            return

        if not self.screen_recorder.is_recording:
            return

        try:
            # Get button position
            if button_widget:
                button_rect = button_widget.rect()
                button_pos = button_widget.mapToGlobal(button_rect.topLeft())
                button_position = {
                    'x': button_pos.x(),
                    'y': button_pos.y(),
                    'width': button_rect.width(),
                    'height': button_rect.height()
                }
            else:
                # Fallback to cursor position
                cursor_pos = pyautogui.position()
                button_position = {
                    'x': cursor_pos.x - 50,
                    'y': cursor_pos.y - 15,
                    'width': 100,
                    'height': 30
                }

            action_description = f"Button clicked: {button_text}"
            self.screen_recorder.capture_button_screenshot(button_text, button_position, action_description)

            logger.debug(f"Captured button screenshot: {button_text}")

        except Exception as e:
            logger.error(f"Error capturing button screenshot: {e}")

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

                # UI settings are now handled dynamically by workflows

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

                # UI settings are now handled dynamically by workflows

                # Update module settings in main application
                if 'petroleum_launcher' not in self.main_window.settings:
                    self.main_window.settings['petroleum_launcher'] = {}

                self.main_window.settings['petroleum_launcher']['workflows'] = workflows_data

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
                'last_saved': datetime.now().isoformat()
            }

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved configuration to local file: {config_file}")

        except Exception as e:
            logger.error(f"Error saving to local file: {e}")
            raise

    def load_configuration_file(self):
        """Load a configuration file using file dialog"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Load Configuration File",
                str(Path.home() / "Downloads"),
                "JSON Files (*.json);;All Files (*)"
            )

            if file_path:
                self.status_label.setText(f"Loading configuration from {file_path}...")

                # Use the config manager to load the file
                if self.config_manager.load_configuration(file_path):
                    # Refresh the programs detection
                    self.detect_programs()

                    self.status_label.setText(f"Configuration loaded successfully")
                    logger.info(f"Configuration loaded from: {file_path}")
                else:
                    self.status_label.setText("Failed to load configuration")
                    logger.error(f"Failed to load configuration from: {file_path}")

        except Exception as e:
            logger.error(f"Error loading configuration file: {e}")
            self.status_label.setText("Error loading configuration")

    def save_configuration_file(self):
        """Save current configuration to a file using file dialog"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Configuration File",
                str(Path.home() / "Downloads" / "petroleum_config.json"),
                "JSON Files (*.json);;All Files (*)"
            )

            if file_path:
                self.status_label.setText(f"Saving configuration to {file_path}...")

                # Use the config manager to save the file
                if self.config_manager.save_configuration(file_path):
                    self.status_label.setText("Configuration saved successfully")
                    logger.info(f"Configuration saved to: {file_path}")
                else:
                    self.status_label.setText("Failed to save configuration")
                    logger.error(f"Failed to save configuration to: {file_path}")

        except Exception as e:
            logger.error(f"Error saving configuration file: {e}")
            self.status_label.setText("Error saving configuration")

    def export_configuration_file(self):
        """Export current configuration with metadata"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Configuration",
                str(Path.home() / "Downloads" / f"petroleum_config_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"),
                "JSON Files (*.json);;All Files (*)"
            )

            if file_path:
                self.status_label.setText(f"Exporting configuration to {file_path}...")

                # Use the config manager to export the file
                if self.config_manager.export_configuration(file_path):
                    self.status_label.setText("Configuration exported successfully")
                    logger.info(f"Configuration exported to: {file_path}")
                else:
                    self.status_label.setText("Failed to export configuration")
                    logger.error(f"Failed to export configuration to: {file_path}")

        except Exception as e:
            logger.error(f"Error exporting configuration file: {e}")
            self.status_label.setText("Error exporting configuration")

    def add_program_from_uninstaller_data(self):
        """Add or update program configuration from uninstaller registry data with editable fields"""
        try:
            # Create a dialog for input
            dialog = QDialog(self)
            dialog.setWindowTitle("Add Program from Uninstaller Data")
            dialog.setMinimumSize(700, 650)

            layout = QVBoxLayout(dialog)

            # Instructions
            instructions = QLabel(
                "Paste the uninstaller registry data below. The fields will be populated automatically,\n"
                "and the system will try to find the executable. You can edit any field before saving."
            )
            instructions.setWordWrap(True)
            layout.addWidget(instructions)

            # Text area for uninstaller data input
            input_group = QGroupBox("📋 Uninstaller Data Input")
            input_layout = QVBoxLayout(input_group)

            text_area = QTextEdit()
            text_area.setPlaceholderText("Paste uninstaller data here...\nExample:\nDisplayName=CMG 2024.20 Release\nInstallLocation=D:\\Program Files\\CMG\\")
            text_area.setMaximumHeight(100)
            input_layout.addWidget(text_area)

            layout.addWidget(input_group)

            # Editable fields group
            fields_group = QGroupBox("✏️ Editable Program Information")
            fields_layout = QFormLayout(fields_group)

            # Program Name
            name_edit = QLineEdit()
            name_edit.setPlaceholderText("Program name will be extracted from DisplayName")
            fields_layout.addRow("Program Name*:", name_edit)

            # Install Location
            location_layout = QHBoxLayout()
            location_edit = QLineEdit()
            location_edit.setPlaceholderText("Install location will be extracted from InstallLocation")
            browse_btn = QPushButton("Browse...")
            browse_btn.setMaximumWidth(80)
            location_layout.addWidget(location_edit)
            location_layout.addWidget(browse_btn)
            fields_layout.addRow("Install Location*:", location_layout)

            # Publisher
            publisher_edit = QLineEdit()
            publisher_edit.setPlaceholderText("Publisher will be extracted from Publisher field")
            fields_layout.addRow("Publisher:", publisher_edit)

            # Version
            version_edit = QLineEdit()
            version_edit.setPlaceholderText("Version will be extracted from DisplayVersion")
            fields_layout.addRow("Version:", version_edit)

            # Executable detection and selection
            exe_group = QGroupBox("🔍 Executable Detection")
            exe_layout = QVBoxLayout(exe_group)

            # Executable path with browse button
            exe_path_layout = QHBoxLayout()
            exe_path_edit = QLineEdit()
            exe_path_edit.setPlaceholderText("Detected executable path will appear here")
            exe_path_edit.setReadOnly(True)
            exe_browse_btn = QPushButton("Browse Manually...")
            exe_browse_btn.setMaximumWidth(120)
            exe_path_layout.addWidget(exe_path_edit)
            exe_path_layout.addWidget(exe_browse_btn)
            exe_layout.addLayout(exe_path_layout)

            # Alternative executables
            exe_layout.addWidget(QLabel("Alternative Executables:"))
            alt_exes_edit = QTextEdit()
            alt_exes_edit.setMaximumHeight(60)
            alt_exes_edit.setPlaceholderText("Alternative executable names (one per line)")
            exe_layout.addWidget(alt_exes_edit)

            layout.addWidget(fields_group)
            layout.addWidget(exe_group)

            # Detection status
            status_label = QLabel("")
            status_label.setStyleSheet("QLabel { color: #666; font-style: italic; }")
            layout.addWidget(status_label)

            # Buttons
            button_layout = QHBoxLayout()

            def parse_uninstaller_data():
                """Parse uninstaller data and populate editable fields"""
                uninstaller_data = text_area.toPlainText().strip()
                if not uninstaller_data:
                    status_label.setText("⚠️ Please paste uninstaller data first")
                    return False

                # Parse the data
                parsed_data = {}
                for line in uninstaller_data.split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        parsed_data[key.strip()] = value.strip()

                # Populate fields with parsed data
                display_name = parsed_data.get('DisplayName', '')
                install_location = parsed_data.get('InstallLocation', '')
                display_version = parsed_data.get('DisplayVersion', '')
                publisher = parsed_data.get('Publisher', '')

                name_edit.setText(display_name)
                location_edit.setText(install_location)
                version_edit.setText(display_version)
                publisher_edit.setText(publisher)

                status_label.setText(f"✅ Parsed data for: {display_name or 'Unknown Program'}")
                return True

            def detect_executable():
                """Try to find executable automatically"""
                install_location = location_edit.text().strip()
                display_name = name_edit.text().strip()
                publisher = publisher_edit.text().strip()

                if not install_location:
                    status_label.setText("⚠️ Please provide install location first")
                    return

                if not os.path.exists(install_location):
                    status_label.setText(f"⚠️ Install location does not exist: {install_location}")
                    return

                status_label.setText("🔍 Searching for executables...")

                # Find main executable
                main_exe = self._find_main_executable_from_path(install_location, display_name, publisher)
                if main_exe:
                    exe_path_edit.setText(main_exe)
                    status_label.setText(f"✅ Found executable: {os.path.basename(main_exe)}")
                else:
                    exe_path_edit.setText("")
                    status_label.setText("⚠️ No executable found automatically - please browse manually")

                # Find alternative executables
                alt_exes = self._find_alternative_executables(install_location, display_name, publisher)
                if alt_exes:
                    alt_exes_edit.setPlainText('\n'.join(alt_exes))

            def browse_location():
                """Browse for install location"""
                directory = QFileDialog.getExistingDirectory(dialog, "Select Install Location")
                if directory:
                    location_edit.setText(directory)

            def browse_executable():
                """Browse for executable manually"""
                install_location = location_edit.text().strip()
                if install_location and os.path.exists(install_location):
                    start_dir = install_location
                else:
                    start_dir = "C:\\Program Files"

                file_path, _ = QFileDialog.getOpenFileName(
                    dialog, "Select Executable", start_dir, "Executable Files (*.exe)"
                )
                if file_path:
                    exe_path_edit.setText(file_path)
                    status_label.setText(f"✅ Manually selected: {os.path.basename(file_path)}")

            # Connect signals
            text_area.textChanged.connect(parse_uninstaller_data)
            location_edit.textChanged.connect(detect_executable)
            browse_btn.clicked.connect(browse_location)
            exe_browse_btn.clicked.connect(browse_executable)

            # Parse initial data if clipboard has content
            clipboard = QApplication.clipboard()
            if clipboard.text():
                text_area.setText(clipboard.text())
                parse_uninstaller_data()
                detect_executable()

            def add_program():
                """Add the program with all configurations"""
                program_name = name_edit.text().strip()
                install_location = location_edit.text().strip()
                executable_path = exe_path_edit.text().strip()

                if not program_name or not install_location:
                    QMessageBox.warning(dialog, "Warning", "Program Name and Install Location are required.")
                    return

                if not executable_path:
                    reply = QMessageBox.question(dialog, "No Executable",
                        "No executable was found. Continue anyway?",
                        QMessageBox.Yes | QMessageBox.No)
                    if reply == QMessageBox.No:
                        return

                # Create program configuration
                program_key = program_name.lower().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '').replace('.', '')
                alt_executables = [line.strip() for line in alt_exes_edit.toPlainText().split('\n') if line.strip()]

                program_config = {
                    "display_name": program_name,
                    "target_version": version_edit.text().strip() or "latest",
                    "identity": {
                        "expected_product_names": [program_name, publisher_edit.text().strip()],
                        "expected_descriptions": [program_name, f"{publisher_edit.text().strip()} Software"],
                        "installer_patterns": [f"{program_name.replace(' ', '*')}*.exe"]
                    },
                    "check_method": {
                        "type": "path",
                        "paths": [install_location]
                    },
                    "automation_capabilities": {
                        "can_record": True,
                        "has_scripting": True,
                        "common_automations": ["data_processing", "analysis", "workflow_automation"],
                        "ui_elements": ["main_window", "workspace", "tools"],
                        "file_types": ["*.*"]
                    },
                    "executable_info": {
                        "main_executable": executable_path,
                        "alternative_names": alt_executables,
                        "common_locations": [install_location],
                        "search_patterns": ["*.exe"]
                    }
                }

                # Add to configuration manager
                if self.config_manager.add_program(program_key, program_config):
                    logger.info(f"Successfully added program from uninstaller data: {program_key}")

                    QMessageBox.information(dialog, "Success",
                        f"Successfully added/updated {program_name} configuration.\n"
                        f"Program Key: {program_key}\n"
                        f"Install Location: {install_location}\n"
                        f"Executable: {executable_path or 'Not specified'}\n"
                        f"Config File: {self.config_manager.config_file}")

                    # Refresh program detection
                    self.detect_programs()
                    dialog.accept()
                else:
                    logger.error(f"Failed to add program: {program_key}")
                    QMessageBox.critical(dialog, "Error", "Failed to add program configuration.")

            # Dialog buttons
            ok_btn = QPushButton("➕ Add Program")
            ok_btn.clicked.connect(add_program)
            button_layout.addWidget(ok_btn)

            cancel_btn = QPushButton("❌ Cancel")
            cancel_btn.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_btn)

            layout.addLayout(button_layout)

            # Show dialog
            if dialog.exec_() == QDialog.Accepted:
                self.status_label.setText("Program configuration added successfully")
                logger.info(f"Added program configuration from uninstaller data with editable fields")

        except Exception as e:
            logger.error(f"Error adding program from uninstaller data: {e}")
            QMessageBox.critical(self, "Error", f"Failed to add program: {str(e)}")

    
    def handle_config_action(self, index):
        """Handle configuration dropdown actions"""
        try:
            if index == 0:  # Default/placeholder item
                return

            action_text = self.sender().itemText(index)

            if "Refresh Programs" in action_text:
                self.detect_programs()
            elif "Load Configuration File" in action_text:
                self.load_configuration_file()
            elif "Save Configuration" in action_text:
                self.save_configuration_file()
            elif "Export Configuration" in action_text:
                self.export_configuration_file()
            elif "Add from Uninstaller Data" in action_text:
                self.add_program_from_uninstaller_data()
            elif "Clear All Programs" in action_text:
                self.clear_all_programs()

            # Reset dropdown to first item after action
            self.sender().setCurrentIndex(0)

        except Exception as e:
            logger.error(f"Error handling config action: {e}")
            QMessageBox.critical(self, "Error", f"Failed to perform action: {str(e)}")

    def clear_all_programs(self):
        """Clear all configured programs"""
        reply = QMessageBox.question(
            self, "Clear All Programs",
            "Are you sure you want to remove all configured programs?\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                # Clear all programs from config
                self.config_manager.config.clear()
                self.config_manager.save_configuration()

                # Clear detected programs
                self.detected_programs.clear()

                # Clear the UI
                self.programs_tree.clear()

                # Show help message
                if hasattr(self, 'no_programs_label'):
                    self.no_programs_label.show()

                self.status_label.setText("All programs cleared")
                logger.info("All programs cleared successfully")
                QMessageBox.information(self, "Success", "All programs have been cleared.")

            except Exception as e:
                logger.error(f"Error clearing programs: {e}")
                QMessageBox.critical(self, "Error", f"Failed to clear programs: {str(e)}")

    def _browse_for_directory(self, line_edit):
        """Browse for a directory and update the line edit"""
        directory = QFileDialog.getExistingDirectory(self, "Select Program Install Directory")
        if directory:
            line_edit.setText(directory)

    def _find_main_executable_from_path(self, install_location: str, display_name: str, publisher: str) -> str:
        """Find the main executable from the install location"""
        try:
            import glob
            import os

            if not os.path.exists(install_location):
                return f"{display_name.replace(' ', '')}.exe"

            # Look for common main executable patterns
            common_patterns = [
                f"{display_name}.exe",
                f"{display_name.replace(' ', '')}.exe",
                f"{publisher}.exe",
                "main.exe",
                "app.exe",
                "run.exe"
            ]

            # Search for exact matches first
            for pattern in common_patterns:
                full_path = os.path.join(install_location, pattern)
                if os.path.exists(full_path):
                    return pattern

            # Search for executables containing program name
            exe_files = []
            for ext in ['*.exe']:
                exe_files.extend(glob.glob(os.path.join(install_location, ext)))

            # Try to find the most likely main executable
            for exe_file in exe_files:
                exe_name = os.path.basename(exe_file).lower()
                display_lower = display_name.lower()
                publisher_lower = publisher.lower()

                # Priority 1: Exact match with display name
                if display_lower in exe_name:
                    return os.path.basename(exe_file)

                # Priority 2: Contains publisher name
                if publisher_lower in exe_name and len(exe_name) > 5:
                    return os.path.basename(exe_file)

                # Priority 3: Common application names
                if exe_name in ['main.exe', 'app.exe', 'run.exe', 'start.exe']:
                    return os.path.basename(exe_file)

            # If no good match, return the first exe file found
            if exe_files:
                return os.path.basename(exe_files[0])

            # Fallback
            return f"{display_name.replace(' ', '')}.exe"

        except Exception as e:
            logger.error(f"Error finding main executable: {e}")
            return f"{display_name.replace(' ', '')}.exe"

    def _find_alternative_executables(self, install_location: str, display_name: str, publisher: str) -> list:
        """Find alternative executable names"""
        try:
            import glob
            import os

            alternatives = []
            if not os.path.exists(install_location):
                return alternatives

            # Find all exe files
            exe_files = []
            for ext in ['*.exe']:
                exe_files.extend(glob.glob(os.path.join(install_location, ext)))

            # Add all executables except the main one
            main_exe = self._find_main_executable_from_path(install_location, display_name, publisher)
            for exe_file in exe_files:
                exe_name = os.path.basename(exe_file)
                if exe_name != main_exe:
                    alternatives.append(exe_name)

            return alternatives[:5]  # Limit to 5 alternatives

        except Exception as e:
            logger.error(f"Error finding alternative executables: {e}")
            return []

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

        # Stop screenshot recording if active
        if self.screen_recorder.is_recording:
            try:
                self.screen_recorder.stop_recording()
                logger.info("Stopped screenshot recording due to widget close")
            except Exception as e:
                logger.error(f"Error stopping screenshot recording: {e}")

        # Stop automation recording if active
        if self.screen_recorder.automation_recorder.is_recording:
            try:
                self.screen_recorder.automation_recorder.stop_recording()
                logger.info("Stopped automation recording due to widget close")
            except Exception as e:
                logger.error(f"Error stopping automation recording: {e}")

        # Save configuration
        self.save_configuration()

        event.accept()


class RecordingAnalysis:
    """Analyzes recorded sessions to identify patterns and convert to workflows"""

    def __init__(self):
        self.patterns = []
        self.petroleum_patterns = self._initialize_petroleum_patterns()

    def _initialize_petroleum_patterns(self) -> Dict[str, Any]:
        """Initialize known petroleum software patterns"""
        return {
            'Petrel': {
                'menu_patterns': [
                    r'File|New|Project',
                    r'File|Open|Project',
                    r'Insert|New.*',
                    r'Processes|Define.*',
                    r'Window|Tile'
                ],
                'button_patterns': [
                    'OK', 'Cancel', 'Apply', 'Next', 'Previous', 'Finish',
                    'Run', 'Execute', 'Calculate', 'Import', 'Export'
                ],
                'window_titles': [
                    'Petrel', 'Petrel -', 'Project', 'Settings', 'Input', 'Results'
                ]
            },
            'Harmony Enterprise': {
                'menu_patterns': [
                    r'File|New.*Case',
                    r'File|Open.*Case',
                    r'Run|Start',
                    r'Tools|.*',
                    r'Results|.*'
                ],
                'button_patterns': [
                    'Start Run', 'Run', 'OK', 'Cancel', 'Apply', 'Save',
                    'Load', 'Import', 'Export', 'Plot', 'Report'
                ],
                'window_titles': [
                    'Harmony', 'Enterprise', 'Case Manager', 'Results'
                ]
            },
            'Kappa': {
                'menu_patterns': [
                    r'File|New.*',
                    r'File|Open.*',
                    r'Analysis|.*',
                    r'Tools|.*'
                ],
                'button_patterns': [
                    'Analyze', 'Calculate', 'Run', 'OK', 'Cancel',
                    'Plot', 'Export', 'Import'
                ],
                'window_titles': [
                    'Kappa', 'Kappa -', 'Analysis', 'Results'
                ]
            }
        }

    def analyze_session(self, session: RecordingSession) -> Dict[str, Any]:
        """Analyze a recording session for patterns and workflow steps"""
        if not session.screenshots and not session.description:
            return {'error': 'No data to analyze'}

        analysis = {
            'session_id': session.session_id,
            'total_actions': len(session.screenshots),
            'duration': self._calculate_duration(session),
            'detected_software': self._detect_software(session),
            'identified_patterns': [],
            'workflow_steps': [],
            'confidence_score': 0.0,
            'recommendations': []
        }

        # Analyze screenshots for patterns
        if session.screenshots:
            analysis['identified_patterns'] = self._identify_patterns(session.screenshots)
            analysis['workflow_steps'] = self._convert_to_workflow_steps(session.screenshots)
            analysis['confidence_score'] = self._calculate_confidence_score(analysis)

        # Add recommendations
        analysis['recommendations'] = self._generate_recommendations(analysis)

        return analysis

    def _calculate_duration(self, session: RecordingSession) -> float:
        """Calculate session duration in minutes"""
        try:
            start_time = datetime.fromisoformat(session.start_time.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(session.end_time.replace('Z', '+00:00'))
            return (end_time - start_time).total_seconds() / 60.0
        except:
            return 0.0

    def _detect_software(self, session: RecordingSession) -> List[str]:
        """Detect which software was used in the session"""
        detected = set()

        if session.screenshots:
            for screenshot in session.screenshots:
                window_title = getattr(screenshot, 'window_title', '').lower()
                button_text = getattr(screenshot, 'button_text', '').lower()

                # Check window titles
                for software, patterns in self.petroleum_patterns.items():
                    if any(title.lower() in window_title for title in patterns['window_titles']):
                        detected.add(software)

                # Check button text for software-specific terms
                if 'petrel' in window_title or 'petrel' in button_text:
                    detected.add('Petrel')
                elif 'harmony' in window_title or 'enterprise' in window_title:
                    detected.add('Harmony Enterprise')
                elif 'kappa' in window_title:
                    detected.add('Kappa')

        return list(detected)

    def _identify_patterns(self, screenshots: List[ScreenshotRecord]) -> List[Dict[str, Any]]:
        """Identify patterns in the sequence of actions"""
        patterns = []

        if not screenshots:
            return patterns

        # Group screenshots by window titles
        window_sequences = self._group_by_window(screenshots)

        # Identify menu navigation patterns
        menu_patterns = self._identify_menu_patterns(screenshots)
        patterns.extend(menu_patterns)

        # Identify data entry patterns
        data_patterns = self._identify_data_entry_patterns(screenshots)
        patterns.extend(data_patterns)

        # Identify dialog interaction patterns
        dialog_patterns = self._identify_dialog_patterns(screenshots)
        patterns.extend(dialog_patterns)

        return patterns

    def _group_by_window(self, screenshots: List[ScreenshotRecord]) -> Dict[str, List[ScreenshotRecord]]:
        """Group screenshots by window title"""
        groups = {}
        for screenshot in screenshots:
            window_title = getattr(screenshot, 'window_title', 'Unknown')
            if window_title not in groups:
                groups[window_title] = []
            groups[window_title].append(screenshot)
        return groups

    def _identify_menu_patterns(self, screenshots: List[ScreenshotRecord]) -> List[Dict[str, Any]]:
        """Identify menu navigation patterns"""
        patterns = []

        # Look for sequences that might be menu navigation
        for i, screenshot in enumerate(screenshots):
            button_text = getattr(screenshot, 'button_text', '').lower()

            # Common menu items
            menu_items = ['file', 'edit', 'view', 'insert', 'tools', 'help', 'window', 'processes']
            for menu_item in menu_items:
                if menu_item in button_text:
                    patterns.append({
                        'type': 'menu_navigation',
                        'action': button_text,
                        'position': i,
                        'confidence': 0.8,
                        'description': f"Menu navigation: {button_text}"
                    })

        return patterns

    def _identify_data_entry_patterns(self, screenshots: List[ScreenshotRecord]) -> List[Dict[str, Any]]:
        """Identify data entry patterns"""
        patterns = []

        # Look for input fields and value entry
        for i, screenshot in enumerate(screenshots):
            action_desc = getattr(screenshot, 'action_description', '').lower()

            # Common data entry indicators
            if any(keyword in action_desc for keyword in ['enter', 'type', 'input', 'value', 'field']):
                patterns.append({
                    'type': 'data_entry',
                    'action': action_desc,
                    'position': i,
                    'confidence': 0.7,
                    'description': f"Data entry: {action_desc}"
                })

        return patterns

    def _identify_dialog_patterns(self, screenshots: List[ScreenshotRecord]) -> List[Dict[str, Any]]:
        """Identify dialog interaction patterns"""
        patterns = []

        # Look for dialog button interactions
        for i, screenshot in enumerate(screenshots):
            button_text = getattr(screenshot, 'button_text', '').lower()

            # Common dialog buttons
            dialog_buttons = ['ok', 'cancel', 'apply', 'yes', 'no', 'next', 'previous', 'finish', 'save', 'don\'t save']
            if button_text in dialog_buttons:
                patterns.append({
                    'type': 'dialog_interaction',
                    'action': button_text,
                    'position': i,
                    'confidence': 0.9,
                    'description': f"Dialog interaction: {button_text}"
                })

        return patterns

    def _convert_to_workflow_steps(self, screenshots: List[ScreenshotRecord]) -> List[Dict[str, Any]]:
        """Convert screenshots to workflow steps"""
        steps = []

        for i, screenshot in enumerate(screenshots):
            step = {
                'step_number': i + 1,
                'action_type': self._determine_action_type(screenshot),
                'description': getattr(screenshot, 'action_description', 'Unknown action'),
                'target': {
                    'button_text': getattr(screenshot, 'button_text', ''),
                    'position': getattr(screenshot, 'button_position', {'x': 0, 'y': 0}),
                    'window_title': getattr(screenshot, 'window_title', ''),
                    'image_path': getattr(screenshot, 'image_path', '')
                },
                'confidence': 0.8,
                'estimated_time': 2.0  # Default 2 seconds per action
            }

            steps.append(step)

        return steps

    def _determine_action_type(self, screenshot: ScreenshotRecord) -> str:
        """Determine the type of action from screenshot data"""
        button_text = getattr(screenshot, 'button_text', '').lower()
        action_desc = getattr(screenshot, 'action_description', '').lower()

        if any(keyword in button_text for keyword in ['ok', 'cancel', 'apply', 'save', 'yes', 'no']):
            return 'click_button'
        elif any(keyword in action_desc for keyword in ['enter', 'type', 'input']):
            return 'input_text'
        elif 'menu' in action_desc or any(keyword in button_text for keyword in ['file', 'edit', 'view']):
            return 'menu_navigation'
        elif any(keyword in button_text for keyword in ['next', 'previous', 'browse']):
            return 'navigate'
        else:
            return 'click'

    def _calculate_confidence_score(self, analysis: Dict[str, Any]) -> float:
        """Calculate confidence score for the analysis"""
        score = 0.0

        # Base score from identified patterns
        if analysis['identified_patterns']:
            pattern_confidence = sum(p.get('confidence', 0) for p in analysis['identified_patterns'])
            score += min(pattern_confidence / len(analysis['identified_patterns']), 1.0) * 0.4

        # Software detection confidence
        if analysis['detected_software']:
            score += 0.3

        # Workflow steps confidence
        if analysis['workflow_steps']:
            step_confidence = sum(s.get('confidence', 0) for s in analysis['workflow_steps'])
            score += min(step_confidence / len(analysis['workflow_steps']), 1.0) * 0.3

        return min(score, 1.0)

    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate recommendations for improving the recording"""
        recommendations = []

        if analysis['confidence_score'] < 0.5:
            recommendations.append("Low confidence detected. Consider re-recording with clearer button clicks.")

        if analysis['total_actions'] < 3:
            recommendations.append("Very few actions recorded. Consider recording a more complete workflow.")

        if not analysis['detected_software']:
            recommendations.append("No specific petroleum software detected. Ensure software windows are visible during recording.")

        if analysis['confidence_score'] > 0.8:
            recommendations.append("High confidence recording! This session is suitable for workflow conversion.")

        # Add software-specific recommendations
        for software in analysis['detected_software']:
            if software in self.petroleum_patterns:
                recommendations.append(f"Detected {software} usage. Consider using petroleum-specific templates for better results.")

        return recommendations


class DragDropRecorder(QWidget):
    """Visual drag-and-drop recording interface for capturing UI elements"""

    element_captured = pyqtSignal(dict)  # Signal when element is captured

    def __init__(self, parent=None):
        super().__init__(parent)
        self.captured_elements = []
        self.is_recording = False
        self.drag_active = False
        self.overlay_window = None
        self.initUI()

    def initUI(self):
        """Initialize the drag-and-drop recording interface"""
        self.setWindowTitle("Drag & Drop Recorder")
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)

        # Header with instructions
        header_label = QLabel("Drag & Drop Element Recorder")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(header_label)

        instructions = QLabel(
            "1. Click 'Start Recording'\n"
            "2. Drag UI elements from other applications to this window\n"
            "3. Elements will be captured and added to the workflow\n"
            "4. Click 'Stop Recording' when finished"
        )
        instructions.setStyleSheet("background-color: #ecf0f1; padding: 10px; border-radius: 5px; margin-bottom: 15px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Recording controls
        controls_layout = QHBoxLayout()

        self.start_recording_btn = QPushButton("Start Recording")
        self.start_recording_btn.clicked.connect(self.start_recording)
        self.start_recording_btn.setStyleSheet("QPushButton { background-color: #27ae60; color: white; font-weight: bold; padding: 8px; }")
        controls_layout.addWidget(self.start_recording_btn)

        self.stop_recording_btn = QPushButton("Stop Recording")
        self.stop_recording_btn.clicked.connect(self.stop_recording)
        self.stop_recording_btn.setEnabled(False)
        self.stop_recording_btn.setStyleSheet("QPushButton { background-color: #e74c3c; color: white; font-weight: bold; padding: 8px; }")
        controls_layout.addWidget(self.stop_recording_btn)

        layout.addLayout(controls_layout)

        # Status indicator
        self.status_label = QLabel("Status: Ready to record")
        self.status_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: #f8f9fa; border: 1px solid #dee2e6;")
        layout.addWidget(self.status_label)

        # Drop zone
        self.drop_zone = QWidget()
        self.drop_zone.setMinimumHeight(200)
        self.drop_zone.setStyleSheet(
            "QWidget { background-color: #f8f9fa; border: 2px dashed #6c757d; border-radius: 10px; }"
        )
        drop_zone_layout = QVBoxLayout(self.drop_zone)

        drop_label = QLabel("Drop UI Elements Here")
        drop_label.setAlignment(Qt.AlignCenter)
        drop_label.setStyleSheet("font-size: 14px; color: #6c757d; font-weight: bold;")
        drop_zone_layout.addWidget(drop_label)

        drop_icon = QLabel("📋")
        drop_icon.setAlignment(Qt.AlignCenter)
        drop_icon.setStyleSheet("font-size: 48px; margin: 20px;")
        drop_zone_layout.addWidget(drop_icon)

        self.drop_hint = QLabel("Drag buttons, menus, or other UI elements from petroleum software")
        self.drop_hint.setAlignment(Qt.AlignCenter)
        self.drop_hint.setStyleSheet("color: #6c757d; font-style: italic;")
        drop_zone_layout.addWidget(self.drop_hint)

        layout.addWidget(self.drop_zone)

        # Captured elements list
        elements_group = QGroupBox("Captured Elements")
        elements_layout = QVBoxLayout(elements_group)

        self.elements_list = QListWidget()
        self.elements_list.setMinimumHeight(150)
        elements_layout.addWidget(self.elements_list)

        # Element actions
        element_actions_layout = QHBoxLayout()

        self.edit_element_btn = QPushButton("Edit")
        self.edit_element_btn.clicked.connect(self.edit_selected_element)
        self.edit_element_btn.setEnabled(False)
        element_actions_layout.addWidget(self.edit_element_btn)

        self.remove_element_btn = QPushButton("Remove")
        self.remove_element_btn.clicked.connect(self.remove_selected_element)
        self.remove_element_btn.setEnabled(False)
        element_actions_layout.addWidget(self.remove_element_btn)

        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.clicked.connect(self.clear_all_elements)
        self.clear_all_btn.setEnabled(False)
        element_actions_layout.addWidget(self.clear_all_btn)

        element_actions_layout.addStretch()
        elements_layout.addLayout(element_actions_layout)

        layout.addWidget(elements_group)

        # Connect list selection signal
        self.elements_list.itemSelectionChanged.connect(self.on_element_selection_changed)

        # Enable drag and drop
        self.setAcceptDrops(True)
        self.drop_zone.setAcceptDrops(True)

    def start_recording(self):
        """Start drag-and-drop recording"""
        self.is_recording = True
        self.captured_elements = []

        self.start_recording_btn.setEnabled(False)
        self.stop_recording_btn.setEnabled(True)
        self.clear_all_btn.setEnabled(True)

        self.status_label.setText("Status: Recording - Drag elements here")
        self.status_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: #d4edda; border: 1px solid #c3e6cb; color: #155724;")

        self.drop_zone.setStyleSheet(
            "QWidget { background-color: #d4edda; border: 2px dashed #28a745; border-radius: 10px; }"
        )

        # Show overlay guide
        self.show_recording_overlay()

    def stop_recording(self):
        """Stop drag-and-drop recording"""
        self.is_recording = False

        self.start_recording_btn.setEnabled(True)
        self.stop_recording_btn.setEnabled(False)

        self.status_label.setText(f"Status: Recording stopped - {len(self.captured_elements)} elements captured")
        self.status_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: #f8f9fa; border: 1px solid #dee2e6;")

        self.drop_zone.setStyleSheet(
            "QWidget { background-color: #f8f9fa; border: 2px dashed #6c757d; border-radius: 10px; }"
        )

        # Hide overlay guide
        if self.overlay_window:
            self.overlay_window.close()
            self.overlay_window = None

    def show_recording_overlay(self):
        """Show an overlay window with recording instructions"""
        try:
            self.overlay_window = QWidget()
            self.overlay_window.setWindowTitle("Recording Guide")
            self.overlay_window.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Tool)
            self.overlay_window.resize(300, 150)
            self.overlay_window.move(100, 100)

            overlay_layout = QVBoxLayout(self.overlay_window)

            guide_label = QLabel("🎯 Recording Guide\n\n• Switch to your petroleum software\n• Click and drag UI elements\n• Drop them in the recorder window\n• Right-click to cancel an element")
            guide_label.setWordWrap(True)
            guide_label.setStyleSheet("padding: 10px; background-color: #e3f2fd; border-radius: 5px;")
            overlay_layout.addWidget(guide_label)

            close_btn = QPushButton("Close Guide")
            close_btn.clicked.connect(self.overlay_window.close)
            overlay_layout.addWidget(close_btn)

            self.overlay_window.show()

        except Exception as e:
            logger.error(f"Error showing recording overlay: {e}")

    def dragEnterEvent(self, event):
        """Handle drag enter event"""
        if self.is_recording:
            if event.mimeData().hasUrls() or event.mimeData().hasText():
                event.acceptProposedAction()
                self.drop_zone.setStyleSheet(
                    "QWidget { background-color: #cce5ff; border: 2px solid #007bff; border-radius: 10px; }"
                )

    def dragMoveEvent(self, event):
        """Handle drag move event"""
        if self.is_recording:
            if event.mimeData().hasUrls() or event.mimeData().hasText():
                event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        """Handle drag leave event"""
        if self.is_recording:
            self.drop_zone.setStyleSheet(
                "QWidget { background-color: #d4edda; border: 2px dashed #28a745; border-radius: 10px; }"
            )

    def dropEvent(self, event):
        """Handle drop event - capture UI element information"""
        if not self.is_recording:
            return

        try:
            # Get drop position
            drop_pos = event.pos()

            # Get screen position at drop
            global_pos = self.mapToGlobal(drop_pos)

            # Capture element information
            element_info = self.capture_element_at_position(global_pos.x(), global_pos.y())

            if element_info:
                # Add element to captured list
                self.captured_elements.append(element_info)
                self.add_element_to_list(element_info)
                self.element_captured.emit(element_info)

                # Update status
                self.status_label.setText(f"Status: Recording - {len(self.captured_elements)} elements captured")

            # Reset drop zone style
            self.drop_zone.setStyleSheet(
                "QWidget { background-color: #d4edda; border: 2px dashed #28a745; border-radius: 10px; }"
            )

            event.acceptProposedAction()

        except Exception as e:
            logger.error(f"Error handling drop event: {e}")
            QMessageBox.warning(self, "Drop Error", f"Failed to capture element: {e}")

    def capture_element_at_position(self, x: int, y: int) -> Optional[Dict[str, Any]]:
        """Capture information about UI element at screen position"""
        try:
            # Take screenshot at position
            screenshot = pyautogui.screenshot(region=(x-25, y-25, 50, 50))

            # Get active window information
            active_window = pyautogui.getActiveWindow()
            window_title = active_window.title if active_window else ""

            # Detect petroleum software
            detected_software = self._detect_petroleum_software(window_title)

            # Try to identify element type using position and heuristics
            element_type = self._identify_element_type(x, y, screenshot)

            # Generate element name
            element_name = self._generate_element_name(element_type, x, y, window_title)

            # Create element info
            element_info = {
                'id': f"element_{len(self.captured_elements) + 1}_{int(time.time())}",
                'name': element_name,
                'type': element_type,
                'position': {'x': x, 'y': y},
                'window_title': window_title,
                'software': detected_software,
                'screenshot': screenshot,
                'timestamp': datetime.now().isoformat(),
                'confidence': self._calculate_element_confidence(element_type, detected_software, window_title),
                'action_type': self._suggest_action_type(element_type),
                'description': f"{element_type.title()} at ({x}, {y}) in {window_title}"
            }

            return element_info

        except Exception as e:
            logger.error(f"Error capturing element at position ({x}, {y}): {e}")
            return None

    def _detect_petroleum_software(self, window_title: str) -> Optional[str]:
        """Detect petroleum software from window title"""
        window_title_lower = window_title.lower()

        if 'petrel' in window_title_lower:
            return 'Petrel'
        elif 'harmony' in window_title_lower:
            return 'Harmony Enterprise'
        elif 'kappa' in window_title_lower:
            return 'Kappa'
        elif 'cmg' in window_title_lower:
            return 'CMG'
        elif any(keyword in window_title_lower for keyword in ['prosper', 'gap', 'ipm']):
            return 'Petroleum Experts'

        return None

    def _identify_element_type(self, x: int, y: int, screenshot) -> str:
        """Identify the type of UI element based on position and appearance"""
        # This is a simplified implementation
        # In a real system, you would use image processing to analyze the screenshot

        # For now, use basic heuristics based on position
        screen_width, screen_height = pyautogui.size()

        # Check if near top (likely menu bar)
        if y < 100:
            return 'menu_item'

        # Check if near edges (likely toolbar or panel)
        if x < 100 or x > screen_width - 100:
            return 'toolbar_button'

        # Check if near bottom (likely status bar)
        if y > screen_height - 100:
            return 'status_bar_element'

        # Default to generic button
        return 'button'

    def _generate_element_name(self, element_type: str, x: int, y: int, window_title: str) -> str:
        """Generate a meaningful name for the captured element"""
        software = self._detect_petroleum_software(window_title) or "Application"

        # Generate name based on element type and software
        if element_type == 'menu_item':
            return f"{software} Menu Item"
        elif element_type == 'toolbar_button':
            return f"{software} Toolbar Button"
        elif element_type == 'status_bar_element':
            return f"{software} Status Element"
        else:
            return f"{software} {element_type.title()} {len(self.captured_elements) + 1}"

    def _calculate_element_confidence(self, element_type: str, software: Optional[str], window_title: str) -> float:
        """Calculate confidence score for element identification"""
        confidence = 0.5  # Base confidence

        # Increase confidence if petroleum software is detected
        if software:
            confidence += 0.3

        # Increase confidence for common element types
        if element_type in ['button', 'menu_item', 'toolbar_button']:
            confidence += 0.1

        # Increase confidence if window title contains relevant keywords
        if any(keyword in window_title.lower() for keyword in ['project', 'process', 'run', 'simulate']):
            confidence += 0.1

        return min(confidence, 1.0)

    def _suggest_action_type(self, element_type: str) -> str:
        """Suggest the best action type for this element"""
        action_mapping = {
            'button': 'click',
            'menu_item': 'click',
            'toolbar_button': 'click',
            'status_bar_element': 'click',
            'text_field': 'input_text',
            'dropdown': 'select_option',
            'checkbox': 'toggle',
            'radio_button': 'select'
        }

        return action_mapping.get(element_type, 'click')

    def add_element_to_list(self, element_info: Dict[str, Any]):
        """Add captured element to the list widget"""
        item_text = f"📋 {element_info['name']} ({element_info['type']})"
        item = QListWidgetItem(item_text)
        item.setData(Qt.UserRole, element_info)

        # Color code by confidence
        confidence = element_info.get('confidence', 0.5)
        if confidence > 0.8:
            item.setStyleSheet("color: #27ae60; font-weight: bold;")
        elif confidence > 0.6:
            item.setStyleSheet("color: #f39c12;")
        else:
            item.setStyleSheet("color: #e74c3c;")

        self.elements_list.addItem(item)

    def on_element_selection_changed(self):
        """Handle element selection change"""
        has_selection = bool(self.elements_list.currentItem())
        self.edit_element_btn.setEnabled(has_selection)
        self.remove_element_btn.setEnabled(has_selection)

    def edit_selected_element(self):
        """Edit the selected captured element"""
        current_item = self.elements_list.currentItem()
        if not current_item:
            return

        element_info = current_item.data(Qt.UserRole)
        if not element_info:
            return

        # Create edit dialog
        edit_dialog = QDialog(self)
        edit_dialog.setWindowTitle(f"Edit Element: {element_info['name']}")
        edit_dialog.setModal(True)
        edit_dialog.resize(400, 300)

        layout = QVBoxLayout(edit_dialog)

        # Element name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        name_edit = QLineEdit(element_info['name'])
        name_layout.addWidget(name_edit)
        layout.addLayout(name_layout)

        # Action type
        action_layout = QHBoxLayout()
        action_layout.addWidget(QLabel("Action Type:"))
        action_combo = QComboBox()
        action_combo.addItems(['click', 'right_click', 'double_click', 'input_text', 'select_option', 'toggle'])
        action_combo.setCurrentText(element_info.get('action_type', 'click'))
        action_layout.addWidget(action_combo)
        layout.addLayout(action_layout)

        # Description
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        desc_edit = QTextEdit(element_info.get('description', ''))
        desc_edit.setMaximumHeight(80)
        desc_layout.addWidget(desc_edit)
        layout.addLayout(desc_layout)

        # Buttons
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(edit_dialog.accept)
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(edit_dialog.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        if edit_dialog.exec_() == QDialog.Accepted:
            # Update element info
            element_info['name'] = name_edit.text()
            element_info['action_type'] = action_combo.currentText()
            element_info['description'] = desc_edit.toPlainText()

            # Update list item
            item_text = f"📋 {element_info['name']} ({element_info['type']})"
            current_item.setText(item_text)
            current_item.setData(Qt.UserRole, element_info)

    def remove_selected_element(self):
        """Remove the selected captured element"""
        current_item = self.elements_list.currentItem()
        if not current_item:
            return

        element_info = current_item.data(Qt.UserRole)
        if element_info in self.captured_elements:
            self.captured_elements.remove(element_info)

        self.elements_list.takeItem(self.elements_list.row(current_item))

        # Update status
        self.status_label.setText(f"Status: Recording - {len(self.captured_elements)} elements captured")

    def clear_all_elements(self):
        """Clear all captured elements"""
        reply = QMessageBox.question(
            self,
            "Clear All Elements",
            "Are you sure you want to clear all captured elements?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.captured_elements = []
            self.elements_list.clear()
            self.status_label.setText("Status: Recording - No elements captured")

    def get_captured_elements(self) -> List[Dict[str, Any]]:
        """Get the list of captured elements"""
        return self.captured_elements.copy()


class ConditionalRecorder(QWidget):
    """Conditional recording system that captures decision points and logic branches"""

    condition_detected = pyqtSignal(dict)  # Signal when a condition is detected
    branch_created = pyqtSignal(dict)  # Signal when a branch is created

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_recording = False
        self.detected_conditions = []
        self.workflow_branches = []
        self.current_branch = None
        self.recording_history = []
        self.context_tracker = {}
        self.initUI()

    def initUI(self):
        """Initialize the conditional recording interface"""
        self.setWindowTitle("Conditional Logic Recorder")
        self.setMinimumSize(500, 600)

        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel("Conditional Logic Recorder")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(header_label)

        instructions = QLabel(
            "This recorder detects decision points and conditional logic in your workflows:\n\n"
            "• Records if/else decisions based on UI states\n"
            "• Captures branching paths for different scenarios\n"
            "• Identifies error handling and recovery patterns\n"
            "• Creates intelligent workflows with adaptive behavior"
        )
        instructions.setStyleSheet("background-color: #e8f4fd; padding: 10px; border-radius: 5px; margin-bottom: 15px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Recording controls
        controls_layout = QHBoxLayout()

        self.start_recording_btn = QPushButton("Start Conditional Recording")
        self.start_recording_btn.clicked.connect(self.start_conditional_recording)
        self.start_recording_btn.setStyleSheet("QPushButton { background-color: #28a745; color: white; font-weight: bold; padding: 8px; }")
        controls_layout.addWidget(self.start_recording_btn)

        self.stop_recording_btn = QPushButton("Stop Recording")
        self.stop_recording_btn.clicked.connect(self.stop_conditional_recording)
        self.stop_recording_btn.setEnabled(False)
        self.stop_recording_btn.setStyleSheet("QPushButton { background-color: #dc3545; color: white; font-weight: bold; padding: 8px; }")
        controls_layout.addWidget(self.stop_recording_btn)

        self.add_condition_btn = QPushButton("Add Manual Condition")
        self.add_condition_btn.clicked.connect(self.add_manual_condition)
        self.add_condition_btn.setEnabled(False)
        self.add_condition_btn.setStyleSheet("QPushButton { background-color: #ffc107; color: black; font-weight: bold; padding: 8px; }")
        controls_layout.addWidget(self.add_condition_btn)

        layout.addLayout(controls_layout)

        # Status indicator
        self.status_label = QLabel("Status: Ready to record conditional logic")
        self.status_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: #f8f9fa; border: 1px solid #dee2e6;")
        layout.addWidget(self.status_label)

        # Tab widget for different views
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Detected conditions tab
        self.create_conditions_tab()

        # Workflow branches tab
        self.create_branches_tab()

        # Logic patterns tab
        self.create_patterns_tab()

    def create_conditions_tab(self):
        """Create the detected conditions tab"""
        conditions_tab = QWidget()
        conditions_layout = QVBoxLayout(conditions_tab)

        # Conditions list
        conditions_group = QGroupBox("Detected Conditions")
        conditions_group_layout = QVBoxLayout(conditions_group)

        self.conditions_list = QListWidget()
        self.conditions_list.setMinimumHeight(200)
        conditions_group_layout.addWidget(self.conditions_list)

        # Condition actions
        condition_actions_layout = QHBoxLayout()

        self.edit_condition_btn = QPushButton("Edit")
        self.edit_condition_btn.clicked.connect(self.edit_selected_condition)
        self.edit_condition_btn.setEnabled(False)
        condition_actions_layout.addWidget(self.edit_condition_btn)

        self.remove_condition_btn = QPushButton("Remove")
        self.remove_condition_btn.clicked.connect(self.remove_selected_condition)
        self.remove_condition_btn.setEnabled(False)
        condition_actions_layout.addWidget(self.remove_condition_btn)

        condition_actions_layout.addStretch()
        conditions_group_layout.addLayout(condition_actions_layout)

        conditions_layout.addWidget(conditions_group)

        # Condition preview
        preview_group = QGroupBox("Condition Logic Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.condition_preview = QTextEdit()
        self.condition_preview.setReadOnly(True)
        self.condition_preview.setMaximumHeight(120)
        self.condition_preview.setPlaceholderText("Select a condition to preview its logic...")
        preview_layout.addWidget(self.condition_preview)

        conditions_layout.addWidget(preview_group)

        self.tab_widget.addTab(conditions_tab, "Conditions")

        # Connect list selection signal
        self.conditions_list.itemSelectionChanged.connect(self.on_condition_selection_changed)

    def create_branches_tab(self):
        """Create the workflow branches tab"""
        branches_tab = QWidget()
        branches_layout = QVBoxLayout(branches_tab)

        # Branches list
        branches_group = QGroupBox("Workflow Branches")
        branches_group_layout = QVBoxLayout(branches_group)

        self.branches_list = QListWidget()
        self.branches_list.setMinimumHeight(200)
        branches_group_layout.addWidget(self.branches_list)

        # Branch actions
        branch_actions_layout = QHBoxLayout()

        self.edit_branch_btn = QPushButton("Edit Branch")
        self.edit_branch_btn.clicked.connect(self.edit_selected_branch)
        self.edit_branch_btn.setEnabled(False)
        branch_actions_layout.addWidget(self.edit_branch_btn)

        self.test_branch_btn = QPushButton("Test Logic")
        self.test_branch_btn.clicked.connect(self.test_selected_branch)
        self.test_branch_btn.setEnabled(False)
        branch_actions_layout.addWidget(self.test_branch_btn)

        branch_actions_layout.addStretch()
        branches_group_layout.addLayout(branch_actions_layout)

        branches_layout.addWidget(branches_group)

        # Branch details
        details_group = QGroupBox("Branch Details")
        details_layout = QVBoxLayout(details_group)

        self.branch_details = QTextEdit()
        self.branch_details.setReadOnly(True)
        self.branch_details.setMaximumHeight(120)
        self.branch_details.setPlaceholderText("Select a branch to view details...")
        details_layout.addWidget(self.branch_details)

        branches_layout.addWidget(details_group)

        self.tab_widget.addTab(branches_tab, "Branches")

        # Connect list selection signal
        self.branches_list.itemSelectionChanged.connect(self.on_branch_selection_changed)

    def create_patterns_tab(self):
        """Create the logic patterns tab"""
        patterns_tab = QWidget()
        patterns_layout = QVBoxLayout(patterns_tab)

        # Pattern detection info
        info_group = QGroupBox("Pattern Detection")
        info_layout = QVBoxLayout(info_group)

        self.pattern_info = QLabel("Conditional patterns will be detected during recording...")
        self.pattern_info.setWordWrap(True)
        self.pattern_info.setStyleSheet("padding: 10px; background-color: #f8f9fa; border: 1px solid #dee2e6;")
        info_layout.addWidget(self.pattern_info)

        patterns_layout.addWidget(info_group)

        # Common patterns
        common_patterns_group = QGroupBox("Common Conditional Patterns")
        patterns_group_layout = QVBoxLayout(common_patterns_group)

        patterns = [
            "• Error Dialog Handling: Detect and respond to error messages",
            "• File Existence Checks: Verify files before processing",
            "• Window State Validation: Check if windows are in expected states",
            "• Data Validation: Verify data values before proceeding",
            "• Process Completion: Wait for processes to finish",
            "• Resource Availability: Check if required resources are available"
        ]

        for pattern in patterns:
            pattern_label = QLabel(pattern)
            pattern_label.setStyleSheet("padding: 5px; margin: 2px; background-color: #e9ecef; border-radius: 3px;")
            patterns_group_layout.addWidget(pattern_label)

        patterns_layout.addWidget(common_patterns_group)

        # Detected patterns
        detected_group = QGroupBox("Detected Patterns in Current Recording")
        detected_layout = QVBoxLayout(detected_group)

        self.detected_patterns_list = QListWidget()
        self.detected_patterns_list.setMinimumHeight(150)
        detected_layout.addWidget(self.detected_patterns_list)

        patterns_layout.addWidget(detected_group)

        self.tab_widget.addTab(patterns_tab, "Patterns")

    def start_conditional_recording(self):
        """Start conditional recording mode"""
        self.is_recording = True
        self.detected_conditions = []
        self.workflow_branches = []
        self.recording_history = []
        self.current_branch = None

        self.start_recording_btn.setEnabled(False)
        self.stop_recording_btn.setEnabled(True)
        self.add_condition_btn.setEnabled(True)

        self.status_label.setText("Status: Recording conditional logic - Perform actions with decision points")
        self.status_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: #d1ecf1; border: 1px solid #bee5eb; color: #0c5460;")

        # Clear lists
        self.conditions_list.clear()
        self.branches_list.clear()
        self.detected_patterns_list.clear()

        # Start monitoring for conditional patterns
        self.start_pattern_monitoring()

        logger.info("Started conditional recording")

    def stop_conditional_recording(self):
        """Stop conditional recording mode"""
        self.is_recording = False

        self.start_recording_btn.setEnabled(True)
        self.stop_recording_btn.setEnabled(False)
        self.add_condition_btn.setEnabled(False)

        self.status_label.setText(f"Status: Recording stopped - {len(self.detected_conditions)} conditions detected")
        self.status_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: #f8f9fa; border: 1px solid #dee2e6;")

        # Stop pattern monitoring
        self.stop_pattern_monitoring()

        # Analyze recorded patterns
        self.analyze_conditional_patterns()

        logger.info("Stopped conditional recording")

    def start_pattern_monitoring(self):
        """Start monitoring for conditional patterns"""
        # This would integrate with the main automation recorder
        # to detect patterns in real-time
        pass

    def stop_pattern_monitoring(self):
        """Stop monitoring for conditional patterns"""
        # Stop real-time pattern detection
        pass

    def add_manual_condition(self):
        """Add a manual condition"""
        try:
            dialog = ConditionalActionDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                condition_data = dialog.get_condition_data()
                self.detected_conditions.append(condition_data)
                self.add_condition_to_list(condition_data)
                self.condition_detected.emit(condition_data)

        except Exception as e:
            logger.error(f"Error adding manual condition: {e}")
            QMessageBox.warning(self, "Condition Error", f"Failed to add condition: {e}")

    def detect_conditional_pattern(self, action_sequence: List[AutomationAction]) -> Optional[Dict[str, Any]]:
        """Detect conditional patterns in a sequence of actions"""
        patterns = []

        # Check for error handling patterns
        error_pattern = self.detect_error_handling_pattern(action_sequence)
        if error_pattern:
            patterns.append(error_pattern)

        # Check for file existence patterns
        file_pattern = self.detect_file_existence_pattern(action_sequence)
        if file_pattern:
            patterns.append(file_pattern)

        # Check for wait/load patterns
        wait_pattern = self.detect_wait_pattern(action_sequence)
        if wait_pattern:
            patterns.append(wait_pattern)

        # Check for retry patterns
        retry_pattern = self.detect_retry_pattern(action_sequence)
        if retry_pattern:
            patterns.append(retry_pattern)

        return patterns[0] if patterns else None

    def detect_error_handling_pattern(self, actions: List[AutomationAction]) -> Optional[Dict[str, Any]]:
        """Detect error handling patterns"""
        error_indicators = ['error', 'failed', 'warning', 'alert', 'exception']

        for i, action in enumerate(actions):
            if any(indicator in action.description.lower() for indicator in error_indicators):
                # Look for subsequent actions that handle the error
                remaining_actions = actions[i+1:i+4]  # Look at next 3 actions

                if len(remaining_actions) >= 2:
                    return {
                        'pattern_type': 'error_handling',
                        'trigger_action': action,
                        'handling_actions': remaining_actions,
                        'description': f"Error handling detected: {action.description}",
                        'condition_type': 'if_window_contains',
                        'condition_parameters': {
                            'text': action.description,
                            'window_title': '*Error*'
                        }
                    }

        return None

    def detect_file_existence_pattern(self, actions: List[AutomationAction]) -> Optional[Dict[str, Any]]:
        """Detect file existence check patterns"""
        file_indicators = ['file', 'open', 'load', 'import', 'browse', 'select file']

        for i, action in enumerate(actions):
            if any(indicator in action.description.lower() for indicator in file_indicators):
                # Check if this looks like a file validation step
                if action.action_type in ['click', 'wait'] and i > 0:
                    previous_action = actions[i-1]
                    if 'check' in previous_action.description.lower() or 'verify' in previous_action.description.lower():
                        return {
                            'pattern_type': 'file_existence',
                            'validation_action': previous_action,
                            'file_action': action,
                            'description': f"File existence check detected before {action.description}",
                            'condition_type': 'if_file_exists',
                            'condition_parameters': {
                                'file_path': 'detected during recording'
                            }
                        }

        return None

    def detect_wait_pattern(self, actions: List[AutomationAction]) -> Optional[Dict[str, Any]]:
        """Detect wait/load patterns"""
        wait_actions = [action for action in actions if action.action_type == 'wait']

        if wait_actions:
            # Look for patterns around wait actions
            for wait_action in wait_actions:
                wait_index = actions.index(wait_action)

                # Check if wait is followed by verification
                if wait_index < len(actions) - 1:
                    next_action = actions[wait_index + 1]
                    if any(keyword in next_action.description.lower() for keyword in ['check', 'verify', 'confirm', 'validate']):
                        return {
                            'pattern_type': 'wait_for_condition',
                            'wait_action': wait_action,
                            'verification_action': next_action,
                            'description': f"Wait and verify pattern detected: {next_action.description}",
                            'condition_type': 'if_exists',
                            'condition_parameters': {
                                'element': next_action.description
                            }
                        }

        return None

    def detect_retry_pattern(self, actions: List[AutomationAction]) -> Optional[Dict[str, Any]]:
        """Detect retry patterns"""
        # Look for repeated similar actions
        for i in range(len(actions) - 2):
            action1 = actions[i]
            action2 = actions[i + 1]
            action3 = actions[i + 2]

            # Check if actions 1 and 3 are similar with a wait/action in between
            if (action1.action_type == action3.action_type and
                action1.description == action3.description and
                action2.action_type in ['wait', 'click']):

                return {
                    'pattern_type': 'retry_logic',
                    'action_to_retry': action1,
                    'retry_interval': action2,
                    'description': f"Retry pattern detected for: {action1.description}",
                    'condition_type': 'if_not_exists',
                    'condition_parameters': {
                        'element': action1.description,
                        'max_retries': 3
                    }
                }

        return None

    def add_condition_to_list(self, condition_data: Dict[str, Any]):
        """Add detected condition to the list"""
        condition_text = f"🔀 {condition_data.get('pattern_type', 'Unknown').title()}: {condition_data.get('description', 'No description')}"
        item = QListWidgetItem(condition_text)
        item.setData(Qt.UserRole, condition_data)

        # Color code by pattern type
        pattern_type = condition_data.get('pattern_type', '')
        if pattern_type == 'error_handling':
            item.setStyleSheet("color: #dc3545; font-weight: bold;")
        elif pattern_type == 'file_existence':
            item.setStyleSheet("color: #28a745; font-weight: bold;")
        elif pattern_type == 'wait_for_condition':
            item.setStyleSheet("color: #ffc107; font-weight: bold;")
        elif pattern_type == 'retry_logic':
            item.setStyleSheet("color: #17a2b8; font-weight: bold;")
        else:
            item.setStyleSheet("color: #6c757d;")

        self.conditions_list.addItem(item)

    def analyze_conditional_patterns(self):
        """Analyze and summarize detected conditional patterns"""
        if not self.detected_conditions:
            self.pattern_info.setText("No conditional patterns detected in this recording.")
            return

        # Count pattern types
        pattern_counts = {}
        for condition in self.detected_conditions:
            pattern_type = condition.get('pattern_type', 'unknown')
            pattern_counts[pattern_type] = pattern_counts.get(pattern_type, 0) + 1

        # Generate summary
        summary_lines = ["Detected Conditional Patterns:"]
        for pattern_type, count in pattern_counts.items():
            summary_lines.append(f"• {pattern_type.title()}: {count} instance(s)")

        summary_lines.append(f"\nTotal: {len(self.detected_conditions)} conditional logic points detected")
        summary_lines.append("\nThese patterns will be converted to conditional workflow steps for intelligent automation.")

        self.pattern_info.setText("\n".join(summary_lines))

        # Add to detected patterns list
        self.detected_patterns_list.clear()
        for condition in self.detected_conditions:
            pattern_text = f"{condition.get('pattern_type', 'Unknown').title()}: {condition.get('description', 'No description')}"
            self.detected_patterns_list.addItem(pattern_text)

    def on_condition_selection_changed(self):
        """Handle condition selection change"""
        has_selection = bool(self.conditions_list.currentItem())
        self.edit_condition_btn.setEnabled(has_selection)
        self.remove_condition_btn.setEnabled(has_selection)

        # Update preview
        if has_selection:
            current_item = self.conditions_list.currentItem()
            condition_data = current_item.data(Qt.UserRole)
            if condition_data:
                preview_text = self.generate_condition_preview(condition_data)
                self.condition_preview.setText(preview_text)

    def on_branch_selection_changed(self):
        """Handle branch selection change"""
        has_selection = bool(self.branches_list.currentItem())
        self.edit_branch_btn.setEnabled(has_selection)
        self.test_branch_btn.setEnabled(has_selection)

        # Update details
        if has_selection:
            current_item = self.branches_list.currentItem()
            branch_data = current_item.data(Qt.UserRole)
            if branch_data:
                details_text = self.generate_branch_details(branch_data)
                self.branch_details.setText(details_text)

    def generate_condition_preview(self, condition_data: Dict[str, Any]) -> str:
        """Generate a preview of the conditional logic"""
        condition_type = condition_data.get('condition_type', 'if_exists')
        parameters = condition_data.get('condition_parameters', {})
        description = condition_data.get('description', '')

        preview = f"Condition Type: {condition_type}\n"
        preview += f"Description: {description}\n"
        preview += f"Parameters: {parameters}\n"

        if 'trigger_action' in condition_data:
            preview += f"\nTrigger: {condition_data['trigger_action'].description}"

        if 'handling_actions' in condition_data:
            preview += f"\nHandling Actions: {len(condition_data['handling_actions'])} steps"

        return preview

    def generate_branch_details(self, branch_data: Dict[str, Any]) -> str:
        """Generate detailed information about a workflow branch"""
        details = f"Branch ID: {branch_data.get('branch_id', 'Unknown')}\n"
        details += f"Description: {branch_data.get('description', 'No description')}\n"

        if 'condition' in branch_data:
            condition = branch_data['condition']
            details += f"\nCondition: {condition.condition_type}\n"
            details += f"True Actions: {len(condition.true_actions)} steps\n"
            details += f"False Actions: {len(condition.false_actions)} steps\n"

        if 'branch_points' in branch_data:
            branch_points = branch_data['branch_points']
            details += f"\nBranch Paths: {list(branch_points.keys())}\n"
            for branch_name, actions in branch_points.items():
                details += f"  • {branch_name}: {len(actions)} actions\n"

        return details

    def edit_selected_condition(self):
        """Edit the selected condition"""
        current_item = self.conditions_list.currentItem()
        if not current_item:
            return

        condition_data = current_item.data(Qt.UserRole)
        if not condition_data:
            return

        # Create edit dialog
        dialog = ConditionalActionDialog(self, condition_data)
        if dialog.exec_() == QDialog.Accepted:
            updated_data = dialog.get_condition_data()
            # Update the condition data
            index = self.detected_conditions.index(condition_data)
            self.detected_conditions[index] = updated_data
            current_item.setData(Qt.UserRole, updated_data)

            # Update list item text
            condition_text = f"🔀 {updated_data.get('pattern_type', 'Unknown').title()}: {updated_data.get('description', 'No description')}"
            current_item.setText(condition_text)

            # Update preview
            preview_text = self.generate_condition_preview(updated_data)
            self.condition_preview.setText(preview_text)

    def remove_selected_condition(self):
        """Remove the selected condition"""
        current_item = self.conditions_list.currentItem()
        if not current_item:
            return

        condition_data = current_item.data(Qt.UserRole)
        if condition_data in self.detected_conditions:
            self.detected_conditions.remove(condition_data)

        self.conditions_list.takeItem(self.conditions_list.row(current_item))
        self.condition_preview.clear()

    def edit_selected_branch(self):
        """Edit the selected branch"""
        current_item = self.branches_list.currentItem()
        if not current_item:
            return

        branch_data = current_item.data(Qt.UserRole)
        if not branch_data:
            return

        QMessageBox.information(self, "Edit Branch", f"Branch editing feature coming soon!\n\nBranch: {branch_data.get('branch_id', 'Unknown')}")

    def test_selected_branch(self):
        """Test the selected branch logic"""
        current_item = self.branches_list.currentItem()
        if not current_item:
            return

        branch_data = current_item.data(Qt.UserRole)
        if not branch_data:
            return

        QMessageBox.information(self, "Test Branch", f"Branch testing feature coming soon!\n\nBranch: {branch_data.get('branch_id', 'Unknown')}")

    def get_detected_conditions(self) -> List[Dict[str, Any]]:
        """Get the list of detected conditions"""
        return self.detected_conditions.copy()

    def get_workflow_branches(self) -> List[Dict[str, Any]]:
        """Get the list of workflow branches"""
        return self.workflow_branches.copy()


class ConditionalActionDialog(QDialog):
    """Dialog for creating/editing conditional actions"""

    def __init__(self, parent=None, condition_data: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.condition_data = condition_data or {}
        self.initUI()

    def initUI(self):
        """Initialize the conditional action dialog"""
        self.setWindowTitle("Conditional Action Editor")
        self.setModal(True)
        self.resize(500, 400)

        layout = QVBoxLayout(self)

        # Condition type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Condition Type:"))
        self.condition_type_combo = QComboBox()
        self.condition_type_combo.addItems([
            "if_exists", "if_not_exists", "if_text_contains",
            "if_window_contains", "if_file_exists", "if_element_visible"
        ])
        self.condition_type_combo.setCurrentText(self.condition_data.get('condition_type', 'if_exists'))
        type_layout.addWidget(self.condition_type_combo)
        layout.addLayout(type_layout)

        # Description
        desc_layout = QHBoxLayout()
        desc_layout.addWidget(QLabel("Description:"))
        self.description_edit = QLineEdit(self.condition_data.get('description', ''))
        desc_layout.addWidget(self.description_edit)
        layout.addLayout(desc_layout)

        # Parameters
        params_group = QGroupBox("Condition Parameters")
        params_layout = QFormLayout(params_group)

        self.param1_edit = QLineEdit()
        params_layout.addRow("Parameter 1:", self.param1_edit)

        self.param2_edit = QLineEdit()
        params_layout.addRow("Parameter 2:", self.param2_edit)

        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(0.0, 1.0)
        self.confidence_spin.setSingleStep(0.1)
        self.confidence_spin.setValue(self.condition_data.get('confidence_threshold', 0.8))
        params_layout.addRow("Confidence:", self.confidence_spin)

        layout.addWidget(params_group)

        # True actions
        true_group = QGroupBox("Actions if Condition is True")
        true_layout = QVBoxLayout(true_group)

        self.true_actions_text = QTextEdit()
        self.true_actions_text.setPlaceholderText("Describe actions to take if condition is true...")
        self.true_actions_text.setMaximumHeight(80)
        true_layout.addWidget(self.true_actions_text)

        layout.addWidget(true_group)

        # False actions
        false_group = QGroupBox("Actions if Condition is False")
        false_layout = QVBoxLayout(false_group)

        self.false_actions_text = QTextEdit()
        self.false_actions_text.setPlaceholderText("Describe actions to take if condition is false (optional)...")
        self.false_actions_text.setMaximumHeight(80)
        false_layout.addWidget(self.false_actions_text)

        layout.addWidget(false_group)

        # Buttons
        button_layout = QHBoxLayout()

        save_btn = QPushButton("Save Condition")
        save_btn.clicked.connect(self.accept)
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def get_condition_data(self) -> Dict[str, Any]:
        """Get the condition data from the dialog"""
        return {
            'condition_type': self.condition_type_combo.currentText(),
            'description': self.description_edit.text(),
            'condition_parameters': {
                'param1': self.param1_edit.text(),
                'param2': self.param2_edit.text()
            },
            'confidence_threshold': self.confidence_spin.value(),
            'true_actions_text': self.true_actions_text.toPlainText(),
            'false_actions_text': self.false_actions_text.toPlainText(),
            'pattern_type': self.condition_data.get('pattern_type', 'manual_condition')
        }


class WorkflowConversionWizard(QDialog):
    """Wizard for converting recorded sessions to structured workflows"""

    def __init__(self, parent=None, recording_sessions=None):
        super().__init__(parent)
        self.recording_sessions = recording_sessions or []
        self.selected_session = None
        self.analysis_result = None
        self.recording_analyzer = RecordingAnalysis()
        self.current_page = 0
        self.total_pages = 4

        self.initUI()
        self.load_sessions()

    def initUI(self):
        """Initialize the wizard UI"""
        self.setWindowTitle("Recording to Workflow Converter")
        self.setModal(True)
        self.resize(900, 700)

        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel("Convert Recording to Workflow")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header_label)

        # Progress indicator
        self.progress_label = QLabel("Step 1 of 4: Select Recording Session")
        self.progress_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        layout.addWidget(self.progress_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(self.total_pages)
        self.progress_bar.setValue(1)
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #3498db; }")
        layout.addWidget(self.progress_bar)

        # Stacked widget for pages
        self.stacked_widget = QStackedWidget()
        layout.addWidget(self.stacked_widget)

        # Create wizard pages
        self.create_session_selection_page()
        self.create_analysis_page()
        self.create_workflow_customization_page()
        self.create_completion_page()

        # Navigation buttons
        nav_layout = QHBoxLayout()

        self.back_btn = QPushButton("Back")
        self.back_btn.clicked.connect(self.go_back)
        self.back_btn.setEnabled(False)
        nav_layout.addWidget(self.back_btn)

        nav_layout.addStretch()

        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.go_next)
        self.next_btn.setDefault(True)
        nav_layout.addWidget(self.next_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        nav_layout.addWidget(self.cancel_btn)

        layout.addLayout(nav_layout)

    def create_session_selection_page(self):
        """Create the session selection page"""
        page = QWidget()
        layout = QVBoxLayout(page)

        # Instructions
        instructions = QLabel("Select a recording session to convert to a workflow:")
        instructions.setStyleSheet("font-size: 12px; margin-bottom: 10px;")
        layout.addWidget(instructions)

        # Sessions table
        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(5)
        self.sessions_table.setHorizontalHeaderLabels([
            "Session ID", "Date", "Duration", "Screenshots", "Description"
        ])

        # Set column widths
        self.sessions_table.setColumnWidth(0, 150)  # Session ID
        self.sessions_table.setColumnWidth(1, 120)  # Date
        self.sessions_table.setColumnWidth(2, 80)   # Duration
        self.sessions_table.setColumnWidth(3, 80)   # Screenshots
        self.sessions_table.setColumnWidth(4, 250)  # Description

        self.sessions_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.sessions_table.itemSelectionChanged.connect(self.on_session_selection_changed)

        layout.addWidget(self.sessions_table)

        # Session details
        details_group = QGroupBox("Session Details")
        details_layout = QVBoxLayout(details_group)

        self.session_details_label = QLabel("Select a session to view details")
        self.session_details_label.setWordWrap(True)
        self.session_details_label.setStyleSheet("padding: 10px; background-color: #f8f9fa; border: 1px solid #dee2e6;")
        details_layout.addWidget(self.session_details_label)

        layout.addWidget(details_group)

        self.stacked_widget.addWidget(page)

    def create_analysis_page(self):
        """Create the analysis page"""
        page = QWidget()
        layout = QVBoxLayout(page)

        # Analysis status
        self.analysis_status_label = QLabel("Analyzing recording session...")
        self.analysis_status_label.setAlignment(Qt.AlignCenter)
        self.analysis_status_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 20px;")
        layout.addWidget(self.analysis_status_label)

        # Analysis results
        results_group = QGroupBox("Analysis Results")
        results_layout = QVBoxLayout(results_group)

        # Detected software
        software_layout = QHBoxLayout()
        software_layout.addWidget(QLabel("Detected Software:"))
        self.detected_software_label = QLabel("-")
        self.detected_software_label.setStyleSheet("font-weight: bold; color: #27ae60;")
        software_layout.addWidget(self.detected_software_label)
        software_layout.addStretch()
        results_layout.addLayout(software_layout)

        # Confidence score
        confidence_layout = QHBoxLayout()
        confidence_layout.addWidget(QLabel("Confidence Score:"))
        self.confidence_score_label = QLabel("-")
        confidence_layout.addWidget(self.confidence_score_label)
        confidence_layout.addStretch()
        results_layout.addLayout(confidence_layout)

        # Identified patterns
        patterns_label = QLabel("Identified Patterns:")
        patterns_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        results_layout.addWidget(patterns_label)

        self.patterns_list = QListWidget()
        self.patterns_list.setMaximumHeight(120)
        results_layout.addWidget(self.patterns_list)

        # Recommendations
        recommendations_label = QLabel("Recommendations:")
        recommendations_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        results_layout.addWidget(recommendations_label)

        self.recommendations_list = QListWidget()
        self.recommendations_list.setMaximumHeight(100)
        results_layout.addWidget(self.recommendations_list)

        # Intelligent suggestions
        suggestions_label = QLabel("Intelligent Suggestions:")
        suggestions_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        results_layout.addWidget(suggestions_label)

        self.suggestions_list = QListWidget()
        self.suggestions_list.setMaximumHeight(120)
        self.suggestions_list.itemDoubleClicked.connect(self.show_suggestion_details)
        results_layout.addWidget(self.suggestions_list)

        layout.addWidget(results_group)

        # Workflow steps preview
        steps_group = QGroupBox("Generated Workflow Steps (Preview)")
        steps_layout = QVBoxLayout(steps_group)

        self.steps_preview_table = QTableWidget()
        self.steps_preview_table.setColumnCount(3)
        self.steps_preview_table.setHorizontalHeaderLabels(["Step", "Action", "Description"])

        # Set column widths
        self.steps_preview_table.setColumnWidth(0, 50)   # Step
        self.steps_preview_table.setColumnWidth(1, 100)  # Action
        self.steps_preview_table.setColumnWidth(2, 300)  # Description

        steps_layout.addWidget(self.steps_preview_table)

        layout.addWidget(steps_group)

        self.stacked_widget.addWidget(page)

    def create_workflow_customization_page(self):
        """Create the workflow customization page"""
        page = QWidget()
        layout = QVBoxLayout(page)

        # Workflow name and description
        info_group = QGroupBox("Workflow Information")
        info_layout = QFormLayout(info_group)

        self.workflow_name_edit = QLineEdit()
        self.workflow_name_edit.setPlaceholderText("Enter workflow name...")
        info_layout.addRow("Workflow Name:", self.workflow_name_edit)

        self.workflow_description_edit = QTextEdit()
        self.workflow_description_edit.setMaximumHeight(80)
        self.workflow_description_edit.setPlaceholderText("Enter workflow description...")
        info_layout.addRow("Description:", self.workflow_description_edit)

        layout.addWidget(info_group)

        # Step customization
        steps_group = QGroupBox("Customize Workflow Steps")
        steps_layout = QVBoxLayout(steps_group)

        # Steps table
        self.workflow_steps_table = QTableWidget()
        self.workflow_steps_table.setColumnCount(5)
        self.workflow_steps_table.setHorizontalHeaderLabels([
            "Step", "Action Type", "Description", "Delay (s)", "Enabled"
        ])

        # Set column widths
        self.workflow_steps_table.setColumnWidth(0, 50)   # Step
        self.workflow_steps_table.setColumnWidth(1, 120)  # Action Type
        self.workflow_steps_table.setColumnWidth(2, 250)  # Description
        self.workflow_steps_table.setColumnWidth(3, 80)   # Delay
        self.workflow_steps_table.setColumnWidth(4, 80)   # Enabled

        steps_layout.addWidget(self.workflow_steps_table)

        # Step actions
        step_actions_layout = QHBoxLayout()

        edit_step_btn = QPushButton("Edit Step")
        edit_step_btn.clicked.connect(self.edit_selected_step)
        step_actions_layout.addWidget(edit_step_btn)

        remove_step_btn = QPushButton("Remove Step")
        remove_step_btn.clicked.connect(self.remove_selected_step)
        step_actions_layout.addWidget(remove_step_btn)

        add_step_btn = QPushButton("Add Step")
        add_step_btn.clicked.connect(self.add_new_step)
        step_actions_layout.addWidget(add_step_btn)

        step_actions_layout.addStretch()
        steps_layout.addLayout(step_actions_layout)

        layout.addWidget(steps_group)

        # Workflow options
        options_group = QGroupBox("Workflow Options")
        options_layout = QFormLayout(options_group)

        self.add_screenshots_check = QCheckBox("Include screenshots in workflow")
        self.add_screenshots_check.setChecked(True)
        options_layout.addRow("", self.add_screenshots_check)

        self.use_image_recognition_check = QCheckBox("Use image recognition where possible")
        self.use_image_recognition_check.setChecked(True)
        options_layout.addRow("", self.use_image_recognition_check)

        self.add_error_handling_check = QCheckBox("Add error handling")
        self.add_error_handling_check.setChecked(True)
        options_layout.addRow("", self.add_error_handling_check)

        layout.addWidget(options_group)

        self.stacked_widget.addWidget(page)

    def create_completion_page(self):
        """Create the completion page"""
        page = QWidget()
        layout = QVBoxLayout(page)

        # Success message
        success_label = QLabel("✓ Workflow Successfully Created!")
        success_label.setAlignment(Qt.AlignCenter)
        success_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #27ae60; margin: 20px;")
        layout.addWidget(success_label)

        # Summary
        summary_group = QGroupBox("Workflow Summary")
        summary_layout = QFormLayout(summary_group)

        self.created_workflow_name_label = QLabel("-")
        summary_layout.addRow("Workflow Name:", self.created_workflow_name_label)

        self.created_steps_count_label = QLabel("-")
        summary_layout.addRow("Total Steps:", self.created_steps_count_label)

        self.created_confidence_label = QLabel("-")
        summary_layout.addRow("Quality Score:", self.created_confidence_label)

        layout.addWidget(summary_group)

        # Next steps
        next_steps_group = QGroupBox("Next Steps")
        next_steps_layout = QVBoxLayout(next_steps_group)

        next_steps_text = QLabel(
            "• You can find the new workflow in the 'Workflows' tab\n"
            "• Test the workflow to ensure it works correctly\n"
            "• You can edit the workflow later if needed\n"
            "• Consider creating variations for different scenarios"
        )
        next_steps_text.setWordWrap(True)
        next_steps_text.setStyleSheet("padding: 10px; background-color: #e8f5e8; border: 1px solid #27ae60;")
        next_steps_layout.addWidget(next_steps_text)

        layout.addWidget(next_steps_group)

        self.stacked_widget.addWidget(page)

    def load_sessions(self):
        """Load recording sessions into the table"""
        if not self.recording_sessions:
            return

        self.sessions_table.setRowCount(len(self.recording_sessions))

        for row, session in enumerate(self.recording_sessions):
            # Session ID
            self.sessions_table.setItem(row, 0, QTableWidgetItem(session.session_id))

            # Date
            try:
                date = datetime.fromisoformat(session.start_time.replace('Z', '+00:00'))
                date_str = date.strftime('%Y-%m-%d %H:%M')
                self.sessions_table.setItem(row, 1, QTableWidgetItem(date_str))
            except:
                self.sessions_table.setItem(row, 1, QTableWidgetItem("Unknown"))

            # Duration
            try:
                start_time = datetime.fromisoformat(session.start_time.replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(session.end_time.replace('Z', '+00:00'))
                duration = (end_time - start_time).total_seconds() / 60.0
                duration_str = f"{duration:.1f} min"
                self.sessions_table.setItem(row, 2, QTableWidgetItem(duration_str))
            except:
                self.sessions_table.setItem(row, 2, QTableWidgetItem("-"))

            # Screenshots count
            screenshots_count = str(len(session.screenshots))
            self.sessions_table.setItem(row, 3, QTableWidgetItem(screenshots_count))

            # Description
            description = session.description or "No description"
            self.sessions_table.setItem(row, 4, QTableWidgetItem(description))

    def on_session_selection_changed(self):
        """Handle session selection change"""
        current_row = self.sessions_table.currentRow()
        if current_row >= 0 and current_row < len(self.recording_sessions):
            self.selected_session = self.recording_sessions[current_row]
            self.update_session_details()
            self.next_btn.setEnabled(True)
        else:
            self.selected_session = None
            self.session_details_label.setText("Select a session to view details")
            self.next_btn.setEnabled(False)

    def update_session_details(self):
        """Update the session details display"""
        if not self.selected_session:
            return

        try:
            start_time = datetime.fromisoformat(self.selected_session.start_time.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(self.selected_session.end_time.replace('Z', '+00:00'))
            duration = (end_time - start_time).total_seconds() / 60.0

            details = f"<b>Session ID:</b> {self.selected_session.session_id}<br>"
            details += f"<b>Start Time:</b> {start_time.strftime('%Y-%m-%d %H:%M:%S')}<br>"
            details += f"<b>Duration:</b> {duration:.1f} minutes<br>"
            details += f"<b>Screenshots:</b> {len(self.selected_session.screenshots)}<br>"
            details += f"<b>Description:</b> {self.selected_session.description or 'No description'}"

            self.session_details_label.setText(details)
        except Exception as e:
            self.session_details_label.setText(f"Error loading session details: {e}")

    def go_back(self):
        """Go to the previous wizard page"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_page()

    def go_next(self):
        """Go to the next wizard page"""
        if self.current_page < self.total_pages - 1:
            # Validate current page before proceeding
            if not self.validate_current_page():
                return

            self.current_page += 1

            # Perform page-specific actions
            if self.current_page == 1:  # Moving to analysis page
                self.analyze_session()
            elif self.current_page == 2:  # Moving to customization page
                self.setup_workflow_customization()
            elif self.current_page == 3:  # Moving to completion page
                self.create_workflow()

            self.update_page()

    def validate_current_page(self) -> bool:
        """Validate the current wizard page"""
        if self.current_page == 0:  # Session selection page
            if not self.selected_session:
                QMessageBox.warning(self, "No Session Selected", "Please select a recording session to continue.")
                return False
        elif self.current_page == 2:  # Workflow customization page
            workflow_name = self.workflow_name_edit.text().strip()
            if not workflow_name:
                QMessageBox.warning(self, "Invalid Workflow Name", "Please enter a workflow name.")
                self.workflow_name_edit.setFocus()
                return False

        return True

    def update_page(self):
        """Update the wizard page display"""
        # Update progress
        self.progress_label.setText(f"Step {self.current_page + 1} of {self.total_pages}: {self.get_page_title()}")
        self.progress_bar.setValue(self.current_page + 1)

        # Update stacked widget
        self.stacked_widget.setCurrentIndex(self.current_page)

        # Update navigation buttons
        self.back_btn.setEnabled(self.current_page > 0)

        if self.current_page == self.total_pages - 1:
            self.next_btn.setText("Finish")
            self.next_btn.clicked.disconnect()
            self.next_btn.clicked.connect(self.finish_wizard)
        else:
            self.next_btn.setText("Next")
            self.next_btn.clicked.disconnect()
            self.next_btn.clicked.connect(self.go_next)

    def get_page_title(self) -> str:
        """Get the current page title"""
        titles = [
            "Select Recording Session",
            "Analyze Recording",
            "Customize Workflow",
            "Complete"
        ]
        return titles[self.current_page] if self.current_page < len(titles) else ""

    def analyze_session(self):
        """Analyze the selected session"""
        if not self.selected_session:
            return

        self.analysis_status_label.setText("Analyzing recording session...")
        QApplication.processEvents()

        try:
            # Perform analysis
            self.analysis_result = self.recording_analyzer.analyze_session(self.selected_session)

            # Update UI with results
            self.update_analysis_display()

        except Exception as e:
            QMessageBox.critical(self, "Analysis Error", f"Failed to analyze session: {e}")
            self.current_page = 0
            self.update_page()

    def update_analysis_display(self):
        """Update the analysis display with results"""
        if not self.analysis_result:
            return

        # Update detected software
        software_list = self.analysis_result.get('detected_software', [])
        if software_list:
            self.detected_software_label.setText(", ".join(software_list))
        else:
            self.detected_software_label.setText("None detected")

        # Update confidence score
        confidence = self.analysis_result.get('confidence_score', 0.0)
        self.confidence_score_label.setText(f"{confidence:.1%}")

        # Color code confidence
        if confidence >= 0.8:
            self.confidence_score_label.setStyleSheet("font-weight: bold; color: #27ae60;")
        elif confidence >= 0.6:
            self.confidence_score_label.setStyleSheet("font-weight: bold; color: #f39c12;")
        else:
            self.confidence_score_label.setStyleSheet("font-weight: bold; color: #e74c3c;")

        # Update patterns
        self.patterns_list.clear()
        for pattern in self.analysis_result.get('identified_patterns', []):
            self.patterns_list.addItem(pattern.get('description', 'Unknown pattern'))

        # Update recommendations
        self.recommendations_list.clear()
        for recommendation in self.analysis_result.get('recommendations', []):
            self.recommendations_list.addItem(recommendation)

        # Update intelligent suggestions
        self.update_intelligent_suggestions()

        # Update workflow steps preview
        self.update_steps_preview()

        self.analysis_status_label.setText("Analysis complete! Review the results below.")

    def update_steps_preview(self):
        """Update the workflow steps preview"""
        if not self.analysis_result:
            return

        workflow_steps = self.analysis_result.get('workflow_steps', [])
        self.steps_preview_table.setRowCount(len(workflow_steps))

        for row, step in enumerate(workflow_steps):
            # Step number
            self.steps_preview_table.setItem(row, 0, QTableWidgetItem(str(step.get('step_number', row + 1))))

            # Action type
            action_type = step.get('action_type', 'unknown')
            self.steps_preview_table.setItem(row, 1, QTableWidgetItem(action_type.title()))

            # Description
            description = step.get('description', 'No description')
            self.steps_preview_table.setItem(row, 2, QTableWidgetItem(description))

    def update_intelligent_suggestions(self):
        """Update the intelligent suggestions display"""
        if not self.selected_session:
            return

        try:
            # Get intelligent suggestions from the analyzer
            # For now, create some basic suggestions based on analysis
            suggestions = self._generate_basic_suggestions()

            self.suggestions_list.clear()
            for suggestion in suggestions:
                # Create list widget item with priority styling
                item = QListWidgetItem(f"• {suggestion['title']}")

                # Store full suggestion data as user data
                item.setData(Qt.UserRole, suggestion)

                # Color code by priority
                if suggestion['priority'] == 'high':
                    item.setStyleSheet("color: #e74c3c; font-weight: bold;")
                elif suggestion['priority'] == 'medium':
                    item.setStyleSheet("color: #f39c12; font-weight: normal;")
                else:
                    item.setStyleSheet("color: #95a5a6; font-weight: normal;")

                # Set tooltip
                item.setToolTip(suggestion['description'])

                self.suggestions_list.addItem(item)

        except Exception as e:
            logger.error(f"Error updating intelligent suggestions: {e}")

    def _generate_basic_suggestions(self) -> List[Dict[str, Any]]:
        """Generate basic suggestions based on analysis results"""
        suggestions = []

        if not self.analysis_result:
            return suggestions

        detected_software = self.analysis_result.get('detected_software', [])
        confidence_score = self.analysis_result.get('confidence_score', 0)
        total_actions = self.analysis_result.get('total_actions', 0)

        # Software-specific suggestions
        for software in detected_software:
            if software == 'Petrel':
                suggestions.append({
                    'type': 'best_practice',
                    'title': 'Petrel Process Templates',
                    'description': 'Save this workflow as a Petrel process template for reuse across projects.',
                    'priority': 'high'
                })
            elif software == 'Harmony Enterprise':
                suggestions.append({
                    'type': 'efficiency',
                    'title': 'Batch Case Processing',
                    'description': 'This workflow can be applied to multiple Harmony cases for batch processing.',
                    'priority': 'medium'
                })

        # Quality-based suggestions
        if confidence_score > 0.8:
            suggestions.append({
                'type': 'quality',
                'title': 'High Quality Recording',
                'description': 'This is a high-quality recording with clear patterns. Perfect for automation!',
                'priority': 'high'
            })
        elif confidence_score < 0.5:
            suggestions.append({
                'type': 'improvement',
                'title': 'Consider Re-recording',
                'description': 'Low confidence detected. Try recording with more deliberate actions and visible UI elements.',
                'priority': 'high'
            })

        # Action-based suggestions
        if total_actions > 20:
            suggestions.append({
                'type': 'optimization',
                'title': 'Complex Workflow Detected',
                'description': 'This workflow has many steps. Consider breaking it into smaller, manageable workflows.',
                'priority': 'medium'
            })

        return suggestions

    def show_suggestion_details(self, item):
        """Show detailed information about a suggestion"""
        suggestion = item.data(Qt.UserRole)
        if not suggestion:
            return

        # Create details dialog
        details_dialog = QDialog(self)
        details_dialog.setWindowTitle(f"Suggestion Details: {suggestion['title']}")
        details_dialog.setModal(True)
        details_dialog.resize(500, 300)

        layout = QVBoxLayout(details_dialog)

        # Title and type
        title_label = QLabel(suggestion['title'])
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title_label)

        type_label = QLabel(f"Type: {suggestion['type'].replace('_', ' ').title()}")
        type_label.setStyleSheet("color: #7f8c8d; font-style: italic; margin-bottom: 10px;")
        layout.addWidget(type_label)

        # Description
        desc_text = QTextEdit()
        desc_text.setPlainText(suggestion['description'])
        desc_text.setReadOnly(True)
        desc_text.setMaximumHeight(100)
        layout.addWidget(desc_text)

        # Priority
        priority_layout = QHBoxLayout()
        priority_layout.addWidget(QLabel("Priority:"))

        priority_color = {
            'high': '#e74c3c',
            'medium': '#f39c12',
            'low': '#95a5a6'
        }

        priority_value = QLabel(suggestion['priority'].title())
        priority_value.setStyleSheet(f"color: {priority_color.get(suggestion['priority'], '#000')}; font-weight: bold;")
        priority_layout.addWidget(priority_value)
        priority_layout.addStretch()
        layout.addLayout(priority_layout)

        # Action buttons
        button_layout = QHBoxLayout()

        apply_btn = QPushButton("Apply Suggestion")
        apply_btn.clicked.connect(lambda: self.apply_suggestion(suggestion, details_dialog))
        button_layout.addWidget(apply_btn)

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.clicked.connect(details_dialog.reject)
        button_layout.addWidget(dismiss_btn)

        layout.addLayout(button_layout)

        details_dialog.exec_()

    def apply_suggestion(self, suggestion: Dict[str, Any], dialog: QDialog):
        """Apply a suggestion to the workflow"""
        try:
            if suggestion['type'] == 'best_practice':
                # For best practices, just show informational message
                QMessageBox.information(
                    self,
                    "Best Practice Applied",
                    f"This suggestion will be considered during workflow creation:\n\n{suggestion['description']}"
                )
            elif suggestion['type'] == 'optimization':
                # For optimization suggestions, modify workflow settings
                if hasattr(self, 'add_error_handling_check'):
                    self.add_error_handling_check.setChecked(True)
                QMessageBox.information(self, "Optimization Applied", "Error handling has been enabled for this workflow.")
            elif suggestion['type'] == 'improvement':
                # For improvement suggestions, provide guidance
                QMessageBox.information(
                    self,
                    "Improvement Suggestion",
                    f"Consider this improvement:\n\n{suggestion['description']}"
                )

            dialog.accept()

        except Exception as e:
            QMessageBox.warning(self, "Application Error", f"Failed to apply suggestion: {e}")

    def setup_workflow_customization(self):
        """Setup the workflow customization page"""
        if not self.analysis_result:
            return

        # Set default workflow name
        session_name = self.selected_session.description or f"Workflow from {self.selected_session.session_id}"
        self.workflow_name_edit.setText(session_name)

        # Set default description
        duration = self.analysis_result.get('duration', 0)
        software = ", ".join(self.analysis_result.get('detected_software', ['Unknown software']))
        default_description = f"Automated workflow created from recording session. Duration: {duration:.1f} minutes. Software: {software}."
        self.workflow_description_edit.setText(default_description)

        # Populate workflow steps table
        workflow_steps = self.analysis_result.get('workflow_steps', [])
        self.workflow_steps_table.setRowCount(len(workflow_steps))

        for row, step in enumerate(workflow_steps):
            # Step number
            self.workflow_steps_table.setItem(row, 0, QTableWidgetItem(str(step.get('step_number', row + 1))))

            # Action type
            action_type = step.get('action_type', 'unknown')
            action_combo = QComboBox()
            action_combo.addItems(['click', 'click_button', 'input_text', 'menu_navigation', 'navigate', 'wait'])
            action_combo.setCurrentText(action_type)
            self.workflow_steps_table.setCellWidget(row, 1, action_combo)

            # Description
            description = step.get('description', 'No description')
            desc_item = QTableWidgetItem(description)
            desc_item.setFlags(desc_item.flags() | Qt.ItemIsEditable)
            self.workflow_steps_table.setItem(row, 2, desc_item)

            # Delay
            delay = step.get('estimated_time', 2.0)
            delay_item = QTableWidgetItem(str(delay))
            delay_item.setFlags(delay_item.flags() | Qt.ItemIsEditable)
            self.workflow_steps_table.setItem(row, 3, delay_item)

            # Enabled checkbox
            enabled_check = QCheckBox()
            enabled_check.setChecked(True)
            self.workflow_steps_table.setCellWidget(row, 4, enabled_check)

    def edit_selected_step(self):
        """Edit the selected workflow step"""
        current_row = self.workflow_steps_table.currentRow()
        if current_row >= 0:
            QMessageBox.information(self, "Edit Step", "Step editing feature coming soon!")

    def remove_selected_step(self):
        """Remove the selected workflow step"""
        current_row = self.workflow_steps_table.currentRow()
        if current_row >= 0:
            self.workflow_steps_table.removeRow(current_row)

    def add_new_step(self):
        """Add a new workflow step"""
        row_count = self.workflow_steps_table.rowCount()
        self.workflow_steps_table.insertRow(row_count)

        # Set default values for new step
        step_number = row_count + 1
        self.workflow_steps_table.setItem(row_count, 0, QTableWidgetItem(str(step_number)))

        action_combo = QComboBox()
        action_combo.addItems(['click', 'click_button', 'input_text', 'menu_navigation', 'navigate', 'wait'])
        self.workflow_steps_table.setCellWidget(row_count, 1, action_combo)

        desc_item = QTableWidgetItem("New step")
        desc_item.setFlags(desc_item.flags() | Qt.ItemIsEditable)
        self.workflow_steps_table.setItem(row_count, 2, desc_item)

        delay_item = QTableWidgetItem("2.0")
        delay_item.setFlags(delay_item.flags() | Qt.ItemIsEditable)
        self.workflow_steps_table.setItem(row_count, 3, delay_item)

        enabled_check = QCheckBox()
        enabled_check.setChecked(True)
        self.workflow_steps_table.setCellWidget(row_count, 4, enabled_check)

    def create_workflow(self):
        """Create the workflow from the analysis and customizations"""
        try:
            # Get workflow information
            workflow_name = self.workflow_name_edit.text().strip()
            workflow_description = self.workflow_description_edit.toPlainText().strip()

            # Get workflow steps
            steps = []
            for row in range(self.workflow_steps_table.rowCount()):
                # Check if step is enabled
                enabled_widget = self.workflow_steps_table.cellWidget(row, 4)
                if isinstance(enabled_widget, QCheckBox) and not enabled_widget.isChecked():
                    continue

                # Get step details
                action_type_widget = self.workflow_steps_table.cellWidget(row, 1)
                action_type = action_type_widget.currentText() if isinstance(action_type_widget, QComboBox) else 'click'

                description_item = self.workflow_steps_table.item(row, 2)
                description = description_item.text() if description_item else 'No description'

                delay_item = self.workflow_steps_table.item(row, 3)
                try:
                    delay = float(delay_item.text()) if delay_item else 2.0
                except:
                    delay = 2.0

                # Create workflow step
                step = WorkflowStep(
                    step_number=row + 1,
                    action_type=action_type,
                    description=description,
                    target_element=f"Step {row + 1}",
                    wait_time=delay,
                    optional=False
                )
                steps.append(step)

            # Create workflow
            workflow = Workflow(
                name=workflow_name,
                description=workflow_description,
                software=",".join(self.analysis_result.get('detected_software', ['Unknown'])),
                category="Recorded",
                difficulty="Beginner",
                estimated_time=sum(step.wait_time for step in steps),
                author="Recording Converter",
                version="1.0.0",
                created_date=datetime.now().isoformat(),
                modified_date=datetime.now().isoformat(),
                tags=["recorded", "automated"],
                steps=steps,
                dependencies=[],
                variables={},
                error_handling=self.add_error_handling_check.isChecked(),
                retry_count=3,
                timeout=30
            )

            # Save workflow
            workflows_dir = Path("workflows")
            workflows_dir.mkdir(exist_ok=True)

            workflow_file = workflows_dir / f"{workflow_name.replace(' ', '_').lower()}.json"
            with open(workflow_file, 'w') as f:
                json.dump(asdict(workflow), f, indent=2)

            # Update completion page
            self.created_workflow_name_label.setText(workflow_name)
            self.created_steps_count_label.setText(str(len(steps)))
            self.created_confidence_label.setText(f"{self.analysis_result.get('confidence_score', 0):.1%}")

        except Exception as e:
            QMessageBox.critical(self, "Workflow Creation Error", f"Failed to create workflow: {e}")
            self.current_page = 2
            self.update_page()

    def finish_wizard(self):
        """Finish the wizard"""
        QMessageBox.information(self, "Success", "Workflow has been created successfully!")
        self.accept()


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
            "launch_program", "open_file", "wait", "run_command", "click_button", "screenshot"
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

        # Button text for click_button
        self.button_text_edit = QLineEdit()
        details_layout.addRow("Button Text:", self.button_text_edit)

        # Screenshot description
        self.screenshot_desc_edit = QLineEdit()
        details_layout.addRow("Screenshot Description:", self.screenshot_desc_edit)

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
                target = step.command[:30] + "..." if len(step.command) > 30 else step.command
            elif step.step_type == "click_button":
                target = step.button_text or ""
            elif step.step_type == "screenshot":
                target = step.screenshot_description[:30] + "..." if step.screenshot_description and len(step.screenshot_description) > 30 else step.screenshot_description or "Screenshot"
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
        elif step.step_type == "click_button":
            self.button_text_edit.setText(step.button_text or "")
        elif step.step_type == "screenshot":
            self.screenshot_desc_edit.setText(step.screenshot_description or "")

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
        self.button_text_edit.setVisible(step_type in ["click_button"])
        self.screenshot_desc_edit.setVisible(step_type == "screenshot")

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
            elif step.step_type == "click_button":
                step.button_text = self.button_text_edit.text()
            elif step.step_type == "screenshot":
                step.screenshot_description = self.screenshot_desc_edit.text()

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


class RecordingReviewDialog(QDialog):
    """Dialog for reviewing recording sessions"""

    def __init__(self, parent=None, session: RecordingSession = None):
        super().__init__(parent)
        self.session = session
        self.current_screenshot_index = 0
        self.initUI()

    def initUI(self):
        """Initialize the review dialog UI"""
        self.setWindowTitle(f"Review Session: {self.session.session_id}")
        self.setModal(True)
        self.setMinimumSize(800, 600)

        # Calculate initial size based on parent
        if self.parent():
            parent_size = self.parent().size()
            dialog_width = min(parent_size.width() - 100, 1000)
            dialog_height = min(parent_size.height() - 100, 800)
            self.resize(dialog_width, dialog_height)
        else:
            self.resize(900, 700)

        layout = QVBoxLayout(self)

        # Session info
        info_group = QGroupBox("Session Information")
        info_layout = QFormLayout(info_group)

        info_layout.addRow("Session ID:", QLabel(self.session.session_id))
        info_layout.addRow("Description:", QLabel(self.session.description))
        info_layout.addRow("Start Time:", QLabel(self.session.start_time[:19].replace('T', ' ')))
        info_layout.addRow("End Time:", QLabel(self.session.end_time[:19].replace('T', ' ')))
        info_layout.addRow("Screenshots:", QLabel(str(len(self.session.screenshots))))
        info_layout.addRow("Video:", QLabel("Yes" if self.session.video_path else "No"))

        layout.addWidget(info_group)

        # Screenshot viewer
        if self.session.screenshots:
            viewer_group = QGroupBox("Screenshot Viewer")
            viewer_layout = QVBoxLayout(viewer_group)

            # Navigation controls
            nav_layout = QHBoxLayout()

            self.prev_btn = QPushButton("Previous")
            self.prev_btn.clicked.connect(self.show_previous_screenshot)
            nav_layout.addWidget(self.prev_btn)

            self.screenshot_label = QLabel(f"Screenshot 1 / {len(self.session.screenshots)}")
            self.screenshot_label.setAlignment(Qt.AlignCenter)
            nav_layout.addWidget(self.screenshot_label)

            self.next_btn = QPushButton("Next")
            self.next_btn.clicked.connect(self.show_next_screenshot)
            nav_layout.addWidget(self.next_btn)

            viewer_layout.addLayout(nav_layout)

            # Screenshot display
            self.screenshot_display = QLabel()
            self.screenshot_display.setAlignment(Qt.AlignCenter)
            self.screenshot_display.setStyleSheet("border: 1px solid gray; background-color: white;")
            self.screenshot_display.setMinimumHeight(400)
            self.screenshot_display.setScaledContents(False)
            viewer_layout.addWidget(self.screenshot_display)

            # Screenshot details
            self.screenshot_details = QTextEdit()
            self.screenshot_details.setReadOnly(True)
            self.screenshot_details.setMaximumHeight(100)
            viewer_layout.addWidget(self.screenshot_details)

            layout.addWidget(viewer_group)

            # Play video button if video exists
            if self.session.video_path and os.path.exists(self.session.video_path):
                play_video_btn = QPushButton("Play Video")
                play_video_btn.clicked.connect(self.play_video)
                layout.addWidget(play_video_btn)

            # Load first screenshot
            self.update_screenshot_display()
        else:
            no_screenshots_label = QLabel("No screenshots in this session")
            no_screenshots_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(no_screenshots_label)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)

        self.update_navigation_buttons()

    def update_screenshot_display(self):
        """Update the screenshot display"""
        if not self.session.screenshots:
            return

        screenshot = self.session.screenshots[self.current_screenshot_index]
        self.screenshot_label.setText(f"Screenshot {self.current_screenshot_index + 1} / {len(self.session.screenshots)}")

        # Load image
        if os.path.exists(screenshot.image_path):
            pixmap = QPixmap(screenshot.image_path)
            # Scale to fit while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.screenshot_display.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.screenshot_display.setPixmap(scaled_pixmap)

        # Update details
        details = f"<b>Timestamp:</b> {screenshot.timestamp}<br>"
        details += f"<b>Button:</b> {screenshot.button_text}<br>"
        details += f"<b>Action:</b> {screenshot.action_description}<br>"
        details += f"<b>Window:</b> {screenshot.window_title}<br>"
        details += f"<b>Position:</b> {screenshot.button_position}"

        self.screenshot_details.setHtml(details)

    def show_previous_screenshot(self):
        """Show previous screenshot"""
        if self.current_screenshot_index > 0:
            self.current_screenshot_index -= 1
            self.update_screenshot_display()
            self.update_navigation_buttons()

    def show_next_screenshot(self):
        """Show next screenshot"""
        if self.current_screenshot_index < len(self.session.screenshots) - 1:
            self.current_screenshot_index += 1
            self.update_screenshot_display()
            self.update_navigation_buttons()

    def update_navigation_buttons(self):
        """Update navigation button states"""
        self.prev_btn.setEnabled(self.current_screenshot_index > 0)
        self.next_btn.setEnabled(self.current_screenshot_index < len(self.session.screenshots) - 1)

    def play_video(self):
        """Play the session video"""
        if self.session.video_path and os.path.exists(self.session.video_path):
            try:
                if sys.platform == 'win32':
                    os.startfile(self.session.video_path)
                elif sys.platform == 'darwin':
                    subprocess.call(['open', self.session.video_path])
                else:
                    subprocess.call(['xdg-open', self.session.video_path])
            except Exception as e:
                QMessageBox.warning(self, "Playback Error", f"Failed to play video: {e}")


class PetroleumTemplateDialog(QDialog):
    """Dialog for selecting petroleum software workflow templates"""

    def __init__(self, parent=None, templates=None, detected_programs=None):
        super().__init__(parent)
        self.templates = templates or []
        self.detected_programs = detected_programs or {}
        self.selected_template = None
        self.initUI()

    def initUI(self):
        """Initialize the template dialog UI"""
        self.setWindowTitle("Petroleum Software Templates")
        self.setModal(True)
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel("Select a petroleum software workflow template:")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_label)

        # Filter controls
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter by software:"))

        self.software_filter = QComboBox()
        self.software_filter.addItem("All Software")
        software_list = list(set(template.software for template in self.templates))
        for software in sorted(software_list):
            display_name = self.get_software_display_name(software)
            self.software_filter.addItem(display_name, software)
        self.software_filter.currentTextChanged.connect(self.filter_templates)
        filter_layout.addWidget(self.software_filter)

        filter_layout.addWidget(QLabel("Category:"))

        self.category_filter = QComboBox()
        self.category_filter.addItem("All Categories")
        categories = list(set(template.category for template in self.templates))
        for category in sorted(categories):
            self.category_filter.addItem(category.title(), category)
        self.category_filter.currentTextChanged.connect(self.filter_templates)
        filter_layout.addWidget(self.category_filter)

        layout.addLayout(filter_layout)

        # Templates table
        self.templates_table = QTableWidget()
        self.templates_table.setColumnCount(6)
        self.templates_table.setHorizontalHeaderLabels([
            "Template Name", "Software", "Category", "Time Estimate", "Difficulty", "Status"
        ])

        # Set column widths
        self.templates_table.setColumnWidth(0, 200)  # Name
        self.templates_table.setColumnWidth(1, 150)  # Software
        self.templates_table.setColumnWidth(2, 120)  # Category
        self.templates_table.setColumnWidth(3, 100)  # Time
        self.templates_table.setColumnWidth(4, 80)   # Difficulty

        self.templates_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.templates_table.itemSelectionChanged.connect(self.on_selection_changed)
        self.templates_table.itemDoubleClicked.connect(self.on_template_double_clicked)

        layout.addWidget(self.templates_table)

        # Details panel
        details_group = QGroupBox("Template Details")
        details_layout = QVBoxLayout(details_group)

        self.template_details = QTextEdit()
        self.template_details.setReadOnly(True)
        self.template_details.setMaximumHeight(150)
        details_layout.addWidget(self.template_details)

        layout.addWidget(details_group)

        # Buttons
        button_layout = QHBoxLayout()

        self.select_btn = QPushButton("Select Template")
        self.select_btn.clicked.connect(self.accept)
        self.select_btn.setEnabled(False)
        button_layout.addWidget(self.select_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        # Populate table
        self.populate_templates_table()

    def get_software_display_name(self, software_key):
        """Get display name for software key"""
        if software_key in self.detected_programs:
            program_info = self.detected_programs[software_key]
            return f"{program_info.display_name} ✓"
        return software_key.replace("_", " ").title()

    def populate_templates_table(self):
        """Populate the templates table"""
        self.templates_table.setRowCount(len(self.templates))

        for row, template in enumerate(self.templates):
            # Template name
            name_item = QTableWidgetItem(template.name)
            self.templates_table.setItem(row, 0, name_item)

            # Software
            software_display = self.get_software_display_name(template.software)
            software_item = QTableWidgetItem(software_display)
            if template.software in self.detected_programs:
                software_item.setStyleSheet("color: green;")
            else:
                software_item.setStyleSheet("color: red;")
            self.templates_table.setItem(row, 1, software_item)

            # Category
            category_item = QTableWidgetItem(template.category.title())
            self.templates_table.setItem(row, 2, category_item)

            # Time estimate
            time_item = QTableWidgetItem(template.estimated_time)
            self.templates_table.setItem(row, 3, time_item)

            # Difficulty
            difficulty_item = QTableWidgetItem(template.difficulty.title())
            if template.difficulty == "beginner":
                difficulty_item.setStyleSheet("color: green;")
            elif template.difficulty == "intermediate":
                difficulty_item.setStyleSheet("color: orange;")
            else:  # advanced
                difficulty_item.setStyleSheet("color: red;")
            self.templates_table.setItem(row, 4, difficulty_item)

            # Status
            if template.software in self.detected_programs:
                status_item = QTableWidgetItem("✓ Available")
                status_item.setStyleSheet("color: green;")
            else:
                status_item = QTableWidgetItem("✗ Not Installed")
                status_item.setStyleSheet("color: red;")
            self.templates_table.setItem(row, 5, status_item)

        self.templates_table.resizeColumnsToContents()

    def filter_templates(self):
        """Filter templates based on selected filters"""
        software_filter = self.software_filter.currentData()
        category_filter = self.category_filter.currentData()

        for row in range(self.templates_table.rowCount()):
            template = self.templates[row]
            show_row = True

            if software_filter and template.software != software_filter:
                show_row = False

            if category_filter and template.category != category_filter:
                show_row = False

            self.templates_table.setRowHidden(row, not show_row)

    def on_selection_changed(self):
        """Handle template selection change"""
        current_row = self.templates_table.currentRow()
        if current_row >= 0:
            template = self.templates[current_row]
            self.selected_template = template
            self.select_btn.setEnabled(True)

            # Update details
            details = f"<b>{template.name}</b><br><br>"
            details += f"<b>Software:</b> {self.get_software_display_name(template.software)}<br>"
            details += f"<b>Category:</b> {template.category.title()}<br>"
            details += f"<b>Estimated Time:</b> {template.estimated_time}<br>"
            details += f"<b>Difficulty:</b> {template.difficulty.title()}<br><br>"
            details += f"<b>Description:</b> {template.description}<br><br>"
            details += f"<b>Prerequisites:</b><br>"
            for prereq in template.prerequisites:
                details += f"• {prereq}<br>"

            self.template_details.setHtml(details)
        else:
            self.selected_template = None
            self.select_btn.setEnabled(False)
            self.template_details.clear()

    def on_template_double_clicked(self, item):
        """Handle double-click on template"""
        if self.selected_template:
            self.accept()

    def get_selected_template(self):
        """Get the selected template"""
        return self.selected_template


class CleanupDialog(QDialog):
    """Dialog for cleanup settings"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        """Initialize the cleanup dialog UI"""
        self.setWindowTitle("Cleanup Old Sessions")
        self.setModal(True)
        self.resize(400, 200)

        layout = QVBoxLayout(self)

        # Description
        desc_label = QLabel("Delete recording sessions older than specified number of days:")
        layout.addWidget(desc_label)

        # Days input
        days_layout = QHBoxLayout()
        days_layout.addWidget(QLabel("Days:"))

        self.days_spin = QSpinBox()
        self.days_spin.setRange(1, 365)
        self.days_spin.setValue(7)
        self.days_spin.setSuffix(" days")
        days_layout.addWidget(self.days_spin)

        days_layout.addStretch()
        layout.addLayout(days_layout)

        # Warning
        warning_label = QLabel("⚠ This will permanently delete all screenshots and videos for old sessions.")
        warning_label.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(warning_label)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_days(self) -> int:
        """Get the number of days to keep"""
        return self.days_spin.value()


if __name__ == "__main__":
    # Standalone testing
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = PetroleumLauncherWidget()
    window.show()
    sys.exit(app.exec_())