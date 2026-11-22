"""Writes manifest.json, main.lua and README.md for one Rotom Reader voice pack."""
import json, os, sys
d, voice, gen = sys.argv[1], sys.argv[2], int(sys.argv[3])
GAMES = {1: ("gen1", "Red, Blue and Yellow"), 2: ("gen2", "Gold, Silver and Crystal")}
token, games = GAMES[gen]
NAME = {"heart": "Heart", "fenrir": "Fenrir", "cast": "Cast"}[voice]
WHAT = {
    "heart": "Heart, a warm female narrator, reading every line of %s, plus a word pack for names and numbers.",
    "fenrir": "Fenrir, a deep male narrator, reading every line of %s, plus a word pack for names and numbers.",
    "cast": "Character voices for %s: the people you meet speak in voices of their own. Turn CAST VOICES on in Rotom Reader's options.",
}[voice] % games
os.makedirs(d, exist_ok=True)
man = {"id": f"rotom_reader_{voice}_gen{gen}", "name": f"Rotom Reader {NAME} (Gen {gen})",
       "version": "0.4.0", "api": 2, "entry": "main.lua", "profile": "content",
       "category": "AUDIO", "games": [token],
       "description": WHAT + " A voice pack for Rotom Reader 0.4.0 or newer.",
       "github": "ElvieBlooms/rotom_reader", "permissions": []}
with open(os.path.join(d, "manifest.json"), "w") as f:
    json.dump(man, f, indent=2); f.write("\n")
with open(os.path.join(d, "main.lua"), "w") as f:
    f.write(f'''-- Rotom Reader {NAME} (Gen {gen}): recordings for Rotom Reader, kept in
-- their own mod so players download only the voices they want. Rotom
-- Reader reads this pack's list of recorded phrases and asks for each clip
-- by id; this mod hands back where it lives.
local mod = ...

local index
local src = mod:read("voice_index.lua")
if type(src) == "string" then
  local chunk = load(src, "@" .. mod.id .. "/voice_index.lua")
  local ok, t = pcall(chunk or error)
  if ok and type(t) == "table" and type(t.clips) == "table" then index = t end
end

mod.exports = {{
  voice = "{voice}",
  generation = {gen},
  index = index,
  clipPath = function(id)
    if type(id) ~= "string" or not id:match("^%x+$") then return nil end
    return mod.assets:path("assets/voice/{voice}/" .. id .. ".ogg")
  end,
}}
''')
with open(os.path.join(d, "README.md"), "w") as f:
    f.write(f"""# Rotom Reader {NAME} (Gen {gen})

{WHAT}

A voice pack for [Rotom Reader](https://github.com/ElvieBlooms/rotom_reader). Install it alongside Rotom Reader 0.4.0 or newer; on its own it does nothing. It only loads on {games}.

Recorded with Rotom Reader's recorder (`tools/build_voice.py`) using Kokoro-82M by hexgrad (Apache 2.0). MIT licensed.
""")
