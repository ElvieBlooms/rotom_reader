-- Rotom Reader
-- Reads the game's text and menus aloud as they appear, for players who
-- can't read the screen. The voice is recorded ahead of time (tools/build_voice.py)
-- and plays from the mod's own folder, so it works offline and on
-- handhelds.
--
-- Hooks into the engine's TextBox (src/render/TextBox.lua): beginLine
-- runs for every line typed, and the first line of a new page is where
-- the page gets read. Everything the box shows comes through here, names
-- already filled in. Text drawn outside a text box (menus, the naming
-- screen) is left alone.
-- ------------------

return function(mod)
  -- the mod's own files, read through mod:read so they load wherever the
  -- mod is installed
  local function own(path)
    local src = mod:read(path)
    if type(src) ~= "string" then error("can't read " .. path) end
    local chunk, err = load(src, "@" .. mod.id .. "/" .. path)
    if not chunk then error(err) end
    return chunk()
  end

  local speech = own("speech.lua")

  -- Which generation is running. Gen 1 and Gen 2 show their battles and
  -- menus through different code (src/ui/gen2 for Gold, Silver and Crystal).
  local GEN = 1
  do
    local ok, GameVersion = pcall(require, "src.core.GameVersion")
    if ok and type(GameVersion) == "table" and type(GameVersion.generation) == "function" then
      local okGen, g = pcall(GameVersion.generation, GameVersion.get())
      if okGen and type(g) == "number" then GEN = g end
    end
  end

  -- ---- Voice packs ----
  -- The recordings come in packs, one per voice and generation
  -- (rotom_reader_heart_gen1, rotom_reader_cast_gen2, ...). Each pack hands
  -- over the list of phrases it has and the path of each clip. Packs load
  -- before this mod (manifest optional_dependencies) and only on their own
  -- generation's games. Names recorded at home go in this mod's own
  -- voice_index.lua and assets/voice/<voice>, and are tried first.
  local NARRATORS = { "heart", "fenrir" }
  local PACK_VOICES = { "heart", "fenrir", "cast" }
  local clips = {}
  local maxWords = 1
  local function addIndex(t)
    if type(t) ~= "table" or type(t.clips) ~= "table" then return end
    for k, v in pairs(t.clips) do clips[k] = v end
    if type(t.maxWords) == "number" and t.maxWords > maxWords then maxWords = t.maxWords end
    speech.maxWords = maxWords
  end
  local okIndex, ownIndex = pcall(own, "voice_index.lua")
  if okIndex then addIndex(ownIndex) end

  local packs
  local function findPacks()
    if packs then return packs end
    packs = {}
    local any = false
    for _, voice in ipairs(PACK_VOICES) do
      packs[voice] = {}
      for g = 1, 3 do
        local handle = mod.find("rotom_reader_" .. voice .. "_gen" .. g)
        local ex = handle and handle.exports
        if type(ex) == "table" and (ex.generation == nil or ex.generation == GEN) then
          local list = packs[voice]
          list[#list + 1] = ex
          addIndex(ex.index)
          any = true
        end
      end
    end
    if not any then
      mod.log:warn("Rotom Reader: no voice pack for this game is installed, so only names recorded into Rotom Reader itself can be said")
    end
    return packs
  end

  mod.options:define({
    { key = "enabled", type = "toggle", label = "ROTOM READER", default = true },
    { key = "voice", type = "choice", label = "VOICE",
      choices = { { "HEART", "heart" }, { "FENRIR", "fenrir" } }, default = "heart" },
    { key = "cast", type = "toggle", label = "CAST VOICES", default = true },
    { key = "volume", type = "number", label = "VOICE VOL",
      min = 0, max = 7, step = 1, default = 7 },
    { key = "duck", type = "toggle", label = "QUIET MUSIC", default = true },
    { key = "wait", type = "toggle", label = "WAIT FOR VOICE", default = true },
    { key = "auto", type = "toggle", label = "AUTO SCROLL", default = true },
    { key = "skipnames", type = "toggle", label = "SKIP NICKNAMES", default = true },
  })

  local function on() return mod.options:get("enabled") ~= false end

  -- ---- Playing a page ----
  -- One clip at a time, each started when the last one ends. A new page
  -- cuts off whatever is still playing.
  local queue, pos, current = {}, 0, nil
  local lastText = nil
  local startedAt = 0
  -- the longest a page may hold the box, so a sound that never reports
  -- finishing can't leave the player stuck
  local HOLD_LIMIT = 20
  -- AUTO SCROLL timing, in seconds: a scroll inside a page waits a beat,
  -- and a new page within the same text follows once the voice has
  -- finished, or after a longer beat with the voice off
  local SCROLL_BEAT = 0.5
  local PAGE_BEAT = 0.6
  local SILENT_PAGE_BEAT = 2.5
  local quietSince = 0

  local function stop()
    if current then pcall(current.stop, current) end
    current, queue, pos = nil, {}, 0
  end

  -- With CAST VOICES on, a line a person says comes from the cast pack, in
  -- that person's own voice. Otherwise the chosen narrator reads; a clip it
  -- lacks comes from the other narrator. Clips recorded into this mod's own
  -- assets/voice/<voice> are tried before the packs. Clips are .ogg (or
  -- .mp3 from older recordings).
  local function tryPath(path)
    if type(path) ~= "string" then return nil end
    local ok, src = pcall(love.audio.newSource, path, "static")
    if ok and src then return src end
    return nil
  end
  local function packClip(voice, id)
    for _, ex in ipairs(findPacks()[voice] or {}) do
      if type(ex.clipPath) == "function" then
        local ok, path = pcall(ex.clipPath, id)
        local src = ok and tryPath(path) or nil
        if src then return src end
      end
    end
    return nil
  end
  local function openClip(id)
    local chosen = mod.options:get("voice") or "heart"
    local folders = {}
    if mod.options:get("cast") ~= false then folders[1] = "cast" end
    folders[#folders + 1] = chosen
    for _, v in ipairs(NARRATORS) do if v ~= chosen then folders[#folders + 1] = v end end
    folders[#folders + 1] = false
    for _, v in ipairs(folders) do
      local base = v and ("assets/voice/" .. v .. "/" .. id) or ("assets/voice/" .. id)
      for _, ext in ipairs({ ".ogg", ".mp3" }) do
        local src = tryPath(mod.assets:path(base .. ext))
        if src then return src end
      end
      if v then
        local src = packClip(v, id)
        if src then return src end
      end
    end
    return nil
  end

  local function startNext()
    while pos < #queue do
      pos = pos + 1
      local src = openClip(queue[pos])
      if src then
        src:setVolume((mod.options:get("volume") or 7) / 7)
        src:play()
        current = src
        return
      end
    end
    current = nil
    quietSince = love.timer.getTime()
  end

  local function speaking()
    return current ~= nil
  end

  -- ---- Names nobody recorded ----
  -- The player's and rival's names are typed in game, so the voice may
  -- have no recording of them. An unrecorded name is said as a stand-in:
  -- "Trainer" for the player, "your rival" for the rival, and a Pokémon's
  -- nickname as its species name.
  local currentGame

  local function recorded(name)
    findPacks()
    local ws = speech.words(speech.clean(name))
    return #ws == 0 or clips[speech.key(ws)] ~= nil, ws
  end

  local function speciesName(mon)
    local data = currentGame and currentGame.data
    local def = data and data.pokemon and data.pokemon[mon.species]
    return def and def.name or nil
  end

  local function standIns(words)
    local save = currentGame and currentGame.save
    if not save then return words end
    local swaps = {}
    local player = save.player or {}
    if type(player.name) == "string" then swaps[#swaps + 1] = { player.name, { "trainer" } } end
    local rival = player.rival
    if type(rival) ~= "string" and type(save.rival) == "table" then rival = save.rival.name end
    if type(rival) == "string" then swaps[#swaps + 1] = { rival, { "your", "rival" } } end
    for _, mon in ipairs(save.party or {}) do
      if type(mon) == "table" and type(mon.nickname) == "string" then
        local species = speciesName(mon)
        if species then
          swaps[#swaps + 1] = { mon.nickname, speech.words(speech.clean(species)) }
        end
      end
    end
    for _, swap in ipairs(swaps) do
      local known, from = recorded(swap[1])
      if not known then words = speech.substitute(words, from, swap[2]) end
    end
    return words
  end

  -- append adds the text after whatever is still being read, for battle
  -- lines that don't wait for a button ("PIKACHU used THUNDERBOLT!").
  local function say(text, append)
    lastText = text
    if not on() then stop() return end
    local okSub, words = pcall(standIns, speech.words(text))
    if not okSub then words = speech.words(text) end
    findPacks()
    local plan = speech.plan(words, clips)
    startedAt = love.timer.getTime()
    if append and current then
      for _, id in ipairs(plan) do queue[#queue + 1] = id end
      return
    end
    stop()
    queue = plan
    startNext()
  end

  local function tick()
    if current and not current:isPlaying() then startNext() end
  end

  -- Moves on to the next clip. render.hud runs every frame, text box or not.
  mod.hooks:wrap("render.hud", function(next, game, viewport)
    next(game, viewport)
    tick()
  end)

  mod.hooks:wrap("music.volume", function(next, vol, ctx)
    vol = next(vol, ctx)
    if speaking() and mod.options:get("duck") ~= false then return vol * 0.35 end
    return vol
  end)

  mod.events:on("mod.options_changed", function(change)
    if change and change.key == "enabled" and not on() then stop() end
  end)

  local function autoOn() return mod.options:get("auto") ~= false end

  -- Runs fn with A reading as pressed, so the game's own code does the
  -- scroll exactly as if she had pressed it.
  local function withA(game, fn, ...)
    local real = game.input
    game.input = setmetatable({
      wasPressed = function(_, button)
        if button == "a" then return true end
        return real:wasPressed(button)
      end,
    }, { __index = function(_, k)
      local v = real[k]
      if type(v) == "function" then
        return function(_, ...) return v(real, ...) end
      end
      return v
    end })
    local ok, r = pcall(fn, ...)
    game.input = real
    if not ok then error(r, 0) end
    return r
  end

  -- Is this in-message wait due to scroll on its own? waitedAt is when the
  -- wait began; page is true for a new page, false for a scroll.
  local function scrollDue(waitedAt, page)
    local now = love.timer.getTime()
    if not page then return now - waitedAt >= SCROLL_BEAT end
    if speaking() then return false end
    if on() then return now - math.max(waitedAt, quietSince) >= PAGE_BEAT end
    return now - waitedAt >= SILENT_PAGE_BEAT
  end

  local function holding()
    return speaking() and mod.options:get("wait") ~= false
      and love.timer.getTime() - startedAt < HOLD_LIMIT
  end

  -- ---- Battles ----
  -- Battle text has its own message queue in BattleState
  -- (src/battle/BattleState.lua startMessage), not a TextBox. Each message
  -- is read whole as it starts. A message waits behind the one still being
  -- read, so lines that run straight on aren't cut off, and the "press A"
  -- prompt holds until the voice is done.
  -- Gen 1 only: requiring a Gen 1 engine module on a Gen 2 game is an error
  -- the mod manager shows the player.
  local okBattle, BattleState = false, nil
  if GEN == 1 then okBattle, BattleState = pcall(require, "src.battle.BattleState") end
  if okBattle and type(BattleState) == "table"
      and type(BattleState.startMessage) == "function"
      and type(BattleState.updateQueue) == "function" then
    local function messageText(battle)
      local lines = {}
      for _, line in ipairs(battle.lines or {}) do lines[#lines + 1] = line.text or "" end
      return speech.clean(speech.joinLines(lines))
    end

    local startMessage = BattleState.startMessage
    BattleState.startMessage = function(self, ...)
      currentGame = self.game or currentGame
    local r = startMessage(self, ...)
      local ok, text = pcall(messageText, self)
      if ok and text and text ~= "" then
        local okSay, err = pcall(say, text, mod.options:get("wait") ~= false)
        if not okSay then mod.log:warn("Rotom Reader: " .. tostring(err)) end
      end
      return r
    end

    local updateQueue = BattleState.updateQueue
    BattleState.updateQueue = function(self, ...)
      tick()
      local input = self.game and self.game.input
      if input and input.wasPressed then
        if self.current and input:wasPressed("select") then
          local ok, text = pcall(messageText, self)
          if ok and text and text ~= "" then pcall(say, text) end
        end
        -- a scroll inside a battle message (msgWaiting) moves on by itself;
        -- the end of the message (msgPrompt) still waits for her
        if self.msgWaiting and autoOn() and self.game then
          self.readToMeWaitAt = self.readToMeWaitAt or love.timer.getTime()
          if scrollDue(self.readToMeWaitAt, false) then
            self.readToMeWaitAt = nil
            return withA(self.game, updateQueue, self, ...)
          end
        else
          self.readToMeWaitAt = nil
        end
        if self.current and self.msgPrompt and holding() then
          if input:wasPressed("b") then
            stop()
          else
            return true
          end
        end
      end
      return updateQueue(self, ...)
    end
  elseif GEN == 1 then
    mod.log:warn("Rotom Reader: couldn't find the battle text, so battles won't be read")
  end

  -- ---- Nicknames ----
  -- With SKIP NICKNAMES on, a new Pokémon keeps its species name and the
  -- "give a nickname?" question and naming screen never come up, since a
  -- name nobody recorded can only be spelled out. Catches go through the
  -- catch.nickname hook; gifts (Eevee, Lapras, fossils) through the
  -- pokemon.before_give event. Only the question is skipped: a name another
  -- mod gives (Name Tags) stands, so this hook runs outermost and asks the
  -- rest of the chain first, and the gift listener runs last.
  local function skipNames() return mod.options:get("skipnames") ~= false end
  local OUTERMOST, LAST = 1000, -1000

  mod.hooks:wrap("catch.nickname", function(next, mon, ctx)
    local verdict = next(mon, ctx)
    if verdict == true and skipNames() then return false end
    return verdict
  end, OUTERMOST)

  -- A gift that already has a name skips the question (pokemon.before_give,
  -- src/script/Commands.lua give_pokemon), so one nobody named is given its
  -- species name.
  mod.events:on("pokemon.before_give", function(gift)
    if not skipNames() or type(gift) ~= "table" or gift.isEgg or gift.nickname then return end
    local game = gift.ctx and gift.ctx.game or currentGame
    local def = game and game.data and game.data.pokemon and game.data.pokemon[gift.species]
    if def and type(def.name) == "string" then gift.nickname = def.name end
  end, LAST)

  -- ---- Menus ----
  -- After each update, a menu's cursor is turned into a short signature.
  -- When it changes, the highlighted thing is read. The first reading
  -- when a menu opens waits behind any line still being read (a YES/NO
  -- after its question); moving the cursor cuts in straight away.
  local data
  local function monName(mon)
    if type(mon) ~= "table" then return nil end
    local def = data and data.pokemon and data.pokemon[mon.species]
    if mon.nickname and recorded(mon.nickname) then return mon.nickname end
    return (def and def.name) or mon.nickname
  end

  local function moveName(id)
    local def = data and data.moves and data.moves[id]
    return def and def.name or nil
  end

  -- name is a module to require, or the class table itself.
  local function watch(name, sigFn, textFn, appendFn)
    local ok, Class = true, name
    if type(name) == "string" then ok, Class = pcall(require, name) end
    if not ok or type(Class) ~= "table" or type(Class.update) ~= "function" then
      mod.log:warn("Rotom Reader: couldn't find " .. tostring(name) .. ", so it won't be read")
      return nil
    end
    local orig = Class.update
    Class.update = function(self, ...)
      local r = orig(self, ...)
      if on() then
        local okSig, sig = pcall(sigFn, self)
        if okSig and sig ~= nil and sig ~= self.readToMeSig then
          local prev = self.readToMeSig
          self.readToMeSig = sig
          data = self.game and self.game.data or self.data or data
          currentGame = self.game or currentGame
          local okText, text = pcall(textFn, self, prev)
          if okText and type(text) == "string" and text ~= "" then
            local append = prev == nil
            if appendFn then append = appendFn(self, prev) end
            local okSay, err = pcall(say, speech.clean(text), append)
            if not okSay then mod.log:warn("Rotom Reader: " .. tostring(err)) end
          end
        end
      end
      return r
    end
    return Class
  end

  -- An item row in a list: its name, then how many or what level.
  local function rowText(item)
    if type(item) ~= "table" then return nil end
    local text = item.label
    if type(text) ~= "string" then return nil end
    if item.count then text = text .. ", " .. tostring(item.count)
    elseif item.level then text = text .. ", level " .. tostring(item.level) end
    return text
  end

  -- ---- Gen 1 menus ----
  if GEN == 1 then
  -- The bag, shops, the PC and other lists (src/ui/ListMenu.lua).
  watch("src.ui.ListMenu",
    function(self) return (self.index or 0) .. "/" .. #(self.items or {}) end,
    function(self) return rowText(self.items[self.index]) end)

  -- Small menus: START, USE/TOSS, the PC's menus (src/ui/Menu.lua).
  watch("src.ui.Menu",
    function(self) return self.index end,
    function(self) return rowText(self.items[self.index]) end)
  end

  -- YES/NO and other two-choice boxes (src/ui/ChoiceBox.lua), in every
  -- generation.
  watch("src.ui.ChoiceBox",
    function(self) return self.index end,
    function(self) return self.labels and self.labels[self.index] end)

  if GEN == 1 then

  -- The party: each Pokémon's name, then the STATS/SWITCH menu beside it.
  -- Opening it reads the prompt at the bottom first.
  watch("src.ui.PartyMenu",
    function(self)
      if self.submenu then return "sub" .. (self.subIndex or 1) end
      return "mon" .. (self.index or 1) .. (self.swapFrom and "s" or "")
    end,
    function(self, prev)
      if self.submenu then
        return rowText(self.subItems and self.subItems[self.subIndex])
      end
      local party = self.party or (self.game.save and self.game.save.party) or {}
      local mon = party[self.index]
      local text = monName(mon)
      if not text then return nil end
      if mon.hp and mon.hp <= 0 then text = text .. ", fainted" end
      if prev == nil and self.bottomMessage then
        local okMsg, msg = pcall(self.bottomMessage, self)
        if okMsg and type(msg) == "string" then text = msg .. " " .. text end
      end
      return text
    end)

  -- A Pokémon's summary: its name and level, then its moves on page 2.
  watch("src.ui.SummaryMenu",
    function(self) return self.page end,
    function(self)
      local mon = self.mon
      if self.page == 2 then
        local names = {}
        for i = 1, 4 do
          local mv = mon.moves and mon.moves[i]
          local nm = mv and moveName(mv.id)
          if nm then names[#names + 1] = nm end
        end
        return table.concat(names, ", ")
      end
      local text = monName(mon)
      if text and mon.level then text = text .. ", level " .. tostring(mon.level) end
      return text
    end)

  -- The battle menu and the FIGHT list (src/battle/BattleState.lua).
  -- Opening the menu asks "What will PIKACHU do?" after the last battle
  -- line, then names what the cursor is on; the FIGHT list names the move.
  local MENU = { "FIGHT", "POKéMON", "ITEM", "RUN" }
  local SAFARI = { "BALL", "BAIT", "Throw rock", "RUN" }
  watch("src.battle.BattleState",
    function(self)
      if self.phase == "menu" and not self.demo
          and self.player and self.player.mon and self.player.mon.hp > 0 then
        return "menu" .. (self.menuIndex or 1)
      elseif self.phase == "moveSelect" and self.player then
        local mv = self.player.curMoves and self.player.curMoves[self.moveIndex]
        return "move" .. (self.moveIndex or 1) .. ":" .. tostring(mv and mv.id)
      end
      return "phase:" .. tostring(self.phase)
    end,
    function(self, prev)
      local entering = not (prev and prev:find("^menu"))
      if self.phase == "menu" then
        local label = (self.safari and SAFARI or MENU)[self.menuIndex or 1]
        if entering then
          local nm = monName(self.player.mon)
          if nm then return "What will " .. nm .. " do? " .. label end
        end
        return label
      elseif self.phase == "moveSelect" then
        local mv = self.player.curMoves[self.moveIndex]
        local nm = mv and moveName(mv.id)
        if nm and self.player.disabledSlot == self.moveIndex then
          nm = nm .. ", disabled"
        end
        return nm
      end
      return nil
    end,
    function(self, prev)
      -- only the question waits behind the last battle line
      return self.phase == "menu" and not (prev and prev:find("^menu"))
    end)
  end

  if GEN == 2 then
    local ok, gen2 = pcall(own, "gen2.lua")
    if ok and type(gen2) == "function" then
      local okRun, err = pcall(gen2, mod, {
        speech = speech, say = say, stop = stop, tick = tick, on = on,
        holding = holding, watch = watch, monName = monName, moveName = moveName,
        setGame = function(game, gameData)
          currentGame = game or currentGame
          data = gameData or (game and game.data) or data
        end,
      })
      if not okRun then mod.log:warn("Rotom Reader: " .. tostring(err)) end
    else
      mod.log:warn("Rotom Reader: couldn't load gen2.lua, so Gen 2 battles and menus won't be read: " .. tostring(gen2))
    end
  end

  -- ---- The text box ----
  local okBox, TextBox = pcall(require, "src.render.TextBox")
  if not okBox or type(TextBox) ~= "table" or type(TextBox.beginLine) ~= "function" then
    mod.log:warn("Rotom Reader: couldn't find the engine's TextBox, so nothing will be read")
    return
  end

  local function pageText(box)
    local page = box.pages and box.pages[box.pageIndex]
    if type(page) ~= "table" then return nil end
    return speech.clean(speech.joinLines(page))
  end

  local beginLine = TextBox.beginLine
  TextBox.beginLine = function(self, ...)
    currentGame = self.game or currentGame
    local r = beginLine(self, ...)
    if self.readToMePage ~= self.pageIndex then
      self.readToMePage = self.pageIndex
      local ok, text = pcall(pageText, self)
      -- a YES/NO box puts the page just read back up, already typed out
      if ok and text and text ~= "" and not (self.instant and text == lastText) then
        local okSay, err = pcall(say, text)
        if not okSay then mod.log:warn("Rotom Reader: " .. tostring(err)) end
      end
    end
    return r
  end

  -- SELECT while a box is up says the page again. With WAIT FOR VOICE on,
  -- a page that has finished typing holds until the voice is done, and B
  -- skips the rest of the reading.
  local update = TextBox.update
  TextBox.update = function(self, dt, ...)
    tick()
    local input = self.game and self.game.input
    local pressed = input and input.wasPressed
    if pressed and input:wasPressed("select") then
      local ok, text = pcall(pageText, self)
      if ok and text and text ~= "" then pcall(say, text) end
    end
    -- AUTO SCROLL: scrolls and new pages inside one text move on by
    -- themselves; the end of the text (done) still waits for her press
    if self.waiting and autoOn() and self.game then
      self.readToMeWaitAt = self.readToMeWaitAt or love.timer.getTime()
      if scrollDue(self.readToMeWaitAt, not self.contAdvance) then
        self.readToMeWaitAt = nil
        return withA(self.game, update, self, dt, ...)
      end
      -- a scroll mid-page never holds for the voice, which is reading the
      -- whole page anyway
      if self.contAdvance then return update(self, dt, ...) end
    elseif not self.waiting then
      self.readToMeWaitAt = nil
    end
    local ready = self.waiting or self.done
    if ready and holding() then
      if pressed and input:wasPressed("b") then
        stop()
      else
        return
      end
    end
    return update(self, dt, ...)
  end
end
