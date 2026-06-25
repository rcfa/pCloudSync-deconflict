# pCloudSync-deconflict 🚀

**A powerful tool to find and interactively resolve duplicate files created by pCloud sync conflicts.**

[![Latest Release](https://img.shields.io/github/v/release/rcfa/pCloudSync-deconflict)](https://github.com/rcfa/pCloudSync-deconflict/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

When pCloud encounters sync conflicts (e.g., when the same file is modified on multiple devices), it creates duplicate files with " [conflicted]" or " (conflicted)" in the filename. This tool helps you:

- **🔍 Find all conflicted file pairs** automatically
- **⚡ Compare them intelligently** using SHA256 hashing or byte comparison
- **🤖 Auto-delete identical duplicates** safely
- **🎯 Resolve real conflicts interactively** with rich metadata and diff display
- **📊 Track conflicts persistently** across multiple runs with JSON logging

## ✨ Key Features

### 🎯 Interactive Conflict Resolution (NEW in v1.1.0)
- **Rich metadata display**: File sizes, modification times, full paths
- **Colored diff viewer**: Beautiful syntax-highlighted diffs for text files
- **Smart file detection**: Automatically detects text vs binary files
- **Multiple resolution options**: Keep original, keep conflicted, skip, or view files
- **Safe preview mode**: `--resolve --dry-run` to preview all conflicts first

### 🚀 Intelligent Processing
- **Smart comparison**: SHA256 hashing with size optimization for performance
- **Perfect workflows**: Combine `--auto-delete` + `--resolve` for complete automation
- **Cloud-aware scanning**: Automatically skips cloud storage and network mounts
- **Unicode support**: Handles international characters, emojis, and special symbols
- **Files without extensions**: Perfect handling of scripts, configs, makefiles

### 🛡️ Safety & Reliability
- **Multiple safety modes**: Dry-run, confirmation prompts, or auto-delete
- **Never touches originals**: Only processes `[conflicted]` and `(conflicted)` files
- **Comprehensive testing**: 17+ test scenarios covering all edge cases
- **Progress tracking**: Real-time progress with smooth spinner animation
- **Error handling**: Graceful handling of permissions and edge cases

## 🚀 Quick Start

### Installation

#### Option 1: Download Pre-built Binary (Recommended)
```bash
# Download the latest universal binary (works on Intel & Apple Silicon)
curl -L -o pCloudSync-deconflict https://github.com/rcfa/pCloudSync-deconflict/releases/latest/download/pCloudSync-deconflict
chmod +x pCloudSync-deconflict
./pCloudSync-deconflict --version
```

#### Option 2: Run from Source
```bash
git clone https://github.com/rcfa/pCloudSync-deconflict.git
cd pCloudSync-deconflict
chmod +x pCloudSync-deconflict.py
./pCloudSync-deconflict.py --help
```

#### Option 3: System-wide Installation
```bash
git clone https://github.com/rcfa/pCloudSync-deconflict.git
cd pCloudSync-deconflict
make install    # Installs to /usr/local/bin
```

### Basic Usage

```bash
# Check version
./pCloudSync-deconflict --version

# Preview all conflicts without making changes
./pCloudSync-deconflict -r --resolve --dry-run ~/Documents

# Perfect workflow: auto-delete identical, resolve conflicts interactively
./pCloudSync-deconflict -r --auto-delete --resolve ~/Documents

# Just clean up identical files automatically
./pCloudSync-deconflict -r --auto-delete ~/Documents
```

## 📋 Complete Command Reference

### Core Commands
```bash
# Basic scanning
./pCloudSync-deconflict /path/to/scan           # Non-recursive scan
./pCloudSync-deconflict -r /path/to/scan        # Recursive scan

# Multiple directories (v1.2.0+)
./pCloudSync-deconflict path1 path2 path3       # Scan multiple directories
./pCloudSync-deconflict -r ~/Documents ~/Desktop # Recursive multi-directory scan

# Conflict resolution
./pCloudSync-deconflict -r --resolve /path      # Interactive resolution
./pCloudSync-deconflict -r --resolve --dry-run  # Preview conflicts

# Automatic cleanup
./pCloudSync-deconflict -r --auto-delete /path  # Auto-delete identical files
./pCloudSync-deconflict -r --dry-run /path      # Preview all actions
```

### Advanced Options
```bash
# Comparison methods
-m hash     # SHA256 hash comparison (default, faster)
-m byte     # Byte-by-byte comparison (slower, thorough)

# Device boundaries
--cross-device          # Include network/cloud storage (slower)
--include-local-mounts  # Include external drives, exclude cloud

# Output and progress
-o custom.json          # Custom output file for conflict tracking
--no-progress          # Disable progress indicator
-v, --verbose          # Show detailed comparison results

# Perfect combinations
--auto-delete --resolve              # Auto-clean identical, resolve different
--auto-delete --resolve --dry-run    # Preview complete workflow
```

### Orphaned Conflicted Files (NEW in v1.4.0)
An **orphan** is a `[conflicted]`/`(conflicted)` file whose original is missing — so it
forms no pair. Earlier versions silently ignored these; they are now detected, logged,
and can be cleaned up:
```bash
# Interactive: --resolve now handles BOTH conflicts and orphans in one pass
--resolve                 # Resolve conflicts AND orphans interactively
--resolve-conflicts       # Only conflicts (pairs with different content)
--resolve-orphans         # Only orphans

# Non-interactive orphan actions (mutually exclusive)
--normalize-orphans       # Rename orphans, stripping the conflict marker
--nuke-orphans            # Delete orphans outright
```
With no orphan option, orphans are **reported and logged** but left untouched.
When normalizing, if the stripped name is already taken the file is treated as a real
conflict (re-paired and compared) instead of being overwritten.

### Conflicted Directories
A *directory* whose name carries a conflict marker is **detected and reported loudly**
but never acted on automatically — it may be an app bundle, a nested tree, or something
else that needs case-by-case handling. The scan still descends into it, so conflicted
files nested inside are found normally.

## 🎯 Workflows & Use Cases

### 📅 Daily pCloud Cleanup
```bash
# Preview what needs attention
./pCloudSync-deconflict -r --auto-delete --resolve --dry-run ~/

# Execute the cleanup and resolution
./pCloudSync-deconflict -r --auto-delete --resolve ~/
```

### 🔍 Careful Conflict Review
```bash
# First, see all conflicts with rich details
./pCloudSync-deconflict -r --resolve --dry-run ~/Documents

# Then resolve them interactively
./pCloudSync-deconflict -r --resolve ~/Documents
```

### 🧹 Quick Identical File Cleanup
```bash
# Just remove obvious duplicates
./pCloudSync-deconflict -r --auto-delete ~/Documents
```

### 🌍 International Files & Special Cases
```bash
# Handle Unicode filenames, files without extensions
./pCloudSync-deconflict -r --resolve ~/Desktop
```

### 📁 Multiple Directory Cleanup (v1.2.0+)
```bash
# Clean up common sync conflict areas in one run
./pCloudSync-deconflict -r --auto-delete ~/Documents ~/Desktop ~/Downloads

# Preview conflicts across all project directories
./pCloudSync-deconflict -r --dry-run ~/Projects/web ~/Projects/mobile ~/Projects/backend
```

## 🧪 Testing & Validation

The tool includes a comprehensive test suite:

```bash
# Run all tests (safe - uses dry-run mode)
./run-tests.sh

# Test specific scenarios
./pCloudSync-deconflict test-data/unicode-files -r --resolve --dry-run
./pCloudSync-deconflict test-data/root-level --auto-delete --dry-run

# Recreate test data
cd test-data && ./create-test-files.sh
```

**Test coverage includes:**
- ✅ 17 different conflict scenarios
- ✅ Unicode filenames (café, 咖啡, emojis)
- ✅ Files with and without extensions
- ✅ Multi-level directory nesting
- ✅ Binary and text files
- ✅ Large files (1000+ lines)
- ✅ Edge cases (empty files, orphaned conflicts)

## 🔧 How It Works

### 1. **Discovery Phase**
- Recursively scans directories for files containing " [conflicted]" or " (conflicted)"
- Matches each conflicted file with its original counterpart
- Skips cloud storage mounts automatically for better performance

### 2. **Analysis Phase**
- Compares file sizes first (quick elimination)
- Uses SHA256 hashing for content comparison (default)
- Detects text vs binary files automatically

### 3. **Resolution Phase**
- **Identical files**: Auto-deleted (with `--auto-delete`) or confirmed
- **Different files**: Interactive resolution (with `--resolve`) or logged to JSON
- **Orphans** (conflicted file, no original): normalized/nuked/resolved interactively, or logged
- **Conflicted directories**: reported loudly for manual handling, never auto-modified

### 4. **Interactive Resolution**
When using `--resolve`, for each conflict you can:
- **View rich metadata**: Sizes, modification times, paths
- **See colored diffs**: For text files with syntax highlighting
- **Choose resolution**: Keep original, keep conflicted, skip, or view files
- **Preview safely**: Use `--dry-run` to see all conflicts first

## 📊 Conflict Tracking

The tool maintains a `conflicted_files_to_review.json` file that:
- **Lives in a fixed location** — `~/Library/Application Support/pCloudSync-deconflict/` by default, so tracking is independent of the working directory you launch from (override with `-o`)
- **Accumulates conflicts** across multiple runs
- **Tracks resolution status** (active vs resolved)
- **Includes rich metadata**: Sizes, timestamps, hashes, reasons
- **Validates existence** of old conflicts on each run
- **Provides history** for systematic conflict management

## 🛡️ Safety Features

- ✅ **Never deletes original files** - only processes `[conflicted]` copies
- ✅ **Multiple confirmation levels** - dry-run, prompts, or auto modes
- ✅ **Comprehensive logging** - detailed JSON tracking of all operations
- ✅ **Permission handling** - gracefully skips protected directories
- ✅ **Unicode safety** - proper handling of international filenames
- ✅ **Atomic operations** - safe file renaming and deletion

## 🔧 Building from Source

### Requirements
- **macOS**: 10.12 or later
- **Python**: 3.6+ (for source execution)
- **PyInstaller**: Automatically installed by Makefile

### Build Commands
```bash
# Build universal binary (recommended)
make                    # Same as 'make build-universal'
make build-universal    # Works on Intel & Apple Silicon

# Build for current architecture only
make build-macos

# Create distribution package
make package

# Install system-wide
make install           # Installs to /usr/local/bin
make uninstall         # Removes from /usr/local/bin

# Clean build artifacts
make clean
```

## 📈 Version History

- **v1.4.0** (Latest): Detect and handle **orphaned** conflicted files (no original) via `--resolve`/`--resolve-orphans`/`--normalize-orphans`/`--nuke-orphans`; loudly report **conflicted directories**; orphans and directories are tracked in the JSON. Fixes a bug where orphan-only runs exited without doing anything
- **v1.3.0**: Conflict-tracking file now lives in a fixed location (`~/Library/Application Support/pCloudSync-deconflict/`) so it no longer depends on the working directory the tool is launched from
- **v1.2.1**: Added support for `(conflicted)` pattern in addition to `[conflicted]`
- **v1.2.0**: Support for processing multiple directories in a single run
- **v1.1.1**: Added `--version` option for standard CLI behavior
- **v1.1.0**: Major update with interactive conflict resolution and comprehensive test suite
- **v1.0.0**: Initial stable release with auto-delete and JSON tracking

[View all releases →](https://github.com/rcfa/pCloudSync-deconflict/releases)

## 🤝 Contributing

Found a bug or have a feature request? 

1. **Check existing issues**: [GitHub Issues](https://github.com/rcfa/pCloudSync-deconflict/issues)
2. **Run the test suite**: `./run-tests.sh` to verify functionality
3. **Create detailed reports**: Include version (`--version`) and test results

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details.

## ✨ Author

Developed to solve real-world pCloud sync conflicts on macOS with a focus on safety, usability, and comprehensive conflict resolution.

---

**🎯 Ready to clean up your pCloud conflicts?** 

[Download the latest release](https://github.com/rcfa/pCloudSync-deconflict/releases/latest) and start with:
```bash
./pCloudSync-deconflict -r --auto-delete --resolve --dry-run ~/
```