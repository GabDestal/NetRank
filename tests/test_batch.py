"""Tests for app.database.batch."""
# pylint: disable=missing-function-docstring

import pytest

from app.database.batch import run_batched
from tests.fakes import FakeDriver


def test_run_batched_splits_rows_into_batches():
    driver = FakeDriver()
    rows = [{"i": i} for i in range(5)]
    assert run_batched(driver, "UNWIND $rows AS row RETURN row", rows, batch_size=2) == 5
    assert [params["rows"] for _, params, _ in driver.queries] == [rows[0:2], rows[2:4], rows[4:5]]


def test_run_batched_with_no_rows_sends_nothing():
    driver = FakeDriver()
    assert run_batched(driver, "UNWIND $rows AS row RETURN row", []) == 0
    assert not driver.queries


def test_run_batched_rejects_bad_batch_size():
    with pytest.raises(ValueError):
        run_batched(FakeDriver(), "RETURN 1", [{}], batch_size=0)
