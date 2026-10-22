#!/usr/bin/env python3
"""Validate local artifacts with Home Assistant's real, pinned schemas.

Requires Python 3.14 and homeassistant==2026.10.2. This tool creates a local,
unstarted HomeAssistant object for template validation in a temporary directory.
It never starts a server, sets up integrations, or calls services.
It checks static schemas, selectors, template syntax and blueprint substitution;
it does not claim to validate integration-specific trigger/action runtime setup.
"""

from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import importlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any


EXPECTED_HA = "2026.10.2"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    result.add_argument("--inputs", type=Path, help="JSON mapping of blueprint input overrides")
    result.add_argument("--json", action="store_true", help="Print a machine-readable report")
    return result


def options(config: dict[str, Any]) -> list[Any]:
    return [item.get("value") if isinstance(item, dict) else item
            for item in config.get("options", [])]


def sample_value(key: str, definition: dict[str, Any]) -> Any:
    """Provide syntactically valid local fixtures, never live entity identities."""
    if "default" in definition:
        return deepcopy(definition["default"])
    spec = definition.get("selector", {"text": {}})
    kind, config = next(iter(spec.items()))
    config = config or {}
    if kind == "entity":
        filters = config.get("filter", config)
        first_filter = filters[0] if isinstance(filters, list) else filters
        domain = first_filter.get("domain", "light")
        domain = domain[0] if isinstance(domain, list) else domain
        identity = f"{domain}.haunted_validation"
        return [identity] if config.get("multiple") else identity
    if kind == "target":
        return {"entity_id": ["light.haunted_validation"]}
    if kind == "text":
        return "Validation room" if "room" in key else "Validation fixture"
    if kind == "boolean":
        return False
    if kind == "number":
        return config.get("min", 0)
    if kind == "select":
        choices = options(config)
        if not choices:
            raise ValueError(f"Input {key!r} has no select options")
        return [choices[0]] if config.get("multiple") else choices[0]
    if kind == "duration":
        return {"seconds": 1}
    if kind == "time":
        return "18:00:00"
    if kind == "action":
        return []
    raise ValueError(f"Provide an explicit --inputs value for {key!r} ({kind})")


def template_strings(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from template_strings(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from template_strings(item, f"{path}[{index}]")
    elif isinstance(value, str) and ("{{" in value or "{%" in value):
        yield path, value


def validate(root: Path, overrides: dict[str, Any], hass: Any) -> list[str]:
    # Deliberately import HA only after CLI parsing and dependency checks.
    from homeassistant.components.automation.config import (
        AUTOMATION_BLUEPRINT_SCHEMA,
        PLATFORM_SCHEMA,
    )
    from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
    from homeassistant.components.script.config import SCRIPT_ENTITY_SCHEMA
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.selector import selector
    from homeassistant.helpers.template import Template
    from homeassistant.util import yaml as yaml_util

    package_path = root / "packages" / "haunted_house.yaml"
    blueprint_path = root / "blueprints" / "automation" / "haunted_house" / "room.yaml"
    package = yaml_util.load_yaml_dict(package_path)
    blueprint_data = yaml_util.load_yaml_dict(blueprint_path)
    checks = []

    for domain, data in package.items():
        if domain == "script":
            if not isinstance(data, dict):
                raise ValueError("Package script section must be a mapping")
            for object_id, body in data.items():
                cv.slug(object_id)
                SCRIPT_ENTITY_SCHEMA(deepcopy(body))
                checks.append(f"script.{object_id}: real SCRIPT_ENTITY_SCHEMA")
        elif domain == "automation":
            for item in data if isinstance(data, list) else [data]:
                PLATFORM_SCHEMA(deepcopy(item))
                checks.append("package automation: real PLATFORM_SCHEMA")
        else:
            integration = importlib.import_module(f"homeassistant.components.{domain}")
            schema = getattr(integration, "CONFIG_SCHEMA", None)
            if schema is None:
                raise ValueError(f"No static CONFIG_SCHEMA for package domain {domain!r}")
            schema({domain: deepcopy(data)})
            checks.append(f"{domain}: real CONFIG_SCHEMA")

    blueprint = Blueprint(
        blueprint_data,
        path="haunted_house/room.yaml",
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    if errors := blueprint.validate():
        raise ValueError("; ".join(errors))
    checks.append("blueprint metadata and !input declarations: real Blueprint schema")
    unknown = set(overrides) - set(blueprint.inputs)
    if unknown:
        raise ValueError(f"Unknown input overrides: {', '.join(sorted(unknown))}")
    supplied = {
        key: deepcopy(overrides[key]) if key in overrides else sample_value(key, definition)
        for key, definition in blueprint.inputs.items()
    }
    for key, definition in blueprint.inputs.items():
        if spec := definition.get("selector"):
            selector(spec)(supplied[key])
    checks.append("all sample/default input values: real selectors")

    # Exercise both trigger kinds and every declared backend, not household IDs.
    cases = [supplied]
    for key, definition in blueprint.inputs.items():
        selection = definition.get("selector", {}).get("select", {}) or {}
        choices = options(selection)
        if set(choices) in (
            {"motion.detected", "occupancy.detected"},
            {"alexa", "sonos", "generic"},
        ):
            cases = [{**case, key: choice} for case in cases for choice in choices]
    for index, values in enumerate(cases):
        instance = {
            "id": f"haunted_validation_{index}",
            "alias": f"Haunted House validation {index}",
            "use_blueprint": {"path": "haunted_house/room.yaml", "input": values},
        }
        inputs = BlueprintInputs(blueprint, instance)
        inputs.validate()
        substituted = inputs.async_substitute()  # HA callback; intentionally not a coroutine.
        PLATFORM_SCHEMA(substituted)
    checks.append(f"{len(cases)} blueprint substitutions: real BlueprintInputs + PLATFORM_SCHEMA")

    count = 0
    for source in (package, blueprint_data):
        for path, text in template_strings(source):
            try:
                Template(text, hass).ensure_valid()
            except Exception as error:
                raise ValueError(f"Template syntax at {path}: {error}") from error
            count += 1
    checks.append(f"{count} embedded templates: real HA Template syntax")
    return checks


async def async_validate(root: Path, overrides: dict[str, Any]) -> list[str]:
    # HA's template schemas require both an event loop and an HA context.
    # Construction alone does not start HA or set up any integration/server.
    from homeassistant.core import HomeAssistant

    with TemporaryDirectory(prefix="haunted-house-schema-") as directory:
        hass = HomeAssistant(directory)
        try:
            return validate(root, overrides, hass)
        finally:
            hass.import_executor.shutdown(wait=True)


def main() -> int:
    args = parser().parse_args()
    report = {
        "success": False,
        "expected_homeassistant": EXPECTED_HA,
        "python": sys.version.split()[0],
        "offline": True,
        "executes_actions": False,
        "checks": [],
        "limitations": [
            "Static schemas and template syntax only; no template rendering or actuator calls.",
            "Integration-specific async trigger/action setup and physical playback are not tested.",
        ],
    }
    code = 1
    try:
        if sys.version_info < (3, 14):
            raise RuntimeError("Requires Python 3.14 and homeassistant==2026.10.2")
        try:
            installed = version("homeassistant")
        except PackageNotFoundError as error:
            raise RuntimeError("Install homeassistant==2026.10.2 in an isolated environment") from error
        report["homeassistant"] = installed
        if installed != EXPECTED_HA:
            raise RuntimeError(f"Expected HA {EXPECTED_HA}; found {installed}")
        supplied = json.loads(args.inputs.read_text()) if args.inputs else {}
        if not isinstance(supplied, dict):
            raise ValueError("--inputs must contain a JSON object")
        report["checks"] = asyncio.run(async_validate(args.root.resolve(), supplied))
        report["success"] = True
        code = 0
    except (RuntimeError, ImportError) as error:
        report["error"] = str(error)
        code = 2
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for check in report["checks"]:
            print(f"PASS {check}")
        print("PASS offline HA schema validation" if report["success"] else f"FAIL {report['error']}")
        for limitation in report["limitations"]:
            print(f"NOTE {limitation}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
