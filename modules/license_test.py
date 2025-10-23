# license_test.py
import sys
import subprocess
import os
import re
import yaml
from dataclasses import dataclass, field
from typing import List, Optional, Dict

# --- Dependency Check & Imports ---
try:
    from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                                 QPushButton, QTreeWidget, QTreeWidgetItem, QHeaderView, QListWidget, QListWidgetItem,
                                 QStatusBar, QToolBar, QAction, QStyle, QDialog, QDialogButtonBox, QLineEdit, QComboBox, QMessageBox)
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    from PyQt5.QtGui import QIcon, QColor, QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QMainWindow: pass
    class QDialog: pass
    class QThread: 
        pyqtSignal = lambda *args, **kwargs: (lambda func: func)
    class QApplication:
        @staticmethod
        def instance(): return None

# --- Data Classes ---
@dataclass
class FeatureUsage:
    name: str
    total: int
    used: int
    users: List[str] = field(default_factory=list)

@dataclass
class LicenseStatus:
    check_name: str
    server_name: str
    server_port: int
    server_up: bool
    server_version: str
    features: List[FeatureUsage] = field(default_factory=list)
    error_message: Optional[str] = None
    raw_output: str = ""

# --- Core Logic Class ---
class LicenseChecker:
    def __init__(self, lmtools_folder: str, checks: List[Dict]):
        self.lmtools_folder = lmtools_folder
        self.checks = checks

    def update_checks(self, checks: List[Dict]):
        self.checks = checks

    def run_all_checks(self, progress_callback=None):
        if not os.path.isdir(self.lmtools_folder):
            error_status = LicenseStatus(
                check_name="Configuration Error", server_name=self.lmtools_folder, server_port=0, server_up=False, server_version="",
                error_message=f"LMTools directory not found: '{self.lmtools_folder}'"
            )
            if progress_callback: progress_callback.emit(error_status)
            return

        for check in self.checks:
            status = self._run_single_check(check)
            if progress_callback: progress_callback.emit(status)

    def _run_single_check(self, check: Dict) -> LicenseStatus:
        util_name = check.get('util', 'lmutil')
        arguments = check.get('args', '')
        util_path = os.path.join(self.lmtools_folder, f"{util_name}.exe")

        server_info = ""
        c_flag_index = arguments.find("-c ")
        if c_flag_index != -1:
            server_info = arguments[c_flag_index + 3:].split(" ")[0]

        if not os.path.isfile(util_path):
            return LicenseStatus(check_name=check.get('name', 'Unnamed'), server_name=server_info, server_port=0, server_up=False, server_version="", error_message=f"Utility '{util_name}.exe' not found.")

        output = self._execute_command(util_path, arguments)
        if output is None:
            return LicenseStatus(check_name=check.get('name', 'Unnamed'), server_name=server_info, server_port=0, server_up=False, server_version="", error_message="Command failed to execute or timed out.")

        if "lmutil" in util_name.lower():
            return self.parse_flexlm_output(output, server_info, check.get('name', 'Unnamed'))
        elif "rlmutil" in util_name.lower():
            return self.parse_rlm_output(output, server_info, check.get('name', 'Unnamed'))
        
        return LicenseStatus(check_name=check.get('name', 'Unnamed'), server_name=server_info, server_port=0, server_up=False, server_version="", error_message=f"Unknown utility type '{util_name}'", raw_output=output)

    def _execute_command(self, util_path: str, arguments: str) -> Optional[str]:
        try:
            result = subprocess.run(f'"{util_path}" {arguments}', shell=True, capture_output=True, text=True, timeout=60, encoding='utf-8', errors='ignore')
            return result.stdout + "\n" + result.stderr
        except Exception: return None

    def parse_flexlm_output(self, output: str, server_info: str, check_name: str) -> LicenseStatus:
        try:
            port, name = server_info.split('@')
            status = LicenseStatus(check_name=check_name, server_name=name, server_port=int(port), server_up=False, server_version="Unknown", raw_output=output)
        except (ValueError, IndexError): status = LicenseStatus(check_name=check_name, server_name=server_info, server_port=0, server_up=False, server_version="Unknown", raw_output=output)
        server_status_match = re.search(r": license server UP \(v(.*?)\)", output)
        if server_status_match: status.server_up = True; status.server_version = server_status_match.group(1).strip()
        feature_blocks = re.finditer(r'Users of (.*?):\s*\(Total of (\d+) licenses issued;\s*Total of (\d+) licenses in use\)', output, re.IGNORECASE)
        for block in feature_blocks:
            feature = FeatureUsage(name=block.group(1).strip(), total=int(block.group(2)), used=int(block.group(3)))
            content_after = output[block.end():]; next_block_match = re.search(r'Users of', content_after)
            user_block_content = content_after[:next_block_match.start()] if next_block_match else content_after
            for user_match in re.finditer(r'\s+([\w\.-]+)\s+([\w\.-]+)', user_block_content): feature.users.append(f"{user_match.group(1)} on {user_match.group(2)}")
            status.features.append(feature)
        return status

    def parse_rlm_output(self, output: str, server_info: str, check_name: str) -> LicenseStatus:
        try:
            port, name = server_info.split('@')
            status = LicenseStatus(check_name=check_name, server_name=name, server_port=int(port), server_up=False, server_version="Unknown", raw_output=output)
        except (ValueError, IndexError): status = LicenseStatus(check_name=check_name, server_name=server_info, server_port=0, server_up=False, server_version="Unknown", raw_output=output)
        server_status_match = re.search(r"is UP on .*? \(port \d+\), version (v.*?)\n", output)
        if server_status_match: status.server_up = True; status.server_version = server_status_match.group(1).strip()
        feature_blocks = re.finditer(r'\s+(.*?):\s*\((\d+)\s+of\s+(\d+).*?\)\s*\n', output)
        for block in feature_blocks:
            feature = FeatureUsage(name=block.group(1).strip(), used=int(block.group(2)), total=int(block.group(3)))
            content_after = output[block.end():]; next_feature_match = re.search(r'\n\s+[\w-]+\s*:', content_after)
            user_block_content = content_after[:next_feature_match.start()] if next_feature_match else content_after
            for user_match in re.finditer(r'\s+([\w\.-]+) on ([\w\.-]+) .*', user_block_content): feature.users.append(f"{user_match.group(1)} on {user_match.group(2)}")
            status.features.append(feature)
        return status

# --- Worker Thread ---
class LicenseWorker(QThread):
    result_ready = pyqtSignal(LicenseStatus)
    finished = pyqtSignal()
    def __init__(self, checker: LicenseChecker): super().__init__(); self.checker = checker
    def run(self): self.checker.run_all_checks(progress_callback=self.result_ready); self.finished.emit()

# --- Edit Dialog ---
class EditChecksDialog(QDialog):
    checks_updated = pyqtSignal(list)
    def __init__(self, checks, parent=None):
        super().__init__(parent)
        self.checks_data = [c.copy() for c in checks] # Work on a copy
        self.setWindowTitle("Edit License Checks")
        self.setMinimumSize(600, 400)
        self._setup_ui()
        self.populate_list()
        if self.list_widget.count() > 0: self.list_widget.setCurrentRow(0)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        self.list_widget = QListWidget(); self.list_widget.setMaximumWidth(180)
        self.list_widget.currentItemChanged.connect(self.show_check_details)
        layout.addWidget(self.list_widget)
        form_container = QWidget(); form_layout = QVBoxLayout(form_container)
        self.details_form = QFormLayout()
        self.edit_name = QLineEdit(); self.edit_name.textChanged.connect(self.update_current_item_data)
        self.combo_util = QComboBox(); self.combo_util.addItems(["lmutil", "rlmutil"]); self.combo_util.currentTextChanged.connect(self.update_current_item_data)
        self.edit_args = QLineEdit(); self.edit_args.textChanged.connect(self.update_current_item_data)
        self.details_form.addRow("Name:", self.edit_name)
        self.details_form.addRow("Utility:", self.combo_util)
        self.details_form.addRow("Arguments:", self.edit_args)
        form_layout.addLayout(self.details_form)
        form_layout.addStretch()
        layout.addWidget(form_container)
        controls_layout = QVBoxLayout(); controls_layout.setSpacing(10)
        btn_add = QPushButton("Add New"); btn_add.clicked.connect(self.add_new_check)
        btn_del = QPushButton("Delete Selected"); btn_del.clicked.connect(self.delete_selected_check)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); self.button_box.accepted.connect(self.save_and_accept); self.button_box.rejected.connect(self.reject)
        controls_layout.addWidget(btn_add); controls_layout.addWidget(btn_del); controls_layout.addStretch(); controls_layout.addWidget(self.button_box)
        layout.addLayout(controls_layout)

    def populate_list(self):
        self.list_widget.clear()
        for check in self.checks_data: self.list_widget.addItem(check.get('name', 'Unnamed'))

    def show_check_details(self, current_item, previous_item):
        if not current_item: self.clear_form(); return
        row = self.list_widget.row(current_item)
        if 0 <= row < len(self.checks_data):
            check = self.checks_data[row]
            self.edit_name.setText(check.get('name', ''))
            self.combo_util.setCurrentText(check.get('util', 'lmutil'))
            self.edit_args.setText(check.get('args', ''))

    def update_current_item_data(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.checks_data):
            name = self.edit_name.text(); util = self.combo_util.currentText(); args = self.edit_args.text()
            self.checks_data[row] = {'name': name, 'util': util, 'args': args}
            self.list_widget.item(row).setText(name)

    def add_new_check(self):
        new_check = {'name': "New Check", 'util': "lmutil", 'args': "lmstat -a -c 27000@licenseserver"}
        self.checks_data.append(new_check)
        self.list_widget.addItem(new_check['name'])
        self.list_widget.setCurrentRow(self.list_widget.count() - 1)

    def delete_selected_check(self):
        row = self.list_widget.currentRow()
        if row != -1: 
            del self.checks_data[row]
            self.list_widget.takeItem(row)

    def clear_form(self): self.edit_name.clear(); self.edit_args.clear(); self.combo_util.setCurrentIndex(0)
    def save_and_accept(self): self.checks_updated.emit(self.checks_data); self.accept()

# --- UI Class ---
class LicenseCheckerUI(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self._get_paths()
        self.load_checks()
        self.checker = LicenseChecker(self.lmtools_folder, self.checks_to_run)
        self.setWindowTitle("Перевірка стану ліцензії")
        self.setMinimumSize(800, 600)
        self._setup_ui()
        self.refresh_licenses()

    def _get_paths(self):
        if getattr(sys, 'frozen', False): self.main_app_folder = os.path.dirname(sys.executable)
        else: self.main_app_folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.lmtools_folder = os.path.join(self.main_app_folder, "lmtools")
        self.config_dir = os.path.join(os.path.expanduser("~"), ".DesktopOrganizer")
        self.config_file = os.path.join(self.config_dir, "license_checks.yaml")

    def load_checks(self):
        default_checks = [
            {"name": "AUTODESK", "util": "lmutil", "args": "lmstat -a -i -c 27000@10.0.0.51"},
            {"name": "CMG", "util": "rlmutil", "args": "rlmstat -a -c 2700@10.100.220.10"},
            {"name": "Kappa", "util": "lmutil", "args": "lmstat -a -i -c 27000@10.0.0.50"},
            {"name": "Schlumberger", "util": "lmutil", "args": "lmstat -a -i -c 27027@10.100.220.10"},
        ]
        if not os.path.exists(self.config_file):
            self.checks_to_run = default_checks
            self.save_checks()
            return
        try:
            with open(self.config_file, 'r') as f: self.checks_to_run = yaml.safe_load(f)
            if not isinstance(self.checks_to_run, list): self.checks_to_run = default_checks
        except Exception: self.checks_to_run = default_checks

    def save_checks(self):
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.config_file, 'w') as f: yaml.dump(self.checks_to_run, f, default_flow_style=False)
        except Exception as e: QMessageBox.warning(self, "Save Error", f"Could not save license checks to file:\n{e}")

    def _setup_ui(self):
        self.central_widget = QWidget(); self.setCentralWidget(self.central_widget); layout = QVBoxLayout(self.central_widget)
        toolbar = QToolBar("Main Toolbar"); toolbar.setMovable(False); self.addToolBar(toolbar)
        style = QApplication.instance().style() if QApplication.instance() else None
        refresh_icon = style.standardIcon(QStyle.SP_BrowserReload) if style else QIcon()
        edit_icon = style.standardIcon(QStyle.SP_FileDialogDetailedView) if style else QIcon()
        self.refresh_action = QAction(refresh_icon, "Refresh", self); self.refresh_action.triggered.connect(self.refresh_licenses)
        self.edit_action = QAction(edit_icon, "Edit Checks...", self); self.edit_action.triggered.connect(self.open_edit_checks_dialog)
        toolbar.addAction(self.refresh_action); toolbar.addAction(self.edit_action)
        self.tree = QTreeWidget(); self.tree.setHeaderLabels(["Property", "Value"]); self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents); self.tree.header().setStretchLastSection(True); layout.addWidget(self.tree)
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)

    def open_edit_checks_dialog(self):
        dialog = EditChecksDialog(self.checks_to_run, self)
        dialog.checks_updated.connect(self.handle_checks_updated)
        dialog.exec_()

    def handle_checks_updated(self, new_checks):
        self.checks_to_run = new_checks
        self.save_checks()
        self.checker.update_checks(self.checks_to_run)
        self.refresh_licenses()

    def refresh_licenses(self):
        if self.worker and self.worker.isRunning(): return
        self.tree.clear(); self.refresh_action.setEnabled(False); self.edit_action.setEnabled(False)
        self.status_bar.showMessage("Running license checks...")
        self.worker = LicenseWorker(self.checker); self.worker.result_ready.connect(self.update_tree); self.worker.finished.connect(self.on_worker_finished); self.worker.start()

    def on_worker_finished(self): self.status_bar.showMessage("Checks complete.", 5000); self.refresh_action.setEnabled(True); self.edit_action.setEnabled(True)
    def update_tree(self, status: LicenseStatus):
        root_item = QTreeWidgetItem(self.tree, [status.check_name]); root_item.setFont(0, QFont("Segoe UI", 10, QFont.Bold))
        if status.error_message: QTreeWidgetItem(root_item, ["Error", status.error_message]).setForeground(1, QColor("red")); root_item.setExpanded(True); return
        QTreeWidgetItem(root_item, ["Server", f"{status.server_name}:{status.server_port}"])
        status_item = QTreeWidgetItem(root_item, ["Status", f"{('UP' if status.server_up else 'DOWN')} (v{status.server_version})"]); status_item.setForeground(1, QColor("green") if status.server_up else QColor("red"))
        if status.features:
            features_root = QTreeWidgetItem(root_item, ["Features"])
            for feature in status.features:
                total_str = str(feature.total) if feature.total != -1 else "Uncounted"
                feature_item = QTreeWidgetItem(features_root, [feature.name, f"{feature.used} of {total_str} in use"])
                if feature.users: 
                    users_item = QTreeWidgetItem(feature_item, ["Users"])
                    for user in feature.users: QTreeWidgetItem(users_item, [user])
        root_item.setExpanded(True)

# --- Main Execution (for standalone use) ---
def main():
    if not PYQT5_AVAILABLE: print("CRITICAL: This UI requires 'PyQt5' (pip install PyQt5).", file=sys.stderr); sys.exit(1)
    app = QApplication(sys.argv); main_window = LicenseCheckerUI(); main_window.show(); sys.exit(app.exec_())

if __name__ == "__main__":
    main()