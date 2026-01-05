"""
Test cases for Merkle tree implementation
"""
import json
import pytest  # THÊM DÒNG NÀY
from src.merkle import MerkleTree
from src.utils import canonical_json

# XÓA class TestMerkleTree, THAY BẰNG các hàm test đơn giản:

def test_empty_manifest():
    """Test Merkle root for empty manifest"""
    manifest = {"files": []}
    manifest_json = canonical_json(manifest)
    
    root = MerkleTree.compute_merkle_root(manifest_json)
    assert len(root) == 64  # SHA-256 hex digest

def test_single_file():
    """Test Merkle root for single file"""
    manifest = {
        "files": [
            {
                "path": "test.txt",
                "chunks": ["hash1", "hash2", "hash3"]
            }
        ]
    }
    manifest_json = canonical_json(manifest)
    
    root = MerkleTree.compute_merkle_root(manifest_json)
    assert len(root) == 64
    
    # Verify function
    assert MerkleTree.verify_merkle_root(manifest_json, root) == True
    assert MerkleTree.verify_merkle_root(manifest_json, "0" * 64) == False

def test_multiple_files():
    """Test Merkle root for multiple files"""
    manifest = {
        "files": [
            {
                "path": "a.txt",
                "chunks": ["hash_a1", "hash_a2"]
            },
            {
                "path": "b.txt",
                "chunks": ["hash_b1"]
            },
            {
                "path": "c.txt",
                "chunks": ["hash_c1", "hash_c2", "hash_c3"]
            }
        ]
    }
    manifest_json = canonical_json(manifest)
    
    root = MerkleTree.compute_merkle_root(manifest_json)
    assert len(root) == 64
    
    # Deterministic: same manifest → same root
    root2 = MerkleTree.compute_merkle_root(manifest_json)
    assert root == root2

def test_leaf_hash_computation():
    """Test leaf hash computation"""
    file_entry = {
        "path": "folder/file.txt",
        "chunks": ["abc123", "def456"]
    }
    
    leaf_hash = MerkleTree.compute_leaf_hash(file_entry)
    assert len(leaf_hash) == 64
    
    # Different order of chunks should give different hash
    file_entry2 = {
        "path": "folder/file.txt",
        "chunks": ["def456", "abc123"]  # Swapped
    }
    leaf_hash2 = MerkleTree.compute_leaf_hash(file_entry2)
    assert leaf_hash != leaf_hash2

def test_manifest_ordering():
    """Test that file ordering doesn't affect Merkle root due to canonicalization"""
    manifest1 = {
        "files": [
            {"path": "a.txt", "chunks": ["hash1"]},
            {"path": "b.txt", "chunks": ["hash2"]}
        ]
    }

    manifest2 = {
        "files": [
            {"path": "b.txt", "chunks": ["hash2"]},
            {"path": "a.txt", "chunks": ["hash1"]}
        ]
    }

    root1 = MerkleTree.compute_merkle_root(canonical_json(manifest1))
    root2 = MerkleTree.compute_merkle_root(canonical_json(manifest2))

    # Should be SAME because canonical_json sorts by path
    assert root1 == root2
    
    # Also test that canonical_json actually sorts
    manifest1_json = canonical_json(manifest1)
    manifest2_json = canonical_json(manifest2)
    assert manifest1_json == manifest2_json