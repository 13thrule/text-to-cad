# Installed wheel follow-on validation — 2026-09-11

The final isolated wheel is complete and functional with the no-VTK dependency
route. This is a bounded correctness/package check, not a performance result.

## Provenance

- Final refresh HEAD: `9081de210e285b1e778079d602ec523cf72d2a1a`.
- Final wheel: `cadgen-0.5.1-py3-none-any.whl`, SHA-256
  `a26b518f75ca27708529c1d732e432e32b631b402115fbe8bb36904f1d28b8a9`.
- Built from a fresh private copy of `packages/cadgen` after removing only that
  copy's ignored `build/`, `src/cadgen.egg-info/`, and `__pycache__/`
  directories, then installed into `/private/tmp/cadgen-d1-install/venv` with
  `--force-reinstall --no-deps`. The final private source/build directory is
  `/private/tmp/cadgen-r5-final-wheel-xn94dihx/`.
  The repository's shared development environment was not used or modified.
- Python 3.13.13; `build123d` 0.11.1;
  `cadquery-ocp-novtk` 7.9.3.1.1. `pip check` passed. Wheel metadata records
  `build123d>=0.11.1` and `cadquery-ocp-novtk>=7.9,<8`.
  `cadquery-ocp`, `vtk`, and `matplotlib` were absent.

## Payload and imports

The wheel's 223 expected payload files matched the final package source and
bundled runtimes byte-for-byte: 191 Python/typing files, 2 internal Node
resolver files, 4 Node-runtime files, 3 browser-snapshot files, 22
Viewer-runtime files, and `viewer/collation.json`. There were zero missing,
extra, or changed files. Importing
`from cadgen import memo` from an empty `PYTHONPATH` left both `build123d`
and `OCP` unloaded.

The main reviewer independently compared all 223 archive payloads against both
the current source and the isolated installed files, with zero mismatches.
The [verification receipt](results/final-wheel-9081de210-20260911.json) records
the final wheel digest and dependency metadata.

The earlier post-bundle wheel's private Viewer served its index (SHA-256
`cb9c21060424c2f3446a09c22f22f19ceac1915d4842bb8be7d356258ed43afc`) and all
21 bundled `/assets/` files over an ephemeral localhost HTTP server. Every
served byte matched the corresponding installed runtime file. The temporary
Viewer was stopped after the check. The final refresh has the same index digest,
all 21 assets, and byte-matches the current 22-file Viewer runtime; R5 changed
the Python authoring return path, not those Viewer assets.

An initial private-copy build inherited ignored package build output and carried
16 superseded hashed Viewer assets. Rebuilding after deleting those private
cache directories produced the clean wheel above. This was a validation-build
cache artifact; no worktree source or bundle files were changed.

## Fresh-worker feature and saved-artifact checks

An isolated three-part fixture used an ordinary `python wheel_fixture.py
--force` invocation, so it followed the normal daemon handoff. It used an
isolated daemon/store with `CADGEN_JOBS=1`, `CADGEN_COMPONENT_WORKERS=1`, no
spares, and worker recycle after one job. The first fresh worker recorded three
feature misses; a second fresh worker reconstructed all three from the disk
cache (`3` hits, `0` misses); and `CADGEN_MEMO_CACHE=0` again recorded three
misses. The three saved STEP byte hashes were identical:

`02e9cc155ff5466daf142186ccd88f839f34e08339e3bf394dc8d1fb706fb654`.

The fixture source was then renamed and the private store's `index/model` and
`index/output` directories were removed. With no source `.py` available, the
installed wheel successfully:

- inspected the saved STEP from its document mapping (3 occurrences, 33 faces);
- exported a native STL (259,884 bytes; SHA-256
  `52a752aa80ef22ee8d0d38ba29eb3d3e917944a0cd6436d67dd5dd67ef61ffd3`);
- rendered a 320×240 PNG snapshot (20,662 bytes; SHA-256
  `1d0b8242c2cd913f2262b3578bcb10e609f2ede82289548a48592858ac409ef6`);
- launched a private API-only ephemeral Viewer. `/__cad/server`,
  `/__cad/catalog`, and the catalog's document-bound `/__cad/store` URL each
  returned HTTP 200. The STEP catalog entry exposed only artifact fields
  (`bytes`, `documentHash`, `file`, `hash`, `kind`, `rootRelativeFile`, `url`),
  with no source, record, or closure fields.

The private daemon and both private Viewer processes were stopped at the end of
the run. This source-free/native result is prior-checkpoint evidence for the
saved-artifact readers. The final R5 change is confined to the source-model
authoring return path; it has separate installed-wheel coverage below. Validation initially staged this fixture under
`/private/tmp/cadgen-final-wheel-S2wTNP/fixture/`; it was then moved intact to
`models/tmp/followon-wheel-20260911/` as the repository fixture/artifact area.
The STEP, STL, and PNG SHA-256 values above were verified unchanged after that
move. The initial private wheel, build logs, and isolated environment remain
under `/private/tmp/cadgen-final-wheel-S2wTNP/`; the earlier post-bundle rebuild and
payload comparison are under `/private/tmp/cadgen-final-wheel-refresh-2JEudZ/`,
for this session's audit only. The final R5 refresh is the `xn94dihx` directory
recorded above.

## Final R5 installed-wheel proof

The final wheel was reinstalled into the same isolated no-VTK environment with
`--force-reinstall --no-deps`; `pip check` passed. With an empty `PYTHONPATH`,
imports resolved to that environment's `site-packages/cadgen`, rather than the
worktree. A normal private daemon built the two-occurrence R5 fixture from
`models/tmp/r5-script-completion`: its bare top-level call completed the
declared STEP while a caller-only import guard observed no `build123d` or `OCP`
modules. The assigned-return control materialized the expected two solids and
960 mm³ volume and did load native modules. Only the proof's private daemon and
workers were stopped afterward.
