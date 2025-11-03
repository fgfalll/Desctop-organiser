"""Configuration manager for petroleum program launcher"""

import json
import logging
import shutil
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger('PetroleumLauncher')


class PetroleumProgramConfigManager:
    """Manages external petroleum program configuration files"""

    def __init__(self):
        self.config_dir = None
        self.config_file = None
        self.config = {}
        self.default_config = {}
        self._init_default_config()
        self._setup_config_directory()
        self.load_configuration()

    def _init_default_config(self):
        """Initialize default petroleum program configuration"""
        self.default_config = self.get_default_config()

    def _setup_config_directory(self):
        """Setup the configuration directory in app settings folder"""
        try:
            # Try to find the application settings directory
            import sys

            # Check if we're running within the main application
            for module_name in sys.modules:
                if 'main' in module_name.lower() or 'organizer' in module_name.lower():
                    main_app = sys.modules[module_name]
                    if hasattr(main_app, 'settings'):
                        # Use the main app's settings directory
                        settings_dir = getattr(main_app.settings, 'settings_dir', None)
                        if settings_dir and os.path.exists(settings_dir):
                            self.config_dir = Path(settings_dir) / "petroleum_launcher"
                            self.config_dir.mkdir(exist_ok=True)
                            logger.info(f"Using app settings directory: {self.config_dir}")
                            break

            # Fallback to user profile
            if not self.config_dir:
                self.config_dir = Path.home() / ".DesktopOrganizer" / "PetroleumLauncher"
                self.config_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Using user profile config directory: {self.config_dir}")

            # Set config file path
            self.config_file = self.config_dir / "petroleum_programs.json"

        except Exception as e:
            logger.error(f"Error setting up config directory: {e}")
            # Use current directory as last resort
            self.config_dir = Path(".")
            self.config_file = self.config_dir / "petroleum_programs.json"

    def load_configuration(self):
        """Load configuration from JSON file"""
        try:
            if self.config_file.exists():
                logger.info(f"Loading configuration from: {self.config_file}")
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)

                # Check if it's the exported format with "programs" key
                if "programs" in loaded_config:
                    program_config = loaded_config["programs"]
                elif "metadata" in loaded_config:
                    # Old format with metadata - extract non-metadata keys
                    program_config = {k: v for k, v in loaded_config.items() if k != "metadata"}
                else:
                    # Direct program config
                    program_config = loaded_config

                # Validate and merge with default config
                self.config = self._validate_and_merge_config(program_config)
                logger.info(f"Loaded {len(self.config)} program configurations: {list(self.config.keys())}")
                logger.debug(f"Configuration structure sample: {list(self.config.items())[:1] if self.config else 'No configs'}")

                # If no valid configurations were loaded, fall back to defaults
                if len(self.config) == 0:
                    logger.warning("No valid configurations loaded, falling back to defaults")
                    self.config = self.default_config.copy()
                    self.save_configuration()  # Recreate config file
                    logger.info(f"Recreated config with {len(self.config)} default programs")
            else:
                logger.info("Configuration file not found, using defaults")
                self.config = self.default_config.copy()
                self.save_configuration()  # Create default config file

        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            self.config = self.default_config.copy()

    def save_configuration(self):
        """Save configuration to JSON file"""
        try:
            if not self.config_file.parent.exists():
                self.config_file.parent.mkdir(parents=True, exist_ok=True)

            # Add metadata
            config_with_metadata = {
                "metadata": {
                    "version": "1.0",
                    "created_date": datetime.now().isoformat(),
                    "last_modified": datetime.now().isoformat(),
                    "description": "Petroleum program configuration for Desktop Organizer",
                    "program_count": len(self.config)
                },
                "programs": self.config
            }

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_with_metadata, f, indent=2, ensure_ascii=False)

            logger.info(f"Configuration saved to: {self.config_file}")
            return True

        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False

    def load_configuration_from_file(self, file_path: str) -> bool:
        """Load configuration from a specific JSON file"""
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                logger.error(f"Configuration file not found: {file_path}")
                return False

            logger.info(f"Loading configuration from: {file_path}")
            with open(file_path_obj, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)

            # Check if it's the new format with "programs" key
            if "programs" in loaded_config:
                program_config = loaded_config["programs"]
            elif "metadata" in loaded_config:
                # Old format with metadata
                program_config = {k: v for k, v in loaded_config.items() if k != "metadata"}
            else:
                program_config = loaded_config

            # Validate and merge with default config
            self.config = self._validate_and_merge_config(program_config)

            # Save to proper location
            self.save_configuration()

            # Check if file was in module directory and move it
            if "modules" in str(file_path).lower():
                try:
                    shutil.move(file_path, self.config_file)
                    logger.info(f"Moved configuration to: {self.config_file}")
                except Exception as e:
                    logger.warning(f"Could not move config file: {e}")

            logger.info(f"Successfully loaded {len(self.config)} program configurations")
            return True

        except Exception as e:
            logger.error(f"Error loading configuration from {file_path}: {e}")
            return False

    def _validate_and_merge_config(self, loaded_config: Dict) -> Dict:
        """Validate and merge loaded configuration with defaults"""
        validated_config = {}

        logger.info(f"Validating loaded config with {len(loaded_config)} items: {list(loaded_config.keys())}")
        logger.info(f"Default config has {len(self.default_config)} items: {list(self.default_config.keys())}")

        for program_key, program_data in loaded_config.items():
            # Validate required fields
            if not isinstance(program_data, dict):
                logger.warning(f"Skipping invalid program config for: {program_key}")
                continue

            required_fields = ["display_name"]
            if not all(field in program_data for field in required_fields):
                logger.warning(f"Program {program_key} missing required fields, using defaults if available")
                if program_key in self.default_config:
                    continue  # Use default config

            # Merge with default if program exists in defaults
            if program_key in self.default_config:
                default_program = self.default_config[program_key]
                # Start with default, then override with loaded config
                merged_program = default_program.copy()
                merged_program.update(program_data)
                validated_config[program_key] = merged_program
            else:
                # New program, validate structure
                if "display_name" in program_data:
                    validated_config[program_key] = program_data
                else:
                    logger.warning(f"Skipping program {program_key} - missing display_name")

        logger.info(f"Validation complete. {len(validated_config)} programs validated: {list(validated_config.keys())}")
        return validated_config

    def add_program(self, program_key: str, program_data: Dict) -> bool:
        """Add a new program to the configuration"""
        try:
            if program_key in self.config:
                logger.warning(f"Program {program_key} already exists, updating")

            # Validate program data
            if "display_name" not in program_data:
                logger.error("Program must have a display_name")
                return False

            self.config[program_key] = program_data
            self.save_configuration()
            logger.info(f"Added program: {program_key} - {program_data.get('display_name', 'Unknown')}")
            return True

        except Exception as e:
            logger.error(f"Error adding program: {e}")
            return False

    def remove_program(self, program_key: str) -> bool:
        """Remove a program from the configuration"""
        try:
            if program_key in self.config:
                del self.config[program_key]
                self.save_configuration()
                logger.info(f"Removed program: {program_key}")
                return True
            else:
                logger.warning(f"Program {program_key} not found in configuration")
                return False

        except Exception as e:
            logger.error(f"Error removing program: {e}")
            return False

    def get_config(self) -> Dict:
        """Get the current configuration"""
        return self.config.copy()

    def get_config_file_path(self) -> str:
        """Get the configuration file path"""
        return str(self.config_file)

    def export_configuration(self, file_path: str) -> bool:
        """Export current configuration to a JSON file"""
        try:
            export_path = Path(file_path)
            if not export_path.parent.exists():
                export_path.parent.mkdir(parents=True, exist_ok=True)

            export_data = {
                "metadata": {
                    "version": "1.0",
                    "export_date": datetime.now().isoformat(),
                    "source": "Desktop Organizer Petroleum Launcher",
                    "program_count": len(self.config)
                },
                "programs": self.config
            }

            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Configuration exported to: {export_path}")
            return True

        except Exception as e:
            logger.error(f"Error exporting configuration: {e}")
            return False

    def get_default_config(self) -> Dict:
        """Get the default program configuration - now empty for user-driven configuration"""
        logger.info("Using empty configuration - all programs must be added manually by users")
        return {}