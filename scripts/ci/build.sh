#!/usr/bin/env bash
#
# ci/build.sh - the two-pass Gradle build.
#
# Pass 1 runs the external native build for :interface. That triggers
# prebuild.py (which downloads the archives, bootstraps vcpkg and builds the
# x64-linux hifi-host-tools) and the QtPackager, which produces the Qt jars,
# jniLibs and libs.xml. Those are inputs to the APK packaging, so they must
# exist before assemble.
#
# Pass 2 assembles and signs the APK.
#
# `qtBundle` is dead code upstream (android/build.gradle:129-138) and is never
# invoked here.
#
# [WROTE-UNRUN] Written but never executed.

set -euxo pipefail

# WORKSPACE is the OVERLAY repository root, which is what the workflow passes.
# The core checkout lives under it at core/, so the Gradle project is
# ${WORKSPACE}/core/android. An earlier revision set ANDROID_DIR to
# ${WORKSPACE}/android, which does not exist in this layout.
WORKSPACE="${1:-${GITHUB_WORKSPACE:-$PWD}}"
VARIANT="${BUILD_VARIANT:-release}"

# Absolute log directory. It must be resolved before the `cd` below, because a
# relative path would otherwise be created here and written there.
LOGDIR="${LOGDIR:-${WORKSPACE}/build-logs}"
mkdir -p "$LOGDIR"

ANDROID_DIR="${WORKSPACE}/core/android"
if [ ! -d "$ANDROID_DIR" ]; then
  echo "FAIL: no Gradle project at ${ANDROID_DIR}" >&2
  echo "      expected the core checkout at ${WORKSPACE}/core" >&2
  exit 1
fi
cd "$ANDROID_DIR"

if [ -x ./gradlew ]; then
  GRADLE=(./gradlew)
elif command -v gradle >/dev/null 2>&1; then
  echo "WARNING: no gradlew wrapper; falling back to the system gradle" >&2
  GRADLE=(gradle)
else
  echo "ERROR: neither ./gradlew nor gradle is available" >&2
  exit 1
fi

VARIANT_CAP="$(printf '%s' "$VARIANT" | sed 's/^\(.\)/\U\1/')"

echo "== gradle: $("${GRADLE[@]}" --version 2>&1 | head -20) =="
"${GRADLE[@]}" --version > "$LOGDIR/gradle-version.txt" 2>&1 || true

# --- pass 1: native only -----------------------------------------------------
echo "==> pass 1: :interface:externalNativeBuild${VARIANT_CAP}"
set +e
"${GRADLE[@]}" --no-daemon --stacktrace \
  ":interface:externalNativeBuild${VARIANT_CAP}" 2>&1 | tee "$LOGDIR/gradle-pass1-native.log"
rc1=${PIPESTATUS[0]}
set -e
echo "pass 1 exit: $rc1"
if [ "$rc1" -ne 0 ]; then
  echo "FAIL: the native build failed - see $LOGDIR/gradle-pass1-native.log" >&2
  exit "$rc1"
fi

# --- pass 2: assemble --------------------------------------------------------
echo "==> pass 2: :interface:assemble${VARIANT_CAP}"
set +e
"${GRADLE[@]}" --no-daemon --stacktrace \
  ":interface:assemble${VARIANT_CAP}" 2>&1 | tee "$LOGDIR/gradle-pass2-assemble.log"
rc2=${PIPESTATUS[0]}
set -e
echo "pass 2 exit: $rc2"

# --- everything that came out, for the log -----------------------------------
echo "== all apks under apps/interface (informational) =="
find "${ANDROID_DIR}/apps/interface" -name '*.apk' -printf '%p  %s bytes\n' 2>/dev/null \
  | sort | tee "$LOGDIR/apk-files.txt" || true

if [ "$rc2" -ne 0 ]; then
  echo "FAIL: assemble failed - see $LOGDIR/gradle-pass2-assemble.log" >&2
  echo "      nothing was selected for upload; $LOGDIR/apk-files.txt lists whatever existed" >&2
  exit "$rc2"
fi

# --- select THE apk for this variant, deterministically ----------------------
# Never `head -1` over a glob and never "whatever the filesystem returns first":
# the verifier and the uploader must agree on exactly one file. The search is
# restricted to this variant's own output directory, and an unsigned APK is
# excluded rather than quietly accepted as a fallback.
APP_DIR="${ANDROID_DIR}/apps/interface"
APK_DIR="${APP_DIR}/build/outputs/apk/${VARIANT}"

CANDIDATES=()
if [ -d "$APK_DIR" ]; then
  while IFS= read -r f; do CANDIDATES+=("$f"); done \
    < <(find "$APK_DIR" -maxdepth 1 -type f -name '*.apk' ! -name '*-unsigned.apk' | sort)
fi

if [ "${#CANDIDATES[@]}" -eq 0 ]; then
  echo "FAIL: no signed APK for variant '${VARIANT}' under ${APK_DIR}" >&2
  echo "      directory contents:" >&2
  find "$APK_DIR" -maxdepth 1 -type f 2>/dev/null | sort | sed 's/^/        /' >&2 || true
  UNSIGNED="$(find "$APK_DIR" -maxdepth 1 -type f -name '*-unsigned.apk' 2>/dev/null \
              | sort | head -1 || true)"
  if [ -n "$UNSIGNED" ]; then
    echo "      NOTE: an unsigned APK exists and was rejected on purpose:" >&2
    echo "        ${UNSIGNED}" >&2
    echo "      That means signing did not apply. Check HIFI_ANDROID_KEYSTORE in" >&2
    echo "      \$HOME/.gradle/gradle.properties and the throwaway-keystore step." >&2
  fi
  exit 1
fi

if [ "${#CANDIDATES[@]}" -gt 1 ]; then
  echo "FAIL: ${#CANDIDATES[@]} signed APKs match variant '${VARIANT}'; refusing to guess:" >&2
  printf '        %s\n' "${CANDIDATES[@]}" >&2
  exit 1
fi

SELECTED="${CANDIDATES[0]}"
echo "== selected APK (variant ${VARIANT}) =="
echo "  $SELECTED"

mkdir -p "${WORKSPACE}/artifacts"
cp "$SELECTED" "${WORKSPACE}/artifacts/"
COPIED="${WORKSPACE}/artifacts/$(basename "$SELECTED")"
# The workflow's verify step reads this file rather than running its own
# `find | head -1`, so the verified APK is provably the selected one.
printf '%s\n' "$COPIED" > "${WORKSPACE}/artifacts/apk-path.txt"
echo "  copied to $COPIED"
echo "  recorded in ${WORKSPACE}/artifacts/apk-path.txt"

echo "== build finished =="
