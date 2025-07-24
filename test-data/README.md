# Test Data for pCloudSync-deconflict  

This directory contains comprehensive test data to validate all functionality of pCloudSync-deconflict.

## 📁 Directory Structure

```
test-data/
├── create-test-files.sh     # Script to recreate all test files
├── README.md               # This documentation
├── root-level/             # Root level test files
├── level1/                 # Nested test files
│   ├── level2/            # Deeper nesting
│   └── level2b/           # Parallel branch
├── unicode-files/         # Unicode and special character tests
└── edge-cases/           # Edge cases and error conditions
```

## 🧪 Test Scenarios

### ✅ Identical Files (Should Auto-Delete)
- `identical-text-file.txt` + `identical-text-file [conflicted].txt`
- `identical-script-no-ext` + `identical-script-no-ext [conflicted]` (no extension)
- `identical-binary.png` + `identical-binary [conflicted].png` (binary files)
- `identical-nested.txt` + `identical-nested [conflicted].txt` (nested)
- `identical-json.json` + `identical-json [conflicted].json` (deep nested)
- `identical-makefile` + `identical-makefile [conflicted]` (no extension, nested)
- `unicode-cafe.txt` + `unicode-cafe [conflicted].txt` (Unicode identical)
- `file with spaces.txt` + `file with spaces [conflicted].txt` (spaces)

### ⚡ Different Files (Need Resolution)
- `different-text-file.txt` + `different-text-file [conflicted].txt` (text diff)
- `different-config-no-ext` + `different-config-no-ext [conflicted]` (no extension)
- `different-binary.png` + `different-binary [conflicted].png` (binary diff)
- `different-nested.txt` + `different-nested [conflicted].txt` (nested)  
- `different-json.json` + `different-json [conflicted].json` (JSON diff)
- `different-unicode.txt` + `different-unicode [conflicted].txt` (Unicode diff)
- `file-with-special-chars.txt` + `file-with-special-chars [conflicted].txt`
- `large-file.txt` + `large-file [conflicted].txt` (1000+ lines)
- `empty-conflict-test.txt` + `empty-conflict-test [conflicted].txt` (empty file)

### 🔍 Edge Cases
- `orphaned [conflicted].txt` - conflicted file with no original
- `no-conflict-original.txt` - original file with no conflicted version
- Large files (1000+ lines) to test performance
- Empty files to test edge case handling

## 🚀 Usage

### Recreate Test Files
```bash
cd test-data
./create-test-files.sh
```

### Run Comprehensive Tests
```bash
./run-tests.sh
```

### Manual Testing Examples
```bash
# Test basic functionality
./pCloudSync-deconflict.py test-data -r --dry-run

# Test auto-delete
./pCloudSync-deconflict.py test-data -r --auto-delete --dry-run

# Test conflict resolution (interactive)
./pCloudSync-deconflict.py test-data -r --resolve

# Test Unicode handling  
./pCloudSync-deconflict.py test-data/unicode-files -r --dry-run

# Test specific subdirectory
./pCloudSync-deconflict.py test-data/level1 -r --dry-run
```

## 📊 Expected Results

When running on the complete test data:
- **Total pairs found**: 17
- **Identical files**: 8 (auto-deletable)
- **Different files**: 9 (need resolution)
- **Unicode support**: ✓ Files with café, 咖啡, émojis
- **Files without extensions**: ✓ Scripts, makefiles, configs
- **Multi-level nesting**: ✓ Up to 3 levels deep
- **Special characters**: ✓ Spaces, symbols in filenames
- **Edge cases**: ✓ Empty files, orphaned files

## 🛠️ Features Tested

- ✅ Recursive vs non-recursive scanning
- ✅ Hash vs byte-by-byte comparison  
- ✅ Auto-delete mode for identical files
- ✅ Interactive conflict resolution
- ✅ Unicode filename support
- ✅ Files with and without extensions
- ✅ Binary file handling
- ✅ Large file processing
- ✅ JSON output generation and persistence
- ✅ Progress indicator (with proper Unicode width)
- ✅ Error handling for edge cases
- ✅ Cross-device boundary respect
- ✅ Cloud storage detection avoidance

## 🔧 Maintenance

To add new test scenarios:
1. Edit `create-test-files.sh` 
2. Add corresponding documentation here
3. Update `run-tests.sh` if needed
4. Run tests to ensure no regressions