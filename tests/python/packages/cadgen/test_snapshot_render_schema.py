"""Photographic Render, technical output, and tessellation are closed schemas."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

from cadgen.snapshot_core import (  # noqa: E402
    MIN_RENDER_TESSELLATION,
    RENDER_BACKDROP_KEYS,
    RENDER_LIGHTING_KEYS,
    RENDER_QUALITY_IDS,
    RENDER_STUDIO_IDS,
    SUPPORTED_OUTPUT_SETTINGS_KEYS,
    SUPPORTED_QUALITY_KEYS,
    SUPPORTED_RENDER_KEYS,
    SnapshotError,
    normalize_common_job,
    validate_render_tessellation,
)


def normalize(**settings: object) -> dict[str, object]:
    return normalize_common_job(
        {"input": "part.step", "outputs": [{"path": "out.png"}], **settings},
        mode="view",
        resolved_cwd=Path("."),
        timestamp="20260907-000000",
    )


class RenderKeySchemaTest(unittest.TestCase):
    def test_every_supported_render_key_is_accepted(self):
        values = {
            "studio": "light",
            "quality": "final",
            "exposure": 0.5,
            "lighting": {"rotation": -30, "size": 1.5, "fill": 0.4},
            "backdrop": {"color": "#abc", "transparent": False, "ground": True},
            "camera": {"projection": "perspective", "focalLength": 70},
        }
        self.assertEqual(set(values), set(SUPPORTED_RENDER_KEYS))
        for key, value in values.items():
            normalize(render={key: value})

    def test_render_ids_are_closed_and_cli_defaults_to_light(self):
        self.assertEqual({"light", "dark"}, set(RENDER_STUDIO_IDS))
        self.assertEqual({"preview", "final"}, set(RENDER_QUALITY_IDS))
        self.assertEqual({"studio": "light"}, normalize(render={})["render"])
        for retired in (
            "studio-light", "studio-dark", "default", "cinematic", "vibrant",
            "blue", "pink", "colorful", "clay-sunrise", "terminal",
        ):
            with self.subTest(studio=retired), self.assertRaisesRegex(
                SnapshotError, "render.studio must be light or dark"
            ):
                normalize(render={"studio": retired})
        for invalid in (None, True, [], {}):
            with self.subTest(studio=invalid), self.assertRaisesRegex(
                SnapshotError, "render.studio must be light or dark"
            ):
                normalize(render={"studio": invalid})
        for retired in ("interactive", "standard", "high"):
            with self.subTest(quality=retired), self.assertRaisesRegex(
                SnapshotError, "render.quality must be preview or final"
            ):
                normalize(render={"quality": retired})
        for invalid in (None, False, [], {}):
            with self.subTest(quality=invalid), self.assertRaisesRegex(
                SnapshotError, "render.quality must be preview or final"
            ):
                normalize(render={"quality": invalid})

    def test_render_values_are_strict_and_sparse(self):
        render = {
            "studio": "dark",
            "quality": "preview",
            "exposure": -1.25,
            "lighting": {"rotation": 180, "size": 0.25, "fill": 1},
            "backdrop": {"color": "#123456", "transparent": True, "ground": False},
        }
        self.assertEqual(render, normalize(render=render)["render"])
        self.assertEqual({"rotation", "size", "fill"}, set(RENDER_LIGHTING_KEYS))
        self.assertEqual({"color", "transparent", "ground"}, set(RENDER_BACKDROP_KEYS))

        invalid = (
            {"exposure": True}, {"exposure": "0"}, {"exposure": -5.01}, {"exposure": 5.01},
            {"lighting": []}, {"lighting": {"rotation": float("inf")}},
            {"lighting": {"rotation": -180.01}}, {"lighting": {"size": 0.24}},
            {"lighting": {"size": 3.01}}, {"lighting": {"fill": -0.01}},
            {"lighting": {"fill": 1.01}}, {"lighting": {"fill": False}},
            {"lighting": {"key": 1}}, {"backdrop": []},
            {"backdrop": {"color": "white"}}, {"backdrop": {"transparent": 1}},
            {"backdrop": {"ground": "true"}}, {"backdrop": {"floor": True}},
        )
        for render_value in invalid:
            with self.subTest(render=render_value), self.assertRaises(SnapshotError):
                normalize(render=render_value)

    def test_render_camera_is_closed_and_display_is_not_a_render_field(self):
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
        for focal_length in (19.9, 200.1, True, "50", float("inf"), float("nan")):
            with self.subTest(focalLength=focal_length), self.assertRaisesRegex(
                SnapshotError, "focalLength must be a finite number between 20 and 200"
            ):
                normalize(render={"camera": {"focalLength": focal_length}})
        self.assertEqual(
            85,
            normalize(render={"camera": {"focalLength": 85}})["render"]["camera"]["focalLength"],
        )
        with self.assertRaisesRegex(SnapshotError, r"render has unknown key\(s\): display"):
            normalize(render={"display": {"mode": "shaded"}})

    def test_old_render_shapes_are_plain_unsupported_schema_errors(self):
        for key, value in {
            "settings": {}, "appearance": "dark", "tessellation": {},
            "sizeProfile": "diagnostic", "scale": "cad", "display": {}, "_comment": "old",
        }.items():
            with self.subTest(key=key), self.assertRaisesRegex(
                SnapshotError, rf"render has unknown key\(s\): {key}; supported keys:"
            ) as caught:
                normalize(render={key: value})
            self.assertNotIn("moved", str(caught.exception))
            self.assertNotIn("use ", str(caught.exception))

    def test_render_normalization_drops_top_level_cad_scene_state(self):
        job = normalize(
            render={"camera": {"preset": "front"}},
            camera={"preset": "back"},
            display={"mode": "wireframe"},
            selection={"focus": ["missing"]},
            kinematics={"hinge": 45},
            jointValues={"joint": 20},
            quality={"tessellation": {"chordTolerance": "ignored"}},
            animation={"clip": "spin", "time": 0.5},
        )
        self.assertEqual(job["render"]["camera"], {"preset": "front"})
        self.assertEqual(job["animation"], {"clip": "spin", "time": 0.5})
        for dormant in (
            "camera", "display", "selection", "kinematics", "jointValues", "quality",
        ):
            self.assertNotIn(dormant, job)

    def test_render_rejects_every_non_view_mode(self):
        for mode in ("section", "list"):
            with self.subTest(mode=mode), self.assertRaisesRegex(
                SnapshotError, "Photographic Render supports only view mode"
            ):
                normalize_common_job(
                    {
                        "input": "part.step",
                        "mode": mode,
                        "render": {},
                        "outputs": [] if mode == "list" else [{"path": "out.png"}],
                    },
                    mode=mode,
                    resolved_cwd=Path("."),
                    timestamp="20260907-000000",
                )

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
