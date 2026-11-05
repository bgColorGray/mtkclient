#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2026 GPLv3 License
"""Tests for fwflash's wait-and-retry loop (SP Flash Tool style plug-in flow)."""
from types import SimpleNamespace

import pytest

import mtk as mtk_cli


def _fake_main(outcomes, calls):
    """A stand-in for Main whose run() reports one outcome per attempt.

    An outcome of None means handle_da_cmds was never reached (device not
    connected, unplugged mid-handshake, DA upload failed).
    """
    class FakeMain:
        def __init__(self, args):
            self.args = args

        def run(self, parser):
            calls.append(1)
            outcome = outcomes[len(calls) - 1]
            if outcome is not None:
                self.args.fwflash_state = outcome
            raise SystemExit(0)

    return FakeMain


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(mtk_cli.time, "sleep", lambda s: None)


def test_waits_again_until_flash_completes(monkeypatch, no_sleep):
    calls = []
    monkeypatch.setattr(mtk_cli, "Main", _fake_main([None, "retry", "done"], calls))
    assert mtk_cli.run_fwflash(SimpleNamespace(), parser=None) == 0
    assert len(calls) == 3


def test_stops_without_retry_once_upgrade_started(monkeypatch, no_sleep):
    calls = []
    monkeypatch.setattr(mtk_cli, "Main", _fake_main([None, "failed", "done"], calls))
    assert mtk_cli.run_fwflash(SimpleNamespace(), parser=None) == 1
    assert len(calls) == 2


def test_stops_on_fatal_package_error(monkeypatch, no_sleep):
    calls = []
    monkeypatch.setattr(mtk_cli, "Main", _fake_main(["fatal"], calls))
    assert mtk_cli.run_fwflash(SimpleNamespace(), parser=None) == 1
    assert len(calls) == 1


def test_state_is_reset_between_attempts(monkeypatch, no_sleep):
    # A stale "retry" from attempt 1 must not leak into attempt 2's result.
    calls = []
    monkeypatch.setattr(mtk_cli, "Main", _fake_main(["retry", None, "done"], calls))
    assert mtk_cli.run_fwflash(SimpleNamespace(), parser=None) == 0
    assert len(calls) == 3
