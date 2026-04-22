import errno

import pytest

from app.services.db_unreachable import is_benign_database_unreachable


def test_connection_refused_error() -> None:
    e = ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused")
    assert is_benign_database_unreachable(e) is True


def test_errno_61_oserror() -> None:
    e = OSError(errno.ECONNREFUSED, "Connection refused")
    assert is_benign_database_unreachable(e) is True


@pytest.mark.parametrize(
    "msg",
    [
        "[Errno 61] Connection refused",
        "connection refused",
        "could not connect to server",
    ],
)
def test_message_heuristics(msg: str) -> None:
    assert is_benign_database_unreachable(RuntimeError(msg)) is True


def test_unrelated_error() -> None:
    assert is_benign_database_unreachable(ValueError("bad payload")) is False
