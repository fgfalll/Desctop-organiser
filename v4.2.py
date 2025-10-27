import sys
import os
import importlib.util
import shutil
import yaml
import platform
import psutil
import re
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QButtonGroup, QComboBox,
    QMenuBar, QAction, QDialog, QTabWidget, QFormLayout,
    QSpinBox, QCheckBox, QLineEdit, QListWidget, QListWidgetItem,
    QDialogButtonBox, QMessageBox, QRadioButton, QGroupBox, QFileDialog, QTimeEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QTime
import subprocess

# --- Configuration File Path ---
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".DesktopOrganizer")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yaml")
LAST_RUN_FILE = os.path.join(CONFIG_DIR, "last_run.txt")
os.makedirs(CONFIG_DIR, exist_ok=True)

# --- Default Settings ---
DEFAULT_SETTINGS = {
    'application': {
        'autostart_timer_enabled': True,
    },
    'timer': {
        'override_default_enabled': False,
        'default_minutes': 3,
    },
    'drives': {
        'main_drive_policy': 'D',
    },
    'file_manager': {
        'max_file_size_mb': 100,
        'allowed_extensions': ['.lnk'],
        'allowed_filenames': []
    },
    'schedule': {
        'type': 'disabled',  # 'вимкнено', 'щодня', 'щотижня', 'щомісяця', 'щокварталу'
        'time_start': '15:00',
        'time_end': '17:00',
        'day_of_week': 1,  # 1=Понеділок, 7=Неділя
        'day_of_month': 1,
        'quarter_month': 1, # 1, 2, 3
        'quarter_day': 1
    }
}

SCHEDULE_TYPE_MAP = {
    "disabled": "Вимкнено",
    "daily": "Щодня",
    "weekly": "Щотижня",
    "monthly": "Щомісяця",
    "quarterly": "Щокварталу",
}

REVERSE_SCHEDULE_TYPE_MAP = {
    "Вимкнено": "disabled",
    "Щодня": "daily",
    "Щотижня": "weekly",
    "Щомісяця": "monthly",
    "Щокварталу": "quarterly",
}

# --- Module Loading Configuration ---
MODULE_DIR_NAME = "modules" # Subdirectory name for optional modules
EXPECTED_MODULES = {
    "license_manager": {
        "filename": "license_manager.py",
        "class_name": "LicenseManager", # Expected main class in the module
        "menu_text": "&Керування Ліцензіями...",
        "menu_object_name": "manageLicenseAction" # To find the action later
    },
    "program_install": {
        "filename": "program_install.py",
        "class_name": "ProgramInstallerUI", # Assuming this will be the class name
        "menu_text": "Встановити Нову Програму...",
        "menu_object_name": "installProgramAction"
    },
    "license_checker": {
        "filename": "license_test.py",
        "class_name": "LicenseCheckerUI",
        "menu_text": "Перевірка стану ліцензії...",
        "menu_object_name": "checkLicenseStateAction"
    },
    # Add more modules here if needed
}

# --- Settings Dialog ---
class SettingsDialog(QDialog):
    settings_applied = pyqtSignal(dict)

    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.current_settings = current_settings.copy()
        self.setWindowTitle("Налаштування Додатку")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.create_general_tab()
        self.create_file_manager_tab()
        self.create_schedule_tab()

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.load_settings_to_ui()
        self.changes_applied = False

    def create_general_tab(self):
        tab_general = QWidget()
        layout = QVBoxLayout(tab_general)

        app_group = QGroupBox("Поведінка Додатку")
        app_layout = QFormLayout(app_group)
        self.chk_enable_autostart = QCheckBox("Автоматично запускати таймер при старті")
        app_layout.addRow(self.chk_enable_autostart)

        timer_group = QGroupBox("Налаштування Таймера")
        timer_layout = QFormLayout(timer_group)
        self.chk_override_timer = QCheckBox("Перевизначити тривалість таймера за замовчуванням")
        self.spin_default_timer = QSpinBox()
        self.spin_default_timer.setRange(1, 60)
        self.spin_default_timer.setSuffix(" хвилин")
        self.chk_override_timer.toggled.connect(self.spin_default_timer.setEnabled)
        timer_layout.addRow(self.chk_override_timer)
        timer_layout.addRow("Тривалість за замовчуванням:", self.spin_default_timer)

        drive_group = QGroupBox("Налаштування Дисків")
        drive_layout = QVBoxLayout(drive_group)
        drive_layout.addWidget(QLabel("Резервний диск завжди C:"))

        self.rb_drive_d = QRadioButton("Встановити основний диск D:")
        self.rb_drive_auto = QRadioButton("Автоматично визначити наступний доступний диск (незнімний)")
        drive_layout.addWidget(self.rb_drive_d)
        drive_layout.addWidget(self.rb_drive_auto)

        layout.addWidget(app_group)
        layout.addWidget(timer_group)
        layout.addWidget(drive_group)
        layout.addStretch()
        self.tabs.addTab(tab_general, "Загальні")

    def create_file_manager_tab(self):
        tab_fm = QWidget()
        layout = QFormLayout(tab_fm)

        self.spin_max_size = QSpinBox()
        self.spin_max_size.setRange(1, 10240)
        self.spin_max_size.setSuffix(" MB")
        layout.addRow("Макс. розмір файлу:", self.spin_max_size)

        ext_layout = QHBoxLayout()
        self.list_extensions = QListWidget()
        self.list_extensions.setFixedHeight(80)
        ext_controls_layout = QVBoxLayout()
        self.edit_add_ext = QLineEdit()
        self.edit_add_ext.setPlaceholderText(".приклад")
        btn_add_ext = QPushButton("Додати")
        btn_rem_ext = QPushButton("Видалити Вибране")
        btn_add_ext.clicked.connect(self.add_extension)
        btn_rem_ext.clicked.connect(self.remove_extension)
        ext_controls_layout.addWidget(self.edit_add_ext)
        ext_controls_layout.addWidget(btn_add_ext)
        ext_controls_layout.addWidget(btn_rem_ext)
        ext_layout.addWidget(self.list_extensions)
        ext_layout.addLayout(ext_controls_layout)
        layout.addRow("Пропускати розширення:", ext_layout)

        name_layout = QHBoxLayout()
        self.list_filenames = QListWidget()
        self.list_filenames.setFixedHeight(80)
        name_controls_layout = QVBoxLayout()
        self.edit_add_name = QLineEdit()
        self.edit_add_name.setPlaceholderText("ім'я_файлу_без_розширення")
        btn_add_name = QPushButton("Додати")
        btn_rem_name = QPushButton("Видалити Вибране")
        btn_add_name.clicked.connect(self.add_filename)
        btn_rem_name.clicked.connect(self.remove_filename)
        name_controls_layout.addWidget(self.edit_add_name)
        name_controls_layout.addWidget(btn_add_name)
        name_controls_layout.addWidget(btn_rem_name)
        name_layout.addWidget(self.list_filenames)
        name_layout.addLayout(name_controls_layout)
        layout.addRow("Пропускати імена файлів:", name_layout)

        self.tabs.addTab(tab_fm, "Фільтри Файлів")

    def create_schedule_tab(self):
        tab_schedule = QWidget()
        self.schedule_layout = QFormLayout(tab_schedule)

        self.schedule_type_combo = QComboBox()
        self.schedule_type_combo.addItems(["Вимкнено", "Щодня", "Щотижня", "Щомісяця", "Щокварталу"])
        self.schedule_type_combo.currentIndexChanged.connect(self.update_schedule_ui)
        self.schedule_layout.addRow("Тип розкладу:", self.schedule_type_combo)

        self.schedule_time_range_widget = QWidget()
        time_range_layout = QHBoxLayout(self.schedule_time_range_widget)
        time_range_layout.setContentsMargins(0, 0, 0, 0)
        self.schedule_time_start_edit = QTimeEdit()
        self.schedule_time_start_edit.setDisplayFormat("HH:mm")
        self.schedule_time_end_edit = QTimeEdit()
        self.schedule_time_end_edit.setDisplayFormat("HH:mm")
        time_range_layout.addWidget(self.schedule_time_start_edit)
        time_range_layout.addWidget(QLabel("до"))
        time_range_layout.addWidget(self.schedule_time_end_edit)
        self.schedule_layout.addRow("Діапазон часу виконання:", self.schedule_time_range_widget)

        # --- Weekly ---
        self.schedule_day_of_week_combo = QComboBox()
        self.schedule_day_of_week_combo.addItems(["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"])
        self.schedule_day_of_week_row = QWidget()
        self.schedule_day_of_week_row_layout = QHBoxLayout(self.schedule_day_of_week_row)
        self.schedule_day_of_week_row_layout.setContentsMargins(0, 0, 0, 0)
        self.schedule_day_of_week_row_layout.addWidget(self.schedule_day_of_week_combo)
        self.schedule_layout.addRow("День тижня:", self.schedule_day_of_week_row)


        # --- Monthly ---
        self.schedule_day_of_month_spin = QSpinBox()
        self.schedule_day_of_month_spin.setRange(1, 31)
        self.schedule_day_of_month_row = QWidget()
        self.schedule_day_of_month_row_layout = QHBoxLayout(self.schedule_day_of_month_row)
        self.schedule_day_of_month_row_layout.setContentsMargins(0, 0, 0, 0)
        self.schedule_day_of_month_row_layout.addWidget(self.schedule_day_of_month_spin)
        self.schedule_layout.addRow("День місяця:", self.schedule_day_of_month_row)

        # --- Quarterly ---
        self.schedule_quarter_month_combo = QComboBox()
        self.schedule_quarter_month_combo.addItems(["Перший", "Другий", "Третій"])
        self.schedule_quarter_day_spin = QSpinBox()
        self.schedule_quarter_day_spin.setRange(1, 31)
        self.schedule_quarter_row = QWidget()
        self.schedule_quarter_row_layout = QHBoxLayout(self.schedule_quarter_row)
        self.schedule_quarter_row_layout.setContentsMargins(0, 0, 0, 0)
        self.schedule_quarter_row_layout.addWidget(QLabel("Місяць кварталу:"))
        self.schedule_quarter_row_layout.addWidget(self.schedule_quarter_month_combo)
        self.schedule_quarter_row_layout.addWidget(QLabel("День місяця:"))
        self.schedule_quarter_row_layout.addWidget(self.schedule_quarter_day_spin)
        self.schedule_layout.addRow(self.schedule_quarter_row)


        self.tabs.addTab(tab_schedule, "Розклад")

    def update_schedule_ui(self, index):
        schedule_type = self.schedule_type_combo.itemText(index)

        # Visibility flags based on selection
        is_daily = (schedule_type == "Щодня")
        is_weekly = (schedule_type == "Щотижня")
        is_monthly = (schedule_type == "Щомісяця")
        is_quarterly = (schedule_type == "Щокварталу")
        is_disabled = (schedule_type == "Вимкнено")

        # Time range is visible for all except 'disabled'
        self.schedule_time_range_widget.setVisible(not is_disabled)
        # Also toggle the label for the time range
        time_range_label = self.schedule_layout.labelForField(self.schedule_time_range_widget)
        if time_range_label:
            time_range_label.setVisible(not is_disabled)

        # Toggle weekly settings
        self.schedule_day_of_week_row.setVisible(is_weekly)
        day_of_week_label = self.schedule_layout.labelForField(self.schedule_day_of_week_row)
        if day_of_week_label:
            day_of_week_label.setVisible(is_weekly)

        # Toggle monthly settings
        self.schedule_day_of_month_row.setVisible(is_monthly)
        day_of_month_label = self.schedule_layout.labelForField(self.schedule_day_of_month_row)
        if day_of_month_label:
            day_of_month_label.setVisible(is_monthly)

        # Toggle quarterly settings
        self.schedule_quarter_row.setVisible(is_quarterly)
        quarterly_label = self.schedule_layout.labelForField(self.schedule_quarter_row)
        if quarterly_label:
            quarterly_label.setVisible(is_quarterly)

    def add_extension(self):
        ext = self.edit_add_ext.text().strip().lower()
        if ext.startswith('.') and len(ext) > 1:
            if not self.list_extensions.findItems(ext, Qt.MatchExactly):
                self.list_extensions.addItem(ext)
                self.edit_add_ext.clear()
        else:
            QMessageBox.warning(self, "Неправильне розширення", "Розширення повинно починатися з '.' і бути не порожнім.")

    def remove_extension(self):
        for item in self.list_extensions.selectedItems():
            self.list_extensions.takeItem(self.list_extensions.row(item))

    def add_filename(self):
        name = self.edit_add_name.text().strip()
        if name and not any(c in name for c in '/\\:*?"<>|'):
             if not self.list_filenames.findItems(name, Qt.MatchExactly):
                self.list_filenames.addItem(name)
                self.edit_add_name.clear()
        else:
             QMessageBox.warning(self, "Неправильне ім'я файлу", "Ім'я файлу не може бути порожнім або містити недопустимі символи.")

    def remove_filename(self):
        for item in self.list_filenames.selectedItems():
            self.list_filenames.takeItem(self.list_filenames.row(item))

    def load_settings_to_ui(self):
        app_cfg = self.current_settings.get('application', DEFAULT_SETTINGS['application'])
        self.chk_enable_autostart.setChecked(app_cfg.get('autostart_timer_enabled', True))

        timer_cfg = self.current_settings.get('timer', DEFAULT_SETTINGS['timer'])
        self.chk_override_timer.setChecked(timer_cfg.get('override_default_enabled', False))
        self.spin_default_timer.setValue(timer_cfg.get('default_minutes', 3))
        self.spin_default_timer.setEnabled(self.chk_override_timer.isChecked())

        drive_cfg = self.current_settings.get('drives', DEFAULT_SETTINGS['drives'])
        policy = drive_cfg.get('main_drive_policy', 'D')
        if policy == 'auto':
            self.rb_drive_auto.setChecked(True)
        else:
            self.rb_drive_d.setChecked(True)

        fm_cfg = self.current_settings.get('file_manager', DEFAULT_SETTINGS['file_manager'])
        self.spin_max_size.setValue(fm_cfg.get('max_file_size_mb', 100))

        self.list_extensions.clear()
        self.list_extensions.addItems(fm_cfg.get('allowed_extensions', []))

        self.list_filenames.clear()
        self.list_filenames.addItems(fm_cfg.get('allowed_filenames', []))

        schedule_cfg = self.current_settings.get('schedule', DEFAULT_SETTINGS['schedule'])
        schedule_type_en = schedule_cfg.get('type', 'disabled')
        
        schedule_type_ua = SCHEDULE_TYPE_MAP.get(schedule_type_en, "Вимкнено")
        
        index = self.schedule_type_combo.findText(schedule_type_ua)
        if index != -1:
            self.schedule_type_combo.setCurrentIndex(index)

        time_start_str = schedule_cfg.get('time_start', '22:00')
        self.schedule_time_start_edit.setTime(QTime.fromString(time_start_str, "HH:mm"))
        time_end_str = schedule_cfg.get('time_end', '23:00')
        self.schedule_time_end_edit.setTime(QTime.fromString(time_end_str, "HH:mm"))
        
        self.schedule_day_of_week_combo.setCurrentIndex(schedule_cfg.get('day_of_week', 1) - 1)
        self.schedule_day_of_month_spin.setValue(schedule_cfg.get('day_of_month', 1))
        self.schedule_quarter_month_combo.setCurrentIndex(schedule_cfg.get('quarter_month', 1) - 1)
        self.schedule_quarter_day_spin.setValue(schedule_cfg.get('quarter_day', 1))

        self.update_schedule_ui(self.schedule_type_combo.currentIndex())

    def get_settings_from_ui(self):
        updated_settings = {
            'application': {
                'autostart_timer_enabled': self.chk_enable_autostart.isChecked()
            },
            'timer': {
                'override_default_enabled': self.chk_override_timer.isChecked(),
                'default_minutes': self.spin_default_timer.value()
            },
            'drives': {
                'main_drive_policy': 'auto' if self.rb_drive_auto.isChecked() else 'D'
            },
            'file_manager': {
                'max_file_size_mb': self.spin_max_size.value(),
                'allowed_extensions': sorted([self.list_extensions.item(i).text() for i in range(self.list_extensions.count())]),
                'allowed_filenames': sorted([self.list_filenames.item(i).text() for i in range(self.list_filenames.count())])
            },
            'schedule': {
                'type': REVERSE_SCHEDULE_TYPE_MAP.get(self.schedule_type_combo.currentText(), "disabled"),
                'time_start': self.schedule_time_start_edit.time().toString("HH:mm"),
                'time_end': self.schedule_time_end_edit.time().toString("HH:mm"),
                'day_of_week': self.schedule_day_of_week_combo.currentIndex() + 1,
                'day_of_month': self.schedule_day_of_month_spin.value(),
                'quarter_month': self.schedule_quarter_month_combo.currentIndex() + 1,
                'quarter_day': self.schedule_quarter_day_spin.value()
            }
        }
        return updated_settings

    def apply_changes(self):
        new_settings = self.get_settings_from_ui()
        self.current_settings = new_settings
        self.settings_applied.emit(new_settings)
        self.changes_applied = True

    def accept(self):
        if not self.changes_applied:
            self.apply_changes()
        super().accept()


# --- File Mover Thread ---
class FileMover(QThread):
    update_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int, int, str)

    def __init__(self, target_drive, fallback_drive, settings):
        super().__init__()
        self.target_drive = target_drive
        self.fallback_drive = fallback_drive
        self.settings = settings
        self.base_folder_name = "Робочі столи"

    def run(self):
        try:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            now = datetime.now()

            fm_settings = self.settings.get('file_manager', DEFAULT_SETTINGS['file_manager'])
            skip_extensions = {ext.lower() for ext in fm_settings.get('allowed_extensions', [])}
            skip_filenames = {name for name in fm_settings.get('allowed_filenames', [])}
            max_size_bytes = fm_settings.get('max_file_size_mb', 100) * 1024 * 1024

            target_base_path = os.path.join(f"{self.target_drive}:\\", self.base_folder_name)
            fallback_base_path = os.path.join(f"{self.fallback_drive}:\\", self.base_folder_name)

            effective_base_path = ""
            if self.check_drive_exists(self.target_drive):
                 effective_base_path = target_base_path
            elif self.check_drive_exists(self.fallback_drive):
                 self.update_signal.emit(f"⚠️ Диск {self.target_drive}: недоступний. Використовуємо {self.fallback_drive}:")
                 effective_base_path = fallback_base_path
            else:
                self.update_signal.emit(f"❌ Критична помилка: Цільовий диск {self.target_drive}: та резервний {self.fallback_drive}: недоступні.")
                self.finished_signal.emit(0, 0, "Помилка: Немає доступних дисків")
                return

            year = now.strftime("%Y")
            timestamp = now.strftime("%d-%m-%Y %H-%M")
            dest_path = os.path.join(effective_base_path, f"Робочий стіл {year}", f"Робочий стіл {timestamp}")

            os.makedirs(dest_path, exist_ok=True)
            self.update_signal.emit(f"📁 Цільова папка: {dest_path}")

            success = errors = 0
            if not os.path.isdir(desktop):
                self.update_signal.emit(f"❌ Помилка: Папка робочого столу не знайдена за шляхом {desktop}")
                self.finished_signal.emit(0, 0, dest_path)
                return

            items_to_move = os.listdir(desktop)
            if not items_to_move:
                 self.update_signal.emit("ℹ️ Робочий стіл порожній. Немає чого переміщувати.")

            for item in items_to_move:
                src = os.path.join(desktop, item)
                item_name_no_ext, item_ext = os.path.splitext(item)
                item_ext_lower = item_ext.lower()

                if item_ext_lower in skip_extensions:
                    self.update_signal.emit(f"⏭️ Пропущено за розширенням: {item}")
                    continue

                if item_name_no_ext in skip_filenames:
                    self.update_signal.emit(f"⏭️ Пропущено за ім'ям файлу: {item}")
                    continue

                if os.path.isfile(src):
                    try:
                        file_size = os.path.getsize(src)
                        if file_size > max_size_bytes:
                            self.update_signal.emit(f"⏭️ Пропущено за розміром ({file_size / (1024*1024):.1f}MB): {item}")
                            continue
                    except OSError as e:
                         self.update_signal.emit(f"⚠️ Не вдалося отримати розмір {item}: {e}")
                         continue

                try:
                    final_dest = os.path.join(dest_path, item)
                    shutil.move(src, final_dest)
                    success += 1
                    self.update_signal.emit(f"✅ Переміщено: {item}")
                except Exception as e:
                    errors += 1
                    self.update_signal.emit(f"❌ Помилка переміщення '{item}': {str(e)}")

            self.finished_signal.emit(success, errors, dest_path)

        except Exception as e:
            self.update_signal.emit(f"❌ Критична помилка потоку: {str(e)}")
            self.finished_signal.emit(0, 0, "Помилка в потоці")

    def check_drive_exists(self, drive_letter):
        drive = f"{drive_letter}:\\"
        return os.path.exists(drive)

# --- Run Statistics Dialog ---
class RunStatisticsDialog(QDialog):
    def __init__(self, success, errors, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Статистика виконання")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        stats_text = f"Успішно переміщено: {success}\nПомилок: {errors}"
        if not path.startswith("Error"):
            stats_text += f"\nВихідна папка: {path}"

        stats_label = QLabel(stats_text)
        layout.addWidget(stats_label)

        button_layout = QHBoxLayout()
        self.open_folder_btn = QPushButton("Відкрити вихідну папку")
        self.open_folder_btn.clicked.connect(lambda: self.open_folder(path))
        if path.startswith("Error"):
            self.open_folder_btn.setEnabled(False)
        button_layout.addWidget(self.open_folder_btn)

        self.close_btn = QPushButton("Закрити")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

        self.auto_close_timer = QTimer(self)
        self.auto_close_timer.setSingleShot(True)
        self.auto_close_timer.timeout.connect(self.close)
        self.auto_close_timer.start(60000) # 1 minute

    def open_folder(self, path):
        try:
            os.startfile(path)
        except Exception as e:
            QMessageBox.warning(self, "Помилка", f"Не вдалося відкрити папку: {e}")


# --- Main Window ---
# --- End of content ---

def _merge_dicts(base, updates):
    for key, value in updates.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            _merge_dicts(base[key], value)
        else:
            base[key] = value
    return base

def load_settings():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            loaded_settings = yaml.safe_load(f)
            if loaded_settings:
                merged = _merge_dicts(DEFAULT_SETTINGS.copy(), loaded_settings)
                return merged
            else:
                return DEFAULT_SETTINGS.copy()
    except FileNotFoundError:
        print(f"Файл конфігурації не знайдено за шляхом {CONFIG_FILE}. Використовуються стандартні налаштування.")
        return DEFAULT_SETTINGS.copy()
    except yaml.YAMLError as e:
        print(f"Помилка розбору файлу конфігурації {CONFIG_FILE}: {e}. Використовуються стандартні налаштування.")
        return DEFAULT_SETTINGS.copy()
    except Exception as e:
        print(f"Неочікувана помилка завантаження конфігурації {CONFIG_FILE}: {e}. Використовуються стандартні налаштування.")
        return DEFAULT_SETTINGS.copy()

def find_next_available_drive():
    available_drives = []
    try:
        partitions = psutil.disk_partitions(all=False)
        for p in partitions:
            if platform.system() == "Windows" and re.match("^[A-Z]:\\?$", p.mountpoint) and p.mountpoint[0] != 'C':
                if p.fstype and 'cdrom' not in p.opts.lower():
                     if 'removable' not in p.opts.lower():
                         if os.path.exists(p.mountpoint):
                              available_drives.append(p.mountpoint[0])
        available_drives.sort()
        return available_drives[0] if available_drives else None
    except Exception as e:
        print(f"⚠️ Помилка визначення дисків: {e}. Використовується резервний варіант.")
        return None

def is_scheduled_day(schedule_cfg):
    now = datetime.now()
    schedule_type = schedule_cfg.get('type', 'disabled')

    if schedule_type == 'daily':
        return True
    elif schedule_type == 'weekly':
        return now.isoweekday() == schedule_cfg.get('day_of_week', 1)
    elif schedule_type == 'monthly':
        return now.day == schedule_cfg.get('day_of_month', 1)
    elif schedule_type == 'quarterly':
        quarter_month = schedule_cfg.get('quarter_month', 1)  # 1, 2, 3
        quarter_day = schedule_cfg.get('quarter_day', 1)
        month_of_quarter = (now.month - 1) % 3 + 1
        return month_of_quarter == quarter_month and now.day == quarter_day
    return False

# --- Background Task Runner ---
class BackgroundTaskRunner:
    def __init__(self):
        self.settings = load_settings()
        self.mover_thread = None
        self.selected_drive = 'C'
        self.auto_configure_drive()

    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    def load_last_run_date(self):
        try:
            with open(LAST_RUN_FILE, 'r') as f:
                date_str = f.read().strip()
                return datetime.strptime(date_str, '%Y-%m-%d').date()
        except (FileNotFoundError, ValueError):
            return None

    def save_last_run_date(self, date):
        try:
            with open(LAST_RUN_FILE, 'w') as f:
                f.write(date.strftime('%Y-%m-%d'))
        except Exception as e:
            self.log_message(f"❌ Помилка збереження дати останнього запуску: {e}")

    def auto_configure_drive(self):
        policy = self.settings.get('drives', {}).get('main_drive_policy', 'D')
        initial_drive = None
        d_exists = os.path.exists("D:\\")
        e_exists = os.path.exists("E:\\")

        if policy == 'D' and d_exists:
            initial_drive = 'D'
        elif policy == 'auto':
            detected_drive = find_next_available_drive()
            if detected_drive:
                initial_drive = detected_drive
            elif d_exists:
                self.log_message("ℹ️ Автовизначення не вдалося, використовується диск D:")
                initial_drive = 'D'
        elif policy == 'D' and not d_exists and e_exists:
            self.log_message("ℹ️ Встановлено політику 'D', але диск D: не знайдено. Використовується диск E:")
            initial_drive = 'E'
        elif e_exists and not initial_drive:
            self.log_message(f"ℹ️ Політика '{policy}' не спрацювала, використовується диск E:")
            initial_drive = 'E'

        if initial_drive:
            self.selected_drive = initial_drive
        else:
            self.selected_drive = 'C'
            if policy != 'C':
                self.log_message("⚠️ Не знайдено відповідного диска. Використовується диск C:")
        self.log_message(f"⚙️ Основний диск встановлено на: {self.selected_drive}:")

    def check_and_run(self):
        schedule_cfg = self.settings.get('schedule', DEFAULT_SETTINGS['schedule'])
        schedule_type = schedule_cfg.get('type', 'disabled')

        if schedule_type == 'disabled':
            self.log_message("ℹ️ Розклад вимкнено. Вихід.")
            return False

        now = datetime.now()
        today = now.date()
        last_run_date = self.load_last_run_date()

        if not is_scheduled_day(schedule_cfg):
            self.log_message("ℹ️ Не запланований день. Вихід.")
            return False

        if last_run_date == today:
            self.log_message("ℹ️ Заплановане завдання вже виконано сьогодні. Вихід.")
            return False

        start_time = QTime.fromString(schedule_cfg.get('time_start', '22:00'), "HH:mm")
        end_time = QTime.fromString(schedule_cfg.get('time_end', '23:00'), "HH:mm")
        current_time = QTime.currentTime()

        run_now = False
        if start_time <= current_time <= end_time:
            cpu_usage = psutil.cpu_percent(interval=1)
            self.log_message(f"ℹ️ У вікні розкладу. ЦП: {cpu_usage}%.")
            if cpu_usage < 15.0:
                self.log_message("⏰ Низьке завантаження ЦП. Запуск запланованого завдання.")
                run_now = True
        elif current_time > end_time:
            self.log_message("⚠️ Вікно розкладу пропущено. Запуск завдання зараз.")
            run_now = True

        if run_now:
            self.launch_gui_app() # Call the new method to launch GUI
            self.save_last_run_date(today)
            return True
        else:
            self.log_message("ℹ️ Умови для запуску завдання зараз не виконані. Вихід.")
            return False

    def launch_gui_app(self):
        self.log_message("🚀 Запуск графічного інтерфейсу для виконання запланованого завдання...")
        try:
            # Determine the path to the current script
            script_path = os.path.abspath(sys.argv[0])
            
            # Use sys.executable to ensure the same Python interpreter is used
            # Pass a special argument to indicate it's a scheduled run
            subprocess.Popen([sys.executable, script_path, '--scheduled-run'])
            
            # Since we are launching a new process, the background runner can exit
            QCoreApplication.instance().quit()
        except Exception as e:
            self.log_message(f"❌ Помилка запуску графічного інтерфейсу: {e}")

    def start_process(self):
        if self.mover_thread and self.mover_thread.isRunning():
            self.log_message("⚠️ Процес вже запущено.")
            return

        self.log_message(f"\n🚀 Початок переміщення файлів на диск {self.selected_drive}:...")
        self.mover_thread = FileMover(target_drive=self.selected_drive, fallback_drive='C', settings=self.settings.copy())
        self.mover_thread.update_signal.connect(self.log_message)
        self.mover_thread.finished_signal.connect(self.process_finished)
        self.mover_thread.start()

    def process_finished(self, success, errors, path):
        self.log_message("\n🏁 Результат:")
        self.log_message(f"✅ Успішно: {success}")
        if errors > 0:
            self.log_message(f"❌ Помилок: {errors}")
        if not path.startswith("Error"):
            self.log_message(f"📁 Збережено до: {path}")
        else:
            self.log_message(f"❌ {path}")
        QCoreApplication.instance().quit()


# --- Main Window ---
class MainWindow(QMainWindow):
    def __init__(self, is_scheduled_run=False):
        super().__init__()
        self.settings = load_settings()
        self.mover_thread = None
        # self.license_manager_window = None # Remove this - we'll handle dynamically
        self.loaded_modules = {}  # Stores loaded module classes/functions
        self.module_windows = {}  # Stores instances of opened module windows
        self.module_actions = {}  # Stores menu actions related to modules

        self.auto_start_timer = QTimer(self)
        self.auto_start_timer.timeout.connect(self.update_timer)
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self.check_schedule)
        self.remaining_time = 0
        self.selected_drive = 'C'
        self.d_exists = False
        self.e_exists = False
        self.last_scheduled_run_date = None

        self.initUI()  # Create UI elements first
        self.load_optional_modules()  # Attempt to load modules
        self.update_ui_for_modules()  # Enable/disable menus based on loaded modules

        self.apply_settings_to_ui()  # Apply loaded settings to UI
        self._log_current_schedule_settings(self.settings.get('schedule', DEFAULT_SETTINGS['schedule']))

        QTimer.singleShot(500, self.auto_configure_start)  # Existing delayed config
        self.schedule_timer.start(60000) # Check every minute

        if is_scheduled_run:
            self.log_message("ℹ️ Запущено за розкладом. Початок процесу переміщення.")
            self.start_process()



    def get_module_dir(self):
        """Determines the path to the 'modules' directory relative to the script or executable."""
        if getattr(sys, 'frozen', False):
            # Running as a bundled executable (PyInstaller)
            base_path = os.path.dirname(sys.executable)
        else:
            # Running as a normal Python script
            base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, MODULE_DIR_NAME)

    def load_optional_modules(self):
        """Scans the module directory and loads any found optional modules."""
        module_dir = self.get_module_dir()
        self.log_message(f"ℹ️ Перевірка додаткових модулів у: {module_dir}")

        if not os.path.isdir(module_dir):
            self.log_message(f"ℹ️ Папку модулів не знайдено. Пропуск додаткових модулів.")
            return

        for key, config in EXPECTED_MODULES.items():
            module_path = os.path.join(module_dir, config["filename"])

            if os.path.exists(module_path):
                self.log_message(f"ℹ️ Знайдено потенційний файл модуля: {config['filename']}")
                try:
                    # Create a unique module name to avoid conflicts
                    module_name = f"dynamic_modules.{key}"

                    # Load the module using importlib
                    spec = importlib.util.spec_from_file_location(module_name, module_path)
                    if spec is None:
                        raise ImportError(f"Could not get spec for module at {module_path}")

                    module = importlib.util.module_from_spec(spec)
                    if module is None:
                        raise ImportError(f"Could not create module from spec {module_name}")

                    # Add to sys.modules BEFORE executing, crucial for relative imports within the module
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

                    # --- Integration Point ---
                    # Find the expected class within the loaded module
                    if hasattr(module, config["class_name"]):
                        self.loaded_modules[key] = getattr(module, config["class_name"])
                        self.log_message(f"✅ Модуль '{key}' успішно завантажено.")
                    else:
                        self.log_message(
                            f"⚠️ Модуль '{key}' завантажено, але необхідний клас '{config['class_name']}' не знайдено.")
                        # Optional: Clean up sys.modules if class not found?
                        # del sys.modules[module_name]

                except Exception as e:
                    self.log_message(f"❌ Помилка завантаження модуля '{config['filename']}': {e}")
                    # Ensure partially loaded module is removed from sys.modules
                    if module_name in sys.modules:
                        del sys.modules[module_name]
            else:
                self.log_message(f"ℹ️ Додатковий модуль '{config['filename']}' не знайдено.")



    def save_settings(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                yaml.dump(self.settings, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        except Exception as e:
            print(f"Помилка збереження налаштувань у {CONFIG_FILE}: {e}")
            QMessageBox.critical(self, "Помилка збереження", f"Не вдалося зберегти налаштування у {CONFIG_FILE}:\n{e}")



    def auto_configure_start(self):
        policy = self.settings.get('drives', {}).get('main_drive_policy', 'D')
        initial_drive = None

        self.check_drive_availability()

        if policy == 'D' and self.d_exists:
            initial_drive = 'D'
        elif policy == 'auto':
            detected_drive = find_next_available_drive()
            if detected_drive:
                initial_drive = detected_drive
            elif self.d_exists:
                self.log_message("ℹ️ Автовизначення не вдалося або немає відповідного диска, повертаємося до D:")
                initial_drive = 'D'
        elif policy == 'D' and not self.d_exists and self.e_exists:
             self.log_message(f"ℹ️ Вказано політику основного диска 'D', але D: не знайдено. Повертаємося до E:")
             initial_drive = 'E'
        elif self.e_exists and not initial_drive:
             self.log_message(f"ℹ️ Політика основного диска '{policy}' не вдалася або не застосовна, повертаємося до E:")
             initial_drive = 'E'

        if initial_drive:
            self.selected_drive = initial_drive
        else:
            self.selected_drive = 'C'
            if policy != 'C':
                self.log_message("⚠️ Не знайдено відповідного основного диска (D:, E:, або автовизначеного). Використовується C:")

        self.log_message(f"⚙️ Початковий основний диск встановлено на: {self.selected_drive}:")
        self.update_drive_buttons_visuals()

        self.apply_settings_to_ui()

        app_settings = self.settings.get('application', DEFAULT_SETTINGS['application'])
        if app_settings.get('autostart_timer_enabled', True):
            self.start_auto_timer()
        else:
             self.log_message("ℹ️ Автозапуск таймера вимкнено в налаштуваннях.")
             self.stop_auto_timer(log_disabled=True)


    def apply_settings_to_ui(self):
        timer_cfg = self.settings.get('timer', DEFAULT_SETTINGS['timer'])
        minutes_to_set = DEFAULT_SETTINGS['timer']['default_minutes']

        if timer_cfg.get('override_default_enabled', False):
            minutes_to_set = timer_cfg.get('default_minutes', minutes_to_set)

        index_to_set = -1
        for i in range(self.time_combo.count()):
            try:
                if int(self.time_combo.itemText(i).split()[0]) == minutes_to_set:
                    index_to_set = i
                    break
            except: pass
        if index_to_set != -1:
             self.time_combo.blockSignals(True)
             self.time_combo.setCurrentIndex(index_to_set)
             self.time_combo.blockSignals(False)
        else:
             self.time_combo.blockSignals(True)
             self.time_combo.setCurrentIndex(1)
             self.time_combo.blockSignals(False)

        if not self.auto_start_timer.isActive():
            self.update_timer_label_when_stopped()

        self.update_drive_buttons_visuals()

    def update_timer_label_when_stopped(self):
        minutes_text = self.time_combo.currentText()
        try:
            minutes_val = int(minutes_text.split()[0])
            self.remaining_time = minutes_val * 60
            self.timer_label.setText(f"Автозапуск вимкнено ({self.format_time()})")
        except:
            self.timer_label.setText("Автозапуск вимкнено (Помилка)")


    def initUI(self):
        self.setWindowTitle("Авто-організатор робочого столу v4.2")
        self.setGeometry(300, 300, 991, 701)

        menubar = self.menuBar()

        # --- File Menu ---
        file_menu = menubar.addMenu('&Файл')
        settings_action = QAction('&Налаштування...', self)
        settings_action.triggered.connect(self.open_settings_dialog)
        file_menu.addAction(settings_action)
        # --- Add Import Module Action ---
        import_module_action = QAction('&Імпортувати додатковий модуль', self)
        import_module_action.triggered.connect(self.import_modules_to_standard_dir)
        file_menu.addAction(import_module_action)
        file_menu.addSeparator()
        exit_action = QAction('&Вихід', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- Modules Menu ---
        modules_menu = menubar.addMenu('&Модулі')
        self.modules_menu = modules_menu

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self.resize_to_current_tab)
        main_layout.addWidget(self.tab_widget)

        # --- Main Tab ---
        main_tab = QWidget()
        self.tab_widget.addTab(main_tab, "Головна")
        main_tab_layout = QVBoxLayout(main_tab)

        self.timer_label = QLabel("Завантаження...")
        main_tab_layout.addWidget(self.timer_label)

        control_layout = QHBoxLayout()
        self.time_combo = QComboBox()
        self.time_combo.addItems(["1 хвилина", "3 хвилини", "5 хвилин", "10 хвилин"])
        self.time_combo.currentIndexChanged.connect(self.time_selection_changed)
        control_layout.addWidget(self.time_combo)
        self.start_now_btn = QPushButton("🚀 Старт зараз")
        self.start_now_btn.clicked.connect(self.start_now)
        control_layout.addWidget(self.start_now_btn)
        self.timer_control_btn = QPushButton("⏱️ Стоп таймер")
        self.timer_control_btn.clicked.connect(self.toggle_timer)
        control_layout.addWidget(self.timer_control_btn)
        main_tab_layout.addLayout(control_layout)

        drive_group = QGroupBox("Вибір основного диска")
        drive_layout = QHBoxLayout(drive_group)
        self.btn_group = QButtonGroup(self)
        self.btn_drive_d = QPushButton("Диск D:")
        self.btn_drive_e = QPushButton("Диск E:")
        self.btn_group.addButton(self.btn_drive_d, ord('D'))
        self.btn_group.addButton(self.btn_drive_e, ord('E'))
        drive_layout.addWidget(self.btn_drive_d)
        drive_layout.addWidget(self.btn_drive_e)
        self.btn_group.buttonClicked[int].connect(self.set_selected_drive)
        main_tab_layout.addWidget(drive_group)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        main_tab_layout.addWidget(self.log)

    def resize_to_current_tab(self, index=-1):
        current_widget = self.tab_widget.currentWidget()
        if current_widget:
            self.centralWidget().adjustSize()
            self.adjustSize()

    def import_modules_to_standard_dir(self):
        """Opens a dialog to select .py files and copies them to the standard module directory."""
        source_files, _ = QFileDialog.getOpenFileNames(
            self,
            "Виберіть файли модулів для імпорту",
            os.path.expanduser("~"),  # Start in user's home directory or last path
            "Файли Python (*.py);;Всі файли (*.*)"
        )

        if not source_files:
            self.log_message("ℹ️ Імпорт модуля скасовано користувачем.")
            return

        target_dir = self.get_module_dir()  # Get ./modules path
        try:
            os.makedirs(target_dir, exist_ok=True)  # Ensure the directory exists
        except OSError as e:
            self.log_message(f"❌ Критична помилка: Не вдалося створити папку модуля '{target_dir}': {e}")
            QMessageBox.critical(self, "Помилка імпорту",
                                 f"Не вдалося створити цільову папку модуля:\n{target_dir}\n\n{e}")
            return

        copied_count = 0
        skipped_count = 0
        error_count = 0
        modules_changed = False

        for src_path in source_files:
            filename = os.path.basename(src_path)
            dest_path = os.path.join(target_dir, filename)

            # Check for overwrite
            if os.path.exists(dest_path):
                reply = QMessageBox.question(
                    self,
                    "Підтвердити перезапис",
                    f"Модуль '{filename}' вже існує в стандартній папці.\nВи хочете перезаписати його?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No  # Default to No
                )
                if reply == QMessageBox.No:
                    self.log_message(f"⏭️ Пропущено перезапис для: {filename}")
                    skipped_count += 1
                    continue

            # Attempt to copy
            try:
                shutil.copy2(src_path, dest_path)  # copy2 preserves metadata
                self.log_message(f"✅ Імпортовано: {filename}")
                copied_count += 1
                modules_changed = True
            except Exception as e:
                self.log_message(f"❌ Помилка імпорту '{filename}': {e}")
                error_count += 1

        summary = f"🏁 Процес імпорту завершено. Скопійовано: {copied_count}, Пропущено: {skipped_count}, Помилок: {error_count}."
        self.log_message(summary)
        QMessageBox.information(self, "Імпорт завершено", summary)

        # Reload modules if any file was successfully copied
        if modules_changed:
            self.log_message("🔄 Перезавантаження модулів після імпорту...")
            self.reload_modules_and_update_ui()

    def update_ui_for_modules(self):
        self.modules_menu.clear()
        for key, config in EXPECTED_MODULES.items():
            is_loaded = key in self.loaded_modules
            action = QAction(config["menu_text"], self)
            action.setEnabled(is_loaded)
            action.triggered.connect(lambda checked=False, key=key: self.open_module_window(key))
            self.modules_menu.addAction(action)
            self.module_actions[key] = action

    def open_module_window(self, module_key):
        if module_key in self.loaded_modules:
            try:
                ModuleClass = self.loaded_modules[module_key]

                # Check if a tab for this module already exists
                for i in range(self.tab_widget.count()):
                    if self.tab_widget.widget(i).property("module_key") == module_key:
                        self.tab_widget.setCurrentIndex(i)
                        return

                module_widget = ModuleClass(parent=self)
                module_widget.setProperty("module_key", module_key)
                tab_name = EXPECTED_MODULES[module_key].get("menu_text", "Module").replace("&", "").replace("...", "")
                self.tab_widget.addTab(module_widget, tab_name)
                self.tab_widget.setCurrentWidget(module_widget)

            except Exception as e:
                self.log_message(f"❌ Помилка створення екземпляра або відображення вікна для модуля '{module_key}': {e}")
                QMessageBox.critical(self, "Помилка модуля", f"Не вдалося запустити вікно модуля '{module_key}'.\n\n{e}")
        else:
            self.log_message(f"⚠️ Спроба відкрити модуль '{module_key}', але він не завантажений.")
            QMessageBox.warning(self, "Модуль недоступний",
                                f"Необхідний модуль '{module_key}' не знайдено або не вдалося завантажити.")

    def reload_modules_and_update_ui(self):
        """Clears, reloads modules, and updates the UI accordingly."""
        # 1. Close existing module windows (Optional but safer)
        keys_to_close = list(self.module_windows.keys())
        for key in keys_to_close:
            window = self.module_windows.pop(key, None)
            if window and window.isVisible():
                self.log_message(f"Спроба закрити вікно для модуля '{key}'...")
                try:
                    # Disconnect signals maybe? Depends on module design
                    window.close()
                    # window.deleteLater() # More aggressive cleanup?
                except Exception as e:
                    self.log_message(f"Помилка закриття вікна для '{key}': {e}")
            elif window:
                # window.deleteLater() # Cleanup non-visible too?
                pass

        QApplication.processEvents()  # Allow windows to close

        # 2. Clear internal references
        # Make copies of keys before iterating if deleting during iteration
        loaded_keys = list(self.loaded_modules.keys())
        self.loaded_modules.clear()
        self.log_message(f"Очищено внутрішні посилання на модулі: {loaded_keys}")

        # 3. Attempt to clean up sys.modules (Use the specific names we created)
        # This might STILL not be enough for C extensions!
        external_prefix = "dynamic_modules.external."
        default_prefix = "dynamic_modules.default."
        modules_to_delete = []
        for mod_name in sys.modules:
            if mod_name.startswith(external_prefix) or mod_name.startswith(default_prefix):
                modules_to_delete.append(mod_name)

        for mod_name in modules_to_delete:
            self.log_message(f"Видалення '{mod_name}' з sys.modules...")
            try:
                del sys.modules[mod_name]
            except KeyError:
                pass  # Already gone

        self.update_ui_for_modules()
        self.log_message("--- Перезавантаження модулів завершено ---")


    def _log_current_schedule_settings(self, schedule_cfg):
        schedule_type_en = schedule_cfg.get('type', 'disabled')
        schedule_type_ua = SCHEDULE_TYPE_MAP.get(schedule_type_en, "Вимкнено")

        log_str = f"ℹ️ Розклад встановлено: {schedule_type_ua}"
        if schedule_type_en != 'disabled':
            time_start = schedule_cfg.get('time_start', '22:00')
            time_end = schedule_cfg.get('time_end', '23:00')
            log_str += f", Час: {time_start}-{time_end}"

            if schedule_type_en == 'weekly':
                day_of_week_index = schedule_cfg.get('day_of_week', 1) - 1
                day_of_week_ua = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"][day_of_week_index]
                log_str += f", День тижня: {day_of_week_ua}"
            elif schedule_type_en == 'monthly':
                day_of_month = schedule_cfg.get('day_of_month', 1)
                log_str += f", День місяця: {day_of_month}"
            elif schedule_type_en == 'quarterly':
                quarter_month_index = schedule_cfg.get('quarter_month', 1) - 1
                quarter_month_ua = ["Перший", "Другий", "Третій"][quarter_month_index]
                quarter_day = schedule_cfg.get('quarter_day', 1)
                log_str += f", Місяць кварталу: {quarter_month_ua}, День: {quarter_day}"
        
        self.log_message(log_str)

    def handle_settings_applied(self, new_settings):
        self.settings = new_settings
        self.save_settings()
        self.apply_settings_to_ui()
        self.log_message("⚙️ Налаштування застосовано.")

        # Log schedule settings
        schedule_cfg = self.settings.get('schedule', DEFAULT_SETTINGS['schedule'])
        self._log_current_schedule_settings(schedule_cfg)

        if not self.auto_start_timer.isActive():
            app_settings = self.settings.get('application', DEFAULT_SETTINGS['application'])
            if not app_settings.get('autostart_timer_enabled', True):
                 self.stop_auto_timer(log_disabled=True)
            else:
                 self.update_timer_label_when_stopped()


    def open_settings_dialog(self):
        dialog = SettingsDialog(self.settings, self)
        dialog.settings_applied.connect(self.handle_settings_applied)
        dialog.exec_()


    def show_install_placeholder(self):
        QMessageBox.information(self, "Встановлення програм", "Ця функція ще не реалізована.")


    def open_license_manager(self):
        if self.license_manager_window and self.license_manager_window.isVisible():
            self.license_manager_window.activateWindow()
            self.license_manager_window.raise_()
        else:
            try:
                # Re-check if the import worked initially
                from license_manager import LicenseManager as ActualLicenseManager
                self.license_manager_window = ActualLicenseManager(self)
                # Optional: Connect log signal
                # self.license_manager_window.log_signal.connect(self.handle_license_log)
                self.license_manager_window.show()
            except ImportError:
                 QMessageBox.critical(self, "Помилка", "Модуль Менеджера Ліцензій не вдалося завантажити.")
            except Exception as e:
                 QMessageBox.critical(self, "Помилка", f"Не вдалося відкрити Менеджер Ліцензій:\n{e}")

    # Optional: Slot to handle logs from License Manager
    # def handle_license_log(self, level, message):
    #     prefix = "[LicenseMgr]"
    #     self.log_message(f"{prefix} [{level.upper()}] {message}")


    def time_selection_changed(self):
        if not self.auto_start_timer.isActive():
            self.update_timer_label_when_stopped()


    def check_drive_availability(self):
        self.d_exists = os.path.exists("D:\\")
        self.e_exists = os.path.exists("E:\\")

        self.btn_drive_d.setEnabled(self.d_exists)
        self.btn_drive_e.setEnabled(self.e_exists)

        self.update_drive_buttons_visuals()


    def update_drive_buttons_visuals(self):
        self.btn_drive_d.setText(f"Диск D: {'🟢' if self.d_exists else '🔴'}")
        self.btn_drive_e.setText(f"Диск E: {'🟢' if self.e_exists else '🔴'}")

        for button in self.btn_group.buttons():
            drive_letter = chr(self.btn_group.id(button))
            is_selected = (drive_letter == self.selected_drive)
            if is_selected:
                button.setStyleSheet("font-weight: bold; border: 2px solid blue;")
            else:
                # Reset style, consider inheriting default look or using a less specific style
                button.setStyleSheet("") # Reset to default or use "font-weight: normal; border: none;"


    def set_selected_drive(self, drive_id):
        drive_letter = chr(drive_id)
        if (drive_letter == 'D' and self.d_exists) or \
           (drive_letter == 'E' and self.e_exists):
            if drive_letter != self.selected_drive:
                self.selected_drive = drive_letter
                self.log_message(f"Обрано основний диск: {self.selected_drive}:")
                self.update_drive_buttons_visuals()
                self.stop_auto_timer()
        else:
             self.log_message(f"⚠️ Диск {drive_letter}: недоступний.")
             self.update_drive_buttons_visuals()


    def toggle_timer(self):
        if self.auto_start_timer.isActive():
            self.stop_auto_timer()
        else:
            # Check if autostart is globally disabled by settings before starting
            app_settings = self.settings.get('application', DEFAULT_SETTINGS['application'])
            if not app_settings.get('autostart_timer_enabled', True):
                 self.log_message("ℹ️ Таймер не можна запустити вручну, коли автозапуск вимкнено в налаштуваннях.")
                 # Optionally show a QMessageBox here too
                 return
            self.start_auto_timer()


    def start_now(self):
        if self.mover_thread and self.mover_thread.isRunning():
             QMessageBox.warning(self, "Зайнято", "Процес переміщення вже запущено.")
             return
        self.stop_auto_timer()
        self.start_process()


    def start_auto_timer(self):
        if self.mover_thread and self.mover_thread.isRunning():
             self.log_message("ℹ️ Неможливо запустити таймер під час переміщення.")
             return

        # Explicitly check the setting again before starting
        app_settings = self.settings.get('application', DEFAULT_SETTINGS['application'])
        if not app_settings.get('autostart_timer_enabled', True):
             self.log_message("ℹ️ Запуск таймера заблоковано налаштуваннями програми (Автозапуск вимкнено).")
             self.stop_auto_timer(log_disabled=True) # Ensure UI reflects disabled state
             return

        minutes_text = self.time_combo.currentText()
        try:
             minutes = int(minutes_text.split()[0])
        except:
             minutes = 3
             self.log_message("⚠️ Не вдалося розпізнати час таймера, встановлено 3 хв.")

        self.remaining_time = minutes * 60
        if self.remaining_time <= 0:
             self.remaining_time = 180
        self.timer_label.setText(f"До автоматичного старту: {self.format_time()}")
        self.timer_control_btn.setText("⏱️ Стоп таймер")
        self.time_combo.setEnabled(False)
        self.btn_drive_d.setEnabled(False)
        self.btn_drive_e.setEnabled(False)
        self.auto_start_timer.start(1000)


    def stop_auto_timer(self, log_disabled=False):
        self.auto_start_timer.stop()
        if log_disabled:
             self.timer_label.setText("Автозапуск вимкнено (Налаштування)")
        else:
             self.update_timer_label_when_stopped()

        self.timer_control_btn.setText("▶️ Старт таймер")
        self.time_combo.setEnabled(True)
        self.check_drive_availability()


    def update_timer(self):
        self.remaining_time -= 1
        if self.remaining_time <= 0:
            self.auto_start_timer.stop()
            self.start_process()
            return
        self.timer_label.setText(f"До автоматичного старту: {self.format_time()}")


    def format_time(self):
        mins, secs = divmod(self.remaining_time, 60)
        return f"{mins:02}:{secs:02}"



    def check_schedule(self):
        app_settings = self.settings.get('application', DEFAULT_SETTINGS['application'])
        schedule_cfg = self.settings.get('schedule', DEFAULT_SETTINGS['schedule'])
        schedule_type = schedule_cfg.get('type', 'disabled')

        # Do not run if both the schedule and the autostart timer are disabled
        if schedule_type == 'disabled' or not app_settings.get('autostart_timer_enabled', True):
            return

        now = datetime.now()
        today = now.date()
        current_time = QTime.currentTime()
        self.log_message(f"ℹ️ Перевірка розкладу: {today.strftime('%Y-%m-%d')} {current_time.toString('HH:mm:ss')}")


        # Reset last run date if it's a new day.
        if self.last_scheduled_run_date and self.last_scheduled_run_date < today:
            self.last_scheduled_run_date = None

        # Check if today is a scheduled day
        if not is_scheduled_day(schedule_cfg):
            return

        # Have we already run for today's schedule?
        if self.last_scheduled_run_date == today:
            return

        start_time = QTime.fromString(schedule_cfg.get('time_start', '22:00'), "HH:mm")
        end_time = QTime.fromString(schedule_cfg.get('time_end', '23:00'), "HH:mm")

        # If we are within the execution window, check for idle
        if start_time <= current_time <= end_time:
            cpu_usage = psutil.cpu_percent(interval=1)
            self.log_message(f"ℹ️ У вікні розкладу. ЦП: {cpu_usage}%.")
            if cpu_usage < 15.0:
                self.log_message("⏰ Низьке завантаження ЦП. Запуск таймера за розкладом.")
                self.start_auto_timer()
                self.last_scheduled_run_date = today
        # If we are past the window and haven't run, run now.
        elif current_time > end_time:
            self.log_message("⚠️ Вікно розкладу пропущено. Запускаємо таймер зараз, оскільки він не був запущений через високе завантаження ЦП.")
            self.start_auto_timer()
            self.last_scheduled_run_date = today


    def start_process(self):
        if not self.selected_drive:
            self.log_message("❌ Помилка: Не вдалося визначити цільовий диск.")
            self.check_drive_availability()
            return

        if self.mover_thread and self.mover_thread.isRunning():
            self.log_message("⚠️ Процес вже запущено.")
            return

        self.log_message(f"\n🚀 Початок переміщення на диск {self.selected_drive}:...")
        self.start_now_btn.setEnabled(False)
        self.timer_control_btn.setEnabled(False)
        self.time_combo.setEnabled(False)
        self.btn_drive_d.setEnabled(False)
        self.btn_drive_e.setEnabled(False)

        self.mover_thread = FileMover(target_drive=self.selected_drive, fallback_drive='C', settings=self.settings.copy())
        self.mover_thread.update_signal.connect(self.log_message)
        self.mover_thread.finished_signal.connect(self.process_finished)
        self.mover_thread.start()


    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{timestamp}] {message}")
        QApplication.processEvents()


    def process_finished(self, success, errors, path):
        self.log_message("\n🏁 Результат:")
        self.log_message(f"✅ Успішно: {success}")
        if errors > 0:
            self.log_message(f"❌ Помилок: {errors}")
        if not path.startswith("Error"):
             self.log_message(f"📁 Збережено до: {path}")
        else:
             self.log_message(f"❌ {path}")

        stats_dialog = RunStatisticsDialog(success, errors, path, self)
        stats_dialog.exec_()
        self.close()


    def closeEvent(self, event):
        # Optional: Add confirmation before closing if needed
        pass


if __name__ == "__main__":
    # If started with --background-run, execute headless task check
    if '--background-run' in sys.argv:
        from PyQt5.QtCore import QCoreApplication

        def run_background_task():
            app = QCoreApplication(sys.argv)
            runner = BackgroundTaskRunner()
            if not runner.check_and_run():
                # If no task was started, quit immediately.
                QCoreApplication.instance().quit()
            sys.exit(app.exec_())

        run_background_task()

    else:  # Otherwise, start the GUI
        app = QApplication(sys.argv)
        is_scheduled_run = '--scheduled-run' in sys.argv
        window = MainWindow(is_scheduled_run=is_scheduled_run)
        window.show()
        sys.exit(app.exec_())