#!/usr/bin/env python3
"""
overlay_patches.py - anchor-based, idempotent, fail-loud source patches for the
native Vircadia Android build.

Usage
    python3 -I overlay_patches.py --apply    <tree>
    python3 -I overlay_patches.py --verify   <tree>
    python3 -I overlay_patches.py --selftest <tree>

Design rules (these are the contract; do not relax them)
  * Every transform is an exact-string or single-regex substitution carrying a
    STRICT expected occurrence count. If an anchor is not found exactly as many
    times as expected the run aborts non-zero. Never a silent no-op.
  * Every transform is idempotent: a second run makes no further change.
  * Every change is printed: patch id, file, count, and a short diff summary.
  * Standard library only. No awk, no network, no subprocess.
  * Writes happen only inside the tree passed on the command line.

Patch index
  001  android/**/*.gradle           jcenter() -> mavenCentral()
  002  AndroidManifest.xml           VR uses-feature -> optional; declare touchscreen
  003  AndroidManifest.xml           accelerometer/gyroscope -> optional
  004  (assertion only, no edit)     default avatar already resolves to the bundled FST
  005  VirtualPadManager.h           initialise _hidden and the Instance members
  006  apps/interface/build.gradle   external-asset transport cmake arguments (opt-in)
  007  PermissionChecker.java        boot into the installed world when none was given
  008  PermissionChecker.java        start the world installer in onCreate
  OVL  overlay/**                    copies this project's new files into the tree

Status vocabulary used in self-test output: PASS / FAIL / SKIP.
"""

import argparse
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

# --------------------------------------------------------------------------
# Paths inside a Vircadia core tree
# --------------------------------------------------------------------------

MANIFEST_REL = "android/apps/interface/src/main/AndroidManifest.xml"
ROOT_GRADLE_REL = "android/build.gradle"
APP_GRADLE_REL = "android/apps/interface/build.gradle"
VPAD_H_REL = "libraries/ui/src/VirtualPadManager.h"
AVATARDATA_CPP_REL = "libraries/avatars/src/AvatarData.cpp"
DEFAULT_AVATAR_REL = "interface/resources/meshes/defaultAvatar_full.fst"
PERMCHECK_REL = ("android/apps/interface/src/main/java/io/highfidelity/hifiinterface/"
                 "PermissionChecker.java")

# Files any patch is allowed to modify. --selftest stages exactly these.
TOUCHED_FILES = [
    ROOT_GRADLE_REL,
    APP_GRADLE_REL,
    MANIFEST_REL,
    VPAD_H_REL,
    PERMCHECK_REL,
]
# Files we only ever READ (assertions). Staged too, so self-test is hermetic.
READONLY_FILES = [
    AVATARDATA_CPP_REL,
]

VR_FEATURES = ("android.software.vr.mode", "android.hardware.vr.high_performance")
SENSOR_FEATURES = ("android.hardware.sensor.accelerometer", "android.hardware.sensor.gyroscope")
TOUCHSCREEN_FEATURE = "android.hardware.touchscreen"

ANDROID_NS = "http://schemas.android.com/apk/res/android"
REQUIRED_TRUE = re.compile(r'android:required\s*=\s*"true"')
USES_FEATURE_LINE = re.compile(
    r'^(?P<indent>\s*)<uses-feature\b[^>]*android:name="(?P<name>[^"]+)"[^>]*>\s*$'
)


class PatchError(Exception):
    """Raised when an anchor does not match its strict expected count."""


def _p(tree, rel):
    return os.path.join(tree, rel)


def _read(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _write(path, text):
    """Write only when the content actually changes. Returns True if written."""
    if os.path.exists(path) and _read(path) == text:
        return False
    tmp = path + ".patchtmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return True


def _replace_exact(text, old, new, label):
    """Substitute `old` for `new`, requiring the occurrence count to be exact.

    `old` may be a list: then it is tried in order and the first one that
    matches exactly once is used (that is how idempotent patches express
    'either the pristine form or the already-patched form').
    """
    candidates = old if isinstance(old, list) else [old]
    for cand in candidates:
        n = text.count(cand)
        if n == 1:
            return text.replace(cand, new, 1), True
    counts = {repr(c)[:70]: text.count(c) for c in candidates}
    raise PatchError("{}: anchor not found exactly once ({})".format(label, counts))


def _replace_idempotent(text, old_forms, new_forms, label, where):
    """Substitute a block that has exactly two legal states: pristine or patched.

    `_replace_exact` cannot express this. It returns the first candidate that
    matches exactly once and raises otherwise, so on a *second* apply it sees the
    already-patched text, finds zero occurrences of the pristine anchor, and
    fails - a false alarm, not a real problem.

    This helper counts both forms and accepts only two outcomes:

        pristine == 1, patched == 0  ->  substitute, return "applied"
        pristine == 0, patched == 1  ->  no-op,      return "already"

    Anything else raises, which covers both remaining states:

      * neither form present - the block was edited or removed upstream, or the
        indentation changed, so our anchor is stale;
      * both forms present - a partial or duplicated edit.

    Both are unexpected source. Failing loudly is the point: a silent no-op here
    would ship a file that is neither the pristine nor the patched version.
    """
    n_old = sum(text.count(c) for c in old_forms)
    n_new = sum(text.count(c) for c in new_forms)
    if n_old == 1 and n_new == 0:
        for cand in old_forms:
            if text.count(cand) == 1:
                return text.replace(cand, new_forms[0], 1), "applied"
    if n_old == 0 and n_new == 1:
        return text, "already"
    raise PatchError(
        "{}: {} is in an unexpected state - found {} pristine and {} patched "
        "occurrence(s) of the block, expected exactly one of the two. Inspect the "
        "file and reconcile it by hand before patching".format(
            label, where, n_old, n_new))


# --------------------------------------------------------------------------
# 001 - jcenter() -> mavenCentral()
# --------------------------------------------------------------------------

EXPECTED_JCENTER = {ROOT_GRADLE_REL: 2, APP_GRADLE_REL: 2}

# A lone jcenter() becomes mavenCentral(); a jcenter() immediately above an
# existing mavenCentral() is dropped, so MavenRepo is not declared twice.
JCENTER_LINE = re.compile(r'^[ \t]*jcenter\(\)[ \t]*$')
MAVENCENTRAL_LINE = re.compile(r'^[ \t]*mavenCentral\(\)[ \t]*$')


def patch_001(tree, changes, apply):
    found = {}
    for rel in (ROOT_GRADLE_REL, APP_GRADLE_REL):
        path = _p(tree, rel)
        if not os.path.isfile(path):
            raise PatchError("001: {} missing".format(rel))
        found[rel] = [i for i, ln in enumerate(_read(path).splitlines()) if JCENTER_LINE.match(ln)]

    total = sum(len(v) for v in found.values())
    if total == 0:
        changes.append(("001", "android/**/*.gradle", 0, "already applied (no jcenter())"))
        return

    if {k: len(v) for k, v in found.items()} != EXPECTED_JCENTER:
        raise PatchError(
            "001: expected jcenter() counts {} but found {} - upstream tree differs "
            "from the pinned revision; inspect before patching".format(
                EXPECTED_JCENTER, {k: len(v) for k, v in found.items()}))

    if not apply:
        changes.append(("001", "android/**/*.gradle", total, "would rewrite {} line(s)".format(total)))
        return

    written = 0
    for rel, idxs in found.items():
        path = _p(tree, rel)
        lines = _read(path).splitlines(keepends=True)
        out = []
        for i, ln in enumerate(lines):
            stripped = ln.rstrip("\r\n")
            eol = ln[len(stripped):]
            if JCENTER_LINE.match(stripped):
                nxt = lines[i + 1].rstrip("\r\n") if i + 1 < len(lines) else ""
                if MAVENCENTRAL_LINE.match(nxt):
                    continue  # drop: the next line already declares mavenCentral()
                out.append(stripped.replace("jcenter()", "mavenCentral()") + eol)
            else:
                out.append(ln)
        if _write(path, "".join(out)):
            written += 1
    changes.append(("001", "android/**/*.gradle", total,
                    "rewrote {} line(s) across {} file(s)".format(total, written)))


def verify_001(tree, results):
    ok = True
    for rel in (ROOT_GRADLE_REL, APP_GRADLE_REL):
        text = _read(_p(tree, rel))
        if "jcenter()" in text:
            results.append(("001", "FAIL", "{} still contains jcenter()".format(rel)))
            ok = False
    if "mavenCentral()" not in _read(_p(tree, ROOT_GRADLE_REL)):
        results.append(("001", "FAIL", "{} has no mavenCentral()".format(ROOT_GRADLE_REL)))
        ok = False
    if ok:
        results.append(("001", "PASS", "no jcenter(); mavenCentral() present"))
    return ok


# --------------------------------------------------------------------------
# Manifest helpers (002 and 003 share them)
# --------------------------------------------------------------------------

def _manifest_lines(tree):
    path = _p(tree, MANIFEST_REL)
    if not os.path.isfile(path):
        raise PatchError("manifest not found: {}".format(MANIFEST_REL))
    return path, _read(path).splitlines(keepends=True)


def _feature_names(lines):
    names = []
    for ln in lines:
        m = USES_FEATURE_LINE.match(ln.rstrip("\r\n"))
        if m:
            names.append(m.group("name"))
    return names


def _relax_required(tree, changes, apply, patch_id, features, title):
    """Flip android:required="true" to "false" on the named uses-feature lines."""
    path, lines = _manifest_lines(tree)
    present = [n for n in _feature_names(lines) if n in features]
    if len(present) != len(features):
        raise PatchError("{}: expected features {} but manifest declares {}".format(
            patch_id, list(features), _feature_names(lines)))

    hits = 0
    out = []
    for ln in lines:
        stripped = ln.rstrip("\r\n")
        eol = ln[len(stripped):]
        m = USES_FEATURE_LINE.match(stripped)
        if m and m.group("name") in features and REQUIRED_TRUE.search(stripped):
            hits += 1
            out.append(REQUIRED_TRUE.sub('android:required="false"', stripped, count=1) + eol)
        else:
            out.append(ln)

    if hits == 0:
        changes.append((patch_id, MANIFEST_REL, 0, "already applied ({})".format(title)))
        return
    if not apply:
        changes.append((patch_id, MANIFEST_REL, hits, "would relax {} line(s)".format(hits)))
        return
    if _write(path, "".join(out)):
        changes.append((patch_id, MANIFEST_REL, hits, "relaxed {} line(s)".format(hits)))


def verify_no_required(tree, results, patch_id, features, label):
    _, lines = _manifest_lines(tree)
    bad = []
    for ln in lines:
        stripped = ln.rstrip("\r\n")
        m = USES_FEATURE_LINE.match(stripped)
        if m and m.group("name") in features and REQUIRED_TRUE.search(stripped):
            bad.append(m.group("name"))
    if bad:
        results.append((patch_id, "FAIL", "{} still required=\"true\": {}".format(label, bad)))
        return False
    results.append((patch_id, "PASS", "{} optional".format(label)))
    return True


# --------------------------------------------------------------------------
# 002 - VR uses-feature optional, and declare the touchscreen
# --------------------------------------------------------------------------

def patch_002(tree, changes, apply):
    _relax_required(tree, changes, apply, "002", VR_FEATURES, "VR features optional")

    # Declare the touchscreen as supported-but-not-required, so one APK stays
    # offerable to a phone (touch) and a headset (no touch) at once.
    path, lines = _manifest_lines(tree)
    if TOUCHSCREEN_FEATURE in _feature_names(lines):
        changes.append(("002", MANIFEST_REL, 0, "touchscreen already declared"))
        return

    anchor = None
    for i, ln in enumerate(lines):
        m = USES_FEATURE_LINE.match(ln.rstrip("\r\n"))
        if m and m.group("name") == "android.hardware.sensor.gyroscope":
            anchor = i
            break
    if anchor is None:
        raise PatchError("002: no gyroscope uses-feature anchor found for the touchscreen insert")
    if not apply:
        changes.append(("002", MANIFEST_REL, 1, "would insert touchscreen uses-feature after line {}".format(anchor + 1)))
        return

    indent = USES_FEATURE_LINE.match(lines[anchor].rstrip("\r\n")).group("indent")
    eol = "\n" if lines[anchor].endswith("\n") else ""
    new_line = '{}<uses-feature android:name="{}" android:required="false" />{}'.format(
        indent, TOUCHSCREEN_FEATURE, eol)
    lines.insert(anchor + 1, new_line)
    if _write(path, "".join(lines)):
        changes.append(("002", MANIFEST_REL, 1, "inserted touchscreen uses-feature after line {}".format(anchor + 1)))


def verify_002(tree, results):
    ok = verify_no_required(tree, results, "002", VR_FEATURES, "VR uses-feature")
    _, lines = _manifest_lines(tree)
    names = _feature_names(lines)
    if TOUCHSCREEN_FEATURE not in names:
        results.append(("002", "FAIL", "touchscreen uses-feature not declared"))
        return False
    for ln in lines:
        stripped = ln.rstrip("\r\n")
        m = USES_FEATURE_LINE.match(stripped)
        if m and m.group("name") == TOUCHSCREEN_FEATURE and REQUIRED_TRUE.search(stripped):
            results.append(("002", "FAIL", "touchscreen must not be required=\"true\""))
            return False
    # The renderer genuinely needs GLES 3.2: this must survive every patch.
    text = _read(_p(tree, MANIFEST_REL))
    if 'android:glEsVersion="0x00030002"' not in text or \
            not re.search(r'glEsVersion="0x00030002"[^>]*required="true"', text):
        results.append(("002", "FAIL", "glEsVersion 0x00030002 is not still required=\"true\""))
        return False
    results.append(("002", "PASS", "VR optional, touchscreen declared, glEsVersion untouched"))
    return ok


# --------------------------------------------------------------------------
# 003 - sensor uses-feature optional
# --------------------------------------------------------------------------

def patch_003(tree, changes, apply):
    _relax_required(tree, changes, apply, "003", SENSOR_FEATURES, "sensor features optional")


def verify_003(tree, results):
    return verify_no_required(tree, results, "003", SENSOR_FEATURES, "sensor uses-feature")


# --------------------------------------------------------------------------
# 004 - assertion only: the default avatar is already the bundled FST
# --------------------------------------------------------------------------
#
# Verified by reading libraries/avatars/src/AvatarData.cpp:126-134:
#
#   QUrl AvatarData::_defaultFullAvatarModelUrl = {};
#   const QUrl& AvatarData::defaultFullAvatarModelUrl() {
#       if (_defaultFullAvatarModelUrl.isEmpty()) {
#           _defaultFullAvatarModelUrl = PathUtils::resourcesUrl("/meshes/defaultAvatar_full.fst");
#       }
#       return _defaultFullAvatarModelUrl;
#   }
#
# and MyAvatar.cpp:204-205 feeds that into the fullAvatarURL setting. So the
# client loads the local, bundled mannequin with no CDN involved. There is
# nothing to repoint, so this "patch" only asserts the invariant and fails loud
# if a future core revision changes it.

AVATAR_ASSERT = 'PathUtils::resourcesUrl("/meshes/defaultAvatar_full.fst")'


def patch_004(tree, changes, apply):
    changes.append(("004", AVATARDATA_CPP_REL, 0,
                    "no edit needed - default avatar already resolves to the bundled FST"))


def verify_004(tree, results):
    path = _p(tree, AVATARDATA_CPP_REL)
    if not os.path.isfile(path):
        results.append(("004", "FAIL", "{} missing".format(AVATARDATA_CPP_REL)))
        return False
    if AVATAR_ASSERT not in _read(path):
        results.append(("004", "FAIL",
                        "defaultFullAvatarModelUrl no longer names the bundled FST - "
                        "the default avatar may now be a network URL"))
        return False
    fst = _p(tree, DEFAULT_AVATAR_REL)
    if not os.path.isfile(fst):
        results.append(("004", "FAIL", "{} missing from the tree".format(DEFAULT_AVATAR_REL)))
        return False
    results.append(("004", "PASS", "default avatar = bundled {}".format(DEFAULT_AVATAR_REL)))
    return True


# --------------------------------------------------------------------------
# 005 - VirtualPadManager: initialise _hidden and the Instance members
# --------------------------------------------------------------------------
#
# Read evidence (2026-10-13):
#   VirtualPadManager.h:73   bool _hidden;              <- no initialiser
#   VirtualPadManager.h:27-30  Instance members, no initialiser, no ctor
#   VirtualPadManager.cpp:47-49  Manager::Manager() { }  <- empty body
#
# So isHidden() (and isBeingTouched()/isShown()) return indeterminate values.
# Every guard in TouchscreenVirtualPadDevice is `isEnabled() && !isHidden()`,
# so an indeterminate _hidden can silently disable the pad, and an
# indeterminate _shown can suppress drawing it. This is the smallest change
# that makes the documented "default-on" behaviour actually true.

VPAD_MGR_OLD = [
    "        bool _enabled { true };\n        bool _hidden;\n",
]
VPAD_MGR_NEW = "        bool _enabled { true };\n        bool _hidden { false };\n"

VPAD_INST_OLD = [
    "        bool _isBeingTouched;\n"
    "        glm::vec2 _firstTouch;\n"
    "        glm::vec2 _currentTouch;\n"
    "        bool _shown;\n",
]
VPAD_INST_NEW = (
    "        bool _isBeingTouched { false };\n"
    "        glm::vec2 _firstTouch { 0.0f };\n"
    "        glm::vec2 _currentTouch { 0.0f };\n"
    "        bool _shown { false };\n"
)


def patch_005(tree, changes, apply):
    path = _p(tree, VPAD_H_REL)
    if not os.path.isfile(path):
        raise PatchError("005: {} missing".format(VPAD_H_REL))
    text = _read(path)

    # Both blocks are replaced IN PLACE, so each has exactly two legal states
    # and each needs the idempotent helper. Without it the second apply finds
    # zero pristine anchors and raises, which is why --selftest pass 2 failed.
    text, mgr_state = _replace_idempotent(
        text, VPAD_MGR_OLD, [VPAD_MGR_NEW], "005/_hidden", VPAD_H_REL)
    text, inst_state = _replace_idempotent(
        text, VPAD_INST_OLD, [VPAD_INST_NEW], "005/Instance", VPAD_H_REL)

    note = "_hidden={}, Instance={}".format(mgr_state, inst_state)

    if mgr_state == "already" and inst_state == "already":
        changes.append(("005", VPAD_H_REL, 0, "already applied"))
        return
    if not apply:
        changes.append(("005", VPAD_H_REL, 5,
                        "would initialise _hidden + 4 Instance members ({})".format(note)))
        return
    if _write(path, text):
        changes.append(("005", VPAD_H_REL, 5,
                        "initialised _hidden + 4 Instance members ({})".format(note)))


def verify_005(tree, results):
    text = _read(_p(tree, VPAD_H_REL))
    bad = []
    if "bool _hidden { false };" not in text:
        bad.append("_hidden uninitialised")
    for decl in ("bool _isBeingTouched;", "glm::vec2 _firstTouch;",
                 "glm::vec2 _currentTouch;", "bool _shown;"):
        if decl in text:
            bad.append("uninitialised member: {}".format(decl.strip()))
    if bad:
        results.append(("005", "FAIL", "; ".join(bad)))
        return False
    results.append(("005", "PASS", "_hidden and all 4 Instance members initialised"))
    return True


# --------------------------------------------------------------------------
# 006 - external-asset transport (opt-in)
# --------------------------------------------------------------------------
#
# Upstream defaults the external asset transport to IPFS. Two of the mirrors
# it can use are personal DDNS hosts. This patch writes explicit CMake flags so
# the transport is chosen deliberately rather than inherited.
#
# SAFETY: the flag names are NOT verified against cmake/ExternalAssetsConfig.cmake
# in this session (no shell available). An unused -D is inert (CMake warns), but
# if the real option is named differently, forcing IPFS=OFF without a working
# replacement would leave the build with no assets at all. So this patch is
# OPT-IN, and scripts/ci/20_preflight.sh checks the option names exist before
# the workflow enables it. See LIMITATIONS.md.

KTX_ANCHOR = "                    '-DDISABLE_KTX_CACHE=OFF',\n"

TRANSPORT_FLAGS = {
    "direct": ("                    '-DUSE_DIRECT_EXTERNAL_BUILD_ASSETS=ON',\n"
               "                    '-DUSE_IPFS_EXTERNAL_BUILD_ASSETS=OFF',\n"),
    "ipfs": ("                    '-DUSE_DIRECT_EXTERNAL_BUILD_ASSETS=OFF',\n"
             "                    '-DUSE_IPFS_EXTERNAL_BUILD_ASSETS=ON',\n"),
}


def patch_006(tree, changes, apply, transport="skip"):
    if transport == "skip":
        changes.append(("006", APP_GRADLE_REL, 0, "skipped (transport=skip; upstream defaults kept)"))
        return
    path = _p(tree, APP_GRADLE_REL)
    text = _read(path)
    if "USE_DIRECT_EXTERNAL_BUILD_ASSETS" in text or "USE_IPFS_EXTERNAL_BUILD_ASSETS" in text:
        changes.append(("006", APP_GRADLE_REL, 0, "already applied"))
        return
    new = TRANSPORT_FLAGS[transport]
    text, _ = _replace_exact(text, KTX_ANCHOR, KTX_ANCHOR + new, "006/ktx-anchor")
    if not apply:
        changes.append(("006", APP_GRADLE_REL, 1, "would add transport={} cmake arguments".format(transport)))
        return
    if _write(path, text):
        changes.append(("006", APP_GRADLE_REL, 1, "added transport={} cmake arguments".format(transport)))


def verify_006(tree, results, transport="skip"):
    if transport == "skip":
        results.append(("006", "SKIP", "transport=skip (upstream defaults)"))
        return True
    text = _read(_p(tree, APP_GRADLE_REL))
    if "USE_DIRECT_EXTERNAL_BUILD_ASSETS" not in text:
        results.append(("006", "FAIL", "transport arguments not present in {}".format(APP_GRADLE_REL)))
        return False
    results.append(("006", "PASS", "transport={} arguments present".format(transport)))
    return True


# --------------------------------------------------------------------------
# 007 / 008 - boot into the installed world pack
# --------------------------------------------------------------------------
#
# Read evidence, PermissionChecker.java (159 lines):
#   :83-92   launchActivityWithPermissions() builds the InterfaceActivity Intent
#            and forwards only the "args" extra. It never sets "url".
#   :37      mArgs comes from the caller's "args" extra.
# InterfaceActivity.java:55,58,100-108 shows the contract: the "url" extra is
# turned into `--url <value>` in applicationArguments, which is what the engine
# consumes. So supplying "url" is sufficient and is the documented path.
#
# With no world installed this is a no-op and the engine boots to
# DEFAULT_HOME_ADDRESS (file:///~/serverless/tutorial.json), i.e. stock
# behaviour is preserved exactly.

PERMCHECK_MARKER = "WorldInstaller.installedWorldJson"

PERMCHECK_ANCHOR = "        startActivity(i);\n        finish();\n    }\n"

PERMCHECK_NEW = (
    "        // If the caller supplied neither a domain url nor args, and a world pack\n"
    "        // has been installed into private storage, boot into it. Otherwise leave\n"
    "        // the engine to its own default (DEFAULT_HOME_ADDRESS - the serverless\n"
    "        // tutorial), so stock behaviour is unchanged when no world is installed.\n"
    "        boolean callerSuppliedTarget = !TextUtils.isEmpty(mArgs)\n"
    "                || (getIntent() != null && getIntent().hasExtra(InterfaceActivity.DOMAIN_URL));\n"
    "        if (!callerSuppliedTarget) {\n"
    "            java.io.File worldJson = WorldInstaller.installedWorldJson(this);\n"
    "            if (worldJson.isFile()) {\n"
    "                i.putExtra(InterfaceActivity.DOMAIN_URL,\n"
    "                        \"file://\" + worldJson.getAbsolutePath());\n"
    "                Log.d(TAG, \"Booting into installed world: \" + worldJson.getAbsolutePath());\n"
    "            }\n"
    "        }\n"
    "\n"
    "        startActivity(i);\n"
    "        finish();\n"
    "    }\n"
)

ONCREATE_ANCHOR = ("        Intent myIntent = new Intent(this, BreakpadUploaderService.class);\n"
                   "        startService(myIntent);\n")

ONCREATE_NEW = (ONCREATE_ANCHOR +
                "\n"
                "        // Install the bundled world pack into private storage, off the UI thread.\n"
                "        WorldInstaller.installAsync(this);\n")


def patch_007(tree, changes, apply):
    path = _p(tree, PERMCHECK_REL)
    if not os.path.isfile(path):
        raise PatchError("007: {} missing".format(PERMCHECK_REL))
    text = _read(path)
    if PERMCHECK_MARKER in text:
        changes.append(("007", os.path.basename(PERMCHECK_REL), 0, "already applied"))
        return
    text, _ = _replace_exact(text, PERMCHECK_ANCHOR, PERMCHECK_NEW, "007/launch")
    if not apply:
        changes.append(("007", os.path.basename(PERMCHECK_REL), 1,
                        "would add the DOMAIN_URL fallback (1 substitution)"))
        return
    if _write(path, text):
        changes.append(("007", os.path.basename(PERMCHECK_REL), 1,
                        "added the DOMAIN_URL fallback (1 substitution)"))


def verify_007(tree, results):
    path = _p(tree, PERMCHECK_REL)
    if not os.path.isfile(path):
        results.append(("007", "FAIL", "{} missing".format(PERMCHECK_REL)))
        return False
    text = _read(path)
    if PERMCHECK_MARKER not in text:
        results.append(("007", "FAIL", "no DOMAIN_URL fallback present"))
        return False
    if "InterfaceActivity.DOMAIN_URL" not in text:
        results.append(("007", "FAIL", "fallback does not use InterfaceActivity.DOMAIN_URL"))
        return False
    results.append(("007", "PASS", "PermissionChecker sets DOMAIN_URL only when no url/args given"))
    return True


def patch_008(tree, changes, apply):
    path = _p(tree, PERMCHECK_REL)
    if not os.path.isfile(path):
        raise PatchError("008: {} missing".format(PERMCHECK_REL))
    text = _read(path)
    if "WorldInstaller.installAsync" in text:
        changes.append(("008", os.path.basename(PERMCHECK_REL), 0, "already applied"))
        return
    text, _ = _replace_exact(text, ONCREATE_ANCHOR, ONCREATE_NEW, "008/onCreate")
    if not apply:
        changes.append(("008", os.path.basename(PERMCHECK_REL), 1,
                        "would start the world installer in onCreate"))
        return
    if _write(path, text):
        changes.append(("008", os.path.basename(PERMCHECK_REL), 1,
                        "started the world installer in onCreate"))


def verify_008(tree, results):
    text = _read(_p(tree, PERMCHECK_REL))
    if "WorldInstaller.installAsync" not in text:
        results.append(("008", "FAIL", "world installer is never started"))
        return False
    results.append(("008", "PASS", "world installer started in onCreate"))
    return True


# --------------------------------------------------------------------------
# Overlay files - whole files this project adds to the tree
# --------------------------------------------------------------------------

OVERLAY_DIRNAME = "overlay"


def install_overlay_files(tree, repo_root, changes, apply):
    """Copy overlay/** into the tree, preserving relative paths."""
    src_root = os.path.join(repo_root, OVERLAY_DIRNAME)
    if not os.path.isdir(src_root):
        changes.append(("OVL", OVERLAY_DIRNAME, 0, "no overlay/ directory - nothing to copy"))
        return
    copied, same = [], []
    for dirpath, _dirnames, filenames in os.walk(src_root):
        for fn in filenames:
            if fn == "README.md":
                continue
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, src_root)
            dst = os.path.join(tree, rel)
            if os.path.exists(dst) and _read(dst) == _read(src):
                same.append(rel)
                continue
            copied.append(rel)
            if apply:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(src, "r", encoding="utf-8", newline="") as fh:
                    _write(dst, fh.read())
    if copied:
        verb = "copied" if apply else "would copy"
        changes.append(("OVL", "overlay/**", len(copied),
                        "{} {} file(s): {}".format(verb, len(copied), ", ".join(sorted(copied)))))
    else:
        changes.append(("OVL", "overlay/**", 0, "already current ({} file(s))".format(len(same))))


def verify_overlay_files(tree, repo_root, results):
    src_root = os.path.join(repo_root, OVERLAY_DIRNAME)
    if not os.path.isdir(src_root):
        results.append(("OVL", "SKIP", "no overlay/ directory"))
        return True
    ok, missing = True, []
    for dirpath, _dirnames, filenames in os.walk(src_root):
        for fn in filenames:
            if fn == "README.md":
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), src_root)
            if not os.path.isfile(os.path.join(tree, rel)):
                missing.append(rel)
                ok = False
    if not ok:
        results.append(("OVL", "FAIL", "overlay files missing from the tree: {}".format(missing)))
        return False
    results.append(("OVL", "PASS", "every overlay file is present in the tree"))
    return True


# --------------------------------------------------------------------------
# Tree-wide structural assertions (run by --verify; not a patch)
# --------------------------------------------------------------------------

def verify_manifest_parses(tree, results):
    path = _p(tree, MANIFEST_REL)
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        results.append(("XML", "FAIL", "{} does not parse: {}".format(MANIFEST_REL, exc)))
        return False
    results.append(("XML", "PASS", "{} parses as XML".format(MANIFEST_REL)))
    return True


def verify_pristine_untouched(tree, results, pristine):
    """Guard: refuse to have written anything into the read-only pristine tree."""
    if pristine and os.path.realpath(tree) == os.path.realpath(pristine):
        results.append(("GUARD", "FAIL", "target tree IS the pristine read-only tree"))
        return False
    results.append(("GUARD", "PASS", "target tree is not the pristine tree"))
    return True


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def apply_all(tree, transport, apply):
    changes = []
    patch_001(tree, changes, apply)
    patch_002(tree, changes, apply)
    patch_003(tree, changes, apply)
    patch_004(tree, changes, apply)
    patch_005(tree, changes, apply)
    patch_006(tree, changes, apply, transport)
    patch_007(tree, changes, apply)
    patch_008(tree, changes, apply)
    install_overlay_files(tree, repo_root(), changes, apply)
    print("")
    print("{:<5} {:<42} {:>5}  {}".format("PATCH", "FILE", "N", "RESULT"))
    print("-" * 100)
    for pid, rel, n, what in changes:
        print("{:<5} {:<42} {:>5}  {}".format(pid, rel, n, what))
    return changes


def verify_all(tree, transport, pristine=None):
    results = []
    verify_pristine_untouched(tree, results, pristine)
    verify_manifest_parses(tree, results)
    verify_001(tree, results)
    verify_002(tree, results)
    verify_003(tree, results)
    verify_004(tree, results)
    verify_005(tree, results)
    verify_006(tree, results, transport)
    verify_007(tree, results)
    verify_008(tree, results)
    verify_overlay_files(tree, repo_root(), results)
    print("")
    print("{:<5} {:<6} {}".format("PATCH", "STATUS", "EVIDENCE"))
    print("-" * 100)
    for pid, status, what in results:
        print("{:<5} {:<6} {}".format(pid, status, what))
    failed = [r for r in results if r[1] == "FAIL"]
    print("")
    if failed:
        print("VERIFY: FAIL ({} check(s) failed)".format(len(failed)))
        return False
    print("VERIFY: OK ({} check(s) passed)".format(len(results)))
    return True


def stage(pristine, dest):
    """Copy ONLY the files the patches touch into an empty staging tree."""
    if os.path.exists(dest):
        shutil.rmtree(dest)
    staged = []
    for rel in TOUCHED_FILES + READONLY_FILES:
        src = os.path.join(pristine, rel)
        if not os.path.isfile(src):
            print("  STAGE MISS: {}".format(rel), file=sys.stderr)
            continue
        out = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copy2(src, out)
        staged.append(rel)
    # The avatar assertion also needs the .fst to exist beside it.
    fst_src = os.path.join(pristine, DEFAULT_AVATAR_REL)
    if os.path.isfile(fst_src):
        fst_out = os.path.join(dest, DEFAULT_AVATAR_REL)
        os.makedirs(os.path.dirname(fst_out), exist_ok=True)
        shutil.copy2(fst_src, fst_out)
        staged.append(DEFAULT_AVATAR_REL)
    return staged


def selftest(pristine, stage_dir, transport):
    print("== self-test ==")
    print("pristine : {}".format(pristine))
    print("stage    : {}".format(stage_dir))
    print("")
    print("staging only the files the patches touch (no full-tree copy) ...")
    staged = stage(pristine, stage_dir)
    for rel in staged:
        print("  staged  {}".format(rel))
    print("")

    print("-- pass 1: apply --")
    apply_all(stage_dir, transport, apply=True)
    first = {rel: _read(os.path.join(stage_dir, rel)) for rel in staged}
    ok1 = verify_all(stage_dir, transport)

    print("")
    print("-- pass 2: re-apply (idempotency) --")
    apply_all(stage_dir, transport, apply=True)
    second = {rel: _read(os.path.join(stage_dir, rel)) for rel in staged}
    idem = first == second
    print("")
    print("IDEMPOTENCY: {}".format("PASS (second apply changed nothing)" if idem
                                   else "FAIL (second apply mutated the tree)"))
    if not idem:
        for rel in staged:
            if first[rel] != second[rel]:
                print("  changed on re-apply: {}".format(rel), file=sys.stderr)

    print("")
    print("SELFTEST: {}".format("PASS" if (ok1 and idem) else "FAIL"))
    return 0 if (ok1 and idem) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Vircadia Android overlay patches")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--apply", metavar="TREE")
    g.add_argument("--verify", metavar="TREE")
    g.add_argument("--selftest", metavar="PRISTINE_TREE")
    g.add_argument("--dry-run", metavar="TREE",
                   help="report every change without writing anything")
    ap.add_argument("--stage-dir", default=None,
                    help="where --selftest stages the touched files")
    ap.add_argument("--transport", choices=("skip", "direct", "ipfs"), default="skip",
                    help="external asset transport for patch 006 (default: skip)")
    ap.add_argument("--pristine", default=None,
                    help="read-only pristine tree, used as a write guard")
    args = ap.parse_args(argv)

    try:
        if args.selftest:
            stage_dir = args.stage_dir or os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "selftest")
            return selftest(args.selftest, stage_dir, args.transport)
        if args.dry_run:
            print("== dry run (nothing will be written) ==")
            print("tree: {}".format(args.dry_run))
            apply_all(args.dry_run, args.transport, apply=False)
            print("")
            print("(dry run - no file was written)")
            return 0
        if args.apply:
            print("== apply ==")
            print("tree: {}".format(args.apply))
            apply_all(args.apply, args.transport, apply=True)
            return 0
        print("== verify ==")
        print("tree: {}".format(args.verify))
        return 0 if verify_all(args.verify, args.transport, args.pristine) else 1
    except PatchError as exc:
        print("", file=sys.stderr)
        print("PATCH ERROR: {}".format(exc), file=sys.stderr)
        print("Nothing further was applied. No silent fallback.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
