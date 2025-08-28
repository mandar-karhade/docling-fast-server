import sqlite3
import json
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from contextlib import contextmanager

class JobDatabase:
    """SQLite-based job storage with thread-safe operations"""
    
    def __init__(self, db_path: str = "/tmp/docling_jobs.db"):
        self.db_path = Path(db_path)
        self.local = threading.local()
        self._init_database()
    
    def _get_connection(self):
        """Get thread-local database connection"""
        if not hasattr(self.local, 'connection'):
            self.local.connection = sqlite3.connect(
                self.db_path,
                timeout=30.0,  # 30 second timeout
                check_same_thread=False
            )
            self.local.connection.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            self.local.connection.execute('PRAGMA journal_mode=WAL')
            self.local.connection.execute('PRAGMA synchronous=NORMAL')
            self.local.connection.execute('PRAGMA cache_size=10000')
            self.local.connection.execute('PRAGMA temp_store=memory')
        return self.local.connection
    
    @contextmanager
    def get_cursor(self):
        """Context manager for database operations"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
    
    def _init_database(self):
        """Initialize database schema"""
        with self.get_cursor() as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    deployment_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    filename TEXT,
                    args_json TEXT,
                    kwargs_json TEXT,
                    result_json TEXT,
                    logs_json TEXT,
                    active INTEGER DEFAULT 0,
                    waiting INTEGER DEFAULT 1,
                    error TEXT
                )
            ''')
            
            # Create indexes for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_deployment_id ON jobs(deployment_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON jobs(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON jobs(created_at)')
            
            print("✅ SQLite job database initialized")
    
    def create_job(self, job_id: str, job_data: Dict) -> bool:
        """Create a new job entry"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute('''
                    INSERT INTO jobs (
                        id, deployment_id, status, created_at, updated_at,
                        filename, args_json, kwargs_json, result_json, logs_json,
                        active, waiting, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    job_id,
                    job_data.get('deployment_id', ''),
                    job_data.get('status', 'queued'),
                    job_data.get('created_at', datetime.utcnow().isoformat()),
                    job_data.get('updated_at', datetime.utcnow().isoformat()),
                    job_data.get('filename', ''),
                    json.dumps(job_data.get('args', [])),
                    json.dumps(job_data.get('kwargs', {})),
                    json.dumps(job_data.get('result', None)),
                    json.dumps(job_data.get('logs', [])),
                    1 if job_data.get('active', False) else 0,
                    1 if job_data.get('waiting', True) else 0,
                    job_data.get('error', None)
                ))
                print(f"💾 Job {job_id} saved to SQLite database")
                return True
        except sqlite3.IntegrityError:
            print(f"⚠️ Job {job_id} already exists in database")
            return False
        except Exception as e:
            print(f"❌ Error creating job {job_id}: {e}")
            return False
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job by ID"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
                row = cursor.fetchone()
                
                if row:
                    return self._row_to_dict(row)
                return None
        except Exception as e:
            print(f"❌ Error getting job {job_id}: {e}")
            return None
    
    def update_job(self, job_id: str, updates: Dict) -> bool:
        """Update job fields"""
        try:
            # Build dynamic update query
            set_clauses = []
            values = []
            
            for field, value in updates.items():
                if field == 'args':
                    set_clauses.append('args_json = ?')
                    values.append(json.dumps(value))
                elif field == 'kwargs':
                    set_clauses.append('kwargs_json = ?')
                    values.append(json.dumps(value))
                elif field == 'result':
                    set_clauses.append('result_json = ?')
                    values.append(json.dumps(value))
                elif field == 'logs':
                    set_clauses.append('logs_json = ?')
                    values.append(json.dumps(value))
                elif field == 'active':
                    set_clauses.append('active = ?')
                    values.append(1 if value else 0)
                elif field == 'waiting':
                    set_clauses.append('waiting = ?')
                    values.append(1 if value else 0)
                elif field in ['status', 'filename', 'error']:
                    set_clauses.append(f'{field} = ?')
                    values.append(value)
            
            # Always update updated_at
            set_clauses.append('updated_at = ?')
            values.append(datetime.utcnow().isoformat())
            values.append(job_id)  # For WHERE clause
            
            with self.get_cursor() as cursor:
                query = f'UPDATE jobs SET {", ".join(set_clauses)} WHERE id = ?'
                cursor.execute(query, values)
                return cursor.rowcount > 0
        except Exception as e:
            print(f"❌ Error updating job {job_id}: {e}")
            return False
    
    def delete_job(self, job_id: str) -> bool:
        """Delete job by ID"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"❌ Error deleting job {job_id}: {e}")
            return False
    
    def get_jobs_by_deployment(self, deployment_id: str) -> List[Dict]:
        """Get all jobs for a deployment"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute('SELECT * FROM jobs WHERE deployment_id = ?', (deployment_id,))
                rows = cursor.fetchall()
                return [self._row_to_dict(row) for row in rows]
        except Exception as e:
            print(f"❌ Error getting jobs for deployment {deployment_id}: {e}")
            return []
    
    def cleanup_old_jobs(self, deployment_id: str, hours: int = 24) -> int:
        """Clean up jobs older than specified hours"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            cutoff_str = cutoff_time.isoformat()
            
            with self.get_cursor() as cursor:
                cursor.execute('''
                    DELETE FROM jobs 
                    WHERE deployment_id != ? AND created_at < ?
                ''', (deployment_id, cutoff_str))
                deleted_count = cursor.rowcount
                
                if deleted_count > 0:
                    print(f"🗑️ Cleaned up {deleted_count} old jobs from database")
                
                return deleted_count
        except Exception as e:
            print(f"❌ Error cleaning up old jobs: {e}")
            return 0
    
    def get_all_jobs(self) -> Dict[str, Dict]:
        """Get all jobs as dictionary (for compatibility)"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute('SELECT * FROM jobs ORDER BY created_at DESC')
                rows = cursor.fetchall()
                return {row['id']: self._row_to_dict(row) for row in rows}
        except Exception as e:
            print(f"❌ Error getting all jobs: {e}")
            return {}
    
    def get_active_job_count(self) -> int:
        """Get count of active jobs"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute('SELECT COUNT(*) FROM jobs WHERE active = 1')
                return cursor.fetchone()[0]
        except Exception as e:
            print(f"❌ Error getting active job count: {e}")
            return 0
    
    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        """Convert SQLite row to job dictionary"""
        return {
            'id': row['id'],
            'deployment_id': row['deployment_id'],
            'status': row['status'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'filename': row['filename'],
            'args': json.loads(row['args_json']) if row['args_json'] else [],
            'kwargs': json.loads(row['kwargs_json']) if row['kwargs_json'] else {},
            'result': json.loads(row['result_json']) if row['result_json'] else None,
            'logs': json.loads(row['logs_json']) if row['logs_json'] else [],
            'active': bool(row['active']),
            'waiting': bool(row['waiting']),
            'error': row['error']
        }
    
    def close_connections(self):
        """Close all thread-local connections"""
        if hasattr(self.local, 'connection'):
            self.local.connection.close()
            del self.local.connection
