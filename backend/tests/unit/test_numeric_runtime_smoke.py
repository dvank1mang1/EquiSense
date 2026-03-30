"""Always safe to collect when numpy segfaults in the parent (e.g. some CI sandboxes)."""


def test_suite_reached_without_numpy_stack() -> None:
    assert True
