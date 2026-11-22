-- Rotom Reader Heart: recordings for Rotom Reader, kept in their own mod so
-- players download only the voices they want. Rotom Reader asks for a clip
-- by id; this mod hands back where it lives.
local mod = ...

mod.exports = {
  voice = "heart",
  clipPath = function(id)
    if type(id) ~= "string" or not id:match("^%x+$") then return nil end
    return mod.assets:path("assets/voice/heart/" .. id .. ".ogg")
  end,
}
