# Cadgen dependency audit — September 11, 2026

## Decision

`cadgen` now directly requires `cadquery-ocp-novtk>=7.9,<8`, the same OCP
provider family and range required by `build123d 0.11.1`. The previous direct
`cadquery-ocp` requirement installed a second provider route whose only extra
native dependency is `vtk==9.6.2`; VTK then requires matplotlib. Cadgen imports
`build123d` and OCP, but source inspection found no production import of VTK or
CadQuery. Its optional native GLTF experiment is not production code; the clean
environment nevertheless imported `OCP.RWGltf.RWGltf_CafWriter` successfully.
The minimum build123d version is now 0.11.1, the audited version that declares
the no-VTK provider. Leaving it unconstrained would permit older build123d
requirements to reintroduce the full OCP provider alongside the direct no-VTK
requirement. This is a dependency floor, not a claim of testing older releases.

The native provider identity used for the persistent operation index and
descriptor-bounds key now resolves `cadquery-ocp-novtk`. Those keys include the
provider name, so a cache made with the former provider is not reused merely
because its OCP version matches. Surface producers obtain their binding version
through the same `op_memo._runtime_versions()` path. Existing `cadqueryOcp`
field spelling is retained as part of the surface-record schema.

The footprint reduction applies to fresh installations. Updating cadgen does
not uninstall an existing VTK or overlapping OCP distribution. Use a fresh
virtual environment to realize and verify the smaller dependency set; this
audit left the shared development environment unchanged.

## Isolated wheel validation

Using Python 3.13.13 on macOS arm64, a wheel built from this checkout was
installed into `/private/tmp/cadgen-d1-install/venv` with dependencies and no
repository path. It resolved `build123d 0.11.1`,
`cadquery-ocp-novtk 7.9.3.1.1`, and its `cadquery-ocp-proxy 7.9.3.1.1` helper.
`importlib.metadata.packages_distributions()["OCP"]` reported only
`["cadquery-ocp-novtk"]`; `cadquery-ocp`, `vtk`, and `matplotlib` were absent.
The installed copies of `_internal/op_memo.py` and
`store/_descriptor_bounds.py` byte-matched both the built wheel and source.

The bounded `models/tmp/cadgen-d1-dependency-audit-20260911/probe.py` box
fixture passed:

- native `BRepPrimAPI_MakeBox` construction and `RWGltf_CafWriter` import;
- decorated STEP plus declared STL/GLB output;
- `cadgen step inspect validate --skip-self-intersection` (one occurrence,
  zero failures), STEP re-export, and explicit STL/GLB exports;
- a 320 × 240 `cadgen step snapshot` using an isolated Playwright Chromium;
- an audit-owned `cadgen viewer --api-only --ephemeral --no-registry` instance,
  including its catalog and generated STEP store payload, then clean shutdown.

All generated CAD and image artifacts are under that `models/tmp` fixture; the
store, wheel, virtual environment, downloaded wheels, browser, and logs are in
`/private/tmp/cadgen-d1-install` or sibling `/private/tmp/cadgen-d1-*` paths.

## Platform artifacts and footprint

Published `cadquery-ocp-novtk 7.9.3.1.1` wheels were found for CPython 3.11,
3.12, and 3.13 on macOS 11 arm64, Windows amd64, and Linux
`manylinux_2_31_x86_64`. They were not published for `manylinux_2_17`,
`_2_24`, `_2_27`, or `_2_28` x86_64. This matches the provider's current
platform baseline; supported Linux environments need glibc 2.31 or later.

On the tested macOS target, the no-VTK provider archive plus its proxy was
62,299,251 bytes (59.41 MiB). Resolving the prior full provider's own archive
closure produced 193,033,764 bytes (184.09 MiB), including the 106,962,262-byte
VTK wheel and its matplotlib closure. These are download archives, not
installed files, and include shared packages in the latter closure.

The clean required cadgen dependency closure occupied 654,135,296 allocated
bytes (623.83 MiB), counted from installed `RECORD` paths with file inodes
deduplicated; it excludes pip/build tooling and the optional Playwright/browser.
The pre-change local measurement recorded in the plan was about 1.07 GiB for
cadgen's declared dependency roots, with VTK alone about 591 MiB under the same
allocated-file method. Different resolver dates make those two whole-closure
figures directional rather than a controlled byte-for-byte delta. The provider
archive comparison above is matched at 7.9.3.1.1.

Smaller download or installed footprint does not establish a startup, memory,
or CAD execution-speed improvement; this audit makes none of those claims.
