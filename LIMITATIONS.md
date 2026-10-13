# LIMITATIONS

Everything in this file is **unverified**. It exists so that nothing here gets
mistaken for working software.

**No APK has been produced. No build has been attempted. Nothing has run on a
phone.** The build machine had no shell available while this was written, so
almost nothing below could be executed.

---

## 1. The whole build is unexecuted

| Item | State |
|---|---|
| `scripts/apply-overlay.sh --selftest` | **[NOT RUN]** — `Bash` was refused for nearly the entire session |
| Any patch actually applied to a tree | **[NOT RUN]** |
| `bash -n` syntax check of any shell script | **[NOT RUN]** |
| `python3 -m py_compile` of any python script | **[NOT RUN]** |
| YAML parse of the workflow | **[NOT RUN]** — re-read by eye only |
| `javac` check of `WorldInstaller.java` | **[NOT RUN]** — no Android SDK / `android.jar` |
| The workflow itself | **[WROTE-UNRUN]** |
| `scripts/ci/cmdline_tools.sh` | **[WROTE-UNRUN]** — written, never executed |

The refusal was intermittent and **discriminated against commands that execute
interpreters or files**: `echo`, `ls` and `git status` got through, while
`python3 -m py_compile <path>`, `bash -n <path>` and `bash script.sh` were all
refused. That is why the parse checks below stayed unrun rather than merely
being skipped — see the exact commands in `PROGRESS.md`.

So: **every shell script here may contain a syntax error, and every python file
may contain an import-time or logic error.** Nothing has been proven to even
parse. The single highest-value next action is the self-test command in
`README.md`.

## 2. The build itself

* **It may not compile.** The pinned stack is Gradle 4.10.1 + AGP 3.2.1 + Qt
  5.11.1 + vcpkg 2022.06.16.1, targeting an Ubuntu 18.04 host the prebuilt
  archives were built for. Running it on `ubuntu-22.04` is a guess.
* **The JDK position is inferred**, not read: Gradle 4.10.1 needs JDK 8, and the
  modern Android `cmdline-tools` need 17+. Both are installed and switched, but
  whether AGP 3.2.1 works under the combination is unverified.
* **The apt package list in the workflow was NOT reconciled with
  `BUILD_LINUX.md`** (that file was never read). A surplus package is harmless; a
  missing one fails at cmake configure.
* **`jcenter()` is dead**, so patch 001 is necessary — but replacing it is not
  sufficient. Any artifact that only ever existed on jcenter still fails.
* **`com.google.vr:sdk-audio:1.80.0` / `sdk-base:1.80.0`
  (`android/apps/interface/build.gradle:155-156`) are the most likely first
  failure.** Their presence on `google()`/`mavenCentral()` is unconfirmed.
  `scripts/ci/gvr.sh` probes this and **now fails the job in seconds** when
  nothing serves them, instead of warning and letting the multi-hour native
  build discover it. `allow_unresolved_gvr: true` downgrades that back to a
  warning. The listed next step — a minimal-strip patch removing the GVR java
  dependency — is **deliberately not written**, because writing it blind would
  mean guessing at the real failure.
* **`gvr_mode: local-aar` is rejected, not supported.** It is still offered in
  the workflow's choice list (removing it would change the input contract), but
  selecting it fails the job immediately. The reason is [READ] evidence:
  nothing in this repository consumes an AAR/JAR directory. No patch adds a
  `flatDir` repository to any `build.gradle` and no patch rewrites the
  coordinates at `android/apps/interface/build.gradle:155-156`, so the mode
  would have changed nothing Gradle sees while appearing to work. An earlier
  revision exported `GVR_FLATDIR` and `GVR_RESOLUTION` into `$GITHUB_ENV` and
  nothing read either one. **The wiring is not written**, so the mode cannot be
  quietly believed in.
* **The Android SDK bootstrap is a new, unrun path.** `scripts/ci/cmdline_tools.sh`
  reuses an SDK already on the runner if one is there; otherwise it requires an
  operator-supplied `cmdline_tools_zip_url` and stops if none is given. It
  **deliberately contains no download URL**: `BUILD_ANDROID.md:15-30` documents
  installing the SDK through the **Android Studio GUI** and names no
  command-line-tools archive, so any URL written here would have been invented.
  Whether the runner image already ships an SDK is **[NOT RUN]**. An earlier
  revision of the workflow deleted `/usr/local/lib/android` and then expected
  `sdkmanager` on `PATH`; that deletion has been removed.
* **Asset transport is honoured exactly or the run fails.** `ipfs` is no longer
  silently converted to `direct`. `preflight.sh` verifies that **both** CMake
  option names (`USE_DIRECT_EXTERNAL_BUILD_ASSETS`,
  `USE_IPFS_EXTERNAL_BUILD_ASSETS`) are present in
  `cmake/ExternalAssetsConfig.cmake` before letting a transport through, and the
  same effective value is passed to both `--apply` and `--verify`. **Whether
  patch 006's option names match this revision is still unverified** — that is
  exactly what the preflight check exists to discover.
* **Dependency download availability is unverified.** The default transport is
  IPFS and two mirrors are personal DDNS hosts. `scripts/ci/preflight.sh` checks
  at run time rather than assuming.
* **The x64-linux `hifi-host-tools` build** (`prebuild.py`) is the step most
  likely to break on a modern runner, and it is on the critical path.
* **Breakpad:** `android/build.gradle:147-185` execs
  `$HIFI_ANDROID_PRECOMPILED/breakpad/bin/dump_syms` from
  `runBreakpadDumpSyms*`, and `variant.mergeResources.dependsOn` that task. If
  the breakpad binaries are not present under that exact path, this may fail the
  build. Unverified.
* **Cache size:** `HIFI_ANDROID_PRECOMPILED` is multi-GB and GitHub's cache is
  capped at 10 GB. `cache_precompiled: false` disables caching it.
* **APK selection no longer uses `head -1`.** `build.sh` searches only
  `build/outputs/apk/${BUILD_VARIANT}/`, excludes `*-unsigned.apk` by name, and
  fails on zero or on more than one remaining candidate. So an unsigned APK
  **cannot** be selected by accident: if signing did not apply, the build fails
  and names the unsigned file it rejected. Whether the excluded name pattern
  matches what AGP 3.2.1 actually emits is **[NOT RUN]** — that is the one
  assumption in the selection logic.
* **No `adb install` and no device test has happened**, so nothing about runtime
  behaviour is known.

## 3. World loading

* **`file://` absolute paths for the world JSON and the model URLs were never
  confirmed against `AddressManager`/`DomainHandler`/`ResourceManager`.** The
  engine does treat `file:///` as a serverless address
  (`NetworkingConstants.h:82-84`), and `PathUtils::resourcesUrl` shows local
  resource URLs are used elsewhere — but whether an arbitrary
  `file:///data/data/…/world/daybreak.json` plus relative model URLs works end
  to end is **unverified**. If it does not, the fallback is
  `ResourceManager::setUrlPrefixOverride`, which is also unverified.
* `build_world.py` has never run, so **the real entity count, unique-URL count
  and resolved/unresolved split are unknown.** The 319/46/37/9 figures it
  compares against are from an earlier inspection and may not match this
  revision. The script reports differences rather than asserting them.
* **9 URLs point outside Daybreak/content.** Whether those hosts are still alive
  is unknown; the script leaves them untouched and lists them.
* **Daybreak asset sizes are a real risk.** `island.fbx` ≈ 61 MB,
  `Rock-1A-detailed` ≈ 37 MB, `Skydiving-Plane` ≈ 12 MB. A phone may load these
  very slowly or run out of memory. **Not measured.**
* `WorldInstaller` copies the pack on a **background thread**, so the **first
  launch after install boots to the stock tutorial, not Daybreak**. A second
  launch gets Daybreak. This is deliberate (it avoids an ANR on a
  multi-hundred-MB copy) but it is not what a user would expect.
* `WorldInstaller` has **never been compiled**. `AssetManager.list()` on a leaf
  file returns an empty array, which is what the copy routine keys on — correct
  in principle, unverified in practice.
* **`PermissionChecker` requests `Manifest.permission.CAMERA`
  (`:57`) but `AndroidManifest.xml` does not declare it.** That request will
  return denied immediately. It does not break the flow (the result handler
  launches either way), but it is a real inconsistency, recorded and not fixed.

## 4. Avatar and animation

* **Resolved:** the default avatar is the bundled local
  `meshes/defaultAvatar_full.fst` (`AvatarData.cpp:126-134`), so no CDN is
  needed for it. This is one of the few things here that is genuinely settled.
* **Animation playback on the mannequin is [NOT RUN].** 127 clip files are
  expected under `interface/resources/avatar/animations/`; the count is checked
  by `validate_assets.py`, which has never run.
* **Whether the animation graph JSON's internal URLs resolve is unverified.**
  The validator checks it, but the validator has never run.

## 5. Touch controls and the pad

* **The input path is verified by reading** —
  `Application::event` (`Application.cpp:4352-4364`) → `touch*Event`
  (`:4924-5007`) → `TouchscreenVirtualPadDevice` → `touchscreenvirtualpad.json`
  → `setDriveKey` (`:6445-6449`). That much is **[READ]**, not inference.
* **What DRAWS the pad is still unknown.** No QML/JS/Java/C++ consumer of
  `VirtualPad::Instance` was located. Ruled out by reading: `libraries/ui`
  (links no renderer), QML (no `Q_INVOKABLE`/`Q_PROPERTY`/`HIFI_QML_DECL` on
  `VirtualPad::Manager`), `ApplicationOverlay`, `ui/AvatarInputs`,
  `ui-plugins`, `input-plugins`, and the obvious QML paths. **The one grep that
  would settle it is [NOT RUN]** — see the command list in `PROGRESS.md`.
* **No fallback pad overlay was written.** The convention would be to add one if
  nothing draws it — but that could not be established, and a blind overlay risks
  drawing a **second** pad on top of a working one. Writing it would have been
  guessing.
* **`patch_005` is a real but unproven fix.** `_hidden` being indeterminate is
  proven from source; that it actually manifests as a missing or disabled pad is
  not.
* **On-device DPI, the portrait-mode guard, and Android's back-gesture edge
  swipe competing with the pad's right-hand touch region
  (`Application.cpp:4693-4703`) are all runtime questions.** Untested.

## 6. Multiplayer, voice, login

* **No live domain has been verified to exist.** This is a non-code question and
  is independent of everything else here.
* **Voice uses Qt Multimedia on Android, not WebRTC**
  (`libraries/audio-client/CMakeLists.txt:10-13`) — that is **[READ]** and it
  removes the WebRTC archive from the Android path. Whether capture actually
  works on a phone is untested.
* **OAuth build fields are empty by default**
  (`apps/interface/build.gradle:81-83,91-93`), so the stock build is
  anonymous-first. No credentials ship.
* **No voice UI exists** (push-to-talk, mute). Not built.

## 7. Licensing — not audited

* The **Vircadia core** is Apache-2.0, which this overlay relies on.
* The **content tree** has **not** been licence-audited. Daybreak contains
  third-party models; redistributing them inside an APK may not be permitted.
  **Do not distribute an APK containing Daybreak without checking.**
* The **prebuilt dependency archives** (Qt 5.11.1, GVR, Oculus SDKs, WebRTC,
  and the rest of the ~17) have **not** been licence-audited. Qt has LGPL
  obligations that matter for redistribution.
* The **throwaway keystore** is generated in-job and never committed. A release
  build signed with it **cannot be updated** by a build signed with a different
  key. Fine for testing, not for distribution.

## 8. What would falsify this project

If the first CI run fails, that is expected and is not evidence the approach is
wrong — it is evidence the pinned 2020-era toolchain needs work. The things that
would actually falsify it are: the engine no longer configuring under AGP 3.2.1
at all; the prebuilt archives being permanently unavailable; or `file://` world
loading not being supported, which would force a server or a URL-prefix
override.
