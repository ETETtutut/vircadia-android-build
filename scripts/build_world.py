#!/usr/bin/env python3
"""
build_world.py - turn the Daybreak world from the CONTENT tree into a
self-contained, file://-addressable world pack for the Android client.

Standard library only. NO network access.

What it does
  1. Finds the world JSON inside CONTENT/Bazaar/Worlds/Daybreak/ (by structure,
     not by an assumed filename).
  2. Walks every string in it that holds an http(s) URL - modelURL, animation
     urls, script, serverScripts, textures, materialURL, compoundShapeURL,
     skybox, sound, particle, userData.
  3. Resolves each one to a real file in the CONTENT tree: first by
     CONTENT-relative path suffix, then by unique basename.
  4. Rewrites the resolved ones to file://@WORLD_ROOT@/<content-relative-path>
     and leaves the unresolved ones exactly as they were.
  5. Writes the world JSON, the list of CONTENT paths CI must fetch, and a
     machine-readable map report.

@WORLD_ROOT@ is substituted at runtime by the Android WorldInstaller with the
app's private files directory. The path structure below it mirrors CONTENT, so
one substitution covers every reference.

Modes
  local (default)  JSON only. Copies no large binaries. Safe on a phone/laptop.
  ci               additionally copies ONLY the referenced files into
                   <assets-dir>, preserving their CONTENT-relative paths, so
                   they ship inside the APK.

Usage
  python3 -I build_world.py --content <CONTENT> --repo <work-repo>
                            [--world Bazaar/Worlds/Daybreak] [--mode local|ci]
                            [--assets-dir <dir>]
"""

import argparse
import json
import os
import re
import shutil
import sys

WORLD_ROOT_TOKEN = "@WORLD_ROOT@"
HTTP_URL = re.compile(r'^https?://', re.IGNORECASE)

# Earlier inspection of this world reported these. They are printed as a
# comparison, never as an assertion - a different core/content revision gives
# different numbers and that is information, not an error.
EXPECTED = {"entities": 319, "unique_urls": 46, "resolved": 37, "unresolved": 9}


def content_index(content_root):
    """Map every file in CONTENT by relative path and by basename."""
    by_rel, by_base = {}, {}
    for dirpath, _dirnames, filenames in os.walk(content_root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, content_root).replace(os.sep, "/")
            by_rel[rel] = full
            by_base.setdefault(fn.lower(), []).append((rel, full))
    return by_rel, by_base


def find_world_json(world_dir):
    """Pick the world description: the JSON holding an Entities array, else the
    largest JSON in the directory."""
    candidates = []
    for dirpath, _dirnames, filenames in os.walk(world_dir):
        for fn in filenames:
            if fn.lower().endswith(".json"):
                candidates.append(os.path.join(dirpath, fn))
    if not candidates:
        return None, []
    scored = []
    for path in candidates:
        has_entities, size = False, 0
        try:
            size = os.path.getsize(path)
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                has_entities = '"Entities"' in fh.read()
        except OSError:
            continue
        scored.append((has_entities, size, path))
    scored.sort(key=lambda t: (not t[0], -t[1]))
    return scored[0][2], [c for c in candidates]


def walk_strings(node, path=()):
    """Yield (json_path, key, string_value) for every string in the document."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str):
                yield path + (key,), key, value
            else:
                yield from walk_strings(value, path + (key,))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            if isinstance(item, str):
                yield path + (i,), None, item
            else:
                yield from walk_strings(item, path + (i,))


def set_at(document, path, value):
    cursor = document
    for step in path[:-1]:
        cursor = cursor[step]
    cursor[path[-1]] = value


def resolve(url, by_rel, by_base):
    """Resolve an http(s) URL to (content_relative_path, full_path) or None."""
    clean = url.split("?", 1)[0].split("#", 1)[0]
    parts = [p for p in clean.split("/") if p not in ("", "http:", "https:")]
    if not parts:
        return None
    # Longest suffix of the URL path that names a real CONTENT file wins.
    for start in range(len(parts)):
        candidate = "/".join(parts[start:])
        if candidate in by_rel:
            return candidate, by_rel[candidate]
    # Then a unique basename match.
    base = parts[-1].lower()
    hits = by_base.get(base, [])
    if len(hits) == 1:
        return hits[0]
    return None


def count_entities(document):
    entities = document.get("Entities")
    if isinstance(entities, list):
        return len(entities)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="build the Daybreak world pack")
    ap.add_argument("--content", required=True, help="CONTENT tree (read-only)")
    ap.add_argument("--repo", required=True, help="work repo root (overlay)")
    ap.add_argument("--world", default="Bazaar/Worlds/Daybreak")
    ap.add_argument("--mode", choices=("local", "ci"), default="local")
    ap.add_argument("--assets-dir", default=None,
                    help="CI: where to copy referenced files (default <repo>/world/assets)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    world_dir = os.path.join(args.content, args.world)
    if not os.path.isdir(world_dir):
        print("world directory not found: {}".format(world_dir), file=sys.stderr)
        return 2

    world_json, all_json = find_world_json(world_dir)
    if not world_json:
        print("no world JSON found under {}".format(world_dir), file=sys.stderr)
        return 2
    if not args.quiet:
        print("world dir   : {}".format(world_dir))
        print("world json  : {}".format(os.path.relpath(world_json, args.content)))
        print("other json  : {}".format(
            [os.path.relpath(p, args.content) for p in all_json if p != world_json]))
        print("mode        : {}".format(args.mode))
        print("")

    with open(world_json, "r", encoding="utf-8", errors="replace") as fh:
        document = json.load(fh)

    by_rel, by_base = content_index(args.content)

    resolved, unresolved, touched = {}, [], []
    seen_urls = set()
    for json_path, key, value in list(walk_strings(document)):
        if not HTTP_URL.match(value):
            continue
        seen_urls.add(value)
        hit = resolve(value, by_rel, by_base)
        if hit is None:
            unresolved.append({"json_path": list(json_path), "url": value})
            continue
        rel, full = hit
        target = "file://{}/{}".format(WORLD_ROOT_TOKEN, rel)
        set_at(document, json_path, target)
        resolved[value] = rel
        touched.append(rel)

    touched = sorted(set(touched))

    # --- outputs -------------------------------------------------------------
    world_out = os.path.join(args.repo, "world", "daybreak.json")
    os.makedirs(os.path.dirname(world_out), exist_ok=True)
    with open(world_out, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2)
        fh.write("\n")

    paths_out = os.path.join(args.repo, "world", "needed-content-paths.txt")
    with open(paths_out, "w", encoding="utf-8") as fh:
        for rel in touched:
            fh.write("{}\n".format(rel))

    map_out = os.path.join(args.repo, "reports", "world-asset-map.json")
    os.makedirs(os.path.dirname(map_out), exist_ok=True)
    entities = count_entities(document)
    report = {
        "content": args.content,
        "world": args.world,
        "world_json": os.path.relpath(world_json, args.content),
        "entities": entities,
        "unique_urls": len(seen_urls),
        "resolved_count": len(resolved),
        "unresolved_count": len(unresolved),
        "resolved": resolved,
        "unresolved": unresolved,
        "needed_content_paths": touched,
        "expected": EXPECTED,
    }
    with open(map_out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")

    # --- optional CI copy ----------------------------------------------------
    copied = 0
    if args.mode == "ci":
        assets_dir = args.assets_dir or os.path.join(args.repo, "world", "assets")
        for rel in touched:
            src = by_rel[rel]
            dst = os.path.join(assets_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1

    # --- summary -------------------------------------------------------------
    if not args.quiet:
        print("entities    : {} (expected {})".format(entities, EXPECTED["entities"]))
        print("unique urls : {} (expected {})".format(len(seen_urls), EXPECTED["unique_urls"]))
        print("resolved    : {} (expected {})".format(len(resolved), EXPECTED["resolved"]))
        print("unresolved  : {} (expected {})".format(len(unresolved), EXPECTED["unresolved"]))
        if args.mode == "ci":
            print("copied      : {} file(s) into {}".format(copied, assets_dir))
        print("")
        print("wrote : {}".format(os.path.relpath(world_out, args.repo)))
        print("wrote : {}".format(os.path.relpath(paths_out, args.repo)))
        print("wrote : {}".format(os.path.relpath(map_out, args.repo)))
        if unresolved:
            print("")
            print("still remote ({} - left untouched):".format(len(unresolved)))
            for item in unresolved[:20]:
                print("  - {}".format(item["url"]))
            if len(unresolved) > 20:
                print("  ... and {} more (see the map report)".format(len(unresolved) - 20))

    for label, got in (("entities", entities), ("unique_urls", len(seen_urls)),
                       ("resolved", len(resolved)), ("unresolved", len(unresolved))):
        if got != EXPECTED[label]:
            print("NOTE: {} is {} but the earlier inspection reported {}".format(
                label, got, EXPECTED[label]), file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
