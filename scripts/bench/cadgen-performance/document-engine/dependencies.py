#!/usr/bin/env python3
"""Measure the installed CAD dependency closure, not the entire development venv.

This is a host observation. It cannot estimate another platform's wheel sizes
or infer the removable subset of a FreeCAD application installation.
"""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import stat
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def closure(root):
    root_requirement = Requirement(root)
    pending = [(canonicalize_name(root_requirement.name), root_requirement.extras)]
    distributions, visited = {}, {}
    missing = set()
    while pending:
        name, requested_extras = pending.pop()
        contexts = {"", *(canonicalize_name(extra) for extra in requested_extras)}
        new_contexts = contexts - visited.get(name, set())
        if not new_contexts or name in missing:
            continue
        if name not in distributions:
            try:
                distributions[name] = metadata.distribution(name)
            except metadata.PackageNotFoundError:
                missing.add(name)
                continue
        distribution = distributions[name]
        visited.setdefault(name, set()).update(new_contexts)
        for text in distribution.requires or ():
            requirement = Requirement(text)
            if requirement.marker is None or any(
                    requirement.marker.evaluate({"extra": extra}) for extra in new_contexts):
                pending.append((canonicalize_name(requirement.name), requirement.extras))
    rows, all_files = [], {}
    for name, distribution in sorted(distributions.items()):
        files = {}
        for relative in distribution.files or ():
            path = Path(distribution.locate_file(relative))
            try:
                info = path.stat()
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode):
                files[(info.st_dev, info.st_ino)] = info.st_size
        all_files.update(files)
        rows.append({"name": name, "version": distribution.version,
                     "recorded_file_bytes": sum(files.values()), "recorded_files": len(files)})
    return {"root": root, "distributions": rows, "missing": sorted(missing),
            "unique_recorded_file_bytes": sum(all_files.values()),
            "unique_recorded_files": len(all_files)}


def application(path):
    """Count installed regular files once; do not traverse linked trees."""
    files, symlinks = {}, 0
    for item in path.rglob("*"):
        try:
            info = item.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(info.st_mode):
            symlinks += 1
        elif stat.S_ISREG(info.st_mode):
            files[(info.st_dev, info.st_ino)] = info.st_size
    return {"path": str(path), "regular_file_bytes": sum(files.values()),
            "regular_files": len(files), "symlinks_not_followed": symlinks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="build123d")
    parser.add_argument("--freecad", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {"platform": platform.platform(), "machine": platform.machine(),
              "python": sys.version, "dependency_closure": closure(args.root),
              "measurement": "logical sizes of existing recorded regular files, deduplicated by inode",
              "limitations": ["Installed files are not compressed wheel/download sizes.",
                              "Distribution RECORD may omit editable source, caches or externally installed runtimes.",
                              "Shared dependency files are counted once; installed venv extras are excluded.",
                              "FreeCAD application size includes GUI, plugins and bundled runtime; it is not a minimal headless build.",
                              "This host does not establish Linux or Windows sizes."]}
    if args.freecad is not None:
        if not args.freecad.is_dir():
            parser.error("--freecad must identify an existing application directory")
        result["freecad_application"] = application(args.freecad.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output),
                      "dependency_bytes": result["dependency_closure"]["unique_recorded_file_bytes"],
                      "freecad_bytes": result.get("freecad_application", {}).get("regular_file_bytes"),
                      "missing": result["dependency_closure"]["missing"]}))


if __name__ == "__main__":
    main()
