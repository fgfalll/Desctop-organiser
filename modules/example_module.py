from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit
from PyQt5.QtCore import Qt

"""MODULE_MANIFEST_START
{
  "name": "example_module",
  "version": "1.0.0",
  "description": "Приклад модуля для демонстрації архітектури з вбудованим маніфестом",
  "author": "Desktop Organizer Team",
  "category": "Demo",
  "menu_text": "&Приклад Модуля...",
  "main_class": "ExampleModule",
  "dependencies": [],
  "python_version": "3.8+",
  "permissions": [
    "file_system_read"
  ]
}
MODULE_MANIFEST_END"""


class ExampleModule(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(991, 701)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("🎯 Приклад Модуля v2.0")
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin: 20px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "Це приклад модуля з новою архітектурою:\n\n"
            "✅ Вбудований маніфест (без окремих JSON файлів)\n"
            "✅ Спільне віртуальне середовище для всіх модулів\n"
            "✅ Автоматичне видалення пакетів при видаленні модуля\n"
            "✅ Управління віртуальним середовищем через налаштування\n"
            "✅ Повна незалежність від основного додатку"
        )
        desc.setStyleSheet("font-size: 14px; margin: 20px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Interactive element
        self.counter = 0
        self.button = QPushButton("Натисни мене!")
        self.button.clicked.connect(self.on_button_click)
        self.button.setStyleSheet("font-size: 16px; padding: 10px; margin: 20px;")
        layout.addWidget(self.button)

        # Status display
        self.status_label = QLabel("Кількість натискань: 0")
        self.status_label.setStyleSheet("font-size: 14px; margin: 10px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Log area
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(200)
        self.log_area.append("🚀 Модуль успішно завантажено!")
        self.log_area.append("📦 Маніфест вбудовано в файл модуля")
        self.log_area.append("🔗 Використовує спільне віртуальне середовище")
        layout.addWidget(self.log_area)

        layout.addStretch()

    def on_button_click(self):
        self.counter += 1
        self.status_label.setText(f"Кількість натискань: {self.counter}")
        self.log_area.append(f"🔘 Кнопка натиснута {self.counter} раз(ів)")

        # Change button text after a few clicks
        if self.counter >= 5:
            self.button.setText("Відмінно! Продовжуй!")
            self.log_area.append("🎉 Досягнуто 5 натискань!")

        if self.counter >= 10:
            self.log_area.append("🏆 Ви - чемпіон натискань!")