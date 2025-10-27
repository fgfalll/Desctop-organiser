# Module Development Guide for Desktop Organizer

This guide provides instructions on how to develop new modules for the Desktop Organizer application. Modules are designed to extend the functionality of the main application and are loaded dynamically into a tabbed interface.

## 1. Module Structure

Each module should be a self-contained Python file (`.py`) located in the `modules` directory of the application.

## 2. Base Class for Module UI

To be compatible with the Desktop Organizer's tabbed interface, your module's main UI class **must inherit from `PyQt5.QtWidgets.QWidget`**, not `QMainWindow`.

## 3. Exposing Module Information

Your module Python file **must contain a function named `get_module_info()`** at the top level. This function will be called by the main application to retrieve essential information about your module, including its display name and the `QWidget` class that represents its UI.

The `get_module_info()` function should return a dictionary with the following keys:

*   `"name"` (str): The human-readable name of your module. This name will be displayed as the tab title in the main application.
*   `"widget"` (class): A reference to your module's main `QWidget` class.

### Example `get_module_info()` implementation:

```python
# my_module.py

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel

class MyModuleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.label = QLabel("Hello from My Module!", self)
        layout.addWidget(self.label)
        self.setWindowTitle("My Module") # set window title for standalone testing

# This function is crucial for integration
def get_module_info():
    return {
        "name": "My Awesome Module",
        "widget": MyModuleWidget
    }

if __name__ == "__main__":
    # Example for standalone testing of your module
    from PyQt5.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    module_data = get_module_info()
    window = module_data["widget"]()
    window.show()
    sys.exit(app.exec_())
```

## 4. Initializing Your Module's UI

When the main application loads your module, it will instantiate your `QWidget` class (e.g., `MyModuleWidget(parent=self)`). The `parent` argument will be a reference to the main application's `MainWindow` instance. You can use this `parent` for:

*   **Accessing main application functionalities:** For example, if the main application exposes a `log_message` method, you can call `self.parent().log_message("Message from module.")`.
*   **Connecting signals:** If your module needs to communicate with the main application, you can define custom signals in your `QWidget` and connect them to slots in the main application.

## 5. Standalone Testing

It is recommended to include a `if __name__ == "__main__":` block in your module file, similar to the example above. This allows you to run and test your module independently during development without needing to launch the entire main application.

## 6. Placement

Place your completed Python module file (`.py`) into the `modules` directory within the Desktop Organizer's root folder. The main application will automatically detect and load it on startup.