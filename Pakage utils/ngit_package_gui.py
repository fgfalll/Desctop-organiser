#!/usr/bin/env python3
"""
NGIT Package GUI - Simple GUI for NGIT Package Packer

This application provides a user-friendly interface for creating,
validating, and managing NGIT packages for Desktop Organizer modules.

Requirements:
- Python 3.6+
- tkinter (usually included with Python)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import threading
import json
import subprocess
from pathlib import Path

# Import the package packer
try:
    from ngit_package_packer import (
        PackageCreator, PackageInspector, NGITPackageSpec,
        PackageValidationError
    )
    PACKAGE_PACKER_AVAILABLE = True
    print("SUCCESS: Found ngit_package_packer.py")
except ImportError:
    PACKAGE_PACKER_AVAILABLE = False
    print("ERROR: ngit_package_packer.py not found!")


class NGITPackageGUI:
    """Main GUI application for NGIT Package Packer"""

    def __init__(self, root):
        self.root = root
        self.root.title("NGIT Package Packer")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)

        # Variables
        self.module_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.current_package = None

        # Style configuration
        self.setup_styles()

        # Create GUI
        self.create_widgets()

        # Center window
        self.center_window()

        if not PACKAGE_PACKER_AVAILABLE:
            self.show_error("Package Packer Not Available",
                          "ngit_package_packer.py not found. Please ensure it's in the same directory.")
            root.quit()

    def setup_styles(self):
        """Setup styles for the application"""
        style = ttk.Style()

        # Configure styles
        style.configure("Title.TLabel", font=("Arial", 12, "bold"))
        style.configure("Heading.TLabel", font=("Arial", 10, "bold"))
        style.configure("Success.TLabel", foreground="green")
        style.configure("Error.TLabel", foreground="red")
        style.configure("Warning.TLabel", foreground="orange")

    def center_window(self):
        """Center the window on the screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def create_widgets(self):
        """Create all GUI widgets"""

        # Create main container with padding
        main_container = ttk.Frame(self.root, padding="10")
        main_container.pack(fill=tk.BOTH, expand=True)

        # Title
        title_label = ttk.Label(main_container, text="NGIT Package Packer",
                               style="Title.TLabel")
        title_label.pack(pady=(0, 10))

        # Create notebook for tabs
        self.notebook = ttk.Notebook(main_container)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Create tabs
        self.create_tab = self.create_create_tab()
        self.validate_tab = self.create_validate_tab()
        self.info_tab = self.create_info_tab()

        # Status bar
        self.status_frame = ttk.Frame(main_container)
        self.status_frame.pack(fill=tk.X)

        self.status_label = ttk.Label(self.status_frame, text="Ready", relief=tk.SUNKEN)
        self.status_label.pack(fill=tk.X, side=tk.LEFT)

        self.progress_bar = ttk.Progressbar(self.status_frame, mode='indeterminate',
                                           length=100)
        # Don't pack progress bar initially

        # Menu bar
        self.create_menu()

    def create_menu(self):
        """Create menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Exit", command=self.root.quit)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        help_menu.add_command(label="Package System Documentation",
                            command=self.show_documentation)

    def create_create_tab(self):
        """Create package creation tab"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Create Package")

        # Module selection
        ttk.Label(frame, text="Select Module:", style="Heading.TLabel").pack(anchor=tk.W, pady=(10, 5))

        module_frame = ttk.Frame(frame)
        module_frame.pack(fill=tk.X, pady=(0, 10))

        module_entry = ttk.Entry(module_frame, textvariable=self.module_path, width=50)
        module_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(module_frame, text="Browse...",
                  command=self.browse_module).pack(side=tk.RIGHT)

        # Output path
        ttk.Label(frame, text="Output Path (optional):", style="Heading.TLabel").pack(anchor=tk.W, pady=(10, 5))

        output_frame = ttk.Frame(frame)
        output_frame.pack(fill=tk.X, pady=(0, 10))

        output_entry = ttk.Entry(output_frame, textvariable=self.output_path, width=50)
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(output_frame, text="Browse...",
                  command=self.browse_output).pack(side=tk.RIGHT)

        # Package type info
        info_frame = ttk.LabelFrame(frame, text="Information", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))

        info_text = """• Select a Python file (.py) or directory containing a module
• Directory modules should have main.py or __init__.py
• Manifest can be embedded in main.py or in manifest.json
• Output will be saved as .ngitpac file
• Package will include all necessary files and checksums"""

        ttk.Label(info_frame, text=info_text, justify=tk.LEFT).pack()

        # Action buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(button_frame, text="Validate Module",
                  command=self.validate_module).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(button_frame, text="Create Package",
                  command=self.create_package, style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(button_frame, text="Clear",
                  command=self.clear_fields).pack(side=tk.RIGHT)

        return frame

    def create_validate_tab(self):
        """Create package validation tab"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Validate Package")

        # Package selection
        ttk.Label(frame, text="Select Package (.ngitpac):", style="Heading.TLabel").pack(anchor=tk.W, pady=(10, 5))

        package_frame = ttk.Frame(frame)
        package_frame.pack(fill=tk.X, pady=(0, 10))

        self.package_path = tk.StringVar()
        package_entry = ttk.Entry(package_frame, textvariable=self.package_path, width=50)
        package_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(package_frame, text="Browse...",
                  command=self.browse_package).pack(side=tk.RIGHT)

        # Action buttons
        ttk.Button(frame, text="Validate Package",
                  command=self.validate_package).pack(pady=(0, 10))

        # Results area
        ttk.Label(frame, text="Validation Results:", style="Heading.TLabel").pack(anchor=tk.W)

        self.validation_text = scrolledtext.ScrolledText(frame, height=15, wrap=tk.WORD)
        self.validation_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        return frame

    def create_info_tab(self):
        """Create package info tab"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Package Info")

        # Package selection
        ttk.Label(frame, text="Select Package (.ngitpac):", style="Heading.TLabel").pack(anchor=tk.W, pady=(10, 5))

        info_package_frame = ttk.Frame(frame)
        info_package_frame.pack(fill=tk.X, pady=(0, 10))

        self.info_package_path = tk.StringVar()
        info_package_entry = ttk.Entry(info_package_frame, textvariable=self.info_package_path, width=50)
        info_package_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(info_package_frame, text="Browse...",
                  command=self.browse_info_package).pack(side=tk.RIGHT)

        # Action buttons
        ttk.Button(frame, text="Get Package Info",
                  command=self.get_package_info).pack(pady=(0, 10))

        # Package info display
        self.info_frame = ttk.LabelFrame(frame, text="Package Information", padding="10")
        self.info_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Create info labels
        self.info_labels = {}
        info_fields = [
            ("name", "Name:"),
            ("version", "Version:"),
            ("description", "Description:"),
            ("author", "Author:"),
            ("category", "Category:"),
            ("main_class", "Main Class:"),
            ("dependencies", "Dependencies:"),
            ("size_mb", "Size:"),
            ("file_count", "File Count:"),
            ("created_at", "Created:")
        ]

        for field, label_text in info_fields:
            frame = ttk.Frame(self.info_frame)
            frame.pack(fill=tk.X, pady=2)

            ttk.Label(frame, text=label_text, width=15, anchor=tk.W).pack(side=tk.LEFT)

            label = ttk.Label(frame, text="-", anchor=tk.W)
            label.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.info_labels[field] = label

        return frame

    def browse_module(self):
        """Browse for module file or directory"""
        # Create a simple choice dialog using Tkinter
        from tkinter import simpledialog

        class ModuleTypeDialog(simpledialog.Dialog):
            def body(self, master):
                self.title("Select Module Type")
                ttk.Label(master, text="What type of module do you want to package?").pack(pady=10)

                self.choice_var = tk.StringVar(value="directory")

                # Radio button for directory module
                dir_radio = ttk.Radiobutton(
                    master,
                    text="📁 Directory Module (Recommended)\nIncludes ALL files in the directory\nPerfect for petroleum_launcher",
                    variable=self.choice_var,
                    value="directory"
                )
                dir_radio.pack(pady=5)

                # Radio button for file module
                file_radio = ttk.Radiobutton(
                    master,
                    text="📄 Single File Module\nIncludes ONLY the selected .py file\nFor simple single-file modules",
                    variable=self.choice_var,
                    value="file"
                )
                file_radio.pack(pady=5)

                return dir_radio  # Return the first radio button for initial focus

            def apply(self):
                self.result = self.choice_var.get()

        # Show the dialog
        dialog = ModuleTypeDialog(self.root)
        choice = dialog.result

        if choice is None:  # Cancelled
            return

        path = None
        if choice == "directory":
            # Directory selection
            path = filedialog.askdirectory(
                title="Select Module Directory - Choose the FOLDER containing your module files",
                initialdir="C:/Users/Nafta/Desktop/test/Desctop-organiser"
            )
            if path:
                messagebox.showinfo("✅ Directory Selected",
                    f"Selected: {path}\n\n"
                    f"This will include ALL files in the directory.\n"
                    f"Perfect for modules with multiple files like petroleum_launcher.")
        else:
            # File selection
            path = filedialog.askopenfilename(
                title="Select Module File - Choose a single .py file",
                filetypes=[("Python Files", "*.py"), ("All Files", "*.*")],
                initialdir="C:/Users/Nafta/Desktop/test/Desctop-organiser"
            )
            if path:
                messagebox.showinfo("📄 File Selected",
                    f"Selected: {path}\n\n"
                    f"This will include ONLY this single file.\n"
                    f"Use this for simple single-file modules.")

        if path:
            self.module_path.set(path)
            # Auto-generate output path
            if not self.output_path.get():
                if os.path.isfile(path):
                    base_name = os.path.splitext(os.path.basename(path))[0]
                else:
                    base_name = os.path.basename(path.rstrip('/\\'))
                self.output_path.set(f"{base_name}{NGITPackageSpec.PACKAGE_EXT}")

            # Update the display to show what was selected
            if os.path.isdir(path):
                print(f"✅ DIRECTORY SELECTED: {path}")
                print(f"   This will include ALL files in the directory")
            else:
                print(f"📄 FILE SELECTED: {path}")
                print(f"   This will include ONLY this single file")

    def browse_output(self):
        """Browse for output file location"""
        path = filedialog.asksaveasfilename(
            title="Save Package As",
            defaultextension=".ngitpac",
            filetypes=[("NGIT Packages", "*.ngitpac"), ("All Files", "*.*")]
        )
        if path:
            self.output_path.set(path)

    def browse_package(self):
        """Browse for package file"""
        path = filedialog.askopenfilename(
            title="Select NGIT Package",
            filetypes=[("NGIT Packages", "*.ngitpac"), ("All Files", "*.*")]
        )
        if path:
            self.package_path.set(path)

    def browse_info_package(self):
        """Browse for package file for info"""
        path = filedialog.askopenfilename(
            title="Select NGIT Package",
            filetypes=[("NGIT Packages", "*.ngitpac"), ("All Files", "*.*")]
        )
        if path:
            self.info_package_path.set(path)

    def clear_fields(self):
        """Clear all input fields"""
        self.module_path.set("")
        self.output_path.set("")
        self.current_package = None

    def validate_module(self):
        """Validate selected module"""
        module_path = self.module_path.get()
        if not module_path:
            self.show_error("No Module Selected", "Please select a module file or directory first.")
            return

        self.start_operation("Validating module...")

        def validate():
            try:
                creator = PackageCreator()
                success = creator.validate_module(module_path)

                # Show results in validation tab
                self.notebook.select(self.validate_tab)
                self.validation_text.delete(1.0, tk.END)

                if success:
                    self.validation_text.insert(tk.END, "SUCCESS: VALIDATION SUCCESSFUL\n\n", "success")
                    self.validation_text.insert(tk.END, f"Module: {module_path}\n")
                    self.validation_text.insert(tk.END, "Type: Directory module\n" if os.path.isdir(module_path) else "Type: File module\n")

                    if creator.warnings:
                        self.validation_text.insert(tk.END, "\nWARNING: WARNINGS:\n", "warning")
                        for warning in creator.warnings:
                            self.validation_text.insert(tk.END, f"  - {warning}\n")
                else:
                    self.validation_text.insert(tk.END, "ERROR: VALIDATION FAILED\n\n", "error")
                    self.validation_text.insert(tk.END, f"Module: {module_path}\n\n")
                    self.validation_text.insert(tk.END, "ERRORS:\n", "error")
                    for error in creator.errors:
                        self.validation_text.insert(tk.END, f"  - {error}\n")

                # Configure text tags
                self.validation_text.tag_config("success", foreground="green")
                self.validation_text.tag_config("error", foreground="red")
                self.validation_text.tag_config("warning", foreground="orange")

            except Exception as e:
                self.show_error("Validation Error", f"Error during validation: {str(e)}")
            finally:
                self.end_operation()

        # Run in thread to avoid GUI freezing
        threading.Thread(target=validate, daemon=True).start()

    def create_package(self):
        """Create package from selected module"""
        module_path = self.module_path.get()
        if not module_path:
            self.show_error("No Module Selected", "Please select a module file or directory first.")
            return

        output_path = self.output_path.get()
        if not output_path:
            # Generate default output path
            if os.path.isfile(module_path):
                base_name = os.path.splitext(os.path.basename(module_path))[0]
            else:
                base_name = os.path.basename(module_path)
            output_path = f"{base_name}{NGITPackageSpec.PACKAGE_EXT}"

        self.start_operation("Creating package...")

        def create():
            try:
                creator = PackageCreator()
                success = creator.create_package(module_path, output_path)

                if success:
                    self.current_package = output_path
                    self.show_info("Package Created Successfully",
                                 f"Package created:\n{output_path}\n\n"
                                 f"You can now distribute this file to users.")
                else:
                    error_msg = "Package creation failed."
                    if creator.errors:
                        error_msg += "\n\nErrors:\n" + "\n".join(f"  - {e}" for e in creator.errors)
                    if creator.warnings:
                        error_msg += "\n\nWarnings:\n" + "\n".join(f"  - {w}" for w in creator.warnings)
                    self.show_error("Package Creation Failed", error_msg)

            except Exception as e:
                self.show_error("Package Creation Error", f"Error during package creation: {str(e)}")
            finally:
                self.end_operation()

        # Run in thread to avoid GUI freezing
        threading.Thread(target=create, daemon=True).start()

    def validate_package(self):
        """Validate selected package"""
        package_path = self.package_path.get()
        if not package_path:
            self.show_error("No Package Selected", "Please select a .ngitpac package file first.")
            return

        if not package_path.endswith(NGITPackageSpec.PACKAGE_EXT):
            self.show_error("Invalid Package", f"Selected file is not a .ngitpac package.")
            return

        self.start_operation("Validating package...")

        def validate():
            try:
                inspector = PackageInspector()
                package_info = inspector.get_package_info(package_path)

                self.validation_text.delete(1.0, tk.END)

                if 'error' in package_info:
                    self.validation_text.insert(tk.END, "ERROR: PACKAGE VALIDATION FAILED\n\n", "error")
                    self.validation_text.insert(tk.END, f"Error: {package_info['error']}\n")
                else:
                    self.validation_text.insert(tk.END, "SUCCESS: PACKAGE VALIDATION SUCCESSFUL\n\n", "success")

                    # Get module info from manifest (nested structure)
                    manifest = package_info.get('manifest', {})
                    module_info = manifest.get('module', {})

                    self.validation_text.insert(tk.END, "Package Information:\n")
                    self.validation_text.insert(tk.END, f"  Name: {module_info.get('name', 'Unknown')}\n")
                    self.validation_text.insert(tk.END, f"  Version: {module_info.get('version', 'Unknown')}\n")
                    self.validation_text.insert(tk.END, f"  Description: {module_info.get('description', 'No description')}\n")
                    self.validation_text.insert(tk.END, f"  Author: {module_info.get('author', 'Unknown')}\n")
                    self.validation_text.insert(tk.END, f"  Main Class: {module_info.get('main_class', 'Unknown')}\n")
                    self.validation_text.insert(tk.END, f"  Dependencies: {len(module_info.get('dependencies', []))} packages\n")
                    self.validation_text.insert(tk.END, f"  File Count: {package_info.get('file_count', 0)}\n")
                    self.validation_text.insert(tk.END, f"  Size: {package_info.get('size_mb', 0):.2f} MB\n")

                # Configure text tags
                self.validation_text.tag_config("success", foreground="green")
                self.validation_text.tag_config("error", foreground="red")

            except Exception as e:
                self.show_error("Package Validation Error", f"Error during package validation: {str(e)}")
            finally:
                self.end_operation()

        # Run in thread to avoid GUI freezing
        threading.Thread(target=validate, daemon=True).start()

    def get_package_info(self):
        """Get and display package information"""
        package_path = self.info_package_path.get()
        if not package_path:
            self.show_error("No Package Selected", "Please select a .ngitpac package file first.")
            return

        if not package_path.endswith(NGITPackageSpec.PACKAGE_EXT):
            self.show_error("Invalid Package", f"Selected file is not a .ngitpac package.")
            return

        self.start_operation("Getting package info...")

        def get_info():
            try:
                inspector = PackageInspector()
                package_info = inspector.get_package_info(package_path)

                if 'error' in package_info:
                    self.show_error("Package Error", f"Error reading package: {package_info['error']}")
                    return

                # Get module info from manifest (nested structure)
                manifest = package_info.get('manifest', {})
                module_info = manifest.get('module', {})

                # Update labels
                self.info_labels["name"].config(text=module_info.get('name', 'Unknown'))
                self.info_labels["version"].config(text=module_info.get('version', 'Unknown'))
                self.info_labels["description"].config(text=module_info.get('description', 'No description')[:100] + "..." if len(module_info.get('description', '')) > 100 else module_info.get('description', 'No description'))
                self.info_labels["author"].config(text=module_info.get('author', 'Unknown'))
                self.info_labels["category"].config(text=module_info.get('category', 'Unknown'))
                self.info_labels["main_class"].config(text=module_info.get('main_class', 'Unknown'))

                deps = module_info.get('dependencies', [])
                if deps:
                    self.info_labels["dependencies"].config(text=f"{len(deps)} packages")
                    # Show dependencies in tooltip if many
                    if len(deps) > 3:
                        dep_text = ", ".join(deps[:3]) + f" and {len(deps) - 3} more..."
                    else:
                        dep_text = ", ".join(deps)
                    self.info_labels["dependencies"].config(text=dep_text)
                else:
                    self.info_labels["dependencies"].config(text="None")

                self.info_labels["size_mb"].config(text=f"{package_info.get('size_mb', 0):.2f} MB")
                self.info_labels["file_count"].config(text=str(package_info.get('file_count', 0)))
                self.info_labels["created_at"].config(text=package_info.get('manifest', {}).get('created_at', 'Unknown'))

            except Exception as e:
                self.show_error("Package Info Error", f"Error getting package info: {str(e)}")
            finally:
                self.end_operation()

        # Run in thread to avoid GUI freezing
        threading.Thread(target=get_info, daemon=True).start()

    def start_operation(self, message):
        """Start an operation with progress indication"""
        self.status_label.config(text=message)
        self.progress_bar.pack(side=tk.RIGHT, padx=(5, 0))
        self.progress_bar.start(10)
        self.root.update_idletasks()

    def end_operation(self):
        """End operation and hide progress bar"""
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.status_label.config(text="Ready")
        self.root.update_idletasks()

    def show_error(self, title, message):
        """Show error message"""
        messagebox.showerror(title, message)

    def show_info(self, title, message):
        """Show info message"""
        messagebox.showinfo(title, message)

    def show_about(self):
        """Show about dialog"""
        about_text = """NGIT Package GUI
Version 1.0

A user-friendly interface for creating NGIT packages
for Desktop Organizer modules.

Features:
• Create packages from files or directories
• Validate module structure
• Inspect package information
• Built-in integrity verification

Created for Desktop Organizer
Package System
"""
        messagebox.showinfo("About NGIT Package GUI", about_text)

    def show_documentation(self):
        """Show documentation"""
        doc_text = """NGIT Package System Documentation

The NGIT Package System provides a complete solution for
creating, distributing, and installing Desktop Organizer
modules as .ngitpac packages.

Quick Start:
1. Select a module file (.py) or directory
2. Click 'Validate Module' to check structure
3. Click 'Create Package' to generate .ngitpac file
4. Distribute the package to users

Module Requirements:
• Embedded manifest in main.py OR manifest.json
• Required fields: name, version, description, main_class
• Optional: dependencies, author, category, permissions

For detailed documentation, see:
NGIT_PACKAGE_SYSTEM.md

Command Line Usage:
python ngit_package_packer.py create <module_path>
python ngit_package_packer.py validate <module_path>
python ngit_package_packer.py info <package_path>
"""

        # Create documentation window
        doc_window = tk.Toplevel(self.root)
        doc_window.title("NGIT Package System Documentation")
        doc_window.geometry("600x500")

        text_widget = scrolledtext.ScrolledText(doc_window, wrap=tk.WORD)
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_widget.insert(1.0, doc_text)
        text_widget.config(state=tk.DISABLED)

        # Center window
        doc_window.update_idletasks()
        width = doc_window.winfo_width()
        height = doc_window.winfo_height()
        x = (doc_window.winfo_screenwidth() // 2) - (width // 2)
        y = (doc_window.winfo_screenheight() // 2) - (height // 2)
        doc_window.geometry(f"{width}x{height}+{x}+{y}")


def main():
    """Main entry point"""
    if not PACKAGE_PACKER_AVAILABLE:
        print("Error: ngit_package_packer.py not found!")
        print("Please ensure ngit_package_packer.py is in the same directory.")
        sys.exit(1)

    root = tk.Tk()
    app = NGITPackageGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()