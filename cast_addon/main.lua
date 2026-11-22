-- Rotom Reader Cast: the cast recordings for Rotom Reader, kept in their own
-- mod so the narrator download stays smaller. Rotom Reader asks for a clip
-- by id; this mod hands back where it lives.
local mod = ...

mod.exports = {
  clipPath = function(id)
    if type(id) ~= "string" or not id:match("^%x+$") then return nil end
    return mod.assets:path("assets/voice/cast/" .. id .. ".ogg")
  end,
}
