#!/usr/bin/env python3
"""
Simple test script without pytest dependency
"""
import os
import sys
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.storage import ChunkStorage, SnapshotManager
from src.merkle import MerkleTree
from src.utils import canonical_json, CHUNK_SIZE

def test_chunk_storage():
    """Test ChunkStorage"""
    print("Testing ChunkStorage...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ChunkStorage(tmpdir)
        
        # Test 1: Store and retrieve
        data = b"Hello, World!" * 100
        hash1 = storage.store_chunk(data)
        
        retrieved = storage.get_chunk(hash1)
        assert retrieved == data, "Retrieved data doesn't match"
        print("  ✓ Store and retrieve")
        
        # Test 2: Deduplication
        hash2 = storage.store_chunk(data)
        assert hash1 == hash2, "Deduplication failed"
        print("  ✓ Deduplication")
        
        # Test 3: Existence check
        assert storage.chunk_exists(hash1), "Chunk should exist"
        assert not storage.chunk_exists("fake" * 16), "Fake chunk shouldn't exist"
        print("  ✓ Existence check")
        
    print("ChunkStorage tests passed!\n")

def test_merkle_tree():
    """Test MerkleTree"""
    print("Testing MerkleTree...")
    
    # Test empty manifest
    manifest = {"files": []}
    manifest_json = canonical_json(manifest)
    root = MerkleTree.compute_merkle_root(manifest_json)
    assert len(root) == 64, "Root should be 64 chars"
    print("  ✓ Empty manifest")
    
    # Test with files
    manifest = {
        "files": [
            {"path": "file1.txt", "chunks": ["hash1", "hash2"]},
            {"path": "file2.txt", "chunks": ["hash3"]}
        ]
    }
    manifest_json = canonical_json(manifest)
    root = MerkleTree.compute_merkle_root(manifest_json)
    assert len(root) == 64, "Root should be 64 chars"
    
    # Verify
    assert MerkleTree.verify_merkle_root(manifest_json, root), "Verification should pass"
    assert not MerkleTree.verify_merkle_root(manifest_json, "0" * 64), "Wrong root should fail"
    print("  ✓ Manifest with files")
    
    print("MerkleTree tests passed!\n")

def test_snapshot_manager():
    """Test SnapshotManager"""
    print("Testing SnapshotManager...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = os.path.join(tmpdir, "data")
        store_dir = os.path.join(tmpdir, "store")
        
        os.makedirs(data_dir)
        os.makedirs(os.path.join(data_dir, "sub"))
        
        # Create test files
        with open(os.path.join(data_dir, "test.txt"), "w") as f:
            f.write("Test content")
        
        with open(os.path.join(data_dir, "sub", "nested.txt"), "w") as f:
            f.write("Nested content")
        
        # Create snapshot
        storage = ChunkStorage(store_dir)
        manager = SnapshotManager(storage)
        
        snapshot = manager.create_snapshot(data_dir, "test")
        
        assert "id" in snapshot
        assert "merkle_root" in snapshot
        assert snapshot["total_files"] == 2
        print("  ✓ Snapshot creation")
        
        # Verify
        is_valid, message = manager.verify_snapshot(snapshot["id"])
        assert is_valid, f"Snapshot should be valid: {message}"
        print("  ✓ Snapshot verification")
        
        # List
        snapshots = manager.list_snapshots()
        assert len(snapshots) == 1
        print("  ✓ List snapshots")
    
    print("SnapshotManager tests passed!\n")

def main():
    """Run all tests"""
    print("=" * 60)
    print("Running Simple Tests")
    print("=" * 60)
    
    tests = [
        ("ChunkStorage", test_chunk_storage),
        ("MerkleTree", test_merkle_tree),
        ("SnapshotManager", test_snapshot_manager),
    ]
    
    passed = 0
    total = len(tests)
    
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
            print(f"✓ {name} PASSED\n")
        except Exception as e:
            print(f"✗ {name} FAILED: {e}\n")
    
    print("=" * 60)
    print(f"Results: {passed}/{total} test suites passed")
    print("=" * 60)
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)