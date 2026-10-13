#!/usr/bin/env bash
#
# ci/gvr.sh - resolve com.google.vr:sdk-audio and sdk-base early, and support
# the local-AAR fallback.
#
# Why this exists: android/apps/interface/build.gradle:155-156 asks for
# com.google.vr:sdk-audio:1.80.0 and com.google.vr:sdk-base:1.80.0. Those were
# distributed via jcenter, which no longer serves artifacts. Whether google()
# or mavenCentral() carries those exact versions is UNVERIFIED. Patch 001
# removes jcenter(), so this is the most likely first dependency failure.
#
# Modes (GVR_MODE):
#   maven      (default) resolve from google()/mavenCentral(); probe first and
#              FAIL here, in seconds, when nothing serves the artifact, rather
#              than warning and letting the multi-hour native build discover it.
#              Set GVR_ALLOW_UNRESOLVED=1 to downgrade that failure to a warning
#              when deliberately pushing past it.
#   local-aar  REJECTED. Nothing in this repo consumes the AAR/JAR directory:
#              no patch adds a flatDir repository and no patch rewrites the
#              coordinates at android/apps/interface/build.gradle:155-156, so
#              this mode would change nothing Gradle sees while appearing to be
#              supported. The archives found are printed for information, then
#              the step fails. See LIMITATIONS.md.
#
# [WROTE-UNRUN] Written but never executed. No version numbers are guessed:
# anything not found is reported as not found.

set -uo pipefail

CORE="${1:-${GITHUB_WORKSPACE:-$PWD}}"
GVR_MODE="${GVR_MODE:-maven}"
GVR_VERSION="${GVR_VERSION:-1.80.0}"
REPORT="${REPORT:-gvr-report.txt}"
: "${GITHUB_STEP_SUMMARY:=}"

say() { echo "$@" | tee -a "$REPORT"; }
: > "$REPORT"

say "== gvr dependency probe =="
say "mode    : $GVR_MODE"
say "version : $GVR_VERSION"
say ""

PROBES=(
  "https://dl.google.com/dl/android/maven2/com/google/vr/sdk-audio/${GVR_VERSION}/sdk-audio-${GVR_VERSION}.pom"
  "https://dl.google.com/dl/android/maven2/com/google/vr/sdk-base/${GVR_VERSION}/sdk-base-${GVR_VERSION}.pom"
  "https://repo1.maven.org/maven2/com/google/vr/sdk-audio/${GVR_VERSION}/sdk-audio-${GVR_VERSION}.pom"
  "https://repo1.maven.org/maven2/com/google/vr/sdk-base/${GVR_VERSION}/sdk-base-${GVR_VERSION}.pom"
)

say "-- probing repositories --"
MAVEN_OK=0
for url in "${PROBES[@]}"; do
  code="$(curl -sI -m 25 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo 000)"
  printf '  %-6s %s\n' "$code" "$url" | tee -a "$REPORT"
  case "$code" in 2*) MAVEN_OK=$((MAVEN_OK + 1)) ;; esac
done
say ""

finish() {
  if [ -n "$GITHUB_STEP_SUMMARY" ]; then cat "$REPORT" >> "$GITHUB_STEP_SUMMARY"; fi
  exit "$1"
}

if [ "$GVR_MODE" = "maven" ]; then
  if [ "$MAVEN_OK" -eq 0 ]; then
    say "FAIL: no probed repository serves sdk-audio/sdk-base ${GVR_VERSION}."
    say ""
    say "      android/apps/interface/build.gradle:155-156 requires:"
    say "        com.google.vr:sdk-audio:${GVR_VERSION}"
    say "        com.google.vr:sdk-base:${GVR_VERSION}"
    say "      Both shipped via jcenter, which no longer serves artifacts, and"
    say "      patch 001 removes jcenter(). Stopping now, before the multi-hour"
    say "      native build, because Gradle cannot resolve these."
    say ""
    say "      Next step (do NOT apply blind): a minimal-strip patch that removes"
    say "      the GVR java dependency and its uses, since :interface does not link"
    say "      ovr_sdk_mobile/ovr_platform_sdk at build time. See README.md."
    say ""
    if [ "${GVR_ALLOW_UNRESOLVED:-0}" = "1" ]; then
      say "      GVR_ALLOW_UNRESOLVED=1 is set: continuing anyway, as instructed."
      if [ -n "${GITHUB_ENV:-}" ]; then echo "GVR_RESOLUTION=maven-unresolved" >> "$GITHUB_ENV"; fi
      finish 0
    fi
    if [ -n "${GITHUB_ENV:-}" ]; then echo "GVR_RESOLUTION=maven-unresolved" >> "$GITHUB_ENV"; fi
    finish 1
  fi
  say "OK: ${MAVEN_OK} candidate POM(s) reachable - leaving the dependency as-is."
  say ""
  if [ -n "${GITHUB_ENV:-}" ]; then echo "GVR_RESOLUTION=maven" >> "$GITHUB_ENV"; fi
  finish 0
fi

# --- local-aar: rejected -----------------------------------------------------
say "-- gvr_mode=local-aar --"
say "searching for AAR/JAR files, for information only:"
GVR_ROOT="${HIFI_ANDROID_PRECOMPILED:-}/gvr"
FOUND=0
if [ -d "$GVR_ROOT" ]; then
  while IFS= read -r f; do
    FOUND=$((FOUND + 1))
    say "  found: $f ($(stat -c '%s' "$f") bytes)"
  done < <(find "$GVR_ROOT" -type f \( -name '*.aar' -o -name '*.jar' \) 2>/dev/null | sort)
else
  say "  gvr root not found: $GVR_ROOT"
fi
say ""
say "FAIL: gvr_mode=local-aar is NOT IMPLEMENTED and is rejected rather than"
say "      silently accepted."
say ""
say "      ${FOUND} archive(s) were found above, and that is the whole story:"
say "      nothing in this repository reads a flatDir directory. No patch adds a"
say "      flatDir repository to any build.gradle, and no patch rewrites the"
say "      coordinates at android/apps/interface/build.gradle:155-156. An earlier"
say "      revision of this script exported GVR_FLATDIR and GVR_RESOLUTION into"
say "      \$GITHUB_ENV; grepping the repository showed no reader for either, so"
say "      selecting this mode changed nothing Gradle saw."
say ""
say "      Nothing was changed and nothing was downloaded. Use gvr_mode=maven, or"
say "      write the flatDir wiring deliberately and verify scripts/apply-overlay.sh"
say "      --selftest covers it before relying on it."
finish 1
