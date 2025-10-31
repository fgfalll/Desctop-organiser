# Module Development Guide for Desktop Organizer

This guide provides instructions on how to develop new modules for the Desktop Organizer application. Modules are designed to extend the functionality of the main application and are loaded dynamically into a tabbed interface.

## 1. Module Structure

Each module should be a self-contained Python file (`.py`) located in the `modules` directory of the application.

## 2. Module Manifest

Your module Python file **must contain an embedded JSON manifest** at the beginning of the file. The manifest provides essential information about your module to the main application.

The manifest must be wrapped between `"""MODULE_MANIFEST_START` and `MODULE_MANIFEST_END"""` comments.

### Required Manifest Fields:

```json
{
  "name": "module_name",           # Internal module name (unique)
  "version": "1.0.0",             # Module version
  "description": "Module description",
  "author": "Your Name",
  "category": "System|Utility|Security|Demo|etc.",
  "menu_text": "Display Name...",  # Text shown in menu
  "main_class": "MainClassName",   # Name of the main QWidget class
  "dependencies": [],             # List of pip packages (like requirements.txt)
  "python_version": "3.8+",       # Minimum Python version required
  "permissions": []               # Required permissions
}
```

### Example Complete Module Structure:

```python
"""MODULE_MANIFEST_START
{
  "name": "my_awesome_module",
  "version": "1.0.0",
  "description": "A module that demonstrates awesome functionality",
  "author": "Your Name",
  "category": "Utility",
  "menu_text": "My Awesome Module...",
  "main_class": "MyModuleWidget",
  "dependencies": [
    "requests>=2.25.0",
    "numpy>=1.20.0"
  ],
  "python_version": "3.8+",
  "permissions": [
    "file_system_read",
    "network_access"
  ]
}
MODULE_MANIFEST_END"""

import sys
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt

class MyModuleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        self.label = QLabel("Hello from My Awesome Module!", self)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        self.button = QPushButton("Click Me!", self)
        self.button.clicked.connect(self.on_button_click)
        layout.addWidget(self.button)

        self.setFixedSize(600, 400)

    def on_button_click(self):
        self.label.setText("Button clicked! Module is working!")

        # Example of accessing main application functionality
        if hasattr(self.parent(), 'log_message'):
            self.parent().log_message("MyModule: Button was clicked")

if __name__ == "__main__":
    # Standalone testing
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = MyModuleWidget()
    window.show()
    sys.exit(app.exec_())
```

## 3. Dependencies Management

### Declaring Dependencies

Dependencies are declared in the manifest using the `dependencies` array, similar to a `requirements.txt` file:

```json
{
  "dependencies": [
    "requests>=2.25.0",    # Minimum version
    "numpy==1.20.0",       # Exact version
    "pandas",             # Any version
    "PyYAML>=6.0,<7.0"     # Version range
  ]
}
```

### Supported Dependency Formats:

- **Minimum version**: `package>=1.0.0`
- **Exact version**: `package==1.2.3`
- **Maximum version**: `package<=2.0.0`
- **Version range**: `package>=1.0.0,<2.0.0`
- **Any version**: `package`

### Available Permissions:

- `file_system_read` - Read access to files
- `file_system_write` - Write access to files
- `network_access` - Internet/network access
- `registry_access` - Windows registry access (Windows only)
- `system_info` - Read system information
- `process_control` - Start/stop processes

## 4. Base Class for Module UI

To be compatible with the Desktop Organizer's tabbed interface, your module's main UI class **must inherit from `PyQt5.QtWidgets.QWidget`**, not `QMainWindow`.

## 5. Module Integration

### Automatic Loading

The main application automatically:
1. **Discovers modules** in the `modules` directory
2. **Parses manifests** to understand module requirements
3. **Installs dependencies** automatically into shared virtual environment
4. **Loads modules** and adds them to the tabbed interface

### Module Lifecycle

1. **Discovery**: Application finds your module file
2. **Validation**: Checks manifest and system requirements
3. **Dependency Installation**: Installs required packages automatically
4. **Loading**: Instantiates your main class and adds it as a tab
5. **Runtime**: Your module runs in the main application interface

## 6. Accessing Main Application

Your module can access the main application through the `parent` parameter:

```python
class MyModuleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent  # Reference to main application

    def some_action(self):
        if hasattr(self.main_window, 'log_message'):
            self.main_window.log_message("MyModule: Action performed")
```

## 7. Best Practices

### DO:
- ✅ Use descriptive names in `menu_text`
- ✅ Specify minimum versions for dependencies
- ✅ Include `if __name__ == "__main__":` for testing
- ✅ Handle errors gracefully
- ✅ Set appropriate window size for standalone testing
- ✅ Use the permissions system properly

### DON'T:
- ❌ Don't use `QMainWindow` - use `QWidget` instead
- ❌ Don't import dependencies at module level without lazy loading
- ❌ Don't modify the main application's core functionality
- ❌ Don't include sensitive data in the manifest

## 8. Standalone Testing

Always include a standalone testing section:

```python
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    window = YourModuleClass()
    window.show()
    sys.exit(app.exec_())
```

This allows you to:
- Test your module independently
- Debug issues without running the full application
- Verify UI layout and functionality

## 9. Deployment

### Module Placement

Place your completed Python module file (`.py`) into the `modules` directory within the Desktop Organizer's root folder.

### Automatic Discovery

The main application will automatically:
- Detect your module on startup
- Read and validate the manifest
- Install required dependencies
- Load your module into the interface

### Distribution

Your module can be distributed as a single `.py` file that users simply place in their `modules` directory.

## 10. Troubleshooting

### Common Issues:

1. **Module not loading**: Check manifest syntax and required fields
2. **Dependencies not found**: Verify package names and versions
3. **Import errors**: Use lazy loading for optional dependencies
4. **UI issues**: Ensure class name matches `main_class` in manifest

### Debugging Tips:

- Check the application console for detailed error messages
- Test your module standalone first
- Verify all required fields in the manifest
- Ensure permissions match actual module functionality

## 11. Example Modules

See the existing modules in the `modules` directory for reference:
- `example_module.py` - Basic structure example
- `program_install.py` - Module with dependencies
- `license_test.py` - Module with YAML dependency

These examples demonstrate different patterns and best practices for module development.