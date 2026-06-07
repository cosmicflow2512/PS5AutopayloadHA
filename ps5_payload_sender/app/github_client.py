"""
GitHub API helpers for fetching release assets and downloading payloads.

All functions are synchronous (blocking) – run them via asyncio.run_in_executor.

Detection priority:
  1. Scan repository file tree for .elf / .lua (Git Trees API, single call, cached).
  2. Fall back to release assets if no repo files found – ZIPs are always ignored.
"""
from __future__ import annotations

import io
import json
import time
import urllib.parse
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

GITHUB_API = "https://api.github.com"

# Hosts download_payload() will fetch from. Every URL the add-on hands to
# urlopen() ultimately originates from a GitHub API response (release asset
# browser_download_url, raw.githubusercontent.com for repo files), so locking
# the download path to known GitHub hosts is essentially free and blocks SSRF
# via tampered payload metadata.
_ALLOWED_DOWNLOAD_HOSTS = frozenset({
    "github.com",
    "api.github.com",
    "raw.githubusercontent.com",
    "objects.githubusercontent.com",
    "codeload.github.com",
})

def _build_headers() -> dict:
    from config import GITHUB_TOKEN
    h = {
        "User-Agent": "PS5AutopayloadHA/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h

_PAYLOAD_EXTENSIONS = {".elf", ".lua", ".bin", ".jar", ".js"}

# ── In-memory tree cache ──────────────────────────────────────────
_tree_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_CACHE_TTL = 300  # seconds
_CACHE_MAX = 100  # hard cap; oldest entry evicted when exceeded


def _gh_get(url: str, timeout: int = 15) -> Any:
    req = urllib.request.Request(url, headers=_build_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise RuntimeError(
                "GitHub API rate limit exceeded — add a GitHub token in add-on options to raise the limit."
            ) from e
        raise


# ── Repo file scanning ────────────────────────────────────────────

def get_repo_folders(owner: str, repo: str) -> List[str]:
    """
    Return top-level directory names in the repository.
    Used to let users select which folder to scan for payloads.
    """
    contents = _gh_get(f"{GITHUB_API}/repos/{owner}/{repo}/contents", timeout=10)
    return sorted(item["name"] for item in contents if item.get("type") == "dir")


def scan_repo_files(
    owner: str, repo: str, folder: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Scan the repository tree for .elf / .lua files using the Git Trees API
    (single recursive call).  Results are cached for _CACHE_TTL seconds.

    If *folder* is given (e.g. "payloads"), only files under that folder are
    returned.  The full tree is always fetched and cached so repeated calls
    with different folder values are cheap.

    Returns a list of:
      { asset_name, path, download_url, sha, tag:"latest", ext, is_zip:False,
        source_type:"repo_file" }
    """
    key = f"{owner}/{repo}"
    now = time.monotonic()
    if key in _tree_cache:
        cached_at, cached = _tree_cache[key]
        if now - cached_at < _CACHE_TTL:
            return _filter_by_folder(cached, folder)

    result = _do_scan_repo_files(owner, repo)
    if len(_tree_cache) >= _CACHE_MAX:
        oldest_key = min(_tree_cache, key=lambda k: _tree_cache[k][0])
        _tree_cache.pop(oldest_key, None)
    _tree_cache[key] = (now, result)
    return _filter_by_folder(result, folder)


def _filter_by_folder(
    files: List[Dict[str, Any]], folder: Optional[str]
) -> List[Dict[str, Any]]:
    if not folder:
        return files
    prefix = folder.strip("/") + "/"
    return [f for f in files if f["path"].startswith(prefix)]


def _do_scan_repo_files(owner: str, repo: str) -> List[Dict[str, Any]]:
    # 1. Discover default branch
    repo_info = _gh_get(f"{GITHUB_API}/repos/{owner}/{repo}", timeout=10)
    branch = repo_info.get("default_branch", "main")

    # 2. Full recursive tree in one request
    tree_data = _gh_get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1",
        timeout=20,
    )

    results: List[Dict[str, Any]] = []
    for item in tree_data.get("tree", []):
        if item.get("type") != "blob":
            continue
        path = item["path"]
        ext = Path(path).suffix.lower()
        if ext not in _PAYLOAD_EXTENSIONS:
            continue
        filename = Path(path).name
        raw_url = (
            f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        )
        results.append({
            "asset_name":  filename,
            "path":        path,
            "download_url": raw_url,
            "sha":         item.get("sha", ""),
            "tag":         "latest",
            "ext":         ext,
            "is_zip":      False,
            "source_type": "repo_file",
        })
    return results


def invalidate_cache(owner: str, repo: str) -> None:
    _tree_cache.pop(f"{owner}/{repo}", None)


# ── Release assets ────────────────────────────────────────────────

def get_releases(owner: str, repo: str) -> List[Dict[str, Any]]:
    """
    Return .elf/.lua and .zip release assets for the last 30 releases.
    ZIP assets have is_zip=True; download_payload() handles extraction.
    Includes published_at and asset_updated_at for smart update detection.
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases?per_page=30"
    releases = _gh_get(url)

    result: List[Dict[str, Any]] = []
    for rel in releases[:30]:
        tag          = rel.get("tag_name", "")
        published_at = rel.get("published_at", "")
        release_id   = rel.get("id", 0)
        for asset in rel.get("assets", []):
            ext    = Path(asset["name"]).suffix.lower()
            is_zip = ext == ".zip"
            if ext not in _PAYLOAD_EXTENSIONS and not is_zip:
                continue
            result.append({
                "tag":              tag,
                "asset_name":       asset["name"],
                "download_url":     asset["browser_download_url"],
                "size":             asset.get("size", 0),
                "release_id":       release_id,
                "ext":              ext,
                "is_zip":           is_zip,
                "source_type":      "release",
                "published_at":     published_at,
                "asset_updated_at": asset.get("updated_at", ""),
            })
    return result


# ── Download helpers ──────────────────────────────────────────────

def _assert_allowed_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Refusing non-https download URL: {url}")
    if parsed.hostname not in _ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError(f"Refusing download from unknown host: {parsed.hostname}")


def download(url: str) -> bytes:
    _assert_allowed_url(url)
    req = urllib.request.Request(url, headers={
        "User-Agent": "PS5AutopayloadHA/1.0",
        "Accept": "application/octet-stream",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def download_payload(url: str, prefer_name: Optional[str] = None) -> Tuple[bytes, str]:
    """
    Download *url* and return (payload_bytes, filename).

    ZIP archives are handled transparently (internal use only – they are never
    surfaced in the UI):
      1. Download into memory
      2. Scan for .elf / .lua
      3. Pick *prefer_name* if present, else first match
    """
    raw = download(url)
    if url.lower().endswith(".zip") or _is_zip(raw):
        return _extract_from_zip(raw, prefer_name)
    filename = prefer_name or Path(url.split("?")[0]).name
    return raw, filename


def _is_zip(data: bytes) -> bool:
    return data[:4] == b"PK\x03\x04"


def _extract_from_zip(data: bytes, prefer_name: Optional[str]) -> Tuple[bytes, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        candidates = [
            n for n in names
            if Path(n).suffix.lower() in _PAYLOAD_EXTENSIONS
        ]
        if not candidates:
            # Surface what IS in the archive so the user can tell whether
            # the release shipped source code, a different artefact, or
            # the wrong file. Backend's HTTPException(502, …) bubbles
            # this string up to the UI's failed-row error chip.
            preview = ", ".join(names[:8])
            if len(names) > 8:
                preview += f", … (+{len(names) - 8} more)"
            raise ValueError(
                f"No .elf or .lua found in archive. "
                f"Archive contains: {preview}. "
                f"This release probably ships source code instead of a "
                f"drop-in payload — re-add the source pointing at a "
                f"specific file URL, or skip this update."
            )
        target = next(
            (n for n in candidates if Path(n).name == prefer_name),
            candidates[0],
        )
        return zf.read(target), Path(target).name
