"""
Audit logging with hash chain for tamper detection
"""
import os
import time
import hashlib
from typing import Optional, List, Tuple, Dict
from .utils import ensure_dir, compute_args_hash

class AuditLogger:
    """Audit log with hash chain for tamper detection"""
    
    def __init__(self, log_path: str):
        self.log_path = log_path
        ensure_dir(os.path.dirname(log_path))
        self.prev_hash = self._get_last_hash() or "0" * 64
    
    def _get_last_hash(self) -> Optional[str]:
        """Get hash of last entry from audit log"""
        if not os.path.exists(self.log_path):
            return None
        
        try:
            with open(self.log_path, 'r') as f:
                lines = f.readlines()
                if lines:
                    last_line = lines[-1].strip()
                    if last_line:
                        return last_line.split()[0]  # First token is ENTRY_HASH
        except:
            pass
        
        return None
    
    def log_command(self, user: str, command: str, args: List[str], 
                   status: str, error_msg: str = "") -> str:
        """
        Log a command execution to audit log
        Returns: entry hash
        """
        # Validate status
        valid_statuses = {"OK", "DENY", "FAIL"}
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")
        
        # Compute args hash
        args_hash = compute_args_hash(args)
        
        # Prepare entry data (excluding ENTRY_HASH)
        timestamp = int(time.time() * 1000)  # UNIX_MS
        entry_data = f"{self.prev_hash} {timestamp} {user} {command} {args_hash} {status}"
        
        if error_msg:
            # Escape newlines and tabs in error message
            error_msg_clean = error_msg.replace('\n', '\\n').replace('\t', '\\t')
            entry_data += f" {error_msg_clean}"
        
        # Compute entry hash
        entry_hash = hashlib.sha256(entry_data.encode()).hexdigest()
        
        # Write to log
        with open(self.log_path, 'a') as f:
            f.write(f"{entry_hash} {entry_data}\n")
            f.flush()
            os.fsync(f.fileno())
        
        # Update previous hash for next entry
        self.prev_hash = entry_hash
        
        return entry_hash
    
    def verify_audit_log(self) -> Tuple[bool, str, Optional[int]]:
        """
        Verify integrity of audit log using hash chain
        Returns: (is_valid, message, corrupt_line_number)
        """
        if not os.path.exists(self.log_path):
            return True, "Audit log does not exist", None
        
        try:
            with open(self.log_path, 'r') as f:
                lines = f.readlines()
            
            prev_hash = "0" * 64  # Genesis hash
            line_num = 0
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split()
                if len(parts) < 7:
                    return False, f"Malformed line {line_num}: insufficient fields", line_num
                
                entry_hash = parts[0]
                stored_prev_hash = parts[1]
                
                # Verify previous hash chain
                if stored_prev_hash != prev_hash:
                    return False, f"Hash chain broken at line {line_num}", line_num
                
                # Recompute hash to verify
                entry_data = " ".join(parts[1:])  # Everything except ENTRY_HASH
                computed_hash = hashlib.sha256(entry_data.encode()).hexdigest()
                
                if computed_hash != entry_hash:
                    return False, f"Hash mismatch at line {line_num}", line_num
                
                prev_hash = entry_hash
            
            # Success
            last_hash = prev_hash if lines else "0" * 64
            return True, f"AUDIT OK - Last hash: {last_hash}", None
            
        except Exception as e:
            return False, f"Audit verification failed: {str(e)}", None
    
    def get_log_entries(self, limit: int = 100) -> List[Dict]:
        """Get recent audit log entries"""
        if not os.path.exists(self.log_path):
            return []
        
        entries = []
        try:
            with open(self.log_path, 'r') as f:
                lines = f.readlines()[-limit:]  # Get last N lines
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split()
                if len(parts) >= 7:
                    entry = {
                        "entry_hash": parts[0],
                        "prev_hash": parts[1],
                        "timestamp": int(parts[2]),
                        "user": parts[3],
                        "command": parts[4],
                        "args_hash": parts[5],
                        "status": parts[6],
                        "error": " ".join(parts[7:]) if len(parts) > 7 else ""
                    }
                    entries.append(entry)
        
        except Exception as e:
            print(f"Error reading audit log: {e}")
        
        return entries
    
    def tamper_test(self) -> None:
        """Test function to demonstrate tamper detection"""
        print("Testing audit log tamper detection...")
        
        # Add a test entry
        test_hash = self.log_command("test_user", "test_command", ["arg1", "arg2"], "OK")
        print(f"Added test entry with hash: {test_hash}")
        
        # Verify log is valid
        is_valid, msg, _ = self.verify_audit_log()
        print(f"Before tampering: {msg}")
        
        if is_valid:
            # Tamper with the log
            with open(self.log_path, 'a') as f:
                f.write("TAMPERED_LINE\n")
            
            # Verify again
            is_valid, msg, line_num = self.verify_audit_log()
            print(f"After tampering: {msg}")
            if line_num:
                print(f"Corruption detected at line: {line_num}")