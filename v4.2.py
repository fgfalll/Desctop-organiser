import sys
import os
import importlib.util
import shutil
import yaml
import platform
import psutil
import re
from datetime import datetime, timedelta
from typing import Optional
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QButtonGroup, QComboBox,
    QMenuBar, QAction, QDialog, QTabWidget, QFormLayout,
    QSpinBox, QCheckBox, QLineEdit, QListWidget, QListWidgetItem,
    QDialogButtonBox, QMessageBox, QRadioButton, QGroupBox, QFileDialog, QTimeEdit, QSplashScreen
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QTime, QObject, QRect
from PyQt5.QtGui import QPainter, QFont, QColor, QPen, QPixmap, QBrush
import subprocess
import json
from pathlib import Path

# --- Configuration File Path ---
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".DesktopOrganizer")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yaml")
LAST_RUN_FILE = os.path.join(CONFIG_DIR, "last_run.txt")
os.makedirs(CONFIG_DIR, exist_ok=True)

# --- Default Settings ---
DEFAULT_SETTINGS = {
    'application': {
        'autostart_timer_enabled': True,
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
    """Add a message to the splash screen if it's active"""
    global global_splash
    if global_splash and hasattr(global_splash, 'add_message') and not getattr(global_splash, 'finished', False):
        global_splash.add_message(message)

# --- Module Management System ---

class ModuleInfo:
    """Represents information about a module with embedded manifest"""

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
        """Extract manifest embedded in the module file"""
        try:
            with open(self.module_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Look for embedded manifest between special markers
            start_marker = '"""MODULE_MANIFEST_START'
            end_marker = 'MODULE_MANIFEST_END"""'

            start_idx = content.find(start_marker)
            if start_idx == -1:
                raise ValueError("Module manifest not found in file")

            start_idx += len(start_marker)
            end_idx = content.find(end_marker, start_idx)
            if end_idx == -1:
                raise ValueError("Module manifest end marker not found")

            manifest_json = content[start_idx:end_idx].strip()
            manifest = json.loads(manifest_json)
            return manifest

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in manifest: {e}")
        except Exception as e:
            raise ValueError(f"Error reading module file: {e}")

    def _validate_manifest(self):
        """Validate required manifest fields"""
        required_fields = ['name', 'version', 'main_class']
        for field in required_fields:
            if field not in self.manifest:
                raise ValueError(f"Missing required field: {field}")

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
        """Returns a mapping of import names to pip package names"""
        # Support both old format and new format
        if 'dependency_packages' in self.manifest:
            return self.manifest['dependency_packages']

        # Auto-generate mapping for simple cases
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
    def python_version(self) -> str:
        return self.manifest.get('python_version', '3.8+')

    @property
    def author(self) -> str:
        return self.manifest.get('author', 'Unknown')

    @property
    def category(self) -> str:
        return self.manifest.get('category', 'General')


class SharedVirtualEnvironmentManager:
    """Manages a shared virtual environment for all modules"""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.venv_dir = os.path.join(base_dir, 'modules_venv')
        self.installed_packages = set()  # Track installed packages
        self.package_modules = {}  # Track which modules installed which packages
        # Store package info in the same directory as settings
        self.packages_file = os.path.join(CONFIG_DIR, 'module_packages.json')
        self._load_package_info()

    def _load_package_info(self):
        """Load package installation info from file and sync with actual venv"""
        try:
            # Check if we need to migrate from old location
            old_packages_file = os.path.join(self.base_dir, 'module_packages.json')
            if os.path.exists(old_packages_file) and not os.path.exists(self.packages_file):
                print(f"🔄 Migrating package info from {old_packages_file} to {self.packages_file}")
                try:
                    import shutil
                    shutil.move(old_packages_file, self.packages_file)
                    print(f"✅ Successfully migrated package info file")
                except Exception as e:
                    print(f"⚠️ Failed to migrate package info: {e}")
                    # Copy the data instead
                    try:
                        with open(old_packages_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        with open(self.packages_file, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=2)
                        print(f"✅ Successfully copied package info file")
                    except Exception as e2:
                        print(f"⚠️ Failed to copy package info: {e2}")

            if os.path.exists(self.packages_file):
                with open(self.packages_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.installed_packages = set(data.get('installed_packages', []))
                    self.package_modules = data.get('package_modules', {})
                print(f"📋 Loaded package info from {self.packages_file}")
            else:
                print(f"📋 No existing package info file found at {self.packages_file}")

            # Sync with actual packages in venv
            self._sync_installed_packages()
        except Exception as e:
            print(f"⚠️ Could not load package info: {e}")

    def _sync_installed_packages(self):
        """Sync the package list with what's actually installed in the venv"""
        try:
            pip_path = self.get_pip_path()
            if not pip_path:
                print("⚠️ Cannot sync packages: no pip available")
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

                print(f"🔄 Synced package list: {len(actual_packages)} packages found")
                print(f"📋 Tracking {new_count} total packages (added {new_count - old_count} new ones)")

                # Show some of the packages for debugging
                if actual_packages:
                    sample_packages = list(sorted(actual_packages))[:5]
                    print(f"📋 Sample packages: {', '.join(sample_packages)}...")
            else:
                print(f"⚠️ Failed to list packages: {result.stderr}")
        except Exception as e:
            print(f"⚠️ Could not sync package list: {e}")

    
    def _is_package_installed(self, package_name: str, use_cache: bool = True) -> bool:
        """Check if a package is actually installed in the venv"""
        # Use cache to avoid repeated checks
        cache_key = f"installed_{package_name.lower()}"
        if use_cache and hasattr(self, '_package_cache'):
            if cache_key in self._package_cache:
                return self._package_cache[cache_key]
        elif not hasattr(self, '_package_cache'):
            self._package_cache = {}

        # Check the exact package name - no smart resolution
        is_installed = self._check_package_direct(package_name)
        self._package_cache[cache_key] = is_installed

        # Only show detailed logging for first few checks
        if not use_cache or len(self._package_cache) < 5:
            if is_installed:
                print(f"✅ Package {package_name} is installed")
            else:
                print(f"❌ Package {package_name} is NOT installed")

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
            print("⚠️ Using legacy dependency_packages format. Consider updating to use dependencies array.")
            for import_name, package_spec in dependency_packages.items():
                pip_package_name = package_spec.split('>=')[0].split('==')[0].split('<=')[0].split('~=')[0].strip().lower()
                if pip_package_name not in packages:
                    packages[pip_package_name] = package_spec
                else:
                    # Keep the more specific requirement
                    if self._is_more_specific_requirement(package_spec, packages[pip_package_name]):
                        packages[pip_package_name] = package_spec

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
            print(f"💾 Saved package info to {self.packages_file}")
        except Exception as e:
            print(f"❌ Could not save package info: {e}")

    def create_shared_venv(self) -> bool:
        """Create shared virtual environment for all modules"""
        if os.path.exists(self.venv_dir):
            # Validate existing venv
            if self._validate_venv():
                print(f"✅ Using existing shared virtual environment: {self.venv_dir}")
                return True
            else:
                print(f"⚠️ Existing venv appears to have issues, attempting to use it anyway: {self.venv_dir}")
                print("💡 If you encounter issues, delete the modules_venv folder and restart")
                # Don't automatically delete - let user decide
                return True

        try:
            import venv
            venv.create(self.venv_dir, with_pip=True)
            print(f"✅ Created shared virtual environment: {self.venv_dir}")
            return True
        except Exception as e:
            print(f"❌ Failed to create shared venv: {e}")
            return False

    def _validate_venv(self) -> bool:
        """Validate that the existing venv is properly set up"""
        try:
            pip_path = self.get_pip_path()
            if not pip_path or not os.path.exists(pip_path):
                print(f"⚠️ Pip not found at {pip_path}")
                return False

            # Try to run pip to ensure it's working
            result = subprocess.run([pip_path, '--version'],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                print(f"⚠️ Pip not working: {result.stderr}")
                return False

            # Also check that we can list packages (this tests the venv more thoroughly)
            result = subprocess.run([pip_path, 'list', '--format=json'],
                                  capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                print(f"⚠️ Cannot list packages in venv: {result.stderr}")
                return False

            return True
        except Exception as e:
            print(f"⚠️ Venv validation failed: {e}")
            return False

    def get_pip_path(self) -> Optional[str]:
        """Get pip path for the shared virtual environment, fallback to system pip"""
        # Try venv pip first
        if os.path.exists(self.venv_dir):
            if sys.platform == "win32":
                venv_pip = os.path.join(self.venv_dir, 'Scripts', 'pip.exe')
            else:
                venv_pip = os.path.join(self.venv_dir, 'bin', 'pip')

            if os.path.exists(venv_pip):
                return venv_pip

        # Fallback to system pip
        try:
            # Check if pip is available in PATH
            result = subprocess.run(['pip', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print("💡 Using system pip (venv pip not available)")
                return 'pip'
        except Exception:
            pass

        # Try python -m pip as last resort
        try:
            result = subprocess.run([sys.executable, '-m', 'pip', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print("💡 Using python -m pip (pip not in PATH)")
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
            print(f"❌ Could not find pip for installing dependencies")
            return False

        try:

            # First, sync with actual venv packages to ensure we have accurate tracking
            self._sync_installed_packages()

            # Deduplicate dependencies from both sources
            deduplicated_packages = self._deduplicate_dependencies(dependencies, dependency_packages)

            if not deduplicated_packages:
                print(f"✅ No dependencies to install for {module_name}")
                return True

            print(f"📦 Processing {len(deduplicated_packages)} unique dependency(ies) for {module_name}: {list(deduplicated_packages.keys())}")

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
                    print(f"📦 Package {pip_package_name} not found, will install")
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
                            print(f"🔄 Package {pip_package_name} version mismatch, will upgrade (installed: {installed_version}, required: {version_req})")
                        else:
                            print(f"✅ Package {pip_package_name} v{installed_version} meets requirements")
                    else:
                        print(f"✅ Package {pip_package_name} already available in venv")

            if not packages_to_process:
                print(f"✅ All dependencies for {module_name} already satisfied in shared venv")
                return True

            # Process packages that need installation or upgrade
            for import_name, package_info in packages_to_process.items():
                package_spec = package_info['spec']
                action = package_info['action']
                reason = package_info['reason']

                action_emoji = "📦" if action == 'install' else "🔄"
                print(f"{action_emoji} {action.capitalize()}ing {package_spec} for module {module_name} ({reason})...")

                # Use pip install with --upgrade flag for upgrades
                if ' -m pip' in pip_path:
                    # Handle python -m pip format
                    cmd = pip_path.split() + ['install']
                else:
                    # Handle direct pip path
                    cmd = [pip_path, 'install']

                if action == 'upgrade':
                    cmd.append('--upgrade')
                cmd.append(package_spec)

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                    print(f"❌ Failed to {action} {package_spec}: {error_msg}")

                    # Try to provide helpful suggestions
                    if "could not find" in error_msg.lower() or "404" in error_msg:
                        print(f"💡 Tip: Package '{pip_package_name}' may not exist. Check the package name.")
                    elif "permission denied" in error_msg.lower():
                        print(f"💡 Tip: Permission denied. Try running with appropriate privileges.")
                    elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                        print(f"💡 Tip: Network error. Check your internet connection.")
                    elif "already satisfied" in error_msg.lower():
                        print(f"✅ Package {package_spec} is already installed")
                        continue  # Continue with next package

                    return False
                else:
                    print(f"✅ Successfully {'installed' if action == 'install' else 'upgraded'} {package_spec}")

                    # Update our tracking
                    installed_package_name = package_spec.split('>=')[0].split('==')[0].split('<=')[0].split('~=')[0].strip().lower()

                    self.installed_packages.add(installed_package_name)

                    if installed_package_name not in self.package_modules:
                        self.package_modules[installed_package_name] = []
                    # Track module->package relationship
                    if module_name not in self.package_modules[installed_package_name]:
                        self.package_modules[installed_package_name].append(module_name)
                        print(f"📋 Tracked {installed_package_name} for module {module_name}")

            self._save_package_info()
            return True

        except Exception as e:
            print(f"❌ Error installing dependencies: {e}")
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
            print(f"❌ Error uninstalling dependencies: {e}")
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
            print(f"❌ Modules directory not found: {self.modules_dir}")
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
            if module_info.dependencies or module_info.dependency_packages:
                all_deps_installed = True

                # Check each dependency package with version requirements
                missing_deps = []
                if module_info.dependency_packages:
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
            print(f"❌ Module not found: {module_name}")
            return False

        module_info = self.module_info[module_name]
        dependencies = module_info.dependencies
        dependency_packages = module_info.dependency_packages

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
            print(f"❌ Module not found: {module_name}")
            return False

        module_info = self.module_info[module_name]

        try:
            # Dependencies should already be installed during validation
            # Only install if validation was skipped or failed
            dependencies = module_info.dependencies
            dependency_packages = module_info.dependency_packages

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
                raise ImportError(f"Could not create spec for module {module_name}")

            module = importlib.util.module_from_spec(spec)

            # Add to sys.modules
            sys.modules[f"module_{module_name}"] = module

            # Execute the module
            spec.loader.exec_module(module)

            # Get the main class
            if not hasattr(module, module_info.main_class):
                raise ImportError(f"Module {module_name} does not have class {module_info.main_class}")

            module_class = getattr(module, module_info.main_class)
            self.loaded_modules[module_name] = module_class

            print(f"✅ Successfully loaded module: {module_name}")
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

        # Add initial messages
        self.add_message("🚀 Starting Desktop Organizer v4.2...")
        self.add_message(f"📍 Python version: {sys.version.split()[0]}")
        self.add_message(f"💻 Platform: {platform.system()} {platform.release()}")

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
        """Draw the modern splash screen contents"""
        # Draw background
        self.drawBackground(painter)

        # Set up modern fonts
        title_font = QFont("Segoe UI", 24, QFont.Bold)
        subtitle_font = QFont("Segoe UI", 12, QFont.Medium)
        console_font = QFont("Consolas", 10)
        status_font = QFont("Segoe UI", 9)

        # Draw main title with shadow effect
        painter.setFont(title_font)

        # Draw shadow
        painter.setPen(QPen(QColor(0, 0, 0, 100)))
        title_shadow_rect = QRect(52, 52, self.splash_width - 104, 40)
        painter.drawText(title_shadow_rect, Qt.AlignCenter, "Desktop Organizer v4.2")

        # Draw main title
        painter.setPen(QPen(QColor(255, 255, 255)))
        title_rect = QRect(50, 50, self.splash_width - 100, 40)
        painter.drawText(title_rect, Qt.AlignCenter, "Desktop Organizer v4.2")

        # Draw subtitle
        painter.setFont(subtitle_font)
        painter.setPen(QPen(QColor(180, 180, 185)))
        subtitle_rect = QRect(50, 95, self.splash_width - 100, 25)
        painter.drawText(subtitle_rect, Qt.AlignCenter, "Automated File Organization & Module Management")

        # Draw console area background (expanded to use available space)
        console_rect = QRect(50, 140, self.splash_width - 100, 280)

        # Console background with gradient
        console_gradient = QColor(30, 30, 35)
        painter.fillRect(console_rect, console_gradient)

        # Console border with glow effect
        painter.setPen(QPen(QColor(60, 60, 65), 2))
        painter.drawRect(console_rect)

        # Draw console header
        header_rect = QRect(55, 145, self.splash_width - 110, 30)
        header_gradient = QColor(45, 45, 50)
        painter.fillRect(header_rect, header_gradient)

        # Console title
        painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
        painter.setPen(QPen(QColor(100, 200, 255)))
        console_title_rect = QRect(65, 150, self.splash_width - 130, 20)
        painter.drawText(console_title_rect, Qt.AlignLeft, "📋 Console Output")

        # Draw console messages
        painter.setFont(console_font)
        y_offset = 185
        # Calculate available space for messages (console height - header - margin)
        available_height = 280 - 35 - 10  # Total height - header - bottom margin
        max_visible_messages = available_height // 18  # 18px per message line
        visible_messages = min(max_visible_messages, len(self.console_messages))

        # Calculate console boundaries
        console_bottom = 140 + 280 - 10  # Console start + height - bottom margin
        max_y_offset = console_bottom - 18  # Leave space for one line

        for i, message in enumerate(self.console_messages[-visible_messages:]):
            # Stop if we've reached the bottom of the console area
            if y_offset > max_y_offset:
                break

            # Color code messages based on content with enhanced colors
            if "✅" in message or "🚀" in message:
                painter.setPen(QPen(QColor(100, 255, 150)))  # Bright green
            elif "❌" in message or "🔴" in message:
                painter.setPen(QPen(QColor(255, 100, 120)))  # Bright red
            elif "⚠️" in message:
                painter.setPen(QPen(QColor(255, 200, 100)))  # Orange
            elif "📦" in message:
                painter.setPen(QPen(QColor(150, 200, 255)))  # Light blue
            elif "🔍" in message:
                painter.setPen(QPen(QColor(200, 150, 255)))  # Purple
            elif "⚙️" in message:
                painter.setPen(QPen(QColor(150, 255, 200)))  # Mint
            elif "ℹ️" in message:
                painter.setPen(QPen(QColor(255, 255, 150)))  # Yellow
            else:
                painter.setPen(QPen(QColor(220, 220, 225)))  # Light gray

            # Ensure text stays within console boundaries
            message_rect = QRect(65, y_offset, self.splash_width - 140, 16)
            painter.drawText(message_rect, Qt.AlignLeft, message)
            y_offset += 18

        
    def drawBackground(self, painter):
        """Draw the modern background"""
        # Create gradient background
        gradient = QColor(45, 45, 48)  # Dark modern background

        # Draw main rounded rectangle
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.splash_width, self.splash_height, 20, 20)

        # Draw subtle inner border
        painter.setPen(QPen(QColor(80, 80, 85), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(2, 2, self.splash_width - 4, self.splash_height - 4, 18, 18)

        # Draw top accent bar (static)
        accent_width = int(self.splash_width * 0.6)
        accent_x = (self.splash_width - accent_width) // 2

        accent_gradient = QColor(100, 200, 255)  # Blue accent
        painter.fillRect(accent_x, 8, accent_width, 4, accent_gradient)

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
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.create_general_tab()
        self.create_file_manager_tab()
        self.create_schedule_tab()
        self.create_virtual_environment_tab()

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.load_settings_to_ui()
        self.changes_applied = False

    def create_general_tab(self):
        tab_general = QWidget()
        layout = QVBoxLayout(tab_general)

        app_group = QGroupBox("Поведінка Додатку")
        app_layout = QFormLayout(app_group)
        self.chk_enable_autostart = QCheckBox("Автоматично запускати таймер при старті")
        app_layout.addRow(self.chk_enable_autostart)

        timer_group = QGroupBox("Налаштування Таймера")
        timer_layout = QFormLayout(timer_group)
        self.chk_override_timer = QCheckBox("Перевизначити тривалість таймера за замовчуванням")
        self.spin_default_timer = QSpinBox()
        self.spin_default_timer.setRange(1, 60)
        self.spin_default_timer.setSuffix(" хвилин")
        self.chk_override_timer.toggled.connect(self.spin_default_timer.setEnabled)
        timer_layout.addRow(self.chk_override_timer)
        timer_layout.addRow("Тривалість за замовчуванням:", self.spin_default_timer)

        drive_group = QGroupBox("Налаштування Дисків")
        drive_layout = QVBoxLayout(drive_group)
        drive_layout.addWidget(QLabel("Резервний диск завжди C:"))

        self.rb_drive_d = QRadioButton("Встановити основний диск D:")
        self.rb_drive_auto = QRadioButton("Автоматично визначити наступний доступний диск (незнімний)")
        drive_layout.addWidget(self.rb_drive_d)
        drive_layout.addWidget(self.rb_drive_auto)

        layout.addWidget(app_group)
        layout.addWidget(timer_group)
        layout.addWidget(drive_group)
        layout.addStretch()
        self.tabs.addTab(tab_general, "Загальні")

    def create_file_manager_tab(self):
        tab_fm = QWidget()
        layout = QFormLayout(tab_fm)

        self.spin_max_size = QSpinBox()
        self.spin_max_size.setRange(1, 10240)
        self.spin_max_size.setSuffix(" MB")
        layout.addRow("Макс. розмір файлу:", self.spin_max_size)

        ext_layout = QHBoxLayout()
        self.list_extensions = QListWidget()
        self.list_extensions.setFixedHeight(80)
        ext_controls_layout = QVBoxLayout()
        self.edit_add_ext = QLineEdit()
        self.edit_add_ext.setPlaceholderText(".приклад")
        btn_add_ext = QPushButton("Додати")
        btn_rem_ext = QPushButton("Видалити Вибране")
        btn_add_ext.clicked.connect(self.add_extension)
        btn_rem_ext.clicked.connect(self.remove_extension)
        ext_controls_layout.addWidget(self.edit_add_ext)
        ext_controls_layout.addWidget(btn_add_ext)
        ext_controls_layout.addWidget(btn_rem_ext)
        ext_layout.addWidget(self.list_extensions)
        ext_layout.addLayout(ext_controls_layout)
        layout.addRow("Пропускати розширення:", ext_layout)

        name_layout = QHBoxLayout()
        self.list_filenames = QListWidget()
        self.list_filenames.setFixedHeight(80)
        name_controls_layout = QVBoxLayout()
        self.edit_add_name = QLineEdit()
        self.edit_add_name.setPlaceholderText("ім'я_файлу_без_розширення")
        btn_add_name = QPushButton("Додати")
        btn_rem_name = QPushButton("Видалити Вибране")
        btn_add_name.clicked.connect(self.add_filename)
        btn_rem_name.clicked.connect(self.remove_filename)
        name_controls_layout.addWidget(self.edit_add_name)
        name_controls_layout.addWidget(btn_add_name)
        name_controls_layout.addWidget(btn_rem_name)
        name_layout.addWidget(self.list_filenames)
        name_layout.addLayout(name_controls_layout)
        layout.addRow("Пропускати імена файлів:", name_layout)

        self.tabs.addTab(tab_fm, "Фільтри Файлів")

    def create_schedule_tab(self):
        tab_schedule = QWidget()
        self.schedule_layout = QFormLayout(tab_schedule)

        self.schedule_type_combo = QComboBox()
        self.schedule_type_combo.addItems(["Вимкнено", "Щодня", "Щотижня", "Щомісяця", "Щокварталу"])
        self.schedule_type_combo.currentIndexChanged.connect(self.update_schedule_ui)
        self.schedule_layout.addRow("Тип розкладу:", self.schedule_type_combo)

        self.schedule_time_range_widget = QWidget()
        time_range_layout = QHBoxLayout(self.schedule_time_range_widget)
        time_range_layout.setContentsMargins(0, 0, 0, 0)
        self.schedule_time_start_edit = QTimeEdit()
        self.schedule_time_start_edit.setDisplayFormat("HH:mm")
        self.schedule_time_end_edit = QTimeEdit()
        self.schedule_time_end_edit.setDisplayFormat("HH:mm")
        time_range_layout.addWidget(self.schedule_time_start_edit)
        time_range_layout.addWidget(QLabel("до"))
        time_range_layout.addWidget(self.schedule_time_end_edit)
        self.schedule_layout.addRow("Діапазон часу виконання:", self.schedule_time_range_widget)

        # --- Weekly ---
        self.schedule_day_of_week_combo = QComboBox()
        self.schedule_day_of_week_combo.addItems(["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"])
        self.schedule_day_of_week_row = QWidget()
        self.schedule_day_of_week_row_layout = QHBoxLayout(self.schedule_day_of_week_row)
        self.schedule_day_of_week_row_layout.setContentsMargins(0, 0, 0, 0)
        self.schedule_day_of_week_row_layout.addWidget(self.schedule_day_of_week_combo)
        self.schedule_layout.addRow("День тижня:", self.schedule_day_of_week_row)


        # --- Monthly ---
        self.schedule_day_of_month_spin = QSpinBox()
        self.schedule_day_of_month_spin.setRange(1, 31)
        self.schedule_day_of_month_row = QWidget()
        self.schedule_day_of_month_row_layout = QHBoxLayout(self.schedule_day_of_month_row)
        self.schedule_day_of_month_row_layout.setContentsMargins(0, 0, 0, 0)
        self.schedule_day_of_month_row_layout.addWidget(self.schedule_day_of_month_spin)
        self.schedule_layout.addRow("День місяця:", self.schedule_day_of_month_row)

        # --- Quarterly ---
        self.schedule_quarter_month_combo = QComboBox()
        self.schedule_quarter_month_combo.addItems(["Перший", "Другий", "Третій"])
        self.schedule_quarter_day_spin = QSpinBox()
        self.schedule_quarter_day_spin.setRange(1, 31)
        self.schedule_quarter_row = QWidget()
        self.schedule_quarter_row_layout = QHBoxLayout(self.schedule_quarter_row)
        self.schedule_quarter_row_layout.setContentsMargins(0, 0, 0, 0)
        self.schedule_quarter_row_layout.addWidget(QLabel("Місяць кварталу:"))
        self.schedule_quarter_row_layout.addWidget(self.schedule_quarter_month_combo)
        self.schedule_quarter_row_layout.addWidget(QLabel("День місяця:"))
        self.schedule_quarter_row_layout.addWidget(self.schedule_quarter_day_spin)
        self.schedule_layout.addRow(self.schedule_quarter_row)


        self.tabs.addTab(tab_schedule, "Розклад")

    def create_virtual_environment_tab(self):
        """Create virtual environment management tab"""
        tab_venv = QWidget()
        layout = QVBoxLayout(tab_venv)

        # Virtual environment info
        info_group = QGroupBox("Інформація про Віртуальне Середовище")
        info_layout = QVBoxLayout(info_group)

        self.venv_status_label = QLabel("Перевірка статусу...")
        info_layout.addWidget(self.venv_status_label)

        self.venv_path_label = QLabel("")
        self.venv_path_label.setWordWrap(True)
        info_layout.addWidget(self.venv_path_label)

        layout.addWidget(info_group)

        # Installed packages
        packages_group = QGroupBox("Встановлені Пакети")
        packages_layout = QVBoxLayout(packages_group)

        self.packages_list = QListWidget()
        self.packages_list.setMaximumHeight(200)
        packages_layout.addWidget(self.packages_list)

        packages_buttons_layout = QHBoxLayout()
        self.refresh_packages_btn = QPushButton("Оновити")
        self.refresh_packages_btn.clicked.connect(self.refresh_package_list)
        packages_buttons_layout.addWidget(self.refresh_packages_btn)

        self.cleanup_venv_btn = QPushButton("Очистити Віртуальне Середовище")
        self.cleanup_venv_btn.clicked.connect(self.cleanup_virtual_environment)
        packages_buttons_layout.addWidget(self.cleanup_venv_btn)

        packages_layout.addLayout(packages_buttons_layout)
        layout.addWidget(packages_group)

        # Package usage info
        usage_group = QGroupBox("Використання Пакетів Модулями")
        usage_layout = QVBoxLayout(usage_group)

        self.package_usage_text = QTextEdit()
        self.package_usage_text.setReadOnly(True)
        self.package_usage_text.setMaximumHeight(150)
        usage_layout.addWidget(self.package_usage_text)

        layout.addWidget(usage_group)

        layout.addStretch()

        self.tabs.addTab(tab_venv, "Віртуальне Середовище")

        # Initialize the tab
        self.refresh_package_list()

    def refresh_package_list(self):
        """Refresh the package list and virtual environment information"""
        if not self.parent_window or not hasattr(self.parent_window, 'module_manager'):
            self.venv_status_label.setText("❌ Менеджер модулів недоступний")
            return

        venv_manager = self.parent_window.module_manager.get_virtual_env_manager()

        # Update status
        if os.path.exists(venv_manager.venv_dir):
            self.venv_status_label.setText("✅ Віртуальне середовище створено")
            self.venv_path_label.setText(f"Шлях: {venv_manager.venv_dir}")
        else:
            self.venv_status_label.setText("⚠️ Віртуальне середовище не створено")
            self.venv_path_label.setText(f"Шлях: {venv_manager.venv_dir}")

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

        if package_modules:
            usage_text = "Пакети та модулі, що їх використовують:\n\n"
            for package, modules in package_modules.items():
                usage_text += f"• {package}: {', '.join(modules)}\n"
        else:
            usage_text = "Немає активних пакетів або модулів"

        self.package_usage_text.setText(usage_text)

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

    def update_schedule_ui(self, index):
        schedule_type = self.schedule_type_combo.itemText(index)

        # Visibility flags based on selection
        is_daily = (schedule_type == "Щодня")
        is_weekly = (schedule_type == "Щотижня")
        is_monthly = (schedule_type == "Щомісяця")
        is_quarterly = (schedule_type == "Щокварталу")
        is_disabled = (schedule_type == "Вимкнено")

        # Time range is visible for all except 'disabled'
        self.schedule_time_range_widget.setVisible(not is_disabled)
        # Also toggle the label for the time range
        time_range_label = self.schedule_layout.labelForField(self.schedule_time_range_widget)
        if time_range_label:
            time_range_label.setVisible(not is_disabled)

        # Toggle weekly settings
        self.schedule_day_of_week_row.setVisible(is_weekly)
        day_of_week_label = self.schedule_layout.labelForField(self.schedule_day_of_week_row)
        if day_of_week_label:
            day_of_week_label.setVisible(is_weekly)

        # Toggle monthly settings
        self.schedule_day_of_month_row.setVisible(is_monthly)
        day_of_month_label = self.schedule_layout.labelForField(self.schedule_day_of_month_row)
        if day_of_month_label:
            day_of_month_label.setVisible(is_monthly)

        # Toggle quarterly settings
        self.schedule_quarter_row.setVisible(is_quarterly)
        quarterly_label = self.schedule_layout.labelForField(self.schedule_quarter_row)
        if quarterly_label:
            quarterly_label.setVisible(is_quarterly)

    def add_extension(self):
        ext = self.edit_add_ext.text().strip().lower()
        if ext.startswith('.') and len(ext) > 1:
            if not self.list_extensions.findItems(ext, Qt.MatchExactly):
                self.list_extensions.addItem(ext)
                self.edit_add_ext.clear()
        else:
            QMessageBox.warning(self, "Неправильне розширення", "Розширення повинно починатися з '.' і бути не порожнім.")

    def remove_extension(self):
        for item in self.list_extensions.selectedItems():
            self.list_extensions.takeItem(self.list_extensions.row(item))

    def add_filename(self):
        name = self.edit_add_name.text().strip()
        if name and not any(c in name for c in '/\\:*?"<>|'):
             if not self.list_filenames.findItems(name, Qt.MatchExactly):
                self.list_filenames.addItem(name)
                self.edit_add_name.clear()
        else:
             QMessageBox.warning(self, "Неправильне ім'я файлу", "Ім'я файлу не може бути порожнім або містити недопустимі символи.")

    def remove_filename(self):
        for item in self.list_filenames.selectedItems():
            self.list_filenames.takeItem(self.list_filenames.row(item))

    def load_settings_to_ui(self):
        app_cfg = self.current_settings.get('application', DEFAULT_SETTINGS['application'])
        self.chk_enable_autostart.setChecked(app_cfg.get('autostart_timer_enabled', True))

        timer_cfg = self.current_settings.get('timer', DEFAULT_SETTINGS['timer'])
        self.chk_override_timer.setChecked(timer_cfg.get('override_default_enabled', False))
        self.spin_default_timer.setValue(timer_cfg.get('default_minutes', 3))
        self.spin_default_timer.setEnabled(self.chk_override_timer.isChecked())

        drive_cfg = self.current_settings.get('drives', DEFAULT_SETTINGS['drives'])
        policy = drive_cfg.get('main_drive_policy', 'D')
        if policy == 'auto':
            self.rb_drive_auto.setChecked(True)
        else:
            self.rb_drive_d.setChecked(True)

        fm_cfg = self.current_settings.get('file_manager', DEFAULT_SETTINGS['file_manager'])
        self.spin_max_size.setValue(fm_cfg.get('max_file_size_mb', 100))

        self.list_extensions.clear()
        self.list_extensions.addItems(fm_cfg.get('allowed_extensions', []))

        self.list_filenames.clear()
        self.list_filenames.addItems(fm_cfg.get('allowed_filenames', []))

        schedule_cfg = self.current_settings.get('schedule', DEFAULT_SETTINGS['schedule'])
        schedule_type_en = schedule_cfg.get('type', 'disabled')
        
        schedule_type_ua = SCHEDULE_TYPE_MAP.get(schedule_type_en, "Вимкнено")
        
        index = self.schedule_type_combo.findText(schedule_type_ua)
        if index != -1:
            self.schedule_type_combo.setCurrentIndex(index)

        time_start_str = schedule_cfg.get('time_start', '22:00')
        self.schedule_time_start_edit.setTime(QTime.fromString(time_start_str, "HH:mm"))
        time_end_str = schedule_cfg.get('time_end', '23:00')
        self.schedule_time_end_edit.setTime(QTime.fromString(time_end_str, "HH:mm"))
        
        self.schedule_day_of_week_combo.setCurrentIndex(schedule_cfg.get('day_of_week', 1) - 1)
        self.schedule_day_of_month_spin.setValue(schedule_cfg.get('day_of_month', 1))
        self.schedule_quarter_month_combo.setCurrentIndex(schedule_cfg.get('quarter_month', 1) - 1)
        self.schedule_quarter_day_spin.setValue(schedule_cfg.get('quarter_day', 1))

        self.update_schedule_ui(self.schedule_type_combo.currentIndex())

    def get_settings_from_ui(self):
        updated_settings = {
            'application': {
                'autostart_timer_enabled': self.chk_enable_autostart.isChecked()
            },
            'timer': {
                'override_default_enabled': self.chk_override_timer.isChecked(),
                'default_minutes': self.spin_default_timer.value()
            },
            'drives': {
                'main_drive_policy': 'auto' if self.rb_drive_auto.isChecked() else 'D'
            },
            'file_manager': {
                'max_file_size_mb': self.spin_max_size.value(),
                'allowed_extensions': sorted([self.list_extensions.item(i).text() for i in range(self.list_extensions.count())]),
                'allowed_filenames': sorted([self.list_filenames.item(i).text() for i in range(self.list_filenames.count())])
            },
            'schedule': {
                'type': REVERSE_SCHEDULE_TYPE_MAP.get(self.schedule_type_combo.currentText(), "disabled"),
                'time_start': self.schedule_time_start_edit.time().toString("HH:mm"),
                'time_end': self.schedule_time_end_edit.time().toString("HH:mm"),
                'day_of_week': self.schedule_day_of_week_combo.currentIndex() + 1,
                'day_of_month': self.schedule_day_of_month_spin.value(),
                'quarter_month': self.schedule_quarter_month_combo.currentIndex() + 1,
                'quarter_day': self.schedule_quarter_day_spin.value()
            }
        }
        return updated_settings

    def apply_changes(self):
        new_settings = self.get_settings_from_ui()
        self.current_settings = new_settings
        self.settings_applied.emit(new_settings)
        self.changes_applied = True

    def accept(self):
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
            skip_extensions = {ext.lower() for ext in fm_settings.get('allowed_extensions', [])}
            skip_filenames = {name for name in fm_settings.get('allowed_filenames', [])}
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

                if item_ext_lower in skip_extensions:
                    self.update_signal.emit(f"⏭️ Пропущено за розширенням: {item}")
                    continue

                if item_name_no_ext in skip_filenames:
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
        add_splash_message(f"🔍 Found: {module_name} v{module_info.get('version', 'Unknown')}")
        self.log_message(f"🔍 Discovered module: {module_name} v{module_info.get('version', 'Unknown')}")

    def on_module_loaded(self, module_name: str, module_class):
        """Called when a module is successfully loaded"""
        add_splash_message(f"✅ Loaded: {module_name}")
        self.log_message(f"✅ Module loaded: {module_name}")
        self.update_modules_menu()

    def on_module_error(self, module_name: str, error_message: str):
        """Called when a module encounters an error"""
        add_splash_message(f"❌ Error loading {module_name}")
        self.log_message(f"❌ Module error ({module_name}): {error_message}")

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

        self.apply_settings_to_ui()

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
        self.time_combo.addItems(["1 хвилина", "3 хвилини", "5 хвилин", "10 хвилин"])
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
                QMessageBox.critical(self, "Module Error", f"Failed to open module '{module_name}'.\n\n{e}")
        else:
            self.log_message(f"⚠️ Attempted to open module '{module_name}', but it's not loaded.")
            QMessageBox.warning(self, "Module Unavailable",
                                f"Required module '{module_name}' not found or failed to load.")

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
        # If we are past the window and haven't run, run now.
        elif current_time > end_time:
            self.log_message("⚠️ Вікно розкладу пропущено. Запускаємо таймер зараз, оскільки він не був запущений через високе завантаження ЦП.")
            self.start_auto_timer()
            self.last_scheduled_run_date = today


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
        # Clean up splash screen if it's still active
        global global_splash
        if global_splash and hasattr(global_splash, 'cleanup'):
            global_splash.cleanup()

        # Save settings before closing
        self.save_settings()

        # Optional: Add confirmation before closing if needed
        event.accept()


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