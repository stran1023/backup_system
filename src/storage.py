"""
Storage engine for chunk storage and snapshot management
"""
import os
import json
import time
from typing import Dict, List, Tuple
from .utils import (
    CHUNK_SIZE, compute_hash, read_file_in_chunks, 
    ensure_dir, canonical_json
)
from .merkle import MerkleTree
from .exceptions import IntegrityError, SnapshotNotFoundError

class ChunkStorage:
    """Content-addressable storage for file chunks"""
    
    def __init__(self, store_path: str):
        self.store_path = store_path
        self.chunks_dir = os.path.join(store_path, "chunks")
        self.snapshots_dir = os.path.join(store_path, "snapshots")
        self.metadata_file = os.path.join(store_path, "metadata.json")
        
        ensure_dir(self.chunks_dir)
        ensure_dir(self.snapshots_dir)
    
    def _chunk_path(self, chunk_hash: str) -> str:
        """Get file path for a chunk"""
        # Use first 2 chars as directory for better distribution
        prefix = chunk_hash[:2]
        dir_path = os.path.join(self.chunks_dir, prefix)
        ensure_dir(dir_path)
        return os.path.join(dir_path, chunk_hash)
    
    def store_chunk(self, chunk_data: bytes) -> str:
        """
        Store chunk and return its hash
        Deduplication: if chunk already exists, just return hash
        """
        chunk_hash = compute_hash(chunk_data)
        chunk_path = self._chunk_path(chunk_hash)
        
        # Deduplication: only store if not exists
        if not os.path.exists(chunk_path):
            # Write to temp file first, then rename atomically
            temp_path = chunk_path + ".tmp"
            with open(temp_path, 'wb') as f:
                f.write(chunk_data)
            os.rename(temp_path, chunk_path)
        
        return chunk_hash
    
    def get_chunk(self, chunk_hash: str) -> bytes:
        """Retrieve chunk data by hash"""
        chunk_path = self._chunk_path(chunk_hash)
        if not os.path.exists(chunk_path):
            raise IntegrityError(f"Chunk not found: {chunk_hash}")
        
        with open(chunk_path, 'rb') as f:
            return f.read()
    
    def chunk_exists(self, chunk_hash: str) -> bool:
        """Check if chunk exists"""
        chunk_path = self._chunk_path(chunk_hash)
        return os.path.exists(chunk_path)

class SnapshotManager:
    """Manages snapshot creation and retrieval"""
    
    def __init__(self, storage: ChunkStorage):
        self.storage = storage
        self.metadata = self._load_metadata()
    
    def _load_metadata(self) -> Dict:
        """Load metadata from file"""
        if not os.path.exists(self.storage.metadata_file):
            return {
                "snapshots": {},
                "latest_snapshot": None,
                "prev_root_chain": []
            }
        
        with open(self.storage.metadata_file, 'r') as f:
            return json.load(f)
    
    def _save_metadata(self) -> None:
        """Save metadata to file atomically"""
        temp_file = self.storage.metadata_file + ".tmp"
        with open(temp_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)
        os.rename(temp_file, self.storage.metadata_file)
    
    def create_snapshot(self, source_path: str, label: str = "") -> Dict:
        """
        Create a new snapshot of source directory
        Returns: snapshot metadata
        """
        source_path = os.path.abspath(source_path)
        if not os.path.exists(source_path):
            raise ValueError(f"Source path does not exist: {source_path}")
        
        snapshot_id = f"snap_{int(time.time())}_{compute_hash(str(time.time_ns()).encode())[:8]}"
        
        # Collect file data
        files_data = {}
        total_chunks = 0
        
        for root, dirs, files in os.walk(source_path):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, source_path)
                
                # Read file and chunk it
                chunk_hashes = []
                for chunk in read_file_in_chunks(file_path):
                    chunk_hash = self.storage.store_chunk(chunk)
                    chunk_hashes.append(chunk_hash)
                    total_chunks += 1
                
                files_data[rel_path] = chunk_hashes
        
        # Create manifest
        manifest = {
            "version": 1,
            "snapshot_id": snapshot_id,
            "source_path": source_path,
            "created_at": time.time(),
            "label": label,
            "files": [
                {
                    "path": path,
                    "chunks": chunks,
                    "size": len(chunks) * CHUNK_SIZE
                }
                for path, chunks in sorted(files_data.items())
            ]
        }
        
        # Compute Merkle root
        manifest_json = canonical_json(manifest)
        merkle_root = MerkleTree.compute_merkle_root(manifest_json)
        
        # Get previous root for chain
        prev_root = self.metadata.get("latest_snapshot_root")
        if prev_root is None:
            prev_root = "0" * 64  # Genesis hash
        
        # Save manifest
        manifest_hash = compute_hash(manifest_json.encode())
        manifest_path = os.path.join(self.storage.snapshots_dir, f"{snapshot_id}.manifest")
        with open(manifest_path, 'w') as f:
            f.write(manifest_json)
        
        # Update metadata
        snapshot_metadata = {
            "id": snapshot_id,
            "created_at": time.time(),
            "label": label,
            "merkle_root": merkle_root,
            "prev_root": prev_root,
            "manifest_hash": manifest_hash,
            "total_files": len(files_data),
            "total_chunks": total_chunks
        }
        
        self.metadata["snapshots"][snapshot_id] = snapshot_metadata
        self.metadata["latest_snapshot"] = snapshot_id
        self.metadata["latest_snapshot_root"] = merkle_root
        self.metadata["prev_root_chain"].append(merkle_root)
        
        self._save_metadata()
        
        return snapshot_metadata
    
    def get_snapshot(self, snapshot_id: str) -> Dict:
        """Get snapshot metadata"""
        if snapshot_id not in self.metadata["snapshots"]:
            raise SnapshotNotFoundError(f"Snapshot not found: {snapshot_id}")
        
        return self.metadata["snapshots"][snapshot_id]
    
    def get_snapshot_manifest(self, snapshot_id: str) -> Dict:
        """Get snapshot manifest"""
        manifest_path = os.path.join(self.storage.snapshots_dir, f"{snapshot_id}.manifest")
        if not os.path.exists(manifest_path):
            raise SnapshotNotFoundError(f"Manifest not found for snapshot: {snapshot_id}")
        
        with open(manifest_path, 'r') as f:
            return json.load(f)
    
    def list_snapshots(self) -> List[Dict]:
        """List all snapshots"""
        snapshots = []
        for snap_id, metadata in self.metadata["snapshots"].items():
            snapshots.append({
                "id": snap_id,
                "created_at": metadata["created_at"],
                "label": metadata.get("label", ""),
                "merkle_root": metadata["merkle_root"],
                "total_files": metadata["total_files"],
                "total_chunks": metadata["total_chunks"]
            })
        
        # Sort by creation time (newest first)
        return sorted(snapshots, key=lambda x: x["created_at"], reverse=True)
    
    def verify_snapshot(self, snapshot_id: str) -> Tuple[bool, str]:
        """
        Verify snapshot integrity
        Returns: (is_valid, message)
        """
        try:
            metadata = self.get_snapshot(snapshot_id)
            manifest = self.get_snapshot_manifest(snapshot_id)
            
            # Verify Merkle root
            manifest_json = canonical_json(manifest)
            computed_root = MerkleTree.compute_merkle_root(manifest_json)
            
            if computed_root != metadata["merkle_root"]:
                return False, "Merkle root mismatch"
            
            # Verify chunk existence
            for file_entry in manifest["files"]:
                for chunk_hash in file_entry["chunks"]:
                    if not self.storage.chunk_exists(chunk_hash):
                        return False, f"Missing chunk: {chunk_hash}"
            
            # Verify rollback protection
            if self._check_rollback(snapshot_id):
                return False, "Rollback detected"
            
            return True, "Snapshot is valid"
            
        except Exception as e:
            return False, f"Verification failed: {str(e)}"
    
    def _check_rollback(self, snapshot_id: str) -> bool:
        """Check for rollback attacks"""
        metadata = self.get_snapshot(snapshot_id)
        
        # Get chain position
        root_chain = self.metadata.get("prev_root_chain", [])
        if metadata["merkle_root"] in root_chain:
            index = root_chain.index(metadata["merkle_root"])
            # Check if this is the latest occurrence
            last_index = len(root_chain) - 1 - root_chain[::-1].index(metadata["merkle_root"])
            return index != last_index
        
        return False
    
    def restore_snapshot(self, snapshot_id: str, target_path: str) -> None:
        """
        Restore snapshot to target directory
        """
        # Verify snapshot first
        is_valid, message = self.verify_snapshot(snapshot_id)
        if not is_valid:
            raise IntegrityError(f"Cannot restore invalid snapshot: {message}")
        
        manifest = self.get_snapshot_manifest(snapshot_id)
        
        # Clean target directory
        ensure_dir(target_path)
        
        # Restore files
        for file_entry in manifest["files"]:
            file_path = os.path.join(target_path, file_entry["path"])
            file_dir = os.path.dirname(file_path)
            ensure_dir(file_dir)
            
            # Reconstruct file from chunks
            with open(file_path, 'wb') as f:
                for chunk_hash in file_entry["chunks"]:
                    chunk_data = self.storage.get_chunk(chunk_hash)
                    f.write(chunk_data)
        
        print(f"Restored snapshot {snapshot_id} to {target_path}")
        print(f"Total files restored: {len(manifest['files'])}")