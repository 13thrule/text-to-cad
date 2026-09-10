#!/usr/bin/env python3
"""Prepare an isolated planetary fixture or a source-free meshing input view."""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from common import REPO, model_path, sha256, write_json


def fixture(directory: Path) -> None:
    source = REPO / "models/assemblies/src/planetary_gear_assembly/planetary_gear_assembly.py"
    text = source.read_text()
    before = '''@step(out="../../STEP/planetary_gear_assembly/planetary_gear_assembly.step", kinematics=_planetary_kinematics())
@stl(out="../../STL/planetary_gear_assembly/planetary_gear_assembly.stl")
@threemf(out="../../3MF/planetary_gear_assembly/planetary_gear_assembly.3mf")
@glb(out="../../GLB/planetary_gear_assembly/planetary_gear_assembly.glb")'''
    if text.count(before) != 1:
        raise ValueError("Planetary fixture decorators changed; review the benchmark workload before updating this preparation step")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / source.name
    with target.open("x") as handle:
        handle.write(text.replace(before, '@step(out="planetary.step")'))
    print(target)


def view(model: Path, store: Path, directory: Path) -> None:
    os.environ["CADGEN_CACHE_DIR"] = str(store)
    from cadgen.store.objects import object_path
    from cadgen.store.records import read_record
    from cadgen.store.trees import flatten

    record = read_record(model) or {}
    descriptor = flatten(record["tree"]) if record.get("tree") else None
    if descriptor is None:
        raise ValueError("Build the fixture into the supplied store before preparing its view")
    # Read every immutable input before making the new view. This path never
    # imports model source, CAD geometry, or STEP text and never changes a store.
    assets = []
    for cid, component in descriptor["components"].items():
        for suffix in ("surf", "brep"):
            digest = component[suffix]
            payload = object_path(digest).read_bytes()
            if sha256(payload) != digest:
                raise ValueError(f"Corrupt {suffix} object for component {cid}")
            assets.append((cid, suffix, payload))
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "components").mkdir()
    for cid, suffix, payload in assets:
        (directory / "components" / f"{cid}.{suffix}").write_bytes(payload)
    write_json(directory / "assembly.json", descriptor)
    print(directory)


def split_fixture(directory: Path) -> None:
    """Copy only the authored split fixture; generated files stay in the copy."""
    source = REPO / "models/examples/performance/planetary_split"
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source / "src", directory / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(source / "README.md", directory / "README.md")
    print(directory / "src/planetary_gear_assembly.py")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="action", required=True)
    setup = subcommands.add_parser("fixture", help="Copy the repository fixture with only a local STEP output")
    setup.add_argument("--directory", required=True, type=model_path)
    split = subcommands.add_parser("split-fixture", help="Copy the same geometry as a root and nine decorated children")
    split.add_argument("--directory", required=True, type=model_path)
    export = subcommands.add_parser("view", help="Copy BREP/SURF inputs from a completed store tree")
    export.add_argument("--directory", required=True, type=model_path)
    export.add_argument("--model", required=True, type=model_path)
    export.add_argument("--store", required=True, type=model_path)
    args = parser.parse_args()
    if args.action == "fixture":
        fixture(args.directory)
    elif args.action == "split-fixture":
        split_fixture(args.directory)
    else:
        view(args.model, args.store, args.directory)


if __name__ == "__main__":
    main()
