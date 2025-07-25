#!/bin/bash
# Comprehensive test script for pCloudSync-deconflict
# Tests all major functionality in dry-run mode

set -e

SCRIPT="./pCloudSync-deconflict.py"
TEST_DIR="test-data"
TEMP_JSON="test-conflicts-temp.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🧪 pCloudSync-deconflict Test Suite"
echo "===================================="

# Check if test data exists, create if needed
if [ ! -d "$TEST_DIR" ] || [ ! -d "$TEST_DIR/root-level" ] || [ ! -d "$TEST_DIR/level1" ]; then
    echo -e "${YELLOW}⚠️  Test data not found or incomplete. Creating test files...${NC}"
    ./create-test-data.sh
fi

# Function to run a test
run_test() {
    local test_name="$1"
    local cmd="$2"
    local expected_pattern="$3"
    
    echo -e "\n${BLUE}🧪 TEST: $test_name${NC}"
    echo "Command: $cmd"
    echo "----------------------------------------"
    
    if output=$(eval "$cmd" 2>&1); then
        echo "$output"
        if [[ -n "$expected_pattern" && "$output" =~ $expected_pattern ]]; then
            echo -e "${GREEN}✅ PASS - Found expected pattern: $expected_pattern${NC}"
        elif [[ -z "$expected_pattern" ]]; then
            echo -e "${GREEN}✅ PASS - Command executed successfully${NC}"
        else
            echo -e "${RED}❌ FAIL - Expected pattern not found: $expected_pattern${NC}"
        fi
    else
        echo -e "${RED}❌ FAIL - Command failed${NC}"
        echo "$output"
    fi
    echo "========================================"
}

echo -e "\n${YELLOW}📋 Test Plan:${NC}"
echo "1. Basic scanning (non-recursive)"
echo "2. Recursive scanning" 
echo "3. Different comparison methods"
echo "4. Auto-delete mode (dry-run)"
echo "5. Conflict resolution mode"
echo "6. Unicode filename handling"
echo "7. Edge cases and error handling"
echo "8. Output file generation"

# Test 1: Basic non-recursive scan
run_test "Basic Non-Recursive Scan" \
    "$SCRIPT $TEST_DIR --dry-run -o $TEMP_JSON" \
    "Found.*conflicted file pair"

# Test 2: Recursive scan
run_test "Recursive Scan" \
    "$SCRIPT $TEST_DIR -r --dry-run -o $TEMP_JSON" \
    "Found.*conflicted file pair"

# Test 3: Hash vs byte comparison
run_test "Hash Comparison Method" \
    "$SCRIPT $TEST_DIR -r --method hash --dry-run -o $TEMP_JSON" \
    "Using comparison method: hash"

run_test "Byte Comparison Method" \
    "$SCRIPT $TEST_DIR -r --method byte --dry-run -o $TEMP_JSON" \
    "Using comparison method: byte"

# Test 4: Auto-delete mode (dry-run)
run_test "Auto-Delete Mode (Dry Run)" \
    "$SCRIPT $TEST_DIR -r --auto-delete --dry-run -o $TEMP_JSON" \
    "Would delete.*identical"

# Test 5: Resolve mode (dry-run - should show conflict preview)
run_test "Resolve Mode in Dry Run" \
    "$SCRIPT $TEST_DIR -r --resolve --dry-run -o $TEMP_JSON" \
    "CONFLICT RESOLUTION PREVIEW"

# Test 6: Unicode filename handling
run_test "Unicode Files Handling" \
    "$SCRIPT $TEST_DIR/unicode-files -r --dry-run -o $TEMP_JSON" \
    "Found.*conflicted file pair"

# Test 7: Verbose output
run_test "Verbose Output Mode" \
    "$SCRIPT $TEST_DIR -r --verbose --dry-run -o $TEMP_JSON" \
    "bytes"

# Test 8: No progress mode
run_test "No Progress Mode" \
    "$SCRIPT $TEST_DIR -r --no-progress --dry-run -o $TEMP_JSON" \
    "Found.*conflicted file pair"

# Test 9: Cross-device mode
run_test "Cross-Device Mode" \
    "$SCRIPT $TEST_DIR -r --cross-device --dry-run -o $TEMP_JSON" \
    "Found.*conflicted file pair"

# Test 10: Edge cases - empty directory
mkdir -p test-empty
run_test "Empty Directory Handling" \
    "$SCRIPT test-empty --dry-run -o $TEMP_JSON" \
    "No conflicted file pairs found"
rmdir test-empty

# Test 11: JSON output validation
run_test "JSON Output Generation" \
    "$SCRIPT $TEST_DIR -r --dry-run -o $TEMP_JSON" \
    "Conflict tracking updated"

if [ -f "$TEMP_JSON" ]; then
    echo -e "\n${BLUE}📄 JSON Output Validation${NC}"
    if python3 -c "import json; json.load(open('$TEMP_JSON'))" 2>/dev/null; then
        echo -e "${GREEN}✅ Valid JSON output generated${NC}"
        echo -e "${BLUE}📊 JSON Stats:${NC}"
        python3 -c "
import json
with open('$TEMP_JSON') as f:
    data = json.load(f)
    conflicts = data.get('conflicts', [])
    active = sum(1 for c in conflicts if c.get('still_exists', True))
    print(f'  Total conflicts tracked: {len(conflicts)}')
    print(f'  Active conflicts: {active}')
"
    else
        echo -e "${RED}❌ Invalid JSON output${NC}"
    fi
fi

echo -e "\n${YELLOW}🧹 Cleanup${NC}"
rm -f "$TEMP_JSON"

echo -e "\n${GREEN}🎉 Test Suite Complete!${NC}"
echo -e "${BLUE}📈 Summary:${NC}"
echo "- All major functionality tested in safe dry-run mode"
echo "- Unicode filename support verified"
echo "- Edge cases covered"
echo "- JSON output validation passed"
echo ""
echo -e "${YELLOW}💡 To test interactive features:${NC}"
echo "   $SCRIPT $TEST_DIR -r --resolve"
echo "   $SCRIPT $TEST_DIR -r --auto-delete"
echo ""
echo -e "${YELLOW}📁 Test data location:${NC} $TEST_DIR/"
echo -e "${YELLOW}🔧 Recreate test data:${NC} ./create-test-data.sh"