#!/usr/bin/env python3
"""Offline release checks. Requires PyYAML (also supplied by Home Assistant)."""
import json
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]

class Input(str):
    pass

class Loader(yaml.SafeLoader):
    pass

def mapping(loader, node, deep=False):
    out = {}
    for k, v in node.value:
        key = loader.construct_object(k, deep=deep)
        if key in out:
            raise ValueError(f'Duplicate YAML key: {key}')
        out[key] = loader.construct_object(v, deep=deep)
    return out

Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
Loader.add_constructor('!input', lambda loader, node: Input(loader.construct_scalar(node)))

def walk(value):
    yield value
    if isinstance(value, dict):
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)

def load(path):
    return yaml.load(path.read_text(), Loader=Loader)

def main():
    paths = sorted(p for p in ROOT.rglob('*.yaml') if not any(x in p.parts for x in ['.venv', 'dist', '.git']))
    parsed = {str(p.relative_to(ROOT)): load(p) for p in paths}
    bp = parsed['blueprints/automation/haunted_house/room.yaml']
    package = parsed['packages/haunted_house.yaml']
    flat = {}
    for key, value in bp['blueprint']['input'].items():
        if 'input' in value:
            if value.get('collapsed'):
                assert all('default' in i for i in value['input'].values()), 'Hidden required input'
            flat.update(value['input'])
        else:
            flat[key] = value
    used = {str(v) for v in walk(bp) if isinstance(v, Input)}
    assert used == set(flat), (used, set(flat))
    assert bp['blueprint']['homeassistant']['min_version'] == '2026.10.2'
    assert bp['blueprint']['source_url'].startswith('https://github.com/')
    assert flat['preview']['default'] is True
    assert bp['mode'] == 'single'
    assert isinstance(bp['actions'][0]['action'], Input)
    assert bp['actions'][0]['response_variable'] == 'haunted_house_result'
    for required in ['room_name', 'sensors', 'player', 'controller']:
        assert 'default' not in flat[required], required
    own = {f'{domain}.{slug}' for domain, entities in package.items() if isinstance(entities, dict) for slug in entities}
    text = json.dumps(package)
    refs = set(re.findall(r'(?:input_boolean|input_number|input_datetime|input_select|input_text|counter|script)\.haunted_house_[a-z_]+', text))
    assert refs <= own, sorted(refs-own)
    assert package['script']['haunted_house_effect']['mode'] == 'parallel'
    sounds = json.loads((ROOT/'assets/sounds.json').read_text())
    assert len(sounds) == len({s['id'] for s in sounds}) == 9
    for sound in sounds:
        assert sound['soundbank'].startswith('soundbank://soundlibrary/')
        assert sound['url'].startswith('https://')
        assert 0 < sound['duration'] <= 120
    for path, value in parsed.items():
        serialized = json.dumps(value)
        if path.startswith('dashboards/'):
            assert 'custom:' not in serialized, 'Dashboard requires a custom card'
    # The distribution must never include real household exports/credentials/media.
    for path in ROOT.rglob('*'):
        if not path.is_file() or any(x in path.parts for x in ['.git', '.venv', 'dist', '__pycache__']):
            continue
        assert path.suffix.lower() not in ['.mp3', '.wav', '.ogg', '.pem', '.key']
        if path.suffix in ['.yaml', '.json', '.py', '.md']:
            content = path.read_text()
            assert not re.search(r'https?://(?:192\.168\.|10\.\d|172\.(?:1[6-9]|2\d|3[01])\.)', content), f'Private network URL in {path.name}'
            assert not re.search(r'(?:ghp|github_pat)_[A-Za-z0-9]{20,}', content), f'Credential pattern in {path.name}'
    print(json.dumps({'yaml_files': len(paths), 'blueprint_inputs': len(flat), 'helpers': len(own)-len(package['script']),
                      'scripts': len(package['script']), 'sounds': len(sounds), 'checks': 'passed'}))

if __name__ == '__main__':
    main()
