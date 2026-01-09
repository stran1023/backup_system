#!/usr/bin/env python3
"""
TEST 1: Xoá một số file từ source, restore từ snapshot và so sánh kết quả
Sử dụng CLI command (python main.py) theo đúng logic test_crash.py
"""

import os
import sys
import time
import json
import hashlib
import subprocess
import shutil
import tempfile

def run(cmd):
    """Run command and return output"""
    print(f"$ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr}")
    return result

def get_file_hash(file_path):
    """Tính hash SHA256 của file"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

def compare_directories(dir1, dir2):
    """So sánh hai thư mục - trả về True nếu giống nhau"""
    # Kiểm tra file trong dir1
    for root, dirs, files in os.walk(dir1):
        rel_root = os.path.relpath(root, dir1)
        dir2_root = os.path.join(dir2, rel_root) if rel_root != '.' else dir2
        
        for file in files:
            file1 = os.path.join(root, file)
            file2 = os.path.join(dir2_root, file)
            
            if not os.path.exists(file2):
                print(f"❌ File missing in restored: {os.path.join(rel_root, file)}")
                return False
            
            hash1 = get_file_hash(file1)
            hash2 = get_file_hash(file2)
            
            if hash1 != hash2:
                print(f"❌ Content mismatch: {os.path.join(rel_root, file)}")
                print(f"   Hash1: {hash1[:16]}..., Hash2: {hash2[:16]}...")
                return False
    
    # Kiểm tra file thừa trong dir2
    for root, dirs, files in os.walk(dir2):
        rel_root = os.path.relpath(root, dir2)
        dir1_root = os.path.join(dir1, rel_root) if rel_root != '.' else dir1
        
        for file in files:
            file2 = os.path.join(root, file)
            file1 = os.path.join(dir1_root, file)
            
            if not os.path.exists(file1):
                print(f"❌ Extra file in restored: {os.path.join(rel_root, file)}")
                return False
    
    return True

def extract_snapshot_id(output):
    """Trích xuất snapshot ID từ output"""
    for line in output.split('\n'):
        if "Snapshot ID:" in line:
            parts = line.split(":")
            if len(parts) >= 2:
                return parts[1].strip()
    return None

def test_delete_and_restore():
    print("🧪 TEST 1: Xóa file từ source và restore từ snapshot")
    print("=" * 60)
    
    # 0. Kiểm tra dataset
    dataset = "dataset"
    if not os.path.exists(dataset):
        print(f"❌ Dataset not found: {dataset}")
        print("   Creating test dataset...")
        os.makedirs(dataset, exist_ok=True)
        for i in range(3):
            with open(os.path.join(dataset, f"test_file_{i}.txt"), "w") as f:
                f.write(f"Nội dung file test {i}\n" * 50)
    
    # 1. Setup test store
    store = "./test_delete_restore_store"
    if os.path.exists(store):
        shutil.rmtree(store)
    
    print("\n1. 🏗️ INIT STORE")
    result = run(f"python main.py init {store}")
    if result.returncode != 0:
        print("❌ INIT FAILED")
        return False
    
    # 2. Tạo backup snapshot đầu tiên (trạng thái gốc)
    print("\n2. 💾 CREATE INITIAL SNAPSHOT")
    result = run(f"python main.py backup {dataset} --label 'original-state'")
    if result.returncode != 0:
        print("❌ BACKUP FAILED")
        return False
    
    # Trích xuất snapshot ID
    snapshot_id = extract_snapshot_id(result.stdout)
    if not snapshot_id:
        print("❌ Cannot extract snapshot ID from output")
        return False
    print(f"   Snapshot ID: {snapshot_id}")
    
    # 3. Tạo bản sao của dataset gốc để so sánh sau này
    original_copy = tempfile.mkdtemp(prefix="original_dataset_")
    shutil.copytree(dataset, os.path.join(original_copy, "dataset"), dirs_exist_ok=True)
    
    # 4. Xóa một số file từ dataset gốc
    print("\n3. 🗑️ DELETE SOME FILES FROM SOURCE")
    deleted_files = []
    files = [f for f in os.listdir(dataset) if os.path.isfile(os.path.join(dataset, f))]
    
    if len(files) >= 2:
        # Xóa 2 file đầu tiên
        for i in range(min(2, len(files))):
            file_path = os.path.join(dataset, files[i])
            os.remove(file_path)
            deleted_files.append(files[i])
            print(f"   Deleted: {files[i]}")
    else:
        # Tạo thêm file để xóa
        for i in range(3):
            new_file = os.path.join(dataset, f"new_file_{i}.txt")
            with open(new_file, "w") as f:
                f.write(f"New file content {i}\n" * 30)
        
        # Xóa 1 file
        file_to_delete = os.path.join(dataset, "new_file_0.txt")
        os.remove(file_to_delete)
        deleted_files.append("new_file_0.txt")
        print(f"   Deleted: new_file_0.txt")
    
    # 5. Restore từ snapshot
    print("\n4. 🔄 RESTORE FROM SNAPSHOT")
    restore_dir = "./test_restored_dataset"
    if os.path.exists(restore_dir):
        shutil.rmtree(restore_dir)
    
    result = run(f"python main.py restore {snapshot_id} {restore_dir}")
    if result.returncode != 0:
        print("❌ RESTORE FAILED")
        return False
    
    # 6. So sánh restored với bản gốc (trước khi xóa)
    print("\n5. 🔍 COMPARE RESTORED WITH ORIGINAL")
    original_dataset_path = os.path.join(original_copy, "dataset")
    
    if compare_directories(original_dataset_path, restore_dir):
        print("✅ PASS: Restored directory matches original!")
        
        # Thống kê
        original_files = sum(len(files) for _, _, files in os.walk(original_dataset_path))
        restored_files = sum(len(files) for _, _, files in os.walk(restore_dir))
        print(f"   Original files: {original_files}")
        print(f"   Restored files: {restored_files}")
        print(f"   Files deleted from source: {len(deleted_files)}")
        print(f"   Files restored from snapshot: {len(deleted_files)}")
    else:
        print("❌ FAIL: Restored directory does not match original")
        return False
    
    # 7. Kiểm tra restore không bị ảnh hưởng bởi source đã thay đổi
    print("\n6. ✅ VERIFY RESTORE INDEPENDENCE")
    print("   Source dataset currently has files:")
    current_files = os.listdir(dataset)
    print(f"   {current_files}")
    
    print("   Restored dataset has files:")
    restored_files = os.listdir(restore_dir)
    print(f"   {restored_files}")
    
    # Kiểm tra các file đã xóa có được restore không
    for deleted_file in deleted_files:
        if deleted_file in restored_files:
            print(f"   ✓ Deleted file '{deleted_file}' was restored")
        else:
            print(f"   ✗ Deleted file '{deleted_file}' was NOT restored")
    
    # 8. Cleanup
    print("\n7. 🧹 CLEANUP")
    if os.path.exists(store):
        shutil.rmtree(store, ignore_errors=True)
    if os.path.exists(restore_dir):
        shutil.rmtree(restore_dir, ignore_errors=True)
    if os.path.exists(original_copy):
        shutil.rmtree(original_copy, ignore_errors=True)
    
    print("\n" + "=" * 60)
    print("🎯 TEST 1 COMPLETE: RESTORE AFTER DELETE")
    print("=" * 60)
    print("✅ Requirements verified:")
    print("1. Snapshot created from original dataset ✓")
    print("2. Files deleted from source ✓")
    print("3. Restore successful from snapshot ✓")
    print("4. Restored directory matches original ✓")
    print("5. Restore independent of source changes ✓")
    
    return True

if __name__ == "__main__":
    try:
        success = test_delete_and_restore()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)