from datetime import datetime
from typing import Dict, Optional, List, Any
from pydantic import BaseModel


class JobLog(BaseModel):
    timestamp: str
    message: str


class WorkerInfo(BaseModel):
    worker_id: int
    worker_number: int
    worker_name: str
    cpu_percent: float
    memory_mb: float
    num_threads: int
    status: str


class Job(BaseModel):
    id: str
    status: str
    created_at: str
    updated_at: str
    uvicorn_worker_number: int
    active: bool
    waiting: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    logs: List[JobLog] = []
    worker_info: WorkerInfo
    rq_job_id: Optional[str] = None
    filename: Optional[str] = None


class JobCreate(BaseModel):
    filename: str


class JobUpdate(BaseModel):
    status: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    active: Optional[bool] = None
    waiting: Optional[bool] = None
    rq_job_id: Optional[str] = None


class JobResponse(BaseModel):
    job_id: str
    status: str
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    filename: Optional[str] = None


class QueueStats(BaseModel):
    queue_name: str
    total_jobs: int
    workers: int
    failed_jobs: int
    started_jobs: int
    deferred_jobs: int
    scheduled_jobs: int


class WorkerStatus(BaseModel):
    name: str
    state: str
    current_job: str
    last_heartbeat: str


class QueueStatus(BaseModel):
    status: str
    queue_stats: QueueStats
    workers: List[WorkerStatus]
    recent_jobs: List[JobResponse]
    timestamp: str
