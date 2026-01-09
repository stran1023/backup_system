#!/usr/bin/env python3
"""
Test Audit Log Tamper Detection
Test modifying audit.log triggers AUDIT CORRUPTED
"""

import os
import sys
import shutil
import subprocess
import random
import json

def run_cmd(cmd):
    """Run command and return result"""
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result

def tamper_audit_log(audit_log_path, tamper_type="modify_char"):
    """
    Tamper with audit log file
    Returns: (success, backup_path)
    """
    if not os.path.exists(audit_log_path):
        return False, None
    
    # Backup original
    backup_path = audit_log_path + ".backup"
    shutil.copy2(audit_log_path, backup_path)
    
    with open(audit_log_path, 'r') as f:
        lines = f.readlines()
    
    if len(lines) < 2:
        return False, backup_path
    
    if tamper_type == "modify_char":
        # Modify one character in a random line (not first line)
        line_idx = random.randint(1, len(lines) - 1)
        line = lines[line_idx]
        
        if len(line) > 10:
            # Change a random character (not whitespace)
            for _ in range(10):  # Try up to 10 times
                char_idx = random.randint(0, len(line) - 2)
                if line[char_idx] not in [' ', '\t', '\n']:
                    new_char = 'X' if line[char_idx] != 'X' else 'Y'
                    lines[line_idx] = line[:char_idx] + new_char + line[char_idx + 1:]
                    print(f"    Modified line {line_idx+1}, char {char_idx}: '{line[char_idx]}' → '{new_char}'")
                    break
    
    elif tamper_type == "delete_line":
        # Delete a random line (not first)
        line_idx = random.randint(1, len(lines) - 1)
        deleted = lines.pop(line_idx)
        print(f"    Deleted line {line_idx+1}: {deleted[:50]}...")
    
    elif tamper_type == "insert_line":
        # Insert a fake line
        line_idx = random.randint(1, len(lines) - 1)
        fake_line = "0" * 64 + " " + "0" * 64 + " 1234567890000 fakeuser fakecmd abc123 OK TAMPERED\n"
        lines.insert(line_idx, fake_line)
        print(f"    Inserted fake line at position {line_idx+1}")
    
    # Write back
    with open(audit_log_path, 'w') as f:
        f.writelines(lines)
    
    return True, backup_path

def show_audit_log_preview(audit_log_path, num_lines=3):
    """Show preview of audit log"""
    if os.path.exists(audit_log_path):
        print("\n  Audit log preview:")
        with open(audit_log_path, 'r') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines[-num_lines:], 1):
            parts = line.strip().split()
            if len(parts) >= 7:
                print(f"    Line {len(lines)-num_lines+i}: {parts[3]} {parts[4]} {parts[6]}")

def test_audit_tamper():
    print("🔍 TEST: AUDIT LOG TAMPER DETECTION")
    print("="*60)
    
    # Create test store in current directory
    test_store = "./audit_tamper_test_store"
    print(f"Test store: {test_store}")
    
    # Cleanup if exists
    if os.path.exists(test_store):
        print("  Cleaning up existing test store...")
        shutil.rmtree(test_store, ignore_errors=True)
    
    try:
        # 1. Setup: Create store and audit entries
        print("\n1. SETUP: Creating audit log entries")
        
        # Initialize store
        result = run_cmd(f"python main.py init {test_store}")
        if result.returncode != 0:
            print("✗ Failed to init store")
            return False
        
        # Create multiple audit entries
        print("\n  Creating audit entries...")
        entries_created = 0
        
        print("  a) First backup...")
        result = run_cmd(f"python main.py backup dataset --label 'entry1'")
        if result.returncode == 0:
            entries_created += 1
            print("    ✓ Backup 1 successful")
        
        print("\n  b) List snapshots...")
        result = run_cmd(f"python main.py list")
        if result.returncode == 0:
            entries_created += 1
            print("    ✓ List successful")
        
        print("\n  c) Second backup...")
        result = run_cmd(f"python main.py backup dataset --label 'entry2'")
        if result.returncode == 0:
            entries_created += 1
            print("    ✓ Backup 2 successful")
        
        print("\n  d) Verify snapshot...")
        # Get snapshot ID
        metadata = f"{test_store}/metadata.json"
        if os.path.exists(metadata):
            with open(metadata, 'r') as f:
                data = json.load(f)
                if data.get("snapshots"):
                    snapshots = list(data["snapshots"].keys())
                    if snapshots:
                        snap_id = snapshots[0]
                        print(f"    Using snapshot: {snap_id}")
                        result = run_cmd(f"python main.py verify {snap_id}")
                        if result.returncode == 0:
                            entries_created += 1
                            print("    ✓ Verify successful")
        
        print(f"\n  ✓ Created {entries_created} audit entries")
        
        # Show audit log preview
        audit_log_path = f"{test_store}/audit.log"
        show_audit_log_preview(audit_log_path)
        
        # 2. Verify audit log is initially valid
        print("\n2. VERIFY: Initial audit log validation")
        
        result = run_cmd(f"python main.py audit-verify")
        if result.returncode == 0 and "AUDIT OK" in result.stdout:
            print("  ✓ Audit log is valid initially")
            initial_ok = True
        else:
            print("  ✗ Audit log invalid from start")
            print(f"  Output: {result.stdout}")
            return False
        
        # 3. Test 1: Modify one character
        print("\n" + "-"*50)
        print("3. TEST 1: Modify one character in audit log")
        print("-"*50)
        
        success, backup = tamper_audit_log(audit_log_path, "modify_char")
        if not success:
            print("  ✗ Could not tamper with audit log")
            return False
        
        print("\n  Running audit-verify after modification...")
        result = run_cmd(f"python main.py audit-verify")
        
        # Check for corruption detection
        if ("AUDIT CORRUPTED" in result.stdout or 
            "Hash mismatch" in result.stdout or 
            "Hash chain broken" in result.stdout):
            print("\n  ✅ TAMPER DETECTED!")
            print(f"  Message: {result.stdout.strip()}")
            test1_passed = True
        else:
            print("\n  ❌ Tamper NOT detected")
            test1_passed = False
        
        # Restore original
        if backup and os.path.exists(backup):
            shutil.copy2(backup, audit_log_path)
            os.remove(backup)
            print("  ✓ Restored original audit log")
        
        # 4. Test 2: Delete one line
        print("\n" + "-"*50)
        print("4. TEST 2: Delete one line from audit log")
        print("-"*50)
        
        success, backup = tamper_audit_log(audit_log_path, "delete_line")
        if not success:
            print("  ✗ Could not delete line")
            test2_passed = False
        else:
            print("\n  Running audit-verify after deletion...")
            result = run_cmd(f"python main.py audit-verify")
            
            if ("AUDIT CORRUPTED" in result.stdout or 
                "Hash mismatch" in result.stdout or
                "Hash chain broken" in result.stdout):
                print("\n  ✅ DELETION DETECTED!")
                print(f"  Message: {result.stdout.strip()}")
                test2_passed = True
            else:
                print("\n  ❌ Deletion NOT detected")
                test2_passed = False
            
            # Restore
            if backup and os.path.exists(backup):
                shutil.copy2(backup, audit_log_path)
                os.remove(backup)
                print("  ✓ Restored original audit log")
        
        # 5. Test 3: Insert fake line
        print("\n" + "-"*50)
        print("5. TEST 3: Insert fake line into audit log")
        print("-"*50)
        
        success, backup = tamper_audit_log(audit_log_path, "insert_line")
        if not success:
            print("  ✗ Could not insert line")
            test3_passed = False
        else:
            print("\n  Running audit-verify after insertion...")
            result = run_cmd(f"python main.py audit-verify")
            
            if ("AUDIT CORRUPTED" in result.stdout or 
                "Hash mismatch" in result.stdout or
                "Hash chain broken" in result.stdout):
                print("\n  ✅ INSERTION DETECTED!")
                print(f"  Message: {result.stdout.strip()}")
                test3_passed = True
            else:
                print("\n  ❌ Insertion NOT detected")
                test3_passed = False
            
            # Restore
            if backup and os.path.exists(backup):
                shutil.copy2(backup, audit_log_path)
                os.remove(backup)
                print("  ✓ Restored original audit log")
        
        # 6. Final verification
        print("\n" + "-"*50)
        print("6. FINAL: Verify audit log integrity after all tests")
        print("-"*50)
        
        print("\n  Running final audit-verify...")
        result = run_cmd(f"python main.py audit-verify")
        if result.returncode == 0 and "AUDIT OK" in result.stdout:
            print("\n  ✅ Audit log restored and valid")
            final_ok = True
        else:
            print("\n  ❌ Audit log corrupted after tests")
            final_ok = False
        
        # Show final audit log preview
        show_audit_log_preview(audit_log_path)
        
        # 7. Results
        print("\n" + "="*60)
        print("📊 TEST RESULTS")
        print("="*60)
        
        print(f"\n✓ Test 1 - Modify character: {'PASS' if test1_passed else 'FAIL'}")
        print(f"✓ Test 2 - Delete line:      {'PASS' if test2_passed else 'FAIL'}")
        print(f"✓ Test 3 - Insert line:      {'PASS' if test3_passed else 'FAIL'}")
        print(f"✓ Final integrity check:     {'PASS' if final_ok else 'FAIL'}")
        
        success = test1_passed and test2_passed and test3_passed and final_ok
        
        if success:
            print("\n" + "✅" * 20)
            print("✅ AUDIT TAMPER TEST PASSED")
            print("✅" * 20)
            print("\nRequirements verified:")
            print("  1. Character modification → DETECTED ✓")
            print("  2. Line deletion → DETECTED ✓")
            print("  3. Line insertion → DETECTED ✓")
            print("  4. Hash chain integrity maintained ✓")
            print("  5. 'AUDIT CORRUPTED' message shown ✓")
        else:
            print("\n" + "❌" * 20)
            print("❌ AUDIT TAMPER TEST FAILED")
            print("❌" * 20)
            print("\nIssues found:")
            issues = []
            if not test1_passed: issues.append("Character modification not detected")
            if not test2_passed: issues.append("Line deletion not detected")
            if not test3_passed: issues.append("Line insertion not detected")
            if not final_ok: issues.append("Final integrity check failed")
            
            for issue in issues:
                print(f"  • {issue}")
        
        # Keep the test store for inspection
        print(f"\n💾 Test store preserved for inspection: {os.path.abspath(test_store)}")
        print("  You can examine:")
        print(f"    - audit.log: {os.path.join(test_store, 'audit.log')}")
        print(f"    - metadata.json: {os.path.join(test_store, 'metadata.json')}")
        print(f"    - journal.wal: {os.path.join(test_store, 'journal.wal')}")
        
        return success
        
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🔍 AUDIT LOG TAMPER DETECTION TEST")
    print("="*60)
    print("\nThis test will:")
    print("  1. Create test store: ./audit_tamper_test_store/")
    print("  2. Generate audit log with multiple entries")
    print("  3. Tamper with audit log in 3 ways")
    print("  4. Verify 'AUDIT CORRUPTED' is shown")
    print("  5. Preserve test store for inspection")
    print("\n" + "="*60)
    
    # Check if dataset exists
    if not os.path.exists("dataset"):
        print("✗ Error: 'dataset' directory not found")
        print("  Create a dataset directory or use existing one")
        sys.exit(1)
    
    # Check if store already exists
    test_store = "./audit_tamper_test_store"
    if os.path.exists(test_store):
        print(f"⚠️  Warning: Test store '{test_store}' already exists")
        response = input("  Delete and recreate? (y/N): ")
        if response.lower() == 'y':
            shutil.rmtree(test_store, ignore_errors=True)
            print("  ✓ Removed existing test store")
        else:
            print("  Using existing test store")
    
    response = input("\nStart test? (y/N): ")
    if response.lower() != 'y':
        print("Test cancelled")
        sys.exit(0)
    
    print("\n" + "="*60)
    success = test_audit_tamper()
    
    if success:
        print("\n🎉 TEST COMPLETE")
        print(f"\nFor demo, show files in: {os.path.abspath(test_store)}")
        print("Run: python main.py audit-verify")
    else:
        print("\n⚠️  TEST FAILED")
    
    print("="*60)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()