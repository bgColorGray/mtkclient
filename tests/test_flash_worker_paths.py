#!/usr/bin/python3
# -*- coding: utf-8 -*-
# (c) B.Kerler 2018-2026 GPLv3 License
"""The flasher must not write runtime files into its working directory.

Launched from Finder, the app starts with "/" as its working directory.
mtkclient defaults hwparam_path to ".", so it tried to create
./hwparam.json on the read-only system volume and the flash failed before
reaching the device.
"""
import os

from mtkclient.gui.flash.flash_worker import user_data_dir


def test_user_data_dir_exists_and_is_writable():
    path = user_data_dir()
    assert os.path.isdir(path)
    assert os.access(path, os.W_OK)


def test_user_data_dir_is_absolute_and_not_the_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = user_data_dir()
    assert os.path.isabs(path)
    assert os.path.realpath(path) != os.path.realpath(os.getcwd())


def test_user_data_dir_is_stable_across_working_directories(tmp_path, monkeypatch):
    first = user_data_dir()
    monkeypatch.chdir(tmp_path)
    assert user_data_dir() == first


def test_worker_passes_the_data_dir_to_connect(monkeypatch, tmp_path):
    # Regression: setting config.hwparam_path was not enough, because
    # DaHandler.connect() replaces a missing directory with "." and the
    # preloader then overwrites hwparam_path with it.
    from types import SimpleNamespace
    from mtkclient.gui.flash import flash_worker

    seen = []

    class FakeMtk:
        def __init__(self, config, loglevel):
            self.config = config

    class FakeHandler:
        def __init__(self, mtk, loglevel):
            self.mtk = mtk

        def connect(self, mtk, directory=None):
            seen.append((directory, mtk.config.hwparam_path))
            return None   # behave like "no phone yet"

    monkeypatch.setattr(flash_worker, "Mtk", FakeMtk)
    monkeypatch.setattr(flash_worker, "DaHandler", FakeHandler)
    monkeypatch.chdir(tmp_path)

    worker = flash_worker.FlashWorker(flash_xml="unused", selected=[])
    ok, retry, _ = worker._attempt(SimpleNamespace(da_loader=""))

    expected = user_data_dir()
    assert seen == [(expected, expected)]
    assert (ok, retry) == (False, True)


def test_default_hwparam_path_is_still_the_cwd():
    # Guards the reason this helper exists: mtkclient's own default is ".",
    # which is why the worker has to override it.
    from mtkclient.config.mtk_config import MtkConfig
    assert MtkConfig().hwparam_path == "."
