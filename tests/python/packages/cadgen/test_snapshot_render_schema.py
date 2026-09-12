"""Snapshot scene, output and quality are separate closed schemas.

Two failure modes this pins, both of which used to be silent or opaque:

* old technical ``render`` keys fail with their new output/quality home;
* an absurd tolerance was accepted here and killed the browser later, so the
  caller saw `Connection closed while reading from the driver` and no cause.

The page validates the same field (packages/cadgen-js/src/common/source.js,
which also serves the viewer); this side refuses the job before a browser is
launched, so the floors have to agree — the parity test below reads the JS.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

from cadgen.snapshot_core import (  # noqa: E402
    MIN_RENDER_TESSELLATION,
    RENDER_STUDIO_IDS,
    SCENE_QUALITY_IDS,
    SUPPORTED_OUTPUT_SETTINGS_KEYS,
    SUPPORTED_QUALITY_KEYS,
    SUPPORTED_RENDER_KEYS,
    SnapshotError,
    normalize_common_job,
    validate_render_tessellation,
)


def normalize(**settings: object) -> dict[str, object]:
    return normalize_common_job(
        {"input": "part.step", "outputs": [], **settings},
        mode="list",
        resolved_cwd=Path("."),
        timestamp="20260907-000000",
    )


class RenderKeySchemaTest(unittest.TestCase):
    def test_every_supported_render_key_is_accepted(self):
        values = {
            "studio": "studio-light",
            "quality": "high",
            "settings": {"materials": {"roughness": 0.5}},
            "camera": {"projection": "perspective", "orthographicHalfHeight": 42.5},
            "display": {"mode": "shaded"},
        }
        self.assertEqual(set(values), set(SUPPORTED_RENDER_KEYS))
        for key, value in values.items():
            normalize(render={key: value})

    def test_scene_presets_are_closed_and_old_names_are_not_aliases(self):
        self.assertEqual(
            {"studio-light", "studio-dark"},
            set(RENDER_STUDIO_IDS),
        )
        self.assertEqual({}, normalize(render={})["render"])
        replacements = {
            "default": "omit studio to follow appearance",
            "cinematic": "studio-dark",
            "vibrant": "studio-light",
            "blue": "customize render.settings",
            "pink": "customize render.settings",
            "colorful": "customize render.settings",
            "clay-sunrise": "customize render.settings",
            "terminal": "customize render.settings",
            "snapshot": "expected one of",
            "workbench-light": "expected one of",
        }
        for retired, replacement in replacements.items():
            with self.subTest(studio=retired), self.assertRaisesRegex(
                SnapshotError, re.escape(replacement)
            ):
                normalize(render={"studio": retired})

    def test_render_appearance_is_removed_with_an_actionable_replacement(self):
        with self.assertRaisesRegex(
            SnapshotError,
            r"render\.appearance was removed; omit studio to follow appearance",
        ):
            normalize(render={"appearance": "dark"})

    def test_render_scene_values_are_strict_and_sparse_payload_is_preserved(self):
        render = {
            "studio": "studio-dark",
            "quality": "high",
            "settings": {
                "materials": {"roughness": 0.35, "overrideSourceColors": False},
                "lighting": {"directional": {"position": {"x": 3, "y": 4, "z": 5}}},
            },
        }
        self.assertEqual(render, normalize(render=render)["render"])
        self.assertEqual(
            {"studio": "studio-light", "quality": "high"},
            normalize(render={"studio": " STUDIO-LIGHT ", "quality": " HIGH "})["render"],
        )
        self.assertEqual(
            {"settings": {"environment": {"presetId": "studio-softbox"}}},
            normalize(render={
                "settings": {"environment": {"presetId": "studio-softbox"}},
            })["render"],
        )
        self.assertEqual({"interactive", "standard", "high"}, set(SCENE_QUALITY_IDS))

        invalid_settings = (
            {"materials": {"roughness": "0.35"}},
            {"materials": {"overrideSourceColors": 1}},
            {"materials": {"metalness": 1.1}},
            {"background": {"solidColor": "blue"}},
            {"environment": {"presetId": "unknown"}},
            {"lighting": {"directional": {"position": [1, 2, 3]}}},
            {"floor": {"grid": True}},
        )
        for settings in invalid_settings:
            with self.subTest(settings=settings), self.assertRaises(SnapshotError):
                normalize(render={"settings": settings})

    def test_render_camera_and_display_are_closed(self):
        with self.assertRaisesRegex(SnapshotError, "camera has unknown key"):
            normalize(render={"camera": {"projection": "perspective", "fov": 30}})
        with self.assertRaisesRegex(SnapshotError, "camera projection"):
            normalize(render={"camera": {"projection": "ortho"}})
        for half_height in (0, -1, True, "12", float("inf"), float("nan")):
            with self.subTest(orthographicHalfHeight=half_height), self.assertRaisesRegex(
                SnapshotError, "orthographicHalfHeight must be a positive finite number"
            ):
                normalize(render={"camera": {"orthographicHalfHeight": half_height}})
        self.assertEqual(
            18.25,
            normalize(render={"camera": {
                "projection": "perspective", "orthographicHalfHeight": 18.25,
            }})["render"]["camera"]["orthographicHalfHeight"],
        )
        with self.assertRaisesRegex(SnapshotError, "display mode .* retired"):
            normalize(render={"display": {"mode": "rendered"}})
        with self.assertRaisesRegex(SnapshotError, "display guides.grid has unknown key"):
            normalize(render={"display": {"guides": {"grid": {"visible": False}}}})
        for display in (
            {"clip": {"offset": "0.5"}},
            {"exploded": {"enabled": 1}},
            {"edges": {"thickness": 0}},
            {"guides": {"grid": {"density": 0.1}}},
            {"partColor": {"mode": "by_part", "colors": []}},
        ):
            with self.subTest(display=display), self.assertRaises(SnapshotError):
                normalize(render={"display": display})

    def test_old_technical_render_keys_name_their_new_home(self):
        with self.assertRaises(SnapshotError) as caught:
            normalize(render={"tessellation": {"chordTolerance": 0.001}})
        message = str(caught.exception)
        self.assertIn("quality.tessellation", message)
        with self.assertRaisesRegex(SnapshotError, "output.sizeProfile"):
            normalize(render={"sizeProfile": "diagnostic"})
        with self.assertRaisesRegex(SnapshotError, "render.scale moved to scale"):
            normalize(render={"scale": "cad"})

    def test_output_and_quality_are_closed(self):
        output = {
            "sizeProfile": "diagnostic", "padding": 0.1, "paddingPercent": 0.1,
            "viewLabels": True, "tightFrame": True, "transparent": True, "renderScale": 2,
        }
        self.assertEqual(set(output), set(SUPPORTED_OUTPUT_SETTINGS_KEYS))
        self.assertEqual({"tessellation"}, set(SUPPORTED_QUALITY_KEYS))
        normalize(output=output, quality={"tessellation": {"chordTolerance": 0.001}})
        with self.assertRaisesRegex(SnapshotError, "output has unknown key"):
            normalize(output={"pixels": 2})


class RenderTessellationLimitsTest(unittest.TestCase):
    def test_unknown_field_and_non_numbers_are_refused(self):
        for value in ({"quality": "high"}, {"chordTolerance": "0.001"}, {"chordTolerance": True}):
            with self.assertRaises(SnapshotError):
                validate_render_tessellation(value)
        with self.assertRaises(SnapshotError):
            validate_render_tessellation([0.001])

    def test_tolerances_below_the_floor_are_refused_here_not_in_the_browser(self):
        with self.assertRaises(SnapshotError) as caught:
            normalize(quality={"tessellation": {"chordTolerance": 1e-12}})
        self.assertIn("at least 1e-05", str(caught.exception))
        with self.assertRaises(SnapshotError):
            normalize(quality={"tessellation": {"angleTolerance": 1e-6}})
        # The floors themselves, and everything coarser, are legal requests.
        validate_render_tessellation(dict(MIN_RENDER_TESSELLATION))
        validate_render_tessellation({"chordTolerance": 0.0005, "angleTolerance": 0.10})
        validate_render_tessellation(None)

    def test_the_floors_match_the_page_that_tessellates(self):
        source = repo_path("packages/cadgen-js/src/common/source.js").read_text(encoding="utf-8")
        block = re.search(r"RENDER_TESSELLATION_FLOORS = Object\.freeze\(\{(.*?)\}\)", source, re.S)
        self.assertIsNotNone(block, "source.js no longer declares RENDER_TESSELLATION_FLOORS")
        declared = {
            key: float(value)
            for key, value in re.findall(r"(\w+):\s*([0-9.e-]+)", block.group(1))
        }
        self.assertEqual(declared, MIN_RENDER_TESSELLATION)


if __name__ == "__main__":
    unittest.main()
