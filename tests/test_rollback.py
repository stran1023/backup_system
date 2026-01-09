#!/usr/bin/env python3
"""
Manual rollback test script
Run: python test_rollback.py
"""

import os
import json
import subprocess
import sys
import time

def run_command(cmd):
    """Run shell command and return output"""
    print(f"$ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(f"ERROR: {result.stderr}")
    return result

def test_rollback_detection():
    """Test rollback detection manually"""
    print("=== ROLLBACK DETECTION TEST ===\n")
    
    # 1. Setup test store
    store = "./test_rollback"
    if os.path.exists(store):
        run_command(f"rm -rf {store}")

    print("\n1. INIT STORE")
    run_command(f"python main.py init {store}")

    # 1. Tạo 2 snapshot
    print("1. Creating two snapshots...")
    
    # Snapshot 1
    result = run_command("python main.py backup dataset --label 'before-rollback'")
    if result.returncode != 0:
        print("Failed to create snapshot 1")
        return False
    
    # Lấy snapshot ID từ output (giả sử output có format)
    # Hoặc đọc từ metadata.json
    with open(f"{store}/metadata.json", "r") as f:
        metadata = json.load(f)
    
    snapshots = list(metadata["snapshots"].keys())
    if len(snapshots) < 2:
        # Tạo snapshot thứ 2 nếu cần
        time.sleep(1)  # Đảm bảo timestamp khác
        result = run_command("python main.py backup dataset --label 'after-rollback'")
        if result.returncode != 0:
            print("Failed to create snapshot 2")
            return False
        
        with open(f"{store}/metadata.json", "r") as f:
            metadata = json.load(f)
        snapshots = list(metadata["snapshots"].keys())
    
    if len(snapshots) < 2:
        print("Need at least 2 snapshots for rollback test")
        return False
    
    snap1_id = snapshots[-2]  # Snapshot cũ hơn
    snap2_id = snapshots[-1]  # Snapshot mới nhất
    
    print(f"Snapshot 1: {snap1_id}")
    print(f"Snapshot 2: {snap2_id}")
    
    # 2. Verify cả 2 trước khi rollback
    print("\n2. Verifying before rollback...")
    result = run_command(f"python main.py verify {snap1_id}")
    valid1 = result.returncode == 0
    
    result = run_command(f"python main.py verify {snap2_id}")
    valid2 = result.returncode == 0
    
    if not (valid1 and valid2):
        print("Snapshots not valid before rollback test")
        return False
    
    print("✓ Both snapshots valid initially")
    
    # 3. Backup metadata
    print("\n3. Backing up metadata...")
    run_command(f"cp {store}/metadata.json {store}/metadata.json.backup")

    # 4. Thực hiện rollback attack
    print("\n4. Performing rollback attack...")
    print("   Modifying snapshot 2 metadata...")

    with open(f"{store}/metadata.json", "r") as f:
        metadata = json.load(f)
    
    # Lấy merkle_root của snapshot 1
    snap1_root = metadata["snapshots"][snap1_id]["merkle_root"]
    
    # ROLLBACK: làm cho snapshot 2 trỏ về genesis (0*64) thay vì snapshot 1
    metadata["snapshots"][snap2_id]["prev_root"] = "0" * 64
    
    # Cũng cần sửa chain_hash để consistency (nhưng vẫn sai)
    # Tính chain_hash sai
    import hashlib
    wrong_chain_data = f"{'0'*64}{metadata['snapshots'][snap2_id]['merkle_root']}{'0'*64}"
    wrong_chain_hash = hashlib.sha256(wrong_chain_data.encode()).hexdigest()
    metadata["snapshots"][snap2_id]["chain_hash"] = wrong_chain_hash
    
    # Save metadata đã sửa
    with open(f"{store}/metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    
    print(f"   Changed prev_root of {snap2_id} from {snap1_root[:16]}... to {'0'*64}")
    
    # 5. Verify sau rollback
    print("\n5. Verifying after rollback...")
    result = run_command(f"python main.py verify {snap2_id}")
    
    if "is VALID" in result.stdout:
        print("\n✗ TEST FAILED: Rollback NOT detected!")
        print("  Snapshot verified successfully after rollback attack")
        test_passed = False
    elif "is INVALID" in result.stdout and "Rollback detected" in result.stdout:
        print("\n✓ TEST PASSED: Rollback detected!")
        print(f"  Error message: {result.stdout}")
        test_passed = True
    else:
        print("\n? UNEXPECTED RESULT")
        print(f"  Output: {result.stdout}")
        test_passed = False
    
    # 6. Khôi phục metadata
    print("\n6. Restoring original metadata...")
    run_command(f"cp {store}/metadata.json.backup {store}/metadata.json")

    # Verify lại để đảm bảo system vẫn hoạt động
    result = run_command(f"python main.py verify {snap2_id}")
    if result.returncode == 0:
        print("✓ System recovered successfully")
    else:
        print("✗ System recovery failed")
    
    return test_passed

def main():
    """Main test function"""
    
    if not os.path.exists("dataset"):
        print("Error: Dataset directory not found")
        sys.exit(1)
    
    print("This test will simulate a rollback attack and verify detection.")
    print("It will modify metadata.json to simulate an attacker replacing")
    print("a new snapshot with an older one.\n")
    
    input("Press Enter to continue (or Ctrl+C to cancel)...")
    
    try:
        passed = test_rollback_detection()
        
        print("\n" + "="*50)
        if passed:
            print("✓ ROLLBACK DETECTION TEST: PASSED")
            print("  Your system correctly detects rollback attacks!")
        else:
            print("✗ ROLLBACK DETECTION TEST: FAILED")
            print("  Your system does NOT detect rollback attacks.")
            print("  Check your _check_rollback() implementation.")
        print("="*50)
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        # Khôi phục metadata nếu có lỗi
        if os.path.exists("store/metadata.json.backup"):
            run_command("cp store/metadata.json.backup store/metadata.json")
        sys.exit(1)

if __name__ == "__main__":
    main()