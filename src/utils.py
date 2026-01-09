"""
Utility functions for the backup system
"""
import os
import hashlib
import json
from typing import Dict, List

# Constants
CHUNK_SIZE = 1024 * 1024  # 1 MiB
HASH_ALGORITHM = 'sha256'

def get_os_user() -> str:
    """
    Get OS user with sudo preference
    Returns: username or raises error if cannot determine
    """
    import pwd
    
    # Priority 1: SUDO_USER environment variable
    sudo_user = os.environ.get('SUDO_USER')
    if sudo_user:
        return sudo_user
    
    # Priority 2: Current OS user
    try:
        uid = os.getuid()
        return pwd.getpwuid(uid).pw_name
    except Exception as e:
        raise ValueError(f"Cannot determine OS user: {e}")

def compute_hash(data: bytes) -> str:
    """Compute SHA-256 hash of data"""
    return hashlib.sha256(data).hexdigest()

def read_file_in_chunks(file_path: str, chunk_size: int = CHUNK_SIZE):
    """Generator to read file in chunks - ĐẢM BẢO trả về bytes"""
    try:
        with open(file_path, 'rb') as f:  # ← 'rb' để đọc binary
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                # ĐẢM BẢO chunk là bytes
                if not isinstance(chunk, bytes):
                    chunk = bytes(chunk)
                yield chunk
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        raise

def ensure_dir(directory: str) -> None:
    """Ensure directory exists"""
    os.makedirs(directory, exist_ok=True)

def canonical_json(data: Dict) -> str:
    """
    Convert data to canonical JSON string
    Ensures deterministic output by sorting files by path
    """
    # Deep copy to avoid modifying original
    import copy
    data_copy = copy.deepcopy(data)
    
    # Sort files list by path if it exists
    if "files" in data_copy and isinstance(data_copy["files"], list):
        data_copy["files"] = sorted(
            data_copy["files"], 
            key=lambda x: x.get("path", "")
        )
    
    # Convert to JSON with sorted keys
    return json.dumps(
        data_copy,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False
    )

def compute_args_hash(args: List[str]) -> str:
    """
    Compute SHA-256 hash of command arguments
    Args: list of arguments (excluding command name)
    """
    if not args:
        args_str = ""
    else:
        args_str = " ".join(str(arg) for arg in args)
    
    return hashlib.sha256(args_str.encode()).hexdigest()