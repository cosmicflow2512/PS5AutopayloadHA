"""Tests for github_client._extract_from_zip — specifically that
errors are informative when a release's ZIP doesn't contain a payload.

User report: clicking "Update Selected" on Gezine/Luac0re's
v2.2d release downloaded `Luac0re_2.2d.zip`, which is a source
bundle without any `.lua` file. The old error message just said
"No valid payload (.elf/.lua) found in archive" — useless for
debugging. New message includes the archive contents so the user
can see WHY it failed.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from github_client import _extract_from_zip, _PAYLOAD_EXTENSIONS


def _make_zip(files: dict) -> bytes:
    """Build an in-memory ZIP from {name: bytes_or_str}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode()
            zf.writestr(name, data)
    return buf.getvalue()


def test_extract_picks_lua_payload():
    zb = _make_zip({"poops_ps5.lua": "print('hi')"})
    payload, name = _extract_from_zip(zb, prefer_name=None)
    assert name == "poops_ps5.lua"
    assert payload == b"print('hi')"


def test_extract_picks_elf_payload():
    zb = _make_zip({"kstuff.elf": b"\x7fELF\x02\x01"})
    payload, name = _extract_from_zip(zb, prefer_name=None)
    assert name == "kstuff.elf"


def test_extract_honours_prefer_name():
    zb = _make_zip({"a.lua": "first", "b.lua": "second"})
    payload, name = _extract_from_zip(zb, prefer_name="b.lua")
    assert name == "b.lua"
    assert payload == b"second"


def test_extract_finds_nested_payload():
    """Source-bundle archives put files under a top-level dir
    (e.g. ``ProjectName-2.2d/foo.lua``). The extractor must walk
    namelist() — Path(...).suffix works on the full path so this
    already works."""
    zb = _make_zip({"Project-2.2d/poops_ps5.lua": "x"})
    payload, name = _extract_from_zip(zb, prefer_name=None)
    assert name == "poops_ps5.lua"


def test_extract_lists_archive_contents_when_no_payload():
    """The user-visible failure mode — what we shipped this PR for.
    Error message must include the archive's contents so the user
    knows what they actually downloaded."""
    zb = _make_zip({
        "README.md":        "docs",
        "src/main.c":       "int main(){}",
        "src/loader.h":     "// header",
        "build.sh":         "#!/bin/sh",
        "LICENSE":          "MIT",
    })
    with pytest.raises(ValueError) as exc_info:
        _extract_from_zip(zb, prefer_name=None)
    msg = str(exc_info.value)
    assert "No .elf or .lua" in msg
    # Each filename is visible in the error so the user can see why
    assert "README.md" in msg
    assert "src/main.c" in msg
    assert "build.sh" in msg


def test_extract_caps_long_file_listing():
    """A massive source bundle would produce a wall-of-text error.
    The listing is capped at 8 entries with a "+N more" suffix."""
    files = {f"src/file_{i:02d}.c": "x" for i in range(20)}
    zb = _make_zip(files)
    with pytest.raises(ValueError) as exc_info:
        _extract_from_zip(zb, prefer_name=None)
    msg = str(exc_info.value)
    assert "+12 more" in msg     # 20 entries - 8 shown = 12 hidden


def test_payload_extensions_accepts_all_supported_types():
    """The GitHub scanner accepts all supported payload extensions —
    kept in sync with config.ALLOWED_PAYLOAD_EXTENSIONS."""
    assert _PAYLOAD_EXTENSIONS == {".elf", ".lua", ".bin", ".jar", ".js"}
