#!/usr/bin/env bash
#
# ci/cmdline_tools.sh - make `sdkmanager` available before ci/sdk.sh needs it.
#
# Resolution order:
#   1. an sdkmanager already inside ANDROID_SDK_ROOT, or on PATH
#   2. an operator-supplied command-line-tools zip (CMDLINE_TOOLS_ZIP_URL)
#   3. fail closed, having downloaded nothing
#
# WHY THERE IS NO DEFAULT URL
# ---------------------------
# This script deliberately hardcodes no download URL. BUILD_ANDROID.md:15-30
# documents installing the SDK through the Android Studio GUI and names no
# command-line-tools archive; nothing in either source tree pins one. A URL
# written here would therefore be invented, and an invented URL that 404s is
# worse than an honest stop. Supply cmdline_tools_zip_url as a workflow input
# instead, and the exact archive used is printed and hashed.
#
# [WROTE-UNRUN] Written but never executed.

set -euo pipefail

: "${ANDROID_SDK_ROOT:?ANDROID_SDK_ROOT must be set (ci/env.sh sets it)}"

# JAVA_HOME_TOOLS is the newer JDK the cmdline-tools need. Adopt it ONLY if
# JAVA_HOME is unset, so behaviour is explicit and never a silent switch: if
# JAVA_HOME is already set, that is the JDK used and no other is substituted.
if [ -z "${JAVA_HOME:-}" ] && [ -n "${JAVA_HOME_TOOLS:-}" ]; then
  echo "JAVA_HOME unset - adopting JAVA_HOME_TOOLS=$JAVA_HOME_TOOLS (explicit, not a switch)"
  export JAVA_HOME="$JAVA_HOME_TOOLS"
fi

SDKMANAGER=""

find_sdkmanager() {
  local c
  for c in \
    "${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin/sdkmanager" \
    "${ANDROID_SDK_ROOT}/cmdline-tools/bin/sdkmanager" \
    "${ANDROID_SDK_ROOT}/tools/bin/sdkmanager"
  do
    if [ -x "$c" ]; then
      SDKMANAGER="$c"
      echo "found existing sdkmanager: $SDKMANAGER"
      return 0
    fi
  done
  if command -v sdkmanager >/dev/null 2>&1; then
    SDKMANAGER="$(command -v sdkmanager)"
    echo "found sdkmanager on PATH: $SDKMANAGER"
    return 0
  fi
  return 1
}

echo "== android command-line tools =="
echo "ANDROID_SDK_ROOT = $ANDROID_SDK_ROOT"
echo "JAVA_HOME        = ${JAVA_HOME:-<unset>}"
echo ""

if ! find_sdkmanager; then
  echo "no sdkmanager under \$ANDROID_SDK_ROOT and none on PATH"
  echo ""

  if [ -z "${CMDLINE_TOOLS_ZIP_URL:-}" ]; then
    cat >&2 <<'EOF'
FAIL: no Android command-line tools are available, and no replacement was supplied.

Nothing was downloaded. This script hardcodes no URL on purpose: the pinned
revision documents installing the SDK through the Android Studio GUI
(BUILD_ANDROID.md:15-30) and names no command-line-tools archive, so any URL
here would be invented rather than sourced.

Fix it in one of two ways:

  * Preferred: run on a runner whose image already provides the SDK, and do not
    delete it first. An earlier version of the workflow ran
    `sudo rm -rf /usr/local/lib/android`, which removes exactly the tree this
    script looks for. That line is gone; if the SDK is still missing, the image
    does not ship one.

  * Otherwise: re-run the workflow with the `cmdline_tools_zip_url` input set to
    the official "Command line tools only" Linux zip from
    https://developer.android.com/studio#command-tools
    The archive is downloaded, hashed, and unpacked into
    $ANDROID_SDK_ROOT/cmdline-tools/latest.
EOF
    exit 1
  fi

  ZIP="${RUNNER_TEMP:-/tmp}/cmdline-tools.zip"
  echo "downloading operator-supplied command-line tools:"
  echo "  $CMDLINE_TOOLS_ZIP_URL"
  curl -fsSL --retry 3 --retry-delay 5 -o "$ZIP" "$CMDLINE_TOOLS_ZIP_URL"
  echo "  sha256: $(sha256sum "$ZIP" | awk '{print $1}')"
  echo "  bytes : $(stat -c '%s' "$ZIP")"

  rm -rf "${ANDROID_SDK_ROOT}/cmdline-tools/latest" \
         "${ANDROID_SDK_ROOT}/cmdline-tools/tmp"
  mkdir -p "${ANDROID_SDK_ROOT}/cmdline-tools/tmp"
  unzip -q -o "$ZIP" -d "${ANDROID_SDK_ROOT}/cmdline-tools/tmp"

  # The official archive always roots at cmdline-tools/. Fail loudly if that
  # stops being true rather than guessing at the layout.
  if [ ! -d "${ANDROID_SDK_ROOT}/cmdline-tools/tmp/cmdline-tools" ]; then
    echo "FAIL: the archive did not contain a top-level cmdline-tools/ directory" >&2
    echo "      found instead:" >&2
    ls -la "${ANDROID_SDK_ROOT}/cmdline-tools/tmp" >&2 || true
    exit 1
  fi
  mv "${ANDROID_SDK_ROOT}/cmdline-tools/tmp/cmdline-tools" \
     "${ANDROID_SDK_ROOT}/cmdline-tools/latest"
  rmdir "${ANDROID_SDK_ROOT}/cmdline-tools/tmp"
  rm -f "$ZIP"

  if ! find_sdkmanager; then
    echo "FAIL: still no sdkmanager after unpacking the supplied archive" >&2
    exit 1
  fi
fi

# --- prove it runs, and make it visible to later steps -----------------------
echo ""
echo "sdkmanager --version:"
"$SDKMANAGER" --version

SDKMANAGER_BIN_DIR="$(dirname "$SDKMANAGER")"
if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$SDKMANAGER_BIN_DIR" >> "$GITHUB_PATH"
fi
if [ -n "${GITHUB_ENV:-}" ]; then
  echo "SDKMANAGER=$SDKMANAGER" >> "$GITHUB_ENV"
fi
echo ""
echo "OK: sdkmanager is $SDKMANAGER (directory added to PATH)"
