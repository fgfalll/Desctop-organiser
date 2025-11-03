"""Window manager for multi-monitor support and window positioning"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger('PetroleumLauncher')

# Try to import pywin32
try:
    import win32api
    WINDOWS_SUPPORT = True
except ImportError:
    WINDOWS_SUPPORT = False


class WindowManager:
    """Manages multi-monitor detection and window positioning"""

    def __init__(self):
        self.monitors = []
        self.primary_monitor = None
        self.detect_monitors()

    def detect_monitors(self) -> List[Dict[str, Any]]:
        """Detect connected monitors and their properties"""
        self.monitors = []

        if not WINDOWS_SUPPORT:
            # Fallback for non-Windows systems
            self.monitors.append({
                'index': 0,
                'is_primary': True,
                'left': 0,
                'top': 0,
                'width': 1920,
                'height': 1080,
                'work_left': 0,
                'work_top': 0,
                'work_width': 1920,
                'work_height': 1080,
                'dpi': 96
            })
            self.primary_monitor = self.monitors[0]
            return self.monitors

        try:
            # Get monitor information
            monitor_info = win32api.GetMonitorInfo(win32api.MonitorFromPoint((0, 0)))

            # Get all monitors with improved callback
            try:
                def callback(hmonitor, hdc, rect, data):
                    try:
                        info = win32api.GetMonitorInfo(hmonitor)
                        monitor = {
                            'index': len(self.monitors),
                            'is_primary': info['flags'] & win32api.MONITORINFOF_PRIMARY != 0,
                            'left': info['Monitor'][0],
                            'top': info['Monitor'][1],
                            'width': info['Monitor'][2] - info['Monitor'][0],
                            'height': info['Monitor'][3] - info['Monitor'][1],
                            'work_left': info['Work'][0],
                            'work_top': info['Work'][1],
                            'work_width': info['Work'][2] - info['Work'][0],
                            'work_height': info['Work'][3] - info['Work'][1]
                        }

                        if monitor['is_primary']:
                            self.primary_monitor = monitor

                        self.monitors.append(monitor)
                        logger.debug(f"Detected monitor {monitor['index']}: {monitor['width']}x{monitor['height']} at ({monitor['left']}, {monitor['top']}) - Primary: {monitor['is_primary']}")
                        return True
                    except Exception as e:
                        logger.debug(f"Error processing monitor: {e}")
                        return True

                # Use proper enumeration for all monitors
                win32api.EnumDisplayMonitors(None, None, callback, None)

            except Exception as e:
                logger.error(f"Error enumerating monitors: {e}")
                # Try alternative method
                try:
                    # Fallback: Get monitor at cursor position
                    hmonitor = win32api.MonitorFromPoint((0, 0))
                    info = win32api.GetMonitorInfo(hmonitor)
                    monitor = {
                        'index': 0,
                        'is_primary': True,
                        'left': info['Monitor'][0],
                        'top': info['Monitor'][1],
                        'width': info['Monitor'][2] - info['Monitor'][0],
                        'height': info['Monitor'][3] - info['Monitor'][1],
                        'work_left': info['Work'][0],
                        'work_top': info['Work'][1],
                        'work_width': info['Work'][2] - info['Work'][0],
                        'work_height': info['Work'][3] - info['Work'][1]
                    }
                    self.monitors.append(monitor)
                    self.primary_monitor = monitor
                    logger.info(f"Using fallback monitor detection: {monitor['width']}x{monitor['height']}")
                except Exception as fallback_e:
                    logger.error(f"Fallback monitor detection failed: {fallback_e}")
                    raise e

        except Exception as e:
            logger.error(f"Error detecting monitors: {e}")
            # Fallback to single monitor with work area fields
            self.monitors.append({
                'index': 0,
                'is_primary': True,
                'left': 0,
                'top': 0,
                'width': 1920,
                'height': 1080,
                'work_left': 0,
                'work_top': 0,
                'work_width': 1920,
                'work_height': 1080,
                'dpi': 96
            })
            self.primary_monitor = self.monitors[0]

        return self.monitors

    def get_optimal_position(self, program_name: str = "") -> Dict[str, int]:
        """Get optimal window position for a program"""
        try:
            if len(self.monitors) == 1:
                # Single monitor setup
                monitor = self.monitors[0]
                work_left = monitor.get('work_left', monitor.get('left', 0))
                work_top = monitor.get('work_top', monitor.get('top', 0))
                work_width = monitor.get('work_width', monitor.get('width', 1920))
                work_height = monitor.get('work_height', monitor.get('height', 1080))

                return {
                    'left': work_left + 50,
                    'top': work_top + 50,
                    'width': min(1200, work_width - 100),
                    'height': min(800, work_height - 100)
                }

            # Multi-monitor setup - always use primary monitor for launching
            # Positioning will be handled dynamically by workflows using OpenCV
            monitor = self.primary_monitor or self.monitors[0]

            work_left = monitor.get('work_left', monitor.get('left', 0))
            work_top = monitor.get('work_top', monitor.get('top', 0))
            work_width = monitor.get('work_width', monitor.get('width', 1920))
            work_height = monitor.get('work_height', monitor.get('height', 1080))

            return {
                'left': work_left + 50,
                'top': work_top + 50,
                'width': min(1200, work_width - 100),
                'height': min(800, work_height - 100)
            }
        except Exception as e:
            logger.error(f"Error getting optimal position: {e}")
            # Fallback to safe default position
            return {
                'left': 50,
                'top': 50,
                'width': 1200,
                'height': 800
            }

    def get_monitor_info(self) -> List[Dict[str, Any]]:
        """Get information about all detected monitors"""
        return self.monitors.copy()

    def get_monitor_count(self) -> int:
        """Get the number of detected monitors"""
        return len(self.monitors)

    def detect_monitors_debug(self) -> str:
        """Debug method to get detailed monitor information"""
        try:
            self.detect_monitors()
            info = f"Detected {len(self.monitors)} monitor(s):\n"
            for i, monitor in enumerate(self.monitors):
                info += f"  Monitor {i}: {monitor['width']}x{monitor['height']} at ({monitor['left']}, {monitor['top']})"
                if monitor.get('is_primary'):
                    info += " [PRIMARY]"
                info += "\n"
            return info
        except Exception as e:
            return f"Error detecting monitors: {e}"