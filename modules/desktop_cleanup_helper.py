"""MODULE_MANIFEST_START
{
  "name": "desktop_cleanup_helper",
  "version": "2.3.2",
  "description": "Комплексний інструмент для очищення та керування архівами робочого столу з розширеною аналітикою файлів, виявленням дублікатів та можливостями стиснення",
  "author": "Команда Desktop Organizer",
  "category": "Utility",
  "menu_text": "Менеджер Архіву Робочого Столу",
  "main_class": "CleanupHelperWidget",
  "dependencies": [
    "pandas>=1.3.0",
    "matplotlib>=3.5.0",
    "tqdm>=4.62.0",
    "seaborn>=0.11.0",
    "compress",
    "humanize>=3.2.0"
  ],
  "python_version": "3.8+",
  "permissions": [
    "file_system_read",
    "file_system_write",
    "system_info"
  ]
}
MODULE_MANIFEST_END"""

import sys
import os
import json
import yaml
import shutil
import hashlib
import threading
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import humanize

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QLabel,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QProgressBar,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QLineEdit,
    QGroupBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QDateEdit,
    QDialog,
    QMenu,
    QListWidget,
    QListWidgetItem,
    QApplication,
    QToolTip,
)
from PyQt5.QtCore import (
    Qt,
    QThread,
    pyqtSignal,
    QTimer,
    QDate,
    QMutex,
    QMutexLocker,
    QRect,
    QPropertyAnimation,
    QEasingCurve,
)
from PyQt5.QtGui import QIcon, QFont, QPixmap, QPainter, QColor, QPen, QBrush, QCursor

import logging
import logging.handlers

LOG_DIR = os.path.join(os.path.expanduser("~"), ".DesktopOrganizer", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            os.path.join(LOG_DIR, "modules.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
            errors="replace",
        ),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger("DesktopOrganizer.Modules")

# Import dependencies with fallback handling
try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None


try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

try:
    import compress

    COMPRESS_AVAILABLE = True
except ImportError:
    COMPRESS_AVAILABLE = False
    compress = None


try:
    import humanize

    HUMANIZE_AVAILABLE = True
except ImportError:
    HUMANIZE_AVAILABLE = False
    humanize = None


class SpinningWheel(QWidget):
    """Custom spinning wheel widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.rotate)
        self.setFixedSize(40, 40)

    def start_rotation(self):
        self.timer.start(50)  # Rotate every 50ms

    def stop_rotation(self):
        self.timer.stop()

    def rotate(self):
        self.angle = (self.angle + 10) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw background circle
        painter.setPen(QPen(QColor(240, 240, 240), 2))
        painter.setBrush(QBrush(QColor(250, 250, 250)))
        painter.drawEllipse(2, 2, 36, 36)

        # Draw spinning arc
        painter.setPen(QPen(QColor(52, 152, 219), 3))
        painter.setBrush(Qt.NoBrush)
        rect = QRect(5, 5, 30, 30)
        painter.drawArc(rect, self.angle * 16, 120 * 16)


class ScanSplashScreen(QWidget):
    """Splash screen for scan operations"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Use different window flags to ensure visibility
        self.setWindowFlags(
            Qt.SplashScreen | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Auto-sizing will be calculated after UI initialization
        self.setMinimumSize(350, 100)
        self.setMaximumSize(600, 200)

        self.initUI()
        self.calculate_auto_size()

        # Center on parent or screen
        self.center_on_parent()

    def center_on_parent(self):
        """Center the splash screen on parent or screen"""
        try:
            if self.parent():
                # Get the parent window's global geometry
                parent_widget = self.parent()
                while parent_widget.parent():
                    parent_widget = parent_widget.parent()

                parent_rect = parent_widget.geometry()
                splash_width = self.width()
                splash_height = self.height()

                # Calculate center position
                x = parent_rect.x() + (parent_rect.width() - splash_width) // 2
                y = parent_rect.y() + (parent_rect.height() - splash_height) // 2

            else:
                # Center on desktop
                from PyQt5.QtWidgets import QDesktopWidget

                screen = QDesktopWidget().screenGeometry()
                splash_width = self.width()
                splash_height = self.height()

                x = (screen.width() - splash_width) // 2
                y = (screen.height() - splash_height) // 2

            self.move(x, y)

        except Exception as e:
            # Fallback to top-left corner
            self.move(100, 100)

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Main container with no borders
        self.container = QWidget()
        self.container.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.95);
                border-radius: 10px;
            }
        """)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(
            30, 25, 30, 25
        )  # More vertical space for text

        # Title and spinner layout
        title_layout = QHBoxLayout()

        # Spinning wheel
        self.spinning_wheel = SpinningWheel()
        title_layout.addWidget(self.spinning_wheel)

        # Title label
        self.title_label = QLabel("🔍 Сканування файлів")
        self.title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
                margin-left: 10px;
            }
        """)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        container_layout.addLayout(title_layout)

        # Progress label - expanded space
        self.progress_label = QLabel("Підготовка до сканування")
        self.progress_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #7f8c8d;
                margin-top: 15px;
                padding: 10px;
                background-color: rgba(236, 240, 241, 0.5);
                border-radius: 5px;
                min-height: 40px;
            }
        """)
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setWordWrap(True)  # Allow text wrapping
        container_layout.addWidget(self.progress_label)

        layout.addWidget(self.container)

        # Add shadow effect
        self.setStyleSheet("""
            ScanSplashScreen {
                background-color: transparent;
            }
        """)

    def calculate_auto_size(self):
        """Calculate optimal size based on content"""
        # Ensure layout is updated
        self.container.layout().update()
        self.container.layout().activate()

        # Calculate required size
        title_width = self.title_label.sizeHint().width()
        progress_width = self.progress_label.sizeHint().width()

        # Add margins and padding
        required_width = (
            max(title_width, progress_width) + 100
        )  # Extra space for spinner and margins
        required_width = max(350, min(600, required_width))  # Clamp between min and max

        # Calculate height based on content
        title_height = self.title_label.sizeHint().height()
        progress_height = self.progress_label.sizeHint().height()
        required_height = (
            title_height + progress_height + 80
        )  # Extra space for margins and spinner
        required_height = max(
            100, min(200, required_height)
        )  # Clamp between min and max

        self.setFixedSize(required_width, required_height)

    def update_progress(self, value, message):
        """Update progress message"""
        self.progress_label.setText(message)
        # Recalculating size on each update causes geometry errors on Windows.
        # The initial size is made sufficient by having a larger min-height.
        # self.calculate_auto_size()

    def hideEvent(self, event):
        """Stop spinning when hidden"""
        super().hideEvent(event)
        self.spinning_wheel.stop_rotation()


class ArchiveSplashScreen(QWidget):
    """Splash screen for archive viewer operations"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Use different window flags to ensure visibility
        self.setWindowFlags(
            Qt.SplashScreen | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Auto-sizing will be calculated after UI initialization
        self.setMinimumSize(350, 100)
        self.setMaximumSize(600, 200)

        self.initUI()
        self.calculate_auto_size()

        # Center on parent or screen
        self.center_on_parent()

    def center_on_parent(self):
        """Center the splash screen on parent or screen"""
        try:
            if self.parent():
                # Get the parent window's global geometry
                parent_widget = self.parent()
                while parent_widget.parent():
                    parent_widget = parent_widget.parent()

                parent_rect = parent_widget.geometry()
                splash_width = self.width()
                splash_height = self.height()

                # Calculate center position
                x = parent_rect.x() + (parent_rect.width() - splash_width) // 2
                y = parent_rect.y() + (parent_rect.height() - splash_height) // 2

            else:
                # Center on desktop
                from PyQt5.QtWidgets import QDesktopWidget

                screen = QDesktopWidget().screenGeometry()
                splash_width = self.width()
                splash_height = self.height()

                x = (screen.width() - splash_width) // 2
                y = (screen.height() - splash_height) // 2

            self.move(x, y)

        except Exception as e:
            # Fallback to top-left corner
            self.move(100, 100)

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Main container with no borders
        self.container = QWidget()
        self.container.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.95);
                border-radius: 10px;
            }
        """)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(
            30, 25, 30, 25
        )  # More vertical space for text

        # Title and spinner layout
        title_layout = QHBoxLayout()

        # Spinning wheel
        self.spinning_wheel = SpinningWheel()
        title_layout.addWidget(self.spinning_wheel)

        # Title label
        self.title_label = QLabel("📂 Пошук в архівах")
        self.title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
                margin-left: 10px;
            }
        """)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        container_layout.addLayout(title_layout)

        # Progress label - expanded space
        self.progress_label = QLabel("Підготовка до пошуку")
        self.progress_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #7f8c8d;
                margin-top: 15px;
                padding: 10px;
                background-color: rgba(236, 240, 241, 0.5);
                border-radius: 5px;
                min-height: 40px;
            }
        """)
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setWordWrap(True)  # Allow text wrapping
        container_layout.addWidget(self.progress_label)

        layout.addWidget(self.container)

        # Add shadow effect
        self.setStyleSheet("""
            ArchiveSplashScreen {
                background-color: transparent;
            }
        """)

    def calculate_auto_size(self):
        """Calculate optimal size based on content"""
        # Ensure layout is updated
        self.container.layout().update()
        self.container.layout().activate()

        # Calculate required size
        title_width = self.title_label.sizeHint().width()
        progress_width = self.progress_label.sizeHint().width()

        # Add margins and padding
        required_width = (
            max(title_width, progress_width) + 100
        )  # Extra space for spinner and margins
        required_width = max(350, min(600, required_width))  # Clamp between min and max

        # Calculate height based on content
        title_height = self.title_label.sizeHint().height()
        progress_height = self.progress_label.sizeHint().height()
        required_height = (
            title_height + progress_height + 80
        )  # Extra space for margins and spinner
        required_height = max(
            100, min(200, required_height)
        )  # Clamp between min and max

        self.setFixedSize(required_width, required_height)

    def update_progress(self, value, message):
        """Update progress message"""
        self.progress_label.setText(message)
        # Recalculating size on each update causes geometry errors on Windows.
        # The initial size is made sufficient by having a larger min-height.
        # self.calculate_auto_size()

    def showEvent(self, event):
        """Start spinning when shown"""
        super().showEvent(event)
        self.spinning_wheel.start_rotation()

    def hideEvent(self, event):
        """Stop spinning when hidden"""
        super().hideEvent(event)
        self.spinning_wheel.stop_rotation()


class DuplicateFinderSplashScreen(QWidget):
    """Splash screen for duplicate finder operations"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Use different window flags to ensure visibility
        self.setWindowFlags(
            Qt.SplashScreen | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Auto-sizing will be calculated after UI initialization
        self.setMinimumSize(350, 100)
        self.setMaximumSize(600, 200)

        self.initUI()
        self.calculate_auto_size()

        # Center on parent or screen
        self.center_on_parent()

    def center_on_parent(self):
        """Center the splash screen on parent or screen"""
        try:
            if self.parent():
                # Get the parent window's global geometry
                parent_widget = self.parent()
                while parent_widget.parent():
                    parent_widget = parent_widget.parent()

                parent_rect = parent_widget.geometry()
                splash_width = self.width()
                splash_height = self.height()

                # Calculate center position
                x = parent_rect.x() + (parent_rect.width() - splash_width) // 2
                y = parent_rect.y() + (parent_rect.height() - splash_height) // 2

            else:
                # Center on desktop
                from PyQt5.QtWidgets import QDesktopWidget

                screen = QDesktopWidget().screenGeometry()
                splash_width = self.width()
                splash_height = self.height()

                x = (screen.width() - splash_width) // 2
                y = (screen.height() - splash_height) // 2

            self.move(x, y)

        except Exception as e:
            # Fallback to top-left corner
            self.move(100, 100)

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Main container with no borders
        self.container = QWidget()
        self.container.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.95);
                border-radius: 10px;
            }
        """)
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(
            30, 25, 30, 25
        )  # More vertical space for text

        # Title and spinner layout
        title_layout = QHBoxLayout()

        # Spinning wheel
        self.spinning_wheel = SpinningWheel()
        title_layout.addWidget(self.spinning_wheel)

        # Title label
        self.title_label = QLabel("🎯 Пошук дублікатів")
        self.title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
                margin-left: 10px;
            }
        """)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        container_layout.addLayout(title_layout)

        # Progress label - expanded space
        self.progress_label = QLabel("Підготовка до пошуку")
        self.progress_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #7f8c8d;
                margin-top: 15px;
                padding: 10px;
                background-color: rgba(236, 240, 241, 0.5);
                border-radius: 5px;
                min-height: 40px;
            }
        """)
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setWordWrap(True)  # Allow text wrapping
        container_layout.addWidget(self.progress_label)

        layout.addWidget(self.container)

        # Add shadow effect
        self.setStyleSheet("""
            DuplicateFinderSplashScreen {
                background-color: transparent;
            }
        """)

    def calculate_auto_size(self):
        """Calculate optimal size based on content"""
        # Ensure layout is updated
        self.container.layout().update()
        self.container.layout().activate()

        # Calculate required size
        title_width = self.title_label.sizeHint().width()
        progress_width = self.progress_label.sizeHint().width()

        # Add margins and padding
        required_width = (
            max(title_width, progress_width) + 100
        )  # Extra space for spinner and margins
        required_width = max(350, min(600, required_width))  # Clamp between min and max

        # Calculate height based on content
        title_height = self.title_label.sizeHint().height()
        progress_height = self.progress_label.sizeHint().height()
        required_height = (
            title_height + progress_height + 80
        )  # Extra space for margins and spinner
        required_height = max(
            100, min(200, required_height)
        )  # Clamp between min and max

        self.setFixedSize(required_width, required_height)

    def update_progress(self, value, message):
        """Update progress message"""
        self.progress_label.setText(message)
        # Recalculating size on each update causes geometry errors on Windows.
        # The initial size is made sufficient by having a larger min-height.
        # self.calculate_auto_size()

    def showEvent(self, event):
        """Start spinning when shown"""
        super().showEvent(event)
        self.spinning_wheel.start_rotation()

    def hideEvent(self, event):
        """Stop spinning when hidden"""
        super().hideEvent(event)
        self.spinning_wheel.stop_rotation()


class ArchiveTreeBuilder(QThread):
    """Thread for building archive tree structure"""

    progress_updated = pyqtSignal(int, str)
    tree_built = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(
        self, scan_path: str, search_term: str = "", filters: dict = None, parent=None
    ):
        super().__init__(parent)
        self.scan_path = scan_path
        self.search_term = search_term
        self.filters = filters or {}
        self.should_stop = False

    def run(self):
        """Build archive tree in background thread"""
        try:
            current_time = time.time()
            use_cache = (
                hasattr(self.parent(), "_last_scan_path")
                and self.parent()._last_scan_path == self.scan_path
                and hasattr(self.parent(), "_file_cache")
                and self.parent()._file_cache
                and hasattr(self.parent(), "_cache_timestamp")
                and current_time - self.parent()._cache_timestamp < 300
            )

            if not use_cache:
                self.progress_updated.emit(25, "Сканування файлів")
                self._build_file_cache()
            else:
                self.progress_updated.emit(50, "Використання кешу")

            self.progress_updated.emit(75, "Побудова дерева файлів")
            tree_widget = self._build_tree_recursive()
            self.tree_built.emit(tree_widget)

        except Exception as e:
            self.error_occurred.emit(str(e))

    def _build_file_cache(self):
        """Build a cache of the file structure for fast searching"""
        if not hasattr(self.parent(), "_file_cache"):
            self.parent()._file_cache = {}
        if not hasattr(self.parent(), "_search_index"):
            self.parent()._search_index = {}

        self.parent()._file_cache.clear()
        self.parent()._search_index.clear()
        self.parent()._last_scan_path = self.scan_path
        self.parent()._cache_timestamp = time.time()

        def _scan_directory(path: str, cache_dict: dict):
            """Recursively scan directory and build cache"""
            try:
                for item_name in os.listdir(path):
                    if self.should_stop:
                        return

                    item_path = os.path.join(path, item_name)
                    if os.path.exists(item_path):
                        is_dir = os.path.isdir(item_path)

                        # Get file metadata
                        try:
                            stat_info = os.stat(item_path)
                            file_size = stat_info.st_size
                            modified_time = stat_info.st_mtime
                            modified_str = datetime.fromtimestamp(
                                modified_time
                            ).strftime("%Y-%m-%d %H:%M")
                        except (OSError, PermissionError):
                            file_size = None
                            modified_time = None
                            modified_str = "Невідомо"

                        cache_dict[item_path] = {
                            "path": item_path,
                            "is_dir": is_dir,
                            "name_lower": item_name.lower(),
                            "size": file_size,
                            "modified_timestamp": modified_time,
                            "modified": modified_str,
                        }

                        # Add to search index for faster lookups
                        name_lower = item_name.lower()
                        for i in range(len(name_lower)):
                            for j in range(
                                i + 1, min(i + 20, len(name_lower) + 1)
                            ):  # Limit substring length
                                substring = name_lower[i:j]
                                if substring not in self.parent()._search_index:
                                    self.parent()._search_index[substring] = []
                                self.parent()._search_index[substring].append(item_path)

                        if is_dir:
                            _scan_directory(item_path, cache_dict)

            except (PermissionError, OSError) as e:
                # Skip directories we can't access
                pass

        _scan_directory(self.scan_path, self.parent()._file_cache)

    def _build_tree_recursive(self):
        """Build the tree structure from cache based on filters."""
        from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem
        from pathlib import Path

        # Step 1: Find all paths that should be visible
        visible_paths = set()
        all_cached_paths = self.parent()._file_cache

        # If no filters are active, show everything
        if not self.search_term and not any(self.filters.values()):
            visible_paths.update(all_cached_paths.keys())
        else:
            # First, find all files that match the filters
            matching_files = set()
            for item_path, item_data in all_cached_paths.items():
                if item_data.get("is_dir", False):
                    continue

                # Apply text search on file name
                if (
                    self.search_term
                    and self.search_term.lower() not in item_data["name_lower"]
                ):
                    continue

                # Apply file type filter
                if self.filters.get("file_types"):
                    ext = os.path.splitext(item_data["name_lower"])[1]
                    if ext not in self.filters["file_types"]:
                        continue

                # Apply date filter
                if (
                    item_data.get("modified_timestamp")
                    and item_data["modified_timestamp"] is not None
                ):
                    ts = item_data["modified_timestamp"]
                    min_date = self.filters.get("min_date")
                    max_date = self.filters.get("max_date")
                    if min_date and ts < min_date.timestamp():
                        continue
                    if max_date and ts > max_date.timestamp():
                        continue

                matching_files.add(item_path)

            visible_paths.update(matching_files)

            # Second, add all parent directories of matching files
            scan_path_obj = Path(self.scan_path)
            for path_str in matching_files:
                try:
                    p = Path(path_str).parent
                    while p != p.parent:  # Stop at root
                        if p in visible_paths:  # Optimization
                            break
                        visible_paths.add(str(p))
                        if p == scan_path_obj:
                            break
                        p = p.parent
                except Exception:
                    continue  # Ignore errors from invalid paths

            # Third, add any directories that match the text search term directly
            if self.search_term:
                for item_path, item_data in all_cached_paths.items():
                    if (
                        item_data.get("is_dir", False)
                        and self.search_term.lower() in item_data["name_lower"]
                    ):
                        visible_paths.add(item_path)

        # Step 2: Build the tree using only the visible paths
        tree_widget = QTreeWidget()
        tree_widget.clear()

        def _build_level(path: str, parent_item):
            """Recursively build tree level from visible paths."""
            child_paths = []
            for p in visible_paths:
                if os.path.dirname(p) == path:
                    child_paths.append(p)

            if not child_paths:
                return

            child_data = [
                all_cached_paths[p] for p in child_paths if p in all_cached_paths
            ]
            child_data.sort(
                key=lambda x: (not x.get("is_dir", False), x.get("name_lower", ""))
            )

            for item_data in child_data:
                if self.should_stop:
                    return

                item_path = item_data["path"]
                item_name = os.path.basename(item_path)
                is_dir = item_data["is_dir"]

                tree_item = QTreeWidgetItem(parent_item)
                tree_item.setData(0, Qt.UserRole, item_path)

                if is_dir:
                    tree_item.setText(0, f"📁 {item_name}")
                    tree_item.setData(1, Qt.DisplayRole, "Папка")
                    _build_level(item_path, tree_item)
                else:
                    file_ext = os.path.splitext(item_name)[1].lower()
                    icon = self._get_file_icon(file_ext)
                    tree_item.setText(0, f"{icon} {item_name}")

                    size_str = "Невідомо"
                    if item_data.get("size") is not None:
                        try:
                            size_str = humanize.naturalsize(item_data["size"])
                        except (TypeError, ValueError):
                            pass
                    tree_item.setData(1, Qt.DisplayRole, size_str)
                    tree_item.setData(
                        2, Qt.DisplayRole, item_data.get("modified", "Невідомо")
                    )

        _build_level(self.scan_path, tree_widget.invisibleRootItem())
        return tree_widget

    def _get_file_icon(self, extension: str) -> str:
        """Get appropriate icon for file extension"""
        icon_map = {
            ".txt": "📄",
            ".doc": "📝",
            ".docx": "📝",
            ".pdf": "📋",
            ".jpg": "🖼️",
            ".jpeg": "🖼️",
            ".png": "🖼️",
            ".gif": "🖼️",
            ".bmp": "🖼️",
            ".mp4": "🎬",
            ".avi": "🎬",
            ".mkv": "🎬",
            ".mov": "🎬",
            ".mp3": "🎵",
            ".wav": "🎵",
            ".flac": "🎵",
            ".aac": "🎵",
            ".zip": "🗜️",
            ".rar": "🗜️",
            ".7z": "🗜️",
            ".tar": "🗜️",
            ".gz": "🗜️",
            ".exe": "⚙️",
            ".msi": "⚙️",
            ".bat": "⚙️",
            ".cmd": "⚙️",
            ".py": "🐍",
            ".js": "🌐",
            ".html": "🌐",
            ".css": "🎨",
        }
        return icon_map.get(extension, "📄")

    def stop(self):
        """Stop the tree building process"""
        self.should_stop = True


class FileScanner(QThread):
    """Thread for scanning files and directories"""

    progress_updated = pyqtSignal(int, str)
    file_found = pyqtSignal(object)
    scanning_finished = pyqtSignal(object)

    def __init__(self, scan_path: str, file_types: List[str] = None):
        super().__init__()
        self.scan_path = scan_path
        self.file_types = file_types or ["*"]
        self.should_stop = False
        self.results = {}
        self.scanned_files = 0
        self.total_estimated_files = 0

    def run(self):
        """Scan files in the specified path"""
        try:
            # Quick estimation of total files
            self.progress_updated.emit(0, "Оцінка кількості файлів...")
            self.total_estimated_files = self._estimate_file_count(self.scan_path)

            # Now do the actual scanning
            self.scanned_files = 0
            self.results = self._scan_directory(self.scan_path)
            self.scanning_finished.emit(self.results)
        except Exception as e:
            self.progress_updated.emit(0, f"Помилка під час сканування: {str(e)}")

    def _estimate_file_count(self, directory: str) -> int:
        """Quick estimation of total files for progress calculation"""
        try:
            file_count = 0
            for root, dirs, files in os.walk(directory):
                if self.should_stop:
                    break
                file_count += len(files)
                if file_count > 10000:  # Cap at 10000 for performance
                    break
            return max(file_count, 1)  # Ensure at least 1
        except:
            return 1

    def _scan_directory(self, directory: str) -> Dict:
        """Recursively scan directory and collect file information"""
        files_data = {
            "total_files": 0,
            "total_size": 0,
            "file_types": {},
            "large_files": [],
            "old_files": [],
            "files": [],
        }

        try:
            for root, dirs, files in os.walk(directory):
                if self.should_stop:
                    break

                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        if os.path.exists(file_path):
                            file_info = self._analyze_file(file_path)
                            if file_info:
                                files_data["files"].append(file_info)
                                files_data["total_files"] += 1
                                files_data["total_size"] += file_info["size"]

                                # Categorize by file type
                                ext = file_info["extension"].lower()
                                if ext not in files_data["file_types"]:
                                    files_data["file_types"][ext] = {
                                        "count": 0,
                                        "size": 0,
                                    }
                                files_data["file_types"][ext]["count"] += 1
                                files_data["file_types"][ext]["size"] += file_info[
                                    "size"
                                ]

                                # Track large files (>10MB)
                                if file_info["size"] > 10 * 1024 * 1024:
                                    files_data["large_files"].append(file_info)

                                # Track old files (>1 year)
                                file_age = datetime.now() - file_info["modified"]
                                if file_age.days > 365:
                                    files_data["old_files"].append(file_info)

                                self.scanned_files += 1
                                # Calculate progress as percentage
                                progress_percentage = min(
                                    int(
                                        (
                                            self.scanned_files
                                            / self.total_estimated_files
                                        )
                                        * 100
                                    ),
                                    95,
                                )  # Cap at 95% until completion
                                self.progress_updated.emit(
                                    progress_percentage,
                                    f"Сканування: {file_info['name']}",
                                )
                    except Exception as e:
                        continue

        except Exception as e:
            self.progress_updated.emit(0, f"Error scanning directory: {str(e)}")

        return files_data

    def _analyze_file(self, file_path: str) -> Optional[Dict]:
        """Analyze a single file and return metadata"""
        try:
            stat = os.stat(file_path)
            return {
                "path": file_path,
                "name": os.path.basename(file_path),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "created": datetime.fromtimestamp(stat.st_ctime),
                "extension": os.path.splitext(file_path)[1],
                "is_directory": os.path.isdir(file_path),
            }
        except Exception:
            return None

    def stop(self):
        """Stop the scanning process"""
        self.should_stop = True


class DuplicateFileFinder(QThread):
    """Thread for finding duplicate files"""

    progress_updated = pyqtSignal(int, str)
    duplicate_found = pyqtSignal(str, object)
    finished = pyqtSignal(object)

    def __init__(self, file_list: List[str], check_content: bool = True):
        super().__init__()
        self.file_list = file_list
        self.check_content = check_content
        self.should_stop = False
        self.duplicates = {}

    def run(self):
        """Find duplicate files using hash comparison"""
        try:
            self._find_duplicates()
        except Exception as e:
            # Try to emit an error message to the user via the progress signal
            try:
                self.progress_updated.emit(0, f"Error finding duplicates: {str(e)}")
            except Exception:
                pass  # Signal might be disconnected
        finally:
            # Always emit finished signal to unblock UI
            self.finished.emit(self.duplicates)

    def _find_duplicates(self):
        """Find duplicate files by size, and optionally by hash."""
        files_by_size = {}
        total_files = len(self.file_list)

        # --- Pass 1: Group files by size ---
        for i, file_path in enumerate(self.file_list):
            if self.should_stop:
                return

            self.progress_updated.emit(
                int((i / total_files) * 20),
                f"Аналіз розміру: {os.path.basename(file_path)}",
            )  # Progress up to 20%

            try:
                # Skip zero-byte files
                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    continue

                if file_size not in files_by_size:
                    files_by_size[file_size] = []
                files_by_size[file_size].append(file_path)
            except OSError:
                continue  # Skip files that can't be accessed

        # --- Pass 2: Find duplicates in same-size groups ---
        potential_duplicates = {
            size: files for size, files in files_by_size.items() if len(files) > 1
        }

        if not self.check_content:
            # If not checking content, report all same-sized files as duplicates
            for size, files in potential_duplicates.items():
                # Use size as the "hash" key for reporting
                group_key = f"size:{size}"
                self.duplicate_found.emit(group_key, files)
                self.duplicates[group_key] = files
            self.progress_updated.emit(
                100, "Знайдено потенційні дублікати за розміром."
            )
            return

        # If checking content, proceed to hash
        processed_files = 0
        num_potential_files = sum(len(files) for files in potential_duplicates.values())

        for size, files in potential_duplicates.items():
            if self.should_stop:
                return

            file_hashes = {}
            for file_path in files:
                if self.should_stop:
                    return

                # Update progress based on number of files to be hashed
                progress = (
                    20 + int((processed_files / num_potential_files) * 80)
                    if num_potential_files > 0
                    else 100
                )
                self.progress_updated.emit(
                    progress, f"Хешування: {os.path.basename(file_path)}"
                )

                file_hash = self._calculate_file_hash(file_path)
                processed_files += 1

                if file_hash:
                    if file_hash not in file_hashes:
                        file_hashes[file_hash] = []
                    file_hashes[file_hash].append(file_path)

            # Report duplicates found by hash within the same-size group
            for file_hash, hashed_files in file_hashes.items():
                if len(hashed_files) > 1:
                    self.duplicate_found.emit(file_hash, hashed_files)
                    self.duplicates[file_hash] = hashed_files

    def _calculate_file_hash(
        self, file_path: str, chunk_size: int = 8192
    ) -> Optional[str]:
        """Calculate SHA256 hash of a file"""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception:
            return None

    def stop(self):
        """Stop the duplicate finding process"""
        self.should_stop = True


class FileCompressor(QThread):
    """Thread for compressing files using compress package"""

    progress_updated = pyqtSignal(int, str)
    compression_finished = pyqtSignal(str, bool)

    def __init__(
        self, files_to_compress: List[str], output_path: str, compression_level: int = 6
    ):
        super().__init__()
        self.files_to_compress = files_to_compress
        self.output_path = output_path
        self.compression_level = compression_level
        self.should_stop = False

    def run(self):
        """Compress files using compress package"""
        try:
            if not COMPRESS_AVAILABLE:
                self.progress_updated.emit(0, "Error: compress package not available")
                self.compression_finished.emit(self.output_path, False)
                return

            success = self._compress_files_with_compress()
            self.compression_finished.emit(self.output_path, success)
        except Exception as e:
            self.progress_updated.emit(0, f"Error during compression: {str(e)}")
            self.compression_finished.emit(self.output_path, False)

    def _compress_files_with_compress(self) -> bool:
        """Compress files using the compress package"""
        try:
            total_files = len(self.files_to_compress)
            processed = 0

            # Determine compression format based on file extension
            if self.output_path.endswith(".zip"):
                format_type = "zip"
            elif self.output_path.endswith(".tar.gz") or self.output_path.endswith(
                ".tgz"
            ):
                format_type = "tar.gz"
            elif self.output_path.endswith(".tar.bz2"):
                format_type = "tar.bz2"
            elif self.output_path.endswith(".tar.xz"):
                format_type = "tar.xz"
            elif self.output_path.endswith(".7z"):
                format_type = "7z"
            else:
                format_type = "zip"  # Default to ZIP

            # Create archive using compress package
            archive = compress.Archive(
                self.output_path, format=format_type, level=self.compression_level
            )

            # Add files to archive
            for file_path in self.files_to_compress:
                if self.should_stop:
                    return False

                try:
                    if os.path.exists(file_path):
                        # Determine archive name (relative path or basename)
                        if os.path.isfile(file_path):
                            archive_name = os.path.basename(file_path)
                        else:
                            # For directories, use the directory name as root
                            archive_name = os.path.basename(file_path.rstrip(os.sep))

                        # Add file or directory to archive
                        archive.add(file_path, arcname=archive_name)

                        processed += 1
                        progress = int((processed / total_files) * 100)
                        self.progress_updated.emit(
                            progress,
                            f"Compressing: {os.path.basename(file_path)} ({format_type.upper()})",
                        )
                    else:
                        self.progress_updated.emit(
                            progress,
                            f"Skipping: {os.path.basename(file_path)} (not found)",
                        )
                except Exception as e:
                    self.progress_updated.emit(
                        progress,
                        f"Warning: Failed to add {os.path.basename(file_path)}: {str(e)}",
                    )
                    continue

            # Close the archive to finalize compression
            archive.close()

            # Verify the archive was created successfully
            if (
                os.path.exists(self.output_path)
                and os.path.getsize(self.output_path) > 0
            ):
                return True
            else:
                return False

        except Exception as e:
            self.progress_updated.emit(0, f"Compression error: {str(e)}")
            return False

    def _compress_files_fallback(self) -> bool:
        """Fallback compression using zipfile if compress package fails"""
        try:
            import zipfile

            total_files = len(self.files_to_compress)
            processed = 0

            with zipfile.ZipFile(
                self.output_path,
                "w",
                zipfile.ZIP_DEFLATED,
                compresslevel=self.compression_level,
            ) as zipf:
                for file_path in self.files_to_compress:
                    if self.should_stop:
                        return False

                    try:
                        if os.path.exists(file_path):
                            if os.path.isfile(file_path):
                                zipf.write(file_path, os.path.basename(file_path))
                            elif os.path.isdir(file_path):
                                for root, dirs, files in os.walk(file_path):
                                    for file in files:
                                        full_path = os.path.join(root, file)
                                        arcname = os.path.relpath(
                                            full_path, os.path.dirname(file_path)
                                        )
                                        zipf.write(full_path, arcname)

                        processed += 1
                        progress = int((processed / total_files) * 100)
                        self.progress_updated.emit(
                            progress,
                            f"Compressing (fallback): {os.path.basename(file_path)}",
                        )
                    except Exception as e:
                        continue

            return True
        except Exception:
            return False

    def stop(self):
        """Stop the compression process"""
        self.should_stop = True


class CleanupHelperWidget(QWidget):
    """Main widget for the Desktop Cleanup Helper module"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.config = self._load_config()

        # Worker threads
        self.scanner_thread = None
        self.duplicate_finder_thread = None
        self.compressor_thread = None

        # Data storage
        self.scan_results = {}
        self.duplicate_results = {}

        # Working path - will be set by analytics tab
        detected_archive = self._detect_archive_path()
        self.working_path = detected_archive or os.path.expanduser("~/Desktop")

        # Search parameters
        self.current_search_term = ""
        self.archive_filters = {
            "file_types": [],
            "min_date": None,
            "max_date": None,
        }

        # Performance optimization: Add caching
        self._file_cache = {}  # Cache for file structure
        self._search_index = {}  # Search index for fast lookups
        self._last_scan_path = ""  # Track last scanned path
        self._cache_timestamp = 0  # Track when cache was built

        # Splash screens for operations
        self.scan_splash = None
        self.archive_splash = None
        self.duplicate_splash = None

        self.initUI()

    def _load_config(self) -> Dict:
        """Load configuration from main application"""
        try:
            config_file = os.path.join(
                os.path.expanduser("~"), ".DesktopOrganizer", "config.yaml"
            )
            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)
        except Exception:
            pass

        # Return default configuration if loading fails
        return {
            "drives": {"main_drive_policy": "D"},
            "file_manager": {
                "max_file_size_mb": 100,
                "allowed_extensions": [".lnk"],
                "allowed_filenames": [],
            },
        }

    def _detect_archive_path(self) -> str:
        """Detect the main archive folder path from configuration"""
        try:
            # Get drive policy from config
            drive_policy = self.config.get("drives", {}).get("main_drive_policy", "D")

            # Determine the drive to use
            if drive_policy == "auto":
                # Try D: first, then E:, then C:
                for drive in ["D", "E", "C"]:
                    if os.path.exists(f"{drive}:\\"):
                        base_drive = drive
                        break
                else:
                    base_drive = "C"
            else:
                base_drive = drive_policy

            # Construct the archive path
            current_year = datetime.now().year
            archive_path = os.path.join(
                f"{base_drive}:\\", "Робочі столи", f"Робочий стіл {current_year}"
            )

            if os.path.exists(archive_path):
                return archive_path
            else:
                # Fallback to common paths
                fallback_paths = [
                    f"C:\\Users\\{os.getenv('USERNAME')}\\Desktop\\Archives",
                    f"{base_drive}:\\Archives",
                    os.path.expanduser("~/Desktop/Archives"),
                ]

                for path in fallback_paths:
                    if os.path.exists(path):
                        return path

        except Exception as e:
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Error detecting archive path: {e}"
                )

        return ""

    def get_compression_level_text(self, level: int) -> str:
        """Get descriptive text for compression level"""
        levels = ["Найшвидший", "Швидкий", "Нормальний", "Хороший", "Найкращий"]
        index = min(level // 2, 4)
        return levels[index]

    def set_working_path(self, path: str):
        """Set the working path and update all components"""
        if os.path.exists(path):
            self.working_path = path
            # Update path fields in all tabs
            self.update_all_path_fields()
            # Log to main application
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Робочий шлях змінено на: {path}"
                )

    def get_working_path(self) -> str:
        """Get the current working path"""
        return self.working_path

    def update_all_path_fields(self):
        """Update path fields in all tabs"""
        try:
            # Update analytics tab
            if hasattr(self, "scan_path_edit"):
                self.scan_path_edit.setText(self.working_path)

            # Update duplicate finder tab
            if hasattr(self, "duplicate_path_edit"):
                self.duplicate_path_edit.setText(self.working_path)

            # Update default scan path in settings
            if hasattr(self, "default_scan_path_edit"):
                self.default_scan_path_edit.setText(self.working_path)

        except Exception as e:
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Помилка оновлення полів шляху: {e}"
                )

    def on_scan_path_changed(self, new_path: str):
        """Handle scan path change - update working path"""
        # Use a timer to avoid rapid updates while typing
        if not hasattr(self, "path_update_timer"):
            self.path_update_timer = QTimer()
            self.path_update_timer.setSingleShot(True)
            self.path_update_timer.timeout.connect(self._delayed_path_update)

        # Cancel any pending update
        self.path_update_timer.stop()
        # Schedule new update after 500ms
        self.path_update_timer.start(500)

    def _delayed_path_update(self):
        """Delayed update of working path"""
        new_path = self.scan_path_edit.text().strip()
        if new_path and os.path.exists(new_path) and new_path != self.working_path:
            self.set_working_path(new_path)

    def setup_keyboard_shortcuts(self):
        """Set up keyboard shortcuts for common actions"""
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QKeySequence

        # Ctrl+F: Focus search box
        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(self.focus_search_box)

        # Ctrl+R: Refresh archive tree
        refresh_shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        refresh_shortcut.activated.connect(self.refresh_archive_tree)

        # Ctrl+A: Select all items in archive tree
        select_all_shortcut = QShortcut(QKeySequence("Ctrl+A"), self)
        select_all_shortcut.activated.connect(self.select_all_archive_items)

        # Delete: Delete selected items
        delete_shortcut = QShortcut(QKeySequence("Delete"), self)
        delete_shortcut.activated.connect(self.delete_selected_items)

        # Ctrl+Shift+C: Clear all filters
        clear_filters_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        clear_filters_shortcut.activated.connect(self.reset_all_filters)

        # F5: Refresh
        f5_shortcut = QShortcut(QKeySequence("F5"), self)
        f5_shortcut.activated.connect(self.refresh_archive_tree)

        # Escape: Clear search
        escape_shortcut = QShortcut(QKeySequence("Escape"), self)
        escape_shortcut.activated.connect(self.clear_search)

    def focus_search_box(self):
        """Focus the search box"""
        self.tab_widget.setCurrentIndex(1)  # Switch to archive browser tab
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def select_all_archive_items(self):
        """Select all items in the archive tree"""
        self.archive_tree.selectAll()

    def initUI(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)

        # Create tab widget
        self.tab_widget = QTabWidget()

        # Set up keyboard shortcuts
        self.setup_keyboard_shortcuts()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #bdc3c7;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #ecf0f1;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 2px solid #3498db;
            }
        """)

        # Create tabs
        self.create_analytics_tab()
        self.create_archive_browser_tab()
        self.create_duplicate_finder_tab()
        self.create_compression_tab()
        self.create_settings_tab()

        layout.addWidget(self.tab_widget)

    def create_analytics_tab(self):
        """Create the analytics tab with storage analysis"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controls
        controls_layout = QHBoxLayout()

        self.scan_path_edit = QLineEdit(self.working_path)
        self.scan_path_edit.setPlaceholderText("Введіть шлях для сканування...")
        # Connect text change to update working path
        self.scan_path_edit.textChanged.connect(self.on_scan_path_changed)
        controls_layout.addWidget(QLabel("Шлях сканування:"))
        controls_layout.addWidget(self.scan_path_edit)

        browse_btn = QPushButton("Огляд")
        browse_btn.clicked.connect(self.browse_scan_path)
        controls_layout.addWidget(browse_btn)

        self.scan_btn = QPushButton("🔍 Почати сканування")
        self.scan_btn.clicked.connect(self.start_scan)
        controls_layout.addWidget(self.scan_btn)

        # Add "Load to Archive Browser" button (initially hidden)
        self.load_to_archive_btn = QPushButton("📂 Завантажити файли до огляду архівів")
        self.load_to_archive_btn.setVisible(False)
        self.load_to_archive_btn.clicked.connect(self.load_scan_results_to_archive)
        controls_layout.addWidget(self.load_to_archive_btn)

        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        # Results area
        results_splitter = QSplitter(Qt.Horizontal)

        # Left side - Summary
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        self.summary_group = QGroupBox("📊 Підсумки зберігання")
        self.summary_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #3498db;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #3498db;
            }
        """)
        summary_layout = QGridLayout(self.summary_group)

        self.total_files_label = QLabel("Файлів: 0")
        self.total_size_label = QLabel("Розмір: 0 Б")
        self.file_types_label = QLabel("Типів: 0")
        self.large_files_label = QLabel("Великих файлів: 0")

        summary_layout.addWidget(QLabel("Всього файлів:"), 0, 0)
        summary_layout.addWidget(self.total_files_label, 0, 1)
        summary_layout.addWidget(QLabel("Загальний розмір:"), 1, 0)
        summary_layout.addWidget(self.total_size_label, 1, 1)
        summary_layout.addWidget(QLabel("Типів файлів:"), 2, 0)
        summary_layout.addWidget(self.file_types_label, 2, 1)
        summary_layout.addWidget(QLabel("Великі файли:"), 3, 0)
        summary_layout.addWidget(self.large_files_label, 3, 1)

        left_layout.addWidget(self.summary_group)

        # File types breakdown
        self.file_types_group = QGroupBox("📁 Розподіл типів файлів")
        self.file_types_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #e74c3c;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #e74c3c;
            }
        """)

        self.file_types_table = QTableWidget()
        self.file_types_table.setColumnCount(3)
        self.file_types_table.setHorizontalHeaderLabels(
            ["Розширення", "Кількість", "Розмір"]
        )
        self.file_types_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.file_types_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.file_types_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self.file_types_table.setMaximumHeight(200)

        file_types_layout = QVBoxLayout(self.file_types_group)
        file_types_layout.addWidget(self.file_types_table)

        left_layout.addWidget(self.file_types_group)

        left_layout.addStretch()

        # Right side - Large files list
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.large_files_group = QGroupBox("🔍 Великі файли (>10МБ)")
        self.large_files_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #f39c12;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #f39c12;
            }
        """)

        # Large files controls
        large_files_controls = QHBoxLayout()

        self.filter_large_files_input = QLineEdit()
        self.filter_large_files_input.setPlaceholderText("🔍 Фільтрувати файли...")
        self.filter_large_files_input.textChanged.connect(self.filter_large_files)
        large_files_controls.addWidget(self.filter_large_files_input)

        self.export_btn = QPushButton("📥 Експорт")
        self.export_btn.clicked.connect(self.export_analytics)
        large_files_controls.addWidget(self.export_btn)

        large_files_controls.addStretch()

        self.large_files_table = QTableWidget()
        self.large_files_table.setColumnCount(4)
        self.large_files_table.setHorizontalHeaderLabels(
            ["Назва файлу", "Розмір", "Змінено", "Шлях"]
        )
        self.large_files_table.horizontalHeader().setStretchLastSection(True)
        self.large_files_table.setAlternatingRowColors(True)
        self.large_files_table.setSortingEnabled(True)
        self.large_files_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.large_files_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.large_files_table.customContextMenuRequested.connect(
            self.show_large_files_context_menu
        )

        # Add tooltip support
        self.large_files_table.setMouseTracking(True)
        self.large_files_table.cellEntered.connect(self.show_file_tooltip)

        large_files_layout = QVBoxLayout(self.large_files_group)
        large_files_layout.addLayout(large_files_controls)
        large_files_layout.addWidget(self.large_files_table)

        right_layout.addWidget(self.large_files_group)

        results_splitter.addWidget(left_widget)
        results_splitter.addWidget(right_widget)
        results_splitter.setSizes([400, 600])

        layout.addWidget(results_splitter)

        self.tab_widget.addTab(tab, "📊 Аналітика")

    def on_archive_build_error(self, error_message: str):
        """Handle archive tree build error."""
        if self.archive_splash:
            self.archive_splash.hide()
        QMessageBox.critical(
            self,
            "Помилка побудови дерева",
            f"Не вдалося побудувати дерево архівів: {error_message}",
        )

    def reset_all_filters(self):
        """Resets all search and filter criteria and refreshes the tree."""
        self.search_edit.clear()
        self.archive_filters = {
            "file_types": [],
            "min_date": None,
            "max_date": None,
        }
        # TODO: Reset advanced filter dialog UI if it exists and is open
        self.refresh_archive_tree()

    def apply_quick_filter(self, filter_type: str):
        """Apply a predefined quick filter and refresh the tree."""
        # Toggling behavior: if the same filter is clicked again, clear it.
        filter_map = {
            "oil_gas": [".las", ".dlis", ".prj", ".dat", ".ini", ".xtf"],
            "images": [".png", ".jpg", ".jpeg", ".gif", ".bmp"],
            "documents": [
                ".pdf",
                ".doc",
                ".docx",
                ".xls",
                ".xlsx",
                ".ppt",
                ".pptx",
                ".txt",
            ],
            "video": [".mp4", ".avi", ".mkv", ".mov"],
            "archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
        }

        new_filter = filter_map.get(filter_type, [])

        if self.archive_filters.get("file_types") == new_filter:
            self.archive_filters["file_types"] = []
        else:
            self.archive_filters["file_types"] = new_filter

        self.refresh_archive_tree()

    def create_archive_browser_tab(self):
        """Create the archive browser tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Search controls
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍 Пошук:"))

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Пошук в архівах...")
        # Add keyboard shortcuts
        self.search_edit.returnPressed.connect(self.refresh_archive_tree)
        # Add Ctrl+F shortcut to focus search
        self.search_edit.setToolTip("Пошук... (Enter для пошуку, Ctrl+F для фокусу)")
        search_layout.addWidget(self.search_edit)

        search_btn = QPushButton("Пошук")
        search_btn.setObjectName("search_button")
        search_btn.clicked.connect(self.refresh_archive_tree)
        search_layout.addWidget(search_btn)

        clear_search_btn = QPushButton("Очистити")
        clear_search_btn.clicked.connect(self.reset_all_filters)
        search_layout.addWidget(clear_search_btn)

        search_layout.addStretch()
        layout.addLayout(search_layout)

        # Archive tree
        self.archive_tree = QTreeWidget()
        self.archive_tree.setHeaderLabels(["Назва", "Розмір", "Змінено", "Тип", "Шлях"])
        self.archive_tree.setColumnWidth(0, 300)
        self.archive_tree.setColumnWidth(1, 100)
        self.archive_tree.setColumnWidth(2, 150)
        self.archive_tree.setColumnWidth(3, 80)
        self.archive_tree.setColumnWidth(4, 200)

        # Enable multiple selection
        self.archive_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.archive_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.archive_tree.customContextMenuRequested.connect(
            self.show_archive_context_menu
        )
        self.archive_tree.itemDoubleClicked.connect(self.open_file_location)

        # Ensure expand controls are always visible for directories
        self.archive_tree.setIndentation(20)
        self.archive_tree.setRootIsDecorated(True)
        self.archive_tree.setAlternatingRowColors(True)

        layout.addWidget(self.archive_tree)

        # Status label for archive operations
        self.archive_status_label = QLabel("Готовий до пошуку та фільтрації")
        self.archive_status_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #2c3e50;
                padding: 8px;
                background-color: #ecf0f1;
                border-radius: 5px;
                border: 1px solid #bdc3c7;
                font-weight: 500;
            }
        """)
        layout.addWidget(self.archive_status_label)

        # Mode indicator and return button (hidden by default)
        self.mode_indicator_label = QLabel("📂 Звичайний режим")
        self.mode_indicator_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #27ae60;
                padding: 6px 12px;
                background-color: #d5f4e6;
                border-radius: 4px;
                border: 1px solid #27ae60;
                font-weight: bold;
            }
        """)
        self.mode_indicator_label.setVisible(False)
        layout.addWidget(self.mode_indicator_label)

        # Action buttons
        actions_layout = QHBoxLayout()

        open_btn = QPushButton("📂 Відкрити місцезнаходження")
        open_btn.clicked.connect(self.open_selected_location)
        actions_layout.addWidget(open_btn)

        restore_btn = QPushButton("↩️ Відновити на стіл")
        restore_btn.clicked.connect(self.restore_selected_file)
        actions_layout.addWidget(restore_btn)

        # Add "Find Duplicates" button
        find_dup_btn = QPushButton("🔍 Знайти дублікати")
        find_dup_btn.clicked.connect(self.send_selection_to_duplicate_finder)
        actions_layout.addWidget(find_dup_btn)

        # Add "Return to normal mode" button (hidden by default)
        self.return_to_normal_btn = QPushButton("↩️ Повернутися до звичайного режиму")
        self.return_to_normal_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.return_to_normal_btn.clicked.connect(self.switch_to_normal_mode)
        self.return_to_normal_btn.setVisible(False)
        actions_layout.addWidget(self.return_to_normal_btn)

        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        # Filter toggle button
        self.filter_toggle_btn = QPushButton("⌃ ⌃ ⌃ Фільтри ⌃ ⌃ ⌃")
        self.filter_toggle_btn.clicked.connect(self.toggle_filters)
        layout.addWidget(self.filter_toggle_btn)

        # Filter controls (collapsible)
        self.filter_widget = QWidget()
        self.filter_widget.setStyleSheet("QWidget { background-color: transparent; }")
        filter_layout = QVBoxLayout(self.filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)

        # Primary filter buttons (Oil & Gas focus)
        primary_filters_layout = QHBoxLayout()

        # Oil & Gas Engineering filter (prominent)
        oil_gas_btn = QPushButton("⛽ Нафтогазова інженерія")
        oil_gas_btn.clicked.connect(lambda: self.apply_quick_filter("oil_gas"))
        primary_filters_layout.addWidget(oil_gas_btn)

        # Common file type filters
        images_btn = QPushButton("🖼️ Зображення")
        images_btn.clicked.connect(lambda: self.apply_quick_filter("images"))
        primary_filters_layout.addWidget(images_btn)

        documents_btn = QPushButton("📄 Документи")
        documents_btn.clicked.connect(lambda: self.apply_quick_filter("documents"))
        primary_filters_layout.addWidget(documents_btn)

        video_btn = QPushButton("🎥 Відео")
        video_btn.clicked.connect(lambda: self.apply_quick_filter("video"))
        primary_filters_layout.addWidget(video_btn)

        archives_btn = QPushButton("📦 Архіви")
        archives_btn.clicked.connect(lambda: self.apply_quick_filter("archives"))
        primary_filters_layout.addWidget(archives_btn)

        # More Filters button (inline with other filters)
        more_filters_btn = QPushButton("⚙️ Більше фільтрів...")
        more_filters_btn.clicked.connect(self.open_advanced_filter_presets)
        primary_filters_layout.addWidget(more_filters_btn)

        primary_filters_layout.addStretch()
        filter_layout.addLayout(primary_filters_layout)

        # Add separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet(
            "QFrame { background-color: rgba(189, 195, 199, 0.3); max-height: 1px; }"
        )
        filter_layout.addWidget(separator)

        layout.addWidget(self.filter_widget)

        # Initialize filter visibility state (hidden by default)
        self.filters_visible = False
        self.filter_widget.hide()  # Hide filters on launch

        self.tab_widget.addTab(tab, "📂 Огляд архівів")

    def create_duplicate_finder_tab(self):
        """Create the duplicate file finder tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controls
        controls_layout = QHBoxLayout()

        controls_layout.addWidget(QLabel("🎯 Знайти дублікати файлів у:"))

        self.duplicate_path_edit = QLineEdit(self.working_path)
        controls_layout.addWidget(self.duplicate_path_edit)

        browse_duplicate_btn = QPushButton("Огляд")
        browse_duplicate_btn.clicked.connect(self.browse_duplicate_path)
        controls_layout.addWidget(browse_duplicate_btn)

        self.find_duplicates_btn = QPushButton("🔍 Знайти дублікати")
        self.find_duplicates_btn.clicked.connect(self.find_duplicates)
        controls_layout.addWidget(self.find_duplicates_btn)

        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        # Options
        options_layout = QHBoxLayout()

        self.min_file_size_spin = QSpinBox()
        self.min_file_size_spin.setRange(1, 1000)
        self.min_file_size_spin.setValue(1)
        self.min_file_size_spin.setSuffix(" МБ")
        options_layout.addWidget(QLabel("Мінімальний розмір файлу:"))
        options_layout.addWidget(self.min_file_size_spin)

        self.check_content_hash = QCheckBox(
            "Порівнювати вміст файлів (повільніше, але точніше)"
        )
        self.check_content_hash.setChecked(True)
        options_layout.addWidget(self.check_content_hash)

        options_layout.addStretch()
        layout.addLayout(options_layout)

        # Results
        self.duplicate_results_group = QGroupBox("🎯 Знайдені дублікати файлів")
        duplicate_results_layout = QVBoxLayout(self.duplicate_results_group)

        self.duplicate_tree = QTreeWidget()
        self.duplicate_tree.setHeaderLabels(["Хеш", "Файли", "Загальний розмір", "Дії"])
        self.duplicate_tree.setColumnWidth(0, 80)
        self.duplicate_tree.setColumnWidth(1, 300)
        self.duplicate_tree.setColumnWidth(2, 100)

        # Enable context menu for duplicate tree
        self.duplicate_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.duplicate_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.duplicate_tree.customContextMenuRequested.connect(
            self.show_duplicate_context_menu
        )

        duplicate_results_layout.addWidget(self.duplicate_tree)

        # Duplicate actions
        duplicate_actions_layout = QHBoxLayout()

        select_all_btn = QPushButton("Вибрати все")
        select_all_btn.clicked.connect(self.select_all_duplicates)
        duplicate_actions_layout.addWidget(select_all_btn)

        delete_selected_btn = QPushButton("🗑️ Видалити вибране")
        delete_selected_btn.clicked.connect(self.delete_selected_duplicates)
        duplicate_actions_layout.addWidget(delete_selected_btn)

        duplicate_actions_layout.addStretch()
        duplicate_results_layout.addLayout(duplicate_actions_layout)

        layout.addWidget(self.duplicate_results_group)

        self.tab_widget.addTab(tab, "🎯 Пошук дублікатів")

    def update_duplicate_progress(self, value, message):
        """Update duplicate finder progress on splash screen"""
        if hasattr(self, "duplicate_splash") and self.duplicate_splash:
            self.duplicate_splash.update_progress(value, message)

    def on_duplicates_finished(self, duplicates):
        """Handle duplicate finder finished signal"""
        self.find_duplicates_btn.setEnabled(True)
        if hasattr(self, "duplicate_splash") and self.duplicate_splash:
            self.duplicate_splash.hide()

        if not duplicates:
            QMessageBox.information(
                self,
                "Дублікати не знайдено",
                "У вказаній папці не знайдено дублікатів файлів.",
            )

    def add_duplicate_item(self, file_hash: str, file_list: list):
        """Add a new duplicate item to the tree"""
        if not file_list:
            return

        # Check if this hash is already in the tree (shouldn't happen with new logic, but for safety)
        root_items = self.duplicate_tree.findItems(file_hash[:12], Qt.MatchExactly, 0)
        if root_items:
            root_item = root_items[0]
        else:
            root_item = QTreeWidgetItem(self.duplicate_tree)
            root_item.setText(0, file_hash[:12])  # Display truncated hash
            self.duplicate_tree.addTopLevelItem(root_item)

        # Clear existing children for this hash and re-add (in case of updates)
        root_item.takeChildren()

        total_size = 0
        for file_path in file_list:
            child_item = QTreeWidgetItem(root_item)
            child_item.setText(1, file_path)  # Full path in column 1
            child_item.setData(1, Qt.UserRole, file_path)  # Store full path in UserRole

            try:
                file_size = os.path.getsize(file_path)
                total_size += file_size
                child_item.setText(
                    2, humanize.naturalsize(file_size)
                )  # Size in column 2
            except OSError:
                child_item.setText(2, "N/A")

        root_item.setText(
            2, humanize.naturalsize(total_size)
        )  # Total size for the hash group
        root_item.setExpanded(True)  # Expand the hash group by default

    def create_compression_tab(self):
        """Create the file compression tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # File selection
        selection_layout = QHBoxLayout()
        selection_layout.addWidget(QLabel("📦 Виберіть файли для стиснення:"))

        self.compression_files_edit = QLineEdit()
        self.compression_files_edit.setPlaceholderText(
            "Перетягніть файли або натисніть огляд..."
        )
        self.compression_files_edit.setReadOnly(True)
        selection_layout.addWidget(self.compression_files_edit)

        browse_files_btn = QPushButton("Огляд файлів")
        browse_files_btn.clicked.connect(self.browse_compression_files)
        selection_layout.addWidget(browse_files_btn)

        layout.addLayout(selection_layout)

        # Compression status
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Рушій стиснення:"))

        compress_status_label = QLabel(
            "🟢 Розширений (compress package)"
            if COMPRESS_AVAILABLE
            else "🟡 Базовий (zipfile)"
        )

        # Set different styles based on availability
        if COMPRESS_AVAILABLE:
            compress_status_label.setStyleSheet("""
                QLabel {
                    font-weight: bold;
                    padding: 5px;
                    border-radius: 3px;
                    background-color: #d4edda;
                    color: #155724;
                }
            """)
        else:
            compress_status_label.setStyleSheet("""
                QLabel {
                    font-weight: bold;
                    padding: 5px;
                    border-radius: 3px;
                    background-color: #fff3cd;
                    color: #856404;
                }
            """)

        status_layout.addWidget(compress_status_label)

        if not COMPRESS_AVAILABLE:
            install_compress_btn = QPushButton("Встановити compress package")
            install_compress_btn.clicked.connect(self.install_compress_package)
            status_layout.addWidget(install_compress_btn)

        status_layout.addStretch()
        layout.addLayout(status_layout)

        # Compression options
        options_group = QGroupBox("⚙️ Налаштування стиснення")
        options_layout = QGridLayout(options_group)

        options_layout.addWidget(QLabel("Назва архіву:"), 0, 0)
        self.archive_name_edit = QLineEdit("compressed_archive.zip")
        options_layout.addWidget(self.archive_name_edit, 0, 1)

        options_layout.addWidget(QLabel("Рівень стиснення:"), 1, 0)
        self.compression_level_slider = QSlider(Qt.Horizontal)
        self.compression_level_slider.setRange(1, 9)
        self.compression_level_slider.setValue(6)
        self.compression_level_slider.setTickPosition(QSlider.TicksBelow)
        self.compression_level_slider.setTickInterval(2)
        options_layout.addWidget(self.compression_level_slider, 1, 1)

        self.compression_level_label = QLabel("6 (Нормальний)")
        self.compression_level_slider.valueChanged.connect(
            lambda v: self.compression_level_label.setText(
                f"{v} ({self.get_compression_level_text(v)})"
            )
        )
        options_layout.addWidget(self.compression_level_label, 1, 2)

        # Supported formats info
        if COMPRESS_AVAILABLE:
            formats_label = QLabel(
                "Підтримувані формати: ZIP, TAR.GZ, TAR.BZ2, TAR.XZ, 7Z"
            )
            formats_label.setStyleSheet(
                "color: #6c757d; font-size: 11px; font-style: italic;"
            )
            options_layout.addWidget(formats_label, 2, 0, 1, 3)

        layout.addWidget(options_group)

        # Selected files list
        self.selected_files_group = QGroupBox("📋 Вибрані файли")
        selected_files_layout = QVBoxLayout(self.selected_files_group)

        self.selected_files_list = QTextEdit()
        self.selected_files_list.setMaximumHeight(150)
        self.selected_files_list.setReadOnly(True)
        selected_files_layout.addWidget(self.selected_files_list)

        layout.addWidget(self.selected_files_group)

        # Actions
        actions_layout = QHBoxLayout()

        self.compress_btn = QPushButton("🗜️ Стиснути файли")
        self.compress_btn.clicked.connect(self.compress_files)
        actions_layout.addWidget(self.compress_btn)

        clear_files_btn = QPushButton("Очистити вибір")
        clear_files_btn.clicked.connect(self.clear_compression_selection)
        actions_layout.addWidget(clear_files_btn)

        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        # Compression log
        self.compression_log = QTextEdit()
        self.compression_log.setMaximumHeight(100)
        self.compression_log.setReadOnly(True)
        layout.addWidget(QLabel("Журнал стиснення:"))
        layout.addWidget(self.compression_log)

        self.tab_widget.addTab(tab, "📦 Стиснення")

    def create_settings_tab(self):
        """Create the settings tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # General settings
        general_group = QGroupBox("⚙️ Загальні налаштування")
        general_layout = QGridLayout(general_group)

        general_layout.addWidget(QLabel("Шлях сканування за замовчуванням:"), 0, 0)
        self.default_scan_path_edit = QLineEdit(self.working_path)
        general_layout.addWidget(self.default_scan_path_edit, 0, 1)

        browse_default_btn = QPushButton("Огляд")
        browse_default_btn.clicked.connect(self.browse_default_scan_path)
        general_layout.addWidget(browse_default_btn, 0, 2)

        self.auto_detect_archives = QCheckBox("Автоматично визначати папки архівів")
        self.auto_detect_archives.setChecked(True)
        general_layout.addWidget(self.auto_detect_archives, 1, 0, 1, 3)

        self.show_hidden_files = QCheckBox("Показувати приховані файли в оглядачі")
        general_layout.addWidget(self.show_hidden_files, 2, 0, 1, 3)

        layout.addWidget(general_group)

        # File size settings
        size_group = QGroupBox("📏 Налаштування розміру файлів")
        size_layout = QGridLayout(size_group)

        size_layout.addWidget(QLabel("Поріг великих файлів:"), 0, 0)
        self.large_file_threshold_spin = QSpinBox()
        self.large_file_threshold_spin.setRange(1, 1000)
        self.large_file_threshold_spin.setValue(10)
        self.large_file_threshold_spin.setSuffix(" МБ")
        size_layout.addWidget(self.large_file_threshold_spin, 0, 1)

        size_layout.addWidget(QLabel("Поріг старих файлів:"), 1, 0)
        self.old_file_threshold_spin = QSpinBox()
        self.old_file_threshold_spin.setRange(30, 3650)
        self.old_file_threshold_spin.setValue(365)
        self.old_file_threshold_spin.setSuffix(" днів")
        size_layout.addWidget(self.old_file_threshold_spin, 1, 1)

        layout.addWidget(size_group)

        # Performance settings
        performance_group = QGroupBox("⚡ Performance Settings")
        performance_layout = QGridLayout(performance_group)

        performance_layout.addWidget(QLabel("Thread Count:"), 0, 0)
        self.thread_count_spin = QSpinBox()
        self.thread_count_spin.setRange(1, 16)
        self.thread_count_spin.setValue(4)
        performance_layout.addWidget(self.thread_count_spin, 0, 1)

        self.enable_caching = QCheckBox("Enable file caching")
        self.enable_caching.setChecked(True)
        performance_layout.addWidget(self.enable_caching, 1, 0, 1, 2)

        layout.addWidget(performance_group)

        # Actions
        actions_layout = QHBoxLayout()

        save_settings_btn = QPushButton("💾 Save Settings")
        save_settings_btn.clicked.connect(self.save_settings)
        actions_layout.addWidget(save_settings_btn)

        reset_settings_btn = QPushButton("🔄 Reset to Defaults")
        reset_settings_btn.clicked.connect(self.reset_settings)
        actions_layout.addWidget(reset_settings_btn)

        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        layout.addStretch()

        self.tab_widget.addTab(tab, "⚙️ Налаштування")

        # Load saved settings
        self.load_settings()

    # === UI Action Methods ===

    def browse_scan_path(self):
        """Browse for scan path"""
        path = QFileDialog.getExistingDirectory(self, "Оберіть каталог для сканування")
        if path:
            self.scan_path_edit.setText(path)
            self.set_working_path(path)

    def browse_duplicate_path(self):
        """Browse for duplicate finder path"""
        path = QFileDialog.getExistingDirectory(
            self, "Оберіть каталог для пошуку дублікатів"
        )
        if path:
            self.duplicate_path_edit.setText(path)

    def browse_compression_files(self):
        """Browse for files to compress"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Оберіть файли для стиснення", "", "Всі файли (*)"
        )
        if files:
            self.compression_files = files
            self.compression_files_edit.setText(f"{len(files)} файлів обрано")
            file_list = "\n".join([os.path.basename(f) for f in files[:10]])
            if len(files) > 10:
                file_list += f"\n... та ще {len(files) - 10} файлів"
            self.selected_files_list.setText(file_list)

    def browse_default_scan_path(self):
        """Browse for default scan path"""
        path = QFileDialog.getExistingDirectory(
            self, "Оберіть каталог сканування за замовчуванням"
        )
        if path:
            self.default_scan_path_edit.setText(path)
            self.set_working_path(path)

    def clear_compression_selection(self):
        """Clear compression file selection"""
        self.compression_files = []
        self.compression_files_edit.setText("")
        self.selected_files_list.setText("")

    def start_scan(self):
        """Start file scanning"""
        scan_path = self.scan_path_edit.text().strip()
        if not scan_path or not os.path.exists(scan_path):
            QMessageBox.warning(
                self, "Помилка", "Будь ласка, введіть коректний шлях для сканування."
            )
            return

        self.scan_btn.setEnabled(False)

        # Show splash screen
        self.show_scan_splash("🔍 Сканування файлів...", "Підготовка до сканування...")

        # Start scanner thread
        self.scanner_thread = FileScanner(scan_path)
        self.scanner_thread.progress_updated.connect(self.update_scan_progress)
        self.scanner_thread.file_found.connect(self.on_file_found)
        self.scanner_thread.scanning_finished.connect(self.on_scan_finished)
        self.scanner_thread.start()

    def update_scan_progress(self, progress, message):
        """Update scan progress"""
        if self.scan_splash and self.scan_splash.isVisible():
            self.scan_splash.update_progress(progress, message)

    def on_file_found(self, file_info):
        """Handle file found during scan"""
        pass  # Could update real-time stats here

    def on_scan_finished(self, results):
        """Handle scan completion"""
        self.scan_results = results

        # Store scan results for archive browser
        self.analytics_scan_results = results

        # Update splash screen to show completion
        if self.scan_splash and self.scan_splash.isVisible():
            self.scan_splash.update_progress(100, "✅ Сканування завершено!")
            QTimer.singleShot(1500, self.hide_scan_splash)

        # Update analytics display with results
        self.update_analytics_display(results)

        # Re-enable scan button after a short delay
        QTimer.singleShot(2000, self.hide_progress_and_enable_button)

    def hide_progress_and_enable_button(self):
        """Hide progress bar and re-enable scan button"""
        self.scan_btn.setEnabled(True)

        # Log to main application
        if hasattr(self.main_window, "log_message"):
            self.main_window.log_message(
                f"CleanupHelper: Scanned {self.analytics_scan_results['total_files']} files, "
                f"total size: {humanize.naturalsize(self.analytics_scan_results['total_size'])}"
            )

    def show_scan_splash(self, title="🔍 Сканування...", message="Підготовка..."):
        """Show scan splash screen"""
        if self.scan_splash:
            self.hide_scan_splash()

        self.scan_splash = ScanSplashScreen(self)
        self.scan_splash.title_label.setText(title)
        self.scan_splash.progress_label.setText(message)

        # Ensure the splash screen is properly sized and visible
        self.scan_splash.calculate_auto_size()

        # Show with multiple methods to ensure visibility
        self.scan_splash.show()
        self.scan_splash.raise_()
        self.scan_splash.activateWindow()

        # Force immediate UI update to prevent delays
        self.scan_splash.repaint()
        QApplication.processEvents()

    def hide_scan_splash(self):
        """Hide scan splash screen"""
        if self.scan_splash:
            self.scan_splash.hide()
            self.scan_splash.deleteLater()
            self.scan_splash = None

    def show_archive_splash(
        self, title="📂 Пошук в архівах...", message="Підготовка..."
    ):
        """Show archive splash screen"""
        if self.archive_splash:
            self.hide_archive_splash()

        # Create splash screen as separate window
        self.archive_splash = ArchiveSplashScreen(self)
        self.archive_splash.title_label.setText(title)
        self.archive_splash.progress_label.setText(message)

        self.archive_splash.show()
        self.archive_splash.raise_()
        self.archive_splash.activateWindow()

        # Force immediate UI update
        QApplication.processEvents()

    def hide_archive_splash(self):
        """Hide archive splash screen"""
        if self.archive_splash:
            self.archive_splash.hide()
            self.archive_splash.deleteLater()
            self.archive_splash = None

    def load_scan_results_to_archive(self):
        """Load analytics scan results into the archive browser"""
        if (
            not hasattr(self, "analytics_scan_results")
            or not self.analytics_scan_results
        ):
            QMessageBox.warning(
                self, "Попередження", "Немає результатів сканування для завантаження."
            )
            return

        # Switch to archive browser tab
        self.tab_widget.setCurrentIndex(1)  # Archive browser is index 1

        # Show loading progress
        self.archive_status_label.setText("Завантаження результатів сканування...")

        # Clear current archive tree
        self.archive_tree.clear()

        # Group files by directory for tree structure
        directory_tree = {}
        scanned_files = self.analytics_scan_results.get("files", [])

        # Add a special root item to indicate this is from analytics scan
        root_item = QTreeWidgetItem(self.archive_tree)
        root_item.setText(0, f"📊 Результати сканування аналітики")
        root_item.setText(1, f"{len(scanned_files)} файлів")
        root_item.setText(2, f"Analytics Scan")
        root_item.setText(3, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        root_item.setText(4, "analytics_scan_results")

        # Style the root item
        font = root_item.font(0)
        font.setBold(True)
        root_item.setFont(0, font)
        root_item.setExpanded(True)

        if not scanned_files:
            return

        # Build directory structure from scan results
        for i, file_info in enumerate(scanned_files):
            file_path = file_info.get("path", file_info.get("full_path", ""))
            if not file_path or not os.path.exists(file_path):
                continue

            # Extract directory and filename
            dir_path = os.path.dirname(file_path)
            file_name = os.path.basename(file_path)

            # Add to directory tree structure
            if dir_path not in directory_tree:
                directory_tree[dir_path] = []
            directory_tree[dir_path].append(
                {
                    "name": file_name,
                    "path": file_path,
                    "size": file_info.get("size", 0),
                    "modified": file_info.get("modified", datetime.now()),
                    "extension": file_info.get("extension", ""),
                    "type": file_info.get("type", "unknown"),
                }
            )

        # Populate archive tree with the results
        self._populate_archive_tree_from_scan_results(directory_tree, root_item)

        # Update status and hide progress
        self.archive_status_label.setText(
            f"📊 Режим перегляду результатів аналітики: {len(scanned_files)} файлів"
        )

        # Set a special flag to indicate this is analytics data
        self.is_showing_analytics_results = True

        # Show analytics mode indicator
        self.mode_indicator_label.setText("📊 Режим аналітики")
        self.mode_indicator_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #9b59b6;
                padding: 6px 12px;
                background-color: #e8daef;
                border-radius: 4px;
                border: 1px solid #9b59b6;
                font-weight: bold;
            }
        """)
        self.mode_indicator_label.setVisible(True)

        # Show "Return to normal mode" button
        self.return_to_normal_btn.setVisible(True)

        # Hide "Find Duplicates" button in analytics mode
        for i in range(self.archive_tree.columnCount()):
            self.archive_tree.resizeColumnToContents(i)

        # Show success message
        QMessageBox.information(
            self,
            "Завантаження завершено",
            f"Завантажено {len(scanned_files)} файлів до огляду архівів.\n\n"
            f"Файли згруповані за каталогами для зручного перегляду.",
        )

    def switch_to_normal_mode(self):
        """Clear analytics results and return to normal archive browsing"""
        # Clear analytics mode flag
        self.is_showing_analytics_results = False

        # Clear the tree
        self.archive_tree.clear()

        # Reset status and mode indicators
        self.archive_status_label.setText("Готовий до пошуку та фільтрації")

        # Hide analytics mode indicator
        self.mode_indicator_label.setVisible(False)

        # Hide return to normal button
        self.return_to_normal_btn.setVisible(False)

        # Reload normal archive view
        self.refresh_archive_tree()

        # Log the mode change
        if hasattr(self.main_window, "log_message"):
            self.main_window.log_message(
                "CleanupHelper: Переключено на звичайний режим перегляду архівів"
            )

    def send_selection_to_duplicate_finder(self):
        """Send selected files to duplicate finder tab"""
        # Get selected items from archive tree
        selected_items = self.archive_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(
                self,
                "Попередження",
                "Будь ласка, виберіть файли для пошуку дублікатів.",
            )
            return

        # Check if we're in analytics mode - don't allow duplicate search in analytics mode
        if self.is_showing_analytics_results:
            QMessageBox.information(
                self,
                "Інформація",
                "У режимі аналітики пошук дублікатів недоступний.\n"
                "Спочатку поверніться до звичайного режиму.",
            )
            return

        # Extract unique directory paths from selected items
        directories = set()
        for item in selected_items:
            file_path = item.text(4)  # Column 4 contains the full path
            if file_path and os.path.exists(file_path):
                if os.path.isfile(file_path):
                    directories.add(os.path.dirname(file_path))
                elif os.path.isdir(file_path):
                    directories.add(file_path)

        if not directories:
            QMessageBox.warning(
                self, "Попередження", "Не вдалося визначити шлях для пошуку дублікатів."
            )
            return

        # Use the first selected directory (or working path if none selected)
        search_path = directories.pop() if directories else self.working_path
        # Add back any remaining directories if multiple
        for d in directories:
            search_path = (
                self.working_path
            )  # If multiple dirs, use working path instead

        # Switch to duplicate finder tab (index 2)
        self.tab_widget.setCurrentIndex(2)

        # Set the search path in duplicate finder
        if hasattr(self, "duplicate_path_edit"):
            self.duplicate_path_edit.setText(search_path)

        # Log the action
        if hasattr(self.main_window, "log_message"):
            self.main_window.log_message(
                f"CleanupHelper: Переключено на пошук дублікатів: {search_path}"
            )

    def _populate_archive_tree_from_scan_results(
        self, directory_tree: dict, parent_item: QTreeWidgetItem
    ):
        """Populate archive tree with scan results grouped by directory"""
        if not directory_tree:
            return

        # Sort directories by path
        sorted_dirs = sorted(directory_tree.keys())

        for dir_path in sorted_dirs:
            files = directory_tree[dir_path]

            # Identify folder structure for the directory
            folder_info = self.identify_folder_structure(dir_path)

            # Create tree item for directory
            dir_item = QTreeWidgetItem(parent_item)
            dir_item.setText(0, f"{folder_info['icon']} {folder_info['name']}")
            dir_item.setText(1, f"{len(files)} файлів")  # Count instead of size
            dir_item.setText(2, f"Скановано")  # Type indicator
            dir_item.setText(
                3, datetime.now().strftime("%Y-%m-%d %H:%M")
            )  # Current time
            dir_item.setText(4, dir_path)  # Store full path

            # Calculate total size of files in this directory
            total_size = sum(f["size"] for f in files)
            dir_item.setText(
                1, f"{len(files)} файлів ({humanize.naturalsize(total_size)})"
            )

            # Add files as children
            for file_data in files:
                file_item = QTreeWidgetItem(dir_item)
                file_icon = self.get_file_icon(
                    file_data["path"], file_data["extension"]
                )
                file_item.setText(0, f"{file_icon} {file_data['name']}")
                file_item.setText(1, humanize.naturalsize(file_data["size"]))
                file_item.setText(
                    2,
                    file_data["extension"].upper()
                    if file_data["extension"]
                    else "FILE",
                )
                file_item.setText(3, file_data["modified"].strftime("%Y-%m-%d %H:%M"))
                file_item.setText(4, file_data["path"])  # Store full path

            # Keep directory items collapsed by default
            dir_item.setExpanded(False)

        # Resize columns to fit content
        for i in range(self.archive_tree.columnCount()):
            self.archive_tree.resizeColumnToContents(i)

    def update_analytics_display(self, results):
        """Update analytics display with scan results"""
        # Update summary
        self.total_files_label.setText(str(results["total_files"]))
        self.total_size_label.setText(humanize.naturalsize(results["total_size"]))
        self.file_types_label.setText(str(len(results["file_types"])))
        self.large_files_label.setText(str(len(results["large_files"])))

        # Update file types table
        self.file_types_table.setRowCount(len(results["file_types"]))
        for i, (ext, data) in enumerate(results["file_types"].items()):
            self.file_types_table.setItem(
                i, 0, QTableWidgetItem(ext or "(no extension)")
            )
            self.file_types_table.setItem(i, 1, QTableWidgetItem(str(data["count"])))
            self.file_types_table.setItem(
                i, 2, QTableWidgetItem(humanize.naturalsize(data["size"]))
            )

        # Show "Load to Archive Browser" button if scan has results
        if results.get("files") and len(results["files"]) > 0:
            self.load_to_archive_btn.setVisible(True)
            self.load_to_archive_btn.setText(
                f"📂 Завантажити {results['total_files']} файлів до огляду архівів"
            )
        else:
            self.load_to_archive_btn.setVisible(False)

        # Update large files table
        self.large_files_table.setRowCount(len(results["large_files"]))
        for i, file_info in enumerate(results["large_files"]):
            self.large_files_table.setItem(i, 0, QTableWidgetItem(file_info["name"]))
            self.large_files_table.setItem(
                i, 1, QTableWidgetItem(humanize.naturalsize(file_info["size"]))
            )
            self.large_files_table.setItem(
                i, 2, QTableWidgetItem(file_info["modified"].strftime("%Y-%m-%d %H:%M"))
            )
            self.large_files_table.setItem(i, 3, QTableWidgetItem(file_info["path"]))

        # Store current analytics data for export and filtering
        self.current_analytics_data = results

    def filter_large_files(self, text):
        """Filter large files table based on search text"""
        if (
            not hasattr(self, "current_analytics_data")
            or not self.current_analytics_data
        ):
            return

        search_text = text.lower().strip()
        large_files = self.current_analytics_data["large_files"]

        if not search_text:
            # Show all files
            filtered_files = large_files
        else:
            # Filter by filename or path
            filtered_files = [
                file_info
                for file_info in large_files
                if search_text in file_info["name"].lower()
                or search_text in file_info["path"].lower()
            ]

        # Update table with filtered results
        self.large_files_table.setRowCount(len(filtered_files))
        for i, file_info in enumerate(filtered_files):
            self.large_files_table.setItem(i, 0, QTableWidgetItem(file_info["name"]))
            self.large_files_table.setItem(
                i, 1, QTableWidgetItem(humanize.naturalsize(file_info["size"]))
            )
            self.large_files_table.setItem(
                i, 2, QTableWidgetItem(file_info["modified"].strftime("%Y-%m-%d %H:%M"))
            )
            self.large_files_table.setItem(i, 3, QTableWidgetItem(file_info["path"]))

        # Update status
        if hasattr(self, "analytics_status_label"):
            self.analytics_status_label.setText(
                f"Показано {len(filtered_files)} з {len(large_files)} великих файлів"
            )

    def show_large_files_context_menu(self, position):
        """Show context menu for large files table"""
        index = self.large_files_table.indexAt(position)
        if not index.isValid():
            return

        row = index.row()
        file_path = self.large_files_table.item(row, 3).text()
        file_name = self.large_files_table.item(row, 0).text()

        menu = QMenu(self)

        # Open file
        open_action = menu.addAction("🔓 Відкрити файл")
        open_action.triggered.connect(lambda: self.open_file(file_path))

        # Open containing folder
        open_folder_action = menu.addAction("📁 Відкрити папку")
        open_folder_action.triggered.connect(
            lambda: self.open_containing_folder(file_path)
        )

        # Copy path
        copy_path_action = menu.addAction("📋 Копіювати шлях")
        copy_path_action.triggered.connect(lambda: self.copy_to_clipboard(file_path))

        menu.addSeparator()

        # File properties
        props_action = menu.addAction("ℹ️ Властивості файлу")
        props_action.triggered.connect(
            lambda: self.show_file_properties(file_path, file_name)
        )

        menu.exec_(self.large_files_table.mapToGlobal(position))

    def show_file_tooltip(self, row, column):
        """Show detailed tooltip for file in table"""
        if (
            not hasattr(self, "current_analytics_data")
            or not self.current_analytics_data
        ):
            return

        try:
            if row >= len(self.current_analytics_data["large_files"]):
                return

            file_info = self.current_analytics_data["large_files"][row]

            tooltip_text = f"""
<b>📁 {file_info["name"]}</b><br/>
📍 <b>Шлях:</b> {file_info["path"]}<br/>
📏 <b>Розмір:</b> {humanize.naturalsize(file_info["size"])}<br/>
📅 <b>Створено:</b> {file_info.get("created", "N/A").strftime("%Y-%m-%d %H:%M") if file_info.get("created") else "N/A"}<br/>
✏️ <b>Змінено:</b> {file_info["modified"].strftime("%Y-%m-%d %H:%M")}<br/>
🏷️ <b>Тип:</b> {os.path.splitext(file_info["name"])[1] or "(немає розширення)"}
            """.strip()

            QToolTip.showText(QCursor.pos(), tooltip_text)

        except Exception as e:
            print(f"Error showing tooltip: {e}")

    def open_file(self, file_path):
        """Open file with default application"""
        try:
            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", file_path])
            else:
                subprocess.run(["xdg-open", file_path])
        except Exception as e:
            QMessageBox.warning(self, "Помилка", f"Не вдалося відкрити файл:\n{str(e)}")

    def open_containing_folder(self, file_path):
        """Open the folder containing the file and select the file"""
        try:
            folder_path = os.path.dirname(file_path)
            if sys.platform == "win32":
                subprocess.run(["explorer", "/select,", file_path])
            elif sys.platform == "darwin":
                subprocess.run(["open", folder_path])
            else:
                subprocess.run(["xdg-open", folder_path])
        except Exception as e:
            QMessageBox.warning(
                self, "Помилка", f"Не вдалося відкрити папку:\n{str(e)}"
            )

    def copy_to_clipboard(self, text):
        """Copy text to clipboard"""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

        # Show brief confirmation
        if hasattr(self, "analytics_status_label"):
            self.analytics_status_label.setText(f"Скопійовано: {text}")
            QTimer.singleShot(2000, lambda: self.analytics_status_label.setText(""))

    def show_file_properties(self, file_path, file_name):
        """Show detailed file properties dialog"""
        try:
            if not os.path.exists(file_path):
                QMessageBox.warning(
                    self, "Файл не знайдено", f"Файл не існує:\n{file_path}"
                )
                return

            stat = os.stat(file_path)

            properties = f"""
<b>📁 Властивості файлу</b>

🏷️ <b>Назва:</b> {file_name}
📍 <b>Повний шлях:</b> {file_path}
📏 <b>Розмір:</b> {humanize.naturalsize(stat.st_size)} ({stat.st_size:,} байт)
📅 <b>Створено:</b> {datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")}
✏️ <b>Змінено:</b> {datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")}
🔍 <b>Доступно:</b> {datetime.fromtimestamp(stat.st_atime).strftime("%Y-%m-%d %H:%M:%S")}
🔒 <b>Атрибути:</b> {oct(stat.st_mode)[-3:]}
            """.strip()

            msg = QMessageBox(self)
            msg.setWindowTitle("Властивості файлу")
            msg.setTextFormat(Qt.RichText)
            msg.setText(properties)
            msg.setIcon(QMessageBox.Information)
            msg.exec_()

        except Exception as e:
            QMessageBox.warning(
                self, "Помилка", f"Не вдалося отримати властивості файлу:\n{str(e)}"
            )

    def export_analytics(self):
        """Export analytics data to CSV file"""
        if (
            not hasattr(self, "current_analytics_data")
            or not self.current_analytics_data
        ):
            QMessageBox.warning(self, "Немає даних", "Немає даних для експорту.")
            return

        try:
            # Ask user for save location
            file_dialog = QFileDialog(self)
            file_dialog.setAcceptMode(QFileDialog.AcceptSave)
            file_dialog.setNameFilter("CSV файли (*.csv)")
            file_dialog.setDefaultSuffix("csv")
            file_dialog.selectFile(
                f"analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )

            if file_dialog.exec_() != QFileDialog.Accepted:
                return

            save_path = file_dialog.selectedFiles()[0]

            # Prepare data for export
            export_data = []

            # Add summary
            export_data.append(["Підсумки"])
            export_data.append(
                [
                    "Загальна кількість файлів",
                    self.current_analytics_data["total_files"],
                ]
            )
            export_data.append(
                ["Загальний розмір", self.current_analytics_data["total_size"]]
            )
            export_data.append(
                [
                    "Кількість типів файлів",
                    len(self.current_analytics_data["file_types"]),
                ]
            )
            export_data.append([])

            # Add file types breakdown
            export_data.append(["Типи файлів"])
            export_data.append(["Розширення", "Кількість", "Розмір"])
            for ext, data in self.current_analytics_data["file_types"].items():
                export_data.append(
                    [ext or "(без розширення)", data["count"], data["size"]]
                )
            export_data.append([])

            # Add large files
            export_data.append(["Великі файли (>10МБ)"])
            export_data.append(["Назва", "Розмір", "Шлях", "Дата зміни"])
            for file_info in self.current_analytics_data["large_files"]:
                export_data.append(
                    [
                        file_info["name"],
                        file_info["size"],
                        file_info["path"],
                        file_info["modified"].strftime("%Y-%m-%d %H:%M:%S"),
                    ]
                )

            # Write to CSV
            with open(save_path, "w", newline="", encoding="utf-8-sig") as csvfile:
                import csv

                writer = csv.writer(csvfile)
                writer.writerows(export_data)

            QMessageBox.information(
                self,
                "Експорт завершено",
                f"Дані аналітики експортовано до:\n{save_path}",
            )

            # Offer to open the file
            reply = QMessageBox.question(
                self,
                "Відкрити файл?",
                "Відкрити експортований файл?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.open_file(save_path)

        except Exception as e:
            QMessageBox.critical(
                self, "Помилка експорту", f"Не вдалося експортувати дані:\n{str(e)}"
            )

    def find_duplicates(self):
        """Find duplicate files"""
        path = self.duplicate_path_edit.text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Шлях не знайдено", "Вказаний шлях не існує.")
            return

        # Show splash screen
        if not self.duplicate_splash:
            self.duplicate_splash = DuplicateFinderSplashScreen(self)
        self.duplicate_splash.show()
        self.duplicate_splash.update_progress(0, "Підготовка до пошуку...")

        # This can be slow and block the UI, but we keep it for now
        try:
            file_list = []
            for root, _, files in os.walk(path):
                for file in files:
                    file_list.append(os.path.join(root, file))
        except Exception as e:
            if self.duplicate_splash:
                self.duplicate_splash.hide()
            QMessageBox.critical(
                self, "Помилка", f"Помилка під час сканування файлів: {e}"
            )
            return

        if not file_list:
            if self.duplicate_splash:
                self.duplicate_splash.hide()
            QMessageBox.information(
                self,
                "Файли не знайдено",
                "У вказаній папці немає файлів для перевірки.",
            )
            return

        self.duplicate_splash.update_progress(0, f"Аналіз {len(file_list)} файлів...")
        self.find_duplicates_btn.setEnabled(False)
        self.duplicate_tree.clear()

        check_content = self.check_content_hash.isChecked()
        self.duplicate_finder_thread = DuplicateFileFinder(
            file_list, check_content=check_content
        )
        self.duplicate_finder_thread.progress_updated.connect(
            self.update_duplicate_progress
        )
        self.duplicate_finder_thread.duplicate_found.connect(self.add_duplicate_item)
        self.duplicate_finder_thread.finished.connect(self.on_duplicates_finished)
        self.duplicate_finder_thread.start()

    def on_duplicate_found(self, duplicate_files):
        """Handle duplicate files found"""
        # Update duplicate tree in real-time
        pass

    def on_duplicates_finished(self, results):
        """Handle duplicate finding completion"""
        self.duplicate_results = results

        # Update and hide duplicate splash screen
        if hasattr(self, "duplicate_splash") and self.duplicate_splash:
            self.duplicate_splash.update_progress(
                100, f"✅ Знайдено {len(results)} груп дублікатів!"
            )
            QTimer.singleShot(1500, self.duplicate_splash.hide)

        # Update duplicate tree
        self.duplicate_tree.clear()
        for hash_val, files in results.items():
            if len(files) > 1:
                item = QTreeWidgetItem(self.duplicate_tree)
                item.setText(0, hash_val[:8] + "...")
                item.setText(1, f"{len(files)} files")

                total_size = sum(os.path.getsize(f) for f in files if os.path.exists(f))
                item.setText(2, humanize.naturalsize(total_size))

                # Add child items for each file
                for file_path in files:
                    child = QTreeWidgetItem(item)
                    child.setText(0, "")
                    child.setText(1, file_path)
                    child.setText(
                        2,
                        humanize.naturalsize(os.path.getsize(file_path))
                        if os.path.exists(file_path)
                        else "N/A",
                    )

                item.setExpanded(True)

        self.find_duplicates_btn.setEnabled(True)

        # Log to main application
        if hasattr(self.main_window, "log_message"):
            self.main_window.log_message(
                f"CleanupHelper: Found {len(results)} groups of duplicate files"
            )

    def compress_files(self):
        """Compress selected files"""
        if not hasattr(self, "compression_files") or not self.compression_files:
            QMessageBox.warning(
                self, "Помилка", "Будь ласка, оберіть файли для стиснення."
            )
            return

        # Get compression level from slider
        compression_level = self.compression_level_slider.value()

        # Supported formats for file dialog
        if COMPRESS_AVAILABLE:
            format_filter = (
                "Archive Files (*.zip *.tar.gz *.tgz *.tar.bz2 *.tar.xz *.7z);;"
                "ZIP Files (*.zip);;"
                "TAR.GZ Files (*.tar.gz *.tgz);;"
                "TAR.BZ2 Files (*.tar.bz2);;"
                "TAR.XZ Files (*.tar.xz);;"
                "7-Zip Files (*.7z);;"
                "All Files (*)"
            )
        else:
            format_filter = "ZIP Files (*.zip);;All Files (*)"

        # Get output path
        output_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Зберегти архів як", self.archive_name_edit.text(), format_filter
        )

        if not output_path:
            return

        # Ensure file has proper extension
        if COMPRESS_AVAILABLE:
            if not any(
                output_path.endswith(ext)
                for ext in [".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".7z"]
            ):
                # Default to .zip if no extension provided
                output_path += ".zip"
        else:
            if not output_path.endswith(".zip"):
                output_path += ".zip"

        self.compress_btn.setEnabled(False)
        self.compression_log.clear()

        # Start compression thread with compression level
        self.compressor_thread = FileCompressor(
            self.compression_files, output_path, compression_level
        )
        self.compressor_thread.progress_updated.connect(
            self.update_compression_progress
        )
        self.compressor_thread.compression_finished.connect(
            self.on_compression_finished
        )
        self.compressor_thread.start()

    def update_compression_progress(self, progress, message):
        """Update compression progress"""
        self.compression_log.append(
            f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        )

    def on_compression_finished(self, output_path, success):
        """Handle compression completion"""
        self.compress_btn.setEnabled(True)

        if success:
            self.compression_log.append(
                f"✅ Successfully created archive: {output_path}"
            )
            QMessageBox.information(
                self, "Успіх", f"Файли успішно стиснено!\nЗбережено в: {output_path}"
            )

            # Log to main application
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Compressed {len(self.compression_files)} files to {output_path}"
                )
        else:
            self.compression_log.append("❌ Compression failed!")
            QMessageBox.critical(
                self,
                "Помилка",
                "Стиснення не вдалося. Будь ласка, перевірте журнал для деталей.",
            )

    def get_file_category(self, file_path: str) -> str:
        """Get file category based on extension"""
        ext = os.path.splitext(file_path)[1].lower()

        # Documents
        if ext in [
            ".pdf",
            ".doc",
            ".docx",
            ".txt",
            ".rtf",
            ".odt",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".ods",
            ".odp",
        ]:
            return "Документи"

        # Images
        elif ext in [
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".tiff",
            ".svg",
            ".webp",
            ".ico",
        ]:
            return "Зображення"

        # Videos
        elif ext in [
            ".mp4",
            ".avi",
            ".mkv",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
            ".3gp",
        ]:
            return "Відео"

        # Audio
        elif ext in [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".opus"]:
            return "Аудіо"

        # Archives
        elif ext in [
            ".zip",
            ".rar",
            ".7z",
            ".tar",
            ".gz",
            ".bz2",
            ".xz",
            ".tar.gz",
            ".tar.bz2",
            ".tar.xz",
        ]:
            return "Архіви"

        # Programs
        elif ext in [".exe", ".msi", ".deb", ".rpm", ".dmg", ".pkg", ".app"]:
            return "Програми"

        # Text files
        elif ext in [
            ".txt",
            ".md",
            ".csv",
            ".json",
            ".xml",
            ".html",
            ".css",
            ".js",
            ".py",
            ".java",
            ".cpp",
            ".c",
        ]:
            return "Тексти"

        # Spreadsheets
        elif ext in [".csv", ".xls", ".xlsx", ".ods"]:
            return "Документи"

        # Presentations
        elif ext in [".ppt", ".pptx", ".odp"]:
            return "Документи"

        else:
            return "Інше"

    def identify_folder_structure(self, folder_path: str) -> dict:
        """Identify if folder follows 'Робочі столи/Рік/Дата' structure"""
        folder_name = os.path.basename(folder_path)

        # Check if it's a "Робочі столі" folder
        if (
            "робочі столи" in folder_name.lower()
            or "робочий стіл" in folder_name.lower()
        ):
            return {
                "type": "archive_root",
                "name": folder_name,
                "icon": "📂",
                "description": "Корінь архіву",
            }

        # Check if it's a year folder
        if folder_name.isdigit() and len(folder_name) == 4:
            year = int(folder_name)
            if 2000 <= year <= datetime.now().year:
                return {
                    "type": "year",
                    "name": folder_name,
                    "icon": "📅",
                    "description": f"Архіви за {year} рік",
                }

        # Check if it's a date folder (DD-MM-YYYY or DD-MM-YYYY HH-MM)
        date_patterns = [
            r"^\d{2}-\d{2}-\d{4}$",  # DD-MM-YYYY
            r"^\d{2}-\d{2}-\d{4} \d{2}-\d{2}$",  # DD-MM-YYYY HH-MM
            r"^\d{4}-\d{2}-\d{2}$",  # YYYY-MM-DD
        ]

        import re

        for pattern in date_patterns:
            if re.match(pattern, folder_name):
                return {
                    "type": "date",
                    "name": folder_name,
                    "icon": "📁",
                    "description": f"Архів за {folder_name}",
                }

        # Default folder
        # Check for common folder types
        folder_name_lower = folder_name.lower()
        if any(
            keyword in folder_name_lower
            for keyword in ["download", "завантаж", "отриман"]
        ):
            return {
                "type": "downloads",
                "name": folder_name,
                "icon": "⬇️",
                "description": "Завантаження",
            }
        elif any(
            keyword in folder_name_lower
            for keyword in ["document", "документ", "текст"]
        ):
            return {
                "type": "documents",
                "name": folder_name,
                "icon": "📄",
                "description": "Документи",
            }
        elif any(
            keyword in folder_name_lower
            for keyword in ["picture", "зображення", "фото", "photo", "image"]
        ):
            return {
                "type": "images",
                "name": folder_name,
                "icon": "🖼️",
                "description": "Зображення",
            }
        elif any(
            keyword in folder_name_lower
            for keyword in ["video", "відео", "фільм", "movie"]
        ):
            return {
                "type": "videos",
                "name": folder_name,
                "icon": "🎬",
                "description": "Відео",
            }
        elif any(
            keyword in folder_name_lower
            for keyword in ["music", "музика", "аудіо", "audio"]
        ):
            return {
                "type": "music",
                "name": folder_name,
                "icon": "🎵",
                "description": "Музика",
            }
        elif any(
            keyword in folder_name_lower
            for keyword in ["archive", "архів", "backup", "резерв"]
        ):
            return {
                "type": "archive",
                "name": folder_name,
                "icon": "🗜️",
                "description": "Архів",
            }

        # Default folder
        return {
            "type": "folder",
            "name": folder_name,
            "icon": "📁",
            "description": "Папка",
        }

    def clear_search(self):
        """Clear search and show all files"""
        self.search_edit.clear()
        self.refresh_archive_tree()

    def refresh_archive_tree(self):
        """Search files in archives"""
        # Get search parameters
        search_term = self.search_edit.text().strip()

        # Update current search term
        self.current_search_term = search_term

        # If no search term, show all files with splash screen
        if not search_term:
            # Show splash screen for refresh
            self.show_archive_splash(
                "🔄 Оновлення архіву...", "Оновлення списку файлів..."
            )

            # Update the search button to show searching state
            search_btn = self.findChild(QPushButton, "search_button")
            if search_btn:
                search_btn.setEnabled(False)
                search_btn.setText("Оновлення...")

            # Add a small delay to ensure splash screen appears before starting search
            QApplication.processEvents()

            self.refresh_archive_tree()
            return
        # Show archive splash screen
        self.show_archive_splash("📂 Пошук в архівах...", f"Пошук: '{search_term}'...")

        # Update the search button to show searching state
        search_btn = self.findChild(QPushButton, "search_button")
        if search_btn:
            search_btn.setEnabled(False)
            search_btn.setText("Пошук...")

        # Add a small delay to ensure splash screen appears before starting search
        QApplication.processEvents()

        self.refresh_archive_tree(search_term)

        # The splash screen will be hidden when refresh_archive_tree completes
        # Button reset happens in refresh_archive_tree

    def refresh_archive_tree(self, search_term: str = ""):
        """Refresh the archive tree view with optional search and category filtering"""
        # If in analytics mode, ask user if they want to switch to normal mode first
        if getattr(self, "is_showing_analytics_results", False):
            reply = QMessageBox.question(
                self,
                "Режим аналітики",
                "Ви перебуваєте в режимі перегляду результатів аналітики.\n\n"
                "Бажаєте очистити результати та переключитися на звичайний режим?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.switch_to_normal_mode()
                return  # switch_to_normal_mode will call refresh internally
            else:
                return  # User chose to stay in analytics mode

        # Determine scan path
        scan_path = getattr(self, "archive_scan_path", self.working_path)
        if not scan_path or not os.path.exists(scan_path):
            self.archive_tree.clear()
            item = QTreeWidgetItem(self.archive_tree)
            item.setText(0, "Каталог не знайдено")

            # Show error message on splash screen before hiding
            if self.archive_splash and self.archive_splash.isVisible():
                self.archive_splash.update_progress(0, "Помилка: шлях не знайдено")
                QApplication.processEvents()
                # Small delay to show error message
                QTimer.singleShot(1000, self.hide_archive_splash)  # Hide after 1 second
            else:
                self.hide_archive_splash()

            # Reset search button on error
            search_btn = self.findChild(QPushButton, "search_button")
            if search_btn:
                search_btn.setEnabled(True)
                search_btn.setText("Пошук")
            return

        # Show splash screen if not already visible
        if not (self.archive_splash and self.archive_splash.isVisible()):
            if search_term:
                self.show_archive_splash(
                    "📂 Пошук в архівах...", f"Пошук: '{search_term}'..."
                )
            else:
                self.show_archive_splash(
                    "🔄 Оновлення архіву...", "Оновлення списку файлів..."
                )

        # Clear tree before rebuilding to prevent duplicates
        self.archive_tree.clear()

        # Stop any existing tree building thread
        if hasattr(self, "tree_builder_thread") and self.tree_builder_thread:
            self.tree_builder_thread.stop()
            self.tree_builder_thread.wait()
            self.tree_builder_thread.deleteLater()

        # Use threading to prevent freezing
        # Create a simple thread to run the tree building without blocking UI
        import threading

        tree_thread = threading.Thread(
            target=self._build_tree_threaded, args=(scan_path, search_term)
        )
        tree_thread.daemon = True  # Thread will exit when main program exits
        tree_thread.start()

    def _build_tree_threaded(self, scan_path: str, search_term: str = ""):
        """Build tree in background thread with progress updates"""
        try:
            # Update splash screen progress immediately
            QTimer.singleShot(
                0, lambda: self._update_splash_progress_safe("Початок сканування...")
            )

            # Small delay to show initial progress
            import time

            time.sleep(0.1)

            # Update progress for cache building
            QTimer.singleShot(
                0, lambda: self._update_splash_progress_safe("Побудова кешу файлів...")
            )
            time.sleep(0.1)

            # Update progress for file scanning
            QTimer.singleShot(
                0,
                lambda: self._update_splash_progress_safe(
                    "Сканування файлів та папок..."
                ),
            )
            time.sleep(0.1)

            # Run the actual tree building (this won't touch UI)
            self._build_tree_directly(scan_path, search_term)

            # Update UI on main thread when done
            QTimer.singleShot(0, self._on_tree_building_completed)

        except Exception as e:
            # Handle errors on main thread
            QTimer.singleShot(0, lambda: self._on_tree_building_error(str(e)))

    def _update_splash_progress_safe(self, message):
        """Thread-safe splash screen progress update"""
        if self.archive_splash and self.archive_splash.isVisible():
            self.archive_splash.update_progress(0, message)
        if hasattr(self, "archive_status_label"):
            self.archive_status_label.setText(message)

    def _on_tree_building_completed(self):
        """Called when tree building completes (runs on main thread)"""
        # Hide splash screen and reset button
        self.hide_archive_splash()
        search_btn = self.findChild(QPushButton, "search_button")
        if search_btn:
            search_btn.setEnabled(True)
            search_btn.setText("Пошук")

        # Clear any lingering progress messages by setting a final status
        if hasattr(self, "archive_status_label"):
            self.archive_status_label.setText("Готовий до пошуку та фільтрації")

    def _on_tree_building_error(self, error_message):
        """Called when tree building has an error (runs on main thread)"""
        self.archive_status_label.setText(f"Помилка: {error_message}")
        # Hide splash screen and reset button on error
        self.hide_archive_splash()
        search_btn = self.findChild(QPushButton, "search_button")
        if search_btn:
            search_btn.setEnabled(True)
            search_btn.setText("Пошук")

    def _build_tree_in_thread(self, scan_path: str, search_term: str = ""):
        """Build tree in background thread"""
        try:
            # Update splash screen progress using thread-safe method
            QTimer.singleShot(
                0, lambda: self._update_splash_progress(25, "Побудова дерева файлів...")
            )

            # Build the tree data in background (this won't touch UI)
            tree_data = self._build_tree_data(scan_path, search_term)

            # Update UI on main thread when done
            QTimer.singleShot(0, lambda: self._update_tree_ui(tree_data))

        except Exception as e:
            # Handle errors on main thread
            QTimer.singleShot(0, lambda: self._handle_tree_error(str(e)))

    def _build_tree_data(self, scan_path: str, search_term: str = ""):
        """Build tree data in background thread (no UI operations)"""
        # This is a simplified version that builds the data structure
        # without touching any UI elements
        tree_items = []

        try:
            # Update progress (thread-safe)
            QTimer.singleShot(
                0, lambda: self._update_splash_progress(50, "Сканування файлів...")
            )

            # Build file cache
            file_cache = {}
            self._build_file_cache_threaded(scan_path, file_cache)

            # Update progress
            QTimer.singleShot(
                0, lambda: self._update_splash_progress(75, "Побудова структури...")
            )

            # Build tree structure from cache
            root_items = self._build_tree_structure_threaded(
                scan_path, file_cache, search_term
            )
            tree_items.extend(root_items)

            # Update progress
            QTimer.singleShot(
                0,
                lambda: self._update_splash_progress(90, "Фіналізація результатів..."),
            )

            return {
                "items": tree_items,
                "count": len(tree_items),
                "scan_path": scan_path,
            }

        except Exception as e:
            raise e

    def _build_file_cache_threaded(self, scan_path: str, file_cache: dict):
        """Build file cache in background thread"""

        def _scan_directory(path: str):
            try:
                for item_name in os.listdir(path):
                    item_path = os.path.join(path, item_name)
                    if os.path.exists(item_path):
                        is_dir = os.path.isdir(item_path)

                        # Get file metadata
                        try:
                            stat_info = os.stat(item_path)
                            file_size = stat_info.st_size
                            modified_time = stat_info.st_mtime
                            modified_str = datetime.fromtimestamp(
                                modified_time
                            ).strftime("%Y-%m-%d %H:%M")
                        except (OSError, PermissionError):
                            file_size = None
                            modified_time = None
                            modified_str = "Невідомо"

                        file_cache[item_path] = {
                            "name": item_name,
                            "path": item_path,
                            "is_dir": is_dir,
                            "name_lower": item_name.lower(),
                            "size": file_size,
                            "modified": modified_str,
                        }

                        if is_dir:
                            _scan_directory(item_path)

            except (PermissionError, OSError):
                # Skip directories we can't access
                pass

        _scan_directory(scan_path)

    def _build_tree_structure_threaded(
        self, scan_path: str, file_cache: dict, search_term: str = ""
    ):
        """Build tree structure from cache in background thread"""
        root_items = []

        for file_path, file_data in file_cache.items():
            # Check if item matches search term
            if search_term and search_term.lower() not in file_data["name_lower"]:
                continue

            # Only include items directly in the scan path for now
            if os.path.dirname(file_path) == scan_path:
                root_items.append(file_data)

        # Sort: directories first, then files
        root_items.sort(key=lambda x: (not x["is_dir"], x["name_lower"]))

        return root_items

    def _update_splash_progress(self, value, message):
        """Thread-safe splash screen progress update"""
        if self.archive_splash and self.archive_splash.isVisible():
            self.archive_splash.update_progress(value, message)
        if hasattr(self, "archive_status_label"):
            self.archive_status_label.setText(message)

    def _update_tree_ui(self, tree_data):
        """Update UI with tree data (runs on main thread)"""
        try:
            self.archive_tree.clear()

            for item_data in tree_data["items"]:
                tree_item = QTreeWidgetItem(self.archive_tree)
                tree_item.setText(0, item_data["name"])
                tree_item.setData(0, Qt.UserRole, item_data["path"])

                if item_data["is_dir"]:
                    tree_item.setText(0, f"📁 {item_data['name']}")
                    tree_item.setData(1, Qt.DisplayRole, "Папка")
                else:
                    file_ext = os.path.splitext(item_data["name"])[1].lower()
                    icon = self._get_file_icon(file_ext)
                    tree_item.setText(0, f"{icon} {item_data['name']}")
                    size_str = (
                        humanize.naturalsize(item_data["size"])
                        if item_data["size"]
                        else "Невідомо"
                    )
                    tree_item.setData(1, Qt.DisplayRole, size_str)
                    tree_item.setData(
                        2, Qt.DisplayRole, item_data.get("modified", "Невідомо")
                    )

            # Set headers
            self.archive_tree.setHeaderLabels(
                ["Назва файлу", "Розмір", "Дата модифікації"]
            )

            # Show final count
            final_count = tree_data["count"]
            self.archive_status_label.setText(
                f"Дерево побудовано: {final_count} елементів"
            )

            # Expand tree
            if final_count > 0:
                self.archive_tree.expandAll()

        except Exception as e:
            self.archive_status_label.setText(f"Помилка при відображенні: {e}")

        finally:
            # Always hide splash screen and reset button
            self.hide_archive_splash()
            search_btn = self.findChild(QPushButton, "search_button")
            if search_btn:
                search_btn.setEnabled(True)
                search_btn.setText("Пошук")

    def _handle_tree_error(self, error_message):
        """Handle tree building errors (runs on main thread)"""
        self.archive_status_label.setText(f"Помилка: {error_message}")
        if hasattr(self, "main_window") and hasattr(self.main_window, "log_message"):
            self.main_window.log_message(
                f"CleanupHelper: Помилка побудови дерева: {error_message}"
            )

        # Hide splash screen and reset button on error
        self.hide_archive_splash()
        search_btn = self.findChild(QPushButton, "search_button")
        if search_btn:
            search_btn.setEnabled(True)
            search_btn.setText("Пошук")

    def _get_file_icon(self, extension: str) -> str:
        """Get appropriate icon for file extension"""
        icon_map = {
            ".txt": "📄",
            ".doc": "📝",
            ".docx": "📝",
            ".pdf": "📋",
            ".jpg": "🖼️",
            ".jpeg": "🖼️",
            ".png": "🖼️",
            ".gif": "🖼️",
            ".bmp": "🖼️",
            ".mp4": "🎬",
            ".avi": "🎬",
            ".mkv": "🎬",
            ".mov": "🎬",
            ".mp3": "🎵",
            ".wav": "🎵",
            ".flac": "🎵",
            ".aac": "🎵",
            ".zip": "🗜️",
            ".rar": "🗜️",
            ".7z": "🗜️",
            ".tar": "🗜️",
            ".gz": "🗜️",
            ".exe": "⚙️",
            ".msi": "⚙️",
            ".bat": "⚙️",
            ".cmd": "⚙️",
            ".py": "🐍",
            ".js": "🌐",
            ".html": "🌐",
            ".css": "🎨",
        }
        return icon_map.get(extension, "📄")

    def _on_tree_progress_updated(self, value, message):
        """Handle tree building progress updates"""
        # Update splash screen if it's active
        if self.archive_splash and self.archive_splash.isVisible():
            self.archive_splash.update_progress(value, message)

        # Update status label
        if hasattr(self, "archive_status_label"):
            self.archive_status_label.setText(message)

    def _on_tree_built(self, tree_widget):
        """Handle successful tree building completion"""
        try:
            # Copy the tree structure to our main tree widget
            self.archive_tree.clear()

            # Copy all items from the built tree to our main tree
            def copy_tree_items(source_parent, target_parent):
                for i in range(source_parent.childCount()):
                    source_item = source_parent.child(i)
                    target_item = QTreeWidgetItem(target_parent)

                    # Copy all columns
                    for col in range(source_item.columnCount()):
                        target_item.setText(col, source_item.text(col))
                        target_item.setData(
                            col, Qt.UserRole, source_item.data(col, Qt.UserRole)
                        )

                    # Recursively copy children
                    copy_tree_items(source_item, target_item)

            copy_tree_items(
                tree_widget.invisibleRootItem(), self.archive_tree.invisibleRootItem()
            )

            # Set tree headers
            self.archive_tree.setHeaderLabels(
                ["Назва файлу", "Розмір", "Дата модифікації"]
            )

            # Count and display final results
            final_count = self._count_tree_items(self.archive_tree.invisibleRootItem())
            self.archive_status_label.setText(
                f"Дерево побудовано: {final_count} елементів"
            )

            # Expand the tree to show items
            if final_count > 0:
                self.archive_tree.expandAll()

        except Exception as e:
            self.archive_status_label.setText(f"Помилка при відображенні дерева: {e}")
            if hasattr(self, "main_window") and hasattr(
                self.main_window, "log_message"
            ):
                self.main_window.log_message(
                    f"CleanupHelper: Помилка відображення дерева: {e}"
                )

        finally:
            # Always hide splash screen and reset button
            self.hide_archive_splash()
            search_btn = self.findChild(QPushButton, "search_button")
            if search_btn:
                search_btn.setEnabled(True)
                search_btn.setText("Пошук")

    def _on_tree_error(self, error_message):
        """Handle tree building errors"""
        self.archive_status_label.setText(f"Помилка: {error_message}")
        if hasattr(self, "main_window") and hasattr(self.main_window, "log_message"):
            self.main_window.log_message(
                f"CleanupHelper: Помилка побудови дерева: {error_message}"
            )

        # Hide splash screen and reset button on error
        self.hide_archive_splash()
        search_btn = self.findChild(QPushButton, "search_button")
        if search_btn:
            search_btn.setEnabled(True)
            search_btn.setText("Пошук")

    def _count_tree_items_with_breakdown(self, item):
        """Count total items in tree (recursive) with file/folder breakdown"""
        count = 0
        file_count = 0
        folder_count = 0

        for i in range(item.childCount()):
            child = item.child(i)
            count += 1

            # Check if this is a file or folder
            child_text = child.text(0)
            if child_text.startswith("📁"):
                folder_count += 1
            else:
                file_count += 1

            # Count children recursively
            child_counts = self._count_tree_items_with_details(child)
            count += child_counts["total"]
            file_count += child_counts["files"]
            folder_count += child_counts["folders"]

        return {"total": count, "files": file_count, "folders": folder_count}

    def _count_tree_items_with_details(self, item):
        """Count items with file/folder breakdown (recursive)"""
        total = 0
        files = 0
        folders = 0

        for i in range(item.childCount()):
            child = item.child(i)
            total += 1

            child_text = child.text(0)
            if child_text.startswith("📁"):
                folders += 1
            else:
                files += 1

            # Recursive count
            child_counts = self._count_tree_items_with_details(child)
            total += child_counts["total"]
            files += child_counts["files"]
            folders += child_counts["folders"]

        return {"total": total, "files": files, "folders": folders}

    def _build_tree_directly(self, scan_path: str, search_term: str = ""):
        """Build the tree structure directly from filesystem with timeout (thread-safe version)"""
        try:
            # Check if we have cached data for this path
            current_time = time.time()
            if (
                self._last_scan_path == scan_path
                and self._file_cache
                and current_time - self._cache_timestamp < 300
            ):  # 5 minutes cache
                QTimer.singleShot(
                    0, lambda: self._update_splash_progress_safe("Використання кешу...")
                )
                self._build_tree_from_cache(search_term)
            else:
                # Build cache and tree structure
                QTimer.singleShot(
                    0, lambda: self._update_splash_progress_safe("Сканування файлів...")
                )
                self._build_file_cache(scan_path)
                QTimer.singleShot(
                    0,
                    lambda: self._update_splash_progress_safe(
                        "Побудова дерева файлів..."
                    ),
                )
                self._build_tree_recursive(
                    scan_path, self.archive_tree.invisibleRootItem(), search_term, 0
                )

            # Update status and count on main thread
            final_counts = self._count_tree_items_with_breakdown(
                self.archive_tree.invisibleRootItem()
            )
            QTimer.singleShot(
                0, lambda: self._update_tree_status_with_details(final_counts)
            )

            # Expand tree on main thread
            if final_counts["total"] > 0:
                QTimer.singleShot(0, lambda: self.archive_tree.expandAll())

        except Exception as e:
            # Handle errors on main thread
            QTimer.singleShot(0, lambda: self._on_tree_building_error(str(e)))

    def _update_tree_status(self, final_count):
        """Update tree status on main thread"""
        self.archive_status_label.setText(f"Дерево побудовано: {final_count} елементів")

    def _update_tree_status_with_details(self, counts):
        """Update tree status with file/folder breakdown on main thread"""
        total = counts["total"]
        files = counts["files"]
        folders = counts["folders"]
        self.archive_status_label.setText(
            f"Дерево побудовано: {total} елементів ({folders} папок, {files} файлів)"
        )

    def _build_file_cache(self, scan_path: str):
        """Build a cache of the file structure for fast searching"""
        self._file_cache = {}
        self._search_index = {}
        self._last_scan_path = scan_path
        self._cache_timestamp = time.time()

        def _scan_directory(path: str, cache_dict: dict):
            """Recursively scan directory and build cache"""
            try:
                for item_name in os.listdir(path):
                    item_path = os.path.join(path, item_name)
                    if os.path.exists(item_path):
                        is_dir = os.path.isdir(item_path)

                        # Get file metadata
                        try:
                            stat_info = os.stat(item_path)
                            file_size = stat_info.st_size
                            modified_time = stat_info.st_mtime
                            modified_str = datetime.fromtimestamp(
                                modified_time
                            ).strftime("%Y-%m-%d %H:%M")
                        except (OSError, PermissionError):
                            file_size = None
                            modified_time = None
                            modified_str = "Невідомо"

                        cache_dict[item_name] = {
                            "path": item_path,
                            "is_dir": is_dir,
                            "name_lower": item_name.lower(),
                            "size": file_size,
                            "modified_timestamp": modified_time,
                            "modified": modified_str,
                        }

                        # Add to search index for faster lookups
                        name_lower = item_name.lower()
                        for i in range(len(name_lower)):
                            for j in range(
                                i + 1, min(i + 20, len(name_lower) + 1)
                            ):  # Limit substring length
                                substring = name_lower[i:j]
                                if substring not in self._search_index:
                                    self._search_index[substring] = []
                                self._search_index[substring].append(item_path)

                        if is_dir:
                            cache_dict[item_name]["children"] = {}
                            _scan_directory(
                                item_path, cache_dict[item_name]["children"]
                            )
            except (PermissionError, OSError):
                pass

        _scan_directory(scan_path, self._file_cache)

    def _build_tree_from_cache(self, search_term: str = ""):
        """Build tree from cached data much faster than filesystem scanning"""
        if not self._file_cache:
            return

        def _build_from_cache(
            cache_dict: dict, parent_item: QTreeWidgetItem, search_term: str
        ):
            """Recursively build tree from cache"""
            for item_name, item_data in cache_dict.items():
                is_dir = item_data["is_dir"]

                if is_dir:
                    # For directories, check both original name and display name
                    folder_info = self.identify_folder_structure(item_data["path"])
                    dir_matches = not search_term or self._matches_search_term(
                        search_term, folder_info["name"]
                    )

                    # Create directory item (always, to preserve tree structure)
                    dir_item = QTreeWidgetItem(parent_item)
                    # Include icon emoji in text (like the working _build_tree_recursive does)
                    display_name = f"{folder_info['icon']} {folder_info['name']}"
                    dir_item.setText(0, display_name)
                    dir_item.setText(1, "Папка")
                    dir_item.setText(2, "")
                    dir_item.setText(3, folder_info["type"])
                    dir_item.setText(4, item_data["path"])

                    # Recursively add children (filtered by search term)
                    if "children" in item_data:
                        _build_from_cache(item_data["children"], dir_item, search_term)

                        # Update item count after building children
                        try:
                            sub_items = len(item_data.get("children", {}))
                            if sub_items > 0:
                                dir_item.setText(1, f"Папка ({sub_items} елементів)")
                        except Exception:
                            logger.debug(
                                f"Failed to count sub-items for directory item"
                            )
                    else:
                        dir_item.setText(1, "Папка")

                    # If directory doesn't match and no children matched, remove the empty folder
                    if not dir_matches and dir_item.childCount() == 0:
                        parent_item.removeChild(dir_item)

                    continue

                # For files (not directories), create file item
                file_item = QTreeWidgetItem(parent_item)
                try:
                    # Use cached values instead of filesystem calls
                    file_category = self.get_file_category(item_data["path"])
                    _, file_ext = os.path.splitext(item_name)
                    file_icon = self.get_file_icon(item_data["path"], file_ext)
                    # Include icon emoji in text (like the working _build_tree_recursive does)
                    display_name = f"{file_icon} {item_name}"

                    file_item.setText(0, display_name)

                    # Use cached size
                    if "size" in item_data and item_data["size"] is not None:
                        file_size = item_data["size"]
                        try:
                            import humanize

                            file_item.setText(1, humanize.naturalsize(file_size))
                        except ImportError:
                            size_mb = file_size / (1024 * 1024)
                            if size_mb < 1:
                                file_item.setText(1, f"{file_size / 1024:.1f} KB")
                            else:
                                file_item.setText(1, f"{size_mb:.1f} MB")
                    else:
                        file_item.setText(1, "Розмір невідомий")

                    # Use cached modified time
                    if "modified" in item_data and item_data["modified"]:
                        file_item.setText(2, item_data["modified"])
                    else:
                        file_item.setText(2, "")

                    file_item.setText(3, file_category)
                    file_item.setText(4, item_data["path"])

                except Exception:
                    # Include default file icon in text
                    file_item.setText(0, f"📄 {item_name}")
                    file_item.setText(1, "Розмір невідомий")
                    file_item.setText(2, "")
                    file_item.setText(3, "Файл")
                    file_item.setText(4, item_data["path"])

        _build_from_cache(
            self._file_cache, self.archive_tree.invisibleRootItem(), search_term
        )

    def _build_tree_recursive(
        self, path: str, parent_item: QTreeWidgetItem, search_term: str, depth: int = 0
    ):
        """Recursively build tree structure from filesystem"""
        try:
            # Limit depth to prevent infinite recursion
            if depth > 10:
                return

            if depth == 0:
                self._scanned_items = 0

            items = []
            try:
                for item_name in os.listdir(path):
                    item_path = os.path.join(path, item_name)
                    if os.path.exists(item_path):
                        items.append((item_name, item_path, os.path.isdir(item_path)))
            except (PermissionError, OSError):
                return

            # Separate directories and files
            directories = [(name, path) for name, path, is_dir in items if is_dir]
            files = [(name, path) for name, path, is_dir in items if not is_dir]

            if depth == 0:
                self.archive_status_label.setText(
                    f"Сканування: {len(directories)} папок, {len(files)} файлів..."
                )
            elif not hasattr(self, "_scanned_items"):
                self._scanned_items = 0

            self._scanned_items += len(directories) + len(files)

            # Update progress for full scans
            if depth == 0 and self._scanned_items % 50 == 0:  # Update every 50 items
                self.archive_status_label.setText(
                    f"Сканування: {self._scanned_items} елементів оброблено..."
                )

            # Sort directories first, then files
            directories.sort(key=lambda x: x[0].lower())
            files.sort(key=lambda x: x[0].lower())

            # Add directories
            for dir_name, dir_path in directories:
                # Create directory item first to get display name
                dir_item = QTreeWidgetItem(parent_item)
                folder_info = self.identify_folder_structure(dir_path)
                display_name = f"{folder_info['icon']} {folder_info['name']}"

                dir_matches = not search_term or self._matches_search_term(
                    search_term, folder_info["name"]
                )

                # Check search filter with improved matching using display name
                if not dir_matches:
                    # Check if it has matching children
                    has_matching_children = self._has_matching_children(
                        dir_path, search_term
                    )
                    if not has_matching_children:
                        # Only remove if no children match
                        parent_item.removeChild(dir_item)
                        continue
                    else:
                        # Directory doesn't match but has matching children - keep it
                        dir_item.setText(
                            0, f"📁 {folder_info['name']} (має відповідні файли)"
                        )
                        # Set a light color to indicate it doesn't match directly
                        dir_item.setForeground(0, QColor(128, 128, 128))
                dir_item.setText(0, display_name)
                dir_item.setText(1, "Папка")
                dir_item.setText(2, "")
                dir_item.setText(3, folder_info["type"])
                dir_item.setText(4, dir_path)

                # Count items in this directory
                try:
                    sub_items = len(os.listdir(dir_path))
                    dir_item.setText(1, f"Папка ({sub_items} елементів)")
                except Exception:
                    logger.debug(f"Failed to count directory items: {dir_path}")

                # Always add a placeholder child to ensure expand icon is visible
                # We'll remove it later if we add actual children
                placeholder = QTreeWidgetItem(dir_item)
                placeholder.setText(0, "Завантаження...")

                # Recursively add subdirectories and files
                self._build_tree_recursive(dir_path, dir_item, search_term, depth + 1)

                # Remove placeholder if we added actual children
                if dir_item.childCount() > 1:
                    dir_item.removeChild(placeholder)
                elif dir_item.childCount() == 1 and placeholder == dir_item.child(0):
                    # Keep placeholder to show it's an empty directory
                    placeholder.setText(0, "(пуста папка)")
                    placeholder.setForeground(0, QColor(128, 128, 128))

            # Add files
            for file_name, file_path in files:
                # Check search filter with improved matching first using file name only
                if search_term and not self._matches_search_term(
                    search_term, file_name
                ):
                    continue
                # Create file item
                file_item = QTreeWidgetItem(parent_item)
                try:
                    file_size = os.path.getsize(file_path)
                    file_mtime = os.path.getmtime(file_path)
                    file_category = self.get_file_category(file_path)

                    # Get file icon
                    file_icon = self.get_file_icon(file_path)
                    display_name = f"{file_icon} {file_name}"

                    file_item.setText(0, display_name)
                    file_item.setText(1, humanize.naturalsize(file_size))
                    file_item.setText(
                        2, datetime.fromtimestamp(file_mtime).strftime("%Y-%m-%d %H:%M")
                    )
                    file_item.setText(3, file_category)
                    file_item.setText(4, file_path)
                except OSError:
                    file_item.setText(0, f"📄 {file_name}")
                    file_item.setText(1, "Розмір невідомий")
                    file_item.setText(2, "")
                    file_item.setText(3, "Файл")
                    file_item.setText(4, file_path)

            if depth == 0:
                # Don't set completion status here - let the completion callback handle it
                pass

        except Exception as e:
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Error processing {path}: {e}"
                )

    def _count_tree_items(self, item: QTreeWidgetItem) -> int:
        """Count all items in the tree recursively"""
        # Don't count the invisible root item
        if item == self.archive_tree.invisibleRootItem():
            count = 0
        else:
            count = 1  # Count this item

        for i in range(item.childCount()):
            count += self._count_tree_items(item.child(i))
        return count

    def update_archive_scan_progress(self, progress, message):
        """Update archive scan progress"""
        self.archive_status_label.setText(message)

    def on_archive_scan_finished(self, results):
        """Handle archive scan completion"""
        # Cache the results for faster future access
        if hasattr(self, "current_scan_path"):
            self.cache_scan_results(self.current_scan_path, results)

        # Apply search filters if needed
        search_term = getattr(self, "current_search_term", "")

        if search_term:
            self._populate_from_filtered_results(results, search_term)
        else:
            self._populate_from_cached_results(results, "")

        # Hide progress bar after completion

    def _populate_from_cached_results(self, results: dict, search_term: str = ""):
        """Populate archive tree from cached or scan results"""
        self.archive_tree.clear()

        if not results.get("files"):
            item = QTreeWidgetItem(self.archive_tree)
            item.setText(0, "Файли не знайдено")
            return

        # Apply filters if needed
        if search_term:
            filtered_files = []
            for file_info in results["files"]:
                file_path = file_info.get("path", "")
                if not file_path or not os.path.exists(file_path):
                    continue

                # Text search filter
                if search_term:
                    file_name = os.path.basename(file_path).lower()
                    if search_term not in file_name:
                        continue

                filtered_files.append(file_info)
            results["files"] = filtered_files

        # Group files by directory
        directory_tree = {}
        for file_info in results["files"]:
            dir_path = os.path.dirname(file_info["path"])
            if dir_path not in directory_tree:
                directory_tree[dir_path] = []
            directory_tree[dir_path].append(file_info)

        # Populate tree
        self._populate_archive_tree_from_scan_results(
            directory_tree, self.archive_tree.invisibleRootItem()
        )

    def _populate_from_filtered_results(self, results: dict, search_term: str):
        """Populate archive tree with filtered results"""
        self._populate_from_cached_results(results, search_term)

    def _filter_analytics_results(self, search_term: str):
        """Filter already loaded analytics results"""
        if (
            not hasattr(self, "analytics_scan_results")
            or not self.analytics_scan_results
        ):
            return

        self.archive_status_label.setText("Фільтрація результатів аналітики...")

        # Clear current tree and reload with filters
        self.archive_tree.clear()

        # Add root item
        root_item = QTreeWidgetItem(self.archive_tree)
        root_item.setText(0, f"📊 Відфільтровані результати аналітики")
        root_item.setText(1, "Фільтрується...")
        root_item.setText(2, "Analytics Scan")
        root_item.setText(3, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        root_item.setText(4, "analytics_scan_results")

        font = root_item.font(0)
        font.setBold(True)
        root_item.setFont(0, font)
        root_item.setExpanded(True)

        # Filter files based on criteria
        scanned_files = self.analytics_scan_results.get("files", [])
        filtered_files = []

        for file_info in scanned_files:
            file_path = file_info.get("path", "")
            if not file_path or not os.path.exists(file_path):
                continue

            # Apply search filters
            include_file = True

            # Text search filter
            if search_term:
                file_name = os.path.basename(file_path).lower()
                if search_term not in file_name:
                    include_file = False

            if include_file:
                filtered_files.append(file_info)

        # Build directory structure from filtered results
        directory_tree = {}
        for file_info in filtered_files:
            dir_path = os.path.dirname(file_info["path"])
            if dir_path not in directory_tree:
                directory_tree[dir_path] = []
            directory_tree[dir_path].append(
                {
                    "name": file_info["name"],
                    "path": file_info["path"],
                    "size": file_info.get("size", 0),
                    "modified": file_info.get("modified", datetime.now()),
                    "extension": file_info.get("extension", ""),
                    "type": file_info.get("type", "unknown"),
                }
            )

        # Populate tree with filtered results
        self._populate_archive_tree_from_scan_results(directory_tree, root_item)

        # Update root item with filtered count
        root_item.setText(1, f"{len(filtered_files)} файлів (з {len(scanned_files)})")

        # Update status and hide progress
        self.archive_status_label.setText(
            f"📊 Відфільтровано: {len(filtered_files)} з {len(scanned_files)} файлів"
        )

    def _get_file_category(self, extension: str) -> str:
        """Get file category based on extension"""
        ext = extension.lower().lstrip(".")

        categories = {
            "Документи": [
                ".pdf",
                ".doc",
                ".docx",
                ".txt",
                ".rtf",
                ".odt",
                ".xls",
                ".xlsx",
                ".ppt",
                ".pptx",
                ".ods",
                ".odp",
            ],
            "Зображення": [
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".bmp",
                ".tiff",
                ".svg",
                ".webp",
                ".ico",
            ],
            "Відео": [
                ".mp4",
                ".avi",
                ".mkv",
                ".mov",
                ".wmv",
                ".flv",
                ".webm",
                ".m4v",
                ".3gp",
            ],
            "Аудіо": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".opus"],
            "Архіви": [
                ".zip",
                ".rar",
                ".7z",
                ".tar",
                ".gz",
                ".bz2",
                ".xz",
                ".tar.gz",
                ".tar.bz2",
                ".tar.xz",
            ],
            "Програми": [".exe", ".msi", ".deb", ".rpm", ".dmg", ".pkg", ".app"],
            "Тексти": [
                ".txt",
                ".md",
                ".rst",
                ".log",
                ".ini",
                ".cfg",
                ".conf",
                ".yaml",
                ".yml",
                ".json",
                ".xml",
                ".csv",
            ],
        }

        for category, extensions in categories.items():
            if ext in extensions:
                return category

        return "Всі файли"

    def _build_folder_tree(self, root_path: str, parent_item: QTreeWidgetItem = None):
        """Build hierarchical folder tree with proper structure detection"""
        try:
            # Get all items in current directory
            items = []
            try:
                for item_name in os.listdir(root_path):
                    item_path = os.path.join(root_path, item_name)
                    items.append((item_name, item_path, os.path.isdir(item_path)))
            except PermissionError:
                return

            # Separate directories and files
            directories = [(name, path) for name, path, is_dir in items if is_dir]
            files = [(name, path) for name, path, is_dir in items if not is_dir]

            # Process directories first
            for dir_name, dir_path in sorted(directories):
                # Skip hidden files unless enabled
                if dir_name.startswith(".") and not hasattr(self, "show_hidden_files"):
                    continue

                # Identify folder structure
                folder_info = self.identify_folder_structure(dir_path)

                # Create tree item for directory
                dir_item = QTreeWidgetItem(parent_item or self.archive_tree)
                dir_item.setText(0, f"{folder_info['icon']} {folder_info['name']}")
                dir_item.setText(1, "")  # Size will be calculated later
                dir_item.setText(2, "")  # Modified time
                dir_item.setText(3, folder_info["type"])
                dir_item.setText(4, dir_path)

                # Store folder info in item data
                dir_item.setData(0, Qt.UserRole, folder_info)

                # Recursively build subdirectories
                self._build_folder_tree(dir_path, dir_item)

                # Calculate folder size and count
                self._calculate_folder_stats(dir_item, dir_path)

            # Process files
            for file_name, file_path in sorted(files):
                # Apply search and category filters
                if not self._should_show_file(file_name, file_path):
                    continue

                # Skip hidden files unless enabled
                if file_name.startswith(".") and not hasattr(self, "show_hidden_files"):
                    continue

                try:
                    file_size = os.path.getsize(file_path)
                    file_mtime = os.path.getmtime(file_path)
                    file_category = self.get_file_category(file_path)

                    # Create tree item for file
                    file_item = QTreeWidgetItem(parent_item or self.archive_tree)
                    file_icon = self.get_file_icon(file_path)
                    file_item.setText(0, f"{file_icon} {file_name}")
                    file_item.setText(1, humanize.naturalsize(file_size))
                    file_item.setText(
                        2, datetime.fromtimestamp(file_mtime).strftime("%Y-%m-%d %H:%M")
                    )
                    file_item.setText(3, file_category)
                    file_item.setText(4, file_path)

                except OSError:
                    continue

        except Exception as e:
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Помилка побудови дерева папок: {e}"
                )

    def _should_show_file(self, file_name: str, file_path: str) -> bool:
        """Check if file should be shown based on search criteria"""
        # Check search term
        if self.current_search_term:
            if self.current_search_term not in file_name.lower():
                return False

        return True

    def _calculate_folder_stats(self, folder_item: QTreeWidgetItem, folder_path: str):
        """Calculate total size and file count for a folder"""
        total_size = 0
        file_count = 0

        try:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(file_path)
                        total_size += file_size
                        file_count += 1
                    except OSError:
                        continue

                # Stop at first level for performance (don't count subdirectories)
                break

            # Update folder item with stats
            folder_item.setText(1, humanize.naturalsize(total_size))
            folder_item.setText(2, f"{file_count} файлів")

        except Exception:
            pass

    def _matches_search_term(self, search_term: str, item_name: str) -> bool:
        """Optimized search term matching"""
        if not search_term or not item_name:
            return True

        search_lower = search_term.lower().strip()
        item_lower = item_name.lower()

        # For very short search terms (1-2 characters), use exact matching only
        if len(search_lower) <= 2:
            return search_lower in item_lower

        # Exact match (fastest)
        if search_lower in item_lower:
            return True

        # Optimized fuzzy matching - much simpler and faster
        if len(search_lower) >= 3:
            # Simple word boundary matching
            import re

            words = re.findall(r"\b\w+\b", item_lower)
            for word in words:
                if len(word) >= len(search_lower):
                    if word.startswith(search_lower) or word.endswith(search_lower):
                        return True
                    # Simple character similarity for words of similar length
                    if abs(len(word) - len(search_lower)) <= 2:
                        common_chars = sum(1 for c in search_lower if c in word)
                        if common_chars >= len(search_lower) * 0.8:
                            return True

        return False

    def _has_matching_children(self, dir_path: str, search_term: str) -> bool:
        """Check if directory has any files/subdirectories that match search term"""
        try:
            for item_name in os.listdir(dir_path):
                item_path = os.path.join(dir_path, item_name)
                if os.path.exists(item_path):
                    if self._matches_search_term(search_term, item_name):
                        return True
                    # If it's a directory, check recursively
                    if os.path.isdir(item_path):
                        if self._has_matching_children(item_path, search_term):
                            return True
        except (PermissionError, OSError):
            pass
        return False

    def _fuzzy_match(self, pattern: str, text: str, max_distance: int) -> bool:
        """Simple fuzzy matching using character-by-character comparison"""
        pattern_len = len(pattern)
        text_len = len(text)

        # If text is much shorter than pattern, no match possible
        if text_len < pattern_len - max_distance:
            return False

        # If pattern is much longer than text, no match possible
        if pattern_len > text_len + max_distance:
            return False

        # Simple sliding window approach
        for i in range(text_len - pattern_len + 1):
            window = text[i : i + pattern_len]
            distance = 0
            for j in range(pattern_len):
                if j < len(window) and pattern[j] != window[j]:
                    distance += 1
                    if distance > max_distance:
                        break
            if distance <= max_distance:
                return True

        return False

    def open_file_location(self, item, column):
        """Open file location in file explorer"""
        # Path is in column 4
        file_path = item.text(4)
        if file_path and os.path.exists(file_path):
            import subprocess

            # Ensure the path is absolute and normalized
            abs_path = os.path.abspath(file_path)
            if sys.platform == "win32":
                # Use a list of arguments for security and to handle paths correctly
                subprocess.run(["explorer", "/select,", abs_path])
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", abs_path])
            else:
                # For Linux, open the containing directory
                subprocess.run(["xdg-open", os.path.dirname(abs_path)])

    def open_selected_location(self):
        """Open selected file location"""
        current_item = self.archive_tree.currentItem()
        if current_item:
            self.open_file_location(current_item, 0)

    def restore_selected_file(self):
        """Restore selected file to desktop"""
        current_item = self.archive_tree.currentItem()
        if not current_item:
            return

        # Path is now in column 4 (index 3)
        source_path = current_item.text(4)
        if not source_path or not os.path.exists(source_path):
            return

        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        target_path = os.path.join(desktop_path, os.path.basename(source_path))

        try:
            # Handle name conflicts
            counter = 1
            while os.path.exists(target_path):
                name, ext = os.path.splitext(os.path.basename(source_path))
                target_path = os.path.join(desktop_path, f"{name}_{counter}{ext}")
                counter += 1

            # Copy file
            if os.path.isfile(source_path):
                shutil.copy2(source_path, target_path)
            else:
                shutil.copytree(source_path, target_path)

            QMessageBox.information(
                self,
                "Успіх",
                f"Файл відновлено на робочий стіл:\n{os.path.basename(target_path)}",
            )

            # Log to main application
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Restored {os.path.basename(source_path)} to desktop"
                )

        except Exception as e:
            QMessageBox.critical(
                self, "Помилка", f"Не вдалося відновити файл:\n{str(e)}"
            )

    def select_all_duplicates(self):
        """Select all duplicate files"""
        # Implement selection logic
        pass

    def delete_selected_duplicates(self):
        """Delete selected duplicate files"""
        # Implement deletion logic with confirmation
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            "Are you sure you want to delete the selected duplicate files? This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            # Implement actual deletion
            pass

    def save_settings(self):
        """Save module settings"""
        try:
            settings = {
                "default_scan_path": self.default_scan_path_edit.text(),
                "auto_detect_archives": self.auto_detect_archives.isChecked(),
                "show_hidden_files": self.show_hidden_files.isChecked(),
                "large_file_threshold_mb": self.large_file_threshold_spin.value(),
                "old_file_threshold_days": self.old_file_threshold_spin.value(),
                "thread_count": self.thread_count_spin.value(),
                "enable_caching": self.enable_caching.isChecked(),
            }

            settings_file = os.path.join(
                os.path.expanduser("~"),
                ".DesktopOrganizer",
                "cleanup_helper_settings.json",
            )

            os.makedirs(os.path.dirname(settings_file), exist_ok=True)
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)

            QMessageBox.information(self, "Успіх", "Налаштування успішно збережено!")

            # Log to main application
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message("CleanupHelper: Settings saved")

        except Exception as e:
            QMessageBox.critical(
                self, "Помилка", f"Не вдалося зберегти налаштування:\n{str(e)}"
            )

    def reset_settings(self):
        """Reset settings to defaults"""
        reply = QMessageBox.question(
            self,
            "Confirm Reset",
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.default_scan_path_edit.setText(self.working_path)
            self.auto_detect_archives.setChecked(True)
            self.show_hidden_files.setChecked(False)
            self.large_file_threshold_spin.setValue(10)
            self.old_file_threshold_spin.setValue(365)
            self.thread_count_spin.setValue(4)
            self.enable_caching.setChecked(True)

    def load_settings(self):
        """Load module settings from file"""
        try:
            settings_file = os.path.join(
                os.path.expanduser("~"),
                ".DesktopOrganizer",
                "cleanup_helper_settings.json",
            )

            if not os.path.exists(settings_file):
                return  # Use defaults

            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)

            # Apply loaded settings to UI
            if "default_scan_path" in settings:
                self.default_scan_path_edit.setText(settings["default_scan_path"])
            if "auto_detect_archives" in settings:
                self.auto_detect_archives.setChecked(settings["auto_detect_archives"])
            if "show_hidden_files" in settings:
                self.show_hidden_files.setChecked(settings["show_hidden_files"])
            if "large_file_threshold_mb" in settings:
                self.large_file_threshold_spin.setValue(
                    settings["large_file_threshold_mb"]
                )
            if "old_file_threshold_days" in settings:
                self.old_file_threshold_spin.setValue(
                    settings["old_file_threshold_days"]
                )
            if "thread_count" in settings:
                self.thread_count_spin.setValue(settings["thread_count"])
            if "enable_caching" in settings:
                self.enable_caching.setChecked(settings["enable_caching"])

        except Exception as e:
            print(f"Failed to load settings: {e}")
            # Silently fail - use defaults

    # === Archive Browser Context Menu Methods ===

    def show_archive_context_menu(self, position):
        """Show context menu for archive browser"""
        selected_items = self.archive_tree.selectedItems()
        if not selected_items:
            return

        menu = QMenu(self)

        # Get selected files and directories
        selected_files = self.get_selected_files()
        selected_directories = self.get_selected_directories()
        has_any_selection = selected_files or selected_directories

        # Compression and deletion for both files and directories
        if has_any_selection:
            if selected_files and selected_directories:
                compress_action = menu.addAction("🗜️ Стиснути файли та папки")
            elif selected_files:
                compress_action = menu.addAction("🗜️ Стиснути файли")
            else:
                compress_action = menu.addAction("🗜️ Стиснути папки")
            compress_action.triggered.connect(self.show_compression_window)

            if selected_files and selected_directories:
                delete_action = menu.addAction("🗑️ Видалити файли та папки")
            elif selected_files:
                delete_action = menu.addAction("🗑️ Видалити файли")
            else:
                delete_action = menu.addAction("🗑️ Видалити папки")
            delete_action.triggered.connect(self.delete_selected_items)

            menu.addSeparator()

        # Operations for both files and directories
        open_action = menu.addAction("📂 Відкрити")
        open_action.triggered.connect(self.open_selected_items)

        show_action = menu.addAction("👁️ Показати у провіднику")
        show_action.triggered.connect(self.show_in_explorer)

        # Copy operation
        copy_path_action = menu.addAction("📋 Копіювати шлях")
        copy_path_action.triggered.connect(self.copy_selected_paths)

        menu.addSeparator()

        # Tree operations
        if self.archive_tree.topLevelItemCount() > 0:
            menu.addSeparator()
            expand_all_action = menu.addAction("📂 Розгорнути все")
            expand_all_action.triggered.connect(self.expand_all_tree_items)

            collapse_all_action = menu.addAction("📁 Згорнути все")
            collapse_all_action.triggered.connect(self.collapse_all_tree_items)

        # Restore files (only if files)
        if selected_files:
            restore_action = menu.addAction("↩️ Відновити на стіл")
            restore_action.triggered.connect(self.restore_selected_files)

        menu.exec_(self.archive_tree.viewport().mapToGlobal(position))

    def expand_all_tree_items(self):
        """Expand all tree items recursively"""

        def expand_items(item):
            item.setExpanded(True)
            for i in range(item.childCount()):
                expand_items(item.child(i))

        for i in range(self.archive_tree.topLevelItemCount()):
            expand_items(self.archive_tree.topLevelItem(i))

    def collapse_all_tree_items(self):
        """Collapse all tree items recursively"""

        def collapse_items(item):
            item.setExpanded(False)
            for i in range(item.childCount()):
                collapse_items(item.child(i))

        for i in range(self.archive_tree.topLevelItemCount()):
            collapse_items(self.archive_tree.topLevelItem(i))

    def show_duplicate_context_menu(self, position):
        """Show context menu for duplicate finder"""
        selected_items = self.duplicate_tree.selectedItems()
        if not selected_items:
            return

        menu = QMenu(self)

        # Get selected files and duplicate groups
        selected_files = self.get_selected_duplicate_files()
        selected_groups = self.get_selected_duplicate_groups()
        has_any_selection = selected_files or selected_groups

        if has_any_selection:
            # Open actions
            open_action = menu.addAction("📂 Відкрити")
            open_action.triggered.connect(self.open_selected_duplicates)

            show_action = menu.addAction("👁️ Показати у провіднику")
            show_action.triggered.connect(self.show_selected_duplicates_in_explorer)

            menu.addSeparator()

            # Duplicate-specific actions
            if selected_files:
                # Keep newest (smart selection)
                keep_newest_action = menu.addAction(
                    "🕐 Залишити найновіший, видалити інші"
                )
                keep_newest_action.triggered.connect(self.keep_newest_delete_others)

                # Keep oldest
                keep_oldest_action = menu.addAction(
                    "🕐 Залишити найстаріший, видалити інші"
                )
                keep_oldest_action.triggered.connect(self.keep_oldest_delete_others)

                # Keep in specific location
                keep_location_action = menu.addAction("📁 Залишити у вибраній папці")
                keep_location_action.triggered.connect(
                    self.keep_in_location_delete_others
                )

                menu.addSeparator()

            # Selection-based actions
            if selected_groups:
                select_all_in_group_action = menu.addAction(
                    "✅ Вибрати всі файли у групі"
                )
                select_all_in_group_action.triggered.connect(self.select_all_in_groups)

                menu.addSeparator()

            # Delete actions
            if selected_files:
                delete_selected_action = menu.addAction("🗑️ Видалити вибрані файли")
                delete_selected_action.triggered.connect(
                    self.delete_selected_duplicate_files
                )

            if selected_groups:
                delete_group_action = menu.addAction("🗑️ Видалити всю групу дублікатів")
                delete_group_action.triggered.connect(
                    self.delete_selected_duplicate_groups
                )

            menu.addSeparator()

            # Copy operations
            copy_path_action = menu.addAction("📋 Копіювати шлях")
            copy_path_action.triggered.connect(self.copy_selected_duplicate_paths)

            copy_hash_action = menu.addAction("🔑 Копіювати хеш")
            copy_hash_action.triggered.connect(self.copy_selected_duplicate_hashes)

            menu.addSeparator()

        # Tree operations
        if self.duplicate_tree.topLevelItemCount() > 0:
            expand_all_action = menu.addAction("📂 Розгорнути все")
            expand_all_action.triggered.connect(self.expand_all_duplicate_items)

            collapse_all_action = menu.addAction("📁 Згорнути все")
            collapse_all_action.triggered.connect(self.collapse_all_duplicate_items)

            menu.addSeparator()

            # Refresh action
            refresh_action = menu.addAction("🔄 Оновити список дублікатів")
            refresh_action.triggered.connect(self.refresh_duplicates)

        menu.exec_(self.duplicate_tree.viewport().mapToGlobal(position))

    def get_selected_duplicate_files(self):
        """Get list of selected file paths from duplicate tree"""
        selected_files = []
        for item in self.duplicate_tree.selectedItems():
            # Child items are files (column 0 is empty for files)
            if item.text(0) == "" and item.text(1):
                selected_files.append(item.text(1))
        return selected_files

    def get_selected_duplicate_groups(self):
        """Get list of selected duplicate groups"""
        selected_groups = []
        for item in self.duplicate_tree.selectedItems():
            # Parent items have hash in column 0
            if item.text(0) and not item.text(0).startswith(""):
                selected_groups.append(item)
        return selected_groups

    def open_selected_duplicates(self):
        """Open selected duplicate files"""
        selected_files = self.get_selected_duplicate_files()
        for file_path in selected_files:
            if os.path.exists(file_path):
                if sys.platform == "win32":
                    os.startfile(file_path)
                elif sys.platform == "darwin":
                    subprocess.run(["open", file_path])
                else:
                    subprocess.run(["xdg-open", file_path])

    def show_selected_duplicates_in_explorer(self):
        """Show selected duplicate files in file explorer"""
        selected_files = self.get_selected_duplicate_files()
        for file_path in selected_files:
            if os.path.exists(file_path):
                # Ensure the path is absolute and normalized
                abs_path = os.path.abspath(file_path)
                if sys.platform == "win32":
                    # Use a list of arguments for security and to handle paths correctly
                    subprocess.run(["explorer", "/select,", abs_path])
                elif sys.platform == "darwin":
                    subprocess.run(["open", "-R", abs_path])
                else:
                    subprocess.run(["xdg-open", os.path.dirname(abs_path)])

    def keep_newest_delete_others(self):
        """Keep the newest file in each selected group and delete others"""
        selected_groups = self.get_selected_duplicate_groups()
        if not selected_groups:
            QMessageBox.warning(
                self, "Попередження", "Будь ласка, виберіть групи дублікатів."
            )
            return

        reply = QMessageBox.question(
            self,
            "Підтвердження",
            f"Ви впевнені, що хочете залишити найновіші файли та видалити інші?\n\n"
            f"Це видалить {sum(group.childCount() - 1 for group in selected_groups)} файлів.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        files_to_delete = []
        for group in selected_groups:
            group_files = []
            for i in range(group.childCount()):
                child = group.child(i)
                file_path = child.text(1)
                if os.path.exists(file_path):
                    mtime = os.path.getmtime(file_path)
                    group_files.append((file_path, mtime))

            # Sort by modification time (newest first) and keep only the newest
            group_files.sort(key=lambda x: x[1], reverse=True)
            if group_files:
                # Keep the newest, add others to delete list
                files_to_delete.extend([f[0] for f in group_files[1:]])

        self._delete_duplicate_files_list(files_to_delete)

    def keep_oldest_delete_others(self):
        """Keep the oldest file in each selected group and delete others"""
        selected_groups = self.get_selected_duplicate_groups()
        if not selected_groups:
            QMessageBox.warning(
                self, "Попередження", "Будь ласка, виберіть групи дублікатів."
            )
            return

        reply = QMessageBox.question(
            self,
            "Підтвердження",
            f"Ви впевнені, що хочете залишити найстаріші файли та видалити інші?\n\n"
            f"Це видалить {sum(group.childCount() - 1 for group in selected_groups)} файлів.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        files_to_delete = []
        for group in selected_groups:
            group_files = []
            for i in range(group.childCount()):
                child = group.child(i)
                file_path = child.text(1)
                if os.path.exists(file_path):
                    mtime = os.path.getmtime(file_path)
                    group_files.append((file_path, mtime))

            # Sort by modification time (oldest first) and keep only the oldest
            group_files.sort(key=lambda x: x[1])
            if group_files:
                # Keep the oldest, add others to delete list
                files_to_delete.extend([f[0] for f in group_files[1:]])

        self._delete_duplicate_files_list(files_to_delete)

    def keep_in_location_delete_others(self):
        """Keep files in preferred location and delete others"""
        selected_groups = self.get_selected_duplicate_groups()
        if not selected_groups:
            QMessageBox.warning(
                self, "Попередження", "Будь ласка, виберіть групи дублікатів."
            )
            return

        # Let user choose preferred location
        location = QFileDialog.getExistingDirectory(
            self, "Оберіть папку для збереження файлів"
        )
        if not location:
            return

        files_to_delete = []
        for group in selected_groups:
            files_to_keep = []
            for i in range(group.childCount()):
                child = group.child(i)
                file_path = child.text(1)
                if os.path.exists(file_path) and file_path.startswith(location):
                    files_to_keep.append(file_path)

            # If no files in preferred location, ask user to choose
            if not files_to_keep:
                # Show dialog to select files to keep
                group_files = []
                for i in range(group.childCount()):
                    child = group.child(i)
                    file_path = child.text(1)
                    group_files.append(file_path)

                # For now, keep the first file
                if group_files:
                    files_to_keep = [group_files[0]]

            # Add all other files to delete list
            for i in range(group.childCount()):
                child = group.child(i)
                file_path = child.text(1)
                if file_path not in files_to_keep:
                    files_to_delete.append(file_path)

        if files_to_delete:
            reply = QMessageBox.question(
                self,
                "Підтвердження",
                f"Видалити {len(files_to_delete)} файлів, що не знаходяться у вибраній папці?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                self._delete_duplicate_files_list(files_to_delete)

    def select_all_in_groups(self):
        """Select all files in selected duplicate groups"""
        selected_groups = self.get_selected_duplicate_groups()
        for group in selected_groups:
            for i in range(group.childCount()):
                child = group.child(i)
                child.setSelected(True)

    def delete_selected_duplicate_files(self):
        """Delete selected duplicate files"""
        selected_files = self.get_selected_duplicate_files()
        if not selected_files:
            QMessageBox.warning(
                self, "Попередження", "Будь ласка, виберіть файли для видалення."
            )
            return

        reply = QMessageBox.question(
            self,
            "Підтвердження видалення",
            f"Ви впевнені, що хочете видалити {len(selected_files)} файлів?\n\n"
            "Ця дія не може бути скасована!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self._delete_duplicate_files_list(selected_files)

    def delete_selected_duplicate_groups(self):
        """Delete entire selected duplicate groups"""
        selected_groups = self.get_selected_duplicate_groups()
        if not selected_groups:
            QMessageBox.warning(
                self, "Попередження", "Будь ласка, виберіть групи для видалення."
            )
            return

        total_files = sum(group.childCount() for group in selected_groups)
        reply = QMessageBox.question(
            self,
            "Підтвердження видалення",
            f"Ви впевнені, що хочете видалити всі {total_files} файлів у вибраних групах?\n\n"
            "Ця дія не може бути скасована!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            files_to_delete = []
            for group in selected_groups:
                for i in range(group.childCount()):
                    child = group.child(i)
                    file_path = child.text(1)
                    files_to_delete.append(file_path)

            self._delete_duplicate_files_list(files_to_delete)

    def copy_selected_duplicate_paths(self):
        """Copy paths of selected duplicate files"""
        selected_files = self.get_selected_duplicate_files()
        if selected_files:
            from PyQt5.QtWidgets import QApplication

            clipboard = QApplication.clipboard()
            clipboard.setText("\n".join(selected_files))

    def copy_selected_duplicate_hashes(self):
        """Copy hashes of selected duplicate groups"""
        selected_groups = self.get_selected_duplicate_groups()
        if selected_groups:
            hashes = [group.text(0) for group in selected_groups]
            from PyQt5.QtWidgets import QApplication

            clipboard = QApplication.clipboard()
            clipboard.setText("\n".join(hashes))

    def expand_all_duplicate_items(self):
        """Expand all duplicate tree items"""
        for i in range(self.duplicate_tree.topLevelItemCount()):
            item = self.duplicate_tree.topLevelItem(i)
            item.setExpanded(True)

    def collapse_all_duplicate_items(self):
        """Collapse all duplicate tree items"""
        for i in range(self.duplicate_tree.topLevelItemCount()):
            item = self.duplicate_tree.topLevelItem(i)
            item.setExpanded(False)

    def refresh_duplicates(self):
        """Refresh duplicate search"""
        current_path = self.duplicate_path_edit.text().strip()
        if current_path and os.path.exists(current_path):
            self.find_duplicates()

    def _delete_duplicate_files_list(self, files_to_delete):
        """Helper method to delete a list of files"""
        deleted_count = 0
        failed_count = 0
        failed_files = []

        for file_path in files_to_delete:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    deleted_count += 1
                    # Log to main application
                    if hasattr(self.main_window, "log_message"):
                        self.main_window.log_message(
                            f"CleanupHelper: Deleted duplicate {file_path}"
                        )
            except Exception as e:
                failed_count += 1
                failed_files.append(f"{file_path}: {str(e)}")

        # Show results
        if failed_count == 0:
            QMessageBox.information(
                self, "Видалення завершено", f"Успішно видалено {deleted_count} файлів."
            )
            # Refresh the duplicate tree
            self.refresh_duplicates()
        else:
            error_details = "\n".join(failed_files[:5])  # Show first 5 errors
            if len(failed_files) > 5:
                error_details += f"\n... та ще {len(failed_files) - 5} помилок"

            QMessageBox.warning(
                self,
                "Часткове видалення",
                f"Видалено {deleted_count} файлів.\n"
                f"Не вдалося видалити {failed_count} файлів:\n{error_details}",
            )

    def handle_action_selection(self, selected_option: str):
        """Handle action selection from dropdown"""
        # Skip separator items
        if selected_option.startswith("───"):
            self.actions_combo.blockSignals(True)
            self.actions_combo.setCurrentIndex(0)
            self.actions_combo.blockSignals(False)
            return

        if selected_option == "📂 Вибрати шлях для сканування":
            self.choose_archive_scan_path()
        elif selected_option == "🗑️ Очистити кеш результатів":
            self.clear_archive_cache()
        elif selected_option == "🔤 Сортувати за назвою (А-Я)":
            self.sort_archive_tree("name", ascending=True)
        elif selected_option == "🔤 Сортувати за назвою (Я-А)":
            self.sort_archive_tree("name", ascending=False)
        elif selected_option == "📏 Сортувати за розміром (зростання)":
            self.sort_archive_tree("size", ascending=True)
        elif selected_option == "📏 Сортувати за розміром (спадання)":
            self.sort_archive_tree("size", ascending=False)
        elif selected_option == "📅 Сортувати за датою (новіші)":
            self.sort_archive_tree("date", ascending=False)
        elif selected_option == "📅 Сортувати за датою (старіші)":
            self.sort_archive_tree("date", ascending=True)

        # Reset dropdown to first item after action (except for the first item itself)
        if selected_option != "📋 Дії":
            self.actions_combo.blockSignals(True)
            self.actions_combo.setCurrentIndex(0)
            self.actions_combo.blockSignals(False)

    def open_presets_window(self):
        """Open the presets window directly"""
        presets_window = FilterPresetsWindow(self.archive_tree)
        presets_window.show()

    def choose_archive_scan_path(self):
        """Choose a different scan path for archive viewer"""
        scan_path = QFileDialog.getExistingDirectory(
            self,
            "Вибрати каталог для сканування",
            self.working_path if self.working_path else "",
        )

        if scan_path:
            self.archive_scan_path = scan_path
            self.is_showing_analytics_results = False
            self.refresh_archive_tree()

    def clear_archive_cache(self):
        """Clear cached analytics results"""
        if hasattr(self, "analytics_scan_results"):
            self.analytics_scan_results = None

        self.is_showing_analytics_results = False
        self.archive_tree.clear()

        if hasattr(self.main_window, "log_message"):
            self.main_window.log_message("CleanupHelper: Archive cache cleared")

    def sort_archive_tree(self, sort_by: str, ascending: bool = True):
        """Sort archive tree items by specified criteria"""
        try:
            self.archive_status_label.setText(f"Сортування за {sort_by}...")

            # Get the root item
            root = self.archive_tree.invisibleRootItem()

            # Collect all top-level items
            top_items = []
            for i in range(root.childCount()):
                top_items.append(root.child(i))

            if not top_items:
                return

            # Sort items based on criteria
            if sort_by == "name":
                # Sort by name (column 0)
                top_items.sort(
                    key=lambda item: item.text(0).lower(), reverse=not ascending
                )
            elif sort_by == "size":
                # Sort by size (column 1) - need to parse human-readable sizes
                def size_to_bytes(size_str: str) -> int:
                    """Convert human-readable size string to bytes"""
                    if not size_str or size_str == "":
                        return 0

                    # Remove common formatting and extract number
                    import re

                    match = re.search(r"([\d.]+)", size_str)
                    if not match:
                        return 0

                    number = float(match.group(1))

                    # Determine multiplier based on unit
                    if "КБ" in size_str.upper() or "KB" in size_str.upper():
                        return int(number * 1024)
                    elif "МБ" in size_str.upper() or "MB" in size_str.upper():
                        return int(number * 1024 * 1024)
                    elif "ГБ" in size_str.upper() or "GB" in size_str.upper():
                        return int(number * 1024 * 1024 * 1024)
                    elif "ТБ" in size_str.upper() or "TB" in size_str.upper():
                        return int(number * 1024 * 1024 * 1024 * 1024)
                    else:
                        return int(number)  # Assume bytes

                top_items.sort(
                    key=lambda item: size_to_bytes(item.text(1)), reverse=not ascending
                )
            elif sort_by == "date":
                # Sort by date (column 2)
                def date_to_timestamp(date_str: str) -> float:
                    """Convert date string to timestamp for sorting"""
                    if not date_str or date_str == "":
                        return 0

                    try:
                        # Try different date formats
                        for fmt in [
                            "%Y-%m-%d %H:%M",
                            "%Y-%m-%d",
                            "%d-%m-%Y %H:%M",
                            "%d-%m-%Y",
                        ]:
                            try:
                                from datetime import datetime

                                return datetime.strptime(date_str, fmt).timestamp()
                            except ValueError:
                                continue
                        return 0
                    except Exception:
                        return 0

                top_items.sort(
                    key=lambda item: date_to_timestamp(item.text(2)),
                    reverse=not ascending,
                )

            # Remove all items from tree
            self.archive_tree.clear()

            # Re-add sorted items
            for i, item in enumerate(top_items):
                self.archive_tree.addTopLevelItem(item)
                int((i + 1) / len(top_items) * 100)

            # Sort children recursively if they exist
            for item in top_items:
                self._sort_children_recursive(item, sort_by, ascending)

                self.archive_status_label.setText(
                    f"Відсортовано за {sort_by} ({'за зростанням' if ascending else 'за спаданням'})"
                )

            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Sorted {len(top_items)} items by {sort_by}"
                )

        except Exception as e:
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(f"CleanupHelper: Error sorting tree: {e}")

    def _sort_children_recursive(
        self, parent_item: QTreeWidgetItem, sort_by: str, ascending: bool
    ):
        """Recursively sort children of a tree item"""
        try:
            # Collect children
            children = []
            for i in range(parent_item.childCount()):
                children.append(parent_item.child(i))

            if len(children) <= 1:
                return

            # Sort children based on same criteria
            if sort_by == "name":
                children.sort(
                    key=lambda item: item.text(0).lower(), reverse=not ascending
                )
            elif sort_by == "size":

                def size_to_bytes(size_str: str) -> int:
                    if not size_str or size_str == "":
                        return 0
                    import re

                    match = re.search(r"([\d.]+)", size_str)
                    if not match:
                        return 0
                    number = float(match.group(1))
                    if "КБ" in size_str.upper() or "KB" in size_str.upper():
                        return int(number * 1024)
                    elif "МБ" in size_str.upper() or "MB" in size_str.upper():
                        return int(number * 1024 * 1024)
                    elif "ГБ" in size_str.upper() or "GB" in size_str.upper():
                        return int(number * 1024 * 1024 * 1024)
                    else:
                        return int(number)

                children.sort(
                    key=lambda item: size_to_bytes(item.text(1)), reverse=not ascending
                )
            elif sort_by == "date":

                def date_to_timestamp(date_str: str) -> float:
                    if not date_str or date_str == "":
                        return 0
                    try:
                        for fmt in [
                            "%Y-%m-%d %H:%M",
                            "%Y-%m-%d",
                            "%d-%m-%Y %H:%M",
                            "%d-%m-%Y",
                        ]:
                            try:
                                from datetime import datetime

                                return datetime.strptime(date_str, fmt).timestamp()
                            except ValueError:
                                continue
                        return 0
                    except Exception:
                        return 0

                children.sort(
                    key=lambda item: date_to_timestamp(item.text(2)),
                    reverse=not ascending,
                )

            # Remove and re-add children in sorted order
            parent_item.takeChildren()
            for child in children:
                parent_item.addChild(child)
                # Recursively sort this child's children
                self._sort_children_recursive(child, sort_by, ascending)

        except Exception as e:
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Error sorting children: {e}"
                )

    def reset_all_filters(self):
        """Reset all filters and show all items"""
        try:
            self.archive_status_label.setText("🔄 Скидання фільтрів...")

            # Clear search filters
            self.current_search_term = ""
            self.search_edit.clear()

            # Clear advanced filters
            if hasattr(self, "archive_filters"):
                self.archive_filters = {
                    "file_types": [],
                    "min_date": None,
                    "max_date": None,
                    "min_size": None,
                    "max_size": None,
                }

            # Clear filter history to prevent re-application
            if hasattr(self, "_filter_history"):
                self._filter_history = []

            # Reset any active date/size filters
            if hasattr(self, "date_filter_active"):
                self.date_filter_active = False
            if hasattr(self, "size_filter_active"):
                self.size_filter_active = False

            # Rebuild the tree to show all items without new scan
            self._rebuild_tree_without_scan()

            self.archive_status_label.setText(
                "✅ Усі фільтри скинуто - показано всі файли"
            )
            self.archive_status_label.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                    color: #27ae60;
                    padding: 8px;
                    background-color: #d5f4e6;
                    border-radius: 5px;
                    border: 1px solid #27ae60;
                    font-weight: 600;
                }
            """)

            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    "CleanupHelper: All filters reset - showing all files"
                )

            QTimer.singleShot(2000, lambda: self._reset_status_style())

        except Exception as e:
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Error resetting filters: {e}"
                )

    def _rebuild_tree_without_scan(self):
        """Show all items in current tree without starting a new scan"""
        try:
            # Simply unhide all items in the current tree instead of rebuilding
            root = self.archive_tree.invisibleRootItem()
            shown_count = 0

            def unhide_all_items(item):
                nonlocal shown_count
                # Unhide this item if it was hidden
                if item.isHidden():
                    item.setHidden(False)
                    shown_count += 1

                # Recursively unhide all children
                for i in range(item.childCount()):
                    unhide_all_items(item.child(i))

            # Unhide all items in the tree
            for i in range(root.childCount()):
                unhide_all_items(root.child(i))

            # Update the tree to show the changes
            self.archive_tree.viewport().update()

        except Exception as e:
            print(f"Error unhiding tree items: {e}")
            # Fallback to full refresh
            self.refresh_archive_tree("")

    def _reset_status_style(self):
        """Reset status label to default style"""
        self.archive_status_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #2c3e50;
                padding: 8px;
                background-color: #ecf0f1;
                border-radius: 5px;
                border: 1px solid #bdc3c7;
                font-weight: 500;
            }
        """)
        self.archive_status_label.setText("Готовий до пошуку та фільтрації")

    def get_cached_scan_results(self, scan_path: str) -> dict:
        """Get cached scan results for faster secondary searches"""
        cache_key = scan_path.lower()

        if hasattr(self, "scan_cache") and cache_key in self.scan_cache:
            cached_data = self.scan_cache[cache_key]
            # Check if cache is still valid (within last 5 minutes)
            cache_time = cached_data.get("timestamp", 0)
            current_time = datetime.now().timestamp()
            if current_time - cache_time < 300:  # 5 minutes
                return cached_data.get("results", {})

        return None

    def cache_scan_results(self, scan_path: str, results: dict):
        """Cache scan results for faster future access"""
        if not hasattr(self, "scan_cache"):
            self.scan_cache = {}

        cache_key = scan_path.lower()
        self.scan_cache[cache_key] = {
            "results": results,
            "timestamp": datetime.now().timestamp(),
        }

    def get_file_icon(self, file_path: str, extension: str = "") -> str:
        """Get appropriate icon for file based on extension"""
        if not extension:
            extension = os.path.splitext(file_path)[1].lower()
        else:
            extension = extension.lower()

        # Directory icons
        if os.path.isdir(file_path):
            return "📁"

        # File type icons mapping
        icon_map = {
            # Documents
            ".pdf": "📄",
            ".doc": "📝",
            ".docx": "📝",
            ".txt": "📄",
            ".rtf": "📄",
            ".odt": "📝",
            ".xls": "📊",
            ".xlsx": "📊",
            ".ppt": "📊",
            ".pptx": "📊",
            ".csv": "📋",
            # Images
            ".jpg": "🖼️",
            ".jpeg": "🖼️",
            ".png": "🖼️",
            ".gif": "🖼️",
            ".bmp": "🖼️",
            ".tiff": "🖼️",
            ".svg": "🎨",
            ".webp": "🖼️",
            ".ico": "🖼️",
            # Videos
            ".mp4": "🎬",
            ".avi": "🎬",
            ".mkv": "🎬",
            ".mov": "🎬",
            ".wmv": "🎬",
            ".flv": "🎬",
            ".webm": "🎬",
            ".m4v": "🎬",
            ".3gp": "🎬",
            # Audio
            ".mp3": "🎵",
            ".wav": "🎵",
            ".flac": "🎵",
            ".aac": "🎵",
            ".ogg": "🎵",
            ".wma": "🎵",
            ".m4a": "🎵",
            ".opus": "🎵",
            # Archives
            ".zip": "🗜️",
            ".rar": "🗜️",
            ".7z": "🗜️",
            ".tar": "🗜️",
            ".gz": "🗜️",
            ".bz2": "🗜️",
            ".xz": "🗜️",
            ".tar.gz": "🗜️",
            ".tar.bz2": "🗜️",
            ".tar.xz": "🗜️",
            # Programs
            ".exe": "⚙️",
            ".msi": "⚙️",
            ".deb": "⚙️",
            ".rpm": "⚙️",
            ".dmg": "⚙️",
            ".pkg": "⚙️",
            ".app": "⚙️",
            # Code files
            ".py": "🐍",
            ".js": "📜",
            ".html": "🌐",
            ".css": "🎨",
            ".php": "🐘",
            ".java": "☕",
            ".cpp": "⚙️",
            ".c": "⚙️",
            ".cs": "🔷",
            ".rb": "💎",
            ".go": "🐹",
            ".rs": "🦀",
            ".swift": "🦉",
            # Config files
            ".json": "📋",
            ".xml": "📋",
            ".yaml": "📋",
            ".yml": "📋",
            ".ini": "⚙️",
            ".cfg": "⚙️",
            ".conf": "⚙️",
            ".log": "📝",
            # Other common files
            ".md": "📝",
            ".rst": "📝",
            ".pdf": "📄",
            ".epub": "📚",
            ".mobi": "📚",
            ".azw": "📚",
            ".azw3": "📚",
        }

        return icon_map.get(extension, "📄")

    def get_selected_files(self) -> List[str]:
        """Get paths of selected files only (exclude directories)"""
        selected_files = []
        for item in self.archive_tree.selectedItems():
            # Path is in column 4 (index 3)
            file_path = item.text(4)
            if file_path and os.path.isfile(file_path):
                selected_files.append(file_path)
        return selected_files

    def get_selected_directories(self) -> List[str]:
        """Get paths of selected directories only"""
        selected_directories = []
        for item in self.archive_tree.selectedItems():
            # Path is in column 4 (index 3)
            dir_path = item.text(4)
            if dir_path and os.path.isdir(dir_path):
                selected_directories.append(dir_path)
        return selected_directories

    def get_selected_items(self) -> List[str]:
        """Get paths of selected items (both files and directories)"""
        selected_paths = []
        for item in self.archive_tree.selectedItems():
            # Path is in column 4 (index 3)
            item_path = item.text(4)
            if item_path and os.path.exists(item_path):
                selected_paths.append(item_path)
        return selected_paths

    def show_compression_window(self):
        """Show compression window with selected files and directories"""
        selected_files = self.get_selected_files()
        selected_directories = self.get_selected_directories()
        selected_items = selected_files + selected_directories

        if not selected_items:
            QMessageBox.warning(
                self, "Увага", "Будь ласка, оберіть файли або папки для стиснення."
            )
            return

        self.compression_window = CompressionWindow(selected_items, self)
        self.compression_window.show()

    def delete_selected_files(self):
        """Delete selected files with confirmation"""
        selected_files = self.get_selected_files()
        if not selected_files:
            return

        reply = QMessageBox.question(
            self,
            "Підтвердження видалення",
            f"Ви впевнені, що хочете видалити {len(selected_files)} файл(ів)?\n\n"
            "Цю дію неможливо скасувати.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.archive_status_label.setText("Видалення файлів...")

            deleted_count = 0
            for i, file_path in enumerate(selected_files):
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        deleted_count += 1
                except Exception as e:
                    if hasattr(self.main_window, "log_message"):
                        self.main_window.log_message(
                            f"CleanupHelper: Помилка видалення {file_path}: {e}"
                        )

            self.archive_status_label.setText(
                f"Видалено {deleted_count} з {len(selected_files)} файлів"
            )

            # Refresh tree after deletion
            self.refresh_archive_tree()

            QMessageBox.information(
                self, "Готово", f"Видалено {deleted_count} файл(ів)."
            )

    def delete_selected_items(self):
        """Delete selected files and directories with confirmation"""
        selected_files = self.get_selected_files()
        selected_directories = self.get_selected_directories()
        selected_items = selected_files + selected_directories

        if not selected_items:
            return

        # Count items and calculate total size
        total_files = len(selected_files)
        total_dirs = len(selected_directories)
        total_items = len(selected_items)

        # Calculate total size
        total_size = 0
        for item_path in selected_items:
            if os.path.exists(item_path):
                if os.path.isfile(item_path):
                    total_size += os.path.getsize(item_path)
                elif os.path.isdir(item_path):
                    # Calculate directory size recursively
                    for root, dirs, files in os.walk(item_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            if os.path.exists(file_path):
                                total_size += os.path.getsize(file_path)

        # Create confirmation message
        message_parts = []
        if total_files > 0:
            message_parts.append(f"{total_files} файл(и)")
        if total_dirs > 0:
            message_parts.append(f"{total_dirs} папок")

        message = f"Ви впевнені, що хочете видалити {', '.join(message_parts)}?\n"
        message += f"Загальний розмір: {humanize.naturalsize(total_size)}\n\n"
        message += "Цю дію неможливо скасувати."

        # Confirmation dialog
        reply = QMessageBox.question(
            self,
            "Підтвердження видалення",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.archive_status_label.setText("Видалення елементів...")

            deleted_count = 0
            current_progress = 0

            # Delete files first
            for file_path in selected_files:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        deleted_count += 1
                    current_progress += 1
                except Exception as e:
                    if hasattr(self.main_window, "log_message"):
                        self.main_window.log_message(
                            f"CleanupHelper: Помилка видалення файлу {file_path}: {e}"
                        )

            # Delete directories
            for dir_path in selected_directories:
                try:
                    if os.path.exists(dir_path):
                        import shutil

                        shutil.rmtree(dir_path)
                        deleted_count += 1
                    current_progress += 1
                except Exception as e:
                    if hasattr(self.main_window, "log_message"):
                        self.main_window.log_message(
                            f"CleanupHelper: Помилка видалення папки {dir_path}: {e}"
                        )

            # Success message
            success_parts = []
            if len(selected_files) > 0:
                success_parts.append(f"{len(selected_files)} файл(и)")
            if len(selected_directories) > 0:
                success_parts.append(f"{len(selected_directories)} папок")

            self.archive_status_label.setText(f"Видалено {', '.join(success_parts)}")

            # Immediately remove deleted items from UI tree for instant feedback
            self._remove_items_from_tree(selected_items)

            # Invalidate cache to ensure next scan is fresh
            self._file_cache = {}
            self._cache_timestamp = 0
            self._last_scan_path = ""

            # Update analytics if on analytics tab
            if hasattr(self, "current_analytics_data") and self.current_analytics_data:
                self._update_analytics_after_deletion(selected_items)

            # Show success message immediately
            QMessageBox.information(
                self, "Готово", f"Видалено {', '.join(success_parts)}."
            )

    def _remove_items_from_tree(self, deleted_items):
        """Immediately remove deleted items from the archive tree UI"""
        try:
            if not deleted_items or not hasattr(self, "archive_tree"):
                return

            root = self.archive_tree.invisibleRootItem()
            items_to_remove = []
            deleted_set = set(deleted_items)  # Convert to set for faster lookup

            # Block signals during tree manipulation to prevent UI flicker
            self.archive_tree.setUpdatesEnabled(False)
            self.archive_tree.blockSignals(True)

            # Find all tree items that correspond to deleted files
            def find_items_to_remove(parent_item):
                for i in range(parent_item.childCount()):
                    child = parent_item.child(i)
                    file_path = child.text(4)  # File path is stored in column 4

                    if file_path and file_path in deleted_set:
                        items_to_remove.append(child)

                    # Recursively check children
                    if child.childCount() > 0:
                        find_items_to_remove(child)

            find_items_to_remove(root)

            # Remove found items from tree (process in reverse order to avoid index issues)
            for item in items_to_remove:
                try:
                    parent = item.parent()
                    if parent:
                        parent.removeChild(item)
                    else:
                        root.removeChild(item)
                except Exception as e:
                    print(f"Error removing individual tree item: {e}")

            # Clean up empty directories
            self._clean_empty_directories(root)

        except Exception as e:
            print(f"Error removing items from tree: {e}")
        finally:
            # Re-enable signals and updates
            if hasattr(self, "archive_tree"):
                self.archive_tree.blockSignals(False)
                self.archive_tree.setUpdatesEnabled(True)
                self.archive_tree.viewport().update()  # Force redraw

    def _clean_empty_directories(self, parent_item):
        """Remove empty directory items from tree"""
        try:
            if not hasattr(self, "archive_tree"):
                return

            # Keep cleaning until no more empty directories are found
            max_passes = 10  # Prevent infinite loops
            for pass_num in range(max_passes):
                empty_dirs = []
                items_to_check = []

                # Collect all items to check
                for i in range(parent_item.childCount()):
                    child = parent_item.child(i)
                    items_to_check.append(child)

                # Find empty directories
                for item in items_to_check:
                    # Directory if column 4 is empty AND it has no children
                    if (
                        not item.text(4) or item.text(4).strip() == ""
                    ) and item.childCount() == 0:
                        empty_dirs.append(item)

                # If no empty directories found, we're done
                if not empty_dirs:
                    break

                # Remove empty directories
                for item in empty_dirs:
                    try:
                        parent = item.parent()
                        if parent:
                            parent.removeChild(item)
                        else:
                            parent_item.removeChild(item)
                    except Exception as e:
                        print(f"Error removing empty directory: {e}")

        except Exception as e:
            print(f"Error cleaning empty directories: {e}")

    def _update_analytics_after_deletion(self, deleted_items):
        """Update analytics data immediately after file deletion"""
        try:
            if not self.current_analytics_data:
                return

            # Update file counts and sizes
            for item_path in deleted_items:
                if os.path.exists(item_path):
                    continue  # File wasn't actually deleted

                # Update total file count
                if os.path.isfile(item_path):
                    self.current_analytics_data["total_files"] -= 1

                # Update large files list
                self.current_analytics_data["large_files"] = [
                    f
                    for f in self.current_analytics_data["large_files"]
                    if f["path"] != item_path
                ]

                # Update file types
                ext = os.path.splitext(item_path)[1].lower()
                if ext in self.current_analytics_data["file_types"]:
                    file_type_data = self.current_analytics_data["file_types"][ext]
                    file_type_data["count"] -= 1

                    if file_type_data["count"] <= 0:
                        del self.current_analytics_data["file_types"][ext]
                    else:
                        # Estimate size removal (we don't have exact size anymore)
                        file_type_data["size"] = max(
                            0, file_type_data["size"] - 1024
                        )  # Remove estimated 1KB

            # Update large files count
            self.current_analytics_data["large_files_count"] = len(
                self.current_analytics_data["large_files"]
            )

            # Update analytics display
            self.update_analytics_display(self.current_analytics_data)

        except Exception as e:
            print(f"Error updating analytics after deletion: {e}")

    def open_selected_items(self):
        """Open selected items with default application"""
        selected_items = self.get_selected_items()
        for item_path in selected_items:
            try:
                if sys.platform == "win32":
                    os.startfile(item_path)
                elif sys.platform == "darwin":
                    subprocess.run(["open", item_path])
                else:
                    subprocess.run(["xdg-open", item_path])
            except Exception as e:
                if hasattr(self.main_window, "log_message"):
                    self.main_window.log_message(
                        f"CleanupHelper: Помилка відкриття {item_path}: {e}"
                    )

    def show_in_explorer(self):
        """Show selected items in file explorer"""
        selected_items = self.get_selected_items()
        if not selected_items:
            return

        for item_path in selected_items:
            try:
                # Ensure the path is absolute and normalized
                abs_path = os.path.abspath(item_path)
                if sys.platform == "win32":
                    # Use a list of arguments for security and to handle paths correctly
                    subprocess.run(["explorer", "/select,", abs_path])
                elif sys.platform == "darwin":
                    subprocess.run(["open", "-R", abs_path])
                else:
                    subprocess.run(["xdg-open", os.path.dirname(abs_path)])
            except Exception as e:
                if hasattr(self.main_window, "log_message"):
                    self.main_window.log_message(
                        f"CleanupHelper: Помилка показу {item_path}: {e}"
                    )

    def copy_selected_paths(self):
        """Copy selected paths to clipboard"""
        selected_items = self.get_selected_items()
        if selected_items:
            from PyQt5.QtWidgets import QApplication

            clipboard = QApplication.clipboard()
            paths_text = "\n".join(selected_items)
            clipboard.setText(paths_text)
            self.archive_status_label.setText(
                f"Скопійовано {len(selected_items)} шлях(ів) до буфера обміну"
            )

    def restore_selected_files(self):
        """Restore selected files to desktop"""
        selected_files = self.get_selected_files()
        if not selected_files:
            return

        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        restored_count = 0

        self.archive_status_label.setText("Відновлення файлів на робочий стіл...")

        for i, source_path in enumerate(selected_files):
            try:
                target_path = os.path.join(desktop_path, os.path.basename(source_path))

                # Handle name conflicts
                counter = 1
                while os.path.exists(target_path):
                    name, ext = os.path.splitext(os.path.basename(source_path))
                    target_path = os.path.join(desktop_path, f"{name}_{counter}{ext}")
                    counter += 1

                # Copy file
                if os.path.isfile(source_path):
                    shutil.copy2(source_path, target_path)
                    restored_count += 1
            except Exception as e:
                if hasattr(self.main_window, "log_message"):
                    self.main_window.log_message(
                        f"CleanupHelper: Помилка відновлення {source_path}: {e}"
                    )
                self.archive_status_label.setText(
                    f"Відновлено {restored_count} з {len(selected_files)} файлів"
                )

        QMessageBox.information(
            self, "Готово", f"Відновлено {restored_count} файл(ів) на робочий стіл."
        )

    def install_compress_package(self):
        """Install the compress package"""
        try:
            # Check if we can access the main window's module manager
            if hasattr(self.main_window, "module_manager"):
                venv_manager = self.main_window.module_manager.get_virtual_env_manager()
                success = venv_manager.install_user_package("compress>=1.0.0")

                if success:
                    QMessageBox.information(
                        self,
                        "Success",
                        "compress package installed successfully!\n\n"
                        "Please restart the Desktop Organizer application to enable advanced compression features.",
                    )

                    # Log to main application
                    if hasattr(self.main_window, "log_message"):
                        self.main_window.log_message(
                            "CleanupHelper: compress package installed"
                        )
                else:
                    QMessageBox.critical(
                        self,
                        "Error",
                        "Failed to install compress package.\n\n"
                        "Please check the main application log for details.",
                    )
            else:
                # Fallback: try to install with subprocess
                import subprocess

                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "compress>=1.0.0"],
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    QMessageBox.information(
                        self,
                        "Success",
                        "compress package installed successfully!\n\n"
                        "Please restart the Desktop Organizer application to enable advanced compression features.",
                    )
                else:
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"Failed to install compress package:\n\n{result.stderr}",
                    )

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to install compress package:\n\n{str(e)}"
            )

    def closeEvent(self, event):
        """Handle widget close event"""
        # Stop any running threads
        if self.scanner_thread and self.scanner_thread.isRunning():
            self.scanner_thread.stop()
            self.scanner_thread.wait()

        if self.duplicate_finder_thread and self.duplicate_finder_thread.isRunning():
            self.duplicate_finder_thread.stop()
            self.duplicate_finder_thread.wait()

        if self.compressor_thread and self.compressor_thread.isRunning():
            self.compressor_thread.stop()
            self.compressor_thread.wait()

        event.accept()

    def apply_quick_filter(self, filter_type: str):
        """Apply a quick filter preset to the archive tree"""
        filter_configs = {
            "oil_gas": {
                "extensions": ".pet,.las,.dlis,.lis,.witsml,.resqml,.sep,.zmap,.grd,.plt,.surfer,.gocad,.rms,.ecl,.data,.dat,.include,.prn,.hdf,.nc,.segy,.sgy,.su,.vdf,.tvd,.azm,.incl",
                "name": "Нафтогазова інженерія",
            },
            "images": {
                "extensions": ".jpg,.jpeg,.png,.gif,.bmp,.tiff,.tif,.svg,.webp,.ico,.psd,.raw,.heic,.heif",
                "name": "Зображення",
            },
            "documents": {
                "extensions": ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.rtf,.odt,.ods,.odp,.pages,.numbers,.key,.md",
                "name": "Документи",
            },
            "video": {
                "extensions": ".mp4,.avi,.mov,.wmv,.mkv,.flv,.webm,.m4v,.3gp,.mpg,.mpeg,.vob,.ts,.mts,.m2ts",
                "name": "Відео",
            },
            "archives": {
                "extensions": ".zip,.rar,.7z,.tar,.gz,.bz2,.xz,.7zip,.ace,.arj,.cab,.lzh,.z,.tar.gz,.tgz,.tar.bz2,.tbz2",
                "name": "Архіви",
            },
        }

        if filter_type not in filter_configs:
            return

        config = filter_configs[filter_type]
        self._apply_filter_to_tree(config["extensions"], config["name"])
        self._update_filter_status(config["name"], self._count_visible_items())

    def clear_all_archive_filters(self):
        """Clear all filters and show all cached items"""
        try:
            # Clear current filter status
            self.archive_status_label.setText("Готовий до пошуку та фільтрації")
            self.archive_status_label.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                    color: #2c3e50;
                    padding: 8px;
                    background-color: #ecf0f1;
                    border-radius: 5px;
                    border: 1px solid #bdc3c7;
                    font-weight: 500;
                }
            """)

            # Rebuild tree from cache to show all items
            if self._file_cache:
                self.archive_status_label.setText("Скидання фільтрів...")
                self.archive_tree.clear()
                self._build_tree_from_cache("")

                # Count items from cache instead of tree
                total_count = self._count_cache_items(self._file_cache)
                self.archive_status_label.setText(f"Всі файли: {total_count} елементів")

                # Expand tree to show all items
                self.archive_tree.expandAll()

                # Enable selection and ensure items are selectable
                for i in range(self.archive_tree.topLevelItemCount()):
                    self._make_tree_item_selectable(self.archive_tree.topLevelItem(i))

                if hasattr(self.main_window, "log_message"):
                    self.main_window.log_message(
                        f"CleanupHelper: Фільтри скинуто. Показано {total_count} файлів"
                    )
            else:
                # If no cache, refresh the tree normally
                self.refresh_archive_tree()

        except Exception as e:
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Помилка скидання фільтрів: {e}"
                )

    def _count_cache_items(self, cache_dict: dict) -> int:
        """Count all items in cache dictionary"""
        try:
            count = 0
            for item_name, item_data in cache_dict.items():
                count += 1
                if item_data.get("is_dir") and "children" in item_data:
                    count += self._count_cache_items(item_data["children"])
            return count
        except Exception:
            logger.debug("Failed to count cache items")
            return 0

    def _make_tree_item_selectable(self, item: QTreeWidgetItem):
        """Make tree item and all its children selectable"""
        if not item:
            return

        # Ensure the item is selectable
        item.setFlags(item.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled)

        # Make all children selectable recursively
        for i in range(item.childCount()):
            self._make_tree_item_selectable(item.child(i))

    def open_advanced_filter_presets(self):
        """Open the advanced filter presets window"""
        try:
            self.filter_presets_window = FilterPresetsWindow(self)
            self.filter_presets_window.show()
        except Exception as e:
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Помилка відкриття розширених фільтрів: {e}"
                )

    def toggle_filters(self):
        """Toggle the visibility of filter controls"""
        if self.filters_visible:
            # Hide filters
            self.filter_widget.hide()
            self.filter_toggle_btn.setText("⌃ ⌃ ⌃ Фільтри ⌃ ⌃ ⌃")
            self.filters_visible = False
        else:
            # Show filters
            self.filter_widget.show()
            self.filter_toggle_btn.setText("⌄ ⌄ ⌄ Фільтри ⌄ ⌄ ⌄")
            self.filters_visible = True

    def _update_filter_status(self, filter_name: str, visible_count: int):
        """Update the filter status label"""
        total_count = (
            self._count_cache_items(self._file_cache) if self._file_cache else 0
        )
        self.archive_status_label.setText(
            f"Фільтр: {filter_name} ({visible_count} з {total_count} файлів)"
        )
        self.archive_status_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #e67e22;
                padding: 8px;
                background-color: #fef5e7;
                border-radius: 5px;
                border: 1px solid #e67e22;
                font-weight: 600;
            }
        """)

        if hasattr(self.main_window, "log_message"):
            self.main_window.log_message(
                f"CleanupHelper: Застосовано фільтр '{filter_name}'. Знайдено {visible_count} файлів"
            )

    def _count_visible_items(self) -> int:
        """Count visible items in the archive tree"""
        try:
            root = self.archive_tree.invisibleRootItem()

            def count_visible(item):
                if item.isHidden():
                    return 0
                count = 1
                for i in range(item.childCount()):
                    count += count_visible(item.child(i))
                return count

            total = 0
            for i in range(root.childCount()):
                total += count_visible(root.child(i))
            return total
        except Exception:
            logger.debug("Failed to count visible items")
            return 0

    def _count_all_items(self) -> int:
        """Count all items in the archive tree (visible and hidden)"""
        try:
            root = self.archive_tree.invisibleRootItem()

            def count_all(item):
                count = 1
                for i in range(item.childCount()):
                    count += count_all(item.child(i))
                return count

            total = 0
            for i in range(root.childCount()):
                total += count_all(root.child(i))
            return total
        except Exception:
            logger.debug("Failed to count all items")
            return 0

    def _apply_filter_to_tree(self, extensions: str, preset_name: str):
        """Apply filter using cached data for optimal performance"""
        try:
            extensions = [
                ext.strip().lower() for ext in extensions.split(",") if ext.strip()
            ]
            if not extensions:
                return

            # Check if we have cached data to work with
            if not self._file_cache:
                if hasattr(self.main_window, "log_message"):
                    self.main_window.log_message(
                        "CleanupHelper: Кеш відсутній, оновлення дерева..."
                    )
                self.refresh_archive_tree()
                return

            self.archive_status_label.setText("Застосування фільтру...")

            # Clear current tree and rebuild from cache with filter
            self.archive_tree.clear()

            def _build_filtered_tree_from_cache(
                cache_dict: dict, parent_item: QTreeWidgetItem, extensions: list
            ):
                """Build tree from cache applying extension filter"""
                visible_count = 0
                items_processed = 0

                for item_name, item_data in cache_dict.items():
                    items_processed += 1
                    if item_data["is_dir"]:
                        # Check if this directory should be included
                        should_include_dir = False
                        dir_has_matching_children = False

                        # Check if directory itself has matching children
                        for child_name, child_data in item_data.get(
                            "children", {}
                        ).items():
                            if not child_data["is_dir"]:
                                _, child_ext = os.path.splitext(child_name)
                                if child_ext.lower() in extensions:
                                    dir_has_matching_children = True
                                    should_include_dir = True
                                    break

                        if should_include_dir:
                            # Create directory item
                            folder_info = self.identify_folder_structure(
                                item_data["path"]
                            )
                            dir_item = QTreeWidgetItem(parent_item)
                            dir_item.setText(0, folder_info["name"])
                            dir_item.setText(2, "Папка")
                            dir_item.setText(3, item_data.get("modified", ""))
                            dir_item.setText(4, item_data["path"])
                            dir_item.setIcon(0, QIcon(folder_info["icon"]))

                            # Build children recursively
                            child_visible = _build_filtered_tree_from_cache(
                                item_data.get("children", {}), dir_item, extensions
                            )

                            # Update directory item count
                            if child_visible > 0:
                                dir_item.setText(
                                    1, f"Папка ({child_visible} елементів)"
                                )
                            else:
                                dir_item.setText(1, "Папка")

                            visible_count += 1
                    else:
                        # For files, check extension
                        _, file_ext = os.path.splitext(item_name)
                        if file_ext.lower() in extensions:
                            file_item = QTreeWidgetItem(parent_item)

                            # Build display name with icon
                            icon_name = self.get_file_icon(item_data["path"], file_ext)
                            display_name = f"{icon_name} {item_name}"

                            file_item.setText(0, display_name)

                            if "size" in item_data:
                                file_size = item_data["size"]
                                try:
                                    import humanize

                                    file_item.setText(
                                        1, humanize.naturalsize(file_size)
                                    )
                                except ImportError:
                                    size_mb = file_size / (1024 * 1024)
                                    if size_mb < 1:
                                        file_item.setText(
                                            1, f"{file_size / 1024:.1f} KB"
                                        )
                                    else:
                                        file_item.setText(1, f"{size_mb:.1f} MB")
                            else:
                                file_item.setText(1, "Розмір невідомий")

                            file_item.setText(
                                2, self.get_file_category(item_data["path"])
                            )
                            file_item.setText(3, item_data.get("modified", ""))
                            file_item.setText(4, item_data["path"])
                            visible_count += 1

                return visible_count

            # Build filtered tree
            total_visible = _build_filtered_tree_from_cache(
                self._file_cache, self.archive_tree.invisibleRootItem(), extensions
            )

            # Update progress and status
            self.archive_status_label.setText(
                f"Фільтр застосовано: {total_visible} файлів"
            )

            # Expand tree to show results
            if total_visible > 0:
                self.archive_tree.expandAll()

            # Make all items selectable
            for i in range(self.archive_tree.topLevelItemCount()):
                self._make_tree_item_selectable(self.archive_tree.topLevelItem(i))

            # Update filter status
            self._update_filter_status(preset_name, total_visible)

            # Log success
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Застосовано фільтр '{preset_name}' - {total_visible} файлів знайдено"
                )

        except Exception as e:
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Помилка застосування фільтра: {e}"
                )
            else:
                print(f"CleanupHelper: Error applying filter: {e}")

    def _apply_size_filter(self, min_mb: float, max_mb: float, filter_name: str):
        """Apply size filter using cached data for optimal performance"""
        try:
            # Check if we have cached data to work with
            if not self._file_cache:
                if hasattr(self.main_window, "log_message"):
                    self.main_window.log_message(
                        "CleanupHelper: Кеш відсутній, оновлення дерева..."
                    )
                self.refresh_archive_tree()
                return

            min_bytes = min_mb * 1024 * 1024
            max_bytes = max_mb * 1024 * 1024

            self.archive_status_label.setText("Застосування фільтру розміру...")

            # Clear current tree and rebuild from cache with size filter
            self.archive_tree.clear()

            def _build_filtered_tree_by_size(
                cache_dict: dict,
                parent_item: QTreeWidgetItem,
                min_bytes: int,
                max_bytes: int,
            ):
                """Build tree from cache applying size filter"""
                visible_count = 0
                items_processed = 0

                for item_name, item_data in cache_dict.items():
                    items_processed += 1
                    if item_data["is_dir"]:
                        # Check if directory should be included (has matching children)
                        should_include_dir = False

                        for child_name, child_data in item_data.get(
                            "children", {}
                        ).items():
                            if not child_data["is_dir"] and "size" in child_data:
                                if min_bytes <= child_data["size"] <= max_bytes:
                                    should_include_dir = True
                                    break

                        if should_include_dir:
                            # Create directory item
                            folder_info = self.identify_folder_structure(
                                item_data["path"]
                            )
                            dir_item = QTreeWidgetItem(parent_item)
                            dir_item.setText(0, folder_info["name"])
                            dir_item.setText(2, "Папка")
                            dir_item.setText(3, item_data.get("modified", ""))
                            dir_item.setText(4, item_data["path"])
                            dir_item.setIcon(0, QIcon(folder_info["icon"]))

                            # Build children recursively
                            child_visible = _build_filtered_tree_by_size(
                                item_data.get("children", {}),
                                dir_item,
                                min_bytes,
                                max_bytes,
                            )

                            # Update directory item count
                            if child_visible > 0:
                                dir_item.setText(
                                    1, f"Папка ({child_visible} елементів)"
                                )
                            else:
                                dir_item.setText(1, "Папка")

                            visible_count += 1
                    else:
                        # For files, check size
                        if (
                            "size" in item_data
                            and min_bytes <= item_data["size"] <= max_bytes
                        ):
                            file_item = QTreeWidgetItem(parent_item)

                            # Build display name with icon
                            _, file_ext = os.path.splitext(item_name)
                            icon_name = self.get_file_icon(item_data["path"], file_ext)
                            display_name = f"{icon_name} {item_name}"

                            file_item.setText(0, display_name)

                            file_size = item_data["size"]
                            try:
                                import humanize

                                file_item.setText(1, humanize.naturalsize(file_size))
                            except ImportError:
                                size_mb = file_size / (1024 * 1024)
                                if size_mb < 1:
                                    file_item.setText(1, f"{file_size / 1024:.1f} KB")
                                else:
                                    file_item.setText(1, f"{size_mb:.1f} MB")

                            file_item.setText(
                                2, self.get_file_category(item_data["path"])
                            )
                            file_item.setText(3, item_data.get("modified", ""))
                            file_item.setText(4, item_data["path"])
                            visible_count += 1

                return visible_count

            # Build filtered tree
            total_visible = _build_filtered_tree_by_size(
                self._file_cache,
                self.archive_tree.invisibleRootItem(),
                min_bytes,
                max_bytes,
            )

            # Update progress and status
            self.archive_status_label.setText(
                f"Фільтр розміру застосовано: {total_visible} файлів"
            )

            # Expand tree to show results
            if total_visible > 0:
                self.archive_tree.expandAll()

            # Make all items selectable
            for i in range(self.archive_tree.topLevelItemCount()):
                self._make_tree_item_selectable(self.archive_tree.topLevelItem(i))

            # Update filter status
            self._update_filter_status(filter_name, total_visible)

            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Застосовано фільтр розміру '{filter_name}' - {total_visible} файлів знайдено"
                )

        except Exception as e:
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Помилка застосування фільтра розміру: {e}"
                )

    def _apply_date_filter(self, min_date, max_date, filter_name: str):
        """Apply date filter using cached data for optimal performance"""
        try:
            # Check if we have cached data to work with
            if not self._file_cache:
                if hasattr(self.main_window, "log_message"):
                    self.main_window.log_message(
                        "CleanupHelper: Кеш відсутній, оновлення дерева..."
                    )
                self.refresh_archive_tree()
                return

            min_timestamp = min_date.timestamp()
            max_timestamp = max_date.timestamp()

            self.archive_status_label.setText("Застосування фільтру дати...")

            # Clear current tree and rebuild from cache with date filter
            self.archive_tree.clear()

            def _build_filtered_tree_by_date(
                cache_dict: dict,
                parent_item: QTreeWidgetItem,
                min_timestamp: float,
                max_timestamp: float,
            ):
                """Build tree from cache applying date filter"""
                visible_count = 0
                items_processed = 0

                for item_name, item_data in cache_dict.items():
                    items_processed += 1
                    if item_data["is_dir"]:
                        # Check if directory should be included (has matching children)
                        should_include_dir = False

                        for child_name, child_data in item_data.get(
                            "children", {}
                        ).items():
                            if (
                                not child_data["is_dir"]
                                and "modified_timestamp" in child_data
                            ):
                                if (
                                    min_timestamp
                                    <= child_data["modified_timestamp"]
                                    <= max_timestamp
                                ):
                                    should_include_dir = True
                                    break

                        if should_include_dir:
                            # Create directory item
                            folder_info = self.identify_folder_structure(
                                item_data["path"]
                            )
                            dir_item = QTreeWidgetItem(parent_item)
                            dir_item.setText(0, folder_info["name"])
                            dir_item.setText(2, "Папка")
                            dir_item.setText(3, item_data.get("modified", ""))
                            dir_item.setText(4, item_data["path"])
                            dir_item.setIcon(0, QIcon(folder_info["icon"]))

                            # Build children recursively
                            child_visible = _build_filtered_tree_by_date(
                                item_data.get("children", {}),
                                dir_item,
                                min_timestamp,
                                max_timestamp,
                            )

                            # Update directory item count
                            if child_visible > 0:
                                dir_item.setText(
                                    1, f"Папка ({child_visible} елементів)"
                                )
                            else:
                                dir_item.setText(1, "Папка")

                            visible_count += 1
                    else:
                        # For files, check modification date
                        item_modified = item_data.get("modified_timestamp")
                        if (
                            item_modified
                            and min_timestamp <= item_modified <= max_timestamp
                        ):
                            file_item = QTreeWidgetItem(parent_item)

                            # Build display name with icon
                            _, file_ext = os.path.splitext(item_name)
                            icon_name = self.get_file_icon(item_data["path"], file_ext)
                            display_name = f"{icon_name} {item_name}"

                            file_item.setText(0, display_name)

                            if "size" in item_data:
                                file_size = item_data["size"]
                                try:
                                    import humanize

                                    file_item.setText(
                                        1, humanize.naturalsize(file_size)
                                    )
                                except ImportError:
                                    size_mb = file_size / (1024 * 1024)
                                    if size_mb < 1:
                                        file_item.setText(
                                            1, f"{file_size / 1024:.1f} KB"
                                        )
                                    else:
                                        file_item.setText(1, f"{size_mb:.1f} MB")
                            else:
                                file_item.setText(1, "Розмір невідомий")

                            file_item.setText(
                                2, self.get_file_category(item_data["path"])
                            )
                            file_item.setText(3, item_data.get("modified", ""))
                            file_item.setText(4, item_data["path"])
                            visible_count += 1

                return visible_count

            # Build filtered tree
            total_visible = _build_filtered_tree_by_date(
                self._file_cache,
                self.archive_tree.invisibleRootItem(),
                min_timestamp,
                max_timestamp,
            )

            # Update progress and status
            self.archive_status_label.setText(
                f"Фільтр дати застосовано: {total_visible} файлів"
            )

            # Expand tree to show results
            if total_visible > 0:
                self.archive_tree.expandAll()

            # Make all items selectable
            for i in range(self.archive_tree.topLevelItemCount()):
                self._make_tree_item_selectable(self.archive_tree.topLevelItem(i))

            # Update filter status
            self._update_filter_status(filter_name, total_visible)

            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Застосовано фільтр дати '{filter_name}' - {total_visible} файлів знайдено"
                )

        except Exception as e:
            if hasattr(self.main_window, "log_message"):
                self.main_window.log_message(
                    f"CleanupHelper: Помилка застосування фільтра дати: {e}"
                )


class FilterPresetsWindow(QDialog):
    """Quick filter presets window with common file type filters"""

    def __init__(self, parent_widget):
        # Handle parent widget - archive tree or standalone
        if hasattr(parent_widget, "archive_tree"):
            # Parent has archive tree (main window)
            super().__init__(parent_widget)
            self.archive_tree = parent_widget.archive_tree
            self.main_window = parent_widget  # Store reference to main window
        else:
            # Direct archive tree passed
            super().__init__()
            self.archive_tree = parent_widget
            self.main_window = None
        self.initUI()

    def initUI(self):
        """Initialize the advanced filters window UI"""
        self.setWindowTitle("Розширені фільтри")
        self.setMinimumSize(450, 600)
        self.resize(480, 650)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Custom Filters Section
        custom_group = QGroupBox("🔧 Власні фільтри")
        custom_group_layout = QVBoxLayout(custom_group)

        # Extension filter
        ext_label = QLabel("Фільтр розширень файлів:")
        custom_group_layout.addWidget(ext_label)

        ext_input_layout = QHBoxLayout()
        self.custom_edit = QLineEdit()
        self.custom_edit.setPlaceholderText("напр. .jpg, .png, .gif, .pdf")
        ext_input_layout.addWidget(self.custom_edit)

        apply_ext_btn = QPushButton("Застосувати")
        apply_ext_btn.clicked.connect(self.apply_custom_filter)
        ext_input_layout.addWidget(apply_ext_btn)

        custom_group_layout.addLayout(ext_input_layout)

        # Quick custom presets
        quick_preset_layout = QHBoxLayout()
        quick_preset_layout.addWidget(QLabel("Швидкі пресети:"))

        quick_custom_btn = QPushButton("Зображення")
        quick_custom_btn.clicked.connect(
            lambda: self.set_custom_extension(
                ".jpg, .jpeg, .png, .gif, .bmp, .svg, .webp"
            )
        )
        quick_preset_layout.addWidget(quick_custom_btn)

        quick_docs_btn = QPushButton("Документи")
        quick_docs_btn.clicked.connect(
            lambda: self.set_custom_extension(".pdf, .doc, .docx, .txt, .rtf, .odt")
        )
        quick_preset_layout.addWidget(quick_docs_btn)

        quick_code_btn = QPushButton("Код")
        quick_code_btn.clicked.connect(
            lambda: self.set_custom_extension(".py, .js, .html, .css, .java, .cpp, .c")
        )
        quick_preset_layout.addWidget(quick_code_btn)

        quick_preset_layout.addStretch()
        custom_group_layout.addLayout(quick_preset_layout)

        layout.addWidget(custom_group)

        # Size-based Filters Section
        size_group = QGroupBox("📏 Фільтри за розміром")
        size_group_layout = QVBoxLayout(size_group)

        # Predefined size filters
        size_buttons_layout = QHBoxLayout()

        small_btn = QPushButton("< 1 МБ")
        small_btn.clicked.connect(
            lambda: self.apply_size_filter("small", "Маленькі файли (< 1 МБ)")
        )
        size_buttons_layout.addWidget(small_btn)

        medium_btn = QPushButton("1-10 МБ")
        medium_btn.clicked.connect(
            lambda: self.apply_size_filter("medium", "Середні файли (1-10 МБ)")
        )
        size_buttons_layout.addWidget(medium_btn)

        large_btn = QPushButton("10-100 МБ")
        large_btn.clicked.connect(
            lambda: self.apply_size_filter("large", "Великі файли (10-100 МБ)")
        )
        size_buttons_layout.addWidget(large_btn)

        huge_btn = QPushButton("> 100 МБ")
        huge_btn.clicked.connect(
            lambda: self.apply_size_filter("huge", "Дуже великі файли (> 100 МБ)")
        )
        size_buttons_layout.addWidget(huge_btn)

        size_group_layout.addLayout(size_buttons_layout)

        # Custom size filter
        custom_size_layout = QHBoxLayout()
        custom_size_layout.addWidget(QLabel("Власний розмір:"))

        self.size_input = QSpinBox()
        self.size_input.setRange(1, 10000)
        self.size_input.setValue(10)
        self.size_input.setSuffix(" МБ")
        custom_size_layout.addWidget(self.size_input)

        self.size_operator = QComboBox()
        self.size_operator.addItems([">", "<", "=", "≥", "≤"])
        custom_size_layout.addWidget(self.size_operator)

        apply_size_btn = QPushButton("Застосувати")
        apply_size_btn.clicked.connect(self.apply_custom_size_filter)
        custom_size_layout.addWidget(apply_size_btn)

        custom_size_layout.addStretch()
        size_group_layout.addLayout(custom_size_layout)

        layout.addWidget(size_group)

        # Date-based Filters Section
        date_group = QGroupBox("📅 Фільтри за датою")
        date_group_layout = QVBoxLayout(date_group)

        # Predefined date filters
        date_buttons_layout = QHBoxLayout()

        recent_btn = QPushButton("За останні 7 днів")
        recent_btn.clicked.connect(
            lambda: self.apply_date_filter("recent_7", "Файли за останні 7 днів")
        )
        date_buttons_layout.addWidget(recent_btn)

        month_btn = QPushButton("За останній місяць")
        month_btn.clicked.connect(
            lambda: self.apply_date_filter("recent_30", "Файли за останній місяць")
        )
        date_buttons_layout.addWidget(month_btn)

        year_btn = QPushButton("За останній рік")
        year_btn.clicked.connect(
            lambda: self.apply_date_filter("recent_365", "Файли за останній рік")
        )
        date_buttons_layout.addWidget(year_btn)

        date_group_layout.addLayout(date_buttons_layout)

        old_btn = QPushButton("Старіші за 1 рік")
        old_btn.clicked.connect(
            lambda: self.apply_date_filter("older_365", "Файли старіші за 1 рік")
        )
        date_group_layout.addWidget(old_btn)

        # Custom date filter
        custom_date_layout = QVBoxLayout()
        custom_date_layout.addWidget(QLabel("Власний діапазон дат:"))

        date_range_layout = QHBoxLayout()
        date_range_layout.addWidget(QLabel("Від:"))

        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        date_range_layout.addWidget(self.from_date)

        date_range_layout.addWidget(QLabel("До:"))

        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDate(QDate.currentDate())
        date_range_layout.addWidget(self.to_date)

        custom_date_layout.addLayout(date_range_layout)

        apply_date_btn = QPushButton("Застосувати фільтр дат")
        apply_date_btn.clicked.connect(self.apply_custom_date_filter)
        custom_date_layout.addWidget(apply_date_btn)

        date_group_layout.addLayout(custom_date_layout)

        layout.addWidget(date_group)

        # Action buttons
        button_layout = QHBoxLayout()

        clear_btn = QPushButton("🔄 Очистити всі фільтри")
        clear_btn.clicked.connect(self.clear_all_filters)

        close_btn = QPushButton("Закрити")
        close_btn.clicked.connect(self.close)

        button_layout.addWidget(clear_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Saved filters section
        saved_group = QGroupBox("💾 Збережені фільтри")
        saved_group_layout = QVBoxLayout(saved_group)

        # Saved filters list
        self.saved_filters_list = QListWidget()
        self.saved_filters_list.setMaximumHeight(150)
        self.saved_filters_list.itemDoubleClicked.connect(
            self.on_saved_filter_double_clicked
        )
        saved_group_layout.addWidget(self.saved_filters_list)

        # Saved filter controls
        saved_controls_layout = QHBoxLayout()

        save_filter_btn = QPushButton("💾 Зберегти поточний")
        save_filter_btn.clicked.connect(self.save_current_filter)
        saved_controls_layout.addWidget(save_filter_btn)

        edit_filter_btn = QPushButton("✏️ Редагувати")
        edit_filter_btn.clicked.connect(self.edit_saved_filter)
        saved_controls_layout.addWidget(edit_filter_btn)

        delete_filter_btn = QPushButton("🗑️ Видалити")
        delete_filter_btn.clicked.connect(self.delete_saved_filter)
        saved_controls_layout.addWidget(delete_filter_btn)

        saved_controls_layout.addStretch()
        saved_group_layout.addLayout(saved_controls_layout)

        layout.addWidget(saved_group)

        # Load saved filters
        self.load_saved_filters()

    def apply_extension_filter(self, extensions: str, preset_name: str):
        """Apply an extension filter preset"""
        try:
            # Apply filter using main window's optimized method
            if hasattr(self, "main_window") and self.main_window:
                self.main_window._apply_filter_to_tree(extensions, preset_name)
            else:
                # Fallback: create a simple filter application
                self._apply_filter_to_tree_standalone(extensions, preset_name)
        except Exception as e:
            print(f"FilterPresetsWindow: Error applying extension filter: {e}")

    def _apply_filter_to_tree_standalone(self, extensions: str, preset_name: str):
        """Apply filter directly to archive tree when standalone (no main window)"""
        try:
            # Simple filter application - hide items that don't match extensions
            extensions = [
                ext.strip().lower() for ext in extensions.split(",") if ext.strip()
            ]
            if not extensions:
                return

            root = self.archive_tree.invisibleRootItem()
            hidden_count = 0
            visible_count = 0

            def filter_item(item):
                nonlocal hidden_count, visible_count
                item_path = item.data(0, Qt.UserRole) if hasattr(item, "data") else ""
                if not item_path:
                    item_path = item.text(4) if item.columnCount() > 4 else ""

                if item_path and os.path.isfile(item_path):
                    _, ext = os.path.splitext(item_path)
                    if ext.lower() not in extensions:
                        item.setHidden(True)
                        hidden_count += 1
                    else:
                        item.setHidden(False)
                        visible_count += 1

                for i in range(item.childCount()):
                    filter_item(item.child(i))

            for i in range(root.childCount()):
                filter_item(root.child(i))

            # Update status label if main window is available
            if (
                hasattr(self, "main_window")
                and self.main_window
                and hasattr(self.main_window, "archive_status_label")
            ):
                self.main_window.archive_status_label.setText(
                    f"Фільтр застосовано: {preset_name} ({visible_count} файлів)"
                )
                self.main_window.archive_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #e67e22;
                        padding: 8px;
                        background-color: #fef5e7;
                        border-radius: 5px;
                        border: 1px solid #e67e22;
                        font-weight: 600;
                    }
                """)

            print(
                f"FilterPresetsWindow: Applied filter '{preset_name}' - {visible_count} items visible, {hidden_count} hidden"
            )

        except Exception as e:
            print(f"FilterPresetsWindow: Error applying filter: {e}")

    def apply_special_filter(self, preset_type: str, preset_name: str):
        """Apply a special filter preset"""
        # Apply filter directly to archive tree
        self._apply_special_filter_to_tree(preset_type, preset_name)

    def _apply_special_filter_to_tree(self, preset_type: str, preset_name: str):
        """Apply special filter directly to archive tree"""
        try:
            root = self.archive_tree.invisibleRootItem()
            hidden_count = 0
            visible_count = 0
            current_time = time.time()

            def matches_filter(item_path, item_size):
                """Check if item matches the special filter"""
                if not item_path or not os.path.exists(item_path):
                    return False

                is_file = os.path.isfile(item_path)
                if not is_file:
                    return False

                file_size = os.path.getsize(item_path)
                file_mtime = os.path.getmtime(item_path)

                if preset_type == "size_large":
                    return file_size > 100 * 1024 * 1024  # > 100 MB
                elif preset_type == "recent_7_days":
                    return (current_time - file_mtime) < 7 * 24 * 3600  # Last 7 days
                elif preset_type == "old_1_year":
                    return (
                        current_time - file_mtime
                    ) > 365 * 24 * 3600  # Older than 1 year
                elif preset_type == "size_small":
                    return file_size < 1024 * 1024  # < 1 MB
                elif preset_type == "size_medium":
                    return 1024 * 1024 <= file_size <= 10 * 1024 * 1024  # 1-10 MB
                elif preset_type == "size_large_10":
                    return (
                        10 * 1024 * 1024 <= file_size <= 100 * 1024 * 1024
                    )  # 10-100 MB
                elif preset_type == "size_very_large":
                    return file_size > 100 * 1024 * 1024  # > 100 MB

                return False

            def filter_item(item):
                nonlocal hidden_count, visible_count
                item_path = item.data(0, Qt.UserRole) if hasattr(item, "data") else ""
                if item_path and matches_filter(
                    item_path,
                    item.data(1, Qt.DisplayRole) if hasattr(item, "data") else "",
                ):
                    item.setHidden(False)
                    visible_count += 1
                else:
                    item.setHidden(True)
                    hidden_count += 1

                # Filter children
                for i in range(item.childCount()):
                    filter_item(item.child(i))

            # Apply filter to all top-level items
            for i in range(root.childCount()):
                filter_item(root.child(i))

            # Update status label if main window is available
            if (
                hasattr(self, "main_window")
                and self.main_window
                and hasattr(self.main_window, "archive_status_label")
            ):
                self.main_window.archive_status_label.setText(
                    f"Фільтр застосовано: {preset_name} ({visible_count} файлів)"
                )
                self.main_window.archive_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #e67e22;
                        padding: 8px;
                        background-color: #fef5e7;
                        border-radius: 5px;
                        border: 1px solid #e67e22;
                        font-weight: 600;
                    }
                """)

            print(
                f"FilterPresetsWindow: Applied special filter '{preset_name}' - {visible_count} items visible, {hidden_count} hidden"
            )

        except Exception as e:
            print(f"FilterPresetsWindow: Error applying special filter: {e}")

    def apply_custom_filter(self):
        """Apply custom extension filter"""
        custom_extensions = self.custom_edit.text().strip()
        if custom_extensions:
            self.apply_extension_filter(custom_extensions, "Власний фільтр")

    def clear_all_filters(self):
        """Clear all filters"""
        # Show all items in archive tree
        try:
            root = self.archive_tree.invisibleRootItem()

            def show_item(item):
                item.setHidden(False)
                for i in range(item.childCount()):
                    show_item(item.child(i))

            for i in range(root.childCount()):
                show_item(root.child(i))

            # Update status label if main window is available
            if (
                hasattr(self, "main_window")
                and self.main_window
                and hasattr(self.main_window, "archive_status_label")
            ):
                self.main_window.archive_status_label.setText(
                    "Готовий до пошуку та фільтрації"
                )
                self.main_window.archive_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #2c3e50;
                        padding: 8px;
                        background-color: #ecf0f1;
                        border-radius: 5px;
                        border: 1px solid #bdc3c7;
                        font-weight: 500;
                    }
                """)

        except Exception as e:
            pass  # Silently handle filter clearing errors

    def set_custom_extension(self, extensions: str):
        """Set the custom extension input"""
        self.custom_edit.setText(extensions)

    def apply_size_filter(self, size_type: str, filter_name: str):
        """Apply predefined size-based filter"""
        size_limits = {
            "small": (0, 1),  # < 1 MB
            "medium": (1, 10),  # 1-10 MB
            "large": (10, 100),  # 10-100 MB
            "huge": (100, float("inf")),  # > 100 MB
        }

        if size_type in size_limits:
            min_size, max_size = size_limits[size_type]
            self._apply_size_filter(min_size, max_size, filter_name)

    def apply_custom_size_filter(self):
        """Apply custom size filter"""
        try:
            size_mb = self.size_input.value()
            operator = self.size_operator.currentText()

            # Convert operator text to numeric range
            if operator == ">":
                min_size, max_size = size_mb, float("inf")
                filter_name = f"Файли > {size_mb} МБ"
            elif operator == "<":
                min_size, max_size = 0, size_mb
                filter_name = f"Файли < {size_mb} МБ"
            elif operator == "=":
                min_size, max_size = size_mb, size_mb
                filter_name = f"Файли = {size_mb} МБ"
            elif operator == "≥":
                min_size, max_size = size_mb, float("inf")
                filter_name = f"Файли ≥ {size_mb} МБ"
            elif operator == "≤":
                min_size, max_size = 0, size_mb
                filter_name = f"Файли ≤ {size_mb} МБ"
            else:
                return

            self._apply_size_filter(min_size, max_size, filter_name)

        except Exception as e:
            print(f"FilterPresetsWindow: Error applying custom size filter: {e}")

    def _apply_size_filter(self, min_mb: float, max_mb: float, filter_name: str):
        """Apply size filter to archive tree"""
        try:
            if hasattr(self, "main_window") and self.main_window:
                self.main_window._apply_size_filter(min_mb, max_mb, filter_name)
            else:
                self._apply_size_filter_standalone(min_mb, max_mb, filter_name)
        except Exception as e:
            print(f"FilterPresetsWindow: Error applying size filter: {e}")

    def _apply_size_filter_standalone(
        self, min_mb: float, max_mb: float, filter_name: str
    ):
        """Apply size filter when standalone (no main window)"""
        try:
            root = self.archive_tree.invisibleRootItem()
            min_bytes = min_mb * 1024 * 1024
            max_bytes = max_mb * 1024 * 1024
            visible_count = 0
            hidden_count = 0

            def filter_by_size(item):
                nonlocal visible_count, hidden_count
                item_path = item.data(0, Qt.UserRole) if hasattr(item, "data") else ""
                if not item_path:
                    item_path = item.text(4) if item.columnCount() > 4 else ""

                if item_path and os.path.isfile(item_path):
                    try:
                        file_size = os.path.getsize(item_path)
                        if min_bytes <= file_size <= max_bytes:
                            item.setHidden(False)
                            visible_count += 1
                        else:
                            item.setHidden(True)
                            hidden_count += 1
                    except OSError:
                        item.setHidden(True)
                        hidden_count += 1
                else:
                    item.setHidden(False)  # Show directories

                for i in range(item.childCount()):
                    filter_by_size(item.child(i))

            for i in range(root.childCount()):
                filter_by_size(root.child(i))

            # Update status label if main window is available
            if (
                hasattr(self, "main_window")
                and self.main_window
                and hasattr(self.main_window, "archive_status_label")
            ):
                self.main_window.archive_status_label.setText(
                    f"Фільтр застосовано: {filter_name} ({visible_count} файлів)"
                )
                self.main_window.archive_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #e67e22;
                        padding: 8px;
                        background-color: #fef5e7;
                        border-radius: 5px;
                        border: 1px solid #e67e22;
                        font-weight: 600;
                    }
                """)

            print(
                f"FilterPresetsWindow: Applied size filter '{filter_name}' - {visible_count} items visible, {hidden_count} hidden"
            )

        except Exception as e:
            print(f"FilterPresetsWindow: Error in size filter: {e}")

    def apply_date_filter(self, date_type: str, filter_name: str):
        """Apply predefined date-based filter"""
        try:
            from datetime import datetime, timedelta

            now = datetime.now()

            if date_type == "recent_7":
                min_date = now - timedelta(days=7)
                max_date = now
            elif date_type == "recent_30":
                min_date = now - timedelta(days=30)
                max_date = now
            elif date_type == "recent_365":
                min_date = now - timedelta(days=365)
                max_date = now
            elif date_type == "older_365":
                min_date = datetime(1970, 1, 1)
                max_date = now - timedelta(days=365)
            else:
                return

            self._apply_date_filter(min_date, max_date, filter_name)

        except Exception as e:
            print(f"FilterPresetsWindow: Error applying date filter: {e}")

    def apply_custom_date_filter(self):
        """Apply custom date range filter"""
        try:
            from datetime import datetime

            from_date_qdate = self.from_date.date()
            to_date_qdate = self.to_date.date()

            min_date = datetime(
                from_date_qdate.year(), from_date_qdate.month(), from_date_qdate.day()
            )
            max_date = datetime(
                to_date_qdate.year(),
                to_date_qdate.month(),
                to_date_qdate.day(),
                23,
                59,
                59,
            )

            filter_name = f"Файли з {from_date_qdate.toString('dd.MM.yyyy')} по {to_date_qdate.toString('dd.MM.yyyy')}"

            self._apply_date_filter(min_date, max_date, filter_name)

        except Exception as e:
            print(f"FilterPresetsWindow: Error applying custom date filter: {e}")

    def _apply_date_filter(self, min_date, max_date, filter_name: str):
        """Apply date filter to archive tree"""
        try:
            if hasattr(self, "main_window") and self.main_window:
                self.main_window._apply_date_filter(min_date, max_date, filter_name)
            else:
                self._apply_date_filter_standalone(min_date, max_date, filter_name)
        except Exception as e:
            print(f"FilterPresetsWindow: Error applying date filter: {e}")

    def _apply_date_filter_standalone(self, min_date, max_date, filter_name: str):
        """Apply date filter when standalone (no main window)"""
        try:
            root = self.archive_tree.invisibleRootItem()
            min_timestamp = min_date.timestamp()
            max_timestamp = max_date.timestamp()
            visible_count = 0
            hidden_count = 0

            def filter_by_date(item):
                nonlocal visible_count, hidden_count
                item_path = item.data(0, Qt.UserRole) if hasattr(item, "data") else ""
                if not item_path:
                    item_path = item.text(4) if item.columnCount() > 4 else ""

                if item_path and os.path.isfile(item_path):
                    try:
                        file_mtime = os.path.getmtime(item_path)
                        if min_timestamp <= file_mtime <= max_timestamp:
                            item.setHidden(False)
                            visible_count += 1
                        else:
                            item.setHidden(True)
                            hidden_count += 1
                    except OSError:
                        item.setHidden(True)
                        hidden_count += 1
                else:
                    item.setHidden(False)  # Show directories

                for i in range(item.childCount()):
                    filter_by_date(item.child(i))

            for i in range(root.childCount()):
                filter_by_date(root.child(i))

            # Update status label if main window is available
            if (
                hasattr(self, "main_window")
                and self.main_window
                and hasattr(self.main_window, "archive_status_label")
            ):
                self.main_window.archive_status_label.setText(
                    f"Фільтр застосовано: {filter_name} ({visible_count} файлів)"
                )
                self.main_window.archive_status_label.setStyleSheet("""
                    QLabel {
                        font-size: 11px;
                        color: #e67e22;
                        padding: 8px;
                        background-color: #fef5e7;
                        border-radius: 5px;
                        border: 1px solid #e67e22;
                        font-weight: 600;
                    }
                """)

            print(
                f"FilterPresetsWindow: Applied date filter '{filter_name}' - {visible_count} items visible, {hidden_count} hidden"
            )

        except Exception as e:
            print(f"FilterPresetsWindow: Error in date filter: {e}")

    def get_saved_filters_path(self):
        """Get path to saved filters file"""
        import os

        filters_dir = os.path.join(os.path.expanduser("~"), ".DesktopOrganizer")
        if not os.path.exists(filters_dir):
            os.makedirs(filters_dir)
        return os.path.join(filters_dir, "saved_filters.json")

    def load_saved_filters(self):
        """Load saved filters from file"""
        try:
            import json

            filters_path = self.get_saved_filters_path()
            if os.path.exists(filters_path):
                with open(filters_path, "r", encoding="utf-8") as f:
                    self.saved_filters = json.load(f)
            else:
                self.saved_filters = []
        except Exception as e:
            print(f"FilterPresetsWindow: Error loading saved filters: {e}")
            self.saved_filters = []

        self.update_saved_filters_list()

    def save_filters_to_file(self):
        """Save filters to file"""
        try:
            import json

            filters_path = self.get_saved_filters_path()
            with open(filters_path, "w", encoding="utf-8") as f:
                json.dump(self.saved_filters, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"FilterPresetsWindow: Error saving filters: {e}")

    def update_saved_filters_list(self):
        """Update the saved filters list widget"""
        self.saved_filters_list.clear()
        for i, filter_data in enumerate(self.saved_filters):
            filter_type = filter_data.get("type", "extension")
            name = filter_data.get("name", f"Фільтр {i + 1}")

            if filter_type == "extension":
                desc = f"📄 {name} ({filter_data.get('extensions', '')})"
            elif filter_type == "size":
                desc = f"📏 {name} ({filter_data.get('description', '')})"
            elif filter_type == "date":
                desc = f"📅 {name} ({filter_data.get('description', '')})"
            else:
                desc = f"🔧 {name}"

            self.saved_filters_list.addItem(desc)

    def save_current_filter(self):
        """Save the current filter settings"""
        try:
            # Get current filter settings from UI
            custom_extensions = self.custom_edit.text().strip()

            if custom_extensions:
                # Save as extension filter
                filter_data = {
                    "type": "extension",
                    "name": f"Кастомний фільтр {len(self.saved_filters) + 1}",
                    "extensions": custom_extensions,
                    "created_at": __import__("datetime").datetime.now().isoformat(),
                }
            else:
                # Save as size filter if size is specified
                size_value = self.size_input.value()
                size_operator = self.size_operator.currentText()
                filter_data = {
                    "type": "size",
                    "name": f"Фільтр розміру {len(self.saved_filters) + 1}",
                    "size_mb": size_value,
                    "operator": size_operator,
                    "description": f"Файли {size_operator} {size_value} МБ",
                    "created_at": __import__("datetime").datetime.now().isoformat(),
                }

            self.saved_filters.append(filter_data)
            self.save_filters_to_file()
            self.update_saved_filters_list()

            if hasattr(self, "main_window") and self.main_window:
                if hasattr(self.main_window, "log_message"):
                    self.main_window.log_message(
                        f"CleanupHelper: Фільтр '{filter_data['name']}' збережено"
                    )

        except Exception as e:
            print(f"FilterPresetsWindow: Error saving filter: {e}")

    def edit_saved_filter(self):
        """Edit selected saved filter"""
        try:
            current_row = self.saved_filters_list.currentRow()
            if current_row < 0 or current_row >= len(self.saved_filters):
                return

            filter_data = self.saved_filters[current_row]

            # Create edit dialog
            from PyQt5.QtWidgets import (
                QDialog,
                QVBoxLayout,
                QHBoxLayout,
                QLabel,
                QLineEdit,
                QPushButton,
            )

            edit_dialog = QDialog(self)
            edit_dialog.setWindowTitle("Редагувати фільтр")
            edit_dialog.setModal(True)
            layout = QVBoxLayout(edit_dialog)

            # Name input
            name_layout = QHBoxLayout()
            name_layout.addWidget(QLabel("Назва:"))
            name_input = QLineEdit(filter_data.get("name", ""))
            name_layout.addWidget(name_input)
            layout.addLayout(name_layout)

            # Type-specific inputs
            if filter_data.get("type") == "extension":
                ext_layout = QHBoxLayout()
                ext_layout.addWidget(QLabel("Розширення:"))
                ext_input = QLineEdit(filter_data.get("extensions", ""))
                ext_layout.addWidget(ext_input)
                layout.addLayout(ext_layout)
            elif filter_data.get("type") == "size":
                size_layout = QHBoxLayout()
                size_layout.addWidget(QLabel("Розмір (МБ):"))
                from PyQt5.QtWidgets import QSpinBox

                size_input = QSpinBox()
                size_input.setRange(1, 10000)
                size_input.setValue(filter_data.get("size_mb", 10))
                size_layout.addWidget(size_input)
                layout.addLayout(size_layout)

            # Buttons
            button_layout = QHBoxLayout()
            save_btn = QPushButton("Зберегти")
            cancel_btn = QPushButton("Скасувати")
            button_layout.addWidget(save_btn)
            button_layout.addWidget(cancel_btn)
            layout.addLayout(button_layout)

            def save_changes():
                if filter_data.get("type") == "extension":
                    filter_data["extensions"] = ext_input.text().strip()
                elif filter_data.get("type") == "size":
                    filter_data["size_mb"] = size_input.value()
                    operator = filter_data.get("operator", ">")
                    filter_data["description"] = (
                        f"Файли {operator} {size_input.value()} МБ"
                    )

                filter_data["name"] = name_input.text().strip()
                self.save_filters_to_file()
                self.update_saved_filters_list()
                edit_dialog.accept()

            save_btn.clicked.connect(save_changes)
            cancel_btn.clicked.connect(edit_dialog.reject)

            edit_dialog.exec_()

        except Exception as e:
            print(f"FilterPresetsWindow: Error editing filter: {e}")

    def delete_saved_filter(self):
        """Delete selected saved filter"""
        try:
            current_row = self.saved_filters_list.currentRow()
            if current_row < 0 or current_row >= len(self.saved_filters):
                return

            # Confirm deletion
            from PyQt5.QtWidgets import QMessageBox

            reply = QMessageBox.question(
                self,
                "Підтвердження видалення",
                "Ви впевнені, що хочете видалити цей фільтр?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                deleted_filter = self.saved_filters.pop(current_row)
                self.save_filters_to_file()
                self.update_saved_filters_list()

                if hasattr(self, "main_window") and self.main_window:
                    if hasattr(self.main_window, "log_message"):
                        self.main_window.log_message(
                            f"CleanupHelper: Фільтр '{deleted_filter.get('name', '')}' видалено"
                        )

        except Exception as e:
            print(f"FilterPresetsWindow: Error deleting filter: {e}")

    def on_saved_filter_double_clicked(self, item):
        """Handle double-click on saved filter item"""
        try:
            current_row = self.saved_filters_list.row(item)
            if current_row >= 0 and current_row < len(self.saved_filters):
                filter_data = self.saved_filters[current_row]
                self.apply_saved_filter(filter_data)
        except Exception as e:
            print(
                f"FilterPresetsWindow: Error applying saved filter on double-click: {e}"
            )

    def apply_saved_filter(self, filter_data):
        """Apply a saved filter"""
        try:
            filter_type = filter_data.get("type", "extension")
            filter_name = filter_data.get("name", "Збережений фільтр")

            if filter_type == "extension":
                extensions = filter_data.get("extensions", "")
                if extensions:
                    self.apply_extension_filter(extensions, filter_name)
            elif filter_type == "size":
                size_mb = filter_data.get("size_mb", 10)
                operator = filter_data.get("operator", ">")

                # Convert operator to range
                if operator == ">":
                    min_size, max_size = size_mb, float("inf")
                elif operator == "<":
                    min_size, max_size = 0, size_mb
                elif operator == "=":
                    min_size, max_size = size_mb, size_mb
                elif operator == "≥":
                    min_size, max_size = size_mb, float("inf")
                elif operator == "≤":
                    min_size, max_size = 0, size_mb
                else:
                    return

                self._apply_size_filter(min_size, max_size, filter_name)

        except Exception as e:
            print(f"FilterPresetsWindow: Error applying saved filter: {e}")


# ControlPanelWindow class has been removed - all filtering functionality is now handled directly

# REMOVED: All ControlPanelWindow UI and methods have been removed


class CompressionWindow(QDialog):
    """Separate window for file compression"""

    def __init__(self, selected_items: List[str], parent=None):
        super().__init__(parent)
        self.selected_items = selected_items
        self.parent_widget = parent
        self.compression_thread = None

        self.initUI()

    def initUI(self):
        """Initialize the compression window UI"""
        self.setWindowTitle("Стиснення")
        self.setMinimumSize(400, 300)
        self.resize(500, 400)

        layout = QVBoxLayout(self)

        # Count files and directories
        file_count = sum(1 for item in self.selected_items if os.path.isfile(item))
        dir_count = sum(1 for item in self.selected_items if os.path.isdir(item))

        # Create header text
        header_parts = []
        if file_count > 0:
            header_parts.append(f"{file_count} файл(и)")
        if dir_count > 0:
            header_parts.append(f"{dir_count} папок")

        header_label = QLabel(f"Обрано {', '.join(header_parts)} для стиснення")
        layout.addWidget(header_label)

        # File list
        self.files_list = QListWidget()
        self.files_list.setMaximumHeight(150)

        # Add files and directories to list with sizes
        total_size = 0
        for item_path in self.selected_items:
            try:
                if os.path.isfile(item_path):
                    # It's a file
                    file_size = os.path.getsize(item_path)
                    total_size += file_size
                    item_text = f"{os.path.basename(item_path)} ({humanize.naturalsize(file_size)})"
                    list_item = QListWidgetItem(item_text)
                    list_item.setData(Qt.UserRole, item_path)
                    self.files_list.addItem(list_item)
                elif os.path.isdir(item_path):
                    # It's a directory - calculate size recursively
                    dir_size = 0
                    for root, dirs, files in os.walk(item_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            if os.path.exists(file_path):
                                dir_size += os.path.getsize(file_path)
                    total_size += dir_size
                    item_text = f"{os.path.basename(item_path)} ({humanize.naturalsize(dir_size)})"
                    list_item = QListWidgetItem(item_text)
                    list_item.setData(Qt.UserRole, item_path)
                    self.files_list.addItem(list_item)
            except OSError:
                item_text = f"{os.path.basename(item_path)} (розмір невідомий)"
                list_item = QListWidgetItem(item_text)
                list_item.setData(Qt.UserRole, item_path)
                self.files_list.addItem(list_item)

        layout.addWidget(QLabel("Файли:"))
        layout.addWidget(self.files_list)

        # Compression options
        options_layout = QGridLayout()

        # Archive name
        options_layout.addWidget(QLabel("Назва:"), 0, 0)
        self.archive_name_edit = QLineEdit(
            f"compressed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        )
        options_layout.addWidget(self.archive_name_edit, 0, 1)

        # Compression level
        options_layout.addWidget(QLabel("Рівень:"), 1, 0)
        self.compression_level_slider = QSlider(Qt.Horizontal)
        self.compression_level_slider.setRange(1, 9)
        self.compression_level_slider.setValue(6)
        self.compression_level_slider.setTickPosition(QSlider.TicksBelow)
        self.compression_level_slider.setTickInterval(2)
        options_layout.addWidget(self.compression_level_slider, 1, 1)

        self.compression_level_label = QLabel("6 (Нормальний)")
        self.compression_level_slider.valueChanged.connect(
            lambda v: self.compression_level_label.setText(f"{v} (Нормальний)")
        )
        options_layout.addWidget(self.compression_level_label, 1, 2)

        # Format selection
        options_layout.addWidget(QLabel("Формат:"), 2, 0)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["ZIP", "TAR.GZ", "TAR.BZ2", "TAR.XZ", "7Z"])
        options_layout.addWidget(self.format_combo, 2, 1)

        layout.addLayout(options_layout)

        # Statistics
        self.total_size_label = QLabel(f"Розмір: {humanize.naturalsize(total_size)}")
        layout.addWidget(self.total_size_label)

        # Buttons
        button_layout = QHBoxLayout()

        self.compress_btn = QPushButton("Стиснути")
        self.compress_btn.clicked.connect(self.start_compression)
        button_layout.addWidget(self.compress_btn)

        cancel_btn = QPushButton("Скасувати")
        cancel_btn.clicked.connect(self.close)
        button_layout.addWidget(cancel_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

    def start_compression(self):
        """Start compression process"""
        if self.compression_thread and self.compression_thread.isRunning():
            return

        # Get output path
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Зберегти архів як",
            self.archive_name_edit.text(),
            self.get_format_filter(),
        )

        if not output_path:
            return

        # Ensure file has proper extension
        format_ext = self.get_format_extension()
        if not output_path.endswith(format_ext):
            output_path += format_ext

        self.compress_btn.setEnabled(False)
        self.status_label.setText("Стиснення файлів...")

        # Start compression thread
        compression_level = self.compression_level_slider.value()
        self.compression_thread = FileCompressor(
            self.selected_items, output_path, compression_level
        )
        self.compression_thread.progress_updated.connect(self.update_progress)
        self.compression_thread.compression_finished.connect(
            self.on_compression_finished
        )
        self.compression_thread.start()

    def get_format_filter(self) -> str:
        """Get file dialog filter based on selected format"""
        format_text = self.format_combo.currentText()
        filters = {
            "ZIP": "ZIP Files (*.zip);;All Files (*)",
            "TAR.GZ": "TAR.GZ Files (*.tar.gz;*.tgz);;All Files (*)",
            "TAR.BZ2": "TAR.BZ2 Files (*.tar.bz2);;All Files (*)",
            "TAR.XZ": "TAR.XZ Files (*.tar.xz);;All Files (*)",
            "7Z": "7-Zip Files (*.7z);;All Files (*)",
        }
        return filters.get(format_text, "ZIP Files (*.zip);;All Files (*)")

    def get_format_extension(self) -> str:
        """Get file extension based on selected format"""
        format_exts = {
            "ZIP": ".zip",
            "TAR.GZ": ".tar.gz",
            "TAR.BZ2": ".tar.bz2",
            "TAR.XZ": ".tar.xz",
            "7Z": ".7z",
        }
        return format_exts.get(self.format_combo.currentText(), ".zip")

    def update_progress(self, progress, message):
        """Update compression progress"""

    def on_compression_finished(self, output_path, success):
        """Handle compression completion"""
        self.compress_btn.setEnabled(True)

        if success:
            pass

            # Check actual file size
            if os.path.exists(output_path):
                compressed_size = os.path.getsize(output_path)
                original_size = sum(
                    os.path.getsize(f) for f in self.selected_files if os.path.exists(f)
                )
                if original_size > 0:
                    ratio = (1 - compressed_size / original_size) * 100
                    self.estimated_size_label.setText(
                        f"Стиснутий розмір: {humanize.naturalsize(compressed_size)} "
                        f"(збережено {ratio:.1f}%)"
                    )

            QMessageBox.information(
                self, "Успіх", f"Файли успішно стиснено!\nЗбережено в: {output_path}"
            )

            # Log to parent application
            if hasattr(self.parent_widget, "main_window") and hasattr(
                self.parent_widget.main_window, "log_message"
            ):
                self.parent_widget.main_window.log_message(
                    f"CleanupHelper: Стиснено {len(self.selected_files)} файлів до {output_path}"
                )

            self.close()
        else:
            QMessageBox.critical(
                self,
                "Помилка",
                "Стиснення не вдалося. Будь ласка, перевірте журнал для деталей.",
            )

    def closeEvent(self, event):
        """Handle window close event"""
        if self.compression_thread and self.compression_thread.isRunning():
            self.compression_thread.stop()
            self.compression_thread.wait()
        event.accept()


# Standalone testing
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    window = CleanupHelperWidget()
    window.setWindowTitle("Desktop Cleanup Helper - Standalone Mode")
    window.resize(1000, 700)
    window.show()

    sys.exit(app.exec_())
