"""
Write-Ahead Log (WAL) for crash consistency
"""
import os
from typing import List
from .utils import ensure_dir

class Journal:
    """Simple Write-Ahead Log for crash recovery"""
    
    def __init__(self, journal_path: str):
        self.journal_path = journal_path
        ensure_dir(os.path.dirname(journal_path))
    
    def _append(self, entry: str) -> None:
        """Append entry to journal with newline"""
        with open(self.journal_path, 'a') as f:
            f.write(entry + '\n')
            f.flush()
            os.fsync(f.fileno())
    
    def begin_transaction(self, snapshot_id: str) -> None:
        """Start a new transaction"""
        self._append(f"BEGIN:{snapshot_id}")
    
    def add_chunk(self, chunk_hash: str) -> None:
        """Record chunk addition"""
        self._append(f"ADD_CHUNK:{chunk_hash}")
    
    def add_manifest(self, manifest_hash: str) -> None:
        """Record manifest addition"""
        self._append(f"ADD_MANIFEST:{manifest_hash}")
    
    def set_metadata(self, snapshot_id: str, merkle_root: str, 
                    prev_root: str, timestamp: float, label: str = "") -> None:
        """Record snapshot metadata"""
        label_escaped = label.replace(":", "_")  # Avoid colon in label
        self._append(f"SET_METADATA:{snapshot_id}:{merkle_root}:{prev_root}:{timestamp}:{label_escaped}")
    
    def commit(self, snapshot_id: str) -> None:
        """Commit transaction"""
        self._append(f"COMMIT:{snapshot_id}")
    
    def abort(self, snapshot_id: str) -> None:
        """Abort transaction"""
        self._append(f"ABORT:{snapshot_id}")
    
    def recover(self) -> List[str]:
        """
        Recover from crash by reading journal
        Returns: list of incomplete snapshot IDs
        """
        if not os.path.exists(self.journal_path):
            return []
        
        incomplete_snapshots = []
        current_tx = None
        tx_start_line = 0
        
        with open(self.journal_path, 'r') as f:
            lines = f.readlines()
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            
            if line.startswith("BEGIN:"):
                current_tx = line.split(":", 1)[1]
                tx_start_line = line_num
            elif line.startswith("COMMIT:") or line.startswith("ABORT:"):
                tx_id = line.split(":", 1)[1]
                if current_tx == tx_id:
                    current_tx = None  # Transaction completed
            elif line.startswith("END_OF_RECOVERY"):
                # Marker for completed recovery
                break
        
        if current_tx:
            incomplete_snapshots.append(current_tx)
            # Truncate journal to before this transaction
            self._truncate_journal(tx_start_line - 1)
        
        return incomplete_snapshots
    
    def _truncate_journal(self, line_count: int) -> None:
        """Truncate journal to specified number of lines"""
        if not os.path.exists(self.journal_path):
            return
        
        with open(self.journal_path, 'r') as f:
            lines = f.readlines()
        
        with open(self.journal_path, 'w') as f:
            f.writelines(lines[:line_count])
    
    def mark_recovery_complete(self) -> None:
        """Mark recovery as complete"""
        self._append("END_OF_RECOVERY")