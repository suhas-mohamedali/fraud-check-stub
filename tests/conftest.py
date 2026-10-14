import os
import random
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main  # noqa: E402


def make_payments(n, start_line=2):
    return [
        {
            "lineNumber": start_line + i,
            "bsbNumber": "062-000",
            "accountNumber": f"{10000000 + i}",
            "amountCents": 1000 + i,
            "transactionCode": "50",
        }
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """Each test starts with no remembered decisions, a fixed seed and the 5% cap."""
    main._decisions.clear()
    monkeypatch.setattr(main, "rng", random.Random(1234))
    monkeypatch.setattr(main, "REJECT_CAP_PERCENT", 5.0)
    yield
    main._decisions.clear()
