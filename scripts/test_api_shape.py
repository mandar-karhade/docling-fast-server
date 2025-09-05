import sys
import types
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeJobStore:
    def __init__(self):
        self._jobs = {}

    def get_job(self, job_id):
        return self._jobs.get(job_id)

    def create_job(self, job_id, job_data):
        if job_id in self._jobs:
            return False
        self._jobs[job_id] = job_data or {"id": job_id}
        return True


class DummyJob:
    def __init__(self, job_id):
        self.id = job_id


class FakeQueueManager:
    def __init__(self):
        self.job_store = FakeJobStore()

    def enqueue_job(self, func, *args, **kwargs):
        job_id = kwargs.get("job_id") or "GEN-123"
        # simulate storing the job
        self.job_store.create_job(job_id, {"id": job_id})
        return DummyJob(job_id)


def build_app_with_fake_queue():
    # Monkeypatch import for queue_manager before importing routes
    fake_module = types.SimpleNamespace(queue_manager=FakeQueueManager())
    sys.modules['src.services.queue_manager'] = fake_module

    from src.routes import ocr as ocr_routes  # noqa: WPS433

    app = FastAPI()
    app.include_router(ocr_routes.router)
    return app, fake_module.queue_manager


def make_pdf_file():
    return {'file': ('doc.pdf', b'%PDF-1.4\n%%EOF', 'application/pdf')}


def main():
    app, fake_qm = build_app_with_fake_queue()
    client = TestClient(app)

    # 1) No ID provided → returns generated job_id
    r = client.post("/ocr/async", files=make_pdf_file())
    assert r.status_code == 200, r.text
    assert r.json().get("job_id") == "GEN-123", r.json()
    print("OK: POST /ocr/async without id → 200 and GEN-123")

    # 2) Provided job_id (new) → echo back
    r = client.post("/ocr/async", files=make_pdf_file(), data={"job_id": "MY-JOB-1"})
    assert r.status_code == 200, r.text
    assert r.json().get("job_id") == "MY-JOB-1", r.json()
    print("OK: POST /ocr/async with job_id → 200 and echo job_id")

    # 3) Duplicate job_id → 409 with {job_id}
    fake_qm.job_store.create_job("DUP-1", {"id": "DUP-1"})
    r = client.post("/ocr/async", files=make_pdf_file(), data={"job_id": "DUP-1"})
    assert r.status_code == 409, r.text
    assert r.json() == {"job_id": "DUP-1"}, r.json()
    print("OK: POST /ocr/async duplicate job_id → 409 with {job_id}")

    # 4) request_id alias duplicate → 409
    fake_qm.job_store.create_job("ALIAS-EXIST", {"id": "ALIAS-EXIST"})
    r = client.post("/ocr/async", files=make_pdf_file(), data={"request_id": "ALIAS-EXIST"})
    assert r.status_code == 409, r.text
    assert r.json() == {"job_id": "ALIAS-EXIST"}, r.json()
    print("OK: POST /ocr/async duplicate request_id → 409 with {job_id}")

    # 5) request_id alias new → 200 echo as job_id
    r = client.post("/ocr/async", files=make_pdf_file(), data={"request_id": "ALIAS-NEW"})
    assert r.status_code == 200, r.text
    assert r.json().get("job_id") == "ALIAS-NEW", r.json()
    print("OK: POST /ocr/async request_id (alias) → 200 echo as job_id")

    print("All shape tests passed.")


if __name__ == "__main__":
    main()


