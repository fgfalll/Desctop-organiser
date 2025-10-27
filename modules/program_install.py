#Additional module for main app V4.2
#Import according to instruction
#Can work standalone

import os
import re
import json
import platform
import logging
import shutil
import subprocess
import winreg
import sys
import fnmatch
import math
from pathlib import Path
from typing import List, Dict, Optional, Set, Callable, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

# --- Dependency Check ---
try:
    import win32api
    import win32com.client
    import pythoncom # Import pythoncom here
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False
    # Define dummy objects if pywin32 is not available
    class DummyWin32Api:
        def GetFileVersionInfo(self, *args): return None
        def HIWORD(self, *args): return 0
        def LOWORD(self, *args): return 0
    win32api = DummyWin32Api()

    class DummyWin32ComClient:
        def Dispatch(self, *args): return None
    win32com.client = DummyWin32ComClient()

    class DummyPythonCom:
        class com_error(Exception): pass
    pythoncom = DummyPythonCom()

try:
    from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                 QPushButton, QTreeWidget, QTreeWidgetItem, QHeaderView,
                                 QLabel, QLineEdit, QComboBox, QProgressBar, QFileDialog,
                                 QMessageBox, QSplitter, QToolBar, QStatusBar,
                                 QStyleFactory, QStyle)
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QSettings, QByteArray, QTimer
    from PyQt5.QtGui import QIcon, QColor, QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QMainWindow: pass
    class QThread: pyqtSignal = lambda *args, **kwargs: (lambda func: func)
    class QWidget: pass
    class QApplication:
        @staticmethod
        def setOrganizationName(name: str): pass
        @staticmethod
        def setApplicationName(name: str): pass
        @staticmethod
        def instance(): return None
        @staticmethod
        def processEvents(): pass
    class QStyle:
        StandardPixmap = int
        SP_DialogApplyButton, SP_DialogCancelButton, SP_BrowserReload, SP_DirOpenIcon, SP_DriveNetIcon, SP_TrashIcon = 0, 0, 0, 0, 0, 0

# --- Platform & Dependency Validation ---
IS_WINDOWS = platform.system() == "Windows"
if not IS_WINDOWS: print("CRITICAL: Requires Windows.", file=sys.stderr); sys.exit(1)
if not PYWIN32_AVAILABLE: print("CRITICAL: Requires 'pywin32' (pip install pywin32). Includes win32api, win32com.client, and pythoncom.", file=sys.stderr); sys.exit(1)
if not PYQT5_AVAILABLE: print("CRITICAL: Requires 'PyQt5' (pip install PyQt5).", file=sys.stderr); sys.exit(1)

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)-8s - %(message)s') # Set level=logging.DEBUG for detailed scan logs
logger = logging.getLogger('ProgramInstaller')

# --- Configuration ---
PROGRAM_CONFIG: Dict[str, Dict[str, Any]] = {
    # --- Schlumberger Software ---
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
        "install_commands": {
            ".exe": '{installer_path} /s /v"/qn /norestart"',
            ".msi": 'msiexec /i "{installer_path}" /qn /norestart',
        },
    },
    "pipesim": {
        "display_name": "PIPESIM",
        "target_version": "latest",
        "identity": {
            "expected_product_names": ["Pipesim", "Schlumberger PIPESIM"],
            "expected_descriptions": ["Pipesim Setup", "PIPESIM *", "PIPESIM Suite"],
            "installer_patterns": ["setup.exe", "PIPESIM*.exe", "SLB.PIPESIM*.exe"], # 'setup.exe' is common but generic, use properties to differentiate
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
        "install_commands": {
            ".exe": '{installer_path} /S /NORESTART',
            ".msi": 'msiexec /i "{installer_path}" /qn /norestart',
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
        "install_commands": {
             ".exe": '{installer_path} /S /NORESTART',
            ".msi": 'msiexec /i "{installer_path}" /qn /norestart',
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
        "install_commands": {
            ".exe": '{installer_path} /s /v"/qn /norestart"',
            ".msi": 'msiexec /i "{installer_path}" /qn /norestart',
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
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"Eclipse Simulation.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"Eclipse Simulation.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\Schlumberger\Eclipse", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\Schlumberger\Eclipse", "check_existence": True},
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Eclipse.exe", "check_existence": True},
            ],
        },
        "install_commands": {
            ".exe": '{installer_path} /S /NORESTART',
            ".msi": 'msiexec /i "{installer_path}" /qn /norestart',
        },
    },

    # --- Kappa Software ---
    "kappa_workstation": {
        "display_name": "Kappa Workstation",
        "target_version": "latest",
        "identity": {
            "expected_product_names": ["Kappa Workstation", "Workstation", "KAPPA-Workstation"],
            "expected_descriptions": ["Kappa Workstation Installer", "Setup", "KAPPA-Workstation Setup"],
            "installer_patterns": ["KappaWorkstation*.exe", "Setup*.exe", "KAPPA*.exe"], # May need refinement if 'Setup.exe' is too generic
        },
        "check_method": {
            "type": "registry",
            "keys": [
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"Kappa Workstation.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"Kappa Workstation.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\Kappa Engineering", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\Kappa Engineering", "check_existence": True},
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\KappaWorkstation.exe", "check_existence": True},
            ],
        },
        "install_commands": {
            ".exe": '{installer_path} /S',
            ".msi": 'msiexec /i "{installer_path}" /qn /norestart',
        },
    },
    # --- CMG Software ---
    "cmg": {
        "display_name": "CMG Suite",
        "target_version": "latest",
        "identity": {
            "expected_product_names": ["CMG", "Computer Modelling Group", "CMG Launcher", "CMG Suite"],
            "expected_descriptions": ["CMG Installation", "CMG Suite Setup", "CMG Launcher Installer", "CMG 20"], # Add version specifics if needed
            "installer_patterns": ["CMG*.exe", "Setup*.exe", "*2024*.exe", "CMGLauncher*.exe"], # Patterns might include year
        },
        "check_method": {
            "type": "registry",
            "keys": [
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"CMG .* Release .*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"CMG .* Release .*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"CMG Suite.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"CMG Suite.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\CMG", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\CMG", "check_existence": True},
                {"path": r"SOFTWARE\Computer Modelling Group", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\Computer Modelling Group", "check_existence": True},
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\CMGLauncher.exe", "check_existence": True},
            ],
        },
        "install_commands": {
            ".exe": '{installer_path} /s /v"/qn /norestart"',
            ".msi": 'msiexec /i "{installer_path}" /qn /norestart',
        },
    },
    # --- S&P global Software ---
    "harmony_enterprise": {
        "display_name": "Harmony Enterprise",
        "target_version": "latest",
        "identity": {
            "expected_product_names": ["Harmony Enterprise", "IHS Harmony", "Harmony Well Performance Software", "S&P Harmony"], # Include variants
            "expected_descriptions": ["Harmony Enterprise Setup", "Harmony Enterprise Installer", "IHS Harmony Installation"],
            "installer_patterns": ["Harmony*.exe", "Harmony*Setup*.exe", "IHS.Harmony*.exe"],
        },
        "check_method": {
            "type": "registry",
            "keys": [
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"Harmony Enterprise.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"Harmony Enterprise.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"IHS Harmony.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"IHS Harmony.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\IHS", "check_existence": True}, # Check parent first
                {"path": r"SOFTWARE\WOW6432Node\IHS", "check_existence": True},
                {"path": r"SOFTWARE\IHS\Harmony", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\IHS\Harmony", "check_existence": True},
                {"path": r"SOFTWARE\S&P Global\Harmony", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\S&P Global\Harmony", "check_existence": True},
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Harmony.exe", "check_existence": True},
            ],
        },
        "install_commands": {
            ".exe": '{installer_path} /S', # Verify this switch
            ".msi": 'msiexec /i "{installer_path}" /qn /norestart',
        },
    },
    # --- Petex Software ---
    "ipm": {
        "display_name": "Petex IPM Suite",
        "target_version": "latest",
        "identity": {
            "expected_product_names": ["IPM", "Petroleum Experts", "IPM Suite", "Petex IPM"],
            "expected_descriptions": ["IPM Setup", "Petroleum Experts Installation", "IPM Suite Installer", "Integrated Production Modelling"],
            "installer_patterns": ["IPM*.exe", "SetupIPM*.exe", "Setup.exe", "Petex.IPM*.exe"], # 'Setup.exe' requires property matching
        },
        "check_method": {
            "type": "registry",
            "keys": [
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"Petroleum Experts IPM.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"Petroleum Experts IPM.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\Petroleum Experts", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\Petroleum Experts", "check_existence": True},
                {"path": r"SOFTWARE\Petroleum Experts\IPM", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\Petroleum Experts\IPM", "check_existence": True},
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\IPM.exe", "check_existence": True},
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\GAP.exe", "check_existence": True}, # Check common modules?
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\PROSPER.exe", "check_existence": True},
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\MBAL.exe", "check_existence": True},
            ],
        },
        "install_commands": {
            ".exe": '{installer_path} /S /NORESTART',
            ".msi": 'msiexec /i "{installer_path}" /qn /norestart',
        },
    },
    # --- Tnavigator Software ---
    "tnavigator": {
        "display_name": "tNavigator",
        "target_version": "latest",
        "identity": {
            "expected_product_names": ["tNavigator", "Rock Flow Dynamics tNavigator"],
            "expected_descriptions": ["tNavigator Setup", "tNavigator Installer", "Rock Flow Dynamics tNavigator"],
            "installer_patterns": ["tNavigator*.exe", "tNav*.exe", "RFD.tNavigator*.exe"],
        },
        "check_method": {
            "type": "registry",
            "keys": [
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"tNavigator.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "match_value": "DisplayName", "match_pattern": r"tNavigator.*", "get_value": "DisplayVersion"},
                {"path": r"SOFTWARE\Rock Flow Dynamics", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\Rock Flow Dynamics", "check_existence": True},
                {"path": r"SOFTWARE\Rock Flow Dynamics\tNavigator", "check_existence": True},
                {"path": r"SOFTWARE\WOW6432Node\Rock Flow Dynamics\tNavigator", "check_existence": True},
                {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\tNavigator.exe", "check_existence": True},
            ],
        },
        "install_commands": {
            ".exe": '{installer_path} /S',
            ".msi": 'msiexec /i "{installer_path}" /qn /norestart',
        },
    },

    # --- Template for program configuration ---
    # "example_software": {
    #    "display_name": "Example Software", "target_version": "1.2.3",
    #    "identity": { "expected_product_names": ["Example Product"], "expected_descriptions": ["Example Installer"], "installer_patterns": ["ExampleSetup_*.exe"], },
    #    "check_method": { "type": "registry", "keys": [ {"path": r"SOFTWARE\ExampleVendor\ExampleApp", "get_value": "Version"} ], },
    #    "install_commands": { ".exe": '{installer_path} /VERYSILENT /SUPPRESSMSGBOXES /NORESTART', },
    # },
}

# --- Detection Tuning ---
DETECTION_SETTINGS: Dict[str, Any] = {
    "exclude_generic_names": ['driver', 'redist', 'runtime', 'package', 'library', 'component'],

    # Exclude files if their properties contain these substrings.
    "exclude_by_property_substrings": [
        '.net framework', 'visual c++', 'visual studio tools', 'vsto',
        'codemeter runtime', 'sentinel runtime',
        'microsoft edge', 'webview2', 'msedge',
        'sql server', 'sql native client', 'odbc driver', 'oledb driver',
        'java update', 'jre', 'jdk',
        'directx', 'nvidia driver', 'amd driver', 'intel driver',
        'adobe reader', 'acrobat reader',
        'silverlight', 'flash player',
        'remote desktop', 'anydesk', 'teamviewer',
        'vcredist',
        'report viewer',
        'crystal reports',

        # --- Vendor-Specific Exclusion ---
        'schlumberger licensing', 'slb licensing', 'codemeter control center',
        'software manager', 'download manager',
        'productmenu', 'studio manager', 'petrel workflow tools',
        ],

    # Exclude files whose properties or filename suggest they are uninstallers or patches
    "exclude_uninstaller_hints": ['uninstall', 'remove', 'uninst', 'cleanup', 'fix', 'patch', 'update'],

    # Minimum file size in bytes to consider. Helps filter out small utilities or stubs.
    #"min_file_size_bytes": 5 * 1024 * 1024,

    # Directory names (lowercase) to completely ignore during scanning.
    "ignore_dirs": {
        # System Folders
        '$recycle.bin', 'system volume information', 'windows', 'programdata',
        'temp', 'tmp', 'logs', 'cache',
        # Common Software Folders
        'drivers', 'fonts', 'inf', 'driverstore', 'winsxs',
        'python', 'python27', 'python3', 'python37', 'python38', 'python39', 'python310', 'python311', 'python312',
        'java', 'jre', 'jdk', 'dotnet', '.net', 'node_modules', 'ruby', 'perl',
        '.git', '.svn', '__pycache__', '.vscode', '.idea',
        # Common Application Folders
        'common files', 'internet explorer', 'windows defender',
        'microsoft', 'google', 'mozilla firefox', 'google chrome', 
        'help', 'documentation', 'docs', 'examples', 'samples', 'bin', 'lib', 'include',
        'licenses', 'thirdparty', '3rdparty', 'redistributables', 'VSCodium', 'techlog'
        # Schlumberger Specific Subfolder Examples
        'extensions', 'plugins', 'addins', 'configuration', 'settings', 'data',
        'petrelhelp', 'studiomanager', 'gurucontentmanager', 'plug-ins', 'simulatorplugins', 'studio', 'pythontoolkit', 'techlog', 'petrel', 'pipesim'
        # Other potential exclusions
        'updates', 'patches', 'hotfixes', 'licensing'
    }
}

# --- Data Structures ---
@dataclass(order=True)
class Version:
    """A comparable class for software versions, handling up to 4 parts."""
    # Sort index is used to make instances sortable
    sort_index: Tuple[int, int, int, int] = field(init=False, repr=False)
    major: int = 0
    minor: int = 0
    patch: int = 0
    build: int = 0

    def __post_init__(self):
        self.major = int(self.major) if self.major is not None else 0
        self.minor = int(self.minor) if self.minor is not None else 0
        self.patch = int(self.patch) if self.patch is not None else 0
        self.build = int(self.build) if self.build is not None else 0
        self.sort_index = (self.major, self.minor, self.patch, self.build)

    @staticmethod
    def from_string(version_str: Optional[str]) -> 'Version':
        """Parses a version string (e.g., '2023.1.2', '5.1', '1.2.3.456') into a Version object."""
        if not version_str or not isinstance(version_str, str):
            return Version(0, 0, 0, 0)

        # Find all sequences of digits
        parts = re.findall(r'\d+', version_str)
        
        # Convert parts to integers
        version_parts = [int(p) for p in parts]

        # Pad with zeros to ensure at least 4 parts for consistent comparison
        version_parts.extend([0] * (4 - len(version_parts)))

        # Take the first 4 parts
        v = version_parts[:4]
        
        return Version(major=v[0], minor=v[1], patch=v[2], build=v[3])

    def __str__(self) -> str:
        """Returns a string representation of the version, trimming trailing zeros."""
        if self.is_zero():
            return "N/A"
        
        parts = [self.major, self.minor, self.patch, self.build]
        # Find the last non-zero part to create a compact representation
        last_significant_index = -1
        for i in range(len(parts) - 1, -1, -1):
            if parts[i] != 0:
                last_significant_index = i
                break
        
        if last_significant_index == -1:
             return "0"

        # Join the significant parts
        return ".".join(map(str, parts[:last_significant_index + 1]))

    def is_zero(self) -> bool:
        """Check if the version is effectively zero or invalid."""
        return self.major == 0 and self.minor == 0 and self.patch == 0 and self.build == 0

@dataclass
class FoundInstallerInfo:
    path: Path
    file_properties: Dict[str, Any] = field(default_factory=dict)
    installer_type: str = ".unknown"
    version: Optional[Version] = None

@dataclass
class ProgramStatus:
    program_key: str
    display_name: str
    config: Dict[str, Any]
    found_installer: Optional[FoundInstallerInfo] = None
    is_installed: Optional[bool] = None
    last_checked: Optional[datetime] = None
    installed_version_str: Optional[str] = None
    installed_version: Optional[Version] = None
    install_error: Optional[str] = None

# --- Windows Utilities ---
class WindowsUtils:
    @staticmethod
    def get_file_properties(file_path_str: str) -> Optional[Dict[str, Any]]:
        file_path = Path(file_path_str)
        if not file_path.is_file():
            logger.debug(f"Get props skipped: Not a file '{file_path_str}'")
            return None
        properties = {}
        try:
            fixed_info = win32api.GetFileVersionInfo(str(file_path), '\\')
            if fixed_info:
                ms = fixed_info['FileVersionMS']; ls = fixed_info['FileVersionLS']
                properties['FileVersion'] = f"{win32api.HIWORD(ms)}.{win32api.LOWORD(ms)}.{win32api.HIWORD(ls)}.{win32api.LOWORD(ls)}"
                ms = fixed_info['ProductVersionMS']; ls = fixed_info['ProductVersionLS']
                properties['ProductVersion'] = f"{win32api.HIWORD(ms)}.{win32api.LOWORD(ms)}.{win32api.HIWORD(ls)}.{win32api.LOWORD(ls)}"
            else:
                 logger.debug(f"No FixedFileInfo found for {file_path.name}")
            lang_codepages = win32api.GetFileVersionInfo(str(file_path), r'\VarFileInfo\Translation')
            if lang_codepages:
                lang_cp = f'{lang_codepages[0][0]:04x}{lang_codepages[0][1]:04x}'
                string_info_path = f'\\StringFileInfo\\{lang_cp}\\'
                string_keys = ['CompanyName', 'FileDescription', 'InternalName', 'LegalCopyright', 'OriginalFilename', 'ProductName']
                for key in string_keys:
                    try:
                        value = win32api.GetFileVersionInfo(str(file_path), string_info_path + key)
                        properties[key] = value.strip() if value else ""
                    except Exception:
                        properties[key] = ""
                logger.debug(f"Read StringFileInfo for {file_path.name} (Lang/CP: {lang_cp})")
            else:
                logger.debug(f"No language/codepage info found for {file_path.name}")
                string_keys = ['CompanyName', 'FileDescription', 'InternalName', 'LegalCopyright', 'OriginalFilename', 'ProductName']
                for key in string_keys:
                    try:
                         properties[key] = win32api.GetFileVersionInfo(str(file_path), f'\\StringFileInfo\\040904b0\\{key}').strip() or "" # Try common English US
                    except Exception: properties[key] = ""
            for key in ['FileVersion', 'ProductVersion', 'CompanyName', 'FileDescription', 'OriginalFilename', 'ProductName']:
                properties.setdefault(key, "")

            return properties
        except Exception as e:
            # Log specific error type and message if possible
            logger.debug(f"Failed getting properties for {file_path.name}: {type(e).__name__} - {e}")
            return None

    @staticmethod
    def run_command(cmd: str, program_name: str, timeout: int = 900) -> Tuple[bool, int, str, str]:
        logger.info(f"Executing command for '{program_name}': {cmd}")
        try:
            result = subprocess.run(cmd, shell=True, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding='utf-8', errors='ignore', timeout=timeout,
                                    creationflags=subprocess.CREATE_NO_WINDOW)

            stdout = result.stdout.strip() if result.stdout else ""
            stderr = result.stderr.strip() if result.stderr else ""

            if stdout: logger.debug(f"Cmd stdout for '{program_name}': {stdout}")
            if stderr: logger.warning(f"Cmd stderr for '{program_name}': {stderr}")

            # Common success codes for installers (0=OK, 3010=Reboot Required, 1641=Reboot Initiated)
            success_codes = {0, 3010, 1641}
            ran_ok = result.returncode in success_codes

            logger.info(f"Command for '{program_name}' finished. Success: {ran_ok}, Return Code: {result.returncode}")
            return ran_ok, result.returncode, stdout, stderr

        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out after {timeout}s for '{program_name}': {cmd}")
            return False, -1, "", "TimeoutExpired"
        except FileNotFoundError:
            logger.error(f"Command failed: Executable not found for '{program_name}': {cmd}")
            return False, -2, "", "FileNotFoundError"
        except Exception as e:
            logger.error(f"Command execution exception for '{program_name}': {e}", exc_info=True)
            return False, -3, "", str(e)

    @staticmethod
    def check_path_exists(path_str: str) -> bool:
        """Checks if a file or directory exists, expanding environment variables."""
        try:
            expanded_path = os.path.expandvars(path_str)
            return Path(expanded_path).exists()
        except Exception as e:
            logger.warning(f"Error checking path existence for '{path_str}': {e}")
            return False

    @staticmethod
    def _reg_read_string(hkey: int, key_path: str, value_name: Optional[str]) -> Optional[str]:
        """Reads a string value from the registry. Returns None if not found or error."""
        if value_name is None: return None
        try:
            with winreg.OpenKey(hkey, key_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                value, reg_type = winreg.QueryValueEx(key, value_name)
                if reg_type in [winreg.REG_SZ, winreg.REG_EXPAND_SZ]:
                    return str(value).strip()
                else:
                    logger.debug(f"Reg value '{value_name}' at '{key_path}' is not a string type (Type: {reg_type}).")
                    return None
        except FileNotFoundError:
            logger.debug(f"Reg value '{value_name}' not found at '{key_path}'.")
            return None
        except OSError as e:
            logger.warning(f"OS Error reading reg value '{value_name}' at '{key_path}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading reg value '{value_name}' at '{key_path}': {e}", exc_info=True)
            return None

    @staticmethod
    def check_registry(check_config: List[Dict]) -> Tuple[bool, Optional[str]]:
        """Checks registry based on a list of rules. Returns (found, version_string)."""
        hkey_map = {'HKLM': winreg.HKEY_LOCAL_MACHINE, 'HKCU': winreg.HKEY_CURRENT_USER}
        found_globally = False
        first_found_version: Optional[str] = None

        for rule in check_config:
            key_path: Optional[str] = rule.get("path")
            base_hive_str: str = rule.get("hive", "HKLM") # Default to HKLM
            base_hive: int = hkey_map.get(base_hive_str, winreg.HKEY_LOCAL_MACHINE)

            match_value: Optional[str] = rule.get("match_value")
            match_pattern: Optional[str] = rule.get("match_pattern")
            check_existence: bool = rule.get("check_existence", False)
            get_value: Optional[str] = rule.get("get_value") # Value to retrieve if found

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

                elif get_value:
                     found_version = WindowsUtils._reg_read_string(base_hive, key_path, get_value)
                     if found_version is not None:
                          logger.debug(f"Reg Check SUCCESS (GetValue): Found value '{get_value}' in '{key_path}'. Version: '{found_version}'")
                          found_globally = True
                          if first_found_version is None:
                              first_found_version = found_version
                     else:
                          logger.debug(f"Reg Check FAIL (GetValue): Value '{get_value}' not found or not string in '{key_path}'.")
                          continue
            except OSError as e:
                 logger.warning(f"OS Error checking registry rule {rule}: {e}")
                 continue
            except Exception as e:
                logger.error(f"Unexpected error checking registry rule {rule}: {e}", exc_info=True)
                continue
            if found_globally:
                logger.info(f"Registry check successful for rule set. Final Result: Found={found_globally}, Version='{first_found_version}'")
                return found_globally, first_found_version

        logger.info(f"Registry check finished. No rules matched successfully. Final Result: Found={found_globally}, Version='{first_found_version}'")
        return found_globally, first_found_version

    # --- MSI Specific Methods ---
    @staticmethod
    def _get_msi_db(msi_path: str) -> Optional[Any]:
        """Helper to open MSI database safely."""
        try:
            import msilib
            db = msilib.OpenDatabase(msi_path, msilib.MSIDBOPEN_READONLY)
            return db
        except ImportError:
            logger.error("Python 'msilib' module not found or import failed. Cannot read MSI properties.")
            return None
        except msilib.MSIError as e:
            logger.warning(f"MSI Error opening database {msi_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to open MSI database {msi_path}: {e}", exc_info=True)
            return None

    @staticmethod
    def get_msi_properties(msi_path: str) -> Dict[str, str]:
        """Extracts properties from the Property table of an MSI file."""
        properties = {}
        db = WindowsUtils._get_msi_db(msi_path)
        if not db: return {}

        try:
            view = db.OpenView("SELECT Property, Value FROM Property")
            view.Execute(None)
            while True:
                record = view.Fetch()
                if not record: break
                try:
                    prop_name = record.GetString(1)
                    prop_value = record.GetString(2)
                    if prop_name and prop_value is not None:
                         properties[prop_name] = prop_value.strip()
                except Exception as fetch_e:
                    logger.debug(f"Error fetching MSI property record in {msi_path}: {fetch_e}")
                    continue
            view.Close()
            logger.debug(f"Successfully read {len(properties)} properties from MSI: {msi_path}")
            try:
                import msilib
                si = db.GetSummaryInformation(0) # 0 = max properties
                summary_props = {
                     'Title': 2, 'Subject': 3, 'Author': 4, 'Keywords': 5,
                     'Comments': 6, 'Template': 7, 'LastSavedBy': 8, 'RevisionNumber': 9,
                }
                for name, pid in summary_props.items():
                     try:
                          value = si.GetProperty(pid)
                          if isinstance(value, bytes): value = value.decode('utf-8', errors='ignore')
                          properties[f"Summary_{name}"] = str(value).strip()
                     except: continue
                logger.debug(f"Read summary info from MSI: {msi_path}")
            except Exception as si_e:
                 logger.debug(f"Could not read summary information from MSI {msi_path}: {si_e}")

            return properties
        except Exception as e:
            logger.warning(f"Failed to read properties view from MSI {msi_path}: {e}")
            return {}

    @staticmethod
    def get_msi_product_code(msi_path: str) -> Optional[str]:
        """Gets the ProductCode GUID from an MSI file."""
        db = WindowsUtils._get_msi_db(msi_path)
        if not db: return None
        try:
            view = db.OpenView("SELECT Value FROM Property WHERE Property='ProductCode'")
            view.Execute(None)
            record = view.Fetch()
            view.Close()
            if record:
                product_code = record.GetString(1)
                logger.debug(f"Found ProductCode '{product_code}' in MSI: {msi_path}")
                return product_code
            else:
                logger.debug(f"ProductCode not found in Property table for MSI: {msi_path}")
                return None
        except Exception as e:
            logger.warning(f"Failed to get ProductCode from MSI {msi_path}: {e}")
            return None

    @staticmethod
    def is_msi_product_installed(product_code: str) -> bool:
        """Checks if an MSI product with the given ProductCode is installed using COM."""
        if not product_code: return False
        try:
            installer = win32com.client.Dispatch("WindowsInstaller.Installer")
            related_products = installer.RelatedProducts(product_code)
            if related_products and len(related_products) > 0:
                 logger.debug(f"MSI check: ProductCode '{product_code}' IS installed.")
                 return True
            logger.debug(f"MSI check: ProductCode '{product_code}' is NOT installed.")
            return False
        except pythoncom.com_error as e:
             logger.error(f"COM Error checking MSI ProductCode '{product_code}': {e}")
             return False
        except Exception as e:
            logger.error(f"Unexpected error checking MSI ProductCode '{product_code}': {e}", exc_info=True)
            return False

# --- Core Installer Logic ---
class ProgramInstaller:
    HEURISTIC_SCORE_THRESHOLD = 0.5

    def __init__(self, config: Dict = PROGRAM_CONFIG, settings: Dict = DETECTION_SETTINGS):
        self.config = config
        self.settings = settings
        self.program_status: Dict[str, ProgramStatus] = self._initialize_program_status()
        self.installation_log: Dict[str, Dict] = {}
        self.search_path: Optional[str] = None
        self.unidentified_installers: List[FoundInstallerInfo] = []
        self._log_file: Optional[Path] = self._get_log_path()
        self._load_installation_log()

    def _initialize_program_status(self) -> Dict[str, ProgramStatus]:
        return {key: ProgramStatus(key, cfg.get("display_name", key), cfg) for key, cfg in self.config.items()}

    def set_search_path(self, path: str) -> bool:
        try:
            resolved = Path(path).resolve(strict=True)
            if resolved.is_dir():
                self.search_path = str(resolved)
                logger.info(f"Search path set to: {self.search_path}")
                for status in self.program_status.values():
                    status.found_installer = None
                self.unidentified_installers.clear()
                return True
            else:
                logger.error(f"Invalid search path: '{path}' is not a directory.")
                self.search_path = None
                return False
        except FileNotFoundError:
             logger.error(f"Invalid search path: '{path}' does not exist.")
             self.search_path = None; return False
        except Exception as e:
            logger.error(f"Error setting search path '{path}': {e}", exc_info=True)
            self.search_path = None
            return False

    def get_current_status(self) -> Dict[str, ProgramStatus]:
        return self.program_status

    def _score_potential_installer(self, info: FoundInstallerInfo) -> float:
        # Base score - Start slightly positive
        score = 0.3
        filename_lower = info.path.name.lower()
        props = info.file_properties

        # --- MSI Specific Scoring ---
        if info.installer_type == '.msi':
            score += 0.3 
            product_name = props.get('ProductName', '').lower()
            if any(p in product_name for p in ['patch', 'update', 'hotfix', 'security update']):
                score -= 0.4
            if any(p in product_name for p in ['runtime', 'redist', 'merge module', 'driver']):
                score -= 0.5
            if product_name and not any(g in product_name for g in ['install', 'setup', 'package']):
                 score += 0.1

        # --- EXE Specific Scoring ---
        elif info.installer_type == '.exe':
            inst_kw = ['setup', 'install', 'installer', 'wizard', 'web', 'online'] # Keywords suggesting installer
            uninst_kw = self.settings.get('exclude_uninstaller_hints', []) # Use configured hints
            if any(k in filename_lower for k in inst_kw): score += 0.25
            if any(k in filename_lower for k in uninst_kw): score -= 0.35 # Strong penalty for uninstall hints in name
            try:
                size_mb = info.path.stat().st_size / (1024*1024)
                if size_mb > 100: score += 0.15 # Large files more likely main installers
                elif size_mb > 10: score += 0.10
                elif size_mb < self.settings.get('min_file_size_bytes', 0) / (1024*1024): score -= 0.15 # Penalize if below min size
            except (FileNotFoundError, OSError): score -= 0.1 # Penalize if size check fails
            if props:
                prod_name = props.get('ProductName', '').lower()
                file_desc = props.get('FileDescription', '').lower()
                comp_name = props.get('CompanyName', '').lower()
                if prod_name and not any(g in prod_name for g in ['install', 'setup', 'package', 'wizard']): score += 0.15
                if file_desc and not any(g in file_desc for g in ['install', 'setup', 'package', 'wizard']): score += 0.10
                if any(k in prod_name or k in file_desc for k in uninst_kw): score -= 0.30
                if comp_name in ['microsoft corporation', '']: score -= 0.05

        # Normalize score to be between 0.0 and 1.0
        return max(0.0, min(score, 1.0))

    def _find_potential_installers(self, search_path_str: str) -> List[FoundInstallerInfo]:
        """Scans the search path recursively for potential installer files (.exe, .msi)."""
        potential_files: List[FoundInstallerInfo] = []
        base_path = Path(search_path_str)
        ignore_dirs_lower = {d.lower() for d in self.settings.get('ignore_dirs', set())}
        min_size = self.settings.get('min_file_size_bytes', 0)
        exclude_generics = [n.lower() for n in self.settings.get('exclude_generic_names', [])]
        exclude_by_prop = [s.lower() for s in self.settings.get('exclude_by_property_substrings', [])]
        exclude_uninstall = [n.lower() for n in self.settings.get('exclude_uninstaller_hints', [])]

        logger.info(f"Starting recursive scan in '{base_path}'...")
        logger.info(f"Ignoring directories: {ignore_dirs_lower}")
        logger.info(f"Min file size: {min_size} bytes")
        logger.info(f"Excluding generics: {exclude_generics}")
        logger.info(f"Excluding by property: {exclude_by_prop}")
        logger.info(f"Excluding uninstall hints: {exclude_uninstall}")

        file_count, dir_count, ignored_dir_count = 0, 0, 0
        prop_read_count, prop_read_fail_count = 0, 0
        size_filter_count, prop_generic_filter_count = 0, 0
        prop_exclude_filter_count, prop_uninst_filter_count = 0, 0
        ext_filter_count = 0
        msi_prop_fail_count = 0

        for root, dirs, files in os.walk(base_path, topdown=True):
            dir_count += 1
            current_path = Path(root)
            logger.debug(f"Scanning directory: {current_path}")
            original_dir_count = len(dirs)
            dirs[:] = [d for d in dirs if d.lower() not in ignore_dirs_lower]
            ignored_count_this_level = original_dir_count - len(dirs)
            ignored_dir_count += ignored_count_this_level
            if ignored_count_this_level > 0:
                 logger.debug(f"  Ignored {ignored_count_this_level} subdirectories based on ignore_dirs list.")

            for filename in files:
                file_count += 1
                filename_lower = filename.lower()
                file_path = current_path / filename
                ext_lower = file_path.suffix.lower()

                # --- Filter 1: Extension ---
                if ext_lower not in ['.exe', '.msi']:
                    ext_filter_count += 1
                    continue

                logger.debug(f" -> Checking file [{file_count}]: {file_path}")

                try:
                    # --- Filter 2: File Size ---
                    file_size = file_path.stat().st_size
                    if file_size < min_size:
                        logger.debug(f"    -> SKIP: Size ({file_size} bytes) below threshold ({min_size} bytes).")
                        size_filter_count += 1
                        continue

                    properties = None
                    # --- Get Properties (Different for MSI vs EXE) ---
                    if ext_lower == '.msi':
                        logger.debug(f"    -> Reading MSI properties...")
                        properties = WindowsUtils.get_msi_properties(str(file_path))
                        prop_read_count += 1
                        if not properties:
                             logger.debug(f"    -> SKIP: Failed to read MSI properties.")
                             prop_read_fail_count += 1
                             msi_prop_fail_count += 1
                             continue
                        properties['MSI_ProductCode'] = WindowsUtils.get_msi_product_code(str(file_path))
                        properties['ProductVersion'] = properties.get('ProductVersion', '')
                        properties['MSI_ProductVersion'] = properties.get('ProductVersion')

                    elif ext_lower == '.exe':
                        logger.debug(f"    -> Reading EXE properties...")
                        properties = WindowsUtils.get_file_properties(str(file_path))
                        prop_read_count += 1
                        if not properties:
                            logger.debug(f"    -> SKIP: Failed to read EXE properties.")
                            prop_read_fail_count += 1
                            continue
                    else:
                         continue

                    # Log the properties found
                    log_props = {k: v for k, v in properties.items() if k in ['ProductName', 'FileDescription', 'OriginalFilename', 'FileVersion', 'ProductVersion', 'CompanyName', 'MSI_ProductCode']}
                    logger.debug(f"    -> Properties: {log_props}")

                    # --- Apply Property-Based Filters ---
                    prop_vals_lower = { str(v).lower() for k, v in properties.items() if v and k in ['ProductName', 'FileDescription', 'OriginalFilename', 'CompanyName']}

                    # Filter 3: Exclude by specific property substrings
                    excluded_by_prop = False
                    for prop_filter in exclude_by_prop:
                         if any(prop_filter in val for val in prop_vals_lower):
                              logger.debug(f"    -> SKIP: Property filter matched '{prop_filter}'.")
                              prop_exclude_filter_count += 1
                              excluded_by_prop = True
                              break
                    if excluded_by_prop: continue

                    # Filter 4: Exclude by generic names
                    excluded_by_generic = False
                    for generic_filter in exclude_generics:
                         if any(generic_filter in val for val in prop_vals_lower):
                              logger.debug(f"    -> SKIP: Generic name filter matched '{generic_filter}'.")
                              prop_generic_filter_count += 1
                              excluded_by_generic = True
                              break
                    if excluded_by_generic: continue

                    # Filter 5: Exclude by uninstaller hints
                    excluded_by_uninst = False
                    prop_vals_lower.add(filename_lower)
                    for uninst_filter in exclude_uninstall:
                         if any(uninst_filter in val for val in prop_vals_lower):
                              logger.debug(f"    -> SKIP: Uninstaller hint filter matched '{uninst_filter}'.")
                              prop_uninst_filter_count += 1
                              excluded_by_uninst = True
                              break
                    if excluded_by_uninst: continue

                    # --- Passed all filters ---
                    logger.debug(f"    -> PASSED ALL FILTERS. Adding as potential installer.")
                    # Parse version
                    version_str = properties.get('ProductVersion') or properties.get('FileVersion')
                    parsed_version = Version.from_string(version_str)
                    if parsed_version.is_zero():
                        logger.debug(f"    -> Could not parse a valid version from string: '{version_str}'")

                    potential_files.append(FoundInstallerInfo(
                        path=file_path,
                        file_properties=properties,
                        installer_type=ext_lower,
                        version=parsed_version
                    ))

                except FileNotFoundError:
                     logger.debug(f"    -> SKIP: File not found during processing (likely deleted mid-scan): {file_path}")
                     continue
                except OSError as e:
                     logger.warning(f"    -> SKIP: OS error processing file {file_path}: {e}")
                     continue
                except Exception as e:
                    logger.error(f"    -> SKIP: Unexpected error processing file {file_path}: {e}", exc_info=True)
                    continue

        logger.info(f"--- Scan Summary ---")
        logger.info(f"Directories scanned: {dir_count} (Excluded: {ignored_dir_count})")
        logger.info(f"Files encountered: {file_count}")
        logger.info(f"Files skipped by extension: {ext_filter_count}")
        logger.info(f"Files skipped by size: {size_filter_count}")
        logger.info(f"Property Reads attempted: {prop_read_count} (Failed: {prop_read_fail_count}, MSI specific fails: {msi_prop_fail_count})")
        logger.info(f"Files skipped by property substring filter: {prop_exclude_filter_count}")
        logger.info(f"Files skipped by generic name filter: {prop_generic_filter_count}")
        logger.info(f"Files skipped by uninstaller hint filter: {prop_uninst_filter_count}")
        logger.info(f"Potential installers identified: {len(potential_files)}")
        logger.info(f"--- End Scan Summary ---")

        return potential_files

    def scan_for_installers(self) -> Tuple[List[str], List[FoundInstallerInfo]]:
        """Scans, identifies installers based on config, and finds heuristic potentials."""
        if not self.search_path:
            logger.error("Scan cannot start: Search path is not set.")
            return [], []

        logger.info(f"Starting installer identification process in: {self.search_path}")
        for status in self.program_status.values():
            status.found_installer = None
        self.unidentified_installers.clear()

        # 1. Find all potential files passing basic filters
        potential_files = self._find_potential_installers(self.search_path)
        if not potential_files:
            logger.info("Scan finished: No potential installer files found after initial filtering.")
            return [], []

        logger.info(f"Found {len(potential_files)} potential installers. Matching against program configurations...")

        matched_keys: List[str] = []
        processed_paths: Set[Path] = set()

        # 2. Match against specific program configurations
        for key, prog_config in self.config.items():
            identity = prog_config.get('identity', {})
            exp_names = [n.lower() for n in identity.get('expected_product_names', [])]
            exp_descs = [d.lower() for d in identity.get('expected_descriptions', [])]
            patterns = [p.lower() for p in identity.get('installer_patterns', [])]
            best_match_for_key: Optional[FoundInstallerInfo] = None
            best_score = -1
            logger.debug(f"--- Comparing potentials against Config Key: '{key}' ({prog_config.get('display_name', '')}) ---")
            logger.debug(f"    Criteria: Names={exp_names}, Descs={exp_descs}, Patterns={patterns}")

            for info in potential_files:
                if info.path in processed_paths or not info.file_properties:
                    continue

                props = info.file_properties
                filename_lower = info.path.name.lower()
                prod_name = props.get('ProductName', '').lower()
                desc = props.get('FileDescription', '').lower()
                orig_name = props.get('OriginalFilename', '').lower()

                logger.debug(f"  Comparing File: '{filename_lower}' (Prod='{prod_name}', Desc='{desc}', Orig='{orig_name}')")

                # --- Matching Logic ---
                # Score based on match quality: filename pattern < description < product name
                current_score = 0
                patt_match = any(fnmatch.fnmatch(filename_lower, pat) for pat in patterns) if patterns else False
                desc_match = any(exp in desc for exp in exp_descs) if exp_descs and desc else False
                name_match = any(exp in prod_name for exp in exp_names) if exp_names and prod_name else False
                orig_name_match = any(fnmatch.fnmatch(orig_name, pat) for pat in patterns) if patterns and orig_name else False


                if patt_match or orig_name_match: current_score += 1
                if desc_match: current_score += 2
                if name_match: current_score += 3

                logger.debug(f"    -> Score: {current_score} (Pattern={patt_match or orig_name_match}, Desc={desc_match}, Name={name_match})")

                if current_score > 0:
                    # If scores are equal, prefer the one with a higher version.
                    # If the new score is higher, it's an automatic new best.
                    is_better = False
                    if current_score > best_score:
                        is_better = True
                        logger.debug(f"    -> New best match for '{key}' (Score: {current_score} > {best_score}).")
                    elif current_score == best_score:
                        # Scores are equal, compare versions
                        if best_match_for_key and info.version and not info.version.is_zero():
                            if not best_match_for_key.version or best_match_for_key.version.is_zero() or info.version > best_match_for_key.version:
                                is_better = True
                                logger.debug(f"    -> New best match for '{key}' (Equal score, but newer version: {info.version} > {best_match_for_key.version}).")

                    if is_better:
                        best_score = current_score
                        best_match_for_key = info
                    else:
                         logger.debug(f"    -> Match found for '{key}', but not better than previous best (Score: {current_score}, Version: {info.version}).")

            if best_match_for_key:
                logger.info(f"  MATCH CONFIRMED: Config '{key}' -> Installer '{best_match_for_key.path.name}' (Score: {best_score})")
                self.program_status[key].found_installer = best_match_for_key
                matched_keys.append(key)
                processed_paths.add(best_match_for_key.path) # Mark this file as used
            else:
                logger.debug(f"--- No suitable match found for Config Key: '{key}' ---")

        # 3. Apply heuristics to remaining, unmatched files
        remaining_files = [info for info in potential_files if info.path not in processed_paths]
        logger.info(f"Applying heuristics to {len(remaining_files)} remaining potential installers...")

        for info in remaining_files:
            score = self._score_potential_installer(info)
            logger.debug(f"  Heuristic check: '{info.path.name}' -> Score: {score:.2f}")
            if score >= self.HEURISTIC_SCORE_THRESHOLD:
                logger.info(f"  HEURISTIC MATCH: '{info.path.name}' (Score: {score:.2f} >= {self.HEURISTIC_SCORE_THRESHOLD}). Adding to unidentified list.")
                self.unidentified_installers.append(info)
            else:
                 logger.debug(f"  Heuristic skip: '{info.path.name}' (Score: {score:.2f} < {self.HEURISTIC_SCORE_THRESHOLD}).")


        # Sort unidentified list for consistent display
        self.unidentified_installers.sort(key=lambda i: i.path.name.lower())

        logger.info(f"--- Identification Summary ---")
        logger.info(f"Matched {len(matched_keys)} configurations to specific installers.")
        logger.info(f"Found {len(self.unidentified_installers)} additional potential installers via heuristics.")
        logger.info(f"--- End Identification Summary ---")

        return matched_keys, self.unidentified_installers

    def check_installation_status(self, program_keys: Optional[List[str]] = None) -> Dict[str, bool]:
        """Checks the installation status for specified (or all) configured programs."""
        keys_to_check = program_keys if program_keys is not None else list(self.config.keys())
        results: Dict[str, bool] = {}
        now = datetime.now()
        logger.info(f"Checking installation status for programs: {keys_to_check}")

        for key in keys_to_check:
            if key not in self.program_status:
                logger.warning(f"Skipping status check for unknown program key: '{key}'")
                continue

            status = self.program_status[key]
            check_cfg = status.config.get('check_method', {})
            check_type = check_cfg.get('type')
            is_installed: Optional[bool] = None
            found_version: Optional[str] = None

            logger.debug(f"Checking status for '{status.display_name}' (Key: {key}) using type: {check_type}")

            try:
                if check_type == 'registry':
                    is_installed, found_version = WindowsUtils.check_registry(check_cfg.get('keys', []))
                elif check_type == 'path':
                    paths_to_check = check_cfg.get('paths', [])
                    is_installed = any(WindowsUtils.check_path_exists(p) for p in paths_to_check)
                    found_version = None
                    logger.debug(f"Path check result for '{key}': {is_installed} (Paths: {paths_to_check})")
                elif check_type == 'msi_product_code':
                    product_code = check_cfg.get('product_code')
                    if product_code:
                         is_installed = WindowsUtils.is_msi_product_installed(product_code)
                         found_version = None # TODO: Could try getting version via COM if needed
                         logger.debug(f"MSI Product Code check result for '{key}' (Code: {product_code}): {is_installed}")
                    else:
                         logger.warning(f"MSI Product Code check type specified for '{key}', but no product_code found in config.")
                         is_installed = False
                else:
                    logger.warning(f"Unsupported check_method type '{check_type}' specified for program '{key}'. Assuming not installed.")
                    is_installed = False

                # Update status object
                status.is_installed = bool(is_installed)
                status.last_checked = now
                status.installed_version_str = found_version if is_installed else None
                status.installed_version = Version.from_string(status.installed_version_str) if is_installed else Version(0,0,0,0)
                results[key] = status.is_installed
                logger.info(f"Status check result for '{status.display_name}': Installed={status.is_installed}, Version='{status.installed_version_str or 'N/A'}'")

            except Exception as e:
                 logger.error(f"Error during installation status check for '{key}': {e}", exc_info=True)
                 status.is_installed = None
                 status.last_checked = now
                 status.last_installed_version = None
                 results[key] = False

        return results

    def install_program(self, program_key: str, mode: str = 'auto') -> bool:
        """Installs a configured program using the found installer and selected mode."""
        if program_key not in self.program_status:
            logger.error(f"Installation failed: Unknown program key '{program_key}'")
            return False

        status = self.program_status[program_key]
        logger.info(f"Initiating installation for '{status.display_name}' (Key: {program_key}) in '{mode}' mode.")

        if not status.found_installer:
            logger.error(f"Installation failed for '{status.display_name}': No installer file was found or matched.")
            status.install_error = "Installer not found"
            return False

        if status.is_installed:
            logger.info(f"Skipping installation for '{status.display_name}': Program is already marked as installed.")
            return True

        info = status.found_installer
        commands = status.config.get('install_commands', {})
        cmd_template = commands.get(info.installer_type)

        if not cmd_template:
            logger.error(f"Installation failed for '{status.display_name}': No install command defined in configuration for installer type '{info.installer_type}'.")
            status.install_error = f"Missing command for {info.installer_type}"
            return False

        path_str = str(info.path)
        quoted_path = f'"{path_str}"'

        base_cmd_for_mode = cmd_template.format(installer_path=quoted_path)
        final_cmd = base_cmd_for_mode

        if mode == 'manual':
            final_cmd = quoted_path
            logger.info(f"Using manual mode: Executing installer directly.")
        elif mode == 'semi':
            if info.installer_type == '.msi':
                final_cmd = f'msiexec /i {quoted_path} /passive /norestart'
            elif info.installer_type == '.exe':
                if '/s /v"/qn' in base_cmd_for_mode.lower():
                     final_cmd = base_cmd_for_mode.replace('/qn', '/qb')
                     final_cmd = final_cmd.replace('/s', '')
                elif '/S' in base_cmd_for_mode or '/SILENT' in base_cmd_for_mode or '/VERYSILENT' in base_cmd_for_mode:
                     final_cmd = base_cmd_for_mode
                     logger.warning(f"Semi-silent mode for EXE ({info.path.name}): No standard passive switch known, attempting configured silent command.")
                else:
                     final_cmd = quoted_path
                     logger.warning(f"Semi-silent mode for EXE ({info.path.name}): No known silent switch to modify, executing manually.")
            logger.info(f"Using semi-silent mode: Attempting execution with potentially reduced UI.")

        run_cmd = f'start /wait "" {final_cmd}'

        logger.info(f"Executing installation command: {run_cmd}")
        ran_ok, return_code, _, stderr = WindowsUtils.run_command(run_cmd, status.display_name)

        # --- Post-Installation Check & Status Update ---
        if ran_ok:
            logger.info(f"Installation command for '{status.display_name}' completed successfully (Return Code: {return_code}).")

            # Verify installation status after command success
            logger.info(f"Verifying installation status post-run for '{status.display_name}'...")
            if info.installer_type == '.msi' and info.file_properties.get('MSI_ProductCode'):
                product_code = info.file_properties['MSI_ProductCode']
                is_really_installed = WindowsUtils.is_msi_product_installed(product_code)
                logger.info(f"Post-install MSI check for ProductCode '{product_code}': {'Installed' if is_really_installed else 'NOT Installed'}")
            else:
                # For EXE or MSI without known product code, re-run the registry check
                is_really_installed, found_version = WindowsUtils.check_registry(status.config.get('check_method', {}).get('keys', []))
                logger.info(f"Post-install registry check: {'Installed' if is_really_installed else 'NOT Installed'}, Version: {found_version}")

            if is_really_installed:
                status.is_installed = True
                status.last_checked = datetime.now()
                status.install_error = None
                # Retrieve version again if registry check was used for verification
                if not (info.installer_type == '.msi' and info.file_properties.get('MSI_ProductCode')):
                     status.installed_version_str = found_version if is_really_installed else None
                     status.installed_version = Version.from_string(status.installed_version_str)
                # Record successful installation
                self._record_installation(program_key, info)
                return True
            else:
                error_msg = f"Install command succeeded (Code {return_code}), but verification check failed. Program may not be installed correctly."
                logger.error(f"Installation verification failed for '{status.display_name}': {error_msg}")
                status.is_installed = False
                status.last_checked = datetime.now()
                status.install_error = "Verification failed"
                return False
        else:
            error_msg = f"Installation command failed (Return Code: {return_code}). Stderr: {stderr or 'N/A'}"
            logger.error(f"Installation failed for '{status.display_name}': {error_msg}")
            status.is_installed = False
            status.last_checked = datetime.now()
            status.install_error = f"Failed (Code {return_code})"
            return False

    def _is_msi_installed(self, product_code: str) -> bool:
        """Convenience wrapper for the WindowsUtils MSI check."""
        return WindowsUtils.is_msi_product_installed(product_code)

    def install_unidentified_program(self, installer_info: FoundInstallerInfo, mode: str = 'auto') -> bool:
        """Attempts to install a heuristically found program using generic silent switches."""
        prog_name = installer_info.path.name
        logger.info(f"Attempting '{mode}' mode installation for heuristically identified file: '{prog_name}'")

        generic_commands = {
            ".exe": '{installer_path} /S /NORESTART',
            ".msi": 'msiexec /i "{installer_path}" /qn /norestart',
        }
        cmd_template = generic_commands.get(installer_info.installer_type)

        if not cmd_template:
            logger.error(f"Installation failed for heuristic file '{prog_name}': Unknown or unsupported installer type '{installer_info.installer_type}'.")
            return False

        path_str = str(installer_info.path)
        quoted_path = f'"{path_str}"'
        base_cmd = cmd_template.format(installer_path=quoted_path)
        final_cmd = base_cmd

        if mode == 'manual':
            final_cmd = quoted_path
            logger.info(f"Heuristic manual mode: Executing installer directly.")
        elif mode == 'semi':
            if installer_info.installer_type == '.msi':
                final_cmd = f'msiexec /i {quoted_path} /passive /norestart'
            elif installer_info.installer_type == '.exe':
                 if '/s /v"/qn' in base_cmd.lower():
                     final_cmd = base_cmd.replace('/qn', '/qb')
                 elif '/S' in base_cmd or '/SILENT' in base_cmd or '/VERYSILENT' in base_cmd:
                     final_cmd = base_cmd #
                     logger.warning(f"Heuristic semi-silent mode for EXE ({prog_name}): Attempting generic silent command.")
                 else:
                     final_cmd = quoted_path
                     logger.warning(f"Heuristic semi-silent mode for EXE ({prog_name}): No known silent switch, executing manually.")
            logger.info(f"Heuristic semi-silent mode: Attempting execution.")

        logger.warning(f"Running installation for unidentified file. Command is a guess: {final_cmd}")
        run_cmd = f'start /wait "" {final_cmd}'
        ran_ok, return_code, _, stderr = WindowsUtils.run_command(run_cmd, f"Heuristic Install {prog_name}")

        if ran_ok:
            logger.info(f"Heuristic install command for '{prog_name}' completed successfully (Code {return_code}).")
            logger.warning("Installation verification and logging are NOT automatically performed for heuristic installs. Manual check recommended.")
            return True
        else:
            logger.error(f"Heuristic install command for '{prog_name}' failed (Code {return_code}). Stderr: {stderr or 'N/A'}")
            return False

    def uninstall_program(self, program_key: str) -> bool:
        """Attempts to silently uninstall a program previously installed and logged by this tool."""
        if program_key not in self.installation_log:
            logger.warning(f"Cannot uninstall '{program_key}': No installation record found in the log file. Was it installed by this tool?")
            if program_key in self.program_status:
                 status = self.program_status[program_key]
                 logger.info(f"Checking registry for potential uninstall string for '{status.display_name}' even though not in log...")
                 uninst_info = self._get_uninstall_info_from_registry(status.display_name, "")
                 cmd_orig = uninst_info.get('uninstall_string')
                 prog_name = status.display_name
                 if cmd_orig:
                      logger.info(f"Found potential uninstall string via registry: {cmd_orig}")
                 else:
                      logger.error(f"Could not find uninstall string via registry for '{status.display_name}'. Cannot proceed.")
                      return False
            else:
                 logger.error(f"Unknown program key '{program_key}'. Cannot uninstall.")
                 return False
        else:
            log_entry = self.installation_log[program_key]
            cmd_orig = log_entry.get('uninstall_string')
            prog_name = log_entry.get('name', program_key)

        if not cmd_orig:
            logger.error(f"Uninstallation failed for '{prog_name}': No uninstall command was found or recorded.")
            return False

        logger.info(f"Attempting uninstallation for '{prog_name}' (Key: {program_key}).")
        logger.debug(f"Original uninstall command: {cmd_orig}")

        product_code = None
        if 'msiexec' in cmd_orig.lower() and ('/x' in cmd_orig.lower() or '/uninstall' in cmd_orig.lower()):
             match = re.search(r'\{([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})\}', cmd_orig, re.IGNORECASE)
             if match:
                  product_code = match.group(0)
                  logger.info(f"Detected MSI uninstall via ProductCode: {product_code}")
                  cmd_orig = f'msiexec /x {product_code}'

        # Attempt to add silent flags
        cmd_silent = self._add_silent_flags_to_command(cmd_orig)
        logger.info(f"Executing uninstallation command: start /wait \"\" {cmd_silent}")

        ran_ok, return_code, _, stderr = WindowsUtils.run_command(f'start /wait "" {cmd_silent}', f"Uninstall {prog_name}", timeout=600)

        if ran_ok:
            logger.info(f"Uninstallation command for '{prog_name}' completed successfully (Code {return_code}).")

            # Verify uninstallation
            verified_uninstalled = False
            if product_code:
                logger.info(f"Verifying MSI uninstallation for ProductCode '{product_code}'...")
                if not WindowsUtils.is_msi_product_installed(product_code):
                    logger.info("MSI verification successful: Product not found.")
                    verified_uninstalled = True
                else:
                    logger.error("MSI verification FAILED: ProductCode still detected after uninstall command success.")
            else:
                # For non-MSI or unknown MSI, re-run registry check
                logger.info("Verifying uninstallation via registry check...")
                if program_key in self.program_status:
                     is_still_installed, _ = WindowsUtils.check_registry(self.program_status[program_key].config.get('check_method', {}).get('keys', []))
                     if not is_still_installed:
                          logger.info("Registry verification successful: Program no longer detected.")
                          verified_uninstalled = True
                     else:
                          logger.error("Registry verification FAILED: Program still detected after uninstall command success.")
                else:
                     logger.warning("Cannot verify uninstallation via registry: Program key unknown.")
                     verified_uninstalled = True

            if verified_uninstalled:
                # Remove from log ONLY if verification passed
                if program_key in self.installation_log:
                     try:
                          del self.installation_log[program_key]
                          self._save_installation_log()
                          logger.info(f"Removed '{program_key}' from installation log.")
                     except Exception as e:
                          logger.error(f"Failed to remove '{program_key}' from log file after successful uninstall: {e}")

                # Update status in memory
                if program_key in self.program_status:
                    self.program_status[program_key].is_installed = False
                    self.program_status[program_key].last_checked = datetime.now()
                    self.program_status[program_key].installed_version_str = None
                    self.program_status[program_key].installed_version = None
                    self.program_status[program_key].install_error = None # Clear any previous install error
                return True
            else:
                 logger.error(f"Uninstallation verification failed for '{prog_name}'. Check system manually.")
                 if program_key in self.program_status:
                      self.program_status[program_key].install_error = "Uninstall verification failed" # Use install_error for this?
                 return False
        else:
            logger.error(f"Uninstallation command for '{prog_name}' failed (Code {return_code}). Stderr: {stderr or 'N/A'}")
            if program_key in self.program_status:
                 self.program_status[program_key].install_error = f"Uninstall failed (Code {return_code})"
            return False

    def _add_silent_flags_to_command(self, command: str) -> str:
        """Attempts to append common silent/quiet flags to an uninstall command string."""
        if not command: return ""
        cmd_lower = command.lower()
        mod_cmd = command.strip()

        is_msi_uninstall = 'msiexec' in cmd_lower and ('/x' in cmd_lower or '/uninstall' in cmd_lower)

        if is_msi_uninstall:
            if '/qn' not in cmd_lower and '/quiet' not in cmd_lower:
                mod_cmd += ' /qn'
                logger.debug("Added '/qn' for MSI silent uninstall.")
            if '/norestart' not in cmd_lower:
                mod_cmd += ' /norestart'
                logger.debug("Added '/norestart' for MSI uninstall.")
        else:
            has_silent_flag = any(flag in cmd_lower for flag in [' /s', '/silent', '/verysilent', '/q', '/quiet', '-s', '-silent', '-q']) # Check common variations
            if not has_silent_flag:
                mod_cmd += ' /S'
                logger.debug("Added '/S' as a potential silent flag for EXE uninstaller.")
                if 'norestart' not in cmd_lower:
                     pass


        if mod_cmd != command.strip():
            logger.info(f"Modified uninstall command for silent execution: '{mod_cmd}' (Original: '{command.strip()}')")
            return mod_cmd
        else:
            logger.debug(f"Uninstall command already contains silent flags or no common flags identified. Using original: '{command.strip()}'")
            return command.strip()

    # --- Logging Persistence ---
    def _get_log_path(self) -> Optional[Path]:
        try:
            appdata = os.environ.get('APPDATA')
            if appdata:
                log_dir = Path(appdata) / 'ProgramInstallerApp'
                return log_dir / 'program_installer_log.json'
            else:
                logger.error("Cannot determine log file path: APPDATA environment variable not found.")
                return None
        except Exception as e:
            logger.error(f"Error getting log file path: {e}", exc_info=True)
            return None

    def _record_installation(self, program_key: str, installer_info: FoundInstallerInfo):
        if not self._log_file:
            logger.warning("Cannot record installation: Log file path is not configured.")
            return

        prog_name = self.program_status[program_key].display_name
        logger.info(f"Recording successful installation for '{prog_name}' (Key: {program_key}).")
        logger.debug(f"Attempting to find uninstall information in registry for '{prog_name}'...")

        uninst_info = self._get_uninstall_info_from_registry(prog_name, str(installer_info.path))

        if not uninst_info.get('uninstall_string'):
             logger.warning(f"Could not find UninstallString in registry for '{prog_name}' after installation. Uninstallation via this tool may fail.")
             if installer_info.installer_type == '.msi' and installer_info.file_properties.get('MSI_ProductCode'):
                  product_code = installer_info.file_properties['MSI_ProductCode']
                  uninst_info['uninstall_string'] = f'msiexec /x {product_code}'
                  logger.info(f"Using MSI ProductCode to construct uninstall string: {uninst_info['uninstall_string']}")

        log_entry = {
            'program_key': program_key,
            'name': prog_name,
            'timestamp': datetime.now().isoformat(),
            'installer_path': str(installer_info.path),
            'installer_type': installer_info.installer_type,
            'uninstall_string': uninst_info.get('uninstall_string'),
            'install_location': uninst_info.get('install_location'),
            'display_version': uninst_info.get('display_version'),
            'installer_product_version': installer_info.file_properties.get('ProductVersion'),
            'installer_file_version': installer_info.file_properties.get('FileVersion'),
        }

        # Add MSI-specific info if available
        if installer_info.installer_type == '.msi':
            log_entry['product_code'] = installer_info.file_properties.get('MSI_ProductCode')
            log_entry['display_version'] = installer_info.file_properties.get('ProductVersion') or log_entry.get('display_version')


        # Filter out None values before saving
        self.installation_log[program_key] = {k: v for k, v in log_entry.items() if v is not None}
        self._save_installation_log()
        logger.info(f"Successfully recorded installation for '{program_key}'.")
        logger.debug(f"Log entry details: {self.installation_log[program_key]}")

    def _get_uninstall_info_from_registry(self, program_name_hint: str, installer_path_hint: str) -> Dict[str, Any]:
        """Scans Uninstall registry keys to find the entry best matching the installed program."""
        # Keys to check (64-bit and 32-bit views)
        uninst_key_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
        ]
        best_match_info: Dict[str, Any] = {}
        best_score = 0
        name_hint_low = program_name_hint.lower()
        inst_dir_hint = ""
        if installer_path_hint:
             try: inst_dir_hint = str(Path(installer_path_hint).parent).lower()
             except: pass

        hkey = winreg.HKEY_LOCAL_MACHINE

        logger.debug(f"Searching registry for uninstall info. Hint Name: '{name_hint_low}', Hint Dir: '{inst_dir_hint}'")

        for key_path in uninst_key_paths:
            try:
                with winreg.OpenKey(hkey, key_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as base_key:
                    subkey_index = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(base_key, subkey_index)
                            subkey_full_path = f"{key_path}\\{subkey_name}"
                            current_info: Dict[str, Any] = {}
                            current_score = 0

                            current_info['display_name'] = WindowsUtils._reg_read_string(hkey, subkey_full_path, "DisplayName")
                            current_info['uninstall_string'] = WindowsUtils._reg_read_string(hkey, subkey_full_path, "UninstallString")
                            current_info['install_location'] = WindowsUtils._reg_read_string(hkey, subkey_full_path, "InstallLocation")
                            current_info['display_version'] = WindowsUtils._reg_read_string(hkey, subkey_full_path, "DisplayVersion")
                            current_info['publisher'] = WindowsUtils._reg_read_string(hkey, subkey_full_path, "Publisher")
                            current_info['key_path'] = subkey_full_path # Store where it was found

                            if not current_info.get('display_name') or not current_info.get('uninstall_string'):
                                subkey_index += 1
                                continue

                            # --- Scoring Logic ---
                            dn_low = current_info['display_name'].lower()
                            il_low = (current_info.get('install_location') or "").lower()

                            # 1. Strong match: DisplayName contains hint name or vice-versa
                            if name_hint_low in dn_low or dn_low in name_hint_low:
                                current_score += 5
                                logger.debug(f"  Score +5: Name match ('{dn_low}' vs '{name_hint_low}') in {subkey_name}")

                            # 2. Good match: InstallLocation matches installer directory hint
                            if il_low and inst_dir_hint and il_low == inst_dir_hint:
                                current_score += 3
                                logger.debug(f"  Score +3: Install location match ('{il_low}') in {subkey_name}")

                            # 3. Bonus: Both name and location match
                            if current_score >= 8: # Matched both name and location
                                current_score += 2
                                logger.debug(f"  Score +2: Bonus for name and location match in {subkey_name}")

                            # 4. Weaker match: Partial name match

                            logger.debug(f"  Checking Subkey: {subkey_name}, DisplayName: '{current_info['display_name']}', Score: {current_score}")

                            # Update best match if current score is higher
                            if current_score > best_score:
                                logger.debug(f"  >>> New best match found: {subkey_name} (Score: {current_score})")
                                best_score = current_score
                                best_match_info = current_info

                            subkey_index += 1
                        except OSError:
                            break
                        except Exception as sub_e:
                            logger.warning(f"Error reading subkey index {subkey_index} under {key_path}: {sub_e}")
                            subkey_index += 1

            except FileNotFoundError:
                logger.debug(f"Uninstall registry path not found: {key_path}")
                continue
            except Exception as base_e:
                logger.error(f"Error accessing registry path {key_path}: {base_e}", exc_info=True)
                continue

        if best_score > 0:
            logger.info(f"Found best uninstall registry match for '{program_name_hint}' with score {best_score}:")
            logger.info(f"  DisplayName: {best_match_info.get('display_name')}")
            logger.info(f"  UninstallString: {best_match_info.get('uninstall_string')}")
            logger.info(f"  KeyPath: {best_match_info.get('key_path')}")

            # Basic cleanup for UninstallString (remove arguments often added by system)
            raw_uninst = best_match_info.get('uninstall_string')
            if raw_uninst:
                if raw_uninst.startswith('"') and raw_uninst.endswith('"'):
                    raw_uninst = raw_uninst[1:-1].strip()
                if 'msiexec.exe' in raw_uninst.lower():
                     parts = re.split(r'(/x\{[0-9a-f-]+\})', raw_uninst, flags=re.IGNORECASE)
                     if len(parts) >= 2:
                          cleaned_uninst = parts[0].strip() + " " + parts[1].strip()
                          logger.debug(f"Cleaned MSI uninstall string: {cleaned_uninst}")
                          best_match_info['uninstall_string'] = cleaned_uninst
                     else:
                          best_match_info['uninstall_string'] = raw_uninst.strip()
                else:
                     best_match_info['uninstall_string'] = raw_uninst.strip()


            return best_match_info
        else:
            logger.warning(f"Could not find a suitable uninstall registry entry for hint '{program_name_hint}'.")
            return {}

    def _load_installation_log(self):
        if not self._log_file:
            logger.warning("Log file path not set, cannot load log.")
            self.installation_log = {}
            return
        if not self._log_file.exists():
            logger.info("Installation log file not found. Starting with empty log.")
            self.installation_log = {}
            return

        try:
            with open(self._log_file, 'r', encoding='utf-8') as f:
                self.installation_log = json.load(f)
            logger.info(f"Loaded {len(self.installation_log)} installation records from {self._log_file}")
        except json.JSONDecodeError as e:
             logger.error(f"Failed to decode JSON from log file {self._log_file}: {e}. Creating backup and starting fresh.", exc_info=True)
             try: shutil.move(str(self._log_file), str(self._log_file) + ".corrupt")
             except Exception as move_e: logger.error(f"Could not backup corrupt log file: {move_e}")
             self.installation_log = {}
        except Exception as e:
            logger.error(f"Failed to load installation log from {self._log_file}: {e}", exc_info=True)
            self.installation_log = {} # Start with empty log on other errors

    def _save_installation_log(self):
        if not self._log_file:
            logger.error("Cannot save installation log: Log file path is not configured.")
            return

        try:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)

            tmp_log_file = self._log_file.with_suffix(".tmp")
            with open(tmp_log_file, 'w', encoding='utf-8') as f:
                json.dump(self.installation_log, f, indent=2, ensure_ascii=False)

            os.replace(tmp_log_file, self._log_file)
            logger.info(f"Successfully saved {len(self.installation_log)} records to installation log: {self._log_file}")

        except Exception as e:
            logger.error(f"Failed to save installation log to {self._log_file}: {e}", exc_info=True)
            if 'tmp_log_file' in locals() and tmp_log_file.exists():
                try:
                    tmp_log_file.unlink()
                    logger.debug("Removed temporary log file after save error.")
                except OSError as unlink_e:
                    logger.warning(f"Could not remove temporary log file {tmp_log_file} after save error: {unlink_e}")


# --- GUI Components ---
class WorkerThread(QThread):
    task_complete = pyqtSignal(str, object)
    progress_update = pyqtSignal(str, str)

    def __init__(self, installer: ProgramInstaller, task_name: str, *args, **kwargs):
        super().__init__()
        self.installer = installer
        self.task_name = task_name
        self.args = args
        self.kwargs = kwargs
        self._is_running = True

    def run(self):
        result = None
        try:
            task_map = {
                "scan": lambda: self.installer.scan_for_installers(),
                "check_status": lambda: self.installer.check_installation_status(self.args[0] if self.args else None),
                "install": lambda: self.installer.install_program(self.args[0], self.kwargs.get('mode', 'auto')),
                "install_heuristic": lambda: self.installer.install_unidentified_program(self.args[0], self.kwargs.get('mode', 'auto')),
                "uninstall": lambda: self.installer.uninstall_program(self.args[0])
            }

            if self.task_name in task_map:
                # Identify the program being worked on for progress messages
                prog_key_or_info = self.args[0] if self.args else None
                prog_name = ""
                if self.task_name == "install":
                    status = self.installer.program_status.get(prog_key_or_info)
                    prog_name = status.display_name if status else str(prog_key_or_info)
                elif self.task_name == "install_heuristic" and isinstance(prog_key_or_info, FoundInstallerInfo):
                    prog_name = f"[Heuristic] {prog_key_or_info.path.name}"
                elif self.task_name == "uninstall":
                    log_entry = self.installer.installation_log.get(prog_key_or_info)
                    prog_name = log_entry.get('name', str(prog_key_or_info)) if log_entry else str(prog_key_or_info)

                self.progress_update.emit(self.task_name, f"Starting {self.task_name}: {prog_name}...")
                logger.info(f"WorkerThread starting task '{self.task_name}' for '{prog_name}'")

                result = task_map[self.task_name]()

                if not self._is_running:
                     logger.info(f"WorkerThread task '{self.task_name}' cancelled.")
                     self.progress_update.emit(self.task_name, f"Task cancelled: {prog_name}")
                     self.task_complete.emit(self.task_name, None)
                     return

                self.progress_update.emit(self.task_name, f"{self.task_name.capitalize()} finished for {prog_name}.")

            else:
                errmsg = f"Unknown task requested in WorkerThread: {self.task_name}"
                logger.error(errmsg)
                self.progress_update.emit(self.task_name, errmsg)
                result = None
            if self._is_running:
                 self.task_complete.emit(self.task_name, result)

        except Exception as e:
            logger.error(f"Error executing task '{self.task_name}' in WorkerThread: {e}", exc_info=True)
            if self._is_running:
                self.progress_update.emit(self.task_name, f"Task failed: {e}")
                self.task_complete.emit(self.task_name, None)

        finally:
            self._is_running = False

    def stop(self):
        """Requests the thread to stop execution."""
        logger.info(f"Stop requested for WorkerThread task '{self.task_name}'")
        self._is_running = False
        self.progress_update.emit(self.task_name, "Cancellation requested...")

class ProgramInstallerUI(QWidget):
    """Main application window."""
    update_tree_signal = pyqtSignal()

    COL_PROGRAM = 0
    COL_INSTALLED = 1
    COL_FOUND = 2
    COL_PATH = 3
    COL_VERSION = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        QApplication.setOrganizationName("InstallerAppOrg")
        QApplication.setApplicationName("ProgramInstallerApp")

        self.installer = ProgramInstaller()
        self.active_threads: List[WorkerThread] = []
        self.pending_updates = False

        self._setup_ui()

        self.update_tree_signal.connect(self._populate_program_list)

        self._populate_program_list()
        self._update_ui_state()

        QTimer.singleShot(500, self._initial_status_check)

    def _setup_ui(self):
        self.setFixedSize(991, 701)
        main_layout = QVBoxLayout(self)

        # --- Toolbar ---
        self.toolbar = self._create_toolbar()
        main_layout.addWidget(self.toolbar)

        # --- Main Splitter ---
        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter)

        # --- Program Tree View ---
        self.program_tree = QTreeWidget()
        self.program_tree.setColumnCount(5)
        self.program_tree.setHeaderLabels(["Назва", "Встановлено?", "Знайдено інсталятор?", "Шлях", "Версія (Встановлено/Знайдено)"])
        hdr = self.program_tree.header()
        hdr.setSectionResizeMode(self.COL_PROGRAM, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(self.COL_INSTALLED, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(self.COL_FOUND, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(self.COL_PATH, QHeaderView.Stretch)
        hdr.setSectionResizeMode(self.COL_VERSION, QHeaderView.ResizeToContents)
        self.program_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.program_tree.setSortingEnabled(True)
        self.program_tree.sortByColumn(self.COL_PROGRAM, Qt.AscendingOrder)
        self.program_tree.itemSelectionChanged.connect(self._update_selection_info)
        self.program_tree.setAlternatingRowColors(True)
        splitter.addWidget(self.program_tree)

        # --- Details Panel (Bottom) ---
        details_panel = QWidget()
        details_layout = QHBoxLayout(details_panel)
        details_layout.setContentsMargins(5, 5, 5, 5)

        # Left side: Information Label
        self.selected_info = QLabel("Виберіть програму для відображення деталей.")
        self.selected_info.setWordWrap(True)
        self.selected_info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        details_layout.addWidget(self.selected_info, 1)

        # Right side: Control Buttons and Install Mode
        control_panel_widget = QWidget()
        control_panel_layout = QVBoxLayout(control_panel_widget)
        control_panel_layout.setAlignment(Qt.AlignTop)
        control_panel_layout.setSpacing(10)

        # Install Mode ComboBox
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Режим встановлення:")
        self.install_mode_combo = QComboBox()
        self.install_mode_combo.addItems(["Авто (тихо)", "Напів-автоматично", "Ручна"])
        self.install_mode_combo.setToolTip("Choose how installers are executed:\n"
                                           " - Авто: Спроба повністю безшумного встановлення за допомогою налаштованих перемикачів.\n"
                                           " - Напів-автоматично: Спроба встановлення з мінімальним інтерфейсом користувача (наприклад, індикатор виконання).\n"
                                           " - Ручний: Запускає програму встановлення в інтерактивному режимі.")
        self.install_mode_combo.setCurrentIndex(0)
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.install_mode_combo)
        control_panel_layout.addLayout(mode_layout)

        # Install Button
        self.install_button = QPushButton(self._get_icon(QStyle.SP_DialogApplyButton), " Встановити")
        self.install_button.clicked.connect(self._install_selected)
        self.install_button.setToolTip("Встановіть вибрані програми, які ще не встановлені та мають знайдений інсталятор.")
        self.install_button.setEnabled(False)
        control_panel_layout.addWidget(self.install_button)

        # Uninstall Button
        self.uninstall_button = QPushButton(self._get_icon(QStyle.SP_TrashIcon), " Видалити вибране")
        self.uninstall_button.clicked.connect(self._uninstall_selected)
        self.uninstall_button.setToolTip("Спроба видалити вибрану програму за допомогою записаної інформації.\nПрацює лише для програм, встановлених за допомогою цього інструменту або з виявленими рядками видалення.")
        self.uninstall_button.setEnabled(False)
        control_panel_layout.addWidget(self.uninstall_button)

        control_panel_layout.addStretch()
        details_layout.addWidget(control_panel_widget)

        splitter.addWidget(details_panel)
        splitter.setSizes([int(self.height() * 0.7), int(self.height() * 0.3)])

        # --- Status Bar ---
        self.status_label = QLabel("Готово. Встановіть шлях для початку сканування.")
        main_layout.addWidget(self.status_label)

    def _get_icon(self, standard_icon: QStyle.StandardPixmap) -> QIcon:
        app_instance = QApplication.instance()
        if app_instance:
            return app_instance.style().standardIcon(standard_icon)
        else:
            return QIcon()

    def _create_toolbar(self) -> QToolBar:
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.setIconSize(QSize(16, 16))

        # Set Scan Path Action
        setp_action = toolbar.addAction(self._get_icon(QStyle.SP_DirOpenIcon), "Шлях сканування")
        setp_action.triggered.connect(self._set_search_path)
        setp_action.setToolTip("Виберіть каталог, що містить інсталятори програм для сканування.")

        # Scan Action
        self.scan_action = toolbar.addAction(self._get_icon(QStyle.SP_BrowserReload), "Сканувати")
        self.scan_action.triggered.connect(self._scan_programs)
        self.scan_action.setToolTip("Сканування вибраного шляху на наявність інсталяторів і порівняйте з конфігураціями.")
        self.scan_action.setEnabled(False)

        # Check Status Action
        self.check_status_action = toolbar.addAction(self._get_icon(QStyle.SP_DriveNetIcon), "Перевірити статус")
        self.check_status_action.triggered.connect(self._check_status)
        self.check_status_action.setToolTip("Перевірити стан встановлення програм через реєстр.")
        toolbar.addSeparator()

        # Filter Input
        toolbar.addWidget(QLabel(" Список фільтрів:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Введіть, щоб відфільтрувати програми...")
        self.filter_input.textChanged.connect(self._filter_program_list)
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.setToolTip("Відфільтр списоку за назвою програми, шляхом або версією.")
        toolbar.addWidget(self.filter_input)
        return toolbar

    def _set_search_path(self):
        settings = QSettings()
        start_dir = self.installer.search_path or settings.value("last_search_path", str(Path.home()))
        path = QFileDialog.getExistingDirectory(self, "Виберіть папку для сканування інсталятора", start_dir)

        if path:
            logger.info(f"The path selected by the user: {path}")
            if self.installer.set_search_path(path):
                self.status_label.setText(f"The scan path is set: {path}")
                settings.setValue("last_search_path", path)
                self._clear_program_list_results()
                self._update_ui_state()
            else:
                QMessageBox.warning(self, "The wrong path", f"The chosen path '{path}' cannot be used. Please make sure it exists and is available.")
                self._update_ui_state()

    def _clear_program_list_results(self):
         self.program_tree.setSortingEnabled(False)
         for i in range(self.program_tree.topLevelItemCount()):
              item = self.program_tree.topLevelItem(i)
              data = item.data(0, Qt.UserRole)
              if data and data['type'] == 'config':
                   item.setText(self.COL_INSTALLED, "?")
                   item.setText(self.COL_FOUND, "No")
                   item.setText(self.COL_PATH, "-")
                   item.setText(self.COL_VERSION, "-")
                   item.setForeground(self.COL_INSTALLED, QColor("orange"))
                   item.setForeground(self.COL_FOUND, QColor("gray"))
                   item.setFont(self.COL_PROGRAM, QFont())
              elif data and data['type'] == 'heuristic':
                   item.setHidden(True)

         self.program_tree.setSortingEnabled(True)
         self._update_selection_info()


    def _scan_programs(self):
        if not self.installer.search_path:
            QMessageBox.warning(self, "Шлях сканування не встановлено", "Будь ласка, спочатку встановіть каталог для пошуку інсталяторів за допомогою пункту «Встановити шлях сканування».'.")
            return
        if self._is_task_running("scan"):
            self.status_label.setText("Сканування вже триває.")
            return
        self._run_task("scan")

    def _check_status(self):
        if self._is_task_running("check_status"):
             self.status_label.setText("Перевірка статусу вже триває.")
             return
        self._run_task("check_status", list(self.installer.program_status.keys()))

    def _initial_status_check(self):
        if self.installer.search_path:
            logger.info("An initial check of the installation status is performed")
            self._check_status()
        else:
             logger.info("Skip the initial status check because the search path is not loaded.")


    def _install_selected(self):
        selected_data = self._get_selected_item_data()
        tasks_to_run: List[Tuple[str, Any]] = []

        for data in selected_data:
            item_type = data.get("type")
            if item_type == "config":
                key = data["key"]
                status = self.installer.program_status.get(key)
                if status and status.found_installer and status.is_installed is False:
                    tasks_to_run.append(("install", key))
                else:
                     logger.debug(f"Skipping install for config '{key}': Not installable (Found: {status.found_installer is not None}, Installed: {status.is_installed})")
            elif item_type == "heuristic":
                info = data.get("info")
                if info:
                     tasks_to_run.append(("install_heuristic", info))

        if not tasks_to_run:
            QMessageBox.information(self, "Нічого встановлювати", "Не вибрано жодної програми, яку можна інсталювати. Виберіть програми, які не встановлено, але для яких знайдено інсталятор.")
            return

        mode_text = self.install_mode_combo.currentText()
        install_mode = 'auto'
        if "Напів-автоматично" in mode_text: install_mode = 'semi'
        elif "Ручна" in mode_text: install_mode = 'manual'
        logger.info(f"Selected install mode: {install_mode} ('{mode_text}')")

        # Confirmation dialog
        names_to_install = []
        for task_type, data in tasks_to_run:
            if task_type == "install": names_to_install.append(self.installer.program_status[data].display_name)
            elif task_type == "install_heuristic": names_to_install.append(f"[Heuristic] {data.path.name}")

        confirm_msg = f"Ви впевнені, що хочете спробувати встановити для {len(tasks_to_run)} елемент з використанням '{install_mode}' режиму?\n\n"
        confirm_msg += f"Items:\n - {', '.join(names_to_install[:5])}"
        if len(names_to_install) > 5: confirm_msg += "\n - ..."
        if any(t == "install_heuristic" for t, d in tasks_to_run):
            confirm_msg += "\n\nПримітка: Команди встановлення для евристичних елементів є найкращими припущеннями і можуть не спрацювати або вимагати втручання."

        reply = QMessageBox.question(self, "Підтвердити встановлення", confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)

        if reply == QMessageBox.Yes:
            logger.info(f"User confirmed installation for {len(tasks_to_run)} items in '{install_mode}' mode.")
            for task_type, data in tasks_to_run:
                # Pass the selected mode to the worker task
                self._run_task(task_type, data, mode=install_mode)
        else:
             logger.info("User cancelled installation.")


    def _uninstall_selected(self):
        selected_data = self._get_selected_item_data()
        tasks_to_run: List[str] = []
        names_to_uninstall: List[str] = []

        for data in selected_data:
            item_type = data.get("type")
            if item_type == "config":
                key = data["key"]
                log_entry = self.installer.installation_log.get(key)
                if log_entry and log_entry.get('uninstall_string'):
                    tasks_to_run.append(key)
                    names_to_uninstall.append(log_entry.get('name', key))
                elif self.installer.program_status.get(key, ProgramStatus(key,"",{})).is_installed:
                     logger.warning(f"Config item '{key}' selected for uninstall, but not found in log or no uninstall string. Attempting registry lookup (may fail).")
                     tasks_to_run.append(key)
                     names_to_uninstall.append(self.installer.program_status[key].display_name + " (Not Logged)")

            elif item_type == "heuristic":
                QMessageBox.warning(self, "Не вдається видалити евристичний елемент", "Видалення не підтримується для евристично визначених елементів, оскільки їхнє встановлення не було відстежено.")
                return

        if not tasks_to_run:
            QMessageBox.warning(self, "Видаляти нічого", "Жодна з вибраних програм не містить інформації про видалення або не інстальована.\nВидалення надійно працює лише для програм, встановлених за допомогою цього інструменту, або для тих, у яких можна виявити записи реєстру.")
            return

        # Confirmation dialog
        confirm_msg = f"Ви впевнені, що хочете спробувати видалити {len(tasks_to_run)} програми?\n\n"
        confirm_msg += f"Items:\n - {', '.join(names_to_uninstall[:5])}"
        if len(names_to_uninstall) > 5: confirm_msg += "\n - ..."
        confirm_msg += "\n\nПопередження: Буде зроблено спробу запустити програму видалення безшумно. Переконайтеся, що не виконується жодна важлива робота."
        if any("(Not Logged)" in name for name in names_to_uninstall):
             confirm_msg += "\nДеякі вибрані елементи не було знайдено у журналі інсталяції; успішне видалення є менш імовірним."

        reply = QMessageBox.question(self, "Підтвердити видалення", confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) # Default No

        if reply == QMessageBox.Yes:
            logger.info(f"User confirmed uninstallation for {len(tasks_to_run)} items.")
            for key in tasks_to_run:
                self._run_task("uninstall", key)
        else:
             logger.info("User cancelled uninstallation.")


    def _populate_program_list(self):
        """Refreshes the QTreeWidget with current program status."""
        logger.debug("Populating program list tree...")
        self.program_tree.setSortingEnabled(False)
        self.program_tree.clear()

        items_to_add: List[QTreeWidgetItem] = []
        status_dict = self.installer.get_current_status()

        # Define colors and fonts for clarity
        colors = {
            'installed': QColor("darkGreen"),
            'not_installed': QColor("red"),
            'found': QColor("darkBlue"),
            'not_found': QColor("gray"),
            'unknown': QColor("orange"),
            'heuristic': QColor("purple"),
            'error': QColor("darkRed"),
        }
        font_normal = QFont()
        font_bold = QFont(); font_bold.setBold(True)
        font_italic = QFont(); font_italic.setItalic(True)

        # 1. Add Configured Programs
        for key, status in status_dict.items():
            if status.is_installed is True:
                inst_text, inst_color = "Yes", colors['installed']
            elif status.is_installed is False:
                inst_text, inst_color = "No", colors['not_installed']
            else:
                inst_text, inst_color = "?", colors['unknown']

            installer_found = status.found_installer is not None
            found_text = "Yes" if installer_found else "No"
            found_color = colors['found'] if installer_found else colors['not_found']
            path_str = str(status.found_installer.path) if installer_found else "-"
            path_tooltip = path_str

            installed_v_str = str(status.installed_version) if status.installed_version and not status.installed_version.is_zero() else "N/A"
            found_v_str = "N/A"
            version_display = installed_v_str
            version_tooltip = f"Installed: {installed_v_str} / Found: N/A"

            if status.found_installer and status.found_installer.version and not status.found_installer.version.is_zero():
                found_v_str = str(status.found_installer.version)
                version_display = f"{installed_v_str} / {found_v_str}"

                # Add visual cue if an upgrade is available
                if status.installed_version and status.found_installer.version > status.installed_version:
                    font = item.font(self.COL_VERSION)
                    font.setBold(True)
                    item.setFont(self.COL_VERSION, font)
                    item.setForeground(self.COL_VERSION, QColor("#008000")) # Green
                    item.setToolTip(self.COL_VERSION, "Знайдено новішу версію інсталятора.")

            item = QTreeWidgetItem([status.display_name, inst_text, found_text, path_str, version_display])
            item.setData(0, Qt.UserRole, {"type": "config", "key": key}) # Store key in item data

            # Apply Colors
            item.setForeground(self.COL_INSTALLED, inst_color)
            item.setForeground(self.COL_FOUND, found_color)

            # Apply Tooltips
            item.setToolTip(self.COL_PROGRAM, f"Configured Program: {status.display_name}\nKey: {key}")
            item.setToolTip(self.COL_INSTALLED, f"Checked: {status.last_checked.strftime('%Y-%m-%d %H:%M:%S') if status.last_checked else 'Never'}\nError: {status.install_error or 'None'}")
            item.setToolTip(self.COL_FOUND, f"Installer file found by scan.")
            item.setToolTip(self.COL_PATH, path_tooltip)
            item.setToolTip(self.COL_VERSION, version_tooltip)


            # Apply Font Styling based on state
            if status.is_installed:
                item.setForeground(self.COL_PROGRAM, colors['installed'])
                item.setFont(self.COL_PROGRAM, font_normal)
            elif installer_found and status.is_installed is False:
                item.setForeground(self.COL_PROGRAM, colors['not_installed'])
                item.setFont(self.COL_PROGRAM, font_bold)
            else:
                item.setForeground(self.COL_PROGRAM, colors['not_found'] if status.is_installed is False else colors['unknown'])
                item.setFont(self.COL_PROGRAM, font_normal)

            items_to_add.append(item)

        #Heuristically Found Programs
        for info in self.installer.unidentified_installers:
            props = info.file_properties
            heur_name = "[SUS] "
            heur_name += props.get('ProductName') or props.get('FileDescription') or Path(info.path.name).stem
            if not props.get('ProductName') and not props.get('FileDescription'):
                 heur_name += " (No Name Prop)"

            inst_text, inst_color = "?", colors['unknown']
            found_text, found_color = "Heuristic", colors['heuristic']
            path_str = str(info.path)
            path_tooltip = path_str

            # Version from file properties
            pv = props.get('ProductVersion') or props.get('FileVersion')
            version_str = f"Found: {pv}" if pv else "Found: ?"
            version_tooltip = f"Heuristic Installer Version (File: {props.get('FileVersion', 'N/A')}, Prod: {props.get('ProductVersion', 'N/A')})"

            item = QTreeWidgetItem([heur_name, inst_text, found_text, path_str, version_str])
            item.setData(0, Qt.UserRole, {"type": "heuristic", "info": info})

            # Apply Colors & Font
            item.setForeground(self.COL_PROGRAM, colors['heuristic'])
            item.setForeground(self.COL_INSTALLED, inst_color)
            item.setForeground(self.COL_FOUND, found_color)
            item.setFont(self.COL_PROGRAM, font_italic)

             # Apply Tooltips
            score = self.installer._score_potential_installer(info)
            item.setToolTip(self.COL_PROGRAM, f"Heuristically Identified Potential Installer\nScore: {score:.2f}\nPath: {path_str}")
            item.setToolTip(self.COL_INSTALLED, "Installation status unknown for heuristic items.")
            item.setToolTip(self.COL_FOUND, f"Identified by heuristic rules (Score: {score:.2f}). Not matched to specific configuration.")
            item.setToolTip(self.COL_PATH, path_tooltip)
            item.setToolTip(self.COL_VERSION, version_tooltip)

            items_to_add.append(item)

        # Add all items to the tree
        self.program_tree.addTopLevelItems(items_to_add)

        # Resize columns after adding items
        for i in range(self.program_tree.columnCount()):
            if i != self.COL_PATH:
                self.program_tree.resizeColumnToContents(i)
        self.program_tree.setSortingEnabled(True)
        self._filter_program_list()
        self._update_selection_info()
        logger.debug("Finished populating program list tree.")

    def _filter_program_list(self):
        filter_text = self.filter_input.text().lower().strip()
        logger.debug(f"Filtering list with text: '{filter_text}'")

        for i in range(self.program_tree.topLevelItemCount()):
            item = self.program_tree.topLevelItem(i)
            data = item.data(0, Qt.UserRole)
            matches_filter = True

            if filter_text:
                text_to_search = [
                    item.text(self.COL_PROGRAM).lower(),
                    item.text(self.COL_PATH).lower(),
                    item.text(self.COL_VERSION).lower(),
                ]
                if data and data['type'] == 'config':
                     text_to_search.append(data['key'].lower())
                matches_filter = any(filter_text in txt for txt in text_to_search)
            item.setHidden(not matches_filter)

    def _get_selected_item_data(self) -> List[Dict]:
        return [item.data(0, Qt.UserRole) for item in self.program_tree.selectedItems() if item.data(0, Qt.UserRole)]

    def _update_selection_info(self):
        selected_data = self._get_selected_item_data()
        count = len(selected_data)
        can_install_any = False
        can_uninstall_any = False

        info_html = ""

        if count == 0:
            info_html = "<i>Виберіть пункт зі списку вище, щоб дізнатися більше.</i>"
        elif count == 1:
            data = selected_data[0]
            item_type = data.get("type")
            info_lines = []

            if item_type == "config":
                key = data["key"]
                status = self.installer.program_status.get(key)
                log_entry = self.installer.installation_log.get(key)

                if status:
                    info_lines.append(f"<b>{status.display_name}</b> (Config Key: {key})")
                    if status.is_installed is True: info_lines.append(f"&nbsp;&nbsp;Статус: <font color='darkGreen'>Встановлено</font> (Version: {status.last_installed_version or '?'})")
                    elif status.is_installed is False: info_lines.append(f"&nbsp;&nbsp;Статус: <font color='red'>Не встановлено</font>")
                    else: info_lines.append(f"&nbsp;&nbsp;Статус: <font color='orange'>Невідомо / Не перевірено</font>")
                    if status.last_checked: info_lines.append(f"&nbsp;&nbsp;Остання перевірка: {status.last_checked.strftime('%Y-%m-%d %H:%M')}")
                    if status.install_error: info_lines.append(f"&nbsp;&nbsp;<font color='darkRed'>Остання помилка:</font> {status.install_error}")

                    # Installer Info
                    if status.found_installer:
                        info_lines.append(f"&nbsp;&nbsp;Інсталятор: <font color='darkBlue'>Found</font>")
                        info_lines.append(f"&nbsp;&nbsp;&nbsp;&nbsp;Шлях: {status.found_installer.path}")
                        props = status.found_installer.file_properties
                        pv = props.get('ProductVersion') or props.get('FileVersion')
                        info_lines.append(f"&nbsp;&nbsp;&nbsp;&nbsp;Версія інсталятора: {pv or 'N/A'}")
                        if status.is_installed is False: can_install_any = True
                    else:
                        info_lines.append(f"&nbsp;&nbsp;Інсталятор: <font color='gray'>Not Found</font>")

                    # Uninstall Info
                    if log_entry and log_entry.get('uninstall_string'):
                        info_lines.append(f"&nbsp;&nbsp;Видалено: Логовано")
                        info_lines.append(f"&nbsp;&nbsp;&nbsp;&nbsp;Команда: {log_entry.get('uninstall_string')}")
                        info_lines.append(f"&nbsp;&nbsp;&nbsp;&nbsp;Встановлено: {log_entry.get('timestamp')}")
                        if status.is_installed: can_uninstall_any = True
                    elif status.is_installed:
                        info_lines.append(f"&nbsp;&nbsp;Видалено: <font color='orange'>Не логовано (можна спробувати пошук в реєстрі)</font>")
                        can_uninstall_any = True
                    else:
                        info_lines.append(f"&nbsp;&nbsp;Видалено: Не логовано / Не стосується")

            elif item_type == "heuristic":
                info: FoundInstallerInfo = data.get("info")
                if info:
                    props = info.file_properties
                    name = props.get('Назва') or props.get('FileDescription') or Path(info.path.name).stem
                    info_lines.append(f"<b>[Heuristic] {name}</b>")
                    info_lines.append(f"&nbsp;&nbsp;Тип: Потенційний інсталятор (евристичний пошук)")
                    score = self.installer._score_potential_installer(info)
                    info_lines.append(f"&nbsp;&nbsp;Рейтинг впевненості: {score:.2f}")
                    info_lines.append(f"&nbsp;&nbsp;Шлях: {info.path}")
                    pv = props.get('ProductVersion') or props.get('FileVersion')
                    info_lines.append(f"&nbsp;&nbsp;Версія: {pv or 'N/A'}")
                    info_lines.append(f"&nbsp;&nbsp;Компанія: {props.get('CompanyName') or 'N/A'}")
                    can_install_any = True

            info_html = "<br>".join(info_lines)
        else:
            info_html = f"<b>{count} items selected.</b><br>"
            installable_count = 0
            uninstallable_count = 0
            for data in selected_data:
                item_type = data.get("type")
                if item_type == 'config':
                    key = data['key']
                    status = self.installer.program_status.get(key)
                    log = self.installer.installation_log.get(key)
                    if status and status.found_installer and status.is_installed is False:
                        can_install_any = True
                        installable_count += 1
                    if status and status.is_installed and (log and log.get('uninstall_string')):
                         can_uninstall_any = True
                         uninstallable_count +=1
                    elif status and status.is_installed:
                         can_uninstall_any = True
                         # uninstallable_count += 1 # Don't count if not logged? Or count as potential?

                elif item_type == 'heuristic':
                    can_install_any = True
                    installable_count += 1

            info_html += f"&nbsp;&nbsp;Installable: {installable_count}<br>"
            info_html += f"&nbsp;&nbsp;Uninstallable (Logged): {uninstallable_count}"


        self.selected_info.setText(info_html)

        # Enable/disable buttons based on *overall* possibility for selection
        self.install_button.setEnabled(can_install_any)
        self.uninstall_button.setEnabled(can_uninstall_any)

    def _update_ui_state(self):
        is_idle = not any(t.isRunning() for t in self.active_threads)
        path_is_set = self.installer.search_path is not None

        # Toolbar Actions
        self.scan_action.setEnabled(is_idle and path_is_set)
        self.scan_action.setToolTip("Проскануйте вибраний шлях на наявність інсталяторів." if path_is_set else "Спочатку встановіть шлях сканування.")
        self.check_status_action.setEnabled(is_idle)
        self.toolbar.setEnabled(is_idle)
        self._update_selection_info()
        if not is_idle:
             self.install_button.setEnabled(False)
             self.uninstall_button.setEnabled(False)

        # Update status label message
        if not is_idle:
            running_tasks = [t.task_name for t in self.active_threads if t.isRunning()]
            self.status_label.setText(f"Зайнято: {', '.join(running_tasks)}...")
        elif not path_is_set:
             self.status_label.setText("Готово. Встановіть шлях для початку сканування.")
        else:
             self.status_label.setText("Готовий.")

    def _is_task_running(self, task_name_prefix: str) -> bool:
        return any(t.isRunning() and t.task_name.startswith(task_name_prefix) for t in self.active_threads)

    def _run_task(self, task_name: str, *args, **kwargs):
        if task_name in ["scan", "check_status"] and self._is_task_running(task_name):
            self.status_bar.showMessage(f"{task_name.capitalize()} is already running.", 3000)
            logger.warning(f"Task '{task_name}' requested but already running.")
            return
        logger.info(f"Starting worker thread for task: '{task_name}'")
        self._set_actions_enabled(False)

        thread = WorkerThread(self.installer, task_name, *args, **kwargs)

        # Connect signals
        thread.task_complete.connect(self._on_task_complete)
        thread.progress_update.connect(self._on_progress_update)
        thread.finished.connect(lambda th=thread: self._thread_finished(th))

        self.active_threads.append(thread)
        thread.start()
        self._update_ui_state()

    def _set_actions_enabled(self, enabled: bool):
        path_is_set = self.installer.search_path is not None
        self.scan_action.setEnabled(enabled and path_is_set)
        self.check_status_action.setEnabled(enabled)
        if enabled:
            self._update_selection_info()
        else:
            self.install_button.setEnabled(False)
            self.uninstall_button.setEnabled(False)
        self.toolbar.setEnabled(enabled)


    def _can_install_selected(self) -> bool:
        data = self._get_selected_item_data()
        return any(
            (d.get('type') == 'heuristic') or
            (d.get('type') == 'config' and (st := self.installer.program_status.get(d.get('key'))) and st.found_installer and st.is_installed is False)
            for d in data
        )

    def _can_uninstall_selected(self) -> bool:
        data = self._get_selected_item_data()
        return any(
             d.get('type') == 'config' and
             (st := self.installer.program_status.get(d.get('key'))) and
             st.is_installed and
             ( (key := d.get('key')) in self.installer.installation_log and self.installer.installation_log[key].get('uninstall_string') or True)
            for d in data
        )

    # --- Signal Handlers / Slots ---
    def _on_progress_update(self, task_name: str, message: str):
        self.status_label.setText(f"[{task_name}] {message}")

    def _on_task_complete(self, task_name: str, result: Any):
        logger.info(f"GUI received task_complete signal: Task='{task_name}', Result type='{type(result)}'")
        if task_name in ["scan", "check_status", "install", "install_heuristic", "uninstall"]:
            logger.debug(f"Requesting UI update after task '{task_name}' completion.")
            if not self.pending_updates:
                 self.pending_updates = True
                 QTimer.singleShot(150, self._trigger_tree_update)

        # Show specific messages for success/failure of install/uninstall
        if task_name == "install" or task_name == "install_heuristic":
            prog_name = self.sender().args[0]
            if isinstance(prog_name, FoundInstallerInfo): prog_name = prog_name.path.name
            else: prog_name = self.installer.program_status.get(prog_name, ProgramStatus("","",{})).display_name

            if result is True:
                QMessageBox.information(self, "Успішне встановлення", f"Успішно завершено встановлення для '{prog_name}'.")
            elif result is False:
                QMessageBox.warning(self, "Помилка інсталяції", f"Не вдалося встановити '{prog_name}'.\nПеревірте журнал для отримання детальної інформації.")
            elif result is None:
                 QMessageBox.critical(self, "Помилка встановлення", f"Під час інсталяції виникла неочікувана помилка для '{prog_name}'. Перевірте журнал.")

        elif task_name == "uninstall":
            prog_key = self.sender().args[0]
            prog_name = self.installer.installation_log.get(prog_key,{}).get('name') or prog_key
            if result is True:
                QMessageBox.information(self, "Успішне видалення", f"Видалення успішно завершено для '{prog_name}'.")
            elif result is False:
                QMessageBox.warning(self, "Видалення не вдалося", f"Видалення не вдалося для '{prog_name}'.\nМоже знадобитися ручне видалення. Детальніше див. у журналі")
            elif result is None:
                 QMessageBox.critical(self, "Помилка видалення", f"Під час видалення виникла неочікувана помилка для '{prog_name}'. Перевірьте журнал.")

    def _trigger_tree_update(self):
        if self.pending_updates:
             logger.debug("Timer triggered: Emitting update_tree_signal.")
             self.update_tree_signal.emit()
             self.pending_updates = False

    def _thread_finished(self, thread: WorkerThread):
        logger.debug(f"WorkerThread finished signal received for task '{thread.task_name}'.")
        try:
            if thread in self.active_threads:
                self.active_threads.remove(thread)
            else:
                 logger.warning(f"Finished thread for task '{thread.task_name}' was not found in active list.")
        except Exception as e:
            logger.error(f"Error removing finished thread from active list: {e}", exc_info=True)

        # Update UI state only if *all* threads are now idle
        if not any(t.isRunning() for t in self.active_threads):
            logger.info("All worker threads have finished. Updating UI state to idle.")
            self._update_ui_state()
            self.status_label.setText("Ready.")
        else:
            logger.debug(f"{len([t for t in self.active_threads if t.isRunning()])} threads still running. UI remains busy.")
            self._update_ui_state()


    # --- Settings Persistence ---


    # --- Window Closing ---
def get_module_info():
    return {
        "name": "Program Installer",
        "widget": ProgramInstallerUI
    }

# --- Main Execution ---
if __name__ == "__main__":
    try:
        import ctypes
        myappid = 'ProgramInstaller.2.5'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        logger.debug(f"AppUserModelID set to: {myappid}")
    except Exception as e:
        print(f"Warning: Could not set AppUserModelID: {e}", file=sys.stderr)
        logger.warning(f"Could not set AppUserModelID: {e}")

    app = QApplication(sys.argv)
    styles = QStyleFactory.keys()
    if 'Fusion' in styles:
        app.setStyle(QStyleFactory.create('Fusion'))
        logger.debug("Applied 'Fusion' style.")
    elif 'WindowsVista' in styles:
        app.setStyle(QStyleFactory.create('WindowsVista'))
        logger.debug("Applied 'WindowsVista' style.")
    else:
         logger.debug(f"Default style '{app.style().objectName()}' will be used. Available: {styles}")


    # Create and show the main window
    try:
        window = ProgramInstallerUI()
        window.show()
        logger.info("Application startup successful. Entering main event loop.")
        sys.exit(app.exec_())
    except Exception as e:
         logger.critical(f"Application failed to start: {e}", exc_info=True)
         try:
              msg = QMessageBox()
              msg.setIcon(QMessageBox.Critical)
              msg.setWindowTitle("Fatal Startup Error")
              msg.setText("The application failed to initialize.")
              msg.setInformativeText(f"Error: {e}\n\nPlease check the console output or logs for more details.")
              msg.exec_()
         except Exception as msg_e:
              print(f"FATAL APPLICATION ERROR: {e}\nCannot show error message box: {msg_e}", file=sys.stderr)
         sys.exit(1)