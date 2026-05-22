"""Tests for autoload_parser — the .txt flow-file DSL."""
from __future__ import annotations

from autoload_parser import (
    DelayDirective,
    SendDirective,
    WaitPortDirective,
    parse_autoload_file,
    parse_line,
    parse_version_pins,
    set_version_pin,
)


class TestParseLine:
    def test_comment_returns_none(self):
        assert parse_line("# a comment") is None
        assert parse_line("   # indented") is None

    def test_blank_returns_none(self):
        assert parse_line("") is None
        assert parse_line("   ") is None

    def test_payload_without_port(self):
        d = parse_line("goldhen.elf")
        assert isinstance(d, SendDirective)
        assert d.filename == "goldhen.elf"
        assert d.port is None

    def test_payload_with_explicit_port(self):
        d = parse_line("exploit.lua 9026")
        assert isinstance(d, SendDirective)
        assert d.filename == "exploit.lua"
        assert d.port == 9026

    def test_payload_case_insensitive_extension(self):
        d = parse_line("Loader.ELF")
        assert isinstance(d, SendDirective)
        assert d.filename == "Loader.ELF"

    def test_unknown_extension_returns_none(self):
        assert parse_line("not_a_payload.txt") is None
        assert parse_line("not_a_payload.pkg") is None

    def test_bin_payload_parsed(self):
        d = parse_line("kpayload.bin")
        assert isinstance(d, SendDirective)
        assert d.filename == "kpayload.bin"
        assert d.port is None

    def test_jar_payload_parsed(self):
        d = parse_line("bdunjb.jar")
        assert isinstance(d, SendDirective)
        assert d.filename == "bdunjb.jar"
        assert d.port is None

    def test_jar_payload_with_explicit_port(self):
        d = parse_line("bdunjb.jar 9025")
        assert isinstance(d, SendDirective)
        assert d.filename == "bdunjb.jar"
        assert d.port == 9025

    def test_delay(self):
        d = parse_line("!3000")
        assert isinstance(d, DelayDirective)
        assert d.milliseconds == 3000

    def test_delay_negative_clamped_to_zero(self):
        d = parse_line("!-100")
        assert isinstance(d, DelayDirective)
        assert d.milliseconds == 0

    def test_delay_invalid_returns_none(self):
        assert parse_line("!not_a_number") is None

    def test_wait_port_minimal(self):
        d = parse_line("?9021")
        assert isinstance(d, WaitPortDirective)
        assert d.port == 9021
        assert d.timeout_seconds == 60.0
        assert d.interval_ms == 500

    def test_wait_port_with_timeout(self):
        d = parse_line("?9021 90")
        assert isinstance(d, WaitPortDirective)
        assert d.port == 9021
        assert d.timeout_seconds == 90.0
        assert d.interval_ms == 500

    def test_wait_port_with_timeout_and_interval(self):
        d = parse_line("?9021 90 250")
        assert isinstance(d, WaitPortDirective)
        assert d.timeout_seconds == 90.0
        assert d.interval_ms == 250

    def test_wait_port_interval_floor_100ms(self):
        d = parse_line("?9021 90 10")
        assert d.interval_ms == 100

    def test_wait_port_empty_returns_none(self):
        assert parse_line("?") is None


class TestParseAutoloadFile:
    def test_full_goldhen_chain(self):
        content = "\n".join([
            "# Full GoldHen automation",
            "?9026 120",
            "exploit.lua",
            "?9021 120 500",
            "goldhen.elf",
        ])
        directives = parse_autoload_file(content)
        assert len(directives) == 4
        assert isinstance(directives[0], WaitPortDirective)
        assert directives[0].port == 9026
        assert isinstance(directives[1], SendDirective)
        assert directives[1].filename == "exploit.lua"
        assert isinstance(directives[2], WaitPortDirective)
        assert isinstance(directives[3], SendDirective)
        assert directives[3].filename == "goldhen.elf"

    def test_skips_blank_and_unparseable_lines(self):
        content = "\n".join(["", "garbage line", "exploit.lua", "  ", "# comment"])
        directives = parse_autoload_file(content)
        assert len(directives) == 1
        assert directives[0].filename == "exploit.lua"


class TestVersionPins:
    def test_parse_single_pin(self):
        content = "# ~version goldhen.elf v2.4b\n?9021\ngoldhen.elf\n"
        assert parse_version_pins(content) == {"goldhen.elf": "v2.4b"}

    def test_parse_multiple_pins(self):
        content = (
            "# ~version exploit.lua v1.0\n"
            "# ~version goldhen.elf v2.4b\n"
            "exploit.lua\ngoldhen.elf\n"
        )
        assert parse_version_pins(content) == {
            "exploit.lua": "v1.0",
            "goldhen.elf": "v2.4b",
        }

    def test_parse_no_pins(self):
        assert parse_version_pins("exploit.lua\ngoldhen.elf\n") == {}

    def test_set_pin_replaces_existing(self):
        content = "# ~version goldhen.elf v1.0\ngoldhen.elf\n"
        updated = set_version_pin(content, "goldhen.elf", "v2.0")
        assert parse_version_pins(updated) == {"goldhen.elf": "v2.0"}
        assert updated.count("~version goldhen.elf") == 1

    def test_set_pin_inserts_before_first_directive(self):
        content = "# header comment\ngoldhen.elf\n"
        updated = set_version_pin(content, "goldhen.elf", "v2.0")
        pins = parse_version_pins(updated)
        assert pins == {"goldhen.elf": "v2.0"}
        lines = updated.splitlines()
        version_idx = next(i for i, l in enumerate(lines) if "~version" in l)
        send_idx = next(i for i, l in enumerate(lines) if l.strip() == "goldhen.elf")
        assert version_idx < send_idx

    def test_set_pin_only_affects_matching_filename(self):
        content = "# ~version a.elf v1\n# ~version b.elf v2\na.elf\nb.elf\n"
        updated = set_version_pin(content, "a.elf", "v9")
        assert parse_version_pins(updated) == {"a.elf": "v9", "b.elf": "v2"}
