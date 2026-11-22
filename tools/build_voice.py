#!/usr/bin/env python3
# Rotom Reader: records the voice clips
# Every clip is a phrase or word, cleaned with the mod's own speech.lua so
# its key matches what the game asks for, recorded, trimmed and levelled
# into assets/voice/, and listed in voice_index.lua. Clips already on disk
# are kept and the index is merged, so running it again only records
# what's new.
#
# Where the phrases come from:
#   --pack       the shareable word pack: single words, Pokémon, move,
#                item and place names, numbers and letters, from the
#                public lists in this folder (pack_*.txt, name_bank.txt),
#                including the Name Tags nicknames (pack_nicknames.txt).
#                No sentences from the game.
#   --game DIR   every line of your own imported game, whole, so lines
#                sound smooth. Made from the game's script, so keep the
#                result on your own devices and don't share it.
#   --names A,B  extra names to record (a player or rival name).
#
# Voices: a Kokoro voice name (af_heart, am_fenrir, ...) or a Piper
# .onnx file. Each voice records into its own folder, assets/voice/<name>/
# (heart, fenrir), and they share one voice_index.lua. Kokoro needs Python 3.10-3.12 with `kokoro`, `misaki[en]`,
# `soundfile` and `lupa` installed (see the README).
#
#   python build_voice.py --pack --voice af_heart
#   python build_voice.py --game ~/.local/share/love/pokemon-love2d/yellow \
#       --voice af_heart --names "MIA,GARY"
# ------------------

import argparse
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)


# ---- The mod's own text rules ----

def lua_runtime():
    from lupa import luajit21
    lua = luajit21.LuaRuntime(unpack_returned_tuples=True)
    speech = lua.execute(open(os.path.join(MOD, "speech.lua"), encoding="utf-8").read())
    return lua, speech


def load_table(lua, path):
    if not os.path.exists(path):
        return None
    return lua.execute(open(path, encoding="utf-8").read())


def arr(t):
    return [t[i] for i in range(1, len(t) + 1)]


def to_py(t):
    """A Lua table as plain lists and dicts."""
    from lupa.luajit21 import lua_type
    if lua_type(t) != "table":
        return t
    keys = list(t.keys())
    if keys and all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
        return [to_py(t[k]) for k in sorted(keys)]
    return {k: to_py(v) for k, v in t.items()}


def clip_id(key):
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


class Phrases:
    """Phrase key -> what the voice is given to say."""

    def __init__(self):
        self.lua, self.speech = lua_runtime()
        self.items = {}

    def add(self, spoken, drop_lead_apostrophe=False):
        speech = self.speech
        spoken = speech.clean(spoken)
        if drop_lead_apostrophe and spoken.startswith("'"):
            # "{USER}'s attack missed": the 's belongs to the name before it
            spoken = spoken.split(" ", 1)[1] if " " in spoken else ""
        words = arr(speech.words(spoken))
        if words:
            self.items.setdefault(" ".join(words), spoken)

    def add_name(self, name, possessive=True):
        self.add(name)
        if possessive:
            self.add(self.speech.clean(name) + "'s")

    def add_basics(self):
        speech = self.speech
        for w in arr(speech.NUMBER_WORDS) + arr(speech.ORDINAL_WORDS):
            self.items.setdefault(w, w)
        for letter, said in speech.LETTERS.items():
            self.items.setdefault("letter " + letter, said)
        self.add("Throw rock")
        # the stand-ins for names nobody recorded
        self.add_name("Trainer")
        self.add_name("Rival")


def read_list(name):
    path = os.path.join(HERE, name)
    return [l.strip() for l in open(path, encoding="utf-8") if l.strip()]


def collect_pack(ph):
    for w in read_list("pack_words.txt"):
        ph.add(w)
    for nm in read_list("pack_names.txt"):
        ph.add_name(nm, possessive=" " not in nm)
    for nm in read_list("pack_pokemon.txt"):
        ph.add_name(nm)
        # the battle menu's question, whole, so it sounds like a question
        ph.add("What will " + nm + " do?")
    bank = read_list("name_bank.txt")
    for i, nm in enumerate(bank):
        # the default names often own things ("BLUE's house"); the rest
        # fall back to the plain name
        ph.add_name(nm, possessive=i < 10)
    # Name Tags nicknames, so a Pokémon it names is called by that name
    for nm in read_list("pack_nicknames.txt"):
        ph.add_name(nm, possessive=False)
    ph.add_basics()


TOKEN = re.compile(r"\{[^}]*\}")


def pieces(lua, speech, value):
    """The spoken pieces of one text entry: each page, split at the game's
    {PLAYER}-style codes, lines joined. Yields (text, piece number)."""
    value = re.sub(r"\{(DONE|PROMPT)\}", "", value.replace("\1", ""))
    for page in value.split("\f"):
        if not page.strip():
            continue
        for n, piece in enumerate(TOKEN.split(page)):
            lines = arr(speech.splitLines(piece))
            yield speech.joinLines(lua.table_from(lines)), n


def collect_cast(ph, game):
    """Every line a person says, with the voice that person gets
    (tools/cast.py). Returns {key: (spoken, voice, semitones)}; lines of
    fewer than three words are left to the narrator's word pack."""
    sys.path.insert(0, HERE)
    import cast
    lua, speech = ph.lua, ph.speech
    gen = os.path.join(game, "data", "generated")
    text = to_py(load_table(lua, os.path.join(gen, "text.lua")))
    maps = to_py(load_table(lua, os.path.join(gen, "maps.lua")))
    maps = list(maps.values()) if isinstance(maps, dict) else maps
    if not os.path.exists(os.path.join(gen, "text_pointers.lua")):
        return collect_cast_gen2(ph, cast, gen, text, maps)
    ptrs = to_py(load_table(lua, os.path.join(gen, "text_pointers.lua")))
    heads = to_py(load_table(lua, os.path.join(gen, "trainer_headers.lua")))
    heads = {k: ({i + 1: x for i, x in enumerate(v)} if isinstance(v, list) else v)
             for k, v in heads.items()}
    labels = sorted(k for k, v in text.items() if isinstance(k, str) and isinstance(v, str))
    who = cast.speakers(maps, ptrs, heads, labels)
    for k in labels:
        if k not in who:
            tag = cast.tagged_speaker(text[k])
            if tag:
                who[k] = tag
    out = {}
    for k in labels:
        if k not in who or cast.narrated(text[k]):
            continue
        voice, semis = cast.voice_for(*who[k])
        for joined, n in pieces(lua, speech, text[k]):
            spoken = speech.clean(joined)
            if n > 0 and spoken.startswith("'"):
                spoken = spoken.split(" ", 1)[1] if " " in spoken else ""
            words = arr(speech.words(spoken))
            if len(words) >= 3:
                out.setdefault(" ".join(words), (spoken, voice, semis))
    return out


def cast_pieces(ph, out, value, voice, semis):
    lua, speech = ph.lua, ph.speech
    for joined, n in pieces(lua, speech, value):
        spoken = speech.clean(joined)
        if n > 0 and spoken.startswith("'"):
            spoken = spoken.split(" ", 1)[1] if " " in spoken else ""
        words = arr(speech.words(spoken))
        if len(words) >= 3:
            out.setdefault(" ".join(words), (spoken, voice, semis))


def collect_cast_gen2(ph, cast, gen, text, maps):
    scripts = to_py(load_table(ph.lua, os.path.join(gen, "scripts.lua")))
    who = cast.speakers_gen2(maps, scripts, text)
    out = {}
    for k in sorted(who):
        if cast.narrated(text[k]):
            continue
        voice, semis = cast.voice_for(*who[k])
        cast_pieces(ph, out, text[k], voice, semis)
    return out


GEN2_PRESETS = ("GOLD", "HIRO", "TAYLOR", "KARL", "SILVER", "KAMON", "OSCAR", "MAX",
                "CHRIS", "MAT", "ALLAN", "JON", "KRIS", "AMANDA", "JUANA", "JODI")

# Gen 2 keeps game text in more places than text.lua: battle and engine
# lines in rom_text.lua, trainer and trade chatter in trainers.lua and
# events.lua. A string there counts as text if it reads like a text box.
EXTRA_TEXT = ("rom_text.lua", "events.lua", "trainers.lua")
TEXTLIKE = re.compile(r"\{(DONE|PROMPT)\}|[\n\v\f]")


def walk_strings(t, out, depth=0):
    if isinstance(t, str):
        out.append(t)
        return
    if depth > 8 or t is None or isinstance(t, (int, float, bool)):
        return
    try:
        values = list(t.values())
    except Exception:
        return
    for v in values:
        walk_strings(v, out, depth + 1)


def game_strings(lua, gen, text):
    out = [v for v in text.values() if isinstance(v, str)]
    for fname in EXTRA_TEXT:
        t = load_table(lua, os.path.join(gen, fname))
        if t is None:
            continue
        found = []
        walk_strings(t, found)
        out.extend(v for v in found if TEXTLIKE.search(v) and " " in v)
    return out


def collect_game(ph, game):
    lua, speech = ph.lua, ph.speech
    gen = os.path.join(game, "data", "generated")
    text = load_table(lua, os.path.join(gen, "text.lua"))
    if text is None:
        sys.exit("no data/generated/text.lua in " + game)
    words = {}
    for value in game_strings(lua, gen, text):
        for joined, n in pieces(lua, speech, value):
            ph.add(joined, drop_lead_apostrophe=n > 0)
            for w in speech.clean(joined).split(" "):
                ws = arr(speech.words(w))
                if len(ws) == 1:
                    words.setdefault(ws[0], w.strip(".,!?:;\"()"))

    def name_list(fname):
        t = load_table(lua, os.path.join(gen, fname))
        out = []
        for _, rec in (t.items() if t is not None else []):
            try:
                nm = rec["name"]
            except Exception:
                nm = None
            if isinstance(nm, str):
                out.append(nm)
        return out

    # the names the game offers the player and rival (Gen 2's NamePick)
    if os.path.exists(os.path.join(gen, "scripts.lua")):
        for nm in GEN2_PRESETS:
            ph.add_name(nm)
    mons = name_list("pokemon.lua")
    for nm in mons + name_list("moves.lua") + name_list("items.lua") + name_list("trainers.lua"):
        ph.add_name(nm)
    for nm in mons:
        ph.add("What will " + nm + " do?")
    for key, spoken in words.items():
        ph.items.setdefault(key, spoken)
    ph.add_basics()


# ---- Levelling ----
# Every clip is levelled to this loudness (dB, voiced parts only) so
# stitched words match, and kept under PEAK_DB so nothing clips.
TARGET_DB = -16.0
PEAK_DB = -4.0


def level(audio):
    import numpy as np
    audio = np.asarray(audio, dtype=np.float32)
    n = 512
    frames = [audio[i:i + n] for i in range(0, max(1, len(audio) - n), n)] or [audio]
    energy = np.array([np.sqrt(np.mean(f ** 2)) for f in frames])
    voiced = energy[energy > 0.01] if (energy > 0.01).any() else energy
    loud = 20 * np.log10(float(np.mean(voiced)) + 1e-9)
    gain = 10 ** ((TARGET_DB - loud) / 20)
    peak = float(np.max(np.abs(audio))) * gain
    limit = 10 ** (PEAK_DB / 20)
    if peak > limit:
        gain *= limit / peak
    return audio * gain


def finish(audio, rate, path):
    """Trim the quiet at both ends, level, and write the clip (.mp3 or .ogg
    by the path's extension)."""
    import numpy as np
    import soundfile as sf
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    loud = np.where(np.abs(audio) > 0.02)[0]
    if len(loud):
        a = max(0, loud[0] - int(rate * 0.02))
        b = min(len(audio), loud[-1] + int(rate * 0.06))
        audio = audio[a:b]
    mp3 = path.endswith(".mp3")
    # MP3 adds about 50 ms of silence at the start of every clip, so it gets
    # less of a gap at the end and stitched words keep the same spacing
    tail = 0.01 if mp3 else 0.06
    audio = np.concatenate([level(audio), np.zeros(int(rate * tail), dtype=np.float32)])
    if mp3:
        fmt = dict(format="MP3", subtype="MPEG_LAYER_III", compression_level=0.8,
                   bitrate_mode="CONSTANT")
    else:
        # Vorbis's lowest quality setting: still clear for speech, and about
        # 15% smaller than the old MP3 clips
        fmt = dict(format="OGG", subtype="VORBIS", compression_level=0.99)
    tmp = path + ".tmp"
    sf.write(tmp, audio, rate, **fmt)
    # the encoder can overshoot a little; pull it back if it clipped
    for _ in range(3):
        back, _r = sf.read(tmp, dtype="float32")
        if np.max(np.abs(back)) <= 0.99:
            break
        audio = audio * 0.8
        sf.write(tmp, audio, rate, **fmt)
    os.replace(tmp, path)


# ---- Voices ----

def load_pronunciations(extra=None):
    out = {}
    for path in [os.path.join(HERE, "pronunciations.json")] + ([extra] if extra else []):
        d = json.load(open(path, encoding="utf-8"))
        out.update({k: v for k, v in d.items() if not k.startswith("_")})
    return out


class KokoroVoice:
    rate = 24000

    def __init__(self, voice, speed, pron=None):
        import torch
        torch.set_num_threads(os.cpu_count() or 1)
        self.pron = load_pronunciations(pron)
        self.pipes = {}
        self.voice, self.speed = voice, speed

    def pipe(self, voice):
        # American (a) and British (b) voices each need their own pipeline
        lang = voice[0] if voice[0] in "ab" else "a"
        if lang not in self.pipes:
            from kokoro import KPipeline
            p = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
            golds = p.g2p.lexicon.golds
            for word, ph in self.pron.items():
                for k in {word, word.lower(), word.upper(), word.capitalize()}:
                    golds[k] = ph
            self.pipes[lang] = p
        return self.pipes[lang]

    def say(self, text, voice=None):
        import numpy as np
        voice = voice or self.voice
        parts = [a.numpy() for _, _, a in self.pipe(voice)(text, voice=voice, speed=self.speed)
                 if a is not None]
        return np.concatenate(parts) if parts else None


def pitch(audio, rate, semitones):
    """Raise a clip's pitch without changing its speed (ffmpeg rubberband)."""
    import subprocess
    import numpy as np
    if not semitones:
        return audio
    ratio = 2 ** (semitones / 12)
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(rate), "-ac", "1", "-i", "-",
         "-af", f"rubberband=pitch={ratio:.4f}:formant=preserved", "-f", "f32le", "-"],
        input=np.asarray(audio, dtype=np.float32).tobytes(), capture_output=True, check=True)
    return np.frombuffer(out.stdout, dtype=np.float32)


# Piper: a few words it gets wrong, as phonemes. Each pattern is what the
# voice produces on its own, stress marks optional.
SAY_LIKE = [
    (r"p[ˈˌ]?ɑːkeɪmən", "pˈoʊkeɪmˌɑːn"),        # Pokémon: POH-kay-mon
    (r"p[ˈˌ]?ɑːkeɪd[ˈˌ]?ɛks", "pˈoʊkeɪdˌɛks"),  # Pokédex
    (r"pək[ˈˌ]?eɪ", "pˈoʊkeɪ"),                  # Poké Ball, Poké Mart
]


class PiperVoice:
    def __init__(self, model, speed, pron=None):
        from piper import PiperVoice as PV, SynthesisConfig
        self.v = PV.load(model)
        self.cfg = SynthesisConfig(length_scale=1.0 / speed)
        self.rate = self.v.config.sample_rate

    def say(self, text):
        import numpy as np
        pieces = []
        for sentence in self.v.phonemize(text):
            ph = "".join(sentence)
            for pat, rep in SAY_LIKE:
                ph = re.sub(pat, rep, ph)
            out = self.v.phoneme_ids_to_audio(self.v.phonemes_to_ids(list(ph)), self.cfg)
            out = out[0] if isinstance(out, tuple) else out
            if pieces:
                pieces.append(np.zeros(int(self.rate * 0.15), dtype=np.float32))
            pieces.append(np.asarray(out, dtype=np.float32).reshape(-1))
        return np.concatenate(pieces) if pieces else None


# ---- The index ----

def lua_quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def read_index(lua, path):
    t = load_table(lua, path)
    if t is None:
        return {}
    return {k: v for k, v in t["clips"].items()}


def write_index(path, clips, voice_root):
    # a phrase is listed when at least one voice has it; the mod falls back
    # to another voice for a clip the chosen one lacks
    have = set()
    for d in os.listdir(voice_root):
        sub = os.path.join(voice_root, d)
        if os.path.isdir(sub):
            have |= {f[:-4] for f in os.listdir(sub) if f.endswith((".mp3", ".ogg"))}
    clips = {k: v for k, v in clips.items() if v in have}
    longest = max([len(k.split(" ")) for k in clips] or [1])
    with open(path, "w", encoding="utf-8") as f:
        f.write("-- Made by tools/build_voice.py. Phrase key -> clip file in assets/voice/<voice>/.\n")
        f.write("return {\n  maxWords = %d,\n  clips = {\n" % longest)
        for key in sorted(clips):
            f.write("    [%s] = \"%s\",\n" % (lua_quote(key), clips[key]))
        f.write("  },\n}\n")
    return len(clips)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", action="store_true", help="record the shareable word pack")
    ap.add_argument("--game", action="append", default=[],
                    help="imported game folder, to record every line whole; give it once per game (Red, Blue, Yellow)")
    ap.add_argument("--cast", action="store_true",
                    help="with --game: record each person's lines in their own voice (tools/cast.py) into assets/voice/cast")
    ap.add_argument("--names", default="", help="comma-separated extra names to record")
    ap.add_argument("--voice", default="af_heart", help="Kokoro voice (af_heart) or Piper .onnx file")
    ap.add_argument("--speed", type=float, default=0.95, help="speaking speed, 1 is normal")
    ap.add_argument("--mod", default=MOD, help="the mod folder to record into")
    ap.add_argument("--pron", help="an extra pronunciations file, like tools/pronunciations.json, for your own names")
    ap.add_argument("--format", choices=["ogg", "mp3"], default="ogg",
                    help="ogg (the default) is a little smaller and plays everywhere LÖVE does")
    ap.add_argument("--folder", help="voice folder under assets/voice (default: from the voice name, af_heart -> heart)")
    ap.add_argument("--redo", default="", help="record again every clip whose text matches this pattern")
    ap.add_argument("--dry", action="store_true", help="count what would be recorded, record nothing")
    args = ap.parse_args()
    if not (args.pack or args.game or args.names):
        ap.error("choose --pack, --game or --names")

    ph = Phrases()
    if args.cast:
        if not args.game:
            ap.error("--cast needs --game")
        return record_cast(ph, args)
    if args.pack:
        collect_pack(ph)
    for game in args.game:
        collect_game(ph, os.path.expanduser(game))
    for nm in (n.strip() for n in args.names.split(",")):
        if nm:
            ph.add_name(nm)

    folder = args.folder or os.path.basename(args.voice).split(".")[0].split("_", 1)[-1].split("-")[0]
    out_dir = os.path.join(args.mod, "assets", "voice", folder)
    index_path = os.path.join(args.mod, "voice_index.lua")
    os.makedirs(out_dir, exist_ok=True)
    clips = read_index(ph.lua, index_path)
    redo = re.compile(args.redo, re.I) if args.redo else None
    jobs = []
    for key, spoken in sorted(ph.items.items()):
        cid = clip_id(key)
        clips[key] = cid
        path = os.path.join(out_dir, cid + "." + args.format)
        if not os.path.exists(path) or (redo and redo.search(spoken)):
            jobs.append((path, spoken))
    print(f"{len(ph.items)} phrases, {len(jobs)} to record", flush=True)
    if args.dry:
        return

    voice = (PiperVoice if args.voice.endswith(".onnx") else KokoroVoice)(args.voice, args.speed, args.pron)
    for done, (path, spoken) in enumerate(jobs, 1):
        audio = voice.say(spoken)
        if audio is not None and len(audio):
            finish(audio, voice.rate, path)
        if done % 250 == 0:
            print(f"  {done}/{len(jobs)}", flush=True)
            write_index(index_path, clips, os.path.dirname(out_dir))
    n = write_index(index_path, clips, os.path.dirname(out_dir))
    print(f"wrote voice_index.lua with {n} clips")


def record_cast(ph, args):
    lines = {}
    for game in args.game:
        for key, line in collect_cast(ph, os.path.expanduser(game)).items():
            lines.setdefault(key, line)
    out_dir = os.path.join(args.mod, "assets", "voice", args.folder or "cast")
    index_path = os.path.join(args.mod, "voice_index.lua")
    os.makedirs(out_dir, exist_ok=True)
    clips = read_index(ph.lua, index_path)
    redo = re.compile(args.redo, re.I) if args.redo else None
    jobs = []
    for key, (spoken, voice, semis) in sorted(lines.items()):
        cid = clip_id(key)
        clips[key] = cid
        path = os.path.join(out_dir, cid + "." + args.format)
        if not os.path.exists(path) or (redo and redo.search(spoken)):
            jobs.append((path, spoken, voice, semis))
    voices = sorted({j[2] for j in jobs})
    print(f"{len(lines)} cast lines, {len(jobs)} to record, {len(voices)} voices", flush=True)
    if args.dry:
        return
    kv = KokoroVoice(args.voice, args.speed, args.pron)
    # one voice at a time, so each pipeline's voice stays loaded
    jobs.sort(key=lambda j: (j[2], j[0]))
    for done, (path, spoken, voice, semis) in enumerate(jobs, 1):
        audio = kv.say(spoken, voice)
        if audio is not None and len(audio):
            finish(pitch(audio, kv.rate, semis), kv.rate, path)
        if done % 250 == 0:
            print(f"  {done}/{len(jobs)}", flush=True)
            write_index(index_path, clips, os.path.dirname(out_dir))
    n = write_index(index_path, clips, os.path.dirname(out_dir))
    print(f"wrote voice_index.lua with {n} clips")


if __name__ == "__main__":
    main()
