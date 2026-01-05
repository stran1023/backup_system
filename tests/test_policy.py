"""
Test cases for policy enforcement
"""
import tempfile
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.policy import PolicyManager

class TestPolicyManager:
    """Test PolicyManager class"""
    
    def setup_method(self):
        """Setup test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.policy_file = os.path.join(self.temp_dir, "policy.yaml")
        
        # Create test policy
        policy_content = """
users:
  alice: admin
  bob: operator
  charlie: auditor

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
"""
        with open(self.policy_file, 'w') as f:
            f.write(policy_content)
        
        self.policy = PolicyManager(self.policy_file)
    
    def teardown_method(self):
        """Clean up"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_check_permission(self):
        """Test permission checking"""
        # Admin should have all permissions
        assert self.policy.check_permission("init", "alice") == True
        assert self.policy.check_permission("backup", "alice") == True
        assert self.policy.check_permission("audit-verify", "alice") == True
        
        # Operator should not have init
        assert self.policy.check_permission("init", "bob") == False
        assert self.policy.check_permission("backup", "bob") == True
        
        # Auditor should only have limited permissions
        assert self.policy.check_permission("init", "charlie") == False
        assert self.policy.check_permission("backup", "charlie") == False
        assert self.policy.check_permission("list-snapshots", "charlie") == True
    
    def test_enforce_permission(self):
        """Test permission enforcement"""
        # Admin should pass
        try:
            self.policy.enforce_permission("init", "alice")
            assert True
        except Exception:
            assert False, "Admin should have permission"
        
        # Operator should fail for init
        try:
            self.policy.enforce_permission("init", "bob")
            assert False, "Operator should not have init permission"
        except Exception as e:
            assert "not allowed" in str(e)
    
    def test_nonexistent_user(self):
        """Test non-existent user"""
        assert self.policy.check_permission("init", "nonexistent") == False
    
    def test_get_allowed_commands(self):
        """Test getting allowed commands for user"""
        admin_commands = self.policy.get_allowed_commands("alice")
        assert "init" in admin_commands
        assert "backup" in admin_commands
        assert len(admin_commands) == 6
        
        auditor_commands = self.policy.get_allowed_commands("charlie")
        assert "init" not in auditor_commands
        assert "list-snapshots" in auditor_commands
        assert len(auditor_commands) == 3