# Rotom Reader

Reads the game aloud: every text box, battle message and menu, as it appears. It's for anyone who can't read the screen, whether they're too young to read yet, have low vision, or are still learning English. It plays offline from recordings in the mod's own folder, so it works on handhelds and phones with nothing else installed.

Made for Red, Blue and Yellow.

## In game

- Every text box is read page by page: people, signs, the Pokédex and every battle message.
- Menus are read as the cursor moves: the START menu, the bag (each item and how many), the party (each Pokémon, and "fainted" if it has), YES/NO, shops and the PC.
- In battle the menu asks "What will Pikachu do?" and names FIGHT, POKéMON, ITEM or RUN as the cursor moves. The FIGHT list names each move.
- A Pokémon's summary reads its name and level, then its moves on the second page.
- Press **SELECT** while a box is up to hear the page again.
- With **AUTO SCROLL** on, a message moves through its own lines and pages by itself, each new page once the voice has finished the last one. The end of a message still waits for A, so the story never runs ahead of the player.
- With **WAIT FOR VOICE** on, A won't move on until the reading is done. Press B to skip ahead.
- With **SKIP NICKNAMES** on, a new Pokémon keeps its species name: the "give a nickname?" question and the naming screen never come up, for catches or for gifts like Eevee and Lapras.
- **VOICE** picks the narrator: **HEART** (a woman's voice) or **FENRIR** (a man's voice).
- With **CAST VOICES** on, people speak in voices of their own: men in a man's voice, women in a woman's, kids in a younger one, and each person sounds the same every time you talk to them. Signs, items and battle messages stay with the narrator.
- Options (OPTION on the start menu, then Rotom Reader): **ROTOM READER** on or off, **VOICE**, **CAST VOICES**, **VOICE VOL**, **QUIET MUSIC**, **WAIT FOR VOICE**, **AUTO SCROLL** and **SKIP NICKNAMES**.

## Names

Names typed in game can't all be recorded ahead of time, so the mod comes with about 3,000 common first names plus the game's own defaults (RED, ASH, JACK, BLUE, GARY, JOHN). If the player's name isn't one of them, it's read as "Trainer", and the rival's as "your rival". Every nickname the [Name Tags](https://github.com/ElvieBlooms/name_tags) mod can give is recorded too, so a Pokémon it names is called by that name. Any other nickname without a recording is read as the Pokémon's species name.

To have any name read properly, record it with the recorder below (`--names`).

## The voice

The mod comes with two narrators, Heart and Fenrir, plus a cast of eighteen more voices for the people you meet. Every line of Red, Blue and Yellow is recorded whole, so it reads like a phone's screen reader rather than a string of separate words. Behind that sits a **word pack** for each narrator: single words, numbers, and Pokémon, move, item, place and first names, which fill in anything the whole lines don't cover (a name, an amount).

### Recording on a PC

The recorder uses [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M), which needs Python 3.10 to 3.12. With [uv](https://docs.astral.sh/uv/):

    uv venv -p 3.12 kokoro-env
    VIRTUAL_ENV=kokoro-env uv pip install kokoro "misaki[en]" soundfile lupa \
        "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"

Then, from the mod folder:

    # every line of your game, whole (the folder is the one the game imported, e.g. .../pokemon-love2d/yellow)
    kokoro-env/bin/python tools/build_voice.py --game <your game folder> --voice af_heart

    # several games at once: give --game once for each
    kokoro-env/bin/python tools/build_voice.py --game <red folder> --game <blue folder> --voice af_heart

    # the cast: each person's lines in their own voice (tools/cast.py says who gets which)
    kokoro-env/bin/python tools/build_voice.py --game <your game folder> --cast

    # just a name
    kokoro-env/bin/python tools/build_voice.py --names "ZOE,GARY" --voice af_heart

Use `--voice af_heart` for Heart or `--voice am_fenrir` for Fenrir, and run it once for each voice you want to match. The cast needs `ffmpeg` with rubberband to pitch the kids' voices. Clips already recorded are kept, so each run only records what's new. A full game takes a few hours.

### Pronunciation

`tools/pronunciations.json` tells the voice how to say the names it would otherwise guess at: all 151 Pokémon, Pokémon, Pokédex and Poké, and the Kanto towns. It was checked against the guide at [pokee.si/pronounce](https://pokee.si/pronounce). To fix a word, add or change its entry and record it again with `--redo "word"`.

## What it doesn't read yet

- The naming screen, the Pokédex list and the town map.
- Pokémon cries and made-up sounds in dialogue ("Kurukkoo!"). Short unknown words like TMs are spelled out.

## Installing

Download the zip from [Releases](https://github.com/ElvieBlooms/rotom_reader/releases), which includes both voices. Unzip it into the game's `mods` folder, or import the zip in the launcher, and turn it on in the mod list.

The repository holds the code and the recorder, not the recordings: `assets/voice/` and `voice_index.lua` come from `tools/build_voice.py` and ship in the release zip.

## Credits

- Voices: Kokoro-82M by hexgrad (Apache 2.0): af_heart and am_fenrir narrate; the cast is af_bella, af_nicole, af_sarah, af_aoede, af_kore, af_nova, af_sky, bf_emma, bf_isabella, am_michael, am_puck, am_echo, am_eric, am_liam, am_onyx, bm_george, bm_fable and bm_lewis.
- Nicknames: the Name Tags mod's name list.
- Words: dwyl/english-words (public domain).
- Pokémon, move, item and place names: PokéAPI (BSD 3-Clause, © 2013–2023 Paul Hallett and PokéAPI contributors). Pokémon and Pokémon character names are trademarks of Nintendo.
- First names: US Social Security Administration baby-name records (public domain), via hadley/data-baby-names.
- Pronunciations checked against pokee.si/pronounce.

## License

The mod's code and tools are MIT licensed (see `LICENSE`). The lists in `tools/` and the voices keep their own licenses, listed under Credits above.
