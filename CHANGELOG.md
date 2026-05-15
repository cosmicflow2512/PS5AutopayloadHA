# Changelog

## [Unreleased]

## [1.1.4] – 2026-05-15

### Multi-Architecture Docker Support

- Switched to the multi-arch `ghcr.io/home-assistant/base-python:3.12-alpine3.23` base image — a single image now covers both `amd64` and `aarch64` (ARM64), so the add-on builds correctly on Raspberry Pi, ODROID, and other ARM64 boards
- Removed the manual `apk add python3 py3-pip` step (Python 3.12 is pre-installed in `base-python`), reducing build time
- Removed the deprecated `build.yaml` — base image is now defined directly in the Dockerfile, per current HA add-on guidance
- Dropped the deprecated `armv7`, `armhf`, and `i386` architectures from `config.yaml` (no longer supported by the modern HA base images); supported architectures are now `aarch64` and `amd64`
- Fixes build failure on ARM platforms reported in [#42](https://github.com/cosmicflow2512/PS5AutopayloadHA/issues/42)

## [1.1.3] – 2026-05-14

### `.bin` Payloads Supported

- `.bin` files (e.g. etaHEN binaries) are now accepted by the local upload, the GitHub repo scanner, and the release-asset importer
- Treated as ELF: routed to the ELF Loader port (9021) and shown with the ELF badge in the payload list
- The ELF filter tab now matches both `.elf` and `.bin` files

### Documentation

- README: documented the alternative HAOS path (`Settings → Apps → Install app`) since newer HA versions no longer expose `Settings → Add-ons → Add-on Store`
- README: added an explicit "integration required" warning above the example automation — without the HA integration, `ps5_autopayload.run_profile` returns *unknown action*
- README: clarified that local files can be uploaded directly via the **Add Payload** button — no GitHub URL is required

## [1.1.2] – 2026-05-13

### P2JB-Compatible Flow Notifications

Flows can now automatically wait for the PS5 loader to become ready before sending payloads — no more sitting at the console watching the screen:

- Supports **ELF Loader** (port 9021) and **Remote Lua Loader** (port 9026)
- Home Assistant notifications are sent when the loader is ready, the flow completes, or a timeout/failure occurs
- Notification settings (service, custom messages, timeout) are saved per flow and work with any `notify.*` service

### Simplified Architecture

- Removed the separate **WAIT FOR LOADER** builder step — port waiting is now built into the flow runner itself
- Removed the **Create P2JB Flow** helper — flows are created directly in the builder with the same result

### UI Improvements

- Inline SVG icons (Lucide) replace emoji/unicode glyphs — consistent rendering on all browsers and operating systems, including Safari on macOS and iOS
- Switched to **Roboto** — the same font Home Assistant uses — so the add-on UI blends naturally into the HA shell
- Multi-select for pending payload updates: choose which payloads to update instead of applying all at once (both per-source panel and global Update All)
- Source cards now show a highlighted background and an update badge when updates are available
- Cleaner notification configuration panel in the flow builder

### Reliability

- All config files now use atomic writes — a power loss or OOM-kill during a save can no longer produce a corrupted or truncated file; you will always see either the previous valid state or the new one
- Static assets (JS/CSS) are cache-busted on every update — browsers automatically fetch the latest version without a manual hard-reload

### Bug Fixes

- Update check no longer misses repos whose release assets have versioned filenames (e.g. `ShadowMountPlus_1.6test8-fix1.zip`)
- Global "Check Updates" and per-source "Check" now use the same detection rule — no more inconsistent results between the two
- Multi-update apply no longer leaves the panel in a stale state after updating
- Per-source "↻ Check" panel now opens correctly and shows the error message on failure instead of silently doing nothing
- Sources unavailable during update checks (rate-limited, no releases, network error) now report an error instead of silently disappearing from the result

---

## [1.1.1] – 2026-04-19

### New Features

**Per-step version control in the builder**
- Each builder step now independently tracks which payload version it targets
- Version dropdown per step — select any locally available version without affecting other steps
- Versions persist across saves: the flow file stores `# ~version <filename> <tag>` annotations that survive reload, export, and Edit cycles
- Before running, the add-on automatically switches each payload to its pinned version (`_ensureBuilderVersions`)

**Selective flow update dialog**
- "Update flows" button (⚠ badge → GitHub update available) shows every saved flow and the active builder flow as checkboxes
- Each row displays the current pinned version → new version transition
- Flows already on the target version are shown as "already up-to-date" and pre-deselected
- Select all / Deselect all quick actions
- "Update selected" is disabled when nothing is checked — no accidental blanket updates

**Full flow scan in "Update flows" button**
- The "Update flows" button (in the builder-usage row) now scans ALL saved flows that use the payload, not just builder steps
- Saved flows and builder steps shown together with per-flow version transitions
- Confirming patches the `# ~version` annotation in each selected saved flow file and updates builder step metadata simultaneously

**GitHub token support**
- New `github_token` option in add-on configuration
- Raises GitHub API rate limit from 60 req/hr (unauthenticated) to 5,000 req/hr
- Clear error message when rate-limited without a token: *"GitHub API rate limit exceeded — add a GitHub token in add-on options to raise the limit."*

**Multi-version storage & smarter imports**
- Up to 5 versions stored per payload (raised from 3)
- Re-importing a payload merges versions rather than overwriting — previously downloaded versions are never lost
- Versions sorted by tier: stable → beta → alpha/test
- Update detection now checks whether the latest GitHub tag is already in the local versions list — eliminates false-positive "update available" badges

**ZIP autoload export improvements**
- Export includes all referenced ELF/LUA binaries alongside the autoload text — ready to drop on a USB stick
- Source display names shown in builder steps (advanced mode)

**UI readability improvements**
- Step font sizes bumped for readability (`.82rem`)
- Payload step rows split into name row + info row for cleaner layout
- Edit button text changed from `✏` icon to `Edit` label
- Version label removed from payload card (redundant with dropdown)
- Builder badge placement fixed for HA ingress scaling

### Bug Fixes

- **Version not persisting**: builder step version was reset after save/load because `builderGenerate()` did not write version annotations to the flow file — fixed
- **False-positive update badge**: update detection compared `latest.tag` against a single `current` field; now checks whether the tag exists in the local `versions[]` array
- **`autoload.txt` reappearing**: the default `autoload.txt` flow was bundled in the Docker image and re-installed on every restart — file deleted from image, cleanup added to `setup_storage()`
- **Duplicate run race condition**: rapid double-click could start two concurrent autoload runs (HTTP 409) — fixed with optimistic guard in `runProfile()`
- **GitHub 403 surfaced as HTTP 502**: rate-limit errors from GitHub now return a descriptive message instead of an opaque 502

### UX / Wording

- **"Profiles" renamed to "Flows"** throughout the UI — heading, placeholders, import modal, empty states
- **"Update usages" renamed to "Update flows"** for consistent language
- **Update dialog shows flow names** instead of internal step numbers ("Step 3") — grouped by flow with usage count and version transition
- Builder checkbox in the "Update flows" (GitHub version) dialog defaults to **unchecked** (safe by default)

---

## [1.1.0] – 2026-03-xx

Initial public release with autoload builder, payload management, GitHub source tracking, and Home Assistant ingress support.
