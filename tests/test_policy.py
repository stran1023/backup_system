#!/usr/bin/env python3
"""
Test Policy DENY - FIXED VERSION
"""

import os
import sys
import shutil
import subprocess
import json
import getpass

def run_cmd(cmd):
    """Run command and return result"""
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result

def show_audit_log_preview(audit_log_path, num_lines=3):
    """Show preview of audit log"""
    if os.path.exists(audit_log_path):
        print("\n  Audit log preview:")
        with open(audit_log_path, 'r') as f:
            lines = f.readlines()
        
        print(f"  Total entries: {len(lines)}")
        for i, line in enumerate(lines[-num_lines:], 1):
            parts = line.strip().split()
            if len(parts) >= 7:
                status_icon = "✅" if parts[6] == "OK" else "❌" if parts[6] == "DENY" else "⚠️"
                print(f"    {status_icon} {parts[3]} {parts[4]} {parts[6]}")

def test_policy_deny_fixed():
    print("🧪 TEST: POLICY DENY - FIXED TEST")
    print("="*60)
    
    # Get current user
    current_user = getpass.getuser()
    print(f"Current OS user: {current_user}")
    
    # Backup original policy
    original_policy = "policy.yaml"
    backup_policy = "policy.yaml.backup"
    
    if os.path.exists(original_policy):
        shutil.copy2(original_policy, backup_policy)
        print("✓ Backed up original policy")
    else:
        print("✗ No policy.yaml found")
        return False
    
    # Create test store
    test_store = "./policy_deny_test_store"
    print(f"\nTest store: {test_store}")
    
    # Cleanup if exists
    if os.path.exists(test_store):
        print("  Cleaning up existing test store...")
        shutil.rmtree(test_store, ignore_errors=True)
    
    try:
        # PHASE 1: Setup with admin permissions
        print("\n" + "="*60)
        print("1. SETUP: Creating store with admin permissions")
        print("="*60)
        
        # Create policy with user as admin
        admin_policy = f"""users:
  {current_user}: admin
  root: admin
  admin: admin

roles:
  admin:
    - init
    - backup
    - list-snapshots
    - verify
    - restore
    - audit-verify
  
  operator:
    - backup
    - list-snapshots
    - verify
    - restore
    - audit-verify
  
  auditor:
    - list-snapshots
    - verify
    - audit-verify
"""
        
        with open(original_policy, 'w') as f:
            f.write(admin_policy)
        
        print(f"  Set user '{current_user}' as 'admin' in policy")
        
        # Create store and backup
        print("\n  a) Initializing store...")
        result = run_cmd(f"python main.py init {test_store}")
        if result.returncode != 0:
            print("    ✗ Failed to init store")
            return False
        print("    ✓ Store initialized")
        
        print("\n  b) Creating baseline backup...")
        result = run_cmd(f"python main.py backup dataset --label 'baseline'")
        if result.returncode != 0:
            print("    ✗ Failed to create baseline backup")
            return False
        print("    ✓ Baseline backup created")
        
        # Get snapshot ID
        snap_id = None
        metadata_file = f"{test_store}/metadata.json"
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r') as f:
                data = json.load(f)
                if data.get("snapshots"):
                    snap_id = list(data["snapshots"].keys())[0]
                    print(f"    Snapshot ID: {snap_id}")
        
        # Show initial audit log
        audit_log = f"{test_store}/audit.log"
        show_audit_log_preview(audit_log)
        
        # PHASE 2: Switch to auditor role
        print("\n" + "="*60)
        print("2. SWITCH: Changing user role to 'auditor'")
        print("="*60)
        
        # Create policy with user as auditor
        auditor_policy = f"""users:
  {current_user}: auditor
  root: admin
  admin: admin

roles:
  admin:
    - init
    - backup
    - list-snapshots
    - verify
    - restore
    - audit-verify
  
  operator:
    - backup
    - list-snapshots
    - verify
    - restore
    - audit-verify
  
  auditor:
    - list-snapshots
    - verify
    - audit-verify
"""
        
        with open(original_policy, 'w') as f:
            f.write(auditor_policy)
        
        print(f"  Changed user '{current_user}' to 'auditor' role")
        
        # PHASE 3: Test unauthorized commands (should DENY with exit code 1)
        print("\n" + "="*60)
        print("3. TEST: Unauthorized commands (should exit with code 1)")
        print("="*60)
        
        deny_tests = []
        
        # Test backup (should exit with code 1)
        print("\n  a) Testing 'backup' command (should exit 1):")
        result = run_cmd(f"python main.py backup dataset --label 'should-deny'")
        
        if result.returncode == 1:
            print("\n    ✅ DENIED as expected (exit code 1)")
            deny_tests.append(("backup", True))
        else:
            print(f"\n    ❌ Expected exit code 1, got {result.returncode}")
            deny_tests.append(("backup", False))
        
        # Test restore (should exit with code 1)
        if snap_id:
            print(f"\n  b) Testing 'restore' command (should exit 1):")
            restore_dir = os.path.join(test_store, "restore_test")
            result = run_cmd(f"python main.py restore {snap_id} {restore_dir}")
            
            if result.returncode == 1:
                print("\n    ✅ DENIED as expected (exit code 1)")
                deny_tests.append(("restore", True))
            else:
                print(f"\n    ❌ Expected exit code 1, got {result.returncode}")
                deny_tests.append(("restore", False))
        
        # Test init (should exit with code 1)
        print("\n  c) Testing 'init' command (should exit 1):")
        another_store = "./policy_deny_another_store"
        result = run_cmd(f"python main.py init {another_store}")
        
        if result.returncode == 1:
            print("\n    ✅ DENIED as expected (exit code 1)")
            deny_tests.append(("init", True))
        else:
            print(f"\n    ❌ Expected exit code 1, got {result.returncode}")
            deny_tests.append(("init", False))
        
        # Cleanup another store
        if os.path.exists(another_store):
            shutil.rmtree(another_store, ignore_errors=True)
        
        # PHASE 4: Test authorized commands (should succeed with exit code 0)
        print("\n" + "="*60)
        print("4. TEST: Authorized commands (should exit with code 0)")
        print("="*60)
        
        allow_tests = []
        
        # Test list (should succeed)
        print("\n  a) Testing 'list' command (should exit 0):")
        result = run_cmd(f"python main.py list")
        
        if result.returncode == 0:
            print("\n    ✅ ALLOWED as expected (exit code 0)")
            allow_tests.append(("list", True))
        else:
            print(f"\n    ❌ Expected exit code 0, got {result.returncode}")
            allow_tests.append(("list", False))
        
        # Test verify (should succeed)
        if snap_id:
            print(f"\n  b) Testing 'verify' command (should exit 0):")
            result = run_cmd(f"python main.py verify {snap_id}")
            
            if result.returncode == 0:
                print("\n    ✅ ALLOWED as expected (exit code 0)")
                allow_tests.append(("verify", True))
            else:
                print(f"\n    ❌ Expected exit code 0, got {result.returncode}")
                allow_tests.append(("verify", False))
        
        # Test audit-verify (should succeed)
        print("\n  c) Testing 'audit-verify' command (should exit 0):")
        result = run_cmd(f"python main.py audit-verify")
        
        if result.returncode == 0:
            print("\n    ✅ ALLOWED as expected (exit code 0)")
            allow_tests.append(("audit-verify", True))
        else:
            print(f"\n    ❌ Expected exit code 0, got {result.returncode}")
            allow_tests.append(("audit-verify", False))
        
        # PHASE 5: Check audit log
        print("\n" + "="*60)
        print("5. VERIFY: Audit log has DENY entries")
        print("="*60)
        
        if os.path.exists(audit_log):
            with open(audit_log, 'r') as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
            
            print(f"  Total audit entries: {len(lines)}")
            
            # Count DENY entries
            deny_entries = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 7 and parts[6] == "DENY":
                    deny_entries.append({
                        "user": parts[3],
                        "command": parts[4],
                        "args_hash": parts[5][:8] + "..."
                    })
            
            print(f"  DENY entries found: {len(deny_entries)}")
            
            if deny_entries:
                print("\n  ✅ Audit log correctly records DENY status")
                print("\n  Last 2 DENY entries:")
                for i, entry in enumerate(deny_entries[-2:], 1):
                    print(f"    {i}. User: {entry['user']}, Command: {entry['command']}")
            else:
                print("\n  ❌ No DENY entries in audit log")
            
            # Verify audit log integrity
            print("\n  Verifying audit log integrity...")
            result = run_cmd(f"python main.py audit-verify")
            if result.returncode == 0 and "AUDIT OK" in result.stdout:
                print("  ✅ Audit log hash chain is valid")
            else:
                print("  ❌ Audit log corrupted")
        else:
            print("  ❌ Audit log not found")
        
        # Calculate results
        deny_passed = sum(1 for _, passed in deny_tests if passed)
        allow_passed = sum(1 for _, passed in allow_tests if passed)
        
        # PHASE 6: Final results
        print("\n" + "="*60)
        print("📊 FINAL RESULTS")
        print("="*60)
        
        print(f"\n🔴 Unauthorized commands (should exit 1):")
        for cmd, passed in deny_tests:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"    {status} {cmd}")
        
        print(f"\n🟢 Authorized commands (should exit 0):")
        for cmd, passed in allow_tests:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"    {status} {cmd}")
        
        print(f"\n📝 Summary:")
        print(f"    • DENY tests: {deny_passed}/{len(deny_tests)} passed")
        print(f"    • ALLOW tests: {allow_passed}/{len(allow_tests)} passed")
        print(f"    • Audit log DENY entries: {len(deny_entries)} found")
        
        success = (deny_passed == len(deny_tests) and 
                  allow_passed == len(allow_tests) and 
                  len(deny_entries) > 0)
        
        if success:
            print("\n" + "✅" * 20)
            print("✅ POLICY TEST PASSED")
            print("✅" * 20)
            print("\nVerified:")
            print("  1. Unauthorized commands → exit code 1 ✓")
            print("  2. Authorized commands → exit code 0 ✓")  
            print("  3. Audit log records DENY status ✓")
            print("  4. System enforces policy correctly ✓")
        else:
            print("\n" + "❌" * 20)
            print("❌ POLICY TEST FAILED")
            print("❌" * 20)
        
        # Keep the test store
        print(f"\n💾 Test store: {os.path.abspath(test_store)}")
        print("  Commands to verify:")
        print(f"    $ grep DENY {test_store}/audit.log")
        print(f"    $ python main.py audit-verify")
        
        return success
        
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Restore original policy
        if os.path.exists(backup_policy):
            shutil.copy2(backup_policy, original_policy)
            os.remove(backup_policy)
            print(f"\n✓ Restored original policy.yaml")

def main():
    print("🧪 POLICY DENY TEST")
    print("="*60)
    print("  'Nếu USER không tồn tại trong policy hoặc role không cho phép lệnh,")
    print("   chương trình phải: từ chối thực hiện, in thông báo lỗi rõ ràng,")
    print("   và ghi audit log với trạng thái DENY.'")
    print("\n" + "="*60)
    
    # Check dataset
    if not os.path.exists("dataset"):
        print("✗ 'dataset' directory not found")
        sys.exit(1)
    
    # Check store
    test_store = "./policy_deny_test_store"
    if os.path.exists(test_store):
        print(f"⚠️  '{test_store}' already exists")
        response = input("  Delete and recreate? (y/N): ")
        if response.lower() == 'y':
            shutil.rmtree(test_store, ignore_errors=True)
            print("  ✓ Removed")
        else:
            print("  Using existing")
    
    response = input("\nStart test? (y/N): ")
    if response.lower() != 'y':
        print("Test cancelled")
        sys.exit(0)
    
    print("\n" + "="*60)
    success = test_policy_deny_fixed()
    
    if success:
        print("\n🎉 TEST PASSED")
    else:
        print("\n⚠️  TEST FAILED")
    
    print("="*60)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()