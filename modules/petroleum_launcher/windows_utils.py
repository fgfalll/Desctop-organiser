"""Windows utility functions for petroleum launcher"""

import os
import re
import glob
import subprocess
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger('PetroleumLauncher')

# Try to import pywin32
try:
    import winreg
    WINDOWS_SUPPORT = True
except ImportError:
    WINDOWS_SUPPORT = False
    print("Warning: pywin32 not available. Some features may be limited.")


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