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


def test_default_hwparam_path_is_still_the_cwd():
    # Guards the reason this helper exists: mtkclient's own default is ".",
    # which is why the worker has to override it.
    from mtkclient.config.mtk_config import MtkConfig
    assert MtkConfig().hwparam_path == "."
