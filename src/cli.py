"""
Command Line Interface for the backup system
"""
import argparse
import sys
import os
import time
import hashlib
import json
from typing import List
from .storage import ChunkStorage, SnapshotManager
from .journal import Journal
from .policy import PolicyManager
from .audit import AuditLogger
from .utils import get_os_user, ensure_dir, canonical_json, compute_hash
from .exceptions import PolicyDeniedError, IntegrityError, SnapshotNotFoundError

class BackupCLI:
    """Main CLI interface for backup system"""
    
    def __init__(self):
        self.store_path = None
        self.storage = None
        self.snapshot_manager = None
        self.journal = None
        self.policy_manager = None
        self.audit_logger = None
        self.current_user = None
        self._load_store_config()

    def _load_store_config(self):
        """Load store path from config file if exists"""
        config_file = os.path.join(os.path.dirname(__file__), "..", "backup_config.json")
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    store_path = config.get("store_path")
                    if store_path and os.path.exists(store_path):
                        print(f"Auto-loaded store from config: {store_path}")
                        self._setup_components(store_path)
            except Exception as e:
                print(f"Warning: Could not load config: {e}")

    def _save_store_config(self, store_path: str):
        """Save store path to config file"""
        config_file = os.path.join(os.path.dirname(__file__), "..", "backup_config.json")
        try:
            with open(config_file, 'w') as f:
                json.dump({"store_path": os.path.abspath(store_path)}, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save config: {e}")

    def _ensure_initialized(self) -> None:
        """Ensure system is initialized"""
        if not self.store_path or not self.storage:
            # THỬ LOAD LẠI TỪ CONFIG
            self._load_store_config()

            # Nếu vẫn không có
            if not self.store_path or not self.storage:
                raise ValueError(
                    "Backup store not initialized. Run 'init' first.\n"
                    "Example: python main.py init ./store"
                )
            
        # ĐẢM BẢO current_user được set
        if not hasattr(self, 'current_user') or self.current_user is None:
            try:
                self.current_user = get_os_user()
            except ValueError as e:
                raise ValueError(f"Cannot determine OS user: {e}")
            
    def _setup_components(self, store_path: str) -> None:
        """Setup all components with automatic recovery"""
        self.store_path = store_path
        
        # Tạo journal TRƯỚC
        journal_path = os.path.join(self.store_path, "journal.wal")
        self.journal = Journal(journal_path)
        
        # Tạo storage và snapshot manager (tự động recovery)
        self.storage = ChunkStorage(self.store_path)
        self.snapshot_manager = SnapshotManager(self.storage, self.journal)
        
        # Policy và audit
        policy_path = os.path.join(os.path.dirname(__file__), "..", "policy.yaml")
        self.policy_manager = PolicyManager(policy_path)
        
        audit_log_path = os.path.join(self.store_path, "audit.log")
        self.audit_logger = AuditLogger(audit_log_path)
    
    def _audit_and_enforce(self, command: str, args: List[str], 
                        func, *func_args, **func_kwargs):
        """
        Wrapper to enforce policy and audit commands
        """
        # Đảm bảo current_user được set
        if not self.current_user:
            try:
                self.current_user = get_os_user()
            except:
                self.current_user = "unknown"
        
        try:
            # Check permission
            self.policy_manager.enforce_permission(command, self.current_user)
            
            # Execute command
            result = func(*func_args, **func_kwargs)
            
            # Log success
            self.audit_logger.log_command(
                self.current_user, command, args, "OK"
            )
            
            return result
            
        except PolicyDeniedError as e:
            # Log denial - ĐẢM BẢO current_user không None
            user_for_log = self.current_user if self.current_user else "unknown"
            self.audit_logger.log_command(
                user_for_log, command, args, "DENY", str(e)
            )
            print(f"Permission denied: {e}")
            sys.exit(1)
            
        except Exception as e:
            # Log failure
            user_for_log = self.current_user if self.current_user else "unknown"
            self.audit_logger.log_command(
                user_for_log, command, args, "FAIL", str(e)
            )
            print(f"Command failed: {e}")
            sys.exit(1)

    def init(self, store_path: str) -> None:
        """Initialize a new backup store"""
        # 1. Get user FIRST
        try:
            self.current_user = get_os_user()
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        
        # 2. Check permission using temporary policy
        policy_path = os.path.join(os.path.dirname(__file__), "..", "policy.yaml")
        temp_policy = PolicyManager(policy_path)
        
        # Audit log tạm nếu cần (không có store nên không ghi được)
        if not temp_policy.check_permission("init", self.current_user):
            print(f"Permission denied: User '{self.current_user}' cannot run 'init'")
            sys.exit(1)
        
        # 3. Check directory
        store_path = os.path.abspath(store_path)
        if os.path.exists(store_path) and os.listdir(store_path):
            response = input(f"Directory '{store_path}' is not empty. Continue? (y/N): ")
            if response.lower() != 'y':
                print("Initialization cancelled.")
                return
        
        # 4. Setup store directory
        ensure_dir(store_path)
        
        # 5. CHỈ tạo Journal và recovery TRƯỚC
        journal = Journal(os.path.join(store_path, "journal.wal"))
        incomplete = journal.recover()
        if incomplete:
            print(f"Recovered from crash. Cleaned incomplete: {incomplete}")
        
        store_path = os.path.abspath(store_path)

        # 6. Bây giờ mới setup components đầy đủ
        self._setup_components(store_path)
        
        # LƯU CONFIG SAU KHI THÀNH CÔNG
        self._save_store_config(store_path)

        # 7. Ghi audit log
        self.audit_logger.log_command(
            self.current_user, "init", [store_path], "OK"
        )
        
        print(f"Initialized backup store at: {store_path}")
        print(f"Config saved to: backup_config.json")
        print(f"Current user: {self.current_user}")
        
    def backup(self, source_path: str, label: str = "") -> None:
        """Create a backup snapshot"""
        # Kiểm tra initialization
        self._ensure_initialized()
        
        # Kiểm tra policy TRƯỚC
        try:
            self._audit_and_enforce("backup", [source_path, f"--label {label}" if label else ""],
                                self._backup_internal, source_path, label)
        except Exception as e:
            print(f"Backup failed: {e}")
            return

    def _backup_internal(self, source_path: str, label: str = "") -> None:
        """Internal backup implementation (after policy check)"""
        source_path = os.path.abspath(source_path)
        
        # Kiểm tra source path
        if not os.path.exists(source_path):
            raise ValueError(f"Source path does not exist: {source_path}")
        
        if not os.access(source_path, os.R_OK):
            raise ValueError(f"Cannot read source path: {source_path}")
        
        print(f"Creating backup of: {source_path}")
        if label:
            print(f"Label: {label}")
        
        # Tạo snapshot ID
        snapshot_id = f"snap_{int(time.time())}_{hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:8]}"
        
        # Bắt đầu WAL transaction
        self.journal.begin_transaction(snapshot_id)
        
        try:
            # Tạo snapshot (gọi phiên bản có journal)
            # CHÚ Ý: SnapshotManager cần được khởi tạo với journal
            metadata = self.snapshot_manager.create_snapshot(source_path, label)
            
            # KHÔNG CẦN GỌI journal.add_manifest ở đây nữa
            # vì SnapshotManager.create_snapshot đã xử lý journaling
            
            # In kết quả
            print(f"✓ Backup created successfully!")
            print(f"  Snapshot ID: {metadata['id']}")
            print(f"  Merkle Root: {metadata['merkle_root'][:16]}...")
            print(f"  Files: {metadata['total_files']}, Chunks: {metadata['total_chunks']}")
            
        except Exception as e:
            # Rollback trong WAL
            self.journal.abort(snapshot_id)
            
            # Clean up any partial files
            self._cleanup_failed_backup(snapshot_id)
            
            # Re-raise với context
            raise RuntimeError(f"Backup failed for {source_path}: {str(e)}") from e

    def _cleanup_failed_backup(self, snapshot_id: str) -> None:
        """Clean up files from failed backup"""
        try:
            # Xóa manifest file nếu tồn tại
            manifest_path = os.path.join(self.store_path, "snapshots", f"{snapshot_id}.manifest")
            if os.path.exists(manifest_path):
                os.remove(manifest_path)
            
            # Note: Không xóa chunks vì chúng có thể được dùng bởi snapshot khác
            # Chunks được deduplicated nên safe
            
        except Exception as e:
            print(f"Warning: Error during cleanup: {e}")
    
    def list_snapshots(self) -> None:
        """List all snapshots"""
        self._ensure_initialized()
        
        snapshots = self.snapshot_manager.list_snapshots()
        
        if not snapshots:
            print("No snapshots found.")
            return
        
        print(f"Found {len(snapshots)} snapshot(s):")
        print("-" * 80)
        
        for i, snap in enumerate(snapshots, 1):
            created_time = time.strftime('%Y-%m-%d %H:%M:%S', 
                                       time.localtime(snap["created_at"]))
            print(f"{i}. ID: {snap['id']}")
            print(f"   Created: {created_time}")
            print(f"   Label: {snap.get('label', 'N/A')}")
            print(f"   Files: {snap['total_files']}, Chunks: {snap['total_chunks']}")
            print(f"   Merkle Root: {snap['merkle_root'][:16]}...")
            print()
    
    def verify(self, snapshot_id: str) -> None:
        """Verify snapshot integrity"""
        self._ensure_initialized()
        
        print(f"Verifying snapshot: {snapshot_id}")
        
        try:
            is_valid, message = self.snapshot_manager.verify_snapshot(snapshot_id)
            
            if is_valid:
                print(f"✓ Snapshot {snapshot_id} is VALID")
                print(f"  {message}")
            else:
                print(f"✗ Snapshot {snapshot_id} is INVALID")
                print(f"  Reason: {message}")
                
        except SnapshotNotFoundError:
            print(f"Error: Snapshot not found: {snapshot_id}")
    
    def restore(self, snapshot_id: str, target_path: str) -> None:
        """Restore snapshot to target directory"""
        self._ensure_initialized()
        
        target_path = os.path.abspath(target_path)
        
        print(f"Restoring snapshot {snapshot_id} to: {target_path}")
        
        if os.path.exists(target_path) and os.listdir(target_path):
            response = input(f"Target directory '{target_path}' is not empty. Continue? (y/N): ")
            if response.lower() != 'y':
                print("Restore cancelled.")
                return
        
        try:
            self.snapshot_manager.restore_snapshot(snapshot_id, target_path)
            print("✓ Restore completed successfully!")
            
        except IntegrityError as e:
            print(f"✗ Restore failed: {e}")
        except SnapshotNotFoundError:
            print(f"Error: Snapshot not found: {snapshot_id}")
    
    def audit_verify(self) -> None:
        """Verify audit log integrity"""
        if not self.audit_logger:
            print("Error: System not initialized.")
            return
        
        print("Verifying audit log integrity...")
        
        is_valid, message, line_num = self.audit_logger.verify_audit_log()
        
        if is_valid:
            print(f"✓ {message}")
        else:
            print(f"✗ {message}")
            if line_num:
                print(f"  Corruption detected at line: {line_num}")
    
    def show_audit_log(self, limit: int = 20) -> None:
        """Show recent audit log entries"""
        if not self.audit_logger:
            print("Error: System not initialized.")
            return
        
        entries = self.audit_logger.get_log_entries(limit)
        
        if not entries:
            print("No audit log entries found.")
            return
        
        print(f"Recent audit log entries (last {len(entries)}):")
        print("=" * 100)
        
        for entry in entries:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', 
                                    time.localtime(entry['timestamp'] / 1000))
            
            print(f"Time: {timestamp}")
            print(f"User: {entry['user']}, Command: {entry['command']}")
            print(f"Status: {entry['status']}, Args Hash: {entry['args_hash'][:16]}...")
            print(f"Entry Hash: {entry['entry_hash'][:16]}...")
            
            if entry['error']:
                print(f"Error: {entry['error']}")
            
            print("-" * 100)
    
    def run(self):
        """Main CLI entry point"""
        parser = argparse.ArgumentParser(
            description="Secure Backup System with Snapshot and Audit Logging"
        )
        subparsers = parser.add_subparsers(dest="command", help="Command to execute")
        
        # Init command
        init_parser = subparsers.add_parser("init", help="Initialize backup store")
        init_parser.add_argument("store_path", help="Path to backup store")
        
        # Backup command
        backup_parser = subparsers.add_parser("backup", help="Create backup snapshot")
        backup_parser.add_argument("source_path", help="Path to backup")
        backup_parser.add_argument("--label", help="Snapshot label", default="")
        
        # List command
        subparsers.add_parser("list", help="List snapshots")
        
        # Verify command
        verify_parser = subparsers.add_parser("verify", help="Verify snapshot")
        verify_parser.add_argument("snapshot_id", help="Snapshot ID to verify")
        
        # Restore command
        restore_parser = subparsers.add_parser("restore", help="Restore snapshot")
        restore_parser.add_argument("snapshot_id", help="Snapshot ID to restore")
        restore_parser.add_argument("target_path", help="Target directory")
        
        # Audit commands
        subparsers.add_parser("audit-verify", help="Verify audit log integrity")
    
        args = parser.parse_args()
        
        if not args.command:
            parser.print_help()
            return
        
        # Map command names
        command_map = {
            "init": self.init,
            "backup": self.backup,
            "list": self.list_snapshots,
            "verify": self.verify,
            "restore": self.restore,
            "audit-verify": self.audit_verify,
        }
        
        # Execute command
        try:
            if args.command == "init":
                self.init(args.store_path)
            elif args.command == "backup":
                self.backup(args.source_path, args.label)
            elif args.command == "list":
                self._audit_and_enforce("list-snapshots", [],
                                       self.list_snapshots)
            elif args.command == "verify":
                self._audit_and_enforce("verify", [args.snapshot_id],
                                       self.verify, args.snapshot_id)
            elif args.command == "restore":
                self._audit_and_enforce("restore", [args.snapshot_id, args.target_path],
                                       self.restore, args.snapshot_id, args.target_path)
            elif args.command == "audit-verify":
                self._audit_and_enforce("audit-verify", [],
                                       self.audit_verify)
            else:
                print(f"Unknown command: {args.command}")
                
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()