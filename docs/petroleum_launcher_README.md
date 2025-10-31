# Petroleum Program Launcher Module

## Overview

The Petroleum Program Launcher is a comprehensive automation module designed specifically for petroleum industry professionals. It provides intelligent program detection, workflow automation, multi-monitor support, and package distribution capabilities for commonly used petroleum software such as Petrel, PIPESIM, OLGA, Techlog, and Eclipse Reservoir Simulator.

## Features

### 🔍 **Smart Program Detection**
- Automatically detects installed petroleum software using Windows Registry scanning
- Finds executable paths through App Paths registry entries
- Version detection and installation status reporting
- Configurable detection rules for additional software

### 🚀 **Program Launching**
- Direct launching of detected petroleum programs
- Error handling and validation before launch
- Process monitoring and status reporting
- Working directory management

### ⚡ **Automation Workflows**
- Create complex multi-step automation sequences
- Support for program launching, file opening, wait delays, and command execution
- Visual workflow builder with drag-and-drop interface
- Real-time workflow execution with progress tracking

### 🖥️ **Multi-Monitor Support**
- Automatic detection of connected monitors
- Intelligent window positioning across multiple displays
- User-configurable monitor preferences
- Resolution-aware layout adaptation

### 📦 **Package Distribution**
- Export workflows as distributable `.petrolpkg` files
- Import and share automation packages between users
- Version compatibility checking
- Resource bundling for complete workflow distribution

### 🎨 **Responsive UI**
- Auto-scaling interface that adapts to different screen sizes
- DPI-aware font scaling for high-resolution displays
- Proportional layout that maintains balance during resize
- Minimum size constraints for usability

## Installation

The Petroleum Program Launcher module is automatically discovered and loaded by the Desktop Organizer. Place the `petroleum_launcher.py` file in the `modules/` directory of the Desktop Organizer application.

### Dependencies
- **pywin32** >= 227 (for Windows Registry access and monitor detection)
- PyQt5 (included with Desktop Organizer)
- Standard Python libraries (json, os, subprocess, threading, etc.)

## Getting Started

### 1. Program Detection
When the module first loads, it automatically scans for installed petroleum software:

1. Click **"Refresh Programs"** to rescan for software
2. View detected programs in the **Programs** tab
3. Check status: ✅ Installed or ❌ Not Found
4. View version information and executable paths

### 2. Launching Programs
- **Double-click** any detected program to launch it
- Select a program and click **"Launch Selected"**
- Monitor launch status in the status bar

### 3. Creating Workflows
1. Click **"New Workflow"** in the Workflows tab
2. Configure workflow information:
   - **Name**: Descriptive workflow title
   - **Description**: What the workflow does
   - **Author**: Your name/organization
3. Add automation steps:
   - **Launch Program**: Start a petroleum application
   - **Open File**: Open project files with default applications
   - **Wait**: Add delays between steps
   - **Run Command**: Execute system commands
4. Configure window positioning for each step
5. Save the workflow

### 4. Running Workflows
- Select a workflow from the list
- Click **"Run Workflow"** to execute
- Monitor progress in the progress panel
- Use **"Stop Automation"** to cancel execution

## Supported Software

The module automatically detects the following petroleum industry software:

### Schlumberger Software
- **Petrel Platform** - E&P software platform
- **PIPESIM** - Multiphase flow simulation
- **OLGA** - Multiphase flow simulator
- **Techlog** - Wellbore software platform
- **Eclipse Reservoir Simulator** - Reservoir simulation

### Adding New Software
To add support for additional petroleum software:

1. Edit the `PETROLEUM_PROGRAM_CONFIG` dictionary in the module
2. Add detection rules similar to existing programs:
```python
"new_program": {
    "display_name": "New Software Name",
    "check_method": {
        "type": "registry",
        "keys": [
            {"path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
             "match_value": "DisplayName",
             "match_pattern": r"New Software.*",
             "get_value": "DisplayVersion"}
        ]
    }
}
```

## Workflow Automation

### Step Types

#### 1. Launch Program
- **Purpose**: Start a petroleum application
- **Configuration**:
  - Select from detected programs
  - Set window position (optional)
  - Add command-line parameters

#### 2. Open File
- **Purpose**: Open project or data files
- **Configuration**:
  - File path selection with browser
  - Automatic file association

#### 3. Wait
- **Purpose**: Add delays between automation steps
- **Configuration**:
  - Duration in seconds (1-3600)
  - Useful for program loading times

#### 4. Run Command
- **Purpose**: Execute system commands or scripts
- **Configuration**:
  - Command string
  - Timeout settings
  - Working directory

### Window Positioning
Each step can configure window positioning:
- **Left/Top**: Screen coordinates
- **Width/Height**: Window dimensions
- **Use Position**: Enable/disable positioning

### Example Workflow
```yaml
Name: "Morning Setup"
Description: "Launch daily petroleum applications"
Steps:
  1. Launch Petrel Platform
  2. Wait 10 seconds (for loading)
  3. Open project file: "C:\Projects\Daily\morning.petrel"
  4. Launch PIPESIM
  5. Wait 8 seconds
  6. Open data file: "C:\Data\pipeline.pipesim"
```

## Package Distribution

### Exporting Workflows
1. Select a workflow from the list
2. Click **"Export Package"**
3. Choose save location and filename
4. Package saved as `.petrolpkg` file

### Importing Packages
1. Click **"Import Package"** in the Workflows tab
2. Select a `.petrolpkg` file
3. Review imported workflow details
4. Workflow added to your collection

### Package Contents
- **workflow.json**: Automation configuration
- **metadata.json**: Package information and version
- **files/**: Referenced project files and resources

## Multi-Monitor Configuration

### Automatic Detection
The module automatically detects:
- Number of connected monitors
- Screen resolutions and positions
- Primary/secondary monitor identification
- Work area (excluding taskbars)

### Settings
- **Default Monitor**: Choose primary or secondary for program launches
- **Remember Positions**: Store window positions per program
- **Click "Save Settings"** to persist configuration

### Positioning Options
- **Primary Monitor**: Main display for most applications
- **Secondary Monitor**: Additional display for supporting tools
- **Custom Positioning**: Per-step configuration in workflows

## Configuration and Settings

### Settings Storage
- **Primary**: Integrated with Desktop Organizer settings
- **Fallback**: Local file at `~/.desktop_organizer/petroleum_launcher_config.json`

### UI Settings
- Default monitor selection
- Window position memory
- Column widths and layout preferences

### Workflow Storage
- Automation sequences with steps and configurations
- Creation and modification timestamps
- Author and version information

## Troubleshooting

### Common Issues

#### Programs Not Detected
1. Click **"Refresh Programs"** to rescan
2. Verify software is properly installed
3. Check Windows Registry entries
4. Ensure pywin32 is installed correctly

#### Launch Failures
1. Verify executable paths are correct
2. Check program executable exists
3. Ensure sufficient permissions
4. Review error messages in status bar

#### Workflow Issues
1. Validate step configurations
2. Check file paths exist
3. Verify program names match detected software
4. Test workflow steps individually

#### Display Scaling
1. Module automatically adapts to screen DPI
2. Minimum size enforced (800x600)
3. Restart Desktop Organizer if scaling issues persist

### Logging
The module provides detailed logging through:
- Python logging system
- Status bar messages
- Error dialog boxes
- Console output (when running standalone)

### Performance Tips
- Use **reasonable wait times** in workflows (5-30 seconds typical)
- **Limit concurrent workflows** to avoid resource conflicts
- **Save workflows regularly** to prevent data loss
- **Close unused programs** before running complex workflows

## Advanced Usage

### Custom Automation Scripts
For complex automation, integrate external scripts:

```python
# In workflow "Run Command" step:
python "C:\Scripts\data_processor.py" --input "project.dat" --output "results.json"
```

### Integration with Other Tools
- Export workflow data as JSON for external processing
- Use command-line tools within workflow steps
- Integrate with version control for workflow management

### Batch Operations
Create workflows for:
- **Project Setup**: Launch multiple programs with specific files
- **Data Processing**: Run analysis sequences automatically
- **Report Generation**: Compile outputs from various tools
- **Backup Operations**: Save project data to specified locations

## Support and Development

### Module Information
- **File**: `petroleum_launcher.py`
- **Version**: 1.0.0
- **Category**: Utility
- **Author**: Desktop Organizer Team

### Dependencies
- Windows OS (for Registry access)
- pywin32 library
- PyQt5 framework
- Standard Python libraries

### Extending the Module
To add new features or program support:
1. Edit the `PETROLEUM_PROGRAM_CONFIG` dictionary
2. Add new step types to the `AutomationStep` class
3. Implement additional detection methods in `WindowsUtils`
4. Extend the workflow builder UI as needed

## License

This module is part of the Desktop Organizer application and follows the same licensing terms as the main application.

---

**For questions, bug reports, or feature requests**, please refer to the Desktop Organizer documentation or contact the development team.