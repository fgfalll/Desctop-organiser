"""Petroleum Launcher Package

A modular petroleum program launcher with automation capabilities and multi-monitor support.
This package has been refactored from a single large file into smaller, maintainable modules.

Main Components:
- data_models: Data structures for workflows and automation
- config_manager: Configuration file management
- windows_utils: Windows-specific utilities
- window_manager: Multi-monitor support and window positioning
- petroleum_launcher_refactored: Main entry point and GUI

Usage:
    from petroleum_launcher import PetroleumLauncherWidget
    widget = PetroleumLauncherWidget(parent)
"""

# Import the main widget for easy access
from .petroleum_launcher_refactored import PetroleumLauncherWidget, create_module_widget

# Import key classes for advanced usage
from .data_models import (
    ProgramInfo, AutomationStep, WorkflowStep, Workflow,
    ScreenshotRecord, AutomationAction, ConditionalAction,
    WorkflowBranch, PetroleumWorkflowTemplate, RecordingSession
)
from .config_manager import PetroleumProgramConfigManager
from .windows_utils import WindowsUtils
from .window_manager import WindowManager

# Package metadata
__version__ = "1.0.0"
__author__ = "Desktop Organizer Team"
__description__ = "Petroleum program launcher with automation capabilities and multi-monitor support"

# Export main symbols
__all__ = [
    'PetroleumLauncherWidget',
    'create_module_widget',
    'PetroleumProgramConfigManager',
    'WindowsUtils',
    'WindowManager',
    'ProgramInfo',
    'AutomationStep',
    'WorkflowStep',
    'Workflow',
    'ScreenshotRecord',
    'AutomationAction',
    'ConditionalAction',
    'WorkflowBranch',
    'PetroleumWorkflowTemplate',
    'RecordingSession'
]