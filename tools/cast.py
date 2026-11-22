"""Rotom Reader: who says each line, and in which voice.

Used by build_voice.py --cast. Each text entry in the imported game is
matched to the person on the map who says it (through the map's object
list, its text pointers and its trainer headers), and that person gets a
voice: a fixed one for named characters, otherwise one picked from the
male or female pool by their name, so the same person always sounds the
same. Kids get Heart or Fenrir pitched up. Lines no one says (signs,
notebooks, item and battle messages) are left to the narrator.
"""
import hashlib
import re

FEMALE = ["af_bella", "af_nicole", "af_sarah", "af_aoede", "af_kore",
          "af_nova", "af_sky", "bf_emma", "bf_isabella"]
MALE = ["am_michael", "am_puck", "am_echo", "am_eric", "am_liam",
        "am_onyx", "bm_george", "bm_fable", "bm_lewis"]
# Heart and Fenrir narrate, so grown-ups never get them; kids do, pitched up.
KID_GIRL, KID_BOY = "af_heart", "am_fenrir"
KID_PITCH = 2.0   # semitones

# Named characters: one voice wherever they turn up.
NAMED = {
    "OAK": "am_michael", "RIVAL": "am_puck", "MOM": "af_sarah",
    "DAISY": "af_bella", "BILL": "am_echo", "BILLS_GRANDPA": "bm_lewis",
    "MR_FUJI": "bm_lewis", "GIOVANNI": "am_onyx", "JESSIE": "af_nova",
    "JAMES": "am_eric", "BROCK": "am_liam", "MISTY": "af_kore",
    "LT_SURGE": "am_onyx", "ERIKA": "bf_isabella", "KOGA": "bm_george",
    "SABRINA": "af_sky", "BLAINE": "bm_fable", "LORELEI": "af_aoede",
    "BRUNO": "am_echo", "AGATHA": "bf_emma", "LANCE": "am_liam",
    "NURSE": "af_nicole", "OFFICER_JENNY": "af_aoede", "COPYCAT": "af_bella",
    "SILPH_PRESIDENT": "bm_george", "CAPTAIN": "bm_fable", "WARDEN": "bm_lewis",
    "MELANIE": "af_kore", "GYM_GUIDE": "am_eric", "CHAIRMAN": "bm_fable",
    "NAME_RATER": "bm_george", "MR_PSYCHIC": "am_echo", "OAKS_AIDE": "am_puck",
    "LINK_RECEPTIONIST": "af_nicole", "RECEPTIONIST": "af_nicole",
    "CLERK": "am_michael", "MART_CLERK": "am_michael",
    "MAGIKARP_SALESMAN": "am_eric", "GAME_DESIGNER": "am_puck",
    "KARATE_MASTER": "am_onyx", "CHIEF": "bm_george", "SURFINDUDE": "am_puck",
    "OLD_MAN": "bm_lewis", "OLD_MAN_SLEEPY": "bm_lewis", "GATE_GUARD": "am_onyx",
    "CeladonMansion1.GRANNY": "bf_emma",
}
# The map object name for the rival in Yellow is RIVAL/RIVAL1/RIVAL2;
# sprites named after a character point there too.
SPRITE_NAMED = {"SPRITE_BLUE": "RIVAL", "SPRITE_OAK": "OAK", "SPRITE_MOM": "MOM",
                "SPRITE_DAISY": "DAISY", "SPRITE_GIOVANNI": "GIOVANNI",
                "SPRITE_JESSIE": "JESSIE", "SPRITE_JAMES": "JAMES",
                "SPRITE_NURSE": "NURSE", "SPRITE_OFFICER_JENNY": "OFFICER_JENNY",
                "SPRITE_MR_FUJI": "MR_FUJI", "SPRITE_LORELEI": "LORELEI",
                "SPRITE_BRUNO": "BRUNO", "SPRITE_AGATHA": "AGATHA", "SPRITE_LANCE": "LANCE",
                "SPRITE_GYM_GUIDE": "GYM_GUIDE", "SPRITE_LINK_RECEPTIONIST": "LINK_RECEPTIONIST",
                "SPRITE_SILPH_PRESIDENT": "SILPH_PRESIDENT", "SPRITE_CAPTAIN": "CAPTAIN",
                "SPRITE_WARDEN": "WARDEN"}

F, M, E, GIRL, BOY = "female", "male", "either", "girl", "boy"
CLASS_KIND = {
    "OPP_BEAUTY": F, "OPP_CHANNELER": F, "OPP_COOLTRAINER_F": F, "OPP_JR_TRAINER_F": F,
    "OPP_LASS": GIRL, "OPP_BUG_CATCHER": BOY, "OPP_YOUNGSTER": BOY,
    "OPP_PSYCHIC_TR": M,
}
SPRITE_KIND = {
    "SPRITE_COOLTRAINER_F": F, "SPRITE_BEAUTY": F, "SPRITE_CHANNELER": F,
    "SPRITE_GIRL": F, "SPRITE_BRUNETTE_GIRL": F, "SPRITE_MIDDLE_AGED_WOMAN": F,
    "SPRITE_SILPH_WORKER_F": F, "SPRITE_GRANNY": F, "SPRITE_NURSE": F,
    "SPRITE_LINK_RECEPTIONIST": F, "SPRITE_DAISY": F, "SPRITE_MOM": F,
    "SPRITE_JESSIE": F, "SPRITE_OFFICER_JENNY": F, "SPRITE_LORELEI": F, "SPRITE_AGATHA": F,
    "SPRITE_LITTLE_GIRL": GIRL, "SPRITE_YOUNGSTER": BOY, "SPRITE_LITTLE_BOY": BOY,
    "SPRITE_GAMEBOY_KID": BOY,
    "SPRITE_COOK": E, "SPRITE_CLERK": M,
}
# Things that "talk" only as signs or item text: the narrator reads them.
NARRATOR_SPRITES = {"SPRITE_POKE_BALL", "SPRITE_BOULDER", "SPRITE_POKEDEX", "SPRITE_CLIPBOARD",
                    "SPRITE_PAPER", "SPRITE_FOSSIL", "SPRITE_OLD_AMBER", "SPRITE_MONSTER",
                    "SPRITE_BIRD", "SPRITE_PIKACHU", "SPRITE_SNORLAX", "SPRITE_SEEL",
                    "SPRITE_JIGGLYPUFF", "SPRITE_CLEFAIRY", "SPRITE_CHANSEY", "SPRITE_ODDISH",
                    "SPRITE_SANDSHREW", "SPRITE_BULBASAUR", "SPRITE_FAIRY", "SPRITE_GAMBLER_ASLEEP"}

# Shared lines no map object owns, by text label.
SHARED = [
    (r"^_?(PokemonCenter|PokemonFightingFit|NurseJoy|LooksContentText|PokemonCenterPikachu)", "NURSE"),
    (r"^_?(Pokemart|PokemonSellingGreeting|PokemartBuyingGreeting|PokemonMartTransaction|ItemsBuy|ItemSold|PokemartThankYou|PokemartAnythingElse|PokemartItemBag|PokemartTellBuyPrice|PokemartTellSellPrice|PokemartUnsellable|PokemartNotEnoughMoney|PokemartBoughtItem|PokemartItemSold|PokemartSell|PokemartBuy|PokemartGreeting|PokemartNoBagRoom|PokemartNothingToSell)", "MART_CLERK"),
    (r"^_?(CableClub|LinkClosed|TradeCenter|Colosseum)", "LINK_RECEPTIONIST"),
    (r"GymGuide|GymGuy", "GYM_GUIDE"),
    (r"LTSurge", "LT_SURGE"),
    (r"JessieJames", "JESSIE"),
    (r"^_?OaksAide", "OAKS_AIDE"),
    (r"FanClubChair|PokemonFanClubChair|FanClubBikeVoucher|FanClubExplainBikeVoucher|FanClubNoStory|FanClubReceivedBike|FanClubBagFull", "CHAIRMAN"),
    (r"^_?Melanie", "MELANIE"),
    (r"^_?OaksLab|^_?Oak[A-Z]|^_?ProfOak", "OAK"),
    (r"^_?(Rival|Blue)[A-Z]", "RIVAL"),
    (r"^_?Mom[A-Z]", "MOM"),
    (r"^_?Daisy", "DAISY"),
    (r"^_?NameRater", "NAME_RATER"),
    (r"^_?Bill[A-Z]|^_?BillsHouseBill", "BILL"),
    (r"OfficerJenny", "OFFICER_JENNY"),
    (r"SurfinDude", "SURFINDUDE"),
    (r"^_?FightingDojo(?!.*(PokeBall|Sign))", "KARATE_MASTER"),
    (r"^_?CeladonMansion1Text\d", "CeladonMansion1.GRANNY"),
    (r"GateGuard|GuardYouCan|^_?Saffron\w*Guard", "GATE_GUARD"),
]
# A line that opens with "NAME:" is that person speaking.
TAGGED = {"OAK": "OAK", "MOM": "MOM", "GIRL": F, "BOY": BOY, "WOMAN": F, "MAN": M,
          "GUY": M, "LASS": GIRL, "KID": BOY, "JESSIE": "JESSIE", "JAMES": "JAMES",
          "BILL": "BILL", "DAISY": "DAISY", "GIOVANNI": "GIOVANNI"}
# Unowned lines from someone a Pokécenter or house "guy" or "girl".
GUY = re.compile(r"(Guy|Man|Gramps|Oldman|OldMan|Gentleman|Fisher|Sailor|Hiker|Boy|Youngster|Scientist)(Text|[A-Z0-9_]|$)")
GAL = re.compile(r"(Girl|Woman|Lady|Granny|Lass|Beauty)(Text|[A-Z0-9_]|$)")


def _pick(pool, who):
    h = int(hashlib.sha1(who.encode()).hexdigest(), 16)
    return pool[h % len(pool)]


def voice_for(who, kind):
    """(voice, semitones) for a speaker id and kind (female/male/either/girl/boy)."""
    if who in NAMED:
        return NAMED[who], 0.0
    if kind == GIRL:
        return KID_GIRL, KID_PITCH
    if kind == BOY:
        return KID_BOY, KID_PITCH
    if kind == F:
        return _pick(FEMALE, who), 0.0
    if kind == M:
        return _pick(MALE, who), 0.0
    return _pick(FEMALE + MALE, who), 0.0


def _camel(s):
    return "".join(p.capitalize() for p in s.split("_") if p)


def _short(name):
    short = name.split("_", 1)[1] if "_" in name else name
    return re.sub(r"\d+$", "", short)


def speakers(maps, ptrs, heads, labels):
    """{text label: (speaker id, kind)} for every line a person says.

    maps, ptrs, heads: the game's maps, text_pointers and trainer_headers
    tables, as plain dicts/lists. labels: the text.lua keys.
    """
    best = {}

    def offer(k, score, who, kind):
        if k not in best or score > best[k][0]:
            best[k] = (score, who, kind)

    for m in maps:
        lab = m["label"]
        mp = ptrs.get(lab) or {}
        hd = heads.get(lab) or {}
        for o in m.get("objects") or []:
            spr, nm = o.get("sprite") or "", o.get("name") or ""
            if spr in NARRATOR_SPRITES:
                continue
            short = _short(nm)
            cls = o.get("trainerClass") or ""
            if short in NAMED:
                who, kind = short, None
            elif spr in SPRITE_NAMED:
                who, kind = SPRITE_NAMED[spr], None
            elif cls.replace("OPP_", "") in NAMED:
                who, kind = cls.replace("OPP_", ""), None
            else:
                who = lab + "." + nm
                kind = CLASS_KIND.get(cls) or SPRITE_KIND.get(spr) or M
            exact = set()
            t = mp.get(o.get("text") or "")
            if t:
                for f in ("text", "label"):
                    if t.get(f):
                        exact.add(t[f].lstrip("_"))
            h = hd.get(o.get("index"))
            if h:
                for f in ("battle", "won", "after"):
                    if h.get(f):
                        exact.add(h[f].lstrip("_"))
            parts = [re.sub(r"\d+$", "", p) for p in (nm.split("_", 1)[1] if "_" in nm else nm).split("_")]
            prefixes = [lab + _camel("_".join(parts[:n])) for n in range(len(parts), 0, -1)]
            for k in labels:
                kk = k.lstrip("_")
                if kk in exact:
                    offer(k, 1000, who, kind)
                    continue
                for p in prefixes:
                    if kk.startswith(p) and not kk[len(p):len(p) + 1].islower():
                        offer(k, len(p), who, kind)
                        break
    out = {k: (v[1], v[2]) for k, v in best.items()}
    for k in labels:
        if k in out:
            continue
        for pat, who in SHARED:
            if re.search(pat, k):
                out[k] = (who, None)
                break
        else:
            if GUY.search(k):
                out[k] = (k.lstrip("_"), M)
            elif GAL.search(k):
                out[k] = (k.lstrip("_"), F)
    return out


def narrated(text):
    """Lines that open on the player ("{PLAYER} received TM34!") are the
    game narrating, whoever's script shows them."""
    return re.match(r"\s*\{(PLAYER|RAM:|NUM:)", text) is not None


def tagged_speaker(text):
    """A line like "OAK: Hey! Wait!" names its speaker."""
    m = re.match(r"\s*([A-Z][A-Z.]+):", text)
    if not m:
        return None
    tag = m.group(1).replace("PROF.", "").strip(".")
    hit = TAGGED.get(tag)
    if hit is None:
        return None
    if hit in (F, M, E, GIRL, BOY):
        return ("tag." + tag, hit)
    return (hit, None)
