"""Tests for `.bin` payload support (etaHEN and similar)."""
from __future__ import annotations


class TestAllowlist:
    def test_bin_in_allowed_extensions(self):
        from config import ALLOWED_PAYLOAD_EXTENSIONS
        assert ".bin" in ALLOWED_PAYLOAD_EXTENSIONS

    def test_lua_and_elf_still_allowed(self):
        from config import ALLOWED_PAYLOAD_EXTENSIONS
        assert ".lua" in ALLOWED_PAYLOAD_EXTENSIONS
        assert ".elf" in ALLOWED_PAYLOAD_EXTENSIONS

    def test_random_extensions_still_rejected(self):
        from config import ALLOWED_PAYLOAD_EXTENSIONS
        for ext in (".exe", ".sh", ".js", ".txt", ".zip"):
            assert ext not in ALLOWED_PAYLOAD_EXTENSIONS


class TestGithubScannerAcceptsBin:
    def test_bin_in_github_scanner_extensions(self):
        from github_client import _PAYLOAD_EXTENSIONS
        assert ".bin" in _PAYLOAD_EXTENSIONS
        assert ".elf" in _PAYLOAD_EXTENSIONS
        assert ".lua" in _PAYLOAD_EXTENSIONS


class TestStorageAcceptsBin:
    def test_list_payloads_includes_bin(self, monkeypatch, tmp_path):
        import storage
        monkeypatch.setattr(storage, "PAYLOAD_DIR", tmp_path)
        monkeypatch.setattr(storage, "PAYLOAD_META_FILE", tmp_path / "meta.json")

        (tmp_path / "etaHEN.bin").write_bytes(b"\x7fELF fake")
        (tmp_path / "goldhen.elf").write_bytes(b"\x7fELF fake")
        (tmp_path / "exploit.lua").write_text("-- lua")
        (tmp_path / "readme.txt").write_text("ignored")

        names = {p["name"] for p in storage.list_payloads()}
        assert "etaHEN.bin" in names
        assert "goldhen.elf" in names
        assert "exploit.lua" in names
        assert "readme.txt" not in names
