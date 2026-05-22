from __future__ import annotations

import asyncio
import fnmatch
import urllib.error

from fastapi import APIRouter, HTTPException

from config import PAYLOAD_DIR
from exec_engine import executor
from github_client import (
    get_releases as gh_get_releases,
    get_repo_folders as gh_get_repo_folders,
    scan_repo_files as gh_scan_repo_files,
)
from models import SourceAddRequest, SourceUpdateRequest
from storage import load_payload_meta, load_sources, save_payload_meta, save_sources

router = APIRouter()


async def _run_gh(fn, *args):
    """Run a blocking github_client call in the executor and translate the
    common urllib errors into HTTPException. Keeps the three /api/sources
    handlers free of repeated boilerplate."""
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(executor, fn, *args)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise HTTPException(404, "Repository not found")
        raise HTTPException(502, f"GitHub API error: HTTP {exc.code}")
    except Exception as exc:
        raise HTTPException(502, f"Could not reach GitHub: {exc}")


@router.get("/api/sources")
async def api_get_sources():
    return {"sources": load_sources()}


@router.get("/api/sources/tree")
async def api_sources_tree(repo: str):
    """Return top-level folder names for a GitHub repository."""
    parts = repo.strip().split("/")
    if len(parts) != 2 or not all(p.strip() for p in parts):
        raise HTTPException(400, "Invalid repository format. Use 'owner/repo'")
    owner, repo_name = parts[0].strip(), parts[1].strip()
    folders = await _run_gh(gh_get_repo_folders, owner, repo_name)
    return {"folders": folders}


@router.post("/api/sources")
async def api_add_source(req: SourceAddRequest):
    parts = req.repo.strip().split("/")
    if len(parts) != 2 or not all(p.strip() for p in parts):
        raise HTTPException(400, "Invalid repository format. Use 'owner/repo'")
    owner, repo_name = parts[0].strip(), parts[1].strip()

    if req.source_type == "releases":
        assets = await _run_gh(gh_get_releases, owner, repo_name)
    elif req.source_type == "folder":
        folder = req.folder.strip().strip("/") or None
        assets = await _run_gh(gh_scan_repo_files, owner, repo_name, folder)
    else:
        assets = await _run_gh(gh_scan_repo_files, owner, repo_name)
        if not assets:
            assets = await _run_gh(gh_get_releases, owner, repo_name)

    if not assets:
        raise HTTPException(
            404,
            "No .elf, .lua, .bin or .jar payload files found. "
            "Try a different source type or folder.",
        )

    if req.filter.strip():
        assets = [a for a in assets if fnmatch.fnmatch(a["asset_name"], req.filter.strip())]
        if not assets:
            raise HTTPException(404, f"No payloads match filter '{req.filter}'")

    slug = f"{owner}/{repo_name}"

    asset_versions: dict = {}
    for a in assets:
        aname = a["asset_name"]
        if aname not in asset_versions:
            asset_versions[aname] = []
        entry: dict = {"tag": a["tag"], "download_url": a["download_url"]}
        if a.get("path"):
            entry["path"] = a["path"]
        if a.get("sha"):
            entry["sha"] = a["sha"]
        if not any(v["tag"] == entry["tag"] for v in asset_versions[aname]):
            asset_versions[aname].append(entry)

    meta = load_payload_meta()
    auto_linked: list = []
    for aname, versions in asset_versions.items():
        if (PAYLOAD_DIR / aname).exists() and aname not in meta:
            meta[aname] = {
                "repo": slug, "asset": aname,
                "version": versions[0]["tag"], "versions": versions,
                "display_name": req.display_name.strip(),
            }
            # Persist the git blob SHA for repo_file sources so the
            # check-updates endpoint can detect content changes without
            # a release/tag bump (folder-mode update detection).
            if versions[0].get("sha"):
                meta[aname]["sha"] = versions[0]["sha"]
            auto_linked.append(aname)
    if auto_linked:
        save_payload_meta(meta)

    sources = load_sources()
    if not any(s["repo"] == slug for s in sources):
        sources.append({
            "repo": slug,
            "filter": req.filter.strip(),
            "source_type": req.source_type,
            "folder": req.folder.strip(),
            "display_name": req.display_name.strip(),
        })
        save_sources(sources)

    return {"success": True, "repo": slug, "assets": assets, "auto_linked": auto_linked}


@router.delete("/api/sources/{owner}/{repo_name}")
async def api_delete_source(owner: str, repo_name: str):
    slug = f"{owner}/{repo_name}"
    save_sources([s for s in load_sources() if s["repo"] != slug])
    return {"success": True}


@router.put("/api/sources/{owner}/{repo_name}")
async def api_update_source(owner: str, repo_name: str, req: SourceUpdateRequest):
    """Update an existing source's config without re-scanning."""
    slug = f"{owner}/{repo_name}"
    sources = load_sources()
    updated = False
    for s in sources:
        if s["repo"] == slug:
            s["filter"] = req.filter.strip()
            s["source_type"] = req.source_type
            s["folder"] = req.folder.strip()
            s["display_name"] = req.display_name.strip()
            updated = True
            break
    if not updated:
        raise HTTPException(404, f"Source '{slug}' not found")
    save_sources(sources)
    return {"success": True, "repo": slug}


@router.get("/api/sources/releases")
async def api_source_releases(repo: str, asset: str = ""):
    parts = repo.strip().split("/")
    if len(parts) != 2:
        raise HTTPException(400, "Use 'owner/repo'")
    owner, repo_name = parts
    assets = await _run_gh(gh_get_releases, owner, repo_name)
    if asset:
        assets = [a for a in assets if a["asset_name"] == asset]
    return {"releases": assets}


@router.get("/api/sources/check-updates")
async def api_check_updates():
    meta = load_payload_meta()
    if not meta:
        return {"updates": [], "checked": 0}
    # Index sources by slug so we can look up source_type / folder for
    # each repo. A source set to source_type="folder" has explicitly
    # opted out of release-based update detection — its files come
    # straight from the repo tree (a click on "Re-scan" picks up new
    # commits). Reporting release tags for such a source produces
    # false-positive updates (e.g. `poops_ps5.lua: latest → 2.2d`
    # when 2.2d is a release ZIP, not a folder file).
    sources_by_slug = {s["repo"]: s for s in load_sources()}

    repos: dict = {}
    for fname, m in meta.items():
        repo = m.get("repo", "")
        if repo:
            repos.setdefault(repo, []).append(fname)
    updates: list = []
    errors:  list = []
    loop = asyncio.get_running_loop()
    meta_dirty = False        # set by folder-mode SHA backfill below
    for slug, filenames in repos.items():
        src_cfg = sources_by_slug.get(slug, {})
        parts = slug.split("/")
        if len(parts) != 2:
            errors.append({"repo": slug, "error": "Invalid repository format"})
            continue
        owner, repo_name = parts

        # Folder-typed sources opt out of release-based detection.
        # Instead, compare the git blob SHA of each owned file against
        # the SHA returned by scan_repo_files (Trees API). If the SHA
        # differs the upstream file was modified — that's an update.
        # First time a file is seen without a stored SHA we silently
        # backfill the current SHA as baseline so the user doesn't
        # get a spurious "update" on the very first check.
        if src_cfg.get("source_type") == "folder":
            folder = src_cfg.get("folder") or None
            try:
                tree_files = await loop.run_in_executor(
                    executor, gh_scan_repo_files, owner, repo_name, folder,
                )
            except urllib.error.HTTPError as exc:
                errors.append({"repo": slug, "error": f"HTTP {exc.code}"})
                continue
            except Exception as exc:
                errors.append({"repo": slug, "error": str(exc)})
                continue
            by_name = {f["asset_name"]: f for f in tree_files}
            for fname in filenames:
                tree_entry = by_name.get(fname)
                if not tree_entry:
                    continue
                tree_sha = tree_entry.get("sha", "")
                if not tree_sha:
                    continue
                current_sha = meta.get(fname, {}).get("sha", "")
                if not current_sha:
                    # Backfill baseline; no update reported this round.
                    meta[fname]["sha"] = tree_sha
                    meta_dirty = True
                    continue
                if current_sha != tree_sha:
                    updates.append({
                        "filename":        fname,
                        # Short SHAs read like a version for the UI:
                        # `latest a1b2c3d → e4f5g6h`
                        "current_version": current_sha[:7],
                        "latest_version":  tree_sha[:7],
                        "download_url":    tree_entry["download_url"],
                        "repo":            slug,
                        "asset_name":      tree_entry["asset_name"],
                        "sha":             tree_sha,
                    })
            continue   # done with this repo — don't fall through to releases

        try:
            assets = await loop.run_in_executor(executor, gh_get_releases, owner, repo_name)
        except urllib.error.HTTPError as exc:
            errors.append({"repo": slug, "error": f"HTTP {exc.code}"})
            continue
        except Exception as exc:
            errors.append({"repo": slug, "error": str(exc)})
            continue
        if not assets:
            continue
        latest_per_asset = {a["asset_name"]: a for a in reversed(assets)}
        newest_tag = assets[0]["tag"]
        newest_release_assets = [a for a in assets if a["tag"] == newest_tag]

        # Single-payload repo + single asset per release: trust the newest
        # release as the source of truth, regardless of whether the saved
        # asset filename still appears in the recent releases. This covers
        # repos that embed the version into the filename
        # (ShadowMountPlus_X.Y.zip) where the old name may still be present
        # in the recent-3 release window.
        single_payload_repo = (
            len(filenames) == 1 and len(newest_release_assets) == 1
        )

        for fname in filenames:
            m          = meta.get(fname, {})
            current    = m.get("version", "")
            asset_name = m.get("asset", fname)
            if single_payload_repo:
                latest = newest_release_assets[0]
            else:
                latest = latest_per_asset.get(asset_name)
            if not latest:
                continue
            if latest["tag"] != current:
                updates.append({
                    "filename": fname, "current_version": current,
                    "latest_version": latest["tag"],
                    "download_url": latest["download_url"],
                    "repo": slug,
                    "asset_name": latest["asset_name"],
                })
    # Persist any silent SHA backfills from the folder-mode branch above
    if meta_dirty:
        save_payload_meta(meta)
    return {"updates": updates, "checked": len(repos), "errors": errors}
