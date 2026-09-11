"""Python snapshots accept exactly the shared scene/camera/display vocabulary."""

from __future__ import annotations

import json
import re
import subprocess
import unittest

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

from cadgen.snapshot_core import (  # noqa: E402
    CAMERA_OPTION_KEYS,
    DISPLAY_AXIS_GUIDE_KEYS,
    DISPLAY_CLIP_KEYS,
    DISPLAY_EDGE_CLASS_IDS,
    DISPLAY_EDGE_CLASS_KEYS,
    DISPLAY_EDGE_KEYS,
    DISPLAY_EXPLODED_KEYS,
    DISPLAY_GRID_GUIDE_KEYS,
    DISPLAY_GUIDE_KEYS,
    DISPLAY_MODES,
    DISPLAY_OPTION_KEYS,
    DISPLAY_PART_COLOR_KEYS,
    PART_COLOR_MODES,
    RENDER_LIGHT_KEYS,
    RENDER_SETTING_BLOCK_KEYS,
    RENDER_STUDIO_IDS,
    SCENE_QUALITY_IDS,
    SUPPORTED_RENDER_KEYS,
    SUPPORTED_RENDER_SETTINGS_KEYS,
    SnapshotError,
    validate_camera_option,
)

SCENE = repo_path("packages/cadgen-js/src/common/sceneSettings.js")
CAMERA = repo_path("packages/cadgen-js/src/common/camera.js")
DISPLAY = repo_path("packages/cadgen-js/src/common/displaySettings.js")


def exported_strings(path, export: str) -> set[str]:
    source = path.read_text(encoding="utf-8")
    match = re.search(
        rf"export const {re.escape(export)}\s*=\s*Object\.freeze\(\[(.*?)\]\);",
        source,
        re.S,
    )
    assert match, f"{path.name} no longer exports {export} as a frozen array"
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def frozen_enum_values(path, export: str, next_export: str) -> set[str]:
    source = path.read_text(encoding="utf-8")
    start = source.index(f"export const {export} =")
    end = source.index(f"export const {next_export}", start)
    return set(re.findall(r':\s*"([^"]+)"', source[start:end]))


class SharedSceneContractParityTests(unittest.TestCase):
    def test_render_envelope_keys_match(self):
        self.assertEqual(exported_strings(SCENE, "RENDER_PAYLOAD_KEYS"), set(SUPPORTED_RENDER_KEYS))

    def test_render_settings_keys_match(self):
        self.assertEqual(
            exported_strings(SCENE, "RENDER_SETTINGS_KEYS"),
            set(SUPPORTED_RENDER_SETTINGS_KEYS),
        )

    def test_studio_ids_match(self):
        self.assertEqual(
            frozen_enum_values(SCENE, "RENDER_STUDIO", "RENDER_STUDIO_PRESETS"),
            set(RENDER_STUDIO_IDS),
        )

    def test_scene_quality_ids_match(self):
        self.assertEqual(
            frozen_enum_values(SCENE, "SCENE_QUALITY", "SCENE_QUALITY_PRESETS"),
            set(SCENE_QUALITY_IDS),
        )

    def test_nested_render_setting_keys_match(self):
        source = SCENE.read_text(encoding="utf-8")
        start = source.index("const STUDIO_SETTING_BLOCK_KEYS =")
        end = source.index("const LIGHT_KEYS =", start)
        block = source[start:end]
        for name, expected in RENDER_SETTING_BLOCK_KEYS.items():
            match = re.search(rf"{name}: Object\.freeze\(\[(.*?)\]\)", block, re.S)
            self.assertIsNotNone(match, f"sceneSettings.js no longer declares {name} setting keys")
            self.assertEqual(set(re.findall(r'"([^"]+)"', match.group(1))), set(expected))

        light_start = source.index("const LIGHT_KEYS =")
        light_end = source.index("const EXPLICIT_PBR_MATERIAL_KEYS", light_start)
        light_block = source[light_start:light_end]
        for name, expected in RENDER_LIGHT_KEYS.items():
            match = re.search(rf"{name}: Object\.freeze\(\[(.*?)\]\)", light_block, re.S)
            self.assertIsNotNone(match, f"sceneSettings.js no longer declares {name} light keys")
            self.assertEqual(set(re.findall(r'"([^"]+)"', match.group(1))), set(expected))

    def test_camera_keys_match(self):
        self.assertEqual(exported_strings(CAMERA, "CAMERA_SPEC_KEYS"), set(CAMERA_OPTION_KEYS))

    def test_malformed_camera_numbers_fail_in_python_and_shared_js(self):
        malformed = [
            {"position": [1, 2, "3"]},
            {"target": [1, 2, True]},
            {"up": None},
            {"direction": [1, 2, 3, 4]},
            {"zoom": "2"},
            {"zoom": True},
            {"zoom": None},
            {"orthographicHalfHeight": "12"},
            {"orthographicHalfHeight": False},
            {"orthographicHalfHeight": None},
        ]
        script = f"""
import fs from "node:fs";
import {{ normalizeCameraSpec }} from {json.dumps(CAMERA.as_uri())};
const cases = JSON.parse(fs.readFileSync(0, "utf8"));
console.log(JSON.stringify(cases.map((camera) => {{
  try {{ normalizeCameraSpec(camera, {{ strict: true }}); return true; }}
  catch {{ return false; }}
}})));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            input=json.dumps(malformed),
            text=True,
            capture_output=True,
            check=True,
            cwd=repo_path(),
        )
        js_accepted = json.loads(completed.stdout)
        python_accepted = []
        for camera in malformed:
            try:
                validate_camera_option(camera, source_label="parity test")
            except SnapshotError:
                python_accepted.append(False)
            else:
                python_accepted.append(True)
        self.assertEqual(js_accepted, python_accepted)
        self.assertEqual([False] * len(malformed), python_accepted)

    def test_display_keys_match(self):
        self.assertEqual(exported_strings(DISPLAY, "DISPLAY_SETTINGS_KEYS"), set(DISPLAY_OPTION_KEYS))

    def test_display_modes_match(self):
        self.assertEqual(
            frozen_enum_values(DISPLAY, "CAD_DISPLAY_MODE", "CAD_DISPLAY_MODE_VALUES"),
            set(DISPLAY_MODES),
        )
        self.assertEqual(
            frozen_enum_values(DISPLAY, "CAD_PART_COLOR_MODE", "CAD_PART_COLOR_MODE_VALUES"),
            set(PART_COLOR_MODES),
        )

    def test_nested_display_keys_match(self):
        pairs = {
            "DISPLAY_EDGE_SETTINGS_KEYS": DISPLAY_EDGE_KEYS,
            "DISPLAY_EDGE_CLASS_SETTINGS_KEYS": DISPLAY_EDGE_CLASS_KEYS,
            "DISPLAY_GUIDE_SETTINGS_KEYS": DISPLAY_GUIDE_KEYS,
            "DISPLAY_GRID_GUIDE_SETTINGS_KEYS": DISPLAY_GRID_GUIDE_KEYS,
            "DISPLAY_AXIS_GUIDE_SETTINGS_KEYS": DISPLAY_AXIS_GUIDE_KEYS,
            "DISPLAY_PART_COLOR_SETTINGS_KEYS": DISPLAY_PART_COLOR_KEYS,
            "DISPLAY_EXPLODED_SETTINGS_KEYS": DISPLAY_EXPLODED_KEYS,
            "DISPLAY_CLIP_SETTINGS_KEYS": DISPLAY_CLIP_KEYS,
        }
        for exported, expected in pairs.items():
            with self.subTest(export=exported):
                self.assertEqual(exported_strings(DISPLAY, exported), set(expected))
        self.assertEqual(exported_strings(DISPLAY, "CAD_EDGE_CLASS_IDS"), set(DISPLAY_EDGE_CLASS_IDS))


if __name__ == "__main__":
    unittest.main()
