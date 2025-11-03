"""Petroleum Program Launcher - Refactored Version

This is the main entry point for the petroleum launcher module.
The original large file has been broken down into smaller, manageable modules.

MODULE_MANIFEST_START
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
import logging
from pathlib import Path

# Set up logging
logger = logging.getLogger('PetroleumLauncher')
logger.setLevel(logging.DEBUG)

# Import all the refactored modules
from .data_models import (
    ProgramInfo, AutomationStep, WorkflowStep, Workflow, ScreenshotRecord,
    AutomationAction, ConditionalAction, WorkflowBranch, PetroleumWorkflowTemplate,
    RecordingSession
)

from .config_manager import PetroleumProgramConfigManager
from .windows_utils import WindowsUtils
from .window_manager import WindowManager

# Import remaining components (these would need to be extracted too)
# For now, we'll create placeholder imports that would be replaced
# when the full refactoring is complete

# Try to import screen recording dependencies
try:
    import pyautogui
    import cv2
    import numpy as np
    SCREEN_RECORDING_SUPPORT = True
except ImportError as e:
    SCREEN_RECORDING_SUPPORT = False
    print(f"Warning: Screen recording dependencies not available: {e}")

# Try to import PIL for image handling
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_SUPPORT = True
except ImportError as e:
    PIL_SUPPORT = False
    print(f"Warning: PIL not available: {e}")

# Enhanced dependency checking system
VISUAL_FEATURES_STATUS = {
    'pyautogui': False,
    'opencv': False,
    'pil': False,
    'numpy': False,
    'psutil': False
}

def check_visual_dependencies():
    """Check availability of visual automation dependencies"""
    global VISUAL_FEATURES_STATUS

    # Check PyAutoGUI
    try:
        import pyautogui
        # Basic safety configuration
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1
        VISUAL_FEATURES_STATUS['pyautogui'] = True
    except ImportError:
        VISUAL_FEATURES_STATUS['pyautogui'] = False

    # Check OpenCV
    try:
        import cv2
        VISUAL_FEATURES_STATUS['opencv'] = True
    except ImportError:
        VISUAL_FEATURES_STATUS['opencv'] = False

    # Check PIL/Pillow
    try:
        from PIL import Image
        VISUAL_FEATURES_STATUS['pil'] = True
    except ImportError:
        VISUAL_FEATURES_STATUS['pil'] = False

    # Check NumPy
    try:
        import numpy as np
        VISUAL_FEATURES_STATUS['numpy'] = True
    except ImportError:
        VISUAL_FEATURES_STATUS['numpy'] = False

    # Check psutil
    try:
        import psutil
        VISUAL_FEATURES_STATUS['psutil'] = True
    except ImportError:
        VISUAL_FEATURES_STATUS['psutil'] = False

# Check dependencies on import
check_visual_dependencies()

# Import GUI components
try:
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
    from PyQt5.QtCore import Qt, pyqtSignal, QTimer
    from PyQt5.QtGui import QPixmap

    # Create a basic version of the main widget
    # In a full refactoring, this would be in main_widget.py

    class PetroleumLauncherWidget(QWidget):
        """Main widget for the Petroleum Program Launcher module"""

        # Signals for thread-safe UI updates
        detection_completed = pyqtSignal()
        detection_status = pyqtSignal(str)
        program_detected = pyqtSignal(str, dict)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.main_window = parent
            self.window_manager = WindowManager()
            self.detected_programs = {}
            self.config_manager = PetroleumProgramConfigManager()
            self.initUI()

            # Auto-detect programs after initialization
            QTimer.singleShot(1000, self.detect_programs)

        def initUI(self):
            """Initialize the user interface"""
            layout = QVBoxLayout(self)

            # Title
            title = QLabel("🛢️ Petroleum Program Launcher")
            title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
            layout.addWidget(title)

            # Status label
            self.status_label = QLabel("Initializing...")
            layout.addWidget(self.status_label)

            # Refresh button
            refresh_btn = QPushButton("🔄 Refresh Programs")
            refresh_btn.clicked.connect(self.detect_programs)
            layout.addWidget(refresh_btn)

            # Programs list
            self.programs_label = QLabel("Detected Programs:")
            layout.addWidget(self.programs_label)

            # Set minimum size
            self.setMinimumSize(400, 300)

        def detect_programs(self):
            """Detect installed petroleum programs"""
            self.status_label.setText("Detecting petroleum programs...")
            config = self.config_manager.get_config()

            if config:
                programs_text = f"Found {len(config)} configured programs:\n"
                for key, program in config.items():
                    name = program.get('display_name', key)
                    programs_text += f"• {name}\n"
                self.programs_label.setText(programs_text)
                self.status_label.setText(f"Detection complete. {len(config)} programs found.")
            else:
                self.programs_label.setText("No programs configured yet.")
                self.status_label.setText("No programs found. Use configuration management to add programs.")

            self.detection_completed.emit()

        def handle_config_action(self, index):
            """Handle configuration dropdown actions"""
            self.status_label.setText("Configuration action selected (placeholder implementation)")

except ImportError as e:
    logger.error(f"PyQt5 not available: {e}")
    # Create a dummy widget for environments without PyQt5
    class PetroleumLauncherWidget:
        def __init__(self, parent=None):
            logger.error("PyQt5 is required for the Petroleum Launcher GUI")
            raise ImportError("PyQt5 is required for the Petroleum Launcher GUI")

# Entry point for module loading
def create_module_widget(parent=None):
    """Create and return the main widget for this module"""
    try:
        return PetroleumLauncherWidget(parent)
    except Exception as e:
        logger.error(f"Error creating petroleum launcher widget: {e}")
        # Return a simple error widget
        try:
            from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
            error_widget = QWidget()
            layout = QVBoxLayout(error_widget)
            error_label = QLabel(f"Error loading Petroleum Launcher:\n{str(e)}")
            error_label.setStyleSheet("color: red; padding: 20px;")
            layout.addWidget(error_label)
            return error_widget
        except ImportError:
            # If even PyQt5 is not available, return None
            return None

# Module metadata
__version__ = "1.0.0"
__author__ = "Desktop Organizer Team"
__description__ = "Petroleum program launcher with automation capabilities and multi-monitor support"

# Export main class
__all__ = ['PetroleumLauncherWidget', 'create_module_widget']