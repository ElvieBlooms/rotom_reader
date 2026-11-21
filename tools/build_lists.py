#!/usr/bin/env python3
# Rotom Reader: builds the word pack and name bank lists
# The shareable voice pack holds single words and names only, never the
# game's sentences. Its words come from public lists:
#   - dwyl/english-words (public domain): the dictionary words
#   - PokéAPI (BSD-3): English Pokémon, move, item and place names
#   - US Social Security baby-name records (public domain, via
#     hadley/data-baby-names): the name bank
# Which dictionary words are kept is decided by --vocab, a plain list of
# words to look for (one per line); without it, the most common words of
# the dictionary are kept.
#
#   python3 build_lists.py --lists ../lists --vocab vocab.txt --out .
# ------------------

import argparse
import csv
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

# Default names from the Gen 1 naming menus, plus the colour names.
DEFAULT_NAMES = ["Red", "Ash", "Jack", "Blue", "Gary", "John", "Green",
                 "Yellow", "Gold", "Silver"]
# Words the mod says on its own, whatever the game's text holds.
MOD_WORDS = ["trainer", "your", "rival", "what", "will", "do", "level",
             "fainted", "disabled", "yes", "no", "throw", "rock", "fight",
             "item", "run", "ball", "bait", "cancel", "experience", "dollars"]


# Everyday English contractions and sounds, which the dictionary leaves out.
CONTRACTIONS = """i'm i'll i've i'd you're you'll you've you'd he's he'll he'd she's she'll
she'd it's it'll we're we'll we've we'd they're they'll they've they'd that's there's
here's what's who's where's how's let's don't doesn't didn't can't couldn't won't
wouldn't shouldn't isn't aren't wasn't weren't hasn't haven't hadn't mustn't c'mon
y'know ma'am o'clock""".split()
SOUNDS = """hmm hm huh uh oh ooh oops ow aw aww eek ssh shh arrgh argh hiya yo yay wow
whoa hey ha haha hahaha hahahaha heh heheh hehehe ahem phew ugh yikes hooray""".split()
# Words from the Pokémon world that are no dictionary's business.
POKEMON_WORDS = """pokedex pokemaniac itemfinder teleporter silph kanto
boulderbadge cascadebadge thunderbadge rainbowbadge soulbadge marshbadge volcanobadge
earthbadge brock misty surge erika koga sabrina blaine giovanni lorelei bruno agatha
lance oak bill jessie james pokeflute""".split()
ORDINALS = """first second third fourth fifth sixth seventh eighth ninth tenth eleventh
twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth
twentieth thirtieth fortieth fiftieth sixtieth seventieth eightieth ninetieth
hundredth thousandth floor basement""".split()


def english_names(path, max_id=None, id_col=0):
    out = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["local_language_id"] != "9":
                continue
            if max_id and int(list(row.values())[id_col]) > max_id:
                continue
            out.append(row["name"])
    return out


def name_bank(path, count):
    total = defaultdict(float)
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            total[row["name"]] += float(row["percent"])
    ranked = sorted(total, key=lambda n: -total[n])
    return ranked[:count]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lists", required=True, help="folder with the downloaded public lists")
    ap.add_argument("--vocab", help="words to keep from the dictionary, one per line")
    ap.add_argument("--names", type=int, default=3000, help="how many first names to bank")
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    L = lambda f: os.path.join(args.lists, f)

    dictionary = set(w.strip() for w in open(L("words_alpha.txt"), encoding="utf-8") if w.strip())
    pokemon = english_names(L("pokemon_species_names.csv"), max_id=151)
    moves = english_names(L("move_names.csv"), max_id=165)
    vocab = set()
    if args.vocab:
        vocab = set(w.strip().lower() for w in open(args.vocab, encoding="utf-8") if w.strip())

    def in_vocab(name):
        ws = re.findall(r"[a-z']+", name.lower().replace("é", "e"))
        return bool(ws) and all(w in vocab for w in ws)

    # items and places from every generation, kept when the game uses them
    items = [n for n in english_names(L("item_names.csv")) if in_vocab(n)]
    places = [n for n in english_names(L("location_names.csv")) if in_vocab(n)]

    names = DEFAULT_NAMES + [n for n in name_bank(L("baby-names.csv"), args.names) if n not in DEFAULT_NAMES]

    words = set(MOD_WORDS) | set(CONTRACTIONS) | set(SOUNDS) | set(POKEMON_WORDS) | set(ORDINALS)
    words |= {w for w in vocab if w in dictionary}
    phrases = sorted(set(moves + items + places) - set(pokemon))

    with open(os.path.join(args.out, "pack_words.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(words)) + "\n")
    with open(os.path.join(args.out, "pack_names.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(phrases) + "\n")
    with open(os.path.join(args.out, "pack_pokemon.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(pokemon) + "\n")
    with open(os.path.join(args.out, "name_bank.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(names) + "\n")
    print(f"{len(words)} words, {len(pokemon)} Pokémon, {len(phrases)} move/item/place names, {len(names)} first names")


if __name__ == "__main__":
    main()
