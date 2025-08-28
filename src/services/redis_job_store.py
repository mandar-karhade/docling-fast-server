import redis
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

class RedisJobStore:
    """Redis-based job storage for multi-worker coordination"""
    
    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0):
        """Initialize Redis connection for local coordination"""
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port, 
                db=redis_db,
                decode_responses=True,  # Automatically decode bytes to strings
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            # Test connection
            self.redis_client.ping()
            print(f"✅ Connected to local Redis at {redis_host}:{redis_port}")
            
        except Exception as e:
            print(f"❌ Failed to connect to local Redis: {e}")
            raise
        
        self._deployment_id = None
        
        # Full results storage (separate from job tracking) 
        self.results_dir = Path("/tmp/docling_results")
        self.results_dir.mkdir(exist_ok=True)
        
        print("✅ Redis job store initialized")
    
    def set_deployment_id(self, deployment_id: str):
        """Set the deployment ID for this store"""
        self._deployment_id = deployment_id
        print(f"🔧 Redis job store deployment ID set to: {deployment_id}")
    
    def _get_job_key(self, job_id: str) -> str:
        """Get Redis key for job data"""
        return f"job:{job_id}"
    
    def _get_deployment_key(self) -> str:
        """Get Redis key for deployment info"""
        return f"deployment:{self._deployment_id}" if self._deployment_id else "deployment:default"
    
    def create_job(self, job_id: str, job_data: Dict) -> bool:
        """Create a new job entry"""
        try:
            job_key = self._get_job_key(job_id)
            
            # Check if job already exists
            if self.redis_client.exists(job_key):
                print(f"⚠️ Job {job_id} already exists in Redis")
                return False
            
            # Add timestamp if not present
            if 'created_at' not in job_data:
                job_data['created_at'] = datetime.utcnow().isoformat()
            if 'updated_at' not in job_data:
                job_data['updated_at'] = datetime.utcnow().isoformat()
            
            # Store job data as JSON with 24 hour expiration
            job_json = json.dumps(job_data, default=str)
            self.redis_client.setex(job_key, 86400, job_json)  # 24 hours
            
            print(f"💾 Job {job_id} saved to Redis store")
            return True
            
        except Exception as e:
            print(f"❌ Error creating job {job_id} in Redis: {e}")
            return False
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job by ID"""
        try:
            job_key = self._get_job_key(job_id)
            job_json = self.redis_client.get(job_key)
            
            if job_json:
                job_data = json.loads(job_json)
                print(f"🔍 Found job {job_id} in Redis store")
                return job_data
            else:
                # Count total jobs for debugging
                job_count = len(self.redis_client.keys("job:*"))
                print(f"❌ Job {job_id} not found in Redis store (have {job_count} jobs)")
                
                # Debug: Show what jobs we do have (first 3)
                if job_count > 0:
                    job_keys = self.redis_client.keys("job:*")[:3]
                    job_ids = [key.replace("job:", "") for key in job_keys]
                    print(f"🔍 Available jobs: {job_ids}...")
                
                return None
                
        except Exception as e:
            print(f"❌ Error getting job {job_id} from Redis: {e}")
            return None
    
    def update_job(self, job_id: str, updates: Dict) -> bool:
        """Update job fields"""
        try:
            job_key = self._get_job_key(job_id)
            
            # Get current job data
            current_data = self.get_job(job_id)
            if not current_data:
                print(f"❌ Job {job_id} not found for update in Redis")
                return False
            
            # Apply updates
            current_data.update(updates)
            current_data['updated_at'] = datetime.utcnow().isoformat()
            
            # Save back to Redis with same TTL
            job_json = json.dumps(current_data, default=str)
            ttl = self.redis_client.ttl(job_key)
            if ttl > 0:
                self.redis_client.setex(job_key, ttl, job_json)
            else:
                self.redis_client.setex(job_key, 86400, job_json)  # Default 24 hours
            
            return True
            
        except Exception as e:
            print(f"❌ Error updating job {job_id} in Redis: {e}")
            return False
    
    def delete_job(self, job_id: str) -> bool:
        """Delete job by ID"""
        try:
            job_key = self._get_job_key(job_id)
            deleted = self.redis_client.delete(job_key)
            
            if deleted:
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
            print(f"❌ Error deleting job {job_id} from Redis: {e}")
            return False
    
    def get_jobs_by_deployment(self, deployment_id: str) -> List[Dict]:
        """Get all jobs for a deployment"""
        try:
            jobs = []
            job_keys = self.redis_client.keys("job:*")
            
            for job_key in job_keys:
                job_json = self.redis_client.get(job_key)
                if job_json:
                    job_data = json.loads(job_json)
                    if job_data.get('deployment_id') == deployment_id:
                        jobs.append(job_data)
            
            return jobs
            
        except Exception as e:
            print(f"❌ Error getting jobs for deployment {deployment_id} from Redis: {e}")
            return []
    
    def get_all_jobs(self) -> Dict[str, Dict]:
        """Get all jobs as dictionary (for compatibility)"""
        try:
            jobs = {}
            job_keys = self.redis_client.keys("job:*")
            
            for job_key in job_keys:
                job_json = self.redis_client.get(job_key)
                if job_json:
                    job_data = json.loads(job_json)
                    job_id = job_key.replace("job:", "")
                    jobs[job_id] = job_data
            
            return jobs
            
        except Exception as e:
            print(f"❌ Error getting all jobs from Redis: {e}")
            return {}
    
    def get_active_job_count(self) -> int:
        """Get count of active jobs"""
        try:
            count = 0
            job_keys = self.redis_client.keys("job:*")
            
            for job_key in job_keys:
                job_json = self.redis_client.get(job_key)
                if job_json:
                    job_data = json.loads(job_json)
                    if job_data.get('active', False):
                        count += 1
            
            return count
            
        except Exception as e:
            print(f"❌ Error getting active job count from Redis: {e}")
            return 0
    
    def cleanup_old_jobs(self, deployment_id: str, hours: int = 24) -> int:
        """Clean up jobs from different deployments or very old jobs"""
        try:
            deleted_count = 0
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            job_keys = self.redis_client.keys("job:*")
            
            for job_key in job_keys:
                job_json = self.redis_client.get(job_key)
                if job_json:
                    job_data = json.loads(job_json)
                    job_deployment = job_data.get('deployment_id')
                    
                    # Remove jobs from different deployments
                    if job_deployment and job_deployment != deployment_id:
                        self.redis_client.delete(job_key)
                        deleted_count += 1
                        continue
                    
                    # Remove very old jobs from current deployment
                    try:
                        created_at = datetime.fromisoformat(job_data.get('created_at', ''))
                        if created_at < cutoff_time:
                            self.redis_client.delete(job_key)
                            deleted_count += 1
                    except:
                        pass  # Keep jobs with invalid dates
            
            if deleted_count > 0:
                print(f"🗑️ Cleaned up {deleted_count} old jobs from Redis store")
            
            return deleted_count
            
        except Exception as e:
            print(f"❌ Error cleaning up old jobs from Redis: {e}")
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
            job_keys = self.redis_client.keys("job:*")
            total_jobs = len(job_keys)
            active_jobs = 0
            status_counts = {}
            
            for job_key in job_keys:
                job_json = self.redis_client.get(job_key)
                if job_json:
                    job_data = json.loads(job_json)
                    if job_data.get('active', False):
                        active_jobs += 1
                    
                    status = job_data.get('status', 'unknown')
                    status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                'total_jobs': total_jobs,
                'active_jobs': active_jobs,
                'status_distribution': status_counts,
                'deployment_id': self._deployment_id,
                'redis_info': {
                    'connected': True,
                    'memory_usage': self.redis_client.info('memory').get('used_memory_human', 'Unknown')
                }
            }
            
        except Exception as e:
            print(f"❌ Error getting Redis stats: {e}")
            return {'error': str(e), 'redis_info': {'connected': False}}
    
    def health_check(self) -> bool:
        """Check if Redis connection is healthy"""
        try:
            self.redis_client.ping()
            return True
        except Exception as e:
            print(f"❌ Redis health check failed: {e}")
            return False
