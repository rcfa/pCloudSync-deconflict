# pCloudSync-deconflict

A tool to find and resolve duplicate files created by pCloud sync conflicts.

## Overview

When pCloud encounters sync conflicts (e.g., when the same file is modified on multiple devices), it creates duplicate files with " [conflicted]" in the filename. This tool helps you:

- Find all conflicted file pairs
- Compare them to determine if they're identical
- Safely remove identical duplicates
- Track different files for manual review

## Features

- **Smart Comparison**: Uses SHA256 hashing to reliably detect identical files
- **Safe Deletion**: Offers dry-run mode, confirmation prompts, or auto-delete options
- **Cloud-Aware**: Automatically skips cloud storage and network mounts for better performance
- **Unicode Support**: Handles files with special characters, emojis, and international text
- **Progress Tracking**: Real-time progress indicator with file/directory counts
- **Persistent Tracking**: Maintains a JSON log of conflicts across multiple runs

## Installation

### From Source
```bash
chmod +x pCloudSync-deconflict.py
./pCloudSync-deconflict.py --help
```

### Building Standalone Executable
```bash
make                     # Build universal binary (default)
make build-universal     # Same as above - works on Intel & Apple Silicon
make build-macos         # Native build for current architecture only
make package             # Create distribution package with universal binary
```

## Usage

### Basic Usage
```bash
# Scan current directory (non-recursive)
./pCloudSync-deconflict.py .

# Recursive scan with confirmation prompts
./pCloudSync-deconflict.py -r ~/Documents

# Auto-delete identical files
./pCloudSync-deconflict.py -r --auto-delete ~/Documents

# Dry run to preview what would be deleted
./pCloudSync-deconflict.py -r --dry-run ~/Documents
```

### Advanced Options
```bash
# Include external drives but exclude cloud storage
./pCloudSync-deconflict.py -r --include-local-mounts ~/

# Scan everything including network/cloud storage
./pCloudSync-deconflict.py -r --cross-device ~/

# Disable progress indicator
./pCloudSync-deconflict.py -r --no-progress ~/Documents

# Use byte-by-byte comparison instead of hashing
./pCloudSync-deconflict.py -r -m byte ~/Documents

# Save conflict list to custom location
./pCloudSync-deconflict.py -r -o ~/Desktop/conflicts.json ~/Documents
```

## How It Works

1. **Scanning**: Searches for files with " [conflicted]" in the name
2. **Pairing**: Matches each conflicted file with its original
3. **Comparison**: Compares file sizes and content (via SHA256 hash)
4. **Action**: 
   - Identical files: Can be deleted (with confirmation)
   - Different files: Logged to JSON file for manual review

## Safety Features

- Never deletes original files, only conflicted copies
- Requires confirmation before deletion (unless using --auto-delete)
- Dry-run mode shows what would be deleted without taking action
- Detailed logging of all operations
- Skips system-protected directories automatically

## Conflict Tracking

The tool maintains a `conflicted_files_to_review.json` file that:
- Accumulates conflicts across multiple runs
- Tracks which conflicts have been resolved
- Includes file sizes, timestamps, and hashes
- Helps you systematically review all sync conflicts

## Requirements

- macOS 10.12 or later
- Python 3.6+ (if running from source)
- No requirements for standalone executable

## Building from Source

Requirements:
- Python 3.6+
- PyInstaller (installed automatically by Makefile)

```bash
# Install dependencies
pip install pyinstaller

# Build executable
make build-macos
```

## License

MIT License - See LICENSE file for details

## Author

Developed to solve pCloud sync conflicts on macOS.