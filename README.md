# 🔐 Secure Backup System - Sao lưu & Phục hồi Dữ liệu An toàn

## 🎯 Giới thiệu
Hệ thống sao lưu dòng lệnh (CLI) đảm bảo:
- **✅ Backup/Restore đúng**: Khôi phục chính xác thư mục tại thời điểm snapshot
- **✅ Toàn vẹn dữ liệu**: Phát hiện sửa đổi/thiếu chunk bằng Merkle tree
- **✅ Chống rollback**: Hash chain phát hiện thay snapshot mới bằng cũ
- **✅ An toàn khi crash**: Write-Ahead Log đảm bảo consistency
- **✅ Policy enforcement**: Role-based access control (admin/operator/auditor)
- **✅ Audit logging**: Log tamper-evident với hash chain

## 📦 Cài đặt

### Yêu cầu hệ thống
- Python 3.13+
- Linux

### Bước 1: Tải file zip và giải nén
```bash
cd backup_system
```

### Bước 2: Tạo và kích hoạt virtual environment (venv)
```bash
# Tạo virtual environment
python -m venv .venv

# Kích hoạt venv (Linux)
source .venv/bin/activate
```

### Bước 3: Cài đặt dependencies
```bash
pip install -r requirements.txt
```

### Bước 4: Cấu hình policy
```bash
# Kiểm tra username hệ thống
whoami

# sửa policy file
nano policy.yaml  # Sửa 'sonchan' thành username thực
```

### Bước 5: Chạy thử
```bash
# Hiển thị help
python main.py --help

# Test toàn bộ test suite
pytest tests/ -v
```

## Các lệnh CLI đầy đủ
```bash
# Quản lý backup
python main.py init <store_path>                # Khởi tạo store
python main.py backup <source_path> [--label]   # Tạo snapshot
python main.py list                             # Liệt kê snapshots
python main.py verify <snapshot_id>             # Xác minh snapshot
python main.py restore <snapshot_id> <target>   # Khôi phục

# Audit & Security
python main.py audit-verify                     # Xác minh audit log
python main.py audit-show [--limit N]           # Hiển thị audit log
python main.py tamper-test                      # Test tamper detection
```

## 🏗️ Cấu trúc dữ liệu
### Chunk Size
- **Kích thước chunk**: 1 MiB (1,048,576 bytes)
- **Lý do**: Cân bằng giữa hiệu suất I/O và deduplication
- **Hash algorithm**: SHA-256 (64 ký tự hex)

### Content-Addressable Storage
Chunks được lưu trữ theo hash của nội dung:
```text
store/chunks/
├── ab/        # 2 ký tự đầu của hash làm thư mục
│   └── abc123...def456  # File chunk
├── cd/
│   └── cde789...fgh012
└── ...
```
Deduplication: Chunks giống nhau chỉ lưu 1 lần, các snapshot chia sẻ chunks.

## 📄 Canonical Manifest
### Định dạng JSON chuẩn hóa
Manifest mô tả toàn bộ snapshot dưới dạng JSON deterministic:
```json
{
  "version": 1,
  "snapshot_id": "snap_1700000000_abc123",
  "source_path": "/path/to/dataset",
  "created_at": 1700000000.0,
  "label": "Backup label",
  "files": [
    {
      "path": "folder/file1.txt",
      "chunks": ["sha256_hash1", "sha256_hash2"],
      "size": 2097152
    },
    {
      "path": "folder/file2.txt", 
      "chunks": ["sha256_hash3"],
      "size": 1048576
    }
  ]
}
```
### Quy tắc canonicalization
1. **Sắp xếp files**: Theo đường dẫn tăng dần (alphabetical)
2. **Sắp xếp keys**: Tất cả dict keys được sort
3. **Encoding cố định**: json.dumps(..., sort_keys=True, separators=(',', ':'))
4. **Không khoảng trắng**: Loại bỏ khoảng trắng không cần thiết

Ví dụ canonical JSON:
```json
{"created_at":1700000000.0,"files":[{"chunks":["hash1","hash2"],"path":"a.txt","size":2097152},{"chunks":["hash3"],"path":"b.txt","size":1048576}],"label":"test","snapshot_id":"snap_1","source_path":"/test","version":1}
```

## 🌳 Tính toàn vẹn & Merkle Tree
### Thuật toán Merkle Tree
Mỗi snapshot có Merkle root đại diện cho toàn bộ nội dung.

#### Bước 1: Tính leaf hash cho mỗi file
```text
leaf_hash = SHA256(path + "|" + chunk1,chunk2,...)
```

Ví dụ: File docs/report.txt với chunks [abc123, def456]
```text
leaf_data = "docs/report.txt|abc123,def456"
leaf_hash = SHA256(leaf_data) = "f1e2d3c4b5a697887766554433221100..."
```

#### Bước 2: Xây dựng Merkle tree
- **Input**: Danh sách leaf hashes đã sort
- **Algorithm**:

   1. Nếu 1 leaf → root = leaf_hash
   2. Nếu số lẻ leaves → duplicate last leaf
   3. Ghép từng cặp: ```parent_hash = SHA256(left_hash + right_hash)```
   4. Lặp lại đến khi còn 1 hash (root)

Ví dụ với 3 files:
```text
File1 → hashA       File2 → hashB       File3 → hashC
       \                  /                    |
        SHA256(hashA+hashB)                    hashC (duplicated)
               \                               /
                \                             /
                 SHA256(hashAB + hashCC) = ROOT
```

#### Bước 3: Lưu và xác minh
- Merkle root được lưu trong metadata snapshot
- Khi verify: tính lại root và so sánh
- Không khớp → snapshot bị hỏng

#### Lệnh verify
```text
python main.py verify snap_1700000000_abc123
```
Kết quả:
```text
✓ Snapshot snap_1700000000_abc123 is VALID
✓ Merkle root matches: a1b2c3d4...
✓ All chunks present
✓ No rollback detected
```

## ⛓️ Chống Rollback
### Cơ chế bảo vệ
Hệ thống sử dụng hash chain để phát hiện rollback:

#### 1. Mỗi snapshot lưu:
- ```merkle_root```: Hash của snapshot hiện tại
- ```prev_root```: Hash của snapshot trước đó
- ```timestamp```: Thời gian tạo

#### 2. Hash chain:
```text
Genesis (0*64) → snap1_root → snap2_root → snap3_root
     ↑              ↑              ↑
  prev_root      prev_root      prev_root
```

#### 3. Kiểm tra rollback:
- Mỗi Merkle root chỉ xuất hiện 1 lần trong chain
- Nếu root cũ xuất hiện sau root mới → rollback
- Chain phải liên tục (không đứt đoạn)

### Triển khai trong code
```python
# metadata.json
{
  "snapshots": {
    "snap_1": {
      "merkle_root": "root1",
      "prev_root": "0"*64,
      "created_at": 1700000000
    },
    "snap_2": {
      "merkle_root": "root2", 
      "prev_root": "root1",
      "created_at": 1700000100
    }
  },
  "prev_root_chain": ["root1", "root2"],
  "latest_snapshot": "snap_2"
}
```

### Test rollback detection
```bash
# 1. Tạo 2 snapshots liên tiếp
echo "Version 1" > testfile.txt
python main.py backup ./test_dataset --label "v1"

echo "Version 2" > testfile.txt  
python main.py backup ./test_dataset --label "v2"

# 2. Lấy snapshot IDs
python main.py list

# 3. Thủ công thay metadata (simulate rollback)
# Tìm file: store/metadata.json
# Thay merkle_root của snap2 bằng merkle_root của snap1

# 4. Verify sẽ phát hiện
python main.py verify <snapshot_id>
# Kết quả: ✗ Rollback detected
```

## 💾 Crash Consistency (Journal/WAL)
### Write-Ahead Log Design
Đảm bảo metadata nhất quán khi crash xảy ra trong quá trình backup.
#### Cấu trúc WAL:
```text
BEGIN:snap_123
ADD_CHUNK:hash1
ADD_CHUNK:hash2
ADD_MANIFEST:manifest_hash
SET_METADATA:snap_123:merkle_root:prev_root:timestamp:label
COMMIT:snap_123
```

#### Quy trình:
   1. **BEGIN**: Bắt đầu transaction
   2. **Operations**: Ghi các thao tác metadata
   3. **COMMIT**: Hoàn thành transaction
   4. **Recovery**: Khởi động lại đọc WAL, rollback transactions chưa commit

### Recovery Logic
```python
def recover():
    if WAL có BEGIN nhưng không có COMMIT tương ứng:
        Xóa các chunks/manifest đã tạo
        Xóa snapshot metadata
        WAL vẫn nhất quán
```

### Test crash recovery
```bash
# 1. Tạo dataset lớn để backup lâu
dd if=/dev/urandom of=large_dataset.bin bs=1M count=50

# 2. Bắt đầu backup và kill process
python main.py backup ./large_dataset --label "Crash Test" &
BACKUP_PID=$!
sleep 1  # Đợi backup bắt đầu
kill -9 $BACKUP_PID

# 3. Kiểm tra store vẫn nhất quán
python main.py init ./store  # Sẽ thông báo recovery
# Output: "Recovered from crash. Cleaned up incomplete snapshots: [...]"

# 4. Verify không có snapshot lỗi
python main.py list  # Chỉ snapshots hợp lệ
```

## 👥 Policy Enforcement
### File ```policy.yaml```
```yaml
# policy.yaml - Role-based access control
users:
  # === CẤU HÌNH USERNAME THỰC ===
  sonchan: admin        # ← Thay 'sonchan' bằng username của bạn
  bob: operator       # ← Thêm users khác nếu cần
  charlie: auditor
  
  # System users (giữ nguyên)
  root: admin
  admin: admin

roles:
  admin:
    - init
    - backup
    - list-snapshots
    - verify
    - restore
    - audit-verify
  
  operator:
    - backup
    - list-snapshots
    - verify
    - restore
    - audit-verify
  
  auditor:
    - list-snapshots
    - verify
    - audit-verify
```

### Schema validation
   1. **users**: Map ```os_username → role```
   2. **roles**: Map ```role → [allowed_commands]```
   3. **Required roles**: admin, operator, auditor

### Permission checking flow
```python
def check_permission(user, command):
    if user không trong policy → DENY
    role = policy["users"][user]
    if command không trong policy["roles"][role] → DENY
    else → ALLOW
```

### Test policy
```bash
# 1. Kiểm tra current user
whoami

# 2. Test các lệnh theo role
python main.py init ./store      # Chỉ admin được
python main.py list              # Tất cả roles được
python main.py backup ./data     # Admin & operator được

# 3. Test DENY case (tạm sửa policy.yaml)
# Thêm user với role auditor, thử chạy backup
# Kết quả: Permission denied: User 'username' (role: auditor) cannot execute 'backup'
```

## 📝 Audit Log
### Định dạng dòng
```text
ENTRY_HASH PREV_HASH UNIX_MS USER COMMAND ARGS_SHA256 STATUS [ERROR_MSG]
```

#### Fields:
- **ENTRY_HASH**: SHA256 của toàn bộ entry (trừ chính nó)
- **PREV_HASH**: Hash của entry trước đó (0*64 cho entry đầu)
- **UNIX_MS**: Timestamp milliseconds
- **USER**: OS username
- **COMMAND**: Tên lệnh
- **ARGS_SHA256**: SHA256 của arguments string
- **STATUS**: OK, DENY, hoặc FAIL
- **ERROR_MSG**: Tùy chọn, thông báo lỗi

### Cách tính hash chain
```text
entry_data = f"{PREV_HASH} {UNIX_MS} {USER} {COMMAND} {ARGS_SHA256} {STATUS}"
ENTRY_HASH = SHA256(entry_data.encode())

# Ví dụ:
# PREV_HASH=0*64, UNIX_MS=1700000000000, USER=alice, COMMAND=init, 
# ARGS_SHA256=abc123..., STATUS=OK
# ENTRY_HASH = SHA256("000... 1700000000000 alice init abc123... OK")
```

### Hash chain verification
```text
Entry1: hash1 = SHA256(genesis + data1)
Entry2: hash2 = SHA256(hash1 + data2)  
Entry3: hash3 = SHA256(hash2 + data3)
...
```
Nếu bất kỳ entry nào bị sửa, toàn bộ chain phía sau invalid.

### Lệnh audit-verify
```bash
python main.py audit-verify
```

#### Output:
```text
✓ AUDIT OK - Last hash: a1b2c3d4e5f6...
```
hoặc
```text
✗ AUDIT CORRUPTED - Hash mismatch at line 5
```

### Test tamper detection
```bash
# 1. Tạo vài audit entries
python main.py init ./test_store
python main.py backup ./dataset

# 2. Verify log hợp lệ
python main.py audit-verify

# 3. Tamper với log
echo "TAMPERED LINE" >> ./test_store/audit.log

# 4. Verify lại (sẽ fail)
python main.py audit-verify
# Output: ✗ AUDIT CORRUPTED - Hash mismatch at line X
```

## 👤 Xác định USER từ OS
### Logic xác định user
```python
def get_os_user() -> str:
    """
    Get OS user with sudo preference
    Returns: username or raises error if cannot determine
    """
    import pwd
    
    # Ưu tiên 1: SUDO_USER (nếu chạy qua sudo)
    sudo_user = os.environ.get('SUDO_USER')
    if sudo_user:
        return sudo_user
    
    # Ưu tiên 2: Current OS user
    try:
        uid = os.getuid()
        return pwd.getpwuid(uid).pw_name
    except Exception as e:
        raise ValueError(f"Cannot determine OS user: {e}")
```

### Các trường hợp
1. **Chạy thường**: whoami → alice → USER=alice
2. **Chạy sudo**: sudo python main.py ... → USER=alice (SUDO_USER), không dùng root
3. **Không xác định được**: Raise error, ghi audit log STATUS=FAIL

### Ví dụ
```bash
# Trường hợp 1: Chạy trực tiếp
whoami                    # alice
python main.py init ./store
# Audit log: ... alice init ... OK

# Trường hợp 2: Chạy sudo
sudo python main.py init ./store  
# Audit log: ... alice init ... OK (không phải root)
```

## 🧪 Kiểm thử
### Chạy toàn bộ test suite
```bash
# Chạy all tests
python -m pytest tests/ -v

# Kết quả mong đợi:
# 26 passed, 4 warnings in X.XXs
```

### Test cases bao gồm
1. ✅ Backup/restore correctness
2. ✅ Integrity verification (tamper detection)
3. ✅ Rollback detection
4. ✅ Crash recovery
5. ✅ Policy enforcement
6. ✅ Audit log tamper detection
7. ✅ Merkle tree computation

### Test manual checklist
```bash
# 1. Init & backup
python main.py init ./test_store
python main.py backup ./test_data --label "Test1"

# 2. List & verify
python main.py list
python main.py verify <snapshot_id>

# 3. Restore
mkdir restored
python main.py restore <snapshot_id> ./restored

# 4. Audit log
python main.py audit-verify
python main.py audit-show --limit 5

# 5. Policy test
# Sửa policy.yaml, test DENY case

# 6. Crash test
# Kill process during backup, verify recovery
```