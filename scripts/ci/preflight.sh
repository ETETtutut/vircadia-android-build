#!/usr/bin/env bash
#
# ci/preflight.sh - check every external-asset URL before committing to a
# multi-hour build, and decide whether the asset-transport patch is safe.
#
# The archive names, versions and mirror lists live in
# cmake/ExternalAssetsConfig.cmake. This script does not hardcode them: it
# extracts the URLs from that file at run time, so it keeps working when the
# pinned revision changes.
#
# FAIL EARLY only when a required archive has no reachable candidate URL.
#
# Usage: preflight.sh [CORE_TREE] [REQUESTED_TRANSPORT]
#   CORE_TREE          default $GITHUB_WORKSPACE/core
#   REQUESTED_TRANSPORT  skip | direct | ipfs   (default skip)
#   Writes ASSET_TRANSPORT_EFFECTIVE to $GITHUB_ENV. That value is always either
#   "skip" or exactly what was requested - never a substitute.
#
# [WROTE-UNRUN] Written but never executed. The exact shape of
# ExternalAssetsConfig.cmake was NOT read when this was written (no shell was
# available), so the extraction is deliberately permissive and reports what it
# could not parse rather than assuming a layout.

set -euo pipefail

CORE="${1:-${GITHUB_WORKSPACE:-$PWD}}"
CONFIG="${CORE}/cmake/ExternalAssetsConfig.cmake"
REPORT="${REPORT:-preflight-report.txt}"
: "${GITHUB_STEP_SUMMARY:=}"

{
  echo "== preflight =="
  echo "core   : $CORE"
  echo "config : $CONFIG"
  echo ""
} | tee "$REPORT"

if [ ! -f "$CONFIG" ]; then
  echo "ERROR: $CONFIG not found - cannot preflight asset URLs" | tee -a "$REPORT" >&2
  exit 1
fi

# --- extract candidate URLs --------------------------------------------------
# Permissive: any http(s) URL literal in the file.
grep -oE 'https?://[^"'"'"' )]+' "$CONFIG" \
  | sed 's/[,;]$//' \
  | sort -u > urls.txt || true

echo "found $(wc -l < urls.txt) unique URL literal(s) in ExternalAssetsConfig.cmake" | tee -a "$REPORT"
echo "" | tee -a "$REPORT"

if [ ! -s urls.txt ]; then
  echo "WARNING: no URL literals found. The asset config may build URLs from" | tee -a "$REPORT"
  echo "         variables. Preflight cannot verify reachability; continuing." | tee -a "$REPORT"
else
  printf '%-6s %s\n' "CODE" "URL" | tee -a "$REPORT"
  printf '%-6s %s\n' "----" "---" | tee -a "$REPORT"
  unreachable=0
  while read -r url; do
    code="$(curl -sI -m 25 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo 000)"
    printf '%-6s %s\n' "$code" "$url" | tee -a "$REPORT"
    case "$code" in
      2*|3*|405|403) ;;   # 403/405 still mean the host answered
      *) unreachable=$((unreachable + 1)) ;;
    esac
  done < urls.txt
  echo "" | tee -a "$REPORT"
  echo "unreachable: $unreachable" | tee -a "$REPORT"

  # Only fatal when NOTHING answers: one dead mirror among several is expected
  # and the downloader can pick another.
  total="$(wc -l < urls.txt)"
  if [ "$unreachable" -eq "$total" ]; then
    echo "FAIL: not a single asset URL answered - the build cannot fetch its dependencies" \
      | tee -a "$REPORT" >&2
    exit 1
  fi
fi

# --- asset transport safety check -------------------------------------------
# scripts/overlay_patches.py patch 006 can set the external asset transport, but
# only for option names that really exist in this revision's CMake config.
#
# The REQUESTED transport is passed in as $2 and is NEVER rewritten to a
# different one. An earlier revision always reported "direct" whenever both
# option names were present, so requesting ipfs silently produced a direct
# build. Either the request is honoured exactly, or this step fails.
REQUESTED="${2:-${ASSET_TRANSPORT_REQUESTED:-skip}}"
case "$REQUESTED" in
  skip|direct|ipfs) ;;
  *)
    echo "FAIL: unknown asset transport '${REQUESTED}' (expected skip|direct|ipfs)" \
      | tee -a "$REPORT" >&2
    exit 1 ;;
esac

echo "" | tee -a "$REPORT"
echo "== asset transport options ==" | tee -a "$REPORT"
echo "requested: $REQUESTED" | tee -a "$REPORT"
DIRECT_FOUND=0
IPFS_FOUND=0
if grep -q 'USE_DIRECT_EXTERNAL_BUILD_ASSETS' "$CONFIG"; then DIRECT_FOUND=1; fi
if grep -q 'USE_IPFS_EXTERNAL_BUILD_ASSETS' "$CONFIG"; then IPFS_FOUND=1; fi
echo "USE_DIRECT_EXTERNAL_BUILD_ASSETS present: $DIRECT_FOUND" | tee -a "$REPORT"
echo "USE_IPFS_EXTERNAL_BUILD_ASSETS   present: $IPFS_FOUND" | tee -a "$REPORT"

if [ "$REQUESTED" = "skip" ]; then
  ASSET_TRANSPORT_EFFECTIVE="skip"
  echo "not requested - upstream defaults kept" | tee -a "$REPORT"
elif [ "$DIRECT_FOUND" -eq 1 ] && [ "$IPFS_FOUND" -eq 1 ]; then
  ASSET_TRANSPORT_EFFECTIVE="$REQUESTED"
  echo "both option names present - transport=${REQUESTED} can be set safely" \
    | tee -a "$REPORT"
else
  ASSET_TRANSPORT_EFFECTIVE=""
  {
    echo "FAIL: transport '${REQUESTED}' was requested, but the CMake option"
    echo "      names are not both present in:"
    echo "        ${CONFIG}"
    echo "      patch 006 cannot set it, and substituting a different transport"
    echo "      is exactly the silent downgrade this check exists to prevent."
    echo "      Re-run with asset_transport=skip, or reconcile the option names."
  } | tee -a "$REPORT" >&2
  if [ -n "$GITHUB_STEP_SUMMARY" ]; then cat "$REPORT" >> "$GITHUB_STEP_SUMMARY"; fi
  exit 1
fi
echo "ASSET_TRANSPORT_EFFECTIVE=$ASSET_TRANSPORT_EFFECTIVE" | tee -a "$REPORT"

if [ -n "${GITHUB_ENV:-}" ]; then
  echo "ASSET_TRANSPORT_EFFECTIVE=$ASSET_TRANSPORT_EFFECTIVE" >> "$GITHUB_ENV"
fi
if [ -n "$GITHUB_STEP_SUMMARY" ]; then
  cat "$REPORT" >> "$GITHUB_STEP_SUMMARY"
fi
