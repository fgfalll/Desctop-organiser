import sys
import os
import importlib.util
import shutil
import yaml
import platform
import psutil
import re
import copy
from datetime import datetime, timedelta, time
from typing import Optional
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QButtonGroup, QComboBox,
    QMenuBar, QAction, QDialog, QTabWidget, QFormLayout,
    QSpinBox, QCheckBox, QLineEdit, QListWidget, QListWidgetItem,
    QDialogButtonBox, QMessageBox, QRadioButton, QGroupBox, QFileDialog, QTimeEdit, QSplashScreen,
    QScrollArea, QProgressDialog, QSystemTrayIcon, QMenu
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QTime, QObject, QRect, QDateTime, QCoreApplication
from PyQt5.QtGui import QPainter, QFont, QColor, QPen, QPixmap, QBrush
from PyQt5.QtWidgets import QStyle
import subprocess
import json
from pathlib import Path

# --- Configuration File Path ---
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".DesktopOrganizer")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yaml")
LAST_RUN_FILE = os.path.join(CONFIG_DIR, "last_run.txt")
os.makedirs(CONFIG_DIR, exist_ok=True)

# --- Setup Virtual Environment Python Path ---
def setup_venv_python_path():
    """Add virtual environment site-packages to Python path"""
    try:
        venv_dir = os.path.join(CONFIG_DIR, 'modules_venv')
        if os.path.exists(venv_dir):
            # Get the Python version
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}"

            # Possible site-packages paths
            site_packages_paths = [
                os.path.join(venv_dir, 'lib', f'python{python_version}', 'site-packages'),
                os.path.join(venv_dir, 'Lib', 'site-packages'),  # Windows
                os.path.join(venv_dir, 'lib', 'site-packages'),   # Some systems
            ]

            for site_packages in site_packages_paths:
                if os.path.exists(site_packages) and site_packages not in sys.path:
                    sys.path.insert(0, site_packages)
                    break

    except Exception:
        # If path setup fails, continue without it
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
    """Module information with embedded manifest"""

    def __init__(self, module_path: str):
        self.module_path = module_path
        self.module_dir = os.path.dirname(module_path)
        self.valid = False
        self.error = None
        self.module_name = os.path.splitext(os.path.basename(module_path))[0]

        # Extract embedded manifest from module file
        try:
            self.manifest = self._extract_manifest()
            self._validate_manifest()
            self.valid = True
        except Exception as e:
            self.error = f"Invalid module manifest: {e}"
            self.manifest = {}

    def _extract_manifest(self) -> dict:
        """Extract embedded manifest"""
        try:
            with open(self.module_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Look for embedded manifest between special markers
            start_marker = '"""MODULE_MANIFEST_START'
            end_marker = 'MODULE_MANIFEST_END"""'

            start_idx = content.find(start_marker)
            if start_idx == -1:
                raise ValueError("Маніфест модуля не знайдено у файлі")

            start_idx += len(start_marker)
            end_idx = content.find(end_marker, start_idx)
            if end_idx == -1:
                raise ValueError("Кінцевий маркер маніфеста модуля не знайдено")

            manifest_json = content[start_idx:end_idx].strip()
            manifest = json.loads(manifest_json)
            return manifest

        except json.JSONDecodeError as e:
            raise ValueError(f"Некоректний JSON у маніфесті: {e}")
        except Exception as e:
            raise ValueError(f"Помилка читання файлу модуля: {e}")

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

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
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
            if ' -m pip' in pip_path:
                cmd = pip_path.split() + ['list', '--format=json']
            else:
                cmd = [pip_path, 'list', '--format=json']

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

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
            if ' -m pip' in pip_path:
                cmd = pip_path.split() + ['show', package_name]
            else:
                cmd = [pip_path, 'show', package_name]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
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

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
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
            venv.create(self.venv_dir, with_pip=True)
            return True
        except Exception:
            return False

    def _validate_venv(self) -> bool:
        """Validate that the existing venv is properly set up"""
        try:
            pip_path = self.get_pip_path()
            if not pip_path or not os.path.exists(pip_path):
                return False

            # Try to run pip to ensure it's working
            result = subprocess.run([pip_path, '--version'],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return False

            # Also check that we can list packages (this tests the venv more thoroughly)
            result = subprocess.run([pip_path, 'list', '--format=json'],
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

        # Try venv pip first
        if os.path.exists(self.venv_dir):
            if sys.platform == "win32":
                venv_pip = os.path.join(self.venv_dir, 'Scripts', 'pip.exe')
                venv_python = os.path.join(self.venv_dir, 'Scripts', 'python.exe')
            else:
                venv_pip = os.path.join(self.venv_dir, 'bin', 'pip')
                venv_python = os.path.join(self.venv_dir, 'bin', 'python')

            # Use virtual environment's python with -m pip for better compatibility
            if os.path.exists(venv_python):
                return f'{venv_python} -m pip'
            elif os.path.exists(venv_pip):
                return venv_pip

        # Last resort: use system python with -m pip to install to venv
        try:
            if os.path.exists(self.venv_dir):
                return f'{sys.executable} -m pip'
        except Exception:
            pass

        return None

    def install_dependencies(self, module_name: str, dependencies: list, dependency_packages: dict = None) -> bool:
        """Install dependencies in shared virtual environment"""
        # Check if there are any dependencies at all - do this first!
        if not dependencies and not dependency_packages:
            print(f"✅ No dependencies to install for {module_name}")
            return True

        if not self.create_shared_venv():
            return False

        pip_path = self.get_pip_path()
        if not pip_path:
            print(f"DEBUG: Failed to get pip path for {module_name}")
            return False

        print(f"DEBUG: Using pip path for {module_name}: {pip_path}")

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

            # Process packages that need installation or upgrade
            for import_name, package_info in packages_to_process.items():
                package_spec = package_info['spec']
                action = package_info['action']
                reason = package_info['reason']

                
                # Use pip install with --upgrade flag for upgrades
                if ' -m pip' in pip_path:
                    # Handle python -m pip format
                    cmd = pip_path.split() + ['install']
                else:
                    # Handle direct pip path
                    cmd = [pip_path, 'install']

                # Add target directory for system pip installations
                if sys.executable in pip_path or pip_path == 'pip':
                    # Using system pip, target our virtual environment
                    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
                    if sys.platform == "win32":
                        site_packages = os.path.join(self.venv_dir, 'Lib', 'site-packages')
                    else:
                        site_packages = os.path.join(self.venv_dir, 'lib', f'python{python_version}', 'site-packages')

                    if os.path.exists(site_packages):
                        cmd.extend(['--target', site_packages])

                if action == 'upgrade':
                    cmd.append('--upgrade')
                cmd.append(package_spec)

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    error_msg = result.stderr.strip() if result.stderr else "Unknown error"

                    # Add debug information
                    print(f"DEBUG: Command failed: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
                    print(f"DEBUG: Error: {error_msg}")
                    print(f"DEBUG: Return code: {result.returncode}")

                    # Try to provide helpful suggestions
                    if "could not find" in error_msg.lower() or "404" in error_msg:
                        pass
                    elif "permission denied" in error_msg.lower():
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
                        
            self._save_package_info()
            return True

        except Exception as e:
            print(f"❌ Помилка встановлення залежностей: {e}")
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
                print(f"🗑️ Uninstalling {package} (no longer needed)...")
                result = subprocess.run([pip_path, 'uninstall', package, '-y'],
                                      capture_output=True, text=True, timeout=300)
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
            if ' -m pip' in pip_path:
                cmd = pip_path.split() + ['install', package_spec]
            else:
                cmd = [pip_path, 'install', package_spec]

            print(f"📦 Installing user package: {package_spec}")

            # Run the installation
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                print(f"❌ Failed to install {package_spec}: {result.stderr}")
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
            print(f"🗑️ Uninstalling package: {package_name}")

            # Run the uninstallation
            result = subprocess.run([pip_path, 'uninstall', package_name, '-y'],
                                  capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                print(f"❌ Failed to uninstall {package_name}: {result.stderr}")
                return False

            print(f"✅ Успішно видалено {package_name}")

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


class ModuleManager(QObject):
    """Dynamic module manager with shared virtual environment support"""

    module_loaded = pyqtSignal(str, object)  # module_name, module_class
    module_error = pyqtSignal(str, str)  # module_name, error_message
    module_discovered = pyqtSignal(str, dict)  # module_name, module_info

    def __init__(self, modules_dir: str):
        super().__init__()
        self.modules_dir = modules_dir
        self.loaded_modules = {}
        self.module_info = {}
        self.venv_manager = SharedVirtualEnvironmentManager(modules_dir)

    def discover_modules(self) -> dict:
        """Discover all modules in the modules directory"""
        discovered = {}

        if not os.path.exists(self.modules_dir):
            print(f"❌ Директорію модулів не знайдено: {self.modules_dir}")
            return discovered

        # Look for .py files with embedded manifests
        for item in os.listdir(self.modules_dir):
            module_path = os.path.join(self.modules_dir, item)

            # Check if it's a Python file
            if item.endswith('.py') and os.path.isfile(module_path):
                module_info = ModuleInfo(module_path)
                if module_info.valid:
                    discovered[module_info.name] = module_info
                    self.module_info[module_info.name] = module_info
                    self.module_discovered.emit(module_info.name, {
                        'name': module_info.name,
                        'version': module_info.version,
                        'description': module_info.description,
                        'menu_text': module_info.menu_text,
                        'author': module_info.author,
                        'category': module_info.category
                    })
                    print(f"✅ Discovered module: {module_info.name} v{module_info.version}")
                else:
                    print(f"❌ Invalid module {item}: {module_info.error}")
                    self.module_error.emit(item, module_info.error)

        return discovered

    def validate_and_repair_dependencies(self) -> bool:
        """Validate that all discovered modules have their dependencies properly installed in the venv"""
        if not self.module_info:
            return True

        print("🔧 Validating module dependencies...")
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
                            missing_deps.append(f"{package_name} (not installed)")
                        else:
                            # Check version requirements
                            installed_version = self.venv_manager._get_installed_version(package_name.lower())
                            if installed_version and ('>=' in package_spec or '==' in package_spec or '<=' in package_spec or '~=' in package_spec):
                                version_req = package_spec.replace(package_name, '').strip()
                                if version_req and not self.venv_manager._check_version_requirement(installed_version, version_req):
                                    missing_deps.append(f"{package_name} (version {installed_version} < {version_req})")
                elif module_info.dependencies:
                    for dep in module_info.dependencies:
                        if isinstance(dep, str):
                            package_name = dep.split('>=')[0].split('==')[0].split('<=')[0].split('~=')[0].strip().lower()
                            package_spec = dep.strip()
                            if not self.venv_manager._is_package_installed(package_name):
                                missing_deps.append(f"{package_name} (not installed)")
                            else:
                                # Check version requirements
                                installed_version = self.venv_manager._get_installed_version(package_name)
                                if installed_version and ('>=' in package_spec or '==' in package_spec or '<=' in package_spec or '~=' in package_spec):
                                    version_req = package_spec.replace(package_name, '').strip()
                                    if version_req and not self.venv_manager._check_version_requirement(installed_version, version_req):
                                        missing_deps.append(f"{package_name} (version {installed_version} < {version_req})")

                if not all_deps_installed:
                    if missing_deps:
                        print(f"🔧 Installing missing dependencies for {module_name}: {', '.join(missing_deps)}")
                    else:
                        print(f"🔧 Installing dependencies for {module_name}...")

                    if self.install_module_dependencies(module_name):
                        repaired_modules.append(module_name)
                        print(f"✅ Repaired dependencies for {module_name}")
                    else:
                        print(f"❌ Failed to repair dependencies for {module_name}")

        if repaired_modules:
            print(f"🔧 Repaired dependencies for {len(repaired_modules)} modules: {', '.join(repaired_modules)}")
        else:
            print("✅ All module dependencies are properly installed")

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
            success = self.venv_manager.install_dependencies(module_name, dependencies, dependency_packages)

            if success:
                # Track which module installed which packages (already handled in install_dependencies)
                self.venv_manager._save_package_info()

            return success

    def load_module(self, module_name: str) -> bool:
        """Load a specific module"""
        if module_name in self.loaded_modules:
            print(f"⚠️ Module {module_name} already loaded")
            return True

        if module_name not in self.module_info:
            print(f"❌ Модуль не знайдено: {module_name}")
            return False

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
                        error_msg = f"Failed to install dependencies for {module_name}"
                        print(f"❌ {error_msg}")
                        self.module_error.emit(module_name, error_msg)
                        return False
                else:
                    print(f"✅ Dependencies already satisfied for {module_name}")

            # Load the module
            spec = importlib.util.spec_from_file_location(f"module_{module_name}", module_info.module_path)
            if spec is None:
                raise ImportError(f"Не вдалося створити spec для модуля {module_name}")

            module = importlib.util.module_from_spec(spec)

            # Add to sys.modules
            sys.modules[f"module_{module_name}"] = module

            # Execute the module
            spec.loader.exec_module(module)

            # Get the main class
            if not hasattr(module, module_info.main_class):
                raise ImportError(f"Модуль {module_name} не має клас {module_info.main_class}")

            module_class = getattr(module, module_info.main_class)
            self.loaded_modules[module_name] = module_class

            print(f"✅ Успішно завантажено модуль: {module_name}")
            self.module_loaded.emit(module_name, module_class)
            return True

        except Exception as e:
            error_msg = f"Failed to load module {module_name}: {e}"
            print(f"❌ {error_msg}")
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
            print(f"✅ Unloaded module: {module_name}")

    def get_module_info(self, module_name: str):
        """Get information about a module"""
        return self.module_info.get(module_name)

    def get_loaded_modules(self) -> dict:
        """Get all loaded modules"""
        return self.loaded_modules.copy()

    def get_virtual_env_manager(self) -> SharedVirtualEnvironmentManager:
        """Get the virtual environment manager"""
        return self.venv_manager

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

        # Add top accent bar using application accent color (#d13438)
        accent_width = int(self.splash_width * 0.8)
        accent_x = (self.splash_width - accent_width) // 2
        accent_color = QColor(209, 52, 56)  # Application red accent
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
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)
        self.resize(800, 700)

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
        """Create a checkbox with given text"""
        return QCheckBox(text)

    def _create_spinbox(self, min_val: int, max_val: int, suffix: str = '') -> QSpinBox:
        """Create a spinbox with range and optional suffix"""
        spinbox = QSpinBox()
        spinbox.setRange(min_val, max_val)
        if suffix:
            spinbox.setSuffix(suffix)
        return spinbox

    def _create_radio_button(self, text: str) -> QRadioButton:
        """Create a radio button with given text"""
        return QRadioButton(text)

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
                border: none;
                background-color: #f5f5f5;
            }
            QScrollBar:vertical {
                background-color: #f0f0f0;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a0a0a0;
            }
        """)

        # Create content widget
        tab_general = QWidget()
        layout = QVBoxLayout(tab_general)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # Quick actions section (moved to top)
        actions_section = self._create_quick_actions_section()
        layout.addWidget(actions_section)

        # Application behavior section
        app_section = self._create_enhanced_application_section()
        layout.addWidget(app_section)

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
        self.chk_override_timer = self._create_checkbox("Перевизначити тривалість таймера за замовчуванням")
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
                border: 2px solid #0078d4;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #0078d4;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 20, 15, 15)

        # Startup behavior
        startup_layout = QHBoxLayout()
        self.chk_enable_autostart = self._create_checkbox("Автоматично запускати таймер при старті")
        self.chk_enable_autostart.setStyleSheet("""
            QCheckBox {
                font-size: 11px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 2px solid #ccc;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border-color: #0078d4;
            }
        """)
        startup_layout.addWidget(self.chk_enable_autostart)
        startup_layout.addStretch()
        layout.addLayout(startup_layout)

        # Notification settings
        notification_layout = QHBoxLayout()
        self.chk_enable_notifications = self._create_checkbox("Показувати сповіщення при організації")
        self.chk_enable_notifications.setStyleSheet("""
            QCheckBox {
                font-size: 11px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 2px solid #ccc;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border-color: #0078d4;
            }
        """)
        notification_layout.addWidget(self.chk_enable_notifications)
        notification_layout.addStretch()
        layout.addLayout(notification_layout)

        # Minimize to tray
        tray_layout = QHBoxLayout()
        self.chk_minimize_to_tray = self._create_checkbox("Мінімізувати в трей при закритті")
        self.chk_minimize_to_tray.setStyleSheet("""
            QCheckBox {
                font-size: 11px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 2px solid #ccc;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border-color: #0078d4;
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
                border: 2px solid #107c10;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #107c10;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 20, 15, 15)

        # Timer override settings
        override_layout = QHBoxLayout()
        self.chk_override_timer = self._create_checkbox("Перевизначити тривалість таймера за замовчуванням")
        self.chk_override_timer.setStyleSheet("""
            QCheckBox {
                font-size: 11px;
                spacing: 8px;
                font-weight: bold;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 2px solid #ccc;
            }
            QCheckBox::indicator:checked {
                background-color: #107c10;
                border-color: #107c10;
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
                border: 2px solid #107c10;
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
        self.btn_timer_5min.setStyleSheet("""
            QPushButton {
                background-color: #e1f5fe;
                color: #01579b;
                border: 1px solid #01579b;
                border-radius: 4px;
                font-weight: bold;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #b3e5fc;
            }
        """)

        self.btn_timer_15min = QPushButton("15 хв")
        self.btn_timer_15min.clicked.connect(lambda: self._set_timer_preset(15))
        self.btn_timer_15min.setStyleSheet("""
            QPushButton {
                background-color: #e1f5fe;
                color: #01579b;
                border: 1px solid #01579b;
                border-radius: 4px;
                font-weight: bold;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #b3e5fc;
            }
        """)

        self.btn_timer_30min = QPushButton("30 хв")
        self.btn_timer_30min.clicked.connect(lambda: self._set_timer_preset(30))
        self.btn_timer_30min.setStyleSheet("""
            QPushButton {
                background-color: #e1f5fe;
                color: #01579b;
                border: 1px solid #01579b;
                border-radius: 4px;
                font-weight: bold;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #b3e5fc;
            }
        """)

        self.btn_timer_60min = QPushButton("1 год")
        self.btn_timer_60min.clicked.connect(lambda: self._set_timer_preset(60))
        self.btn_timer_60min.setStyleSheet("""
            QPushButton {
                background-color: #e1f5fe;
                color: #01579b;
                border: 1px solid #01579b;
                border-radius: 4px;
                font-weight: bold;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #b3e5fc;
            }
        """)

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
                color: #666;
                padding: 5px;
                background-color: #f0f8ff;
                border-radius: 4px;
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
                border: 2px solid #5c2d91;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #5c2d91;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 20, 15, 15)

        # Drive selection
        drive_selection_layout = QVBoxLayout()
        drive_label = QLabel("Основний диск для організації:")
        drive_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #333; margin-bottom: 8px;")
        drive_selection_layout.addWidget(drive_label)

        # Create button group for drive selection
        self.drive_button_group = QButtonGroup()

        # Drive options with descriptions
        self.rb_drive_c = self._create_radio_button("Диск C: (поточний диск системи)")
        self.rb_drive_c.setStyleSheet("""
            QRadioButton {
                font-size: 11px;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #5c2d91;
            }
            QRadioButton::indicator:checked {
                background-color: #5c2d91;
            }
        """)

        self.rb_drive_d = self._create_radio_button("Диск D: (рекомендовано для даних)")
        self.rb_drive_d.setStyleSheet("""
            QRadioButton {
                font-size: 11px;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #5c2d91;
            }
            QRadioButton::indicator:checked {
                background-color: #5c2d91;
            }
        """)

        self.rb_drive_auto = self._create_radio_button("Автоматичний вибір (найкращий варіант)")
        self.rb_drive_auto.setStyleSheet("""
            QRadioButton {
                font-size: 11px;
                spacing: 8px;
                font-weight: bold;
                color: #5c2d91;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #5c2d91;
            }
            QRadioButton::indicator:checked {
                background-color: #5c2d91;
            }
        """)

        # Add radio buttons to button group
        self.drive_button_group.addButton(self.rb_drive_c)
        self.drive_button_group.addButton(self.rb_drive_d)
        self.drive_button_group.addButton(self.rb_drive_auto)

        drive_selection_layout.addWidget(self.rb_drive_c)
        drive_selection_layout.addWidget(self.rb_drive_d)
        drive_selection_layout.addWidget(self.rb_drive_auto)
        layout.addLayout(drive_selection_layout)

        # Drive info
        drive_info_layout = QHBoxLayout()
        self.drive_info_label = QLabel("Поточний диск: C:\\")
        self.drive_info_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #666;
                padding: 5px;
                background-color: #f5f0ff;
                border-radius: 4px;
            }
        """)
        self.refresh_drive_btn = QPushButton("Оновити")
        self.refresh_drive_btn.setStyleSheet("""
            QPushButton {
                background-color: #5c2d91;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                padding: 4px 8px;
                font-size: 9px;
            }
            QPushButton:hover {
                background-color: #4a2375;
            }
        """)
        drive_info_layout.addWidget(self.drive_info_label)
        drive_info_layout.addWidget(self.refresh_drive_btn)
        drive_info_layout.addStretch()
        layout.addLayout(drive_info_layout)

        # Connect refresh button to update drive information
        self.refresh_drive_btn.clicked.connect(self._refresh_drive_info)

        return group

    def _refresh_drive_info(self):
        """Refresh drive availability information"""
        try:
            # Check drive availability
            import subprocess
            import platform

            def check_drive_exists(drive_letter):
                if platform.system() == "Windows":
                    try:
                        result = subprocess.run(['cmd', '/c', f'if exist {drive_letter}:\\nul echo exists'],
                                               capture_output=True, text=True, timeout=3)
                        return result.returncode == 0
                    except:
                        return os.path.exists(f"{drive_letter}:\\")
                else:
                    return os.path.exists(f"/mnt/{drive_letter.lower()}")
                return False

            # Update drive availability status
            self.d_exists = check_drive_exists('D')
            self.e_exists = check_drive_exists('E')

            # Update drive info label based on current selection
            if self.rb_drive_c.isChecked():
                current_drive = 'C'
            elif self.rb_drive_d.isChecked():
                current_drive = 'D'
            elif self.rb_drive_auto.isChecked():
                current_drive = 'Автоматичний'
            else:
                current_drive = 'D'  # fallback

            # Check if selected drive is available
            if current_drive != 'Автоматичний':
                available = check_drive_exists(current_drive)
                status = "✅ Доступний" if available else "❌ Не доступний"
                self.drive_info_label.setText(f"Поточний диск: {current_drive}: {status}")
            else:
                # For auto mode, show what will be selected
                if self.d_exists:
                    self.drive_info_label.setText(f"Автоматичний вибір: Буде використано D: ✅")
                elif self.e_exists:
                    self.drive_info_label.setText(f"Автоматичний вибір: Буде використано E: ✅")
                else:
                    self.drive_info_label.setText(f"Автоматичний вибір: Буде використано C: ⚠️")

        except Exception as e:
            self.drive_info_label.setText(f"Помилка перевірки: {str(e)}")

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

    def _create_quick_actions_section(self) -> QGroupBox:
        """Create quick actions section"""
        group = QGroupBox("Швидкі Дії")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid #d13438;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #d13438;
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

        self.quick_actions_dropdown.setStyleSheet("""
            QComboBox {
                background-color: #d13438;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 8px 12px;
                font-size: 11px;
                min-width: 200px;
            }
            QComboBox:hover {
                background-color: #a4262c;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                border-left-width: 3px;
                border-left-color: #a4262c;
                border-left-style: solid;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid white;
                width: 0;
                height: 0;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                border: 2px solid #d13438;
                border-radius: 6px;
                selection-background-color: #f0f0f0;
                padding: 4px;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px 12px;
                border: none;
                font-size: 11px;
                color: #333;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #d13438;
                color: white;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #f8f8f8;
            }
        """)

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

    def _set_timer_preset(self, minutes: int):
        """Set timer to preset value"""
        self.chk_override_timer.setChecked(True)
        self.spin_default_timer.setValue(minutes)
        self.timer_status_label.setText(f"Таймер: Налаштовано на {minutes} хвилин")

    def test_organization(self):
        """Run a test organization with actual progress feedback"""
        reply = QMessageBox.question(
            self,
            "Тестова Організація",
            "Бажаєте виконати тестову організацію робочого столу?\n\n"
            "Це допоможе перевірити, чи працюють ваші налаштування фільтрів та дисків.",
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

                        # If allowed_extensions is not empty, only move files with those extensions
                        if allowed_extensions and file_ext not in allowed_extensions:
                            would_move = False
                            reason = f"Extension not allowed: {file_ext}"

                        # If allowed_filenames is not empty, only move files with those names
                        elif allowed_filenames and item_name_no_ext not in allowed_filenames:
                            would_move = False
                            reason = f"Filename not allowed: {item_name_no_ext}"

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

                # Step 4: Simulate organization with test directory
                progress.setLabelText(f"Створення тестової структури та симуляція організації...")

                # Create test directory structure
                test_base_dir = os.path.join(desktop_path, "TEST_ORGANIZATION")
                if os.path.exists(test_base_dir):
                    shutil.rmtree(test_base_dir)
                os.makedirs(test_base_dir)

                # Create typical organization structure
                test_dirs = {
                    'Documents': os.path.join(test_base_dir, 'Documents'),
                    'Images': os.path.join(test_base_dir, 'Images'),
                    'Videos': os.path.join(test_base_dir, 'Videos'),
                    'Archives': os.path.join(test_base_dir, 'Archives'),
                    'Programs': os.path.join(test_base_dir, 'Programs'),
                    'Other': os.path.join(test_base_dir, 'Other')
                }

                for dir_path in test_dirs.values():
                    os.makedirs(dir_path, exist_ok=True)

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
                            QMessageBox.information(self, "Скасовано", "Тестову організацію скасовано.")
                            # Clean up test directory
                            try:
                                shutil.rmtree(test_base_dir)
                            except:
                                pass
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

                        # If allowed_extensions is not empty, only move files with those extensions
                        if allowed_extensions and file_ext not in allowed_extensions:
                            would_move = False
                            reason = f"Extension not allowed: {file_ext}"

                        # If allowed_filenames is not empty, only move files with those names
                        elif allowed_filenames and item_name_no_ext not in allowed_filenames:
                            would_move = False
                            reason = f"Filename not allowed: {item_name_no_ext}"

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

                            # Add Shortcuts directory to test structure if needed
                            if target_dir == 'Shortcuts' and 'Shortcuts' not in test_dirs:
                                test_dirs['Shortcuts'] = os.path.join(test_base_dir, 'Shortcuts')
                                os.makedirs(test_dirs['Shortcuts'], exist_ok=True)

                            # Simulate the move by creating a placeholder
                            target_path = os.path.join(test_dirs[target_dir], item)

                            if is_file:
                                # Create a small text file as placeholder
                                placeholder_content = f"""Тестовий плейсхолдер для: {item}
Оригінальний шлях: {item_path}
Розмір: {os.path.getsize(item_path) if os.path.exists(item_path) else 'N/A'} bytes
Тип: Файл
Причина переміщення: {reason}
Це симуляція - оригінальний файл не було переміщено."""

                                try:
                                    with open(target_path, 'w', encoding='utf-8') as f:
                                        f.write(placeholder_content)
                                    simulated_moves += 1
                                    simulated_copies.append(f"📄 {item} → {target_dir}/")
                                except:
                                    pass
                            else:
                                # Create a directory placeholder
                                try:
                                    os.makedirs(target_path, exist_ok=True)
                                    placeholder_content = f"""Тестовий плейсхолдер для: {item}
Оригінальний шлях: {item_path}
Тип: Директорія
Причина переміщення: {reason}
Це симуляція - оригінальна директорія не була переміщена."""

                                    readme_path = os.path.join(target_path, '_README_.txt')
                                    with open(readme_path, 'w', encoding='utf-8') as f:
                                        f.write(placeholder_content)
                                    simulated_moves += 1
                                    simulated_copies.append(f"📁 {item} → {target_dir}/")
                                except:
                                    pass

                        # Update progress
                        progress_value = 70 + int(30 * processed_files / max(total_files, 1))
                        progress.setLabelText(f"Обробка {processed_files}/{total_files} елементів (симульовано переміщень: {simulated_moves})...")
                        progress.setValue(progress_value)
                        QApplication.processEvents()

                # Complete
                progress.setValue(100)
                QApplication.processEvents()

                # Show results
                result_msg = f"Тестову організацію завершено успішно!\n\n"
                result_msg += f"📁 Цільовий диск: {target_drive}\n"
                result_msg += f"📄 Загалом елементів на робочому столі: {file_count}\n"
                result_msg += f"🔄 Симульовано переміщень: {simulated_moves} елементів\n"
                result_msg += f"📂 Тестова структура створена: {test_base_dir}\n\n"

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
                    result_msg += f"  • Дозволені розширення: {', '.join(ext_list[:3])}"
                    if len(ext_list) > 3:
                        result_msg += f" (+{len(ext_list)-3} ще)"
                    result_msg += "\n"
                if allowed_filenames:
                    name_list = list(allowed_filenames)
                    result_msg += f"  • Дозволені імена: {', '.join(name_list[:3])}"
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

                result_msg += f"\n💡 Перевірте тестову структуру у папці:\n{test_base_dir}"
                result_msg += f"\n\n⚙️ Статус налаштувань: ✅ Перевірено"
                result_msg += f"\n🔒 Оригінальні файли не були переміщені"

                progress.close()

                # Ask if user wants to open the test directory
                reply = QMessageBox.question(
                    self,
                    "Відкрити Тестову Папку?",
                    f"Тестову організацію завершено!\n\n"
                    f"Бажаєте відкрити тестову структуру?\n"
                    f"Папка: {test_base_dir}",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )

                if reply == QMessageBox.Yes:
                    try:
                        if platform.system() == "Windows":
                            os.startfile(test_base_dir)
                        else:
                            subprocess.run(['xdg-open', test_base_dir])
                    except:
                        pass

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
            # Check if running on Windows
            if platform.system() != "Windows":
                QMessageBox.warning(self, "Помилка",
                    "Налаштування автозапуску доступне лише на Windows системах.")
                return

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
                    # Set the autorun value
                    winreg.SetValueEx(registry_key, app_name, 0, winreg.REG_SZ, app_path)

                # Update UI
                self.chk_minimize_to_tray.setChecked(True)
                self.autorun_status_label.setText("Статус автозапуску: ✅ Налаштовано")
                self.autorun_status_label.setStyleSheet("font-size: 10px; color: #107c10; padding: 5px;")

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

    def remove_autorun(self):
        """Remove Windows autorun"""
        try:
            # Check if running on Windows
            if platform.system() != "Windows":
                QMessageBox.warning(self, "Помилка",
                    "Налаштування автозапуску доступне лише на Windows системах.")
                return

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
                self.autorun_status_label.setStyleSheet("font-size: 10px; color: #d13438; padding: 5px;")

                QMessageBox.information(self, "Успіх!",
                    "Автозапуск успішно видалено!\n\n"
                    "Додаток більше не буде запускатися автоматично при старті Windows.")

            except OSError:
                # Entry doesn't exist
                self.autorun_status_label.setText("Статус автозапуску: ❌ Вимкнено")
                self.autorun_status_label.setStyleSheet("font-size: 10px; color: #d13438; padding: 5px;")
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
        try:
            if platform.system() != "Windows":
                self.autorun_status_label.setText("Статус автозапуску: Не Windows")
                self.autorun_status_label.setStyleSheet("font-size: 10px; color: #666; padding: 5px;")
                return

            import winreg
            key = winreg.HKEY_CURRENT_USER
            subkey = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            app_name = "DesktopOrganizer"

            try:
                with winreg.OpenKey(key, subkey, 0, winreg.KEY_READ) as registry_key:
                    # Try to read the value
                    value, _ = winreg.QueryValueEx(registry_key, app_name)
                    self.autorun_status_label.setText("Статус автозапуску: ✅ Активно")
                    self.autorun_status_label.setStyleSheet("font-size: 10px; color: #107c10; padding: 5px;")
            except OSError:
                self.autorun_status_label.setText("Статус автозапуску: ❌ Вимкнено")
                self.autorun_status_label.setStyleSheet("font-size: 10px; color: #d13438; padding: 5px;")

        except ImportError:
            self.autorun_status_label.setText("Статус автозапуску: Невідомо")
        except Exception as e:
            self.autorun_status_label.setText("Статус автозапуску: Помилка")

    def create_file_manager_tab(self):
        """Create the file manager settings tab"""
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #f5f5f5;
            }
            QScrollBar:vertical {
                background-color: #f0f0f0;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a0a0a0;
            }
        """)

        # Create content widget
        tab_fm = QWidget()
        main_layout = QVBoxLayout(tab_fm)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # File size limit (keep existing functionality)
        size_group = QGroupBox("Обмеження Розміру Файлу")
        size_layout = QHBoxLayout(size_group)
        size_layout.addWidget(QLabel("Макс. розмір файлу:"))
        self.spin_max_size = self._create_spinbox(1, 10240, " MB")
        size_layout.addWidget(self.spin_max_size)
        size_layout.addStretch()
        main_layout.addWidget(size_group)

        # Common presets section
        presets_group = self._create_presets_section()
        main_layout.addWidget(presets_group)

        # File filters section
        filters_splitter = QWidget()
        filters_layout = QHBoxLayout(filters_splitter)
        filters_layout.setSpacing(20)

        # File extensions filter group
        ext_group = self._create_enhanced_filter_group("extension")
        filters_layout.addWidget(ext_group, 1)

        # File names filter group
        name_group = self._create_enhanced_filter_group("filename")
        filters_layout.addWidget(name_group, 1)

        main_layout.addWidget(filters_splitter)

        # Actions section
        actions_group = self._create_filter_actions_section()
        main_layout.addWidget(actions_group)

        main_layout.addStretch()

        # Set up scroll area
        scroll_area.setWidget(tab_fm)
        self.tabs.addTab(scroll_area, "Фільтри Файлів")

    def _create_presets_section(self) -> QGroupBox:
        """Create common filter presets section"""
        presets_group = QGroupBox("Шаблонні Набори Фільтрів")
        presets_layout = QVBoxLayout(presets_group)

        # First row of preset buttons
        buttons_layout1 = QHBoxLayout()

        self.btn_preset_system = QPushButton("Системні Файли")
        self.btn_preset_system.clicked.connect(lambda: self.apply_preset("system"))
        self.btn_preset_system.setToolTip("Пропускати системні файли Windows")

        self.btn_preset_media = QPushButton("Медіа Файли")
        self.btn_preset_media.clicked.connect(lambda: self.apply_preset("media"))
        self.btn_preset_media.setToolTip("Пропускати медіа файли (зображення, відео, аудіо)")

        self.btn_preset_docs = QPushButton("Документи")
        self.btn_preset_docs.clicked.connect(lambda: self.apply_preset("documents"))
        self.btn_preset_docs.setToolTip("Пропускати файли документів")

        self.btn_preset_dev = QPushButton("Розробка")
        self.btn_preset_dev.clicked.connect(lambda: self.apply_preset("development"))
        self.btn_preset_dev.setToolTip("Пропускати файли розробки (код, білди)")

        buttons_layout1.addWidget(self.btn_preset_system)
        buttons_layout1.addWidget(self.btn_preset_media)
        buttons_layout1.addWidget(self.btn_preset_docs)
        buttons_layout1.addWidget(self.btn_preset_dev)
        buttons_layout1.addStretch()

        # Second row - Reservoir Simulation Software
        buttons_layout2 = QHBoxLayout()

        self.btn_preset_reservoir = QPushButton("Резервуарна Симуляція")
        self.btn_preset_reservoir.clicked.connect(lambda: self.apply_preset("reservoir"))
        self.btn_preset_reservoir.setToolTip("Пропускати файли резервуарної симуляції (ECLIPSE, PETREL, tNavigator)")

        self.btn_preset_cmgs = QPushButton("CMG Софт")
        self.btn_preset_cmgs.clicked.connect(lambda: self.apply_preset("cmg"))
        self.btn_preset_cmgs.setToolTip("Пропускати файли CMG (IMEX, GEM, STARS)")

        self.btn_preset_schlumberger = QPushButton("Schlumberger")
        self.btn_preset_schlumberger.clicked.connect(lambda: self.apply_preset("schlumberger"))
        self.btn_preset_schlumberger.setToolTip("Пропускати файли Schlumberger (ECLIPSE, INTERSECT, PETREL)")

        self.btn_preset_halliburton = QPushButton("Halliburton")
        self.btn_preset_halliburton.clicked.connect(lambda: self.apply_preset("halliburton"))
        self.btn_preset_halliburton.setToolTip("Пропускати файли Halliburton (NEXUS, VIP)")

        buttons_layout2.addWidget(self.btn_preset_reservoir)
        buttons_layout2.addWidget(self.btn_preset_cmgs)
        buttons_layout2.addWidget(self.btn_preset_schlumberger)
        buttons_layout2.addWidget(self.btn_preset_halliburton)
        buttons_layout2.addStretch()

        presets_layout.addLayout(buttons_layout1)
        presets_layout.addLayout(buttons_layout2)

        return presets_group

    def _create_enhanced_filter_group(self, filter_type: str) -> QGroupBox:
        """Create an enhanced filter group with better layout and functionality"""
        if filter_type == "extension":
            group_title = "Фільтри Розширень Файлів"
            placeholder = ".txt, .exe, .dll"
            search_placeholder = "Пошук розширень..."
        else:  # filename
            group_title = "Фільтри Імен Файлів"
            placeholder = "temp*, *cache*, config"
            search_placeholder = "Пошук імен файлів..."

        group = QGroupBox(group_title)
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid #cccccc;
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
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(12)
        group_layout.setContentsMargins(15, 20, 15, 15)  # Add more padding

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.setSpacing(10)
        search_layout.setContentsMargins(0, 5, 0, 10)

        search_edit = QLineEdit()
        search_edit.setPlaceholderText(search_placeholder)
        search_edit.setFixedHeight(28)  # Consistent height
        search_edit.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 2px solid #0078d4;
            }
        """)
        search_edit.textChanged.connect(lambda text, ft=filter_type: self.filter_list_items(ft))

        search_label = QLabel("Пошук:")
        search_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #555;")

        search_layout.addWidget(search_label)
        search_layout.addWidget(search_edit)
        group_layout.addLayout(search_layout)

        # List with better styling
        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)

        list_widget = QListWidget()
        list_widget.setAlternatingRowColors(True)
        list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        list_widget.setFixedHeight(140)  # Increased height for better visibility
        list_widget.setMinimumWidth(300)  # Set minimum width

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
        input_layout.setSpacing(12)
        input_layout.setContentsMargins(0, 15, 0, 0)  # Add top margin to move elements down

        # Input with validation
        input_group = QGroupBox("Додавання елемента")
        input_group_layout = QVBoxLayout(input_group)
        input_group_layout.setSpacing(10)

        edit_widget = QLineEdit()
        edit_widget.setPlaceholderText(placeholder)
        edit_widget.setFixedHeight(35)  # Increased height for better usability
        edit_widget.setMinimumWidth(250)  # Increased minimum width
        edit_widget.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 2px solid #ddd;
                border-radius: 6px;
                font-size: 12px;
                background-color: white;
            }
            QLineEdit:focus {
                border: 2px solid #0078d4;
                outline: none;
            }
        """)

        # Help text
        help_label = QLabel()
        if filter_type == "extension":
            help_label.setText("💡 Введіть розширення (напр., .txt) або декілька через кому")
        else:
            help_label.setText("💡 Використовуйте * (будь-які символи) та ? (один символ) для шаблонів")
        help_label.setStyleSheet("font-size: 10px; color: #888; margin: 5px 0;")
        help_label.setWordWrap(True)

        input_group_layout.addWidget(edit_widget)
        input_group_layout.addWidget(help_label)

        input_layout.addWidget(input_group)

        # Buttons section
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        buttons_layout.setContentsMargins(0, 10, 0, 0)  # Add top margin

        btn_add = QPushButton("Додати")
        btn_add.setFixedHeight(35)  # Increased height to match input field
        btn_add.setMinimumWidth(80)  # Set minimum width
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #666;
            }
        """)

        btn_remove = QPushButton("Видалити Вибране")
        btn_remove.setFixedHeight(35)  # Increased height
        btn_remove.setMinimumWidth(120)  # Set minimum width
        btn_remove.setEnabled(False)
        btn_remove.setStyleSheet("""
            QPushButton {
                background-color: #d13438;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #a4262c;
            }
            QPushButton:pressed {
                background-color: #8b1111;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #666;
            }
        """)

        btn_clear = QPushButton("Очистити Все")
        btn_clear.setFixedHeight(35)  # Increased height
        btn_clear.setMinimumWidth(100)  # Set minimum width
        btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #666;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #555;
            }
            QPushButton:pressed {
                background-color: #444;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #666;
            }
        """)

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
        actions_layout = QHBoxLayout(actions_group)
        actions_layout.setSpacing(15)

        # Import/Export buttons
        self.btn_import_filters = QPushButton("Імпортувати Фільтри")
        self.btn_import_filters.clicked.connect(self.import_filters)

        self.btn_export_filters = QPushButton("Експортувати Фільтри")
        self.btn_export_filters.clicked.connect(self.export_filters)

        self.btn_reset_filters = QPushButton("Скинути Усі")
        self.btn_reset_filters.clicked.connect(self.reset_all_filters)

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
                border: none;
                background-color: #f5f5f5;
            }
            QScrollBar:vertical {
                background-color: #f0f0f0;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a0a0a0;
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
                border: 2px solid #cccccc;
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
                border: 2px solid #0078d4;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #0078d4;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 20, 15, 15)

        # Description
        desc = QLabel("Windows Task Scheduler забезпечує більш надійне виконання завдань, "
                     "навіть коли додаток закрито. Система працюватиме у фоновому режимі.")
        desc.setStyleSheet("font-size: 11px; color: #555; background-color: #f0f8ff; padding: 10px; border-radius: 4px;")
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
        self.create_task_btn.setStyleSheet("""
            QPushButton {
                background-color: #107c10;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #0e6e0e;
            }
        """)
        self.create_task_btn.setFixedHeight(35)
        self.create_task_btn.setMinimumWidth(120)

        self.remove_task_btn = QPushButton("Видалити Завдання")
        self.remove_task_btn.clicked.connect(self.remove_windows_task)
        self.remove_task_btn.setStyleSheet("""
            QPushButton {
                background-color: #d13438;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #a4262c;
            }
        """)
        self.remove_task_btn.setFixedHeight(35)
        self.remove_task_btn.setMinimumWidth(120)

        self.open_task_scheduler_btn = QPushButton("Відкрити Task Scheduler")
        self.open_task_scheduler_btn.clicked.connect(self.open_windows_task_scheduler)
        self.open_task_scheduler_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
        """)
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
                border: 2px solid #666;
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
        self.current_status_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #d13438;")
        layout.addWidget(self.current_status_label)

        # Next run time
        self.next_run_label = QLabel("Наступне виконання: Н/Д")
        self.next_run_label.setStyleSheet("font-size: 11px; color: #666;")
        layout.addWidget(self.next_run_label)

        # Time remaining
        self.time_remaining_label = QLabel("Час до виконання: Н/Д")
        self.time_remaining_label.setStyleSheet("font-size: 11px; color: #107c10; font-weight: bold;")
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
        self.test_schedule_btn = QPushButton("Тестовий Запуск")
        self.test_schedule_btn.clicked.connect(self.test_schedule)
        self.test_schedule_btn.setFixedHeight(30)
        self.test_schedule_btn.setMinimumWidth(100)

        self.refresh_status_btn = QPushButton("Оновити Статус")
        self.refresh_status_btn.clicked.connect(self.refresh_schedule_status)
        self.refresh_status_btn.setFixedHeight(30)
        self.refresh_status_btn.setMinimumWidth(100)

        actions_layout.addWidget(self.test_schedule_btn)
        actions_layout.addWidget(self.refresh_status_btn)
        actions_layout.addStretch()

        layout.addLayout(actions_layout)

        return group

      # Windows Task Scheduler functionality
    def check_windows_scheduler_status(self):
        """Check if Windows Task Scheduler is available and task exists"""
        try:
            import ctypes
            # Check if running on Windows
            if platform.system() != "Windows":
                self.scheduler_status_label.setText("Статус: Не Windows система")
                self.scheduler_status_label.setStyleSheet("font-weight: bold; color: #666;")
                return

            # Check admin privileges
            try:
                is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            except:
                is_admin = False

            if not is_admin:
                self.scheduler_status_label.setText("Статус: Потрібні права адміністратора")
                self.scheduler_status_label.setStyleSheet("font-weight: bold; color: #f9a825;")
                return

            # Check if task exists
            task_exists = self._check_task_exists()
            if task_exists:
                self.scheduler_status_label.setText("Статус: Завдання створено ✅")
                self.scheduler_status_label.setStyleSheet("font-weight: bold; color: #107c10;")
                self.create_task_btn.setEnabled(False)
                self.remove_task_btn.setEnabled(True)
            else:
                self.scheduler_status_label.setText("Статус: Завдання не створено")
                self.scheduler_status_label.setStyleSheet("font-weight: bold; color: #d13438;")
                self.create_task_btn.setEnabled(True)
                self.remove_task_btn.setEnabled(False)

        except Exception as e:
            self.scheduler_status_label.setText(f"Статус: Помилка - {str(e)}")
            self.scheduler_status_label.setStyleSheet("font-weight: bold; color: #d13438;")

    def _check_task_exists(self) -> bool:
        """Check if the Windows Task exists"""
        try:
            result = subprocess.run([
                'schtasks', '/Query', '/TN', 'DesktopOrganizer'
            ], capture_output=True, text=True, timeout=10)
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
            ], capture_output=True, text=True, timeout=30)

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
                ], capture_output=True, text=True, timeout=15)

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

    def test_schedule(self):
        """Test schedule trigger logic and organization process"""
        try:
            reply = QMessageBox.question(
                self,
                "Тестовий Запуск Розкладу",
                "Бажаєте виконати тестовий запуск розкладу?\n\n"
                "Це перевірить логіку розкладу (день, час, завантаження ЦП) "
                "і симулює організацію робочого столу.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Yes:
                # Create progress dialog
                progress = QProgressDialog("Перевірка логіки розкладу...", "Скасувати", 0, 100, self)
                progress.setWindowTitle("Тест Розкладу")
                progress.setWindowModality(Qt.WindowModal)
                progress.setMinimumDuration(0)
                progress.show()

                try:
                    # Step 1: Get current settings
                    progress.setLabelText("Завантаження налаштувань...")
                    progress.setValue(10)
                    QApplication.processEvents()

                    # Get current settings from parent
                    parent_window = self.parent()
                    if parent_window and hasattr(parent_window, 'current_settings'):
                        settings = parent_window.current_settings
                    elif hasattr(self, 'current_settings'):
                        settings = self.current_settings
                    else:
                        settings = {}

                    app_settings = settings.get('application', DEFAULT_SETTINGS['application'])
                    schedule_cfg = settings.get('schedule', DEFAULT_SETTINGS['schedule'])
                    schedule_type = schedule_cfg.get('type', 'disabled')

                    progress.setValue(20)
                    QApplication.processEvents()

                    # Step 2: Test schedule logic
                    progress.setLabelText("Перевірка логіки розкладу...")
                    progress.setValue(30)
                    QApplication.processEvents()

                    now = datetime.now()
                    today = now.date()
                    current_time = QTime.currentTime()

                    # Schedule test results
                    schedule_results = []

                    # Initialize would_run_now variable
                    would_run_now = False

                    # Check if schedule is enabled
                    if schedule_type == 'disabled':
                        schedule_results.append("❌ Розклад вимкнено")
                    elif not app_settings.get('autostart_timer_enabled', True):
                        schedule_results.append("❌ Автозапуск таймера вимкнено")
                    else:
                        schedule_results.append(f"✅ Розклад увімкнено: {schedule_type}")

                        # Test if today is a scheduled day
                        if is_scheduled_day(schedule_cfg):
                            schedule_results.append(f"✅ Сьогодні ({today.strftime('%Y-%m-%d')}) є scheduled day")

                            # Test time window
                            start_time = QTime.fromString(schedule_cfg.get('time_start', '22:00'), "HH:mm")
                            end_time = QTime.fromString(schedule_cfg.get('time_end', '23:00'), "HH:mm")

                            schedule_results.append(f"⏰ Вікно розкладу: {start_time.toString('HH:mm')} - {end_time.toString('HH:mm')}")
                            schedule_results.append(f"🕐 Поточний час: {current_time.toString('HH:mm:ss')}")

                            if start_time <= current_time <= end_time:
                                schedule_results.append("✅ Поточний час у вікні розкладу")

                                # Test CPU usage
                                progress.setLabelText("Перевірка завантаження ЦП...")
                                progress.setValue(40)
                                QApplication.processEvents()

                                cpu_usage = psutil.cpu_percent(interval=1)
                                schedule_results.append(f"🖥️ Поточне завантаження ЦП: {cpu_usage:.1f}%")

                                if cpu_usage < 15.0:
                                    schedule_results.append("✅ Низьке завантаження ЦП - організація запуститься")
                                    would_run_now = True
                                else:
                                    schedule_results.append("⚠️ Високе завантаження ЦП - організація відкладена")
                                    would_run_now = False
                            elif current_time > end_time:
                                schedule_results.append("⚠️ Час вікна розкладу минув - організація запуститься зараз")
                                would_run_now = True
                            else:
                                schedule_results.append("⏳ Час ще не настав - організація запуститься пізніше")
                                would_run_now = False
                        else:
                            schedule_results.append(f"❌ Сьогодні не є scheduled day для розкладу {schedule_type}")
                            would_run_now = False

                    progress.setValue(50)
                    QApplication.processEvents()

                    # Step 3: Check target drive
                    progress.setLabelText("Перевірка цільового диска...")
                    progress.setValue(60)
                    QApplication.processEvents()

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
                        if drive_policy == 'auto':
                            schedule_results.append(f"❌ Не знайдено доступного диска для політики 'auto'")
                        else:
                            schedule_results.append(f"❌ Цільовий диск {target_drive}: не знайдено")
                        progress.setValue(100)
                        QMessageBox.warning(self, "Попередження", f"Цільовий диск не знайдено!")
                        progress.close()
                        return
                    else:
                        if drive_policy == 'auto':
                            schedule_results.append(f"✅ Знайдено диск {target_drive}: для політики 'auto'")
                        else:
                            schedule_results.append(f"✅ Цільовий диск {target_drive}: доступний")

                    # Step 4: Test organization logic if conditions are met
                    if would_run_now and schedule_type != 'disabled':
                        progress.setLabelText("Симуляція організації робочого столу...")
                        progress.setValue(70)
                        QApplication.processEvents()

                        desktop_path = os.path.expanduser("~/Desktop")
                        if not os.path.exists(desktop_path):
                            desktop_path = os.path.expanduser("~/Робочий стіл")

                        file_count = 0
                        would_move_count = 0
                        affected_files = []

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
                                if file_count <= 50:  # Only scan first 50 files for speed
                                    # Apply filter logic
                                    is_file = os.path.isfile(item_path)
                                    file_ext = os.path.splitext(item)[1].lower()
                                    item_name_no_ext, _ = os.path.splitext(item)

                                    would_move = True

                                    if allowed_extensions and file_ext not in allowed_extensions:
                                        would_move = False
                                    elif allowed_filenames and item_name_no_ext not in allowed_filenames:
                                        would_move = False
                                    elif is_file:
                                        try:
                                            file_size = os.path.getsize(item_path)
                                            if file_size > max_size_bytes:
                                                would_move = False
                                        except:
                                            pass

                                    if would_move:
                                        would_move_count += 1
                                        if len(affected_files) < 10:
                                            affected_files.append(f"📄 {item}")

                        schedule_results.append(f"📁 На робочому столі: {file_count} файлів/папок")
                        schedule_results.append(f"📋 Було б переміщено: {would_move_count} файлів")

                    progress.setValue(90)
                    QApplication.processEvents()

                    # Step 5: Show complete results
                    progress.setLabelText("Формування результатів...")
                    progress.setValue(95)
                    QApplication.processEvents()

                    progress.close()

                    # Build comprehensive results message
                    result_msg = f"🧪 Тест розкладу завершено!\n\n"

                    result_msg += f"📅 Налаштування розкладу:\n"
                    result_msg += f"  • Тип: {schedule_type}\n"
                    if schedule_type != 'disabled':
                        result_msg += f"  • Час: {schedule_cfg.get('time_start', '22:00')} - {schedule_cfg.get('time_end', '23:00')}\n"
                        if schedule_type == 'weekly':
                            day_names = ['Понеділок', 'Вівторок', 'Середа', 'Четвер', 'П\'ятниця', 'Субота', 'Неділя']
                            day_idx = schedule_cfg.get('day_of_week', 1) - 1
                            result_msg += f"  • День: {day_names[day_idx]}\n"
                        elif schedule_type == 'monthly':
                            result_msg += f"  • День місяця: {schedule_cfg.get('day_of_month', 1)}\n"
                        elif schedule_type == 'quarterly':
                            quarter_names = ['Перший', 'Другий', 'Третій']
                            month_idx = schedule_cfg.get('quarter_month', 1) - 1
                            result_msg += f"  • Місяць кварталу: {quarter_names[month_idx]}\n"
                            result_msg += f"  • День: {schedule_cfg.get('quarter_day', 1)}\n"

                        # Calculate and show time remaining
                        next_run_datetime, time_remaining = self.calculate_time_remaining(schedule_cfg)
                        if next_run_datetime:
                            result_msg += f"  • Час до наступного запуску: {time_remaining}\n"
                        else:
                            result_msg += f"  • Час до наступного запуску: {time_remaining}\n"
                    result_msg += "\n"

                    result_msg += f"🔍 Результати перевірки:\n"
                    for result in schedule_results:
                        result_msg += f"  • {result}\n"
                    result_msg += "\n"

                    if would_run_now and schedule_type != 'disabled':
                        result_msg += f"🔍 Активні фільтри файлів:\n"
                        if allowed_extensions:
                            ext_list = list(allowed_extensions)
                            result_msg += f"  • Дозволені розширення: {', '.join(ext_list[:3])}"
                            if len(ext_list) > 3:
                                result_msg += f" (+{len(ext_list)-3} ще)"
                            result_msg += "\n"
                        if allowed_filenames:
                            name_list = list(allowed_filenames)
                            result_msg += f"  • Дозволені імена: {', '.join(name_list[:3])}"
                            if len(name_list) > 3:
                                result_msg += f" (+{len(name_list)-3} ще)"
                            result_msg += "\n"
                        result_msg += f"  • Максимальний розмір файлу: {fm_settings.get('max_file_size_mb', 100)}MB\n\n"

                        if affected_files:
                            result_msg += f"📋 Файли, що були б переміщені:\n"
                            for file in affected_files:
                                result_msg += f"  {file}\n"

                    # Tray minimization info
                    result_msg += f"\n🖥️ Статус мінімізації в трей:\n"
                    if app_settings.get('minimize_to_tray', False):
                        result_msg += "  • Мінімізація в трей: ✅ Увімкнено\n"
                        result_msg += "  • Додаток буде мінімізовано в трей після закриття\n"
                        result_msg += "  • Доступ через іконку в системному треї\n"
                    else:
                        result_msg += "  • Мінімізація в трей: ❌ Вимкнено\n"
                        result_msg += "  • Додаток буде повністю закриватися\n"

                    # Final recommendation
                    result_msg += f"\n💡 Висновок:\n"
                    if schedule_type == 'disabled':
                        result_msg += "  Розклад вимкнено. Увімкніть його в налаштуваннях для автоматичної організації."
                    elif would_run_now:
                        if app_settings.get('minimize_to_tray', False):
                            result_msg += "  Умови для організації виконані! Розклад працює правильно.\n"
                            result_msg += "  Додаток буде працювати у фонці з доступом через трей."
                        else:
                            result_msg += "  Умови для організації виконані! Розклад працює правильно."
                    else:
                        result_msg += "  Умови для організації ще не настанули. Розклад перевірить пізніше."

                    QMessageBox.information(self, "Результати Тесту Розкладу", result_msg)

                except Exception as e:
                    progress.close()
                    QMessageBox.critical(self, "Помилка", f"Помилка під час тесту розкладу:\n{e}")

                self.refresh_schedule_status()

        except Exception as e:
            QMessageBox.critical(self, "Помилка",
                               f"Помилка тестування розкладу:\n{str(e)}")

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
                self.current_status_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #d13438;")
                self.next_run_label.setText("Наступне виконання: Н/Д")
                self.time_remaining_label.setText("Час до виконання: Н/Д")
                self.last_run_label.setText("Останнє виконання: Н/Д")
                self.tray_info_label.setText("Мінімізація в трей: Н/Д")
            else:
                # Check if Windows task exists
                if self._check_task_exists():
                    self.current_status_label.setText("Поточний статус: Активно (Windows Task)")
                    self.current_status_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #107c10;")
                else:
                    self.current_status_label.setText("Поточний статус: Налаштовано (Тільки в додатку)")
                    self.current_status_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #f9a825;")

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
                        self.time_remaining_label.setStyleSheet("font-size: 11px; color: #d13438; font-weight: bold;")
                    elif hours_remaining < 24:
                        self.time_remaining_label.setStyleSheet("font-size: 11px; color: #f9a825; font-weight: bold;")
                    else:
                        self.time_remaining_label.setStyleSheet("font-size: 11px; color: #107c10; font-weight: bold;")
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
                        self.tray_info_label.setStyleSheet("font-size: 11px; color: #107c10;")
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
                border: none;
                background-color: #f5f5f5;
            }
            QScrollBar:vertical {
                background-color: #f0f0f0;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a0a0a0;
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

        # Advanced Operations Section
        advanced_group = self._create_advanced_operations_section()
        main_layout.addWidget(advanced_group)

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
                border: 2px solid #0078d4;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #0078d4;
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
        self.venv_path_label.setStyleSheet("font-size: 11px; color: #555; padding: 8px; background-color: #f5f5f5; border-radius: 4px;")
        layout.addWidget(self.venv_path_label)

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
        self.repair_venv_btn.setStyleSheet("""
            QPushButton {
                background-color: #f9a825;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #e68900;
            }
        """)
        self.repair_venv_btn.setFixedHeight(30)
        self.repair_venv_btn.setMinimumWidth(80)

        self.recreate_venv_btn = QPushButton("Перестворити")
        self.recreate_venv_btn.clicked.connect(self.recreate_virtual_environment)
        self.recreate_venv_btn.setStyleSheet("""
            QPushButton {
                background-color: #d13438;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #a4262c;
            }
        """)
        self.recreate_venv_btn.setFixedHeight(30)
        self.recreate_venv_btn.setMinimumWidth(90)

        actions_layout.addWidget(self.repair_venv_btn)
        actions_layout.addWidget(self.recreate_venv_btn)
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
                border: 2px solid #107c10;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #107c10;
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
                border: 2px solid #0078d4;
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
                background-color: #0078d4;
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
                border: 2px solid #0078d4;
            }
        """)
        input_layout.addWidget(self.package_input)

        self.install_package_btn = QPushButton("Встановити")
        self.install_package_btn.clicked.connect(self.install_user_package)
        self.install_package_btn.setStyleSheet("""
            QPushButton {
                background-color: #107c10;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #0e6e0e;
            }
        """)
        self.install_package_btn.setFixedHeight(35)
        input_layout.addWidget(self.install_package_btn)

        install_layout.addLayout(input_layout)
        layout.addWidget(install_group)

        # Package management buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        self.upgrade_packages_btn = QPushButton("Оновити Всі")
        self.upgrade_packages_btn.clicked.connect(self.upgrade_all_packages)
        self.upgrade_packages_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
        """)
        self.upgrade_packages_btn.setFixedHeight(30)

        self.uninstall_package_btn = QPushButton("Видалити Вибрані")
        self.uninstall_package_btn.clicked.connect(self.uninstall_selected_packages)
        self.uninstall_package_btn.setEnabled(False)
        self.uninstall_package_btn.setStyleSheet("""
            QPushButton {
                background-color: #d13438;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #a4262c;
            }
        """)
        self.uninstall_package_btn.setFixedHeight(30)

        self.refresh_packages_btn = QPushButton("Оновити Список")
        self.refresh_packages_btn.clicked.connect(self.refresh_package_list)
        self.refresh_packages_btn.setStyleSheet("""
            QPushButton {
                background-color: #666;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #555;
            }
        """)
        self.refresh_packages_btn.setFixedHeight(30)

        buttons_layout.addWidget(self.upgrade_packages_btn)
        buttons_layout.addWidget(self.uninstall_package_btn)
        buttons_layout.addWidget(self.refresh_packages_btn)
        buttons_layout.addStretch()

        layout.addLayout(buttons_layout)

        # Connect selection change
        self.packages_list.itemSelectionChanged.connect(self.update_package_buttons)

        return group

    def _create_advanced_operations_section(self) -> QGroupBox:
        """Create advanced operations section"""
        group = QGroupBox("Розширені Операції")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid #5c2d91;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #5c2d91;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 20, 15, 15)

        # Export/Import functionality
        io_layout = QHBoxLayout()
        io_layout.setSpacing(10)

        self.export_requirements_btn = QPushButton("Експортувати requirements.txt")
        self.export_requirements_btn.clicked.connect(self.export_requirements)
        self.export_requirements_btn.setStyleSheet("""
            QPushButton {
                background-color: #5c2d91;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background-color: #4a2375;
            }
        """)
        self.export_requirements_btn.setFixedHeight(35)

        self.import_requirements_btn = QPushButton("Імпортувати з requirements.txt")
        self.import_requirements_btn.clicked.connect(self.import_requirements)
        self.import_requirements_btn.setStyleSheet("""
            QPushButton {
                background-color: #5c2d91;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background-color: #4a2375;
            }
        """)
        self.import_requirements_btn.setFixedHeight(35)

        io_layout.addWidget(self.export_requirements_btn)
        io_layout.addWidget(self.import_requirements_btn)
        io_layout.addStretch()

        layout.addLayout(io_layout)

        # Dangerous operations
        danger_layout = QHBoxLayout()
        danger_layout.setSpacing(10)

        self.cleanup_venv_btn = QPushButton("Очистити Кеш")
        self.cleanup_venv_btn.clicked.connect(self.cleanup_virtual_environment_cache)
        self.cleanup_venv_btn.setStyleSheet("""
            QPushButton {
                background-color: #f9a825;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #e68900;
            }
        """)
        self.cleanup_venv_btn.setFixedHeight(30)

        self.reset_venv_btn = QPushButton("Скинути Віртуальне Середовище")
        self.reset_venv_btn.clicked.connect(self.reset_virtual_environment)
        self.reset_venv_btn.setStyleSheet("""
            QPushButton {
                background-color: #d13438;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #a4262c;
            }
        """)
        self.reset_venv_btn.setFixedHeight(30)

        danger_layout.addWidget(self.cleanup_venv_btn)
        danger_layout.addWidget(self.reset_venv_btn)
        danger_layout.addStretch()

        layout.addLayout(danger_layout)

        return group

    def _create_environment_details_section(self) -> QGroupBox:
        """Create environment details section"""
        group = QGroupBox("Деталі Середовища")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid #666;
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
        self.python_version_label.setStyleSheet("font-size: 11px; color: #555;")
        layout.addWidget(self.python_version_label)

        # Pip version
        self.pip_version_label = QLabel("Pip: Обчислюється...")
        self.pip_version_label.setStyleSheet("font-size: 11px; color: #555;")
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

        # Update packages list
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

        # Update status
        if os.path.exists(venv_manager.venv_dir):
            self.venv_status_label.setText("✅ Віртуальне середовище створено")
            self.venv_status_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #107c10;")
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
            self.venv_status_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #d13438;")
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
            ], capture_output=True, text=True, timeout=10)

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
                ], capture_output=True, text=True, timeout=10)

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
                ], capture_output=True, text=True, timeout=600)

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
                ], capture_output=True, text=True, timeout=30)

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
                    ], capture_output=True, text=True, timeout=600)

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
                        # Upgrade pip
                        subprocess.run([
                            pip_path, 'install', '--upgrade', 'pip'
                        ], capture_output=True, text=True, timeout=120)

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
            "Підтвердження Перестворення",
            "Ви впевнені, що хочете перестворити віртуальне середовище?\n\n"
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
                    ], capture_output=True, text=True, timeout=60)

                    QMessageBox.information(self, "Успіх", "Кеш успішно очищено")
                else:
                    QMessageBox.warning(self, "Попередження", "Pip не доступний для очищення кешу")

                self.refresh_venv_status()

            except Exception as e:
                QMessageBox.critical(self, "Помилка", f"Помилка очищення кешу:\n{str(e)}")

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
        self.chk_enable_autostart.setChecked(app_cfg.get('autostart_timer_enabled', True))

        # Load new application settings with defaults
        self.chk_enable_notifications.setChecked(app_cfg.get('notifications_enabled', True))
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
        """Load drive settings"""
        drive_cfg = self.current_settings.get('drives', DEFAULT_SETTINGS['drives'])
        policy = drive_cfg.get('main_drive_policy', 'D')
        if policy == 'auto':
            self.rb_drive_auto.setChecked(True)
        elif policy == 'C':
            self.rb_drive_c.setChecked(True)
        else:
            self.rb_drive_d.setChecked(True)

        # Update drive info label
        current_drive = policy if policy != 'auto' else 'Автоматичний'
        self.drive_info_label.setText(f"Поточний диск: {current_drive}")

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
        return {
            'autostart_timer_enabled': self.chk_enable_autostart.isChecked(),
            'notifications_enabled': self.chk_enable_notifications.isChecked(),
            'minimize_to_tray': self.chk_minimize_to_tray.isChecked()
        }

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
        """Accept dialog with auto-apply if changes not applied"""
        if not self.changes_applied:
            self.apply_changes()
        super().accept()


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

                # If allowed_extensions is not empty, only move files with those extensions
                if allowed_extensions and item_ext_lower not in allowed_extensions:
                    self.update_signal.emit(f"⏭️ Пропущено за розширенням: {item}")
                    continue

                # If allowed_filenames is not empty, only move files with those names
                if allowed_filenames and item_name_no_ext not in allowed_filenames:
                    self.update_signal.emit(f"⏭️ Пропущено за ім'ям файлу: {item}")
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

def find_next_available_drive():
    available_drives = []
    try:
        partitions = psutil.disk_partitions(all=False)
        for p in partitions:
            if platform.system() == "Windows" and re.match("^[A-Z]:\\?$", p.mountpoint) and p.mountpoint[0] != 'C':
                if p.fstype and 'cdrom' not in p.opts.lower():
                     if 'removable' not in p.opts.lower():
                         if os.path.exists(p.mountpoint):
                              available_drives.append(p.mountpoint[0])
        available_drives.sort()
        return available_drives[0] if available_drives else None
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
        self.module_manager = ModuleManager(self.get_module_dir())
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

            # Create tray menu
            self.tray_menu = QMenu()

            # Show/Hide action
            show_hide_action = QAction("Показати", self)
            show_hide_action.triggered.connect(self.toggle_window_visibility)
            self.tray_menu.addAction(show_hide_action)

            # Settings action
            settings_action = QAction("Налаштування", self)
            settings_action.triggered.connect(self.open_settings)
            self.tray_menu.addAction(settings_action)

            self.tray_menu.addSeparator()

            # Exit action
            exit_action = QAction("Вихід", self)
            exit_action.triggered.connect(self.force_close_application)
            self.tray_menu.addAction(exit_action)

            # Set menu for tray icon
            self.tray_icon.setContextMenu(self.tray_menu)

            # Connect double-click event
            self.tray_icon.activated.connect(self.on_tray_icon_activated)

            # Show the tray icon
            self.tray_icon.show()

            self.log_message("✅ System tray initialized successfully")

        except Exception as e:
            self.log_message(f"❌ Failed to initialize system tray: {e}")
            self.tray_icon = None
            self.tray_menu = None

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
        # Create and show settings dialog
        settings_dialog = SettingsDialog(self.settings, self)
        settings_dialog.settings_applied.connect(self.handle_settings_applied)
        settings_dialog.exec_()

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

        else:
            add_splash_message("ℹ️ No modules found")
            self.log_message("ℹ️ No modules found")

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
        self.log_message(f"❌ Помилка модуля ({module_name}): {error_message}")

    def update_modules_menu(self):
        """Update the modules menu based on loaded modules"""
        if hasattr(self, 'modules_menu'):
            self.modules_menu.clear()

            loaded_modules = self.module_manager.get_loaded_modules()
            discovered_modules = self.module_manager.module_info

            for module_name in discovered_modules:
                module_info = discovered_modules[module_name]
                is_loaded = module_name in loaded_modules

                action = QAction(module_info.menu_text, self)
                action.setEnabled(is_loaded)
                action.triggered.connect(lambda checked=False, name=module_name: self.open_module_window(name))

                self.modules_menu.addAction(action)
                self.module_actions[module_name] = action



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
        self.setFixedSize(991, 701)
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
        main_layout.addWidget(self.tab_widget)

        # --- Main Tab ---
        main_tab = QWidget()
        self.tab_widget.addTab(main_tab, "Головна")
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

        start_time = QTime.fromString(schedule_cfg.get('time_start', '22:00'), "HH:mm")
        end_time = QTime.fromString(schedule_cfg.get('time_end', '23:00'), "HH:mm")

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

        # Add startup messages to splash
        splash.add_message("⚙️ Initializing application...")
        splash.add_message("📚 Loading settings...")

        # Create main window (this may take time)
        window = MainWindow(is_scheduled_run=is_scheduled_run)

        splash.add_message("🖥️ Main window created...")
        splash.add_message("✅ Application ready!")

        # Add a small delay to show the final message, then fade out
        QTimer.singleShot(1500, lambda: splash.fade_out_and_close(800))
        window.show()

        # Clear global reference after splash is closed
        QTimer.singleShot(2500, lambda: globals().__setitem__('global_splash', None))

        sys.exit(app.exec_())