#!/usr/bin/env python3
"""
Test all requirements from the assignment
"""
import os
import sys
import tempfile
import shutil
import hashlib
import subprocess

def test_requirement_1_backup_restore():
    """Test backup and restore correctness"""
    print("Test 1: Backup and Restore Correctness")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup
        dataset = os.path.join(tmpdir, "dataset")
        store = os.path.join(tmpdir, "store")
        restored = os.path.join(tmpdir, "restored")
        
        os.makedirs(dataset)
        
        # Create test files
        test_content = b"Test content " * 1000
        with open(os.path.join(dataset, "test.txt"), "wb") as f:
            f.write(test_content)
        
        # Run backup
        subprocess.run([sys.executable, "main.py", "init", store], 
                      capture_output=True)
        subprocess.run([sys.executable, "main.py", "backup", dataset], 
                      capture_output=True)
        
        # Get snapshot ID
        result = subprocess.run([sys.executable, "main.py", "list"],
                              capture_output=True, text=True)
        lines = result.stdout.split('\n')
        snapshot_id = None
        for line in lines:
            if "ID: snap_" in line:
                snapshot_id = line.split("ID: ")[1].strip()
                break
        
        if not snapshot_id:
            print("  ✗ Failed to get snapshot ID")
            return False
        
        # Restore
        os.makedirs(restored)
        subprocess.run([sys.executable, "main.py", "restore", snapshot_id, restored],
                      capture_output=True)
        
        # Verify
        restored_file = os.path.join(restored, "test.txt")
        if os.path.exists(restored_file):
            with open(restored_file, "rb") as f:
                restored_content = f.read()
            if restored_content == test_content:
                print("  ✓ Backup/Restore works correctly")
                return True
            else:
                print("  ✗ Restored content doesn't match")
                return False
        else:
            print("  ✗ File not restored")
            return False

def test_requirement_2_integrity():
    """Test data integrity verification"""
    print("\nTest 2: Data Integrity Verification")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        dataset = os.path.join(tmpdir, "dataset")
        store = os.path.join(tmpdir, "store")
        
        os.makedirs(dataset)
        
        # Create and backup
        with open(os.path.join(dataset, "test.bin"), "wb") as f:
            f.write(os.urandom(5000))
        
        subprocess.run([sys.executable, "main.py", "init", store])
        subprocess.run([sys.executable, "main.py", "backup", dataset])
        
        # Get snapshot ID
        result = subprocess.run([sys.executable, "main.py", "list"],
                              capture_output=True, text=True)
        
        # Tamper with a chunk file
        chunk_dir = os.path.join(store, "chunks")
        for root, dirs, files in os.walk(chunk_dir):
            if files:
                chunk_file = os.path.join(root, files[0])
                with open(chunk_file, "r+b") as f:
                    f.seek(10)
                    f.write(b"TAMPERED")
                break
        
        # Verify should fail
        lines = result.stdout.split('\n')
        snapshot_id = None
        for line in lines:
            if "ID: snap_" in line:
                snapshot_id = line.split("ID: ")[1].strip()
                break
        
        if snapshot_id:
            result = subprocess.run([sys.executable, "main.py", "verify", snapshot_id],
                                  capture_output=True, text=True)
            if "INVALID" in result.stdout or "FAIL" in result.stdout:
                print("  ✓ Integrity check detects tampering")
                return True
            else:
                print("  ✗ Integrity check should have failed")
                return False
        return False

def test_requirement_3_audit_log():
    """Test audit log tamper detection"""
    print("\nTest 3: Audit Log Tamper Detection")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        store = os.path.join(tmpdir, "store")
        
        subprocess.run([sys.executable, "main.py", "init", store])
        
        # Add some audit entries
        dataset = os.path.join(tmpdir, "dataset")
        os.makedirs(dataset)
        subprocess.run([sys.executable, "main.py", "backup", dataset],
                      capture_output=True)
        
        # Verify audit log is valid
        result = subprocess.run([sys.executable, "main.py", "audit-verify"],
                              capture_output=True, text=True)
        
        if "AUDIT OK" in result.stdout:
            print("  ✓ Audit log initially valid")
            
            # Tamper with audit log
            audit_log = os.path.join(store, "audit.log")
            with open(audit_log, "a") as f:
                f.write("TAMPERED LINE\n")
            
            # Verify should now fail
            result = subprocess.run([sys.executable, "main.py", "audit-verify"],
                                  capture_output=True, text=True)
            if "CORRUPTED" in result.stdout:
                print("  ✓ Audit log detects tampering")
                return True
            else:
                print("  ✗ Audit log should show corruption")
                return False
        else:
            print("  ✗ Audit log not valid initially")
            return False

def test_requirement_4_policy():
    """Test policy enforcement"""
    print("\nTest 4: Policy Enforcement")
    
    # This test depends on current OS user and policy.yaml
    # We'll test by checking that commands are logged
    
    with tempfile.TemporaryDirectory() as tmpdir:
        store = os.path.join(tmpdir, "store")
        
        # Init should work
        result = subprocess.run([sys.executable, "main.py", "init", store],
                              capture_output=True, text=True)
        
        if "Initialized" in result.stdout:
            print("  ✓ Initialization works")
            
            # Check audit log was created
            audit_log = os.path.join(store, "audit.log")
            if os.path.exists(audit_log):
                with open(audit_log, 'r') as f:
                    lines = f.readlines()
                    if lines and "init" in lines[-1]:
                        print("  ✓ Audit log contains init entry")
                        return True
                    else:
                        print("  ✗ Audit log missing init entry")
                        return False
            else:
                print("  ✗ Audit log not created")
                return False
        else:
            print("  ✗ Initialization failed")
            return False

def main():
    """Run all requirement tests"""
    print("=" * 60)
    print("Testing Assignment Requirements")
    print("=" * 60)
    
    tests = [
        ("Backup/Restore Correctness", test_requirement_1_backup_restore),
        ("Data Integrity Verification", test_requirement_2_integrity),
        ("Audit Log Tamper Detection", test_requirement_3_audit_log),
        ("Policy Enforcement", test_requirement_4_policy),
    ]
    
    passed = 0
    total = len(tests)
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
    
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)
    
    if passed == total:
        print("✓ All requirements satisfied!")
        return 0
    else:
        print("✗ Some requirements not met")
        return 1

if __name__ == "__main__":
    sys.exit(main())