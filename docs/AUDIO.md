# Audio backends and sound catalogue / Audio e catalogo suoni

Documentation checked: **2026-10-22**. This document describes backend capabilities; it does not install anything or run playback tests.

## Italiano

### Catalogo e provenienza

[`../assets/sounds.json`](../assets/sounds.json) contiene nove riferimenti audio, senza file MP3. Ogni record ha `id` stabile, `label` italiana, `label_en`, `level` (1–3, classificazione editoriale del progetto), `duration` nominale in secondi, `soundbank`, `url`, `path` e `official_name`. Le durate e i percorsi provengono dall’[indice pubblico Amazon](https://m.media-amazon.com/images/G/01/mobile-apps/dex/ask-tech-docs/ask-soundlibrary._TTH_.json), caricato dalla [pagina ufficiale ASK Sound Library](https://developer.amazon.com/en-US/docs/alexa/custom-skills/ask-soundlibrary.html).

Gli URL `url` sono **anteprime esterne Amazon**, non asset del progetto. Il 22 ottobre 2026 i nove endpoint hanno risposto a HEAD con HTTP 200 e `audio/mpeg`; questo non garantisce disponibilità futura, riproduzione su ogni dispositivo o diritti di riutilizzo. La documentazione Amazon descrive l’uso nella risposta Alexa e limita l’accesso diretto ai file. **Questo repository non distribuisce MP3 e non concede una licenza sui suoni Amazon.** La licenza del codice non si estende a quegli asset. Per una distribuzione autonoma usare registrazioni proprie o audio con licenza adeguata, documentandone autore, fonte e condizioni.

### Alexa Media Player

Il backend `alexa` richiede l’integrazione custom Alexa Media Player. Usa `notify.alexa_media`, un singolo Echo come `target` e `data.type: tts`; il messaggio contiene `<audio src="soundbank://soundlibrary/…"/>`. Non usare `announce` per il tag audio: la wiki dell’integrazione lo esclude. TTS non offre sincronizzazione fra dispositivi né supporto ai gruppi Whole House Audio. [Wiki delle notifiche](https://github.com/alandtse/alexa_media_player/wiki/Configuration:-Notification-Component)

Un file proprio può essere usato come sorgente SSML solo se rispetta i requisiti Amazon: MP3 MPEG-2, 48 kbps, 16/22,05/24 kHz, endpoint HTTPS pubblico con certificato valido e durata entro i limiti SSML. Un URL locale HTTP non basta; la compatibilità con un normale player MP3 non prova quella con Alexa. [Specifiche SSML audio](https://developer.amazon.com/en-US/docs/alexa/custom-skills/speech-synthesis-markup-language-ssml-reference.html#audio)

`data.volume` non viene inoltrato dal servizio notify attuale. Per cambiare volume serve `media_player.volume_set`; modificare e poi ripristinare soltanto quando il volume precedente è numerico e disponibile. Se manca, mantenere il volume corrente. Lo snapshot non ricostruisce un attributo assente e la latenza cloud impedisce di dedurre con precisione la fine audio dalla sola durata del catalogo. [Implementazione notify](https://github.com/alandtse/alexa_media_player/blob/dev/custom_components/alexa_media/notify.py)

### Sonos diretto

Il backend `sonos` usa l’entità dell’integrazione **Sonos**, con `media_player.play_media`, URL raggiungibile dal diffusore, tipo `music`, `announce: true` e `extra.volume` intero 0–100. Sonos sovrappone l’effetto, attenua la musica e ripristina il livello precedente. Hardware datato o firmware S1 possono non supportare pienamente questa modalità. Per gli annunci Home Assistant deve poter raggiungere TCP 1443 sul Sonos. [Documentazione Sonos](https://www.home-assistant.io/integrations/sonos/#playing-media)

### Player generico

Il backend `generic` usa `media_player.play_media` con `url` e tipo `music`. Supporto URL, codec, annunci e ripresa dipendono dall’integrazione: il dominio `media_player` non li garantisce. `announce: true` su un player senza supporto può lasciare la musica interrotta. Impostare il volume con `volume_set` richiede un valore **0–1**, non 0–100; non inviare `extra.volume` di Sonos a backend generici. Un ripristino del volume non equivale al ripristino di coda, sorgente o posizione. [Play specified media](https://www.home-assistant.io/actions/media_player.play_media/), [Volume](https://www.home-assistant.io/actions/media_player.volume_set/)

## English

### Catalogue and media notices

`assets/sounds.json` bundles metadata and external references only. `level` is this project’s editorial intensity rating; `duration` is nominal, not a playback completion signal. English labels and stable IDs carry no household-specific information.

Amazon’s library and public metadata index are the sources linked above. The preview endpoints returned HTTP 200 on **2026-10-22**. Reachability is not a redistribution licence or a long-term hosting commitment. **No Amazon MP3 files are included, and this project grants no rights to those recordings.** Replace external previews with original or appropriately licensed audio when distributing a self-contained collection; keep its separate attribution and licence records.

### Backend behaviour

| Backend | Content | Volume | Playback behaviour |
|---|---|---|---|
| `alexa` | `notify.alexa_media`, TTS, SSML `audio` using `soundbank` | Separate `volume_set`, 0–1; preserve current level if unknown | Individual Echo; cloud-dependent |
| `sonos` | `play_media`, directly reachable `url`, type `music`, `announce: true` | `extra.volume`, integer 0–100 | Supported Sonos devices overlay and restore volume |
| `generic` | `play_media`, `url`, type `music` | Optional separate `volume_set`, 0–1 | Format and interruption/resume support vary |

The [Alexa Media Player wiki](https://github.com/alandtse/alexa_media_player/wiki/Configuration:-Notification-Component) documents the TTS/announce distinction. Its [current notify implementation](https://github.com/alandtse/alexa_media_player/blob/dev/custom_components/alexa_media/notify.py) does not pass a per-notification volume. Avoid changing an unknown volume or assuming a snapshot restores missing data.

Custom Alexa audio needs public HTTPS and the encoding/duration requirements in the [Amazon SSML reference](https://developer.amazon.com/en-US/docs/alexa/custom-skills/speech-synthesis-markup-language-ssml-reference.html#audio). A file playable by Sonos is not automatically Alexa-compatible. The project’s default Alexa route uses the catalogue `soundbank`, not its preview `url`.

The [Sonos integration](https://www.home-assistant.io/integrations/sonos/#playing-media) supplies its announcement overlay. The [generic action](https://www.home-assistant.io/actions/media_player.play_media/) leaves content and announcement support to each integration. Do not advertise universal queue recovery or sample-accurate synchronization. A successful service call confirms dispatch, not audible output.

## Recommended backend contract / Contratto consigliato

This is a capability contract for adapters, not a claim that every player supports every field:

- Input: one configured `player` entity, explicit backend `alexa` / `sonos` / `generic`, selected sound record, requested `volume_pct` clamped to 0–100, and dry-run flag.
- `alexa` requires `soundbank`; `sonos` and `generic` require `url`. Do not pass a `soundbank://` URI to an HTTP media player. Custom HTTPS Alexa audio is a separate, explicitly validated extension.
- Resolve availability and overlap guards **before** temporary changes. One run per physical speaker avoids competing snapshots. Room-level locks alone are insufficient if two rooms share a speaker.
- Dry-run returns backend, target, content reference and intended volume without services, snapshots, timers, lights or counters.
- Sonos delegates temporary volume to its announcement path. Alexa/generic change volume only when they can restore a known value; ensure the restore step remains reachable after playback errors. Use backend-specific restore guarantees rather than promising generic media recovery.
- Report `skipped`, `dispatched` or `error`. Reserve `heard`/`verified` for a real output check. Skip offline targets rather than queueing stale surprises.

## Attribution and reference dates / Attribuzione e date

The creative starting point was Henrik Sozzi’s [“Notifiche Alexa più personali con Home Assistant”](https://henriksozzi.it/2022/08/notifiche-alexa-in-home-assistant-piu-personali/), first published 2022-08-06, which mentions eerie Halloween sounds. This project acknowledges that inspiration; no article code or prose has been copied.

All linked technical references and the inspiration article were checked on **2026-10-22**. The Alexa Media Player source link targets a moving branch; integrations, schemas, cloud behaviour and external audio endpoints can change. Confirm the installed integration’s action schema and perform an intentional low-volume device test after installation.
