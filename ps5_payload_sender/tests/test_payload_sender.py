"""Tests for the pure payload_sender helpers (TCP send is not covered here)."""
from __future__ import annotations

from pathlib import Path

import payload_sender
from payload_sender import DEFAULT_ELF_PORT, DEFAULT_JS_PORT, DEFAULT_LUA_PORT, get_payload_path, resolve_port


class TestResolvePort:
    def test_explicit_port_wins(self):
        assert resolve_port("anything.lua", 1234) == 1234
        assert resolve_port("anything.elf", 1234) == 1234

    def test_lua_default(self):
        assert resolve_port("exploit.lua") == DEFAULT_LUA_PORT

    def test_elf_default(self):
        assert resolve_port("goldhen.elf") == DEFAULT_ELF_PORT

    def test_extension_case_insensitive(self):
        assert resolve_port("exploit.LUA") == DEFAULT_LUA_PORT
        assert resolve_port("goldhen.ELF") == DEFAULT_ELF_PORT
        assert resolve_port("etaHEN.BIN") == DEFAULT_ELF_PORT

    def test_bin_routes_to_elf_port(self):
        # .bin files (e.g. etaHEN) are renamed ELF payloads — same loader port
        assert resolve_port("etaHEN.bin") == DEFAULT_ELF_PORT

    def test_js_routes_to_js_port(self):
        assert resolve_port("lapse.js") == DEFAULT_JS_PORT

    def test_js_explicit_port_wins(self):
        assert resolve_port("lapse.js", 12345) == 12345

    def test_unknown_extension_falls_back_to_elf(self):
        assert resolve_port("mystery.xyz") == DEFAULT_ELF_PORT


class TestGetPayloadPath:
    def test_strips_directory_traversal(self, monkeypatch, tmp_path):
        monkeypatch.setattr(payload_sender, "PAYLOAD_DIR", tmp_path)
        result = get_payload_path("../../etc/passwd")
        assert result == tmp_path / "passwd"

    def test_strips_nested_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(payload_sender, "PAYLOAD_DIR", tmp_path)
        result = get_payload_path("subdir/goldhen.elf")
        assert result == tmp_path / "goldhen.elf"

    def test_plain_filename(self, monkeypatch, tmp_path):
        monkeypatch.setattr(payload_sender, "PAYLOAD_DIR", tmp_path)
        assert get_payload_path("goldhen.elf") == tmp_path / "goldhen.elf"
