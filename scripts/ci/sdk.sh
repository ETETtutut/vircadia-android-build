#!/usr/bin/env bash
#
# ci/sdk.sh - install the Android SDK, NDK and CMake the pinned toolchain needs.
#
# BUILD_ANDROID.md:19-32 asks for platform 26 and 28, CMake 3.6.4 and NDK 18+.
# AGP 3.2.1 selects build-tools 28.0.3 and CMake 3.6.4111459 by default; those
# exact package names are listed explicitly below so a missing package fails
# here, loudly, rather than deep inside Gradle.
#
# JDK: sdkmanager needs 17+. This script does NOT choose or switch a JDK - it
# uses $JAVA_HOME and refuses to run if that JDK is too old. JAVA_HOME_TOOLS is
# NOT consulted here; the workflow sets JAVA_HOME from that step's output before
# calling this script, which keeps the switch visible in the workflow rather
# than hidden inside a script. Earlier revisions of this file claimed otherwise.
#
# Usage: sdk.sh [CORE_TREE]     (default: $GITHUB_WORKSPACE/core)
#
# [WROTE-UNRUN] Written but never executed.

set -euxo pipefail

CORE="${1:-${GITHUB_WORKSPACE:-$PWD}/core}"
ANDROID_DIR="${CORE}/android"

# --- sdkmanager must already exist -------------------------------------------
# ci/cmdline_tools.sh is responsible for providing it; this script does not
# download anything.
command -v sdkmanager >/dev/null 2>&1 || {
  echo "FAIL: sdkmanager is not on PATH." >&2
  echo "      ci/cmdline_tools.sh runs before this script and must provide it." >&2
  exit 1
}

# --- the JDK must be new enough ----------------------------------------------
require_modern_jdk() {
  : "${JAVA_HOME:?JAVA_HOME must be set; the workflow sets it from the setup-java 'jdktools' step}"
  [ -x "${JAVA_HOME}/bin/java" ] || {
    echo "FAIL: JAVA_HOME=${JAVA_HOME} has no bin/java" >&2
    exit 1
  }
  local ver major rest
  ver="$("${JAVA_HOME}/bin/java" -version 2>&1 \
        | sed -n 's/.*version "\([0-9._]*\)".*/\1/p' | head -1)"
  major="${ver%%.*}"
  if [ "$major" = "1" ]; then rest="${ver#*.}"; major="${rest%%.*}"; fi
  case "$major" in
    ''|*[!0-9]*)
      echo "FAIL: could not parse a JDK version from ${JAVA_HOME}/bin/java (got '${ver}')" >&2
      exit 1 ;;
  esac
  if [ "$major" -lt 17 ]; then
    echo "FAIL: sdkmanager needs JDK 17+, but JAVA_HOME=${JAVA_HOME} is JDK ${major}." >&2
    echo "      Refusing to switch JDKs inside this script: a silent version" >&2
    echo "      change is exactly what we are trying to avoid. Point JAVA_HOME at" >&2
    echo "      the newer JDK before calling sdk.sh." >&2
    exit 1
  fi
  echo "==> sdkmanager JDK: ${JAVA_HOME} (Java ${major})"
  if [ -n "${JAVA_HOME_TOOLS:-}" ] && [ "${JAVA_HOME_TOOLS}" != "${JAVA_HOME}" ]; then
    echo "    NOTE: JAVA_HOME_TOOLS=${JAVA_HOME_TOOLS} is set but not used here;" >&2
    echo "          JAVA_HOME takes precedence." >&2
  fi
}
require_modern_jdk

: "${ANDROID_SDK_ROOT:?ANDROID_SDK_ROOT must be set}"
: "${ANDROID_NDK_VERSION:=18.1.5063045}"

# Older sdkmanager builds refuse to run on a JDK it does not recognise.
yes | sdkmanager --licenses >/dev/null 2>&1 || true

PACKAGES=(
  "platform-tools"
  "platforms;android-26"
  "platforms;android-28"
  "build-tools;28.0.3"
  "cmake;3.6.4111459"
  "ndk;${ANDROID_NDK_VERSION}"
)

for pkg in "${PACKAGES[@]}"; do
  echo "==> installing ${pkg}"
  sdkmanager --install "$pkg"
done

# --- local.properties --------------------------------------------------------
# Gradle reads sdk.dir and ndk.dir from here. This file is build output, never
# committed.
#
# The path is ${CORE}/android. The workflow clones the core tree to
# $GITHUB_WORKSPACE/core, so testing "${GITHUB_WORKSPACE}/android" - as an
# earlier revision did - never matched and the file was silently never written.
write_local_properties() {
  local android_dir="$1"
  {
    echo "sdk.dir=${ANDROID_SDK_ROOT}"
    echo "ndk.dir=${ANDROID_SDK_ROOT}/ndk/${ANDROID_NDK_VERSION}"
  } > "${android_dir}/local.properties"
  echo "wrote ${android_dir}/local.properties:"
  sed 's/^/    /' "${android_dir}/local.properties"
}

if [ ! -d "$ANDROID_DIR" ]; then
  echo "FAIL: no android/ directory at ${ANDROID_DIR}" >&2
  echo "      CORE=${CORE} - the checkout layout is not what this script expects." >&2
  exit 1
fi
write_local_properties "$ANDROID_DIR"

echo ""
echo "== installed =="
sdkmanager --list_installed || true
echo ""
echo "== ndk source.properties =="
cat "${ANDROID_SDK_ROOT}/ndk/${ANDROID_NDK_VERSION}/source.properties" 2>/dev/null || true
