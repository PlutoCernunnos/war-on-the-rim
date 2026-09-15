"""
War on the Rim
--------------
Build your town and train a warband in real time, then send it to war.
Battles play out automatically in rounds, in the spirit of Conquest of
Elysium: troops deploy in formation, advance, shoot, cast spells, strike,
break and flee on their own. Your choices are what you build, who you
train, and when you march.

Soldiers earn experience and climb the ranks:
  Recruit -> Regular -> Veteran -> Elite -> Champion
Each rank adds attack, defence, morale and hit points (and damage and
spell power at higher ranks). Enemy garrisons gain experience too.

Every unit carries one or more weapons and uses all of its melee weapons
each round, like Conquest of Elysium. Weapons can have reach, charge, repel,
sweep, stun, poison, life drain, armour-piercing and more. Hover over any
unit in battle to see them.

Controls
  Town:   click a plot, use the side panel. M opens the War Map.
          P (or the Pause button) pauses the town; you can still give orders.
  Map:    click a location, then March. M or ESC returns to town.
  Battle: SPACE or P pause, 1/2/3 speed, S skip to the end, ENTER continue.
  R restarts after victory or defeat.

Requires pygame 2.x  (pip install pygame)
"""
import itertools
import math
import random
import sys
from dataclasses import dataclass

import pygame

W, H = 1280, 760
FPS = 60

C = {
    "bg": (20, 22, 25), "ink": (12, 13, 15), "paper": (232, 224, 201),
    "muted": (150, 146, 131), "dim": (96, 94, 86),
    "panel": (31, 34, 38), "panel2": (41, 45, 50), "edge": (92, 81, 62),
    "grass": (50, 68, 51), "grass2": (56, 75, 56), "dirt": (92, 76, 56),
    "road": (104, 88, 64), "field": (72, 69, 50), "field2": (78, 75, 54),
    "gold": (216, 170, 72), "iron": (152, 166, 180), "red": (192, 74, 60),
    "blue": (78, 140, 188), "green": (106, 182, 94), "white": (248, 242, 222),
    "purple": (150, 104, 186), "undead": (122, 100, 146), "mana": (96, 156, 236),
    "fire": (255, 140, 50), "holy": (255, 222, 120), "nature": (120, 210, 110),
    "dark": (176, 110, 220), "lightning": (170, 210, 255),
}
FONTS = {}

RANKS = [(0, "Recruit"), (8, "Regular"), (22, "Veteran"), (45, "Elite"), (80, "Champion")]
RANK_COLORS = [(120, 120, 120), (120, 180, 110), (90, 150, 220), (190, 120, 220), (230, 180, 70)]


def init_fonts():
    sans, serif = "segoeui,dejavusans,arial", "georgia,dejavuserif,times"
    FONTS["tiny"] = pygame.font.SysFont(sans, 11)
    FONTS["small"] = pygame.font.SysFont(sans, 13)
    FONTS["body"] = pygame.font.SysFont(sans, 15)
    FONTS["bold"] = pygame.font.SysFont(sans, 15, bold=True)
    FONTS["head"] = pygame.font.SysFont(serif, 20, bold=True)
    FONTS["title"] = pygame.font.SysFont(serif, 26, bold=True)
    FONTS["big"] = pygame.font.SysFont(serif, 56, bold=True)


def text(surf, s, pos, font="body", color=None, center=False, right=False):
    img = FONTS[font].render(str(s), True, color or C["paper"])
    r = img.get_rect()
    if center:
        r.center = pos
    elif right:
        r.topright = pos
    else:
        r.topleft = pos
    surf.blit(img, r)
    return r


def fit(s, font, width):
    if FONTS[font].size(s)[0] <= width:
        return s
    while s and FONTS[font].size(s + "...")[0] > width:
        s = s[:-1]
    return s + "..."


def wrap(s, font, width):
    words, lines, line = s.split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if FONTS[font].size(trial)[0] > width and line:
            lines.append(line)
            line = w
        else:
            line = trial
    return lines + ([line] if line else [])


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def drn():
    """Open-ended d6: a 6 counts as 5 and rolls again."""
    total = 0
    while True:
        r = random.randint(1, 6)
        if r < 6:
            return total + r
        total += 5


# --------------------------------------------------------------------------
# Spells
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Spell:
    name: str
    kind: str          # bolt / blast / chain / entangle / summon / heal / bless / curse / raise
    cost: int
    rng: int = 0
    dmg: int = 0
    style: str = "fire"
    ap: bool = False
    holy: bool = False
    slow: int = 0
    offensive: bool = True


SPELLS = {
    "firebolt": Spell("Firebolt", "bolt", 1, 8, 6, "fire", ap=True),
    "fireball": Spell("Fireball", "blast", 4, 7, 6, "fire"),
    "lightning": Spell("Chain Lightning", "chain", 5, 9, 7, "lightning", ap=True),
    "entangle": Spell("Entangle", "entangle", 2, 7, style="nature", slow=2),
    "summon_wolf": Spell("Call Wolf", "summon", 4, style="nature", offensive=False),
    "heal": Spell("Heal", "heal", 1, 4, 5, "holy", offensive=False),
    "smite": Spell("Smite", "bolt", 2, 5, 6, "holy", holy=True),
    "bless": Spell("Bless", "bless", 3, 2, style="holy", offensive=False),
    "curse": Spell("Hex", "curse", 2, 7, style="dark"),
    "raise_dead": Spell("Raise Dead", "raise", 3, 6, style="dark", offensive=False),
    "drain": Spell("Grave Bolt", "bolt", 1, 7, 5, "dark", ap=True),
    "haste": Spell("Haste", "haste", 3, 3, style="lightning", offensive=False),
}


# --------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Weapon:
    name: str
    dmg: int
    rng: int = 0
    ammo: int = 0
    reach: int = 1
    att: int = 0
    chance: int = 0
    tags: tuple = ()

    LONG = {"ap": "armour-piercing", "an": "ignores armour", "charge": "only when charging",
            "repel": "strikes first vs charges", "sweep": "sweeps a second foe", "poison": "poison",
            "drain": "drains life", "magic": "magic", "holy": "holy", "thrown": "thrown once",
            "reload": "slow reload", "anti_mount": "+5 vs riders"}
    SHORT = {"ap": "AP", "an": "AN", "charge": "charge", "repel": "repel", "sweep": "sweep",
             "poison": "poison", "drain": "drain", "magic": "magic", "holy": "holy", "thrown": "thrown",
             "reload": "slow", "anti_mount": "anti-rider", "stun": "stun"}

    def describe(self):
        bits = [f"range {self.rng}"] if self.rng else []
        if self.reach > 1:
            bits.append("reach 2")
        for t in self.tags:
            bits.append(f"stun {self.chance}%" if t == "stun" else self.LONG.get(t, t))
        return f"{self.name} {self.dmg}" + (f" ({', '.join(bits)})" if bits else "")

    def short(self):
        bits = ([f"r{self.rng}"] if self.rng else []) + (["reach"] if self.reach > 1 else [])
        bits += [self.SHORT[t] for t in self.tags if t in self.SHORT]
        return f"{self.name} {self.dmg}" + (f" [{' '.join(bits)}]" if bits else "")


Wp = Weapon


@dataclass(frozen=True)
class UnitType:
    key: str
    name: str
    hp: int
    att: int
    defense: int
    prot: int
    mor: int
    weapons: tuple = ()
    move: int = 1
    mana: int = 0
    regen: int = 0
    spells: tuple = ()
    gold: int = 0
    iron: int = 0
    train: float = 5.0
    building: str = ""
    req_level: int = 1
    glyph: str = "sword"
    big: bool = False
    mounted: bool = False
    tint: tuple = None
    tags: tuple = ()
    desc: str = ""

    @property
    def rng(self):
        return max((w.rng for w in self.weapons if w.rng and "thrown" not in w.tags), default=0)

    def attack_line(self):
        s = " · ".join(w.short() for w in self.weapons)
        if self.spells:
            s += " · " + ", ".join(SPELLS[k].name for k in self.spells)
        return s


UNITS = {u.key: u for u in [
    # ---- your people ----
    UnitType("captain", "Captain", 17, 11, 11, 3, 15,
             (Wp("Longsword", 6), Wp("Shield Bash", 2, chance=25, tags=("stun",))),
             glyph="banner", big=True, tags=("commander",),
             desc="Leads the warband. Allies stand firm near."),
    UnitType("militia", "Militia", 9, 8, 8, 1, 8, (Wp("Pitchfork", 4, reach=2),),
             gold=10, train=4, building="hall", glyph="fork",
             desc="Cheap levies. Pitchforks reach past the front."),
    UnitType("spearman", "Spearman", 11, 10, 12, 4, 10,
             (Wp("Spear", 5, reach=2, tags=("repel", "anti_mount")),),
             gold=18, iron=4, train=6, building="barracks", glyph="spear",
             desc="Holds the line. Stops charges cold."),
    UnitType("berserker", "Berserker", 13, 11, 8, 1, 12,
             (Wp("Axe", 5), Wp("Axe", 5)),
             gold=24, iron=8, train=8, building="barracks", req_level=2, glyph="axe",
             tags=("frenzy",), desc="Two axes. Wounded: +3 damage, never flees."),
    UnitType("archer", "Archer", 8, 10, 7, 1, 9,
             (Wp("Longbow", 5, rng=10, ammo=12), Wp("Dagger", 3)),
             gold=20, train=6, building="range", glyph="bow",
             desc="Long range, lots of arrows. Weak up close."),
    UnitType("crossbow", "Crossbowman", 10, 10, 9, 5, 10,
             (Wp("Heavy Crossbow", 9, rng=6, ammo=8, tags=("ap", "reload")), Wp("Hatchet", 4)),
             gold=26, iron=10, train=8, building="range", req_level=2, glyph="xbow",
             desc="Short range armour-breaker. Slow to reload."),
    UnitType("knight", "Knight", 20, 12, 13, 9, 13,
             (Wp("Lance", 9, tags=("charge", "ap")), Wp("Longsword", 6), Wp("Hooves", 3)),
             move=2, gold=50, iron=25, train=14, building="stables", glyph="lance", big=True,
             mounted=True, desc="Devastating charge, then sword and hooves."),
    UnitType("horse_archer", "Horse Archer", 12, 11, 10, 3, 11,
             (Wp("Shortbow", 5, rng=7, ammo=10), Wp("Sabre", 4)),
             move=2, gold=40, iron=10, train=11, building="stables", req_level=2, glyph="hbow",
             mounted=True, tags=("skirmish",), desc="Rides away from melee and keeps shooting."),
    UnitType("priest", "Priest", 9, 7, 7, 1, 12, (Wp("Mace", 4),),
             mana=8, regen=1, spells=("heal", "smite"), gold=32, train=10, building="temple",
             glyph="cross", desc="Heals allies. Smites the undead."),
    UnitType("paladin", "Paladin", 18, 13, 14, 8, 15,
             (Wp("Holy Blade", 7, tags=("magic", "holy")), Wp("Shield Bash", 2, chance=25, tags=("stun",))),
             mana=3, regen=1, spells=("bless",), gold=60, iron=30, train=16, building="temple",
             req_level=2, glyph="shield", big=True, tags=("melee_caster",),
             desc="Frontline holy knight. Blesses those beside."),
    UnitType("apprentice", "Apprentice", 7, 7, 6, 0, 9, (Wp("Dagger", 2),),
             mana=8, regen=1, spells=("firebolt",), gold=28, train=8, building="arcanum",
             glyph="orb", desc="Cheap caster. Firebolts burn through armour."),
    UnitType("battlemage", "Battle Mage", 9, 8, 7, 0, 11, (Wp("Staff", 3),),
             mana=12, regen=1, spells=("fireball", "firebolt"), gold=48, iron=10, train=12,
             building="arcanum", req_level=2, glyph="flame",
             desc="Fireballs scorch a 3x3 area. Mind your lines."),
    UnitType("stormmage", "Storm Mage", 10, 9, 8, 1, 12, (Wp("Staff", 3),),
             mana=15, regen=1, spells=("lightning", "haste"), gold=75, iron=20, train=16,
             building="arcanum", req_level=3, glyph="bolt",
             desc="Chain lightning. Hastens allies to double move."),
    UnitType("druid", "Druid", 9, 7, 7, 1, 12, (Wp("Staff", 3),),
             mana=10, regen=2, spells=("summon_wolf", "entangle"), gold=38, train=10,
             building="grove", glyph="leaf", desc="Calls wolves and roots enemies in place."),
    UnitType("treant", "Treant", 30, 10, 9, 6, 30,
             (Wp("Branches", 8, tags=("sweep",)), Wp("Grasping Roots", 3, chance=30, tags=("stun",))),
             gold=65, train=18, building="grove", req_level=2, glyph="tree", big=True,
             tags=("mindless", "regen", "plant"), desc="Sweeping branches. Regrows, never flees."),
    UnitType("wolf", "Wolf", 10, 10, 9, 1, 9, (Wp("Bite", 5),), move=2, glyph="fang",
             desc="Summoned by a druid."),
    UnitType("tower", "Tower Archer", 12, 11, 9, 5, 20, (Wp("Longbow", 6, rng=10, ammo=14),),
             glyph="tower", tags=("static",), desc="Fires from the walls."),
    # ---- Ironveil ----
    UnitType("raider", "Raider", 9, 10, 8, 2, 9,
             (Wp("Hand Axe", 6), Wp("Throwing Axe", 5, rng=3, ammo=1, tags=("thrown", "ap"))),
             glyph="axe", desc="Throws an axe, then charges in."),
    UnitType("slinger", "Slinger", 7, 9, 7, 0, 8, (Wp("Sling", 4, rng=7, ammo=12), Wp("Knife", 3)),
             glyph="sling", desc="Skirmisher with a sling."),
    UnitType("brute", "Brute", 24, 10, 7, 3, 11,
             (Wp("Great Club", 11, chance=20, tags=("stun",)), Wp("Kick", 3)),
             glyph="club", big=True, desc="Huge. Its club can stun."),
    UnitType("warg", "Warg Rider", 12, 11, 10, 2, 9,
             (Wp("Spear", 5, tags=("charge",)), Wp("Scimitar", 4), Wp("Warg Bite", 5)),
             move=2, glyph="fang", mounted=True, desc="Rider and wolf both attack."),
    UnitType("ironguard", "Ironguard", 14, 12, 12, 6, 12,
             (Wp("Mace", 8, tags=("ap",)), Wp("Shield Bash", 2, chance=25, tags=("stun",))),
             glyph="helm", desc="Armoured elite. Maces crush armour."),
    UnitType("shaman", "Ash Shaman", 9, 8, 6, 0, 10, (Wp("Staff", 3),),
             mana=8, regen=1, spells=("firebolt",), glyph="star", desc="Hurls armour-burning cinders."),
    UnitType("hexer", "Hexer", 9, 8, 7, 0, 11, (Wp("Venom Dagger", 2, tags=("poison",)),),
             mana=10, regen=2, spells=("curse", "firebolt"), glyph="eye",
             desc="Hexes your best fighters."),
    UnitType("warlord", "Warlord", 34, 15, 13, 9, 16,
             (Wp("Great Axe", 11, tags=("sweep", "ap")), Wp("Kick", 3)),
             glyph="crown", big=True, tags=("commander",), desc="Master of Ironveil."),
    # ---- The Barrow ----
    UnitType("skeleton", "Skeleton", 8, 9, 9, 3, 30, (Wp("Rusty Sword", 6),),
             glyph="skull", tint=C["undead"], tags=("undead",), desc="Rattling dead. Never flees."),
    UnitType("ghoul", "Ghoul", 13, 11, 8, 1, 30,
             (Wp("Claw", 4), Wp("Claw", 4), Wp("Bite", 4, tags=("poison",))),
             glyph="claw", tint=C["undead"], tags=("undead",), desc="Claws twice, bites with grave-rot."),
    UnitType("wraith", "Wraith", 14, 12, 12, 0, 30, (Wp("Chill Touch", 6, tags=("an", "drain")),),
             glyph="ghost", tint=C["undead"], tags=("undead", "ethereal"),
             desc="Ethereal. Its touch ignores armour."),
    UnitType("necromancer", "Necromancer", 10, 8, 7, 1, 14, (Wp("Bone Staff", 3),),
             mana=12, regen=2, spells=("raise_dead", "drain"), glyph="necro", tint=C["undead"],
             desc="Raises the fallen as skeletons."),
    UnitType("barrowking", "Barrow King", 30, 14, 13, 8, 30,
             (Wp("Black Blade", 10, tags=("drain", "ap")), Wp("Grave Grip", 3, chance=30, tags=("stun",))),
             glyph="crown", big=True, tint=C["undead"], tags=("undead", "commander", "fear"),
             desc="Ancient lord. Terrifies those beside it."),
]}
RECRUITABLE = [u for u in UNITS.values() if u.building]


# --------------------------------------------------------------------------
# Buildings
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class BuildingType:
    key: str
    name: str
    gold: int
    iron: int
    time: float
    max_level: int
    desc: str
    color: tuple
    glyph: str = ""
    requires: tuple = ()


BUILDINGS = {b.key: b for b in [
    BuildingType("hall", "Town Hall", 120, 30, 25, 4,
                 "Heart of the town. Each level adds gold and 2 army cap. Trains Militia.",
                 (150, 116, 72), "banner"),
    BuildingType("market", "Market", 60, 0, 12, 3, "+1.2 gold per second per level.",
                 (178, 136, 62), "coin"),
    BuildingType("mine", "Iron Mine", 50, 0, 12, 3, "+0.7 iron per second per level.",
                 (112, 118, 128), "pick"),
    BuildingType("longhouse", "Longhouse", 50, 10, 10, 4,
                 "+4 army cap per level. Wounded soldiers recover faster.", (128, 96, 70), "bed"),
    BuildingType("barracks", "Barracks", 70, 15, 15, 2,
                 "Spearmen. Lv2: Berserkers, and idle troops drill up to Regular.",
                 (132, 72, 60), "sword"),
    BuildingType("range", "Archery Range", 70, 10, 15, 2,
                 "Archers. Lv2: Crossbowmen.", (90, 120, 70), "bow"),
    BuildingType("stables", "Stables", 110, 40, 22, 2, "Knights. Lv2: Horse Archers.",
                 (120, 100, 60), "lance", (("building", "hall", 2), ("building", "barracks", 1))),
    BuildingType("temple", "Temple", 90, 20, 18, 2,
                 "Priests. Lv2: Paladins. Speeds healing at home.", (170, 164, 150), "cross",
                 (("building", "hall", 2),)),
    BuildingType("arcanum", "Arcanum", 100, 30, 20, 3,
                 "Apprentices. Lv2: Battle Mages. Lv3: Storm Mages.", (96, 90, 150), "orb",
                 (("building", "hall", 2),)),
    BuildingType("grove", "Druid Grove", 80, 10, 16, 2, "Druids. Lv2: Treants.",
                 (70, 120, 70), "leaf", (("building", "hall", 2),)),
    BuildingType("forge", "Forge", 90, 40, 18, 3,
                 "Arms the whole army. Lv1: +1 armour. Lv2: +1 damage. Lv3: +2 armour.", (140, 90, 60), "anvil",
                 (("building", "barracks", 1), ("building", "mine", 1))),
    BuildingType("tower", "Watchtower", 60, 25, 14, 3,
                 "Each level adds a Tower Archer when your town is raided.", (100, 100, 110), "tower"),
]}

LEVEL_REQS = {
    ("hall", 4): (("target", "Ashfang Warcamp"),),
    ("barracks", 2): (("building", "hall", 2),),
    ("range", 2): (("building", "hall", 2),),
    ("stables", 2): (("building", "hall", 3),),
    ("temple", 2): (("building", "hall", 3),),
    ("arcanum", 2): (("building", "hall", 3),),
    ("arcanum", 3): (("target", "Cinder Shrine"),),
    ("grove", 2): (("building", "hall", 3),),
    ("forge", 3): (("building", "hall", 3),),
    ("longhouse", 4): (("building", "hall", 4),),
}


def building_reqs(key, level):
    base = BUILDINGS[key].requires if level == 1 else ()
    return tuple(base) + LEVEL_REQS.get((key, level), ())


def building_cost(key, target_level):
    b = BUILDINGS[key]
    steps = target_level - 2 if key == "hall" else target_level - 1
    mult = 1 + 0.8 * steps
    return int(b.gold * mult), int(b.iron * mult)


def building_time(key, target_level):
    b = BUILDINGS[key]
    steps = target_level - 2 if key == "hall" else target_level - 1
    return b.time * (1 + 0.6 * steps)


# --------------------------------------------------------------------------
# Campaign
# --------------------------------------------------------------------------
def comp_text(comp):
    return ", ".join(f"{n} {UNITS[k].name}" for k, n in comp)


def raid_force(n, undead=False, cap=10):
    n = min(n, cap)
    if undead:
        comp = [("skeleton", 3 + n), ("ghoul", n // 2), ("wraith", n // 4), ("necromancer", 1)]
    else:
        comp = [("raider", 2 + n), ("slinger", 1 + n // 2), ("brute", n // 2)]
        if n >= 3:
            comp += [("warg", (n - 1) // 2), ("ironguard", (n - 1) // 2)]
        if n >= 5:
            comp += [("shaman", n // 5), ("hexer", n // 6)]
    return [(k, c) for k, c in comp if c > 0]


class Target:
    def __init__(self, name, faction, desc, pos, prereq, garrison, pool, cap,
                 gold=0, income=0.0, iron_income=0.0, special="", relic=False, final=False,
                 xp=0, walls=0):
        self.name, self.faction, self.desc, self.pos = name, faction, desc, pos
        self.prereq = prereq
        self.xp, self.walls = xp, walls
        self.garrison = [Soldier(k, "enemy", xp + random.randint(0, 3)) for k, n in garrison for _ in range(n)]
        self.pool, self.cap = pool, cap
        self.gold, self.income, self.iron_income = gold, income, iron_income
        self.special, self.relic, self.final = special, relic, final
        self.conquered = False

    def grouped(self):
        groups = {}
        for u in self.garrison:
            groups.setdefault(u.t.key, []).append(u)
        return groups

    def summary(self):
        return ", ".join(f"{len(v)} {UNITS[k].name}" for k, v in self.grouped().items())

    def new_recruit(self):
        return Soldier(random.choice(self.pool), "enemy", self.xp + random.randint(0, 3))

    def bonuses(self):
        return {"enemy": {"defense": self.walls, "prot": self.walls // 2}} if self.walls else {}

    def reward_lines(self):
        lines = []
        if self.gold:
            lines.append(f"+{self.gold} gold")
        if self.income:
            lines.append(f"+{self.income:.1f} gold/s")
        if self.iron_income:
            lines.append(f"+{self.iron_income:.1f} iron/s")
        if self.special:
            lines.append(self.special)
        return lines


IV = ["raider", "slinger", "brute", "warg", "ironguard"]


def make_targets():
    return [
        Target("Rim Outpost", "Ironveil", "A palisade watching the old road.", (170, 330), [],
               [("raider", 4), ("slinger", 2)], ["raider", "slinger"], 9, 120, income=0.8),
        Target("Miller's Ford", "Ironveil", "Warg riders hold the river crossing.", (320, 500), [0],
               [("raider", 7), ("slinger", 3), ("warg", 3)], ["raider", "slinger", "warg"], 18,
               150, iron_income=0.5, xp=3),
        Target("Ashfang Warcamp", "Ironveil", "Wolf pens and war tents.", (320, 170), [0],
               [("raider", 8), ("ironguard", 3), ("brute", 3), ("slinger", 4), ("warg", 3)],
               IV, 28, 200, income=1.0, special="Unlocks Town Hall Lv4", xp=6),
        Target("Barrow of Whispers", "Barrow", "Old graves that do not stay shut.", (490, 560), [1],
               [("skeleton", 16), ("ghoul", 7), ("wraith", 4), ("necromancer", 2), ("barrowking", 1)],
               ["skeleton", "skeleton", "ghoul", "wraith"], 40, 250,
               special="Relics: +1 spell power for your casters. Ends undead raids.", relic=True, xp=8),
        Target("Cinder Shrine", "Ironveil", "Where the ash shamans chant.", (490, 120), [2],
               [("shaman", 5), ("hexer", 3), ("ironguard", 5), ("raider", 8), ("brute", 3)],
               ["shaman", "hexer", "ironguard", "raider"], 34, 250, income=1.0,
               special="Unlocks Arcanum Lv3 (Storm Mages)", xp=12),
        Target("Iron Gate", "Ironveil", "The fortified pass before the Hold. Walls: +2 defence.",
               (640, 340), [3, 4],
               [("ironguard", 12), ("brute", 6), ("raider", 10), ("slinger", 6), ("warg", 5),
                ("hexer", 3), ("shaman", 2)],
               IV + ["hexer", "ironguard"], 54, 300, income=1.0, iron_income=1.0, xp=20, walls=2),
        Target("Ironveil Hold", "Ironveil",
               "The Warlord's fortress. Walls: +4 defence, +2 armour. Take it to win the war.",
               (760, 340), [5],
               [("warlord", 1), ("ironguard", 12), ("brute", 6), ("raider", 10), ("slinger", 7),
                ("warg", 5), ("shaman", 3), ("hexer", 2), ("necromancer", 1)],
               IV + ["shaman", "hexer", "ironguard"], 58, final=True, xp=22, walls=4),
    ]


# --------------------------------------------------------------------------
# Soldiers
# --------------------------------------------------------------------------
class Soldier:
    _ids = itertools.count(1)

    def __init__(self, key, team, xp=0):
        self.t = UNITS[key]
        self.team = team
        self.xp = xp
        self.hp = self.max_hp
        self.heal_acc = 0.0
        self.uid = next(Soldier._ids)
        self.summoned = False
        self.reset_for_battle()

    @property
    def rank(self):
        r = 0
        for i, (threshold, _) in enumerate(RANKS):
            if self.xp >= threshold:
                r = i
        return r

    @property
    def rank_name(self):
        return RANKS[self.rank][1]

    @property
    def max_hp(self):
        return self.t.hp + self.rank * max(1, round(self.t.hp * 0.1))

    @property
    def att(self):
        return self.t.att + self.rank + self.b_att

    @property
    def defense(self):
        return self.t.defense + self.rank + self.b_def

    @property
    def frenzied(self):
        return "frenzy" in self.t.tags and self.hp * 2 < self.max_hp

    @property
    def dmg_bonus(self):
        return self.rank // 2 + self.b_dmg + (3 if self.frenzied else 0)

    @property
    def prot(self):
        return self.t.prot + self.b_prot

    @property
    def mor(self):
        return self.t.mor + self.rank

    @property
    def power(self):
        return self.rank // 2 + self.b_power

    @property
    def pos(self):
        return (self.gx, self.gy)

    @property
    def move(self):
        return self.t.move * (2 if self.hasted else 1)

    def reset_for_battle(self):
        self.state = "fight"          # fight / rout / fled / dead
        self.ammo = [w.ammo for w in self.t.weapons]
        self.mana = self.t.mana
        self.poison = 0
        self.poisoner = None
        self.hasted = False
        self.stats = {"dmg": 0, "taken": 0, "kills": 0, "hits": 0, "spells": 0, "healed": 0}
        self.reload = 0
        self.slowed = 0
        self.b_att = self.b_def = self.b_dmg = self.b_prot = self.b_power = 0
        self.blessed = self.cursed = self.raised = False
        self.summons = 0
        self.start_rank = self.rank
        self.start_xp = self.xp
        self.gx = self.gy = 0
        self.prev = (0, 0)
        self.disp_hp = self.hp
        self.disp_dead = False
        self.hidden = False
        self.flash = 0.0


# --------------------------------------------------------------------------
# Drawing helpers
# --------------------------------------------------------------------------
def draw_glyph(surf, glyph, c, s, col):
    x, y = c
    L = pygame.draw.line
    P = pygame.draw.polygon
    if glyph == "sword":
        L(surf, col, (x - s * .45, y + s * .45), (x + s * .45, y - s * .45), 3)
        L(surf, col, (x - s * .35, y - s * .05), (x + s * .05, y + s * .35), 2)
    elif glyph == "spear":
        L(surf, col, (x - s * .5, y + s * .5), (x + s * .35, y - s * .35), 2)
        P(surf, col, [(x + s * .55, y - s * .55), (x + s * .2, y - s * .38), (x + s * .38, y - s * .2)])
    elif glyph == "fork":
        L(surf, col, (x, y + s * .55), (x, y - s * .2), 2)
        L(surf, col, (x - s * .3, y - s * .2), (x + s * .3, y - s * .2), 2)
        for dx in (-.3, 0, .3):
            L(surf, col, (x + s * dx, y - s * .2), (x + s * dx, y - s * .55), 2)
    elif glyph in ("bow", "hbow"):
        pygame.draw.arc(surf, col, (x - s * .55, y - s * .55, s * .9, s * 1.1), -1.3, 1.3, 2)
        L(surf, col, (x - s * .05, y - s * .5), (x - s * .05, y + s * .5), 1)
        if glyph == "hbow":
            P(surf, col, [(x - s * .55, y + s * .55), (x - s * .3, y + s * .2), (x - s * .15, y + s * .55)])
    elif glyph == "xbow":
        L(surf, col, (x - s * .5, y - s * .1), (x + s * .5, y - s * .1), 3)
        L(surf, col, (x, y - s * .1), (x, y + s * .55), 3)
        pygame.draw.arc(surf, col, (x - s * .5, y - s * .45, s, s * .6), 0.2, 2.94, 2)
    elif glyph == "lance":
        L(surf, col, (x - s * .55, y + s * .55), (x + s * .5, y - s * .5), 3)
        P(surf, col, [(x - s * .1, y + s * .05), (x + s * .15, y - s * .2), (x - s * .35, y - s * .2)])
    elif glyph == "cross":
        L(surf, col, (x, y - s * .55), (x, y + s * .55), 3)
        L(surf, col, (x - s * .35, y - s * .15), (x + s * .35, y - s * .15), 3)
    elif glyph == "shield":
        P(surf, col, [(x - s * .45, y - s * .5), (x + s * .45, y - s * .5), (x + s * .45, y), (x, y + s * .55),
                      (x - s * .45, y)], 2)
        L(surf, col, (x, y - s * .35), (x, y + s * .3), 2)
        L(surf, col, (x - s * .25, y - s * .12), (x + s * .25, y - s * .12), 2)
    elif glyph == "banner":
        L(surf, col, (x - s * .35, y + s * .55), (x - s * .35, y - s * .55), 2)
        P(surf, col, [(x - s * .35, y - s * .55), (x + s * .5, y - s * .35), (x - s * .35, y - s * .1)])
    elif glyph == "axe":
        L(surf, col, (x - s * .3, y + s * .55), (x + s * .2, y - s * .5), 2)
        P(surf, col, [(x + s * .1, y - s * .3), (x + s * .55, y - s * .45), (x + s * .45, y)])
    elif glyph == "club":
        L(surf, col, (x - s * .4, y + s * .5), (x + s * .2, y - s * .2), 4)
        pygame.draw.circle(surf, col, (x + s * .25, y - s * .25), s * .28)
    elif glyph == "sling":
        pygame.draw.arc(surf, col, (x - s * .5, y - s * .5, s, s), 3.4, 6.0, 2)
        pygame.draw.circle(surf, col, (x + s * .1, y + s * .3), s * .18)
    elif glyph == "fang":
        P(surf, col, [(x - s * .5, y - s * .4), (x - s * .1, y - s * .4), (x - s * .3, y + s * .5)])
        P(surf, col, [(x + s * .1, y - s * .4), (x + s * .5, y - s * .4), (x + s * .3, y + s * .5)])
    elif glyph == "star":
        for a in range(4):
            ang = a * math.pi / 4
            L(surf, col, (x - math.cos(ang) * s * .55, y - math.sin(ang) * s * .55),
              (x + math.cos(ang) * s * .55, y + math.sin(ang) * s * .55), 2)
    elif glyph == "crown":
        P(surf, col, [(x - s * .55, y + s * .35), (x - s * .55, y - s * .4), (x - s * .25, y - s * .05),
                      (x, y - s * .5), (x + s * .25, y - s * .05), (x + s * .55, y - s * .4),
                      (x + s * .55, y + s * .35)])
    elif glyph == "helm":
        P(surf, col, [(x - s * .45, y + s * .45), (x - s * .45, y - s * .15), (x, y - s * .55),
                      (x + s * .45, y - s * .15), (x + s * .45, y + s * .45)])
        L(surf, C["ink"], (x - s * .3, y), (x + s * .3, y), 3)
    elif glyph == "tower":
        pygame.draw.rect(surf, col, (x - s * .35, y - s * .25, s * .7, s * .8))
        for dx in (-.35, -.05, .25):
            pygame.draw.rect(surf, col, (x + s * dx, y - s * .5, s * .15, s * .25))
    elif glyph == "orb":
        pygame.draw.circle(surf, col, (x, y), s * .25)
        for a in range(8):
            ang = a * math.pi / 4
            L(surf, col, (x + math.cos(ang) * s * .35, y + math.sin(ang) * s * .35),
              (x + math.cos(ang) * s * .55, y + math.sin(ang) * s * .55), 2)
    elif glyph == "flame":
        P(surf, col, [(x, y - s * .6), (x + s * .4, y), (x + s * .25, y + s * .5), (x - s * .25, y + s * .5),
                      (x - s * .4, y), (x - s * .1, y - s * .15)])
    elif glyph == "bolt":
        P(surf, col, [(x + s * .1, y - s * .6), (x - s * .35, y + s * .05), (x - s * .02, y + s * .05),
                      (x - s * .15, y + s * .6), (x + s * .35, y - s * .1), (x + s * .02, y - s * .1)])
    elif glyph == "leaf":
        P(surf, col, [(x, y - s * .6), (x + s * .35, y - s * .1), (x, y + s * .45), (x - s * .35, y - s * .1)])
        L(surf, C["ink"], (x, y - s * .4), (x, y + s * .55), 2)
    elif glyph == "tree":
        pygame.draw.rect(surf, col, (x - s * .1, y, s * .2, s * .55))
        pygame.draw.circle(surf, col, (x, y - s * .15), s * .4)
    elif glyph == "skull":
        pygame.draw.circle(surf, col, (x, y - s * .1), s * .38)
        pygame.draw.rect(surf, col, (x - s * .2, y + s * .15, s * .4, s * .3))
        pygame.draw.circle(surf, C["ink"], (x - s * .14, y - s * .1), s * .1)
        pygame.draw.circle(surf, C["ink"], (x + s * .14, y - s * .1), s * .1)
    elif glyph == "claw":
        for dx in (-.3, 0, .3):
            L(surf, col, (x + s * dx - s * .1, y + s * .5), (x + s * dx + s * .15, y - s * .5), 2)
    elif glyph == "ghost":
        P(surf, col, [(x - s * .4, y + s * .55), (x - s * .4, y - s * .1), (x, y - s * .55), (x + s * .4, y - s * .1),
                      (x + s * .4, y + s * .55), (x + s * .2, y + s * .35), (x, y + s * .55), (x - s * .2, y + s * .35)])
        pygame.draw.circle(surf, C["ink"], (x - s * .14, y - s * .1), s * .08)
        pygame.draw.circle(surf, C["ink"], (x + s * .14, y - s * .1), s * .08)
    elif glyph == "eye":
        pygame.draw.ellipse(surf, col, (x - s * .55, y - s * .3, s * 1.1, s * .6), 2)
        pygame.draw.circle(surf, col, (x, y), s * .18)
    elif glyph == "necro":
        L(surf, col, (x - s * .35, y + s * .55), (x - s * .35, y - s * .5), 2)
        pygame.draw.circle(surf, col, (x + s * .12, y - s * .1), s * .3)
        pygame.draw.circle(surf, C["ink"], (x + s * .02, y - s * .12), s * .07)
        pygame.draw.circle(surf, C["ink"], (x + s * .22, y - s * .12), s * .07)
    elif glyph == "anvil":
        P(surf, col, [(x - s * .55, y - s * .3), (x + s * .5, y - s * .3), (x + s * .3, y), (x + s * .15, y),
                      (x + s * .25, y + s * .45), (x - s * .25, y + s * .45), (x - s * .15, y), (x - s * .3, y)])
    elif glyph == "coin":
        pygame.draw.circle(surf, col, (x, y), s * .5, 2)
        pygame.draw.circle(surf, col, (x, y), s * .2)
    elif glyph == "pick":
        pygame.draw.arc(surf, col, (x - s * .55, y - s * .55, s * 1.1, s * .8), 0.3, 2.84, 3)
        L(surf, col, (x, y - s * .55), (x, y + s * .55), 3)
    elif glyph == "bed":
        P(surf, col, [(x - s * .55, y), (x, y - s * .5), (x + s * .55, y)], 2)
        pygame.draw.rect(surf, col, (x - s * .4, y, s * .8, s * .45), 2)


def draw_token(surf, t, team, center, hp_frac=1.0, flash=False, routed=False, radius=None,
               bar=True, rank=0, mana_frac=None):
    r = radius or (20 if t.big else 16)
    team_col = C["blue"] if team == "player" else (t.tint or C["red"])
    body = C["white"] if flash else team_col
    if routed:
        body = mix(body, (110, 110, 110), 0.6)
    x, y = center
    pygame.draw.ellipse(surf, (0, 0, 0), (x - r, y + r - 5, r * 2, 10))
    pygame.draw.circle(surf, C["ink"], (x, y), r + 2)
    pygame.draw.circle(surf, body, (x, y), r)
    pygame.draw.circle(surf, mix(body, C["ink"], 0.35), (x, y), r - 3)
    draw_glyph(surf, t.glyph, (x, y), r * 1.05, C["paper"])
    if bar:
        bw = r * 2 + 4
        pygame.draw.rect(surf, (36, 34, 30), (x - bw / 2, y - r - 9, bw, 4))
        pygame.draw.rect(surf, C["green"] if hp_frac > .4 else C["gold"],
                         (x - bw / 2, y - r - 9, bw * max(0, min(1, hp_frac)), 4))
        if mana_frac is not None:
            pygame.draw.rect(surf, (30, 34, 48), (x - bw / 2, y - r - 5, bw, 2))
            pygame.draw.rect(surf, C["mana"], (x - bw / 2, y - r - 5, bw * max(0, min(1, mana_frac)), 2))
    for i in range(rank):
        px = x - (rank - 1) * 4 + i * 8
        pygame.draw.polygon(surf, C["gold"], [(px - 3, y + r - 1), (px, y + r + 3), (px + 3, y + r - 1)])
    if routed:
        pygame.draw.line(surf, C["paper"], (x + r - 2, y - r), (x + r - 2, y - r - 16), 2)
        pygame.draw.rect(surf, C["white"], (x + r - 1, y - r - 16, 9, 6))


def draw_glow(surf, pos, radius, color, alpha):
    size = int(radius * 2 + 4)
    g = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(g, (*color, max(0, min(255, int(alpha)))), (size // 2, size // 2), int(radius))
    surf.blit(g, (pos[0] - size // 2, pos[1] - size // 2))


class UI:
    """Tiny immediate-mode button system: buttons are re-registered every frame."""

    def __init__(self):
        self.buttons = []
        self.mouse = (0, 0)

    def reset(self, mouse):
        self.buttons = []
        self.mouse = mouse

    def button(self, surf, rect, label, cb, enabled=True, accent=False, font="bold"):
        rect = pygame.Rect(rect)
        hover = enabled and rect.collidepoint(self.mouse)
        if not enabled:
            bg, fg, edge = (38, 40, 44), C["dim"], (52, 54, 58)
        elif accent:
            bg, fg, edge = (132, 98, 40) if hover else (110, 80, 34), C["white"], C["gold"]
        else:
            bg, fg, edge = (66, 72, 80) if hover else (52, 57, 64), C["paper"], (90, 96, 104)
        pygame.draw.rect(surf, bg, rect, border_radius=4)
        pygame.draw.rect(surf, edge, rect, 1, border_radius=4)
        text(surf, label, rect.center, font, fg, center=True)
        if enabled:
            self.buttons.append((rect, cb))

    def click(self, pos):
        for rect, cb in reversed(self.buttons):
            if rect.collidepoint(pos):
                cb()
                return True
        return False


# --------------------------------------------------------------------------
# Battle (automatic, round based)
# --------------------------------------------------------------------------
COLS, ROWS, TILE = 22, 11, 54
FIELD_X, FIELD_Y = (W - COLS * TILE) // 2, 62
ROUND_TIME = 0.85
MAX_ROUNDS = 45
XP_PER_BATTLE = 12
DIRS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


def tile_center(gx, gy):
    return (FIELD_X + gx * TILE + TILE / 2, FIELD_Y + gy * TILE + TILE / 2)


def cheb(a, b):
    return max(abs(a.gx - b.gx), abs(a.gy - b.gy))


def unit_role(t):
    if "static" in t.tags:
        return "static"
    if "commander" in t.tags:
        return "support"
    if t.spells and "melee_caster" not in t.tags:
        kinds = {SPELLS[s].kind for s in t.spells}
        return "support" if kinds & {"heal", "summon", "entangle"} else "caster"
    if t.rng:
        return "ranged"
    return "front"


ROLE_COLS = {"static": [0, 1], "support": [1, 2, 0], "caster": [2, 1, 3],
             "ranged": [3, 2, 4], "front": [6, 5, 4, 7, 3]}


class Battle:
    def __init__(self, kind, title, players, enemies, attacker, target=None, bonuses=None, spoils=("", "")):
        self.kind, self.title, self.attacker, self.target = kind, title, attacker, target
        self.spoils = spoils
        self.defender = "enemy" if attacker == "player" else "player"
        self.units = players + enemies
        self.occ = {}
        for u in self.units:
            u.reset_for_battle()
            for stat, val in (bonuses or {}).get(u.team, {}).items():
                if "static" not in u.t.tags:
                    attr = "b_def" if stat == "defense" else "b_" + stat
                    setattr(u, attr, getattr(u, attr) + val)
        self.deploy(players, "player")
        self.deploy(enemies, "enemy")
        for u in self.units:
            u.prev = u.pos
        self.start = {"player": len(players), "enemy": len(enemies)}
        self.had_commander = {team: self.commander_up(team) for team in ("player", "enemy")}
        self.morale_marks = {"player": set(), "enemy": set()}
        self.round = 0
        self.speed = 1
        self.paused = False
        self.timer = 1.6
        self.anim_t = 1.0
        self.shots, self.strikes, self.floaters, self.blasts = [], {}, [], []
        self.instant = False
        self.log = [f"The armies deploy: {len(players)} against {len(enemies)}."]
        self.round_notes, self.round_slain = [], []
        self.round_hits = self.round_heals = 0
        self.result = None
        self.reason = ""
        self.promotions = []
        self.weapon_dmg, self.spell_counts = {}, {}
        self.friendly = {"player": 0, "enemy": 0}
        self.poison_dmg = {"player": 0, "enemy": 0}
        self.finished = False
        self.ui = UI()
        self.continue_cb = None

    # ---- setup -----------------------------------------------------------
    def deploy(self, units, team):
        order = sorted(range(ROWS), key=lambda r: (abs(r - ROWS // 2), r))
        ranked = sorted(units, key=lambda u: (["static", "support", "caster", "ranged", "front"]
                                              .index(unit_role(u.t)), u.t.mounted))
        for u in ranked:
            cols = ROLE_COLS[unit_role(u.t)]
            spots = [(c, r) for c in cols for r in order] + [(c, r) for c in range(10) for r in order]
            for c, r in spots:
                gx = c if team == "player" else COLS - 1 - c
                if (gx, r) not in self.occ:
                    u.gx, u.gy = gx, r
                    self.occ[(gx, r)] = u
                    break

    # ---- queries ---------------------------------------------------------
    def active(self, u):
        return u.state in ("fight", "rout")

    def foes(self, u):
        return [v for v in self.units if v.team != u.team and self.active(v)]

    def allies(self, u):
        return [v for v in self.units if v.team == u.team and v.state == "fight"]

    def lost_frac(self, team):
        fighting = sum(1 for v in self.units if v.team == team and v.state == "fight")
        return max(0.0, 1 - fighting / max(1, self.start[team]))

    def commander_up(self, team):
        return any(v.team == team and v.state == "fight" and "commander" in v.t.tags for v in self.units)

    def side_name(self, team):
        return "your" if team == "player" else "enemy"

    # ---- effects ---------------------------------------------------------
    def schedule(self, u, label, color, action=None, delay=0.5):
        if self.instant:
            if action:
                action()
            return
        x, y = tile_center(u.gx, u.gy)
        self.floaters.append({"x": x + random.uniform(-7, 7), "y": y - 22, "label": label,
                              "color": color, "delay": ROUND_TIME * delay, "age": 0.0,
                              "action": action})

    def shot(self, a, target_pos, style):
        self.shots.append((tile_center(a.gx, a.gy), tile_center(*target_pos), style))

    def spawn(self, key, team, pos):
        s = Soldier(key, team)
        s.summoned = True
        s.gx, s.gy = pos
        s.prev = pos
        s.hidden = True
        self.occ[pos] = s
        self.units.append(s)

        def show(v=s):
            v.hidden = False
        self.schedule(s, UNITS[key].name, C["nature"] if key == "wolf" else C["dark"], show)
        return s

    def morale_check(self, u, extra=0):
        if u.state != "fight" or {"commander", "static", "undead", "mindless"} & set(u.t.tags):
            return
        if u.frenzied:
            return
        bonus = 2 if self.commander_up(u.team) else (-2 if self.had_commander[u.team] else 0)
        if u.mor + bonus + drn() < 7 + int(self.lost_frac(u.team) * 8) + extra + drn():
            u.state = "rout"
            self.schedule(u, "ROUT", C["white"])
            self.round_notes.append(f"{'Your' if u.team == 'player' else 'Enemy'} {u.t.name} flees!")

    def damage(self, a, d, dmg, ap=False, an=False, magic=False, holy=False, stray=False,
               special=False, source=""):
        if d.state == "dead":
            return 0
        if "ethereal" in d.t.tags and not magic and random.random() < 0.75:
            self.schedule(d, "phase", C["muted"])
            return 0
        if holy and "undead" in d.t.tags:
            dmg = int(dmg * 1.5) + 1
            special = True
        prot = 0 if an else (d.prot // 2 if ap else d.prot)
        dealt = max(0, dmg + drn() - (prot + drn()))
        if special:
            color = (255, 214, 120)
        elif magic:
            color = (200, 190, 255)
        else:
            color = C["white"] if dealt else C["muted"]
        return self.apply_damage(a, d, dealt, source, color, stray)

    def apply_damage(self, a, d, dealt, source, color, stray=False):
        d.hp = max(0, d.hp - dealt)
        dead = d.hp <= 0
        self.round_hits += 1
        d.stats["taken"] += dealt
        if a is not None and a.team != d.team:
            a.stats["dmg"] += dealt
            if dealt:
                a.xp += 1
            key = (a.team, source)
            self.weapon_dmg[key] = self.weapon_dmg.get(key, 0) + dealt
        elif a is not None and dealt:
            self.friendly[a.team] += dealt

        def act(u=d, hp=d.hp, dead=dead, dealt=dealt):
            u.disp_hp = hp
            if dealt:
                u.flash = 0.18
            if dead:
                u.disp_dead = True

        self.schedule(d, str(dealt), color, act)
        if dead:
            d.state = "dead"
            self.occ.pop(d.pos, None)
            if a is not None and a.team != d.team:
                a.xp += 3
                a.stats["kills"] += 1
            how = " (poison)" if source == "Poison" else ""
            self.round_slain.append(f"{self.side_name(d.team)} {d.t.name}{how}")
            if stray and a is not None and a.team == d.team:
                self.round_notes.append(f"A stray shot killed one of {'your' if a.team == 'player' else 'their'} own!")
        elif d.hp * 2 < d.max_hp:
            self.morale_check(d)
        return dealt

    def on_hit(self, a, d, w, dealt):
        if d.state == "dead" or dealt <= 0:
            return
        if "stun" in w.tags and random.randint(1, 100) <= w.chance and "static" not in d.t.tags:
            d.slowed = max(d.slowed, 1)
            self.schedule(d, "stunned", C["holy"], delay=0.6)
        if "poison" in w.tags and not ({"undead", "plant"} & set(d.t.tags)):
            d.poison = min(9, d.poison + 3)
            d.poisoner = a
            self.schedule(d, "poisoned", C["nature"], delay=0.6)
        if "drain" in w.tags and a.hp < a.max_hp:
            gain = min(dealt // 2 + 1, a.max_hp - a.hp)
            a.hp += gain

            def act(v=a, hp=a.hp):
                v.disp_hp = hp
            self.schedule(a, f"+{gain}", C["dark"], act, delay=0.6)

    def strike(self, a, d, w, charge=False):
        harass = max(0, sum(1 for f in self.foes(d) if cheb(f, d) == 1) - 1)
        defense = d.defense - harass - (4 if d.state == "rout" else 0)
        if a.att + w.att + drn() <= defense + drn():
            return 0
        a.stats["hits"] += 1
        bonus = (3 if charge else 0) + (5 if "anti_mount" in w.tags and d.t.mounted else 0)
        dealt = self.damage(a, d, w.dmg + a.dmg_bonus + bonus, ap="ap" in w.tags, an="an" in w.tags,
                            magic="magic" in w.tags, holy="holy" in w.tags, special=bool(bonus),
                            source=w.name)
        self.on_hit(a, d, w, dealt)
        return dealt

    def melee(self, a, d, moved=False, reach_only=False):
        """Attack with every melee weapon the unit carries, like CoE5."""
        self.strikes[a.uid] = tile_center(d.gx, d.gy)
        weapons = [w for w in a.t.weapons if not w.rng and ("charge" not in w.tags or moved)]
        if reach_only:
            weapons = [w for w in weapons if w.reach > 1]
        charging = moved and any("charge" in w.tags for w in weapons)
        if charging and cheb(a, d) == 1 and d.state == "fight":
            repel = [w for w in d.t.weapons if "repel" in w.tags]
            if repel and self.strike(d, a, repel[0]) > 0:
                self.schedule(a, "repelled!", C["white"], delay=0.35)
                self.round_notes.append(f"{'Your' if d.team == 'player' else 'Enemy'} {d.t.name} "
                                        f"breaks a {a.t.name}'s charge!")
                weapons = [w for w in weapons if "charge" not in w.tags]
                charging = False
        for w in weapons:
            if a.state != "fight":
                return
            target = d if self.active(d) and cheb(a, d) <= w.reach else None
            if target is None:
                near = [f for f in self.foes(a) if cheb(a, f) <= w.reach]
                if not near:
                    return
                target = min(near, key=lambda f: f.hp)
            self.strike(a, target, w, charge=charging and "charge" in w.tags)
            if "sweep" in w.tags:
                others = [f for f in self.foes(a) if f is not target and cheb(a, f) == 1]
                if others:
                    self.strike(a, random.choice(others), w)

    def shoot(self, a, d, idx):
        w = a.t.weapons[idx]
        a.ammo[idx] -= 1
        dist = cheb(a, d)
        kw = dict(ap="ap" in w.tags, an="an" in w.tags, magic="magic" in w.tags, source=w.name)
        if a.att + w.att + drn() - dist // 3 > 6 + d.defense // 3 + drn():
            self.shot(a, d.pos, "arrow")
            a.stats["hits"] += 1
            self.on_hit(a, d, w, self.damage(a, d, w.dmg + a.dmg_bonus, **kw))
            return
        tx, ty = d.gx + random.randint(-1, 1), d.gy + random.randint(-1, 1)
        self.shot(a, (tx, ty), "arrow")
        victim = self.occ.get((tx, ty))
        if victim is not None and victim is not d and victim is not a:
            self.damage(a, victim, w.dmg, stray=True, **kw)

    # ---- spells ------------------------------------------------------------
    def cast(self, u):
        for key in u.t.spells:
            sp = SPELLS[key]
            if u.mana < sp.cost:
                continue
            if getattr(self, "sp_" + sp.kind)(u, sp):
                u.mana -= sp.cost
                u.xp += 1
                u.stats["spells"] += 1
                key = (u.team, sp.name)
                self.spell_counts[key] = self.spell_counts.get(key, 0) + 1
                return True
        return False

    def pick_target(self, u, rng, prefer=None):
        foes = [f for f in self.foes(u) if cheb(u, f) <= rng]
        if prefer:
            preferred = [f for f in foes if prefer(f)]
            foes = preferred or foes
        fighting = [f for f in foes if f.state == "fight"] or foes
        if not fighting:
            return None
        fighting.sort(key=lambda f: cheb(u, f))
        return random.choice(fighting[:4])

    def sp_bolt(self, u, sp):
        d = self.pick_target(u, sp.rng, (lambda f: "undead" in f.t.tags) if sp.holy else None)
        if d is None:
            return False
        self.shot(u, d.pos, sp.style)
        if 10 + u.power + drn() > 5 + d.defense // 3 + drn():
            self.damage(u, d, sp.dmg + u.power, ap=sp.ap, magic=True, holy=sp.holy, source=sp.name)
        return True

    def area(self, center):
        cx, cy = center
        return [self.occ[(cx + dx, cy + dy)] for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                if (cx + dx, cy + dy) in self.occ]

    def best_area(self, u, rng, ally_penalty, want):
        best, best_score = None, 0
        for f in self.foes(u):
            if cheb(u, f) > rng:
                continue
            score = 0
            for v in self.area(f.pos):
                if v.team != u.team:
                    score += 1 if want(v) else 0
                else:
                    score -= ally_penalty
            if score > best_score:
                best, best_score = f.pos, score
        return best, best_score

    def sp_blast(self, u, sp):
        center, score = self.best_area(u, sp.rng, 2, lambda v: True)
        if center is None or score < (2 if len(self.foes(u)) > 3 else 1):
            return False
        self.shot(u, center, sp.style)
        self.blasts.append((tile_center(*center), TILE * 1.5, C[sp.style]))
        for v in self.area(center):
            self.damage(u, v, sp.dmg + u.power, magic=True, source=sp.name)
        return True

    def sp_chain(self, u, sp):
        d = self.pick_target(u, sp.rng)
        if d is None:
            return False
        hit, last = [], u
        while d is not None and len(hit) < 3:
            self.shots.append((tile_center(last.gx, last.gy), tile_center(d.gx, d.gy), "lightning"))
            hit.append(d)
            last = d
            power = sp.dmg + u.power - 2 * (len(hit) - 1)
            self.damage(u, d, power, ap=True, magic=True, source=sp.name)
            nxt = [f for f in self.foes(u) if f not in hit and cheb(last, f) <= 2]
            d = min(nxt, key=lambda f: cheb(last, f)) if nxt else None
        return True

    def sp_entangle(self, u, sp):
        center, score = self.best_area(u, sp.rng, 0, lambda v: v.state == "fight" and not v.slowed)
        if center is None or score < 2:
            return False
        self.shot(u, center, sp.style)
        self.blasts.append((tile_center(*center), TILE * 1.5, C["nature"]))
        for v in self.area(center):
            if v.team != u.team and v.state == "fight":
                v.slowed = sp.slow
                self.schedule(v, "rooted", C["nature"])
        return True

    def sp_summon(self, u, sp):
        foes = self.foes(u)
        if not foes or u.summons >= 3:
            return False
        goal = min(foes, key=lambda f: cheb(u, f))
        spots = [(u.gx + dx, u.gy + dy) for dx, dy in DIRS]
        spots = [p for p in spots if 0 <= p[0] < COLS and 0 <= p[1] < ROWS and p not in self.occ]
        if not spots:
            return False
        pos = min(spots, key=lambda p: math.hypot(p[0] - goal.gx, p[1] - goal.gy))
        u.summons += 1
        self.spawn("wolf", u.team, pos)
        self.blasts.append((tile_center(*pos), TILE * 0.8, C["nature"]))
        return True

    def sp_heal(self, u, sp):
        hurt = [a for a in self.allies(u) if a.max_hp - a.hp >= 3 and cheb(u, a) <= sp.rng]
        if not hurt:
            return False
        a = min(hurt, key=lambda v: v.hp / v.max_hp)
        amount = min(sp.dmg + u.power + random.randint(0, 2), a.max_hp - a.hp)
        a.hp += amount
        self.round_heals += amount
        u.stats["healed"] += amount

        def act(v=a, hp=a.hp):
            v.disp_hp = hp
        self.schedule(a, f"+{amount}", C["green"], act, delay=0.3)
        return True

    def sp_bless(self, u, sp):
        near = [a for a in self.allies(u) if cheb(u, a) <= sp.rng and not a.blessed
                and "static" not in a.t.tags]
        if len(near) < 2:
            return False
        for a in near:
            a.blessed = True
            a.b_att += 2
            a.b_def += 2
            self.schedule(a, "blessed", C["holy"], delay=0.3)
        self.blasts.append((tile_center(u.gx, u.gy), TILE * 2.5, C["holy"]))
        return True

    def sp_haste(self, u, sp):
        near = [a for a in self.allies(u) if cheb(u, a) <= sp.rng and not a.hasted
                and "static" not in a.t.tags and a is not u]
        if len(near) < 3:
            return False
        for a in near:
            a.hasted = True
            self.schedule(a, "hasted", C["lightning"], delay=0.3)
        self.blasts.append((tile_center(u.gx, u.gy), TILE * 3, C["lightning"]))
        return True

    def sp_curse(self, u, sp):
        foes = [f for f in self.foes(u) if f.state == "fight" and not f.cursed and cheb(u, f) <= sp.rng]
        if not foes:
            return False
        d = max(foes, key=lambda f: f.att + sum(w.dmg for w in f.t.weapons if not w.rng))
        d.cursed = True
        d.b_att -= 2
        d.b_def -= 3
        self.shot(u, d.pos, "dark")
        self.schedule(d, "hexed", C["dark"])
        return True

    def sp_raise(self, u, sp):
        corpses = [v for v in self.units if v.state == "dead" and not v.raised and v.pos not in self.occ
                   and cheb(u, v) <= sp.rng and "static" not in v.t.tags]
        if not corpses:
            return False
        v = min(corpses, key=lambda c: cheb(u, c))
        v.raised = True

        def hide(c=v):
            c.hidden = True
        self.schedule(v, "", C["dark"], hide, delay=0.45)
        self.shot(u, v.pos, "dark")
        self.spawn("skeleton", u.team, v.pos)
        self.blasts.append((tile_center(*v.pos), TILE * 0.8, C["dark"]))
        return True

    # ---- movement ----------------------------------------------------------
    def step_toward(self, u, goal):
        best, best_key = None, (cheb(u, goal), math.hypot(u.gx - goal.gx, u.gy - goal.gy))
        for dx, dy in DIRS:
            nx, ny = u.gx + dx, u.gy + dy
            if not (0 <= nx < COLS and 0 <= ny < ROWS) or (nx, ny) in self.occ:
                continue
            key = (max(abs(nx - goal.gx), abs(ny - goal.gy)), math.hypot(nx - goal.gx, ny - goal.gy))
            if key < best_key:
                best, best_key = (nx, ny), key
        if best is None:
            return False
        del self.occ[u.pos]
        u.gx, u.gy = best
        self.occ[best] = u
        return True

    def advance(self, u, foes, stop_range=1):
        goal = min(foes, key=lambda f: cheb(u, f) + (3 if f.state == "rout" else 0))
        moved = False
        for _ in range(u.move):
            if cheb(u, goal) <= stop_range or not self.step_toward(u, goal):
                break
            moved = True
        return moved

    def flee(self, u):
        edge, dx = (0, -1) if u.team == "player" else (COLS - 1, 1)
        for _ in range(u.move + 1):
            if u.gx == edge:
                break
            for ddy in random.sample([0, -1, 1], 3):
                nx, ny = u.gx + dx, u.gy + ddy
                if 0 <= ny < ROWS and (nx, ny) not in self.occ:
                    del self.occ[u.pos]
                    u.gx, u.gy = nx, ny
                    self.occ[(nx, ny)] = u
                    break
        if u.gx == edge:
            u.state = "fled"
            self.occ.pop(u.pos, None)

    # ---- one unit's turn ---------------------------------------------------
    def ranged_weapon(self, u, thrown=False):
        for i, w in enumerate(u.t.weapons):
            if w.rng and ("thrown" in w.tags) == thrown and u.ammo[i] > 0:
                return i, w
        return None, None

    def retreat(self, u, foes):
        for _ in range(u.move):
            here = min(cheb(u, f) for f in foes)
            best, best_d = None, here
            for dx, dy in DIRS:
                p = (u.gx + dx, u.gy + dy)
                if not (0 <= p[0] < COLS and 0 <= p[1] < ROWS) or p in self.occ:
                    continue
                dd = min(max(abs(p[0] - f.gx), abs(p[1] - f.gy)) for f in foes)
                if dd > best_d:
                    best, best_d = p, dd
            if best is None:
                return
            del self.occ[u.pos]
            u.gx, u.gy = best
            self.occ[best] = u

    def act(self, u):
        t = u.t
        if "regen" in t.tags and u.hp < u.max_hp:
            u.hp = min(u.max_hp, u.hp + 2)

            def act(v=u, hp=u.hp):
                v.disp_hp = hp
            self.schedule(u, "+2", C["green"], act, delay=0.2)
        if u.slowed > 0:
            u.slowed -= 1
            return
        foes = self.foes(u)
        if not foes:
            return
        adj = [f for f in foes if cheb(u, f) == 1]
        if t.spells:
            if self.cast(u):
                return
            if "melee_caster" not in t.tags:
                if adj:
                    self.melee(u, random.choice(adj))
                    return
                reach = [SPELLS[s].rng for s in t.spells if SPELLS[s].offensive and u.mana >= SPELLS[s].cost]
                if reach:
                    self.advance(u, foes, stop_range=max(reach))
                return

        idx, w = self.ranged_weapon(u)
        if w is not None:
            if adj and "skirmish" in t.tags:
                self.retreat(u, foes)
                adj = [f for f in foes if cheb(u, f) == 1]
            if not adj:
                if u.reload > 0:
                    u.reload -= 1
                    return
                d = self.pick_target(u, w.rng)
                if d is not None:
                    self.shoot(u, d, idx)
                    if "reload" in w.tags:
                        u.reload = 1
                elif "static" not in t.tags:
                    self.advance(u, foes, stop_range=w.rng)
                return
        if "static" in t.tags:
            if adj:
                self.melee(u, random.choice(adj))
            return
        if adj:
            self.melee(u, min(adj, key=lambda f: f.hp))
            return
        if any(wp.reach > 1 for wp in t.weapons):
            far = [f for f in foes if cheb(u, f) == 2]
            if far:
                self.melee(u, min(far, key=lambda f: f.hp), reach_only=True)
                return
        ti, tw = self.ranged_weapon(u, thrown=True)
        if tw is not None:
            d = self.pick_target(u, tw.rng)
            if d is not None and cheb(u, d) >= 2:
                self.shoot(u, d, ti)
                self.advance(u, foes)
                return
        moved = self.advance(u, foes)
        adj = [f for f in foes if self.active(f) and cheb(u, f) == 1]
        if adj:
            self.melee(u, min(adj, key=lambda f: f.hp), moved=moved)

    def resolve_round(self):
        self.round += 1
        self.shots, self.strikes, self.blasts = [], {}, []
        self.round_hits = self.round_heals = 0
        self.round_slain, self.round_notes = [], []
        for u in self.units:
            u.prev = u.pos
            if u.state == "fight" and u.t.regen:
                u.mana = min(u.t.mana, u.mana + u.t.regen)
        for u in list(self.units):
            if u.poison > 0 and self.active(u):
                dmg = 1 + u.poison // 3
                u.poison -= 1
                self.poison_dmg[u.team] += dmg
                self.apply_damage(u.poisoner, u, dmg, "Poison", C["nature"])
        for u in self.units:
            if u.state == "fight" and "fear" in u.t.tags:
                for f in self.foes(u):
                    if f.state == "fight" and cheb(u, f) == 1:
                        self.morale_check(f, extra=2)
        for team in ("player", "enemy"):
            lost = self.lost_frac(team)
            for mark in (0.5, 0.75):
                if lost >= mark and mark not in self.morale_marks[team]:
                    self.morale_marks[team].add(mark)
                    self.round_notes.append(("Your" if team == "player" else "The enemy")
                                            + " army wavers after heavy losses.")
                    for u in self.units:
                        if u.team == team:
                            self.morale_check(u, extra=-2)
        order = [u for u in self.units if self.active(u)]
        random.shuffle(order)
        order.sort(key=lambda u: -u.move)
        for u in order:
            if u.state == "rout":
                self.flee(u)
            elif u.state == "fight":
                self.act(u)

        line = f"Round {self.round}: {self.round_hits} blows landed"
        if self.round_heals:
            line += f", {self.round_heals} healed"
        if self.round_slain:
            line += ". Slain: " + ", ".join(self.round_slain[:5]) + ("..." if len(self.round_slain) > 5 else "")
        self.log.append(line)
        self.log.extend(self.round_notes[:3])

        alive = {team: any(u.team == team and u.state == "fight" for u in self.units)
                 for team in ("player", "enemy")}
        def how(loser):
            fled = sum(1 for u in self.units if u.team == loser and u.state in ("fled", "rout"))
            who = "Your army" if loser == "player" else "The enemy"
            return f"{who} broke and fled" if fled else f"{who} was wiped out"
        if not alive["player"]:
            self.result, self.reason = "enemy", how("player")
        elif not alive["enemy"]:
            self.result, self.reason = "player", how("enemy")
        elif self.round >= MAX_ROUNDS:
            self.result = self.defender
            self.reason = "Night fell and the attackers withdrew"
            self.log.append("Night falls. The attackers withdraw.")
        if self.result:
            self.conclude()

    def conclude(self):
        self.log.append("Victory!" if self.result == "player" else "Your army is beaten.")
        for u in self.units:
            if u.state != "dead" and not u.summoned and "static" not in u.t.tags:
                u.xp += 2 + (2 if u.team == self.result else 0)
            u.xp = min(u.xp, u.start_xp + (XP_PER_BATTLE if self.kind == "attack" else XP_PER_BATTLE // 2))
        self.promotions = [u for u in self.units if u.team == "player" and u.state != "dead"
                           and not u.summoned and u.rank > u.start_rank]

    def skip(self):
        for f in self.floaters:
            if f["action"] and f["delay"] > 0:
                f["action"]()
        self.floaters.clear()
        self.instant = True
        while not self.result:
            self.resolve_round()
        self.shots, self.strikes, self.blasts = [], {}, []
        for u in self.units:
            u.prev = u.pos
            u.disp_hp = u.hp
            u.disp_dead = u.state == "dead"
            u.hidden = u.raised
        self.anim_t = 1.0

    # ---- loop --------------------------------------------------------------
    def on_key(self, key):
        if key in (pygame.K_SPACE, pygame.K_p):
            self.paused = not self.paused
        elif key in (pygame.K_1, pygame.K_2, pygame.K_3):
            self.speed = {pygame.K_1: 1, pygame.K_2: 2, pygame.K_3: 4}[key]
        elif key == pygame.K_s and not self.result:
            self.skip()
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.finished and self.continue_cb:
            self.continue_cb()

    def on_click(self, pos):
        self.ui.click(pos)

    def update(self, dt):
        bdt = 0 if self.paused else dt * self.speed
        for f in self.floaters:
            if f["delay"] > 0:
                f["delay"] -= bdt
                if f["delay"] <= 0 and f["action"]:
                    f["action"]()
            else:
                f["age"] += bdt
        self.floaters = [f for f in self.floaters if f["age"] < 1.0]
        for u in self.units:
            u.flash = max(0.0, u.flash - bdt)
        if self.result:
            self.anim_t = min(1.0, self.anim_t + bdt / ROUND_TIME)
            if self.anim_t >= 1 and not self.floaters:
                self.finished = True
            return
        self.timer -= bdt
        if self.round:
            self.anim_t = min(1.0, 1 - self.timer / ROUND_TIME)
        if self.timer <= 0:
            self.resolve_round()
            self.timer = ROUND_TIME
            self.anim_t = 0.0

    def unit_screen_pos(self, u):
        p = min(1.0, self.anim_t / 0.45)
        e = p * p * (3 - 2 * p)
        ax, ay = tile_center(*u.prev)
        bx, by = tile_center(u.gx, u.gy)
        x, y = ax + (bx - ax) * e, ay + (by - ay) * e
        tgt = self.strikes.get(u.uid)
        if tgt and 0.45 <= self.anim_t <= 0.8:
            k = math.sin((self.anim_t - 0.45) / 0.35 * math.pi) * 10
            dx, dy = tgt[0] - bx, tgt[1] - by
            d = math.hypot(dx, dy) or 1
            x, y = x + dx / d * k, y + dy / d * k
        return x, y

    def draw_shots(self, surf):
        for start, end, style in self.shots:
            if style == "lightning":
                if 0.3 <= self.anim_t <= 0.6:
                    pts = [start]
                    for i in range(1, 6):
                        q = i / 6
                        pts.append((start[0] + (end[0] - start[0]) * q + random.uniform(-8, 8),
                                    start[1] + (end[1] - start[1]) * q + random.uniform(-8, 8)))
                    pts.append(end)
                    pygame.draw.lines(surf, C["lightning"], False, pts, 3)
                    pygame.draw.lines(surf, C["white"], False, pts, 1)
                continue
            q = (self.anim_t - 0.15) / 0.4
            if not 0 <= q <= 1:
                continue
            arc = 30 if style == "arrow" else 12
            x = start[0] + (end[0] - start[0]) * q
            y = start[1] + (end[1] - start[1]) * q - math.sin(q * math.pi) * arc
            if style == "arrow":
                dx, dy = end[0] - start[0], end[1] - start[1]
                d = math.hypot(dx, dy) or 1
                pygame.draw.line(surf, C["white"], (x - dx / d * 9, y - dy / d * 9), (x, y), 2)
            else:
                col = C[style]
                draw_glow(surf, (x, y), 10, col, 90)
                pygame.draw.circle(surf, mix(col, C["white"], 0.4), (x, y), 5)
        for pos, radius, col in self.blasts:
            q = (self.anim_t - 0.45) / 0.45
            if 0 <= q <= 1:
                draw_glow(surf, pos, radius * (0.5 + q * 0.5), col, 150 * (1 - q))

    def draw(self, surf, mouse, continue_cb):
        self.continue_cb = continue_cb
        self.ui.reset(mouse)
        surf.fill(C["bg"])
        for gx in range(COLS):
            for gy in range(ROWS):
                col = C["field"] if (gx + gy) % 2 else C["field2"]
                if gx < 2:
                    col = mix(col, C["blue"], 0.08)
                elif gx >= COLS - 2:
                    col = mix(col, C["red"], 0.08)
                pygame.draw.rect(surf, col, (FIELD_X + gx * TILE, FIELD_Y + gy * TILE, TILE, TILE))
        pygame.draw.rect(surf, C["edge"], (FIELD_X - 2, FIELD_Y - 2, COLS * TILE + 4, ROWS * TILE + 4), 2)

        for u in self.units:
            if u.disp_dead and not u.hidden:
                x, y = tile_center(u.gx, u.gy)
                base = C["blue"] if u.team == "player" else (u.t.tint or C["red"])
                col = mix(base, C["field"], 0.6)
                pygame.draw.line(surf, col, (x - 9, y - 9), (x + 9, y + 9), 4)
                pygame.draw.line(surf, col, (x - 9, y + 9), (x + 9, y - 9), 4)

        hover = None
        for u in sorted(self.units, key=lambda v: v.gy):
            if u.disp_dead or u.hidden or (u.state == "fled" and self.anim_t >= 0.45):
                continue
            pos = self.unit_screen_pos(u)
            mana = u.mana / u.t.mana if u.t.mana else None
            draw_token(surf, u.t, u.team, pos, u.disp_hp / u.max_hp, u.flash > 0,
                       u.state in ("rout", "fled"), rank=u.rank, mana_frac=mana)
            if u.slowed:
                pygame.draw.circle(surf, C["nature"], pos, 22, 2)
            if u.cursed:
                pygame.draw.circle(surf, C["dark"], (pos[0] - 16, pos[1] + 12), 4)
            if u.blessed:
                pygame.draw.circle(surf, C["holy"], (pos[0] + 16, pos[1] + 12), 4)
            if math.hypot(mouse[0] - pos[0], mouse[1] - pos[1]) < 20:
                hover = u

        self.draw_shots(surf)

        for f in self.floaters:
            if f["delay"] <= 0 and f["label"]:
                a = f["age"]
                img = FONTS["bold"].render(f["label"], True, f["color"])
                img.set_alpha(int(255 * (1 - max(0, a - 0.5) * 2)))
                surf.blit(img, img.get_rect(center=(f["x"], f["y"] - a * 26)))

        # top bar
        pygame.draw.rect(surf, C["panel"], (0, 0, W, 56))
        pygame.draw.line(surf, C["edge"], (0, 56), (W, 56), 2)
        text(surf, fit(self.title, "title", 480), (20, 13), "title")
        for team, x, col, label in (("player", 520, C["blue"], "Yours"), ("enemy", 660, C["red"], "Foes")):
            fighting = sum(1 for u in self.units if u.team == team and u.state == "fight")
            routed = sum(1 for u in self.units if u.team == team and u.state in ("rout", "fled"))
            text(surf, f"{label} {fighting}", (x, 10), "bold", col)
            text(surf, f"{routed} fleeing", (x, 30), "small", C["muted"])
        text(surf, f"Round {self.round}/{MAX_ROUNDS}", (790, 19), "bold")
        bx = 920
        for sp in (1, 2, 4):
            self.ui.button(surf, (bx, 14, 44, 28), f"{sp}x", lambda s=sp: setattr(self, "speed", s),
                           accent=self.speed == sp)
            bx += 50
        self.ui.button(surf, (bx, 14, 70, 28), "Play" if self.paused else "Pause",
                       lambda: setattr(self, "paused", not self.paused))
        self.ui.button(surf, (bx + 76, 14, 60, 28), "Skip", self.skip, enabled=not self.result)

        # log
        ly = FIELD_Y + ROWS * TILE + 6
        pygame.draw.rect(surf, C["panel"], (0, ly, W, H - ly))
        lines = self.log[-4:]
        for i, line in enumerate(lines):
            text(surf, fit(line, "small", 1000), (24, ly + 4 + i * 18), "small",
                 C["paper"] if i == len(lines) - 1 else C["muted"])
        text(surf, "SPACE/P pause · 1/2/3 speed · S skip · hover units for details", (W - 24, ly + 4), "small", C["dim"], right=True)

        if self.paused and not self.finished:
            r = text(surf, "PAUSED", (W // 2, FIELD_Y + 26), "title", C["gold"], center=True)
        if hover and not self.finished:
            self.draw_tooltip(surf, hover, mouse)
        if self.finished:
            self.draw_result(surf, continue_cb)

    def draw_tooltip(self, surf, u, mouse):
        t = u.t
        lines = [(f"{t.name}  ({'yours' if u.team == 'player' else 'enemy'})  {u.rank_name}", "bold", C["paper"]),
                 (f"HP {u.disp_hp}/{u.max_hp}   Att {u.att}  Def {u.defense}  Prot {u.prot}  Mor {u.mor}"
                  f"  Move {u.move}" + (f"  Mana {u.mana}/{t.mana}" if t.mana else ""), "small", C["paper"])]
        for i, w in enumerate(t.weapons):
            extra = f"  ×{u.ammo[i]}" if w.rng else ""
            lines.append(("• " + w.describe() + extra, "small", C["paper"]))
        if t.spells:
            lines.append(("• Spells: " + ", ".join(SPELLS[s].name for s in t.spells), "small", C["mana"]))
        status = [s for s, on in (("blessed", u.blessed), ("hexed", u.cursed), ("stunned/rooted", u.slowed),
                                  ("poisoned", u.poison), ("hasted", u.hasted), ("frenzied", u.frenzied),
                                  ("summoned", u.summoned)) if on]
        tail = {"rout": "Fleeing!", "fled": "Fled"}.get(u.state, ", ".join(status) or t.desc)
        lines.append((tail, "small", C["gold"] if status else C["muted"]))
        if u.stats["dmg"] or u.stats["kills"]:
            lines.append((f"This battle: {u.stats['kills']} kills, {u.stats['dmg']} damage", "small", C["muted"]))
        bh = 12 + len(lines) * 17
        bw = max(FONTS[f].size(s)[0] for s, f, _ in lines) + 24
        bx, by = min(mouse[0] + 16, W - bw - 6), min(mouse[1] + 16, H - bh - 6)
        pygame.draw.rect(surf, (18, 20, 22), (bx, by, bw, bh), border_radius=4)
        pygame.draw.rect(surf, C["edge"], (bx, by, bw, bh), 1, border_radius=4)
        for i, (s, f, col) in enumerate(lines):
            text(surf, s, (bx + 10, by + 6 + i * 17), f, col)

    # ---- after-battle report ----------------------------------------------
    def team_rows(self, team):
        rows = {}
        for u in self.units:
            if u.team != team:
                continue
            key = (u.t.key, u.summoned)
            r = rows.setdefault(key, {"t": u.t, "summoned": u.summoned, "start": 0, "lost": 0,
                                      "fled": 0, "kills": 0, "dmg": 0})
            r["start"] += 1
            r["lost"] += u.state == "dead"
            r["fled"] += u.state in ("fled", "rout")
            r["kills"] += u.stats["kills"]
            r["dmg"] += u.stats["dmg"]
        return sorted(rows.values(), key=lambda r: (r["summoned"], -r["dmg"]))

    def draw_table(self, surf, team, x0, y, color, label):
        text(surf, label, (x0, y), "head", color)
        cols = [("Start", 205), ("Lost", 255), ("Fled", 305), ("Kills", 355), ("Damage", 420)]
        y += 30
        for name, cx in cols:
            text(surf, name, (x0 + cx, y), "tiny", C["muted"], center=True)
        pygame.draw.line(surf, C["edge"], (x0, y + 9), (x0 + 450, y + 9))
        y += 14
        rows = self.team_rows(team)
        totals = {"start": 0, "lost": 0, "fled": 0, "kills": 0, "dmg": 0}
        for i, r in enumerate(rows):
            for k in totals:
                if not r["summoned"] or k in ("kills", "dmg"):
                    totals[k] += r[k]
            if i >= 11:
                continue
            draw_token(surf, r["t"], team, (x0 + 9, y + 9), radius=8, bar=False)
            name = r["t"].name + (" (summoned)" if r["summoned"] else "")
            text(surf, fit(name, "small", 150), (x0 + 24, y + 1), "small")
            vals = [r["start"], r["lost"], r["fled"], r["kills"], r["dmg"]]
            for (cname, cx), v in zip(cols, vals):
                col = C["red"] if cname == "Lost" and v else (C["gold"] if cname == "Fled" and v else C["paper"])
                text(surf, v, (x0 + cx, y + 9), "small", col if v else C["dim"], center=True)
            y += 20
        if len(rows) > 11:
            text(surf, f"+{len(rows) - 11} more types", (x0 + 24, y + 1), "tiny", C["muted"])
            y += 16
        pygame.draw.line(surf, C["edge"], (x0, y + 1), (x0 + 450, y + 1))
        has_summons = any(r["summoned"] for r in rows)
        text(surf, "Total*" if has_summons else "Total", (x0 + 24, y + 4), "bold")
        for (cname, cx), k in zip(cols, ["start", "lost", "fled", "kills", "dmg"]):
            text(surf, totals[k], (x0 + cx, y + 12), "bold", center=True)
        if has_summons:
            text(surf, "* summoned units count toward kills and damage only", (x0 + 24, y + 24), "tiny", C["muted"])
            return y + 38
        return y + 26

    def best_unit(self, team):
        pool = [u for u in self.units if u.team == team and (u.stats["dmg"] or u.stats["kills"] or u.stats["healed"])]
        if not pool:
            return "—"
        u = max(pool, key=lambda v: v.stats["kills"] * 10 + v.stats["dmg"] + v.stats["healed"])
        s = f"{u.t.name} ({u.rank_name}): {u.stats['kills']} kills, {u.stats['dmg']} dmg"
        if u.stats["healed"]:
            s += f", {u.stats['healed']} healed"
        return s + (" — fell" if u.state == "dead" else "")

    def top_attacks(self, team):
        items = sorted(((v, k[1]) for k, v in self.weapon_dmg.items() if k[0] == team and v), reverse=True)
        return ", ".join(f"{name} {v}" for v, name in items[:3]) or "—"

    def spells_text(self, team):
        items = sorted(((v, k[1]) for k, v in self.spell_counts.items() if k[0] == team), reverse=True)
        return ", ".join(f"{name} ×{v}" for v, name in items[:4]) or "none"

    def draw_result(self, surf, continue_cb):
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((8, 9, 10, 190))
        surf.blit(shade, (0, 0))
        won = self.result == "player"
        card = pygame.Rect(140, 22, 1000, 716)
        pygame.draw.rect(surf, C["panel"], card, border_radius=8)
        pygame.draw.rect(surf, C["gold"] if won else C["red"], card, 2, border_radius=8)
        text(surf, "VICTORY" if won else "DEFEAT", (W // 2, 62), "big", C["gold"] if won else C["red"], center=True)
        text(surf, f"{self.title}  ·  {self.reason} after {self.round} rounds.", (W // 2, 108), "body",
             C["muted"], center=True)

        left, right = card.x + 30, card.centerx + 20
        y1 = self.draw_table(surf, "player", left, 128, C["blue"], "Your army")
        y2 = self.draw_table(surf, "enemy", right, 128, C["red"], "The enemy")
        y = max(y1, y2) + 6
        pygame.draw.line(surf, C["edge"], (card.x + 20, y), (card.right - 20, y))
        y += 10

        heal = sum(u.stats["healed"] for u in self.units if u.team == "player")
        eheal = sum(u.stats["healed"] for u in self.units if u.team == "enemy")
        rows = [
            (("Hero of the day", self.best_unit("player")), ("Deadliest foe", self.best_unit("enemy"))),
            (("Your best attacks", self.top_attacks("player")), ("Their best attacks", self.top_attacks("enemy"))),
            (("Your spells", self.spells_text("player")), ("Their spells", self.spells_text("enemy"))),
            (("Healing / poison", f"{heal} healed, {self.poison_dmg['enemy']} poison dealt"),
             ("Healing / poison", f"{eheal} healed, {self.poison_dmg['player']} poison dealt")),
            (("Friendly fire", f"{self.friendly['player']} damage to your own"),
             ("Friendly fire", f"{self.friendly['enemy']} damage to their own")),
        ]
        for (l1, v1), (l2, v2) in rows:
            for x, lab, val in ((left, l1, v1), (right, l2, v2)):
                text(surf, lab, (x, y), "bold", C["gold"])
                text(surf, fit(val, "small", 300), (x + 148, y + 2), "small")
            y += 22
        y += 6
        pygame.draw.line(surf, C["edge"], (card.x + 20, y), (card.right - 20, y))
        y += 10

        survivors = [u for u in self.units if u.team == "player" and u.state != "dead"
                     and not u.summoned and "static" not in u.t.tags]
        xp = sum(u.xp - u.start_xp for u in survivors)
        text(surf, f"Experience: your {len(survivors)} survivors earned {xp} XP.", (left, y), "bold")
        y += 22
        if self.promotions:
            names = [f"{u.t.name} → {u.rank_name}" for u in self.promotions]
            shown = "Promotions: " + ", ".join(names[:8]) + (f" and {len(names) - 8} more" if len(names) > 8 else "")
            for line in wrap(shown, "small", card.w - 60)[:2]:
                text(surf, line, (left, y), "small", C["gold"])
                y += 18
        else:
            text(surf, "No promotions this time.", (left, y), "small", C["muted"])
            y += 18
        y += 6
        outcome = self.spoils[0] if won else self.spoils[1]
        if outcome:
            for line in wrap(outcome, "bold", card.w - 60)[:2]:
                text(surf, line, (left, y), "bold", C["gold"] if won else C["red"])
                y += 20
        self.ui.button(surf, (W // 2 - 100, card.bottom - 52, 200, 38), "Continue (Enter)", continue_cb, accent=True)


# --------------------------------------------------------------------------
# Town (real time), war map and game state
# --------------------------------------------------------------------------
class Plot:
    def __init__(self, idx, rect):
        self.idx, self.rect = idx, pygame.Rect(rect)
        self.key = None
        self.level = 0
        self.building = None      # {"target", "remaining", "total"}
        self.queue = []           # [unit_key, remaining, total]


TOWN_RECT = pygame.Rect(20, 72, 780, 474)
MAP_RECT = pygame.Rect(20, 72, 820, 678)
HOME_POS = (60, 340)
HALL_PLOT = 5


class Game:
    def __init__(self):
        self.gold, self.iron = 160.0, 20.0
        self.plots = []
        for i in range(12):
            r, c = divmod(i, 4)
            self.plots.append(Plot(i, (TOWN_RECT.x + 8 + c * 193, TOWN_RECT.y + 8 + r * 154, 185, 146)))
        self.plots[HALL_PLOT].key, self.plots[HALL_PLOT].level = "hall", 1
        self.captain = Soldier("captain", "player")
        self.army = [self.captain] + [Soldier("militia", "player") for _ in range(3)]
        self.captain_down = 0.0
        self.integrity = 3
        self.time = 0.0
        self.raid_timer, self.raid_count, self.raid_warned = 180.0, 0, False
        self.growth_timer = 45.0
        self.growth_ticks = 0
        self.drill_timer = 0.0
        self.targets = make_targets()
        self.bonus_income = self.bonus_iron = 0.0
        self.relic = 0
        self.scene, self.return_scene, self.battle = "town", "town", None
        self.selected, self.map_sel = HALL_PLOT, 0
        self.toasts = []
        self.over = None
        self.paused = False
        self.ui = UI()
        self.peons = [{"x": 400.0, "y": 300.0, "tx": 400.0, "ty": 300.0} for _ in range(6)]
        self.decor = self.make_decor()

    # ---- economy ---------------------------------------------------------
    def level(self, key):
        return max((p.level for p in self.plots if p.key == key), default=0)

    def gold_rate(self):
        return 1.5 + 0.5 * (self.level("hall") - 1) + 1.2 * self.level("market") + self.bonus_income

    def iron_rate(self):
        return 0.3 + 0.7 * self.level("mine") + self.bonus_iron

    def army_cap(self):
        return 6 + 2 * self.level("hall") + 4 * self.level("longhouse")

    def troops(self):
        return [s for s in self.army if s is not self.captain]

    def queued(self):
        return sum(len(p.queue) for p in self.plots)

    def builders_busy(self):
        return any(p.building for p in self.plots)

    def toast(self, msg, color=None):
        self.toasts.append([msg, 4.5, color or C["paper"]])

    def target_named(self, name):
        return next(t for t in self.targets if t.name == name)

    def req_met(self, req):
        if req[0] == "building":
            return self.level(req[1]) >= req[2]
        return self.target_named(req[1]).conquered

    @staticmethod
    def req_text(req):
        if req[0] == "building":
            return f"Needs {BUILDINGS[req[1]].name} Lv{req[2]}"
        return f"Conquer {req[1]}"

    def bonuses(self):
        forge = self.level("forge")
        return {"player": {"prot": (forge + 1) // 2, "dmg": 1 if forge >= 2 else 0, "power": self.relic}}

    def can_build(self, plot, key):
        b = BUILDINGS[key]
        target = plot.level + 1
        if plot.key is None and any(p.key == key for p in self.plots):
            return False, "Already built"
        if target > b.max_level:
            return False, "Max level"
        for req in building_reqs(key, target):
            if not self.req_met(req):
                return False, self.req_text(req)
        if self.builders_busy():
            return False, "Builders busy"
        g, i = building_cost(key, target)
        if self.gold < g or self.iron < i:
            return False, "Can't afford"
        return True, ""

    def build(self, plot, key):
        if not self.can_build(plot, key)[0]:
            return
        target = plot.level + 1
        g, i = building_cost(key, target)
        self.gold -= g
        self.iron -= i
        plot.key = key
        t = building_time(key, target)
        plot.building = {"target": target, "remaining": t, "total": t}

    def can_recruit(self, plot, ukey):
        t = UNITS[ukey]
        if plot.level < t.req_level:
            return False, f"Needs Lv{t.req_level}"
        if len(self.troops()) + self.queued() >= self.army_cap():
            return False, "Army full"
        if len(plot.queue) >= 5:
            return False, "Queue full"
        if self.gold < t.gold or self.iron < t.iron:
            return False, "Can't afford"
        return True, ""

    def recruit(self, plot, ukey):
        if not self.can_recruit(plot, ukey)[0]:
            return
        t = UNITS[ukey]
        self.gold -= t.gold
        self.iron -= t.iron
        plot.queue.append([ukey, t.train, t.train])

    def available(self):
        units = self.troops()
        if self.captain_down <= 0:
            units = [self.captain] + units
        return units

    # ---- war -------------------------------------------------------------
    def open_targets(self):
        return [t for t in self.targets
                if not t.conquered and all(self.targets[i].conquered for i in t.prereq)]

    def attack(self, target):
        if self.captain_down > 0 or target not in self.open_targets():
            return
        self.return_scene = self.scene
        bonuses = dict(self.bonuses(), **target.bonuses())
        win = ("Ironveil falls. You have won the war!" if target.final
               else f"{target.name} is yours. Spoils: " + ", ".join(target.reward_lines()).rstrip(".") + ".")
        lose = f"The survivors of {target.name} will heal and hold the walls against your next attempt."
        self.battle = Battle("attack", f"Assault on {target.name}", self.available(), target.garrison,
                             attacker="player", target=target, bonuses=bonuses, spoils=(win, lose))
        self.scene = "battle"

    def next_raid(self):
        n = self.raid_count + 1
        undead = n >= 4 and n % 3 == 0 and not self.target_named("Barrow of Whispers").conquered
        cap = 6 + 2 * sum(t.conquered for t in self.targets)
        return raid_force(n, undead, cap), undead

    def start_raid(self):
        comp, undead = self.next_raid()
        self.raid_count += 1
        enemies = [Soldier(k, "enemy") for k, n in comp for _ in range(n)]
        towers = [Soldier("tower", "player") for _ in range(self.level("tower"))]
        defenders = self.available()
        if not defenders and not towers:
            self.lose_raid()
            self.raid_timer = max(80.0, 140.0 - 4 * self.raid_count)
            return
        self.return_scene = self.scene
        who = "The dead rise against" if undead else f"Raid #{self.raid_count} on"
        loot = 25 + 10 * min(self.raid_count, 16)
        lost_gold = int(self.gold * 0.3)
        fall = " This will be the end of your town!" if self.integrity <= 1 else ""
        spoils = (f"The raid is broken. You loot {loot} gold from the fallen.",
                  f"The raiders will sack the town: -1 town strength and {lost_gold} gold stolen.{fall}")
        self.battle = Battle("defense", f"{who} your town", defenders + towers, enemies,
                             attacker="enemy", bonuses=self.bonuses(), spoils=spoils)
        self.scene = "battle"

    def lose_raid(self):
        self.integrity -= 1
        stolen = int(self.gold * 0.3)
        self.gold -= stolen
        self.toast(f"Raiders sacked the town and stole {stolen} gold!", C["red"])
        if self.integrity <= 0:
            self.over = "defeat"

    def finish_battle(self):
        b = self.battle
        won = b.result == "player"
        for s in list(self.army):
            if s.state == "dead":
                if s is self.captain:
                    self.captain_down = 45.0
                    self.toast("Your Captain was carried from the field, badly hurt.", C["red"])
                else:
                    self.army.remove(s)
        if b.kind == "attack":
            t = b.target
            if won:
                t.conquered = True
                self.gold += t.gold
                self.bonus_income += t.income
                self.bonus_iron += t.iron_income
                self.relic += 1 if t.relic else 0
                if t.final:
                    self.over = "victory"
                else:
                    self.toast(f"{t.name} taken! " + ", ".join(t.reward_lines()[:3]), C["gold"])
                    nxt = self.open_targets()
                    if nxt:
                        self.map_sel = self.targets.index(nxt[0])
            else:
                t.garrison = [u for u in t.garrison if u.state != "dead"]
                for u in t.garrison:
                    u.hp = u.max_hp
                self.toast(f"The assault on {t.name} failed.", C["red"])
        else:
            if won:
                loot = 25 + 10 * min(self.raid_count, 16)
                self.gold += loot
                self.toast(f"Raid repelled! Looted {loot} gold from the fallen.", C["gold"])
            else:
                self.lose_raid()
            self.raid_timer = max(80.0, 140.0 - 4 * self.raid_count)
            self.raid_warned = False
        if b.promotions:
            n = len(b.promotions)
            self.toast(f"{n} soldier{'s' if n > 1 else ''} earned a promotion!", C["gold"])
        self.battle = None
        self.scene = self.return_scene

    # ---- update ----------------------------------------------------------
    def update(self, dt):
        if self.over:
            return
        if self.scene == "battle":
            self.battle.update(dt)
            return
        if self.paused:
            return
        self.time += dt
        self.gold = min(9999, self.gold + self.gold_rate() * dt)
        self.iron = min(9999, self.iron + self.iron_rate() * dt)

        for p in self.plots:
            if p.building:
                p.building["remaining"] -= dt
                if p.building["remaining"] <= 0:
                    p.level = p.building["target"]
                    p.building = None
                    self.toast(f"{BUILDINGS[p.key].name} Lv{p.level} complete.")
            if p.queue and p.level > 0 and len(self.troops()) < self.army_cap():
                p.queue[0][1] -= dt
                if p.queue[0][1] <= 0:
                    ukey = p.queue.pop(0)[0]
                    self.army.append(Soldier(ukey, "player"))
                    self.toast(f"{UNITS[ukey].name} joins the warband.")

        rate = 0.3 + 0.35 * self.level("longhouse") + 0.4 * self.level("temple")
        for s in self.army:
            if s.hp < s.max_hp and not (s is self.captain and self.captain_down > 0):
                s.heal_acc += rate * dt
                while s.heal_acc >= 1 and s.hp < s.max_hp:
                    s.heal_acc -= 1
                    s.hp += 1
        if self.captain_down > 0:
            self.captain_down -= dt
            if self.captain_down <= 0:
                self.captain.hp = self.captain.max_hp
                self.toast("Your Captain is back on their feet.", C["gold"])

        if self.level("barracks") >= 2:
            self.drill_timer += dt
            if self.drill_timer >= 15:
                self.drill_timer -= 15
                for s in self.troops():
                    if s.xp < RANKS[1][0]:
                        s.xp += 1

        self.growth_timer -= dt
        if self.growth_timer <= 0:
            self.growth_timer = 45.0
            self.growth_ticks += 1
            opened = self.open_targets()
            for t in self.targets:
                if t.conquered or (t not in opened and self.growth_ticks % 2):
                    continue
                if len(t.garrison) < t.cap:
                    t.garrison.append(t.new_recruit())
                random.choice(t.garrison).xp += 3

        self.raid_timer -= dt
        if self.raid_timer <= 30 and not self.raid_warned:
            self.raid_warned = True
            _, undead = self.next_raid()
            self.toast("The dead are stirring toward your town!" if undead
                       else "Scouts report an Ironveil raid approaching!", C["red"])
        if self.raid_timer <= 0:
            self.start_raid()

        for t in self.toasts:
            t[1] -= dt
        self.toasts = [t for t in self.toasts if t[1] > 0]

        for pe in self.peons:
            dx, dy = pe["tx"] - pe["x"], pe["ty"] - pe["y"]
            d = math.hypot(dx, dy)
            if d < 3:
                sites = [p for p in self.plots if p.building] * 3 + [p for p in self.plots if p.key]
                p = random.choice(sites)
                pe["tx"] = p.rect.centerx + random.uniform(-50, 50)
                pe["ty"] = p.rect.bottom - random.uniform(8, 24)
            else:
                pe["x"] += dx / d * 45 * dt
                pe["y"] += dy / d * 45 * dt

    # ---- input -----------------------------------------------------------
    def node_pos(self, pos):
        return (MAP_RECT.x + pos[0], MAP_RECT.y + pos[1])

    def on_click(self, pos):
        if self.scene == "battle":
            self.battle.on_click(pos)
            return
        if self.ui.click(pos):
            return
        if self.scene == "town":
            for p in self.plots:
                if p.rect.collidepoint(pos):
                    self.selected = p.idx
        else:
            for i, t in enumerate(self.targets):
                x, y = self.node_pos(t.pos)
                if math.hypot(pos[0] - x, pos[1] - y) < 28:
                    self.map_sel = i

    def on_key(self, key):
        if self.scene == "battle":
            self.battle.on_key(key)
        elif key in (pygame.K_p, pygame.K_SPACE):
            self.paused = not self.paused
        elif key == pygame.K_m:
            self.scene = "map" if self.scene == "town" else "town"
        elif key == pygame.K_ESCAPE and self.scene == "map":
            self.scene = "town"

    # ---- drawing: shared -------------------------------------------------
    def draw(self, surf, mouse):
        if self.scene == "battle":
            self.battle.draw(surf, mouse, self.finish_battle)
        else:
            self.ui.reset(mouse)
            surf.fill(C["bg"])
            self.draw_topbar(surf)
            if self.scene == "town":
                self.draw_town(surf)
                self.draw_side(surf)
                self.draw_army(surf)
                self.draw_campaign(surf)
                cx = TOWN_RECT.centerx
            else:
                self.draw_map(surf)
                self.draw_map_panel(surf)
                cx = MAP_RECT.centerx
            if self.paused:
                banner = "PAUSED — you can still build, train and plan. Press P to resume."
                img = FONTS["bold"].render(banner, True, C["ink"])
                r = img.get_rect(center=(cx, 530 if self.scene == "town" else 735))
                pygame.draw.rect(surf, C["gold"], r.inflate(24, 10), border_radius=5)
                surf.blit(img, r)
            for i, (msg, life, col) in enumerate(self.toasts[-4:]):
                img = FONTS["bold"].render(msg, True, col)
                img.set_alpha(int(255 * min(1, life)))
                r = img.get_rect(center=(cx, 92 + i * 24))
                pygame.draw.rect(surf, (16, 18, 20), r.inflate(20, 6), border_radius=4)
                surf.blit(img, r)
        if self.over:
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((8, 9, 10, 200))
            surf.blit(shade, (0, 0))
            won = self.over == "victory"
            text(surf, "IRONVEIL HAS FALLEN" if won else "YOUR TOWN IS LOST", (W // 2, 300), "big",
                 C["gold"] if won else C["red"], center=True)
            best = max(self.army, key=lambda s: s.xp)
            text(surf, f"Time: {int(self.time // 60)}m {int(self.time % 60)}s    "
                       f"Finest soldier: {best.t.name} ({best.rank_name}, {best.xp} xp)",
                 (W // 2, 370), "body", center=True)
            text(surf, "Press R to play again", (W // 2, 400), "body", C["muted"], center=True)

    def draw_topbar(self, surf):
        pygame.draw.rect(surf, C["panel"], (0, 0, W, 60))
        pygame.draw.line(surf, C["edge"], (0, 60), (W, 60), 2)
        text(surf, "WAR ON THE RIM", (20, 15), "title")
        x = 290
        pygame.draw.circle(surf, C["gold"], (x, 30), 8)
        text(surf, f"{int(self.gold)}", (x + 14, 14), "head", C["gold"])
        text(surf, f"+{self.gold_rate():.1f}/s", (x + 14, 38), "small", C["muted"])
        x = 410
        pygame.draw.rect(surf, C["iron"], (x - 8, 23, 16, 14), border_radius=2)
        text(surf, f"{int(self.iron)}", (x + 14, 14), "head", C["iron"])
        text(surf, f"+{self.iron_rate():.1f}/s", (x + 14, 38), "small", C["muted"])
        text(surf, f"Warband {len(self.troops())}/{self.army_cap()}", (530, 12), "bold", C["blue"])
        taken = sum(t.conquered for t in self.targets)
        text(surf, f"Conquests {taken}/{len(self.targets)}", (530, 34), "small", C["muted"])
        text(surf, "Town", (700, 20), "bold")
        for i in range(3):
            col = C["green"] if i < self.integrity else (60, 60, 60)
            x = 748 + i * 22
            pygame.draw.polygon(surf, col, [(x, 20), (x + 15, 20), (x + 15, 30), (x + 7, 40), (x, 30)])
        comp, undead = self.next_raid()
        col = C["red"] if self.raid_timer < 30 else C["paper"]
        text(surf, f"Next {'undead ' if undead else ''}raid in {int(self.raid_timer)}s", (840, 12), "head", col)
        text(surf, fit(comp_text(comp), "small", 320), (840, 38), "small", C["muted"])
        self.ui.button(surf, (1170, 12, 94, 36), "Resume" if self.paused else "Pause (P)",
                       lambda: setattr(self, "paused", not self.paused), accent=self.paused)

    # ---- drawing: town ---------------------------------------------------
    def draw_town(self, surf):
        pygame.draw.rect(surf, C["grass"], TOWN_RECT, border_radius=6)
        for i in range(0, TOWN_RECT.w, 34):
            for j in range(0, TOWN_RECT.h, 34):
                if (i * 7 + j * 3) % 5 == 0:
                    pygame.draw.circle(surf, C["grass2"], (TOWN_RECT.x + i + 10, TOWN_RECT.y + j + 12), 3)
        hall = self.plots[HALL_PLOT].rect.center
        for p in self.plots:
            if p.idx != HALL_PLOT:
                pygame.draw.line(surf, C["road"], hall, p.rect.center, 9)
        for p in self.plots:
            self.draw_plot(surf, p)
        for pe in self.peons:
            pygame.draw.circle(surf, (40, 34, 28), (pe["x"], pe["y"] + 1), 4)
            pygame.draw.circle(surf, (190, 160, 120), (pe["x"], pe["y"] - 5), 3)
        pygame.draw.rect(surf, C["edge"], TOWN_RECT, 2, border_radius=6)

    def draw_plot(self, surf, p):
        r = p.rect
        sel = p.idx == self.selected
        hover = r.collidepoint(self.ui.mouse)
        pygame.draw.rect(surf, C["dirt"] if p.key else mix(C["grass"], C["dirt"], 0.35),
                         r.inflate(-12, -12), border_radius=8)
        if p.key and (p.level or p.building):
            b = BUILDINGS[p.key]
            lvl = max(p.level, 1)
            cx, base = r.centerx, r.bottom - 36
            w, h = 70 + 12 * lvl, 32 + 6 * lvl
            wall = mix(b.color, C["ink"], 0.25)
            if p.level == 0:
                wall = mix(wall, C["dirt"], 0.6)
            pygame.draw.rect(surf, wall, (cx - w / 2, base - h, w, h))
            roof = mix(b.color, C["ink"], 0.55) if p.level else mix(b.color, C["dirt"], 0.7)
            if p.key == "arcanum":
                pygame.draw.rect(surf, wall, (cx - 14, base - h - 40, 28, 40))
                pygame.draw.polygon(surf, roof, [(cx - 20, base - h - 40), (cx, base - h - 70), (cx + 20, base - h - 40)])
            else:
                pygame.draw.polygon(surf, roof, [(cx - w / 2 - 7, base - h), (cx, base - h - 30),
                                                 (cx + w / 2 + 7, base - h)])
            pygame.draw.rect(surf, C["ink"], (cx - 7, base - 18, 14, 18))
            if p.key in ("hall", "tower"):
                for side in (-1, 1):
                    pygame.draw.rect(surf, wall, (cx + side * w / 2 - 9, base - h - 20, 18, h + 20))
            if b.glyph:
                gy = base - h - (52 if p.key == "arcanum" else 11)
                pygame.draw.circle(surf, mix(b.color, C["paper"], 0.3), (cx, gy), 12)
                draw_glyph(surf, b.glyph, (cx, gy), 13, C["ink"])
            if p.building:
                for k in range(4):
                    x = cx - w / 2 - 6 + k * (w + 12) / 3
                    pygame.draw.line(surf, (160, 130, 90), (x, base), (x, base - h - 10), 2)
                pygame.draw.line(surf, (160, 130, 90), (cx - w / 2 - 6, base - h / 2),
                                 (cx + w / 2 + 6, base - h / 2), 2)
            text(surf, fit(b.name, "bold", 120), (r.x + 10, r.bottom - 32), "bold")
            text(surf, f"Lv {p.level}/{b.max_level}", (r.right - 10, r.bottom - 30), "small",
                 C["muted"], right=True)
            bar = None
            if p.building:
                bar = (1 - p.building["remaining"] / p.building["total"], C["gold"])
            elif p.queue:
                q = p.queue[0]
                bar = (1 - q[1] / q[2], C["blue"])
                text(surf, fit(f"Training {UNITS[q[0]].name}" + (f" +{len(p.queue) - 1}" if len(p.queue) > 1 else ""),
                               "small", 165), (r.x + 10, r.y + 9), "small")
            if bar:
                pygame.draw.rect(surf, (30, 30, 30), (r.x + 10, r.bottom - 13, r.w - 20, 5))
                pygame.draw.rect(surf, bar[1], (r.x + 10, r.bottom - 13, (r.w - 20) * bar[0], 5))
        else:
            text(surf, "+ Empty plot", r.center, "bold", C["muted"], center=True)
        edge = C["gold"] if sel else ((140, 140, 120) if hover else None)
        if edge:
            pygame.draw.rect(surf, edge, r.inflate(-6, -6), 2, border_radius=8)

    def draw_side(self, surf):
        box = pygame.Rect(812, 72, 448, 474)
        pygame.draw.rect(surf, C["panel"], box, border_radius=6)
        pygame.draw.rect(surf, C["edge"], box, 1, border_radius=6)
        p = self.plots[self.selected]
        x, y = box.x + 16, box.y + 12
        if p.key is None:
            text(surf, "Empty plot — choose a building", (x, y), "head")
            y += 34
            options = [k for k in BUILDINGS if not any(q.key == k for q in self.plots)]
            if not options:
                text(surf, "Every building is already in your town.", (x, y), "body", C["muted"])
            for key in options:
                b = BUILDINGS[key]
                ok, why = self.can_build(p, key)
                g, i = building_cost(key, 1)
                text(surf, b.name, (x, y), "bold")
                text(surf, f"{g}g" + (f"  {i}i" if i else ""), (x + 130, y + 1), "small", C["gold"])
                sub = b.desc if not why or why == "Can't afford" else why
                text(surf, fit(sub, "small", 330), (x, y + 17), "small",
                     C["muted"] if sub == b.desc else C["red"])
                self.ui.button(surf, (box.right - 80, y + 4, 64, 26), "Build",
                               lambda k=key: self.build(p, k), enabled=ok)
                y += 38
            return
        b = BUILDINGS[p.key]
        text(surf, b.name, (x, y), "title")
        text(surf, f"Level {p.level}/{b.max_level}", (box.right - 16, y + 8), "bold", C["muted"], right=True)
        y += 38
        for line in wrap(b.desc, "body", box.w - 32):
            text(surf, line, (x, y), "body", C["muted"])
            y += 19
        y += 6
        if p.building:
            pr = 1 - p.building["remaining"] / p.building["total"]
            text(surf, f"Building Lv{p.building['target']}... {int(p.building['remaining'])}s",
                 (x, y), "bold", C["gold"])
            pygame.draw.rect(surf, (30, 30, 30), (x, y + 24, box.w - 32, 6))
            pygame.draw.rect(surf, C["gold"], (x, y + 24, (box.w - 32) * pr, 6))
            y += 42
        elif p.level < b.max_level:
            ok, why = self.can_build(p, p.key)
            g, i = building_cost(p.key, p.level + 1)
            label = f"Upgrade to Lv{p.level + 1}   {g}g" + (f" {i}i" if i else "")
            self.ui.button(surf, (x, y, 250, 32), label, lambda: self.build(p, p.key), enabled=ok, accent=ok)
            if why:
                text(surf, fit(why, "small", 160), (x + 260, y + 8), "small", C["red"])
            y += 44
        else:
            text(surf, "Fully upgraded", (x, y), "bold", C["green"])
            y += 30

        units = [u for u in RECRUITABLE if u.building == p.key]
        if units:
            pygame.draw.line(surf, C["edge"], (x, y), (box.right - 16, y))
            y += 6
            text(surf, "Train", (x, y), "head")
            y += 28
            for t in units:
                ok, why = self.can_recruit(p, t.key)
                locked = p.level < t.req_level
                draw_token(surf, t, "player", (x + 16, y + 26), radius=15, bar=False)
                text(surf, t.name, (x + 42, y), "bold", C["dim"] if locked else C["paper"])
                cost = f"{t.gold}g" + (f" {t.iron}i" if t.iron else "") + f"  {int(t.train)}s"
                text(surf, cost, (x + 175, y + 1), "small", C["gold"])
                stats = f"HP {t.hp}  Att {t.att}  Def {t.defense}  Prot {t.prot}  Mor {t.mor}"
                if t.move > 1:
                    stats += f"  Move {t.move}"
                if t.mana:
                    stats += f"  Mana {t.mana}"
                text(surf, fit(stats, "small", 318), (x + 42, y + 17), "small", C["muted"])
                text(surf, fit(t.attack_line(), "small", 318), (x + 42, y + 33), "small",
                     C["dim"] if locked else (215, 200, 160))
                text(surf, fit(why or t.desc, "small", 318), (x + 42, y + 49), "small",
                     C["red"] if why else C["dim"])
                self.ui.button(surf, (box.right - 80, y + 14, 64, 28), "Train",
                               lambda k=t.key: self.recruit(p, k), enabled=ok)
                y += 70
            if p.queue:
                text(surf, "Queue:", (x, y + 2), "small", C["muted"])
                for i, q in enumerate(p.queue):
                    draw_token(surf, UNITS[q[0]], "player", (x + 70 + i * 32, y + 12), radius=11,
                               hp_frac=1 - q[1] / q[2])

    def draw_army(self, surf):
        box = pygame.Rect(20, 556, 780, 194)
        pygame.draw.rect(surf, C["panel"], box, border_radius=6)
        pygame.draw.rect(surf, C["edge"], box, 1, border_radius=6)
        text(surf, f"Warband  {len(self.troops())}/{self.army_cap()}", (box.x + 16, box.y + 10), "head")
        lx = box.right - 16
        for i in range(len(RANKS) - 1, -1, -1):
            lbl = RANKS[i][1]
            r = text(surf, lbl, (lx, box.y + 15), "tiny", C["muted"], right=True)
            pygame.draw.circle(surf, RANK_COLORS[i], (r.x - 7, r.centery), 4)
            lx = r.x - 18
        groups = {}
        for s in self.troops():
            groups.setdefault(s.t.key, []).append(s)
        order = [u.key for u in RECRUITABLE]
        chips = [("captain", [self.captain])] + sorted(groups.items(), key=lambda kv: order.index(kv[0]))
        for i, (key, members) in enumerate(chips[:16]):
            cx = box.x + 14 + (i % 4) * 190
            cy = box.y + 42 + (i // 4) * 37
            t = UNITS[key]
            hp = sum(m.hp for m in members) / sum(m.max_hp for m in members)
            down = key == "captain" and self.captain_down > 0
            draw_token(surf, t, "player", (cx + 13, cy + 15), 0 if down else hp, routed=down, radius=12)
            if key == "captain":
                label = f"Hurt — back in {int(self.captain_down)}s" if down else f"Captain · {self.captain.rank_name}"
                text(surf, fit(label, "bold", 150), (cx + 32, cy + 2), "bold", C["red"] if down else C["paper"])
            else:
                text(surf, fit(f"{len(members)} × {t.name}", "bold", 150), (cx + 32, cy + 2), "bold")
            for j, m in enumerate(sorted(members, key=lambda s: -s.xp)[:20]):
                pygame.draw.circle(surf, RANK_COLORS[m.rank], (cx + 36 + j * 7, cy + 27), 3)
        if len(chips) > 16:
            text(surf, f"+{len(chips) - 16} more", (box.right - 16, box.bottom - 20), "small",
                 C["muted"], right=True)

    def draw_campaign(self, surf):
        box = pygame.Rect(812, 556, 448, 194)
        pygame.draw.rect(surf, C["panel"], box, border_radius=6)
        pygame.draw.rect(surf, C["edge"], box, 1, border_radius=6)
        taken = sum(t.conquered for t in self.targets)
        text(surf, "Campaign", (box.x + 16, box.y + 10), "head")
        text(surf, f"{taken}/{len(self.targets)} taken", (box.right - 16, box.y + 15), "small",
             C["muted"], right=True)
        y = box.y + 42
        down = self.captain_down > 0
        for t in self.open_targets()[:2]:
            text(surf, t.name, (box.x + 16, y), "bold", C["purple"] if t.faction == "Barrow" else C["paper"])
            text(surf, fit(f"{len(t.garrison)} troops: {t.summary()}", "small", 320),
                 (box.x + 16, y + 19), "small", C["muted"])
            self.ui.button(surf, (box.right - 96, y + 4, 80, 30), "March",
                           lambda tt=t: self.attack(tt), enabled=not down, accent=not down)
            y += 46
        hint = "Your Captain must lead the march." if down else "Garrisons grow and train over time."
        text(surf, hint, (box.x + 16, box.bottom - 30), "small", C["dim"])
        self.ui.button(surf, (box.right - 136, box.bottom - 40, 120, 30), "War Map (M)",
                       lambda: setattr(self, "scene", "map"))

    # ---- drawing: war map ------------------------------------------------
    def make_decor(self):
        rng = random.Random(11)
        nodes = [HOME_POS] + [t.pos for t in self.targets]
        decor = []
        while len(decor) < 70:
            x, y = rng.uniform(20, MAP_RECT.w - 20), rng.uniform(20, MAP_RECT.h - 20)
            if any(abs(x - nx) < 95 and -45 < y - ny < 85 for nx, ny in nodes):
                continue
            kind = "mount" if y < 90 or y > 600 or rng.random() < 0.25 else rng.choice(["forest", "forest", "hill"])
            decor.append((kind, x, y, rng.uniform(0.7, 1.3)))
        return sorted(decor, key=lambda d: d[2])

    def draw_map(self, surf):
        pygame.draw.rect(surf, (60, 64, 48), MAP_RECT, border_radius=6)
        ox, oy = MAP_RECT.topleft
        river = [(420, 0), (400, 120), (430, 260), (395, 400), (420, 540), (400, 678)]
        pygame.draw.lines(surf, (62, 92, 110), False, [(ox + x, oy + y) for x, y in river], 12)
        pygame.draw.lines(surf, (78, 112, 130), False, [(ox + x, oy + y) for x, y in river], 5)
        barrow = self.node_pos(self.targets[3].pos)
        draw_glow(surf, barrow, 90, (60, 40, 80), 110)
        for kind, x, y, s in self.decor:
            x, y = ox + x, oy + y
            if kind == "mount":
                pygame.draw.polygon(surf, (88, 86, 80), [(x - 22 * s, y + 12 * s), (x, y - 20 * s), (x + 22 * s, y + 12 * s)])
                pygame.draw.polygon(surf, (200, 200, 190), [(x - 6 * s, y - 9 * s), (x, y - 20 * s), (x + 6 * s, y - 9 * s)])
            elif kind == "forest":
                for dx, dy in ((-8, 2), (6, 0), (-1, -7)):
                    pygame.draw.circle(surf, (38, 62, 40), (x + dx * s, y + dy * s), 8 * s)
            else:
                pygame.draw.ellipse(surf, (72, 76, 56), (x - 18 * s, y - 7 * s, 36 * s, 14 * s))

        def dashed(a, b, col, width, dash):
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            n = max(1, int(d / dash))
            for i in range(0, n, 2):
                p = (a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n)
                q = (a[0] + (b[0] - a[0]) * min(n, i + 1) / n, a[1] + (b[1] - a[1]) * min(n, i + 1) / n)
                pygame.draw.line(surf, col, p, q, width)

        home = self.node_pos(HOME_POS)
        opened = self.open_targets()
        for t in self.targets:
            sources = [home] if not t.prereq else [self.node_pos(self.targets[i].pos) for i in t.prereq]
            for src in sources:
                if t.conquered:
                    pygame.draw.line(surf, C["road"], src, self.node_pos(t.pos), 6)
                elif t in opened:
                    dashed(src, self.node_pos(t.pos), C["gold"], 4, 10)
                else:
                    dashed(src, self.node_pos(t.pos), (90, 88, 76), 3, 10)

        pygame.draw.circle(surf, C["ink"], home, 28)
        pygame.draw.circle(surf, C["blue"], home, 25)
        draw_glyph(surf, "banner", home, 26, C["paper"])
        text(surf, "Your Town", (home[0], home[1] + 38), "bold", center=True)

        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 250)
        for i, t in enumerate(self.targets):
            pos = self.node_pos(t.pos)
            if i == self.map_sel:
                pygame.draw.circle(surf, C["white"], pos, 33, 2)
            if t.conquered:
                fill, glyph = C["blue"], "banner"
            else:
                fill = C["undead"] if t.faction == "Barrow" else C["red"]
                glyph = "crown" if t.final else ("skull" if t.faction == "Barrow" else "helm")
                if t not in opened:
                    fill = mix(fill, (70, 70, 70), 0.6)
                else:
                    draw_glow(surf, pos, 34 + pulse * 6, C["gold"], 60 + 40 * pulse)
            pygame.draw.circle(surf, C["ink"], pos, 27)
            pygame.draw.circle(surf, fill, pos, 24)
            draw_glyph(surf, glyph, pos, 24, C["paper"])
            text(surf, t.name, (pos[0], pos[1] + 36), "bold", C["paper"] if t in opened or t.conquered else C["muted"],
                 center=True)
            sub = "Taken" if t.conquered else f"{len(t.garrison)} troops"
            text(surf, sub, (pos[0], pos[1] + 54), "small", C["green"] if t.conquered else C["muted"], center=True)
        pygame.draw.rect(surf, C["edge"], MAP_RECT, 2, border_radius=6)

    def draw_map_panel(self, surf):
        box = pygame.Rect(852, 72, 408, 678)
        pygame.draw.rect(surf, C["panel"], box, border_radius=6)
        pygame.draw.rect(surf, C["edge"], box, 1, border_radius=6)
        t = self.targets[self.map_sel]
        x, y = box.x + 16, box.y + 12
        opened = t in self.open_targets()
        text(surf, fit(t.name, "title", box.w - 32), (x, y), "title")
        y += 36
        status = "Taken" if t.conquered else ("Ready to attack" if opened else "Locked")
        text(surf, f"{t.faction}  ·  {status}", (x, y), "bold",
             C["green"] if t.conquered else (C["gold"] if opened else C["muted"]))
        y += 24
        for line in wrap(t.desc, "body", box.w - 32):
            text(surf, line, (x, y), "body", C["muted"])
            y += 19
        if t.prereq and not t.conquered and not opened:
            need = [self.targets[i].name for i in t.prereq if not self.targets[i].conquered]
            text(surf, fit("Requires: " + ", ".join(need), "small", box.w - 32), (x, y + 2), "small", C["red"])
            y += 20
        y += 10
        if not t.conquered:
            text(surf, f"Garrison ({len(t.garrison)}/{t.cap})", (x, y), "head")
            y += 28
            groups = t.grouped()
            for key, members in groups.items():
                ut = UNITS[key]
                draw_token(surf, ut, "enemy", (x + 12, y + 12), radius=11, bar=False)
                text(surf, f"{len(members)} × {ut.name}", (x + 32, y + 2), "bold")
                for j, m in enumerate(sorted(members, key=lambda s: -s.xp)[:18]):
                    pygame.draw.circle(surf, RANK_COLORS[m.rank], (box.x + 214 + j * 9, y + 11), 3)
                y += 27
            y += 8
            text(surf, "Spoils", (x, y), "head")
            y += 26
            for line in t.reward_lines() or (["Victory in the war"] if t.final else []):
                for part in wrap(line, "small", box.w - 32):
                    text(surf, part, (x, y), "small", C["gold"])
                    y += 18
        else:
            text(surf, "Your banner flies here.", (x, y), "body", C["green"])

        ready = self.available()
        text(surf, f"Your warband: {len(ready)} ready to march", (x, box.bottom - 88), "small", C["muted"])
        down = self.captain_down > 0
        if opened:
            self.ui.button(surf, (x, box.bottom - 64, 180, 40), "March!" if not down else "Captain hurt",
                           lambda: self.attack(t), enabled=not down, accent=not down)
        self.ui.button(surf, (box.right - 196, box.bottom - 64, 180, 40), "Back to Town (M)",
                       lambda: setattr(self, "scene", "town"))


def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("War on the Rim")
    init_fonts()
    clock = pygame.time.Clock()
    game = Game()
    while True:
        dt = min(clock.tick(FPS) / 1000, 0.05)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r and game.over:
                    game = Game()
                else:
                    game.on_key(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not game.over:
                game.on_click(event.pos)
        game.update(dt)
        game.draw(screen, pygame.mouse.get_pos())
        pygame.display.flip()


if __name__ == "__main__":
    main()
