"""
Custom exceptions for the backup system
"""

class BackupSystemError(Exception):
    """Base exception for backup system"""
    pass

class PolicyDeniedError(BackupSystemError):
    """Raised when policy denies an operation"""
    pass

class IntegrityError(BackupSystemError):
    """Raised when data integrity check fails"""
    pass

class RollbackDetectedError(IntegrityError):
    """Raised when rollback is detected"""
    pass

class SnapshotNotFoundError(BackupSystemError):
    """Raised when snapshot is not found"""
    pass

class CrashRecoveryError(BackupSystemError):
    """Raised during crash recovery"""
    pass