"""
Policy enforcement for command authorization
"""
import yaml
import os
from typing import Dict, List, Set, Optional
from .utils import get_os_user
from .exceptions import PolicyDeniedError

class PolicyManager:
    """Manages policy loading and enforcement"""
    
    def __init__(self, policy_path: str):
        self.policy_path = policy_path
        self.policy = self._load_policy()
        self._validate_policy()
    
    def _load_policy(self) -> Dict:
        """Load policy from YAML file"""
        if not os.path.exists(self.policy_path):
            # Default policy if file doesn't exist
            return self._get_default_policy()
        
        with open(self.policy_path, 'r') as f:
            return yaml.safe_load(f)
    
    def _get_default_policy(self) -> Dict:
        """Get default policy structure"""
        return {
            "users": {
                "root": "admin",
                "admin": "admin"
            },
            "roles": {
                "admin": [
                    "init", "backup", "list-snapshots", 
                    "verify", "restore", "audit-verify"
                ],
                "operator": [
                    "backup", "list-snapshots", "verify", 
                    "restore", "audit-verify"
                ],
                "auditor": [
                    "list-snapshots", "verify", "audit-verify"
                ]
            }
        }
    
    def _validate_policy(self) -> None:
        """Validate policy structure"""
        required_sections = ["users", "roles"]
        for section in required_sections:
            if section not in self.policy:
                raise ValueError(f"Policy missing section: {section}")
        
        required_roles = {"admin", "operator", "auditor"}
        if not required_roles.issubset(self.policy["roles"].keys()):
            raise ValueError(f"Policy must contain roles: {required_roles}")
    
    def check_permission(self, command: str, user: Optional[str] = None) -> bool:
        """
        Check if user is allowed to execute command
        Returns: True if allowed, False if denied
        """
        if user is None:
            user = get_os_user()
        
        # Check if user exists in policy
        if user not in self.policy["users"]:
            return False
        
        # Get user's role
        role = self.policy["users"][user]
        
        # Check if role exists
        if role not in self.policy["roles"]:
            return False
        
        # Check if command is allowed for this role
        allowed_commands = self.policy["roles"][role]
        return command in allowed_commands
    
    def enforce_permission(self, command: str, user: Optional[str] = None) -> None:
        """
        Enforce policy permission
        Raises PolicyDeniedError if not allowed
        """
        if not self.check_permission(command, user):
            if user is None:
                user = get_os_user()
            raise PolicyDeniedError(
                f"User '{user}' is not allowed to execute command '{command}'"
            )
    
    def get_allowed_commands(self, user: Optional[str] = None) -> Set[str]:
        """Get set of commands allowed for user"""
        if user is None:
            user = get_os_user()
        
        if user not in self.policy["users"]:
            return set()
        
        role = self.policy["users"][user]
        if role not in self.policy["roles"]:
            return set()
        
        return set(self.policy["roles"][role])