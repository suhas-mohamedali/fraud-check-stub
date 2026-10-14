"""Unit tests for the rejection rule in main._decide / main._key."""
import random

import pytest

import main
from main import APPROVED, DECLINED, PrmPayment
from tests.conftest import make_payments


def payments(n, start_line=2):
    return [PrmPayment(**p) for p in make_payments(n, start_line)]


def rejected(decisions):
    return sum(1 for s in decisions.values() if s == DECLINED)


class TestKey:
    def test_uses_line_number_when_present(self):
        assert main._key(PrmPayment(lineNumber=7), 0) == "L7"

    def test_falls_back_to_position(self):
        assert main._key(PrmPayment(), 3) == "I3"


class TestDecide:
    def test_every_payment_gets_a_or_d(self):
        d = main._decide("f.bpy", payments(100))
        assert len(d) == 100
        assert set(d.values()) <= {APPROVED, DECLINED}

    @pytest.mark.parametrize("n", [1, 5, 19])
    def test_files_under_20_payments_are_never_rejected(self, n):
        for seed in range(50):
            main._decisions.clear()
            main.rng = random.Random(seed)
            assert rejected(main._decide("small.bpy", payments(n))) == 0

    @pytest.mark.parametrize("n", [20, 39, 40, 100, 999, 1000])
    def test_never_more_than_5_percent_rounded_down(self, n):
        cap = n * 5 // 100
        for seed in range(30):
            main._decisions.clear()
            main.rng = random.Random(seed)
            assert rejected(main._decide("f.bpy", payments(n))) <= cap

    def test_cap_is_reached_for_some_seed(self):
        # Rejections are random, so across seeds the full 5% should show up.
        counts = set()
        for seed in range(200):
            main._decisions.clear()
            main.rng = random.Random(seed)
            counts.add(rejected(main._decide("f.bpy", payments(100))))
        assert 5 in counts
        assert 0 in counts

    def test_same_seed_is_repeatable(self):
        main.rng = random.Random(42)
        first = main._decide("a.bpy", payments(200))
        main._decisions.clear()
        main.rng = random.Random(42)
        assert main._decide("a.bpy", payments(200)) == first

    def test_resending_a_file_returns_the_same_decisions(self):
        first = main._decide("f.bpy", payments(200))
        for _ in range(20):
            assert main._decide("f.bpy", payments(200)) == first

    def test_repeated_partial_sends_never_exceed_cap(self):
        # 10 batches of 20 payments for the same file: 200 total, cap 10.
        for b in range(10):
            d = main._decide("f.bpy", payments(20, start_line=2 + b * 20))
            assert rejected(d) <= len(d) * 5 // 100
        assert len(d) == 200

    def test_files_are_independent(self):
        main._decide("a.bpy", payments(100))
        main._decide("b.bpy", payments(50))
        assert len(main._decisions["a.bpy"]) == 100
        assert len(main._decisions["b.bpy"]) == 50

    def test_duplicate_line_numbers_count_once(self):
        ps = payments(30) + payments(30)
        assert len(main._decide("dup.bpy", ps)) == 30

    def test_empty_file(self):
        assert main._decide("empty.bpy", []) == {}

    def test_cap_percent_is_configurable(self, monkeypatch):
        monkeypatch.setattr(main, "REJECT_CAP_PERCENT", 0.0)
        for seed in range(20):
            main._decisions.clear()
            main.rng = random.Random(seed)
            assert rejected(main._decide("f.bpy", payments(500))) == 0
