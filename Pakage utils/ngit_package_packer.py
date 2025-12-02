#!/usr/bin/env python3
"""
NGIT Package Packer - Desktop Organizer Module Packaging Tool

This tool allows users to package modules as .ngitpac files for distribution
and easy installation through the Desktop Organizer main application.

Usage:
    python ngit_package_packer.py create <module_path> [output_path]
    python ngit_package_packer.py validate <module_path>
    python ngit_package_packer.py info <package_file>
    python ngit_package_packer.py extract <package_file> [output_path]
"""

import os
import sys
import json
import zipfile
import tempfile
import shutil
import argparse
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import importlib.util


# NGIT Package Specification
class NGITPackageSpec:
    """NGIT Package Format Specification"""

    # File extensions
    PACKAGE_EXT = ".ngitpac"
    MANIFEST_FILE = "package.json"
    CHECKSUM_FILE = "checksums.json"

    # Required manifest fields
    REQUIRED_FIELDS = [
        "name", "version", "description", "author",
        "main_class", "dependencies", "python_version"
    ]

    # Optional fields with defaults
    OPTIONAL_FIELDS = {
        "category": "General",
        "menu_text": None,
        "permissions": [],
        "min_desktop_organizer_version": "1.0.0",
        "license": "Unknown",
        "homepage": "",
        "repository": "",
        "keywords": [],
        "entry_point": "main.py",
        "package_type": "module"  # module, theme, plugin
    }


class PackageValidationError(Exception):
    """Raised when package validation fails"""
    pass


class PackageCreator:
    """Creates NGIT packages from modules"""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def validate_module(self, module_path: str) -> bool:
        """Validate a module before packaging"""
        self.errors.clear()
        self.warnings.clear()

        print(f"Validating module: {module_path}")

        # Check if path exists
        if not os.path.exists(module_path):
            self.errors.append(f"Module path does not exist: {module_path}")
            return False

        # Determine if it's a file or directory module
        is_directory = os.path.isdir(module_path)

        if is_directory:
            return self._validate_directory_module(module_path)
        else:
            return self._validate_file_module(module_path)

    def _validate_directory_module(self, module_path: str) -> bool:
        """Validate directory module"""
        print("  Type: Directory module")

        # Check for main.py or __init__.py
        main_file = os.path.join(module_path, "main.py")
        init_file = os.path.join(module_path, "__init__.py")

        if not os.path.exists(main_file) and not os.path.exists(init_file):
            self.errors.append("Directory module must have main.py or __init__.py")
            return False

        # Extract and validate manifest
        manifest = self._extract_manifest(module_path, is_directory=True)
        if not manifest:
            return False

        # Validate module structure
        return self._validate_module_structure(module_path, manifest, is_directory=True)

    def _validate_file_module(self, module_path: str) -> bool:
        """Validate single file module"""
        print("  Type: File module")

        if not module_path.endswith('.py'):
            self.errors.append("File module must be a Python file (.py)")
            return False

        # Extract and validate manifest
        manifest = self._extract_manifest(module_path, is_directory=False)
        if not manifest:
            return False

        return True

    def _extract_manifest(self, module_path: str, is_directory: bool) -> Optional[Dict]:
        """Extract manifest from module"""
        try:
            if is_directory:
                # Try main.py first, then separate manifest.json
                main_file = os.path.join(module_path, "main.py")
                manifest_json_file = os.path.join(module_path, "package.json")

                if os.path.exists(main_file):
                    manifest = self._extract_from_file(main_file)
                    if manifest:
                        return manifest

                if os.path.exists(manifest_json_file):
                    with open(manifest_json_file, 'r', encoding='utf-8') as f:
                        return json.load(f)

                self.errors.append("No manifest found in main.py or package.json")
            else:
                manifest = self._extract_from_file(module_path)
                if manifest:
                    return manifest
                else:
                    self.errors.append("No manifest found in module file")

        except Exception as e:
            self.errors.append(f"Error extracting manifest: {e}")

        return None

    def _extract_from_file(self, file_path: str) -> Optional[Dict]:
        """Extract manifest from Python file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Look for embedded manifest
            start_marker = 'MODULE_MANIFEST_START'
            end_marker = 'MODULE_MANIFEST_END'

            start_idx = content.find(start_marker)
            if start_idx == -1:
                return None

            start_idx += len(start_marker)
            end_idx = content.find(end_marker, start_idx)
            if end_idx == -1:
                return None

            manifest_json = content[start_idx:end_idx].strip()
            return json.loads(manifest_json)

        except Exception:
            return None

    def _validate_module_structure(self, module_path: str, manifest: Dict, is_directory: bool) -> bool:
        """Validate module structure and manifest"""
        print("  Validating manifest...")

        # Check required fields
        for field in NGITPackageSpec.REQUIRED_FIELDS:
            if field not in manifest:
                self.errors.append(f"Missing required field: {field}")

        # Validate field values
        if 'name' in manifest:
            name = manifest['name']
            if not name or not isinstance(name, str):
                self.errors.append("Module name must be a non-empty string")
            elif not name.replace('_', '').replace('-', '').isalnum():
                self.warnings.append("Module name should contain only alphanumeric characters, underscores, and hyphens")

        if 'version' in manifest:
            version = manifest['version']
            if not isinstance(version, str) or not version:
                self.errors.append("Version must be a non-empty string")

        if 'main_class' in manifest:
            main_class = manifest['main_class']
            if not isinstance(main_class, str) or not main_class:
                self.errors.append("Main class must be a non-empty string")

        # Validate dependencies
        if 'dependencies' in manifest:
            deps = manifest['dependencies']
            if not isinstance(deps, list):
                self.errors.append("Dependencies must be a list")
            else:
                for dep in deps:
                    if not isinstance(dep, str):
                        self.errors.append(f"Invalid dependency: {dep} (must be string)")

        # For directory modules, check if main class exists
        if is_directory and 'main_class' in manifest:
            entry_file = os.path.join(module_path, manifest.get('entry_point', 'main.py'))
            if not self._check_main_class_exists(entry_file, manifest['main_class']):
                self.errors.append(f"Main class '{manifest['main_class']}' not found in entry point")

        # Test import (basic validation)
        if is_directory:
            if not self._test_module_import(module_path):
                self.warnings.append("Module has import issues - may not load correctly")

        return len(self.errors) == 0

    def _check_main_class_exists(self, entry_file: str, main_class: str) -> bool:
        """Check if main class exists in entry file"""
        try:
            with open(entry_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Simple check - look for class definition
            return f"class {main_class}" in content

        except Exception:
            return False

    def _test_module_import(self, module_path: str) -> bool:
        """Test if module can be imported without errors"""
        try:
            # Add module path to sys.path temporarily
            if module_path not in sys.path:
                sys.path.insert(0, module_path)

            # Try to import the module
            module_name = os.path.basename(module_path)
            spec = importlib.util.spec_from_file_location(f"test_{module_name}",
                                                         os.path.join(module_path, "main.py"))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                # Don't execute - just check if it can be loaded
                return True

        except Exception as e:
            print(f"    Import test failed: {e}")
            return False
        finally:
            # Clean up sys.path
            if module_path in sys.path:
                sys.path.remove(module_path)

        return False

    def create_package(self, module_path: str, output_path: Optional[str] = None) -> bool:
        """Create NGIT package from module"""
        print(f"Creating package from: {module_path}")

        # Validate module first
        if not self.validate_module(module_path):
            print("Validation failed:")
            for error in self.errors:
                print(f"  ERROR: {error}")
            return False

        if self.warnings:
            print("Validation warnings:")
            for warning in self.warnings:
                print(f"  WARNING: {warning}")

        # Determine output path
        if not output_path:
            module_name = os.path.basename(module_path.rstrip('/\\'))
            output_path = f"{module_name}{NGITPackageSpec.PACKAGE_EXT}"

        # Create package
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                print(f"  Building package in: {temp_dir}")

                # Copy module files
                module_temp_dir = os.path.join(temp_dir, "module")
                if os.path.isdir(module_path):
                    shutil.copytree(module_path, module_temp_dir)
                else:
                    os.makedirs(module_temp_dir)
                    shutil.copy2(module_path, os.path.join(module_temp_dir, os.path.basename(module_path)))

                # Create package manifest
                manifest = self._extract_manifest(module_path, os.path.isdir(module_path))
                package_manifest = self._create_package_manifest(manifest, module_path)

                # Write package manifest
                manifest_path = os.path.join(temp_dir, NGITPackageSpec.MANIFEST_FILE)
                with open(manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(package_manifest, f, indent=2)

                # Calculate checksums
                checksums = self._calculate_checksums(temp_dir)
                checksum_path = os.path.join(temp_dir, NGITPackageSpec.CHECKSUM_FILE)
                with open(checksum_path, 'w', encoding='utf-8') as f:
                    json.dump(checksums, f, indent=2)

                # Create package zip
                print(f"  Creating package: {output_path}")
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(temp_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arc_path = os.path.relpath(file_path, temp_dir)
                            zipf.write(file_path, arc_path)

                # Verify package
                if self._verify_package(output_path):
                    size = os.path.getsize(output_path) / (1024 * 1024)  # MB
                    print(f"  Package created successfully: {output_path}")
                    print(f"  Package size: {size:.2f} MB")
                    return True
                else:
                    print("  ERROR: Package verification failed")
                    return False

        except Exception as e:
            print(f"  ERROR: Failed to create package: {e}")
            return False

    def _create_package_manifest(self, module_manifest: Dict, module_path: str) -> Dict:
        """Create package manifest from module manifest"""
        package_manifest = {
            "format_version": "1.0",
            "created_at": datetime.now().isoformat(),
            "created_by": "NGIT Package Packer v1.0",
            "module": module_manifest
        }

        # Add optional fields with defaults
        for field, default in NGITPackageSpec.OPTIONAL_FIELDS.items():
            if field not in package_manifest["module"]:
                package_manifest["module"][field] = default

        # Set menu_text to name if not provided
        if not package_manifest["module"]["menu_text"]:
            package_manifest["module"]["menu_text"] = package_manifest["module"]["name"]

        return package_manifest

    def _calculate_checksums(self, directory: str) -> Dict[str, str]:
        """Calculate SHA256 checksums for all files"""
        checksums = {}

        for root, dirs, files in os.walk(directory):
            for file in files:
                if file == NGITPackageSpec.CHECKSUM_FILE:
                    continue  # Skip checksum file itself

                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, directory)
                # Convert to forward slashes for consistent zip paths
                rel_path = rel_path.replace(os.sep, '/')

                try:
                    with open(file_path, 'rb') as f:
                        file_hash = hashlib.sha256(f.read()).hexdigest()
                        checksums[rel_path] = file_hash
                except Exception as e:
                    print(f"    Warning: Could not calculate checksum for {rel_path}: {e}")

        return checksums

    def _verify_package(self, package_path: str) -> bool:
        """Verify created package"""
        try:
            with zipfile.ZipFile(package_path, 'r') as zipf:
                # Check required files exist
                required_files = [
                    NGITPackageSpec.MANIFEST_FILE,
                    NGITPackageSpec.CHECKSUM_FILE,
                    "module/"
                ]

                file_list = zipf.namelist()
                for req_file in required_files:
                    if req_file.endswith('/'):
                        # Check directory exists
                        if not any(f.startswith(req_file) for f in file_list):
                            print(f"    Missing directory: {req_file}")
                            return False
                    else:
                        if req_file not in file_list:
                            print(f"    Missing file: {req_file}")
                            return False

                # Verify checksums
                checksum_data = {}
                with zipf.open(NGITPackageSpec.CHECKSUM_FILE) as f:
                    checksum_data = json.loads(f.read().decode('utf-8'))

                for file_path, expected_hash in checksum_data.items():
                    try:
                        # Convert forward slashes to backslashes for Windows compatibility
                        zip_path = file_path.replace('/', os.sep)
                        with zipf.open(zip_path) as f:
                            file_hash = hashlib.sha256(f.read()).hexdigest()
                            if file_hash != expected_hash:
                                print(f"    Checksum mismatch: {file_path}")
                                return False
                    except Exception as e:
                        # Try the original path as well
                        try:
                            with zipf.open(file_path) as f:
                                file_hash = hashlib.sha256(f.read()).hexdigest()
                                if file_hash != expected_hash:
                                    print(f"    Checksum mismatch: {file_path}")
                                    return False
                        except Exception as e2:
                            print(f"    Could not verify checksum for {file_path}: {e}")
                            return False

                return True

        except Exception as e:
            print(f"    Package verification error: {e}")
            return False


class PackageInspector:
    """Inspect NGIT packages"""

    @staticmethod
    def get_package_info(package_path: str) -> Dict:
        """Get information about a package"""
        try:
            with zipfile.ZipFile(package_path, 'r') as zipf:
                # Read manifest
                with zipf.open(NGITPackageSpec.MANIFEST_FILE) as f:
                    manifest = json.loads(f.read().decode('utf-8'))

                # Get file list
                files = zipf.namelist()

                # Calculate package size
                size = os.path.getsize(package_path)

                return {
                    "manifest": manifest,
                    "file_count": len(files),
                    "size_bytes": size,
                    "size_mb": round(size / (1024 * 1024), 2),
                    "files": files
                }

        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def extract_package(package_path: str, output_path: Optional[str] = None) -> bool:
        """Extract package contents"""
        try:
            if not output_path:
                output_path = os.path.splitext(package_path)[0] + "_extracted"

            print(f"Extracting package to: {output_path}")

            with zipfile.ZipFile(package_path, 'r') as zipf:
                zipf.extractall(output_path)

            print(f"Package extracted successfully to: {output_path}")
            return True

        except Exception as e:
            print(f"Extraction failed: {e}")
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="NGIT Package Packer - Desktop Organizer Module Packaging Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create package from directory module
  python ngit_package_packer.py create modules/my_module

  # Create package with specific output path
  python ngit_package_packer.py create modules/my_module my_module.ngitpac

  # Validate module before packaging
  python ngit_package_packer.py validate modules/my_module

  # Get package information
  python ngit_package_packer.py info my_module.ngitpac

  # Extract package contents
  python ngit_package_packer.py extract my_module.ngitpac
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create package from module')
    create_parser.add_argument('module_path', help='Path to module (file or directory)')
    create_parser.add_argument('output_path', nargs='?', help='Output package path')

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate module')
    validate_parser.add_argument('module_path', help='Path to module (file or directory)')

    # Info command
    info_parser = subparsers.add_parser('info', help='Get package information')
    info_parser.add_argument('package_path', help='Path to .ngitpac package')

    # Extract command
    extract_parser = subparsers.add_parser('extract', help='Extract package contents')
    extract_parser.add_argument('package_path', help='Path to .ngitpac package')
    extract_parser.add_argument('output_path', nargs='?', help='Output directory')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Execute command
    if args.command == 'create':
        creator = PackageCreator()
        success = creator.create_package(args.module_path, args.output_path)
        return 0 if success else 1

    elif args.command == 'validate':
        creator = PackageCreator()
        success = creator.validate_module(args.module_path)
        if success:
            print("SUCCESS: Module validation passed")
            if creator.warnings:
                print("Warnings:")
                for warning in creator.warnings:
                    print(f"  - {warning}")
        else:
            print("FAILED: Module validation failed:")
            for error in creator.errors:
                print(f"  - {error}")
        return 0 if success else 1

    elif args.command == 'info':
        info = PackageInspector.get_package_info(args.package_path)
        if 'error' in info:
            print(f"Error: {info['error']}")
            return 1

        manifest = info['manifest']
        module = manifest.get('module', {})

        print(f"Package Information: {args.package_path}")
        print("=" * 50)
        print(f"Name: {module.get('name', 'Unknown')}")
        print(f"Version: {module.get('version', 'Unknown')}")
        print(f"Description: {module.get('description', 'No description')}")
        print(f"Author: {module.get('author', 'Unknown')}")
        print(f"Category: {module.get('category', 'Unknown')}")
        print(f"Main Class: {module.get('main_class', 'Unknown')}")
        print(f"Dependencies: {len(module.get('dependencies', []))} packages")
        print(f"Package Size: {info['size_mb']} MB")
        print(f"File Count: {info['file_count']}")
        print(f"Created: {manifest.get('created_at', 'Unknown')}")

        if module.get('dependencies'):
            print("\nDependencies:")
            for dep in module.get('dependencies', []):
                print(f"  - {dep}")

        return 0

    elif args.command == 'extract':
        success = PackageInspector.extract_package(args.package_path, args.output_path)
        return 0 if success else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())