-- Rotom Reader Fenrir (Gen 1): recordings for Rotom Reader, kept in
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

mod.exports = {
  voice = "fenrir",
  generation = 1,
  index = index,
  clipPath = function(id)
    if type(id) ~= "string" or not id:match("^%x+$") then return nil end
    return mod.assets:path("assets/voice/fenrir/" .. id .. ".ogg")
  end,
}
