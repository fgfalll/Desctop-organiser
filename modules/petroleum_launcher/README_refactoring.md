# Petroleum Launcher - Refactoring Documentation

## Overview

The original `petroleum_launcher.py` file was over 14,000 lines long, making it difficult to maintain and understand. This refactoring breaks down the large file into smaller, more manageable modules.

## New Module Structure

### Core Modules Created

1. **`data_models.py`** - Contains all dataclass definitions
   - `ProgramInfo`
   - `AutomationStep`
   - `WorkflowStep`
   - `Workflow`
   - `ScreenshotRecord`
   - `AutomationAction`
   - `ConditionalAction`
   - `WorkflowBranch`
   - `PetroleumWorkflowTemplate`
   - `RecordingSession`

2. **`config_manager.py`** - Configuration management
   - `PetroleumProgramConfigManager` class
   - Handles JSON configuration files
   - Manages program settings and detection

3. **`windows_utils.py`** - Windows-specific utilities
   - `WindowsUtils` class
   - Registry access functions
   - Executable path detection
   - Windows OS integration

4. **`window_manager.py`** - Multi-monitor support
   - `WindowManager` class
   - Monitor detection and positioning
   - Window placement logic

5. **`petroleum_launcher_refactored.py`** - Main entry point
   - Module manifest
   - Import statements
   - Basic GUI implementation
   - Dependency checking

### Modules Still to be Created

The following modules need to be extracted from the original file:

1. **`automation_engine.py`** - Workflow execution engine
2. **`automation_recorder.py`** - Input recording functionality
3. **`screen_recorder.py`** - Screen capture and recording
4. **`main_widget.py`** - Main GUI widget implementation
5. **`dialogs.py`** - All dialog classes

## Benefits of Refactoring

1. **Maintainability**: Smaller files are easier to understand and modify
2. **Reusability**: Components can be imported and used independently
3. **Testing**: Individual modules can be unit tested more easily
4. **Collaboration**: Multiple developers can work on different modules simultaneously
5. **Performance**: Only needed modules are loaded into memory

## Usage

To use the refactored version:

1. Replace `petroleum_launcher.py` with `petroleum_launcher_refactored.py`
2. Ensure all module files are in the same directory
3. The new structure maintains the same external API

## Next Steps

1. Complete extraction of remaining large classes
2. Add proper unit tests for each module
3. Update import statements throughout the codebase
4. Add comprehensive documentation for each module
5. Consider creating a package structure with `__init__.py`

## File Sizes Comparison

- **Original**: `petroleum_launcher.py` (~14,000 lines)
- **Refactored**:
  - `data_models.py` (~250 lines)
  - `config_manager.py` (~300 lines)
  - `windows_utils.py` (~350 lines)
  - `window_manager.py` (~180 lines)
  - `petroleum_launcher_refactored.py` (~200 lines)
  - **Total**: ~1,280 lines (main file) + components to be extracted

This represents a significant improvement in code organization and maintainability.