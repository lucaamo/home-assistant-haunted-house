# Dashboard and room controls

The supplied dashboard uses built-in Home Assistant cards. It needs no HACS cards, custom JavaScript, fonts or external images. Install the core package and the room blueprint described in the project's [README](../README.md) before adding it.

## Add the dashboard

For a dedicated dashboard, create a new empty dashboard in **Settings → Dashboards**, open its raw configuration editor, and paste [dashboards/haunted_house.yaml](../dashboards/haunted_house.yaml). This file is a complete dashboard configuration containing one view.

For an existing dashboard, preserve its configuration and append only the single item below `views:` to its existing `views` list. Do not replace all its views with the supplied file. You can also create the cards with the visual editor; every supplied card is native.

The `haunted-house` view uses the responsive **Sections** layout with up to three columns. It becomes a single column on smaller screens. No room entities are hardcoded in the supplied dashboard, so a new installation has no missing sample-room cards.

## Create rooms in the UI

After installing `blueprints/automation/haunted_house/room.yaml`, open **Settings → Automations & scenes → Blueprints**, select **Haunted House**, and create an automation. The blueprint's actual display title may be more descriptive than this short project name.

[![Import the room blueprint into Home Assistant](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Flucaamo%2Fhome-assistant-haunted-house%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fhaunted_house%2Froom.yaml)

Fill in the room inputs:

| Input | What to choose |
| --- | --- |
| Room name | A friendly name such as `Hall` or `Study`. |
| Sensors | One or more existing motion or occupancy binary sensors for this room. |
| Sensor kind | Motion detected (`motion.detected`) or occupancy detected (`occupancy.detected`), matching the selected sensors. Use one kind within an automation. |
| Player | The existing media player in this room. |
| Backend | `alexa`, `sonos` or `generic`, matching that player and its supported audio path. |
| Lights | Individual lights or light groups for the brief effect, or an empty selection for audio only. Nested groups are supported up to eight levels. |
| Volume | The room's effect volume, as a percentage. |
| Controller | Select `script.haunted_house_effect` from the script entity picker. |
| Preview | Leave enabled for onboarding: inspect the plan under `haunted_house_result` in the automation trace. Preview bypasses all automatic gates and changes no audio, lights, helpers or cooldown. Disable it for real effects. |
| Media URLs | Optional custom audio URL list for the `sonos` or `generic` backend; follow the [audio requirements](AUDIO.md). |
| Custom duration | Duration in seconds for custom sounds, default `8`. Set it for the longest URL in the custom list. |
| Memory | Optional list containing zero or one `input_text` helper owned by this room. It remembers the last sound ID or URL to avoid an immediate repeat when alternatives exist. Leave empty to omit memory. |

Save the automation with a clear name. Reuse the blueprint to create as many room automations as you need; there is no fixed room limit or shared list of personal device IDs to edit. Each instance keeps its own selected devices and uses `single` mode to avoid overlapping runs in that room.

To change a room later, open its automation and edit the blueprint inputs. The player picker can select a different speaker; the light picker can add or remove lamps. The shared dashboard controls continue to apply without rebuilding its cards.

If you enable Memory, create a Text helper with a maximum length sufficient for the sound ID or custom URL and select it only for that room. Do not share the same memory helper across different rooms.

The two configurations in [examples/rooms.yaml](../examples/rooms.yaml) illustrate an Alexa motion room with a light and a Sonos occupancy room without lights. Their entity IDs are fictional placeholders. They are not imported automatically, and both retain `preview: true`.

## Add each room's on/off tile

The shared dashboard intentionally contains only core entities. Add your own room controls with the visual editor:

1. Open the Haunted House dashboard and select **Edit dashboard**.
2. In **Your rooms**, add a **Tile** card.
3. Select the room's **automation entity** using the entity picker, then give the tile a short room name.
4. Set the tile's tap action to **Toggle**, or add its **Toggle** feature. Save the card.
5. Repeat for the other rooms you want to control.

Use the actual entity offered by Home Assistant; an automation's display name does not guarantee its entity ID. Use **Disarm** and wait for active effects to finish before turning a room's tile off or editing its automation: disabling an automation during an effect can cancel the sequence before lights are restored. Its tile then excludes just that room. The global **Haunted House** toggle arms or disarms the whole system, while room automations retain their individual enabled states.

For reference, a room tile looks like this after you choose your own automation:

```yaml
type: tile
entity: automation.haunted_house_hall  # Example only: use your own entity picker result.
name: Hall
icon: mdi:ghost-outline
tap_action:
  action: toggle
features:
  - type: toggle
features_position: inline
grid_options:
  columns: full
```

## Shared controls

| Dashboard section | Controls |
| --- | --- |
| The portal | Global arm/disarm, Disarm action, respect-music preference and Preview guidance. |
| When the shadows arrive | October 31 restriction, optional daily time window and its start/end times. |
| Direct the fright | Sound atmosphere, chance per detection, per-room cooldown and maximum random delay. Cooldown and delay use seconds. |
| Lights and atmosphere | Global light-effects preference, profile and temporary effect brightness. Each room still chooses its own lights. |
| Your rooms | A link to the automation editor and space for the room tiles you add. |
| Footprints in the dark | Last event, effects-requested counter and Restore defaults. |

Global sliders configure the shared engine; they do not change the selected room devices. Room volume and Preview are blueprint inputs, so edit that room's automation to change them. Lights are optional: an empty room selection is audio only even when the global light toggle is on.

The time window uses the Home Assistant time zone and can cross midnight. **Only on October 31** is a separate calendar restriction; turn it off when practising on another date. Preview is configured separately for each room.

**Disarm** stops accepting new effects. Effects already handed to a device may finish, and any in-progress light effect needs to complete its restoration. **Restore defaults** resets the shared controls to the package's defaults; review the confirmation before using it.

## Check the setup

Leave new rooms in Preview and inspect `haunted_house_result` in their automation traces. Preview returns its plan before all automatic gates, so it works without arming the system or changing dates, schedules or room presence. It does not update the last-event panel, counter, memory or cooldown, and does not create scenes or touch devices.

The counter records effects **requested**, not an audio acknowledgement from a device. Once the selected sensors and targets look correct, disable Preview for one room and use a normal presence detection to try its actual effect. Device availability and backend audio support still matter.

The automation editor's **Run actions** command is a manual request: it bypasses the automatic master, date, time, presence, chance, music and cooldown gates. Preview still takes priority, and the global light-effects preference still applies. Use Run actions deliberately after checking the room's Preview setting.

Downloading these files does not change your running Home Assistant instance. You choose whether to install them and select your own room devices in the Home Assistant UI.

## Home Assistant references

- [Using automation blueprints](https://www.home-assistant.io/docs/automation/using_blueprints/)
- [Sections view](https://www.home-assistant.io/dashboards/sections/)
- [Tile card](https://www.home-assistant.io/dashboards/tile/)
- [Markdown card](https://www.home-assistant.io/dashboards/markdown/)
