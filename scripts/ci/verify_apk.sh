#!/usr/bin/env bash
#
# ci/verify_apk.sh - inspect the built APK and write apk-report.txt.
#
# Hard failure (non-zero exit) ONLY when:
#   * no APK was found
#   * the APK is not a valid zip
#   * lib/arm64-v8a/libnative-lib.so is absent
#
# Everything else is REPORT-ONLY: it is written to apk-report.txt and printed,
# and it never fails the run. A missing animation or a badge we did not expect
# is information, not a build break.
#
# [WROTE-UNRUN] Written but never executed.

set -uo pipefail

APK="${1:-}"
WORKSPACE="${2:-${GITHUB_WORKSPACE:-$PWD}}"
REPORT="${REPORT:-apk-report.txt}"
: "${GITHUB_STEP_SUMMARY:=}"

say() { echo "$@" | tee -a "$REPORT"; }
note() { echo "  $*" | tee -a "$REPORT"; }

: > "$REPORT"
say "== apk report =="
say "date    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "apk     : ${APK:-<none found>}"
say ""

fail_hard() {
  say ""
  say "RESULT: FAIL - $1"
  if [ -n "$GITHUB_STEP_SUMMARY" ]; then cat "$REPORT" >> "$GITHUB_STEP_SUMMARY"; fi
  exit 1
}

if [ -z "$APK" ] || [ ! -f "$APK" ]; then
  fail_hard "no APK file was produced"
fi

say "size    : $(stat -c '%s' "$APK") bytes"
say "sha256  : $(sha256sum "$APK" | awk '{print $1}')"
say ""

if ! unzip -tq "$APK" >/dev/null 2>&1; then
  fail_hard "the APK is not a valid zip archive"
fi
say "zip     : valid"
say ""

# --- hard requirements -------------------------------------------------------
say "== native libraries =="
unzip -l "$APK" | awk '{print $4}' | grep -E '^lib/' | sort > /tmp/apk-libs.txt || true
if [ -s /tmp/apk-libs.txt ]; then
  sed 's/^/  /' /tmp/apk-libs.txt | tee -a "$REPORT"
else
  note "(no lib/ entries)"
fi
say ""

if ! grep -qx 'lib/arm64-v8a/libnative-lib.so' /tmp/apk-libs.txt; then
  fail_hard "lib/arm64-v8a/libnative-lib.so is missing from the APK"
fi
say "OK: lib/arm64-v8a/libnative-lib.so present"
say ""

# --- report-only checks ------------------------------------------------------
say "== manifest (report only) =="
AAPT="$(command -v aapt || command -v aapt2 || true)"
if [ -n "$AAPT" ]; then
  BADGING="$("$AAPT" dump badging "$APK" 2>&1 || true)"
  printf '%s\n' "$BADGING" | grep -E '^(package|launchable-activity|uses-permission|uses-feature|sdkVersion|targetSdkVersion|native-code)' \
    | sed 's/^/  /' | tee -a "$REPORT"
  say ""
  say "  -- uses-feature detail --"
  printf '%s\n' "$BADGING" | grep -E 'uses-feature' | sed 's/^/  /' | tee -a "$REPORT" || true
  if printf '%s\n' "$BADGING" | grep -q "uses-feature: name='android.software.vr.mode'"; then
    if printf '%s\n' "$BADGING" | grep -q "name='android.software.vr.mode'.*required='true'"; then
      note "NOTE: VR mode is still required='true' - patch 002 did not take effect"
    else
      note "OK: VR mode is not required"
    fi
  fi
  if printf '%s\n' "$BADGING" | grep -q "name='android.hardware.touchscreen'"; then
    note "OK: touchscreen feature declared"
  else
    note "NOTE: no touchscreen uses-feature in the badge"
  fi
else
  note "aapt not available - manifest not inspected"
fi
say ""

say "== Qt and codec libraries (report only) =="
QT_COUNT="$(grep -cE "lib/arm64-v8a/libQt" /tmp/apk-libs.txt || true)"
say "  libQt*.so entries : $QT_COUNT"
if grep -q 'libplugins_libhifiCodec.so' /tmp/apk-libs.txt; then
  note "OK: libplugins_libhifiCodec.so present"
else
  note "NOTE: libplugins_libhifiCodec.so absent"
fi
if [ "$QT_COUNT" -eq 0 ]; then
  note "WARNING: no Qt libraries in the APK - the Qt runtime did not get packaged"
fi
say ""

say "== avatar and animation assets (report only) =="
TMP="$(mktemp -d)"
unzip -qq "$APK" -d "$TMP" 2>/dev/null || true

check_asset_string() {
  local needle="$1" label="$2"
  if grep -rqa -- "$needle" "$TMP/assets" 2>/dev/null; then
    note "OK: $label"
  else
    note "NOTE: not found in assets: $label ($needle)"
  fi
}

check_asset_string "meshes/defaultAvatar_full.fst" "default avatar .fst (qrc)"
check_asset_string "meshes/mannequin/mannequin.baked.fbx" "mannequin baked FBX (qrc)"

ANIM_HITS="$(grep -rla 'avatar/animations/' "$TMP/assets" 2>/dev/null | wc -l || true)"
say "  assets referencing avatar/animations/: $ANIM_HITS"
if [ "$ANIM_HITS" -eq 0 ]; then
  note "NOTE: no asset references avatar/animations/ - the qrc may not list them"
fi

SCRIPT_HITS="$(find "$TMP/assets" -path '*scripts*' -name '*.js' 2>/dev/null | wc -l || true)"
say "  packaged script .js files          : $SCRIPT_HITS"
if [ "$SCRIPT_HITS" -eq 0 ]; then
  note "NOTE: no scripts/*.js reached the APK - check the mergeAssets copy task"
fi

if [ -d "$TMP/assets/world" ]; then
  WORLD_FILES="$(find "$TMP/assets/world" -type f 2>/dev/null | wc -l || true)"
  say "  world pack files in assets/world   : $WORLD_FILES"
else
  note "NOTE: no assets/world/ - the Daybreak pack was not included"
fi

rm -rf "$TMP"
say ""
say "RESULT: PASS (hard checks passed; the entries above are report-only)"
say ""
say "REMINDER: this report proves the APK was produced and inspected. It does NOT"
say "prove the app runs. No device or emulator test has been performed."

if [ -n "$GITHUB_STEP_SUMMARY" ]; then cat "$REPORT" >> "$GITHUB_STEP_SUMMARY"; fi
exit 0
