# Automated Windows Software Installer

## Overview

The Automated Windows Software Installer is a Python-based utility designed to streamline the discovery, installation, and management of software programs on Windows systems, with a particular focus on engineering applications. It features a PyQt5 graphical user interface (GUI) for ease of use and leverages configuration files to identify specific installers, check prerequisites or existing installations via the Windows Registry, and execute installations using silent or semi-silent command-line switches. The tool also logs successful installations to facilitate automated uninstallation.

This tool is primarily aimed at IT administrators, power users, or engineering teams needing to manage the deployment of specific software suites across multiple machines or ensure consistent setups.

## Key Features

*   **Graphical User Interface:** Intuitive and responsive UI built with PyQt5.
*   **Configurable Software Definitions:** Define known software titles, their identifying characteristics (metadata, filename patterns), registry check methods, and silent installation commands via a central Python configuration (`PROGRAM_CONFIG`).
*   **Automated Installer Discovery:** Recursively scans specified directories for `.exe` and `.msi` files, applying configurable filters to exclude irrelevant files (e.g., dependencies, uninstallers, small files).
*   **Intelligent Identification:**
    *   Matches installers against `PROGRAM_CONFIG` using file metadata (Product Name, Description, Version extracted via `pywin32` and `msilib`) and filename patterns.
    *   Includes heuristic analysis to identify potential installers not explicitly configured, based on properties and naming conventions.
*   **Installation Status Verification:** Queries the Windows Registry (primarily `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` and corresponding `HKCU` keys) based on configured rules to detect if software is already installed and retrieve its version.
*   **Flexible Installation Modes:**
    *   **Auto (Silent):** Attempts unattended installation using pre-defined silent switches.
    *   **Semi-Silent:** Executes installation with minimal user interface (e.g., progress only) using passive switches.
    *   **Manual (Interactive):** Launches the standard installer GUI for user interaction.
*   **Installation Logging:** Records details of installations performed *by this tool* (program identifier, name, timestamp, installer path, discovered uninstall command/ProductCode, version) to a persistent JSON log file (`%APPDATA%\ProgramInstallerApp\program_installer_log.json`).
*   **Automated Uninstallation:** Leverages the installation log to attempt silent uninstallation of previously installed programs, using either the logged `UninstallString` or MSI ProductCode.
*   **UI Enhancements:** Includes filtering, sorting, status color-coding, progress indicators, and detailed information display.
*   **State Persistence:** Remembers the last used scan path and window geometry.
*   **Dependency Management:** Checks for required Python libraries (`PyQt5`, `pywin32`) on startup.
*   **Background Processing:** Utilizes `QThread` for non-blocking scanning, status checking, and installation/uninstallation operations, maintaining GUI responsiveness.

## Prerequisites

*   **Operating System:** Windows (Developed and tested on Windows 10/11). Requires access to Windows APIs and the Registry.
*   **Python:** Python 3.7 or newer.
*   **Python Packages:**
    *   `PyQt5`: For the graphical user interface.
    *   `pywin32`: For accessing native Windows APIs (file metadata, registry access, MSI properties, process management).

## Installation (Dependencies)

Ensure Python 3.7+ is installed and accessible from your command line or environment. Install the required Python packages using pip:

```bash
pip install PyQt5 pywin32
```

It is recommended to use a Python virtual environment to manage dependencies.

## Configuration

**Crucially, this tool requires configuration to recognize and manage your specific software.**

1.  **`PROGRAM_CONFIG` Dictionary (Mandatory Customization):**
    *   Located within the `install_programs.py` script.
    *   This dictionary is the core of the tool's knowledge base. Each key represents a unique software identifier (e.g., `"autocad_2024"`).
    *   The associated value is a dictionary defining:
        *   `display_name`: User-friendly name shown in the GUI.
        *   `target_version`: (Optional, currently informational) e.g., "2024.1" or "latest".
        *   `identity`: Criteria for identifying the installer file:
            *   `expected_product_names`: List of potential "ProductName" metadata values.
            *   `expected_descriptions`: List of potential "FileDescription" metadata values.
            *   `installer_patterns`: List of `fnmatch`-style filename patterns (e.g., `ACAD_2024*.exe`).
        *   `check_method`: Rules for checking if the program is installed via the registry:
            *   `type`: Currently only `"registry"` is supported.
            *   `keys`: A list of registry check rules (dictionaries) specifying `path`, `hive` (`HKLM`/`HKCU`), `match_value`, `match_pattern` (regex), `get_value` (e.g., `DisplayVersion`), or `check_existence`.
        *   `install_commands`: Command-line templates for different installation modes:
            *   Keys: `.exe` or `.msi`.
            *   Values: Command strings using `{installer_path}` (will be quoted) and appropriate silent (`/S`, `/qn`, `/quiet`), passive (`/passive`), or other switches. **Finding the correct switches often requires vendor documentation or experimentation (e.g., running `installer.exe /?`).**

    *   **Action Required:** You *must* populate `PROGRAM_CONFIG` with accurate details corresponding to the specific software installers you intend to manage. The example entries are illustrative placeholders.

2.  **`DETECTION_SETTINGS` Dictionary (Optional Tuning):**
    *   Located within the `install_programs.py` script.
    *   Fine-tunes the initial scanning and heuristic detection process:
        *   `exclude_generic_names`: Filters out common dependency names (e.g., 'driver', 'redist').
        *   `exclude_by_property_substrings`: Filters based on substrings in file metadata (e.g., '.net framework', 'visual c++').
        *   `exclude_uninstaller_hints`: Filters files likely to be uninstallers (e.g., 'uninstall', 'remove').
        *   `min_file_size_bytes`: Ignores files smaller than this threshold.
        *   `ignore_dirs`: Skips specified directory names during scanning (e.g., 'backup', 'docs', 'temp').

## Usage Guide

1.  **Configure:** Edit the `PROGRAM_CONFIG` and optionally `DETECTION_SETTINGS` dictionaries in the script as described above.
2.  **Launch:** Run the script from your terminal. **Note:** Installation and uninstallation typically require administrator privileges. Consider running the script as an administrator ("Run as administrator").
    ```bash
    python install_programs.py
    ```
3.  **Set Scan Path:** Click the "Set Scan Path..." button (folder icon) in the toolbar. Browse to and select the root directory containing your software installers. The scan will be recursive, respecting `ignore_dirs`.
4.  **Scan for Installers:** Click the "Scan" button (magnifying glass icon). The application will search the specified path, identify installers based on configuration and heuristics, and populate the main list.
5.  **Check Installation Status:** Click the "Check Status" button (checklist icon). The tool will query the Windows Registry for each configured program to determine its installation status and version.
6.  **Review Results:**
    *   The central table displays identified programs, their status (Installed, Version, Installer Found), and the path to the detected installer.
    *   Color-coding indicates status: Green (Installed), Blue (Installer Found, Not Installed), Yellow (Heuristic Match), White/Gray (Configured, No Installer Found/Not Installed).
    *   Select an item to view detailed file properties and configuration data in the bottom panel.
    *   Use the "Filter" text box to dynamically search the list. Click column headers to sort.
7.  **Perform Actions:**
    *   Select one or more program entries in the list.
    *   Choose the desired installation mode ("Auto", "Semi-Silent", "Manual") from the dropdown menu.
    *   Click "Install Selected": Initiates installation for selected programs that have an installer found and are not currently marked as installed. Requires administrator privileges for most software.
    *   Click "Uninstall Selected": Attempts silent uninstallation for selected *configured* programs that were previously installed *by this tool* (and thus logged). This relies on the logged uninstall information. Uninstallation of heuristic items is not supported.
8.  **Monitor Progress:** Observe the status bar at the bottom for real-time updates on current operations (scanning, checking, installing). Check the console output or the application's log file (`%APPDATA%\ProgramInstallerApp\program_installer.log`) for detailed messages and potential errors.

## How It Works (Technical Summary)

*   **Scanning:** `os.walk` iterates through the target directory structure, filtering based on `DETECTION_SETTINGS` and file extensions (`.exe`, `.msi`).
*   **Identification:**
    *   Metadata Extraction: Uses `win32api.GetFileVersionInfo` (EXE) and `msilib` (MSI via COM) to read properties like ProductName, FileDescription, ProductVersion, and ProductCode.
    *   Filtering: Applies further filters based on `DETECTION_SETTINGS`.
    *   Matching: Compares extracted metadata and filenames against rules defined in `PROGRAM_CONFIG`.
    *   Heuristics: Scores unidentified files based on size, naming, and metadata presence to flag potential installers.
*   **Registry Check:** Uses the `winreg` module to navigate registry hives (`HKLM`, `HKCU`) and query keys/values according to `PROGRAM_CONFIG` rules.
*   **Execution:** Uses `subprocess.run` (often with `start /wait ""`) to launch installer/uninstaller processes with appropriate command-line arguments based on selected mode and configuration. Monitors process exit codes (0, 3010, 1641 commonly indicate success/reboot needed). For MSI actions, it uses the Windows Installer COM API (`msilib`) to verify installation/uninstallation status via ProductCode when available.
*   **Logging:** Employs Python's standard `logging` module for runtime diagnostics. Persists installation records (key, name, timestamp, paths, uninstall command/ProductCode, version) to a JSON file in the user's Application Data directory for uninstallation purposes.

## Installation Logging

A crucial aspect for uninstallation is the log file: `%APPDATA%\ProgramInstallerApp\program_installer_log.json`. When this tool successfully completes an installation, it records:

*   The `PROGRAM_CONFIG` key used.
*   The program's display name.
*   Timestamp of installation.
*   Full path to the installer file used.
*   The detected `UninstallString` from the registry *after* installation, OR the MSI `ProductCode`.
*   The detected version string.

The "Uninstall Selected" feature relies entirely on this logged information.

## Troubleshooting

*   **Installation Fails:**
    *   Verify the silent switches in `PROGRAM_CONFIG` are correct for the specific installer version. Consult vendor documentation.
    *   Ensure the script is running with Administrator privileges.
    *   Check the console output and `program_installer.log` for error messages from the installer.
    *   Ensure all prerequisite software or runtimes are installed.
*   **Uninstallation Fails:**
    *   Uninstallation only works reliably for programs installed *by this tool* where an uninstall string or ProductCode was successfully logged.
    *   The logged uninstall command might require silent switches not automatically added; manual intervention may be needed.
    *   Ensure Administrator privileges.
*   **Program Not Detected Correctly:**
    *   Refine the `identity` rules (product names, descriptions, patterns) in `PROGRAM_CONFIG` to match the installer's metadata accurately. Use the details panel in the GUI to see the metadata read from the file.
    *   Adjust `DETECTION_SETTINGS` if valid installers are being filtered out (e.g., increase `min_file_size_bytes`, remove conflicting exclusion strings).
*   **Registry Check Incorrect:**
    *   Verify the `check_method` registry paths, value names, and patterns in `PROGRAM_CONFIG` are correct. Use `regedit.exe` to inspect the registry manually. Remember to check both HKLM and HKCU under `SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` (and potentially vendor-specific keys).

## Limitations and Considerations

*   **Silent Switch Accuracy:** The effectiveness of "Auto" and "Semi-Silent" modes depends entirely on discovering and configuring the correct command-line switches for each specific installer. This often requires research or experimentation.
*   **Complex Installers:** Installers involving multiple stages, prerequisite checks, reboots within the process, or interactive configuration prompts may not be fully automated by simple silent switches.
*   **Administrator Privileges:** Most software installations/uninstallations require elevated privileges. The script must be run as an administrator for these operations.
*   **Heuristic Reliability:** Heuristic detection ([Unk]/[SuS]) is imperfect and may misidentify files or fail to identify valid installers. Always verify heuristic matches manually before attempting installation.
*   **Uninstallation Scope:** Automated uninstallation primarily targets software installed *via this tool*. While registry checks might identify other installations, uninstalling them is not guaranteed or directly supported without logged information. Uninstaller reliability depends on the quality of the vendor's uninstaller and the accuracy of the logged `UninstallString` or `ProductCode`.
*   **Error Handling:** While basic error handling exists, intricate errors generated *within* complex installers might not be captured or reported clearly by this tool. Refer to installer-specific logs if available.

## License

Distributed under the MIT License. See the `LICENSE` file.