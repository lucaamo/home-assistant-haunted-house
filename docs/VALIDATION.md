# Validation and release scope

Version: **0.1.0-beta.1**. Checked on **2026-10-22** against **Home Assistant 2026.10.2**, using an isolated **Python 3.14.5** environment. The generic project was not installed over the original household setup.

## Checks performed

- YAML parsing with duplicate-key detection, blueprint input references, safe preview defaults, shared-helper references, native dashboard cards and a distribution/privacy scan.
- **29 automated tests**: 20 control-flow/cleanup invariants, 8 runtime tests using real Home Assistant templates with fictional, in-memory states, and a validator subprocess exit check. Tests cover group-member sets, nested groups, duplicates, cycles, unavailable lights, excess group depth, color/dimmer/on-off capabilities, native payload types, numerical bounds, optional repeat memory, every atmosphere, sound/profile matching and manual-run detection.
- The real HA configuration schemas for six helper domains, four scripts and the one-time initialization automation.
- The real blueprint metadata and selector schemas, six substitutions covering two sensor kinds × three audio backends, and syntax validation of **139 embedded templates**.
- Home Assistant's read-only WebSocket `validate_config` for all script sequences, initialization, and both motion/occupancy blueprint action paths. Additional template evaluation checked native types, group snapshot resolution, custom media URLs and manual `trigger.platform: null`. Summary: [validation-websocket.json](validation-websocket.json).

No device actions, audio, light changes or HA configuration writes were made by these checks. The offline HA object is constructed solely to provide a validation/template context; it is never started and has no integrations or registered device services.

## Reproduce

```sh
# Use a clean Python 3.14 environment.
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python tools/lint.py
python -m unittest discover -s tests -v
python tools/validate_ha.py --json
```

The same checks run in GitHub Actions. `tools/validate_ha.py` rejects a different HA version rather than silently validating against another schema. Its fixture entity IDs are fictional: it validates configuration structure, not their existence in a real home. With a Python environment lacking the pinned HA runtime, the structural tests can run but the eight template tests are explicitly skipped; use the pinned environment for a release check.

`tools/build.py` regenerates the installable package using Python and Ruby's standard YAML serializer. Build output contains no timestamp. After editing the builder/catalogue, regenerate and rerun the checks before distributing.

## What is not proven

Schema and template checks do not prove audible playback, cloud delivery timing, speaker announcement capability, physical light behavior or recovery after a process crash. They do not test every integration, Sonos generation, firmware or media codec. The earlier household implementation had a real Sonos/Hue trial; that is not a physical-device acceptance test of every route in this generic release.

After installing, keep each room in silent preview, inspect its trace, then make one intentional low-volume test with preview disabled. Verify the speaker, lights and restoration before arming automatic effects. Review the recovery and shared-device limits in the [README](../README.md).
