# CHANGES

Every file this project adds or changes, with an honest status tag.

| Tag | Meaning |
|---|---|
| **[RAN]** | Executed, real output seen |
| **[READ]** | Established by reading source |
| **[WROTE-UNRUN]** | Written but never executed |
| **[NOT RUN]** | Required, not attempted |

---

## Added — build and patch machinery

| File | Status | Notes |
|---|---|---|
| `scripts/overlay_patches.py` | **[WROTE-UNRUN]** | New patch engine. Replaces the awk transforms. Anchor-based, strict occurrence counts, idempotent, stdlib only. Patches 001–008 plus the overlay-file copy. |
| `scripts/apply-overlay.sh` | **[WROTE-UNRUN]** | Rewritten. Modes `--selftest`, `--dry-run`, `--apply <tree>`, `--verify <tree>`. All logic delegated to the python engine; the awk is gone. |
| `scripts/validate_assets.py` | **[WROTE-UNRUN]** | New. Static avatar/animation/world validation. No network. |
| `scripts/build_world.py` | **[WROTE-UNRUN]** | New. Builds the Daybreak world pack. `local` mode writes JSON only; `ci` mode copies referenced files into `assets/world/`. |
| `scripts/ci/env.sh` | **[WROTE-UNRUN]** | Environment: `HIFI_ANDROID_PRECOMPILED`, `QT_CMAKE_PREFIX_PATH`, `CI_BUILD=Github`, `CI_WORKSPACE`, SDK/NDK paths; prints all tool versions. |
| `scripts/ci/sdk.sh` | **[WROTE-UNRUN]** | Installs `platforms;android-26`, `platforms;android-28`, `build-tools;28.0.3`, `cmake;3.6.4111459`, `ndk;<input>`, and writes `android/local.properties`. |
| `scripts/ci/preflight.sh` | **[WROTE-UNRUN]** | Extracts URLs from `cmake/ExternalAssetsConfig.cmake`, HEADs each, prints a table, and decides whether forcing the direct asset transport is safe. |
| `scripts/ci/gvr.sh` | **[WROTE-UNRUN]** | Probes whether `com.google.vr:sdk-audio/sdk-base:1.80.0` is resolvable; supports the `local-aar` fallback and prints exactly what it found. |
| `scripts/ci/build.sh` | **[WROTE-UNRUN]** | The two Gradle passes. Pass 1 is native-only (triggers `prebuild.py` and QtPackager); pass 2 assembles and signs. `qtBundle` is never used. |
| `scripts/ci/verify_apk.sh` | **[WROTE-UNRUN]** | Hard-fails only on missing APK / invalid zip / missing `lib/arm64-v8a/libnative-lib.so`. Everything else is report-only into `apk-report.txt`. |
| `.github/workflows/android-apk.yml` | **[WROTE-UNRUN]** | `workflow_dispatch` only, 360-minute timeout, disk reclaim, caches restored before and saved under `if: always()`, artefacts uploaded `if: always()`. |
| `.gitignore`, `.gitattributes` | **[WROTE-UNRUN]** | Ignore build output and `selftest/`; mark `*.fbx`/`*.glb` binary. |
| `overlay/README.md` | **[WROTE-UNRUN]** | Explains the overlay convention. |

## Added — source overlay

| File | Status | Notes |
|---|---|---|
| `overlay/android/apps/interface/src/main/java/io/highfidelity/hifiinterface/WorldInstaller.java` | **[WROTE-UNRUN]** | New Java. Copies `assets/world/**` into `getFilesDir()/world` off the UI thread, substitutes `@WORLD_ROOT@`, writes a version marker keyed on `versionCode:lastUpdateTime`. Plain SDK APIs only. **Not compiled — no `javac`/SDK was available.** |

## Added — documentation

| File | Status | Notes |
|---|---|---|
| `README.md` | **[WROTE-UNRUN]** | Setup, inputs, the two CORE sources, cost estimates, sideloading, entering a world, daybreak, failure triage, fallbacks. |
| `PROGRESS.md` | **[WROTE-UNRUN]** | New Phase 7 entry; the stale "add patch_004" next-task section was replaced with what actually remains. |
| `CHANGES.md` | this file | |
| `LIMITATIONS.md` | **[WROTE-UNRUN]** | Every unverified item and the licensing position. |

## Modified — existing plan

| File | Status | Notes |
|---|---|---|
| `APP_IMPLEMENTATION_PLAN.md` | **[READ]** | §3's "default-avatar URL choice" is now marked **CLOSED** with the `AvatarData.cpp:126-134` quote, and the summary table row 3 reads `none — CLOSED 2026-10-13`. Item 4's pad renderer is now flagged as the plan's largest remaining unknown. Earlier corrections were kept, not deleted. |

---

## Patches applied to the core tree

All are applied to a **copy**. No file in either pristine tree was written.

| # | File | Change | Status |
|---|---|---|---|
| 001 | `android/build.gradle`, `android/apps/interface/build.gradle` | `jcenter()` → `mavenCentral()` (4 occurrences). A `jcenter()` directly above an existing `mavenCentral()` is deleted rather than duplicated. | **[READ]** anchors verified against both files; **[WROTE-UNRUN]** never executed |
| 002 | `AndroidManifest.xml` | `android.software.vr.mode` and `android.hardware.vr.high_performance` → `required="false"`; declares `android.hardware.touchscreen` `required="false"`. `glEsVersion` deliberately untouched. | **[READ]** + **[WROTE-UNRUN]** |
| 003 | `AndroidManifest.xml` | `accelerometer` and `gyroscope` → `required="false"`. Justified by the now-verified touch look path. | **[READ]** + **[WROTE-UNRUN]** |
| 004 | *(none)* | **No patch.** The default full-avatar URL **already** resolves to the bundled `meshes/defaultAvatar_full.fst`. Implemented as a fail-loud assertion instead. | **[READ]** — `AvatarData.cpp:126-134`; **[WROTE-UNRUN]** assertion |
| 005 | `libraries/ui/src/VirtualPadManager.h` | `bool _hidden;` → `bool _hidden { false };`; initialises the four `Instance` members (`_isBeingTouched`, `_firstTouch`, `_currentTouch`, `_shown`). They are provably uninitialised: no in-class initialiser and `Manager::Manager() {}` is empty. | **[READ]** — `.h:27-30,73`, `.cpp:47-49`; **[WROTE-UNRUN]** |
| 006 | `android/apps/interface/build.gradle` | Opt-in: adds `-DUSE_DIRECT_EXTERNAL_BUILD_ASSETS` / `-DUSE_IPFS_EXTERNAL_BUILD_ASSETS` to the cmake `arguments`. **Off by default** because the option names were not verified against `cmake/ExternalAssetsConfig.cmake`. | **[WROTE-UNRUN]** |
| 007 | `PermissionChecker.java` | Adds the `url` extra (`file://…/world/daybreak.json`) **only** when the caller supplied neither `url` nor `args`. No-op otherwise. | **[READ]** — anchors from the 159-line file; **[WROTE-UNRUN]** |
| 008 | `PermissionChecker.java` | Starts `WorldInstaller.installAsync(this)` in `onCreate`. | **[READ]** + **[WROTE-UNRUN]** |
| OVL | `overlay/**` | Copies this project's new files into the tree. | **[WROTE-UNRUN]** |

---

## Changed — findings that replace earlier claims

| Claim | Correction | Evidence |
|---|---|---|
| "There is no local `.fst` / no avatar" | **Wrong.** A complete 69-joint skinned avatar ships locally. | **[READ]** `interface/resources/meshes/defaultAvatar_full.fst`, `mannequin/mannequin.baked.fbx` |
| "The default avatar URL is unknown; patch 004 is blocked on finding it" | **Resolved.** It is `AvatarData::defaultFullAvatarModelUrl()` → `PathUtils::resourcesUrl("/meshes/defaultAvatar_full.fst")`. No patch needed. | **[READ]** `AvatarData.cpp:126-134`, `MyAvatar.cpp:204-205` |
| "`_hidden` defaults to false" | **Unproven, and probably false.** It has no initialiser and the constructor is empty — it is indeterminate. | **[READ]** `VirtualPadManager.h:73`, `.cpp:47-49` |
| "Patch 002's sensor rationale: the sensors are the only look input" | **Falsified.** The touch look path is verified end to end. | **[READ]** `Application.cpp:4352-4364`, `:4924-5007` |
| "`mpassets.highfidelity.com` URLs are an active defect" | **Dead code**, behind `CHOOSE_AVATAR_ON_STARTUP = false`. | **[READ]** `PermissionChecker.java:28,41-43,96-99,108-127` |
| "The pad's on-screen component is unknown" | **Still unknown.** Not resolved — see LIMITATIONS.md. | **[NOT RUN]** one grep |

---

## Added — CI integration fixes (2026-10-13)

All of these are **[WROTE-UNRUN]**. None was executed. See
`reports/04_ci_fixes.md` for the issue-by-issue reasoning and
`reports/03_ci_integration_audit.md` for the audit that prompted them.

| File | Change | Reason |
|---|---|---|
| `scripts/ci/cmdline_tools.sh` | **New.** Provides `sdkmanager` before `ci/sdk.sh` needs it: reuse an existing SDK, else install an operator-supplied `CMDLINE_TOOLS_ZIP_URL`, else fail closed having downloaded nothing. | Nothing bootstrapped the tools, and the reclaim step deleted the SDK tree that had them. **Contains no hardcoded URL** — `BUILD_ANDROID.md:15-30` names no command-line-tools archive, so any URL would have been invented. |
| `scripts/ci/env.sh` | `detect_sdk_root()`: honour a preset `ANDROID_SDK_ROOT`/`ANDROID_HOME`, else probe `/usr/local/lib/android/sdk` and `~/Android/Sdk`, else fall back. Header now says **executed, not sourced**. JDK comment corrected. | The old default was a fresh empty path, so packages installed where nothing looked. |
| `scripts/ci/sdk.sh` | Rewritten JDK handling: uses `$JAVA_HOME` and **refuses to run** below 17 rather than switching. `local.properties` now written to `${CORE}/android`, and the script fails loudly if that is absent. `JAVA_HOME_TOOLS` no longer consulted. | Previously the `local.properties` guard tested `${GITHUB_WORKSPACE}/android`, which never exists in this layout, so the file was silently never written. The header claimed `JAVA_HOME_TOOLS` behaviour the code did not implement. |
| `scripts/ci/gvr.sh` | `maven` mode **fails the job** when nothing serves 1.80.0 (`GVR_ALLOW_UNRESOLVED=1` downgrades). `local-aar` is **rejected**: it lists what it found, then fails. `GVR_FLATDIR`/`GVR_RESOLUTION` exports removed. | The mode appeared supported while changing nothing Gradle saw — no patch adds a `flatDir` repo and nothing read those variables. |
| `scripts/ci/preflight.sh` | Takes the requested transport as `$2`, validates it, and publishes it **unchanged** to `ASSET_TRANSPORT_EFFECTIVE`, or fails. | It used to report `direct` whenever both CMake option names existed, so requesting `ipfs` silently produced a `direct` build. |
| `scripts/ci/build.sh` | `ANDROID_DIR=${WORKSPACE}/core/android` (fail-loud if absent); absolute `LOGDIR`; deterministic APK selection that fails on zero or multiple candidates and **excludes `*-unsigned.apk`**; records the choice in `artifacts/apk-path.txt`. | It looked for `${WORKSPACE}/android`, copied every APK, and let `head -1` decide. |
| `.github/workflows/android-apk.yml` | Reclaim step no longer deletes `/usr/local/lib/android`; new bootstrap step; `local.properties`/preflight/apply/verify wired to the effective transport via `:?`; verify step reads `artifacts/apk-path.txt`; new `allow_unresolved_gvr` and `cmdline_tools_zip_url` inputs. | See the audit — five separate defects in the plumbing. |
| `README.md` | Inputs table and fallbacks corrected: `local-aar` marked rejected, new inputs documented, the `gvr_mode: local-aar` fallback replaced. | The table advertised behaviour that did not exist. |
| `LIMITATIONS.md` | Added the SDK-bootstrap position, the `local-aar` rejection, the transport position, APK selection, and why the parse checks are unrun. | — |

### Corrected — patch 005 idempotency

`scripts/overlay_patches.py` gained `_replace_idempotent()` (three outcomes:
pristine → apply, already-patched → accept, anything else → raise) and
`patch_005` now uses it for both the `_hidden` block and the four `Instance`
members. **Reason:** both blocks are replaced in place, so a second apply found
zero pristine anchors and raised — which is why `--selftest` pass 2 failed.
`verify_005` is unchanged. **[WROTE-UNRUN]** — traced statically against the
staged `selftest/` file, never executed.

---

## Never executed

**No file in `/storage/emulated/0/GLB/vircadia-native-core-master` or
`/storage/emulated/0/GLB/vircadia-content-master` was created, modified or
deleted.** No build was attempted. No APK exists. Nothing ran on a phone.

`Bash` was refused repeatedly across the whole project by a classifier outage
(`deepseek-v4-flash is temporarily unavailable`). It flapped rather than going
down, and it **discriminated by command shape**: a handful of read-only
commands (`grep -n`, `ls`, `echo`, `git status`) were permitted and are the only
**[RAN]** results in this project, while **every** command that would execute an
interpreter or a file — `bash -n <script>`, `bash <script>`, `python3 -m
py_compile <script>`, `command -v <tool>` — was refused, every time. That is why
the static checks below are unrun rather than merely unattempted.

Consequently **no script in this repository has ever been executed, parsed or
compiled.** In particular `apply-overlay.sh --selftest` — the self-test that would
prove patches 001–008 apply cleanly and idempotently — has **not run**. The
commands are listed at the end of `PROGRESS.md`, in `README.md`, and in
`reports/04_ci_fixes.md`.
