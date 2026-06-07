"""Regression tests for three issues caught by the post-PR-39 audit:

1. `import_payload` wiped existing `published_at` when the new payload
   came from a folder source (frontend sends `""`).
2. `parse_backup_archive` was case-sensitive on the ``payloads/``
   prefix — a Windows-edited ZIP with ``Payloads/`` would silently
   drop every binary.
3. The release-mode branch of `checkSourceUpdates` (frontend) did
   not pre-clear stale `state.updateResults` entries for the repo,
   so a payload updated via some other path stayed flagged forever.
   The folder-mode branch already cleared them; this restores parity.

Tests #1 and #2 are backend; #3 lives in the frontend and is
verified by a static-content check against the served JS bundle.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def storage_module(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
    import config as cfg
    base = tmp_path / "config"
    base.mkdir()
    monkeypatch.setattr(cfg, "CONFIG_BASE",       base)
    monkeypatch.setattr(cfg, "PAYLOAD_DIR",       base / "payloads")
    monkeypatch.setattr(cfg, "PAYLOAD_META_FILE", base / "payload_meta.json")
    import storage
    monkeypatch.setattr(storage, "CONFIG_BASE",       base)
    monkeypatch.setattr(storage, "PAYLOAD_DIR",       base / "payloads")
    monkeypatch.setattr(storage, "PAYLOAD_META_FILE", base / "payload_meta.json")
    storage.PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return storage


# ── Bug #2: case-insensitive payloads/ ─────────────────────────────


def test_parse_archive_accepts_uppercase_payload_prefix(storage_module):
    storage = storage_module
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("backup.json", json.dumps({"version": 1}))
        zf.writestr("Payloads/foo.elf", b"binary")  # ← capital P
        zf.writestr("PAYLOADS/bar.lua", b"-- lua") # ← all caps
    _, payloads = storage.parse_backup_archive(buf.getvalue())
    assert payloads == {"foo.elf": b"binary", "bar.lua": b"-- lua"}


def test_parse_archive_still_rejects_non_payload_prefix(storage_module):
    """Make sure the case-insensitive prefix didn't accidentally
    swallow other directories."""
    storage = storage_module
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("backup.json",              json.dumps({"version": 1}))
        zf.writestr("payloads/legit.elf",       b"yes")
        zf.writestr("payload_meta/junk.elf",    b"no")
        zf.writestr("logs/payloads_dump.lua",   b"no")
        zf.writestr("source/payloads.txt",      b"no")
    _, payloads = storage.parse_backup_archive(buf.getvalue())
    assert set(payloads.keys()) == {"legit.elf"}


# ── Bug #1: import_payload preserves published_at ─────────────────


@pytest.fixture
def import_module(tmp_path, monkeypatch, storage_module):
    """Build a TestClient that hits /api/payloads/import."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

    # Stub the network download so the test stays offline + deterministic
    from routers import payloads as payloads_router
    monkeypatch.setattr(
        payloads_router,
        "gh_download_payload",
        lambda download_url, asset_name: (b"\x7fELF stub binary", asset_name),
    )
    return storage_module, payloads_router


def test_import_preserves_existing_published_at_when_new_is_empty(
    import_module, monkeypatch,
):
    """User flow: a payload was first imported from a release source
    (versions carry real `published_at`). The user later re-adds the
    same repo as a folder source and clicks Re-scan + Import — the
    frontend sends every version with ``published_at=""``. The merge
    must keep the existing dates, otherwise `sort_versions` regresses
    to the legacy ranking and the UI's "(latest)" label flips back."""
    storage, _ = import_module

    # Seed the meta with the prior release-import (has dates)
    storage.save_payload_meta({"foo.elf": {
        "repo": "x/y", "asset": "foo.elf", "version": "2.0",
        "versions": [
            {"tag": "2.0", "download_url": "https://r/2.0",
             "published_at": "2026-05-01T00:00:00Z"},
            {"tag": "1.0", "download_url": "https://r/1.0",
             "published_at": "2026-01-01T00:00:00Z"},
        ],
    }})

    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)

    # Re-import: frontend sends folder-mode payload (no dates)
    r = c.post("/api/payloads/import", json={
        "repo": "x/y", "asset_name": "foo.elf",
        "download_url": "https://r/2.0", "version": "2.0",
        "all_versions": [
            {"tag": "2.0", "download_url": "https://r/2.0", "published_at": ""},
            {"tag": "1.0", "download_url": "https://r/1.0", "published_at": ""},
        ],
        "release_published_at": "",
    })
    assert r.status_code == 200, r.text

    meta = storage.load_payload_meta()["foo.elf"]
    by_tag = {v["tag"]: v for v in meta["versions"]}
    assert by_tag["2.0"]["published_at"] == "2026-05-01T00:00:00Z"
    assert by_tag["1.0"]["published_at"] == "2026-01-01T00:00:00Z"


def test_import_accepts_new_published_at_when_provided(import_module):
    """Inverse case: a fresh import with real dates supplied by the
    frontend must persist those dates verbatim (no regression from
    the preserve-existing logic)."""
    storage, _ = import_module
    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)

    r = c.post("/api/payloads/import", json={
        "repo": "x/y", "asset_name": "bar.elf",
        "download_url": "https://r/2.0", "version": "2.0",
        "all_versions": [
            {"tag": "2.0", "download_url": "https://r/2.0",
             "published_at": "2026-05-13T00:00:00Z"},
        ],
        "release_published_at": "2026-05-13T00:00:00Z",
    })
    assert r.status_code == 200, r.text
    meta = storage.load_payload_meta()["bar.elf"]
    assert meta["versions"][0]["published_at"] == "2026-05-13T00:00:00Z"


# ── Bug #3: release-branch clears stale updateResults ─────────────


def test_release_branch_clears_stale_update_results_in_served_js():
    """Static check: the served PayloadSources.js must clear the
    repo's prior `state.updateResults` entries in the release branch
    of `checkSourceUpdates`, matching the folder-mode branch."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
    from fastapi.testclient import TestClient
    import main
    js = TestClient(main.app).get("/static/js/PayloadSources.js").text

    # Folder branch (already had this)
    assert ".filter(k => state.updateResults[k].repo === repo)" in js
    # The release branch should now have the same dedup. We check
    # for at least two occurrences — one for folder, one for release.
    assert js.count("state.updateResults[k].repo === repo") >= 2, (
        "release-mode branch of checkSourceUpdates still does not "
        "pre-clear stale state.updateResults entries"
    )


# ── v1.1.13: set-default-version validates tag exists ─────────────


def test_set_default_version_rejects_unknown_tag(import_module):
    """Setting an active version that doesn't exist in versions[]
    would leave the meta record in a state where `version` doesn't
    match any tracked entry — list_payloads then falls through to
    `versions[0]["tag"]` and silently mislabels the active version."""
    storage, _ = import_module
    storage.save_payload_meta({"foo.elf": {
        "repo": "x/y", "asset": "foo.elf", "version": "1.0",
        "versions": [
            {"tag": "1.0", "download_url": "https://r/1.0"},
            {"tag": "2.0", "download_url": "https://r/2.0"},
        ],
    }})

    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)

    r = c.post("/api/payloads/foo.elf/set-default-version",
               json={"version": "9.9.9"})
    assert r.status_code == 422
    assert "not tracked" in r.text


def test_set_default_version_accepts_known_tag(import_module):
    storage, _ = import_module
    storage.save_payload_meta({"foo.elf": {
        "repo": "x/y", "asset": "foo.elf", "version": "1.0",
        "versions": [
            {"tag": "1.0", "download_url": "https://r/1.0"},
            {"tag": "2.0", "download_url": "https://r/2.0"},
        ],
    }})

    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)

    r = c.post("/api/payloads/foo.elf/set-default-version",
               json={"version": "2.0"})
    assert r.status_code == 200
    assert storage.load_payload_meta()["foo.elf"]["version"] == "2.0"


def test_set_default_version_legacy_empty_versions_accepts_any(import_module):
    """Legacy meta entries that predate the versions[] field must keep
    accepting any tag — otherwise existing installs would start
    rejecting their own dropdown choices."""
    storage, _ = import_module
    storage.save_payload_meta({"foo.elf": {
        "repo": "x/y", "asset": "foo.elf", "version": "latest",
        # NB: no "versions" key
    }})

    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)

    r = c.post("/api/payloads/foo.elf/set-default-version",
               json={"version": "anything-goes"})
    assert r.status_code == 200


# ── v1.1.13: delete source unlinks orphan meta ────────────────────


def test_delete_source_unlinks_orphan_meta(import_module, monkeypatch):
    """When a source is removed, payload_meta entries that referenced
    it must be unlinked too — otherwise the UI shows orphan payloads
    that can never be checked for updates again."""
    storage, _ = import_module
    storage.save_payload_meta({
        "from_x.elf": {"repo": "x/y", "asset": "from_x.elf", "version": "1.0"},
        "other.elf":  {"repo": "z/w", "asset": "other.elf",  "version": "1.0"},
    })
    # Point load_sources at a sources.json file so delete can rewrite it.
    import config as cfg
    sources_file = cfg.CONFIG_BASE / "sources.json"
    sources_file.write_text(
        '[{"repo": "x/y", "filter": "", "source_type": "folder", '
        '"folder": "", "display_name": ""}]',
        encoding="utf-8",
    )
    monkeypatch.setattr(storage, "SOURCES_FILE", sources_file)
    import config as cfg2
    monkeypatch.setattr(cfg2, "SOURCES_FILE", sources_file)

    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)

    r = c.delete("/api/sources/x/y")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["orphans_unlinked"] == ["from_x.elf"]

    meta = storage.load_payload_meta()
    assert "from_x.elf" not in meta
    assert "other.elf"  in meta, "unrelated payload must survive"
