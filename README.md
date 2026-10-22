# Haunted House 🎃

**Presence-triggered spooky audio and gentle light effects for Home Assistant.**

[Italiano](#italiano) · [English installation](#installation) · [Audio compatibility](docs/AUDIO.md) · [Dashboard](docs/DASHBOARD.md)

![Home Assistant 2026.10.2+](https://img.shields.io/badge/Home_Assistant-2026.10.2%2B-18BCF2)
![Release](https://img.shields.io/badge/release-0.1.0--beta.1-orange)
![License](https://img.shields.io/badge/code-MIT-green)

An install-once **package** supplies shared controls and effects. A **blueprint** supplies a form for each room: choose its name, movement/presence sensors, speaker, integration, lights or light groups, volume, and optional audio files. Create as many room instances as needed (up to 30 simultaneous effects). No room names, device IDs, IP addresses, tokens, or recordings from the original house are included.

[![Import room blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Flucaamo%2Fhome-assistant-haunted-house%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fhaunted_house%2Froom.yaml)

**Install the package before using the blueprint.** This is a beta distribution: configuration and templates are checked, but compatibility still depends on your speaker/light integration. See [validation](docs/VALIDATION.md) for exactly what was tested.

## What you can control

- Global enable/disarm; individual rooms use their automation's enable switch.
- Optional time window, including overnight windows, and October 31-only mode.
- Chance of an effect, maximum random delay, and a cooldown independent for each room.
- Nine sound references in three intensities; optional custom files for Sonos/other players.
- Alexa Media Player, Sonos announcements, and a generic media-player mode.
- Violet, pumpkin-orange, and cold apparition light profiles, chosen by sound or fixed.
- Slow 5–8-second light pulses. Color-capable lights use color; white dimmable lights use brightness. On/off-only targets are skipped.
- Per-lamp light snapshots, including lights initially off. Hue/native light-group membership is resolved at run time, including nested groups up to eight levels.
- Silent preview, manual room tests, requested-effect count and diary.
- Optional per-room `input_text` memory to avoid an immediate repeat.

## Installation

Requires **Home Assistant Core 2026.10.2 or newer**. It uses the current `motion.detected` / `occupancy.detected` triggers and current media-action format. No HACS frontend cards are required. Alexa audio requires the third-party [Alexa Media Player integration](https://github.com/alandtse/alexa_media_player); Sonos uses the built-in [Sonos integration](https://www.home-assistant.io/integrations/sonos/).

1. Download/clone this repository. Back up any configuration file you will edit.
2. Copy `packages/haunted_house.yaml` to `/config/packages/haunted_house.yaml`.
3. If packages are not already enabled, merge this into your **existing** `homeassistant:` block in `configuration.yaml`. Do not create a duplicate block or replace an existing packages include:

   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```

   If you use `!include_dir_merge_named` instead, the package needs an outer `haunted_house:` key. This repository is laid out for `!include_dir_named`.

4. Run **Tools → YAML → Check configuration**, then restart HA once to load the package. Initialization runs once: master **off**, October 31-only **on**, time window **18:00–23:00**, chance **100%**, delay **0–4 s**, room cooldown **300 s**, light peak **35%**. Subsequent restarts restore your settings; the defaults script does not run again. The **Reset defaults** command intentionally disarms and resets those settings.
5. Import the blueprint with the button above, or copy `blueprints/automation/haunted_house/room.yaml` to the same path under `/config/` and reload automations.
6. In **Settings → Automations & scenes → Blueprints**, select **Haunted House · A room comes alive** and create one automation per room. Choose:

   | Input | What to select |
   | --- | --- |
   | Room name | Any label, such as “Hallway” or “Cinema” |
   | Sensors / kind | One or more motion sensors **or** occupancy sensors; choose the matching kind |
   | Speaker / integration | The actual player and `alexa`, `sonos`, or `generic` backend |
   | Lights | Optional individual lights or light groups |
   | Controller | **Haunted House · Effect controller** (`script.haunted_house_effect`) |
   | Silent preview | Leave **on** for commissioning |

   With several sensors, `behavior: first` means a new effect is triggered when the room goes from no selected sensors detecting to at least one detecting. Continuous presence does not replay a sound; all selected sensors must clear before a new entry.

7. Choose **Run actions** and inspect the trace, including `haunted_house_result`. Preview returns before all automatic gates, scenes, device calls, helper changes, and cooldown. It is a silent routing check, not proof of audible playback. Check your entities and backend, then turn **Silent preview off** and run one deliberate manual test.
8. Add the optional [native dashboard](docs/DASHBOARD.md). Configure the date/time switches and enable **Haunted House** for automatic runs. Disable October 31-only mode to use it on other dates.

Example automation instances are in [examples/rooms.yaml](examples/rooms.yaml). They contain fictional entities: replace them with your own, or use the UI instead. Optional `media_urls` are used by Sonos/generic, while Alexa uses soundbank IDs. Set `custom_duration` to at least your longest file's length; generic playback is stopped after that duration plus two seconds.

For no immediate repeats, create one **Text helper** per room in HA, with a maximum length sufficient for the sound ID or your longest URL, and select only that helper in the optional **Last-sound memory** input. It is not required. Without it, each choice is independently random and may repeat.

## Behavior and recovery

**Disarm with the master switch or `script.haunted_house_disarm`.** This cancels pending random waits and prevents new effects. Audio/light effects already sent finish and attempt their snapshots' restore; disarming also releases cooldown waits. It does not immediately stop a remote audio clip.

Manual **Run actions** bypasses master, calendar, schedule, presence, chance, music guard, and cooldown; it still respects silent preview and the global light-effect switch. Keep volume modest for the first audible test.

Each room automation is `single` and synchronously waits for the controller through playback, light cleanup and cooldown. Cooldown starts **after** an automatic effect finishes; it is an in-memory wait and resets after reload/restart. It does not run after previews, skipped/offline players, or manual tests. Counts describe requests, not proof that sound was heard; a failed remote audio request can still be counted.

Assign each physical speaker and light to **one room automation**. Two automations sharing devices, or group members overlapping another room, can overwrite one another's effects and snapshots. Do not call the controller directly in parallel with the same room key. The names of snapshot scenes derive from the automation's entity ID, not from its free-text room label.

Stopping a running script/automation, reloading scripts, or restarting HA can interrupt cleanup. Disarm first, allow the current effect to finish, then edit or reload. A lamp that was offline at snapshot time has no usable previous state; if it comes online mid-effect, the group may reach it without a restorable snapshot. Manual light changes made during an effect are replaced by the captured state at cleanup.

Sonos announcements usually preserve current music on supported devices. Generic media playback may replace music; media snapshots provide best-effort recovery, with no universal guarantee of restoring queues, position or grouped playback. Alexa uses a cloud service, so audio and light starts are approximate. “Respect music” skips automatic Alexa/generic effects while the player reports `playing`; it is not a TV-activity or do-not-disturb detector.

## Updating, uninstalling and development

Back up your package before replacing it, disarm, wait for effects to finish, replace the file, check configuration, restart. Re-import the blueprint from the same URL. Do not rename input keys casually; room instances store them. The package is single-instance with a shared `haunted_house_` namespace; multiple rooms use the same controller.

To uninstall: disarm, let effects finish, delete room automation instances and the dashboard view, remove the package file and blueprint, check configuration and restart. Remove the `packages:` include only if you added it solely for this project. Snapshot scenes are temporary and disappear on restart.

The editable source is `tools/build.py` plus `assets/sounds.json`; `packages/haunted_house.yaml` is the generated installable output. Build with `python3 tools/build.py` (requires Ruby's standard YAML library). Run `python3 tools/lint.py`, `python3 -m unittest discover -s tests -v`, and, with the pinned HA development dependencies, `python3 tools/validate_ha.py --json`. See [validation](docs/VALIDATION.md) for the supported environment. Only repository files are shipped; local household exports and backups are excluded.

## Italiano

**Haunted House è il package generico derivato dalle automazioni di Halloween.** Si installa il package una volta e si crea un’automazione dal blueprint per ogni stanza. Il modulo di HA permette di scegliere nome, sensori, luci/gruppi e media player, senza modificare il codice del motore.

L’installazione è descritta sopra: abilita i package, copia `packages/haunted_house.yaml`, controlla la configurazione e riavvia. Importa il blueprint dal pulsante, scegli il controller e i dispositivi, prova con **Silent preview acceso**, controlla la traccia, poi disattiva l’anteprima per una prova reale. Per usarlo prima del 31 ottobre, spegni **Only October 31**. La [dashboard](docs/DASHBOARD.md) contiene i comandi globali; puoi aggiungere dall’interfaccia una tile per ciascuna automazione stanza.

Il master **Disarm** blocca i nuovi effetti e lascia finire i ripristini. Evita di fermare gli script o riavviare durante un effetto. I dispositivi condivisi tra stanze possono interferire: assegna ogni luce e altoparlante a una sola automazione. Nessuna registrazione audio è inclusa: il catalogo contiene soltanto riferimenti; per Sonos/altri player puoi scegliere URL di file che hai diritto di usare.

## Credits and license

Inspired by Henrik Sozzi's discussion of [personal Alexa notifications in Home Assistant](https://henriksozzi.it/2022/08/notifiche-alexa-in-home-assistant-piu-personali/). No article text or code is copied. Developed from a household setup into a separate, parameterized community project.

Code and documentation: [MIT](LICENSE). Referenced sounds, trademarks and linked third-party services remain subject to their owners' terms. The MIT license does **not** license Amazon recordings. See [audio sources and limits](docs/AUDIO.md).
