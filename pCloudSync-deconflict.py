#!/usr/bin/env python3
"""
DeConflict - A tool to find and compare conflicted files from pCloud sync services
"""

import os
import sys
import argparse
import hashlib
import filecmp
import json
import time
import subprocess
import shutil
import unicodedata
import mimetypes
import re
from pathlib import Path
from typing import List, Tuple, Dict, Set
from datetime import datetime

def get_file_hash(file_path: Path, chunk_size: int = 8192) -> str:
    """Calculate SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()

def get_mount_points() -> Set[str]:
    """Get all mount points on the system, particularly FUSE/cloud storage mounts."""
    mount_points = set()
    try:
        # Use mount command to get all mount points
        result = subprocess.run(['mount'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                # Parse mount output: "filesystem on /mount/point type fstype (options)"
                if ' on ' in line and ' type ' in line:
                    parts = line.split(' on ')
                    if len(parts) >= 2:
                        mount_path = parts[1].split(' type ')[0].strip()
                        # Check for cloud storage indicators
                        if any(indicator in line.lower() for indicator in ['fuse', 'osxfuse', 'macfuse', 'sshfs', 'webdav', 'smb', 'afp', 'nfs']):
                            mount_points.add(mount_path)
    except Exception:
        pass
    
    # Also check common cloud storage locations
    cloud_patterns = [
        '*/Library/CloudStorage/*',
        '*/Library/Mobile Documents/*',  # iCloud Drive
        '*/Dropbox*',
        '*/Google Drive*',
        '*/OneDrive*',
        '*/Box Sync*',
        '*/pCloud Drive*',
        '*/ShellFish/*',  # ShellFish SFTP/SSH mounts
    ]
    
    home = Path.home()
    for pattern in cloud_patterns:
        for cloud_path in home.glob(pattern.replace('*/', '')):
            if cloud_path.is_dir():
                mount_points.add(str(cloud_path))
    
    return mount_points

def is_under_cloud_storage(path: Path, mount_points: Set[str]) -> bool:
    """Check if a path is under any cloud storage mount point."""
    path_str = str(path.resolve())
    
    # Quick check for common parent directories
    if "/Library/Mobile Documents" in path_str:
        return True
    if "/Library/CloudStorage" in path_str:
        return True
    
    # Check against detected mount points
    for mount in mount_points:
        if path_str.startswith(mount):
            return True
    return False

# Matches the markers pCloud injects into conflicted file/directory names:
#   " [conflicted]"  " [conflicted 2]"  " (conflicted)"  " (conflicted 3)"  ...
# pCloud escalates to a numbered form ([conflicted N]) when several conflicts
# collide on the same name, so N (any positive integer) is optional.
CONFLICT_MARKER_RE = re.compile(r' (?:\[conflicted(?: \d+)?\]|\(conflicted(?: \d+)?\))')


def is_conflict_name(name: str) -> bool:
    """True if the name carries a pCloud conflict marker (numbered or not)."""
    return CONFLICT_MARKER_RE.search(name) is not None


def strip_conflict_marker(name: str) -> str:
    """Return the name with every conflict marker removed (the 'normalized' name)."""
    return CONFLICT_MARKER_RE.sub("", name)


def find_conflicted_pairs(directory: str, recursive: bool = True, show_progress: bool = True, cross_device: bool = False, include_local_mounts: bool = False) -> Tuple[List[Tuple[Path, Path]], List[Path], List[Path]]:
    """Scan a directory for conflict artifacts.

    Returns a 3-tuple ``(pairs, orphans, conflicted_dirs)``:
      * pairs           - (original, conflicted) file pairs where both exist
      * orphans         - conflicted files whose original is missing
      * conflicted_dirs - directories whose name carries a conflict marker
    All three are gathered in a single tree walk.
    """
    conflicted_pairs = []
    orphans = []
    conflicted_dirs = []
    skipped_paths = []
    
    path = Path(directory)
    
    # Get terminal width for proper line clearing
    term_width = shutil.get_terminal_size(fallback=(80, 24)).columns
    
    # Progress tracking
    spinner = ['-', '\\', '|', '/']
    spinner_idx = 0
    last_spinner_update = time.time()
    files_processed = 0
    dirs_processed = 0
    last_update = time.time()
    current_dir = ""
    
    # Get cloud storage mount points if needed
    cloud_mounts = get_mount_points() if not cross_device else set()
    
    def get_display_width(text):
        """Calculate actual display width of text, accounting for Unicode characters."""
        width = 0
        for char in text:
            if unicodedata.east_asian_width(char) in ('F', 'W'):
                width += 2  # Full-width characters
            else:
                width += 1
        return width
    
    def truncate_to_width(text, max_width):
        """Truncate text to fit within max_width display columns."""
        if get_display_width(text) <= max_width:
            return text
        
        truncated = ""
        width = 0
        for char in text:
            char_width = 2 if unicodedata.east_asian_width(char) in ('F', 'W') else 1
            if width + char_width + 3 > max_width:  # Leave room for "..."
                return truncated + "..."
            truncated += char
            width += char_width
        return truncated
    
    def update_progress(current_path):
        nonlocal spinner_idx, last_spinner_update
        if show_progress:
            # Update spinner character only every 0.125 seconds
            current_time = time.time()
            if current_time - last_spinner_update >= 0.125:
                spinner_idx = (spinner_idx + 1) % 4
                last_spinner_update = current_time
            
            # Put counts first for steady display
            prefix = f"{spinner[spinner_idx]} ({dirs_processed} dirs, {files_processed} files) Scanning: "
            path_str = str(current_path)
            
            # Calculate available width for path
            prefix_width = get_display_width(prefix)
            suffix = "..."
            suffix_width = get_display_width(suffix)
            available_width = term_width - prefix_width - suffix_width - 2
            
            # Truncate path if needed
            path_str = truncate_to_width(path_str, available_width)
            
            progress_msg = f"{prefix}{path_str}{suffix}"
            
            # Clear entire line and redraw
            sys.stdout.write(f"\r{' ' * term_width}\r{progress_msg}")
            sys.stdout.flush()
    
    # Get the device ID of the starting directory for boundary checking
    try:
        start_device = os.stat(directory).st_dev
    except (PermissionError, OSError):
        start_device = None
    
    if recursive:
        # Use os.walk for better control and progress updates
        for root, dirs, files in os.walk(directory):
            dirs_processed += 1
            current_dir = Path(root)
            
            # Check device boundary and cloud storage
            if not cross_device:
                current_path = Path(root)
                
                # Check if this is cloud storage
                if is_under_cloud_storage(current_path, cloud_mounts):
                    dirs[:] = []  # Skip subdirectories
                    if show_progress:
                        # Clear the progress line first
                        sys.stdout.write(f"\r{' ' * term_width}\r")
                        sys.stdout.flush()
                        time.sleep(0.01)  # Brief pause to ensure terminal catches up
                        print(f"Skipping cloud storage: {root}")
                    continue
                
                # Check device boundary (skip if include_local_mounts is True)
                if not include_local_mounts and start_device is not None:
                    try:
                        current_device = os.stat(root).st_dev
                        if current_device != start_device:
                            # Skip this directory and its subdirectories
                            dirs[:] = []  # This tells os.walk to not recurse into subdirs
                            if show_progress:
                                # Clear the progress line first
                                sys.stdout.write(f"\r{' ' * term_width}\r")
                                sys.stdout.flush()
                                time.sleep(0.01)  # Brief pause to ensure terminal catches up
                                print(f"Skipping mount point: {root}")
                            continue
                    except (PermissionError, OSError):
                        pass
            
            update_progress(current_dir)

            # Flag any conflict-marked subdirectories (still descend into them so
            # conflicted files nested inside are found too).
            for dirname in dirs:
                if is_conflict_name(dirname):
                    conflicted_dirs.append(current_dir / dirname)

            # Process files in this directory
            for filename in files:
                files_processed += 1
                update_progress(current_dir)
                
                if is_conflict_name(filename):
                    try:
                        conflicted_file = current_dir / filename
                        original_name = strip_conflict_marker(filename)
                        original_file = current_dir / original_name

                        # Pair if the original exists, otherwise it's an orphan.
                        try:
                            if original_file.exists() and original_file.is_file():
                                conflicted_pairs.append((original_file, conflicted_file))
                            else:
                                orphans.append(conflicted_file)
                        except (PermissionError, OSError) as e:
                            skipped_paths.append((str(original_file), str(e)))
                    except (PermissionError, OSError) as e:
                        skipped_paths.append((str(conflicted_file), str(e)))
    else:
        # Non-recursive: just scan the directory
        try:
            for item in path.iterdir():
                files_processed += 1
                update_progress(path)
                
                if not is_conflict_name(item.name):
                    continue

                if item.is_dir():
                    conflicted_dirs.append(item)
                elif item.is_file():
                    conflicted_file = item
                    original_name = strip_conflict_marker(item.name)
                    original_file = item.parent / original_name

                    if original_file.exists() and original_file.is_file():
                        conflicted_pairs.append((original_file, conflicted_file))
                    else:
                        orphans.append(conflicted_file)
        except (PermissionError, OSError) as e:
            skipped_paths.append((str(path), str(e)))
    
    # Clear progress line
    if show_progress:
        sys.stdout.write("\r" + " " * term_width + "\r")
        sys.stdout.flush()
    
    if skipped_paths:
        # Clear progress line before printing
        if show_progress:
            sys.stdout.write(f"\r{' ' * term_width}\r")
            sys.stdout.flush()
        print(f"Skipped {len(skipped_paths)} path(s) due to permission errors")
        if len(skipped_paths) <= 5:
            for path, error in skipped_paths:
                print(f"  - {path}: {error}")
        else:
            print(f"  (showing first 5 of {len(skipped_paths)})")
            for path, error in skipped_paths[:5]:
                print(f"  - {path}: {error}")
    
    return conflicted_pairs, orphans, conflicted_dirs

def compare_files(file1: Path, file2: Path, method: str = "hash") -> Dict[str, any]:
    """Compare two files and return comparison results."""
    result = {
        "original": str(file1),
        "conflicted": str(file2),
        "identical": False,
        "method": method,
        "original_size": file1.stat().st_size,
        "conflicted_size": file2.stat().st_size,
        "original_mtime": datetime.fromtimestamp(file1.stat().st_mtime).isoformat(),
        "conflicted_mtime": datetime.fromtimestamp(file2.stat().st_mtime).isoformat(),
    }
    
    # Quick size check
    if result["original_size"] != result["conflicted_size"]:
        result["identical"] = False
        result["reason"] = "Different file sizes"
        return result
    
    # Compare based on method
    if method == "hash":
        original_hash = get_file_hash(file1)
        conflicted_hash = get_file_hash(file2)
        result["original_hash"] = original_hash
        result["conflicted_hash"] = conflicted_hash
        result["identical"] = original_hash == conflicted_hash
        if not result["identical"]:
            result["reason"] = "Different content (hash mismatch)"
    elif method == "byte":
        result["identical"] = filecmp.cmp(str(file1), str(file2), shallow=False)
        if not result["identical"]:
            result["reason"] = "Different content (byte comparison)"
    
    if result["identical"]:
        result["reason"] = "Files are identical"
    
    return result

def confirm_deletion(file_path: Path) -> bool:
    """Ask user for confirmation before deleting a file."""
    response = input(f"Delete '{file_path.name}'? [y/N]: ").strip().lower()
    return response in ['y', 'yes']

def default_output_file() -> str:
    """Return the default conflict-tracking file path.

    Anchored in the user's macOS Application Support directory so the tool
    always reads and writes the *same* tracking file regardless of the
    current working directory it happens to be launched from.
    """
    app_dir = Path.home() / "Library" / "Application Support" / "pCloudSync-deconflict"
    return str(app_dir / "conflicted_files_to_review.json")

def load_existing_tracking(output_file: str) -> Tuple[Dict[str, Dict], Dict[str, Dict], Dict[str, Dict]]:
    """Load existing tracking data, returning (conflicts, orphans, dirs) dicts.

    Each dict is keyed by the field that uniquely identifies an entry so new
    findings can be merged in: conflicts by 'original', orphans and directories
    by their on-disk path.
    """
    if not os.path.exists(output_file):
        return {}, {}, {}

    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Key by the *conflicted* path: it is unique, whereas several numbered
        # conflicts ([conflicted], [conflicted 2], ...) can share one original.
        conflicts = {c['conflicted']: c for c in data.get('conflicts', data.get('files', []))}
        orphans = {o['conflicted']: o for o in data.get('orphans', [])}
        dirs = {d['path']: d for d in data.get('conflicted_directories', [])}
        return conflicts, orphans, dirs
    except Exception as e:
        print(f"Warning: Could not load existing tracking file: {e}")
        return {}, {}, {}

def validate_conflict_still_exists(conflict: Dict) -> bool:
    """Check if a conflict pair still exists on disk."""
    try:
        original = Path(conflict['original'])
        conflicted = Path(conflict['conflicted'])
        return original.exists() and conflicted.exists()
    except Exception:
        return False

def save_tracking(different_files: List[Dict], orphan_records: List[Dict] = None,
                  dir_records: List[Dict] = None, output_file: str = None):
    """Merge new findings into the tracking JSON and persist all three categories.

    Returns ``(output_file, active_conflicts, resolved_conflicts,
    active_orphans, active_dirs)``. Each category tracks ``still_exists`` so
    items handled (deleted/renamed) in this run are recorded as resolved.
    """
    orphan_records = orphan_records or []
    dir_records = dir_records or []
    if output_file is None:
        output_file = default_output_file()
    # Ensure the destination directory exists (covers both the default
    # Application Support location and any custom -o path the user gives).
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    existing_conflicts, existing_orphans, existing_dirs = load_existing_tracking(output_file)

    # --- Conflicts (pairs) -------------------------------------------------
    # Keyed by conflicted path so multiple numbered conflicts of the same
    # original are each tracked instead of overwriting one another.
    for conflict in different_files:
        conflict['last_seen'] = now
        conflict['still_exists'] = True
        existing_conflicts[conflict['conflicted']] = conflict
    new_conflict_keys = {c['conflicted'] for c in different_files}
    for key, conflict in existing_conflicts.items():
        if key not in new_conflict_keys:
            if validate_conflict_still_exists(conflict):
                conflict['still_exists'] = True
                conflict['last_checked'] = now
            else:
                conflict['still_exists'] = False
                conflict['resolved_at'] = now

    # --- Orphans -----------------------------------------------------------
    # still_exists reflects the disk *now*, so anything nuked/normalized this
    # run is correctly recorded as resolved.
    for orphan in orphan_records:
        key = orphan['conflicted']
        orphan['last_seen'] = now
        orphan['still_exists'] = Path(key).exists()
        if not orphan['still_exists']:
            orphan['resolved_at'] = now
        existing_orphans[key] = orphan
    new_orphan_keys = {o['conflicted'] for o in orphan_records}
    for key, orphan in existing_orphans.items():
        if key not in new_orphan_keys:
            if Path(key).exists():
                orphan['still_exists'] = True
                orphan['last_checked'] = now
            else:
                orphan['still_exists'] = False
                orphan.setdefault('resolved_at', now)

    # --- Conflicted directories (report-only, never acted on) --------------
    for entry in dir_records:
        key = entry['path']
        entry['last_seen'] = now
        entry['still_exists'] = Path(key).exists()
        existing_dirs[key] = entry
    new_dir_keys = {d['path'] for d in dir_records}
    for key, entry in existing_dirs.items():
        if key not in new_dir_keys:
            if Path(key).exists():
                entry['still_exists'] = True
                entry['last_checked'] = now
            else:
                entry['still_exists'] = False
                entry.setdefault('resolved_at', now)

    active_conflicts = [c for c in existing_conflicts.values() if c.get('still_exists', True)]
    active_orphans = [o for o in existing_orphans.values() if o.get('still_exists', True)]
    active_dirs = [d for d in existing_dirs.values() if d.get('still_exists', True)]
    all_conflicts = list(existing_conflicts.values())
    all_orphans = list(existing_orphans.values())
    all_dirs = list(existing_dirs.values())

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "last_updated": now,
            "total_active_conflicts": len(active_conflicts),
            "total_resolved_conflicts": len(all_conflicts) - len(active_conflicts),
            "conflicts": all_conflicts,
            "total_active_orphans": len(active_orphans),
            "total_resolved_orphans": len(all_orphans) - len(active_orphans),
            "orphans": all_orphans,
            "total_active_conflicted_dirs": len(active_dirs),
            "total_resolved_conflicted_dirs": len(all_dirs) - len(active_dirs),
            "conflicted_directories": all_dirs,
        }, f, indent=2, ensure_ascii=False, sort_keys=True)

    return (output_file, len(active_conflicts),
            len(all_conflicts) - len(active_conflicts),
            len(active_orphans), len(active_dirs))

def format_file_info(file_path: Path) -> str:
    """Format file metadata for display."""
    try:
        stat = file_path.stat()
        size = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        
        # Human readable size
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{size / (1024 * 1024 * 1024):.1f} GB"
        
        return f"  Size: {size_str}\n  Modified: {mtime}\n  Path: {file_path}"
    except Exception as e:
        return f"  Error reading file info: {e}\n  Path: {file_path}"

def is_text_file(file_path: Path) -> bool:
    """Determine if a file is likely a text file."""
    try:
        # Check MIME type first
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type and mime_type.startswith('text/'):
            return True
        
        # Check file extension
        text_extensions = {'.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.yaml', '.yml', 
                          '.md', '.rst', '.conf', '.cfg', '.ini', '.log', '.csv', '.tsv'}
        if file_path.suffix.lower() in text_extensions:
            return True
        
        # Try to read first few bytes to check for binary content
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
            # Check for null bytes (common in binary files)
            if b'\x00' in chunk:
                return False
            # Try to decode as UTF-8
            try:
                chunk.decode('utf-8')
                return True
            except UnicodeDecodeError:
                return False
    except Exception:
        return False

def show_text_diff(original: Path, conflicted: Path) -> bool:
    """Show a unified diff between two text files. Returns True if diff was shown."""
    try:
        with open(original, 'r', encoding='utf-8') as f1, open(conflicted, 'r', encoding='utf-8') as f2:
            lines1 = f1.readlines()
            lines2 = f2.readlines()
        
        import difflib
        diff = list(difflib.unified_diff(
            lines1, lines2, 
            fromfile=f"a/{original.name}", 
            tofile=f"b/{conflicted.name}",
            lineterm=''
        ))
        
        if diff:
            print("\n📄 File Content Differences:")
            print("-" * 60)
            for line in diff[:50]:  # Limit to first 50 lines of diff
                if line.startswith('+++') or line.startswith('---'):
                    print(f"\033[1m{line}\033[0m")  # Bold
                elif line.startswith('+'):
                    print(f"\033[32m{line}\033[0m")  # Green
                elif line.startswith('-'):
                    print(f"\033[31m{line}\033[0m")  # Red
                elif line.startswith('@@'):
                    print(f"\033[36m{line}\033[0m")  # Cyan
                else:
                    print(line)
            
            if len(diff) > 50:
                print(f"\n... (showing first 50 lines of {len(diff)} total diff lines)")
            print("-" * 60)
            return True
    except Exception as e:
        print(f"Could not show diff: {e}")
        return False
    return False

def resolve_conflict_interactive(original: Path, conflicted: Path) -> str:
    """Interactively resolve a conflict between two files. Returns action to take."""
    print(f"\n🔀 CONFLICT: {original.name}")
    print("=" * 60)
    
    print("\n📁 ORIGINAL FILE:")
    print(format_file_info(original))
    
    print("\n📁 CONFLICTED FILE:")
    print(format_file_info(conflicted))
    
    # Show diff for text files
    if is_text_file(original) and is_text_file(conflicted):
        show_text_diff(original, conflicted)
    else:
        print(f"\n💾 Binary files - use 'open' command to view content")
    
    while True:
        print(f"\nChoose action:")
        print(f"  [o] Keep ORIGINAL   (delete {conflicted.name})")
        print(f"  [c] Keep CONFLICTED (replace {original.name} with {conflicted.name})")
        print(f"  [d] Show diff again")
        print(f"  [v] Open both files in default application")
        print(f"  [s] Skip this conflict")
        print(f"  [q] Quit conflict resolution")
        
        choice = input("Your choice [o/c/d/v/s/q]: ").strip().lower()
        
        if choice in ['o', 'original']:
            return 'keep_original'
        elif choice in ['c', 'conflicted']:
            return 'keep_conflicted'
        elif choice in ['d', 'diff']:
            if is_text_file(original) and is_text_file(conflicted):
                show_text_diff(original, conflicted)
            else:
                print("Cannot show diff for binary files")
        elif choice in ['v', 'view', 'open']:
            try:
                subprocess.run(['open', str(original)], check=False)
                subprocess.run(['open', str(conflicted)], check=False)
                print("Opened both files in default application")
            except Exception as e:
                print(f"Could not open files: {e}")
        elif choice in ['s', 'skip']:
            return 'skip'
        elif choice in ['q', 'quit']:
            return 'quit'
        else:
            print("Invalid choice. Please enter o, c, d, v, s, or q.")

def resolve_conflicts_dry_run(different_files: List[Dict]) -> int:
    """Show what conflict resolution actions would be taken without doing them."""
    if not different_files:
        return 0
    
    print(f"\n🔧 CONFLICT RESOLUTION PREVIEW (DRY RUN)")
    print(f"Found {len(different_files)} file(s) with different content that would need resolution.")
    print("Showing what actions would be available for each conflict.\n")
    
    for i, conflict in enumerate(different_files, 1):
        original = Path(conflict['original'])
        conflicted = Path(conflict['conflicted'])
        
        # Skip if files no longer exist
        if not original.exists() or not conflicted.exists():
            print(f"⚠️ Conflict {i}/{len(different_files)}: One or both files no longer exist")
            continue
        
        print(f"\n📍 Conflict {i}/{len(different_files)}")
        print(f"🔀 CONFLICT: {original.name}")
        print("=" * 60)
        
        print("\n📁 ORIGINAL FILE:")
        print(format_file_info(original))
        
        print("\n📁 CONFLICTED FILE:")
        print(format_file_info(conflicted))
        
        # Show diff for text files
        if is_text_file(original) and is_text_file(conflicted):
            show_text_diff(original, conflicted)
        else:
            print(f"\n💾 Binary files - content differs")
        
        print(f"\n🎯 Available actions in interactive mode:")
        print(f"   [o] Keep ORIGINAL   → Would delete {conflicted.name}")
        print(f"   [c] Keep CONFLICTED → Would replace {original.name} with {conflicted.name}")
        print(f"   [s] Skip this conflict")
        print(f"   [v] Open both files for comparison")
        print("=" * 60)
    
    print(f"\n💡 To actually resolve conflicts, run without --dry-run:")
    print(f"   ./pCloudSync-deconflict.py [path] -r --resolve")
    
    return len(different_files)

def resolve_conflicts(different_files: List[Dict]) -> int:
    """Interactive conflict resolution for files with different content."""
    if not different_files:
        return 0
    
    print(f"\n🔧 CONFLICT RESOLUTION MODE")
    print(f"Found {len(different_files)} file(s) with different content that need resolution.")
    print("You can choose which version to keep for each conflict.\n")
    
    resolved_count = 0
    
    for i, conflict in enumerate(different_files, 1):
        original = Path(conflict['original'])
        conflicted = Path(conflict['conflicted'])
        
        # Skip if files no longer exist
        if not original.exists() or not conflicted.exists():
            print(f"Skipping conflict {i}/{len(different_files)}: One or both files no longer exist")
            continue
        
        print(f"\n📍 Conflict {i}/{len(different_files)}")
        
        action = resolve_conflict_interactive(original, conflicted)
        
        if action == 'keep_original':
            try:
                conflicted.unlink()
                print(f"✅ Deleted {conflicted.name} (kept original)")
                resolved_count += 1
            except Exception as e:
                print(f"❌ Error deleting {conflicted.name}: {e}")
        
        elif action == 'keep_conflicted':
            try:
                original.unlink()
                new_path = conflicted.parent / original.name
                conflicted.rename(new_path)
                print(f"✅ Replaced {original.name} with conflicted version")
                resolved_count += 1
            except Exception as e:
                print(f"❌ Error replacing {original.name}: {e}")
        
        elif action == 'skip':
            print(f"⏭️ Skipped {original.name}")
            continue
        
        elif action == 'quit':
            print(f"\n🛑 Exiting conflict resolution. Resolved {resolved_count} conflicts so far.")
            break
    
    return resolved_count

def build_orphan_record(orphan: Path) -> Dict:
    """Build a JSON-tracking record for an orphaned conflicted file."""
    record = {
        "conflicted": str(orphan),
        "normalized_target": str(orphan.parent / strip_conflict_marker(orphan.name)),
    }
    try:
        stat = orphan.stat()
        record["size"] = stat.st_size
        record["mtime"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
    except OSError:
        pass
    return record

def build_dir_record(directory: Path) -> Dict:
    """Build a JSON-tracking record for a conflicted directory."""
    return {
        "path": str(directory),
        "normalized_target": str(directory.parent / strip_conflict_marker(directory.name)),
    }

def resolve_orphan_interactive(orphan: Path) -> str:
    """Prompt for what to do with a single orphan. Returns the chosen action."""
    target = orphan.parent / strip_conflict_marker(orphan.name)
    collision = target.exists()

    print(f"\n🗑️  ORPHAN: {orphan.name}   (no original found)")
    print("=" * 60)
    print(format_file_info(orphan))

    while True:
        print(f"\nChoose action:")
        print(f"  [n] Nuke (delete {orphan.name})")
        if collision:
            print(f"  [r] Normalize → '{target.name}' EXISTS; will re-pair and compare")
        else:
            print(f"  [r] Normalize (rename → {target.name})")
        print(f"  [s] Skip this orphan")
        print(f"  [q] Quit orphan resolution")

        choice = input("Your choice [n/r/s/q]: ").strip().lower()
        if choice in ['n', 'nuke']:
            return 'nuke'
        elif choice in ['r', 'rename', 'normalize']:
            return 'normalize'
        elif choice in ['s', 'skip']:
            return 'skip'
        elif choice in ['q', 'quit']:
            return 'quit'
        else:
            print("Invalid choice. Please enter n, r, s, or q.")

def process_orphans(orphans: List[Path], mode: str, dry_run: bool, method: str) -> Tuple[Dict[str, int], List[Dict]]:
    """Act on orphaned conflicted files.

    mode is one of 'interactive', 'nuke', 'normalize', or None (report-only).
    Returns (tally, repaired_conflicts) where repaired_conflicts holds
    compare_files() results for orphans whose normalize target already existed
    and turned out to differ (so they get logged as real conflicts).
    """
    tally = {'nuked': 0, 'normalized': 0, 'skipped': 0, 'repaired': 0, 'errors': 0}
    repaired_conflicts = []
    if not orphans:
        return tally, repaired_conflicts

    print(f"\n🧹 ORPHANED CONFLICTED FILES ({len(orphans)} found)")
    if mode is None:
        print("   (report-only — re-run with --resolve-orphans, --nuke-orphans, "
              "or --normalize-orphans to act on these)")
        for orphan in orphans:
            print(f"   • {orphan}")
        tally['skipped'] = len(orphans)
        return tally, repaired_conflicts

    for i, orphan in enumerate(orphans, 1):
        if not orphan.exists():
            continue

        if mode == 'interactive':
            if dry_run:
                # Preview only — never block on input() during a dry run.
                target = orphan.parent / strip_conflict_marker(orphan.name)
                note = " (target exists → would re-pair)" if target.exists() else f" → {target.name}"
                print(f"\n🗑️  ORPHAN: {orphan.name}  "
                      f"(would prompt: [n]uke / [r]normalize{note} / [s]kip)")
                tally['skipped'] += 1
                continue
            action = resolve_orphan_interactive(orphan)
            if action == 'quit':
                print(f"\n🛑 Exiting orphan resolution.")
                break
        else:
            action = mode  # 'nuke' or 'normalize'
            print(f"\n[{i}/{len(orphans)}] {orphan}")

        if action == 'skip':
            tally['skipped'] += 1
            continue

        if action == 'nuke':
            if dry_run:
                print(f"  → Would nuke: {orphan}")
                tally['nuked'] += 1
            else:
                try:
                    orphan.unlink()
                    print(f"  🗑️  Nuked: {orphan}")
                    tally['nuked'] += 1
                except Exception as e:
                    print(f"  ❌ Error nuking {orphan.name}: {e}")
                    tally['errors'] += 1

        elif action == 'normalize':
            target = orphan.parent / strip_conflict_marker(orphan.name)
            if target.exists():
                # Target taken ⇒ this is really a pair. Re-pair and compare.
                tally['repaired'] += 1
                print(f"  ⚠️  '{target.name}' already exists — re-pairing as a conflict")
                try:
                    result = compare_files(target, orphan, method)
                    if result['identical']:
                        if dry_run:
                            print(f"  → Identical to existing; would delete orphan {orphan.name}")
                        else:
                            orphan.unlink()
                            print(f"  🗑️  Orphan identical to existing file; deleted {orphan.name}")
                    else:
                        print(f"  ✗ Differs from existing '{target.name}' — logged for review "
                              f"(use --resolve)")
                        repaired_conflicts.append(result)
                except Exception as e:
                    print(f"  ❌ Re-pair comparison failed: {e}")
                    tally['errors'] += 1
            else:
                if dry_run:
                    print(f"  → Would normalize: {orphan.name} → {target.name}")
                    tally['normalized'] += 1
                else:
                    try:
                        orphan.rename(target)
                        print(f"  ✅ Normalized: {orphan.name} → {target.name}")
                        tally['normalized'] += 1
                    except Exception as e:
                        print(f"  ❌ Error normalizing {orphan.name}: {e}")
                        tally['errors'] += 1

    return tally, repaired_conflicts

def report_conflicted_dirs(conflicted_dirs: List[Path]) -> None:
    """Print a loud, hard-to-miss warning about conflict-marked directories."""
    if not conflicted_dirs:
        return
    border = "!" * 70
    print("\n" + border)
    print(f"⚠️  ATTENTION: {len(conflicted_dirs)} CONFLICTED DIRECTORY(IES) FOUND")
    print("These are NOT handled automatically and require manual review.")
    print("A conflicted directory could be an app bundle, a nested file tree, or")
    print("something else entirely — each needs different, careful handling:")
    for directory in conflicted_dirs:
        print(f"   📁 {directory}")
    print(border)

def main():
    parser = argparse.ArgumentParser(
        description="Find and compare conflicted files from cloud sync services"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="pCloudSync-deconflict 1.4.1"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Path(s) to the directory/directories to scan"
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        default=False,
        help="Scan directories recursively (default: False)"
    )
    parser.add_argument(
        "-m", "--method",
        choices=["hash", "byte"],
        default="hash",
        help="Comparison method: 'hash' (SHA256) or 'byte' (byte-by-byte) (default: hash)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed output for all files"
    )
    parser.add_argument(
        "--show-identical",
        action="store_true",
        help="Also show files that are identical"
    )
    parser.add_argument(
        "--auto-delete",
        action="store_true",
        help="Automatically delete identical conflicted files without confirmation"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output file for list of different files "
             "(default: ~/Library/Application Support/pCloudSync-deconflict/conflicted_files_to_review.json)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress indicator during scanning"
    )
    parser.add_argument(
        "--cross-device",
        action="store_true",
        help="Cross device boundaries (scan network mounts, external drives, etc.)"
    )
    parser.add_argument(
        "--include-local-mounts",
        action="store_true",
        help="Include local physical drives while still excluding cloud/network storage"
    )
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="Interactively resolve BOTH conflicts (different content) and orphans"
    )
    parser.add_argument(
        "--resolve-conflicts",
        action="store_true",
        help="Interactively resolve only conflicts (pairs with different content)"
    )
    parser.add_argument(
        "--resolve-orphans",
        action="store_true",
        help="Interactively resolve only orphaned conflicted files (no original)"
    )
    parser.add_argument(
        "--nuke-orphans",
        action="store_true",
        help="Delete all orphaned conflicted files (no prompts)"
    )
    parser.add_argument(
        "--normalize-orphans",
        action="store_true",
        help="Rename all orphaned conflicted files, stripping the conflict marker"
    )

    args = parser.parse_args()

    # Determine conflict (pair) resolution and orphan handling modes.
    do_resolve_conflicts = args.resolve or args.resolve_conflicts

    orphan_actions = []
    if args.nuke_orphans:
        orphan_actions.append('nuke')
    if args.normalize_orphans:
        orphan_actions.append('normalize')
    if args.resolve or args.resolve_orphans:
        orphan_actions.append('interactive')
    if len(orphan_actions) > 1:
        print("Error: choose at most one orphan action "
              "(--nuke-orphans, --normalize-orphans, or interactive via "
              "--resolve/--resolve-orphans).", file=sys.stderr)
        sys.exit(1)
    orphan_mode = orphan_actions[0] if orphan_actions else None

    # Resolve the default tracking-file location once, independent of the
    # current working directory. An explicit -o always wins.
    if args.output is None:
        args.output = default_output_file()

    # Validate all paths first
    for path in args.paths:
        if not os.path.exists(path):
            print(f"Error: Path '{path}' does not exist", file=sys.stderr)
            sys.exit(1)
        
        if not os.path.isdir(path):
            print(f"Error: Path '{path}' is not a directory", file=sys.stderr)
            sys.exit(1)
    
    # Display scanning configuration
    if len(args.paths) == 1:
        print(f"Scanning {'recursively' if args.recursive else 'non-recursively'} in: {args.paths[0]}")
    else:
        print(f"Scanning {'recursively' if args.recursive else 'non-recursively'} in {len(args.paths)} directories:")
        for path in args.paths:
            print(f"  - {path}")
    print(f"Using comparison method: {args.method}")
    if not args.auto_delete and not args.dry_run:
        print("Will ask for confirmation before deleting identical files")
    print()
    
    # Accumulate results across all paths
    all_pairs = []
    all_orphans = []
    all_conflicted_dirs = []
    path_results = {}

    # Process each path
    for path_idx, path in enumerate(args.paths):
        if len(args.paths) > 1:
            print(f"\n{'='*60}")
            print(f"Processing directory {path_idx + 1}/{len(args.paths)}: {path}")
            print(f"{'='*60}\n")

        # Find conflict artifacts for this path
        pairs, orphans, conflicted_dirs = find_conflicted_pairs(
            path, args.recursive, show_progress=not args.no_progress,
            cross_device=args.cross_device, include_local_mounts=args.include_local_mounts)

        # Store results for this path
        path_results[path] = {
            'pairs': pairs,
            'orphans': orphans,
            'conflicted_dirs': conflicted_dirs,
            'identical_count': 0,
            'different_count': 0,
            'deleted_files': [],
            'different_files': []
        }
        all_orphans.extend(orphans)
        all_conflicted_dirs.extend(conflicted_dirs)

        all_pairs.extend(pairs)
    
    if not all_pairs and not all_orphans and not all_conflicted_dirs:
        print("No conflicted file pairs found (nor orphans or conflicted directories) "
              "in any of the specified directories.")
        return

    summary_bits = [f"{len(all_pairs)} conflicted file pair(s)"]
    if all_orphans:
        summary_bits.append(f"{len(all_orphans)} orphan(s)")
    if all_conflicted_dirs:
        summary_bits.append(f"{len(all_conflicted_dirs)} conflicted directory(ies)")
    print("Found " + ", ".join(summary_bits) + " total\n")

    # Global counters
    total_identical_count = 0
    total_different_count = 0
    all_deleted_files = []
    all_different_files = []
    
    # Compare each pair
    for original, conflicted in all_pairs:
        # Find which path this pair belongs to
        for path in path_results:
            if (original, conflicted) in path_results[path]['pairs']:
                current_path_key = path
                break
        try:
            result = compare_files(original, conflicted, args.method)
            
            if result["identical"]:
                total_identical_count += 1
                path_results[current_path_key]['identical_count'] += 1
                if args.show_identical or args.verbose:
                    print(f"✓ IDENTICAL: {original.name}")
                    if args.verbose:
                        print(f"  Original:    {result['original']}")
                        print(f"  Conflicted:  {result['conflicted']}")
                        print(f"  Size:        {result['original_size']:,} bytes")
                        print(f"  Modified:    Original: {result['original_mtime']}")
                        print(f"               Conflicted: {result['conflicted_mtime']}")
                        if result.get("original_hash"):
                            print(f"  Hash:        {result['original_hash']}")
                
                # Handle deletion
                should_delete = False
                if args.dry_run:
                    print(f"  → The two files")
                    print(f"      {result['original']}")
                    print(f"      {result['conflicted']}")
                    print(f"    are identical, would delete")
                    print(f"      {result['conflicted']}")
                    all_deleted_files.append(str(conflicted))
                    path_results[current_path_key]['deleted_files'].append(str(conflicted))
                elif args.auto_delete:
                    should_delete = True
                else:
                    should_delete = confirm_deletion(conflicted)
                
                if should_delete and not args.dry_run:
                    try:
                        print(f"  → The two files")
                        print(f"      {result['original']}")
                        print(f"      {result['conflicted']}")
                        print(f"    are identical, deleting")
                        print(f"      {result['conflicted']}")
                        conflicted.unlink()
                        all_deleted_files.append(str(conflicted))
                        path_results[current_path_key]['deleted_files'].append(str(conflicted))
                        print(f"    ✓ Deleted successfully")
                    except Exception as e:
                        print(f"  → Error deleting {conflicted}: {e}", file=sys.stderr)
                elif not should_delete and not args.dry_run:
                    print(f"  → Skipped deletion")
                
                if args.verbose:
                    print()
            else:
                total_different_count += 1
                path_results[current_path_key]['different_count'] += 1
                print(f"✗ DIFFERENT: {original.name}")
                if args.verbose:
                    print(f"  Original:    {result['original']} ({result['original_size']:,} bytes)")
                    print(f"  Conflicted:  {result['conflicted']} ({result['conflicted_size']:,} bytes)")
                    print(f"  Modified:    Original: {result['original_mtime']}")
                    print(f"               Conflicted: {result['conflicted_mtime']}")
                    print(f"  Reason:      {result['reason']}")
                    if result.get("original_hash"):
                        print(f"  Original hash:    {result['original_hash']}")
                        print(f"  Conflicted hash:  {result['conflicted_hash']}")
                    print()
                
                # Add to list for manual review
                all_different_files.append(result)
                path_results[current_path_key]['different_files'].append(result)
        
        except Exception as e:
            print(f"Error comparing {original} and {conflicted}: {e}", file=sys.stderr)
            continue
    
    # Interactive conflict resolution for different files
    if do_resolve_conflicts and all_different_files:
        if args.dry_run:
            # Show what actions would be taken without doing them
            resolved_count_interactive = resolve_conflicts_dry_run(all_different_files)
            print(f"\n🔍 Would show {resolved_count_interactive} conflict(s) for interactive resolution")
        else:
            # Actually perform interactive resolution
            resolved_count_interactive = resolve_conflicts(all_different_files)
            # Update the all_different_files list to remove resolved conflicts
            if resolved_count_interactive > 0:
                print(f"\n🎉 Successfully resolved {resolved_count_interactive} conflict(s) interactively")
                # Re-scan to update all_different_files list (files may have been deleted/renamed)
                all_different_files = [f for f in all_different_files
                                 if Path(f['original']).exists() and Path(f['conflicted']).exists()]
                total_different_count = len(all_different_files)

    # Capture orphan metadata BEFORE acting on them (nuke/normalize removes the
    # files, after which size/mtime can't be read).
    orphan_records = [build_orphan_record(o) for o in all_orphans]
    dir_records = [build_dir_record(d) for d in all_conflicted_dirs]

    # Handle orphaned conflicted files (report-only when no orphan mode chosen).
    orphan_tally = None
    if all_orphans:
        orphan_tally, repaired_conflicts = process_orphans(
            all_orphans, orphan_mode, args.dry_run, args.method)
        if repaired_conflicts:
            all_different_files.extend(repaired_conflicts)
            total_different_count += len(repaired_conflicts)

    # Save tracking (conflicts + orphans + directories)
    active_count = active_orphan_count = active_dir_count = 0
    if all_different_files or all_orphans or all_conflicted_dirs or os.path.exists(args.output):
        (output_file, active_count, resolved_count,
         active_orphan_count, active_dir_count) = save_tracking(
            all_different_files, orphan_records, dir_records, args.output)
        print(f"\nConflict tracking updated in: {output_file}")
        print(f"  Active conflicts: {active_count}")
        if resolved_count > 0:
            print(f"  Resolved conflicts: {resolved_count}")
        if active_orphan_count > 0:
            print(f"  Active orphans: {active_orphan_count}")
        if active_dir_count > 0:
            print(f"  Conflicted directories: {active_dir_count}")

    # Per-directory summary if multiple paths
    if len(args.paths) > 1:
        print("\n" + "="*60)
        print("PER-DIRECTORY RESULTS:")
        print("="*60)
        for path in args.paths:
            results = path_results[path]
            print(f"\n📁 {path}:")
            print(f"   Conflicted pairs: {len(results['pairs'])}")
            if len(results['pairs']) > 0:
                print(f"   Identical files: {results['identical_count']}")
                print(f"   Different files: {results['different_count']}")
                if results['deleted_files']:
                    print(f"   {'Would delete' if args.dry_run else 'Deleted'}: {len(results['deleted_files'])} file(s)")
            if results['orphans']:
                print(f"   Orphaned conflicted files: {len(results['orphans'])}")
            if results['conflicted_dirs']:
                print(f"   Conflicted directories: {len(results['conflicted_dirs'])}")

    # Overall summary
    print("\n" + "="*50)
    print("OVERALL SUMMARY:")
    print(f"Total conflicted pairs found: {len(all_pairs)}")
    print(f"Identical files: {total_identical_count}")
    print(f"Different files: {total_different_count}")
    print(f"Orphaned conflicted files: {len(all_orphans)}")
    print(f"Conflicted directories: {len(all_conflicted_dirs)}")

    if all_deleted_files:
        print(f"\n{'Would delete' if args.dry_run else 'Deleted'} {len(all_deleted_files)} identical conflicted file(s)")

    if orphan_tally:
        verb = "Would " if args.dry_run else ""
        actions = []
        if orphan_tally['nuked']:
            actions.append(f"{verb.lower()}nuked {orphan_tally['nuked']}" if verb else f"nuked {orphan_tally['nuked']}")
        if orphan_tally['normalized']:
            actions.append(f"normalized {orphan_tally['normalized']}")
        if orphan_tally['repaired']:
            actions.append(f"re-paired {orphan_tally['repaired']}")
        if orphan_tally['skipped']:
            actions.append(f"skipped {orphan_tally['skipped']}")
        if orphan_tally['errors']:
            actions.append(f"errored on {orphan_tally['errors']}")
        if actions:
            prefix = "Would have " if args.dry_run else ""
            print(f"\nOrphans: {prefix}{', '.join(actions)}")

    if total_identical_count > 0 and not args.auto_delete and not args.dry_run and len(all_deleted_files) < total_identical_count:
        print(f"\nTip: Use --auto-delete to automatically delete identical conflicted files")

    if active_count > 0:
        print(f"\nFiles requiring manual review are tracked in: {args.output}")
        print("The file contains all active conflicts from this and previous runs.")
        print("Resolved conflicts are marked but kept for history.")
        if not do_resolve_conflicts:
            print(f"\n💡 Tip: Use --resolve to interactively resolve conflicts with different content")

    if all_orphans and orphan_mode is None:
        print(f"\n💡 Tip: {len(all_orphans)} orphan(s) left untouched. Use --resolve-orphans "
              f"(interactive), --normalize-orphans, or --nuke-orphans to handle them.")

    # Loud, last-thing-on-screen warning about conflicted directories.
    report_conflicted_dirs(all_conflicted_dirs)

if __name__ == "__main__":
    main()
