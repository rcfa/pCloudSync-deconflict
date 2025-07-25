#!/bin/bash
# Script to create comprehensive test files for pCloudSync-deconflict

set -e  # Exit on any error

echo "Creating comprehensive test files..."

# Create the test-data directory structure
mkdir -p test-data/{level1/{level2,level2b},root-level,unicode-files,edge-cases,parentheses-conflicts}

# Change to test-data directory for file creation
cd test-data

# Root level - IDENTICAL files (should be auto-deletable)
echo "This content is identical in both files" > root-level/identical-text-file.txt
echo "This content is identical in both files" > "root-level/identical-text-file [conflicted].txt"

cat > root-level/identical-script-no-ext << 'EOF'
#!/bin/bash
echo 'Same script content'
EOF
cp root-level/identical-script-no-ext "root-level/identical-script-no-ext [conflicted]"

# Root level - DIFFERENT files (real conflicts)
cat > root-level/different-text-file.txt << 'EOF'
Original version of this text file
Line 2 content
Line 3 original  
EOF

cat > "root-level/different-text-file [conflicted].txt" << 'EOF'
Modified version of this text file  
Line 2 CHANGED content
Line 3 modified
Line 4 added
EOF

echo "original config value=123" > root-level/different-config-no-ext
echo "modified config value=456" > "root-level/different-config-no-ext [conflicted]"

# Binary files - IDENTICAL
printf "\x89PNG\x0D\x0A\x1A\x0A fake png header" > root-level/identical-binary.png
cp root-level/identical-binary.png "root-level/identical-binary [conflicted].png"

# Binary files - DIFFERENT  
printf "\x89PNG\x0D\x0A\x1A\x0A fake png v1" > root-level/different-binary.png
printf "\x89PNG\x0D\x0A\x1A\x0A fake png v2" > "root-level/different-binary [conflicted].png"

# Level 1 - nested files
echo "Deep nested identical content" > level1/identical-nested.txt
echo "Deep nested identical content" > "level1/identical-nested [conflicted].txt"

echo "Deep nested different original" > level1/different-nested.txt  
echo "Deep nested different modified" > "level1/different-nested [conflicted].txt"

# Level 2 - deeper nesting
echo '{"config": "identical", "value": 42}' > level1/level2/identical-json.json
echo '{"config": "identical", "value": 42}' > "level1/level2/identical-json [conflicted].json"

echo '{"config": "original", "value": 100}' > level1/level2/different-json.json
echo '{"config": "modified", "value": 200, "new_field": true}' > "level1/level2/different-json [conflicted].json"

# Level 2b - parallel branch  
cat > level1/level2b/identical-makefile << 'EOF'
# Makefile content
all: build

build:
	echo building
EOF
cp level1/level2b/identical-makefile "level1/level2b/identical-makefile [conflicted]"

# Unicode and special character files
echo "Content with café and émojis 🚀" > "unicode-files/unicode-cafe.txt"
echo "Content with café and émojis 🚀" > "unicode-files/unicode-cafe [conflicted].txt"

echo "Different café content ☕" > "unicode-files/different-unicode.txt"  
echo "Different 咖啡 content ☕" > "unicode-files/different-unicode [conflicted].txt"

# Files with spaces
echo "File with spaces identical content" > "unicode-files/file with spaces.txt"
echo "File with spaces identical content" > "unicode-files/file with spaces [conflicted].txt"

echo "Original version with special chars" > "unicode-files/file-with-special-chars.txt"
echo "Modified version with special chars" > "unicode-files/file-with-special-chars [conflicted].txt"

# Edge cases
echo "Empty conflicted file test" > edge-cases/empty-conflict-test.txt
touch "edge-cases/empty-conflict-test [conflicted].txt"  # Empty file

echo "Large file content" > edge-cases/large-file.txt
for i in {1..1000}; do echo "Line $i of large file content for testing" >> edge-cases/large-file.txt; done
cp edge-cases/large-file.txt "edge-cases/large-file [conflicted].txt"
echo "Modified last line" >> "edge-cases/large-file [conflicted].txt"

# Files with no conflicts (orphaned conflicted files)
echo "This has no matching original" > "edge-cases/orphaned [conflicted].txt"
echo "This has no matching conflicted" > "edge-cases/no-conflict-original.txt"

# Test files with (conflicted) pattern instead of [conflicted]
echo "Identical content with parentheses" > parentheses-conflicts/identical-parens.txt
echo "Identical content with parentheses" > "parentheses-conflicts/identical-parens (conflicted).txt"

echo "Different original with parens" > parentheses-conflicts/different-parens.txt
echo "Different modified with parens" > "parentheses-conflicts/different-parens (conflicted).txt"

# Mixed patterns in same directory
echo "Mixed pattern identical" > parentheses-conflicts/mixed-pattern.txt
echo "Mixed pattern identical" > "parentheses-conflicts/mixed-pattern [conflicted].txt"
echo "Mixed pattern identical" > "parentheses-conflicts/mixed-pattern (conflicted).txt"

# Unicode with parentheses pattern
echo "Unicode café ☕ identical" > "parentheses-conflicts/unicode-parens.txt"
echo "Unicode café ☕ identical" > "parentheses-conflicts/unicode-parens (conflicted).txt"

# Orphaned (conflicted) file
echo "Orphaned with parentheses" > "parentheses-conflicts/orphaned-parens (conflicted).txt"

cd ..  # Return to project root directory

echo "✅ Test files created successfully in test-data/"
echo "📊 Test file summary:"
echo "   - Identical files (should auto-delete): 9 pairs (6 [conflicted] + 3 (conflicted))"
echo "   - Different files (need resolution): 8 pairs (6 [conflicted] + 2 (conflicted))"
echo "   - Unicode/special chars: 5 pairs"
echo "   - Edge cases: 5 items"
echo "   - Multi-level nesting: ✓"
echo "   - Files without extensions: ✓"
echo "   - Both [conflicted] and (conflicted) patterns: ✓"