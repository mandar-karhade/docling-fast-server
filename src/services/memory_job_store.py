import threading
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

class InMemoryJobStore:
    """Thread-safe in-memory job storage for ephemeral job management"""
    
    def __init__(self):
        self._jobs: Dict[str, Dict] = {}
        self._lock = threading.RLock()  # Reentrant lock for nested operations
        self._deployment_id = None
        
        # Full results storage (separate from job tracking) 
        self.results_dir = Path("/tmp/docling_results")
        self.results_dir.mkdir(exist_ok=True)
        
        print("✅ In-memory job store initialized")
    
    def set_deployment_id(self, deployment_id: str):
        """Set the deployment ID for this store"""
        with self._lock:
            self._deployment_id = deployment_id
            print(f"🔧 Job store deployment ID set to: {deployment_id}")
    
    def create_job(self, job_id: str, job_data: Dict) -> bool:
        """Create a new job entry"""
        try:
            with self._lock:
                if job_id in self._jobs:
                    print(f"⚠️ Job {job_id} already exists")
                    return False
                
                # Add timestamp if not present
                if 'created_at' not in job_data:
                    job_data['created_at'] = datetime.utcnow().isoformat()
                if 'updated_at' not in job_data:
                    job_data['updated_at'] = datetime.utcnow().isoformat()
                
                self._jobs[job_id] = job_data.copy()
                print(f"💾 Job {job_id} saved to memory store")
                return True
        except Exception as e:
            print(f"❌ Error creating job {job_id}: {e}")
            return False
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job by ID"""
        try:
            with self._lock:
                job_data = self._jobs.get(job_id)
                if job_data:
                    return job_data.copy()  # Return copy to prevent external modification
                return None
        except Exception as e:
            print(f"❌ Error getting job {job_id}: {e}")
            return None
    
    def update_job(self, job_id: str, updates: Dict) -> bool:
        """Update job fields"""
        try:
            with self._lock:
                if job_id not in self._jobs:
                    print(f"❌ Job {job_id} not found for update")
                    return False
                
                # Update the job data
                self._jobs[job_id].update(updates)
                self._jobs[job_id]['updated_at'] = datetime.utcnow().isoformat()
                return True
        except Exception as e:
            print(f"❌ Error updating job {job_id}: {e}")
            return False
    
    def delete_job(self, job_id: str) -> bool:
        """Delete job by ID"""
        try:
            with self._lock:
                if job_id in self._jobs:
                    del self._jobs[job_id]
                    
                    # Also delete the full result file if it exists
                    try:
                        result_file = self.results_dir / f"{job_id}.json"
                        if result_file.exists():
                            result_file.unlink()
                            print(f"🗑️ Deleted result file for job {job_id}")
                    except Exception as e:
                        print(f"⚠️ Could not delete result file for job {job_id}: {e}")
                    
                    return True
                return False
        except Exception as e:
            print(f"❌ Error deleting job {job_id}: {e}")
            return False
    
    def get_jobs_by_deployment(self, deployment_id: str) -> List[Dict]:
        """Get all jobs for a deployment"""
        try:
            with self._lock:
                jobs = []
                for job_data in self._jobs.values():
                    if job_data.get('deployment_id') == deployment_id:
                        jobs.append(job_data.copy())
                return jobs
        except Exception as e:
            print(f"❌ Error getting jobs for deployment {deployment_id}: {e}")
            return []
    
    def get_all_jobs(self) -> Dict[str, Dict]:
        """Get all jobs as dictionary (for compatibility)"""
        try:
            with self._lock:
                return {job_id: job_data.copy() for job_id, job_data in self._jobs.items()}
        except Exception as e:
            print(f"❌ Error getting all jobs: {e}")
            return {}
    
    def get_active_job_count(self) -> int:
        """Get count of active jobs"""
        try:
            with self._lock:
                count = 0
                for job_data in self._jobs.values():
                    if job_data.get('active', False):
                        count += 1
                return count
        except Exception as e:
            print(f"❌ Error getting active job count: {e}")
            return 0
    
    def cleanup_old_jobs(self, deployment_id: str, hours: int = 24) -> int:
        """Clean up jobs from different deployments (since we don't persist between deployments)"""
        try:
            with self._lock:
                old_jobs = []
                cutoff_time = datetime.utcnow() - timedelta(hours=hours)
                
                for job_id, job_data in self._jobs.items():
                    # Remove jobs from different deployments or old jobs
                    job_deployment = job_data.get('deployment_id')
                    if job_deployment != deployment_id:
                        old_jobs.append(job_id)
                    else:
                        # Also remove very old jobs from current deployment
                        try:
                            created_at = datetime.fromisoformat(job_data.get('created_at', ''))
                            if created_at < cutoff_time:
                                old_jobs.append(job_id)
                        except:
                            pass  # Keep jobs with invalid dates
                
                # Remove old jobs
                for job_id in old_jobs:
                    del self._jobs[job_id]
                    # Clean up result files
                    try:
                        result_file = self.results_dir / f"{job_id}.json"
                        if result_file.exists():
                            result_file.unlink()
                    except:
                        pass
                
                if old_jobs:
                    print(f"🗑️ Cleaned up {len(old_jobs)} old jobs from memory store")
                
                return len(old_jobs)
        except Exception as e:
            print(f"❌ Error cleaning up old jobs: {e}")
            return 0
    
    def store_full_result(self, job_id: str, result) -> bool:
        """Store full result to file (separate from job metadata)"""
        try:
            result_file = self.results_dir / f"{job_id}.json"
            with open(result_file, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            return True
        except Exception as e:
            print(f"⚠️ Error storing full result for job {job_id}: {e}")
            return False
    
    def get_full_result(self, job_id: str):
        """Get full result from file"""
        try:
            result_file = self.results_dir / f"{job_id}.json"
            if result_file.exists():
                with open(result_file, 'r') as f:
                    return json.load(f)
            return None
        except Exception as e:
            print(f"⚠️ Error loading full result for job {job_id}: {e}")
            return None
    
    def get_stats(self) -> Dict:
        """Get store statistics"""
        try:
            with self._lock:
                total_jobs = len(self._jobs)
                active_jobs = sum(1 for job in self._jobs.values() if job.get('active', False))
                
                status_counts = {}
                for job in self._jobs.values():
                    status = job.get('status', 'unknown')
                    status_counts[status] = status_counts.get(status, 0) + 1
                
                return {
                    'total_jobs': total_jobs,
                    'active_jobs': active_jobs,
                    'status_distribution': status_counts,
                    'deployment_id': self._deployment_id
                }
        except Exception as e:
            print(f"❌ Error getting stats: {e}")
            return {'error': str(e)}
