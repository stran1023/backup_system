"""
Storage engine for chunk storage and snapshot management
"""
import os
import json
import time
from typing import Dict, List, Tuple, Any, Optional
from .journal import Journal
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
            """Check if chunk exists AND content matches hash"""
            chunk_path = self._chunk_path(chunk_hash)
            if not os.path.exists(chunk_path):
                return False
            
            # THÊM PHẦN NÀY: Kiểm tra nội dung
            try:
                with open(chunk_path, 'rb') as f:
                    chunk_data = f.read()
                computed_hash = compute_hash(chunk_data)
                return computed_hash == chunk_hash
            except:
                return False

class SnapshotManager:
    """Manages snapshot creation với journaling tích hợp"""
    
    def __init__(self, storage: ChunkStorage, journal=None):
        self.storage = storage
        self.journal = journal
        self.metadata = self._load_metadata()
    
    def _recover_from_crash(self) -> None:
        """Khôi phục từ crash khi khởi động"""
        if not self.journal:
            return
        
        incomplete_txs = self.journal.recover()
        
        for tx in incomplete_txs:
            snapshot_id = tx["snapshot_id"]
            print(f"[RECOVERY] Found incomplete transaction: {snapshot_id}")
            
            # CLEANUP TÀI NGUYÊN
            self._cleanup_incomplete_snapshot(snapshot_id)
            
            # CLEANUP JOURNAL
            self.journal.cleanup_incomplete(snapshot_id)
        
        if incomplete_txs:
            print(f"[RECOVERY] Cleaned {len(incomplete_txs)} incomplete transactions")
    
    def _cleanup_incomplete_snapshot(self, snapshot_id: str) -> None:
        """Xóa tài nguyên của snapshot chưa hoàn tất"""
        try:
            # 1. Xóa manifest file
            manifest_path = os.path.join(self.storage.snapshots_dir, f"{snapshot_id}.manifest")
            if os.path.exists(manifest_path):
                os.remove(manifest_path)
            
            # 2. Xóa metadata entry nếu có
            if snapshot_id in self.metadata["snapshots"]:
                del self.metadata["snapshots"][snapshot_id]
                
                # Nếu đây là latest snapshot, tìm lại latest
                if self.metadata.get("latest_snapshot") == snapshot_id:
                    snapshots = self.metadata["snapshots"]
                    if snapshots:
                        latest = max(snapshots.items(), 
                                   key=lambda x: x[1]["created_at"])
                        self.metadata["latest_snapshot"] = latest[0]
                    else:
                        self.metadata["latest_snapshot"] = None
                
                self._save_metadata()
            
            # 3. CHÚ Ý: KHÔNG xóa chunks vì chúng có thể được dùng bởi snapshot khác
            # Deduplication sẽ xử lý
            
        except Exception as e:
            print(f"[RECOVERY] Cleanup error for {snapshot_id}: {e}")
    
    def create_snapshot(self, source_path: str, label: str = "") -> Dict:
        """
        Tạo snapshot mới với journaling tích hợp
        """
        # 1. KIỂM TRA INPUT
        source_path = os.path.abspath(source_path)
        if not os.path.exists(source_path):
            raise ValueError(f"Source path does not exist: {source_path}")
        
        # 2. TẠO SNAPSHOT ID
        snapshot_id = f"snap_{int(time.time())}_{compute_hash(str(time.time_ns()).encode())[:8]}"
        
        # 3. BẮT ĐẦU JOURNAL TRANSACTION (nếu có journal)
        if self.journal:
            self.journal.begin_transaction(snapshot_id)
        
        try:
            # 4. THU THẬP DỮ LIỆU FILE
            files_data = {}
            total_chunks = 0
            
            for root, dirs, files in os.walk(source_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, source_path)
                    
                    chunk_hashes = []
                    file_size = 0
                    
                    for chunk in read_file_in_chunks(file_path):
                        chunk_hash = self.storage.store_chunk(chunk)
                        chunk_hashes.append(chunk_hash)
                        total_chunks += 1
                        file_size += len(chunk)
                    
                    files_data[rel_path] = {
                        "chunks": chunk_hashes,
                        "size": file_size
                    }
            
            # 5. TẠO MANIFEST
            manifest = {
                "version": 1,
                "snapshot_id": snapshot_id,
                "source_path": source_path,
                "created_at": time.time(),
                "label": label,
                "files": [
                    {
                        "path": path,
                        "chunks": data["chunks"],
                        "size": data["size"]
                    }
                    for path, data in sorted(files_data.items())
                ]
            }
            
            # 6. TÍNH MERKLE ROOT
            manifest_json = canonical_json(manifest)
            merkle_root = MerkleTree.compute_merkle_root(manifest_json)
            
            # 7. TÍNH HASH CHAIN (chống rollback)
            prev_snapshot_id = self.metadata.get("latest_snapshot")
            if prev_snapshot_id:
                prev_metadata = self.metadata["snapshots"][prev_snapshot_id]
                prev_root = prev_metadata["merkle_root"]
                prev_chain_hash = prev_metadata.get("chain_hash", "0" * 64)
            else:
                # First snapshot (genesis)
                prev_root = "0" * 64
                prev_chain_hash = "0" * 64
            
            chain_data = f"{prev_chain_hash}{merkle_root}{prev_root}"
            chain_hash = compute_hash(chain_data.encode())
            
            # 8. TẠO METADATA
            snapshot_metadata = {
                "id": snapshot_id,
                "created_at": time.time(),
                "label": label,
                "merkle_root": merkle_root,
                "prev_root": prev_root,
                "prev_chain_hash": prev_chain_hash,
                "chain_hash": chain_hash,
                "manifest_hash": compute_hash(manifest_json.encode()),
                "total_files": len(files_data),
                "total_chunks": total_chunks,
                "sequence": len(self.metadata.get("prev_root_chain", []))
            }
            
            # 9. GHI VÀO JOURNAL TRƯỚC (Write-Ahead Log)
            if self.journal:
                # Ghi manifest và metadata vào journal
                self.journal.write_manifest(snapshot_id, manifest)
                self.journal.write_metadata(snapshot_id, snapshot_metadata)
                
                # FLUSH để đảm bảo trên disk
                self.journal._flush_current()
            
            # 10. LƯU DỮ LIỆU THẬT (SAU KHI JOURNAL ĐÃ GHI)
            # 10.1. Lưu manifest file
            manifest_path = os.path.join(self.storage.snapshots_dir, f"{snapshot_id}.manifest")
            with open(manifest_path, 'w') as f:
                f.write(manifest_json)
            
            # 10.2. Lưu metadata
            self.metadata["snapshots"][snapshot_id] = snapshot_metadata
            self.metadata["latest_snapshot"] = snapshot_id
            self.metadata["latest_snapshot_root"] = merkle_root
            self.metadata["prev_root_chain"].append(merkle_root)
            
            self._save_metadata()
            
            # 11. COMMIT JOURNAL (sau khi mọi thứ thành công)
            if self.journal:
                self.journal.commit(snapshot_id)
            
            return snapshot_metadata
            
        except Exception as e:
            # 12. ROLLBACK NẾU CÓ LỖI
            if self.journal:
                self.journal.abort(snapshot_id)
            
            # Cleanup any partial files
            self._cleanup_incomplete_snapshot(snapshot_id)
            
            raise RuntimeError(f"Snapshot creation failed: {str(e)}") from e
    
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
        Verify snapshot integrity với hash chain
        Returns: (is_valid, message)
        """
        try:
            # 1. Đọc metadata và manifest
            metadata = self.get_snapshot(snapshot_id)
            
            # 2. Đọc manifest từ DISK
            manifest_path = os.path.join(self.storage.snapshots_dir, f"{snapshot_id}.manifest")
            if not os.path.exists(manifest_path):
                return False, "Manifest file not found"
            
            with open(manifest_path, 'r') as f:
                manifest_json_from_disk = f.read()
            
            # Parse manifest
            try:
                manifest = json.loads(manifest_json_from_disk)
            except json.JSONDecodeError:
                return False, "Manifest file corrupted (invalid JSON)"
            
            # 3. Tính Merkle root từ manifest
            computed_root = MerkleTree.compute_merkle_root(manifest_json_from_disk)
            
            # 4. So sánh với stored Merkle root
            if computed_root != metadata["merkle_root"]:
                return False, f"Merkle root mismatch. Computed: {computed_root[:16]}..., Stored: {metadata['merkle_root'][:16]}..."
            
            # 5. Kiểm tra tất cả chunks
            for file_entry in manifest["files"]:
                for chunk_hash in file_entry["chunks"]:
                    if not self.storage.chunk_exists(chunk_hash):
                        return False, f"Chunk missing or corrupted: {chunk_hash[:16]}..."
            
            # 6. ========== KIỂM TRA ROLLBACK VỚI HASH CHAIN ==========
            is_rollback, rollback_reason = self._check_rollback_hash_chain(snapshot_id)
            if is_rollback:
                return False, f"Rollback detected: {rollback_reason}"
            
            # 7. Thêm: Kiểm tra manifest hash
            computed_manifest_hash = compute_hash(manifest_json_from_disk.encode())
            if computed_manifest_hash != metadata.get("manifest_hash"):
                return False, f"Manifest hash mismatch"
            
            return True, f"Snapshot valid (Merkle root: {computed_root[:16]}..., Chain hash: {metadata['chain_hash'][:16]}...)"
            
        except Exception as e:
            return False, f"Verification failed: {str(e)}"
              
    def _check_rollback(self, snapshot_id: str) -> bool:
        """Backward compatibility - use hash chain version"""
        is_rollback, _ = self._check_rollback_hash_chain(snapshot_id)
        return is_rollback
    
    def _check_rollback_hash_chain(self, snapshot_id: str) -> Tuple[bool, str]:
        """
        Check for rollback using hash chain
        Returns: (is_rollback, reason)
        """
        try:
            metadata = self.get_snapshot(snapshot_id)
            
            # 1. Kiểm tra genesis snapshot
            if metadata["prev_root"] == "0" * 64:
                # Đây là snapshot đầu tiên, chỉ cần kiểm tra chain_hash tính đúng
                expected_chain_hash = compute_hash(
                    f"{metadata['prev_chain_hash']}{metadata['merkle_root']}{metadata['prev_root']}".encode()
                )
                if metadata["chain_hash"] != expected_chain_hash:
                    return True, "Genesis snapshot chain hash mismatch"
                return False, "OK"
            
            # 2. Tìm snapshot trước đó (dựa vào prev_root)
            prev_snapshot = None
            for snap_id, snap_meta in self.metadata["snapshots"].items():
                if snap_meta["merkle_root"] == metadata["prev_root"]:
                    prev_snapshot = snap_meta
                    break
            
            if not prev_snapshot:
                return True, f"Previous snapshot not found for root: {metadata['prev_root'][:16]}..."
            
            # 3. Kiểm tra chain hash của snapshot trước có khớp với prev_chain_hash không
            if metadata["prev_chain_hash"] != prev_snapshot["chain_hash"]:
                return True, f"Chain hash mismatch with previous snapshot"
            
            # 4. Tính toán chain hash hiện tại
            expected_chain_hash = compute_hash(
                f"{metadata['prev_chain_hash']}{metadata['merkle_root']}{metadata['prev_root']}".encode()
            )
            
            if metadata["chain_hash"] != expected_chain_hash:
                return True, f"Chain hash verification failed"
            
            # 5. Kiểm tra sequence number (tùy chọn nhưng hữu ích)
            if "sequence" in metadata and "sequence" in prev_snapshot:
                if metadata["sequence"] != prev_snapshot["sequence"] + 1:
                    return True, f"Sequence number mismatch: expected {prev_snapshot['sequence'] + 1}, got {metadata['sequence']}"
            
            return False, "Hash chain valid"
            
        except Exception as e:
            return True, f"Rollback check error: {str(e)}"

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

                    # KIỂM TRA THÊM: Verify chunk hash
                    computed_hash = compute_hash(chunk_data)
                    if computed_hash != chunk_hash:
                        raise IntegrityError(f"Chunk corrupted: {chunk_hash[:16]}...")

                    f.write(chunk_data)
        
        print(f"Restored snapshot {snapshot_id} to {target_path}")
        print(f"Total files restored: {len(manifest['files'])}")