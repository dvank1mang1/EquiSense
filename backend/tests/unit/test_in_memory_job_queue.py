from app.jobs.queue import InMemoryJobQueue


def test_in_memory_job_queue_enqueue_get_complete() -> None:
    q = InMemoryJobQueue()
    q.enqueue("run-1", {"type": "backtest_single", "ticker": "AAPL", "max_attempts": 3})
    row = q.get_job("run-1")
    assert row is not None
    assert row["status"] == "queued"
    assert row["payload"]["ticker"] == "AAPL"
    assert q.status("run-1") == "queued"

    q.mark_completed("run-1")
    assert q.status("run-1") == "completed"
    assert q.get_job("run-1")["status"] == "completed"


def test_in_memory_job_queue_mark_failed() -> None:
    q = InMemoryJobQueue()
    q.enqueue("run-2", {"type": "x", "max_attempts": 1})
    q.mark_failed("run-2", "boom")
    assert q.status("run-2") == "failed"
    assert q.get_job("run-2")["error"] == "boom"
