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

def find_conflicted_pairs(directory: str, recursive: bool = True, show_progress: bool = True, cross_device: bool = False, include_local_mounts: bool = False) -> List[Tuple[Path, Path]]:
    """Find all pairs of original and conflicted files in a directory."""
    conflicted_pairs = []
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
            
            # Process files in this directory
            for filename in files:
                files_processed += 1
                update_progress(current_dir)
                
                if " [conflicted]" in filename:
                    try:
                        conflicted_file = current_dir / filename
                        original_name = filename.replace(" [conflicted]", "")
                        original_file = current_dir / original_name
                        
                        # Check if the original file exists
                        try:
                            if original_file.exists() and original_file.is_file():
                                conflicted_pairs.append((original_file, conflicted_file))
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
                
                if item.is_file() and " [conflicted]" in item.name:
                    conflicted_file = item
                    original_name = item.name.replace(" [conflicted]", "")
                    original_file = item.parent / original_name
                    
                    if original_file.exists() and original_file.is_file():
                        conflicted_pairs.append((original_file, conflicted_file))
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
    
    return conflicted_pairs

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

def load_existing_conflicts(output_file: str) -> Dict[str, Dict]:
    """Load existing conflicts from JSON file if it exists."""
    if not os.path.exists(output_file):
        return {}
    
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Convert list to dict keyed by original file path for easy merging
            conflicts = {}
            for conflict in data.get('conflicts', data.get('files', [])):
                key = conflict['original']
                conflicts[key] = conflict
            return conflicts
    except Exception as e:
        print(f"Warning: Could not load existing conflicts file: {e}")
        return {}

def validate_conflict_still_exists(conflict: Dict) -> bool:
    """Check if a conflict pair still exists on disk."""
    try:
        original = Path(conflict['original'])
        conflicted = Path(conflict['conflicted'])
        return original.exists() and conflicted.exists()
    except Exception:
        return False

def save_different_files_list(different_files: List[Dict], output_file: str = "conflicted_files_to_review.json"):
    """Save the list of different files to a JSON file for manual review, merging with existing conflicts."""
    # Load existing conflicts
    existing_conflicts = load_existing_conflicts(output_file)
    
    # Update with new conflicts
    for conflict in different_files:
        key = conflict['original']
        conflict['last_seen'] = datetime.now().isoformat()
        conflict['still_exists'] = True
        existing_conflicts[key] = conflict
    
    # Check if old conflicts still exist
    for key, conflict in existing_conflicts.items():
        if key not in [c['original'] for c in different_files]:
            if validate_conflict_still_exists(conflict):
                conflict['still_exists'] = True
                conflict['last_checked'] = datetime.now().isoformat()
            else:
                conflict['still_exists'] = False
                conflict['resolved_at'] = datetime.now().isoformat()
    
    # Filter to only active conflicts (unless keeping resolved ones for history)
    active_conflicts = [c for c in existing_conflicts.values() if c.get('still_exists', True)]
    all_conflicts = list(existing_conflicts.values())
    
    # Save updated list
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "last_updated": datetime.now().isoformat(),
            "total_active_conflicts": len(active_conflicts),
            "total_resolved_conflicts": len(all_conflicts) - len(active_conflicts),
            "conflicts": all_conflicts
        }, f, indent=2, ensure_ascii=False, sort_keys=True)
    
    return output_file, len(active_conflicts), len(all_conflicts) - len(active_conflicts)

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

def main():
    parser = argparse.ArgumentParser(
        description="Find and compare conflicted files from cloud sync services"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="pCloudSync-deconflict 1.1.0"
    )
    parser.add_argument(
        "path",
        help="Path to the directory to scan"
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
        default="conflicted_files_to_review.json",
        help="Output file for list of different files (default: conflicted_files_to_review.json)"
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
        help="Interactively resolve actual conflicts (files with different content)"
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.path):
        print(f"Error: Path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)
    
    if not os.path.isdir(args.path):
        print(f"Error: Path '{args.path}' is not a directory", file=sys.stderr)
        sys.exit(1)
    
    print(f"Scanning {'recursively' if args.recursive else 'non-recursively'} in: {args.path}")
    print(f"Using comparison method: {args.method}")
    if not args.auto_delete and not args.dry_run:
        print("Will ask for confirmation before deleting identical files")
    print()
    
    # Find conflicted pairs
    pairs = find_conflicted_pairs(args.path, args.recursive, show_progress=not args.no_progress, 
                                 cross_device=args.cross_device, include_local_mounts=args.include_local_mounts)
    
    if not pairs:
        print("No conflicted file pairs found.")
        return
    
    print(f"Found {len(pairs)} conflicted file pair(s)\n")
    
    identical_count = 0
    different_count = 0
    deleted_files = []
    different_files = []
    
    # Compare each pair
    for original, conflicted in pairs:
        try:
            result = compare_files(original, conflicted, args.method)
            
            if result["identical"]:
                identical_count += 1
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
                    deleted_files.append(str(conflicted))
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
                        deleted_files.append(str(conflicted))
                        print(f"    ✓ Deleted successfully")
                    except Exception as e:
                        print(f"  → Error deleting {conflicted}: {e}", file=sys.stderr)
                elif not should_delete and not args.dry_run:
                    print(f"  → Skipped deletion")
                
                if args.verbose:
                    print()
            else:
                different_count += 1
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
                different_files.append(result)
        
        except Exception as e:
            print(f"Error comparing {original} and {conflicted}: {e}", file=sys.stderr)
            continue
    
    # Interactive conflict resolution for different files
    if args.resolve and different_files:
        if args.dry_run:
            # Show what actions would be taken without doing them
            resolved_count_interactive = resolve_conflicts_dry_run(different_files)
            print(f"\n🔍 Would show {resolved_count_interactive} conflict(s) for interactive resolution")
        else:
            # Actually perform interactive resolution
            resolved_count_interactive = resolve_conflicts(different_files)
            # Update the different_files list to remove resolved conflicts
            if resolved_count_interactive > 0:
                print(f"\n🎉 Successfully resolved {resolved_count_interactive} conflict(s) interactively")
                # Re-scan to update different_files list (files may have been deleted/renamed)
                different_files = [f for f in different_files 
                                 if Path(f['original']).exists() and Path(f['conflicted']).exists()]
                different_count = len(different_files)
    
    # Save list of different files
    active_count = 0
    if different_files or os.path.exists(args.output):
        output_file, active_count, resolved_count = save_different_files_list(different_files, args.output)
        print(f"\nConflict tracking updated in: {output_file}")
        print(f"  Active conflicts: {active_count}")
        if resolved_count > 0:
            print(f"  Resolved conflicts: {resolved_count}")
    
    # Summary
    print("\n" + "="*50)
    print("SUMMARY:")
    print(f"Total conflicted pairs found: {len(pairs)}")
    print(f"Identical files: {identical_count}")
    print(f"Different files: {different_count}")
    
    if deleted_files:
        print(f"\n{'Would delete' if args.dry_run else 'Deleted'} {len(deleted_files)} identical conflicted file(s)")
    
    if identical_count > 0 and not args.auto_delete and not args.dry_run and len(deleted_files) < identical_count:
        print(f"\nTip: Use --auto-delete to automatically delete identical conflicted files")
    
    if active_count > 0:
        print(f"\nFiles requiring manual review are tracked in: {args.output}")
        print("The file contains all active conflicts from this and previous runs.")  
        print("Resolved conflicts are marked but kept for history.")
        if not args.resolve:
            print(f"\n💡 Tip: Use --resolve to interactively resolve conflicts with different content")

if __name__ == "__main__":
    main()
