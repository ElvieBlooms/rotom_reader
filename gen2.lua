-- Rotom Reader: Gold, Silver and Crystal
-- Gen 2 shows its battles and menus through its own screens
-- (src/ui/gen2). The overworld text box and the YES/NO box are shared with
-- Gen 1 and are read in main.lua; this file reads the rest:
--   * typed messages in Gen 2's screens (marts, the PC, saving, the
--     clock), which all start through src/ui/gen2/Typer.lua
--   * battle lines, the FIGHT / PkMn / PACK / RUN menu and the move list
--   * the START menu and other plain lists (Chrome.List)
--   * script menus (multiple choice), the PACK, the party, the summary
--     and the mart's buy list
-- R holds main.lua's helpers: speech, say, stop, tick, on, holding, watch,
-- monName, moveName, setGame.
-- ------------------

return function(mod, R)
  local speech, say = R.speech, R.say

  local function plain(page)
    local lines = page
    if type(page) == "string" then lines = speech.splitLines(page) end
    if type(lines) ~= "table" then return nil end
    local out = {}
    for i, line in ipairs(lines) do out[i] = tostring(line) end
    return speech.clean(speech.joinLines(out))
  end

  -- ---- Typed messages ----
  -- Every page a Gen 2 screen types out starts with Typer:start. Battle
  -- lines are read by the battle code below, so they are kept quiet here.
  -- A screen that starts the same page again (a redraw) isn't read twice.
  local quiet = 0
  local okTyper, Typer = pcall(require, "src.ui.gen2.Typer")
  if okTyper and type(Typer) == "table" and type(Typer.start) == "function" then
    local start = Typer.start
    local lastTyped, lastAt = nil, 0
    Typer.start = function(self, page, ...)
      local r = start(self, page, ...)
      if quiet == 0 and R.on() then
        local ok, text = pcall(plain, page)
        if ok and text and text ~= "" then
          local now = love.timer.getTime()
          local again = text == lastTyped and now - lastAt < 2
          lastTyped, lastAt = text, now
          if not again then
            R.setGame(self.game)
            pcall(say, text)
          end
        end
      end
      return r
    end
  else
    mod.log:warn("Rotom Reader: couldn't find Gen 2's Typer, so messages in menus won't be read")
  end

  -- ---- Battles ----
  -- A battle line is self.message; syncTyper starts typing it whenever it
  -- changes, so that is where it gets read. The line waits behind the one
  -- still being read, and with WAIT FOR VOICE on a line that has finished
  -- typing holds its A/B prompt until the voice is done (B skips the rest).
  local okBattle, Battle = pcall(require, "src.ui.gen2.BattleState")
  if okBattle and type(Battle) == "table" and type(Battle.syncTyper) == "function"
      and type(Battle.update) == "function" then
    local sync = Battle.syncTyper
    Battle.syncTyper = function(self, ...)
      local fresh = self.message ~= self.typedText
      quiet = quiet + 1
      local ok, r = pcall(sync, self, ...)
      quiet = quiet - 1
      if not ok then error(r, 0) end
      if fresh and type(self.message) == "string" and self.message ~= "" then
        R.setGame(self.game)
        local okText, text = pcall(plain, self.message)
        if okText and text and text ~= "" then
          pcall(say, text, mod.options:get("wait") ~= false)
        end
      end
      return r
    end

    local update = Battle.update
    Battle.update = function(self, ...)
      R.tick()
      local input = self.game and self.game.input
      local talking = (self.phase == "resolving" or self.phase == "intro")
        and type(self.message) == "string" and self.message ~= ""
      if talking and input and input.wasPressed then
        if input:wasPressed("select") then
          local ok, text = pcall(plain, self.message)
          if ok and text and text ~= "" then pcall(say, text) end
        end
        local typing = self.typer ~= nil and not self.typer:done()
        if (self.messageTimer or 0) > 0 and not typing and R.holding() then
          if input:wasPressed("b") then
            R.stop()
          else
            return
          end
        end
      end
      return update(self, ...)
    end

    -- The menu and the move list. Opening the menu asks "What will
    -- TOTODILE do?" after the last battle line, then names what the cursor
    -- is on.
    local MENU = { "FIGHT", "Pokémon", "PACK", "RUN" }
    local CONTEST = { "FIGHT", "Pokémon", "Park Ball", "RUN" }
    R.watch("src.ui.gen2.BattleState",
      function(self)
        if self.phase == "menu" then
          return "menu" .. (self.menuIndex or 1)
        elseif self.phase == "moves" then
          local moves = self:playerMoves()
          local mv = moves[self.moveIndex or 1]
          return "move" .. (self.moveIndex or 1) .. ":" .. tostring(mv and mv.id)
        end
        return "phase:" .. tostring(self.phase)
      end,
      function(self, prev)
        if self.phase == "menu" then
          local label = (self.contest and CONTEST or MENU)[self.menuIndex or 1]
          if not (prev and prev:find("^menu")) then
            local nm = R.monName(self:activeMon("player"))
            if nm then return "What will " .. nm .. " do? " .. label end
          end
          return label
        elseif self.phase == "moves" then
          local mv = self:playerMoves()[self.moveIndex or 1]
          local nm = mv and R.moveName(mv.id)
          local fighter = self.battle and self.battle.player
          if nm and fighter and self.battle.moveDisabled
              and self.battle:moveDisabled(fighter, mv.id) then
            nm = nm .. ", disabled"
          end
          return nm
        end
        return nil
      end,
      function(self, prev)
        return self.phase == "menu" and not (prev and prev:find("^menu"))
      end)
  else
    mod.log:warn("Rotom Reader: couldn't find Gen 2's battle screen, so battles won't be read")
  end

  -- ---- Menus ----
  local function label(item)
    if type(item) == "string" then return item end
    if type(item) == "table" and type(item.label) == "string" then return item.label end
    return nil
  end

  -- The START menu, the title menu and other plain lists (Chrome.List).
  local okChrome, Chrome = pcall(require, "src.ui.gen2.Chrome")
  if okChrome and type(Chrome) == "table" and type(Chrome.List) == "table" then
    R.watch(Chrome.List,
      function(self) return (self.index or 0) .. "/" .. #(self.items or {}) end,
      function(self) return label(self.items[self.index]) end)
  end

  -- Multiple-choice menus a script puts up.
  R.watch("src.ui.gen2.ScriptMenu",
    function(self)
      if self.done then return nil end
      return (self.row or 1) .. ":" .. (self.col or 1)
    end,
    function(self)
      local i = ((self.row or 1) - 1) * (self.cols or 1) + (self.col or 1)
      return label(self.items and self.items[i])
    end)

  -- The PACK: the pocket's name when it changes, then the item under the
  -- cursor and how many; USE / GIVE / TOSS beside it.
  R.watch("src.ui.gen2.PackMenu",
    function(self)
      local sub = self.submenu and ("s" .. (self.submenu.index or 1)) or ""
      return (self.pocketIndex or 1) .. ":" .. (self.index or 1) .. sub
    end,
    function(self, prev)
      if self.submenu then
        return label(self.submenu.rows and self.submenu.rows[self.submenu.index])
      end
      local text
      local row = self.rows and self.rows[self.index]
      if row then
        text = row.name or row.id
        if row.tmhmLabel then text = row.tmhmLabel .. " " .. text end
        if row.showCount and row.count then text = text .. ", " .. tostring(row.count) end
      else
        text = "Cancel"
      end
      local pocket = self.pocket and self:pocket()
      local pocketWas = prev and prev:match("^(%d+):")
      if pocket and pocket.label and pocketWas ~= tostring(self.pocketIndex or 1) then
        text = pocket.label .. ". " .. text
      end
      return text
    end)

  -- The party: each Pokémon's name, then the menu beside it. Opening it
  -- reads the prompt at the bottom first.
  R.watch("src.ui.gen2.PartyMenu",
    function(self)
      if self.submenu then return "sub" .. (self.submenu.index or 1) end
      return "mon" .. (self.index or 1) .. (self.switchFrom and "s" or "")
    end,
    function(self, prev)
      if self.submenu then
        return label(self.submenu.items and self.submenu.items[self.submenu.index])
      end
      local mon = (self.party or {})[self.index]
      local text = R.monName(mon)
      if not text then return nil end
      if mon.hp and mon.hp <= 0 then text = text .. ", fainted" end
      if prev == nil and type(self.prompt) == "string" then
        text = self.prompt .. " " .. text
      end
      return text
    end)

  -- A Pokémon's summary: its name and level, then its moves on the
  -- second page.
  R.watch("src.ui.gen2.SummaryMenu",
    function(self) return (self.index or 1) .. ":" .. (self.page or 1) end,
    function(self)
      local mon = self.mon or (self.party and self.party[self.index])
      if type(mon) ~= "table" then return nil end
      if self.page == 2 then
        local names = {}
        for i = 1, 4 do
          local mv = mon.moves and mon.moves[i]
          local nm = mv and R.moveName(type(mv) == "table" and mv.id or mv)
          if nm then names[#names + 1] = nm end
        end
        return table.concat(names, ", ")
      end
      local text = R.monName(mon)
      if text and mon.level then text = text .. ", level " .. tostring(mon.level) end
      return text
    end)

  -- A mart: BUY / SELL / QUIT, then each item and its price.
  local TOP = { "BUY", "SELL", "QUIT" }
  R.watch("src.ui.gen2.MartMenu",
    function(self)
      if self.message or self.confirm then return nil end
      if self.phase == "top" then return "top" .. (self.topIndex or 1) end
      if self.phase == "buy" then return "buy" .. (self.index or 1) end
      return nil
    end,
    function(self)
      if self.phase == "top" then return TOP[self.topIndex or 1] end
      local entry = self.entries and self.entries[self.index]
      if not entry then return "Cancel" end
      local text = entry.name or entry.id
      if entry.soldOut then return text .. ", sold out" end
      if entry.price then text = text .. ", " .. tostring(entry.price) .. " dollars" end
      return text
    end)
end
