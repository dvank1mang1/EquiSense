from app.jobs.queue import InMemoryJobQueue


def test_inmemory_job_queue_snapshot_contains_dead_letter() -> None:
    queue = InMemoryJobQueue()
    snap = queue.snapshot(stale_after_sec=60)
    assert snap["queued"] == 0
    assert snap["dead_letter"] == 0
