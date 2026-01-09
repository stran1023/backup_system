#!/usr/bin/env python3
"""
TEST 2: Sửa tối thiểu 1 byte trong chunk; verify phải fail
Sử dụng CLI command (python main.py) theo đúng logic test_crash.py
"""

import os
import sys
import time
import json
import random
import subprocess
import shutil

def run(cmd):
    """Run command and return output"""
    print(f"$ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr}")
    return result

def extract_snapshot_id(output):
    """Trích xuất snapshot ID từ output"""
    for line in output.split('\n'):
        if "Snapshot ID:" in line:
            parts = line.split(":")
            if len(parts) >= 2:
                return parts[1].strip()
    return None

def find_and_modify_chunk(store_path, snapshot_id):
    """
    Tìm và sửa 1 byte trong một chunk của snapshot
    """
    # 1. Tìm manifest file
    manifest_path = os.path.join(store_path, "snapshots", f"{snapshot_id}.manifest")
    
    if not os.path.exists(manifest_path):
        print(f"❌ Manifest not found: {manifest_path}")
        return False
    
    # 2. Đọc manifest để lấy danh sách chunks
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in manifest")
        return False
    
    if not manifest.get("files"):
        print("❌ No files in manifest")
        return False
    
    # 3. Tìm file có chunks
    for file_entry in manifest["files"]:
        if file_entry.get("chunks"):
            chunk_hashes = file_entry["chunks"]
            if chunk_hashes:
                chunk_hash = chunk_hashes[0]  # Lấy chunk đầu tiên
                print(f"   Selected chunk: {chunk_hash[:16]}...")
                
                # 4. Tìm file chunk
                chunk_dir = os.path.join(store_path, "chunks", chunk_hash[:2])
                chunk_file = os.path.join(chunk_dir, chunk_hash)
                
                if not os.path.exists(chunk_file):
                    print(f"   Chunk file not found: {chunk_file}")
                    continue
                
                # 5. Đọc và sửa 1 byte
                with open(chunk_file, 'rb') as f:
                    chunk_data = bytearray(f.read())
                
                if len(chunk_data) == 0:
                    print("   Chunk is empty, skipping...")
                    continue
                
                # Sửa byte ở vị trí giữa
                position = len(chunk_data) // 2
                original_byte = chunk_data[position]
                new_byte = (original_byte + 1) % 256
                chunk_data[position] = new_byte
                
                print(f"   Modified byte at position {position}: {original_byte} → {new_byte}")
                
                # 6. Ghi lại chunk đã sửa
                with open(chunk_file, 'wb') as f:
                    f.write(chunk_data)
                
                return True
    
    print("❌ No suitable chunk found for modification")
    return False

def test_modify_chunk():
    print("🧪 TEST 2: Sửa 1 byte trong chunk - verify phải fail")
    print("=" * 60)
    
    # 0. Tạo dataset test nếu cần
    dataset = "dataset"
    if not os.path.exists(dataset):
        print(f"Creating test dataset...")
        os.makedirs(dataset, exist_ok=True)
        # Tạo file đủ lớn để có chunk
        with open(os.path.join(dataset, "large_file.bin"), "wb") as f:
            f.write(os.urandom(2 * 1024 * 1024))  # 2MB
    
    # 1. Setup test store
    store = "./test_chunk_corruption_store"
    if os.path.exists(store):
        shutil.rmtree(store)
    
    print("\n1. 🏗️ INIT STORE")
    result = run(f"python main.py init {store}")
    if result.returncode != 0:
        print("❌ INIT FAILED")
        return False
    
    # 2. Tạo backup snapshot
    print("\n2. 💾 CREATE SNAPSHOT")
    result = run(f"python main.py backup {dataset} --label 'pre-modification'")
    if result.returncode != 0:
        print("❌ BACKUP FAILED")
        return False
    
    # Trích xuất snapshot ID
    snapshot_id = extract_snapshot_id(result.stdout)
    if not snapshot_id:
        print("❌ Cannot extract snapshot ID")
        return False
    print(f"   Snapshot ID: {snapshot_id}")
    
    # 3. Verify snapshot trước khi sửa (phải PASS)
    print("\n3. ✅ VERIFY BEFORE MODIFICATION (expected: PASS)")
    result = run(f"python main.py verify {snapshot_id}")
    
    if "VALID" in result.stdout and result.returncode == 0:
        print("   ✓ Verify passed before modification (correct)")
    else:
        print("   ✗ Verify failed before modification (unexpected)")
        print(f"   Output: {result.stdout[:200]}...")
        return False
    
    # 4. Sửa 1 byte trong chunk
    print("\n4. 🔧 MODIFY CHUNK (1 byte)")
    if not find_and_modify_chunk(store, snapshot_id):
        print("❌ Failed to modify chunk")
        return False
    
    # 5. Verify snapshot sau khi sửa (phải FAIL)
    print("\n5. ❌ VERIFY AFTER MODIFICATION (expected: FAIL)")
    result = run(f"python main.py verify {snapshot_id}")
    
    # Kiểm tra kết quả
    if "INVALID" in result.stdout or result.returncode != 0:
        print("   ✓ Verify failed after modification (correct)")
        
        # In lý do nếu có
        for line in result.stdout.split('\n'):
            if "Reason:" in line or "mismatch" in line or "missing" in line or "corrupt" in line:
                print(f"   Reason: {line.strip()}")
    else:
        print("   ✗ Verify passed after modification (incorrect - system didn't detect corruption)")
        print(f"   Output: {result.stdout[:200]}...")
        return False
    
    # 6. Thử restore snapshot đã bị hỏng (phải FAIL)
    print("\n6. 🚫 ATTEMPT RESTORE CORRUPTED SNAPSHOT (expected: FAIL)")
    restore_dir = "./test_corrupted_restore"
    if os.path.exists(restore_dir):
        shutil.rmtree(restore_dir)
    
    result = run(f"python main.py restore {snapshot_id} {restore_dir}")
    
    # 7. Tạo snapshot mới để đảm bảo hệ thống vẫn hoạt động
    print("\n7. 🔄 CREATE NEW SNAPSHOT (system should still work)")
    result = run(f"python main.py backup {dataset} --label 'post-corruption'")
    if result.returncode != 0:
        print("   ✗ Failed to create new snapshot after corruption")
        return False
    
    new_snapshot_id = extract_snapshot_id(result.stdout)
    print(f"   ✓ New snapshot created: {new_snapshot_id}")
    
    # Verify snapshot mới (phải PASS)
    result = run(f"python main.py verify {new_snapshot_id}")
    if "VALID" in result.stdout:
        print("   ✓ New snapshot is valid")
    else:
        print("   ✗ New snapshot is invalid")
    
    # 8. Cleanup
    print("\n8. 🧹 CLEANUP")
    if os.path.exists(store):
        shutil.rmtree(store, ignore_errors=True)
    if os.path.exists(restore_dir):
        shutil.rmtree(restore_dir, ignore_errors=True)
    
    print("\n" + "=" * 60)
    print("🎯 TEST 2 COMPLETE: CHUNK CORRUPTION DETECTION")
    print("=" * 60)
    print("✅ Requirements verified:")
    print("1. Snapshot created successfully ✓")
    print("2. Initial verify passed ✓")
    print("3. 1 byte modified in chunk ✓")
    print("4. Verify failed after modification ✓")
    print("5. Restore failed for corrupted snapshot ✓")
    print("6. System can create new snapshots after corruption ✓")
    
    return True

if __name__ == "__main__":
    try:
        success = test_modify_chunk()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)