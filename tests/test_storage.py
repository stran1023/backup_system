"""
Test cases for storage functionality
"""
import os
import tempfile
import pytest
import sys

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.storage import ChunkStorage, SnapshotManager
from src.utils import CHUNK_SIZE

class TestChunkStorage:
    """Test ChunkStorage class"""
    
    def setup_method(self):
        """Create temporary directory for each test"""
        self.temp_dir = tempfile.mkdtemp()
        self.storage = ChunkStorage(self.temp_dir)
    
    def teardown_method(self):
        """Clean up temporary directory"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_store_and_retrieve_chunk(self):
        """Test storing and retrieving a chunk"""
        test_data = b"Hello, World!" * 1000  # 13KB
        
        # Store chunk
        chunk_hash = self.storage.store_chunk(test_data)
        assert len(chunk_hash) == 64  # SHA-256 hex digest
        
        # Retrieve chunk
        retrieved_data = self.storage.get_chunk(chunk_hash)
        assert retrieved_data == test_data
    
    def test_deduplication(self):
        """Test chunk deduplication"""
        test_data = b"Duplicate me!" * 100
        
        # Store same chunk twice
        hash1 = self.storage.store_chunk(test_data)
        hash2 = self.storage.store_chunk(test_data)
        
        # Should be same hash and not create duplicate file
        assert hash1 == hash2
        
        # Count chunk files
        chunk_files = []
        for root, dirs, files in os.walk(os.path.join(self.temp_dir, "chunks")):
            chunk_files.extend(files)
        
        assert len(chunk_files) == 1  # Only one physical file
    
    def test_chunk_exists(self):
        """Test chunk existence check"""
        test_data = b"Test data"
        chunk_hash = self.storage.store_chunk(test_data)
        
        assert self.storage.chunk_exists(chunk_hash) == True
        assert self.storage.chunk_exists("nonexistent" * 8) == False
    
    def test_missing_chunk(self):
        """Test retrieval of non-existent chunk"""
        with pytest.raises(Exception):
            self.storage.get_chunk("nonexistent" * 8)

class TestSnapshotManager:
    """Test SnapshotManager class"""
    
    def setup_method(self):
        """Setup test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.temp_dir, "test_data")
        self.store_dir = os.path.join(self.temp_dir, "store")
        
        # Create test data
        os.makedirs(self.data_dir)
        os.makedirs(self.store_dir)
        
        # Create test files
        self.file1_path = os.path.join(self.data_dir, "file1.txt")
        self.file2_path = os.path.join(self.data_dir, "subdir", "file2.txt")
        
        os.makedirs(os.path.dirname(self.file2_path))
        
        with open(self.file1_path, 'wb') as f:
            f.write(b"Content of file 1" * 1000)  # ~17KB
        
        with open(self.file2_path, 'wb') as f:
            f.write(b"Content of file 2" * 2000)  # ~34KB
        
        # Initialize storage
        self.storage = ChunkStorage(self.store_dir)
        self.manager = SnapshotManager(self.storage)
    
    def teardown_method(self):
        """Clean up"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_create_snapshot(self):
        """Test snapshot creation"""
        snapshot = self.manager.create_snapshot(self.data_dir, "test_snapshot")
        
        assert "id" in snapshot
        assert "merkle_root" in snapshot
        assert "total_files" in snapshot
        assert snapshot["total_files"] == 2
        assert snapshot["total_chunks"] > 0
        
        # Verify snapshot appears in list
        snapshots = self.manager.list_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0]["id"] == snapshot["id"]
    
    def test_verify_snapshot(self):
        """Test snapshot verification"""
        snapshot = self.manager.create_snapshot(self.data_dir, "test")
        
        is_valid, message = self.manager.verify_snapshot(snapshot["id"])
        assert is_valid == True
        assert "valid" in message.lower() or "ok" in message.lower()
    
    def test_restore_snapshot(self):
        """Test snapshot restoration"""
        snapshot = self.manager.create_snapshot(self.data_dir, "test")
        
        # Restore to new location
        restore_dir = os.path.join(self.temp_dir, "restored")
        self.manager.restore_snapshot(snapshot["id"], restore_dir)
        
        # Verify restored files
        assert os.path.exists(os.path.join(restore_dir, "file1.txt"))
        assert os.path.exists(os.path.join(restore_dir, "subdir", "file2.txt"))
        
        # Compare file contents
        with open(self.file1_path, 'rb') as f1, \
             open(os.path.join(restore_dir, "file1.txt"), 'rb') as f2:
            assert f1.read() == f2.read()