# Desktop Organizer

A desktop organization application with modular architecture for automatic file management, license monitoring, and program installation.

## Overview

Desktop Organizer provides automated file organization with support for scheduled operations, custom filtering rules, and module-based extensibility. The application uses a single-file architecture with dynamic module loading and shared virtual environment management.

## Features

- **Automated File Organization**: Schedule and automate file cleanup with customizable rules
- **Flexible Configuration**: Configure target drives, file filters, size limits, and scheduling
- **Module System**: Extensible architecture with dynamic module loading
- **Virtual Environment Management**: Shared environment for module dependencies with automatic cleanup
- **License Management**: Track and validate software licenses
- **Program Installation**: Automated software deployment tools

## Architecture

### System Architecture Overview

```mermaid
graph TB
    subgraph "Desktop Organizer Application"
        A[Main Application<br/>Desctop organiser.py] --> B[Core UI Engine]
        A --> C[Configuration Manager]
        A --> D[Scheduler Engine]
        A --> E[Module Manager]

        B --> F[Settings Dialog]
        B --> G[Main Window Interface]
        B --> H[Splash Screen]

        C --> I[YAML Config Files]
        C --> J[Schedule Tracking]

        D --> K[Timer Management]
        D --> L[Windows Task Scheduler]
        D --> M[Idle Detection]

        E --> N[Module Discovery]
        E --> O[Dynamic Loading]
        E --> P[Virtual Environment Manager]
    end

    subgraph "Module System"
        Q[Embedded Manifests] --> R[Module Registry]
        N --> R
        R --> S[License Manager Module]
        R --> T[License Test Module]
        R --> U[Program Installer Module]
        R --> V[Example Module]

        P --> W[Shared Virtual Environment]
        W --> X[Package Installation]
        W --> Y[Dependency Resolution]
        W --> Z[Package Cleanup]
    end

    subgraph "External Systems"
        AA[Windows File System]
        BB[Windows Task Scheduler]
        CC[Package Repositories]
        DD[System Resources]
    end

    G --> AA
    L --> BB
    X --> CC
    A --> DD
```

### Core Application (`v4.2.py`)
- Single-file application containing all core functionality
- Main window with tabbed interface for modules
- Configuration management with YAML files
- Scheduled task execution with idle detection

### Module System
- **Embedded Manifests**: Module metadata embedded in Python files
- **Dynamic Loading**: Modules discovered and loaded automatically
- **Shared Virtual Environment**: Isolated dependency management
- **Automatic Cleanup**: Package removal when modules are unloaded

### Available Modules
- `license_manager.py`: License validation and management
- `license_test.py`: License status monitoring
- `program_install.py`: Software installation automation
- `example_module.py`: Reference implementation

### Application Startup Flow

```mermaid
sequenceDiagram
    participant User
    participant MainApp as Main Application
    participant ConfigMgr as Configuration Manager
    participant ModuleMgr as Module Manager
    participant VenvMgr as Virtual Environment Manager
    participant UI as User Interface

    User->>MainApp: Launch Application
    MainApp->>MainApp: Initialize Core Components
    MainApp->>ConfigMgr: Load Configuration
    ConfigMgr-->>MainApp: Configuration Loaded

    MainApp->>ModuleMgr: Discover Modules
    ModuleMgr->>ModuleMgr: Scan modules/ Directory
    ModuleMgr->>ModuleMgr: Parse Embedded Manifests
    ModuleMgr-->>MainApp: Module Registry Created

    MainApp->>VenvMgr: Initialize Virtual Environment
    VenvMgr->>VenvMgr: Check/create shared venv
    VenvMgr->>VenvMgr: Load package tracking
    VenvMgr-->>MainApp: Environment Ready

    MainApp->>UI: Create Main Window
    UI->>UI: Initialize Splash Screen
    UI->>UI: Load Module Menu Items
    UI->>UI: Apply Settings
    UI-->>User: Application Ready
```

### Module Loading Process

```mermaid
flowchart TD
    A[Module Discovery Start] --> B[Scan modules/ Directory]
    B --> C{Found Python Files?}
    C -->|No| D[Module Discovery Complete]
    C -->|Yes| E[Extract Embedded Manifest]
    E --> F{Valid Manifest?}
    F -->|No| G[Skip Module - Log Error]
    G --> B
    F -->|Yes| H[Parse Manifest Data]
    H --> I{Dependencies Required?}
    I -->|No| J[Register Module]
    I -->|Yes| K[Check Virtual Environment]
    K --> L{Dependencies Satisfied?}
    L -->|No| M[Install Missing Packages]
    M --> N{Installation Success?}
    N -->|No| O[Mark Module as Failed]
    N -->|Yes| J
    L -->|Yes| J
    J --> P{More Files to Process?}
    P -->|Yes| B
    P -->|No| D
```

### Virtual Environment Management

```mermaid
graph LR
    subgraph "Package Management Flow"
        A[Module Request] --> B[Dependency Analysis]
        B --> C{Packages Available?}
        C -->|No| D[Install from Repository]
        C -->|Yes| E[Version Check]
        E --> F{Version Compatible?}
        F -->|No| G[Upgrade Package]
        F -->|Yes| H[Load Module]
        D --> I{Installation Success?}
        I -->|No| J[Mark Module Failed]
        I -->|Yes| H
        G --> H
        H --> K[Track Package Usage]
    end

    subgraph "Environment Components"
        L[modules_venv/]
        M[Package Registry]
        N[Usage Tracking]
        O[Dependency Graph]
    end

    K --> M
    K --> N
    M --> O
    L --> M
```

### File Organization Workflow

```mermaid
stateDiagram-v2
    [*] --> Idle: Application Start
    Idle --> Configuring: User Opens Settings
    Configuring --> Idle: Settings Applied
    Idle --> Monitoring: Timer Started

    Monitoring --> Processing: Timer Triggered
    Processing --> Scanning: Start File Scan
    Scanning --> Filtering: Apply Filter Rules
    Filtering --> Organizing: Files Match
    Filtering --> Processing: No Files Match
    Organizing --> Moving: Move Files
    Moving --> Processing: Complete
    Processing --> Monitoring: Reset Timer

    Monitoring --> Idle: Timer Stopped
    Monitoring --> Paused: System Activity
    Paused --> Monitoring: System Idle

    state Processing {
        [*] --> ScanDirectory
        ScanDirectory --> CheckFilters
        CheckFilters --> MoveFile: Match Found
        CheckFilters --> Complete: No Match
        MoveFile --> UpdateRegistry
        UpdateRegistry --> Complete
        Complete --> [*]
    }
```

## Installation

### System Requirements
- Python 3.8 or higher
- Windows (recommended for full functionality)
- Administrative privileges for some operations

### Dependencies

Install core dependencies:
```bash
pip install -r requirements.txt
```

### Setup

1. Download or clone the repository
2. Install dependencies from `requirements.txt`
3. Run the application:
   ```bash
   python v4.2.py
   ```

## Usage

### Application Workflow

```mermaid
journey
    title User Interaction Journey
    section First Launch
      Launch Application: 5: User
      Configure Settings: 4: User
      Test File Organization: 4: User
      Enable Scheduler: 3: User
    section Daily Use
      Start Application: 5: User
      Monitor Organization: 3: User
      Access Modules: 4: User
      Review Settings: 2: User
    section Maintenance
      Check Virtual Environment: 3: User
      Update Configuration: 3: User
      Monitor Logs: 2: User
```

### Main Application
1. **File Organization**:
   - Select target drive (D:, E:, or auto-detect)
   - Configure timer duration
   - Set file filters (extensions, names, size limits)
   - Start automatic or manual cleanup

2. **Settings**:
   - Configure application behavior
   - Set up scheduled operations
   - Manage file filtering rules
   - Control virtual environment settings

3. **Modules**:
   - Access additional functionality through Modules menu
   - Modules load automatically with embedded manifests

### Settings Management Flow

```mermaid
flowchart TD
    A[User Opens Settings] --> B[Load Current Configuration]
    B --> C[Display Settings Dialog]
    C --> D{User Selects Tab?}
    D -->|General| E[Show General Settings]
    D -->|File Filters| F[Show Filter Configuration]
    D -->|Schedule| G[Show Scheduler Settings]
    D -->|Virtual Environment| H[Show Venv Management]

    E --> I[Modify Application Behavior]
    F --> J[Configure File Filtering Rules]
    G --> K[Set Up Scheduling]
    H --> L[Manage Packages]

    I --> M[Apply Changes]
    J --> M
    K --> M
    L --> M

    M --> N{Validation Passed?}
    N -->|No| O[Show Error Message]
    N -->|Yes| P[Save Configuration]
    O --> C
    P --> Q[Update Running Application]
    Q --> R[Close Settings]
```

### Configuration

Configuration stored in:
- `~/.DesktopOrganizer/config.yaml`: Application settings
- `~/.DesktopOrganizer/last_run.txt`: Schedule tracking
- `~/.DesktopOrganizer/module_packages.json`: Package usage tracking
- `~/.DesktopOrganizer/modules_venv/`: Shared virtual environment

### Virtual Environment Management

Access through Settings → "Віртуальне Середовище":
- View installed packages
- Monitor package usage by modules
- Clean/reset virtual environment
- Automatic dependency installation/uninstallation

### Package Management Interface

```mermaid
graph TB
    subgraph "Virtual Environment Interface"
        A[Package List View] --> B[Package Details]
        A --> C[Usage Statistics]
        A --> D[Control Actions]

        B --> E[Version Information]
        B --> F[Size Information]
        B --> G[Module Dependencies]

        C --> H[Usage by Modules]
        C --> I[Installation History]

        D --> J[Install New Package]
        D --> K[Upgrade Package]
        D --> L[Uninstall Package]
        D --> M[Repair Environment]

        J --> N[Package Input Dialog]
        K --> O[Version Selection]
        L --> P[Confirmation Dialog]
        M --> Q[Repair Options]

        N --> R[Installation Process]
        O --> R
        P --> S[Uninstallation Process]
        Q --> T[Repair Process]

        R --> U[Update Package Registry]
        S --> U
        T --> U
    end
```

## Module Development

### Module Development Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Planning: Define Requirements
    Planning --> Development: Create Python File
    Development --> Manifest: Add Embedded Manifest
    Manifest --> Implementation: Implement Main Class
    Implementation --> Testing: Load and Test Module
    Testing --> Validation: Check Dependencies
    Validation --> Deployment: Deploy to modules/
    Deployment --> Monitoring: Monitor Usage
    Monitoring --> Maintenance: Updates Required
    Maintenance --> Development: Code Changes
    Maintenance --> [*]: End of Life

    state Implementation {
        [*] --> CreateClass
        CreateClass --> SetupUI
        SetupUI --> AddFeatures
        AddFeatures --> ErrorHandling
        ErrorHandling --> [*]
    }

    state Testing {
        [*] --> LoadTest
        LoadTest --> FunctionalityTest
        FunctionalityTest --> DependencyTest
        DependencyTest --> UITest
        UITest --> [*]
    }
```

### Creating Modules

1. Create Python file in `modules/` directory
2. Add embedded manifest at top of file:
   ```python
   """MODULE_MANIFEST_START
   {
     "name": "module_name",
     "version": "1.0.0",
     "description": "Module description",
     "menu_text": "&Menu Text...",
     "main_class": "MainClassName",
     "dependencies": ["package>=version"],
     "dependency_packages": {
       "import_name": "pip_package>=version"
     },
     "python_version": "3.8+"
   }
   MODULE_MANIFEST_END"""
   ```

3. Implement main class:
   ```python
   class MainClassName(QWidget):
       def __init__(self, parent=None):
           super().__init__(parent)
           self.setFixedSize(991, 701)
           self.initUI()
   ```

### Module Architecture Pattern

```mermaid
classDiagram
    class BaseModule {
        +QWidget parent
        +str module_name
        +dict config
        +__init__(parent)
        +initUI()
        +loadConfiguration()
        +saveConfiguration()
        +showNotification(message)
        +logError(error)
        +cleanup()
    }

    class MainClassName {
        +QVBoxLayout layout
        +QMenuBar menu_bar
        +QStatusBar status_bar
        +QWidget central_widget
        +__init__(parent)
        +initUI()
        +setupMenu()
        +setupStatusBar()
        +setupCentralWidget()
        +connectSignals()
        +handleEvent(event)
    }

    class ModuleInterface {
        <<interface>>
        +initialize()
        +execute()
        +configure()
        +getStatus()
        +cleanup()
    }

    BaseModule <|-- MainClassName
    ModuleInterface <|.. MainClassName

    note for MainClassName "Fixed size: 991x701\nPyQt5 QWidget based\nEmbedded manifest required"
```

### Module Guidelines

- Window size must be 991x701 pixels
- Include proper error handling
- Use embedded manifests (no separate JSON files)
- List all dependencies in manifest
- Follow PyQt5 best practices

### Module Integration Flow

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant File as Module File
    participant App as Application
    participant Loader as Module Loader
    participant Venv as Virtual Environment
    participant UI as User Interface

    Dev->>File: Create Module Code
    File->>File: Add Embedded Manifest
    Dev->>App: Place in modules/ directory

    App->>Loader: Discover New Module
    Loader->>File: Parse Manifest
    File-->>Loader: Module Metadata
    Loader->>Venv: Check Dependencies
    Venv-->>Loader: Dependency Status

    alt Dependencies Missing
        Loader->>Venv: Install Packages
        Venv-->>Loader: Installation Complete
    end

    Loader->>File: Load Module Class
    File-->>Loader: Module Instance
    Loader-->>App: Module Registered

    App->>UI: Add Menu Item
    UI-->>Dev: Module Available
```

## File Structure

```mermaid
graph TD
    subgraph "Desktop Organizer Root"
        A[Desctop organiser.py<br/>Main Application] --> B[requirements.txt<br/>Dependencies]
        A --> C[UPDATE.md<br/>Latest Updates]
        A --> D[README.md<br/>Documentation]

        B --> E[modules/ Directory]
        A --> F[.DesktopOrganizer/ Config]
    end

    subgraph "Modules Directory"
        E --> G[license_manager.py<br/>License Management]
        E --> H[license_test.py<br/>License Testing]
        E --> I[program_install.py<br/>Program Installation]
        E --> J[example_module.py<br/>Reference Implementation]
    end

    subgraph "Configuration Directory"
        F --> P[config.yaml<br/>Application Settings]
        F --> Q[last_run.txt<br/>Schedule Tracking]
        F --> R[module_packages.json<br/>Package Usage]
        F --> S[modules_venv/ Virtual Environment]
    end

    subgraph "Virtual Environment"
        S --> T[lib/python/site-packages/<br/>Installed Packages]
        S --> U[Scripts/ Python Executables]
        S --> V[pip.conf Configuration]
    end

    G --> R
    H --> R
    I --> R
    J --> R
    R --> T
```

### Detailed Directory Structure

```
Desktop Organizer/
├── Desctop organiser.py              # Main application
├── requirements.txt                  # Core dependencies
├── UPDATE.md                         # Version updates
├── README.md                         # Documentation
├── modules/                         # Module directory
│   ├── license_manager.py           # License management
│   ├── license_test.py              # License checking
│   ├── program_install.py           # Program installation
│   └── example_module.py            # Example module
├── .DesktopOrganizer/               # Configuration directory
│   ├── config.yaml                  # Application settings
│   ├── last_run.txt                 # Schedule tracking
│   ├── module_packages.json         # Package usage tracking
│   └── modules_venv/                # Shared virtual environment
│       ├── lib/python3.x/site-packages/
│       ├── Scripts/
│       └── pyvenv.cfg
└── docs/                           # Documentation
    ├── UPDATE.md
    └── README.md
```

## Troubleshooting

### Troubleshooting Decision Tree

```mermaid
flowchart TD
    A[Application Issue] --> B{Module Related?}
    B -->|Yes| C[Module Troubleshooting]
    B -->|No| D[Application Troubleshooting]

    C --> E{Manifest Valid?}
    E -->|No| F[Check Manifest Format]
    E -->|Yes| G{Dependencies OK?}
    G -->|No| H[Check Virtual Environment]
    G -->|Yes| I{Class Name Correct?}
    I -->|No| J[Update Manifest]
    I -->|Yes| K[Check File Permissions]

    D --> L{Configuration Loads?}
    L -->|No| M[Check Config Directory]
    L -->|Yes| N{Virtual Environment OK?}
    N -->|No| O[Recreate Environment]
    N -->|Yes| P{Scheduler Working?}
    P -->|No| Q[Check Windows Scheduler]
    P -->|Yes| R[Check File Permissions]

    F --> S[Fixed]
    H --> T[Fixed]
    J --> S
    K --> S
    M --> S
    O --> S
    Q --> S
    R --> S
```

### Common Issues and Solutions

```mermaid
mindmap
  root((Troubleshooting))
    Module Issues
      ❌ Manifest Format Errors
        ✅ Check JSON syntax
        ✅ Verify required fields
        ✅ Validate markers
      ❌ Class Not Found
        ✅ Check class name in manifest
        ✅ Verify implementation exists
        ✅ Review import statements
      ❌ Dependency Problems
        ✅ Check network connection
        ✅ Verify package names
        ✅ Review version requirements
    Virtual Environment
      ❌ Creation Failed
        ✅ Check Python venv module
        ✅ Verify write permissions
        ✅ Check disk space
      ❌ Package Installation Failed
        ✅ Check pip availability
        ✅ Verify repository access
        ✅ Review dependency conflicts
      ❌ Environment Corruption
        ✅ Reset virtual environment
        ✅ Clear package cache
        ✅ Reinstall dependencies
    Application Errors
      ❌ Configuration Loading
        ✅ Check config directory permissions
        ✅ Verify YAML syntax
        ✅ Review default settings
      ❌ Scheduler Issues
        ✅ Check admin privileges
        ✅ Verify Windows Scheduler service
        ✅ Review task configuration
      ❌ File Organization Problems
        ✅ Check target drive permissions
        ✅ Verify filter rules
        ✅ Review timer settings
```

### Debugging Process

```mermaid
sequenceDiagram
    participant User as User
    participant App as Application
    participant Log as Log System
    participant Config as Configuration
    participant Venv as Virtual Environment

    User->>App: Report Issue
    App->>Log: Generate Debug Information
    Log-->>App: Error Details

    App->>Config: Check Configuration Validity
    Config-->>App: Configuration Status

    App->>Venv: Verify Environment Health
    Venv-->>App: Environment Status

    App->>App: Analyze Problem
    App-->>User: Provide Solution Steps

    User->>App: Apply Fix
    App->>Log: Log Resolution
    Log-->>App: Confirmation
    App-->>User: Issue Resolved
```

### Module Issues
- Verify embedded manifest format
- Check that Python files are in `modules/` directory
- Ensure main class matches manifest
- Review application log for detailed errors

### Virtual Environment Issues
- Check Python venv module availability
- Verify write permissions in modules directory
- Use Settings → Virtual Environment to diagnose
- Reset environment if package conflicts occur

### Dependency Issues
- Modules auto-install dependencies in shared environment
- Check Settings → Virtual Environment for package status
- Network connectivity required for automatic installation
- Manual installation possible in modules_venv/

## Technical Specifications

### System Architecture

```mermaid
C4Context
    title System Context
    Person(user, "End User", "Uses the desktop organizer")
    System(desktop_organizer, "Desktop Organizer", "File organization and module management")
    System_Ext(windows_scheduler, "Windows Task Scheduler", "System scheduling service")
    System_Ext(file_system, "Windows File System", "File storage and management")
    System_Ext(package_repo, "PyPI Repository", "Python package repository")

    Rel(user, desktop_organizer, "Configures and uses")
    Rel(desktop_organizer, windows_scheduler, "Creates scheduled tasks")
    Rel(desktop_organizer, file_system, "Organizes files")
    Rel(desktop_organizer, package_repo, "Downloads dependencies")
```

### Technology Stack

```mermaid
graph TB
    subgraph "Application Layer"
        A[Desktop Organizer Application]
        B[Module System]
        C[Configuration Manager]
    end

    subgraph "Python Framework"
        D[Python 3.8+]
        E[PyQt5 GUI Framework]
        F[YAML Configuration]
        G[psutil System Info]
    end

    subgraph "Package Management"
        H[pip Package Manager]
        I[virtual Environment]
        J[Dynamic importlib]
    end

    subgraph "Windows Integration"
        K[Windows Task Scheduler]
        L[Windows File System API]
        M[System Registry]
    end

    A --> D
    A --> E
    B --> J
    C --> F
    A --> G
    B --> H
    B --> I
    A --> K
    A --> L
    C --> M
```

### Performance Requirements

```mermaid
gantt
    title Performance Benchmarks
    dateFormat X
    axisFormat %s

    section Startup Time
    Application Launch   :active, launch, 0, 3s
    Module Discovery    :active, discovery, 0, 2s
    Environment Check   :active, envcheck, 2s, 4s
    UI Ready           :active, ui, 3s, 5s

    section Module Operations
    Module Load        :active, modload, 0, 1s
    Dependency Install :active, depinstall, 0, 30s
    Module Execution   :active, modexec, 0, 0.5s

    section File Operations
    Scan Directory     :active, scan, 0, 5s
    Filter Processing  :active, filter, 0, 2s
    File Organization  :active, org, 0, 10s
```

### Resource Usage

```mermaid
pie title Resource Allocation
    "Core Application" : 35
    "Module System" : 25
    "Virtual Environment" : 20
    "File Operations" : 15
    "Configuration" : 5
```

- **Language**: Python 3.8+
- **GUI Framework**: PyQt5
- **Configuration**: YAML
- **System Information**: psutil
- **Module Loading**: Dynamic importlib-based system
- **Package Management**: pip in shared virtual environment
- **Scheduling**: Windows Task Scheduler integration
- **System Requirements**: Windows 7/8/10/11, 100MB disk space, 4GB RAM recommended

## License

Copyright © 2024

See LICENSE.md for license information.

## Support

For technical support:
- Review troubleshooting section
- Check module development documentation
- Examine application logs for error details
- Report issues with system specifications and error messages