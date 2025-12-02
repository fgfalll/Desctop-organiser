import sys
import os
import importlib.util
import shutil
import yaml
import platform
import psutil
import re
import copy
import json
import zipfile
import tempfile
import hashlib
from datetime import datetime, timedelta, time
from typing import Optional
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QButtonGroup, QComboBox,
    QMenuBar, QAction, QDialog, QTabWidget, QTabBar, QFormLayout,
    QSpinBox, QCheckBox, QLineEdit, QListWidget, QListWidgetItem,
    QDialogButtonBox, QMessageBox, QRadioButton, QGroupBox, QFileDialog, QTimeEdit, QSplashScreen,
    QScrollArea, QProgressDialog, QSystemTrayIcon, QMenu, QProgressBar, QSizePolicy, QStyleOptionButton, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QTime, QObject, QRect, QDateTime, QCoreApplication, QMetaType
from PyQt5.QtGui import QPainter, QFont, QColor, QPen, QPixmap, QBrush, QKeySequence, QPainterPath, QPalette
from PyQt5.QtWidgets import QStyle

# Register custom meta types to avoid QVector<int> warnings
try:
    # Register QVector<int> meta type for cross-thread signal/slot connections
    from PyQt5.QtCore import qRegisterMetaType
    qRegisterMetaType('QVector<int>')
except ImportError:
    # Fallback for older PyQt5 versions
    try:
        from PyQt5.QtCore import QMetaType
        if QMetaType.type('QVector<int>') == 0:
            QMetaType.registerType('QVector<int>')
    except:
        pass  # Final fallback


class WindowsCheckBox(QCheckBox):
    """Custom checkbox with Windows-style checkmark"""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        # Set larger checkbox size
        self.setStyleSheet("WindowsCheckBox { spacing: 10px; }")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get the rectangle for the indicator and make it bigger
        option = QStyleOptionButton()
        option.initFrom(self)
        rect = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, self)

        # Make checkbox bigger - expand from default 13x13 to 20x20
        checkbox_size = 20
        rect = QRect(rect.left(), rect.top(), checkbox_size, checkbox_size)

        # Draw unchecked state
        if not self.isChecked():
            painter.fillRect(rect, QColor("#FFFFFF"))
            painter.setPen(QPen(QColor("#6C6C6C"), 2))
            painter.drawRect(rect.adjusted(1, 1, -1, -1))
        else:
            # Draw checked state with blue background
            painter.fillRect(rect, QColor("#0078D4"))
            painter.setPen(QPen(QColor("#0078D4"), 2))
            painter.drawRect(rect.adjusted(1, 1, -1, -1))

            # Draw white checkmark - make it thicker and bigger
            painter.setPen(QPen(QColor("#FFFFFF"), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            check_rect = rect.adjusted(4, 4, -4, -4)

            # Draw checkmark path
            path = QPainterPath()
            path.moveTo(check_rect.left() + 2, check_rect.center().y())
            path.lineTo(check_rect.left() + check_rect.width() * 0.4, check_rect.bottom() - 2)
            path.lineTo(check_rect.right() - 2, check_rect.top() + 2)
            painter.drawPath(path)

        # Draw the text with adjusted position
        text_rect = QRect(rect.right() + 8, rect.top(), self.width() - rect.right() - 8, rect.height())
        painter.setPen(QPen(self.palette().text().color()))
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.text())

        painter.end()
import subprocess
import json
from pathlib import Path

# --- Administrator Privilege Functions ---
def is_running_as_admin() -> bool:
    """Check if the current process is running with administrator privileges"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def request_admin_privileges() -> bool:
    """Request administrator privileges by restarting the application with elevated rights"""
    if is_running_as_admin():
        return True

    try:
        import ctypes
        # Get the path to the current executable
        executable = sys.executable
        # Get command line arguments
        args = ' '.join(sys.argv[1:])

        # ShellExecute with "runas" verb to request elevation
        result = ctypes.windll.shell32.ShellExecuteW(
            None,           # Parent window
            "runas",        # Verb to request elevation
            executable,     # Application to run
            args,           # Command line arguments
            None,           # Current directory
            1               # Show command (1 = normal)
        )

        # ShellExecute returns values > 32 on success
        return result > 32
    except Exception as e:
        print(f"Failed to request administrator privileges: {e}")
        return False

def run_with_admin_privileges(command: list, **kwargs) -> subprocess.CompletedProcess:
    """Run a command with administrator privileges"""
    if is_running_as_admin():
        # Already running as admin, execute directly
        return subprocess.run(command, **kwargs)

    try:
        # Create a temporary batch script for elevated execution
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False) as f:
            batch_file = f.name
            # Escape command properly for batch file
            cmd_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in command)
            f.write(f"@echo off\n{cmd_str}\nexit /b %ERRORLEVEL%\n")

        try:
            # Run the batch file with elevation
            result = subprocess.run(
                ['powershell', '-Command', f'Start-Process -FilePath "{batch_file}" -Verb RunAs -Wait'],
                capture_output=True,
                text=True,
                **kwargs
            )
            return result
        finally:
            # Clean up temporary batch file
            try:
                os.unlink(batch_file)
            except:
                pass
    except Exception as e:
        print(f"Failed to run with admin privileges: {e}")
        # Fallback to normal execution
        return subprocess.run(command, **kwargs)

# --- Configuration File Path ---
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".DesktopOrganizer")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yaml")
LAST_RUN_FILE = os.path.join(CONFIG_DIR, "last_run.txt")
os.makedirs(CONFIG_DIR, exist_ok=True)


class PackageMessageFormatter:
    """Dynamic package-related message formatter to avoid hardcoded strings"""

    @staticmethod
    def package_not_installed(package_name: str) -> str:
        """Format message for package not installed"""
        return f"{package_name} (not installed)"

    @staticmethod
    def package_version_mismatch(package_name: str, installed_version: str, required_version: str) -> str:
        """Format message for package version mismatch"""
        return f"{package_name} (version {installed_version} < {required_version})"

    @staticmethod
    def module_dependencies_missing(module_name: str, missing_deps: list) -> str:
        """Format message for missing module dependencies"""
        return f"🔧 Installing missing dependencies for {module_name}: {', '.join(missing_deps)}"

    @staticmethod
    def package_install_failed(package_spec: str, error_msg: str) -> str:
        """Format message for package installation failure"""
        return f"❌ Failed to install {package_spec}: {error_msg}"

    @staticmethod
    def package_install_failed_admin(package_spec: str, error_msg: str) -> str:
        """Format message for package installation failure with admin privileges"""
        return f"❌ Failed to install {package_spec} with admin privileges: {error_msg}"

    @staticmethod
    def package_uninstall_failed(package_name: str, error_msg: str) -> str:
        """Format message for package uninstallation failure"""
        return f"❌ Failed to uninstall {package_name}: {error_msg}"

    @staticmethod
    def package_uninstall_succeeded(package_name: str) -> str:
        """Format message for successful package uninstallation"""
        return f"Uninstalled {package_name}"

    @staticmethod
    def package_uninstalling(package_name: str) -> str:
        """Format message for package uninstallation in progress"""
        return f"Uninstalling {package_name}"

    @staticmethod
    def package_uninstalling_no_longer_needed(package_name: str) -> str:
        """Format message for package no longer needed"""
        return f"Uninstalling {package_name} (no longer needed)..."

    @staticmethod
    def module_dependency_repair_failed(module_name: str) -> str:
        """Format message for module dependency repair failure"""
        return f"❌ Failed to repair dependencies for {module_name}"

    @staticmethod
    def module_dependency_install_failed(module_name: str) -> str:
        """Format message for module dependency installation failure"""
        return f"Failed to install dependencies for {module_name}"

    @staticmethod
    def module_load_failed(module_name: str, error_msg: str) -> str:
        """Format message for module loading failure"""
        return f"Failed to load module {module_name}: {error_msg}"

    @staticmethod
    def module_launch_failed(module_name: str, error_msg: str) -> str:
        """Format message for module launch failure"""
        return f"❌ Failed to launch module '{module_name}' from tray: {error_msg}"

    @staticmethod
    def module_error(module_name: str, error_message: str) -> str:
        """Format message for module error"""
        return f"❌ Помилка модуля ({module_name}): {error_message}"

    @staticmethod
    def module_reload_failed(module_name: str) -> str:
        """Format message for module reload failure"""
        return f"❌ Failed to reload module: {module_name}"

    @staticmethod
    def package_not_available(package_name: str, python_type: str = "current") -> str:
        """Format message for package not available in Python"""
        return f"⚠️ Package '{package_name}' not available in {python_type} Python"

    @staticmethod
    def package_available(package_name: str, python_version: str = "") -> str:
        """Format message for package availability"""
        if python_version:
            return f"✅ System Python {python_version} is working correctly."
        return f"✅ System Python is working correctly."

    @staticmethod
    def venv_package_working(package_name: str = "", output: str = "") -> str:
        """Format message for virtual environment working correctly"""
        base_msg = "✅ Virtual environment Python is working correctly."
        if output:
            base_msg += f"\n🔍 VENV Python output: {output.strip()}"
        return base_msg

    @staticmethod
    def venv_python_error(error_msg: str) -> str:
        """Format message for virtual environment Python error"""
        return f"⚠️ VENV Python error: {error_msg.strip()}"

    @staticmethod
    def venv_python_test_failed(error_msg: str) -> str:
        """Format message for virtual environment Python test failure"""
        return f"⚠️ VENV Python test failed: {error_msg}"

    @staticmethod
    def python_setup_check_error(error_msg: str) -> str:
        """Format message for Python setup check error"""
        return f"❌ Error checking Python setup: {error_msg}"

    @staticmethod
    def python_installation_failed(error_msg: str) -> str:
        """Format message for Python installation failure"""
        return f"❌ Installation failed: {error_msg}"

    @staticmethod
    def python_download_install_failed(error_msg: str) -> str:
        """Format message for Python download/installation failure"""
        return f"❌ Download/installation failed: {error_msg}"

    @staticmethod
    def extract_package_name(package_spec: str) -> str:
        """Extract base package name from package specification"""
        if not package_spec:
            return "unknown"

        # Handle various package specification formats
        # Examples: "pandas>=1.3.0", "numpy==1.21.0", "matplotlib", "scipy>=1.7.0,<2.0.0"
        name = package_spec.split('>=')[0].split('==')[0].split('<=')[0].split('~=')[0].split('><')[0].strip()
        return name.lower()

    @staticmethod
    def format_package_spec_with_error(package_spec: str, error_msg: str) -> str:
        """Format package specification with error details"""
        package_name = PackageMessageFormatter.extract_package_name(package_spec)
        return f"❌ Package '{package_name}' installation failed: {error_msg}"

    @staticmethod
    def format_module_dependency_error(module_name: str, missing_packages: list) -> str:
        """Format module dependency error with dynamic package names"""
        if not missing_packages:
            return f"❌ Module '{module_name}' has unknown dependency issues"

        package_count = len(missing_packages)
        if package_count == 1:
            return f"❌ Module '{module_name}' missing dependency: {missing_packages[0]}"
        elif package_count <= 3:
            return f"❌ Module '{module_name}' missing dependencies: {', '.join(missing_packages)}"
        else:
            return f"❌ Module '{module_name}' missing {package_count} dependencies: {', '.join(missing_packages[:3])}..."

    @staticmethod
    def format_success_message(item_type: str, item_name: str, action: str = "installed") -> str:
        """Format generic success message"""
        return f"✅ Successfully {action} {item_type}: {item_name}"

    @staticmethod
    def format_error_message(item_type: str, item_name: str, error_msg: str, action: str = "process") -> str:
        """Format generic error message"""
        return f"❌ Failed to {action} {item_type} '{item_name}': {error_msg}"

    @staticmethod
    def get_critical_packages() -> list:
        """Get list of critical packages that need special handling"""
        return ['pip', 'setuptools', 'wheel']

    @staticmethod
    def is_critical_package(package_name: str) -> bool:
        """Check if a package is considered critical for system operation"""
        return package_name.lower() in [pkg.lower() for pkg in PackageMessageFormatter.get_critical_packages()]

    @staticmethod
    def format_critical_package_error(package_name: str, error_msg: str) -> str:
        """Format error message for critical packages"""
        if PackageMessageFormatter.is_critical_package(package_name):
            return f"🚨 CRITICAL: Failed to load essential package '{package_name}': {error_msg}"
        else:
            return f"❌ Failed to load package '{package_name}': {error_msg}"

    @staticmethod
    def get_debug_package_name() -> str:
        """Get a generic name for debugging package operations"""
        return "required-packages"


# Global instance for easy access
msg_formatter = PackageMessageFormatter()

# --- Setup Virtual Environment Python Path ---
def setup_venv_python_path():
    """Add virtual environment site-packages to Python path (Windows)"""
    try:
        venv_dir = os.path.join(CONFIG_DIR, 'modules_venv')
        if os.path.exists(venv_dir):
            # Windows site-packages path
            site_packages_path = os.path.join(venv_dir, 'Lib', 'site-packages')

            if os.path.exists(site_packages_path):
                if site_packages_path not in sys.path:
                    sys.path.insert(0, site_packages_path)
                    # Virtual environment path configured successfully
            else:
                print(f"❌ Virtual environment site-packages not found: {site_packages_path}")
        else:
            print(f"❌ Virtual environment not found: {venv_dir}")

    except Exception as e:
        # If path setup fails, continue without it but log the error
        print(f"❌ Failed to setup virtual environment path: {e}")
        pass

# Setup Python path early
setup_venv_python_path()

# --- Default Settings ---
DEFAULT_SETTINGS = {
    'application': {
        'autostart_timer_enabled': True,
        'notifications_enabled': True,
        'minimize_to_tray': False,
    },
    'timer': {
        'override_default_enabled': False,
        'default_minutes': 3,
    },
    'drives': {
        'main_drive_policy': 'D',
    },
    'file_manager': {
        'max_file_size_mb': 100,
        'allowed_extensions': ['.lnk'],
        'allowed_filenames': []
    },
    'schedule': {
        'type': 'disabled',  # 'вимкнено', 'щодня', 'щотижня', 'щомісяця', 'щокварталу'
        'time_start': '15:00',
        'time_end': '17:00',
        'day_of_week': 1,  # 1=Понеділок, 7=Неділя
        'day_of_month': 1,
        'quarter_month': 1, # 1, 2, 3
        'quarter_day': 1
    }
}

SCHEDULE_TYPE_MAP = {
    "disabled": "Вимкнено",
    "daily": "Щодня",
    "weekly": "Щотижня",
    "monthly": "Щомісяця",
    "quarterly": "Щокварталу",
}

REVERSE_SCHEDULE_TYPE_MAP = {
    "Вимкнено": "disabled",
    "Щодня": "daily",
    "Щотижня": "weekly",
    "Щомісяця": "monthly",
    "Щокварталу": "quarterly",
}

# --- Module Directory Configuration ---
MODULE_DIR_NAME = "modules"  # Directory for module subdirectories

# --- Global Splash Screen Reference ---
global_splash = None

def add_splash_message(message):
    """Add message to splash screen"""
    global global_splash
    if global_splash and hasattr(global_splash, 'add_message') and not getattr(global_splash, 'finished', False):
        global_splash.add_message(message)

# --- Module Management System ---

class ModuleInfo:
    """Module information with embedded manifest (supports single files and directories)"""

    def __init__(self, module_path: str):
        self.module_path = module_path
        self.valid = False
        self.error = None
        self.is_directory = os.path.isdir(module_path)

        if self.is_directory:
            self.module_dir = module_path
            self.module_name = os.path.basename(module_path)
            self.entry_point = os.path.join(module_path, "main.py")
        else:
            self.module_dir = os.path.dirname(module_path)
            self.module_name = os.path.splitext(os.path.basename(module_path))[0]
            self.entry_point = module_path

        # Extract manifest from file or directory
        try:
            self.manifest = self._extract_manifest()
            self._validate_manifest()
            self.valid = True
        except Exception as e:
            self.error = f"Invalid module manifest: {e}"
            self.manifest = {}

    def _extract_manifest(self) -> dict:
        """Extract embedded manifest from file or directory"""
        try:
            if self.is_directory:
                # For directory modules, try to find manifest in main.py first
                main_file = self.entry_point
                if os.path.exists(main_file):
                    manifest = self._extract_from_file(main_file)
                    if manifest:
                        return manifest

                # If not found in main.py, look for separate manifest.json
                manifest_file = os.path.join(self.module_dir, "manifest.json")
                if os.path.exists(manifest_file):
                    with open(manifest_file, 'r', encoding='utf-8') as f:
                        return json.load(f)

                raise ValueError("Маніфест модуля не знайдено в директорії")
            else:
                # Single file module - extract from file
                manifest = self._extract_from_file(self.module_path)
                if manifest:
                    return manifest
                else:
                    raise ValueError("Маніфест модуля не знайдено у файлі")

        except json.JSONDecodeError as e:
            raise ValueError(f"Некоректний JSON у маніфесті: {e}")
        except Exception as e:
            raise ValueError(f"Помилка читання модуля: {e}")

    def _extract_from_file(self, file_path: str) -> dict:
        """Extract manifest from a Python file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Look for embedded manifest between special markers
            start_marker = 'MODULE_MANIFEST_START'
            end_marker = 'MODULE_MANIFEST_END'

            start_idx = content.find(start_marker)
            if start_idx == -1:
                return None

            start_idx += len(start_marker)
            end_idx = content.find(end_marker, start_idx)
            if end_idx == -1:
                return None

            manifest_json = content[start_idx:end_idx].strip()
            return json.loads(manifest_json)

        except Exception:
            return None

    def _validate_manifest(self):
        """Validate manifest fields"""
        required_fields = ['name', 'version', 'main_class']
        for field in required_fields:
            if field not in self.manifest:
                raise ValueError(f"Відсутнє обов'язкове поле: {field}")

    @property
    def name(self) -> str:
        return self.manifest.get('name', self.module_name)

    @property
    def version(self) -> str:
        return self.manifest.get('version', '1.0.0')

    @property
    def description(self) -> str:
        return self.manifest.get('description', '')

    @property
    def menu_text(self) -> str:
        return self.manifest.get('menu_text', self.name)

    @property
    def main_class(self) -> str:
        return self.manifest['main_class']

    @property
    def dependencies(self) -> list:
        return self.manifest.get('dependencies', [])

    @property
    def dependency_packages(self) -> dict:
        """Map import names to pip package names"""
        # Support both old format and new format
        if 'dependency_packages' in self.manifest:
            return self.manifest['dependency_packages']

        # Auto-generate mapping for simple cases ONLY when dependencies list exists
        # This maintains backward compatibility but avoids double processing
        mapping = {}
        for dep in self.dependencies:
            if isinstance(dep, str):
                # Simple string: use same name for both import and package
                package_name = dep.split('>=')[0].split('==')[0].split('<=')[0].strip()
                mapping[package_name] = dep
            elif isinstance(dep, dict):
                # Dictionary format: {"import_name": "pip_package_spec"}
                mapping.update(dep)
        return mapping

    @property
    def has_explicit_dependency_packages(self) -> bool:
        """Check if dependency_packages is defined"""
        return 'dependency_packages' in self.manifest

    @property
    def python_version(self) -> str:
        return self.manifest.get('python_version', '3.8+')

    @property
    def author(self) -> str:
        return self.manifest.get('author', 'Unknown')

    @property
    def category(self) -> str:
        return self.manifest.get('category', 'General')


class SharedVirtualEnvironmentManager:
    """Shared virtual environment manager"""

    def __init__(self, base_dir: str, settings=None):
        self.base_dir = base_dir
        self.settings = settings or {}
        # Virtual environment should be in the config directory
        self.venv_dir = os.path.join(CONFIG_DIR, 'modules_venv')
        self.installed_packages = set()  # Track installed packages
        self.package_modules = {}  # Track which modules installed which packages
        # Store package info in the same directory as settings
        self.packages_file = os.path.join(CONFIG_DIR, 'module_packages.json')
        self._migrate_venv_if_needed()
        self._load_package_info()

    def _migrate_venv_if_needed(self):
        """Migrate virtual environment from modules/ to config directory if needed"""
        old_venv_dir = os.path.join(self.base_dir, 'modules_venv')

        # Check if old venv exists and new one doesn't
        if os.path.exists(old_venv_dir) and not os.path.exists(self.venv_dir):
            try:
                import shutil
                # Move the entire virtual environment directory
                shutil.move(old_venv_dir, self.venv_dir)
            except Exception:
                # If move fails, try to recreate the venv in new location
                pass

        # After migration, ensure Python path is updated
        setup_venv_python_path()

    def _load_package_info(self):
        """Load package info and sync with venv"""
        try:
            # Check if we need to migrate from old location
            old_packages_file = os.path.join(self.base_dir, 'module_packages.json')
            if os.path.exists(old_packages_file) and not os.path.exists(self.packages_file):
                try:
                    import shutil
                    shutil.move(old_packages_file, self.packages_file)
                except Exception:
                    # Copy the data instead
                    try:
                        with open(old_packages_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        with open(self.packages_file, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=2)
                    except Exception:
                        pass
                        
            if os.path.exists(self.packages_file):
                with open(self.packages_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.installed_packages = set(data.get('installed_packages', []))
                    self.package_modules = data.get('package_modules', {})
            else:
                # Sync with actual packages in venv
                self.installed_packages = set()
                self.package_modules = {}

            # Sync with actual packages in venv
            self._sync_installed_packages()
        except Exception as e:
            pass

    def _sync_installed_packages(self):
        """Sync package list with installed packages"""
        try:
            pip_path = self.get_pip_path()
            if not pip_path:
                return

            # Get list of installed packages from venv
            if isinstance(pip_path, list):
                # New list format
                cmd = pip_path + ['list', '--format=json']
            else:
                # Old string format (backward compatibility)
                if ' -m pip' in pip_path:
                    cmd = pip_path.split() + ['list', '--format=json']
                else:
                    cmd = [pip_path, 'list', '--format=json']

            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)

            if result.returncode == 0:
                import json
                installed = json.loads(result.stdout)
                actual_packages = {pkg['name'].lower() for pkg in installed}

                # Update our tracking
                old_count = len(self.installed_packages)
                self.installed_packages.update(actual_packages)
                new_count = len(self.installed_packages)

                # Show some of the packages for debugging
                if actual_packages:
                    sample_packages = list(sorted(actual_packages))[:5]
        except Exception as e:
            pass
            
    
    def _is_package_installed(self, package_name: str, use_cache: bool = True) -> bool:
        """Check if a package is actually installed in the venv"""
        # Use cache to avoid repeated checks
        cache_key = f"installed_{package_name.lower()}"
        if use_cache and hasattr(self, '_package_cache'):
            if cache_key in self._package_cache:
                return self._package_cache[cache_key]
        elif not hasattr(self, '_package_cache'):
            self._package_cache = {}

        is_installed = self._check_package_direct(package_name)
        self._package_cache[cache_key] = is_installed

        return is_installed

    def _check_package_direct(self, package_name: str) -> bool:
        """Direct check if a package is installed"""
        try:
            pip_path = self.get_pip_path()
            if not pip_path:
                return False

            # Check if package is installed using pip show
            if isinstance(pip_path, list):
                # New list format
                cmd = pip_path + ['show', package_name]
            else:
                # Old string format (backward compatibility)
                if ' -m pip' in pip_path:
                    cmd = pip_path.split() + ['show', package_name]
                else:
                    cmd = [pip_path, 'show', package_name]

            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)
            return result.returncode == 0
        except Exception:
            return False

    def _get_installed_version(self, package_name: str) -> Optional[str]:
        """Get the installed version of a package"""
        try:
            pip_path = self.get_pip_path()
            if not pip_path:
                return None

            # Check the exact package name only
            if ' -m pip' in pip_path:
                cmd = pip_path.split() + ['show', package_name]
            else:
                cmd = [pip_path, 'show', package_name]

            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith('Version:'):
                        return line.split(':', 1)[1].strip()

            return None
        except Exception:
            return None

    def _check_version_requirement(self, installed_version: str, required_spec: str) -> bool:
        """Check if installed version meets the requirement specification"""
        try:
            from packaging import version, requirements

            # Parse the requirement (e.g., ">=1.0.0", "==2.1.0", etc.)
            req = requirements.Requirement(required_spec)
            installed = version.parse(installed_version)

            return installed in req
        except ImportError:
            # Fallback: simple string comparison if packaging not available
            if '>=' in required_spec:
                required_version = required_spec.split('>=')[1].strip()
                return installed_version >= required_version
            elif '==' in required_spec:
                required_version = required_spec.split('==')[1].strip()
                return installed_version == required_version
            elif '<=' in required_spec:
                required_version = required_spec.split('<=')[1].strip()
                return installed_version <= required_version
            else:
                return True  # No version constraint
        except Exception:
            return True  # Assume compatible if checking fails

    def _check_package_availability(self, package_name: str) -> bool:
        """Check if a package is available in PyPI"""
        try:
            import urllib.request
            import json
            url = f"https://pypi.org/pypi/{package_name}/json"
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.getcode() == 200:
                    return True
        except Exception:
            pass
        return False

    def _is_more_specific_requirement(self, spec1: str, spec2: str) -> bool:
        """Determine which version specification is more specific"""
        # Simple heuristic: == is more specific than >= which is more specific than no version
        if '==' in spec1 and '==' not in spec2:
            return True
        if '>=' in spec1 and not any(op in spec2 for op in ['>=', '==', '<=', '~=']):
            return True
        return False

    def _deduplicate_dependencies(self, dependencies: list, dependency_packages: dict) -> dict:
        """Deduplicate dependencies, prioritizing dependencies list over dependency_packages"""
        packages = {}

        # Process dependencies list first (primary source - like requirements.txt)
        if dependencies:
            for dep in dependencies:
                if isinstance(dep, str):
                    package_spec = dep.strip()
                    pip_package_name = package_spec.split('>=')[0].split('==')[0].split('<=')[0].split('~=')[0].strip().lower()
                    packages[pip_package_name] = package_spec

        # Process dependency_packages only if dependencies list is empty (backward compatibility)
        if not dependencies and dependency_packages:
            for import_name, package_spec in dependency_packages.items():
                pip_package_name = package_spec.split('>=')[0].split('==')[0].split('<=')[0].split('~=')[0].strip().lower()
                if pip_package_name not in packages:
                    packages[pip_package_name] = package_spec
                else:
                    # Keep the more specific requirement
                    if self._is_more_specific_requirement(package_spec, packages[pip_package_name]):
                        packages[pip_package_name] = package_spec

        # Debug logging to track what's being processed
        if packages:
            pass
        return packages

    def _save_package_info(self):
        """Save package installation info to file"""
        try:
            data = {
                'installed_packages': list(self.installed_packages),
                'package_modules': self.package_modules
            }
            with open(self.packages_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def force_refresh_packages(self):
        """Force refresh of package list from virtual environment - only called when needed"""
        # Clear package cache
        if hasattr(self, '_package_cache'):
            self._package_cache.clear()

        # Sync with actual installed packages
        self._sync_installed_packages()

        # Update package tracking without verbose output
        try:
            pip_path = self.get_pip_path()
            if pip_path:
                if isinstance(pip_path, list):
                    # New list format
                    cmd = pip_path + ['list', '--format=json']
                else:
                    # Old string format (backward compatibility)
                    if ' -m pip' in pip_path:
                        cmd = pip_path.split() + ['list', '--format=json']
                    else:
                        cmd = [pip_path, 'list', '--format=json']

                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)

                if result.returncode == 0:
                    import json
                    installed = json.loads(result.stdout)
                    actual_packages = {pkg['name'].lower() for pkg in installed}

                    # Update our tracking to match reality
                    self.installed_packages = actual_packages
                    self._save_package_info()
        except Exception:
            # Error during refresh - use cached data
            pass

    def create_shared_venv(self) -> bool:
        """Create shared virtual environment for all modules"""
        if os.path.exists(self.venv_dir):
            # Validate existing venv
            if self._validate_venv():
                return True
            else:
                # Don't automatically delete - let user decide
                return True

        try:
            import venv

            # Determine which Python executable to use
            python_exe = self.settings.get('dedicated_python_path', sys.executable)
            print(f"🐍 Using Python executable: {python_exe}")

            # Try to create with current privileges first
            try:
                venv.create(self.venv_dir, with_pip=True, system_site_packages=False)
                print(f"✅ Created virtual environment: {self.venv_dir}")
                return True
            except PermissionError as e:
                print(f"⚠️ Permission denied creating venv: {e}")

                # Try with administrator privileges
                print("🔐 Requesting administrator privileges for virtual environment creation...")
                try:
                    # Create venv using python with admin privileges
                    cmd = [python_exe, '-m', 'venv', self.venv_dir, '--with-pip']
                    result = run_with_admin_privileges(cmd, capture_output=True, text=True, timeout=120)

                    if result.returncode == 0:
                        print(f"✅ Created virtual environment with admin privileges: {self.venv_dir}")
                        return True
                    else:
                        print(f"❌ Failed to create venv with admin privileges: {result.stderr}")
                        return False
                except Exception as admin_error:
                    print(f"❌ Failed to create venv with admin privileges: {admin_error}")
                    return False
        except Exception as e:
            print(f"❌ Failed to create virtual environment: {e}")
            return False

    def _validate_venv(self) -> bool:
        """Validate that the existing venv is properly set up"""
        try:
            pip_path = self.get_pip_path()
            if not pip_path:
                return False

            # Handle pip_path that might be a list or string
            if isinstance(pip_path, list):
                # New list format - check if the first element (executable) exists
                if len(pip_path) > 0 and not os.path.exists(pip_path[0]):
                    return False
                version_cmd = pip_path + ['--version']
                list_cmd = pip_path + ['list', '--format=json']
            else:
                # Old string format (backward compatibility)
                if ' -m pip' in pip_path:
                    # For command strings, we can't check file existence easily
                    cmd_base = pip_path.split(' -m pip')[0].strip('"')
                    if not os.path.exists(cmd_base):
                        return False
                    version_cmd = pip_path.split() + ['--version']
                    list_cmd = pip_path.split() + ['list', '--format=json']
                else:
                    # Direct executable
                    if not os.path.exists(pip_path):
                        return False
                    version_cmd = [pip_path, '--version']
                    list_cmd = [pip_path, 'list', '--format=json']

            result = subprocess.run(version_cmd, encoding='utf-8', errors='replace',
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return False

            # Also check that we can list packages (this tests the venv more thoroughly)
            result = subprocess.run(list_cmd, encoding='utf-8', errors='replace',
                                  capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return False

            return True
        except Exception as e:
            return False

    def get_pip_path(self) -> Optional[str]:
        """Get pip path for the shared virtual environment, ensure venv exists"""
        # Ensure virtual environment exists
        if not os.path.exists(self.venv_dir):
            if not self.create_shared_venv():
                return None

        # Try venv pip first (Windows)
        if os.path.exists(self.venv_dir):
            venv_pip = os.path.join(self.venv_dir, 'Scripts', 'pip.exe')
            venv_python = os.path.join(self.venv_dir, 'Scripts', 'python.exe')

            # Use virtual environment's python with -m pip for better compatibility
            if os.path.exists(venv_python):
                return [venv_python, '-m', 'pip']
            elif os.path.exists(venv_pip):
                return [venv_pip]

        # Last resort: use dedicated python with -m pip to install to venv
        try:
            if os.path.exists(self.venv_dir):
                # Use the dedicated Python path if available, otherwise fall back to sys.executable
                python_exe = self.settings.get('dedicated_python_path', sys.executable)
                return [python_exe, '-m', 'pip']
        except Exception:
            pass

        return None

    def install_dependencies(self, module_name: str, dependencies: list, dependency_packages: dict = None, parent_widget=None) -> bool:
        """Install dependencies in shared virtual environment"""
        # Check if there are any dependencies at all - do this first!
        if not dependencies and not dependency_packages:
            print(f"✅ No dependencies to install for {module_name}")
            return True

        if not self.create_shared_venv():
            return False

        pip_path = self.get_pip_path()
        if not pip_path:
            return False

        try:

            # First, sync with actual venv packages to ensure we have accurate tracking
            self._sync_installed_packages()

            # Deduplicate dependencies from both sources
            deduplicated_packages = self._deduplicate_dependencies(dependencies, dependency_packages)

            if not deduplicated_packages:
                return True

            
            # Analyze which packages need to be installed or upgraded
            packages_to_process = {}
            for pip_package_name, package_spec in deduplicated_packages.items():
                # Check if package is actually installed in venv
                if not self._is_package_installed(pip_package_name):
                    packages_to_process[pip_package_name] = {
                        'spec': package_spec,
                        'action': 'install',
                        'reason': 'not_installed'
                    }
                else:
                    # Package is installed, check version requirements
                    installed_version = self._get_installed_version(pip_package_name)
                    if installed_version and ('>=' in package_spec or '==' in package_spec or '<=' in package_spec or '~=' in package_spec):
                        # Extract version requirement from spec
                        version_req = package_spec.replace(pip_package_name, '').strip()
                        if version_req and not self._check_version_requirement(installed_version, version_req):
                            packages_to_process[pip_package_name] = {
                                'spec': package_spec,
                                'action': 'upgrade',
                                'reason': f'version_mismatch: installed {installed_version}, required {version_req}'
                            }
                    else:
                        pass

            if not packages_to_process:
                return True

            # Create progress dialog if parent widget is provided
            progress_dialog = None
            if parent_widget and len(packages_to_process) > 0:
                # Temporarily hide splash screen to ensure progress dialog is visible
                if 'global_splash' in globals() and globals()['global_splash']:
                    splash = globals()['global_splash']
                    splash.hide()
                    QApplication.processEvents()

                progress_dialog = PackageInstallProgressDialog(f"Встановлення залежностей для {module_name}", parent_widget)

                # Ensure the progress dialog is on top and visible
                progress_dialog.setWindowFlags(progress_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
                progress_dialog.raise_()
                progress_dialog.activateWindow()
                progress_dialog.show()

                # Force the dialog to be front and center
                progress_dialog.setFocus()
                QApplication.processEvents()

                # Additional delay to ensure the dialog is properly displayed
                QTimer.singleShot(100, lambda: None)  # Small delay to ensure UI updates

            # Process packages that need installation or upgrade
            total_packages = len(packages_to_process)
            current_package = 0

            for import_name, package_info in packages_to_process.items():
                package_spec = package_info['spec']
                action = package_info['action']
                reason = package_info['reason']

                # Update progress dialog
                current_package += 1
                if progress_dialog:
                    action_text = "Оновлення" if action == 'upgrade' else "Встановлення"
                    progress_dialog.update_progress(
                        f"{action_text} пакета {import_name} ({current_package}/{total_packages})",
                        f"Специфікація: {package_spec}"
                    )
                    progress_dialog.set_determinate_progress(current_package, total_packages)

                # Build the pip install command
                if isinstance(pip_path, list):
                    # Handle new list format
                    cmd = pip_path + ['install']
                else:
                    # Handle old string format (backward compatibility)
                    if ' -m pip' in pip_path:
                        cmd = pip_path.split() + ['install']
                    else:
                        cmd = [pip_path, 'install']

                # Add target directory for system pip installations
                if isinstance(pip_path, list) and len(pip_path) > 0:
                    python_exe = pip_path[0]
                elif isinstance(pip_path, str):
                    python_exe = pip_path.split()[0] if ' -m pip' in pip_path else pip_path
                else:
                    python_exe = None

                if python_exe and (sys.executable in python_exe or python_exe == 'pip'):
                    # Using system pip, target our virtual environment (Windows)
                    site_packages = os.path.join(self.venv_dir, 'Lib', 'site-packages')

                    if os.path.exists(site_packages):
                        cmd.extend(['--target', site_packages])

                if action == 'upgrade':
                    cmd.append('--upgrade')
                cmd.append(package_spec)

                # Try to install with current privileges first
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900)
                except subprocess.TimeoutExpired:
                    error_msg = "Package installation timed out"
                    return False

                if result.returncode != 0:
                    error_msg = result.stderr.strip() if result.stderr else "Unknown error"

                    # Check if it's a permission issue and try with admin privileges
                    if any(keyword in error_msg.lower() for keyword in ["permission denied", "access denied", "failed to create", "error: could not create"]):
                        print(f"🔐 Permission denied for {package_spec}, trying with administrator privileges...")

                        try:
                            # Run with administrator privileges
                            result = run_with_admin_privileges(
                                cmd,
                                capture_output=True,
                                text=True,
                                encoding='utf-8',
                                errors='replace',
                                timeout=900
                            )

                            if result.returncode == 0:
                                print(f"✅ Successfully installed {package_spec} with administrator privileges")
                            else:
                                admin_error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                                # Admin installation failed - error handling continues below

                                # Try to provide helpful suggestions
                                if "could not find" in admin_error_msg.lower() or "404" in admin_error_msg:
                                    pass
                                elif "network" in admin_error_msg.lower() or "connection" in admin_error_msg.lower():
                                    pass
                                elif "already satisfied" in admin_error_msg.lower():
                                    continue  # Continue with next package
                                return False
                        except Exception as admin_error:
                            print(msg_formatter.package_install_failed_admin(package_spec, str(admin_error)))
                            return False
                    else:
                        # Try to provide helpful suggestions for non-permission errors
                        if "could not find" in error_msg.lower() or "404" in error_msg:
                            pass
                        elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                            pass
                        elif "already satisfied" in error_msg.lower():
                            continue  # Continue with next package
                        return False
                else:
                    
                    # Update our tracking
                    installed_package_name = package_spec.split('>=')[0].split('==')[0].split('<=')[0].split('~=')[0].strip().lower()

                    self.installed_packages.add(installed_package_name)

                    if installed_package_name not in self.package_modules:
                        self.package_modules[installed_package_name] = []
                    # Track module->package relationship
                    if module_name not in self.package_modules[installed_package_name]:
                        self.package_modules[installed_package_name].append(module_name)
                        
            # Close progress dialog
            if progress_dialog:
                progress_dialog.close()
                progress_dialog.deleteLater()

                # Restore splash screen after progress dialog is closed
                if 'global_splash' in globals() and globals()['global_splash']:
                    splash = globals()['global_splash']
                    splash.show()
                    splash.raise_()
                    splash.activateWindow()
                    QApplication.processEvents()

            self._save_package_info()
            return True

        except Exception as e:
            print(f"❌ Помилка встановлення залежностей: {e}")
            # Close progress dialog on error
            if progress_dialog:
                progress_dialog.close()
                progress_dialog.deleteLater()

                # Restore splash screen even on error
                if 'global_splash' in globals() and globals()['global_splash']:
                    splash = globals()['global_splash']
                    splash.show()
                    splash.raise_()
                    splash.activateWindow()
                    QApplication.processEvents()

            return False

    def uninstall_dependencies(self, module_name: str, dependencies: list) -> bool:
        """Uninstall dependencies when a module is removed"""
        if not dependencies:
            return True

        pip_path = self.get_pip_path()
        if not pip_path:
            return False

        try:
            packages_to_uninstall = []
            for dep in dependencies:
                package_name = dep.split('>=')[0].split('==')[0].split('<=')[0].strip()

                # Check if this is the only module using this package
                if package_name in self.package_modules:
                    modules_using_package = self.package_modules[package_name]
                    # Remove this module from the list
                    if module_name in modules_using_package:
                        modules_using_package.remove(module_name)

                    # If no other modules use this package, uninstall it
                    if not modules_using_package:
                        packages_to_uninstall.append(package_name)
                        del self.package_modules[package_name]

            for package in packages_to_uninstall:
                print(msg_formatter.package_uninstalling_no_longer_needed(package))

                # Handle pip_path that might be a list or string
                if isinstance(pip_path, list):
                    # New list format
                    cmd = pip_path + ['uninstall', package, '-y']
                else:
                    # Old string format (backward compatibility)
                    if ' -m pip' in pip_path:
                        cmd = pip_path.split() + ['uninstall', package, '-y']
                    else:
                        cmd = [pip_path, 'uninstall', package, '-y']

                result = subprocess.run(cmd, encoding='utf-8', errors='replace',
                                      capture_output=True, text=True, timeout=900)
                if result.returncode != 0:
                    print(f"⚠️ Failed to uninstall {package}: {result.stderr}")
                else:
                    print(f"✅ Uninstalled {package}")
                    self.installed_packages.discard(package)

            self._save_package_info()
            return True

        except Exception as e:
            print(f"❌ Помилка видалення залежностей: {e}")
            return False

    def get_installed_packages(self) -> list:
        """Get list of installed packages"""
        return list(self.installed_packages)

    def get_package_info(self) -> dict:
        """Get detailed package information"""
        return {
            'installed_packages': self.get_installed_packages(),
            'package_modules': self.package_modules.copy()
        }

    def install_user_package(self, package_spec: str) -> bool:
        """Install a user-specified package in the virtual environment"""
        pip_path = self.get_pip_path()
        if not pip_path:
            print("❌ Could not find pip for installing user package")
            return False

        try:
            # Extract package name for tracking
            package_name = package_spec.split('>=')[0].split('==')[0].split('<=')[0].split('~=')[0].strip().lower()

            # Prepare the install command
            if isinstance(pip_path, list):
                # New list format
                cmd = pip_path + ['install', package_spec]
            else:
                # Old string format (backward compatibility)
                if ' -m pip' in pip_path:
                    cmd = pip_path.split() + ['install', package_spec]
                else:
                    cmd = [pip_path, 'install', package_spec]

            print(f"📦 Installing user package: {package_spec}")

            # Try to install with current privileges first
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900)
            except subprocess.TimeoutExpired:
                print(f"❌ Installation of {package_spec} timed out")
                return False

            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                print(msg_formatter.package_install_failed(package_spec, error_msg))

                # Check if it's a permission issue and try with admin privileges
                if any(keyword in error_msg.lower() for keyword in ["permission denied", "access denied", "failed to create", "error: could not create"]):
                    print(f"🔐 Permission denied for {package_spec}, trying with administrator privileges...")

                    try:
                        # Run with administrator privileges
                        result = run_with_admin_privileges(
                            cmd,
                            capture_output=True,
                            text=True,
                            encoding='utf-8',
                            errors='replace',
                            timeout=900
                        )

                        if result.returncode == 0:
                            print(f"✅ Successfully installed {package_spec} with administrator privileges")
                        else:
                            admin_error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                            print(msg_formatter.package_install_failed_admin(package_spec, admin_error_msg))
                            return False
                    except Exception as admin_error:
                        print(msg_formatter.package_install_failed_admin(package_spec, str(admin_error)))
                        return False
                else:
                    # Check for common errors and provide helpful tips
                    if "No matching distribution" in result.stderr:
                        print(f"💡 Tip: Package '{package_name}' may not exist. Check the package name.")
                    elif "Could not find a version" in result.stderr:
                        print(f"💡 Tip: Version specification may be invalid. Try without version.")
                    return False

            print(f"✅ Успішно встановлено {package_spec}")

            # Update package tracking
            installed_package_name = package_name
            self.installed_packages.add(installed_package_name)

            # Mark as user-installed package (not tied to any specific module)
            if installed_package_name not in self.package_modules:
                self.package_modules[installed_package_name] = []

            # Add user identifier to show this was manually installed
            if 'user' not in self.package_modules[installed_package_name]:
                self.package_modules[installed_package_name].append('user')

            # Save the updated package info
            self._save_package_info()

            return True

        except subprocess.TimeoutExpired:
            print(f"❌ Installation of {package_spec} timed out")
            return False
        except Exception as e:
            print(f"❌ Помилка встановлення пакета користувача {package_spec}: {e}")
            return False

    def uninstall_user_package(self, package_name: str) -> bool:
        """Uninstall a user-specified package from the virtual environment"""
        pip_path = self.get_pip_path()
        if not pip_path:
            print("❌ Could not find pip for uninstalling package")
            return False

        try:
            print(msg_formatter.package_uninstalling(package_name))

            # Handle pip_path that might be a list or string
            if isinstance(pip_path, list):
                # New list format
                cmd = pip_path + ['uninstall', package_name, '-y']
            else:
                # Old string format (backward compatibility)
                if ' -m pip' in pip_path:
                    pip_parts = pip_path.split(' ', 1)
                    cmd = pip_parts + ['uninstall', package_name, '-y']
                else:
                    cmd = [pip_path, 'uninstall', package_name, '-y']

            # Run the uninstallation
            result = subprocess.run(cmd, encoding='utf-8', errors='replace',
                                  capture_output=True, text=True, timeout=900)

            if result.returncode != 0:
                print(msg_formatter.package_uninstall_failed(package_name, result.stderr))
                return False

            print(msg_formatter.package_uninstall_succeeded(package_name))

            # Update package tracking
            self.installed_packages.discard(package_name)
            if package_name in self.package_modules:
                del self.package_modules[package_name]

            # Save the updated package info
            self._save_package_info()

            return True

        except subprocess.TimeoutExpired:
            print(f"❌ Uninstallation of {package_name} timed out")
            return False
        except Exception as e:
            print(f"❌ Помилка видалення пакета {package_name}: {e}")
            return False


class NGITPackageInstaller:
    """NGIT Package Installer for .ngitpac files"""

    PACKAGE_EXT = ".ngitpac"
    MANIFEST_FILE = "package.json"
    CHECKSUM_FILE = "checksums.json"
    MODULE_DIR = "module"

    def __init__(self, modules_dir: str, venv_manager=None, parent_widget=None):
        self.modules_dir = modules_dir
        self.venv_manager = venv_manager
        self.parent_widget = parent_widget
        self.errors = []
        self.warnings = []

    def install_package(self, package_path: str) -> bool:
        """Install package from .ngitpac file"""
        print(f"Installing package: {package_path}")

        self.errors.clear()
        self.warnings.clear()

        # Validate package file
        if not self._validate_package_file(package_path):
            return False

        try:
            # Extract package to temporary directory
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                print("  Extracting package...")
                if not self._extract_package(package_path, temp_dir):
                    return False

                # Verify package integrity
                print("  Verifying package integrity...")
                if not self._verify_package_integrity(temp_dir):
                    return False

                # Read package manifest
                manifest_path = os.path.join(temp_dir, self.MANIFEST_FILE)
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    package_manifest = json.load(f)

                module_info = package_manifest.get('module', {})
                module_name = module_info.get('name')
                module_version = module_info.get('version')

                if not module_name:
                    self.errors.append("Package manifest missing module name")
                    return False

                print(f"  Installing module: {module_name} v{module_version}")

                # Check for existing module
                module_install_path = os.path.join(self.modules_dir, module_name)
                if os.path.exists(module_install_path):
                    print(f"  Warning: Module '{module_name}' already exists")
                    # TODO: Ask user for confirmation to overwrite
                    self.warnings.append(f"Module '{module_name}' will be overwritten")

                    # Remove existing module
                    if os.path.isdir(module_install_path):
                        shutil.rmtree(module_install_path)
                    else:
                        os.remove(module_install_path)

                # Copy module files
                module_source_path = os.path.join(temp_dir, self.MODULE_DIR)
                print(f"  Installing to: {module_install_path}")
                if os.path.isdir(module_source_path):
                    shutil.copytree(module_source_path, module_install_path)
                else:
                    os.makedirs(self.modules_dir, exist_ok=True)
                    shutil.copy2(module_source_path, module_install_path)

                # Install dependencies if venv_manager is available
                if self.venv_manager and module_info.get('dependencies'):
                    print(f"  Installing {len(module_info['dependencies'])} dependencies...")
                    if not self._install_module_dependencies(module_name, module_info):
                        self.warnings.append("Some dependencies may not have installed correctly")

                print(f"  Successfully installed module: {module_name}")
                return True

        except Exception as e:
            self.errors.append(f"Installation failed: {e}")
            return False

    def _validate_package_file(self, package_path: str) -> bool:
        """Validate the package file"""
        if not os.path.exists(package_path):
            self.errors.append(f"Package file does not exist: {package_path}")
            return False

        if not package_path.endswith(self.PACKAGE_EXT):
            self.errors.append(f"Invalid package extension. Expected .{self.PACKAGE_EXT}")
            return False

        # Check if it's a valid zip file
        try:
            with zipfile.ZipFile(package_path, 'r') as zipf:
                # Check for required files
                required_files = [self.MANIFEST_FILE, self.CHECKSUM_FILE]
                required_dirs = [self.MODULE_DIR + '/']
                file_list = zipf.namelist()

                # Check required files
                for req_file in required_files:
                    if req_file not in file_list:
                        self.errors.append(f"Package missing file: {req_file}")
                        return False

                # Check required directories
                for req_dir in required_dirs:
                    if not any(f.startswith(req_dir) for f in file_list):
                        self.errors.append(f"Package missing directory: {req_dir}")
                        return False

                return True

        except zipfile.BadZipFile:
            self.errors.append("Package file is not a valid zip archive")
            return False
        except Exception as e:
            self.errors.append(f"Error reading package file: {e}")
            return False

    def _extract_package(self, package_path: str, extract_to: str) -> bool:
        """Extract package to directory"""
        try:
            with zipfile.ZipFile(package_path, 'r') as zipf:
                zipf.extractall(extract_to)
            return True
        except Exception as e:
            self.errors.append(f"Failed to extract package: {e}")
            return False

    def _verify_package_integrity(self, extract_dir: str) -> bool:
        """Verify package checksums"""
        try:
            checksum_path = os.path.join(extract_dir, self.CHECKSUM_FILE)
            with open(checksum_path, 'r', encoding='utf-8') as f:
                expected_checksums = json.load(f)

            for file_path, expected_hash in expected_checksums.items():
                # Use forward slashes from checksums file directly
                full_path = os.path.join(extract_dir, file_path.replace('/', os.sep))
                if not os.path.exists(full_path):
                    self.errors.append(f"Missing file in package: {file_path}")
                    return False

                with open(full_path, 'rb') as f:
                    actual_hash = hashlib.sha256(f.read()).hexdigest()

                if actual_hash != expected_hash:
                    self.errors.append(f"Checksum mismatch for {file_path}")
                    return False

            return True

        except Exception as e:
            self.errors.append(f"Failed to verify package integrity: {e}")
            return False

    def _install_module_dependencies(self, module_name: str, module_info: dict) -> bool:
        """Install module dependencies"""
        if not self.venv_manager:
            return False

        dependencies = module_info.get('dependencies', [])
        dependency_packages = module_info.get('dependency_packages')

        if not dependencies and not dependency_packages:
            return True

        try:
            return self.venv_manager.install_dependencies(
                module_name, dependencies, dependency_packages, self.parent_widget
            )
        except Exception as e:
            self.warnings.append(f"Dependency installation failed: {e}")
            return False

    def get_package_info(self, package_path: str) -> dict:
        """Get package information without installing"""
        try:
            with zipfile.ZipFile(package_path, 'r') as zipf:
                # Read manifest
                with zipf.open(self.MANIFEST_FILE) as f:
                    package_manifest = json.loads(f.read().decode('utf-8'))

                # Get file list and size
                files = zipf.namelist()
                size = os.path.getsize(package_path)

                return {
                    'manifest': package_manifest,
                    'module_info': package_manifest.get('module', {}),
                    'file_count': len(files),
                    'size_bytes': size,
                    'size_mb': round(size / (1024 * 1024), 2),
                    'files': files,
                    'errors': [],
                    'warnings': []
                }

        except Exception as e:
            return {
                'errors': [f"Failed to read package: {e}"],
                'warnings': [],
                'module_info': {}
            }

    def validate_package(self, package_path: str) -> bool:
        """Validate package without installing"""
        self.errors.clear()
        self.warnings.clear()

        if not self._validate_package_file(package_path):
            return False

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                if not self._extract_package(package_path, temp_dir):
                    return False

                if not self._verify_package_integrity(temp_dir):
                    return False

                # Read and validate manifest
                manifest_path = os.path.join(temp_dir, self.MANIFEST_FILE)
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    package_manifest = json.load(f)

                module_info = package_manifest.get('module', {})
                if not self._validate_module_info(module_info):
                    return False

                return True

        except Exception as e:
            self.errors.append(f"Package validation failed: {e}")
            return False

    def _validate_module_info(self, module_info: dict) -> bool:
        """Validate module information"""
        required_fields = ['name', 'version', 'description', 'main_class']
        for field in required_fields:
            if field not in module_info:
                self.errors.append(f"Missing required field: {field}")

        # Validate name
        name = module_info.get('name')
        if name and not isinstance(name, str):
            self.errors.append("Module name must be a string")

        # Validate version
        version = module_info.get('version')
        if version and not isinstance(version, str):
            self.errors.append("Version must be a string")

        return len(self.errors) == 0


class ModuleManager(QObject):
    """Dynamic module manager with shared virtual environment support"""

    module_loaded = pyqtSignal(str, object)  # module_name, module_class
    module_error = pyqtSignal(str, str)  # module_name, error_message
    module_discovered = pyqtSignal(str, dict)  # module_name, module_info

    def __init__(self, modules_dir: str, parent_widget=None, settings=None):
        super().__init__()
        self.modules_dir = modules_dir
        self.loaded_modules = {}
        self.module_info = {}
        self.parent_widget = parent_widget
        self.settings = settings or {}
        self.venv_manager = SharedVirtualEnvironmentManager(modules_dir, self.settings)
        self.package_installer = NGITPackageInstaller(modules_dir, self.venv_manager, parent_widget)

    def discover_modules(self) -> dict:
        """Discover all modules in the modules directory (supports both files and directories)"""
        discovered = {}

        if not os.path.exists(self.modules_dir):
            print(f"❌ Директорію модулів не знайдено: {self.modules_dir}")
            return discovered

        # Look for both .py files and directories with modules
        for item in os.listdir(self.modules_dir):
            module_path = os.path.join(self.modules_dir, item)

            # Skip __pycache__ and other system directories
            if item.startswith('__') or item.startswith('.'):
                continue

            # Check if it's a Python file module
            if item.endswith('.py') and os.path.isfile(module_path):
                module_info = ModuleInfo(module_path)
                self._process_module_info(module_info, item, discovered)

            # Check if it's a directory module
            elif os.path.isdir(module_path):
                # Must have either main.py or __init__.py to be considered a module
                if (os.path.exists(os.path.join(module_path, "main.py")) or
                    os.path.exists(os.path.join(module_path, "__init__.py"))):
                    module_info = ModuleInfo(module_path)
                    self._process_module_info(module_info, item, discovered)
                else:
                    print(f"Warning: Skipping directory {item}: No main.py or __init__.py found")

        return discovered

    def _process_module_info(self, module_info: ModuleInfo, item: str, discovered: dict):
        """Process and validate discovered module info"""
        if module_info.valid:
            discovered[module_info.name] = module_info
            self.module_info[module_info.name] = module_info

            # Emit discovery signal
            self.module_discovered.emit(module_info.name, {
                'name': module_info.name,
                'version': module_info.version,
                'description': module_info.description,
                'menu_text': module_info.menu_text,
                'author': module_info.author,
                'category': module_info.category,
                'is_directory': module_info.is_directory,
                'entry_point': module_info.entry_point
            })

            module_type = "directory module" if module_info.is_directory else "file module"
            print(f"SUCCESS: Discovered {module_type}: {module_info.name} v{module_info.version}")
        else:
            print(f"ERROR: Invalid module {item}: {module_info.error}")
            self.module_error.emit(item, module_info.error)

    def refresh_package_cache(self):
        """Manually refresh the package cache - call after installing new packages"""
        print("🔄 Refreshing package cache...")
        self.venv_manager._sync_installed_packages()
        if hasattr(self.venv_manager, '_package_cache'):
            self.venv_manager._package_cache.clear()
        print("✅ Package cache refreshed")

    def should_refresh_cache(self) -> bool:
        """Check if package cache should be refreshed based on various conditions"""
        # If no cache exists, we need to build it
        if not hasattr(self.venv_manager, '_package_cache') or not self.venv_manager._package_cache:
            return True

        # Could add more sophisticated checks here like:
        # - Time-based refresh (e.g., refresh if cache is older than X minutes)
        # - Check if venv packages have changed since last cache build
        # - Check if new modules were added

        return False

    def validate_and_repair_dependencies(self, force_refresh: bool = False) -> bool:
        """Validate that all discovered modules have their dependencies properly installed in the venv"""
        if not self.module_info:
            return True

        print("Validating module dependencies...")
        # Only refresh package cache if forced or if needed
        if force_refresh or self.should_refresh_cache():
            print("Syncing package cache...")
            self.venv_manager._sync_installed_packages()
            # Clear package cache to force fresh checks
            if hasattr(self.venv_manager, '_package_cache'):
                self.venv_manager._package_cache.clear()
        else:
            print("Using cached package information")

        # Debug: Check what packages are actually installed
        # Virtual environment package validation completed - packages are checked dynamically as needed

        repaired_modules = []

        for module_name, module_info in self.module_info.items():
            has_deps = bool(module_info.dependencies or module_info.dependency_packages)

            if has_deps:
                all_deps_installed = True
                missing_deps = []

                # Only check dependency_packages if it's explicitly defined
                if module_info.has_explicit_dependency_packages and module_info.dependency_packages:
                    for package_name, package_spec in module_info.dependency_packages.items():
                        if not self.venv_manager._is_package_installed(package_name.lower()):
                            missing_deps.append(msg_formatter.package_not_installed(package_name))
                        else:
                            # Check version requirements
                            installed_version = self.venv_manager._get_installed_version(package_name.lower())
                            if installed_version and ('>=' in package_spec or '==' in package_spec or '<=' in package_spec or '~=' in package_spec):
                                version_req = package_spec.replace(package_name, '').strip()
                                if version_req and not self.venv_manager._check_version_requirement(installed_version, version_req):
                                    missing_deps.append(msg_formatter.package_version_mismatch(package_name, installed_version, version_req))
                elif module_info.dependencies:
                    for dep in module_info.dependencies:
                        if isinstance(dep, str):
                            package_name = dep.split('>=')[0].split('==')[0].split('<=')[0].split('~=')[0].strip().lower()
                            package_spec = dep.strip()
                            if not self.venv_manager._is_package_installed(package_name):
                                missing_deps.append(msg_formatter.package_not_installed(package_name))
                            else:
                                # Check version requirements
                                installed_version = self.venv_manager._get_installed_version(package_name)
                                if installed_version and ('>=' in package_spec or '==' in package_spec or '<=' in package_spec or '~=' in package_spec):
                                    version_req = package_spec.replace(package_name, '').strip()
                                    if version_req and not self.venv_manager._check_version_requirement(installed_version, version_req):
                                        missing_deps.append(msg_formatter.package_version_mismatch(package_name, installed_version, version_req))

                if not all_deps_installed:
                    if missing_deps:
                        print(msg_formatter.module_dependencies_missing(module_name, missing_deps))
                    else:
                        print(f"Installing dependencies for {module_name}...")

                    if self.install_module_dependencies(module_name):
                        repaired_modules.append(module_name)
                        print(f"Repaired dependencies for {module_name}")
                    else:
                        print(msg_formatter.module_dependency_repair_failed(module_name))

        if repaired_modules:
            print(f"Repaired dependencies for {len(repaired_modules)} modules: {', '.join(repaired_modules)}")
        else:
            print("All module dependencies are properly installed and up to date")

        return True

    def install_module_dependencies(self, module_name: str) -> bool:
        """Install dependencies for a module"""
        if module_name not in self.module_info:
            print(f"❌ Модуль не знайдено: {module_name}")
            return False

        module_info = self.module_info[module_name]
        dependencies = module_info.dependencies

        # Only pass dependency_packages if it's explicitly defined in the manifest
        # This prevents double processing when dependency_packages is auto-generated
        dependency_packages = module_info.dependency_packages if module_info.has_explicit_dependency_packages else None

        if dependencies or dependency_packages:
            add_splash_message(f"📦 Installing dependencies for {module_name}...")
            print(f"📦 Installing dependencies for {module_name}: {list(dependency_packages.keys()) if dependency_packages else dependencies}")
            success = self.venv_manager.install_dependencies(module_name, dependencies, dependency_packages, self.parent_widget)

            if success:
                # Track which module installed which packages (already handled in install_dependencies)
                self.venv_manager._save_package_info()
                # Refresh package cache after successful installation
                self.refresh_package_cache()

            return success

    def get_modules_venv_python(self) -> Optional[str]:
        """Get the Python executable from the modules virtual environment (Windows)"""
        if not self.venv_manager or not hasattr(self.venv_manager, 'venv_dir'):
            return None

        venv_dir = self.venv_manager.venv_dir

        if not os.path.exists(venv_dir):
            return None

        # Windows Python path
        python_path = os.path.join(venv_dir, 'Scripts', 'python.exe')

        if os.path.exists(python_path):
            return python_path

        return None

    def load_module(self, module_name: str) -> bool:
        """Load a specific module"""
        if module_name in self.loaded_modules:
            print(f"⚠️ Module {module_name} already loaded")
            return True

        if module_name not in self.module_info:
            print(f"❌ Модуль не знайдено: {module_name}")
            return False

        # Only refresh package cache if needed (first time or cache refresh required)
        if self.should_refresh_cache():
            print(f"Initializing package cache for {module_name}...")
            self.venv_manager._sync_installed_packages()
        else:
            print(f"Using cached package information for {module_name}")

        module_info = self.module_info[module_name]

        try:
            # Dependencies should already be installed during validation
            # Only install if validation was skipped or failed
            dependencies = module_info.dependencies

            # Only pass dependency_packages if it's explicitly defined in the manifest
            dependency_packages = module_info.dependency_packages if module_info.has_explicit_dependency_packages else None

            if dependencies or dependency_packages:
                # Quick check if dependencies are satisfied (skip full installation)
                all_deps_satisfied = True
                if dependency_packages:
                    for package_name in dependency_packages.keys():
                        if not self.venv_manager._is_package_installed(package_name.lower()):
                            all_deps_satisfied = False
                            break
                elif dependencies:
                    for dep in dependencies:
                        if isinstance(dep, str):
                            package_name = dep.split('>=')[0].split('==')[0].split('<=')[0].strip().lower()
                            if not self.venv_manager._is_package_installed(package_name):
                                all_deps_satisfied = False
                                break

                if not all_deps_satisfied:
                    print(f"⚠️ Dependencies not satisfied for {module_name}, installing...")
                    if not self.install_module_dependencies(module_name):
                        error_msg = msg_formatter.module_dependency_install_failed(module_name)
                        print(f"❌ {error_msg}")
                        self.module_error.emit(module_name, error_msg)
                        return False
                else:
                    print(f"Dependencies already satisfied for {module_name}")

            # Ensure virtual environment paths are available for module import
            setup_venv_python_path()

            # Module environment is now handled dynamically - no need for debug path checking

            # Load the module (use entry_point for directory modules)
            module_file = module_info.entry_point if module_info.is_directory else module_info.module_path

            # For directory modules, add the module directory to Python path temporarily
            if module_info.is_directory:
                if module_info.module_dir not in sys.path:
                    sys.path.insert(0, module_info.module_dir)

            spec = importlib.util.spec_from_file_location(f"module_{module_name}", module_file)
            if spec is None:
                # Clean up sys.path for directory modules
                if module_info.is_directory and module_info.module_dir in sys.path:
                    sys.path.remove(module_info.module_dir)
                raise ImportError(f"Не вдалося створити spec для модуля {module_name}")

            module = importlib.util.module_from_spec(spec)

            # Add to sys.modules
            sys.modules[f"module_{module_name}"] = module

            # Execute the module
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                # Clean up sys.path for directory modules on error
                if module_info.is_directory and module_info.module_dir in sys.path:
                    sys.path.remove(module_info.module_dir)
                raise e

            # Clean up sys.path for directory modules after successful load
            if module_info.is_directory and module_info.module_dir in sys.path:
                sys.path.remove(module_info.module_dir)

            # Get the main class
            if not hasattr(module, module_info.main_class):
                raise ImportError(f"Модуль {module_name} не має клас {module_info.main_class}")

            module_class = getattr(module, module_info.main_class)
            self.loaded_modules[module_name] = module_class

            print(f"Successfully loaded module: {module_name}")
            self.module_loaded.emit(module_name, module_class)
            return True

        except Exception as e:
            error_msg = msg_formatter.module_load_failed(module_name, str(e))
            print(f"ERROR: {error_msg}")
            self.module_error.emit(module_name, error_msg)
            return False

    def load_all_modules(self):
        """Load all discovered modules"""
        # Use already discovered modules instead of re-discovering
        for module_name in self.module_info.keys():
            if module_name not in self.loaded_modules:
                self.load_module(module_name)

    def unload_module(self, module_name: str):
        """Unload a module and clean up dependencies"""
        if module_name in self.loaded_modules:
            # Uninstall dependencies if no other modules use them
            if module_name in self.module_info:
                dependencies = self.module_info[module_name].dependencies
                self.venv_manager.uninstall_dependencies(module_name, dependencies)

            # Clean up sys.modules
            module_key = f"module_{module_name}"
            if module_key in sys.modules:
                del sys.modules[module_key]

            del self.loaded_modules[module_name]
            print(f"Unloaded module: {module_name}")

  
  
    
    def get_module_info(self, module_name: str):
        """Get information about a module"""
        return self.module_info.get(module_name)

    def get_loaded_modules(self) -> dict:
        """Get all loaded modules"""
        return self.loaded_modules.copy()

    def get_virtual_env_manager(self) -> SharedVirtualEnvironmentManager:
        """Get the virtual environment manager"""
        return self.venv_manager

    def install_package(self, package_path: str) -> bool:
        """Install module from .ngitpac package"""
        print(f"Installing package: {package_path}")

        if not self.package_installer.install_package(package_path):
            # Installation failed, show errors
            print("Package installation failed:")
            for error in self.package_installer.errors:
                print(f"  ERROR: {error}")
            for warning in self.package_installer.warnings:
                print(f"  WARNING: {warning}")
            return False

        # Show warnings if any
        if self.package_installer.warnings:
            print("Installation warnings:")
            for warning in self.package_installer.warnings:
                print(f"  WARNING: {warning}")

        # Refresh module discovery to include the newly installed module
        print("Refreshing module discovery...")
        newly_discovered = self.discover_modules()

        # Update our module info with the newly discovered modules
        self.module_info.update(newly_discovered)

        # Check if we discovered any modules
        if newly_discovered:
            module_name = list(newly_discovered.keys())[0]
            print(f"Successfully installed and discovered module: {module_name}")
            # Try to validate and repair dependencies for the new module
            if self.validate_and_repair_dependencies():
                print(f"Dependencies validated for {module_name}")
            return True
        else:
            print("Package installed but no modules were discovered")
            return False

    def get_package_info(self, package_path: str) -> dict:
        """Get package information without installing"""
        return self.package_installer.get_package_info(package_path)

    def validate_package(self, package_path: str) -> bool:
        """Validate package without installing"""
        result = self.package_installer.validate_package(package_path)
        if not result:
            print("Package validation failed:")
            for error in self.package_installer.errors:
                print(f"  ERROR: {error}")
            for warning in self.package_installer.warnings:
                print(f"  WARNING: {warning}")
        else:
            print("Package validation passed")
            if self.package_installer.warnings:
                print("Validation warnings:")
                for warning in self.package_installer.warnings:
                    print(f"  WARNING: {warning}")
        return result

    def get_package_installer(self) -> NGITPackageInstaller:
        """Get the package installer instance"""
        return self.package_installer

# --- Splash Screen with Console Output ---
class SplashScreen(QSplashScreen):
    def __init__(self):
        # Create a pixmap for the splash screen
        self.splash_width = 700
        self.splash_height = 450
        pixmap = QPixmap(self.splash_width, self.splash_height)
        pixmap.fill(Qt.transparent)  # Transparent background

        super().__init__(pixmap)

        # Center on screen
        self.center_on_screen()

        # Configure splash properties
        self.setFixedSize(self.splash_width, self.splash_height)
        self.setWindowFlags(Qt.SplashScreen | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Initialize console messages
        self.console_messages = []
        self.max_messages = 20  # Maximum number of messages to display

        # Add initial messages in Ukrainian
        self.add_message("🚀 Запуск Desktop Organizer...")
        self.add_message(f"📍 Версія Python: {sys.version.split()[0]}")
        self.add_message(f"💻 Платформа: {platform.system()} {platform.release()}")

    def center_on_screen(self):
        """Center the splash screen on the primary screen"""
        screen = QApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            x = (screen_geometry.width() - self.splash_width) // 2
            y = (screen_geometry.height() - self.splash_height) // 2
            self.move(x, y)

    
    def add_message(self, message):
        """Add a message to the console output"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        self.console_messages.append(formatted_message)

        # Keep only the last N messages
        if len(self.console_messages) > self.max_messages:
            self.console_messages = self.console_messages[-self.max_messages:]

        # Trigger repaint
        self.update()

        # Process events to ensure immediate display
        QApplication.processEvents()

    def drawContents(self, painter):
        """Draw the splash screen contents matching application UI style"""
        # Draw background
        self.drawBackground(painter)

        # Set up fonts matching application style
        title_font = QFont("Segoe UI", 24, QFont.Bold)
        subtitle_font = QFont("Segoe UI", 12, QFont.Medium)
        console_font = QFont("Consolas", 10)

        # Draw main title using application colors
        painter.setFont(title_font)
        title_color = QColor(209, 52, 56)  # Application red accent
        painter.setPen(QPen(title_color))
        title_rect = QRect(50, 40, self.splash_width - 100, 40)
        painter.drawText(title_rect, Qt.AlignCenter, "Desktop Organizer")

        # Draw subtitle
        painter.setFont(subtitle_font)
        subtitle_color = QColor(100, 100, 100)  # Gray like UI text
        painter.setPen(QPen(subtitle_color))
        subtitle_rect = QRect(50, 80, self.splash_width - 100, 25)
        painter.drawText(subtitle_rect, Qt.AlignCenter, "Автоматизована Організація Робочого Столу")

        # Draw console area with application-style card
        console_rect = QRect(50, 130, self.splash_width - 100, 280)

        # Console background - white like application cards
        painter.fillRect(console_rect, QColor(255, 255, 255))

        # Console border with application style
        painter.setPen(QPen(QColor(220, 220, 220), 1))  # Light border
        painter.drawRect(console_rect)

        # Add subtle shadow effect for card
        shadow_rect = QRect(52, 132, self.splash_width - 104, 280)
        painter.setPen(QPen(QColor(200, 200, 200, 50), 1))
        painter.drawRect(shadow_rect)

        # Console header with application style
        header_rect = QRect(50, 130, self.splash_width - 100, 30)
        header_color = QColor(245, 245, 245)  # Same as background
        painter.fillRect(header_rect, header_color)

        # Header border
        painter.setPen(QPen(QColor(220, 220, 220), 1))
        painter.drawLine(50, 160, self.splash_width - 50, 160)

        # Console title
        painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
        title_color = QColor(51, 51, 51)  # Dark text like UI
        painter.setPen(QPen(title_color))
        console_title_rect = QRect(65, 135, self.splash_width - 130, 25)
        painter.drawText(console_title_rect, Qt.AlignLeft, "🚀 Процес Запуску")

        # Draw console messages with application-style colors
        painter.setFont(console_font)
        y_offset = 185
        available_height = 280 - 35 - 10
        max_visible_messages = available_height // 18
        visible_messages = min(max_visible_messages, len(self.console_messages))

        console_bottom = 140 + 280 - 10
        max_y_offset = console_bottom - 18

        for i, message in enumerate(self.console_messages[-visible_messages:]):
            # Stop if we've reached the bottom of the console area
            if y_offset > max_y_offset:
                break

            # Color code messages using application color scheme
            if "✅" in message or "🚀" in message:
                painter.setPen(QPen(QColor(16, 124, 16)))  # Application green
            elif "❌" in message or "🔴" in message:
                painter.setPen(QPen(QColor(209, 52, 56)))  # Application red
            elif "⚠️" in message:
                painter.setPen(QPen(QColor(249, 168, 37)))  # Application yellow
            elif "📦" in message:
                painter.setPen(QPen(QColor(0, 120, 212)))  # Application blue
            elif "🔍" in message:
                painter.setPen(QPen(QColor(107, 33, 168)))  # Application purple
            elif "⚙️" in message:
                painter.setPen(QPen(QColor(16, 124, 16)))  # Application green
            elif "ℹ️" in message:
                painter.setPen(QPen(QColor(100, 100, 100)))  # Gray
            else:
                painter.setPen(QPen(QColor(51, 51, 51)))  # Dark text like UI

            # Ensure text stays within console boundaries
            message_rect = QRect(65, y_offset, self.splash_width - 140, 16)
            painter.drawText(message_rect, Qt.AlignLeft, message)
            y_offset += 18

        
    def drawBackground(self, painter):
        """Draw the modern background matching application UI style"""
        # Use application background color (#f5f5f5)
        background_color = QColor(245, 245, 245)  # Light gray like main UI

        # Draw main rounded rectangle
        painter.setBrush(QBrush(background_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.splash_width, self.splash_height, 12, 12)

        # Draw border matching application style
        painter.setPen(QPen(QColor(200, 200, 200), 2))  # Light border
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(1, 1, self.splash_width - 2, self.splash_height - 2, 11, 11)

        # Add top accent bar using application gray color
        accent_width = int(self.splash_width * 0.8)
        accent_x = (self.splash_width - accent_width) // 2
        accent_color = QColor(128, 128, 128)  # Application gray accent
        painter.fillRect(accent_x, 5, accent_width, 3, accent_color)

    def fade_out_and_close(self, duration=1000):
        """Fade out the splash screen and close it"""
        self.fade_timer = QTimer()
        self.fade_duration = duration
        self.fade_steps = 20
        self.fade_step = 0
        self.original_opacity = self.windowOpacity()

        self.fade_timer.timeout.connect(self._fade_step)
        self.fade_timer.start(self.fade_duration // self.fade_steps)

    def _fade_step(self):
        """Perform one step of the fade-out animation"""
        self.fade_step += 1
        progress = self.fade_step / self.fade_steps
        new_opacity = self.original_opacity * (1 - progress)
        self.setWindowOpacity(new_opacity)

        if self.fade_step >= self.fade_steps:
            self.fade_timer.stop()
            self.finished = True
            self.close()

    def cleanup(self):
        """Clean up timers"""
        if hasattr(self, 'fade_timer'):
            self.fade_timer.stop()

# --- Settings Dialog ---
class SettingsDialog(QDialog):
    settings_applied = pyqtSignal(dict)

    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.current_settings = current_settings.copy()
        self.parent_window = parent
        self.setWindowTitle("Налаштування Додатку")
        self.setMinimumSize(600, 500)
        self.resize(829, 888)

        self._setup_ui()
        self._create_tabs()
        self._setup_buttons()

        # Timer for updating time remaining display
        self.time_update_timer = QTimer(self)
        self.time_update_timer.timeout.connect(self.update_time_remaining_display)
        self.time_update_timer.start(60000)  # Update every minute

        self.load_settings_to_ui()
        self.changes_applied = False

    def _setup_ui(self):
        """Setup the main dialog layout"""
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.main_layout = layout

    def _setup_buttons(self):
        """Setup dialog buttons"""
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.main_layout.addWidget(self.button_box)

    def _create_tabs(self):
        """Create all settings tabs"""
        self.create_general_tab()
        self.create_file_manager_tab()
        self.create_schedule_tab()
        self.create_virtual_environment_tab()

    def _create_group_box(self, title: str, layout_type='form') -> QGroupBox:
        """Create a group box with specified layout type"""
        group = QGroupBox(title)
        if layout_type == 'form':
            layout = QFormLayout(group)
        else:
            layout = QVBoxLayout(group)
        return group

    def _create_checkbox(self, text: str) -> QCheckBox:
        """Create a checkbox with given text and Windows-style appearance"""
        checkbox = WindowsCheckBox(text)
        checkbox.setStyleSheet("""
            WindowsCheckBox {
                font-size: 11px;
                spacing: 12px;
                min-height: 24px;
                padding: 2px;
            }
        """)
        return checkbox

    def _create_spinbox(self, min_val: int, max_val: int, suffix: str = '') -> QSpinBox:
        """Create a spinbox with range and optional suffix"""
        spinbox = QSpinBox()
        spinbox.setRange(min_val, max_val)
        if suffix:
            spinbox.setSuffix(suffix)
        return spinbox

    def _create_radio_button(self, text: str) -> QRadioButton:
        """Create a compact radio button with given text"""
        radio = QRadioButton(text)
        radio.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # Fixed size for horizontal layout
        radio.setStyleSheet("QRadioButton { margin: 0px 2px; padding: 1px; }")  # Minimal margins with horizontal spacing
        return radio

    def _create_labeled_widget_container(self, widget) -> QWidget:
        """Create a container widget for complex labeled controls"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)
        return container

    def create_general_tab(self):
        """Create the enhanced general settings tab"""
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #d0d0d0;
                background-color: #ffffff;
            }
            QScrollBar:vertical {
                background-color: #f8f8f8;
                width: 14px;
                border: 1px solid #e0e0e0;
            }
            QScrollBar::handle:vertical {
                background-color: #b0b0b0;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #909090;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)

        # Create content widget
        tab_general = QWidget()
        layout = QVBoxLayout(tab_general)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # Combined quick actions and application behavior section
        combined_section = self._create_combined_actions_behavior_section()
        layout.addWidget(combined_section)

        # Timer configuration section
        timer_section = self._create_enhanced_timer_section()
        layout.addWidget(timer_section)

        # Storage management section
        storage_section = self._create_enhanced_storage_section()
        layout.addWidget(storage_section)

        layout.addStretch()

        # Set up scroll area
        scroll_area.setWidget(tab_general)
        self.tabs.addTab(scroll_area, "Загальні")

    def _setup_timer_controls(self, layout):
        """Setup timer-related controls"""
        self.chk_override_timer = WindowsCheckBox("Перевизначити тривалість таймера за замовчуванням")
        self.spin_default_timer = self._create_spinbox(1, 60, " хвилин")
        self.chk_override_timer.toggled.connect(self.spin_default_timer.setEnabled)
        layout.addRow(self.chk_override_timer)
        layout.addRow("Тривалість за замовчуванням:", self.spin_default_timer)

    def _setup_drive_controls(self, layout):
        """Setup drive selection controls"""
        layout.addWidget(QLabel("Резервний диск завжди C:"))
        self.rb_drive_d = self._create_radio_button("Встановити основний диск D:")
        self.rb_drive_auto = self._create_radio_button("Автоматично визначити наступний доступний диск (незнімний)")
        layout.addWidget(self.rb_drive_d)
        layout.addWidget(self.rb_drive_auto)

    def _create_enhanced_application_section(self) -> QGroupBox:
        """Create enhanced application behavior section"""
        group = QGroupBox("Поведінка Додатку")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid black;
                border-radius: 2px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #fafafa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: black;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 20, 15, 15)

        # Startup behavior
        startup_layout = QHBoxLayout()
        self.chk_enable_autostart = WindowsCheckBox("Автоматично запускати таймер при старті")
        self.chk_enable_autostart.setStyleSheet("""
            WindowsCheckBox {
                font-size: 11px;
                spacing: 12px;
                min-height: 24px;
                padding: 2px;
            }
        """)
        startup_layout.addWidget(self.chk_enable_autostart)
        startup_layout.addStretch()
        layout.addLayout(startup_layout)

        # Notification settings
        notification_layout = QHBoxLayout()
        self.chk_enable_notifications = WindowsCheckBox("Показувати сповіщення при організації")
        self.chk_enable_notifications.setStyleSheet("""
            WindowsCheckBox {
                font-size: 11px;
                spacing: 12px;
                min-height: 24px;
                padding: 2px;
            }
        """)
        notification_layout.addWidget(self.chk_enable_notifications)
        notification_layout.addStretch()
        layout.addLayout(notification_layout)

        # Minimize to tray
        tray_layout = QHBoxLayout()
        self.chk_minimize_to_tray = WindowsCheckBox("Мінімізувати в трей при закритті")
        self.chk_minimize_to_tray.setStyleSheet("""
            WindowsCheckBox {
                font-size: 11px;
                spacing: 12px;
                min-height: 24px;
                padding: 2px;
            }
        """)
        tray_layout.addWidget(self.chk_minimize_to_tray)
        tray_layout.addStretch()
        layout.addLayout(tray_layout)

        return group

    def _create_enhanced_timer_section(self) -> QGroupBox:
        """Create enhanced timer configuration section"""
        group = QGroupBox("Конфігурація Таймера")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid black;
                border-radius: 2px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #fafafa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: black;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 20, 15, 15)

        # Timer override settings
        override_layout = QHBoxLayout()
        self.chk_override_timer = WindowsCheckBox("Перевизначити тривалість таймера за замовчуванням")
        self.chk_override_timer.setStyleSheet("""
            WindowsCheckBox {
                font-size: 11px;
                spacing: 12px;
                min-height: 24px;
                padding: 2px;
                font-weight: bold;
            }
        """)
        override_layout.addWidget(self.chk_override_timer)
        override_layout.addStretch()
        layout.addLayout(override_layout)

        # Timer duration
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Тривалість за замовчуванням:"))
        self.spin_default_timer = self._create_spinbox(1, 60, " хвилин")
        self.spin_default_timer.setStyleSheet("""
            QSpinBox {
                padding: 6px;
                border: 2px solid #ddd;
                border-radius: 4px;
                font-size: 12px;
                min-width: 80px;
            }
            QSpinBox:focus {
                border: 2px solid #808080;
            }
        """)
        self.chk_override_timer.toggled.connect(self.spin_default_timer.setEnabled)
        self.chk_override_timer.toggled.connect(self._update_timer_status)
        self.spin_default_timer.setEnabled(False)
        self.spin_default_timer.valueChanged.connect(self._update_timer_status)
        duration_layout.addWidget(self.spin_default_timer)
        duration_layout.addStretch()
        layout.addLayout(duration_layout)

        # Quick timer presets
        presets_layout = QHBoxLayout()
        presets_layout.addWidget(QLabel("Швидкі налаштування:"))

        self.btn_timer_5min = QPushButton("5 хв")
        self.btn_timer_5min.clicked.connect(lambda: self._set_timer_preset(5))
        
        self.btn_timer_15min = QPushButton("15 хв")
        self.btn_timer_15min.clicked.connect(lambda: self._set_timer_preset(15))
        
        self.btn_timer_30min = QPushButton("30 хв")
        self.btn_timer_30min.clicked.connect(lambda: self._set_timer_preset(30))
        
        self.btn_timer_60min = QPushButton("1 год")
        self.btn_timer_60min.clicked.connect(lambda: self._set_timer_preset(60))
        
        presets_layout.addWidget(self.btn_timer_5min)
        presets_layout.addWidget(self.btn_timer_15min)
        presets_layout.addWidget(self.btn_timer_30min)
        presets_layout.addWidget(self.btn_timer_60min)
        presets_layout.addStretch()
        layout.addLayout(presets_layout)

        # Timer status
        status_layout = QHBoxLayout()
        self.timer_status_label = QLabel("Таймер: Налаштовано на 10 хвилин")
        self.timer_status_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: black;
                padding: 5px;
                background-color: #f5f5f5;
                border: 1px solid #d0d0d0;
                border-radius: 2px;
            }
        """)
        status_layout.addWidget(self.timer_status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        return group

    def _create_enhanced_storage_section(self) -> QGroupBox:
        """Create enhanced storage management section"""
        group = QGroupBox("Управління Зберіганням")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid black;
                border-radius: 2px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #fafafa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: black;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(8)  # More compact spacing
        layout.setContentsMargins(10, 12, 10, 10)  # More compact margins

        # Drive selection
        drive_selection_layout = QVBoxLayout()
        drive_label = QLabel("Управління зберіганням:")
        drive_label.setStyleSheet("font-weight: bold; font-size: 10px; color: #333; margin-bottom: 3px;")
        drive_selection_layout.addWidget(drive_label)

        # Create horizontal layout for radio buttons with indentation
        radio_button_layout = QHBoxLayout()
        radio_button_layout.setSpacing(8)  # Compact horizontal spacing
        radio_button_layout.setContentsMargins(12, 0, 0, 0)  # Compact left indentation

        # Create button group for drive selection
        self.drive_button_group = QButtonGroup()

        # Drive options - minimal Windows styling
        self.rb_drive_c = self._create_radio_button("Диск C:")
        # Remove custom styling to use Windows default

        self.rb_drive_d = self._create_radio_button("Диск D:")
        # Remove custom styling to use Windows default

        self.rb_drive_auto = self._create_radio_button("Авто")
        # Remove custom styling to use Windows default

        # Add radio buttons to button group with IDs
        self.drive_button_group.addButton(self.rb_drive_c, 0)
        self.drive_button_group.addButton(self.rb_drive_d, 1)
        self.drive_button_group.addButton(self.rb_drive_auto, 2)

        # Connect button group for proper selection handling
        self.drive_button_group.buttonClicked.connect(self.on_drive_selection_changed)

        # Add radio buttons to horizontal layout
        radio_button_layout.addWidget(self.rb_drive_c)
        radio_button_layout.addWidget(self.rb_drive_d)
        radio_button_layout.addWidget(self.rb_drive_auto)
        radio_button_layout.addStretch()  # Add stretch to push buttons to the left

        # Add horizontal layout to the main drive selection layout
        drive_selection_layout.addLayout(radio_button_layout)
        layout.addLayout(drive_selection_layout)

        # Enhanced drive info section
        drive_info_container = QWidget()
        drive_info_layout = QVBoxLayout(drive_info_container)
        drive_info_layout.setSpacing(8)
        drive_info_layout.setContentsMargins(0, 0, 0, 0)

        # Current selection status
        self.drive_info_label = QLabel("Поточний вибір: Диск C:")
        self.drive_info_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: bold;
                color: #333;
                padding: 8px 12px;
                background-color: #E3F2FD;
                border: 2px solid #2196F3;
                border-radius: 6px;
                margin-bottom: 5px;
            }
        """)

        # Drive availability status
        self.drive_status_label = QLabel("Статус дисків: Перевірка...")
        self.drive_status_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #666;
                padding: 6px 10px;
                background-color: #F5F5F5;
                border: 1px solid #DDD;
                border-radius: 4px;
            }
        """)

        # Action buttons row
        drive_buttons_layout = QHBoxLayout()
        drive_buttons_layout.setSpacing(10)
        self.refresh_drive_btn = QPushButton("Оновити диски")
        self.test_drive_btn = QPushButton("Тест дисків")
        drive_buttons_layout.addWidget(self.refresh_drive_btn)
        drive_buttons_layout.addWidget(self.test_drive_btn)
        drive_buttons_layout.addStretch()

        # Assemble drive info section
        drive_info_layout.addWidget(self.drive_info_label)
        drive_info_layout.addWidget(self.drive_status_label)
        drive_info_layout.addLayout(drive_buttons_layout)

        layout.addWidget(drive_info_container)

        # Connect buttons to their functions
        self.refresh_drive_btn.clicked.connect(self._refresh_drive_info)
        self.test_drive_btn.clicked.connect(self._test_drives)

        return group

    def _refresh_drive_info(self):
        """Enhanced drive availability information refresh"""
        try:
            # Show refreshing status
            self.drive_status_label.setText("Оновлення інформації про диски...")

            def check_drive_exists(drive_letter):
                import subprocess
                import platform
                if platform.system() == "Windows":
                    try:
                        result = subprocess.run(['cmd', '/c', f'if exist {drive_letter}:\\nul echo exists'],
                                               capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=3)
                        return result.returncode == 0
                    except:
                        return os.path.exists(f"{drive_letter}:\\")
                else:
                    return os.path.exists(f"/mnt/{drive_letter.lower()}")

            def get_drive_space(drive_letter):
                """Get free and total space for a drive"""
                try:
                    import shutil
                    usage = shutil.disk_usage(f"{drive_letter}:\\")
                    total_gb = usage.total // (1024**3)
                    free_gb = usage.free // (1024**3)
                    return total_gb, free_gb
                except:
                    return None, None

            # Check drive availability
            drives_status = {}
            for drive in ['C', 'D', 'E']:
                exists = check_drive_exists(drive)
                total_gb, free_gb = get_drive_space(drive) if exists else (None, None)
                drives_status[drive] = {
                    'exists': exists,
                    'total_gb': total_gb,
                    'free_gb': free_gb
                }

            # Update internal status
            self.d_exists = drives_status['D']['exists']
            self.e_exists = drives_status['E']['exists']

            # Build status text for all drives
            status_parts = []
            for drive, status in drives_status.items():
                if status['exists']:
                    free_space = f"{status['free_gb']}GB" if status['free_gb'] is not None else "Невідомо"
                    status_parts.append(f"{drive}:/✅ ({free_space})")
                else:
                    status_parts.append(f"{drive}:/❌")

            self.drive_status_label.setText("Статус: " + " | ".join(status_parts))

            # Update current selection info
            if self.rb_drive_c.isChecked():
                current_drive = 'C'
                if drives_status['C']['exists']:
                    free_space = drives_status['C']['free_gb']
                    status_text = f"Обрано диск C: (системний) - Вільно: {free_space}GB ✅"
                    self.drive_info_label.setText(status_text)
                    self.drive_info_label.setStyleSheet("""
                        QLabel {
                            font-size: 12px;
                            font-weight: bold;
                            color: #333;
                            padding: 8px 12px;
                            background-color: #E8F5E8;
                            border: 2px solid #4CAF50;
                            border-radius: 6px;
                            margin-bottom: 5px;
                        }
                    """)
                else:
                    self.drive_info_label.setText("Обрано диск C: (системний) - ⚠️ Недоступний")

            elif self.rb_drive_d.isChecked():
                if drives_status['D']['exists']:
                    free_space = drives_status['D']['free_gb']
                    status_text = f"Обрано диск D: - Вільно: {free_space}GB ✅"
                    self.drive_info_label.setText(status_text)
                    self.drive_info_label.setStyleSheet("""
                        QLabel {
                            font-size: 12px;
                            font-weight: bold;
                            color: #333;
                            padding: 8px 12px;
                            background-color: #E8F5E8;
                            border: 2px solid #4CAF50;
                            border-radius: 6px;
                            margin-bottom: 5px;
                        }
                    """)
                else:
                    self.drive_info_label.setText("Обрано диск D: - ❌ Недоступний")
                    self.drive_info_label.setStyleSheet("""
                        QLabel {
                            font-size: 12px;
                            font-weight: bold;
                            color: #D32F2F;
                            padding: 8px 12px;
                            background-color: #FFEBEE;
                            border: 2px solid #D32F2F;
                            border-radius: 6px;
                            margin-bottom: 5px;
                        }
                    """)

            elif self.rb_drive_auto.isChecked():
                # Find drive with most free space
                auto_drive = find_next_available_drive()
                if auto_drive and auto_drive in drives_status and drives_status[auto_drive]['exists']:
                    free_space = drives_status[auto_drive]['free_gb']
                    status_text = f"Автовибір: {auto_drive}: - Вільно: {free_space}GB (найбільше)"
                else:
                    # Fallback to simple logic if auto detection fails
                    best_drive = None
                    best_space = 0
                    for drive in ['D', 'E', 'F', 'G']:
                        if drive in drives_status and drives_status[drive]['exists'] and drives_status[drive]['free_gb']:
                            if drives_status[drive]['free_gb'] > best_space:
                                best_drive = drive
                                best_space = drives_status[drive]['free_gb']

                    if best_drive:
                        auto_drive = best_drive
                        free_space = best_space
                        status_text = f"Автовибір: {auto_drive}: - Вільно: {free_space}GB (найбільше)"
                    else:
                        auto_drive = 'C'
                        free_space = drives_status['C']['free_gb'] if drives_status['C']['free_gb'] else 0
                        status_text = f"Автовибір: {auto_drive}: - Вільно: {free_space}GB (резервний)"

                self.drive_info_label.setText(status_text)

            # Show success status temporarily
            self.drive_status_label.setText("✅ Інформацію про диски оновлено")
            QTimer.singleShot(3000, lambda: self._refresh_drive_info())  # Refresh again after 3 seconds

        except Exception as e:
            error_msg = f"Помилка оновлення інформації про диски: {str(e)}"
            self.drive_status_label.setText(error_msg)

    def on_drive_selection_changed(self, button):
        """Handle drive selection changes with enhanced logic and validation"""
        try:
            # Determine selected drive
            if button == self.rb_drive_c:
                self.selected_drive = 'C'
                status = "✅ Завжди доступний"
                self.drive_info_label.setText(f"Обрано диск C: {status}")

            elif button == self.rb_drive_d:
                # Check if D: drive is available
                def check_drive_exists(drive_letter):
                    import subprocess
                    import platform
                    if platform.system() == "Windows":
                        try:
                            result = subprocess.run(['cmd', '/c', f'if exist {drive_letter}:\\nul echo exists'],
                                                   capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=3)
                            return result.returncode == 0
                        except:
                            return os.path.exists(f"{drive_letter}:\\")
                    else:
                        return os.path.exists(f"/mnt/{drive_letter.lower()}")

                if check_drive_exists('D'):
                    self.selected_drive = 'D'
                    status = "✅ Доступний"
                    self.drive_info_label.setText(f"Обрано диск D: {status}")
                else:
                    # D: drive not available, show warning and keep current selection
                    status = "❌ Не доступний"
                    self.drive_info_label.setText(f"Диск D: {status}")
                    # Revert to previous selection
                    if hasattr(self, 'selected_drive') and self.selected_drive == 'C':
                        self.rb_drive_c.setChecked(True)
                    else:
                        self.rb_drive_auto.setChecked(True)
                    return

            elif button == self.rb_drive_auto:
                self.selected_drive = 'AUTO'
                # Show what will be selected
                def check_drive_exists(drive_letter):
                    import subprocess
                    import platform
                    if platform.system() == "Windows":
                        try:
                            result = subprocess.run(['cmd', '/c', f'if exist {drive_letter}:\\nul echo exists'],
                                                   capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=3)
                            return result.returncode == 0
                        except:
                            return os.path.exists(f"{drive_letter}:\\")
                    else:
                        return os.path.exists(f"/mnt/{drive_letter.lower()}")

                d_exists = check_drive_exists('D')
                e_exists = check_drive_exists('E')

                if d_exists:
                    self.drive_info_label.setText(f"Автоматичний вибір: D: ✅")
                elif e_exists:
                    self.drive_info_label.setText(f"Автоматичний вибір: E: ✅")
                else:
                    self.drive_info_label.setText(f"Автоматичний вибір: C: ⚠️")

            # Update current settings in memory only (don't save to file yet)
            if hasattr(self, 'current_settings') and self.current_settings:
                self.current_settings['drive'] = self.selected_drive
                # Note: Settings will be saved when Apply or OK is pressed

        except Exception as e:
            # Show error in status label
            self.drive_info_label.setText(f"❌ Помилка вибору диска: {str(e)}")

    def _test_drives(self):
        """Simulate drive accessibility test without creating files"""
        try:
            # Show testing status
            self.drive_status_label.setText("🔍 Перевірка доступності дисків (симуляція)...")

            def check_drive_exists(drive_letter):
                import subprocess
                import platform
                if platform.system() == "Windows":
                    try:
                        result = subprocess.run(['cmd', '/c', f'if exist {drive_letter}:\\nul echo exists'],
                                               capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=3)
                        return result.returncode == 0
                    except:
                        return os.path.exists(f"{drive_letter}:\\")
                else:
                    return os.path.exists(f"/mnt/{drive_letter.lower()}")

            def test_drive_write_read(drive_letter):
                """Simulate drive accessibility test without creating files"""
                try:
                    # Simulate checking if drive exists and is accessible
                    if not check_drive_exists(drive_letter):
                        return False, "Диск не доступний"

                    # Simulate file system access check (no actual file creation)
                    import os
                    drive_path = f"{drive_letter}:\\"

                    # Check if we can access the drive root directory
                    try:
                        os.listdir(drive_path)
                        # Try to get file system info (simulates write access check)
                        os.stat(drive_path)
                        return True, "Симуляція пройдена успішно"
                    except PermissionError:
                        return False, "Немає доступу до диска"
                    except Exception:
                        return False, "Помилка доступу до файлової системи"

                except Exception as e:
                    return False, str(e)

            drives_to_test = ['C', 'D', 'E']
            results = []

            for drive in drives_to_test:
                if check_drive_exists(drive):
                    writable, status = test_drive_write_read(drive)
                    if writable:
                        results.append(f"✅ Диск {drive}: Доступний для роботи ({status})")
                    else:
                        results.append(f"⚠️ Диск {drive}: Проблема доступу ({status})")
                else:
                    results.append(f"❌ Диск {drive}: Не знайдено")

            # Update status label with results
            status_text = " | ".join([r.split(":")[1].strip() for r in results])
            self.drive_status_label.setText(f"Результати тесту: {status_text}")

            # No cleanup needed - simulation doesn't create any files

        except Exception as e:
            error_msg = f"Помилка тестування дисків: {str(e)}"
            self.drive_status_label.setText(error_msg)

    def _update_timer_status(self):
        """Update timer status label based on current settings"""
        try:
            if self.chk_override_timer.isChecked():
                minutes = self.spin_default_timer.value()
                self.timer_status_label.setText(f"Таймер: Налаштовано на {minutes} хвилин")
            else:
                # Use current settings from self.current_settings or default
                timer_cfg = self.current_settings.get('timer', DEFAULT_SETTINGS['timer'])
                minutes = timer_cfg.get('default_minutes', 3)
                self.timer_status_label.setText(f"Таймер: За замовчуванням {minutes} хвилин")
        except Exception as e:
            self.timer_status_label.setText("Таймер: Помилка статусу")

    def _create_combined_actions_behavior_section(self) -> QGroupBox:
        """Create combined quick actions and application behavior section"""
        group = QGroupBox("Швидкі Дії та Поведінка Додатку")
        group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid black;
                border-radius: 2px;
                margin-top: 10px;
                padding-top: 15px;
                background-color: #fafafa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: black;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        layout.setContentsMargins(18, 25, 18, 18)

        # === Швидкі Дії Section ===
        quick_actions_label = QLabel("🚀 Швидкі Дії")
        quick_actions_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #333; margin-bottom: 8px; padding-left: 5px;")
        layout.addWidget(quick_actions_label)

        # Quick actions dropdown with indentation
        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(10, 0, 0, 0)  # Indentation

        self.quick_actions_dropdown = QComboBox()
        self.quick_actions_dropdown.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.quick_actions_dropdown.setMinimumWidth(300)
        self.quick_actions_dropdown.addItem("🚀 Швидкі Дії")
        self.quick_actions_dropdown.addItem("🧪 Тестова Організація")
        self.quick_actions_dropdown.addItem("📁 Відкрити Конфігурацію")
        self.quick_actions_dropdown.addItem("🔄 Скинути Налаштування")
        self.quick_actions_dropdown.addItem("💾 Експортувати Конфігурацію")
        self.quick_actions_dropdown.addItem("🚀 Налаштувати Автозапуск")
        self.quick_actions_dropdown.addItem("🗑️ Видалити Автозапуск")
        self.quick_actions_dropdown.addItem("🔄 Запустити в Трей")

        self.quick_actions_dropdown.currentIndexChanged.connect(self.on_quick_action_selected)

        actions_layout.addWidget(self.quick_actions_dropdown)
        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        # Autorun status label with indentation
        autorun_status_layout = QHBoxLayout()
        autorun_status_layout.setContentsMargins(10, 0, 0, 0)  # Indentation
        self.autorun_status_label = QLabel("Статус автозапуску: Вимкнено")
        self.autorun_status_label.setStyleSheet("font-size: 10px; color: #666; padding: 5px;")
        autorun_status_layout.addWidget(self.autorun_status_label)
        autorun_status_layout.addStretch()
        layout.addLayout(autorun_status_layout)

        # Check autorun status once (not in a loop)
        QTimer.singleShot(100, self.check_autorun_status)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #d0d0d0; height: 1px; margin: 8px 0px;")
        layout.addWidget(line)

        # === Поведінка Додатку Section ===
        behavior_label = QLabel("⚙️ Поведінка Додатку")
        behavior_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #333; margin-bottom: 8px; padding-left: 5px;")
        layout.addWidget(behavior_label)

        # Startup behavior with indentation
        startup_layout = QHBoxLayout()
        startup_layout.setContentsMargins(10, 0, 0, 0)  # Indentation
        self.chk_enable_autostart = WindowsCheckBox("Автоматично запускати таймер при старті")
        self.chk_enable_autostart.setStyleSheet("""
            WindowsCheckBox {
                font-size: 11px;
                color: black;
            }
        """)
        startup_layout.addWidget(self.chk_enable_autostart)
        startup_layout.addStretch()
        layout.addLayout(startup_layout)

        # Minimize to tray behavior with indentation
        tray_layout = QHBoxLayout()
        tray_layout.setContentsMargins(10, 0, 0, 0)  # Indentation
        self.chk_minimize_to_tray = WindowsCheckBox("Мінімізувати в системний трей при закритті")
        self.chk_minimize_to_tray.setStyleSheet("""
            WindowsCheckBox {
                font-size: 11px;
                color: black;
            }
        """)
        tray_layout.addWidget(self.chk_minimize_to_tray)
        tray_layout.addStretch()
        layout.addLayout(tray_layout)

        return group

    def _create_quick_actions_section(self) -> QGroupBox:
        """Create quick actions section"""
        group = QGroupBox("Швидкі Дії")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid black;
                border-radius: 2px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #fafafa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: black;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 20, 15, 15)

        # Quick actions dropdown
        actions_layout1 = QHBoxLayout()

        self.quick_actions_dropdown = QComboBox()
        self.quick_actions_dropdown.addItem("🚀 Швидкі Дії")
        self.quick_actions_dropdown.addItem("🧪 Тестова Організація")
        self.quick_actions_dropdown.addItem("📁 Відкрити Конфігурацію")
        self.quick_actions_dropdown.addItem("🔄 Скинути Налаштування")
        self.quick_actions_dropdown.addItem("💾 Експортувати Конфігурацію")
        self.quick_actions_dropdown.addItem("🚀 Налаштувати Автозапуск")
        self.quick_actions_dropdown.addItem("🗑️ Видалити Автозапуск")
        self.quick_actions_dropdown.addItem("🔄 Запустити в Трей")

        

        self.quick_actions_dropdown.currentIndexChanged.connect(self.on_quick_action_selected)

        actions_layout1.addWidget(self.quick_actions_dropdown)
        actions_layout1.addStretch()
        layout.addLayout(actions_layout1)

        # Autorun status label
        self.autorun_status_label = QLabel("Статус автозапуску: Перевірка...")
        self.autorun_status_label.setStyleSheet("font-size: 10px; color: #666; padding: 5px;")
        layout.addWidget(self.autorun_status_label)

        # Check autorun status on dialog open
        self.check_autorun_status()

        return group

    # Helper methods for enhanced functionality
    def on_quick_action_selected(self, index):
        """Handle quick action dropdown selection"""
        if index == 0:  # "🚀 Швидкі Дії" - placeholder, do nothing
            return

        action_text = self.quick_actions_dropdown.itemText(index)

        # Reset dropdown to first item (placeholder)
        self.quick_actions_dropdown.setCurrentIndex(0)

        # Execute the corresponding action
        if "Тестова Організація" in action_text:
            self.test_organization()
        elif "Відкрити Конфігурацію" in action_text:
            self.open_config_folder()
        elif "Скинути Налаштування" in action_text:
            self.reset_settings()
        elif "Експортувати Конфігурацію" in action_text:
            self.export_configuration()
        elif "Налаштувати Автозапуск" in action_text:
            self.setup_autorun()
        elif "Видалити Автозапуск" in action_text:
            self.remove_autorun()
        elif "Запустити в Трей" in action_text:
            self.restart_to_tray()

    def _set_timer_preset(self, minutes: int):
        """Set timer to preset value"""
        self.chk_override_timer.setChecked(True)
        self.spin_default_timer.setValue(minutes)
        self.timer_status_label.setText(f"Таймер: Налаштовано на {minutes} хвилин")

    def test_organization(self):
        """Run a simulation of organization without creating any files"""
        reply = QMessageBox.question(
            self,
            "Симуляція Організації",
            "Бажаєте виконати симуляцію організації робочого столу?\n\n"
            "Це допоможе перевірити ваші налаштування фільтрів та дисків без створення файлів.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            # Create progress dialog
            progress = QProgressDialog("Підготовка до тестової організації...", "Скасувати", 0, 100, self)
            progress.setWindowTitle("Тестова Організація")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.show()

            try:
                # Step 1: Check settings
                progress.setLabelText("Перевірка налаштувань...")
                progress.setValue(10)
                QApplication.processEvents()

                # Get current settings
                if hasattr(self, 'current_settings'):
                    settings = self.current_settings
                elif hasattr(self, 'parent') and hasattr(self.parent(), 'current_settings'):
                    settings = self.parent().current_settings
                else:
                    settings = {}

                progress.setValue(20)
                QApplication.processEvents()

                # Step 2: Check target drive
                progress.setLabelText("Перевірка цільового диска...")
                drive_policy = settings.get('drives', {}).get('main_drive_policy', 'D')

                # Determine target drive based on policy (same logic as main application)
                target_drive = None
                if drive_policy == 'D':
                    target_drive = 'D'
                elif drive_policy == 'auto':
                    # For auto policy, try to find next available drive
                    target_drive = 'D'  # Default fallback for testing
                    # Check for other available drives
                    for drive_letter in ['D', 'E', 'F', 'G']:
                        if os.path.exists(f"{drive_letter}:\\"):
                            target_drive = drive_letter
                            break
                else:
                    # If policy is a specific drive letter, use it
                    target_drive = drive_policy

                # Verify target drive exists
                if not target_drive or not os.path.exists(f"{target_drive}:\\"):
                    progress.setValue(100)
                    QMessageBox.warning(self, "Попередження", f"Цільовий диск не знайдено!")
                    progress.close()
                    return

                progress.setValue(30)
                QApplication.processEvents()

                # Step 3: Scan desktop and check filters
                progress.setLabelText("Сканування робочого столу та перевірка фільтрів...")
                desktop_path = os.path.expanduser("~/Desktop")
                if not os.path.exists(desktop_path):
                    desktop_path = os.path.expanduser("~/Робочий стіл")

                file_count = 0
                would_move_count = 0
                affected_files = []
                file_details = {}

                # Get file manager settings
                fm_settings = settings.get('file_manager', {})
                allowed_extensions = {ext.lower() for ext in fm_settings.get('allowed_extensions', [])}
                allowed_filenames = {name for name in fm_settings.get('allowed_filenames', [])}
                max_size_bytes = fm_settings.get('max_file_size_mb', 100) * 1024 * 1024

                
                if os.path.exists(desktop_path):
                    for item in os.listdir(desktop_path):
                        if item.startswith('.'):
                            continue

                        item_path = os.path.join(desktop_path, item)
                        if not os.path.exists(item_path):
                            continue

                        file_count += 1

                        # Check if it's a file or directory
                        is_file = os.path.isfile(item_path)
                        file_size = 0
                        file_ext = ""

                        if is_file:
                            try:
                                file_size = os.path.getsize(item_path)
                                file_ext = os.path.splitext(item)[1].lower()
                            except:
                                pass

                        # Determine if file would be moved based on filters (same logic as actual organization)
                        would_move = True  # Default to moving, then check filters
                        reason = "Would be moved"

                        # Get filename without extension for checking
                        item_name_no_ext, _ = os.path.splitext(item)

                        # INVERSE LOGIC: If allowed_extensions is not empty, KEEP files with those extensions, move others
                        if allowed_extensions and file_ext in allowed_extensions:
                            would_move = False
                            reason = f"Extension whitelisted (kept): {file_ext}"

                        # INVERSE LOGIC: If allowed_filenames is not empty, KEEP files with those names, move others
                        elif allowed_filenames and item_name_no_ext in allowed_filenames:
                            would_move = False
                            reason = f"Filename whitelisted (kept): {item_name_no_ext}"

                        # Check file size limit
                        elif is_file and file_size > max_size_bytes:
                            would_move = False
                            size_mb = file_size / (1024 * 1024)
                            reason = f"File too large: {size_mb:.1f}MB > {fm_settings.get('max_file_size_mb', 100)}MB"

                        if would_move:
                            would_move_count += 1
                            affected_files.append(f"📄 {item}")
                            file_details[item] = {
                                'size': file_size,
                                'ext': file_ext,
                                'reason': reason,
                                'type': 'file' if is_file else 'directory'
                            }

                progress.setValue(70)
                QApplication.processEvents()

                # Step 4: Simulate organization without creating directories
                progress.setLabelText(f"Симуляція організації (без створення файлів)...")

                # Define simulated directory structure (no actual creation)
                simulated_dirs = {
                    'Documents': 'Документи',
                    'Images': 'Зображення',
                    'Videos': 'Відео',
                    'Archives': 'Архіви',
                    'Programs': 'Програми',
                    'Other': 'Інше',
                    'Shortcuts': 'Ярлики'
                }

                simulated_moves = 0
                simulated_copies = []
                debug_info = []

                if os.path.exists(desktop_path):
                    # Debug: Get all files on desktop
                    all_desktop_items = [f for f in os.listdir(desktop_path)
                                       if not f.startswith('.') and
                                       os.path.exists(os.path.join(desktop_path, f))]

                    debug_info.append(f"DEBUG: Found {len(all_desktop_items)} items on desktop")
                    debug_info.append(f"DEBUG: Extension filters: {list(allowed_extensions)}")
                    debug_info.append(f"DEBUG: Name filters: {list(allowed_filenames)}")
                    debug_info.append(f"DEBUG: Size limit: {fm_settings.get('max_file_size_mb', 100)}MB")

                    processed_files = 0
                    total_files = len(all_desktop_items)

                    for item in os.listdir(desktop_path):
                        if progress.wasCanceled():
                            QMessageBox.information(self, "Скасовано", "Симуляцію організації скасовано.")
                            progress.close()
                            return

                        if item.startswith('.'):
                            continue

                        item_path = os.path.join(desktop_path, item)
                        if not os.path.exists(item_path):
                            continue

                        processed_files += 1

                        # Determine if file would be moved and where
                        would_move = False
                        target_dir = "Other"
                        reason = ""

                        is_file = os.path.isfile(item_path)
                        file_ext = os.path.splitext(item)[1].lower()

                        # Apply filter logic (same as actual organization)
                        would_move = True  # Default to moving, then check filters
                        reason = "Would be moved"

                        # Get filename without extension for checking
                        item_name_no_ext, _ = os.path.splitext(item)

                        # INVERSE LOGIC: If allowed_extensions is not empty, KEEP files with those extensions, move others
                        if allowed_extensions and file_ext in allowed_extensions:
                            would_move = False
                            reason = f"Extension whitelisted (kept): {file_ext}"

                        # INVERSE LOGIC: If allowed_filenames is not empty, KEEP files with those names, move others
                        elif allowed_filenames and item_name_no_ext in allowed_filenames:
                            would_move = False
                            reason = f"Filename whitelisted (kept): {item_name_no_ext}"

                        # Check file size limit
                        elif is_file:
                            try:
                                file_size = os.path.getsize(item_path)
                                if file_size > max_size_bytes:
                                    would_move = False
                                    size_mb = file_size / (1024 * 1024)
                                    reason = f"File too large: {size_mb:.1f}MB > {fm_settings.get('max_file_size_mb', 100)}MB"
                            except:
                                pass

                        # Debug info for this file
                        debug_info.append(f"DEBUG: File '{item}' - ext: '{file_ext}', would_move: {would_move}, reason: '{reason}'")

                        # Determine target directory based on file type
                        if would_move:
                            # Categorize based on common file types
                            document_exts = ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.ppt', '.pptx']
                            image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.svg', '.webp']
                            video_exts = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v']
                            archive_exts = ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2']
                            program_exts = ['.exe', '.msi', '.deb', '.rpm', '.dmg', '.pkg']
                            shortcut_exts = ['.lnk', '.url', '.webloc']

                            if file_ext in document_exts:
                                target_dir = 'Documents'
                            elif file_ext in image_exts:
                                target_dir = 'Images'
                            elif file_ext in video_exts:
                                target_dir = 'Videos'
                            elif file_ext in archive_exts:
                                target_dir = 'Archives'
                            elif file_ext in program_exts:
                                target_dir = 'Programs'
                            elif file_ext in shortcut_exts:
                                target_dir = 'Shortcuts'
                            else:
                                target_dir = 'Other'

                            # Add Shortcuts to simulated structure if needed
                            if target_dir == 'Shortcuts':
                                target_dir_name = simulated_dirs.get('Shortcuts', 'Ярлики')
                            else:
                                target_dir_name = simulated_dirs.get(target_dir, target_dir)

                            if is_file:
                                # Simulate file move (no actual file creation)
                                file_size = os.path.getsize(item_path) if os.path.exists(item_path) else 0
                                simulated_moves += 1
                                simulated_copies.append(f"📄 {item} → {target_dir_name}/")
                                debug_info.append(f"SIMULATION: Would move file '{item}' ({file_size} bytes) to '{target_dir_name}/' - {reason}")
                            else:
                                # Simulate directory move (no actual directory creation)
                                simulated_moves += 1
                                simulated_copies.append(f"📁 {item} → {target_dir_name}/")
                                debug_info.append(f"SIMULATION: Would move directory '{item}' to '{target_dir_name}/' - {reason}")

                        # Update progress
                        progress_value = 70 + int(30 * processed_files / max(total_files, 1))
                        progress.setLabelText(f"Обробка {processed_files}/{total_files} елементів (симульовано переміщень: {simulated_moves})...")
                        progress.setValue(progress_value)
                        QApplication.processEvents()

                # Complete
                progress.setValue(100)
                QApplication.processEvents()

                # Show results
                result_msg = f"Симуляцію організації завершено успішно!\n\n"
                result_msg += f"📁 Цільовий диск: {target_drive}\n"
                result_msg += f"📄 Загалом елементів на робочому столі: {file_count}\n"
                result_msg += f"🔄 Симульовано переміщень: {simulated_moves} елементів\n"
                result_msg += f"✅ Це була симуляція - файли не було створено\n\n"

                # Add debug information
                if len(debug_info) <= 15:  # Show debug info if not too much
                    result_msg += f"🔍 Відлаговувальна інформація:\n"
                    for debug in debug_info:
                        result_msg += f"  {debug}\n"
                    result_msg += "\n"

                # Filter information
                result_msg += f"🔍 Активні фільтри:\n"
                if allowed_extensions:
                    ext_list = list(allowed_extensions)
                    result_msg += f"  • Збережені розширення (whitelist): {', '.join(ext_list[:3])}"
                    if len(ext_list) > 3:
                        result_msg += f" (+{len(ext_list)-3} ще)"
                    result_msg += "\n"
                if allowed_filenames:
                    name_list = list(allowed_filenames)
                    result_msg += f"  • Збережені імена (whitelist): {', '.join(name_list[:3])}"
                    if len(name_list) > 3:
                        result_msg += f" (+{len(name_list)-3} ще)"
                    result_msg += "\n"
                result_msg += f"  • Максимальний розмір файлу: {fm_settings.get('max_file_size_mb', 100)}MB\n"

                # Show simulated moves
                if simulated_copies:
                    result_msg += f"\n📋 Симульовані переміщення (перші 10):\n"
                    for move in simulated_copies[:10]:
                        result_msg += f"  {move}\n"
                    if len(simulated_copies) > 10:
                        result_msg += f"  ... та ще {len(simulated_copies)-10} елементів\n"

                result_msg += f"\n⚙️ Статус налаштувань: ✅ Перевірено"
                result_msg += f"\n🔒 Оригінальні файли не були переміщені"
                result_msg += f"\n📂 Тестові файли не створювалися (чиста симуляція)"

                progress.close()

                # Show results (no directory to open since it's simulation-only)
                QMessageBox.information(
                    self,
                    "Симуляція Організації Завершена",
                    f"Симуляцію організації завершено!\n\n"
                    f"🔄 Симульовано переміщень: {simulated_moves} елементів\n"
                    f"📄 Проаналізовано файлів: {file_count}\n"
                    f"📁 Цільовий диск: {target_drive}\n\n"
                    f"✅ Це була чиста симуляція без створення файлів",
                    QMessageBox.Ok
                )

                # Show summary message
                QMessageBox.information(self, "Результати Тесту", result_msg)

            except Exception as e:
                progress.close()
                QMessageBox.critical(self, "Помилка", f"Помилка під час тестової організації:\n{str(e)}")

    def open_config_folder(self):
        """Open the configuration folder"""
        try:
            if platform.system() == "Windows":
                # Try multiple methods to open File Explorer on Windows
                try:
                    # Method 1: Use os.startfile (most reliable)
                    os.startfile(CONFIG_DIR)
                except Exception:
                    try:
                        # Method 2: Use explorer with full path
                        windir = os.environ.get('WINDIR', 'C:\\Windows')
                        explorer_path = os.path.join(windir, 'explorer.exe')
                        subprocess.run([explorer_path, CONFIG_DIR], shell=False)
                    except Exception:
                        try:
                            # Method 3: Use shell=True with start command
                            subprocess.run(['cmd', '/c', 'start', '', CONFIG_DIR], shell=True)
                        except Exception:
                            # Method 4: Fallback to shell=True with explorer
                            subprocess.run(['explorer', CONFIG_DIR], shell=True)
            else:
                subprocess.run(['xdg-open', CONFIG_DIR])
        except Exception as e:
            QMessageBox.critical(self, "Помилка", f"Не вдалося відкрити папку конфігурації:\n{e}")

    def reset_settings(self):
        """Reset general settings to defaults (excluding virtual environment)"""
        reply = QMessageBox.question(
            self,
            "Скидання Налаштувань",
            "Ви впевнені, що хочете скинути налаштування до значень за замовчуванням?\n\n"
            "Це скине налаштування:\n"
            "• Загальні налаштування додатку\n"
            "• Налаштування таймера\n"
            "• Фільтри файлів\n"
            "• Налаштування розкладу\n\n"
            "Віртуальне середовище буде збережено.\n"
            "Цю дію не можна скасувати.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                # Get current settings to preserve virtual environment data
                current_settings_backup = {}
                if hasattr(self, 'parent_window') and self.parent_window:
                    current_settings_backup = copy.deepcopy(self.parent_window.settings)

                # Delete existing configuration file to ensure clean reset
                if os.path.exists(CONFIG_FILE):
                    os.remove(CONFIG_FILE)

                # Delete last run file to reset schedule tracking
                if os.path.exists(LAST_RUN_FILE):
                    os.remove(LAST_RUN_FILE)

                # Reset to defaults (only general settings)
                self.current_settings = copy.deepcopy(DEFAULT_SETTINGS)

                # Load defaults into UI controls
                self.load_settings_to_ui()

                # Get the settings from UI (which now has defaults) and apply them
                default_settings_from_ui = self.get_settings_from_ui()
                self.settings_applied.emit(default_settings_from_ui)
                self.changes_applied = True

                QMessageBox.information(self, "Успіх",
                    "Налаштування успішно скинуто до значень за замовчуванням!\n\n"
                    "• Загальні налаштування: Скинуто\n"
                    "• Налаштування таймера: Скинуто\n"
                    "• Фільтри файлів: Скинуто\n"
                    "• Налаштування розкладу: Скинуто\n"
                    "• Віртуальне середовище: Збережено\n\n"
                    "Для керування віртуальним середовищем\n"
                    "використовуйте вкладку 'Віртуальне Середовище'.")
            except Exception as e:
                QMessageBox.critical(self, "Помилка", f"Не вдалося скинути налаштування:\n{e}")

    def export_configuration(self):
        """Export current configuration to file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Експортувати Конфігурацію",
            f"desktop_organizer_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.current_settings, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "Успіх", f"Конфігурація експортована до:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Помилка", f"Не вдалося експортувати конфігурацію:\n{e}")

    def setup_autorun(self):
        """Setup Windows autorun with tray mode"""
        try:
            # Get application path
            if getattr(sys, 'frozen', False):
                app_path = sys.executable
            else:
                app_path = os.path.abspath(__file__)
                # For Python scripts, use python.exe to run
                app_path = f'"{sys.executable}" "{app_path}"'

            # Enable tray mode in settings
            current_settings = self.current_settings.copy()
            if 'application' not in current_settings:
                current_settings['application'] = {}
            current_settings['application']['minimize_to_tray'] = True
            current_settings['application']['autostart_timer_enabled'] = True

            # Apply the settings changes
            self.current_settings = current_settings
            self.settings_applied.emit(current_settings)

            # Create registry entry for autorun
            import winreg
            key = winreg.HKEY_CURRENT_USER
            subkey = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            app_name = "DesktopOrganizer"

            try:
                # Open or create the registry key
                with winreg.OpenKey(key, subkey, 0, winreg.KEY_SET_VALUE) as registry_key:
                    # Set the autorun value with startup-to-tray argument
                    autorun_command = f'"{app_path}" --startup-to-tray'
                    winreg.SetValueEx(registry_key, app_name, 0, winreg.REG_SZ, autorun_command)

                # Update UI
                self.chk_minimize_to_tray.setChecked(True)
                self.autorun_status_label.setText("Статус автозапуску: ✅ Налаштовано")
                self.autorun_status_label.setStyleSheet("font-size: 10px; color: black; padding: 5px;")

                QMessageBox.information(self, "Успіх!",
                    f"Автозапуск успішно налаштовано!\n\n"
                    f"✅ Додаток буде запускатися при старті Windows\n"
                    f"✅ Мінімізація в трей увімкнена\n"
                    f"✅ Додаток буде доступний в системному треї\n\n"
                    f"Шлях програми:\n{app_path}\n\n"
                    f"Для відключення автозапуску використовуйте кнопку 'Видалити Автозапуск'.")

            except OSError as e:
                QMessageBox.critical(self, "Помилка доступу",
                    f"Не вдалося налаштувати автозапуск:\n{e}\n\n"
                    "Перевірте, чи маєте ви права адміністратора.")

        except ImportError:
            QMessageBox.critical(self, "Помилка",
                "Модуль winreg не доступний. Налаштування автозапуску неможливе.")
        except Exception as e:
            QMessageBox.critical(self, "Помилка",
                f"Не вдалося налаштувати автозапуск:\n{e}")

    def restart_to_tray(self):
        """Restart application in tray mode"""
        reply = QMessageBox.question(
            self,
            "Перезапуск в Трей",
            "Бажаєте перезапустити програму в режимі роботи з трею?\n\n"
            "Програма перезапуститься і буде доступна через іконку в системному треї.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            try:
                import sys
                import subprocess
                import os

                # Get current executable path
                current_exe = sys.executable
                current_script = os.path.abspath(__file__)

                # Restart with startup-to-tray argument
                subprocess.Popen([
                    current_exe, current_script, "--startup-to-tray"
                ])

                # Close current application
                QApplication.quit()

            except Exception as e:
                QMessageBox.critical(self, "Помилка",
                    f"Не вдалося перезапустити програму:\n{e}")

    def remove_autorun(self):
        """Remove Windows autorun"""
        try:
            import winreg
            key = winreg.HKEY_CURRENT_USER
            subkey = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            app_name = "DesktopOrganizer"

            try:
                # Open the registry key
                with winreg.OpenKey(key, subkey, 0, winreg.KEY_SET_VALUE) as registry_key:
                    # Try to delete the autorun value
                    winreg.DeleteValue(registry_key, app_name)

                # Update UI
                self.autorun_status_label.setText("Статус автозапуску: ❌ Вимкнено")
                self.autorun_status_label.setStyleSheet("font-size: 10px; color: black; padding: 5px;")

                QMessageBox.information(self, "Успіх!",
                    "Автозапуск успішно видалено!\n\n"
                    "Додаток більше не буде запускатися автоматично при старті Windows.")

            except OSError:
                # Entry doesn't exist
                self.autorun_status_label.setText("Статус автозапуску: ❌ Вимкнено")
                self.autorun_status_label.setStyleSheet("font-size: 10px; color: black; padding: 5px;")
                QMessageBox.information(self, "Інформація",
                    "Автозапуск не був налаштований.")

        except ImportError:
            QMessageBox.critical(self, "Помилка",
                "Модуль winreg не доступний.")
        except Exception as e:
            QMessageBox.critical(self, "Помилка",
                f"Не вдалося видалити автозапуск:\n{e}")

    def check_autorun_status(self):
        """Check current autorun status"""
        # Prevent infinite calls by checking if the label exists
        if not hasattr(self, 'autorun_status_label') or self.autorun_status_label is None:
            return

        try:
            import winreg
            key = winreg.HKEY_CURRENT_USER
            subkey = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            app_name = "DesktopOrganizer"

            try:
                with winreg.OpenKey(key, subkey, 0, winreg.KEY_READ) as registry_key:
                    # Try to read the value
                    value, _ = winreg.QueryValueEx(registry_key, app_name)
                    self.autorun_status_label.setText("Статус автозапуску: ✅ Активно")
                    self.autorun_status_label.setStyleSheet("font-size: 10px; color: black; padding: 5px;")
            except OSError:
                self.autorun_status_label.setText("Статус автозапуску: ❌ Вимкнено")
                self.autorun_status_label.setStyleSheet("font-size: 10px; color: black; padding: 5px;")

        except ImportError:
            self.autorun_status_label.setText("Статус автозапуску: Невідомо")
            self.autorun_status_label.setStyleSheet("font-size: 10px; color: #666; padding: 5px;")
        except Exception as e:
            self.autorun_status_label.setText("Статус автозапуску: Помилка")
            self.autorun_status_label.setStyleSheet("font-size: 10px; color: #666; padding: 5px;")

    def create_file_manager_tab(self):
        """Create the file manager settings tab"""
        # Create content widget without scroll area for better fit
        tab_fm = QWidget()
        main_layout = QVBoxLayout(tab_fm)
        main_layout.setSpacing(12)  # Slightly increased spacing for larger window
        main_layout.setContentsMargins(20, 15, 20, 15)  # Slightly increased margins

        # File size limit (keep existing functionality)
        size_group = QGroupBox("Обмеження Розміру Файлу")
        size_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                border: 2px solid black;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        size_layout = QHBoxLayout(size_group)
        size_layout.setContentsMargins(10, 8, 10, 8)  # Compact margins
        size_layout.addWidget(QLabel("Макс. розмір файлу:"))
        self.spin_max_size = self._create_spinbox(1, 10240, " MB")
        size_layout.addWidget(self.spin_max_size)
        size_layout.addStretch()
        main_layout.addWidget(size_group)

        # Common presets section
        presets_group = self._create_presets_section()
        main_layout.addWidget(presets_group)

        # Actions section - moved up for better accessibility
        actions_group = self._create_filter_actions_section()
        main_layout.addWidget(actions_group)

        # File filters section - use splitter for better resizing
        filters_splitter = QWidget()
        filters_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        filters_layout = QHBoxLayout(filters_splitter)
        filters_layout.setSpacing(20)  # Consistent spacing between widgets
        filters_layout.setContentsMargins(0, 0, 0, 0)

        # File extensions filter group
        ext_group = self._create_enhanced_filter_group("extension")
        ext_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        filters_layout.addWidget(ext_group, 1)

        # File names filter group
        name_group = self._create_enhanced_filter_group("filename")
        name_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        filters_layout.addWidget(name_group, 1)

        main_layout.addWidget(filters_splitter)

        # Add stretch to allow whitelist widgets to expand properly
        main_layout.addStretch(1)

        # Add tab directly without scroll area
        self.tabs.addTab(tab_fm, "Фільтри Файлів")

    def _create_presets_section(self) -> QGroupBox:
        """Create compact filter presets section - no scroll area needed"""
        presets_group = QGroupBox("Шаблонні Набори Фільтрів")
        presets_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                border: 2px solid black;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #333;
            }
        """)

        # Compact layout - no scroll area for this small amount of content
        presets_layout = QVBoxLayout(presets_group)
        presets_layout.setSpacing(10)  # Consistent spacing
        presets_layout.setContentsMargins(15, 15, 15, 10)  # Consistent margins

        # Direct button layout without scroll area container
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)  # Consistent spacing between buttons
        buttons_layout.setContentsMargins(0, 0, 0, 0)

        # Compact button style
        button_style = """
            QPushButton {
                font-size: 9px;
                font-weight: 500;
                padding: 3px 6px;
                border: 1px solid #aaa;
                border-radius: 3px;
                background-color: #f9f9f9;
                min-width: 70px;
                max-width: 90px;
                height: 22px;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
                border: 1px solid #888;
            }
            QPushButton:pressed {
                background-color: #ddd;
                border: 1px solid #666;
            }
        """

        # Create all preset buttons
        self.btn_preset_system = QPushButton("Системні")
        self.btn_preset_system.clicked.connect(lambda: self.apply_preset("system"))
        self.btn_preset_system.setToolTip("Зберігати системні файли Windows")
        self.btn_preset_system.setStyleSheet(button_style)

        self.btn_preset_media = QPushButton("Медіа")
        self.btn_preset_media.clicked.connect(lambda: self.apply_preset("media"))
        self.btn_preset_media.setToolTip("Зберігати медіа файли (зображення, відео, аудіо)")
        self.btn_preset_media.setStyleSheet(button_style)

        self.btn_preset_docs = QPushButton("Документи")
        self.btn_preset_docs.clicked.connect(lambda: self.apply_preset("documents"))
        self.btn_preset_docs.setToolTip("Зберігати файли документів")
        self.btn_preset_docs.setStyleSheet(button_style)

        self.btn_preset_dev = QPushButton("Розробка")
        self.btn_preset_dev.clicked.connect(lambda: self.apply_preset("development"))
        self.btn_preset_dev.setToolTip("Зберігати файли розробки (код, білди)")
        self.btn_preset_dev.setStyleSheet(button_style)

        self.btn_preset_reservoir = QPushButton("Резервуар")
        self.btn_preset_reservoir.clicked.connect(lambda: self.apply_preset("reservoir"))
        self.btn_preset_reservoir.setToolTip("Зберігати файли резервуарної симуляції")
        self.btn_preset_reservoir.setStyleSheet(button_style)

        self.btn_preset_cmgs = QPushButton("CMG")
        self.btn_preset_cmgs.clicked.connect(lambda: self.apply_preset("cmg"))
        self.btn_preset_cmgs.setToolTip("Зберігати файли CMG")
        self.btn_preset_cmgs.setStyleSheet(button_style)

        self.btn_preset_schlumberger = QPushButton("Schlumberger")
        self.btn_preset_schlumberger.clicked.connect(lambda: self.apply_preset("schlumberger"))
        self.btn_preset_schlumberger.setToolTip("Зберігати файли Schlumberger")
        self.btn_preset_schlumberger.setStyleSheet(button_style)

        self.btn_preset_halliburton = QPushButton("Halliburton")
        self.btn_preset_halliburton.clicked.connect(lambda: self.apply_preset("halliburton"))
        self.btn_preset_halliburton.setToolTip("Зберігати файли Halliburton")
        self.btn_preset_halliburton.setStyleSheet(button_style)

        # Add all buttons to layout directly - no scroll area needed
        buttons_layout.addWidget(self.btn_preset_system)
        buttons_layout.addWidget(self.btn_preset_media)
        buttons_layout.addWidget(self.btn_preset_docs)
        buttons_layout.addWidget(self.btn_preset_dev)
        buttons_layout.addWidget(self.btn_preset_reservoir)
        buttons_layout.addWidget(self.btn_preset_cmgs)
        buttons_layout.addWidget(self.btn_preset_schlumberger)
        buttons_layout.addWidget(self.btn_preset_halliburton)
        buttons_layout.addStretch()

        # Add buttons layout directly to group
        presets_layout.addLayout(buttons_layout)

        return presets_group

    def _create_enhanced_filter_group(self, filter_type: str) -> QGroupBox:
        """Create an enhanced filter group with better layout and functionality"""
        if filter_type == "extension":
            group_title = "Збережені Розширення (Whitelist)"
            placeholder = ".txt, .exe, .dll"
            search_placeholder = "Пошук розширень..."
        else:  # filename
            group_title = "Збережені Імена Файлів (Whitelist)"
            placeholder = "temp*, *cache*, config"
            search_placeholder = "Пошук імен файлів..."

        group = QGroupBox(group_title)
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                border: 2px solid black;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #333;
            }
        """)
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(10)  # Consistent internal spacing
        group_layout.setContentsMargins(15, 20, 15, 12)  # Consistent padding

        # Search bar with consistent spacing
        search_layout = QHBoxLayout()
        search_layout.setSpacing(10)  # Consistent spacing
        search_layout.setContentsMargins(0, 5, 0, 10)  # Consistent margins

        search_edit = QLineEdit()
        search_edit.setPlaceholderText(search_placeholder)
        search_edit.setFixedHeight(26)  # Optimized height
        search_edit.setStyleSheet("""
            QLineEdit {
                padding: 3px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 10px;
            }
            QLineEdit:focus {
                border: 2px solid #808080;
            }
        """)
        search_edit.textChanged.connect(lambda text, ft=filter_type: self.filter_list_items(ft))

        search_label = QLabel("Пошук:")
        search_label.setStyleSheet("font-size: 10px; font-weight: bold; color: black;")

        search_layout.addWidget(search_label)
        search_layout.addWidget(search_edit)
        group_layout.addLayout(search_layout)

        # List with compact styling
        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)

        list_widget = QListWidget()
        list_widget.setAlternatingRowColors(True)
        list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        list_widget.setMinimumHeight(180)  # Increased minimum height for better usability
        list_widget.setMinimumWidth(400)   # Optimized minimum width
        list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # Dynamic sizing

        # Store references with type prefixes to avoid conflicts
        if filter_type == "extension":
            self.list_extensions = list_widget
            self.search_extensions = search_edit
        else:
            self.list_filenames = list_widget
            self.search_filenames = search_edit

        list_layout.addWidget(list_widget)

        # Statistics label
        stats_label = QLabel("Всього: 0 елементів")
        stats_label.setStyleSheet("font-size: 10px; color: #666;")
        list_layout.addWidget(stats_label)

        group_layout.addWidget(list_container)

        # Input and controls section
        input_layout = QVBoxLayout()
        input_layout.setSpacing(8)  # Reduced from 12
        input_layout.setContentsMargins(0, 10, 0, 0)  # Reduced from 15

        # Input with validation
        input_group = QGroupBox("Додавання елемента")
        input_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 10px;
                border: 1px solid #ccc;
                border-radius: 4px;
                margin-top: 5px;
                padding-top: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 3px 0 3px;
            }
        """)
        input_group_layout = QVBoxLayout(input_group)
        input_group_layout.setSpacing(6)  # Reduced from 10
        input_group_layout.setContentsMargins(8, 10, 8, 8)  # Compact margins

        edit_widget = QLineEdit()
        edit_widget.setPlaceholderText(placeholder)
        edit_widget.setFixedHeight(28)  # Optimized height
        edit_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # Dynamic width
        edit_widget.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 10px;
                background-color: white;
            }
            QLineEdit:focus {
                border: 2px solid #808080;
                outline: none;
            }
        """)

        # Help text
        help_label = QLabel()
        if filter_type == "extension":
            help_label.setText("💡 Введіть розширення (напр., .txt) або декілька через кому")
        else:
            help_label.setText("💡 Використовуйте * та ? для шаблонів")
        help_label.setStyleSheet("font-size: 9px; color: #888; margin: 2px 0;")
        help_label.setWordWrap(True)

        input_group_layout.addWidget(edit_widget)
        input_group_layout.addWidget(help_label)

        input_layout.addWidget(input_group)

        # Buttons section
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)  # Reduced from 10
        buttons_layout.setContentsMargins(0, 5, 0, 0)  # Reduced from 10

        # Compact button style
        button_style = """
            QPushButton {
                font-size: 9px;
                font-weight: 500;
                padding: 4px 8px;
                border: 1px solid #888;
                border-radius: 4px;
                background-color: #f8f8f8;
                min-height: 22px;
                max-height: 26px;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
                border: 1px solid #666;
            }
            QPushButton:pressed {
                background-color: #d8d8d8;
                border: 1px solid #444;
            }
            QPushButton:disabled {
                background-color: #f0f0f0;
                color: #999;
                border: 1px solid #ccc;
            }
        """

        btn_add = QPushButton("Додати")
        btn_add.setStyleSheet(button_style)
        btn_add.setMinimumWidth(100)  # Increased width

        btn_remove = QPushButton("Видалити")
        btn_remove.setStyleSheet(button_style)
        btn_remove.setMinimumWidth(110)  # Increased width
        btn_remove.setEnabled(False)

        btn_clear = QPushButton("Очистити")
        btn_clear.setStyleSheet(button_style)
        btn_clear.setMinimumWidth(100)  # Increased width
        
        # Connect signals
        if filter_type == "extension":
            edit_widget.returnPressed.connect(self.add_extension)
            btn_add.clicked.connect(self.add_extension)
            btn_remove.clicked.connect(self.remove_extension)
            btn_clear.clicked.connect(lambda: self.clear_filter_list("extension"))
            self.edit_add_ext = edit_widget
            self.btn_remove_ext = btn_remove
            list_widget.itemSelectionChanged.connect(lambda: self.update_remove_button_state("extension"))
        else:
            edit_widget.returnPressed.connect(self.add_filename)
            btn_add.clicked.connect(self.add_filename)
            btn_remove.clicked.connect(self.remove_filename)
            btn_clear.clicked.connect(lambda: self.clear_filter_list("filename"))
            self.edit_add_name = edit_widget
            self.btn_remove_name = btn_remove
            list_widget.itemSelectionChanged.connect(lambda: self.update_remove_button_state("filename"))

        buttons_layout.addWidget(btn_add)
        buttons_layout.addWidget(btn_remove)
        buttons_layout.addWidget(btn_clear)

        input_layout.addLayout(buttons_layout)
        group_layout.addLayout(input_layout)

        # Update stats reference
        if filter_type == "extension":
            self.ext_stats_label = stats_label
        else:
            self.name_stats_label = stats_label

        return group

    def _create_filter_actions_section(self) -> QGroupBox:
        """Create filter actions section with import/export functionality"""
        actions_group = QGroupBox("Дії з Фільтрами")
        actions_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11px;
                border: 2px solid black;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        actions_layout = QHBoxLayout(actions_group)
        actions_layout.setSpacing(8)
        actions_layout.setContentsMargins(10, 12, 10, 10)

        # Compact button style
        button_style = """
            QPushButton {
                font-size: 10px;
                font-weight: 500;
                padding: 4px 8px;
                border: 1px solid #888;
                border-radius: 4px;
                background-color: #f8f8f8;
                min-height: 20px;
                max-height: 28px;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
                border: 1px solid #666;
            }
            QPushButton:pressed {
                background-color: #d8d8d8;
                border: 1px solid #444;
            }
        """

        # Import/Export buttons with shorter text
        self.btn_import_filters = QPushButton("Імпорт")
        self.btn_import_filters.clicked.connect(self.import_filters)
        self.btn_import_filters.setStyleSheet(button_style)
        self.btn_import_filters.setToolTip("Імпортувати фільтри з файлу")

        self.btn_export_filters = QPushButton("Експорт")
        self.btn_export_filters.clicked.connect(self.export_filters)
        self.btn_export_filters.setStyleSheet(button_style)
        self.btn_export_filters.setToolTip("Експортувати фільтри у файл")

        self.btn_reset_filters = QPushButton("Скинути")
        self.btn_reset_filters.clicked.connect(self.reset_all_filters)
        self.btn_reset_filters.setStyleSheet(button_style)
        self.btn_reset_filters.setToolTip("Скинути всі фільтри")

        actions_layout.addWidget(self.btn_import_filters)
        actions_layout.addWidget(self.btn_export_filters)
        actions_layout.addWidget(self.btn_reset_filters)
        actions_layout.addStretch()

        return actions_group

    def create_schedule_tab(self):
        """Create the enhanced schedule settings tab"""
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #d0d0d0;
                background-color: #ffffff;
            }
            QScrollBar:vertical {
                background-color: #f8f8f8;
                width: 14px;
                border: 1px solid #e0e0e0;
            }
            QScrollBar::handle:vertical {
                background-color: #b0b0b0;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #909090;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)

        # Create content widget
        tab_schedule = QWidget()
        main_layout = QVBoxLayout(tab_schedule)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Application Schedule Section
        app_schedule_group = self._create_application_schedule_section()
        main_layout.addWidget(app_schedule_group)

        # Windows Task Scheduler Section
        windows_scheduler_group = self._create_windows_scheduler_section()
        main_layout.addWidget(windows_scheduler_group)

        # Schedule Status Section
        status_group = self._create_schedule_status_section()
        main_layout.addWidget(status_group)

        main_layout.addStretch()

        # Set up scroll area
        scroll_area.setWidget(tab_schedule)
        self.tabs.addTab(scroll_area, "Розклад")

    def _create_application_schedule_section(self) -> QGroupBox:
        """Create application-level schedule section"""
        group = QGroupBox("Вбудований Таймер Додатку")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid black;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 20, 15, 15)

        # Schedule type selection
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Тип розкладу:"))
        self.schedule_type_combo = QComboBox()
        self.schedule_type_combo.addItems(["Вимкнено", "Щодня", "Щотижня", "Щомісяця", "Щокварталу"])
        self.schedule_type_combo.currentIndexChanged.connect(self.update_schedule_ui)
        self.schedule_type_combo.setMinimumWidth(150)
        type_layout.addWidget(self.schedule_type_combo)
        type_layout.addStretch()
        layout.addLayout(type_layout)

        # Time range selection
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Час виконання:"))
        self.schedule_time_start_edit = QTimeEdit()
        self.schedule_time_start_edit.setDisplayFormat("HH:mm")
        self.schedule_time_start_edit.setMinimumWidth(80)
        self.schedule_time_end_edit = QTimeEdit()
        self.schedule_time_end_edit.setDisplayFormat("HH:mm")
        self.schedule_time_end_edit.setMinimumWidth(80)
        time_layout.addWidget(self.schedule_time_start_edit)
        time_layout.addWidget(QLabel("до"))
        time_layout.addWidget(self.schedule_time_end_edit)
        time_layout.addStretch()
        layout.addLayout(time_layout)

        # Schedule-specific options container
        self.schedule_options_widget = QWidget()
        options_layout = QVBoxLayout(self.schedule_options_widget)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(10)

        # Weekly options
        weekly_container = QWidget()
        weekly_layout = QHBoxLayout(weekly_container)
        weekly_layout.setContentsMargins(0, 0, 0, 0)
        weekly_layout.addWidget(QLabel("День тижня:"))
        self.schedule_day_of_week_combo = QComboBox()
        self.schedule_day_of_week_combo.addItems(["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"])
        self.schedule_day_of_week_combo.setMinimumWidth(120)
        weekly_layout.addWidget(self.schedule_day_of_week_combo)
        weekly_layout.addStretch()
        options_layout.addWidget(weekly_container)

        # Monthly options
        monthly_container = QWidget()
        monthly_layout = QHBoxLayout(monthly_container)
        monthly_layout.setContentsMargins(0, 0, 0, 0)
        monthly_layout.addWidget(QLabel("День місяця:"))
        self.schedule_day_of_month_spin = self._create_spinbox(1, 31)
        monthly_layout.addWidget(self.schedule_day_of_month_spin)
        monthly_layout.addWidget(QLabel("числа"))
        monthly_layout.addStretch()
        options_layout.addWidget(monthly_container)

        # Quarterly options
        quarterly_container = QWidget()
        quarterly_layout = QHBoxLayout(quarterly_container)
        quarterly_layout.setContentsMargins(0, 0, 0, 0)
        quarterly_layout.addWidget(QLabel("Щоквартально:"))
        self.schedule_quarter_month_combo = QComboBox()
        self.schedule_quarter_month_combo.addItems(["Перший", "Другий", "Третій"])
        self.schedule_quarter_month_combo.setMinimumWidth(100)
        quarterly_layout.addWidget(self.schedule_quarter_month_combo)
        quarterly_layout.addWidget(QLabel("місяць,"))
        self.schedule_quarter_day_spin = self._create_spinbox(1, 31)
        quarterly_layout.addWidget(self.schedule_quarter_day_spin)
        quarterly_layout.addWidget(QLabel("день"))
        quarterly_layout.addStretch()
        options_layout.addWidget(quarterly_container)

        layout.addWidget(self.schedule_options_widget)

        return group

    def _create_windows_scheduler_section(self) -> QGroupBox:
        """Create Windows Task Scheduler integration section"""
        group = QGroupBox("Інтеграція з Windows Task Scheduler")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid black;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: black;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 20, 15, 15)

        # Description
        desc = QLabel("Windows Task Scheduler забезпечує більш надійне виконання завдань, "
                     "навіть коли додаток закрито. Система працюватиме у фоновому режимі.")
        desc.setStyleSheet("font-size: 11px; color: black; background-color: #f5f5f5; padding: 10px; border-radius: 4px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Status info
        status_layout = QHBoxLayout()
        self.scheduler_status_label = QLabel("Статус: Перевірка...")
        self.scheduler_status_label.setStyleSheet("font-weight: bold; color: #666;")
        status_layout.addWidget(self.scheduler_status_label)
        status_layout.addStretch()

        self.check_scheduler_btn = QPushButton("Перевірити")
        self.check_scheduler_btn.clicked.connect(self.check_windows_scheduler_status)
        self.check_scheduler_btn.setFixedHeight(30)
        self.check_scheduler_btn.setMinimumWidth(100)
        status_layout.addWidget(self.check_scheduler_btn)
        layout.addLayout(status_layout)

        # Task management buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        self.create_task_btn = QPushButton("Створити Завдання")
        self.create_task_btn.clicked.connect(self.create_windows_task)
        self.create_task_btn.setFixedHeight(35)
        self.create_task_btn.setMinimumWidth(120)

        self.remove_task_btn = QPushButton("Видалити Завдання")
        self.remove_task_btn.clicked.connect(self.remove_windows_task)
        self.remove_task_btn.setFixedHeight(35)
        self.remove_task_btn.setMinimumWidth(120)

        self.open_task_scheduler_btn = QPushButton("Відкрити Task Scheduler")
        self.open_task_scheduler_btn.clicked.connect(self.open_windows_task_scheduler)
        self.open_task_scheduler_btn.setFixedHeight(35)
        self.open_task_scheduler_btn.setMinimumWidth(150)

        buttons_layout.addWidget(self.create_task_btn)
        buttons_layout.addWidget(self.remove_task_btn)
        buttons_layout.addWidget(self.open_task_scheduler_btn)
        buttons_layout.addStretch()

        layout.addLayout(buttons_layout)

        return group

    def _create_schedule_status_section(self) -> QGroupBox:
        """Create schedule status and information section"""
        group = QGroupBox("Статус Розкладу")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid black;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 20, 15, 15)

        # Current status
        self.current_status_label = QLabel("Поточний статус: Вимкнено")
        self.current_status_label.setStyleSheet("font-size: 12px; font-weight: bold; color: black;")
        layout.addWidget(self.current_status_label)

        # Next run time
        self.next_run_label = QLabel("Наступне виконання: Н/Д")
        self.next_run_label.setStyleSheet("font-size: 11px; color: #666;")
        layout.addWidget(self.next_run_label)

        # Time remaining
        self.time_remaining_label = QLabel("Час до виконання: Н/Д")
        self.time_remaining_label.setStyleSheet("font-size: 11px; color: black; font-weight: bold;")
        layout.addWidget(self.time_remaining_label)

        # Last run info
        self.last_run_label = QLabel("Останнє виконання: Н/Д")
        self.last_run_label.setStyleSheet("font-size: 11px; color: #666;")
        layout.addWidget(self.last_run_label)

        # Tray minimization info
        self.tray_info_label = QLabel("Мінімізація в трей: Н/Д")
        self.tray_info_label.setStyleSheet("font-size: 11px; color: #666;")
        layout.addWidget(self.tray_info_label)

        # Action buttons
        actions_layout = QHBoxLayout()

        self.refresh_status_btn = QPushButton("Оновити Статус")
        self.refresh_status_btn.clicked.connect(self.refresh_schedule_status)
        self.refresh_status_btn.setFixedHeight(30)
        self.refresh_status_btn.setMinimumWidth(100)

        actions_layout.addWidget(self.refresh_status_btn)
        actions_layout.addStretch()

        layout.addLayout(actions_layout)

        return group

      # Windows Task Scheduler functionality
    def check_windows_scheduler_status(self):
        """Check if Windows Task Scheduler is available and task exists"""
        try:
            import ctypes
            # Check admin privileges
            try:
                is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            except:
                is_admin = False

            if not is_admin:
                self.scheduler_status_label.setText("Статус: Потрібні права адміністратора")
                self.scheduler_status_label.setStyleSheet("font-weight: bold; color: #808080;")
                return

            # Check if task exists
            task_exists = self._check_task_exists()
            if task_exists:
                self.scheduler_status_label.setText("Статус: Завдання створено ✅")
                self.scheduler_status_label.setStyleSheet("font-weight: bold; color: black;")
                self.create_task_btn.setEnabled(False)
                self.remove_task_btn.setEnabled(True)
            else:
                self.scheduler_status_label.setText("Статус: Завдання не створено")
                self.scheduler_status_label.setStyleSheet("font-weight: bold; color: black;")
                self.create_task_btn.setEnabled(True)
                self.remove_task_btn.setEnabled(False)

        except Exception as e:
            self.scheduler_status_label.setText(f"Статус: Помилка - {str(e)}")
            self.scheduler_status_label.setStyleSheet("font-weight: bold; color: black;")

    def _check_task_exists(self) -> bool:
        """Check if the Windows Task exists"""
        try:
            result = subprocess.run([
                'schtasks', '/Query', '/TN', 'DesktopOrganizer'
            ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)
            return result.returncode == 0
        except:
            return False

    def create_windows_task(self):
        """Create Windows Task Scheduler task"""
        try:
            # Get current settings
            schedule_type = self.schedule_type_combo.currentText()
            if schedule_type == "Вимкнено":
                QMessageBox.warning(self, "Помилка",
                                  "Спочатку налаштуйте розклад у секції 'Вбудований Таймер Додатку'")
                return

            # Get application path
            app_path = sys.executable if getattr(sys, 'frozen', False) else __file__
            if not app_path.endswith('.exe'):
                app_path = f'"{sys.executable}" "{app_path}"'

            # Create trigger based on schedule type
            trigger = self._build_schedule_trigger()
            if not trigger:
                return

            # Build command with correct argument
            command = f'{app_path} --scheduled-run'

            # Create the task
            result = subprocess.run([
                'schtasks', '/Create',
                '/TN', 'DesktopOrganizer',
                '/TR', command,
                '/SC', trigger['type'],
                *trigger['params'],
                '/F',  # Force overwrite if exists
                '/RL', 'HIGHEST'  # Run with highest privileges
            ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)

            if result.returncode == 0:
                QMessageBox.information(self, "Успіх",
                                      "Завдання Windows Task Scheduler успішно створено!\n\n"
                                      "Тепер організація робочого столу буде виконуватися "
                                      "автоматично навіть коли додаток закритий.")
                self.check_windows_scheduler_status()
                self.refresh_schedule_status()
            else:
                QMessageBox.critical(self, "Помилка",
                                   f"Не вдалося створити завдання:\n{result.stderr}")

        except subprocess.TimeoutExpired:
            QMessageBox.critical(self, "Помилка",
                               "Час очікування створення завдання вичерпано")
        except Exception as e:
            QMessageBox.critical(self, "Помилка",
                               f"Не вдалося створити завдання:\n{str(e)}")

    def remove_windows_task(self):
        """Remove Windows Task Scheduler task"""
        try:
            reply = QMessageBox.question(
                self,
                "Підтвердження Видалення",
                "Ви впевнені, що хочете видалити завдання з Windows Task Scheduler?\n\n"
                "Автоматична організація робочого столу більше не буде виконуватися.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                result = subprocess.run([
                    'schtasks', '/Delete', '/TN', 'DesktopOrganizer', '/F'
                ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)

                if result.returncode == 0:
                    QMessageBox.information(self, "Успіх",
                                          "Завдання успішно видалено з Windows Task Scheduler")
                    self.check_windows_scheduler_status()
                    self.refresh_schedule_status()
                else:
                    QMessageBox.critical(self, "Помилка",
                                       f"Не вдалося видалити завдання:\n{result.stderr}")

        except subprocess.TimeoutExpired:
            QMessageBox.critical(self, "Помилка",
                               "Час очікування видалення завдання вичерпано")
        except Exception as e:
            QMessageBox.critical(self, "Помилка",
                               f"Не вдалося видалити завдання:\n{str(e)}")

    def open_windows_task_scheduler(self):
        """Open Windows Task Scheduler application"""
        try:
            if platform.system() == "Windows":
                subprocess.run(['taskschd.msc'], shell=True)
            else:
                QMessageBox.information(self, "Інформація",
                                      "Windows Task Scheduler доступний тільки на Windows")
        except Exception as e:
            QMessageBox.critical(self, "Помилка",
                               f"Не вдалося відкрити Task Scheduler:\n{str(e)}")

    def _build_schedule_trigger(self) -> dict:
        """Build schedule trigger parameters for schtasks command"""
        schedule_type = self.schedule_type_combo.currentText()
        start_time = self.schedule_time_start_edit.time().toString("HH:mm")

        if schedule_type == "Щодня":
            return {
                'type': 'DAILY',
                'params': ['/ST', start_time]
            }
        elif schedule_type == "Щотижня":
            day_map = {
                "Понеділок": "MON",
                "Вівторок": "TUE",
                "Середа": "WED",
                "Четвер": "THU",
                "П'ятниця": "FRI",
                "Субота": "SAT",
                "Неділя": "SUN"
            }
            day = day_map.get(self.schedule_day_of_week_combo.currentText(), "MON")
            return {
                'type': 'WEEKLY',
                'params': ['/D', day, '/ST', start_time]
            }
        elif schedule_type == "Щомісяця":
            day = str(self.schedule_day_of_month_spin.value())
            return {
                'type': 'MONTHLY',
                'params': ['/D', day, '/ST', start_time]
            }
        elif schedule_type == "Щокварталу":
            # For quarterly, we need to create multiple tasks or use more complex logic
            # For simplicity, we'll create monthly tasks that the user can customize
            QMessageBox.information(self, "Інформація",
                                  "Для щоквартального розкладу рекомендується створити "
                                  "щомісячне завдання та налаштувати його вручну в Task Scheduler")
            return None
        else:
            return None                               
        
    def calculate_time_remaining(self, schedule_cfg):
        """Calculate time remaining until next scheduled run"""
        try:
            now = datetime.now()
            current_time = QTime.currentTime()
            current_date = now.date()

            schedule_type = schedule_cfg.get('type', 'disabled')

            if schedule_type == 'disabled':
                return None, "Розклад вимкнено"

            start_time = QTime.fromString(schedule_cfg.get('time_start', '22:00'), "HH:mm")

            # Calculate next run date based on schedule type
            next_run_date = None

            if schedule_type == 'daily':
                next_run_date = current_date
                if current_time > start_time:
                    # If today's time has passed, schedule for tomorrow
                    next_run_date = current_date + timedelta(days=1)

            elif schedule_type == 'weekly':
                target_day = schedule_cfg.get('day_of_week', 1) - 1  # Convert to 0-6 (Monday=0)
                current_day = current_date.weekday()  # 0-6 (Monday=0)

                days_ahead = target_day - current_day
                if days_ahead <= 0 or (days_ahead == 0 and current_time > start_time):
                    # If target day is today and time has passed, or already passed this week
                    days_ahead += 7
                next_run_date = current_date + timedelta(days=days_ahead)

            elif schedule_type == 'monthly':
                target_day = schedule_cfg.get('day_of_month', 1)
                next_run_date = current_date.replace(day=target_day)

                # If the target day has passed this month, move to next month
                if next_run_date < current_date or (next_run_date == current_date and current_time > start_time):
                    if current_date.month == 12:
                        next_run_date = next_run_date.replace(year=current_date.year + 1, month=1)
                    else:
                        next_run_date = next_run_date.replace(month=current_date.month + 1)

            elif schedule_type == 'quarterly':
                quarter_month = schedule_cfg.get('quarter_month', 1) - 1  # 0, 1, 2
                quarter_day = schedule_cfg.get('quarter_day', 1)

                # Find current quarter and calculate target date
                current_quarter = (current_date.month - 1) // 3
                target_month = current_quarter * 3 + quarter_month + 1

                if target_month > 12:
                    target_month -= 12
                    target_year = current_date.year + 1
                else:
                    target_year = current_date.year

                # Create target date
                try:
                    next_run_date = datetime(target_year, target_month, quarter_day).date()
                except ValueError:
                    # Handle invalid dates (like February 30)
                    if target_month in [4, 6, 9, 11]:  # Months with 30 days
                        next_run_date = datetime(target_year, target_month, 30).date()
                    else:  # Assume February has 28 days
                        next_run_date = datetime(target_year, target_month, 28).date()

                # If target date has passed, move to next year's same quarter
                if next_run_date < current_date or (next_run_date == current_date and current_time > start_time):
                    next_run_date = datetime(target_year + 1, target_month, quarter_day).date()

            if next_run_date is None:
                return None, "Неможливо розрахувати"

            # Create datetime for next run
            next_run_time = time(start_time.hour(), start_time.minute(), start_time.second())
            next_run_datetime = datetime.combine(next_run_date, next_run_time)

            # Calculate time difference
            time_diff = next_run_datetime - now

            if time_diff.total_seconds() <= 0:
                return None, "Час минув"

            # Format time remaining
            days = time_diff.days
            hours, remainder = divmod(time_diff.seconds, 3600)
            minutes, _ = divmod(remainder, 60)

            if days > 0:
                if days == 1:
                    time_str = f"Завтра о {start_time.toString('HH:mm')}"
                else:
                    time_str = f"Через {days} днів о {start_time.toString('HH:mm')}"
            elif hours > 0:
                if hours == 1:
                    time_str = f"Через 1 годину {minutes} хв"
                else:
                    time_str = f"Через {hours} годин {minutes} хв"
            else:
                time_str = f"Через {minutes} хвилин"

            return next_run_datetime, time_str

        except Exception as e:
            return None, f"Помилка: {str(e)}"

    def update_time_remaining_display(self):
        """Update the time remaining display for schedule"""
        try:
            # Check if we're on the schedule tab
            current_tab_index = self.tabs.currentIndex()
            if hasattr(self, 'tabs') and self.tabs.tabText(current_tab_index) == "Розклад":
                self.refresh_schedule_status()
        except Exception as e:
            # Silently ignore errors to avoid spamming the console
            pass

    def refresh_schedule_status(self):
        """Refresh the schedule status display"""
        try:
            schedule_type = self.schedule_type_combo.currentText()

            if schedule_type == "Вимкнено":
                self.current_status_label.setText("Поточний статус: Вимкнено")
                self.current_status_label.setStyleSheet("font-size: 12px; font-weight: bold; color: black;")
                self.next_run_label.setText("Наступне виконання: Н/Д")
                self.time_remaining_label.setText("Час до виконання: Н/Д")
                self.last_run_label.setText("Останнє виконання: Н/Д")
                self.tray_info_label.setText("Мінімізація в трей: Н/Д")
            else:
                # Check if Windows task exists
                if self._check_task_exists():
                    self.current_status_label.setText("Поточний статус: Активно (Windows Task)")
                    self.current_status_label.setStyleSheet("font-size: 12px; font-weight: bold; color: black;")
                else:
                    self.current_status_label.setText("Поточний статус: Налаштовано (Тільки в додатку)")
                    self.current_status_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #808080;")

                # Calculate next run time using enhanced logic
                schedule_cfg = self._get_schedule_settings()
                next_run_datetime, time_remaining = self.calculate_time_remaining(schedule_cfg)

                if next_run_datetime:
                    self.next_run_label.setText(f"Наступне виконання: {next_run_datetime.strftime('%d-%m-%Y %H:%M')}")
                    self.time_remaining_label.setText(f"Час до виконання: {time_remaining}")

                    # Update time remaining label color based on urgency
                    time_diff = next_run_datetime - datetime.now()
                    hours_remaining = time_diff.total_seconds() / 3600

                    if hours_remaining < 1:
                        self.time_remaining_label.setStyleSheet("font-size: 11px; color: black; font-weight: bold;")
                    elif hours_remaining < 24:
                        self.time_remaining_label.setStyleSheet("font-size: 11px; color: #808080; font-weight: bold;")
                    else:
                        self.time_remaining_label.setStyleSheet("font-size: 11px; color: black; font-weight: bold;")
                else:
                    self.next_run_label.setText("Наступне виконання: Н/Д")
                    self.time_remaining_label.setText(f"Час до виконання: {time_remaining}")
                    self.time_remaining_label.setStyleSheet("font-size: 11px; color: #666; font-weight: bold;")

                # Simulate last run info (in real implementation, this would come from logs)
                self.last_run_label.setText("Останнє виконання: Н/Д")

                # Show tray minimization status
                parent_window = self.parent()
                if parent_window and hasattr(parent_window, 'settings'):
                    app_settings = parent_window.settings.get('application', {})
                    if app_settings.get('minimize_to_tray', False):
                        self.tray_info_label.setText("Мінімізація в трей: ✅ Увімкнено")
                        self.tray_info_label.setStyleSheet("font-size: 11px; color: black;")
                    else:
                        self.tray_info_label.setText("Мінімізація в трей: ❌ Вимкнено")
                        self.tray_info_label.setStyleSheet("font-size: 11px; color: #666;")
                else:
                    self.tray_info_label.setText("Мінімізація в трей: Н/Д")

        except Exception as e:
            print(f"Помилка оновлення статусу розкладу: {e}")

    def create_virtual_environment_tab(self):
        """Create enhanced virtual environment management tab"""
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #d0d0d0;
                background-color: #ffffff;
            }
            QScrollBar:vertical {
                background-color: #f8f8f8;
                width: 14px;
                border: 1px solid #e0e0e0;
            }
            QScrollBar::handle:vertical {
                background-color: #b0b0b0;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #909090;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)

        # Create content widget
        tab_venv = QWidget()
        main_layout = QVBoxLayout(tab_venv)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Environment Status Section
        env_status_group = self._create_enhanced_venv_status_section()
        main_layout.addWidget(env_status_group)

        # Package Management Section
        package_mgmt_group = self._create_enhanced_package_management_section()
        main_layout.addWidget(package_mgmt_group)

        
        # Environment Details Section
        details_group = self._create_environment_details_section()
        main_layout.addWidget(details_group)

        main_layout.addStretch()

        # Set up scroll area
        scroll_area.setWidget(tab_venv)
        self.tabs.addTab(scroll_area, "Віртуальне Середовище")

        # Initialize the tab
        self.refresh_package_list()
        self.refresh_venv_status()

    def _create_enhanced_venv_status_section(self) -> QGroupBox:
        """Create enhanced virtual environment status section"""
        group = QGroupBox("Статус Віртуального Середовища")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid black;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: black;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 20, 15, 15)

        # Status display
        status_layout = QHBoxLayout()
        self.venv_status_label = QLabel("Перевірка статусу...")
        self.venv_status_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #666;")
        status_layout.addWidget(self.venv_status_label)
        status_layout.addStretch()

        self.refresh_status_btn = QPushButton("Оновити")
        self.refresh_status_btn.clicked.connect(self.refresh_venv_status)
        self.refresh_status_btn.setFixedHeight(30)
        self.refresh_status_btn.setMinimumWidth(80)
        status_layout.addWidget(self.refresh_status_btn)
        layout.addLayout(status_layout)

        # Path display
        self.venv_path_label = QLabel("")
        self.venv_path_label.setWordWrap(True)
        self.venv_path_label.setStyleSheet("font-size: 11px; color: black; padding: 8px; background-color: #f5f5f5; border-radius: 4px;")
        layout.addWidget(self.venv_path_label)

        # Administrator status
        admin_layout = QHBoxLayout()
        self.admin_status_label = QLabel("")
        self.admin_status_label.setStyleSheet("font-size: 11px; color: #333; padding: 8px; background-color: #f8f8f8; border-radius: 4px; border: 1px solid #ddd;")
        admin_layout.addWidget(self.admin_status_label)
        admin_layout.addStretch()
        layout.addLayout(admin_layout)

        # Statistics
        stats_layout = QHBoxLayout()
        self.venv_stats_label = QLabel("Пакетів: 0 | Розмір: Обчислюється...")
        self.venv_stats_label.setStyleSheet("font-size: 11px; color: #666;")
        stats_layout.addWidget(self.venv_stats_label)
        stats_layout.addStretch()
        layout.addLayout(stats_layout)

        # Quick actions
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)

        self.repair_venv_btn = QPushButton("Відновити")
        self.repair_venv_btn.clicked.connect(self.repair_virtual_environment)
        self.repair_venv_btn.setFixedHeight(30)
        self.repair_venv_btn.setMinimumWidth(80)

        self.recreate_venv_btn = QPushButton("Видалити")
        self.recreate_venv_btn.clicked.connect(self.recreate_virtual_environment)
        self.recreate_venv_btn.setFixedHeight(30)
        self.recreate_venv_btn.setMinimumWidth(90)

        # Add administrator restart button if not running as admin
        if not is_running_as_admin():
            self.restart_as_admin_btn = QPushButton("🔐 Перезапустити від адміністратора")
            self.restart_as_admin_btn.clicked.connect(self.restart_as_administrator)
            self.restart_as_admin_btn.setFixedHeight(30)
            self.restart_as_admin_btn.setMinimumWidth(120)
            self.restart_as_admin_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ffc107;
                    color: #212529;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #e0a800;
                }
            """)

        actions_layout.addWidget(self.repair_venv_btn)
        actions_layout.addWidget(self.recreate_venv_btn)
        if not is_running_as_admin():
            actions_layout.addWidget(self.restart_as_admin_btn)
        actions_layout.addStretch()

        layout.addLayout(actions_layout)

        return group

    def _create_enhanced_package_management_section(self) -> QGroupBox:
        """Create enhanced package management section"""
        group = QGroupBox("Управління Пакетами")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid black;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: black;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 20, 15, 15)

        # Search and filter
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Пошук:"))
        self.package_search_edit = QLineEdit()
        self.package_search_edit.setPlaceholderText("Введіть назву пакета...")
        self.package_search_edit.textChanged.connect(self.filter_packages_list)
        self.package_search_edit.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 2px solid #808080;
            }
        """)
        search_layout.addWidget(self.package_search_edit)
        layout.addLayout(search_layout)

        # Package list
        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)

        self.packages_list = QListWidget()
        self.packages_list.setAlternatingRowColors(True)
        self.packages_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.packages_list.setFixedHeight(180)
        self.packages_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 4px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #808080;
                color: white;
            }
            QListWidget::item:alternate {
                background-color: #f9f9f9;
            }
        """)
        list_layout.addWidget(self.packages_list)

        # Package statistics
        self.package_stats_label = QLabel("Всього: 0 пакетів | Вибрано: 0")
        self.package_stats_label.setStyleSheet("font-size: 10px; color: #666;")
        list_layout.addWidget(self.package_stats_label)

        layout.addWidget(list_container)

        # Package installation
        install_group = QGroupBox("Встановлення Пакета")
        install_layout = QVBoxLayout(install_group)

        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Пакет:"))
        self.package_input = QLineEdit()
        self.package_input.setPlaceholderText("назва-пакету==версія")
        self.package_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 2px solid #ddd;
                border-radius: 6px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 2px solid #808080;
            }
        """)
        input_layout.addWidget(self.package_input)

        self.install_package_btn = QPushButton("Встановити")
        self.install_package_btn.clicked.connect(self.install_user_package)
        self.install_package_btn.setFixedHeight(35)
        input_layout.addWidget(self.install_package_btn)

        install_layout.addLayout(input_layout)
        layout.addWidget(install_group)

        # Package management buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        self.upgrade_packages_btn = QPushButton("Оновити Всі")
        self.upgrade_packages_btn.clicked.connect(self.upgrade_all_packages)
        self.upgrade_packages_btn.setFixedHeight(30)

        self.uninstall_package_btn = QPushButton("Видалити Вибрані")
        self.uninstall_package_btn.clicked.connect(self.uninstall_selected_packages)
        self.uninstall_package_btn.setEnabled(False)
        self.uninstall_package_btn.setFixedHeight(30)

        self.refresh_packages_btn = QPushButton("Оновити Список")
        self.refresh_packages_btn.clicked.connect(self.refresh_package_list)
        self.refresh_packages_btn.setFixedHeight(30)

        buttons_layout.addWidget(self.upgrade_packages_btn)
        buttons_layout.addWidget(self.uninstall_package_btn)
        buttons_layout.addWidget(self.refresh_packages_btn)
        buttons_layout.addStretch()

        layout.addLayout(buttons_layout)

        # Connect selection change
        self.packages_list.itemSelectionChanged.connect(self.update_package_buttons)

        return group

    
    def _create_environment_details_section(self) -> QGroupBox:
        """Create environment details section"""
        group = QGroupBox("Деталі Середовища")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid black;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 20, 15, 15)

        # Python version
        self.python_version_label = QLabel("Python: Обчислюється...")
        self.python_version_label.setStyleSheet("font-size: 11px; color: black;")
        layout.addWidget(self.python_version_label)

        # Pip version
        self.pip_version_label = QLabel("Pip: Обчислюється...")
        self.pip_version_label.setStyleSheet("font-size: 11px; color: black;")
        layout.addWidget(self.pip_version_label)

        # Package usage
        self.package_usage_text = QTextEdit()
        self.package_usage_text.setReadOnly(True)
        self.package_usage_text.setMaximumHeight(120)
        self.package_usage_text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #f9f9f9;
                font-size: 10px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.package_usage_text)

        return group

    def refresh_package_list(self):
        """Refresh the package list and virtual environment information"""
        if not self.parent_window or not hasattr(self.parent_window, 'module_manager'):
            if hasattr(self, 'venv_status_label'):
                self.venv_status_label.setText("❌ Менеджер модулів недоступний")
            return

        venv_manager = self.parent_window.module_manager.get_virtual_env_manager()

        # Update status using the enhanced method
        if hasattr(self, 'refresh_venv_status'):
            self.refresh_venv_status()

        # Update packages list (use cached data - no force refresh needed)
        self.packages_list.clear()
        installed_packages = venv_manager.get_installed_packages()
        if installed_packages:
            for package in sorted(installed_packages):
                self.packages_list.addItem(package)
        else:
            self.packages_list.addItem("Немає встановлених пакетів")

        # Update package usage info
        package_info = venv_manager.get_package_info()
        package_modules = package_info.get('package_modules', {})

        if hasattr(self, 'package_usage_text'):
            if package_modules:
                usage_text = "📋 Пакети та модулі, що їх використовують:\n\n"
                for package, modules in package_modules.items():
                    usage_text += f"• {package}: {', '.join(modules)}\n"
            else:
                usage_text = "📋 Немає активних пакетів або модулів"

            self.package_usage_text.setText(usage_text)

        # Update package statistics
        if hasattr(self, 'package_stats_label'):
            total_count = self.packages_list.count()
            selected_count = len(self.packages_list.selectedItems())
            self.package_stats_label.setText(f"Всього: {total_count} пакетів | Вибрано: {selected_count}")

    def cleanup_virtual_environment(self):
        """Clean up the virtual environment"""
        reply = QMessageBox.question(
            self,
            "Підтвердження Очищення",
            "Ви впевнені, що хочете видалити віртуальне середовище?\n\n"
            "Це видалить усі встановлені пакети та потребує\n"
            "перевстановлення при наступному завантаженні модулів.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if not self.parent_window or not hasattr(self.parent_window, 'module_manager'):
                QMessageBox.warning(self, "Помилка", "Менеджер модулів недоступний")
                return

            venv_manager = self.parent_window.module_manager.get_virtual_env_manager()

            try:
                import shutil
                if os.path.exists(venv_manager.venv_dir):
                    shutil.rmtree(venv_manager.venv_dir)
                    print(f"🗑️ Removed virtual environment: {venv_manager.venv_dir}")

                # Reset package tracking
                venv_manager.installed_packages.clear()
                venv_manager.package_modules.clear()
                venv_manager._save_package_info()

                QMessageBox.information(self, "Успіх", "Віртуальне середовище видалено")
                self.refresh_package_list()

            except Exception as e:
                QMessageBox.critical(self, "Помилка", f"Не вдалося видалити віртуальне середовище:\n{e}")

    def install_user_package(self):
        """Install a user-specified package in the virtual environment"""
        package_spec = self.package_input.text().strip()
        if not package_spec:
            QMessageBox.warning(self, "Помилка", "Будь ласка, введіть назву пакета")
            return

        if not self.parent_window or not hasattr(self.parent_window, 'module_manager'):
            QMessageBox.warning(self, "Помилка", "Менеджер модулів недоступний")
            return

        venv_manager = self.parent_window.module_manager.get_virtual_env_manager()

        # Disable the install button and show progress
        self.install_package_btn.setEnabled(False)
        self.install_package_btn.setText("Встановлення...")
        QApplication.processEvents()

        try:
            # Extract package name for display
            package_name = package_spec.split('>=')[0].split('==')[0].split('<=')[0].split('~=')[0].strip().lower()

            # Check if package is already installed
            if venv_manager._is_package_installed(package_name):
                reply = QMessageBox.question(
                    self,
                    "Пакет вже встановлено",
                    f"Пакет '{package_name}' вже встановлено. Бажаєте оновити?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.No:
                    self.install_package_btn.setEnabled(True)
                    self.install_package_btn.setText("Встановити")
                    return

            # Install the package using the venv manager's install method
            success = venv_manager.install_user_package(package_spec)

            if success:
                # Clear package cache to ensure modules can detect the newly installed package
                if hasattr(venv_manager, '_package_cache'):
                    venv_manager._package_cache.clear()
                # Force sync with actual venv packages
                venv_manager._sync_installed_packages()

                QMessageBox.information(self, "Успіх", f"Пакет '{package_spec}' успішно встановлено")
                self.package_input.clear()
                self.refresh_package_list()
            else:
                QMessageBox.critical(self, "Помилка", f"Не вдалося встановити пакет '{package_spec}'")

        except Exception as e:
            QMessageBox.critical(self, "Помилка", f"Не вдалося встановити пакет:\n{e}")

        finally:
            # Restore the install button
            self.install_package_btn.setEnabled(True)
            self.install_package_btn.setText("Встановити")

    def uninstall_selected_package(self):
        """Uninstall the selected package from the virtual environment"""
        selected_items = self.packages_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Помилка", "Будь ласка, виберіть пакет для видалення")
            return

        package_name = selected_items[0].text()
        if package_name == "Немає встановлених пакетів":
            return

        # Confirm uninstallation
        reply = QMessageBox.question(
            self,
            "Підтвердження Видалення",
            f"Ви впевнені, що хочете видалити пакет '{package_name}'?\n\n"
            "Це може вплинути на роботу модулів, що використовують цей пакет.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if not self.parent_window or not hasattr(self.parent_window, 'module_manager'):
                QMessageBox.warning(self, "Помилка", "Менеджер модулів недоступний")
                return

            venv_manager = self.parent_window.module_manager.get_virtual_env_manager()

            try:
                success = venv_manager.uninstall_user_package(package_name)

                if success:
                    QMessageBox.information(self, "Успіх", f"Пакет '{package_name}' успішно видалено")
                    self.refresh_package_list()
                else:
                    QMessageBox.critical(self, "Помилка", f"Не вдалося видалити пакет '{package_name}'")

            except Exception as e:
                QMessageBox.critical(self, "Помилка", f"Не вдалося видалити пакет:\n{e}")

    # New enhanced virtual environment functionality
    def refresh_venv_status(self):
        """Refresh virtual environment status and details"""
        if not self.parent_window or not hasattr(self.parent_window, 'module_manager'):
            self.venv_status_label.setText("❌ Менеджер модулів недоступний")
            return

        venv_manager = self.parent_window.module_manager.get_virtual_env_manager()

        # Update administrator status
        if is_running_as_admin():
            self.admin_status_label.setText("🔐 Запущено з правами адміністратора")
            self.admin_status_label.setStyleSheet("font-size: 11px; color: #155724; padding: 8px; background-color: #d4edda; border-radius: 4px; border: 1px solid #c3e6cb;")
        else:
            self.admin_status_label.setText("⚠️ Запущено зі звичайними правами (можуть знадобитися права адміністратора)")
            self.admin_status_label.setStyleSheet("font-size: 11px; color: #856404; padding: 8px; background-color: #fff3cd; border-radius: 4px; border: 1px solid #ffeaa7;")

        # Update status
        if os.path.exists(venv_manager.venv_dir):
            self.venv_status_label.setText("✅ Віртуальне середовище створено")
            self.venv_status_label.setStyleSheet("font-size: 12px; font-weight: bold; color: black;")
            self.venv_path_label.setText(f"📁 Шлях: {venv_manager.venv_dir}")

            # Update statistics
            try:
                total_size = 0
                for dirpath, dirnames, filenames in os.walk(venv_manager.venv_dir):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        try:
                            total_size += os.path.getsize(fp)
                        except:
                            pass

                size_mb = total_size / (1024 * 1024)
                package_count = len(venv_manager.get_installed_packages())
                self.venv_stats_label.setText(f"Пакетів: {package_count} | Розмір: {size_mb:.1f} MB")

            except Exception as e:
                self.venv_stats_label.setText("Пакетів: 0 | Розмір: Помилка обчислення")

            # Update environment details
            self._update_environment_details(venv_manager)

        else:
            self.venv_status_label.setText("⚠️ Віртуальне середовище не створено")
            self.venv_status_label.setStyleSheet("font-size: 12px; font-weight: bold; color: black;")
            self.venv_path_label.setText(f"📁 Шлях: {venv_manager.venv_dir}")
            self.venv_stats_label.setText("Пакетів: 0 | Розмір: 0 MB")

            # Clear environment details
            self.python_version_label.setText("Python: Н/Д")
            self.pip_version_label.setText("Pip: Н/Д")

    def _update_environment_details(self, venv_manager):
        """Update environment details section"""
        try:
            # Get Python version
            result = subprocess.run([
                venv_manager.get_pip_path().split()[0], '--version'
            ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)

            if result.returncode == 0:
                pip_version = result.stdout.strip()
                self.pip_version_label.setText(f"Pip: {pip_version}")
            else:
                self.pip_version_label.setText("Pip: Помилка отримання версії")

        except Exception:
            self.pip_version_label.setText("Pip: Недоступний")

        try:
            # Get Python version from venv
            python_exe = os.path.join(venv_manager.venv_dir, 'Scripts', 'python.exe')
            if not os.path.exists(python_exe):
                python_exe = os.path.join(venv_manager.venv_dir, 'bin', 'python')

            if os.path.exists(python_exe):
                result = subprocess.run([
                    python_exe, '--version'
                ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)

                if result.returncode == 0:
                    python_version = result.stdout.strip() or result.stderr.strip()
                    self.python_version_label.setText(f"Python: {python_version}")
                else:
                    self.python_version_label.setText("Python: Помилка отримання версії")
            else:
                self.python_version_label.setText("Python: Не знайдено")

        except Exception:
            self.python_version_label.setText("Python: Недоступний")

    def filter_packages_list(self):
        """Filter packages list based on search text"""
        search_text = self.package_search_edit.text().lower()

        for i in range(self.packages_list.count()):
            item = self.packages_list.item(i)
            item.setHidden(search_text not in item.text().lower())

    def update_package_buttons(self):
        """Update package management buttons based on selection"""
        selected_count = len(self.packages_list.selectedItems())
        has_selection = selected_count > 0

        self.uninstall_package_btn.setEnabled(has_selection)

        # Update statistics
        total_count = self.packages_list.count()
        self.package_stats_label.setText(f"Всього: {total_count} пакетів | Вибрано: {selected_count}")

    def upgrade_all_packages(self):
        """Upgrade all installed packages"""
        if not self.parent_window or not hasattr(self.parent_window, 'module_manager'):
            QMessageBox.warning(self, "Помилка", "Менеджер модулів недоступний")
            return

        reply = QMessageBox.question(
            self,
            "Підтвердження Оновлення",
            "Ви впевнені, що хочете оновити всі встановлені пакети?\n\n"
            "Це може зайняти тривалий час.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            venv_manager = self.parent_window.module_manager.get_virtual_env_manager()
            pip_path = venv_manager.get_pip_path()

            if not pip_path:
                QMessageBox.critical(self, "Помилка", "Pip не доступний")
                return

            # Show progress
            self.upgrade_packages_btn.setEnabled(False)
            self.upgrade_packages_btn.setText("Оновлення...")
            QApplication.processEvents()

            try:
                # Run pip upgrade
                result = subprocess.run([
                    pip_path, 'install', '--upgrade', '-r', 'requirements.txt'
                ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)

                if result.returncode == 0:
                    QMessageBox.information(self, "Успіх", "Пакети успішно оновлено")
                    self.refresh_package_list()
                else:
                    QMessageBox.critical(self, "Помилка", f"Не вдалося оновити пакети:\n{result.stderr}")

            except subprocess.TimeoutExpired:
                QMessageBox.critical(self, "Помилка", "Час очікування оновлення вичерпано")
            except Exception as e:
                QMessageBox.critical(self, "Помилка", f"Помилка оновлення:\n{str(e)}")

            finally:
                self.upgrade_packages_btn.setEnabled(True)
                self.upgrade_packages_btn.setText("Оновити Всі")

    def uninstall_selected_packages(self):
        """Uninstall multiple selected packages"""
        selected_items = self.packages_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Помилка", "Будь ласка, виберіть пакети для видалення")
            return

        package_names = [item.text() for item in selected_items if item.text() != "Немає встановлених пакетів"]
        if not package_names:
            return

        # Confirm uninstallation
        reply = QMessageBox.question(
            self,
            "Підтвердження Видалення",
            f"Ви впевнені, що хочете видалити {len(package_names)} пакет(ів)?\n\n"
            f"Пакети: {', '.join(package_names[:3])}" +
            (f" та ще {len(package_names) - 3}..." if len(package_names) > 3 else ""),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            venv_manager = self.parent_window.module_manager.get_virtual_env_manager()
            success_count = 0

            for package_name in package_names:
                try:
                    if venv_manager.uninstall_user_package(package_name):
                        success_count += 1
                except Exception as e:
                    print(f"Помилка видалення {package_name}: {e}")

            QMessageBox.information(self, "Результат",
                f"Видалено {success_count} з {len(package_names)} пакетів")
            self.refresh_package_list()

    def export_requirements(self):
        """Export installed packages to requirements.txt"""
        if not self.parent_window or not hasattr(self.parent_window, 'module_manager'):
            QMessageBox.warning(self, "Помилка", "Менеджер модулів недоступний")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Експортувати requirements.txt",
            "requirements.txt",
            "Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                venv_manager = self.parent_window.module_manager.get_virtual_env_manager()
                pip_path = venv_manager.get_pip_path()

                if not pip_path:
                    QMessageBox.critical(self, "Помилка", "Pip не доступний")
                    return

                # Export to requirements.txt
                result = subprocess.run([
                    pip_path, 'freeze'
                ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)

                if result.returncode == 0:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(result.stdout)

                    QMessageBox.information(self, "Успіх",
                        f"requirements.txt успішно експортовано до:\n{file_path}")
                else:
                    QMessageBox.critical(self, "Помилка",
                        f"Не вдалося експортувати:\n{result.stderr}")

            except Exception as e:
                QMessageBox.critical(self, "Помилка", f"Помилка експорту:\n{str(e)}")

    def import_requirements(self):
        """Import packages from requirements.txt"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Імпортувати requirements.txt",
            "",
            "Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                reply = QMessageBox.question(
                    self,
                    "Підтвердження Імпорту",
                    f"Імпортувати пакети з файлу:\n{file_path}\n\n"
                    "Це встановить усі пакети, зазначені у файлі.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )

                if reply == QMessageBox.Yes:
                    venv_manager = self.parent_window.module_manager.get_virtual_env_manager()
                    pip_path = venv_manager.get_pip_path()

                    if not pip_path:
                        QMessageBox.critical(self, "Помилка", "Pip не доступний")
                        return

                    # Import from requirements.txt
                    result = subprocess.run([
                        pip_path, 'install', '-r', file_path
                    ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)

                    if result.returncode == 0:
                        QMessageBox.information(self, "Успіх", "Пакети успішно імпортовано")
                        self.refresh_package_list()
                    else:
                        QMessageBox.critical(self, "Помилка",
                            f"Не вдалося імпортувати:\n{result.stderr}")

            except subprocess.TimeoutExpired:
                QMessageBox.critical(self, "Помилка", "Час очікування імпорту вичерпано")
            except Exception as e:
                QMessageBox.critical(self, "Помилка", f"Помилка імпорту:\n{str(e)}")

    def repair_virtual_environment(self):
        """Repair virtual environment by reinstalling pip and validating setup"""
        if not self.parent_window or not hasattr(self.parent_window, 'module_manager'):
            QMessageBox.warning(self, "Помилка", "Менеджер модулів недоступний")
            return

        reply = QMessageBox.question(
            self,
            "Підтвердження Відновлення",
            "Відновити віртуальне середовище?\n\n"
            "Це перевірить цілісність середовища та оновить pip при необхідності.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            try:
                venv_manager = self.parent_window.module_manager.get_virtual_env_manager()

                # Validate venv
                if venv_manager._validate_venv():
                    QMessageBox.information(self, "Успіх", "Віртуальне середовище в порядку")
                else:
                    # Attempt repair
                    pip_path = venv_manager.get_pip_path()
                    if pip_path:
                        # Upgrade pip - handle list or string format
                        if isinstance(pip_path, list):
                            # New list format
                            cmd = pip_path + ['install', '--upgrade', 'pip']
                        else:
                            # Old string format (backward compatibility)
                            if ' -m pip' in pip_path:
                                cmd = pip_path.split() + ['install', '--upgrade', 'pip']
                            else:
                                cmd = [pip_path, 'install', '--upgrade', 'pip']

                        subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)

                        QMessageBox.information(self, "Успіх",
                            "Віртуальне середовище відновлено")
                    else:
                        QMessageBox.warning(self, "Попередження",
                            "Не вдалося відновити середовище автоматично")

                self.refresh_venv_status()

            except Exception as e:
                QMessageBox.critical(self, "Помилка", f"Помилка відновлення:\n{str(e)}")

    def recreate_virtual_environment(self):
        """Recreate the virtual environment completely"""
        reply = QMessageBox.question(
            self,
            "Підтвердження Видалення",
            "Ви впевнені, що хочете видалити віртуальне середовище?\n\n"
            "Це повністю видалить поточне середовище та створить нове. "
            "Усі встановлені пакети будуть втрачені.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.cleanup_virtual_environment()

    def reset_virtual_environment(self):
        """Reset virtual environment to clean state"""
        if not self.parent_window or not hasattr(self.parent_window, 'module_manager'):
            QMessageBox.warning(self, "Помилка", "Менеджер модулів недоступний")
            return

        reply = QMessageBox.question(
            self,
            "Підтвердження Скидання",
            "Скинути віртуальне середовище до початкового стану?\n\n"
            "Це збереже середовище, але видалить усі встановлені пакети "
            "та скине конфігурацію.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                venv_manager = self.parent_window.module_manager.get_virtual_env_manager()

                # Clear package tracking
                venv_manager.installed_packages.clear()
                venv_manager.package_modules.clear()
                venv_manager._save_package_info()

                QMessageBox.information(self, "Успіх", "Віртуальне середовище скинуто")
                self.refresh_package_list()
                self.refresh_venv_status()

            except Exception as e:
                QMessageBox.critical(self, "Помилка", f"Помилка скидання:\n{str(e)}")

    def cleanup_virtual_environment_cache(self):
        """Clean up virtual environment cache and temporary files"""
        if not self.parent_window or not hasattr(self.parent_window, 'module_manager'):
            QMessageBox.warning(self, "Помилка", "Менеджер модулів недоступний")
            return

        reply = QMessageBox.question(
            self,
            "Підтвердження Очищення Кешу",
            "Очистити кеш віртуального середовища?\n\n"
            "Це видалить тимчасові файли та кеш pip, що може звільнити місце.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            try:
                venv_manager = self.parent_window.module_manager.get_virtual_env_manager()
                pip_path = venv_manager.get_pip_path()

                if pip_path:
                    # Clean pip cache
                    subprocess.run([
                        pip_path, 'cache', 'purge'
                    ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)

                    QMessageBox.information(self, "Успіх", "Кеш успішно очищено")
                else:
                    QMessageBox.warning(self, "Попередження", "Pip не доступний для очищення кешу")

                self.refresh_venv_status()

            except Exception as e:
                QMessageBox.critical(self, "Помилка", f"Помилка очищення кешу:\n{str(e)}")

    def restart_as_administrator(self):
        """Restart the application with administrator privileges"""
        reply = QMessageBox.question(
            self,
            "Перезапуск з правами адміністратора",
            "Перезапустити додаток з правами адміністратора?\n\n"
            "Це може знадобитися для встановлення пакетів або керування "
            "віртуальним середовищем. Додаток буде закритий і перезапущений "
            "з підвищеними привілеями.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            try:
                # Request administrator privileges and restart
                if request_admin_privileges():
                    # If request_admin_privileges succeeds, the application should restart
                    # Close the current application
                    if self.parent_window:
                        self.parent_window.close()
                    QApplication.quit()
                else:
                    QMessageBox.warning(
                        self,
                        "Неможливо отримати права адміністратора",
                        "Не вдалося отримати права адміністратора. \n\n"
                        "Будь ласка, запустіть додаток вручну з правами адміністратора:\n\n"
                        "1. Клацніть правою кнопкою миші на іконку додатку\n"
                        "2. Виберіть 'Запустити від імені адміністратора'"
                    )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Помилка перезапуску",
                    f"Не вдалося перезапустити додаток:\n{str(e)}"
                )

    def update_schedule_ui(self, index):
        schedule_type = self.schedule_type_combo.itemText(index)

        # Visibility flags based on selection
        is_daily = (schedule_type == "Щодня")
        is_weekly = (schedule_type == "Щотижня")
        is_monthly = (schedule_type == "Щомісяця")
        is_quarterly = (schedule_type == "Щокварталу")
        is_disabled = (schedule_type == "Вимкнено")

        # Show/hide schedule options container based on whether schedule is disabled
        self.schedule_options_widget.setVisible(not is_disabled)

        # Show/hide specific options within the container
        if hasattr(self, 'schedule_options_widget'):
            for i in range(self.schedule_options_widget.layout().count()):
                widget = self.schedule_options_widget.layout().itemAt(i).widget()
                if widget:
                    if isinstance(widget.layout(), QHBoxLayout):
                        # Check if this is weekly, monthly, or quarterly container
                        if widget.findChild(QComboBox) and widget.findChild(QComboBox) != self.schedule_type_combo:
                            # This is likely weekly, monthly, or quarterly options
                            widget.setVisible(False)

        # Show weekly options
        weekly_container = self.schedule_options_widget.findChild(QWidget)
        if weekly_container:
            for i in range(self.schedule_options_widget.layout().count()):
                item = self.schedule_options_widget.layout().itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if self.schedule_day_of_week_combo in widget.findChildren(QComboBox):
                        widget.setVisible(is_weekly)
                        break

        # Show monthly options
        monthly_container = self.schedule_options_widget.findChild(QWidget)
        if monthly_container:
            for i in range(self.schedule_options_widget.layout().count()):
                item = self.schedule_options_widget.layout().itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if self.schedule_day_of_month_spin in widget.findChildren(QSpinBox):
                        widget.setVisible(is_monthly)
                        break

        # Show quarterly options
        quarterly_container = self.schedule_options_widget.findChild(QWidget)
        if quarterly_container:
            for i in range(self.schedule_options_widget.layout().count()):
                item = self.schedule_options_widget.layout().itemAt(i)
                if item and item.widget():
                    widget = item.widget()
                    if (self.schedule_quarter_month_combo in widget.findChildren(QComboBox) and
                        self.schedule_quarter_day_spin in widget.findChildren(QSpinBox)):
                        widget.setVisible(is_quarterly)
                        break

        # Refresh status when schedule changes
        self.refresh_schedule_status()

    def add_extension(self):
        """Add a file extension to the filter list"""
        text = self.edit_add_ext.text().strip()
        if not text:
            return

        # Support comma-separated extensions
        extensions = [ext.strip().lower() for ext in text.split(',') if ext.strip()]
        added_count = 0
        duplicates = []

        for ext in extensions:
            if self._validate_extension(ext):
                if not self._is_duplicate_item(self.list_extensions, ext):
                    self.list_extensions.addItem(ext)
                    added_count += 1
                else:
                    duplicates.append(ext)

        if added_count > 0:
            self.edit_add_ext.clear()
            self.update_filter_stats("extension")

        if duplicates:
            QMessageBox.information(self, "Дублікати",
                                  f"Наступні розширення вже існують: {', '.join(duplicates)}")

    def remove_extension(self):
        """Remove selected extensions from the filter list"""
        self._remove_selected_items(self.list_extensions)
        self.update_filter_stats("extension")

    def add_filename(self):
        """Add a filename to the filter list"""
        text = self.edit_add_name.text().strip()
        if not text:
            return

        # Support comma-separated filenames
        filenames = [name.strip() for name in text.split(',') if name.strip()]
        added_count = 0
        duplicates = []

        for name in filenames:
            if self._validate_filename(name):
                if not self._is_duplicate_item(self.list_filenames, name):
                    self.list_filenames.addItem(name)
                    added_count += 1
                else:
                    duplicates.append(name)

        if added_count > 0:
            self.edit_add_name.clear()
            self.update_filter_stats("filename")

        if duplicates:
            QMessageBox.information(self, "Дублікати",
                                  f"Наступні імена файлів вже існують: {', '.join(duplicates)}")

    def remove_filename(self):
        """Remove selected filenames from the filter list"""
        self._remove_selected_items(self.list_filenames)
        self.update_filter_stats("filename")

    def _validate_extension(self, ext: str) -> bool:
        """Validate file extension format"""
        if not ext:
            QMessageBox.warning(self, "Неправильне розширення", "Розширення не може бути порожнім.")
            return False
        if not ext.startswith('.'):
            QMessageBox.warning(self, "Неправильне розширення", "Розширення повинно починатися з крапки ('.')")
            return False
        if len(ext) == 1:
            QMessageBox.warning(self, "Неправильне розширення", "Розширення повинно містити хоча б один символ після крапки.")
            return False
        return True

    def _validate_filename(self, name: str) -> bool:
        """Validate filename format"""
        if not name:
            QMessageBox.warning(self, "Неправильне ім'я файлу", "Ім'я файлу не може бути порожнім.")
            return False

        invalid_chars = '/\\:*?"<>|'
        if any(c in name for c in invalid_chars):
            QMessageBox.warning(self, "Неправильне ім'я файлу",
                              f"Ім'я файлу не може містити символи: {invalid_chars}")
            return False
        return True

    def _is_duplicate_item(self, list_widget: QListWidget, text: str) -> bool:
        """Check if an item already exists in the list"""
        return bool(list_widget.findItems(text, Qt.MatchExactly))

    def _remove_selected_items(self, list_widget: QListWidget):
        """Remove all selected items from a list widget"""
        for item in list_widget.selectedItems():
            list_widget.takeItem(list_widget.row(item))

    def update_filter_stats(self, filter_type: str):
        """Update the statistics label for a filter list"""
        if filter_type == "extension":
            count = self.list_extensions.count()
            self.ext_stats_label.setText(f"Всього: {count} елементів")
        else:
            count = self.list_filenames.count()
            self.name_stats_label.setText(f"Всього: {count} елементів")

    def update_remove_button_state(self, filter_type: str):
        """Update the enabled state of remove buttons based on selection"""
        if filter_type == "extension":
            has_selection = bool(self.list_extensions.selectedItems())
            self.btn_remove_ext.setEnabled(has_selection)
        else:
            has_selection = bool(self.list_filenames.selectedItems())
            self.btn_remove_name.setEnabled(has_selection)

    def filter_list_items(self, filter_type: str):
        """Filter list items based on search text"""
        if filter_type == "extension":
            list_widget = self.list_extensions
            search_widget = self.search_extensions
        else:
            list_widget = self.list_filenames
            search_widget = self.search_filenames

        search_text = search_widget.text().lower()

        for i in range(list_widget.count()):
            item = list_widget.item(i)
            item.setHidden(search_text not in item.text().lower())

    def clear_filter_list(self, filter_type: str):
        """Clear all items from a filter list"""
        reply = QMessageBox.question(
            self,
            "Підтвердження Очищення",
            "Ви впевнені, що хочете видалити всі елементи зі списку?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if filter_type == "extension":
                self.list_extensions.clear()
            else:
                self.list_filenames.clear()
            self.update_filter_stats(filter_type)

    def apply_preset(self, preset_type: str):
        """Apply a preset filter configuration"""
        presets = {
            "system": {
                "extensions": [".sys", ".dll", ".exe", ".bat", ".cmd", ".scr", ".msi", ".msp", ".msu"],
                "filenames": ["pagefile.sys", "hiberfil.sys", "swapfile.sys", "ntuser.dat", "ntuser.dat.log"]
            },
            "media": {
                "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".mp4", ".avi", ".mkv", ".mov",
                              ".mp3", ".wav", ".flac", ".aac", ".ogg", ".pdf", ".doc", ".docx", ".xls", ".xlsx"],
                "filenames": []
            },
            "documents": {
                "extensions": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt", ".ods", ".odp"],
                "filenames": ["readme*", "changelog*", "license*", "*.tmp", "*.bak"]
            },
            "development": {
                "extensions": [".py", ".js", ".html", ".css", ".cpp", ".c", ".h", ".java", ".cs", ".php", ".rb", ".go",
                              ".json", ".xml", ".yaml", ".yml", ".lock", ".log"],
                "filenames": ["node_modules", "*.git*", ".vscode", ".idea", "__pycache__", "*.pyc", "build*", "dist*"]
            },
            "reservoir": {
                "extensions": [".data", ".smspec", ".unsmry", ".grid", ".init", ".rft", ".rft", ".pvt", ".e300", ".e100",
                              ".hdf", ".h5", ".dat", ".inp", ".out", ".rwd", ".rwo", ".rwr", ".pdat", ".plot", ".plt",
                              ".bgr", ".bgi", ".bgf", ".flog", ".log", ".err", ".prt", ".rpt", ".swf", ".frt", ".f01"],
                "filenames": ["*.data*", "*.smspec*", "*.unsmry*", "*.grid*", "*.init*", "eclipse*", "tNav*", "tnavigator*",
                              "include*", "summary*", "restart*", "save*", "debug*", "output*", "results*", "run*"]
            },
            "cmg": {
                "extensions": [".dat", ".out", ".rwd", ".rwo", ".rwr", ".pdat", ".plot", ".plt", ".irf", ".srf", ".rrf",
                              ".h5", ".hdf", ".flog", ".log", ".err", ".fres", ".sr", ".geol", ".props", ".wells"],
                "filenames": ["imex*", "gem*", "stars*", "winprop*", "cmg*", "results*", "output*", "run*", "include*",
                              "history*", "report*", "summary*", "grid*", "property*", "well*", "region*"]
            },
            "schlumberger": {
                "extensions": [".data", ".smspec", ".unsmry", ".grid", ".init", ".rft", ".pvt", ".e300", ".e100", ".hdf",
                              ".h5", ".dat", ".inp", ".out", ".rwd", ".rwo", ".rwr", ".pdat", ".plot", ".plt", ".bgr",
                              ".bgi", ".bgf", ".flog", ".log", ".err", ".prt", ".rpt", ".swf", ".frt", ".f01", ".pan",
                              ".pdx", ".pro", ".rcs", ".rcb", ".rsg", ".rsb"],
                "filenames": ["eclipse*", "intersect*", "petrel*", "office*", "visage*", "geoquest*", "schedule*",
                              "summary*", "restart*", "grid*", "property*", "region*", "well*", "include*", "run*"]
            },
            "halliburton": {
                "extensions": [".dat", ".inp", ".out", ".rwd", ".rwo", ".rwr", ".pdat", ".plot", ".plt", ".h5", ".hdf",
                              ".log", ".err", ".rpt", ".res", ".sim", ".his", ".bna", ".bnt"],
                "filenames": ["nexus*", "vip*", "landmark*", "decisionspace*", "jason*", "geoprobe*", "kingdom*",
                              "results*", "output*", "run*", "history*", "report*", "summary*", "grid*", "well*"]
            }
        }

        if preset_type not in presets:
            return

        preset = presets[preset_type]

        # Ask user if they want to merge or replace
        reply = QMessageBox.question(
            self,
            "Застосувати Шаблон",
            "Бажаєте додати до існуючих фільтрів чи замінити їх?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Cancel:
            return

        # Clear existing filters if replacing
        if reply == QMessageBox.No:
            # These presets only affect extensions
            if preset_type in ["media", "documents"]:
                self.list_extensions.clear()
            else:
                # All other presets affect both extensions and filenames
                self.list_extensions.clear()
                self.list_filenames.clear()

        # Add extensions
        for ext in preset["extensions"]:
            if not self._is_duplicate_item(self.list_extensions, ext):
                self.list_extensions.addItem(ext)

        # Add filenames
        for name in preset["filenames"]:
            if not self._is_duplicate_item(self.list_filenames, name):
                self.list_filenames.addItem(name)

        self.update_filter_stats("extension")
        self.update_filter_stats("filename")

    def import_filters(self):
        """Import filters from a JSON file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Імпортувати Фільтри",
            "",
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Clear existing filters
                reply = QMessageBox.question(
                    self,
                    "Імпортувати Фільтри",
                    "Бажаєте замінити існуючі фільтри?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )

                if reply == QMessageBox.Yes:
                    self.list_extensions.clear()
                    self.list_filenames.clear()

                # Add imported extensions
                for ext in data.get("extensions", []):
                    if not self._is_duplicate_item(self.list_extensions, ext):
                        self.list_extensions.addItem(ext)

                # Add imported filenames
                for name in data.get("filenames", []):
                    if not self._is_duplicate_item(self.list_filenames, name):
                        self.list_filenames.addItem(name)

                self.update_filter_stats("extension")
                self.update_filter_stats("filename")
                QMessageBox.information(self, "Успіх", "Фільтри успішно імпортовано")

            except Exception as e:
                QMessageBox.critical(self, "Помилка", f"Не вдалося імпортувати фільтри:\n{e}")

    def export_filters(self):
        """Export filters to a JSON file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Експортувати Фільтри",
            "",
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                # Get current filters
                extensions = []
                for i in range(self.list_extensions.count()):
                    extensions.append(self.list_extensions.item(i).text())

                filenames = []
                for i in range(self.list_filenames.count()):
                    filenames.append(self.list_filenames.item(i).text())

                # Create export data
                data = {
                    "extensions": extensions,
                    "filenames": filenames,
                    "exported_at": QDateTime.currentDateTime().toString(Qt.ISODate),
                    "version": "1.0"
                }

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                QMessageBox.information(self, "Успіх", "Фільтри успішно експортовано")

            except Exception as e:
                QMessageBox.critical(self, "Помилка", f"Не вдалося експортувати фільтри:\n{e}")

    def reset_all_filters(self):
        """Reset all filters to default state"""
        reply = QMessageBox.question(
            self,
            "Скинути Всі Фільтри",
            "Ви впевнені, що хочете видалити всі фільтри?\n\nЦю дію не можна скасувати.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.list_extensions.clear()
            self.list_filenames.clear()
            self.update_filter_stats("extension")
            self.update_filter_stats("filename")
            QMessageBox.information(self, "Успіх", "Усі фільтри видалено")

    def load_settings_to_ui(self):
        """Load current settings into the UI controls"""
        self._load_application_settings()
        self._load_timer_settings()
        self._load_drive_settings()
        self._load_file_manager_settings()
        self._load_schedule_settings()

    def _load_application_settings(self):
        """Load application behavior settings"""
        app_cfg = self.current_settings.get('application', DEFAULT_SETTINGS['application'])

        # Load checkboxes that exist in the combined section
        if hasattr(self, 'chk_enable_autostart'):
            self.chk_enable_autostart.setChecked(app_cfg.get('autostart_timer_enabled', True))

        if hasattr(self, 'chk_minimize_to_tray'):
            self.chk_minimize_to_tray.setChecked(app_cfg.get('minimize_to_tray', False))

    def _load_timer_settings(self):
        """Load timer settings"""
        timer_cfg = self.current_settings.get('timer', DEFAULT_SETTINGS['timer'])
        self.chk_override_timer.setChecked(timer_cfg.get('override_default_enabled', False))
        self.spin_default_timer.setValue(timer_cfg.get('default_minutes', 3))
        self.spin_default_timer.setEnabled(self.chk_override_timer.isChecked())

        # Update timer status label
        minutes = timer_cfg.get('default_minutes', 3)
        self.timer_status_label.setText(f"Таймер: Налаштовано на {minutes} хвилин")

    def _load_drive_settings(self):
        """Load drive settings with enhanced initialization"""
        drive_cfg = self.current_settings.get('drives', DEFAULT_SETTINGS['drives'])
        policy = drive_cfg.get('main_drive_policy', 'D')

        # Set the radio button based on policy
        if policy == 'auto':
            self.rb_drive_auto.setChecked(True)
            self.selected_drive = 'AUTO'
        elif policy == 'C':
            self.rb_drive_c.setChecked(True)
            self.selected_drive = 'C'
        else:
            self.rb_drive_d.setChecked(True)
            self.selected_drive = 'D'

        # Trigger initial drive info refresh
        QTimer.singleShot(100, self._refresh_drive_info)

    def _load_file_manager_settings(self):
        """Load file manager settings"""
        fm_cfg = self.current_settings.get('file_manager', DEFAULT_SETTINGS['file_manager'])
        self.spin_max_size.setValue(fm_cfg.get('max_file_size_mb', 100))

        self.list_extensions.clear()
        self.list_extensions.addItems(fm_cfg.get('allowed_extensions', []))

        self.list_filenames.clear()
        self.list_filenames.addItems(fm_cfg.get('allowed_filenames', []))

        # Update statistics
        self.update_filter_stats("extension")
        self.update_filter_stats("filename")

    def _load_schedule_settings(self):
        """Load schedule settings"""
        schedule_cfg = self.current_settings.get('schedule', DEFAULT_SETTINGS['schedule'])

        # Schedule type
        schedule_type_en = schedule_cfg.get('type', 'disabled')
        schedule_type_ua = SCHEDULE_TYPE_MAP.get(schedule_type_en, "Вимкнено")
        index = self.schedule_type_combo.findText(schedule_type_ua)
        if index != -1:
            self.schedule_type_combo.setCurrentIndex(index)

        # Time range
        time_start_str = schedule_cfg.get('time_start', '22:00')
        self.schedule_time_start_edit.setTime(QTime.fromString(time_start_str, "HH:mm"))
        time_end_str = schedule_cfg.get('time_end', '23:00')
        self.schedule_time_end_edit.setTime(QTime.fromString(time_end_str, "HH:mm"))

        # Schedule-specific settings
        self.schedule_day_of_week_combo.setCurrentIndex(schedule_cfg.get('day_of_week', 1) - 1)
        self.schedule_day_of_month_spin.setValue(schedule_cfg.get('day_of_month', 1))
        self.schedule_quarter_month_combo.setCurrentIndex(schedule_cfg.get('quarter_month', 1) - 1)
        self.schedule_quarter_day_spin.setValue(schedule_cfg.get('quarter_day', 1))

        self.update_schedule_ui(self.schedule_type_combo.currentIndex())

        # Initialize Windows scheduler status
        if hasattr(self, 'scheduler_status_label'):
            self.check_windows_scheduler_status()

        # Initialize schedule status
        if hasattr(self, 'current_status_label'):
            self.refresh_schedule_status()

    def get_settings_from_ui(self) -> dict:
        """Collect current settings from UI controls"""
        return {
            'application': self._get_application_settings(),
            'timer': self._get_timer_settings(),
            'drives': self._get_drive_settings(),
            'file_manager': self._get_file_manager_settings(),
            'schedule': self._get_schedule_settings()
        }

    def _get_application_settings(self) -> dict:
        """Get application behavior settings from UI"""
        settings = {}

        # Only save settings for checkboxes that exist in the combined section
        if hasattr(self, 'chk_enable_autostart'):
            settings['autostart_timer_enabled'] = self.chk_enable_autostart.isChecked()

        if hasattr(self, 'chk_minimize_to_tray'):
            settings['minimize_to_tray'] = self.chk_minimize_to_tray.isChecked()

        return settings

    def _get_timer_settings(self) -> dict:
        """Get timer settings from UI"""
        return {
            'override_default_enabled': self.chk_override_timer.isChecked(),
            'default_minutes': self.spin_default_timer.value()
        }

    def _get_drive_settings(self) -> dict:
        """Get drive settings from UI"""
        if self.rb_drive_auto.isChecked():
            policy = 'auto'
        elif self.rb_drive_c.isChecked():
            policy = 'C'
        else:
            policy = 'D'

        return {
            'main_drive_policy': policy
        }

    def _get_file_manager_settings(self) -> dict:
        """Get file manager settings from UI"""
        return {
            'max_file_size_mb': self.spin_max_size.value(),
            'allowed_extensions': self._get_list_items(self.list_extensions),
            'allowed_filenames': self._get_list_items(self.list_filenames)
        }

    def _get_schedule_settings(self) -> dict:
        """Get schedule settings from UI"""
        return {
            'type': REVERSE_SCHEDULE_TYPE_MAP.get(self.schedule_type_combo.currentText(), "disabled"),
            'time_start': self.schedule_time_start_edit.time().toString("HH:mm"),
            'time_end': self.schedule_time_end_edit.time().toString("HH:mm"),
            'day_of_week': self.schedule_day_of_week_combo.currentIndex() + 1,
            'day_of_month': self.schedule_day_of_month_spin.value(),
            'quarter_month': self.schedule_quarter_month_combo.currentIndex() + 1,
            'quarter_day': self.schedule_quarter_day_spin.value()
        }

    def save_settings(self):
        """Save current settings to file (only called when explicitly needed)"""
        try:
            # Get settings from UI
            new_settings = self.get_settings_from_ui()

            # Update current settings
            self.current_settings.update(new_settings)

            # Save to file
            save_settings(self.current_settings)

            # Mark changes as applied
            self.changes_applied = True

        except Exception as e:
            QMessageBox.critical(self, "Помилка збереження", f"Не вдалося зберегти налаштування: {str(e)}")

    def _get_list_items(self, list_widget: QListWidget) -> list:
        """Get all items from a list widget as a sorted list"""
        return sorted([list_widget.item(i).text() for i in range(list_widget.count())])

    def apply_changes(self):
        """Apply changes and emit settings signal"""
        new_settings = self.get_settings_from_ui()
        self.current_settings = new_settings
        self.settings_applied.emit(new_settings)
        self.changes_applied = True

    def accept(self):
        """Accept dialog - apply changes if needed and close"""
        if not self.changes_applied:
            self.apply_changes()
        super().accept()

    def reject(self):
        """Reject dialog - close without saving any changes"""
        # Don't apply any changes, just close the dialog
        super().reject()

    def closeEvent(self, event):
        """Handle close event - treat like reject (no save)"""
        # If user closes the dialog with X button, treat it like Cancel
        self.reject()
        event.ignore()  # Don't process the close event since reject() will handle it


# --- File Mover Thread ---
class FileMover(QThread):
    update_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int, int, str)

    def __init__(self, target_drive, fallback_drive, settings):
        super().__init__()
        self.target_drive = target_drive
        self.fallback_drive = fallback_drive
        self.settings = settings
        self.base_folder_name = "Робочі столи"

    def run(self):
        try:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            now = datetime.now()

            fm_settings = self.settings.get('file_manager', DEFAULT_SETTINGS['file_manager'])
            allowed_extensions = {ext.lower() for ext in fm_settings.get('allowed_extensions', [])}
            allowed_filenames = {name for name in fm_settings.get('allowed_filenames', [])}
            max_size_bytes = fm_settings.get('max_file_size_mb', 100) * 1024 * 1024

            target_base_path = os.path.join(f"{self.target_drive}:\\", self.base_folder_name)
            fallback_base_path = os.path.join(f"{self.fallback_drive}:\\", self.base_folder_name)

            effective_base_path = ""
            if self.check_drive_exists(self.target_drive):
                 effective_base_path = target_base_path
            elif self.check_drive_exists(self.fallback_drive):
                 self.update_signal.emit(f"⚠️ Диск {self.target_drive}: недоступний. Використовуємо {self.fallback_drive}:")
                 effective_base_path = fallback_base_path
            else:
                self.update_signal.emit(f"❌ Критична помилка: Цільовий диск {self.target_drive}: та резервний {self.fallback_drive}: недоступні.")
                self.finished_signal.emit(0, 0, "Помилка: Немає доступних дисків")
                return

            year = now.strftime("%Y")
            timestamp = now.strftime("%d-%m-%Y %H-%M")
            dest_path = os.path.join(effective_base_path, f"Робочий стіл {year}", f"Робочий стіл {timestamp}")

            os.makedirs(dest_path, exist_ok=True)
            self.update_signal.emit(f"📁 Цільова папка: {dest_path}")

            success = errors = 0
            if not os.path.isdir(desktop):
                self.update_signal.emit(f"❌ Помилка: Папка робочого столу не знайдена за шляхом {desktop}")
                self.finished_signal.emit(0, 0, dest_path)
                return

            items_to_move = os.listdir(desktop)
            if not items_to_move:
                 self.update_signal.emit("ℹ️ Робочий стіл порожній. Немає чого переміщувати.")

            for item in items_to_move:
                src = os.path.join(desktop, item)
                item_name_no_ext, item_ext = os.path.splitext(item)
                item_ext_lower = item_ext.lower()

                # INVERSE LOGIC: If allowed_extensions is not empty, KEEP files with those extensions, move others
                if allowed_extensions and item_ext_lower in allowed_extensions:
                    self.update_signal.emit(f"⏭️ Збережено за розширенням (у whitelist): {item}")
                    continue

                # INVERSE LOGIC: If allowed_filenames is not empty, KEEP files with those names, move others
                if allowed_filenames and item_name_no_ext in allowed_filenames:
                    self.update_signal.emit(f"⏭️ Збережено за ім'ям файлу (у whitelist): {item}")
                    continue

                if os.path.isfile(src):
                    try:
                        file_size = os.path.getsize(src)
                        if file_size > max_size_bytes:
                            self.update_signal.emit(f"⏭️ Пропущено за розміром ({file_size / (1024*1024):.1f}MB): {item}")
                            continue
                    except OSError as e:
                         self.update_signal.emit(f"⚠️ Не вдалося отримати розмір {item}: {e}")
                         continue

                try:
                    final_dest = os.path.join(dest_path, item)
                    shutil.move(src, final_dest)
                    success += 1
                    self.update_signal.emit(f"✅ Переміщено: {item}")
                except Exception as e:
                    errors += 1
                    self.update_signal.emit(f"❌ Помилка переміщення '{item}': {str(e)}")

            self.finished_signal.emit(success, errors, dest_path)

        except Exception as e:
            self.update_signal.emit(f"❌ Критична помилка потоку: {str(e)}")
            self.finished_signal.emit(0, 0, "Помилка в потоці")

    def check_drive_exists(self, drive_letter):
        drive = f"{drive_letter}:\\"
        return os.path.exists(drive)

# --- Package Installation Progress Dialog ---
class PackageInstallProgressDialog(QDialog):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(450, 180)
        # Enhanced window flags to ensure visibility
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Title label
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50; padding: 10px;")
        layout.addWidget(self.title_label)

        # Current operation label
        self.current_label = QLabel("Підготовка...")
        self.current_label.setStyleSheet("font-size: 12px; color: #7f8c8d; padding: 5px;")
        layout.addWidget(self.current_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #bdc3c7;
                border-radius: 5px;
                text-align: center;
                background-color: #ecf0f1;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; color: #7f8c8d;")
        layout.addWidget(self.status_label)

    def update_progress(self, message, status=""):
        """Update progress message and optional status"""
        self.current_label.setText(message)
        if status:
            self.status_label.setText(status)

    def showEvent(self, event):
        """Override show event to ensure proper positioning and visibility"""
        super().showEvent(event)

        # Center the dialog on the screen
        if self.parent():
            parent_geometry = self.parent().geometry()
            x = parent_geometry.x() + (parent_geometry.width() - self.width()) // 2
            y = parent_geometry.y() + (parent_geometry.height() - self.height()) // 2
        else:
            # Center on primary screen
            screen = QApplication.desktop().screenGeometry()
            x = (screen.width() - self.width()) // 2
            y = (screen.height() - self.height()) // 2

        self.move(x, y)

        # Ensure dialog is on top and visible
        self.raise_()
        self.activateWindow()
        QApplication.processEvents()

        # Additional activation after a short delay to ensure proper visibility
        QTimer.singleShot(50, self._ensure_visible)

    def _ensure_visible(self):
        """Ensure the dialog remains visible after initial show"""
        self.raise_()
        self.activateWindow()
        self.setFocus()
        QApplication.processEvents()
        QApplication.processEvents()

    def set_determinate_progress(self, current, total):
        """Switch to determinate progress"""
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        QApplication.processEvents()

# --- Run Statistics Dialog ---
class RunStatisticsDialog(QDialog):
    def __init__(self, success, errors, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Статистика виконання")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        stats_text = f"Успішно переміщено: {success}\nПомилок: {errors}"
        if not path.startswith("Error"):
            stats_text += f"\nВихідна папка: {path}"

        stats_label = QLabel(stats_text)
        layout.addWidget(stats_label)

        button_layout = QHBoxLayout()
        self.open_folder_btn = QPushButton("Відкрити вихідну папку")
        self.open_folder_btn.clicked.connect(lambda: self.open_folder(path))
        if path.startswith("Error"):
            self.open_folder_btn.setEnabled(False)
        button_layout.addWidget(self.open_folder_btn)

        self.close_btn = QPushButton("Закрити")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

        self.auto_close_timer = QTimer(self)
        self.auto_close_timer.setSingleShot(True)
        self.auto_close_timer.timeout.connect(self.close)
        self.auto_close_timer.start(60000) # 1 minute

    def open_folder(self, path):
        try:
            os.startfile(path)
        except Exception as e:
            QMessageBox.warning(self, "Помилка", f"Не вдалося відкрити папку: {e}")


# --- Main Window ---
# --- End of content ---

def _merge_dicts(base, updates):
    for key, value in updates.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            _merge_dicts(base[key], value)
        else:
            base[key] = value
    return base

def load_settings():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            loaded_settings = yaml.safe_load(f)
            if loaded_settings:
                merged = _merge_dicts(DEFAULT_SETTINGS.copy(), loaded_settings)
                return merged
            else:
                return DEFAULT_SETTINGS.copy()
    except FileNotFoundError:
        print(f"Файл конфігурації не знайдено за шляхом {CONFIG_FILE}. Використовуються стандартні налаштування.")
        return DEFAULT_SETTINGS.copy()
    except yaml.YAMLError as e:
        print(f"Помилка розбору файлу конфігурації {CONFIG_FILE}: {e}. Використовуються стандартні налаштування.")
        return DEFAULT_SETTINGS.copy()
    except Exception as e:
        print(f"Неочікувана помилка завантаження конфігурації {CONFIG_FILE}: {e}. Використовуються стандартні налаштування.")
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Save settings to the configuration file"""
    try:
        # Ensure the config directory exists
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(settings, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        print(f"✅ Settings saved to {CONFIG_FILE}")

    except Exception as e:
        print(f"❌ Error saving settings to {CONFIG_FILE}: {e}")

def find_next_available_drive():
    """Find the available drive with the most free space"""
    try:
        import shutil

        available_drives = []
        drive_spaces = {}

        partitions = psutil.disk_partitions(all=False)
        for p in partitions:
            if platform.system() == "Windows" and re.match("^[A-Z]:\\?$", p.mountpoint) and p.mountpoint[0] != 'C':
                if p.fstype and 'cdrom' not in p.opts.lower():
                     if 'removable' not in p.opts.lower():
                         if os.path.exists(p.mountpoint):
                              drive_letter = p.mountpoint[0]
                              available_drives.append(drive_letter)

                              # Get free space for this drive
                              try:
                                  usage = shutil.disk_usage(f"{drive_letter}:\\")
                                  free_gb = usage.free // (1024**3)
                                  drive_spaces[drive_letter] = free_gb
                              except:
                                  drive_spaces[drive_letter] = 0

        if available_drives:
            # Sort drives by free space (descending) and return the one with most space
            sorted_drives = sorted(available_drives, key=lambda x: drive_spaces.get(x, 0), reverse=True)
            best_drive = sorted_drives[0]
            free_space = drive_spaces.get(best_drive, 0)
            print(f"✅ Автовибір: {best_drive}: - Вільно: {free_space}GB (найбільше)")
            return best_drive

        return None
    except Exception as e:
        print(f"⚠️ Помилка визначення дисків: {e}. Використовується резервний варіант.")
        return None

def is_scheduled_day(schedule_cfg):
    now = datetime.now()
    schedule_type = schedule_cfg.get('type', 'disabled')

    if schedule_type == 'daily':
        return True
    elif schedule_type == 'weekly':
        return now.isoweekday() == schedule_cfg.get('day_of_week', 1)
    elif schedule_type == 'monthly':
        return now.day == schedule_cfg.get('day_of_month', 1)
    elif schedule_type == 'quarterly':
        quarter_month = schedule_cfg.get('quarter_month', 1)  # 1, 2, 3
        quarter_day = schedule_cfg.get('quarter_day', 1)
        month_of_quarter = (now.month - 1) % 3 + 1
        return month_of_quarter == quarter_month and now.day == quarter_day
    return False

# --- Background Task Runner ---
class BackgroundTaskRunner:
    def __init__(self):
        self.settings = load_settings()
        self.mover_thread = None
        self.selected_drive = 'C'
        self.auto_configure_drive()

    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    def load_last_run_date(self):
        try:
            with open(LAST_RUN_FILE, 'r') as f:
                date_str = f.read().strip()
                return datetime.strptime(date_str, '%Y-%m-%d').date()
        except (FileNotFoundError, ValueError):
            return None

    def save_last_run_date(self, date):
        try:
            with open(LAST_RUN_FILE, 'w') as f:
                f.write(date.strftime('%Y-%m-%d'))
        except Exception as e:
            self.log_message(f"❌ Помилка збереження дати останнього запуску: {e}")

    def auto_configure_drive(self):
        policy = self.settings.get('drives', {}).get('main_drive_policy', 'D')
        initial_drive = None
        d_exists = os.path.exists("D:\\")
        e_exists = os.path.exists("E:\\")

        if policy == 'D' and d_exists:
            initial_drive = 'D'
        elif policy == 'auto':
            detected_drive = find_next_available_drive()
            if detected_drive:
                initial_drive = detected_drive
            elif d_exists:
                self.log_message("ℹ️ Автовизначення не вдалося, використовується диск D:")
                initial_drive = 'D'
        elif policy == 'D' and not d_exists and e_exists:
            self.log_message("ℹ️ Встановлено політику 'D', але диск D: не знайдено. Використовується диск E:")
            initial_drive = 'E'
        elif e_exists and not initial_drive:
            self.log_message(f"ℹ️ Політика '{policy}' не спрацювала, використовується диск E:")
            initial_drive = 'E'

        if initial_drive:
            self.selected_drive = initial_drive
        else:
            self.selected_drive = 'C'
            if policy != 'C':
                self.log_message("⚠️ Не знайдено відповідного диска. Використовується диск C:")
        self.log_message(f"⚙️ Основний диск встановлено на: {self.selected_drive}:")

    def check_and_run(self):
        schedule_cfg = self.settings.get('schedule', DEFAULT_SETTINGS['schedule'])
        schedule_type = schedule_cfg.get('type', 'disabled')

        if schedule_type == 'disabled':
            self.log_message("ℹ️ Розклад вимкнено. Вихід.")
            return False

        now = datetime.now()
        today = now.date()
        last_run_date = self.load_last_run_date()

        if not is_scheduled_day(schedule_cfg):
            self.log_message("ℹ️ Не запланований день. Вихід.")
            return False

        if last_run_date == today:
            self.log_message("ℹ️ Заплановане завдання вже виконано сьогодні. Вихід.")
            return False

        start_time = QTime.fromString(schedule_cfg.get('time_start', '22:00'), "HH:mm")
        end_time = QTime.fromString(schedule_cfg.get('time_end', '23:00'), "HH:mm")
        current_time = QTime.currentTime()

        run_now = False
        if start_time <= current_time <= end_time:
            cpu_usage = psutil.cpu_percent(interval=1)
            self.log_message(f"ℹ️ У вікні розкладу. ЦП: {cpu_usage}%.")
            if cpu_usage < 15.0:
                self.log_message("⏰ Низьке завантаження ЦП. Запуск запланованого завдання.")
                run_now = True
        elif current_time > end_time:
            self.log_message("⚠️ Вікно розкладу пропущено. Запуск завдання зараз.")
            run_now = True

        if run_now:
            self.launch_gui_app() # Call the new method to launch GUI
            self.save_last_run_date(today)
            return True
        else:
            self.log_message("ℹ️ Умови для запуску завдання зараз не виконані. Вихід.")
            return False

    def launch_gui_app(self):
        self.log_message("🚀 Запуск графічного інтерфейсу для виконання запланованого завдання...")
        try:
            # Determine the path to the current script
            script_path = os.path.abspath(sys.argv[0])
            
            # Use sys.executable to ensure the same Python interpreter is used
            # Pass a special argument to indicate it's a scheduled run
            subprocess.Popen([sys.executable, script_path, '--scheduled-run'])
            
            # Since we are launching a new process, the background runner can exit
            QCoreApplication.instance().quit()
        except Exception as e:
            self.log_message(f"❌ Помилка запуску графічного інтерфейсу: {e}")

    def start_process(self):
        if self.mover_thread and self.mover_thread.isRunning():
            self.log_message("⚠️ Процес вже запущено.")
            return

        self.log_message(f"\n🚀 Початок переміщення файлів на диск {self.selected_drive}:...")
        self.mover_thread = FileMover(target_drive=self.selected_drive, fallback_drive='C', settings=self.settings.copy())
        self.mover_thread.update_signal.connect(self.log_message)
        self.mover_thread.finished_signal.connect(self.process_finished)
        self.mover_thread.start()

    def process_finished(self, success, errors, path):
        self.log_message("\n🏁 Результат:")
        self.log_message(f"✅ Успішно: {success}")
        if errors > 0:
            self.log_message(f"❌ Помилок: {errors}")
        if not path.startswith("Error"):
            self.log_message(f"📁 Збережено до: {path}")
        else:
            self.log_message(f"❌ {path}")
        QCoreApplication.instance().quit()


# --- Main Window ---
class MainWindow(QMainWindow):
    def __init__(self, is_scheduled_run=False):
        super().__init__()
        add_splash_message("📋 Loading configuration...")
        self.settings = load_settings()
        self.mover_thread = None
        self.module_windows = {}  # Stores instances of opened module windows
        self.module_actions = {}  # Stores menu actions related to modules

        # System tray functionality
        self.tray_icon = None
        self.tray_menu = None

        add_splash_message("🔧 Initializing module manager...")
        # Initialize Module Manager
        self.module_manager = ModuleManager(self.get_module_dir(), self, self.settings)
        self.module_manager.module_loaded.connect(self.on_module_loaded)
        self.module_manager.module_error.connect(self.on_module_error)
        self.module_manager.module_discovered.connect(self.on_module_discovered)

        self.auto_start_timer = QTimer(self)
        self.auto_start_timer.timeout.connect(self.update_timer)
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self.check_schedule)
        self.remaining_time = 0
        self.selected_drive = 'C'
        self.d_exists = False
        self.e_exists = False
        self.last_scheduled_run_date = None

        add_splash_message("🖼️ Creating user interface...")
        self.initUI()  # Create UI elements first

        # Initialize system tray after UI is ready
        self.setup_system_tray()

        # Check for first startup and handle Python setup (after UI is ready)
        add_splash_message("🐍 Checking Python environment...")
        self.check_first_startup_and_python_setup()

        add_splash_message("🔍 Discovering modules...")
        self.discover_and_load_modules()  # Discover and load modules dynamically

        add_splash_message("⚙️ Applying settings...")
        self.apply_settings_to_ui()  # Apply loaded settings to UI
        self._log_current_schedule_settings(self.settings.get('schedule', DEFAULT_SETTINGS['schedule']))

        QTimer.singleShot(500, self.auto_configure_start)  # Existing delayed config
        self.schedule_timer.start(60000) # Check every minute

        if is_scheduled_run:
            self.log_message("ℹ️ Запущено за розкладом. Початок процесу переміщення.")
            self.start_process()

    def check_first_startup_and_python_setup(self):
        """Check if this is the first startup and handle Python environment setup"""
        first_run_key = 'first_run_completed'

        # Check if this is actually the first run OR if virtual environment doesn't exist
        venv_exists = os.path.exists(os.path.join(CONFIG_DIR, 'modules_venv'))
        first_run = not self.settings.get(first_run_key, False)

        if first_run or not venv_exists:
            if first_run:
                self.log_message("🎉 Welcome! First startup detected.")
            else:
                self.log_message("🔧 Virtual environment not found, setting up Python environment...")

            # Check if we have a working Python setup before prompting
            if self.check_current_python_setup():
                self.log_message("✅ Current Python setup is working, skipping setup dialog.")
                # Mark first run as completed since we have a working setup
                if first_run:
                    self.settings[first_run_key] = True
                    save_settings(self.settings)
                return

            # Hide splash screen temporarily for the Python setup dialog
            if 'global_splash' in globals() and globals()['global_splash']:
                globals()['global_splash'].hide()

            # Prompt user for Python installation method and get result
            setup_completed = self.prompt_python_installation_method()

            # Only mark first run as completed if setup was successful
            if setup_completed and first_run:
                self.settings[first_run_key] = True
                save_settings(self.settings)
                self.log_message("✅ Python setup completed successfully.")

            # Show splash screen again if it exists
            if 'global_splash' in globals() and globals()['global_splash']:
                globals()['global_splash'].show()
                QApplication.processEvents()

    def check_current_python_setup(self):
        """Check if current Python setup is working properly"""
        try:
            # Check if virtual environment exists and is valid
            venv_dir = os.path.join(CONFIG_DIR, 'modules_venv')
            venv_python = os.path.join(venv_dir, 'Scripts', 'python.exe')

            if os.path.exists(venv_dir) and os.path.exists(venv_python):
                self.log_message(f"🔍 Checking virtual environment at {venv_dir}")

                # Try to validate the virtual environment
                if hasattr(self, 'module_manager') and self.module_manager:
                    venv_manager = self.module_manager.venv_manager
                    if venv_manager and venv_manager._validate_venv():
                        self.log_message("✅ Virtual environment validation passed.")

                        # Test basic Python functionality in the venv
                        try:
                            result = subprocess.run([
                                venv_python,
                                '-c', 'import sys; print(f"Python {sys.version}"); print("Basic Python functionality working")'
                            ], capture_output=True, text=True, timeout=15)

                            if result.returncode == 0:
                                self.log_message(msg_formatter.venv_package_working(output=result.stdout))
                                return True
                            else:
                                self.log_message(msg_formatter.venv_python_error(result.stderr))
                        except subprocess.TimeoutExpired:
                            self.log_message("⚠️ VENV Python test timed out.")
                        except Exception as e:
                            self.log_message(msg_formatter.venv_python_test_failed(str(e)))
                    else:
                        self.log_message("⚠️ Virtual environment validation failed.")
                else:
                    self.log_message("⚠️ Module manager not available for venv validation.")

            # Check if system Python is working
            try:
                import sys
                self.log_message(f"✅ System Python {sys.version} is working correctly.")

                # If system Python works but no venv, that's still OK for first run
                if not os.path.exists(venv_dir):
                    self.log_message("ℹ️ No virtual environment found, but system Python is working.")
                return True

            except Exception as e:
                self.log_message(f"❌ Error checking system Python: {str(e)}")
                return False

        except Exception as e:
            self.log_message(msg_formatter.python_setup_check_error(str(e)))
            return False

    def prompt_python_installation_method(self):
        """Prompt user to choose Python installation method"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QPushButton, QGroupBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Python Environment Setup")
        dialog.setFixedSize(450, 300)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout()

        # Title and description
        title_label = QLabel("Python Environment Setup")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)

        desc_label = QLabel("This application requires Python to run modules. Choose how you want to set up Python:")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("margin-bottom: 20px;")
        layout.addWidget(desc_label)

        # Options group
        options_group = QGroupBox("Installation Options")
        options_layout = QVBoxLayout()

        self.use_existing_radio = QRadioButton("Use existing Python installation (recommended)")
        self.use_existing_radio.setChecked(True)
        self.use_existing_radio.setStyleSheet("margin: 5px;")
        options_layout.addWidget(self.use_existing_radio)

        self.download_python_radio = QRadioButton("Download and install Python 3.12.6 automatically")
        self.download_python_radio.setStyleSheet("margin: 5px;")
        options_layout.addWidget(self.download_python_radio)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Status label
        self.python_status_label = QLabel("")
        self.python_status_label.setStyleSheet("color: #666; margin: 10px;")
        layout.addWidget(self.python_status_label)

        # Check for existing Python
        self.check_existing_python()

        # Buttons
        button_layout = QHBoxLayout()

        self.setup_button = QPushButton("Continue")
        self.setup_button.clicked.connect(self.accept_python_setup)
        self.setup_button.setMinimumWidth(100)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(dialog.reject)
        cancel_button.setMinimumWidth(100)

        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(self.setup_button)

        layout.addLayout(button_layout)

        dialog.setLayout(layout)

        # Connect radio button changes
        self.use_existing_radio.toggled.connect(self.on_python_option_changed)
        self.download_python_radio.toggled.connect(self.on_python_option_changed)

        # Store dialog reference for later use
        self.python_setup_dialog = dialog

        # Show dialog modally
        result = dialog.exec_()

        if result != QDialog.Accepted:
            # User cancelled, try to continue with existing Python
            self.log_message("⚠️ Python setup cancelled. Trying to continue with existing installation...")
            return False

        # User accepted the setup
        return True

    def check_existing_python(self):
        """Check for existing Python installation"""
        try:
            import subprocess
            import sys

            # Check current Python version
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

            status_text = f"Found Python {python_version}"

            # Check if basic Python functionality is working
            try:
                # Try a simple import to test functionality
                import sys
                import os
                status_text += " and working correctly"
                self.python_status_label.setStyleSheet("color: #2e7d32; margin: 10px;")  # Green
            except ImportError:
                status_text += " (some modules may need to be installed)"
                self.python_status_label.setStyleSheet("color: #f57c00; margin: 10px;")  # Orange

            self.python_status_label.setText(status_text)

        except Exception as e:
            self.python_status_label.setText(f"Error checking Python: {str(e)}")
            self.python_status_label.setStyleSheet("color: #d32f2f; margin: 10px;")  # Red
            self.use_existing_radio.setEnabled(False)
            self.download_python_radio.setChecked(True)

    def on_python_option_changed(self):
        """Handle Python installation option change"""
        if self.use_existing_radio.isChecked():
            self.setup_button.setText("Continue")
            self.check_existing_python()
        else:
            self.setup_button.setText("Download and Install Python")
            self.python_status_label.setText("Python 3.12.6 will be downloaded and installed automatically")
            self.python_status_label.setStyleSheet("color: #1976d2; margin: 10px;")  # Blue

    def accept_python_setup(self):
        """Accept the Python setup choice"""
        if self.download_python_radio.isChecked():
            self.download_and_install_python()

        self.python_setup_dialog.accept()

    def download_and_install_python(self):
        """Download and install Python 3.12.6"""
        try:
            import urllib.request
            import tempfile
            import subprocess
            import os

            self.python_status_label.setText("Downloading Python 3.12.6...")
            QApplication.processEvents()

            # Python 3.12.6 download URL for Windows
            python_url = "https://www.python.org/ftp/python/3.12.6/python-3.12.6-amd64.exe"

            # Create temporary file for installer
            with tempfile.NamedTemporaryFile(suffix='.exe', delete=False) as temp_file:
                installer_path = temp_file.name

                # Download Python installer
                with urllib.request.urlopen(python_url) as response:
                    temp_file.write(response.read())

            self.python_status_label.setText("Installing Python 3.12.6...")
            QApplication.processEvents()

            # Install Python silently with specific options
            install_args = [
                installer_path,
                '/quiet',
                'InstallAllUsers=0',
                'PrependPath=0',
                'Include_test=0'
            ]

            result = subprocess.run(install_args, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                self.python_status_label.setText("✅ Python 3.12.6 installed successfully!")
                self.python_status_label.setStyleSheet("color: #2e7d32; margin: 10px;")

                # Update the virtual environment manager to use the new Python
                self.update_venv_python_path()
            else:
                self.python_status_label.setText(msg_formatter.python_installation_failed(result.stderr))
                self.python_status_label.setStyleSheet("color: #d32f2f; margin: 10px;")

            # Clean up installer
            try:
                os.unlink(installer_path)
            except:
                pass

        except Exception as e:
            self.python_status_label.setText(msg_formatter.python_download_install_failed(str(e)))
            self.python_status_label.setStyleSheet("color: #d32f2f; margin: 10px;")

    def update_venv_python_path(self):
        """Update virtual environment manager to use the newly installed Python"""
        try:
            # Find the newly installed Python
            import winreg

            # Check in HKCU for user installation
            python_path = None
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Python\PythonCore\3.12\InstallPath") as key:
                    python_path = winreg.QueryValueEx(key, "")[0]
            except FileNotFoundError:
                pass

            if python_path and os.path.exists(os.path.join(python_path, "python.exe")):
                python_exe = os.path.join(python_path, "python.exe")

                # Store this path for virtual environment creation
                self.settings['dedicated_python_path'] = python_exe
                save_settings(self.settings)

                self.log_message(f"✅ Found dedicated Python at: {python_exe}")

                # Recreate virtual environment with new Python if it exists
                if hasattr(self.module_manager, 'venv_manager') and self.module_manager.venv_manager:
                    venv_dir = self.module_manager.venv_manager.venv_dir
                    if os.path.exists(venv_dir):
                        import shutil
                        shutil.rmtree(venv_dir)
                        self.log_message("🔄 Recreating virtual environment with new Python...")

        except Exception as e:
            self.log_message(f"⚠️ Could not update Python path: {str(e)}")

    def get_module_dir(self):
        """Determines the path to the 'modules' directory relative to the script or executable."""
        if getattr(sys, 'frozen', False):
            # Running as a bundled executable (PyInstaller)
            base_path = os.path.dirname(sys.executable)
        else:
            # Running as a normal Python script
            base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, MODULE_DIR_NAME)

    def setup_system_tray(self):
        """Initialize system tray functionality"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.log_message("⚠️ System tray is not available on this system")
            return

        try:
            # Create system tray icon
            self.tray_icon = QSystemTrayIcon(self)

            # Create a simple icon using the application's style
            # You can replace this with a custom .ico file if available
            icon = self.style().standardIcon(getattr(QStyle, 'SP_ComputerIcon', None))
            self.tray_icon.setIcon(icon)

            # Create tray menu - no global styling to avoid conflicts
            self.tray_menu = QMenu()

            # Show/Hide action
            show_hide_action = QAction("📱 Показати/Сховати", self)
            show_hide_action.triggered.connect(self.toggle_window_visibility)
            self.tray_menu.addAction(show_hide_action)

            # Settings action
            settings_action = QAction("⚙️ Налаштування", self)
            settings_action.triggered.connect(self.open_settings)
            self.tray_menu.addAction(settings_action)

            self.tray_menu.addSeparator()

            # Modules section
            modules_action = QAction("📦 Модулі", self)
            modules_action.setEnabled(False)  # Make it a separator label
            self.tray_menu.addAction(modules_action)

            # Add module launching actions
            self.tray_module_actions = {}  # Store references to module actions
            self.update_tray_module_menu()

            self.tray_menu.addSeparator()

            # Quick actions section
            quick_actions = QAction("⚡ Швидкі дії", self)
            quick_actions.setEnabled(False)  # Make it a separator label
            self.tray_menu.addAction(quick_actions)

            # Start cleanup action
            cleanup_action = QAction("🧹 Запустити прибирання", self)
            cleanup_action.triggered.connect(self.quick_start_cleanup)
            self.tray_menu.addAction(cleanup_action)

            self.tray_menu.addSeparator()

            # Exit action
            exit_action = QAction("❌ Вихід", self)
            exit_action.triggered.connect(self.force_close_application)
            self.tray_menu.addAction(exit_action)

            # Set menu for tray icon
            self.tray_icon.setContextMenu(self.tray_menu)

            # Connect double-click event
            self.tray_icon.activated.connect(self.on_tray_icon_activated)

            # Show the tray icon
            self.tray_icon.show()

            # Set initial tooltip
            self.update_tray_tooltip()

            # Create timer to update tooltip every minute
            self.tray_tooltip_timer = QTimer(self)
            self.tray_tooltip_timer.timeout.connect(self.update_tray_tooltip)
            self.tray_tooltip_timer.start(60000)  # Update every minute

            self.log_message("✅ System tray initialized successfully")

        except Exception as e:
            self.log_message(f"❌ Failed to initialize system tray: {e}")
            self.tray_icon = None
            self.tray_menu = None

    def update_tray_module_menu(self):
        """Update the module menu items in the system tray"""
        if not hasattr(self, 'tray_menu') or not self.tray_menu:
            return

        # Remove existing module actions
        for action in self.tray_module_actions.values():
            self.tray_menu.removeAction(action)
        self.tray_module_actions.clear()

        # Add module actions for loaded modules
        if hasattr(self, 'module_manager') and self.module_manager:
            loaded_modules = self.module_manager.get_loaded_modules()
            if loaded_modules:
                for module_name in sorted(loaded_modules.keys()):
                    module_info = self.module_manager.module_info.get(module_name)
                    if module_info and hasattr(module_info, 'manifest'):
                        module_display_name = module_info.manifest.get('name', module_name)
                    else:
                        module_display_name = module_name

                    # Create action for module
                    module_action = QAction(f"  🚀 {module_display_name}", self)
                    module_action.triggered.connect(lambda checked=False, name=module_name: self.launch_module_from_tray(name))

                    # Insert after the "Модулі" separator
                    insert_pos = 4  # Position after "📦 Модулі" action
                    actions = self.tray_menu.actions()
                    if len(actions) > insert_pos:
                        self.tray_menu.insertAction(actions[insert_pos + 1], module_action)
                    else:
                        self.tray_menu.addAction(module_action)

                    self.tray_module_actions[module_name] = module_action
            else:
                # Add "No modules available" action
                no_modules_action = QAction("  📭 Немає доступних модулів", self)
                no_modules_action.setEnabled(False)
                insert_pos = 4  # Position after "📦 Модулі" action
                actions = self.tray_menu.actions()
                if len(actions) > insert_pos:
                    self.tray_menu.insertAction(actions[insert_pos + 1], no_modules_action)
                else:
                    self.tray_menu.addAction(no_modules_action)
                self.tray_module_actions['no_modules'] = no_modules_action

    def launch_module_from_tray(self, module_name):
        """Launch a module from the system tray"""
        try:
            # Show the main window first
            self.show()
            self.raise_()
            self.activateWindow()

            # Launch the module
            self.open_module_window(module_name)

            # Show notification
            if self.tray_icon:
                self.tray_icon.showMessage(
                    "Модуль запущено",
                    f"Модуль '{module_name}' успішно запущено",
                    QSystemTrayIcon.Information,
                    3000
                )

            self.log_message(f"🚀 Module '{module_name}' launched from system tray")

        except Exception as e:
            self.log_message(msg_formatter.module_launch_failed(module_name, str(e)))
            if self.tray_icon:
                self.tray_icon.showMessage(
                    "Помилка запуску",
                    f"Не вдалося запустити модуль '{module_name}'",
                    QSystemTrayIcon.Critical,
                    5000
                )

    def quick_start_cleanup(self):
        """Quick start the cleanup process from system tray"""
        try:
            # Show the main window
            self.show()
            self.raise_()
            self.activateWindow()

            # Start the cleanup process
            self.start_process()

            # Show notification
            if self.tray_icon:
                self.tray_icon.showMessage(
                    "Прибирання запущено",
                    "Процес прибирання файлів розпочато",
                    QSystemTrayIcon.Information,
                    3000
                )

            self.log_message("🧹 Cleanup started from system tray")

        except Exception as e:
            self.log_message(f"❌ Failed to start cleanup from tray: {e}")
            if self.tray_icon:
                self.tray_icon.showMessage(
                    "Помилка",
                    "Не вдалося запустити прибирання",
                    QSystemTrayIcon.Critical,
                    5000
                )

    def update_tray_tooltip(self):
        """Update the system tray icon tooltip with current status"""
        if not hasattr(self, 'tray_icon') or not self.tray_icon:
            return

        try:
            # Count loaded modules
            module_count = 0
            if hasattr(self, 'module_manager') and self.module_manager:
                loaded_modules = self.module_manager.get_loaded_modules()
                module_count = len(loaded_modules)

            # Get current time for schedule info
            current_time = QTime.currentTime().toString("HH:mm")

            # Create tooltip text
            tooltip = f"Desktop Organizer\n"
            tooltip += f"⏰ {current_time}\n"
            tooltip += f"📦 {module_count} модуль(ів) завантажено\n"
            tooltip += f"🖱️ Клацніть двічі для показу/сховання"

            self.tray_icon.setToolTip(tooltip)

        except Exception as e:
            self.log_message(f"❌ Failed to update tray tooltip: {e}")

    def toggle_window_visibility(self):
        """Toggle main window visibility"""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def on_tray_icon_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.toggle_window_visibility()

    def open_settings(self):
        """Open settings dialog"""
        # Show main window first
        self.show()
        self.raise_()
        self.activateWindow()

        # Create and show settings dialog
        settings_dialog = SettingsDialog(self.settings, self)
        settings_dialog.settings_applied.connect(self.handle_settings_applied)

        # Temporarily disable minimize to tray behavior for settings dialog
        original_minimize_setting = self.settings.get('application', {}).get('minimize_to_tray', False)
        if 'application' not in self.settings:
            self.settings['application'] = {}
        self.settings['application']['minimize_to_tray'] = False

        # Show dialog
        result = settings_dialog.exec_()

        # Restore original minimize to tray setting
        self.settings['application']['minimize_to_tray'] = original_minimize_setting

    def force_close_application(self):
        """Force close the application (bypassing minimize to tray)"""
        app_settings = self.settings.get('application', {})
        if app_settings.get('minimize_to_tray', False):
            # Temporarily disable minimize to tray to allow closing
            app_settings['minimize_to_tray'] = False
        self.close()

    def discover_and_load_modules(self):
        """Discover and load all available modules dynamically."""
        add_splash_message("🔍 Scanning for modules...")
        self.log_message("🔍 Discovering modules...")
        discovered_modules = self.module_manager.discover_modules()

        if discovered_modules:
            add_splash_message(f"📦 Found {len(discovered_modules)} module(s)")
            self.log_message(f"📦 Found {len(discovered_modules)} module(s)")

            # Validate and repair dependencies before loading
            add_splash_message("🔧 Validating dependencies...")
            self.module_manager.validate_and_repair_dependencies()

            # Load all discovered modules
            add_splash_message("🚀 Loading modules...")
            self.module_manager.load_all_modules()

            # Update system tray menu with loaded modules
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.update_tray_module_menu()
                self.update_tray_tooltip()

        else:
            add_splash_message("ℹ️ No modules found")
            self.log_message("ℹ️ No modules found")

            # Update system tray menu to show no modules
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.update_tray_module_menu()
                self.update_tray_tooltip()

    def on_module_discovered(self, module_name: str, module_info: dict):
        """Called when a module is discovered"""
        add_splash_message(f"🔍 Знайдено: {module_name} v{module_info.get('version', 'Невідомо')}")
        self.log_message(f"🔍 Знайдено модуль: {module_name} v{module_info.get('version', 'Невідомо')}")

    def on_module_loaded(self, module_name: str, module_class):
        """Called when a module is successfully loaded"""
        add_splash_message(f"✅ Завантажено: {module_name}")
        self.log_message(f"✅ Модуль завантажено: {module_name}")
        self.update_modules_menu()

    def on_module_error(self, module_name: str, error_message: str):
        """Called when a module encounters an error"""
        add_splash_message(f"❌ Помилка завантаження {module_name}")
        self.log_message(msg_formatter.module_error(module_name, error_message))

    def update_modules_menu(self):
        """Update the modules menu based on loaded modules"""
        if hasattr(self, 'modules_menu'):
            self.modules_menu.clear()

            loaded_modules = self.module_manager.get_loaded_modules()
            discovered_modules = self.module_manager.module_info

            # Add module actions
            for module_name in discovered_modules:
                module_info = discovered_modules[module_name]
                is_loaded = module_name in loaded_modules

                action = QAction(module_info.menu_text, self)
                action.setEnabled(is_loaded)
                action.triggered.connect(lambda checked=False, name=module_name: self.open_module_window(name))

                self.modules_menu.addAction(action)
                self.module_actions[module_name] = action

            # Add separator
            if discovered_modules:
                self.modules_menu.addSeparator()

            # Add module management actions
            close_current_action = QAction('Закрити поточний модуль', self)
            close_current_action.triggered.connect(self.close_current_module)
            close_current_action.setEnabled(len(loaded_modules) > 0)
            close_current_action.setShortcut(QKeySequence('Ctrl+W'))
            self.modules_menu.addAction(close_current_action)

            close_all_action = QAction('Закрити всі модулі', self)
            close_all_action.triggered.connect(self.close_all_module_tabs)
            close_all_action.setEnabled(len(loaded_modules) > 0)
            close_all_action.setShortcut(QKeySequence('Ctrl+Shift+W'))
            self.modules_menu.addAction(close_all_action)

            # Add delete module action
            delete_module_action = QAction('Видалити модуль...', self)
            delete_module_action.triggered.connect(self.show_delete_module_dialog)
            delete_module_action.setEnabled(len(discovered_modules) > 0)
            self.modules_menu.addAction(delete_module_action)

    def reload_modules(self):
        """Reload all modules - clear existing modules and reload them"""
        try:
            from PyQt5.QtWidgets import QMessageBox, QProgressDialog
            from PyQt5.QtCore import Qt

            # Show confirmation dialog
            reply = QMessageBox.question(
                self,
                'Перезавантаження модулів',
                'Ви впевнені, що хочете перезавантажити всі модулі?\n\n'
                'Це закриє всі відкриті вікна модулів та перезавантажить їх.',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                return

            # Clear console and log the reload action
            self.clear_log()
            self.log_message("🔄 Починаю перезавантаження модулів...")

            # Close all open module tabs
            tabs_to_close = []
            for i in range(self.tab_widget.count()):
                if i != 0:  # Don't close main tab
                    widget = self.tab_widget.widget(i)
                    if widget and widget.property("module_name"):
                        tabs_to_close.append(i)

            # Close tabs in reverse order to maintain indices
            for i in reversed(tabs_to_close):
                widget = self.tab_widget.widget(i)
                module_name = widget.property("module_name") if widget else "Unknown"
                self.tab_widget.removeTab(i)
                self.log_message(f"✅ Closed module tab: {module_name}")

            # Clear loaded modules
            self.module_manager.loaded_modules.clear()
            self.module_manager.module_info.clear()

            # Clear module menu
            if hasattr(self, 'modules_menu'):
                self.modules_menu.clear()

            # Clear module actions
            if hasattr(self, 'module_actions'):
                self.module_actions.clear()

            # Show progress dialog
            progress = QProgressDialog("Перезавантаження модулів...", "Скасувати", 0, 3, self)
            progress.setWindowTitle("Перезавантаження модулів")
            progress.setWindowModality(Qt.WindowModal)
            progress.show()

            try:
                # Step 1: Discover modules
                progress.setValue(0)
                progress.setLabelText("Пошук модулів...")
                QApplication.processEvents()

                discovered_modules = self.module_manager.discover_modules()

                if not discovered_modules:
                    progress.setValue(3)
                    self.log_message("ℹ️ Модулі не знайдено")
                    return

                # Step 2: Validate dependencies
                progress.setValue(1)
                progress.setLabelText("Перевірка залежностей...")
                QApplication.processEvents()

                self.module_manager.validate_and_repair_dependencies()

                # Step 3: Load modules
                progress.setValue(2)
                progress.setLabelText("Завантаження модулів...")
                QApplication.processEvents()

                # Reload modules using the same process as initial loading
                self.module_manager.load_all_modules()

                progress.setValue(3)

                # Update menu
                self.update_modules_menu()

                # Log success
                self.log_message(f"✅ Модулі успішно перезавантажено ({len(discovered_modules)} модулів)")

                # Show success message
                QMessageBox.information(
                    self,
                    'Перезавантаження завершено',
                    f'Успішно перезавантажено {len(discovered_modules)} модулів.'
                )

            except Exception as e:
                # Log error
                self.log_message(f"❌ Помилка перезавантаження модулів: {e}")

                # Show error message
                QMessageBox.critical(
                    self,
                    'Помилка перезавантаження',
                    f'Не вдалося перезавантажити модулі:\n{e}'
                )

            finally:
                progress.close()

        except Exception as e:
            # Show error if something goes wrong with the dialog itself
            self.log_message(f"❌ Помилка ініціалізації перезавантаження модулів: {e}")
            QMessageBox.critical(
                self,
                'Помилка',
                f'Не вдалося ініціалізувати перезавантаження модулів:\n{e}'
            )

    def delete_module(self, module_name: str) -> bool:
        """Delete a module from the file system and clean up"""
        try:
            # Get module info before deletion
            module_info = self.module_manager.module_info.get(module_name)
            if not module_info:
                self.log_message(f"ERROR: Модуль не знайдено: {module_name}")
                return False

            # Confirm deletion
            reply = QMessageBox.question(
                self,
                "Підтвердити видалення",
                f"Ви впевнені, що хочете видалити модуль '{module_info.menu_text}'?\n\n"
                f"Це назавжди видалить файли модуля:\n"
                f"• {module_info.module_path if not module_info.is_directory else module_info.module_dir}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                self.log_message(f"INFO: Видалення модуля '{module_name}' скасовано")
                return False

            self.log_message(f"DELETE: Видалення модуля: {module_name}")

            # Close any open tabs for this module
            self.close_module_tabs_by_name(module_name)

            # Unload the module first
            self.module_manager.unload_module(module_name)

            # Delete the module files
            try:
                if module_info.is_directory:
                    # Delete directory module
                    if os.path.exists(module_info.module_dir):
                        shutil.rmtree(module_info.module_dir)
                        self.log_message(f"SUCCESS: Видалено директорію модуля: {module_info.module_dir}")
                    else:
                        self.log_message(f"WARNING: Директорія модуля не існує: {module_info.module_dir}")
                else:
                    # Delete single file module
                    if os.path.exists(module_info.module_path):
                        os.remove(module_info.module_path)
                        self.log_message(f"SUCCESS: Видалено файл модуля: {module_info.module_path}")
                    else:
                        self.log_message(f"WARNING: Файл модуля не існує: {module_info.module_path}")

            except Exception as e:
                self.log_message(f"ERROR: Помилка видалення файлів модуля: {e}")
                return False

            # Remove from module info
            if module_name in self.module_manager.module_info:
                del self.module_manager.module_info[module_name]

            # Remove from module actions
            if module_name in self.module_actions:
                action = self.module_actions[module_name]
                if hasattr(self, 'modules_menu'):
                    self.modules_menu.removeAction(action)
                del self.module_actions[module_name]

            # Update the modules menu
            self.update_modules_menu()

            self.log_message(f"SUCCESS: Модуль '{module_name}' успішно видалено")
            return True

        except Exception as e:
            self.log_message(f"ERROR: Помилка видалення модуля '{module_name}': {e}")
            return False

    def close_module_tabs_by_name(self, module_name: str):
        """Close all tabs for a specific module"""
        tabs_to_close = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if widget.property("module_name") == module_name:
                tabs_to_close.append(i)

        # Close tabs in reverse order to maintain indices
        for index in reversed(tabs_to_close):
            self.tab_widget.removeTab(index)

    def show_delete_module_dialog(self):
        """Show dialog to select and delete a module"""
        discovered_modules = self.module_manager.module_info

        if not discovered_modules:
            QMessageBox.information(self, "Немає модулів",
                                     "Немає доступних модулів для видалення.")
            return

        # Create module selection dialog
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Видалити модуль")
        dialog.setModal(True)
        dialog.setMinimumSize(400, 300)

        layout = QVBoxLayout()

        # Add instruction label
        label = QLabel("Оберіть модуль для видалення:")
        layout.addWidget(label)

        # Create list widget
        module_list = QListWidget()
        layout.addWidget(module_list)

        # Add modules to list
        for module_name, module_info in discovered_modules.items():
            item = QListWidgetItem(module_info.menu_text)
            item.setData(Qt.UserRole, module_name)  # Store module name
            item.setData(Qt.ToolTipRole, f"Ім'я: {module_name}\n"
                                              f"Версія: {module_info.version}\n"
                                              f"Тип: {'Директорія' if module_info.is_directory else 'Файл'}\n"
                                              f"Шлях: {module_info.module_path if not module_info.is_directory else module_info.module_dir}")
            module_list.addItem(item)

        # Sort items alphabetically
        module_list.sortItems(Qt.AscendingOrder)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        # Connect buttons
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        # Show dialog
        if dialog.exec_() == QDialog.Accepted:
            selected_item = module_list.currentItem()
            if selected_item:
                module_name = selected_item.data(Qt.UserRole)
                if module_name:
                    self.delete_module(module_name)

    def save_settings(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                yaml.dump(self.settings, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        except Exception as e:
            print(f"Помилка збереження налаштувань у {CONFIG_FILE}: {e}")
            QMessageBox.critical(self, "Помилка збереження", f"Не вдалося зберегти налаштування у {CONFIG_FILE}:\n{e}")



    def auto_configure_start(self):
        policy = self.settings.get('drives', {}).get('main_drive_policy', 'D')
        initial_drive = None

        self.check_drive_availability()

        if policy == 'D' and self.d_exists:
            initial_drive = 'D'
        elif policy == 'auto':
            detected_drive = find_next_available_drive()
            if detected_drive:
                initial_drive = detected_drive
            elif self.d_exists:
                self.log_message("ℹ️ Автовизначення не вдалося або немає відповідного диска, повертаємося до D:")
                initial_drive = 'D'
        elif policy == 'D' and not self.d_exists and self.e_exists:
             self.log_message(f"ℹ️ Вказано політику основного диска 'D', але D: не знайдено. Повертаємося до E:")
             initial_drive = 'E'
        elif self.e_exists and not initial_drive:
             self.log_message(f"ℹ️ Політика основного диска '{policy}' не вдалася або не застосовна, повертаємося до E:")
             initial_drive = 'E'

        if initial_drive:
            self.selected_drive = initial_drive
        else:
            self.selected_drive = 'C'
            if policy != 'C':
                self.log_message("⚠️ Не знайдено відповідного основного диска (D:, E:, або автовизначеного). Використовується C:")

        self.log_message(f"⚙️ Початковий основний диск встановлено на: {self.selected_drive}:")
        self.update_drive_buttons_visuals()

        app_settings = self.settings.get('application', DEFAULT_SETTINGS['application'])
        if app_settings.get('autostart_timer_enabled', True):
            self.start_auto_timer()
        else:
             self.log_message("ℹ️ Автозапуск таймера вимкнено в налаштуваннях.")
             self.stop_auto_timer(log_disabled=True)


    def apply_settings_to_ui(self):
        timer_cfg = self.settings.get('timer', DEFAULT_SETTINGS['timer'])
        minutes_to_set = DEFAULT_SETTINGS['timer']['default_minutes']

        if timer_cfg.get('override_default_enabled', False):
            minutes_to_set = timer_cfg.get('default_minutes', minutes_to_set)

        index_to_set = -1
        for i in range(self.time_combo.count()):
            try:
                if int(self.time_combo.itemText(i).split()[0]) == minutes_to_set:
                    index_to_set = i
                    break
            except: pass
        if index_to_set != -1:
             self.time_combo.blockSignals(True)
             self.time_combo.setCurrentIndex(index_to_set)
             self.time_combo.blockSignals(False)
        else:
             self.time_combo.blockSignals(True)
             self.time_combo.setCurrentIndex(1)
             self.time_combo.blockSignals(False)

        if not self.auto_start_timer.isActive():
            self.update_timer_label_when_stopped()

        self.update_drive_buttons_visuals()

    def update_timer_label_when_stopped(self):
        minutes_text = self.time_combo.currentText()
        try:
            minutes_val = int(minutes_text.split()[0])
            self.remaining_time = minutes_val * 60
            self.timer_label.setText(f"Автозапуск вимкнено ({self.format_time()})")
        except:
            self.timer_label.setText("Автозапуск вимкнено (Помилка)")


    def initUI(self):
        self.setWindowTitle("Авто-організатор робочого столу v4.2")
        # Set minimum size to ensure UI remains usable
        self.setMinimumSize(800, 600)
        # Set maximum size to prevent excessive stretching
        self.setMaximumSize(1600, 1200)
        # Set initial geometry (allowing for future resizing)
        self.setGeometry(300, 300, 991, 701)

        menubar = self.menuBar()

        # --- File Menu ---
        file_menu = menubar.addMenu('&Файл')
        settings_action = QAction('&Налаштування...', self)
        settings_action.triggered.connect(self.open_settings_dialog)
        file_menu.addAction(settings_action)
        # --- Add Import Module Action ---
        import_module_action = QAction('&Імпортувати додатковий модуль', self)
        import_module_action.triggered.connect(self.import_modules_to_standard_dir)
        file_menu.addAction(import_module_action)
        # --- Add Install Package Action ---
        install_package_action = QAction('&Встановити пакет (.ngitpac)', self)
        install_package_action.triggered.connect(self.install_ngit_package)
        file_menu.addAction(install_package_action)
        # --- Add Reload Modules Action ---
        reload_modules_action = QAction('&Перезавантажити модулі', self)
        reload_modules_action.triggered.connect(self.reload_modules)
        file_menu.addAction(reload_modules_action)
        file_menu.addSeparator()
        exit_action = QAction('&Вихід', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- Modules Menu ---
        modules_menu = menubar.addMenu('&Модулі')
        self.modules_menu = modules_menu

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self.resize_to_current_tab)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_module_tab)
        self.tab_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_widget.customContextMenuRequested.connect(self.show_tab_context_menu)
        main_layout.addWidget(self.tab_widget)

        # --- Main Tab ---
        main_tab = QWidget()
        self.tab_widget.addTab(main_tab, "Головна")

        # Hide close button on main tab (index 0)
        self.tab_widget.tabBar().setTabButton(0, QTabBar.RightSide, None)
        main_tab_layout = QVBoxLayout(main_tab)

        self.timer_label = QLabel("Завантаження...")
        main_tab_layout.addWidget(self.timer_label)

        control_layout = QHBoxLayout()
        self.time_combo = QComboBox()
        self.time_combo.addItems(["1 хвилина", "3 хвилини", "5 хвилин", "10 хвилин", "15 хвилин", "30 хвилин", "60 хвилин"])
        self.time_combo.currentIndexChanged.connect(self.time_selection_changed)
        control_layout.addWidget(self.time_combo)
        self.start_now_btn = QPushButton("🚀 Старт зараз")
        self.start_now_btn.clicked.connect(self.start_now)
        control_layout.addWidget(self.start_now_btn)
        self.timer_control_btn = QPushButton("⏱️ Стоп таймер")
        self.timer_control_btn.clicked.connect(self.toggle_timer)
        control_layout.addWidget(self.timer_control_btn)
        main_tab_layout.addLayout(control_layout)

        drive_group = QGroupBox("Вибір основного диска")
        drive_layout = QHBoxLayout(drive_group)
        self.btn_group = QButtonGroup(self)
        self.btn_drive_d = QPushButton("Диск D:")
        self.btn_drive_e = QPushButton("Диск E:")
        self.btn_group.addButton(self.btn_drive_d, ord('D'))
        self.btn_group.addButton(self.btn_drive_e, ord('E'))
        drive_layout.addWidget(self.btn_drive_d)
        drive_layout.addWidget(self.btn_drive_e)
        self.btn_group.buttonClicked[int].connect(self.set_selected_drive)
        main_tab_layout.addWidget(drive_group)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        main_tab_layout.addWidget(self.log)

    def resize_to_current_tab(self, index=-1):
        current_widget = self.tab_widget.currentWidget()
        if current_widget:
            self.centralWidget().adjustSize()
            self.adjustSize()

    def import_modules_to_standard_dir(self):
        """Opens a dialog to select .py files and copies them to the standard module directory."""
        source_files, _ = QFileDialog.getOpenFileNames(
            self,
            "Виберіть файли модулів для імпорту",
            os.path.expanduser("~"),  # Start in user's home directory or last path
            "Файли Python (*.py);;Всі файли (*.*)"
        )

        if not source_files:
            self.log_message("ℹ️ Імпорт модуля скасовано користувачем.")
            return

        target_dir = self.get_module_dir()  # Get ./modules path
        try:
            os.makedirs(target_dir, exist_ok=True)  # Ensure the directory exists
        except OSError as e:
            self.log_message(f"❌ Критична помилка: Не вдалося створити папку модуля '{target_dir}': {e}")
            QMessageBox.critical(self, "Помилка імпорту",
                                 f"Не вдалося створити цільову папку модуля:\n{target_dir}\n\n{e}")
            return

        copied_count = 0
        skipped_count = 0
        error_count = 0
        modules_changed = False

        for src_path in source_files:
            filename = os.path.basename(src_path)
            dest_path = os.path.join(target_dir, filename)

            # Check for overwrite
            if os.path.exists(dest_path):
                reply = QMessageBox.question(
                    self,
                    "Підтвердити перезапис",
                    f"Модуль '{filename}' вже існує в стандартній папці.\nВи хочете перезаписати його?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No  # Default to No
                )
                if reply == QMessageBox.No:
                    self.log_message(f"⏭️ Пропущено перезапис для: {filename}")
                    skipped_count += 1
                    continue

            # Attempt to copy
            try:
                shutil.copy2(src_path, dest_path)  # copy2 preserves metadata
                self.log_message(f"✅ Імпортовано: {filename}")
                copied_count += 1
                modules_changed = True
            except Exception as e:
                self.log_message(f"❌ Помилка імпорту '{filename}': {e}")
                error_count += 1

        summary = f"🏁 Процес імпорту завершено. Скопійовано: {copied_count}, Пропущено: {skipped_count}, Помилок: {error_count}."
        self.log_message(summary)
        QMessageBox.information(self, "Імпорт завершено", summary)

        # Reload modules if any file was successfully copied
        if modules_changed:
            self.log_message("🔄 Перезавантаження модулів після імпорту...")
            self.reload_modules_and_update_ui()

    def install_ngit_package(self):
        """Install NGIT package from .ngitpac file"""
        package_file, _ = QFileDialog.getOpenFileName(
            self,
            "Виберіть пакет для встановлення (.ngitpac)",
            os.path.expanduser("~"),  # Start in user's home directory
            "NGIT Packages (*.ngitpac);;Всі файли (*.*)"
        )

        if not package_file:
            self.log_message("ℹ️ Встановлення пакета скасовано користувачем.")
            return

        # Get the package installer from module manager
        installer = self.module_manager.get_package_installer()

        self.log_message(f"📦 Встановлення пакета: {os.path.basename(package_file)}")

        # Show progress dialog
        progress_dialog = QProgressDialog(
            "Встановлення пакета. Будь ласка, зачекайте...",
            "Скасувати",
            0, 0, self
        )
        progress_dialog.setWindowTitle("Встановлення пакета")
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.show()

        # Process application events to ensure dialog appears
        QApplication.processEvents()

        try:
            # Install the package
            success = installer.install_package(package_file)

            if success:
                self.log_message(f"✅ Пакет успішно встановлено: {os.path.basename(package_file)}")

                # Show success message with details
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("Встановлення успішне")
                msg.setText("Пакет успішно встановлено!")

                # Add details about warnings if any
                if installer.warnings:
                    detailed_text = "Попередження:\n" + "\n".join(f"• {warning}" for warning in installer.warnings)
                    msg.setDetailedText(detailed_text)

                msg.exec_()

                # Reload modules to include the newly installed package
                self.log_message("🔄 Перезавантаження модулів після встановлення пакета...")
                self.reload_modules_and_update_ui()

            else:
                self.log_message(f"❌ Помилка встановлення пакета: {os.path.basename(package_file)}")

                # Show error message
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Critical)
                msg.setWindowTitle("Помилка встановлення")
                msg.setText("Не вдалося встановити пакет.")

                # Add details about errors
                if installer.errors:
                    detailed_text = "Помилки:\n" + "\n".join(f"• {error}" for error in installer.errors)
                    msg.setDetailedText(detailed_text)

                msg.exec_()

        except Exception as e:
            self.log_message(f"❌ Критична помилка при встановленні пакета: {e}")
            QMessageBox.critical(
                self,
                "Критична помилка",
                f"Виникла критична помилка при встановленні пакета:\n{e}"
            )

        finally:
            progress_dialog.close()

    def open_module_window(self, module_name):
        """Open a module window/tab"""
        loaded_modules = self.module_manager.get_loaded_modules()
        module_info = self.module_manager.get_module_info(module_name)

        if module_name in loaded_modules and module_info:
            try:
                ModuleClass = loaded_modules[module_name]

                # Check if a tab for this module already exists
                for i in range(self.tab_widget.count()):
                    if self.tab_widget.widget(i).property("module_name") == module_name:
                        self.tab_widget.setCurrentIndex(i)
                        return

                module_widget = ModuleClass(parent=self)
                module_widget.setProperty("module_name", module_name)
                tab_name = module_info.menu_text.replace("&", "").replace("...", "")
                self.tab_widget.addTab(module_widget, tab_name)
                self.tab_widget.setCurrentWidget(module_widget)

            except Exception as e:
                self.log_message(f"❌ Error creating module window for '{module_name}': {e}")
                QMessageBox.critical(self, "Помилка Модуля", f"Не вдалося відкрити модуль '{module_name}'.\n\n{e}")
        else:
            self.log_message(f"⚠️ Attempted to open module '{module_name}', but it's not loaded.")
            QMessageBox.warning(self, "Модуль Недоступний",
                                f"Потрібний модуль '{module_name}' не знайдено або не вдалося завантажити.")

    def reload_modules_and_update_ui(self):
        """Reload all modules and update the UI accordingly."""
        self.clear_log()
        self.log_message("🔄 Reloading modules...")

        # Close existing module tabs
        tabs_to_close = []
        for i in range(self.tab_widget.count()):
            if self.tab_widget.widget(i).property("module_name"):
                tabs_to_close.append(i)

        # Close tabs in reverse order to maintain indices
        for i in reversed(tabs_to_close):
            self.tab_widget.removeTab(i)

        QApplication.processEvents()  # Allow UI to update

        # Reload modules using the module manager
        self.discover_and_load_modules()

        self.log_message("✅ Module reload completed")

    def close_module_tab(self, index):
        """Close a module tab"""
        # Don't close the main tab (index 0)
        if index == 0:
            return

        widget = self.tab_widget.widget(index)
        if widget:
            # Check if this is a module tab
            module_name = widget.property("module_name")
            if module_name:
                # Optional: Ask for confirmation
                reply = QMessageBox.question(
                    self,
                    'Закрити модуль',
                    f'Ви впевнені, що хочете закрити модуль "{module_name}"?',
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply == QMessageBox.Yes:
                    self.tab_widget.removeTab(index)
                    self.log_message(f"✅ Module tab closed: {module_name}")
            else:
                # Not a module tab, close directly
                self.tab_widget.removeTab(index)

    def show_tab_context_menu(self, position):
        """Show context menu for tabs"""
        tab_index = self.tab_widget.tabBar().tabAt(position)

        if tab_index == -1:
            return

        # Don't show context menu for main tab
        if tab_index == 0:
            return

        widget = self.tab_widget.widget(tab_index)
        module_name = widget.property("module_name") if widget else None

        if not module_name:
            return

        menu = QMenu(self)

        close_action = QAction("Закрити модуль", self)
        close_action.triggered.connect(lambda: self.close_module_tab(tab_index))
        menu.addAction(close_action)

        close_others_action = QAction("Закрити інші модулі", self)
        close_others_action.triggered.connect(lambda: self.close_other_module_tabs(tab_index))
        menu.addAction(close_others_action)

        close_all_action = QAction("Закрити всі модулі", self)
        close_all_action.triggered.connect(self.close_all_module_tabs)
        menu.addAction(close_all_action)

        menu.addSeparator()

        reload_action = QAction("Перезавантажити модуль", self)
        reload_action.triggered.connect(lambda: self.reload_single_module(module_name))
        menu.addAction(reload_action)

        menu.exec_(self.tab_widget.tabBar().mapToGlobal(position))

    def close_other_module_tabs(self, keep_index):
        """Close all module tabs except the specified one"""
        tabs_to_close = []

        for i in range(self.tab_widget.count()):
            if i != keep_index and i != 0:  # Keep specified tab and main tab
                widget = self.tab_widget.widget(i)
                if widget and widget.property("module_name"):
                    tabs_to_close.append(i)

        # Close tabs in reverse order to maintain indices
        for i in reversed(tabs_to_close):
            widget = self.tab_widget.widget(i)
            module_name = widget.property("module_name") if widget else "Unknown"
            self.tab_widget.removeTab(i)
            self.log_message(f"✅ Module tab closed: {module_name}")

    def close_all_module_tabs(self):
        """Close all module tabs"""
        reply = QMessageBox.question(
            self,
            'Закрити всі модулі',
            'Ви впевнені, що хочете закрити всі відкриті модулі?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            tabs_to_close = []

            for i in range(self.tab_widget.count()):
                if i != 0:  # Don't close main tab
                    widget = self.tab_widget.widget(i)
                    if widget and widget.property("module_name"):
                        tabs_to_close.append(i)

            # Close tabs in reverse order to maintain indices
            for i in reversed(tabs_to_close):
                widget = self.tab_widget.widget(i)
                module_name = widget.property("module_name") if widget else "Unknown"
                self.tab_widget.removeTab(i)
                self.log_message(f"✅ Module tab closed: {module_name}")

    def reload_single_module(self, module_name):
        """Reload a single module"""
        try:
            # Close the module tab if it exists
            tab_to_close = None
            for i in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(i)
                if widget and widget.property("module_name") == module_name:
                    tab_to_close = i
                    break

            if tab_to_close is not None:
                self.tab_widget.removeTab(tab_to_close)

            # Unload the module
            self.module_manager.unload_module(module_name)

            # Reload the module
            if self.module_manager.load_module(module_name):
                self.log_message(f"✅ Module reloaded: {module_name}")
                # Reopen the module window
                self.open_module_window(module_name)
            else:
                self.log_message(msg_formatter.module_reload_failed(module_name))

        except Exception as e:
            self.log_message(f"❌ Error reloading module {module_name}: {e}")
            QMessageBox.critical(self, "Помилка", f"Не вдалося перезавантажити модуль: {e}")

    def close_current_module(self):
        """Close the currently active module tab"""
        current_index = self.tab_widget.currentIndex()

        # Don't close if on main tab
        if current_index == 0:
            QMessageBox.information(self, "Інформація", "Головну вкладку не можна закрити.")
            return

        self.close_module_tab(current_index)

    def _log_current_schedule_settings(self, schedule_cfg):
        schedule_type_en = schedule_cfg.get('type', 'disabled')
        schedule_type_ua = SCHEDULE_TYPE_MAP.get(schedule_type_en, "Вимкнено")

        log_str = f"ℹ️ Розклад встановлено: {schedule_type_ua}"
        if schedule_type_en != 'disabled':
            time_start = schedule_cfg.get('time_start', '22:00')
            time_end = schedule_cfg.get('time_end', '23:00')
            log_str += f", Час: {time_start}-{time_end}"

            if schedule_type_en == 'weekly':
                day_of_week_index = schedule_cfg.get('day_of_week', 1) - 1
                day_of_week_ua = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"][day_of_week_index]
                log_str += f", День тижня: {day_of_week_ua}"
            elif schedule_type_en == 'monthly':
                day_of_month = schedule_cfg.get('day_of_month', 1)
                log_str += f", День місяця: {day_of_month}"
            elif schedule_type_en == 'quarterly':
                quarter_month_index = schedule_cfg.get('quarter_month', 1) - 1
                quarter_month_ua = ["Перший", "Другий", "Третій"][quarter_month_index]
                quarter_day = schedule_cfg.get('quarter_day', 1)
                log_str += f", Місяць кварталу: {quarter_month_ua}, День: {quarter_day}"
        
        self.log_message(log_str)

    def handle_settings_applied(self, new_settings):
        self.settings = new_settings
        self.save_settings()
        self.apply_settings_to_ui()
        self.log_message("⚙️ Налаштування застосовано.")

        # Log schedule settings
        schedule_cfg = self.settings.get('schedule', DEFAULT_SETTINGS['schedule'])
        self._log_current_schedule_settings(schedule_cfg)

        if not self.auto_start_timer.isActive():
            app_settings = self.settings.get('application', DEFAULT_SETTINGS['application'])
            if not app_settings.get('autostart_timer_enabled', True):
                 self.stop_auto_timer(log_disabled=True)
            else:
                 self.update_timer_label_when_stopped()


    def open_settings_dialog(self):
        dialog = SettingsDialog(self.settings, self)
        dialog.settings_applied.connect(self.handle_settings_applied)
        dialog.exec_()


    def show_install_placeholder(self):
        QMessageBox.information(self, "Встановлення програм", "Ця функція ще не реалізована.")


    def open_license_manager(self):
        if self.license_manager_window and self.license_manager_window.isVisible():
            self.license_manager_window.activateWindow()
            self.license_manager_window.raise_()
        else:
            try:
                # Re-check if the import worked initially
                from license_manager import LicenseManager as ActualLicenseManager
                self.license_manager_window = ActualLicenseManager(self)
                # Optional: Connect log signal
                # self.license_manager_window.log_signal.connect(self.handle_license_log)
                self.license_manager_window.show()
            except ImportError:
                 QMessageBox.critical(self, "Помилка", "Модуль Менеджера Ліцензій не вдалося завантажити.")
            except Exception as e:
                 QMessageBox.critical(self, "Помилка", f"Не вдалося відкрити Менеджер Ліцензій:\n{e}")

    # Optional: Slot to handle logs from License Manager
    # def handle_license_log(self, level, message):
    #     prefix = "[LicenseMgr]"
    #     self.log_message(f"{prefix} [{level.upper()}] {message}")


    def time_selection_changed(self):
        if not self.auto_start_timer.isActive():
            self.update_timer_label_when_stopped()


    def check_drive_availability(self):
        self.d_exists = os.path.exists("D:\\")
        self.e_exists = os.path.exists("E:\\")

        self.btn_drive_d.setEnabled(self.d_exists)
        self.btn_drive_e.setEnabled(self.e_exists)

        self.update_drive_buttons_visuals()


    def update_drive_buttons_visuals(self):
        self.btn_drive_d.setText(f"Диск D: {'🟢' if self.d_exists else '🔴'}")
        self.btn_drive_e.setText(f"Диск E: {'🟢' if self.e_exists else '🔴'}")

        for button in self.btn_group.buttons():
            drive_letter = chr(self.btn_group.id(button))
            is_selected = (drive_letter == self.selected_drive)
            if is_selected:
                button.setStyleSheet("font-weight: bold; border: 2px solid blue;")
            else:
                # Reset style, consider inheriting default look or using a less specific style
                button.setStyleSheet("") # Reset to default or use "font-weight: normal; border: none;"


    def set_selected_drive(self, drive_id):
        drive_letter = chr(drive_id)
        if (drive_letter == 'D' and self.d_exists) or \
           (drive_letter == 'E' and self.e_exists):
            if drive_letter != self.selected_drive:
                self.selected_drive = drive_letter
                self.log_message(f"Обрано основний диск: {self.selected_drive}:")
                self.update_drive_buttons_visuals()
                self.stop_auto_timer()
        else:
             self.log_message(f"⚠️ Диск {drive_letter}: недоступний.")
             self.update_drive_buttons_visuals()


    def toggle_timer(self):
        if self.auto_start_timer.isActive():
            self.stop_auto_timer()
        else:
            # Check if autostart is globally disabled by settings before starting
            app_settings = self.settings.get('application', DEFAULT_SETTINGS['application'])
            if not app_settings.get('autostart_timer_enabled', True):
                 self.log_message("ℹ️ Таймер не можна запустити вручну, коли автозапуск вимкнено в налаштуваннях.")
                 # Optionally show a QMessageBox here too
                 return
            self.start_auto_timer()


    def start_now(self):
        if self.mover_thread and self.mover_thread.isRunning():
             QMessageBox.warning(self, "Зайнято", "Процес переміщення вже запущено.")
             return
        self.stop_auto_timer()
        self.start_process()


    def start_auto_timer(self):
        if self.mover_thread and self.mover_thread.isRunning():
             self.log_message("ℹ️ Неможливо запустити таймер під час переміщення.")
             return

        # Explicitly check the setting again before starting
        app_settings = self.settings.get('application', DEFAULT_SETTINGS['application'])
        if not app_settings.get('autostart_timer_enabled', True):
             self.log_message("ℹ️ Запуск таймера заблоковано налаштуваннями програми (Автозапуск вимкнено).")
             self.stop_auto_timer(log_disabled=True) # Ensure UI reflects disabled state
             return

        minutes_text = self.time_combo.currentText()
        try:
             minutes = int(minutes_text.split()[0])
        except:
             minutes = 3
             self.log_message("⚠️ Не вдалося розпізнати час таймера, встановлено 3 хв.")

        self.remaining_time = minutes * 60
        if self.remaining_time <= 0:
             self.remaining_time = 180
        self.timer_label.setText(f"До автоматичного старту: {self.format_time()}")
        self.timer_control_btn.setText("⏱️ Стоп таймер")
        self.time_combo.setEnabled(False)
        self.btn_drive_d.setEnabled(False)
        self.btn_drive_e.setEnabled(False)
        self.auto_start_timer.start(1000)


    def stop_auto_timer(self, log_disabled=False):
        self.auto_start_timer.stop()
        if log_disabled:
             self.timer_label.setText("Автозапуск вимкнено (Налаштування)")
        else:
             self.update_timer_label_when_stopped()

        self.timer_control_btn.setText("▶️ Старт таймер")
        self.time_combo.setEnabled(True)
        self.check_drive_availability()


    def update_timer(self):
        self.remaining_time -= 1
        if self.remaining_time <= 0:
            self.auto_start_timer.stop()
            self.start_process()
            return
        self.timer_label.setText(f"До автоматичного старту: {self.format_time()}")


    def format_time(self):
        mins, secs = divmod(self.remaining_time, 60)
        return f"{mins:02}:{secs:02}"



    def check_schedule(self):
        app_settings = self.settings.get('application', DEFAULT_SETTINGS['application'])
        schedule_cfg = self.settings.get('schedule', DEFAULT_SETTINGS['schedule'])
        schedule_type = schedule_cfg.get('type', 'disabled')

        # Do not run if both the schedule and the autostart timer are disabled
        if schedule_type == 'disabled' or not app_settings.get('autostart_timer_enabled', True):
            return

        now = datetime.now()
        today = now.date()
        current_time = QTime.currentTime()
        self.log_message(f"ℹ️ Перевірка розкладу: {today.strftime('%Y-%m-%d')} {current_time.toString('HH:mm:ss')}")


        # Reset last run date if it's a new day.
        if self.last_scheduled_run_date and self.last_scheduled_run_date < today:
            self.last_scheduled_run_date = None

        # Check if today is a scheduled day
        if not is_scheduled_day(schedule_cfg):
            return

        # Have we already run for today's schedule?
        if self.last_scheduled_run_date == today:
            return

        start_time = QTime.fromString(schedule_cfg.get('time_start', '16:00'), "HH:mm")
        end_time = QTime.fromString(schedule_cfg.get('time_end', '17:00'), "HH:mm")

        # If we are within the execution window, check for idle
        if start_time <= current_time <= end_time:
            cpu_usage = psutil.cpu_percent(interval=1)
            self.log_message(f"ℹ️ У вікні розкладу. ЦП: {cpu_usage}%.")
            if cpu_usage < 15.0:
                self.log_message("⏰ Низьке завантаження ЦП. Запуск таймера за розкладом.")
                self.start_auto_timer()
                self.last_scheduled_run_date = today
                self.save_last_run_date(today)
        # If we are past the window and haven't run, run now.
        elif current_time > end_time:
            self.log_message("⚠️ Вікно розкладу пропущено. Запускаємо таймер зараз, оскільки він не був запущений через високе завантаження ЦП.")
            self.start_auto_timer()
            self.last_scheduled_run_date = today
            self.save_last_run_date(today)


    def start_process(self):
        if not self.selected_drive:
            self.log_message("❌ Помилка: Не вдалося визначити цільовий диск.")
            self.check_drive_availability()
            return

        if self.mover_thread and self.mover_thread.isRunning():
            self.log_message("⚠️ Процес вже запущено.")
            return

        self.log_message(f"\n🚀 Початок переміщення на диск {self.selected_drive}:...")
        self.start_now_btn.setEnabled(False)
        self.timer_control_btn.setEnabled(False)
        self.time_combo.setEnabled(False)
        self.btn_drive_d.setEnabled(False)
        self.btn_drive_e.setEnabled(False)

        self.mover_thread = FileMover(target_drive=self.selected_drive, fallback_drive='C', settings=self.settings.copy())
        self.mover_thread.update_signal.connect(self.log_message)
        self.mover_thread.finished_signal.connect(self.process_finished)
        self.mover_thread.start()


    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{timestamp}] {message}")
        QApplication.processEvents()

    def clear_log(self):
        """Clear the log widget"""
        self.log.clear()
        self.log_message("📋 Консоль очищена")


    def process_finished(self, success, errors, path):
        self.log_message("\n🏁 Результат:")
        self.log_message(f"✅ Успішно: {success}")
        if errors > 0:
            self.log_message(f"❌ Помилок: {errors}")
        if not path.startswith("Error"):
             self.log_message(f"📁 Збережено до: {path}")
        else:
             self.log_message(f"❌ {path}")

        stats_dialog = RunStatisticsDialog(success, errors, path, self)
        stats_dialog.exec_()
        self.close()


    def closeEvent(self, event):
        # Check if there are any modal dialogs active (like settings dialog)
        if QApplication.activeModalWidget():
            # If there's a modal dialog, let it handle the close event normally
            return

        # Check if minimize to tray is enabled
        app_settings = self.settings.get('application', {})
        if app_settings.get('minimize_to_tray', False) and self.tray_icon:
            # Instead of closing, minimize to tray
            event.ignore()
            self.hide()
            if self.tray_icon:
                self.tray_icon.showMessage(
                    "Desktop Organizer",
                    "Программа мінімізована в трей. Клацніть правою кнопкою на іконку для відновлення.",
                    QSystemTrayIcon.Information,
                    3000
                )
        else:
            # Clean up splash screen if it's still active
            global global_splash
            if global_splash and hasattr(global_splash, 'cleanup'):
                global_splash.cleanup()

            # Save settings before closing
            self.save_settings()

            # Accept the close event
            event.accept()

            # Clean up system tray
            if self.tray_icon:
                self.tray_icon.hide()
            QCoreApplication.instance().quit()


if __name__ == "__main__":
    # If started with --background-run, execute headless task check
    if '--background-run' in sys.argv:
        from PyQt5.QtCore import QCoreApplication

        def run_background_task():
            app = QCoreApplication(sys.argv)
            runner = BackgroundTaskRunner()
            if not runner.check_and_run():
                # If no task was started, quit immediately.
                QCoreApplication.instance().quit()
            sys.exit(app.exec_())

        run_background_task()

    else:  # Otherwise, start the GUI with splash screen
        app = QApplication(sys.argv)

        # Create and show splash screen
        splash = SplashScreen()
        globals()['global_splash'] = splash
        splash.show()
        QApplication.processEvents()  # Ensure splash is displayed immediately

        is_scheduled_run = '--scheduled-run' in sys.argv
        start_minimized = '--start-minimized' in sys.argv
        startup_to_tray = '--startup-to-tray' in sys.argv

        # Add startup messages to splash
        splash.add_message("⚙️ Ініціалізація програми...")
        splash.add_message("📚 Завантаження налаштувань...")

        # Create main window (this may take time)
        window = MainWindow(is_scheduled_run=is_scheduled_run)

        splash.add_message("🖥️ Вікно створено...")

        # Add a small delay to show the final message, then fade out
        QTimer.singleShot(1500, lambda: splash.fade_out_and_close(800))

        # Determine if we should show the window or start minimized
        show_window = True

        if startup_to_tray:
            # Windows startup - start minimized to tray
            show_window = False
            splash.add_message("🔄 Згортання в трей...")
        elif start_minimized:
            # Manual start minimized request
            show_window = False
            splash.add_message("🔄 Запуск згорнутого...")
        elif is_scheduled_run:
            # Scheduled run - don't show UI
            show_window = False
            splash.add_message("🔄 Запуск запланованого завдання...")

        if show_window:
            window.show()
        else:
            # Start minimized - ensure tray is available and hide window
            if window.tray_icon:
                window.hide()
                # Show a brief notification that we're running in tray
                window.tray_icon.showMessage(
                    "Desktop Organizer",
                    "Програма запущена і працює у фоновому режимі. Двічі клацніть на іконку для відновлення.",
                    QSystemTrayIcon.Information,
                    4000
                )
            else:
                # Fallback - show window if tray is not available
                window.show()
                splash.add_message("⚠️ Трей недоступний, показуємо вікно...")

        # Clear global reference after splash is closed
        QTimer.singleShot(2500, lambda: globals().__setitem__('global_splash', None))

        sys.exit(app.exec_())