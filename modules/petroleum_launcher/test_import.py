"""Test script to verify that the refactored petroleum launcher package works correctly"""

import sys
import os
from pathlib import Path

# Add the parent directory to the path so we can import the package
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

def test_imports():
    """Test that all modules can be imported successfully"""
    print("Testing petroleum launcher package imports...")

    try:
        # Test package import
        import petroleum_launcher
        print("✅ Package import successful")

        # Test main widget import
        from petroleum_launcher import PetroleumLauncherWidget
        print("✅ Main widget import successful")

        # Test core components
        from petroleum_launcher import (
            PetroleumProgramConfigManager,
            WindowsUtils,
            WindowManager,
            ProgramInfo,
            Workflow,
            AutomationAction
        )
        print("✅ Core components import successful")

        # Test instantiation of key classes
        config_manager = PetroleumProgramConfigManager()
        print("✅ ConfigManager instantiation successful")

        windows_utils = WindowsUtils()
        print("✅ WindowsUtils instantiation successful")

        window_manager = WindowManager()
        print("✅ WindowManager instantiation successful")

        # Test data models
        program_info = ProgramInfo(
            name="test",
            display_name="Test Program",
            executable_path="C:\\test.exe",
            version="1.0",
            install_path="C:\\test"
        )
        print("✅ ProgramInfo creation successful")

        print("\n🎉 All tests passed! The refactored package is working correctly.")
        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_package_info():
    """Test package metadata"""
    try:
        import petroleum_launcher

        print(f"\n📦 Package Information:")
        print(f"   Version: {petroleum_launcher.__version__}")
        print(f"   Author: {petroleum_launcher.__author__}")
        print(f"   Description: {petroleum_launcher.__description__}")

        return True
    except Exception as e:
        print(f"❌ Package info test failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Petroleum Launcher Package Test")
    print("=" * 60)

    success = test_imports()
    if success:
        test_package_info()

    print("=" * 60)
    if success:
        print("✅ All tests completed successfully!")
        sys.exit(0)
    else:
        print("❌ Some tests failed!")
        sys.exit(1)