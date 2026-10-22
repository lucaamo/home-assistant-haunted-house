"""Offline regression checks for the package's control-flow safeguards.

The basic checks use only the Python standard library and inspect the action
graph. If the pinned HA development dependency is installed, additional tests
render the real HA templates against fictional, in-memory states. No test starts
HA, loads integrations, calls services, or contacts a running installation.
See tools/validate_ha.py for validation against the real HA schemas.
"""

from __future__ import annotations

from pathlib import Path
from importlib.metadata import PackageNotFoundError, version
import json
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = runpy.run_path(str(ROOT / "tools" / "build.py"), run_name="haunted_test_builder")
PACKAGE = BUILDER["PACKAGE"]
SCRIPTS = PACKAGE["script"]
ENGINE = SCRIPTS["haunted_house_effect"]["sequence"]
LIGHTS = SCRIPTS["haunted_house_light_effect"]["sequence"]
BLUEPRINT = (ROOT / "blueprints/automation/haunted_house/room.yaml").read_text()
try:
    HAS_PINNED_HA = sys.version_info >= (3, 14) and version("homeassistant") == "2026.10.2"
except PackageNotFoundError:
    HAS_PINNED_HA = False


def nodes(value):
    """Yield action/config dictionaries recursively, including parallel branches."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def actions(value, name=None):
    return [node for node in nodes(value)
            if "action" in node and (name is None or node["action"] == name)]


def sequence_index(sequence, service):
    return next(index for index, step in enumerate(sequence)
                if step.get("action") == service)


def assert_no_aborting_gates(test, sequence):
    """A standalone condition would abort cleanup; if/choose conditions do not."""
    for step in sequence:
        test.assertNotIn("condition", step, "standalone gate can bypass snapshot restore")
        test.assertNotIn("stop", step, "early stop can bypass snapshot restore")
        if "repeat" in step:
            assert_no_aborting_gates(test, step["repeat"]["sequence"])
        if "parallel" in step:
            for branch in step["parallel"]:
                assert_no_aborting_gates(test, branch["sequence"])
        if "if" in step:
            assert_no_aborting_gates(test, step.get("then", []))
            assert_no_aborting_gates(test, step.get("else", []))
        if "choose" in step:
            for branch in step["choose"]:
                assert_no_aborting_gates(test, branch["sequence"])
            assert_no_aborting_gates(test, step.get("default", []))


class PreviewTests(unittest.TestCase):
    def test_preview_exits_before_any_action_or_wait(self):
        for name, sequence in (("controller", ENGINE), ("lights", LIGHTS)):
            with self.subTest(script=name):
                preview_index = next(i for i, step in enumerate(sequence)
                                     if step.get("if", [{}])[0].get("value_template") == "{{ preview }}")
                earlier = list(nodes(sequence[:preview_index]))
                self.assertFalse(any("action" in node or "wait_template" in node or "delay" in node
                                     for node in earlier))
                preview = sequence[preview_index]["then"]
                self.assertFalse(actions(preview))
                self.assertEqual(preview[0]["variables"]["result"]["status"], "preview")
                self.assertEqual(preview[-1]["response_variable"], "result")
                self.assertIn("stop", preview[-1])

    def test_preview_defaults_are_safe_for_direct_script_calls(self):
        for variables in (BUILDER["engine_vars"], BUILDER["light_vars"]):
            self.assertIn("default(true)", variables["preview"])
        self.assertTrue(SCRIPTS["haunted_house_effect"]["fields"]["preview"]["default"])


class InitializationTests(unittest.TestCase):
    def test_user_settings_have_no_forced_restart_values(self):
        for domain, definitions in PACKAGE.items():
            if domain.startswith("input_"):
                for entity_id, definition in definitions.items():
                    with self.subTest(entity=entity_id):
                        self.assertNotIn("initial", definition)

    def test_defaults_disarm_first_and_commit_initialized_last(self):
        sequence = SCRIPTS["haunted_house_reset_defaults"]["sequence"]
        self.assertEqual(sequence[0]["action"], "input_boolean.turn_off")
        self.assertEqual(sequence[0]["target"]["entity_id"], "input_boolean.haunted_house_enabled")
        self.assertEqual(sequence[-1]["action"], "input_boolean.turn_on")
        self.assertEqual(sequence[-1]["target"]["entity_id"], "input_boolean.haunted_house_initialized")
        self.assertFalse(any(step.get("action") == "input_boolean.turn_on"
                             and step.get("target", {}).get("entity_id") == "input_boolean.haunted_house_enabled"
                             for step in sequence))

    def test_startup_initialization_only_when_marker_is_off(self):
        automation = next(item for item in PACKAGE["automation"]
                          if item["id"] == "haunted_house_initialize")
        self.assertEqual(automation["conditions"], [{
            "condition": "state", "entity_id": "input_boolean.haunted_house_initialized", "state": "off",
        }])
        self.assertEqual(automation["actions"][0]["action"], "script.haunted_house_reset_defaults")


class CleanupTests(unittest.TestCase):
    def test_light_snapshot_precedes_all_light_changes(self):
        snapshot_index = sequence_index(LIGHTS, "scene.create")
        self.assertFalse(actions(LIGHTS[:snapshot_index], "light.turn_on"))
        self.assertNotIn("continue_on_error", LIGHTS[snapshot_index],
                         "a failed snapshot must abort before changing lights")

    def test_light_restore_cannot_be_bypassed_by_a_late_gate(self):
        snapshot_index = sequence_index(LIGHTS, "scene.create")
        restore_index = sequence_index(LIGHTS, "scene.turn_on")
        self.assertGreater(restore_index, snapshot_index)
        assert_no_aborting_gates(self, LIGHTS[snapshot_index + 1:restore_index])
        for action in actions(LIGHTS[snapshot_index + 1:restore_index], "light.turn_on"):
            self.assertTrue(action.get("continue_on_error"),
                            "a lamp error must leave the restore reachable")

    def test_audio_request_failures_leave_cleanup_reachable(self):
        normal = BUILDER["audio_normal"]
        for service in ("notify.alexa_media", "media_player.play_media", "media_player.media_stop"):
            matches = actions(normal, service)
            self.assertTrue(matches, service)
            self.assertTrue(all(item.get("continue_on_error") for item in matches), service)
        self.assertEqual(actions(normal[-1], "scene.turn_on")[0]["target"]["entity_id"],
                         "{{ 'scene.' ~ audio_snapshot }}")
        assert_no_aborting_gates(self, normal[1:])

    def test_volume_is_changed_only_after_successful_snapshot(self):
        normal = BUILDER["audio_normal"]
        volume_branches = [node for node in nodes(normal) if "then" in node
                           and actions(node["then"], "media_player.volume_set")]
        self.assertEqual(len(volume_branches), 1)
        branch = volume_branches[0]
        self.assertIn("known_volume", branch["if"][0]["value_template"])
        snapshot_index = next(i for i, step in enumerate(normal) if actions(step, "scene.create"))
        volume_index = next(i for i, step in enumerate(normal) if actions(step, "media_player.volume_set"))
        self.assertLess(snapshot_index, volume_index)
        snapshot = normal[snapshot_index]
        self.assertIn("known_volume", snapshot["if"][0]["value_template"])
        self.assertNotIn("continue_on_error", actions(snapshot, "scene.create")[0])

    def test_generic_playback_snapshots_even_when_volume_is_unknown(self):
        normal = BUILDER["audio_normal"]
        for service in ("scene.create", "scene.turn_on"):
            branch = next(step for step in normal if actions(step, service))
            self.assertIn("backend == 'generic'", branch["if"][0]["value_template"])

    def test_parallel_light_failure_is_contained_while_audio_cleanup_finishes(self):
        parallel = next(step["parallel"] for step in ENGINE if "parallel" in step)
        self.assertEqual(len(parallel), 2)
        worker = actions(parallel, "script.haunted_house_light_effect")
        self.assertEqual(len(worker), 1)
        self.assertTrue(worker[0].get("continue_on_error"))
        self.assertIs(worker[0]["data"]["preview"], False)

    def test_no_fire_and_forget_script_calls_release_room_lock_early(self):
        self.assertFalse(actions(PACKAGE, "script.turn_on"))
        self.assertRegex(BLUEPRINT, r"(?m)^mode: single$")
        self.assertRegex(BLUEPRINT, r"(?m)^  - action: !input controller$")
        self.assertRegex(BLUEPRINT, r"(?m)^    response_variable: haunted_house_result$")

    def test_cleanup_gate_detector_rejects_aborting_regressions(self):
        # Exercise the guard itself so accidental gates cannot be silently missed.
        with self.assertRaises(AssertionError):
            assert_no_aborting_gates(self, [{"repeat": {"sequence": [
                {"condition": "state", "entity_id": "input_boolean.master", "state": "on"},
            ]}}])


class RoutingTests(unittest.TestCase):
    def test_group_members_are_materialized_before_list_concatenation(self):
        # Hue returns an unordered set on some HA versions. A direct list+set
        # crashes nested group resolution before its available leaves are saved.
        group = BUILDER["group_template"]
        self.assertRegex(group, r"next\.ids\s*\+\s*\(members\s*\|\s*list\)")
        self.assertIn("e not in ns.seen", group)
        self.assertIn("unique | list", group)
        self.assertIn("states(e) in ['on','off']", group)
        self.assertIn("'unresolved': ns.queue", group)

    def test_sonos_announcement_volume_is_sibling_of_media(self):
        sonos = BUILDER["audio"]["choose"][0]["sequence"][0]["data"]
        self.assertTrue(sonos["announce"])
        self.assertEqual(sonos["extra"], {"volume": "{{ volume | int }}"})
        self.assertNotIn("extra", sonos["media"])

    def test_manual_run_actions_accepts_platform_none(self):
        # HA's Run actions supplies trigger={'platform': None} rather than an
        # undefined trigger. Without this clause an intentional manual test is gated.
        self.assertIn("trigger.get('platform') is none", BLUEPRINT)

    def test_blueprint_sensor_choices_match_trigger_types(self):
        self.assertIn("device_class: [motion, occupancy]", BLUEPRINT)
        self.assertIn("value: motion.detected", BLUEPRINT)
        self.assertIn("value: occupancy.detected", BLUEPRINT)
        self.assertIn("trigger: !input sensor_kind", BLUEPRINT)
        self.assertIn("behavior: first", BLUEPRINT)

    def test_room_scene_names_use_the_automation_entity_id(self):
        self.assertIn('room_key: "{{ this.entity_id }}"', BLUEPRINT)
        self.assertIn("room_key", BUILDER["engine_vars"]["key"])
        self.assertIn("room_key", BUILDER["light_vars"]["key"])

    def test_live_snapshot_targets_leaves_but_effect_targets_selection(self):
        snapshot = actions(LIGHTS, "scene.create")[0]
        self.assertEqual(snapshot["data"]["snapshot_entities"], "{{ leaves }}")
        self.assertIn("for e in lights", BUILDER["light_vars"]["color_targets"])
        self.assertIn("for e in lights", BUILDER["light_vars"]["white_targets"])

    def test_sound_profile_mapping_uses_real_catalogue_ids(self):
        profile = BUILDER["engine_vars"]["profile"]
        for sound_id in ("ghost", "ghosts_demons", "thunder_rumble", "wolf_howl", "whistling_wind"):
            self.assertIn("'" + sound_id + "'", profile)
            self.assertIn(sound_id, {item["id"] for item in BUILDER["SOUNDS"]})


@unittest.skipUnless(HAS_PINNED_HA, "requires isolated Python 3.14 + homeassistant==2026.10.2")
class SchemaCommandTests(unittest.TestCase):
    def test_offline_schema_validator_reports_success_and_exits_cleanly(self):
        # A successful JSON report alone is insufficient: lingering executor
        # threads would leave CI stuck after the validation has passed.
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "validate_ha.py"), "--json"],
            capture_output=True, text=True, timeout=15, check=True,
        )
        report = json.loads(result.stdout)
        self.assertTrue(report["success"])
        self.assertFalse(report["executes_actions"])
        self.assertEqual(report["homeassistant"], "2026.10.2")
        self.assertIn("6 blueprint substitutions: real BlueprintInputs + PLATFORM_SCHEMA", report["checks"])


@unittest.skipUnless(HAS_PINNED_HA, "requires isolated Python 3.14 + homeassistant==2026.10.2")
class TemplateRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from homeassistant.core import HomeAssistant
        from homeassistant.helpers.template import Template

        self.directory = TemporaryDirectory(prefix="haunted-house-template-test-")
        self.hass = HomeAssistant(self.directory.name)
        self.Template = Template
        self.hass.states.async_set("media_player.fixture", "idle", {"volume_level": 0.42})
        self.hass.states.async_set("input_select.haunted_house_atmosphere", "Classic")
        self.hass.states.async_set("input_select.haunted_house_light_profile", "Match sound")

    async def asyncTearDown(self):
        self.hass.import_executor.shutdown(wait=True)
        self.directory.cleanup()

    def render(self, value, variables):
        if isinstance(value, dict):
            return {key: self.render(item, variables) for key, item in value.items()}
        if isinstance(value, list):
            return [self.render(item, variables) for item in value]
        if isinstance(value, str) and ("{{" in value or "{%" in value):
            return self.Template(value, self.hass).async_render(variables)
        return value

    def render_variables(self, definitions, supplied):
        result = dict(supplied)
        for key, template in definitions.items():
            result[key] = self.render(template, result)
        return result

    def light_context(self, selected):
        return self.render_variables(BUILDER["light_vars"], {
            "room_key": "automation.fixture", "lights": selected, "profile": "Violet breath",
            "brightness": 35, "duration": 8,
        })

    def engine_context(self, **overrides):
        return self.render_variables(BUILDER["engine_vars"], {
            "room_name": "Fictional room", "room_key": "automation.fixture",
            "player": "media_player.fixture", "backend": "generic", **overrides,
        })

    async def test_nested_hue_sets_duplicates_cycles_and_offline_leaves(self):
        self.hass.states.async_set("light.root", "on", {
            "entity_id": {"light.branch", "light.rgb"}, "supported_color_modes": {"xy"},
        })
        self.hass.states.async_set("light.branch", "on", {
            "group_entities": {"light.rgb", "light.white", "light.offline", "light.root"},
            "supported_color_modes": {"xy"},
        })
        self.hass.states.async_set("light.rgb", "on", {"supported_color_modes": {"xy"}})
        self.hass.states.async_set("light.white", "off", {"supported_color_modes": {"brightness"}})
        self.hass.states.async_set("light.offline", "unavailable", {"supported_color_modes": {"xy"}})
        context = self.light_context(["light.root", "light.rgb"])
        self.assertIsInstance(context["snapshot_info"], dict)
        self.assertIsInstance(context["leaves"], list)
        self.assertEqual(set(context["leaves"]), {"light.rgb", "light.white"})
        self.assertEqual(context["snapshot_info"]["unresolved"], [])
        self.assertEqual(set(context["color_targets"]), {"light.root", "light.rgb"})

    async def test_excessive_group_depth_is_reported_instead_of_partial_snapshot(self):
        for index in range(10):
            self.hass.states.async_set(f"light.depth_{index}", "on", {
                "entity_id": {f"light.depth_{index + 1}"}, "supported_color_modes": {"xy"},
            })
        context = self.light_context(["light.depth_0"])
        self.assertTrue(context["snapshot_info"]["unresolved"])
        self.assertEqual(context["leaves"], [])
        gate = next(step["value_template"] for step in LIGHTS
                    if step.get("condition") == "template")
        self.assertIs(self.render(gate, context), False)

    async def test_color_white_and_onoff_targets_are_separated_with_native_types(self):
        for entity, modes in (("light.rgb", {"rgb"}), ("light.white", {"color_temp"}),
                              ("light.onoff", {"onoff"})):
            self.hass.states.async_set(entity, "off", {"supported_color_modes": modes})
        context = self.light_context(["light.rgb", "light.white", "light.onoff"])
        self.assertEqual(context["color_targets"], ["light.rgb"])
        self.assertEqual(context["white_targets"], ["light.white"])
        self.assertIsInstance(context["peak"], int)
        self.assertIsInstance(context["cycles"], int)
        self.assertIsInstance(context["half"], float)
        self.assertIsInstance(context["palette"]["high"], list)
        self.assertIs(context["preview"], True)

    async def test_engine_selects_nonrepeating_custom_audio_and_handles_single_choice(self):
        first, second = "https://example.com/a.mp3", "https://example.com/b.mp3"
        self.hass.states.async_set("input_text.fixture_memory", first)
        context = self.engine_context(media_urls=[first, second], memory=["input_text.fixture_memory"])
        self.assertEqual(context["sound"]["url"], second)
        self.assertIsInstance(context["sound"], dict)
        self.assertIsInstance(context["volume"], int)
        self.assertIs(context["preview"], True)
        self.assertIs(context["manual"], False)
        self.assertIs(context["known_volume"], True)
        single = self.engine_context(media_urls=[first], memory=["input_text.fixture_memory"])
        self.assertEqual(single["sound"]["url"], first)

    async def test_backend_and_numeric_bounds_produce_valid_native_payloads(self):
        context = self.engine_context(backend="sonos", volume=999, custom_duration=-5, preview="off")
        self.assertEqual(context["volume"], 100)
        self.assertEqual(context["custom_duration"], 1)
        self.assertIs(context["preview"], False)
        action = BUILDER["audio"]["choose"][0]["sequence"][0]
        payload = self.render(action["data"], context)
        self.assertIs(payload["announce"], True)
        self.assertIsInstance(payload["extra"]["volume"], int)
        self.assertIsInstance(payload["media"]["media_content_id"], str)
        self.assertTrue(payload["media"]["media_content_id"].startswith("https://"))

    async def test_every_atmosphere_has_eligible_catalogue_entries(self):
        for atmosphere, maximum in (("Light", 1), ("Classic", 2), ("Intense", 3)):
            self.hass.states.async_set("input_select.haunted_house_atmosphere", atmosphere)
            context = self.engine_context(backend="alexa")
            self.assertTrue(context["candidates"])
            self.assertTrue(all(sound["level"] <= maximum for sound in context["candidates"]))
            self.assertTrue(context["sound"]["soundbank"].startswith("soundbank://"))

    async def test_match_sound_profiles_cover_actual_catalogue_ids(self):
        expected = {
            "ghost": "Apparition", "ghosts_demons": "Apparition", "thunder_rumble": "Apparition",
            "wolf_howl": "Violet breath", "whistling_wind": "Violet breath", "wood_creak": "Haunted pumpkin",
        }
        for sound_id, profile in expected.items():
            with self.subTest(sound=sound_id):
                result = self.render(BUILDER["engine_vars"]["profile"], {
                    "profile_selection": "Match sound", "sound": {"id": sound_id},
                })
                self.assertEqual(result, profile)

    async def test_manual_run_actions_differs_from_presence_trigger(self):
        expression = BLUEPRINT.split('manual: "', 1)[1].split('"\n', 1)[0]
        for supplied in ({}, {"trigger": None}, {"trigger": {"platform": None}}):
            self.assertIs(self.render(expression, supplied), True)
        self.assertIs(self.render(expression, {"trigger": {"platform": "motion.detected"}}), False)


if __name__ == "__main__":
    unittest.main()
