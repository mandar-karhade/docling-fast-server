"""
Shared deployment ID management for container-level isolation
"""
import os
import uuid
import fcntl
import time
from pathlib import Path
from typing import Optional


class DeploymentIDManager:
    """
    Manages container-level deployment ID with file locking to prevent race conditions
    """
    
    _deployment_file = Path("/tmp/docling_deployment_id")
    _lock_file = Path("/tmp/docling_deployment_id.lock")
    _instance: Optional['DeploymentIDManager'] = None
    _deployment_id: Optional[str] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_deployment_id(self) -> str:
        """Get or create a container-level deployment ID shared across all workers"""
        if self._deployment_id is not None:
            return self._deployment_id
        
        try:
            # Use file locking to prevent race conditions between workers
            with open(self._lock_file, 'w') as lock_file:
                # Acquire exclusive lock
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                
                try:
                    # Check again if deployment ID exists (another worker might have created it)
                    if self._deployment_file.exists():
                        with open(self._deployment_file, 'r') as f:
                            deployment_id = f.read().strip()
                            if deployment_id:
                                self._deployment_id = deployment_id
                                print(f"📋 Using existing container deployment ID: {deployment_id}")
                                return deployment_id
                    
                    # Generate new deployment ID for this container
                    deployment_id = str(uuid.uuid4())[:8]
                    
                    # Save it atomically
                    temp_file = self._deployment_file.with_suffix('.tmp')
                    with open(temp_file, 'w') as f:
                        f.write(deployment_id)
                        f.flush()
                        os.fsync(f.fileno())
                    
                    # Atomic rename
                    os.rename(temp_file, self._deployment_file)
                    
                    self._deployment_id = deployment_id
                    print(f"✨ Generated new container deployment ID: {deployment_id}")
                    return deployment_id
                    
                finally:
                    # Lock is automatically released when file is closed
                    pass
                    
        except Exception as e:
            print(f"⚠️  Error managing deployment ID file: {e}")
            # Fallback to process-based ID
            fallback_id = f"fallback_{os.getpid()}"
            self._deployment_id = fallback_id
            return fallback_id


# Global singleton instance
deployment_id_manager = DeploymentIDManager()


def get_container_deployment_id() -> str:
    """Convenience function to get container deployment ID"""
    return deployment_id_manager.get_deployment_id()
