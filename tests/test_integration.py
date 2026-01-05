"""
Integration tests for the backup system
"""
import os
import tempfile
import shutil
import sys

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.cli import BackupCLI

class TestIntegration:
    """Integration tests"""
    
    def setup_method(self):
        """Setup test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.dataset_dir = os.path.join(self.temp_dir, "dataset")
        self.store_dir = os.path.join(self.temp_dir, "store")
        self.restore_dir = os.path.join(self.temp_dir, "restored")
        
        # Create test dataset
        os.makedirs(self.dataset_dir)
        os.makedirs(os.path.join(self.dataset_dir, "subdir"))
        
        # Create test files
        self.test_files = {
            "file1.txt": b"Content of file 1" * 100,
            "file2.txt": b"Content of file 2" * 200,
            "subdir/file3.txt": b"Content in subdirectory" * 50,
            "empty.txt": b"",
        }
        
        for filename, content in self.test_files.items():
            filepath = os.path.join(self.dataset_dir, filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'wb') as f:
                f.write(content)
    
    def teardown_method(self):
        """Clean up"""
        shutil.rmtree(self.temp_dir)
    
    def test_full_backup_restore_cycle(self):
        """Test complete backup and restore cycle"""
        # Initialize store
        cli = BackupCLI()
        cli.init(self.store_dir)
        
        # Create backup
        cli.backup(self.dataset_dir, "test_backup")
        
        # List snapshots
        snapshots = cli.snapshot_manager.list_snapshots()
        assert len(snapshots) == 1
        
        snapshot_id = snapshots[0]["id"]
        
        # Verify snapshot
        is_valid, message = cli.snapshot_manager.verify_snapshot(snapshot_id)
        assert is_valid == True
        
        # Restore snapshot
        os.makedirs(self.restore_dir, exist_ok=True)
        cli.restore(snapshot_id, self.restore_dir)
        
        # Verify restored files
        for filename, expected_content in self.test_files.items():
            restored_path = os.path.join(self.restore_dir, filename)
            assert os.path.exists(restored_path)
            
            with open(restored_path, 'rb') as f:
                actual_content = f.read()
                assert actual_content == expected_content
    
    def test_multiple_backups(self):
        """Test multiple backups with deduplication"""
        cli = BackupCLI()
        cli.init(self.store_dir)
        
        # First backup
        cli.backup(self.dataset_dir, "backup1")
        
        # Modify dataset
        with open(os.path.join(self.dataset_dir, "newfile.txt"), 'w') as f:
            f.write("New file content")
        
        # Second backup
        cli.backup(self.dataset_dir, "backup2")
        
        snapshots = cli.snapshot_manager.list_snapshots()
        assert len(snapshots) == 2
        
        # Verify both snapshots
        for snapshot in snapshots:
            is_valid, message = cli.snapshot_manager.verify_snapshot(snapshot["id"])
            assert is_valid == True