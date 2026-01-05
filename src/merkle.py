"""
Merkle tree implementation for snapshot integrity verification
"""
import hashlib
import json
from typing import List, Dict, Any

class MerkleTree:
    """Merkle Tree implementation for snapshot verification"""
    
    @staticmethod
    def compute_leaf_hash(file_entry: Dict[str, Any]) -> str:
        """
        Compute leaf hash for a file entry
        Format: "path|chunk1,chunk2,..."
        """
        path = file_entry["path"]
        chunks_str = ",".join(file_entry["chunks"])
        data = f"{path}|{chunks_str}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    @staticmethod
    def compute_merkle_root(manifest_json: str) -> str:
        """
        Compute Merkle root from canonical manifest JSON
        """
        try:
            manifest = json.loads(manifest_json)
        except json.JSONDecodeError:
            raise ValueError("Invalid manifest JSON")
        
        # Get leaf hashes
        leaf_hashes = []
        for file_entry in manifest.get("files", []):
            leaf_hash = MerkleTree.compute_leaf_hash(file_entry)
            leaf_hashes.append(leaf_hash)
        
        # Handle empty directory
        if not leaf_hashes:
            return hashlib.sha256(b"").hexdigest()
        
        # Build Merkle tree
        return MerkleTree._build_tree(leaf_hashes)
    
    @staticmethod
    def _build_tree(hashes: List[str]) -> str:
        """Recursively build Merkle tree"""
        if len(hashes) == 1:
            return hashes[0]
        
        next_level = []
        for i in range(0, len(hashes), 2):
            if i + 1 < len(hashes):
                # Pair: hash(left + right)
                pair_data = hashes[i] + hashes[i + 1]
            else:
                # Odd number: duplicate last hash
                pair_data = hashes[i] + hashes[i]
            
            pair_hash = hashlib.sha256(pair_data.encode()).hexdigest()
            next_level.append(pair_hash)
        
        return MerkleTree._build_tree(next_level)
    
    @staticmethod
    def verify_merkle_root(manifest_json: str, expected_root: str) -> bool:
        """Verify manifest against expected Merkle root"""
        computed_root = MerkleTree.compute_merkle_root(manifest_json)
        return computed_root == expected_root