#!/usr/bin/env python3
"""
Main entry point for the Secure Backup System
"""
import sys
import os

# Đảm bảo chúng ta có thể import từ src
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Bây giờ import
try:
    from src.cli import BackupCLI
except ImportError:
    print("Cannot import modules. Make sure you're in the right directory.")
    print("Current directory:", current_dir)
    sys.exit(1)

def main():
    """Main function"""
    cli = BackupCLI()
    cli.run()

if __name__ == "__main__":
    main()