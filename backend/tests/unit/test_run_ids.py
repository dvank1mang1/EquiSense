from app.jobs.run_ids import new_run_id


def test_new_run_id_unique_per_call() -> None:
    a = new_run_id()
    b = new_run_id()
    assert a != b
    assert "-" in a
    assert len(a) > 20
