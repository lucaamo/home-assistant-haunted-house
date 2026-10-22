#!/usr/bin/env python3
"""Build the installable package from the public sound catalogue (Python + Ruby)."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOUNDS = json.loads((ROOT / 'assets/sounds.json').read_text())
P = 'haunted_house_'

def state(entity, value):
    return {'condition': 'state', 'entity_id': entity, 'state': value}

def cond(expr):
    return {'condition': 'template', 'value_template': expr}

def call(service, target=None, data=None, **kw):
    out = {'action': service, **kw}
    if target is not None:
        out['target'] = {'entity_id': target}
    if data is not None:
        out['data'] = data
    return out

def optional(test, sequence):
    return {'if': [cond(test)], 'then': sequence}

def stop(status, reason):
    return [
        {'variables': {'result': {'status': status, 'reason': reason}}},
        {'stop': reason, 'response_variable': 'result'},
    ]

def input_field(name, selector, **kw):
    return {'name': name, 'selector': selector, **kw}

def script(alias, sequence, **kw):
    return {'alias': alias, 'sequence': sequence, **kw}

PACKAGE = {
    'input_boolean': {P+k: {'name': 'Haunted House · '+label, 'icon': icon}
        for k, label, icon in [
            ('enabled', 'Enabled', 'mdi:halloween'),
            ('use_schedule', 'Use time window', 'mdi:clock-outline'),
            ('only_halloween', 'Only October 31', 'mdi:calendar'),
            ('respect_music', 'Respect music', 'mdi:music-note'),
            ('lights_enabled', 'Light effects', 'mdi:lightbulb-group'),
            ('initialized', 'Defaults initialized', 'mdi:check-circle'),
        ]},
    'input_datetime': {P+k: {'name': 'Haunted House · '+name, 'has_date': False, 'has_time': True}
        for k, name in [('start', 'Start'), ('end', 'End')]},
    'input_number': {P+k: {'name': 'Haunted House · '+name, 'min': minimum, 'max': maximum,
        'step': 1, 'unit_of_measurement': unit, 'mode': 'slider'}
        for k, name, minimum, maximum, unit in [
            ('probability', 'Chance', 0, 100, '%'), ('cooldown', 'Room cooldown', 0, 3600, 's'),
            ('delay', 'Maximum random delay', 0, 60, 's'), ('light_brightness', 'Light peak brightness', 5, 70, '%')]},
    'input_select': {
        P+'atmosphere': {'name': 'Haunted House · Atmosphere', 'options': ['Light', 'Classic', 'Intense']},
        P+'light_profile': {'name': 'Haunted House · Light profile', 'options': ['Match sound', 'Violet breath', 'Haunted pumpkin', 'Apparition']},
    },
    'input_text': {P+'last_event': {'name': 'Haunted House · Last event', 'max': 255}},
    'counter': {P+'effects': {'name': 'Haunted House · Effects requested', 'initial': 0, 'step': 1, 'restore': True}},
    'script': {},
}

# All helper input_* omit initial: users' settings survive restart. Initialize once.
defaults = [call('input_boolean.turn_off', 'input_boolean.'+P+'enabled')]
for suffix in ['use_schedule', 'only_halloween', 'respect_music', 'lights_enabled']:
    defaults.append(call('input_boolean.turn_on', 'input_boolean.'+P+suffix))
for suffix, value in [('probability', 100), ('cooldown', 300), ('delay', 4), ('light_brightness', 35)]:
    defaults.append(call('input_number.set_value', 'input_number.'+P+suffix, {'value': value}))
for suffix, value in [('start', '18:00:00'), ('end', '23:00:00')]:
    defaults.append(call('input_datetime.set_datetime', 'input_datetime.'+P+suffix, {'time': value}))
for suffix, value in [('atmosphere', 'Classic'), ('light_profile', 'Match sound')]:
    defaults.append(call('input_select.select_option', 'input_select.'+P+suffix, {'option': value}))
defaults += [call('input_boolean.turn_on', 'input_boolean.'+P+'initialized')]
PACKAGE['script'][P+'reset_defaults'] = script('Haunted House · Reset defaults (disarms)', defaults, mode='single', icon='mdi:restore')
PACKAGE['script'][P+'disarm'] = script('Haunted House · Disarm', [call('input_boolean.turn_off', 'input_boolean.'+P+'enabled')], mode='single', icon='mdi:shield-off')
PACKAGE['automation'] = [{
    'id': P+'initialize', 'alias': 'Haunted House · Initialize defaults once', 'mode': 'single',
    'triggers': [{'trigger': 'homeassistant', 'event': 'start'}],
    'conditions': [state('input_boolean.'+P+'initialized', 'off')],
    'actions': [call('script.'+P+'reset_defaults')],
}]

# The group itself remains the command target. Snapshot available leaves separately.
# Bounded traversal supports nested Hue/native groups and detects excess depth.
group_template = '''{% set ns = namespace(queue=lights, seen=[], leaves=[]) %}
{% for depth in range(8) %}
  {% set next = namespace(ids=[]) %}
  {% for e in ns.queue %}
    {% if e not in ns.seen %}
      {% set ns.seen = ns.seen + [e] %}
      {% set members = state_attr(e, 'entity_id') or state_attr(e, 'group_entities') or [] %}
      {% if members %}{% set next.ids = next.ids + (members | list) %}
      {% elif e.startswith('light.') and states(e) in ['on','off'] %}
        {% set ns.leaves = ns.leaves + [e] %}
      {% endif %}
    {% endif %}
  {% endfor %}
  {% set ns.queue = next.ids %}
{% endfor %}
{{ {'leaves': ns.leaves | unique | list, 'unresolved': ns.queue} }}'''

def light_targets(color):
    test = "'xy' in modes or 'hs' in modes or 'rgb' in modes or 'rgbw' in modes or 'rgbww' in modes"
    if not color:
        test = '('+test+") == false and ('brightness' in modes or 'color_temp' in modes or 'white' in modes)"
    return "{% set ns = namespace(ids=[]) %}{% for e in lights %}{% set modes = state_attr(e, 'supported_color_modes') or [] %}{% if has_value(e) and ("+test+") %}{% set ns.ids = ns.ids + [e] %}{% endif %}{% endfor %}{{ ns.ids | unique | list }}"

profiles = {
    'Violet breath': {'high': [115, 0, 255], 'low': [200, 0, 255], 'ratio': .20},
    'Haunted pumpkin': {'high': [255, 65, 0], 'low': [255, 12, 0], 'ratio': .35},
    'Apparition': {'high': [110, 190, 255], 'low': [105, 20, 255], 'ratio': .18},
}
light_vars = {
    'lights': '{{ lights | default([]) }}', 'preview': '{{ preview | default(true) | bool }}',
    'key': "{{ room_key | lower | regex_replace('[^a-z0-9_]', '_') }}",
    'snapshot_id': "{{ 'haunted_house_lights_' ~ key }}", 'profiles': profiles,
    'palette': '{{ profiles.get(profile, profiles["Violet breath"]) }}',
    'peak': '{{ [70, [5, brightness | int(35)] | max] | min }}',
    'low': '{{ [4, (peak | float * palette.ratio) | round(0) | int] | max }}',
    'length': '{{ [8, [5, duration | float(6)] | max] | min }}',
    'cycles': '{{ 3 if length | float >= 6.5 else 2 }}',
    'half': '{{ length | float / (cycles | int * 2) }}',
    'snapshot_info': group_template,
    'leaves': '{{ snapshot_info.leaves }}',
    'color_targets': light_targets(True), 'white_targets': light_targets(False),
    'reset_effects': "{% set ns = namespace(ids=[]) %}{% for e in leaves %}{% if 'off' in (state_attr(e, 'effect_list') or []) %}{% set ns.ids = ns.ids + [e] %}{% endif %}{% endfor %}{{ ns.ids }}",
}
repeat = []
for level, rgb in [('peak', 'high'), ('low', 'low')]:
    repeat += [
        optional('{{ color_targets | length > 0 }}', [call('light.turn_on', '{{ color_targets }}', {
            'brightness_pct': '{{ '+level+' | int }}', 'rgb_color': '{{ palette.'+rgb+' }}', 'transition': '{{ half | float * 0.85 }}'}, continue_on_error=True)]),
        optional('{{ white_targets | length > 0 }}', [call('light.turn_on', '{{ white_targets }}', {
            'brightness_pct': '{{ '+level+' | int }}', 'transition': '{{ half | float * 0.85 }}'}, continue_on_error=True)]),
        {'delay': {'seconds': '{{ half | float }}'}},
    ]
PACKAGE['script'][P+'light_effect'] = script('Haunted House · Light effect', [
    {'variables': light_vars},
    optional('{{ preview }}', [
        {'variables': {'result': {'status': 'preview', 'controls': '{{ lights }}', 'snapshot_entities': '{{ leaves }}',
            'color_targets': '{{ color_targets }}', 'white_targets': '{{ white_targets }}',
            'unresolved_groups': '{{ snapshot_info.unresolved }}', 'scene_id': '{{ snapshot_id }}'}}},
        {'stop': 'Preview: no light or scene was changed', 'response_variable': 'result'},
    ]),
    state('input_boolean.'+P+'lights_enabled', 'on'),
    cond('{{ leaves | length > 0 and snapshot_info.unresolved | length == 0 and (color_targets | length + white_targets | length) > 0 }}'),
    call('scene.create', data={'scene_id': '{{ snapshot_id }}', 'snapshot_entities': '{{ leaves }}'}),
    optional('{{ reset_effects | length > 0 }}', [call('light.turn_on', '{{ reset_effects }}', {'effect': 'off'}, continue_on_error=True)]),
    {'repeat': {'count': '{{ cycles | int }}', 'sequence': repeat}},
    call('scene.turn_on', "{{ 'scene.' ~ snapshot_id }}", {'transition': 1}),
    {'delay': {'seconds': 1.1}},
], mode='parallel', max=30, max_exceeded='warning', description='Commands selected lights/groups; snapshots available leaves individually. Master disarm lets cleanup finish. Never stop/reload while running.')

hour_gate = {'condition': 'or', 'conditions': [state('input_boolean.'+P+'use_schedule', 'off'),
    {'condition': 'time', 'after': 'input_datetime.'+P+'start', 'before': 'input_datetime.'+P+'end'}]}
date_gate = {'condition': 'or', 'conditions': [state('input_boolean.'+P+'only_halloween', 'off'), cond('{{ now().month == 10 and now().day == 31 }}')]}
gates = [state('input_boolean.'+P+'initialized', 'on'), state('input_boolean.'+P+'enabled', 'on'), hour_gate, date_gate,
    cond("{{ sensors | select('is_state', 'on') | list | length > 0 }}"),
    cond("{{ backend == 'sonos' or not is_state('input_boolean.haunted_house_respect_music', 'on') or not is_state(player, 'playing') }}")]
automatic_gate = {'condition': 'or', 'conditions': [cond('{{ manual }}'), {'condition': 'and', 'conditions': gates}]}
engine_vars = {
    'room_name': '{{ room_name | default("Room") }}', 'room_key': '{{ room_key | default("manual_preview") }}',
    'sensors': '{{ sensors | default([]) }}', 'lights': '{{ lights | default([]) }}',
    'player': '{{ player | default("") }}', 'backend': '{{ backend | default("generic") }}',
    'preview': '{{ preview | default(true) | bool }}', 'manual': '{{ manual | default(false) | bool }}',
    'volume': '{{ [100, [0, volume | default(25) | int(25)] | max] | min }}',
    'media_urls': '{{ media_urls | default([]) }}', 'custom_duration': '{{ [120, [1, custom_duration | default(8) | float(8)] | max] | min }}',
    'memory': '{{ memory | default([]) }}',
    'level': "{{ {'Light':1, 'Classic':2, 'Intense':3}.get(states('input_select.haunted_house_atmosphere'), 2) }}",
    'catalogue': [{**s, 'label': s['label_en']} for s in SOUNDS],
    'previous': '{{ states(memory[0]) if memory | length > 0 else "" }}',
    'candidates': "{% if media_urls | length > 0 and backend != 'alexa' %}{% set ns = namespace(s=[]) %}{% for u in media_urls %}{% set ns.s = ns.s + [{'id':u, 'label':'Custom ' ~ loop.index, 'url':u, 'duration':custom_duration, 'level':1}] %}{% endfor %}{{ ns.s }}{% else %}{{ catalogue | selectattr('level', 'le', level | int) | list }}{% endif %}",
    'pool': '{{ candidates | rejectattr("id", "eq", previous) | list }}',
    'sound': '{{ (pool if pool | length > 0 else candidates) | random }}',
    'profile_selection': "{{ states('input_select.haunted_house_light_profile') }}",
    'profile': "{{ profile_selection if profile_selection in ['Violet breath','Haunted pumpkin','Apparition'] else ('Apparition' if sound.id in ['ghost','ghosts_demons','thunder_rumble'] else ('Violet breath' if sound.id in ['wolf_howl','whistling_wind'] else 'Haunted pumpkin')) }}",
    'light_length': '{{ [8, [5, sound.duration | float(3) + 3] | max] | min }}',
    'key': "{{ room_key | lower | regex_replace('[^a-z0-9_]', '_') }}",
    'audio_snapshot': "{{ 'haunted_house_audio_' ~ key }}",
    'known_volume': '{{ is_number(state_attr(player, "volume_level")) }}',
}
# Non-AudioClip backends use a media snapshot before touching volume.
audio_normal = [
    optional("{{ known_volume or backend == 'generic' }}", [
        call('scene.create', data={'scene_id': '{{ audio_snapshot }}', 'snapshot_entities': ['{{ player }}']}),
    ]),
    optional('{{ known_volume }}', [
        call('media_player.volume_set', '{{ player }}', {'volume_level': '{{ volume | float / 100 }}'}, continue_on_error=True),
    ]),
    {'choose': [{'conditions': [cond("{{ backend == 'alexa' }}")], 'sequence': [
        call('notify.alexa_media', data={'target': ['{{ player }}'], 'message': '{{ \'<audio src="\' ~ sound.soundbank ~ \'"/>\' }}', 'data': {'type': 'tts'}}, continue_on_error=True)
    ]}], 'default': [call('media_player.play_media', '{{ player }}', {'media': {'media_content_id': '{{ sound.url }}', 'media_content_type': 'music'}}, continue_on_error=True)]},
    {'delay': {'seconds': '{{ sound.duration | float + (5 if backend == "alexa" else 2) }}'}},
    optional("{{ backend == 'generic' }}", [call('media_player.media_stop', '{{ player }}', continue_on_error=True)]),
    optional("{{ known_volume or backend == 'generic' }}", [call('scene.turn_on', "{{ 'scene.' ~ audio_snapshot }}")]),
]
audio = {'choose': [{'conditions': [cond("{{ backend == 'sonos' }}")], 'sequence': [
    call('media_player.play_media', '{{ player }}', {'media': {'media_content_id': '{{ sound.url }}', 'media_content_type': 'music'}, 'announce': True, 'extra': {'volume': '{{ volume | int }}'}}, continue_on_error=True),
    {'delay': {'seconds': '{{ sound.duration | float + 2 }}'}},
]}], 'default': audio_normal}
engine = [
    {'variables': engine_vars},
    optional("{{ backend not in ['alexa','sonos','generic'] or not player.startswith('media_player.') or not room_key or memory | length > 1 }}", stop('invalid', 'Check backend, player, room key and memory helper')),
    optional('{{ preview }}', [
        {'variables': {'result': {'status': 'preview', 'room': '{{ room_name }}', 'room_key': '{{ room_key }}',
            'player': '{{ player }}', 'backend': '{{ backend }}', 'available': '{{ has_value(player) }}', 'sound': '{{ sound }}',
            'lights': '{{ lights }}', 'profile': '{{ profile }}', 'volume': '{{ volume }}', 'known_volume': '{{ known_volume }}',
            'manual': '{{ manual }}', 'audio_scene_id': '{{ audio_snapshot }}'}}},
        {'stop': 'Preview: no devices, helpers or cooldown were changed; gates were not applied', 'response_variable': 'result'},
    ]),
    automatic_gate,
    cond("{{ manual or range(1, 101) | random <= states('input_number.haunted_house_probability') | int(0) }}"),
    {'variables': {'wait_seconds': "{{ 0 if manual else range(0, (states('input_number.haunted_house_delay') | int(0)) + 1) | random }}"}},
    optional('{{ wait_seconds | int > 0 }}', [
        {'wait_template': "{{ not is_state('input_boolean.haunted_house_enabled','on') or sensors | select('is_state','on') | list | length == 0 }}",
         'timeout': {'seconds': '{{ wait_seconds | int }}'}, 'continue_on_timeout': True},
    ]),
    automatic_gate,
    optional('{{ not has_value(player) }}', stop('unavailable', 'Player unavailable; no audio or lights were sent')),
    {'parallel': [
        {'sequence': [audio]},
        {'sequence': [optional("{{ lights | length > 0 and is_state('input_boolean.haunted_house_lights_enabled','on') }}", [
            call('script.'+P+'light_effect', data={'room_key': '{{ room_key }}', 'lights': '{{ lights }}', 'profile': '{{ profile }}',
                'brightness': "{{ states('input_number.haunted_house_light_brightness') | int(35) }}", 'duration': '{{ light_length }}', 'preview': False}, continue_on_error=True)
        ])]},
    ]},
    optional('{{ memory | length == 1 }}', [call('input_text.set_value', '{{ memory[0] }}', {'value': '{{ sound.id }}'}, continue_on_error=True)]),
    call('input_text.set_value', 'input_text.'+P+'last_event', {'value': "{{ (now().strftime('%H:%M') ~ ' · ' ~ room_name ~ ' · ' ~ sound.label ~ (' · test' if manual else ''))[:255] }}"}, continue_on_error=True),
    optional('{{ not manual }}', [call('counter.increment', 'counter.'+P+'effects')]),
    optional('{{ not manual }}', [
        {'wait_template': "{{ not is_state('input_boolean.haunted_house_enabled', 'on') }}",
         'timeout': {'seconds': "{{ states('input_number.haunted_house_cooldown') | int(300) }}"}, 'continue_on_timeout': True},
    ]),
    {'variables': {'result': {'status': 'requested', 'room': '{{ room_name }}', 'sound': '{{ sound.label }}'}}},
    {'stop': 'Effect completed and cleanup attempted', 'response_variable': 'result'},
]
PACKAGE['script'][P+'effect'] = script('Haunted House · Effect controller', engine, mode='parallel', max=30, max_exceeded='warning',
    icon='mdi:ghost', description='Public entry point for the room blueprint. One automation owns each player/light. Calls remain synchronous through cleanup and room cooldown. Preview returns before any mutation.',
    fields={
        'room_name': input_field('Room name', {'text': {}}, default='Room'),
        'room_key': input_field('Unique room key (automation entity ID)', {'text': {}}, required=True),
        'sensors': input_field('Sensors', {'entity': {'filter': {'domain': 'binary_sensor'}, 'multiple': True}}, default=[]),
        'player': input_field('Media player', {'entity': {'filter': {'domain': 'media_player'}}}, required=True),
        'backend': input_field('Audio backend', {'select': {'options': ['alexa', 'sonos', 'generic']}}, default='generic'),
        'lights': input_field('Lights or groups', {'entity': {'filter': {'domain': 'light'}, 'multiple': True}}, default=[]),
        'volume': input_field('Volume', {'number': {'min': 0, 'max': 100, 'unit_of_measurement': '%'}}, default=25),
        'preview': input_field('Silent preview', {'boolean': {}}, default=True),
        'manual': input_field('Manual test bypasses automatic gates', {'boolean': {}}, default=False),
        'media_urls': input_field('Custom audio URLs', {'text': {'multiple': True}}, default=[]),
        'custom_duration': input_field('Custom sound duration', {'number': {'min': 1, 'max': 120, 'unit_of_measurement': 's'}}, default=8),
        'memory': input_field('Optional one input_text for no immediate repeat', {'entity': {'filter': {'domain': 'input_text'}, 'multiple': True}}, default=[]),
    })

def main():
    dest = ROOT / 'packages/haunted_house.yaml'
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(PACKAGE, ensure_ascii=False)
    result = subprocess.run(['ruby', '-rjson', '-ryaml', '-e', 'puts YAML.dump(JSON.parse(STDIN.read), line_width: 120)'], input=data, text=True, capture_output=True, check=True)
    header = '# Haunted House 0.1.0-beta.1 · Home Assistant >= 2026.10.2\n# Install once as a package. Room/device selection is in the room blueprint.\n# No recordings or credentials are included. See README and docs/AUDIO.md.\n'
    dest.write_text(header + result.stdout, encoding='utf-8')
    print(json.dumps({'package': str(dest), 'scripts': len(PACKAGE['script']), 'sounds': len(SOUNDS)}))

if __name__ == '__main__':
    main()
