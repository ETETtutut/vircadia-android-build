#!/usr/bin/env python3
"""
validate_assets.py - static asset validation for the Vircadia Android build.

Standard library only. NO network access. Read-only: never writes into the
trees it inspects (a JSON report goes to --report, default under the work repo).

Checks
  1. The default full-avatar .fst exists and every file it references
     (its `filename = ...` model) resolves to a real file.
  2. Every animation graph JSON under interface/resources/avatar/animations/
     has its `url` references resolve to real files beneath that directory.
  3. The mandatory serverless world files exist.
  4. Reports a count of animation files found and compares it to the expected
     count (127 in the pinned core revision).

Exit status
  0  every check passed
  1  at least one asset is missing
  2  usage / tree error

Usage
  python3 -I validate_assets.py --core <CORE> [--expect-animations 127]
                                [--report <path>] [--quiet]
"""

import argparse
import json
import os
import re
import sys

ANIMATIONS_REL = "interface/resources/avatar/animations"
MESHES_REL = "interface/resources/meshes"
DEFAULT_FST_REL = "interface/resources/meshes/defaultAvatar_full.fst"
DEFAULT_FBX_REL = "interface/resources/meshes/mannequin/mannequin.baked.fbx"
SERVERLESS_REL = "interface/resources/serverless"
SERVERLESS_REQUIRED = ["tutorial.json"]

URL_IN_JSON = re.compile(r'"(?:url|modelURL|animationURL|textures|materialURL|skybox|sound)"\s*:\s*"([^"]+)"')
FST_FILENAME = re.compile(r'^\s*filename\s*=\s*(.+?)\s*$', re.MULTILINE)


def walk(root, exts):
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in exts:
                yield os.path.join(dirpath, fn)


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        return {"__parse_error__": str(exc)}


def collect_urls(node, out):
    """Recursively collect every string value under a URL-ish key."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and key.lower() in (
                    "url", "modelurl", "animationurl", "textures", "materialurl",
                    "skybox", "sound", "script", "serverscripts", "compoundshapeurl",
                    "particle", "userdata"):
                out.append((key, value))
            else:
                collect_urls(value, out)
    elif isinstance(node, list):
        for item in node:
            collect_urls(item, out)


def check_avatar(core, missing, notes):
    fst = os.path.join(core, DEFAULT_FST_REL)
    if not os.path.isfile(fst):
        missing.append({"kind": "avatar", "what": DEFAULT_FST_REL, "why": "default .fst not found"})
        return
    with open(fst, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    notes.append("avatar: {} ({} bytes)".format(DEFAULT_FST_REL, os.path.getsize(fst)))

    target = None
    m = FST_FILENAME.search(text)
    if m:
        target = m.group(1).strip().strip('"')
        model = os.path.normpath(os.path.join(os.path.dirname(fst), target))
        if os.path.isfile(model):
            notes.append("avatar: model {} resolves ({} bytes)".format(
                target, os.path.getsize(model)))
        else:
            missing.append({"kind": "avatar", "what": target,
                            "why": "filename referenced by the .fst does not exist"})
    else:
        notes.append("avatar: .fst has no `filename =` line (nothing to resolve)")

    fbx = os.path.join(core, DEFAULT_FBX_REL)
    if os.path.isfile(fbx):
        notes.append("avatar: {} present ({} bytes)".format(
            DEFAULT_FBX_REL, os.path.getsize(fbx)))
    else:
        missing.append({"kind": "avatar", "what": DEFAULT_FBX_REL, "why": "baked mannequin FBX missing"})


def check_animations(core, missing, notes, expect_animations):
    root = os.path.join(core, ANIMATIONS_REL)
    if not os.path.isdir(root):
        missing.append({"kind": "animations", "what": ANIMATIONS_REL,
                        "why": "animation directory not found"})
        return 0
    files = sorted(walk(root, {".fbx", ".json", ".glb"}))
    clips = [f for f in files if os.path.splitext(f)[1].lower() != ".json"]
    notes.append("animations: {} file(s) under {} ({} clip file(s), {} graph(s))".format(
        len(files), ANIMATIONS_REL, len(clips), len(files) - len(clips)))

    if expect_animations and len(clips) != expect_animations:
        notes.append("animations: NOTE expected {} clip files, found {} - "
                     "core revision may differ".format(expect_animations, len(clips)))

    graphs = [f for f in files if f.lower().endswith(".json")]
    for graph in graphs:
        data = load_json(graph)
        if "__parse_error__" in data:
            notes.append("animations: {} is not valid JSON ({})".format(
                os.path.relpath(graph, core), data["__parse_error__"]))
            continue
        refs = []
        collect_urls(data, refs)
        for key, value in refs:
            if value.startswith(("http://", "https://", "file://", "data:")):
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(graph), value))
            if not os.path.isfile(resolved):
                missing.append({"kind": "animation", "graph": os.path.relpath(graph, core),
                                "key": key, "what": value,
                                "why": "referenced file does not exist"})
    return len(clips)


def check_serverless(core, missing, notes):
    for rel in SERVERLESS_REQUIRED:
        path = os.path.join(core, SERVERLESS_REL, rel)
        if os.path.isfile(path):
            notes.append("world: {}/{} present ({} bytes)".format(
                SERVERLESS_REL, rel, os.path.getsize(path)))
        else:
            missing.append({"kind": "world", "what": "{}/{}".format(SERVERLESS_REL, rel),
                            "why": "mandatory serverless world file missing"})


def main(argv=None):
    ap = argparse.ArgumentParser(description="static Vircadia asset validation")
    ap.add_argument("--core", required=True, help="path to the CORE tree (read-only)")
    ap.add_argument("--expect-animations", type=int, default=127)
    ap.add_argument("--report", default=None, help="write the JSON report here")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.core):
        print("core tree not found: {}".format(args.core), file=sys.stderr)
        return 2

    missing, notes = [], []
    check_avatar(args.core, missing, notes)
    clips = check_animations(args.core, missing, notes, args.expect_animations)
    check_serverless(args.core, missing, notes)

    report = {
        "core": args.core,
        "animation_clip_files": clips,
        "expected_animation_clip_files": args.expect_animations,
        "missing": missing,
        "notes": notes,
        "status": "FAIL" if missing else "PASS",
    }
    if args.report:
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")

    if not args.quiet:
        for note in notes:
            print("  {}".format(note))
        if missing:
            print("")
            print("MISSING ({}):".format(len(missing)))
            for item in missing:
                print("  - {}/{}: {}".format(item["kind"], item.get("what"), item["why"]))
    print("")
    print("validate_assets: {} ({} missing)".format(report["status"], len(missing)))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
