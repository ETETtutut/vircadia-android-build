# overlay/

Whole files this project **adds** to a Vircadia core checkout.

The convention is simple: a path under `overlay/` mirrors the same path under
the core tree root. `scripts/apply-overlay.sh --apply <tree>` copies every file
here into `<tree>`, preserving relative paths, and `--verify` fails if any of
them is missing afterwards.

```
overlay/android/apps/interface/src/main/java/io/highfidelity/hifiinterface/WorldInstaller.java
        -> <tree>/android/apps/interface/src/main/java/io/highfidelity/hifiinterface/WorldInstaller.java
```

Only ever **add** files here. Anything that *modifies* an existing upstream file
belongs in `scripts/overlay_patches.py` as an anchored patch instead, so the
upstream file stays authoritative and reviewable.

This directory is copied to the build tree, never to either pristine source
tree.

## Current contents

| File | Why |
|---|---|
| `android/apps/interface/src/main/java/io/highfidelity/hifiinterface/WorldInstaller.java` | Copies the world pack shipped in the APK's assets into the app's private files directory, substitutes `@WORLD_ROOT@` with that real path, and writes a version marker. Runs off the UI thread. Uses only plain Android SDK APIs available at minSdk 24. |

## Note

Nothing in this directory has been compiled. `WorldInstaller.java` was never run
through `javac` against an `android.jar` — no Android SDK was available when it
was written. See `../LIMITATIONS.md`.
