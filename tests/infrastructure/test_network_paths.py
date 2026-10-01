from pathlib import Path

import pytest

from infrastructure.network_paths import resolve_mapped_drive


@pytest.fixture
def s_drive_mapped(monkeypatch):
    monkeypatch.setenv("MAPPED_DRIVE_S_UNC", r"\\LAB-SERVER\LabShare")


def test_translates_mapped_drive_to_unc(s_drive_mapped):
    result = resolve_mapped_drive(r"S:\Testing_Requests\Fxfilm TX\file.xlsx")
    assert result == Path(r"\\LAB-SERVER\LabShare\Testing_Requests\Fxfilm TX\file.xlsx")


def test_case_insensitive_drive_letter(s_drive_mapped):
    result = resolve_mapped_drive(r"s:\Testing_Requests\file.xlsx")
    assert result == Path(r"\\LAB-SERVER\LabShare\Testing_Requests\file.xlsx")


def test_bare_drive_root_translates_correctly(s_drive_mapped):
    result = resolve_mapped_drive("S:/")
    assert result == Path(r"\\LAB-SERVER\LabShare")


def test_unconfigured_drive_letter_is_a_no_op(s_drive_mapped):
    # Only S: has a mapping configured -- a Z: path must pass through unchanged.
    result = resolve_mapped_drive(r"Z:\USBSTORAGE\file.xlsx")
    assert result == Path(r"Z:\USBSTORAGE\file.xlsx")


def test_no_mapping_configured_is_a_no_op(monkeypatch):
    monkeypatch.delenv("MAPPED_DRIVE_S_UNC", raising=False)
    result = resolve_mapped_drive(r"S:\Testing_Requests\file.xlsx")
    assert result == Path(r"S:\Testing_Requests\file.xlsx")


def test_already_unc_path_is_a_no_op(s_drive_mapped):
    result = resolve_mapped_drive(r"\\LAB-SERVER\LabShare\Testing_Requests\file.xlsx")
    assert result == Path(r"\\LAB-SERVER\LabShare\Testing_Requests\file.xlsx")


def test_relative_path_is_a_no_op(s_drive_mapped):
    result = resolve_mapped_drive(r"Testing_Requests\file.xlsx")
    assert result == Path(r"Testing_Requests\file.xlsx")
