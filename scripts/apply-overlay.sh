#!/usr/bin/env bash
#
# apply-overlay.sh - apply the working project's source patches to a Vircadia
# core tree, self-test them, or verify an already-patched tree.
#
#   ./apply-overlay.sh --selftest
#       Stage ONLY the files the patches touch into ./selftest/, apply, verify,
#       re-apply to prove idempotency, and print PASS/FAIL per patch.
#       Cheap, hermetic, writes nothing outside ./selftest/.
#
#   ./apply-overlay.sh --dry-run [<tree>]
#       Report every change without writing anything.
#
#   ./apply-overlay.sh --apply <tree>
#       Patch <tree> in place. Refuses if <tree> is the pristine tree.
#
#   ./apply-overlay.sh --verify <tree>
#       Assert the post-conditions. Non-zero exit on any failure.
#
#   ./apply-overlay.sh --apply <tree> --materialise
#       Also create <tree> first by copying the pristine tree. This is a
#       full-tree `cp -a`; it is local (no network) but large. --apply without
#       it assumes the tree already exists.
#
#   ./apply-overlay.sh --apply <tree> --transport direct|ipfs|skip
#       Enable patch 006 (external asset transport). Default: skip.
#
# The pristine tree is read-only by contract and is never written to. All the
# real work lives in scripts/overlay_patches.py (python3 stdlib, no awk).
# This script does NOT download anything and does NOT run a build.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
PY="${PYTHON:-python3}"
ENGINE="$HERE/overlay_patches.py"

PRISTINE="${PRISTINE:-/storage/emulated/0/GLB/vircadia-native-core-master}"
WORK="${WORK:-$HOME/vircadia-android-work/build-tree/vircadia-native-core}"
STAGE_DIR="${STAGE_DIR:-$REPO_ROOT/selftest}"

MODE=""
TREE=""
TRANSPORT="skip"
MATERIALISE=0

usage() { sed -n '3,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --selftest)    MODE="selftest"; shift ;;
    --dry-run)     MODE="dryrun";   if [ $# -ge 2 ] && [ "${2#--}" = "$2" ]; then TREE="$2"; shift; fi; shift ;;
    --apply)       MODE="apply";    [ $# -ge 2 ] || { echo "--apply needs a tree" >&2; exit 2; }; TREE="$2"; shift 2 ;;
    --verify)      MODE="verify";   [ $# -ge 2 ] || { echo "--verify needs a tree" >&2; exit 2; }; TREE="$2"; shift 2 ;;
    --materialise) MATERIALISE=1; shift ;;
    --transport)   [ $# -ge 2 ] || { echo "--transport needs a value" >&2; exit 2; }; TRANSPORT="$2"; shift 2 ;;
    -h|--help)     usage 0 ;;
    *) echo "unknown argument: $1" >&2; usage 2 ;;
  esac
done

[ -n "$MODE" ] || usage 2
[ -f "$ENGINE" ] || { echo "missing patch engine: $ENGINE" >&2; exit 2; }
command -v "$PY" >/dev/null 2>&1 || { echo "python3 not found (set PYTHON=...)" >&2; exit 2; }

# --- Safety guards -----------------------------------------------------------
# The pristine tree is read-only by contract. Refuse to write anywhere that is
# not under $HOME, and refuse if the target and the pristine tree coincide.

guard_target() {
  local t="$1"
  case "$t" in
    "$HOME"/*) : ;;
    *) echo "REFUSING: target must be under \$HOME (got: $t)" >&2; exit 2 ;;
  esac
  if [ "$(readlink -f "$t" 2>/dev/null || echo "$t")" = "$(readlink -f "$PRISTINE" 2>/dev/null || echo "$PRISTINE")" ]; then
    echo "REFUSING: target IS the pristine read-only tree: $t" >&2; exit 2
  fi
}

echo "repo root : $REPO_ROOT"
echo "pristine  : $PRISTINE   (read-only - never written)"
echo "engine    : $ENGINE"
echo

case "$MODE" in
  selftest)
    [ -d "$PRISTINE" ] || { echo "pristine tree not found: $PRISTINE" >&2; exit 2; }
    exec "$PY" -I "$ENGINE" --selftest "$PRISTINE" --stage-dir "$STAGE_DIR" --transport "$TRANSPORT"
    ;;

  dryrun)
    [ -n "$TREE" ] || TREE="$PRISTINE"
    [ -d "$TREE" ] || { echo "tree not found: $TREE" >&2; exit 2; }
    exec "$PY" -I "$ENGINE" --dry-run "$TREE" --transport "$TRANSPORT"
    ;;

  apply)
    [ -n "$TREE" ] || TREE="$WORK"

    if [ "$MATERIALISE" -eq 1 ] && [ ! -d "$TREE" ]; then
      echo "==> materialising build tree (local cp -a, no network)"
      echo "    large copy: $PRISTINE -> $TREE"
      mkdir -p "$(dirname "$TREE")"
      cp -a "$PRISTINE" "$TREE"
      echo
    fi

    [ -d "$TREE" ] || { echo "tree not found: $TREE (use --materialise to copy it)" >&2; exit 2; }
    guard_target "$TREE"

    echo "==> applying patches to $TREE"
    "$PY" -I "$ENGINE" --apply "$TREE" --transport "$TRANSPORT"
    echo
    echo "==> verifying $TREE"
    "$PY" -I "$ENGINE" --verify "$TREE" --transport "$TRANSPORT" --pristine "$PRISTINE"
    ;;

  verify)
    [ -n "$TREE" ] || TREE="$WORK"
    [ -d "$TREE" ] || { echo "tree not found: $TREE" >&2; exit 2; }
    exec "$PY" -I "$ENGINE" --verify "$TREE" --transport "$TRANSPORT" --pristine "$PRISTINE"
    ;;
esac

echo
echo "next task: see $REPO_ROOT/PROGRESS.md"
