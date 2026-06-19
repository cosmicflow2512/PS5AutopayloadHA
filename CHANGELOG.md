# Changelog

## [Unreleased]

## [1.1.15] – 2026-06-19

### FTP Upload for Autoload Files

Instead of downloading `autoload.zip` and copying it to a USB stick, autoload files can now be uploaded directly to the PS5 via FTP.

**Requirement:** `ftpsrv.elf` must be running on the PS5 (default port: 2121, no authentication required).

**How to use:**

A new **FTP Upload (ftpsrv)** section appears below the "Export autoload.zip" button in the Auto-Load Builder:

1. Enter the PS5 IP in the FTP field (auto-filled from the configured PS5 IP on startup)
2. Adjust the remote path if needed (default: `/mnt/usb0/ps5_autoloader/`)
3. Click **⬆ FTP**

The add-on connects via `ftplib` (Python standard library — no new dependency), creates the directory if it does not exist, and uploads `autoload.txt` along with all ELF/BIN payloads. Progress appears in the Execution Log.

IP and path are saved and restored across restarts.

**New `config.yaml` option:** `ftp_port: 2121` — the FTP port can be changed in the add-on settings if needed.

## [1.1.14] – 2026-06-08

### Debug Tracer in Advanced Mode

Added a **Debug Tracer** to the Execution Log (Advanced Mode) so the update flow can be inspected step by step.

**How to use**

1. Enable **Advanced Mode** (top-right toggle).
2. Open the **Execution Log** section.
3. Change the filter dropdown to **Trace**.
4. Click **Check Updates** (global) or the per-source **Check** button.

The trace will show exactly which repos and payloads were inspected, what was compared, and why a payload was — or was not — flagged as having an update.

**What the trace explains**

- Global **Check Updates** only inspects payloads that have already been imported. If a payload from a source has never been imported, the global check cannot see it — it is simply not in the metadata. This is by design: the global check is an *update* checker, not a *discovery* scanner.
- The per-source **Check** button scans all release assets from GitHub, including ones that were never imported. That is why it can report "1 new payload found" while the global check reports "all up to date" — the payload is genuinely new, not an update.
- The trace labels new (not-yet-imported) assets as `NEW` and existing tracked updates as `UPDATE`, making this distinction explicit.

**What was added**

- `DebugTracer.js` — wraps the global `api()` function when Advanced Mode is on, logging every HTTP call (method, URL, timing, response summary) at trace level. Also logs named button clicks via document-level event delegation.
- `dtrace()` helper in `StatusLog.js` (shorthand for `log(msg, 'trace')`).
- "Trace" filter option in the Execution Log dropdown — shows only trace-level entries.
- Verbose trace calls in `checkAllUpdates()` and `checkSourceUpdates()` describing repos checked, assets found, updates/new payloads detected, and why global vs per-source results differ.
- `.log-trace` CSS class (indigo, slightly smaller) to visually distinguish trace entries from info/warn/error.

## [1.1.13] – 2026-06-07

### Update Flow: Eight Follow-up Fixes

v1.1.12 fixed the backend cache + release-window issues that made Check-Updates miss real updates. A follow-up audit then found eight more bugs in the surrounding flow — none of them headline failures on their own, but together they made the experience feel "off". All eight land here so the update flow can finally be shipped.

**Frontend correctness**

- The version dropdown in the payload list now actually switches the file on disk. Previously it called `set-default-version`, which only updated the meta `version` field — the underlying `.elf/.lua` binary stayed at whatever the last `switch-version` wrote. Picking an older entry from the dropdown now runs the full download + atomic write, mirroring the dedicated Update buttons.
- The dropdown also no longer calls a non-existent `renderPayloadList()` (legacy name) — that JS error meant the row never re-rendered after a version change. Same rename in the "apply to flows" dialog.
- After Import Selected (both the source-add and per-source-edit panels) the UI now runs Check Updates automatically. Without this the just-imported payload kept showing as "update available" until the user clicked Check manually.
- After a folder-mode per-source Check the payload list is re-rendered. The release branch already did this; the folder branch now matches it so the "update available" pill appears immediately instead of only after a full reload.
- A global `state.isUpdating` flag now blocks concurrent switch-version batches. Previously firing Update Selected and Update All in quick succession could leave the second batch silently no-op'ing because the first batch had already removed entries from `state.updateResults`.
- WebSocket `status` messages for `imported` / `switched to` now trigger a debounced (500 ms) `refreshPayloads()`. A second open tab or the HA mobile sidebar reflects new payloads within a second instead of waiting for a manual reload.

**Backend tightening**

- `DELETE /api/sources/{owner}/{repo}` now unlinks orphaned `payload_meta.json` entries pointing at the deleted source. Binaries on disk are intentionally kept (the user may still want a payload they already downloaded), only the meta link is removed. The response includes `orphans_unlinked: [...]` so the UI can surface them.
- `POST /api/payloads/{name}/set-default-version` now rejects (422) tags that are not in the payload's tracked `versions[]`. Legacy entries with no `versions[]` keep accepting any value to avoid regressing existing flows.

**Tests**: 4 new (`test_set_default_version_rejects_unknown_tag`, `test_set_default_version_accepts_known_tag`, `test_set_default_version_legacy_empty_versions_accepts_any`, `test_delete_source_unlinks_orphan_meta`). Total suite: **148 passing**.

## [1.1.12] – 2026-06-07

### Update Flow: Four Root Causes Fixed

Real-world testing of the update flow exposed four independent bugs that each made "Check Updates" or "Re-scan" behave unreliably. After a maintainer pushed a new payload or release the user would see one of three failure modes, depending on which bug was hit first: updates not detected, an update reported but the next check still flagged the just-imported version, or a clean source showing "no upstream version available". All four root causes are fixed here.

- **Stale tree cache after Re-scan / Check-Updates.** The in-memory tree cache (`github_client._tree_cache`, 300 s TTL) was never invalidated. `invalidate_cache()` existed but had no callers. POST /api/sources (Re-scan / Add Source), GET /api/sources/check-updates, POST /api/payloads/import and POST /api/payloads/{filename}/switch-version now all drop the cached tree for the target repo before/after their state change. Fresh pushes to GitHub are visible immediately instead of up to 5 minutes later, and the second Check-Updates after a successful import now correctly reports "up to date".
- **Release window too small.** `get_releases()` used `per_page=3`, so users more than 3 releases behind never saw any update. Raised to `per_page=30` (GitHub's default page size).
- **Silent skip when a source has no releases.** Previously `if not assets: continue` made an empty release feed indistinguishable from "up to date". Now reported as `errors: [{repo, error: "No releases found"}]` so the UI can surface it.
- **Silent skip when the stored asset name isn't in the release window.** If a maintainer renamed the asset (or it falls outside the 30-release window) the meta entry was silently dropped from the check. Now reported as `errors: [{repo, error: "<file>: asset not found in last 30 releases"}]` so the user knows a re-scan is needed.

Four new tests in `test_check_updates_source_type.py` lock in the new behaviour (`test_check_updates_invalidates_tree_cache`, `test_empty_releases_reports_error`, `test_asset_missing_from_release_window_reports_error`, `test_add_source_invalidates_tree_cache`). Full suite: 144 tests green.

## [1.1.11] – 2026-05-28

### Y2JB Support: `.js` Payloads on Port 50000

When using the Y2JB (YouTube jailbreak) exploit the first step after userland entry is sending `lapse.js` to port **50000** (the WebKit-stage loader). `.js` is now a first-class payload type alongside `.elf`, `.lua`, `.bin` and `.jar`:

- `.js` files are accepted by the upload endpoint, the GitHub source scanner, and the release-asset importer.
- Auto port resolution: `.js` → **50000** (`JS_PORT`, new add-on option, configurable). All other mappings stay unchanged (`.lua → 9026`, `.jar → 9025`, `.elf/.bin → 9021`).
- New add-on option `js_port: 50000` (with schema entry), exported as `JS_PORT` env var and exposed via `/api/config` and the WebSocket config event.
- Dedicated **JS** badge (green) and filter tab in the payload list.
- Builder: `.js` steps show a green `Payload` label; ZIP autoload export marks `.js` steps as skipped (the PS5-side autoloader is ELF-only).
- A complete Y2JB flow can now be built in the Auto-Load Builder: `?50000` → `lapse.js` → `?9021` → `etaHEN.bin`.

## [1.1.10] – 2026-05-22

### BD-UN-JB `.jar` Flow Steps: Actually Execute Now

Reported by @sagacity in #53: a `.jar` step added to a flow via the builder showed up correctly in the saved profile but was silently dropped at run time — the step never appeared in the execution log and nothing was sent to port 9025.

- **Root cause:** the autoload parser regex (`autoload_parser._PAYLOAD_RE`) only matched `.lua` and `.elf` filenames. Lines containing `.jar` (and `.bin`) were parsed as `None` and quietly skipped, so the directive list reaching the exec engine had no JAR send step in it at all. 1.1.9 added uploads, the picker badge and the auto-port mapping, but the parser was missed — the flow engine never saw `.jar` directives.
- **Fix:** the payload regex now accepts `.lua`, `.elf`, `.bin` and `.jar` (case-insensitive). `.bin` flow steps are now also valid (previously only the upload endpoint accepted them — they were dropped from flows). Tests cover all four extensions and the explicit-port form (e.g. `bdunjb.jar 9025`).

### File Picker Filter Now Includes `.jar`

- The **Add Payload** file dialog filter (`accept` attribute) was still `.lua,.elf,.bin` — meaning users had to switch the dialog to *All files* to even see their `.jar` files. The accept list now includes `.jar`, matching the upload endpoint and the empty-state hint.

## [1.1.9] – 2026-05-17

### BD-UN-JB Support: `.jar` Payloads on Port 9025

- `.jar` files are now first-class payloads alongside `.elf`, `.lua` and `.bin`. Uploads (local + GitHub source scans + release-asset importer) accept the new extension, the payload list shows a dedicated **JAR** badge, and a JAR filter tab lets you isolate `.jar` payloads.
- Auto port resolution: `.jar` is routed to the BD-UN-JB loader on port **9025** (`JAR_PORT`, configurable in the add-on options). `.lua → 9026`, `.elf/.bin → 9021` remain unchanged.
- New add-on option `jar_port: 9025` (with matching schema entry) — exposed through `/api/config` and the WebSocket config event as `jar_port`.
- ZIP autoload export marks `.jar` steps as skipped (the PS5-side autoloader can only chain `.elf`).

### Dropdown Refresh: The Real Root Cause (finally)

Every dropdown-refresh attempt since 1.1.5 silently failed for one reason: the generated integration called `hass.services.async_set_service_schema(...)`, but `async_set_service_schema` is **not** a method on the `ServiceRegistry` — it is a module-level helper in `homeassistant.helpers.service` that takes `hass` as its first argument. The call raised `'ServiceRegistry' object has no attribute 'async_set_service_schema'` on **every** invocation, was swallowed by the surrounding `try/except`, and only ever logged as a warning — so the selector was never actually updated and the dropdown only refreshed on a full HA Core restart.

- The integration now imports `async_set_service_schema` from `homeassistant.helpers.service` and calls it correctly as `_set_service_schema(hass, DOMAIN, "run_profile", schema)`. This is the API HA itself uses to register service descriptions, and it is the missing piece that makes the live dropdown update work without a Core restart.
- No behavioural change to the push-based flow list (1.1.8) — that part was already correct; it just never reached a working `async_set_service_schema`.

### Removed Both Update/Setup Notices

- Removed the **Repairs "Restart required" notice** (the `_version_guard` issue-registry mechanism added in 1.1.7) — no more badge on Settings or card under Settings → System → Repairs.
- Removed the **persistent post-install/-update notification** ("Integration installiert/aktualisiert … bitte Home Assistant Core neu starten …") that was created in HA's notification center.

> Note: the generated integration is still only rewritten when the add-on version changes, so after updating to 1.1.9 restart Home Assistant once so HA loads the corrected integration. There is no longer any in-HA prompt for this — it is a one-time manual restart.

## [1.1.8] – 2026-05-15

### Dropdown Refresh: Timeout/502 Fixed (log-confirmed)

The 1.1.7 service call worked (no more 404), but the add-on log then showed `reload_profiles error: timed out` / `HTTP 502` on every save. Cause: the blocking REST service call waited for the integration handler, which called *back* to the add-on (`_get /api/autoload/profiles`) to fetch the flow list — that round-trip exceeded the request timeout.

- The add-on now **pushes the flow list inside the service payload** (`reload_profiles: {profiles: [...]}`). The integration reads it from `call.data` and never calls back, so the service completes instantly — no timeout, no 502.
- Integration base URLs reordered (`172.30.32.1` before `localhost`) since `localhost` never reaches the add-on from the HA Core container, only added latency.

## [1.1.7] – 2026-05-15

### The Actual Root Cause (log-confirmed)

The add-on log revealed `HA reload HTTP 404: Not Found` on **every** flow save. `reload_integration()` was calling `GET /core/api/config/config_entries/entries` — a REST path that **does not exist** in HA Core (config entries are WebSocket-only). The entire dropdown-refresh chain died at step 1 every time; nothing in 1.1.5/1.1.6 could ever run. The dropdown only updated on a full HA Core restart.

- The add-on now calls the integration's own `ps5_autopayload.reload_profiles` service via `POST /core/api/services/<domain>/<service>` — the exact endpoint already proven to work for notifications. No more 404.
- The integration's `reload_profiles` handler now rebuilds the selector **directly**: it fetches the live flow list, removes + re-registers `run_profile` (which fires the service events the HA frontend listens to, forcing a description refetch), then applies the new options via `async_set_service_schema`.
- Net result: saving/deleting a flow updates the automation dropdown within ~1–2 s, no Core restart.

### "Restart Required" Repair Notice

- The add-on's old restart notification was sent at add-on start-up, before HA Core is ready — it returned `502 Bad Gateway` and was silently lost, so the prompt to restart often never appeared.
- The integration now compares the running add-on version against the integration version HA actually has loaded. On a mismatch it raises a **HA Repairs issue** ("Restart Home Assistant to finish updating PS5 Autopayload") — the same mechanism other integrations use: it shows as a badge on Settings and a card under Settings → System → Repairs. Once the versions match again (after the restart) the issue clears itself automatically. The check runs inside HA, so it is always delivered.

## [1.1.6] – 2026-05-15

### Flow Dropdown Actually Updates Now

- **Root cause fix**: HA caches `services.yaml` descriptions and does *not* re-read them on `reload_config_entry`, so the v1.1.5 auto-refresh never reached the dropdown. The `run_profile` flow list is now set at runtime via `async_set_service_schema`, pulling the live flow list directly from the add-on — this is the only mechanism HA honors without a full Core restart.
- The selector is rebuilt on every integration reload (triggered automatically when a flow is saved or deleted), so the automation editor always shows the current flows.

## [1.1.5] – 2026-05-15

### HA Integration — Robustness & Auto-Refresh

- **Flow dropdown auto-updates**: the `profile_name` selector in HA automations now refreshes automatically whenever a flow is saved or deleted — no more manual `reload_profiles` call required
- **Integration survives add-on updates**: services (`run_profile`, `stop`, `pause`, `resume`) are now registered in `async_setup` instead of only `async_setup_entry`, so they remain available even if the config entry fails to reload after a version bump
- **Startup sync**: on add-on startup the integration is reloaded automatically to ensure HA's service list reflects the current flow library

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
