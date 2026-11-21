-- Rotom Reader: turning game text into words to say
-- Cleans a text box page into something a voice can read (POKéMON
-- becomes Pokémon, shouted names become plain names, box codes go),
-- and splits it into lookup keys. The recorder (tools/build_voice.py)
-- runs this same file, so the keys it records always match the keys
-- the game asks for.
-- ------------------

local speech = {}

-- Short words the game writes in caps that should stay letters.
local KEEP_CAPS = { HP = true, PP = true, TM = true, HM = true, PC = true,
  OT = true, ID = true, TV = true, KO = true, SS = true }

-- Caps words read better as a different word.
local SAY_AS = { OK = "okay", EXP = "experience", PKMN = "Pokémon",
  LV = "level", MT = "Mount", CO = "Co", ST = "St", PROF = "Professor" }

local function titleWord(w)
  local up = w:upper()
  if SAY_AS[up] then return SAY_AS[up] end
  if KEEP_CAPS[up] then return up end
  if #w < 2 then return w end
  -- the first byte is always ASCII here, so lowercasing the rest is safe
  return w:sub(1, 1) .. w:sub(2):lower()
end

-- Joins a page's lines. A line ending in a hyphen runs into the next
-- one, the way the game splits "grand-" / "daughter".
function speech.joinLines(lines)
  local out = ""
  for i, line in ipairs(lines) do
    line = line:gsub("\1", "")
    if i == 1 then
      out = line
    elseif out:find("%a%-$") and line:find("^%a") then
      out = out:sub(1, -2) .. line
    else
      out = out .. " " .. line
    end
  end
  return out
end

-- Page text with \n and \v breaks, as the game's text tables hold it.
function speech.splitLines(text)
  local lines = {}
  for line in (text .. "\n"):gmatch("(.-)[\n\v]") do lines[#lines + 1] = line end
  return lines
end

function speech.clean(s)
  s = s:gsub("[\1\n\v\f]", " ")
  s = s:gsub("<PK><MN>", "POKéMON"):gsub("<PK>", "POKé"):gsub("<MN>", "MON")
  s = s:gsub("#", "POKé")
  s = s:gsub("POKéMON", "Pokémon"):gsub("POKéDEX", "Pokédex"):gsub("POKé", "Poké")
  s = s:gsub("PROF%.", "Professor "):gsub("S%.S%.", "S.S. ")
  s = s:gsub("MR%.", "Mr. "):gsub("MRS%.", "Mrs. ")
  s = s:gsub("EXP%.", "EXP ")
  s = s:gsub("¥%s*(%d+)", "%1 dollars"):gsub("¥", "")
  s = s:gsub("…", "..."):gsub("♂", " boy"):gsub("♀", " girl")
  s = s:gsub("×", " times "):gsub("&", " and ")
  s = s:gsub("’", "'"):gsub("‘", "'"):gsub("“", '"'):gsub("”", '"')
  -- any other non-ASCII glyph (arrows, cursors, box art) says nothing;
  -- é is the one kept, so Pokémon stays Pokémon
  s = s:gsub("[\128-\255]+", function(seq)
    local kept = {}
    for _ in seq:gmatch("é") do kept[#kept + 1] = "é" end
    return #kept > 0 and table.concat(kept) or " "
  end)
  s = s:gsub("[<>{}%[%]_]", " ")
  -- ordinals, floors and levels: 1st, 5F, B1F, L30
  s = s:gsub("(%d+)[snrt][tdh]%f[%W]", function(n) return speech.ordinal(n) end)
  s = s:gsub("%f[%w]B(%d+)F%f[%W]", "basement %1"):gsub("%f[%w](%d+)F%f[%W]", "floor %1")
  s = s:gsub("%f[%w]L(%d+)%f[%W]", "level %1")
  -- caps words (two or more letters) become ordinary words
  s = s:gsub("%u[%u']+", titleWord)
  s = s:gsub("%s+", " "):gsub("^ ", ""):gsub(" $", "")
  return s
end

-- Lowercase words, accents folded, so "Pokémon" and "POKéMON" match.
function speech.words(s)
  s = s:gsub("é", "e"):gsub("É", "e"):lower()
  local out = {}
  for w in s:gmatch("[%w']+") do
    w = w:gsub("^'+", ""):gsub("'+$", "")
    if w ~= "" then out[#out + 1] = w end
  end
  return out
end

function speech.key(words, i, j)
  return table.concat(words, " ", i or 1, j or #words)
end

local ONES = { "one", "two", "three", "four", "five", "six", "seven", "eight",
  "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
  "sixteen", "seventeen", "eighteen", "nineteen" }
local TENS = { [2] = "twenty", [3] = "thirty", [4] = "forty", [5] = "fifty",
  [6] = "sixty", [7] = "seventy", [8] = "eighty", [9] = "ninety" }
speech.NUMBER_WORDS = { "zero", "hundred", "thousand", "million" }
for _, w in ipairs(ONES) do speech.NUMBER_WORDS[#speech.NUMBER_WORDS + 1] = w end
for _, w in pairs(TENS) do speech.NUMBER_WORDS[#speech.NUMBER_WORDS + 1] = w end

local function under1000(n, out)
  if n >= 100 then
    out[#out + 1] = ONES[math.floor(n / 100)]
    out[#out + 1] = "hundred"
    n = n % 100
  end
  if n >= 20 then
    out[#out + 1] = TENS[math.floor(n / 10)]
    n = n % 10
  end
  if n > 0 then out[#out + 1] = ONES[n] end
end

-- 245 -> { "two", "hundred", "forty", "five" }
function speech.numberWords(n)
  n = math.floor(tonumber(n) or 0)
  if n == 0 then return { "zero" } end
  local out = {}
  if n >= 1000000 then
    under1000(math.floor(n / 1000000), out); out[#out + 1] = "million"
    n = n % 1000000
  end
  if n >= 1000 then
    under1000(math.floor(n / 1000), out); out[#out + 1] = "thousand"
    n = n % 1000
  end
  under1000(n, out)
  return out
end

local ORDINAL = { one = "first", two = "second", three = "third", five = "fifth",
  eight = "eighth", nine = "ninth", twelve = "twelfth" }

-- 21 -> "twenty first"
function speech.ordinal(n)
  local ws = speech.numberWords(n)
  local last = ws[#ws]
  if ORDINAL[last] then ws[#ws] = ORDINAL[last]
  elseif last:sub(-1) == "y" then ws[#ws] = last:sub(1, -2) .. "ieth"
  else ws[#ws] = last .. "th" end
  return table.concat(ws, " ")
end
speech.ORDINAL_WORDS = { "first", "second", "third", "fourth", "fifth", "sixth",
  "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth",
  "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth",
  "nineteenth", "twentieth", "thirtieth", "fortieth", "fiftieth", "sixtieth",
  "seventieth", "eightieth", "ninetieth", "hundredth", "thousandth", "floor", "basement" }

-- How each letter is said when a word has to be spelled out.
speech.LETTERS = { a = "ay", b = "bee", c = "see", d = "dee", e = "ee", f = "eff",
  g = "jee", h = "aitch", i = "eye", j = "jay", k = "kay", l = "el", m = "em",
  n = "en", o = "oh", p = "pee", q = "cue", r = "ar", s = "ess", t = "tee",
  u = "you", v = "vee", w = "double you", x = "ex", y = "why", z = "zee" }

-- The longest phrase the recorder kept, in words; set from the index.
speech.maxWords = 80

-- Unknown words this short are spelled out (TMs, HQ); longer ones, mostly
-- cries and made-up sounds ("Kurukkoo!"), are left out.
speech.SPELL_MAX = 4

-- Replaces every run of words `from` in `words` with `to`, keeping a
-- possessive: { "blue's", "house" } with from { "blue" } and to
-- { "your", "rival" } becomes { "your", "rival's", "house" }.
function speech.substitute(words, from, to)
  if #from == 0 then return words end
  local out, i = {}, 1
  while i <= #words do
    local match = i + #from - 1 <= #words
    local poss = false
    for k = 1, #from do
      local w = words[i + k - 1]
      if not w then match = false break end
      if w ~= from[k] then
        if k == #from and w == from[k] .. "'s" then poss = true
        else match = false break end
      end
    end
    if match then
      for k = 1, #to do
        out[#out + 1] = (poss and k == #to) and (to[k] .. "'s") or to[k]
      end
      i = i + #from
    else
      out[#out + 1] = words[i]
      i = i + 1
    end
  end
  return out
end

-- Turns a cleaned page into the list of recordings to play, in order.
-- Longest recorded phrase first, then single words, then numbers said as
-- words; an unknown short word is spelled and a longer one left out.
function speech.plan(words, clips)
  local out, i, n = {}, 1, #words
  while i <= n do
    local found
    for j = math.min(n, i + speech.maxWords - 1), i, -1 do
      local k = speech.key(words, i, j)
      if clips[k] then
        out[#out + 1] = clips[k]
        i = j + 1
        found = true
        break
      end
    end
    if not found then
      local w = words[i]
      if w:find("^%d+$") then
        for _, nw in ipairs(speech.numberWords(w)) do
          if clips[nw] then out[#out + 1] = clips[nw] end
        end
      elseif w:find("'s$") and clips[w:sub(1, -3)] then
        out[#out + 1] = clips[w:sub(1, -3)]
      elseif #w:gsub("%A", "") <= speech.SPELL_MAX then
        for ch in w:gmatch("%a") do
          local c = clips["letter " .. ch]
          if c then out[#out + 1] = c end
        end
        for d in w:gmatch("%d+") do
          for _, nw in ipairs(speech.numberWords(d)) do
            if clips[nw] then out[#out + 1] = clips[nw] end
          end
        end
      end
      i = i + 1
    end
  end
  return out
end

return speech
