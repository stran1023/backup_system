#!/usr/bin/env python3
"""
TEST 3: Sửa manifest/metadata; verify phải fail
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

def modify_manifest_directly(store_path, snapshot_id):
    """
    Sửa trực tiếp manifest file
    """
    manifest_path = os.path.join(store_path, "snapshots", f"{snapshot_id}.manifest")
    
    if not os.path.exists(manifest_path):
        print(f"❌ Manifest not found: {manifest_path}")
        return False
    
    # Đọc manifest
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in manifest")
        return False
    
    print(f"   Original manifest has {len(manifest.get('files', []))} files")
    
    # Sửa manifest: thay đổi size của file đầu tiên
    if manifest.get("files"):
        first_file = manifest["files"][0]
        original_size = first_file.get("size", 0)
        
        # Tăng size lên 100 bytes
        new_size = original_size + 100
        first_file["size"] = new_size
        
        print(f"   Modified file size: {original_size} → {new_size}")
        
        # Hoặc thêm file giả
        # fake_file = {
        #     "path": "fake_file.txt",
        #     "chunks": ["fake_chunk_hash"],
        #     "size": 100
        # }
        # manifest["files"].append(fake_file)
        # print(f"   Added fake file entry")
    
    # Ghi lại manifest
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    return True

def modify_metadata_directly(store_path, snapshot_id):
    """
    Sửa trực tiếp metadata
    """
    metadata_path = os.path.join(store_path, "metadata.json")
    
    if not os.path.exists(metadata_path):
        print(f"❌ Metadata not found: {metadata_path}")
        return False
    
    # Đọc metadata
    try:
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in metadata")
        return False
    
    # Tìm và sửa snapshot metadata
    if snapshot_id in metadata.get("snapshots", {}):
        snap_meta = metadata["snapshots"][snapshot_id]
        
        # Sửa Merkle root
        original_root = snap_meta.get("merkle_root", "")
        if original_root and len(original_root) == 64:  # SHA256 hex
            # Đảo ngược 2 ký tự cuối
            new_root = original_root[:-2] + original_root[-1] + original_root[-2]
            snap_meta["merkle_root"] = new_root
            print(f"   Modified Merkle root: {original_root[:8]}... → {new_root[:8]}...")
        
        # Hoặc sửa label
        original_label = snap_meta.get("label", "")
        snap_meta["label"] = f"MODIFIED_{original_label}"
        print(f"   Modified label: {original_label} → {snap_meta['label']}")
    
    # Ghi lại metadata
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    return True

def test_modify_manifest_metadata():
    print("🧪 TEST 3: Sửa manifest/metadata - verify phải fail")
    print("=" * 60)
    
    # 0. Kiểm tra dataset
    dataset = "dataset"
    if not os.path.exists(dataset):
        print(f"Creating test dataset...")
        os.makedirs(dataset, exist_ok=True)
        for i in range(3):
            with open(os.path.join(dataset, f"file_{i}.txt"), "w") as f:
                f.write(f"Test content for file {i}\n" * 50)
    
    # 1. Setup test store
    store = "./test_manifest_corruption_store"
    if os.path.exists(store):
        shutil.rmtree(store)
    
    print("\n1. 🏗️ INIT STORE")
    result = run(f"python main.py init {store}")
    if result.returncode != 0:
        print("❌ INIT FAILED")
        return False
    
    # 2. Tạo backup snapshot
    print("\n2. 💾 CREATE SNAPSHOT")
    result = run(f"python main.py backup {dataset} --label 'integrity-test'")
    if result.returncode != 0:
        print("❌ BACKUP FAILED")
        return False
    
    # Trích xuất snapshot ID
    snapshot_id = extract_snapshot_id(result.stdout)
    if not snapshot_id:
        print("❌ Cannot extract snapshot ID")
        return False
    print(f"   Snapshot ID: {snapshot_id}")
    
    # 3. TEST A: Sửa manifest file
    print("\n3. 🔧 TEST A: MODIFY MANIFEST FILE")
    
    # Verify trước khi sửa
    print("   a) Verify before modification (expected: PASS)")
    result = run(f"python main.py verify {snapshot_id}")
    if "VALID" in result.stdout:
        print("     ✓ Verify passed (correct)")
    else:
        print("     ✗ Verify failed (unexpected)")
        return False
    
    # Sửa manifest
    print("   b) Modifying manifest file...")
    if not modify_manifest_directly(store, snapshot_id):
        print("     ✗ Failed to modify manifest")
        return False
    
    # Verify sau khi sửa manifest
    print("   c) Verify after manifest modification (expected: FAIL)")
    result = run(f"python main.py verify {snapshot_id}")
    
    if "INVALID" in result.stdout or result.returncode != 0:
        print("     ✓ Verify failed after manifest modification (correct)")
        for line in result.stdout.split('\n'):
            if "Reason:" in line or "mismatch" in line:
                print(f"     Reason: {line.strip()}")
    else:
        print("     ✗ Verify passed after manifest modification (incorrect)")
        return False
    
    # 4. TEST B: Sửa metadata (cần snapshot mới vì cái cũ đã hỏng)
    print("\n4. 🔧 TEST B: MODIFY METADATA")
    
    # Tạo snapshot mới
    print("   a) Create new snapshot for metadata test...")
    result = run(f"python main.py backup {dataset} --label 'metadata-test'")
    if result.returncode != 0:
        print("     ✗ Failed to create new snapshot")
        return False
    
    snapshot_id2 = extract_snapshot_id(result.stdout)
    print(f"     New Snapshot ID: {snapshot_id2}")
    
    # Verify snapshot mới trước khi sửa
    print("   b) Verify new snapshot before modification...")
    result = run(f"python main.py verify {snapshot_id2}")
    if "VALID" in result.stdout:
        print("     ✓ New snapshot is valid")
    else:
        print("     ✗ New snapshot is invalid")
        return False
    
    # Sửa metadata
    print("   c) Modifying metadata...")
    if not modify_metadata_directly(store, snapshot_id2):
        print("     ✗ Failed to modify metadata")
        return False
    
    # Verify sau khi sửa metadata
    print("   d) Verify after metadata modification (expected: FAIL)")
    result = run(f"python main.py verify {snapshot_id2}")
    
    if "INVALID" in result.stdout or result.returncode != 0:
        print("     ✓ Verify failed after metadata modification (correct)")
        for line in result.stdout.split('\n'):
            if "Reason:" in line or "mismatch" in line:
                print(f"     Reason: {line.strip()}")
    else:
        print("     ✗ Verify passed after metadata modification (incorrect)")
        return False
    
    # 5. TEST C: Sửa cả manifest và metadata của snapshot thứ 3
    print("\n5. 🔧 TEST C: MODIFY BOTH MANIFEST AND METADATA")
    
    # Tạo snapshot thứ 3
    print("   a) Create third snapshot...")
    result = run(f"python main.py backup {dataset} --label 'comprehensive-test'")
    if result.returncode != 0:
        print("     ✗ Failed to create third snapshot")
        return False
    
    snapshot_id3 = extract_snapshot_id(result.stdout)
    print(f"     Third Snapshot ID: {snapshot_id3}")
    
    # Sửa cả manifest và metadata
    print("   b) Modifying both manifest and metadata...")
    modify_manifest_directly(store, snapshot_id3)
    modify_metadata_directly(store, snapshot_id3)
    
    # Verify
    print("   c) Verify after both modifications (expected: FAIL)")
    result = run(f"python main.py verify {snapshot_id3}")
    
    if "INVALID" in result.stdout or result.returncode != 0:
        print("     ✓ Verify failed after both modifications (correct)")
    else:
        print("     ✗ Verify passed after both modifications (incorrect)")
        return False
    
    # 6. Kiểm tra hệ thống vẫn có thể tạo snapshot mới
    print("\n6. 🔄 SYSTEM RECOVERY TEST")
    result = run(f"python main.py backup {dataset} --label 'recovery-test'")
    if result.returncode != 0:
        print("   ✗ Failed to create new snapshot after corruption")
        return False
    
    snapshot_id4 = extract_snapshot_id(result.stdout)
    print(f"   ✓ New snapshot created: {snapshot_id4}")
    
    # Verify snapshot mới
    result = run(f"python main.py verify {snapshot_id4}")
    if "VALID" in result.stdout:
        print("   ✓ New snapshot is valid")
    else:
        print("   ✗ New snapshot is invalid")
    
    # 7. Cleanup
    print("\n7. 🧹 CLEANUP")
    if os.path.exists(store):
        shutil.rmtree(store, ignore_errors=True)
    
    print("\n" + "=" * 60)
    print("🎯 TEST 3 COMPLETE: MANIFEST/METADATA CORRUPTION DETECTION")
    print("=" * 60)
    print("✅ Requirements verified:")
    print("1. Manifest modification detected ✓")
    print("2. Metadata modification detected ✓")
    print("3. Combined modification detected ✓")
    print("4. System can recover and create new snapshots ✓")
    
    return True

if __name__ == "__main__":
    try:
        success = test_modify_manifest_metadata()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)