# Petroleum Launcher Package

A modular petroleum program launcher with automation capabilities and multi-monitor support for the Desktop Organizer application.

## 📁 Package Structure

```
petroleum_launcher/
├── __init__.py                     # Package initialization and exports
├── petroleum_launcher_refactored.py # Main entry point and GUI
├── data_models.py                  # Data structures for workflows
├── config_manager.py               # Configuration management
├── windows_utils.py                # Windows-specific utilities
├── window_manager.py               # Multi-monitor support
├── petroleum_launcher.py           # Original monolithic file (backup)
├── README_refactoring.md           # Detailed refactoring documentation
└── README.md                       # This file
```

## 🚀 Quick Start

### Basic Usage

```python
from petroleum_launcher import PetroleumLauncherWidget

# Create the main widget
widget = PetroleumLauncherWidget(parent=None)
widget.show()
```

### Using Individual Components

```python
from petroleum_launcher import PetroleumProgramConfigManager, WindowsUtils

# Configuration management
config_manager = PetroleumProgramConfigManager()
config = config_manager.get_config()

# Windows utilities
utils = WindowsUtils()
executable_path = utils.find_executable_path("petrel")
```

## 📦 Modules Overview

### Core Components

1. **`petroleum_launcher_refactored.py`**
   - Main GUI widget (`PetroleumLauncherWidget`)
   - Module manifest and metadata
   - Dependency checking
   - Entry point for the application

2. **`data_models.py`**
   - All dataclass definitions
   - `ProgramInfo` - Program detection information
   - `Workflow` - Automation workflow structure
   - `AutomationAction` - Individual automation steps
   - Other supporting data models

3. **`config_manager.py`**
   - `PetroleumProgramConfigManager` class
   - JSON configuration file handling
   - Program configuration management
   - Import/export functionality

4. **`windows_utils.py`**
   - `WindowsUtils` class
   - Windows Registry access
   - Executable path detection
   - System integration functions

5. **`window_manager.py`**
   - `WindowManager` class
   - Multi-monitor detection
   - Window positioning logic
   - Display management

## 🔧 Dependencies

### Required Dependencies
- `PyQt5>=5.15.0` - GUI framework
- `pywin32>=227` - Windows API access
- `python>=3.8` - Python runtime

### Optional Dependencies (for enhanced features)
- `PyAutoGUI>=0.9.53` - Screen automation
- `opencv-python>=4.5.0` - Image recognition
- `Pillow>=8.0.0` - Image processing
- `numpy>=1.19.0` - Numerical operations
- `pynput>=1.7.6` - Input recording

## 🎯 Features

- **Multi-Monitor Support**: Automatically detects and manages multiple displays
- **Program Detection**: Finds installed petroleum software
- **Configuration Management**: JSON-based program configuration
- **Windows Integration**: Registry access and system utilities
- **Automation Capabilities**: Workflow recording and playback
- **Extensible Architecture**: Modular design for easy extension

## 📝 Module Manifest

```json
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
```

## 🔄 Migration from Original

The original `petroleum_launcher.py` (14,000+ lines) has been refactored into:
- **5 core modules** (~1,300 lines total)
- **Better maintainability** and code organization
- **Improved reusability** of individual components
- **Easier testing** and debugging

### To migrate:

1. **Backup**: Keep the original file as reference
2. **Replace**: Use the new package structure
3. **Update imports**: Change from direct imports to package imports
4. **Test**: Verify all functionality works as expected

## 🐛 Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all module files are in the same directory
2. **Missing Dependencies**: Install required packages with `pip install -r requirements.txt`
3. **Windows Support**: Some features require Windows OS and pywin32
4. **GUI Issues**: PyQt5 must be properly installed

### Debug Mode

Enable debug logging:

```python
import logging
logging.getLogger('PetroleumLauncher').setLevel(logging.DEBUG)
```

## 🤝 Contributing

When adding new features:

1. **Follow the modular structure** - create new modules for large functionality
2. **Update data models** - add new dataclasses to `data_models.py`
3. **Document changes** - update README files
4. **Test thoroughly** - ensure compatibility with existing code

## 📄 License

This package is part of the Desktop Organizer project. See the main project license for details.

## 📞 Support

For issues and questions:
- Check the troubleshooting section
- Review the refactoring documentation (`README_refactoring.md`)
- Contact the Desktop Organizer development team