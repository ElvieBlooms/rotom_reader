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
#                public lists in this folder (pack_*.txt, name_bank.txt).
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
    ph.add_basics()


def collect_game(ph, game):
    lua, speech = ph.lua, ph.speech
    gen = os.path.join(game, "data", "generated")
    text = load_table(lua, os.path.join(gen, "text.lua"))
    if text is None:
        sys.exit("no data/generated/text.lua in " + game)
    token = re.compile(r"\{[^}]*\}")
    words = {}
    for _, value in text.items():
        if not isinstance(value, str):
            continue
        value = re.sub(r"\{(DONE|PROMPT)\}", "", value.replace("\1", ""))
        for page in value.split("\f"):
            if not page.strip():
                continue
            for n, piece in enumerate(token.split(page)):
                lines = arr(speech.splitLines(piece))
                joined = speech.joinLines(lua.table_from(lines))
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
        fmt = dict(format="OGG", subtype="VORBIS")
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
        from kokoro import KPipeline
        torch.set_num_threads(os.cpu_count() or 1)
        lang = voice[0] if voice[0] in "ab" else "a"
        self.pipe = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
        golds = self.pipe.g2p.lexicon.golds
        for word, ph in load_pronunciations(pron).items():
            for k in {word, word.lower(), word.upper(), word.capitalize()}:
                golds[k] = ph
        self.voice, self.speed = voice, speed

    def say(self, text):
        import numpy as np
        parts = [a.numpy() for _, _, a in self.pipe(text, voice=self.voice, speed=self.speed)
                 if a is not None]
        return np.concatenate(parts) if parts else None


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
    ap.add_argument("--game", help="imported game folder, to record every line whole")
    ap.add_argument("--names", default="", help="comma-separated extra names to record")
    ap.add_argument("--voice", required=True, help="Kokoro voice (af_heart) or Piper .onnx file")
    ap.add_argument("--speed", type=float, default=0.95, help="speaking speed, 1 is normal")
    ap.add_argument("--mod", default=MOD, help="the mod folder to record into")
    ap.add_argument("--pron", help="an extra pronunciations file, like tools/pronunciations.json, for your own names")
    ap.add_argument("--format", choices=["mp3", "ogg"], default="mp3",
                    help="mp3 is about half the size; ogg is the older format")
    ap.add_argument("--folder", help="voice folder under assets/voice (default: from the voice name, af_heart -> heart)")
    ap.add_argument("--redo", default="", help="record again every clip whose text matches this pattern")
    ap.add_argument("--dry", action="store_true", help="count what would be recorded, record nothing")
    args = ap.parse_args()
    if not (args.pack or args.game or args.names):
        ap.error("choose --pack, --game or --names")

    ph = Phrases()
    if args.pack:
        collect_pack(ph)
    if args.game:
        collect_game(ph, os.path.expanduser(args.game))
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


if __name__ == "__main__":
    main()
