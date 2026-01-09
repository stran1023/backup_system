"""
Write-Ahead Log (WAL) for crash consistency - IMPROVED VERSION
"""
import os
import json
from typing import List, Dict, Optional
import base64

class Journal:
    """Write-Ahead Log với recovery đầy đủ"""
    
    def __init__(self, journal_path: str):
        self.journal_path = journal_path
        self._ensure_dir()
    
    def _ensure_dir(self):
        """Tạo thư mục nếu chưa có"""
        os.makedirs(os.path.dirname(self.journal_path), exist_ok=True)
    
    def _append(self, entry: str) -> None:
        """Append entry với fsync"""
        with open(self.journal_path, 'a') as f:
            f.write(entry + '\n')
            f.flush()
            os.fsync(f.fileno())
    
    def begin_transaction(self, snapshot_id: str) -> None:
        """Bắt đầu transaction mới"""
        self._append(f"BEGIN:{snapshot_id}")

    def add_manifest(self, manifest_hash: str) -> None:
        """Record manifest addition - FIX FOR LEGACY CODE"""
        self._append(f"ADD_MANIFEST:{manifest_hash}")
    
    def write_manifest(self, snapshot_id: str, manifest_data: Dict) -> None:
        """Ghi manifest vào journal"""
        manifest_json = json.dumps(manifest_data, sort_keys=True)
        # Encode để tránh newline trong journal
        manifest_b64 = base64.b64encode(manifest_json.encode()).decode()
        self._append(f"MANIFEST:{snapshot_id}:{manifest_b64}")
    
    def write_metadata(self, snapshot_id: str, metadata: Dict) -> None:
        """Ghi metadata vào journal"""
        metadata_json = json.dumps(metadata, sort_keys=True)
        metadata_b64 = base64.b64encode(metadata_json.encode()).decode()
        self._append(f"METADATA:{snapshot_id}:{metadata_b64}")
    
    def commit(self, snapshot_id: str) -> None:
        """Commit transaction"""
        self._append(f"COMMIT:{snapshot_id}")
    
    def abort(self, snapshot_id: str) -> None:
        """Abort transaction"""
        self._append(f"ABORT:{snapshot_id}")
    
    def recover(self) -> List[Dict]:
        """
        Khôi phục từ crash
        Trả về: list các transaction chưa hoàn tất với dữ liệu đầy đủ
        """
        if not os.path.exists(self.journal_path):
            return []
        
        incomplete_transactions = []
        current_tx = None
        tx_data = {}
        
        with open(self.journal_path, 'r') as f:
            lines = f.readlines()
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            
            if line.startswith("BEGIN:"):
                # Kết thúc transaction trước nếu có
                if current_tx and tx_data:
                    incomplete_transactions.append(tx_data.copy())
                
                # Bắt đầu transaction mới
                current_tx = line.split(":", 1)[1]
                tx_data = {
                    "snapshot_id": current_tx,
                    "start_line": line_num,
                    "manifest": None,
                    "metadata": None,
                    "completed": False
                }
            
            elif line.startswith("MANIFEST:") and current_tx:
                parts = line.split(":", 2)
                if len(parts) == 3 and parts[1] == current_tx:
                    try:
                        manifest_json = base64.b64decode(parts[2]).decode()
                        tx_data["manifest"] = json.loads(manifest_json)
                    except:
                        tx_data["manifest"] = None
            
            elif line.startswith("METADATA:") and current_tx:
                parts = line.split(":", 2)
                if len(parts) == 3 and parts[1] == current_tx:
                    try:
                        metadata_json = base64.b64decode(parts[2]).decode()
                        tx_data["metadata"] = json.loads(metadata_json)
                    except:
                        tx_data["metadata"] = None
            
            elif line.startswith("COMMIT:") or line.startswith("ABORT:"):
                tx_id = line.split(":", 1)[1]
                if current_tx == tx_id:
                    tx_data["completed"] = True
                    current_tx = None
        
        # Thêm transaction cuối nếu chưa hoàn tất
        if current_tx and not tx_data.get("completed"):
            incomplete_transactions.append(tx_data)
        
        return incomplete_transactions
    
    def cleanup_incomplete(self, snapshot_id: str) -> bool:
        """
        Cleanup sau khi recovery
        Trả về: True nếu cleanup thành công
        """
        try:
            # 1. Đọc toàn bộ journal
            with open(self.journal_path, 'r') as f:
                lines = f.readlines()
            
            # 2. Tìm lines cần giữ lại (trước BEGIN của transaction này)
            keep_lines = []
            in_transaction = False
            
            for line in lines:
                if line.startswith(f"BEGIN:{snapshot_id}"):
                    in_transaction = True
                
                if not in_transaction:
                    keep_lines.append(line)
                
                if in_transaction and (line.startswith(f"COMMIT:{snapshot_id}") or 
                                      line.startswith(f"ABORT:{snapshot_id}")):
                    in_transaction = False
                    # KHÔNG giữ commit/abort line vì transaction bị rollback
            
            # 3. Ghi lại journal
            with open(self.journal_path, 'w') as f:
                f.writelines(keep_lines)
            
            return True
            
        except Exception as e:
            print(f"Journal cleanup failed: {e}")
            return False
    
    def get_last_committed(self) -> Optional[str]:
        """Lấy snapshot_id cuối cùng đã commit thành công"""
        if not os.path.exists(self.journal_path):
            return None
        
        last_committed = None
        with open(self.journal_path, 'r') as f:
            for line in reversed(f.readlines()):
                line = line.strip()
                if line.startswith("COMMIT:"):
                    last_committed = line.split(":", 1)[1]
                    break
        
        return last_committed
    
    def _flush_current(self):
        """Flush current file handle"""
        # Với implementation hiện tại, mỗi lần _append đều có flush
        # Nhưng có thể optimize bằng cách giữ file handle mở
        pass  # Hiện tại đã có flush trong _append