# Vircadia Android — native client build overlay

This repository builds a **genuine native Vircadia Android client** from the
upstream Vircadia engine (`interface` app, Qt on Android, C++ renderer). It is
**not** a WebView wrapper and **not** a Three.js reimplementation. The native
engine, its assets, its avatar, its animation system and its networking stack
are all used as they ship.

This repo is an **overlay**. It contains no Vircadia source. It patches a
pristine checkout at build time and adds a small number of new files.

> **Status: no APK has ever been produced.** Nothing here has been executed end
> to end, and no script in this repo has ever been run, parsed or compiled — the
> build host had no working shell while this was written. See
> [LIMITATIONS.md](LIMITATIONS.md) — every unverified claim is listed there rather
> than glossed over.

---

## What is here

| Path | What it is |
|---|---|
| `scripts/apply-overlay.sh` | entry point: `--selftest`, `--dry-run`, `--apply <tree>`, `--verify <tree>` |
| `scripts/overlay_patches.py` | the actual patch engine (python3 stdlib, anchor-based, idempotent, fail-loud) |
| `scripts/validate_assets.py` | static avatar/animation/world validation, no network |
| `scripts/build_world.py` | turns the Daybreak world into a `file://`-addressable pack |
| `scripts/ci/*.sh` | the build steps the workflow runs |
| `overlay/**` | whole files this project adds to the tree |
| `.github/workflows/android-apk.yml` | the manual build workflow |
| `world/`, `reports/` | generated output (git-ignored except the small JSON) |

---

## One-time GitHub setup

1. Push this repo to GitHub. It can be private, but note that **Actions minutes
   are billed** on private repos (a 360-minute run is up to 360 minutes); public
   repos get free minutes. This is your call, not a technical requirement.
2. No secrets are needed. The build signs with a **throwaway keystore generated
   inside the job** — it is never committed and never leaves the runner.
3. Nothing else. There is no `secrets.*` reference in the workflow.

---

## Running the build

Actions → **android-apk** → *Run workflow*. Inputs:

| Input | Default | Meaning |
|---|---|---|
| `core_ref` | `master` | Vircadia core branch/tag/SHA to build |
| `content_ref` | `master` | Vircadia content branch/tag/SHA |
| `runner` | `ubuntu-22.04` | Closest to the Ubuntu 18.04 host the prebuilt archives came from. Unverified. |
| `ndk_version` | `18.1.5063045` | NDK 18+. `BUILD_ANDROID.md:30` says 18 or higher. |
| `gvr_mode` | `maven` | `maven` resolves `com.google.vr:*` and **fails in seconds** if nothing serves 1.80.0. `local-aar` is **not implemented** and is rejected — see LIMITATIONS.md. |
| `allow_unresolved_gvr` | `false` | When `true`, downgrades that GVR resolution failure to a warning. Only for deliberately pushing past it. |
| `asset_transport` | `skip` | `skip` keeps upstream defaults. `direct` / `ipfs` are honoured **exactly or the run fails** — the request is never silently converted to a different transport. |
| `cmdline_tools_zip_url` | *(empty)* | Only needed if the runner image has no Android SDK. The official *Command line tools only* Linux zip. Left empty, the run stops with instructions rather than downloading anything unverified. |
| `include_daybreak` | `true` | Ship the Daybreak world pack. Turn **off** for a clean baseline APK. |
| `cache_precompiled` | `true` | Cache the multi-GB precompiled directory. Turn off if the 10 GB cache cap rejects the save. |
| `build_variant` | `release` | `release` or `debug`. The selected APK is matched to this variant exactly. |

### The two ways to supply CORE

1. **Clone from GitHub (default).** The workflow clones `CORE_REPO`
   (`https://github.com/vircadia/vircadia.git`) at `core_ref`, **with
   submodules**. Submodules are not optional: a ZIP snapshot lacks
   `libraries/networking/src/acme`.
2. **Vendor it.** Commit a checkout as `core/` in this repo and the workflow
   uses it instead of cloning. Only do this if upstream is unreachable — it makes
   the repo enormous.

The same applies to CONTENT via `content/`, except CONTENT is fetched
**sparsely** (only `Bazaar/Worlds/Daybreak` and `DomainContent/Tutorial`).

### Expected cost

| | Estimate | Confidence |
|---|---|---|
| First run wall clock | 90–180 min | **Estimate, not measured.** `BUILD_ANDROID.md:91` says a first Gradle sync alone is "around 20 minutes"; on top of that are ~17 archive downloads, a vcpkg bootstrap and an x64-linux host-tools build. |
| Warm-cache rerun | 30–60 min | Estimate |
| Disk | 30–60 GB | Estimate |
| Cache | Multi-GB | The precompiled directory may exceed the 10 GB cap; then set `cache_precompiled: false`. |

### Running it locally instead

```bash
# 1. self-test the patches. Cheap, hermetic, stages only the touched files.
bash scripts/apply-overlay.sh --selftest

# 2. see what would change, writing nothing
bash scripts/apply-overlay.sh --dry-run /path/to/core

# 3. patch a core checkout in place
bash scripts/apply-overlay.sh --apply /path/to/core

# 4. verify it
bash scripts/apply-overlay.sh --verify /path/to/core
```

`--apply` never writes to the tree you pass as `$PRISTINE`, and refuses to write
anywhere outside `$HOME`.

---

## Getting the APK onto the phone

1. Download the **`vircadia-android-apk`** artefact from the run page. It
   contains the `.apk`, `apk-report.txt` and the JSON reports.
2. Sideload:

```bash
adb install -r vircadia-android-*.apk
```

`uses-feature` is not enforced by `adb install`, so the APK installs on a phone
even before the manifest patches. Those patches matter for **distribution**, not
for sideloading.

---

## Entering a world

Derived from source, not from documentation:

* `InterfaceActivity.java:55` — `DOMAIN_URL = "url"`.
* `InterfaceActivity.java:100-108` — on create, the `url` extra becomes
  `--url <value>` in `applicationArguments`, which is what the engine consumes.
  The `args` extra is forwarded verbatim.
* `InterfaceActivity.java:290-299` — while running, a new `url` extra triggers
  `nativeGotoUrl`.
* `PermissionChecker.java:37,83-92` — the launcher activity forwards **only** the
  `args` extra. It does not read `url`.

So:

```bash
# Through the normal launcher activity (PermissionChecker): use `args`.
adb shell am start -n io.highfidelity.hifiinterface/.PermissionChecker \
  --es args "--url hifi://your.domain.example:40102"

# Straight into the engine activity: use `url`.
adb shell am start -n io.highfidelity.hifiinterface/.InterfaceActivity \
  --es url "hifi://your.domain.example:40102"

# A local, serverless world (no server at all).
adb shell am start -n io.highfidelity.hifiinterface/.InterfaceActivity \
  --es url "file:///sdcard/worlds/tutorial.json"
```

`file:///` addresses are treated as **serverless** domains by the engine
(`DomainHandler::isServerless()`). With no extra at all, the engine boots to
`DEFAULT_HOME_ADDRESS` = `file:///~/serverless/tutorial.json`
(`NetworkingConstants.h:82-84`).

`hifi://` deep links are **commented out** in `InterfaceActivity.java:66,115-117`,
so a URL scheme intent will not work; use the extras above.

---

## The world pack

`include_daybreak: true` runs `scripts/build_world.py`, which:

* finds the world JSON inside `CONTENT/Bazaar/Worlds/Daybreak/` by structure
  (it looks for the document holding `Entities`), not by an assumed filename;
* resolves every `http(s)` URL in it to a real CONTENT file;
* rewrites the resolved ones to `file://@WORLD_ROOT@/<content-relative-path>`;
* copies only the referenced files into the APK's `assets/world/`;
* writes `world/daybreak.json`, `world/needed-content-paths.txt` and
  `reports/world-asset-map.json`.

At runtime `WorldInstaller.java` copies `assets/world/**` into the app's private
files directory, replaces `@WORLD_ROOT@` with that real path, and writes a
version marker. `PermissionChecker` then boots into it **only when the caller
supplied neither `url` nor `args`**.

**Daybreak is deliberately never put in the qrc.** Some of its FBX files are
tens of megabytes (`island.fbx` ≈ 61 MB), which would bloat the Qt resource
binary; it ships as plain APK assets instead.

**First launch after install boots to the stock tutorial, not Daybreak** — the
installer runs off the UI thread and the world is not there yet. Launch it a
second time. This is a deliberate trade against an ANR on a multi-hundred-MB
copy. See [LIMITATIONS.md](LIMITATIONS.md).

---

## If a run fails

Download the **`build-logs`** artefact (uploaded with `if: always()`, so it exists
even on failure) and send:

* `build-logs/gradle-pass1-native.log` — the native build. **This is where the
  first failure is most likely**, because it is the step that downloads ~17
  archives and bootstraps vcpkg.
* `build-logs/gradle-pass2-assemble.log` — packaging and signing.
* `preflight-report.txt` — which asset URLs answered.
* `gvr-report.txt` — whether `com.google.vr:*:1.80.0` is resolvable.
* `apk-report.txt` — only if an APK was produced.
* The run's step summary, which carries the effective input values.

---

## Fallbacks

| Symptom | Try |
|---|---|
| `com.google.vr:*` won't resolve | **`gvr_mode: local-aar` will not help — it is rejected.** The GVR probe now fails the run in seconds instead of surfacing after the native build. Next step is a **minimal-strip patch** removing the GVR java dependency — **not written here on purpose**, because it must be written against the real failure, not guessed. `allow_unresolved_gvr: true` only pushes past the check; it does not make Gradle resolve anything. |
| Native build can't fetch assets | `asset_transport: ipfs` (upstream default), or inspect `preflight-report.txt`. A transport that the CMake config cannot express now fails rather than being swapped for another. |
| Run stops saying it has no Android SDK | The runner image had none. Pass `cmdline_tools_zip_url` with the official *Command line tools only* Linux zip; the script will not download anything you did not name. |
| NDK complains | `ndk_version: 21.4.7075529` or similar; `BUILD_ANDROID.md:30` requires 18+ |
| Cache save rejected | `cache_precompiled: false` |
| Runner too new for the 18.04-built archives | `runner: ubuntu-20.04` |
| Want a clean baseline to isolate a problem | `include_daybreak: false` |

---

## Licence

This overlay contains no Vircadia source. Vircadia is Apache-2.0. The content
tree and the prebuilt dependencies have **not** been licence-audited — see
[LIMITATIONS.md](LIMITATIONS.md).
