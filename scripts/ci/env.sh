#!/usr/bin/env bash
#
# ci/env.sh - establish the build environment and print every tool version.
#
# EXECUTED by the workflow (`bash scripts/ci/env.sh`), not sourced. Variables
# reach later steps through $GITHUB_ENV, which this script appends to. Every
# variable it sets is overridable by the caller.
#
# [WROTE-UNRUN] Written but never executed - no shell was available when this
# was authored. See LIMITATIONS.md.

set -euo pipefail

: "${GITHUB_ENV:=}"

# --- Directories -------------------------------------------------------------
# HIFI_ANDROID_PRECOMPILED holds the ~17 downloaded archives, the built
# x64-linux hifi-host-tools and the Qt android kit. It is multi-GB, so put it
# on the roomiest writable volume when one is provided.
pick_roomy_dir() {
  local candidate
  for candidate in /mnt /opt /var/tmp; do
    if [ -d "$candidate" ] && [ -w "$candidate" ]; then
      echo "$candidate/hifi_externals"
      return
    fi
  done
  echo "$HOME/hifi_externals"
}

export HIFI_ANDROID_PRECOMPILED="${HIFI_ANDROID_PRECOMPILED:-$(pick_roomy_dir)}"
export HIFI_VCPKG_BASE="${HIFI_VCPKG_BASE:-${HIFI_ANDROID_PRECOMPILED}/vcpkg}"

# CMakeLists.txt:159 reads HIFI_ANDROID_PRECOMPILED as an ENVIRONMENT variable,
# while hifi_vcpkg.py writes it as a CMake variable. BUILD_ANDROID.md:133-139
# documents the workaround, which is to export QT_CMAKE_PREFIX_PATH as well.
export QT_CMAKE_PREFIX_PATH="${QT_CMAKE_PREFIX_PATH:-${HIFI_ANDROID_PRECOMPILED}/qt/lib/cmake}"

# prebuild.py honours these.
export CI_BUILD="${CI_BUILD:-Github}"
export CI_WORKSPACE="${CI_WORKSPACE:-${GITHUB_WORKSPACE:-$PWD}}"

# --- Android SDK / NDK -------------------------------------------------------
# Reuse an SDK that already exists rather than defaulting to a fresh empty path.
# If the runner image ships one, that is the one to install packages into, and
# ci/cmdline_tools.sh needs to find it before ci/sdk.sh can call sdkmanager.
# Only when nothing is found do we fall back to a directory we create ourselves.
detect_sdk_root() {
  local candidate
  if [ -n "${ANDROID_SDK_ROOT:-}" ] && [ -d "${ANDROID_SDK_ROOT}" ]; then
    echo "$ANDROID_SDK_ROOT"; return
  fi
  if [ -n "${ANDROID_HOME:-}" ] && [ -d "${ANDROID_HOME}" ]; then
    echo "$ANDROID_HOME"; return
  fi
  # /usr/local/lib/android/sdk is the GitHub-hosted Ubuntu location; an earlier
  # version of the workflow deleted /usr/local/lib/android, which is why this
  # is looked for rather than assumed.
  for candidate in /usr/local/lib/android/sdk "${HOME}/Android/Sdk"; do
    if [ -d "$candidate" ]; then echo "$candidate"; return; fi
  done
  echo "${RUNNER_TEMP:-$HOME}/android-sdk"
}
export ANDROID_SDK_ROOT="$(detect_sdk_root)"
export ANDROID_HOME="$ANDROID_SDK_ROOT"
export ANDROID_NDK_VERSION="${ANDROID_NDK_VERSION:-18.1.5063045}"
export ANDROID_NDK_HOME="${ANDROID_SDK_ROOT}/ndk/${ANDROID_NDK_VERSION}"
export ANDROID_NDK_ROOT="$ANDROID_NDK_HOME"
export CMAKE_ANDROID_NDK="$ANDROID_NDK_HOME"

# --- Gradle ------------------------------------------------------------------
# Gradle 4.10.1 needs JDK 8; the Android cmdline-tools need 17+. This script
# selects neither. The workflow installs both with setup-java and sets JAVA_HOME
# per step; ci/sdk.sh asserts the JDK it is handed is 17+ and fails rather than
# switching. JAVA_HOME_8 and JAVA_HOME_TOOLS are reported below for the log only.
: "${JAVA_HOME_8:=}"
: "${JAVA_HOME_TOOLS:=}"

mkdir -p "$HIFI_ANDROID_PRECOMPILED"

echo "== environment =="
echo "HIFI_ANDROID_PRECOMPILED = $HIFI_ANDROID_PRECOMPILED"
echo "HIFI_VCPKG_BASE          = $HIFI_VCPKG_BASE"
echo "QT_CMAKE_PREFIX_PATH     = $QT_CMAKE_PREFIX_PATH"
echo "CI_BUILD                 = $CI_BUILD"
echo "CI_WORKSPACE             = $CI_WORKSPACE"
echo "ANDROID_SDK_ROOT         = $ANDROID_SDK_ROOT"
echo "ANDROID_NDK_HOME         = $ANDROID_NDK_HOME"
echo "JAVA_HOME_8              = ${JAVA_HOME_8:-<unset>}"
echo "JAVA_HOME_TOOLS          = ${JAVA_HOME_TOOLS:-<unset>}"
echo ""

echo "== tool versions =="
for tool in git curl unzip python3 cmake ninja; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf '%-8s %s\n' "$tool" "$("$tool" --version 2>&1 | head -1)"
  else
    printf '%-8s MISSING\n' "$tool"
  fi
done
df -h "$HIFI_ANDROID_PRECOMPILED" 2>/dev/null || true
echo ""

# --- Publish to later steps --------------------------------------------------
if [ -n "$GITHUB_ENV" ]; then
  {
    echo "HIFI_ANDROID_PRECOMPILED=$HIFI_ANDROID_PRECOMPILED"
    echo "HIFI_VCPKG_BASE=$HIFI_VCPKG_BASE"
    echo "QT_CMAKE_PREFIX_PATH=$QT_CMAKE_PREFIX_PATH"
    echo "CI_BUILD=$CI_BUILD"
    echo "CI_WORKSPACE=$CI_WORKSPACE"
    echo "ANDROID_SDK_ROOT=$ANDROID_SDK_ROOT"
    echo "ANDROID_HOME=$ANDROID_HOME"
    echo "ANDROID_NDK_HOME=$ANDROID_NDK_HOME"
    echo "ANDROID_NDK_ROOT=$ANDROID_NDK_ROOT"
    echo "ANDROID_NDK_VERSION=$ANDROID_NDK_VERSION"
  } >> "$GITHUB_ENV"
fi
