"""
WAR ON THE RIM
==============
A real-time town builder with automatic, Conquest-of-Elysium-style battles.

  * Build your town, research upgrades and train a warband in real time.
  * March across a freshly generated map. Every region is new, bigger and
    nastier than the last. Clear a region's stronghold to push deeper.
  * Battles resolve on their own in rounds: units deploy, advance, shoot,
    cast spells, summon allies, strike with every weapon they carry,
    break and flee. Your choices are what you build and who you bring.
  * Soldiers have names, earn experience and climb the ranks
    (Recruit, Regular, Veteran, Elite, Champion). Losing a Champion hurts.

Modes: Campaign (3 regions, then the final Hold) or Endless War.

Controls
  Town/Map : click things. M = war map, P = pause, H = chronicle,
             C = compendium, ESC = menu.
  Battle   : SPACE/P pause, 1/2/3 speed, S skip, ENTER continue, ESC menu.
  Menus    : mouse, mouse wheel to scroll, ESC to go back.

Requires Python 3.8+ and pygame 2  (pip install pygame)
Save and settings files are written next to this script.
"""
import array
import itertools
import json
import math
import os
import pickle
import random
import time
from dataclasses import dataclass

import pygame

W, H = 1280, 760
FPS = 60
SAVE_VERSION = 4
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_PATH = os.path.join(BASE_DIR, "war_on_the_rim_save.dat")
SETTINGS_PATH = os.path.join(BASE_DIR, "war_on_the_rim_settings.json")

C = {
    "bg": (20, 22, 25), "ink": (12, 13, 15), "paper": (232, 224, 201),
    "muted": (150, 146, 131), "dim": (96, 94, 86),
    "panel": (31, 34, 38), "panel2": (41, 45, 50), "edge": (92, 81, 62),
    "grass": (50, 68, 51), "grass2": (56, 75, 56), "dirt": (92, 76, 56),
    "road": (104, 88, 64), "field": (72, 69, 50), "field2": (78, 75, 54),
    "gold": (216, 170, 72), "iron": (152, 166, 180), "essence": (120, 206, 226),
    "red": (192, 74, 60), "blue": (78, 140, 188), "green": (106, 182, 94),
    "white": (248, 242, 222), "purple": (150, 104, 186), "undead": (122, 100, 146),
    "wild": (118, 136, 64), "ember": (206, 104, 44), "mana": (96, 156, 236),
    "fire": (255, 140, 50), "holy": (255, 222, 120), "nature": (120, 210, 110),
    "dark": (176, 110, 220), "lightning": (170, 210, 255), "stone": (170, 160, 140),
}
FONTS = {}

RANKS = [(0, "Recruit"), (10, "Regular"), (30, "Veteran"), (65, "Elite"), (115, "Champion")]
RANK_COLORS = [(140, 140, 140), (120, 190, 110), (90, 160, 230), (200, 120, 230), (240, 190, 70)]
TIER_COLORS = {1: (150, 150, 150), 2: (110, 190, 110), 3: (100, 160, 235), 4: (240, 190, 70)}

DIFFICULTY = {
    "Easy": {"size": 0.75, "xp": -6, "raid": 0.75, "growth": 0.6},
    "Normal": {"size": 1.0, "xp": 0, "raid": 1.0, "growth": 1.0},
    "Hard": {"size": 1.3, "xp": 8, "raid": 1.25, "growth": 1.4},
}


def init_fonts():
    sans, serif = "segoeui,dejavusans,arial", "georgia,dejavuserif,times"
    FONTS["tiny"] = pygame.font.SysFont(sans, 11)
    FONTS["tinyb"] = pygame.font.SysFont(sans, 11, bold=True)
    FONTS["small"] = pygame.font.SysFont(sans, 13)
    FONTS["smallb"] = pygame.font.SysFont(sans, 13, bold=True)
    FONTS["body"] = pygame.font.SysFont(sans, 15)
    FONTS["bold"] = pygame.font.SysFont(sans, 15, bold=True)
    FONTS["head"] = pygame.font.SysFont(serif, 20, bold=True)
    FONTS["title"] = pygame.font.SysFont(serif, 26, bold=True)
    FONTS["big"] = pygame.font.SysFont(serif, 56, bold=True)
    FONTS["huge"] = pygame.font.SysFont(serif, 84, bold=True)


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
    s = str(s)
    if FONTS[font].size(s)[0] <= width:
        return s
    while s and FONTS[font].size(s + "...")[0] > width:
        s = s[:-1]
    return s + "..."


def wrap(s, font, width):
    lines = []
    for para in str(s).split("\n"):
        line = ""
        for w in para.split():
            trial = f"{line} {w}".strip()
            if FONTS[font].size(trial)[0] > width and line:
                lines.append(line)
                line = w
            else:
                line = trial
        lines.append(line)
    return lines


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


def fmt_time(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
class Settings:
    DEFAULTS = {"master": 80, "sfx": 80, "mute": False, "battle_speed": 1,
                "damage_numbers": True, "fullscreen": False, "raid_pause": True,
                "autosave": True, "best_endless": 0, "campaign_wins": 0}

    def __init__(self, path=SETTINGS_PATH):
        self.path = path
        self.data = dict(self.DEFAULTS)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            for k, v in loaded.items():
                if k in self.data:
                    self.data[k] = v
        except (OSError, ValueError):
            pass

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except OSError:
            pass


SETTINGS = Settings()


# --------------------------------------------------------------------------
# Sound: every effect is synthesised at start-up, no files needed
# --------------------------------------------------------------------------
class SoundBank:
    def __init__(self):
        self.ok = False
        self.sounds = {}
        self.last = {}

    def init(self):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1, 512)
            freq, size, channels = pygame.mixer.get_init()
            if size not in (-16, 16, 32, -32):
                return
            self.rate, self.size, self.channels = freq, size, channels
            pygame.mixer.set_num_channels(24)
            self.build()
            self.ok = True
        except Exception:
            self.ok = False

    def make(self, samples):
        if abs(self.size) == 16:
            arr = array.array("h")
            for v in samples:
                s = int(max(-1.0, min(1.0, v)) * 28000)
                for _ in range(self.channels):
                    arr.append(s)
        else:
            arr = array.array("f")
            for v in samples:
                s = max(-1.0, min(1.0, v)) * 0.85
                for _ in range(self.channels):
                    arr.append(s)
        return pygame.mixer.Sound(buffer=arr.tobytes())

    def synth(self, dur, fn, attack=0.004, curve=2.0):
        n = int(dur * self.rate)
        out = []
        for i in range(n):
            t = i / self.rate
            env = min(1.0, t / attack) * (1 - i / n) ** curve
            out.append(fn(t) * env)
        return out

    def build(self):
        rng = random.Random(3)
        tau = math.tau

        def noise_lp(alpha):
            state = [0.0]

            def f(_t):
                state[0] += alpha * (rng.uniform(-1, 1) - state[0])
                return state[0] * 2.2
            return f

        def seq(notes, each, wave=math.sin, overtone=0.3):
            out = []
            for f0 in notes:
                out += self.synth(each, lambda t, f0=f0: wave(tau * f0 * t) + overtone * wave(tau * 2 * f0 * t),
                                  curve=1.5)
            return out

        def square(x):
            return 1.0 if math.sin(x) >= 0 else -1.0

        lp1 = noise_lp(0.25)
        lp2 = noise_lp(0.08)
        lp3 = noise_lp(0.5)
        lp4 = noise_lp(0.15)
        self.sounds = {
            "click": self.make(self.synth(0.05, lambda t: 0.5 * math.sin(tau * 900 * t) + 0.2 * math.sin(tau * 1800 * t))),
            "hit": self.make(self.synth(0.12, lambda t: 0.9 * lp1(t) + 0.6 * math.sin(tau * 110 * t))),
            "block": self.make(self.synth(0.16, lambda t: 0.4 * (math.sin(tau * 1250 * t) + math.sin(tau * 1870 * t)
                                                                 + 0.6 * math.sin(tau * 2630 * t)), curve=3)),
            "arrow": self.make(self.synth(0.14, lambda t: lp3(t) * math.sin(math.pi * t / 0.14), attack=0.03)),
            "fire": self.make(self.synth(0.35, lambda t: lp2(t) * (1 + 0.5 * math.sin(tau * 13 * t)) * 1.4, attack=0.02)),
            "magic": self.make(self.synth(0.28, lambda t: 0.5 * math.sin(tau * (400 + 2400 * t) * t)
                                          + 0.2 * math.sin(tau * (800 + 4000 * t) * t), attack=0.01)),
            "lightning": self.make(self.synth(0.3, lambda t: lp3(t) * (1.5 if int(t * 90) % 3 == 0 else 0.3))),
            "death": self.make(self.synth(0.4, lambda t: 0.45 * square(tau * (260 - 380 * t) * t) * 0.6
                                          + 0.3 * lp4(t), curve=1.5)),
            "summon": self.make(seq([330, 415, 494, 659], 0.07)),
            "heal": self.make(self.synth(0.35, lambda t: 0.4 * math.sin(tau * (660 + 500 * t) * t)
                                         + 0.15 * math.sin(tau * 1320 * t), attack=0.03)),
            "build": self.make(self.synth(0.12, lambda t: lp1(t) + math.sin(tau * 90 * t))
                               + self.synth(0.16, lambda t: lp1(t) + math.sin(tau * 80 * t))),
            "train": self.make(seq([523, 784], 0.09)),
            "horn": self.make(self.synth(1.0, lambda t: 0.35 * (math.sin(tau * 147 * t + 0.4 * math.sin(tau * 5 * t))
                                                                + 0.5 * math.sin(tau * 294 * t)
                                                                + 0.25 * math.sin(tau * 441 * t)),
                                         attack=0.12, curve=0.7)),
            "victory": self.make(seq([523, 659, 784], 0.12) + seq([1046], 0.5)),
            "defeat": self.make(seq([392, 349, 311], 0.18) + seq([262], 0.6)),
            "promote": self.make(seq([988, 1319], 0.16, overtone=0.5)),
            "error": self.make(self.synth(0.15, lambda t: 0.3 * square(tau * 110 * t))),
            "coin": self.make(seq([1318, 1975], 0.07, overtone=0.1)),
            "march": self.make(self.synth(0.1, lambda t: math.sin(tau * 70 * t) + 0.5 * lp1(t)) * 3),
        }

    def play(self, name, vol=1.0):
        if not self.ok or SETTINGS["mute"] or name not in self.sounds:
            return
        now = pygame.time.get_ticks()
        if now - self.last.get(name, -1000) < 55:
            return
        self.last[name] = now
        v = SETTINGS["master"] / 100 * SETTINGS["sfx"] / 100 * vol
        if v <= 0:
            return
        snd = self.sounds[name]
        snd.set_volume(min(1.0, v))
        snd.play()


SOUND = SoundBank()


# --------------------------------------------------------------------------
# Spells
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Spell:
    name: str
    kind: str     # bolt blast chain entangle summon raise heal massheal bless haste stoneskin curse wail
    cost: int
    rng: int = 0
    dmg: int = 0
    style: str = "fire"
    ap: bool = False
    an: bool = False
    holy: bool = False
    slow: int = 0
    area: int = 1
    unit: str = ""
    limit: int = 0
    offensive: bool = True
    desc: str = ""


SPELLS = {
    "firebolt": Spell("Firebolt", "bolt", 1, 8, 6, "fire", ap=True, desc="A bolt of fire that burns through armour."),
    "fireball": Spell("Fireball", "blast", 4, 7, 6, "fire", desc="Explodes over a 3x3 area. Hits friends too."),
    "meteor": Spell("Meteor", "blast", 7, 10, 9, "fire", area=2, desc="Crushes a 5x5 area. Hits friends too."),
    "lightning": Spell("Chain Lightning", "chain", 5, 9, 7, "lightning", ap=True,
                       desc="Leaps between up to three foes."),
    "frostbolt": Spell("Frostbolt", "bolt", 2, 8, 5, "lightning", slow=1, desc="Chills and slows the target."),
    "entangle": Spell("Entangle", "entangle", 2, 7, style="nature", slow=2,
                      desc="Roots every foe in a 3x3 area for two rounds."),
    "heal": Spell("Heal", "heal", 1, 4, 5, "holy", offensive=False, desc="Mends the most wounded ally nearby."),
    "mass_heal": Spell("Mass Heal", "massheal", 5, 3, 6, "holy", offensive=False,
                       desc="Heals every wounded ally within 3 tiles."),
    "regrowth": Spell("Regrowth", "massheal", 4, 2, 4, "nature", offensive=False,
                      desc="Heals every wounded ally within 2 tiles."),
    "smite": Spell("Smite", "bolt", 2, 5, 5, "holy", holy=True, desc="Holy fire. Extra damage to undead."),
    "bless": Spell("Bless", "bless", 3, 2, style="holy", offensive=False,
                   desc="Nearby allies gain +2 attack and defence."),
    "haste": Spell("Haste", "haste", 3, 3, style="lightning", offensive=False,
                   desc="Nearby allies move twice as far."),
    "stoneskin": Spell("Stoneskin", "stoneskin", 4, 2, style="stone", offensive=False,
                       desc="Nearby allies gain +3 armour."),
    "curse": Spell("Hex", "curse", 2, 7, style="dark", desc="The strongest foe in range loses attack and defence."),
    "drain": Spell("Grave Bolt", "bolt", 1, 7, 5, "dark", ap=True, desc="A bolt of grave-cold."),
    "soulbolt": Spell("Soul Bolt", "bolt", 2, 8, 7, "dark", an=True, desc="Ignores armour entirely."),
    "wail": Spell("Wail", "wail", 4, 3, style="dark", desc="Terrifies every living foe within 3 tiles."),
    "raise_dead": Spell("Raise Dead", "raise", 3, 6, style="dark", unit="skeleton", offensive=False,
                        desc="A nearby corpse rises as a skeleton (up to 6)."),
    "summon_wolf": Spell("Call Wolf", "summon", 4, style="nature", unit="wolf", limit=3, offensive=False,
                         desc="Summons a wolf (up to 3)."),
    "summon_bear": Spell("Call Bear", "summon", 6, style="nature", unit="bear", limit=2, offensive=False,
                         desc="Summons a great bear (up to 2)."),
    "summon_imp": Spell("Conjure Imp", "summon", 3, style="fire", unit="imp", limit=4, offensive=False,
                        desc="Conjures a flying fire imp (up to 4)."),
    "summon_elemental": Spell("Bind Fire Elemental", "summon", 7, style="fire", unit="fire_elemental", limit=2,
                              offensive=False, desc="Binds a burning elemental (up to 2)."),
    "summon_golem": Spell("Raise Earth Golem", "summon", 9, style="stone", unit="earth_golem", limit=1,
                          offensive=False, desc="Raises a towering golem (1)."),
    "summon_guardian": Spell("Call Guardian", "summon", 6, style="holy", unit="guardian", limit=2,
                             offensive=False, desc="Calls a radiant guardian spirit (up to 2)."),
    "summon_wraith": Spell("Bind Wraith", "summon", 7, style="dark", unit="wraith", limit=2, offensive=False,
                           desc="Binds a wraith to your will (up to 2)."),
    "summon_direwolf": Spell("Call Pack", "summon", 4, style="nature", unit="dire_wolf", limit=3,
                             offensive=False, desc="Summons dire wolves (up to 3)."),
    "summon_spiderling": Spell("Brood", "summon", 3, style="nature", unit="spiderling", limit=4,
                               offensive=False, desc="Spawns spiderlings (up to 4)."),
}

TAG_TEXT = {
    "commander": "Commander: allies fight bravely while it stands.",
    "frenzy": "Frenzy: when badly hurt, +3 damage and never flees.",
    "guard": "Guardian: allies next to it get +2 defence.",
    "skirmish": "Skirmisher: moves away from melee to keep shooting.",
    "melee_caster": "Fights in the front line and casts.",
    "mindless": "Mindless: never flees.",
    "undead": "Undead: never flees, immune to poison, hurt by holy.",
    "ethereal": "Ethereal: 75% of non-magic hits pass through.",
    "regen": "Regenerates 2 HP each round.",
    "plant": "Plant: immune to poison.",
    "construct": "Construct: immune to poison, never flees.",
    "fear": "Terrifying: foes beside it must pass morale checks.",
    "aura_fire": "Burning aura: scorches adjacent foes each round.",
    "flying": "Flying: moves over other units.",
    "static": "Static: never moves.",
    "stalker": "Stalker: hunts casters and archers first.",
    "siege": "Siege engine: slow, never flees.",
}


# --------------------------------------------------------------------------
# Weapons and units
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
            "reload": "slow reload", "anti_mount": "+5 vs riders", "area": "3x3 blast"}
    SHORT = {"ap": "AP", "an": "AN", "charge": "charge", "repel": "repel", "sweep": "sweep",
             "poison": "poison", "drain": "drain", "magic": "magic", "holy": "holy", "thrown": "thrown",
             "reload": "slow", "anti_mount": "anti-rider", "stun": "stun", "area": "area"}

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
    essence: int = 0
    train: float = 5.0
    building: str = ""
    req_level: int = 1
    tier: int = 1
    family: str = ""
    faction: str = "player"
    glyph: str = "sword"
    big: bool = False
    mounted: bool = False
    tint: tuple = None
    tags: tuple = ()
    desc: str = ""

    @property
    def rng(self):
        return max((w.rng for w in self.weapons if w.rng and "thrown" not in w.tags), default=0)

    @property
    def points(self):
        return {1: 1, 2: 2, 3: 4, 4: 8}[self.tier]

    def attack_line(self):
        s = " · ".join(w.short() for w in self.weapons)
        if self.spells:
            s += " · " + ", ".join(SPELLS[k].name for k in self.spells)
        return s

    def cost_text(self):
        parts = [f"{self.gold}g"]
        if self.iron:
            parts.append(f"{self.iron}i")
        if self.essence:
            parts.append(f"{self.essence}e")
        return " ".join(parts)


def U(key, name, hp, att, df, prot, mor, weapons, **kw):
    return UnitType(key, name, hp, att, df, prot, mor, tuple(weapons), **kw)


STUN = ("stun",)
UD, EM, WK, IV_T = C["undead"], C["ember"], C["wild"], None

UNIT_LIST = [
    # ================= your people =================
    U("captain", "Captain", 18, 11, 11, 3, 15, [Wp("Longsword", 6), Wp("Shield Bash", 2, chance=25, tags=STUN)],
      tier=3, family="captain", glyph="banner", big=True, tags=("commander",),
      desc="Leads the warband. Allies stand firm while the Captain lives."),
    U("militia", "Militia", 9, 8, 8, 1, 8, [Wp("Pitchfork", 4, reach=2)], gold=10, train=4,
      building="hall", family="infantry", glyph="fork", desc="Cheap levies. Pitchforks reach past the front."),
    # barracks
    U("spearman", "Spearman", 11, 10, 12, 4, 10, [Wp("Spear", 5, reach=2, tags=("repel", "anti_mount"))],
      gold=18, iron=4, train=6, building="barracks", family="infantry", glyph="spear",
      desc="Holds the line and stops charges cold."),
    U("berserker", "Berserker", 13, 11, 8, 1, 12, [Wp("Axe", 5), Wp("Axe", 5)], gold=24, iron=8, train=8,
      building="barracks", req_level=2, tier=2, family="infantry", glyph="axe", tags=("frenzy",),
      desc="Two axes. Wounded: hits harder, never flees."),
    U("shieldbearer", "Shieldbearer", 15, 9, 14, 7, 13, [Wp("Shortsword", 4), Wp("Shield Bash", 2, chance=30, tags=STUN)],
      gold=30, iron=18, train=9, building="barracks", req_level=3, tier=2, family="infantry", glyph="shield",
      tags=("guard",), desc="Living wall. Allies beside it are harder to hit."),
    U("blademaster", "Blademaster", 18, 14, 13, 5, 14, [Wp("Greatsword", 9, tags=("sweep", "ap"))],
      gold=55, iron=25, train=14, building="barracks", req_level=4, tier=3, family="infantry", glyph="gsword",
      big=True, desc="Sweeping greatsword cuts through two foes."),
    # archery range
    U("archer", "Archer", 8, 10, 7, 1, 9, [Wp("Longbow", 5, rng=10, ammo=12), Wp("Dagger", 3)], gold=20, train=6,
      building="range", family="ranged", glyph="bow", desc="Long range, lots of arrows. Weak up close."),
    U("crossbow", "Crossbowman", 10, 10, 9, 5, 10,
      [Wp("Heavy Crossbow", 9, rng=6, ammo=8, tags=("ap", "reload")), Wp("Hatchet", 4)],
      gold=26, iron=10, train=8, building="range", req_level=2, tier=2, family="ranged", glyph="xbow",
      desc="Short-range armour breaker. Slow to reload."),
    U("ranger", "Ranger", 11, 12, 10, 2, 12,
      [Wp("Hunting Bow", 6, rng=9, ammo=14, tags=("poison",)), Wp("Knife", 3), Wp("Knife", 3)],
      move=2, gold=45, iron=5, train=12, building="range", req_level=3, tier=3, family="ranged", glyph="hood",
      tags=("skirmish",), desc="Poisoned arrows. Slips away from melee."),
    # stables
    U("knight", "Knight", 20, 12, 13, 9, 13,
      [Wp("Lance", 9, tags=("charge", "ap")), Wp("Longsword", 6), Wp("Hooves", 3)],
      move=2, gold=50, iron=25, train=14, building="stables", tier=3, family="cavalry", glyph="lance",
      big=True, mounted=True, desc="Devastating charge, then sword and hooves."),
    U("horse_archer", "Horse Archer", 12, 11, 10, 3, 11, [Wp("Shortbow", 5, rng=7, ammo=10), Wp("Sabre", 4)],
      move=2, gold=40, iron=10, train=11, building="stables", req_level=2, tier=2, family="cavalry",
      glyph="hbow", mounted=True, tags=("skirmish",), desc="Rides away from melee and keeps shooting."),
    # temple
    U("priest", "Priest", 9, 7, 7, 1, 12, [Wp("Mace", 4)], mana=8, regen=1, spells=("heal", "smite"),
      gold=32, essence=2, train=10, building="temple", tier=2, family="holy", glyph="cross",
      desc="Heals allies. Smites the undead."),
    U("paladin", "Paladin", 18, 13, 14, 8, 15,
      [Wp("Holy Blade", 7, tags=("magic", "holy")), Wp("Shield Bash", 2, chance=25, tags=STUN)],
      mana=3, regen=1, spells=("bless",), gold=60, iron=30, essence=4, train=16, building="temple",
      req_level=2, tier=3, family="holy", glyph="pshield", big=True, tags=("melee_caster",),
      desc="Frontline holy knight. Blesses those beside."),
    U("high_priestess", "High Priestess", 12, 9, 10, 2, 16, [Wp("Sun Staff", 4, tags=("magic", "holy"))],
      mana=16, regen=2, spells=("mass_heal", "summon_guardian", "smite"), gold=90, essence=12, train=20,
      building="temple", req_level=3, tier=4, family="holy", glyph="sun",
      desc="Mass healing and radiant guardian spirits."),
    # arcanum
    U("apprentice", "Apprentice", 7, 7, 6, 0, 9, [Wp("Dagger", 2)], mana=8, regen=1, spells=("firebolt",),
      gold=28, essence=2, train=8, building="arcanum", family="arcane", glyph="orb",
      desc="Cheap caster. Firebolts burn through armour."),
    U("battlemage", "Battle Mage", 9, 8, 7, 0, 11, [Wp("Staff", 3)], mana=12, regen=1,
      spells=("fireball", "firebolt"), gold=48, iron=10, essence=5, train=12, building="arcanum",
      req_level=2, tier=2, family="arcane", glyph="flame", desc="Fireballs scorch a 3x3 area. Mind your lines."),
    U("stormmage", "Storm Mage", 10, 9, 8, 1, 12, [Wp("Staff", 3)], mana=15, regen=1,
      spells=("lightning", "haste"), gold=75, iron=20, essence=8, train=16, building="arcanum",
      req_level=3, tier=3, family="arcane", glyph="bolt", desc="Chain lightning. Hastens allies."),
    U("archmage", "Archmage", 12, 10, 9, 2, 15, [Wp("Runed Staff", 4, tags=("magic",))], mana=20, regen=2,
      spells=("meteor", "frostbolt", "firebolt"), gold=120, iron=20, essence=15, train=24,
      building="arcanum", req_level=4, tier=4, family="arcane", glyph="meteor",
      desc="Calls down meteors on whole regiments."),
    # grove
    U("druid", "Druid", 9, 7, 7, 1, 12, [Wp("Staff", 3)], mana=10, regen=2, spells=("summon_wolf", "entangle"),
      gold=38, essence=3, train=10, building="grove", tier=2, family="nature", glyph="leaf",
      desc="Calls wolves and roots enemies in place."),
    U("treant", "Treant", 30, 10, 9, 6, 30, [Wp("Branches", 8, tags=("sweep",)), Wp("Grasping Roots", 3, chance=30, tags=STUN)],
      gold=65, essence=3, train=18, building="grove", req_level=2, tier=3, family="nature", glyph="tree",
      big=True, tags=("mindless", "regen", "plant"), desc="Sweeping branches. Regrows, never flees."),
    U("archdruid", "Archdruid", 12, 9, 9, 2, 15, [Wp("Oak Staff", 4)], mana=16, regen=2,
      spells=("summon_bear", "regrowth", "entangle"), gold=85, essence=10, train=20, building="grove",
      req_level=3, tier=4, family="nature", glyph="oak", desc="Calls great bears and regrows the wounded."),
    # summoning circle
    U("conjurer", "Conjurer", 8, 7, 7, 0, 10, [Wp("Dagger", 2)], mana=10, regen=2, spells=("summon_imp",),
      gold=34, essence=4, train=10, building="conjury", tier=2, family="conjury", glyph="rune",
      desc="Fills the sky with fire imps."),
    U("elementalist", "Elementalist", 10, 8, 8, 1, 12, [Wp("Staff", 3)], mana=14, regen=2,
      spells=("summon_elemental", "firebolt"), gold=60, iron=5, essence=8, train=14, building="conjury",
      req_level=2, tier=3, family="conjury", glyph="flame2", desc="Binds living fire to fight for you."),
    U("geomancer", "Geomancer", 14, 9, 10, 4, 14, [Wp("Stone Maul", 5)], mana=18, regen=2,
      spells=("summon_golem", "stoneskin"), gold=90, iron=20, essence=12, train=20, building="conjury",
      req_level=3, tier=4, family="conjury", glyph="rock", desc="Raises earth golems and stone-skins allies."),
    # bone crypt
    U("gravecaller", "Gravecaller", 9, 7, 7, 1, 12, [Wp("Sickle", 4)], mana=12, regen=2,
      spells=("raise_dead", "drain"), gold=34, essence=4, train=10, building="crypt", tier=2, family="necro",
      glyph="sickle", desc="Raises the fallen, friend or foe, as skeletons."),
    U("deathknight", "Death Knight", 22, 13, 12, 9, 20, [Wp("Runeblade", 9, tags=("drain", "magic")), Wp("Bone Fist", 3)],
      gold=70, iron=30, essence=6, train=16, building="crypt", req_level=2, tier=3, family="necro",
      glyph="dknight", big=True, tags=("undead", "fear"), desc="Undead champion. Terrifies and drains."),
    U("lich", "Lich", 16, 10, 10, 4, 20, [Wp("Soul Staff", 4, tags=("an",))], mana=18, regen=2,
      spells=("soulbolt", "summon_wraith", "raise_dead"), gold=110, iron=15, essence=15, train=24,
      building="crypt", req_level=3, tier=4, family="necro", glyph="lich", tags=("undead",),
      desc="Soul bolts, bound wraiths and endless dead."),
    # beast lodge
    U("war_hound", "War Hound", 9, 10, 9, 1, 9, [Wp("Bite", 5)], move=2, gold=14, train=4, building="lodge",
      family="beast", glyph="fang", desc="Fast, cheap and hungry."),
    U("falconer", "Falconer", 9, 10, 8, 1, 11, [Wp("Falcon Strike", 5, rng=7, ammo=16), Wp("Knife", 3)],
      gold=30, train=8, building="lodge", req_level=2, tier=2, family="beast", glyph="bird",
      desc="Sends a falcon to harry the enemy."),
    U("war_bear", "War Bear", 26, 12, 9, 4, 14, [Wp("Claw", 6), Wp("Claw", 6), Wp("Maul", 4, chance=20, tags=STUN)],
      gold=55, iron=5, train=14, building="lodge", req_level=3, tier=3, family="beast", glyph="paw", big=True,
      desc="Armoured bear. Three brutal attacks."),
    U("griffin", "Griffin", 24, 14, 13, 4, 15, [Wp("Talons", 7), Wp("Beak", 6, tags=("ap",))], move=3,
      gold=100, iron=10, essence=5, train=20, building="lodge", req_level=4, tier=4, family="beast",
      glyph="wing", big=True, tags=("flying",), desc="Flies over the lines to strike the rear."),
    # siege workshop
    U("ballista", "Ballista", 14, 10, 5, 6, 20, [Wp("Bolt Thrower", 12, rng=12, ammo=10, tags=("ap", "reload"))],
      gold=45, iron=20, train=12, building="workshop", tier=2, family="siege", glyph="ballista",
      tags=("siege",), desc="Huge bolts at extreme range."),
    U("catapult", "Catapult", 18, 8, 4, 6, 20, [Wp("Boulder", 8, rng=13, ammo=8, tags=("area", "reload"))],
      gold=60, iron=25, train=16, building="workshop", req_level=2, tier=3, family="siege", glyph="catapult",
      big=True, tags=("siege",), desc="Hurls boulders that smash a 3x3 area."),
    U("iron_golem", "Iron Golem", 34, 11, 8, 12, 30, [Wp("Iron Fist", 9), Wp("Iron Fist", 9)],
      gold=110, iron=60, essence=6, train=22, building="workshop", req_level=3, tier=4, family="siege",
      glyph="golem", big=True, tags=("construct",), desc="Walking fortress of iron."),
    # monastery
    U("monk", "Monk", 12, 12, 14, 0, 14, [Wp("Fist", 4), Wp("Fist", 4), Wp("Palm Strike", 2, chance=25, tags=STUN)],
      move=2, gold=28, train=9, building="monastery", tier=2, family="monk", glyph="fist",
      desc="Fast, hard to hit, strikes three times."),
    U("witch_hunter", "Witch Hunter", 11, 11, 10, 3, 14,
      [Wp("Silver Crossbow", 7, rng=7, ammo=10, tags=("magic", "holy")), Wp("Silver Dagger", 4, tags=("magic", "holy"))],
      gold=40, iron=10, train=11, building="monastery", req_level=2, tier=2, family="monk", glyph="hunter",
      desc="Silver weapons. Bane of undead and spirits."),
    # mercenary guild
    U("sellsword", "Sellsword", 14, 11, 10, 5, 10, [Wp("Zweihander", 8, tags=("sweep",))], gold=36, train=8,
      building="guild", tier=2, family="merc", glyph="zwei", desc="Hired steel. Sweeps two foes. No iron needed."),
    U("assassin", "Assassin", 10, 14, 13, 1, 12, [Wp("Poison Blade", 5, tags=("poison",)), Wp("Poison Blade", 5, tags=("poison",))],
      move=2, gold=55, train=12, building="guild", req_level=2, tier=3, family="merc", glyph="daggers",
      tags=("stalker",), desc="Hunts down enemy casters and archers."),
    U("ogre_merc", "Ogre Mercenary", 30, 11, 7, 4, 13, [Wp("Great Club", 12, chance=20, tags=STUN), Wp("Stomp", 4)],
      gold=70, train=16, building="guild", req_level=3, tier=3, family="merc", glyph="club", big=True,
      desc="A very large, very expensive friend."),
    # walls
    U("tower", "Tower Archer", 12, 11, 9, 5, 20, [Wp("Longbow", 6, rng=10, ammo=14)], tier=2, family="tower",
      glyph="tower", tags=("static",), desc="Fires from the walls during raids."),

    # ================= summons =================
    U("wolf", "Wolf", 10, 10, 9, 1, 9, [Wp("Bite", 5)], move=2, family="beast", faction="summon", glyph="fang",
      desc="Summoned by druids."),
    U("bear", "Great Bear", 26, 12, 9, 4, 14, [Wp("Claw", 6), Wp("Claw", 6)], tier=3, family="beast",
      faction="summon", glyph="paw", big=True, desc="Summoned by archdruids."),
    U("imp", "Fire Imp", 7, 10, 11, 1, 10, [Wp("Fire Spit", 4, rng=4, ammo=6, tags=("magic",)), Wp("Claw", 3)],
      move=2, tier=2, family="conjured", faction="summon", glyph="horns", tint=EM, tags=("flying",),
      desc="Small, fast, spits fire."),
    U("fire_elemental", "Fire Elemental", 22, 11, 9, 3, 30, [Wp("Burning Fist", 8, tags=("magic", "sweep"))],
      tier=3, family="conjured", faction="summon", glyph="flame", tint=EM, big=True,
      tags=("mindless", "aura_fire", "construct"), desc="Living flame. Burns all beside it."),
    U("earth_golem", "Earth Golem", 40, 11, 7, 11, 30,
      [Wp("Stone Fist", 10, chance=20, tags=STUN), Wp("Stone Fist", 10)], tier=4, family="conjured",
      faction="summon", glyph="rock", tint=C["stone"], big=True, tags=("mindless", "construct"),
      desc="A hill that walks."),
    U("guardian", "Guardian Spirit", 18, 13, 13, 5, 30, [Wp("Radiant Sword", 8, tags=("magic", "holy"))],
      tier=3, family="holy_summon", faction="summon", glyph="wing", tint=C["holy"],
      tags=("mindless", "flying"), desc="A radiant warrior from beyond."),
    U("dire_wolf", "Dire Wolf", 14, 11, 9, 2, 10, [Wp("Bite", 7)], move=2, tier=2, family="beast",
      faction="summon", glyph="fang", tint=WK, desc="Huge wolf of the wilds."),
    U("spiderling", "Spiderling", 6, 9, 9, 1, 30, [Wp("Venom Bite", 3, tags=("poison",))], move=2,
      family="beast", faction="summon", glyph="spider", tint=WK, tags=("mindless",), desc="Chittering brood."),

    # ================= Ironveil =================
    U("raider", "Raider", 9, 10, 8, 2, 9, [Wp("Hand Axe", 6), Wp("Throwing Axe", 5, rng=3, ammo=1, tags=("thrown", "ap"))],
      faction="Ironveil", glyph="axe", desc="Throws an axe, then charges in."),
    U("slinger", "Slinger", 7, 9, 7, 0, 8, [Wp("Sling", 4, rng=7, ammo=12), Wp("Knife", 3)],
      faction="Ironveil", glyph="sling", desc="Skirmisher with a sling."),
    U("warg", "Warg Rider", 12, 11, 10, 2, 9, [Wp("Spear", 5, tags=("charge",)), Wp("Scimitar", 4), Wp("Warg Bite", 5)],
      move=2, tier=2, faction="Ironveil", glyph="fang", mounted=True, desc="Rider and wolf both attack."),
    U("ironguard", "Ironguard", 14, 12, 12, 6, 12, [Wp("Mace", 8, tags=("ap",)), Wp("Shield Bash", 2, chance=25, tags=STUN)],
      tier=2, faction="Ironveil", glyph="helm", desc="Armoured elite. Maces crush armour."),
    U("shaman", "Ash Shaman", 9, 8, 6, 0, 10, [Wp("Staff", 3)], mana=8, regen=1, spells=("firebolt",),
      tier=2, faction="Ironveil", glyph="star", desc="Hurls armour-burning cinders."),
    U("hexer", "Hexer", 9, 8, 7, 0, 11, [Wp("Venom Dagger", 2, tags=("poison",))], mana=10, regen=2,
      spells=("curse", "firebolt"), tier=2, faction="Ironveil", glyph="eye", desc="Hexes your best fighters."),
    U("brute", "Brute", 24, 10, 7, 3, 11, [Wp("Great Club", 11, chance=20, tags=STUN), Wp("Kick", 3)],
      tier=3, faction="Ironveil", glyph="club", big=True, desc="Huge. Its club can stun."),
    U("ogre", "Ogre", 30, 11, 7, 4, 13, [Wp("Great Club", 12, chance=20, tags=STUN), Wp("Stomp", 4)],
      tier=3, faction="Ironveil", glyph="club", big=True, desc="Chained war-ogre."),
    U("warlord", "Warlord", 34, 15, 13, 9, 16, [Wp("Great Axe", 11, tags=("sweep", "ap")), Wp("Kick", 3)],
      tier=4, faction="Ironveil", glyph="crown", big=True, tags=("commander",), desc="Master of Ironveil."),

    # ================= The Barrow =================
    U("skeleton", "Skeleton", 8, 9, 9, 3, 30, [Wp("Rusty Sword", 7)], faction="Barrow", glyph="skull", tint=UD,
      tags=("undead",), desc="Rattling dead. Never flees."),
    U("bone_archer", "Bone Archer", 8, 9, 8, 2, 30, [Wp("Bone Bow", 5, rng=8, ammo=10), Wp("Rusty Knife", 3)],
      faction="Barrow", glyph="bow", tint=UD, tags=("undead",), desc="Skeletal archer."),
    U("ghoul", "Ghoul", 13, 11, 8, 1, 30, [Wp("Claw", 5), Wp("Claw", 5), Wp("Bite", 5, tags=("poison",))],
      tier=2, faction="Barrow", glyph="claw", tint=UD, tags=("undead",), desc="Claws twice, bites with grave-rot."),
    U("wraith", "Wraith", 14, 12, 12, 0, 30, [Wp("Chill Touch", 6, tags=("an", "drain"))], tier=2,
      faction="Barrow", glyph="ghost", tint=UD, tags=("undead", "ethereal"), desc="Ethereal. Its touch ignores armour."),
    U("necromancer", "Necromancer", 10, 8, 7, 1, 14, [Wp("Bone Staff", 3)], mana=12, regen=2,
      spells=("raise_dead", "drain"), tier=2, faction="Barrow", glyph="necro", tint=UD,
      desc="Raises the fallen as skeletons."),
    U("grave_knight", "Grave Knight", 22, 13, 12, 9, 30, [Wp("Cursed Lance", 8, tags=("charge", "ap")), Wp("Black Sword", 6)],
      move=2, tier=3, faction="Barrow", glyph="lance", tint=UD, big=True, mounted=True, tags=("undead",),
      desc="Dead knight on a dead horse."),
    U("banshee", "Banshee", 12, 10, 12, 0, 30, [Wp("Chill Touch", 4, tags=("an",))], mana=8, regen=1,
      spells=("wail",), tier=3, faction="Barrow", glyph="ghost", tint=UD,
      tags=("undead", "ethereal", "flying"), desc="Her wail breaks the living."),
    U("barrowking", "Barrow King", 30, 14, 13, 8, 30,
      [Wp("Black Blade", 10, tags=("drain", "ap")), Wp("Grave Grip", 3, chance=30, tags=STUN)],
      tier=4, faction="Barrow", glyph="crown", big=True, tint=UD, tags=("undead", "commander", "fear"),
      desc="Ancient lord. Terrifies those beside it."),

    # ================= Wildkin =================
    U("beastman", "Beastman", 12, 10, 9, 2, 10, [Wp("Crude Spear", 5), Wp("Gore", 4)], faction="Wildkin",
      glyph="horns", tint=WK, desc="Horned raider of the deep woods."),
    U("harpy", "Harpy", 10, 11, 12, 1, 9, [Wp("Talons", 4), Wp("Talons", 4)], move=3, tier=2,
      faction="Wildkin", glyph="wing", tint=WK, tags=("flying",), desc="Swoops over the lines."),
    U("giant_spider", "Giant Spider", 16, 11, 10, 4, 30,
      [Wp("Venom Bite", 5, tags=("poison",)), Wp("Web", 1, rng=4, ammo=3, chance=60, tags=STUN)],
      tier=2, faction="Wildkin", glyph="spider", tint=WK, tags=("mindless",), desc="Webs its prey, then feeds."),
    U("wild_shaman", "Wild Shaman", 10, 8, 8, 1, 12, [Wp("Antler Staff", 3)], mana=12, regen=2,
      spells=("summon_direwolf", "entangle"), tier=2, faction="Wildkin", glyph="leaf", tint=WK,
      desc="Calls dire wolves and grasping vines."),
    U("brood_mother", "Brood Mother", 24, 11, 10, 5, 30, [Wp("Venom Fangs", 6, tags=("poison",))], mana=9, regen=2,
      spells=("summon_spiderling",), tier=3, faction="Wildkin", glyph="spider", tint=WK, big=True,
      tags=("mindless",), desc="Spills spiderlings into battle."),
    U("cave_bear", "Cave Bear", 28, 12, 9, 5, 14, [Wp("Claw", 7), Wp("Claw", 7)], tier=3, faction="Wildkin",
      glyph="paw", tint=WK, big=True, desc="Enormous and furious."),
    U("troll", "Forest Troll", 32, 12, 8, 5, 14, [Wp("Claw", 8), Wp("Claw", 8)], tier=3, faction="Wildkin",
      glyph="claw", tint=WK, big=True, tags=("regen",), desc="Regenerates. Burn it down."),
    U("beastlord", "Beastlord", 40, 15, 13, 6, 18, [Wp("Twin Axe", 9), Wp("Twin Axe", 9), Wp("Gore", 6)],
      tier=4, faction="Wildkin", glyph="crown", tint=WK, big=True, tags=("commander", "fear"),
      desc="Horned king of the Wildkin."),

    # ================= Emberkin =================
    U("cultist", "Ash Cultist", 10, 9, 8, 1, 9, [Wp("Sickle", 5), Wp("Fire Dart", 3, rng=3, ammo=2, tags=("magic", "thrown"))],
      faction="Emberkin", glyph="sickle", tint=EM, desc="Zealot of the flame."),
    U("flamecaller", "Flamecaller", 9, 8, 7, 0, 11, [Wp("Staff", 3)], mana=12, regen=1,
      spells=("fireball", "firebolt"), tier=2, faction="Emberkin", glyph="flame", tint=EM,
      desc="Throws fireballs into your ranks."),
    U("salamander", "Salamander", 14, 10, 10, 4, 12, [Wp("Fire Spit", 6, rng=4, ammo=4, tags=("magic",)), Wp("Bite", 5)],
      tier=2, faction="Emberkin", glyph="fang", tint=EM, tags=("plant",), desc="Fire-spitting lizard."),
    U("ember_knight", "Ember Knight", 20, 13, 13, 8, 14,
      [Wp("Burning Sword", 8, tags=("magic",)), Wp("Shield Bash", 2, chance=25, tags=STUN)], tier=3,
      faction="Emberkin", glyph="helm", tint=EM, tags=("aura_fire",), desc="Armour that burns to the touch."),
    U("ember_priest", "Ember Priest", 10, 9, 9, 1, 14, [Wp("Brand", 4, tags=("magic",))], mana=16, regen=2,
      spells=("summon_elemental", "summon_imp", "firebolt"), tier=3, faction="Emberkin", glyph="star",
      tint=EM, desc="Summons imps and elementals."),
    U("pyre_lord", "Pyre Lord", 42, 15, 13, 8, 20,
      [Wp("Hellfire Blade", 11, tags=("magic", "sweep")), Wp("Horns", 5)], mana=10, regen=2,
      spells=("summon_imp",), tier=4, faction="Emberkin", glyph="horns", tint=EM, big=True,
      tags=("commander", "aura_fire", "melee_caster"), desc="A demon of the burning pit."),
]
UNITS = {u.key: u for u in UNIT_LIST}
RECRUITABLE = [u for u in UNIT_LIST if u.building]
SUMMON_TYPES = [u for u in UNIT_LIST if u.faction == "summon"]
SUMMONER_OF = {}
for _u in UNIT_LIST:
    for _s in _u.spells:
        if SPELLS[_s].unit:
            SUMMONER_OF.setdefault(SPELLS[_s].unit, []).append(_u.name)


def in_group(t, group):
    if group == "all":
        return "static" not in t.tags
    if group.startswith("u:"):
        return t.key in group[2:].split(",")
    if group == "melee":
        return not t.rng and not t.spells and "static" not in t.tags
    if group == "ranged":
        return t.rng > 0 and "static" not in t.tags
    if group == "casters":
        return bool(t.spells)
    return t.family == group


# --------------------------------------------------------------------------
# Research
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Tech:
    key: str
    name: str
    building: str
    level: int
    gold: int
    iron: int = 0
    essence: int = 0
    desc: str = ""
    mods: tuple = ()     # (group, stat, value)
    econ: tuple = ()     # (name, value)


T = Tech
TECHS = [
    T("caravans", "Caravans", "market", 2, 120, desc="+1 gold per second.", econ=(("gold_flat", 1.0),)),
    T("merchant_guilds", "Merchant Guilds", "market", 4, 260, 40, desc="+15% gold income.", econ=(("gold_mult", 0.15),)),
    T("deep_shafts", "Deep Shafts", "mine", 2, 110, desc="+40% iron income.", econ=(("iron_mult", 0.4),)),
    T("ley_lines", "Ley Lines", "well", 2, 120, 10, desc="+50% essence income.", econ=(("ess_mult", 0.5),)),
    T("tax_reform", "Tax Reform", "treasury", 1, 150, desc="+15% gold income.", econ=(("gold_mult", 0.15),)),
    T("trade_routes", "Trade Routes", "treasury", 2, 200, 20,
      desc="+0.5 iron and +0.3 essence per second.", econ=(("iron_flat", 0.5), ("ess_flat", 0.3))),
    T("harvest_feasts", "Harvest Feasts", "farm", 2, 120, desc="+1 morale for the whole army.", mods=(("all", "mor", 1),)),
    T("field_hospital", "Field Hospital", "longhouse", 3, 140, 10, desc="Wounded heal twice as fast at home.",
      econ=(("heal_mult", 1.0),)),
    T("chainmail", "Chainmail", "forge", 2, 150, 60, desc="+1 armour for melee troops.", mods=(("melee", "prot", 1),)),
    T("masterwork", "Masterwork Arms", "forge", 3, 220, 80, desc="+1 attack for the whole army.", mods=(("all", "att", 1),)),
    T("runed_steel", "Runed Steel", "forge", 4, 260, 90, 30, desc="+1 damage for the whole army.", mods=(("all", "dmg", 1),)),
    T("tactics", "Tactics", "academy", 1, 140, 0, 10, desc="+1 defence for the whole army.", mods=(("all", "def", 1),)),
    T("field_medicine", "Field Medicine", "academy", 1, 120, 0, 10,
      desc="After each battle, survivors recover 35% of their wounds.", econ=(("heal_after", 0.35),)),
    T("logistics", "Logistics", "academy", 2, 200, 30, 15, desc="+4 army cap.", econ=(("cap", 4),)),
    T("arcane_theory", "Arcane Theory", "academy", 2, 180, 0, 30, desc="+1 spell power for every caster.",
      mods=(("casters", "power", 1),)),
    T("war_college", "War College", "academy", 3, 300, 40, 30, desc="New recruits start as Regulars.",
      econ=(("start_xp", 10),)),
    T("murder_holes", "Murder Holes", "walls", 2, 120, 40, desc="Tower Archers: +2 damage, +6 arrows.",
      mods=(("u:tower", "dmg", 2), ("u:tower", "ammo", 6))),
    T("reinforced_gates", "Reinforced Gates", "walls", 3, 180, 80, desc="+1 maximum town strength.",
      econ=(("integrity", 1),)),
    T("sharpshooters", "Sharpshooters", "tower", 2, 110, 20, desc="Tower Archers: +2 attack.", mods=(("u:tower", "att", 2),)),
    T("rally_banner", "Rally Banner", "hall", 3, 160, 20, desc="Your Captain inspires more: +1 morale army-wide.",
      mods=(("all", "mor", 1),)),
    T("standing_army", "Standing Army", "hall", 5, 400, 80, 20, desc="+6 army cap.", econ=(("cap", 6),)),
    T("tempered_steel", "Tempered Steel", "barracks", 1, 110, 30, desc="Infantry: +1 damage.", mods=(("infantry", "dmg", 1),)),
    T("drill_sergeants", "Drill Sergeants", "barracks", 2, 140, 20, desc="Barracks recruits start as Regulars.",
      econ=(("xp_barracks", 10),)),
    T("tower_shields", "Tower Shields", "barracks", 3, 160, 60, desc="Shieldbearers +2 armour, Spearmen +1.",
      mods=(("u:shieldbearer", "prot", 2), ("u:spearman", "prot", 1))),
    T("bodkin_arrows", "Bodkin Arrows", "range", 1, 120, 20, desc="Bows and slings become armour-piercing.",
      mods=(("ranged", "ranged_ap", 1),)),
    T("deep_quivers", "Deep Quivers", "range", 2, 110, desc="Ranged troops: +4 ammunition.", mods=(("ranged", "ammo", 4),)),
    T("steady_aim", "Steady Aim", "range", 3, 180, desc="Ranged troops: +2 attack.", mods=(("ranged", "att", 2),)),
    T("barding", "Barding", "stables", 1, 140, 50, desc="Cavalry: +2 armour.", mods=(("cavalry", "prot", 2),)),
    T("lance_drills", "Lance Drills", "stables", 2, 160, 20, desc="Cavalry: +1 attack, +1 damage.",
      mods=(("cavalry", "att", 1), ("cavalry", "dmg", 1))),
    T("holy_water", "Holy Water", "temple", 1, 100, 0, 15, desc="Holy troops: +3 mana.", mods=(("holy", "mana", 3),)),
    T("martyrs_faith", "Martyrs' Faith", "temple", 2, 150, 0, 20, desc="+2 morale for the whole army.",
      mods=(("all", "mor", 2),)),
    T("consecration", "Consecration", "temple", 3, 200, 0, 30, desc="Holy troops and guardians: +1 power, +1 damage.",
      mods=(("holy", "power", 1), ("holy", "dmg", 1), ("holy_summon", "dmg", 1))),
    T("mana_font", "Mana Font", "arcanum", 1, 110, 0, 20, desc="Arcane casters: +3 mana.", mods=(("arcane", "mana", 3),)),
    T("focus_crystals", "Focus Crystals", "arcanum", 2, 180, 0, 35, desc="Arcane casters: +1 spell power.",
      mods=(("arcane", "power", 1),)),
    T("druidic_circle", "Druidic Circle", "grove", 1, 110, 0, 15, desc="Nature casters: +3 mana.", mods=(("nature", "mana", 3),)),
    T("wild_growth", "Wild Growth", "grove", 2, 160, 0, 25, desc="Beasts and nature troops: +1 attack, +1 armour.",
      mods=(("beast", "att", 1), ("beast", "prot", 1), ("nature", "prot", 1))),
    T("binding_runes", "Binding Runes", "conjury", 1, 130, 0, 25, desc="Conjured creatures: +1 attack, +2 damage.",
      mods=(("conjured", "att", 1), ("conjured", "dmg", 2))),
    T("greater_bindings", "Greater Bindings", "conjury", 2, 200, 0, 40, desc="Every summoner may keep one more summon.",
      mods=(("casters", "summon_cap", 1),)),
    T("iron_bones", "Iron Bones", "crypt", 1, 130, 20, 20, desc="Your undead: +2 armour.",
      mods=(("necro", "prot", 2), ("u:skeleton,wraith", "prot", 2))),
    T("grave_lore", "Grave Lore", "crypt", 2, 180, 0, 35, desc="Necromancers: +4 mana, +1 spell power.",
      mods=(("necro", "mana", 4), ("necro", "power", 1))),
    T("beast_mastery", "Beast Mastery", "lodge", 1, 120, desc="Beasts: +1 attack, +1 damage.",
      mods=(("beast", "att", 1), ("beast", "dmg", 1))),
    T("thick_hides", "Thick Hides", "lodge", 2, 150, 20, desc="Beasts: +2 armour and +3 HP.",
      mods=(("beast", "prot", 2), ("beast", "hp", 3))),
    T("counterweights", "Counterweights", "workshop", 1, 140, 40, desc="Siege engines: +2 range.", mods=(("siege", "rng", 2),)),
    T("iron_shot", "Iron Shot", "workshop", 2, 180, 60, desc="Siege engines: +2 damage.", mods=(("siege", "dmg", 2),)),
    T("iron_fist", "Iron Fist", "monastery", 1, 120, desc="Monastery troops: +1 damage.", mods=(("monk", "dmg", 1),)),
    T("inner_calm", "Inner Calm", "monastery", 2, 150, desc="Monastery troops: +1 defence, +3 morale.",
      mods=(("monk", "def", 1), ("monk", "mor", 3))),
    T("blood_money", "Blood Money", "guild", 1, 150, desc="Mercenaries cost 20% less.", econ=(("merc_discount", 0.2),)),
    T("veteran_contracts", "Veteran Contracts", "guild", 2, 220, desc="Mercenaries arrive as Veterans.",
      econ=(("xp_guild", 30),)),
]
TECH_BY_KEY = {t.key: t for t in TECHS}


# --------------------------------------------------------------------------
# Buildings
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class BuildingType:
    key: str
    name: str
    gold: int
    iron: int
    essence: int
    time: float
    max_level: int
    desc: str
    color: tuple
    glyph: str
    category: str
    requires: tuple = ()


B = BuildingType
BUILDING_LIST = [
    B("hall", "Town Hall", 120, 30, 0, 25, 5, "Heart of the town. Each level: more gold, +2 army cap, more building plots.",
      (150, 116, 72), "banner", "core"),
    B("market", "Market", 60, 0, 0, 12, 4, "+1.2 gold per second per level.", (178, 136, 62), "coin", "economy"),
    B("mine", "Iron Mine", 50, 0, 0, 12, 4, "+0.7 iron per second per level.", (112, 118, 128), "pick", "economy"),
    B("well", "Mana Well", 70, 10, 0, 14, 4, "+0.4 essence per second per level. Essence fuels magic.",
      (70, 120, 150), "orb", "economy"),
    B("treasury", "Treasury", 150, 20, 0, 18, 3, "+10% gold income per level.", (190, 160, 70), "coin", "economy",
      (("building", "market", 2),)),
    B("farm", "Farmstead", 60, 0, 0, 10, 3, "+2 army cap per level. Faster healing at home.", (120, 140, 60),
      "wheat", "economy"),
    B("longhouse", "Longhouse", 50, 10, 0, 10, 5, "+4 army cap per level. Faster healing at home.",
      (128, 96, 70), "bed", "economy"),
    B("forge", "Forge", 90, 40, 0, 18, 4, "Arms the army. Lv1 +1 armour, Lv2 +1 damage, Lv4 +2 armour.",
      (140, 90, 60), "anvil", "economy", (("building", "mine", 1),)),
    B("academy", "Academy", 110, 20, 10, 20, 3, "Research tactics, medicine and logistics.", (110, 110, 150),
      "book", "economy", (("building", "hall", 2),)),
    B("walls", "Town Walls", 80, 40, 0, 18, 4, "Raid defenders gain +1 defence per level.", (120, 116, 110),
      "wall", "economy"),
    B("tower", "Watchtower", 60, 25, 0, 14, 4, "Each level adds a Tower Archer when raided.", (100, 100, 110),
      "tower", "economy"),
    B("barracks", "Barracks", 70, 15, 0, 15, 4, "Spearmen, Berserkers, Shieldbearers, Blademasters.",
      (132, 72, 60), "sword", "military"),
    B("range", "Archery Range", 70, 10, 0, 15, 3, "Archers, Crossbowmen, Rangers.", (90, 120, 70), "bow", "military"),
    B("stables", "Stables", 110, 40, 0, 22, 2, "Knights and Horse Archers.", (120, 100, 60), "lance", "military",
      (("building", "hall", 2), ("building", "barracks", 1))),
    B("lodge", "Beast Lodge", 70, 10, 0, 15, 4, "War Hounds, Falconers, War Bears, Griffins.", (120, 90, 50),
      "paw", "military"),
    B("workshop", "Siege Workshop", 100, 50, 0, 20, 3, "Ballistae, Catapults, Iron Golems.", (110, 96, 80),
      "ballista", "military", (("building", "forge", 1),)),
    B("monastery", "Monastery", 90, 10, 0, 16, 2, "Monks and Witch Hunters.", (150, 130, 100), "fist", "military",
      (("building", "temple", 1),)),
    B("guild", "Mercenary Guild", 120, 0, 0, 16, 3, "Sellswords, Assassins, Ogres. Gold only.", (150, 110, 60),
      "zwei", "military", (("building", "market", 2),)),
    B("temple", "Temple", 90, 20, 5, 18, 3, "Priests, Paladins, High Priestesses. Speeds healing.",
      (170, 164, 150), "cross", "magic", (("building", "hall", 2),)),
    B("arcanum", "Arcanum", 100, 30, 15, 20, 4, "Apprentices, Battle Mages, Storm Mages, Archmages.",
      (96, 90, 150), "orb", "magic", (("building", "hall", 2), ("building", "well", 1))),
    B("grove", "Druid Grove", 80, 10, 10, 16, 3, "Druids, Treants, Archdruids.", (70, 120, 70), "leaf", "magic",
      (("building", "hall", 2),)),
    B("conjury", "Summoning Circle", 100, 20, 20, 18, 3, "Conjurers, Elementalists, Geomancers.",
      (150, 80, 60), "rune", "magic", (("building", "hall", 2), ("building", "well", 1))),
    B("crypt", "Bone Crypt", 90, 20, 20, 18, 3, "Gravecallers, Death Knights, Liches.", (90, 80, 110),
      "skull", "magic", (("building", "hall", 2), ("building", "well", 1))),
]
BUILDINGS = {b.key: b for b in BUILDING_LIST}


def building_reqs(key, level):
    reqs = list(BUILDINGS[key].requires) if level == 1 else []
    if key == "hall":
        if level >= 4:
            reqs.append(("region", level - 2))
    elif level >= 2:
        reqs.append(("building", "hall", min(level, 5)))
    top_tier = max((u.tier for u in RECRUITABLE if u.building == key and u.req_level == level), default=0)
    if top_tier >= 4:
        reqs.append(("region", 2))
    return reqs


def building_cost(key, target_level):
    b = BUILDINGS[key]
    steps = target_level - 2 if key == "hall" else target_level - 1
    mult = 1 + 0.8 * steps
    return int(b.gold * mult), int(b.iron * mult), int(b.essence * mult + (5 * steps if b.category == "magic" else 0))


def building_time(key, target_level):
    b = BUILDINGS[key]
    steps = target_level - 2 if key == "hall" else target_level - 1
    return b.time * (1 + 0.5 * steps)


def units_of(building):
    return [u for u in RECRUITABLE if u.building == building]


def techs_of(building):
    return [t for t in TECHS if t.building == building]


# --------------------------------------------------------------------------
# Factions and the procedurally generated war map
# --------------------------------------------------------------------------
FACTIONS = {
    "Ironveil": {
        "color": C["red"], "ground": (72, 64, 48), "glyph": "helm", "boss": "warlord",
        "stronghold": ["Ironveil Hold", "Skullspire Keep", "The Iron Bastion"],
        "units": [("raider", 5), ("slinger", 3), ("warg", 2), ("ironguard", 2), ("shaman", 1),
                  ("hexer", 1), ("brute", 1.2), ("ogre", 0.6)],
        "pre": ["Ash", "Iron", "Grim", "Blood", "Rust", "Skull", "Black", "Gore"],
        "suf": ["fang", "tooth", "hold", "claw", "maw", "spike"],
        "place": ["Camp", "Outpost", "Stockade", "Warcamp", "Ford", "Pits"],
        "desc": ["Orc-blooded raiders and their war-wolves.", "A palisade bristling with spears.",
                 "Smoke rises from the forges of Ironveil."],
    },
    "Barrow": {
        "color": C["undead"], "ground": (58, 56, 66), "glyph": "skull", "boss": "barrowking",
        "stronghold": ["The Black Barrow", "Tomb of Kings", "The Hollow Throne"],
        "units": [("skeleton", 6), ("bone_archer", 3), ("ghoul", 3), ("wraith", 1.5),
                  ("necromancer", 1), ("grave_knight", 1), ("banshee", 0.7)],
        "pre": ["Grey", "Hollow", "Pale", "Whisper", "Crow", "Grave", "Mourn", "Dusk"],
        "suf": ["mere", "moor", "fen", "hill", "wood", "vale"],
        "place": ["Barrow", "Tombs", "Crypt", "Cairn", "Ossuary", "Graves"],
        "desc": ["Old graves that do not stay shut.", "The dead walk here at night.",
                 "Cold mist and colder hands."],
    },
    "Wildkin": {
        "color": C["wild"], "ground": (50, 70, 46), "glyph": "horns", "boss": "beastlord",
        "stronghold": ["Thornheart Lair", "The Antler Throne", "Wyldroot Hollow"],
        "units": [("beastman", 5), ("harpy", 2), ("giant_spider", 2), ("wild_shaman", 1),
                  ("brood_mother", 0.7), ("cave_bear", 1), ("troll", 0.8)],
        "pre": ["Thorn", "Moss", "Wolf", "Bramble", "Elk", "Briar", "Fern", "Root"],
        "suf": ["wood", "glen", "hollow", "dell", "brake", "tangle"],
        "place": ["Den", "Lair", "Grove", "Nest", "Warren", "Circle"],
        "desc": ["Beastmen hunt these woods.", "Webs hang thick between the trees.",
                 "Something big lives here."],
    },
    "Emberkin": {
        "color": C["ember"], "ground": (80, 58, 44), "glyph": "flame", "boss": "pyre_lord",
        "stronghold": ["Pyre Citadel", "The Burning Gate", "Cinderheart"],
        "units": [("cultist", 5), ("salamander", 2), ("flamecaller", 1.5), ("imp", 1.5),
                  ("ember_knight", 1.2), ("ember_priest", 0.8), ("fire_elemental", 0.5)],
        "pre": ["Cinder", "Ember", "Soot", "Char", "Flame", "Pyre", "Scorch", "Brand"],
        "suf": ["peak", "rock", "vent", "crag", "pit", "fall"],
        "place": ["Shrine", "Altar", "Temple", "Forge", "Pyre", "Sanctum"],
        "desc": ["The fire cult chants day and night.", "The ground here is warm to the touch.",
                 "Ash falls like snow."],
    },
}
REGION_NAMES = ["The Ashen Marches", "The Hollow Fens", "The Thornwilds", "The Cinder Steppe",
                "The Grey Reaches", "The Broken Crowns", "The Howling Deep", "The Sunken Vale",
                "The Last Frontier", "The Shattered Rim", "The Red Wastes", "The Sorrow Coast"]
SPECIALS = {
    "relic": "Ancient Relic: +1 spell power for your casters.",
    "armory": "Old Armory: +1 armour for your whole army.",
    "banner": "Fallen Banner: +2 morale for your whole army.",
    "mercs": "Mercenary Band: veteran mercenaries join your warband.",
    "vault": "Treasure Vault: a hoard of gold, iron and essence.",
    "shrine": "Warding Shrine: +1 maximum town strength.",
}

MAP_RECT = pygame.Rect(20, 72, 820, 678)
HOME_POS = (60, 339)
NAME_FIRST = ["Al", "Bran", "Cor", "Da", "El", "Fen", "Gar", "Hal", "Ivo", "Jor", "Kel", "Lor", "Mar",
              "Ned", "Os", "Per", "Quin", "Ros", "Sten", "Tor", "Ulf", "Vic", "Wil", "Yor", "Ash", "Bea",
              "Cyn", "Dag", "Eda", "Gwen", "Hild", "Isa", "Mae", "Ro", "Sig", "Thea"]
NAME_LAST = ["ric", "wen", "dan", "mir", "eth", "o", "as", "ard", "wyn", "ley", "ius", "gar", "ren",
             "el", "a", "ith", "ulf", "bert", "mund", "ora"]


def make_name(rng=random):
    return rng.choice(NAME_FIRST) + rng.choice(NAME_LAST)


def unit_power(t, rank=0, mods=None):
    """Rough fighting value of one unit, used for the odds estimate on the war map."""
    m = mods or {}
    hp = t.hp * (1 + 0.1 * rank) + m.get("hp", 0)
    prot = t.prot + m.get("prot", 0)
    df = t.defense + rank + m.get("def", 0)
    att = t.att + rank + m.get("att", 0)
    bonus = rank // 2 + m.get("dmg", 0)
    hits = sorted(((w.dmg + bonus) * (0.4 if "charge" in w.tags else 1) * (1.3 if "sweep" in w.tags else 1)
                   * (1.3 if w.reach > 1 else 1)
                   * (1.2 if {"ap", "an", "magic", "poison", "drain"} & set(w.tags) else 1)
                   for w in t.weapons if not w.rng), reverse=True)
    melee = sum(h * f for h, f in zip(hits, (1.0, 0.6, 0.4, 0.3)))
    ranged = max(((w.dmg + bonus) * 1.4 * (1.3 if "ap" in w.tags or "area" in w.tags else 1)
                  for w in t.weapons if w.rng and "thrown" not in w.tags), default=0)
    offense = max(melee, ranged + melee * 0.3)
    if t.spells:
        offense += (t.mana + m.get("mana", 0)) * 1.2 + 6 + 3 * m.get("power", 0)
    durability = hp * (1 + prot / 4) * (1.1 ** (df - 10))
    durability *= 0.75 + 0.025 * min(t.mor + rank, 20)
    if "flying" in t.tags:
        durability *= 1.1
        offense *= 1.15
    if "ethereal" in t.tags:
        durability *= 1.8
    if "regen" in t.tags:
        durability *= 1.2
    return (durability * max(offense, 2) * 1.08 ** (att - 10)) ** 0.7 / 12


MAX_GARRISON = 150


def pick_units(faction, budget, max_tier, rng, region=1):
    lift = {1: 1.0, 2: 1 + 0.3 * (region - 1), 3: 1 + 0.7 * (region - 1)}
    pool = [(k, w * lift[UNITS[k].tier] if UNITS[k].tier in lift else w)
            for k, w in FACTIONS[faction]["units"] if UNITS[k].tier <= max_tier]
    total = sum(w for _, w in pool)
    out, spent = [], 0
    while spent < budget and len(out) < MAX_GARRISON:
        r = rng.uniform(0, total)
        for k, w in pool:
            r -= w
            if r <= 0:
                break
        out.append(k)
        spent += UNITS[k].points
    return out


class Target:
    def __init__(self, idx, name, faction, desc, pos, prereq, comp, depth, xp=0, walls=0,
                 gold=0, income=0.0, iron_income=0.0, ess_income=0.0, special="", boss=False, final=False):
        self.idx, self.name, self.faction, self.desc, self.pos = idx, name, faction, desc, pos
        self.prereq, self.depth = prereq, depth
        self.xp, self.walls = xp, walls
        self.garrison = [Soldier(k, "enemy", max(0, xp + random.randint(0, 3))) for k in comp]
        self.cap = min(MAX_GARRISON + 20, int(len(comp) * 1.3) + 1)
        self.gold, self.income, self.iron_income, self.ess_income = gold, income, iron_income, ess_income
        self.special, self.boss, self.final = special, boss, final
        self.conquered = False

    def pool(self):
        return [k for k, w in FACTIONS[self.faction]["units"] for _ in range(int(w * 2) or 1)
                if UNITS[k].tier <= (3 if self.depth > 2 or self.boss else 2)]

    def new_recruit(self):
        return Soldier(random.choice(self.pool()), "enemy", max(0, self.xp + random.randint(0, 3)))

    def grouped(self):
        groups = {}
        for u in self.garrison:
            groups.setdefault(u.t.key, []).append(u)
        return groups

    def summary(self):
        return ", ".join(f"{len(v)} {UNITS[k].name}" for k, v in
                         sorted(self.grouped().items(), key=lambda kv: -len(kv[1])))

    def strength(self):
        base = sum(unit_power(u.t, u.rank) for u in self.garrison)
        return base * (1 + 0.08 * self.walls)

    def bonuses(self):
        rb = getattr(self, "region_bonus", 0)
        stats = region_stats(rb)
        stats["def"] = stats.get("def", 0) + self.walls
        stats["prot"] = stats.get("prot", 0) + self.walls // 2
        return {"enemy": stats}

    def reward_lines(self):
        lines = []
        if self.gold:
            lines.append(f"+{self.gold} gold")
        if self.income:
            lines.append(f"+{self.income:.1f} gold/s")
        if self.iron_income:
            lines.append(f"+{self.iron_income:.1f} iron/s")
        if self.ess_income:
            lines.append(f"+{self.ess_income:.1f} essence/s")
        if self.special:
            lines.append(SPECIALS[self.special])
        if self.boss:
            lines.append("Clears the region and opens the way deeper.")
        return lines


def region_stats(rb):
    """Deeper regions field better-equipped enemies."""
    if rb <= 0:
        return {}
    return {"att": 3 * rb, "def": 3 * rb, "prot": 2 * rb, "mor": 3 * rb, "dmg": 2 * rb}


def overflow_xp(comp, budget):
    spent = sum(UNITS[k].points for k in comp)
    return int(max(0, budget - spent) / max(1, spent) * 40)


def region_mult(number):
    return 1 + 1.6 * (number - 1)


class Region:
    def __init__(self, number, mode, difficulty, seed):
        rng = random.Random(seed)
        diff = DIFFICULTY[difficulty]
        self.number = number
        self.name = REGION_NAMES[(seed + number) % len(REGION_NAMES)] if number > 1 else REGION_NAMES[seed % 3]
        final = mode == "campaign" and number == 3
        factions = rng.sample(list(FACTIONS), 2)
        if final and "Ironveil" not in factions:
            factions[0] = "Ironveil"
        self.factions = factions
        boss_faction = "Ironveil" if final else rng.choice(factions)
        self.ground = mix(FACTIONS[factions[0]]["ground"], FACTIONS[factions[1]]["ground"], 0.4)
        mult = region_mult(number) * diff["size"]
        xp_base = (number - 1) * 15 + diff["xp"]
        ncols = min(4 + number, 7)
        xs = [170 + (740 - 170) * i / ncols for i in range(ncols + 1)]
        self.targets = []
        prev = []
        for c in range(ncols):
            count = rng.choice([1, 2]) if c == 0 else rng.choice([2, 2, 3, 3])
            col = []
            for j in range(count):
                y = 100 + (j + 0.5) * (480 / count) + rng.uniform(-30, 30)
                faction = factions[0] if y < 339 else factions[1]
                if rng.random() < 0.25:
                    faction = rng.choice(factions)
                depth = c + 1
                budget = (4 + depth * 4) * mult + 10 * (number - 1)
                max_tier = 2 if (number == 1 and depth <= 2) else 3
                comp = pick_units(faction, budget, max_tier, rng, number)
                extra_xp = overflow_xp(comp, budget)
                walls = min(3, 1 + number // 2) if depth >= 4 and rng.random() < 0.35 else 0
                gold = int(40 + budget * 6)
                income = iron = ess = 0.0
                special = ""
                roll = rng.random()
                scale = 1 + 0.3 * (number - 1)
                if roll < 0.3:
                    income = round((0.2 + 0.05 * depth) * scale, 1)
                elif roll < 0.5:
                    iron = round((0.15 + 0.03 * depth) * scale, 1)
                elif roll < 0.68:
                    ess = round((0.1 + 0.03 * depth) * scale, 1)
                elif roll < 0.84:
                    special = rng.choice(list(SPECIALS))
                else:
                    gold = int(gold * 1.6)
                f = FACTIONS[faction]
                name = f"{rng.choice(f['pre'])}{rng.choice(f['suf'])} {rng.choice(f['place'])}"
                desc = rng.choice(f["desc"]) + (f" Walls: +{walls} defence." if walls else "")
                t = Target(len(self.targets), name, faction, desc, (xs[c], y), [], comp, depth,
                           xp=max(0, (depth - 1) * 2 + xp_base + extra_xp), walls=walls, gold=gold, income=income,
                           iron_income=iron, ess_income=ess, special=special)
                self.targets.append(t)
                col.append(t)
            if prev:
                for t in col:
                    near = sorted(prev, key=lambda p: abs(p.pos[1] - t.pos[1]))
                    t.prereq = [near[0].idx] + ([near[1].idx] if len(near) > 1 and rng.random() < 0.35 else [])
                for p in prev:
                    if not any(p.idx in t.prereq for t in col):
                        min(col, key=lambda t: abs(p.pos[1] - t.pos[1])).prereq.append(p.idx)
            prev = col
        budget = (4 + (ncols + 1) * 4) * mult * 1.8
        comp = [FACTIONS[boss_faction]["boss"]] + pick_units(boss_faction, budget, 3, rng, number)
        extra_xp = overflow_xp(comp[1:], budget)
        f = FACTIONS[boss_faction]
        walls = min(2 + number, 6)
        boss = Target(len(self.targets), rng.choice(f["stronghold"]), boss_faction,
                      f"The stronghold of this region. Walls: +{walls} defence, +{walls // 2} armour."
                      + (" Take it to win the war!" if final else " Take it to push deeper into the Rim."),
                      (min(xs[-1] + 10, 735), 339), [p.idx for p in prev], comp, ncols + 1,
                      xp=max(0, ncols * 2 + 6 + xp_base + extra_xp), walls=walls, gold=250 * number,
                      income=round(0.8 * number, 1), boss=True, final=final)
        self.targets.append(boss)
        self.boss = boss
        for t in self.targets:
            t.region_bonus = number - 1

        nodes = [HOME_POS] + [t.pos for t in self.targets]
        self.decor = []
        tries = 0
        while len(self.decor) < 75 and tries < 3000:
            tries += 1
            x, y = rng.uniform(15, MAP_RECT.w - 15), rng.uniform(15, MAP_RECT.h - 15)
            if any(abs(x - nx) < 70 and -60 < y - ny < 70 for nx, ny in nodes):
                continue
            kind = "mount" if y < 70 or y > 610 or rng.random() < 0.25 else rng.choice(["forest", "forest", "hill"])
            if "Barrow" in factions and rng.random() < 0.15:
                kind = "grave"
            if "Emberkin" in factions and rng.random() < 0.15:
                kind = "lava"
            self.decor.append((kind, x, y, rng.uniform(0.7, 1.3)))
        self.decor.sort(key=lambda d: d[2])
        rx = rng.uniform(250, 600)
        self.river = [(rx + rng.uniform(-40, 40), y) for y in range(0, MAP_RECT.h + 1, 113)]

    def boss_needs(self):
        """How many more sites must fall before the stronghold can be attacked."""
        others = [t for t in self.targets if not t.boss]
        need = math.ceil(len(others) * 0.6)
        return max(0, need - sum(t.conquered for t in others))

    def open_targets(self):
        locked = self.boss_needs() > 0
        return [t for t in self.targets if not t.conquered and not (t.boss and locked)
                and (not t.prereq or any(self.targets[i].conquered for i in t.prereq))]


# --------------------------------------------------------------------------
# Soldiers
# --------------------------------------------------------------------------
class Soldier:
    _ids = itertools.count(1)

    def __init__(self, key, team, xp=0, named=None):
        self._rxp, self._rank = -1, 0
        self.t = UNITS[key]
        self.team = team
        self.xp = xp
        self.bonus_hp = 0
        self.hp = self.max_hp
        self.heal_acc = 0.0
        self.uid = next(Soldier._ids)
        self.summoned = False
        if named is None:
            named = team == "player" and self.t.faction == "player" and "static" not in self.t.tags
        self.name = make_name() if named else ""
        self.kills_total = 0
        self.battles = 0
        self.reset_for_battle()

    @property
    def rank(self):
        if self._rxp != self.xp:
            r = 0
            for i, (threshold, _) in enumerate(RANKS):
                if self.xp >= threshold:
                    r = i
            self._rxp, self._rank = self.xp, r
        return self._rank

    @property
    def rank_name(self):
        return RANKS[self.rank][1]

    @property
    def label(self):
        return f"{self.name} ({self.t.name})" if self.name else self.t.name

    @property
    def max_hp(self):
        return self.t.hp + self.rank * max(1, round(self.t.hp * 0.1)) + self.bonus_hp

    @property
    def att(self):
        return self.t.att + self.rank + self.b_att

    @property
    def defense(self):
        return self.t.defense + self.rank + self.b_def

    @property
    def prot(self):
        return max(0, self.t.prot + self.b_prot)

    @property
    def mor(self):
        return self.t.mor + self.rank + self.b_mor

    @property
    def power(self):
        return self.rank // 2 + self.b_power

    @property
    def frenzied(self):
        return "frenzy" in self.t.tags and self.hp * 2 < self.max_hp

    @property
    def dmg_bonus(self):
        return self.rank // 2 + self.b_dmg + (3 if self.frenzied else 0)

    @property
    def move(self):
        return self.t.move * (2 if self.hasted else 1)

    @property
    def pos(self):
        return (self.gx, self.gy)

    @property
    def value(self):
        return self.t.tier * 10 + self.rank * 8

    def apply_mods(self, mods):
        for stat, val in mods.items():
            if stat == "ammo":
                self.ammo = [a + val if w.rng and "thrown" not in w.tags else a
                             for a, w in zip(self.ammo, self.t.weapons)]
            elif stat == "mana":
                if self.t.mana:
                    self.max_mana += val
                    self.mana += val
            elif stat == "hp":
                pass
            else:
                setattr(self, "b_" + stat, getattr(self, "b_" + stat) + val)

    def reset_for_battle(self):
        self.state = "fight"          # fight / rout / fled / dead
        self.ammo = [w.ammo for w in self.t.weapons]
        self.max_mana = self.t.mana
        self.mana = self.t.mana
        self.reload = 0
        self.slowed = 0
        self.poison = 0
        self.poisoner = None
        self.b_att = self.b_def = self.b_dmg = self.b_prot = self.b_power = self.b_mor = 0
        self.b_rng = self.b_ranged_ap = self.b_summon_cap = 0
        self.blessed = self.cursed = self.raised = self.hasted = self.stoned = False
        self.summons = {}
        self.start_rank = self.rank
        self.start_xp = self.xp
        self.gx = self.gy = 0
        self.prev = (0, 0)
        self.disp_hp = self.hp
        self.disp_dead = False
        self.hidden = False
        self.flash = 0.0
        self.stats = {"dmg": 0, "taken": 0, "kills": 0, "hits": 0, "spells": 0, "healed": 0}


# --------------------------------------------------------------------------
# Drawing helpers
# --------------------------------------------------------------------------
def draw_glyph(surf, glyph, c, s, col):
    x, y = c
    L = pygame.draw.line
    P = pygame.draw.polygon
    O = pygame.draw.circle
    ink = C["ink"]
    if glyph == "sword":
        L(surf, col, (x - s * .45, y + s * .45), (x + s * .45, y - s * .45), 3)
        L(surf, col, (x - s * .35, y - s * .05), (x + s * .05, y + s * .35), 2)
    elif glyph == "gsword":
        L(surf, col, (x - s * .5, y + s * .5), (x + s * .5, y - s * .5), 4)
        L(surf, col, (x - s * .45, y - s * .05), (x + s * .05, y + s * .45), 3)
        O(surf, col, (x - s * .5, y + s * .5), s * .1)
    elif glyph == "zwei":
        L(surf, col, (x, y + s * .6), (x, y - s * .6), 4)
        L(surf, col, (x - s * .4, y + s * .2), (x + s * .4, y + s * .2), 3)
        L(surf, col, (x - s * .15, y), (x + s * .15, y), 2)
    elif glyph == "daggers":
        L(surf, col, (x - s * .45, y + s * .45), (x + s * .2, y - s * .5), 2)
        L(surf, col, (x + s * .45, y + s * .45), (x - s * .2, y - s * .5), 2)
        L(surf, col, (x - s * .4, y + s * .15), (x - s * .05, y + s * .25), 2)
        L(surf, col, (x + s * .4, y + s * .15), (x + s * .05, y + s * .25), 2)
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
    elif glyph == "hood":
        P(surf, col, [(x - s * .45, y + s * .5), (x - s * .35, y - s * .15), (x, y - s * .55),
                      (x + s * .35, y - s * .15), (x + s * .45, y + s * .5)])
        O(surf, ink, (x, y + s * .05), s * .22)
    elif glyph in ("xbow", "hunter"):
        L(surf, col, (x - s * .5, y - s * .1), (x + s * .5, y - s * .1), 3)
        L(surf, col, (x, y - s * .1), (x, y + s * .55), 3)
        pygame.draw.arc(surf, col, (x - s * .5, y - s * .45, s, s * .6), 0.2, 2.94, 2)
        if glyph == "hunter":
            P(surf, col, [(x - s * .35, y - s * .45), (x + s * .35, y - s * .45), (x, y - s * .7)])
    elif glyph == "lance":
        L(surf, col, (x - s * .55, y + s * .55), (x + s * .5, y - s * .5), 3)
        P(surf, col, [(x - s * .1, y + s * .05), (x + s * .15, y - s * .2), (x - s * .35, y - s * .2)])
    elif glyph == "cross":
        L(surf, col, (x, y - s * .55), (x, y + s * .55), 3)
        L(surf, col, (x - s * .35, y - s * .15), (x + s * .35, y - s * .15), 3)
    elif glyph in ("shield", "pshield"):
        P(surf, col, [(x - s * .45, y - s * .5), (x + s * .45, y - s * .5), (x + s * .45, y), (x, y + s * .55),
                      (x - s * .45, y)], 0 if glyph == "shield" else 2)
        if glyph == "pshield":
            L(surf, col, (x, y - s * .35), (x, y + s * .3), 2)
            L(surf, col, (x - s * .25, y - s * .12), (x + s * .25, y - s * .12), 2)
        else:
            L(surf, ink, (x, y - s * .4), (x, y + s * .4), 2)
    elif glyph == "banner":
        L(surf, col, (x - s * .35, y + s * .55), (x - s * .35, y - s * .55), 2)
        P(surf, col, [(x - s * .35, y - s * .55), (x + s * .5, y - s * .35), (x - s * .35, y - s * .1)])
    elif glyph == "axe":
        L(surf, col, (x - s * .3, y + s * .55), (x + s * .2, y - s * .5), 2)
        P(surf, col, [(x + s * .1, y - s * .3), (x + s * .55, y - s * .45), (x + s * .45, y)])
    elif glyph == "club":
        L(surf, col, (x - s * .4, y + s * .5), (x + s * .2, y - s * .2), 4)
        O(surf, col, (x + s * .25, y - s * .25), s * .28)
    elif glyph == "sling":
        pygame.draw.arc(surf, col, (x - s * .5, y - s * .5, s, s), 3.4, 6.0, 2)
        O(surf, col, (x + s * .1, y + s * .3), s * .18)
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
        L(surf, ink, (x - s * .3, y), (x + s * .3, y), 3)
    elif glyph in ("tower", "wall"):
        w = .35 if glyph == "tower" else .55
        pygame.draw.rect(surf, col, (x - s * w, y - s * .25, s * w * 2, s * .8))
        n = 3 if glyph == "tower" else 4
        for i in range(n):
            pygame.draw.rect(surf, col, (x - s * w + i * s * w * 2 / (n - 0.5), y - s * .5, s * .15, s * .25))
    elif glyph in ("orb", "sun"):
        O(surf, col, (x, y), s * (.25 if glyph == "orb" else .3))
        for a in range(8):
            ang = a * math.pi / 4
            r1, r2 = (.35, .55) if glyph == "orb" else (.4, .62)
            L(surf, col, (x + math.cos(ang) * s * r1, y + math.sin(ang) * s * r1),
              (x + math.cos(ang) * s * r2, y + math.sin(ang) * s * r2), 2)
    elif glyph == "meteor":
        O(surf, col, (x + s * .2, y + s * .2), s * .25)
        for d in (-.12, 0, .12):
            L(surf, col, (x + s * (.05 + d), y + s * (.05 - d)), (x - s * (.5 - d), y - s * (.5 + d)), 2)
    elif glyph in ("flame", "flame2"):
        P(surf, col, [(x, y - s * .6), (x + s * .4, y), (x + s * .25, y + s * .5), (x - s * .25, y + s * .5),
                      (x - s * .4, y), (x - s * .1, y - s * .15)])
        if glyph == "flame2":
            O(surf, ink, (x, y + s * .15), s * .15)
    elif glyph == "bolt":
        P(surf, col, [(x + s * .1, y - s * .6), (x - s * .35, y + s * .05), (x - s * .02, y + s * .05),
                      (x - s * .15, y + s * .6), (x + s * .35, y - s * .1), (x + s * .02, y - s * .1)])
    elif glyph == "leaf":
        P(surf, col, [(x, y - s * .6), (x + s * .35, y - s * .1), (x, y + s * .45), (x - s * .35, y - s * .1)])
        L(surf, ink, (x, y - s * .4), (x, y + s * .55), 2)
    elif glyph in ("tree", "oak"):
        pygame.draw.rect(surf, col, (x - s * .1, y, s * .2, s * .55))
        O(surf, col, (x, y - s * .15), s * .4)
        if glyph == "oak":
            O(surf, col, (x - s * .3, y + s * .05), s * .22)
            O(surf, col, (x + s * .3, y + s * .05), s * .22)
    elif glyph == "rune":
        pts = [(x + math.cos(-math.pi / 2 + i * 4 * math.pi / 5) * s * .55,
                y + math.sin(-math.pi / 2 + i * 4 * math.pi / 5) * s * .55) for i in range(5)]
        pygame.draw.lines(surf, col, True, pts, 2)
    elif glyph in ("rock", "golem"):
        P(surf, col, [(x - s * .5, y + s * .45), (x - s * .4, y - s * .2), (x - s * .05, y - s * .5),
                      (x + s * .4, y - s * .3), (x + s * .5, y + s * .45)])
        if glyph == "golem":
            pygame.draw.rect(surf, ink, (x - s * .25, y - s * .15, s * .15, s * .1))
            pygame.draw.rect(surf, ink, (x + s * .1, y - s * .15, s * .15, s * .1))
        else:
            L(surf, ink, (x - s * .1, y - s * .3), (x + s * .1, y + s * .3), 2)
    elif glyph == "sickle":
        pygame.draw.arc(surf, col, (x - s * .5, y - s * .55, s * .9, s * .9), 0.3, 3.0, 3)
        L(surf, col, (x - s * .05, y - s * .05), (x - s * .3, y + s * .55), 3)
    elif glyph in ("skull", "dknight", "lich"):
        O(surf, col, (x, y - s * .1), s * .38)
        pygame.draw.rect(surf, col, (x - s * .2, y + s * .15, s * .4, s * .3))
        O(surf, ink, (x - s * .14, y - s * .1), s * .1)
        O(surf, ink, (x + s * .14, y - s * .1), s * .1)
        if glyph == "dknight":
            L(surf, col, (x + s * .45, y + s * .6), (x + s * .45, y - s * .6), 2)
        if glyph == "lich":
            P(surf, col, [(x - s * .35, y - s * .35), (x - s * .35, y - s * .7), (x - s * .12, y - s * .5),
                          (x, y - s * .75), (x + s * .12, y - s * .5), (x + s * .35, y - s * .7), (x + s * .35, y - s * .35)])
    elif glyph == "claw":
        for dx in (-.3, 0, .3):
            L(surf, col, (x + s * dx - s * .1, y + s * .5), (x + s * dx + s * .15, y - s * .5), 2)
    elif glyph == "ghost":
        P(surf, col, [(x - s * .4, y + s * .55), (x - s * .4, y - s * .1), (x, y - s * .55), (x + s * .4, y - s * .1),
                      (x + s * .4, y + s * .55), (x + s * .2, y + s * .35), (x, y + s * .55), (x - s * .2, y + s * .35)])
        O(surf, ink, (x - s * .14, y - s * .1), s * .08)
        O(surf, ink, (x + s * .14, y - s * .1), s * .08)
    elif glyph == "eye":
        pygame.draw.ellipse(surf, col, (x - s * .55, y - s * .3, s * 1.1, s * .6), 2)
        O(surf, col, (x, y), s * .18)
    elif glyph == "necro":
        L(surf, col, (x - s * .35, y + s * .55), (x - s * .35, y - s * .5), 2)
        O(surf, col, (x + s * .12, y - s * .1), s * .3)
        O(surf, ink, (x + s * .02, y - s * .12), s * .07)
        O(surf, ink, (x + s * .22, y - s * .12), s * .07)
    elif glyph == "bird":
        P(surf, col, [(x - s * .6, y - s * .1), (x - s * .1, y), (x, y - s * .15), (x + s * .1, y),
                      (x + s * .6, y - s * .1), (x + s * .1, y + s * .25), (x, y + s * .45), (x - s * .1, y + s * .25)])
    elif glyph == "wing":
        P(surf, col, [(x - s * .1, y + s * .5), (x - s * .55, y - s * .1), (x - s * .1, y - s * .55),
                      (x + s * .15, y - s * .2), (x + s * .55, y - s * .45), (x + s * .3, y + s * .2)])
    elif glyph == "paw":
        O(surf, col, (x, y + s * .15), s * .3)
        for dx, dy in ((-.35, -.25), (-.12, -.45), (.12, -.45), (.35, -.25)):
            O(surf, col, (x + s * dx, y + s * dy), s * .13)
    elif glyph == "horns":
        O(surf, col, (x, y + s * .1), s * .3)
        P(surf, col, [(x - s * .2, y - s * .1), (x - s * .6, y - s * .6), (x - s * .35, y - s * .05)])
        P(surf, col, [(x + s * .2, y - s * .1), (x + s * .6, y - s * .6), (x + s * .35, y - s * .05)])
    elif glyph == "spider":
        O(surf, col, (x, y), s * .25)
        for sgn in (-1, 1):
            for dy in (-.3, -.1, .1, .3):
                L(surf, col, (x, y), (x + sgn * s * .6, y + s * dy - s * .1), 2)
    elif glyph == "fist":
        pygame.draw.rect(surf, col, (x - s * .35, y - s * .3, s * .7, s * .6), border_radius=int(s * .15))
        for i in range(3):
            L(surf, ink, (x - s * .15 + i * s * .15, y - s * .3), (x - s * .15 + i * s * .15, y), 1)
    elif glyph == "ballista":
        L(surf, col, (x - s * .55, y), (x + s * .55, y), 3)
        pygame.draw.arc(surf, col, (x - s * .45, y - s * .5, s * .9, s * .8), 0.3, 2.84, 2)
        O(surf, col, (x - s * .3, y + s * .4), s * .12)
        O(surf, col, (x + s * .3, y + s * .4), s * .12)
    elif glyph == "catapult":
        L(surf, col, (x - s * .5, y + s * .3), (x + s * .5, y + s * .3), 3)
        L(surf, col, (x - s * .2, y + s * .3), (x + s * .35, y - s * .45), 3)
        O(surf, col, (x + s * .4, y - s * .5), s * .15)
    elif glyph == "coin":
        O(surf, col, (x, y), s * .5, 2)
        O(surf, col, (x, y), s * .2)
    elif glyph == "pick":
        pygame.draw.arc(surf, col, (x - s * .55, y - s * .55, s * 1.1, s * .8), 0.3, 2.84, 3)
        L(surf, col, (x, y - s * .55), (x, y + s * .55), 3)
    elif glyph == "bed":
        P(surf, col, [(x - s * .55, y), (x, y - s * .5), (x + s * .55, y)], 2)
        pygame.draw.rect(surf, col, (x - s * .4, y, s * .8, s * .45), 2)
    elif glyph == "anvil":
        P(surf, col, [(x - s * .55, y - s * .3), (x + s * .5, y - s * .3), (x + s * .3, y), (x + s * .15, y),
                      (x + s * .25, y + s * .45), (x - s * .25, y + s * .45), (x - s * .15, y), (x - s * .3, y)])
    elif glyph == "wheat":
        L(surf, col, (x, y + s * .55), (x, y - s * .5), 2)
        for dy in (-.35, -.1, .15):
            L(surf, col, (x, y + s * dy), (x - s * .25, y + s * (dy - .2)), 2)
            L(surf, col, (x, y + s * dy), (x + s * .25, y + s * (dy - .2)), 2)
    elif glyph == "book":
        pygame.draw.rect(surf, col, (x - s * .45, y - s * .35, s * .9, s * .7), 2)
        L(surf, col, (x, y - s * .35), (x, y + s * .35), 2)


def draw_token(surf, t, team, center, hp_frac=1.0, flash=False, routed=False, radius=None,
               bar=True, rank=0, mana_frac=None, tier=False):
    r = radius or (20 if t.big else 16)
    team_col = C["blue"] if team == "player" else (t.tint or C["red"])
    if team == "player" and t.faction == "summon":
        team_col = mix(C["blue"], t.tint or C["blue"], 0.35)
    body = C["white"] if flash else team_col
    if routed:
        body = mix(body, (110, 110, 110), 0.6)
    x, y = center
    if r >= 12:
        pygame.draw.ellipse(surf, (0, 0, 0), (x - r, y + r - 5, r * 2, 10))
    pygame.draw.circle(surf, C["ink"], (x, y), r + 2)
    pygame.draw.circle(surf, body, (x, y), r)
    pygame.draw.circle(surf, mix(body, C["ink"], 0.35), (x, y), max(1, r - 3))
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
        pygame.draw.polygon(surf, RANK_COLORS[rank], [(px - 3, y + r - 1), (px, y + r + 3), (px + 3, y + r - 1)])
    if tier:
        tier_badge(surf, t.tier, (x - r - 2, y - r - 2))
    if routed:
        pygame.draw.line(surf, C["paper"], (x + r - 2, y - r), (x + r - 2, y - r - 16), 2)
        pygame.draw.rect(surf, C["white"], (x + r - 1, y - r - 16, 9, 6))


def tier_badge(surf, tier, pos, font="tinyb"):
    img = FONTS[font].render(f"T{tier}", True, C["ink"])
    r = img.get_rect(topleft=pos).inflate(6, 2)
    pygame.draw.rect(surf, TIER_COLORS[tier], r, border_radius=3)
    surf.blit(img, img.get_rect(center=r.center))
    return r


def rank_text(surf, rank, pos, font="smallb", right=False, center=False):
    return text(surf, RANKS[rank][1], pos, font, RANK_COLORS[rank], right=right, center=center)


def draw_glow(surf, pos, radius, color, alpha):
    size = int(radius * 2 + 4)
    if size <= 4:
        return
    g = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(g, (*color, max(0, min(255, int(alpha)))), (size // 2, size // 2), int(radius))
    surf.blit(g, (pos[0] - size // 2, pos[1] - size // 2))


def shade(surf, alpha=170):
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    s.fill((8, 9, 10, alpha))
    surf.blit(s, (0, 0))


def panel(surf, rect, border=None, radius=6):
    pygame.draw.rect(surf, C["panel"], rect, border_radius=radius)
    pygame.draw.rect(surf, border or C["edge"], rect, 1 if border is None else 2, border_radius=radius)


def cost_parts(surf, x, y, gold, iron=0, essence=0, font="small", have=None):
    for amount, key, suffix in ((gold, "gold", "g"), (iron, "iron", "i"), (essence, "essence", "e")):
        if amount:
            col = C[key]
            if have is not None and have.get(key, 0) < amount:
                col = C["red"]
            r = text(surf, f"{amount}{suffix}", (x, y), font, col)
            x = r.right + 6
    return x


class UI:
    """Tiny immediate-mode button system: widgets are re-registered every frame."""

    def __init__(self):
        self.buttons = []
        self.mouse = (0, 0)

    def reset(self, mouse):
        self.buttons = []
        self.mouse = mouse

    def button(self, surf, rect, label, cb, enabled=True, accent=False, font="bold", danger=False):
        rect = pygame.Rect(rect)
        hover = enabled and rect.collidepoint(self.mouse)
        if not enabled:
            bg, fg, edge = (38, 40, 44), C["dim"], (52, 54, 58)
        elif danger:
            bg, fg, edge = (140, 52, 44) if hover else (112, 42, 36), C["white"], C["red"]
        elif accent:
            bg, fg, edge = (132, 98, 40) if hover else (110, 80, 34), C["white"], C["gold"]
        else:
            bg, fg, edge = (66, 72, 80) if hover else (52, 57, 64), C["paper"], (90, 96, 104)
        pygame.draw.rect(surf, bg, rect, border_radius=4)
        pygame.draw.rect(surf, edge, rect, 1, border_radius=4)
        text(surf, fit(label, font, rect.w - 8), rect.center, font, fg, center=True)
        if enabled:
            self.buttons.append((rect, cb))
        return rect

    def tabs(self, surf, x, y, labels, current, cb, w=110, h=28, font="smallb"):
        for i, lab in enumerate(labels):
            r = pygame.Rect(x + i * (w + 4), y, w, h)
            on = lab == current
            hover = r.collidepoint(self.mouse)
            bg = (92, 72, 36) if on else ((62, 66, 72) if hover else (44, 48, 54))
            pygame.draw.rect(surf, bg, r, border_radius=4)
            pygame.draw.rect(surf, C["gold"] if on else (80, 84, 90), r, 1, border_radius=4)
            text(surf, fit(lab, font, w - 6), r.center, font, C["white"] if on else C["paper"], center=True)
            self.buttons.append((r, lambda l=lab: cb(l)))

    def click(self, pos):
        for rect, cb in reversed(self.buttons):
            if rect.collidepoint(pos):
                SOUND.play("click", 0.6)
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
XP_PER_BATTLE = 10
DIRS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
ROLE_ORDER = ["static", "support", "caster", "siege", "ranged", "front"]
ROLE_COLS = {"static": [0, 1], "support": [1, 2, 0], "caster": [2, 1, 3], "siege": [0, 1, 2],
             "ranged": [3, 2, 4], "front": [6, 5, 4, 7, 3]}


def configure_field(n_units):
    global COLS, ROWS, TILE, FIELD_X, FIELD_Y
    if n_units <= 70:
        COLS, ROWS, TILE = 22, 11, 54
    elif n_units <= 120:
        COLS, ROWS, TILE = 28, 14, 42
    else:
        COLS, ROWS, TILE = 34, 17, 35
    FIELD_X, FIELD_Y = (W - COLS * TILE) // 2, 62


def tile_center(gx, gy):
    return (FIELD_X + gx * TILE + TILE / 2, FIELD_Y + gy * TILE + TILE / 2)


def cheb(a, b):
    return max(abs(a.gx - b.gx), abs(a.gy - b.gy))


def other(team):
    return "enemy" if team == "player" else "player"


def unit_role(t):
    if "static" in t.tags:
        return "static"
    if "siege" in t.tags:
        return "siege"
    if "commander" in t.tags and not ("melee_caster" in t.tags or t.tier >= 4 and not t.spells):
        return "support"
    if t.spells and "melee_caster" not in t.tags:
        kinds = {SPELLS[s].kind for s in t.spells}
        return "support" if kinds & {"heal", "massheal", "summon", "entangle", "raise"} else "caster"
    if t.rng and "flying" not in t.tags:
        return "ranged"
    return "front"


class Battle:
    def __init__(self, kind, title, players, enemies, attacker, target=None, bonuses=None,
                 spoils=("", ""), mod_fn=None):
        configure_field(len(players) + len(enemies))
        self.kind, self.title, self.attacker, self.target = kind, title, attacker, target
        self.defender = other(attacker)
        self.spoils = spoils
        self.mod_fn = mod_fn
        self.max_rounds = MAX_ROUNDS + (10 if COLS > 22 else 0) + (10 if COLS > 28 else 0)
        self.units = players + enemies
        self.occ = {}
        self.version = 0
        self._cache = {}
        for u in self.units:
            u.reset_for_battle()
            if "static" not in u.t.tags:
                u.apply_mods((bonuses or {}).get(u.team, {}))
            if u.team == "player" and mod_fn:
                u.apply_mods(mod_fn(u.t))
            u.disp_hp = u.hp
        self.deploy(players, "player")
        self.deploy(enemies, "enemy")
        for u in self.units:
            u.prev = u.pos
        self.start = {"player": len(players), "enemy": len(enemies)}
        self.fighting = dict(self.start)
        self.had_commander = {team: self.commander_up(team) for team in ("player", "enemy")}
        self.morale_marks = {"player": set(), "enemy": set()}
        self.round = 0
        self.speed = SETTINGS["battle_speed"]
        self.paused = False
        self.timer = 1.6
        self.anim_t = 1.0
        self.shots, self.strikes, self.floaters, self.blasts = [], {}, [], []
        self.pending_sounds = []
        self.instant = False
        self.log = [(f"The armies deploy: {len(players)} against {len(enemies)}.", C["paper"])]
        self.round_notes, self.round_slain = [], []
        self.round_hits = self.round_heals = self.round_blocks = 0
        self.round_flags = set()
        self.result = None
        self.reason = ""
        self.promotions = []
        self.fallen = []
        self.weapon_dmg, self.spell_counts = {}, {}
        self.friendly = {"player": 0, "enemy": 0}
        self.poison_dmg = {"player": 0, "enemy": 0}
        self.finished = False
        self.report_tab = "Summary"
        self.ui = UI()
        self.continue_cb = None
        self.menu_cb = None

    # ---- setup -----------------------------------------------------------
    def deploy(self, units, team):
        order = sorted(range(ROWS), key=lambda r: (abs(r - ROWS // 2), r))
        shift = (COLS - 10) // 2 - 6
        ranked = sorted(units, key=lambda u: (ROLE_ORDER.index(unit_role(u.t)), u.t.mounted, -u.t.tier))
        for u in ranked:
            role = unit_role(u.t)
            cols = [c + (shift if role != "static" else 0) for c in ROLE_COLS[role]]
            spots = [(c, r) for c in cols for r in order] + \
                    [(c, r) for c in range(COLS // 2 - 1) for r in order]
            for c, r in spots:
                gx = c if team == "player" else COLS - 1 - c
                if (gx, r) not in self.occ:
                    u.gx, u.gy = gx, r
                    self.occ[(gx, r)] = u
                    break

    # ---- queries ---------------------------------------------------------
    def active(self, u):
        return u.state in ("fight", "rout")

    def active_of(self, team):
        c = self._cache.get(team)
        if c and c[0] == self.version:
            return c[1]
        lst = [v for v in self.units if v.team == team and v.state in ("fight", "rout")]
        self._cache[team] = (self.version, lst)
        return lst

    def foes(self, u):
        return self.active_of(other(u.team))

    def allies(self, u):
        return [v for v in self.active_of(u.team) if v.state == "fight"]

    def adjacent_foes(self, u):
        out = []
        for dx, dy in DIRS:
            v = self.occ.get((u.gx + dx, u.gy + dy))
            if v is not None and v.team != u.team:
                out.append(v)
        return out

    def guarded(self, u):
        for dx, dy in DIRS:
            v = self.occ.get((u.gx + dx, u.gy + dy))
            if v is not None and v.team == u.team and v.state == "fight" and "guard" in v.t.tags:
                return True
        return False

    def lost_frac(self, team):
        return max(0.0, 1 - self.fighting[team] / max(1, self.start[team]))

    def commander_up(self, team):
        key = ("cmd", team)
        c = self._cache.get(key)
        if c and c[0] == self.version:
            return c[1]
        val = any(v.team == team and v.state == "fight" and "commander" in v.t.tags for v in self.units)
        self._cache[key] = (self.version, val)
        return val

    def side_name(self, team):
        return "your" if team == "player" else "enemy"

    def set_state(self, u, state):
        old = u.state
        if old == state:
            return
        if old == "fight":
            self.fighting[u.team] -= 1
        if state == "fight":
            self.fighting[u.team] += 1
        u.state = state
        if state in ("dead", "fled"):
            if self.occ.get(u.pos) is u:
                del self.occ[u.pos]
            self.version += 1

    def move_to(self, u, pos):
        if self.occ.get(u.pos) is u:
            del self.occ[u.pos]
        u.gx, u.gy = pos
        self.occ[pos] = u

    def free(self, p):
        return 0 <= p[0] < COLS and 0 <= p[1] < ROWS and p not in self.occ

    # ---- effects ---------------------------------------------------------
    def note(self, msg, color=None):
        self.round_notes.append((msg, color or C["paper"]))

    def schedule(self, u, label, color, action=None, delay=0.5, numeric=False):
        if self.instant:
            if action:
                action()
            return
        x, y = tile_center(u.gx, u.gy)
        self.floaters.append({"x": x + random.uniform(-7, 7), "y": y - TILE * 0.4, "label": label,
                              "color": color, "delay": ROUND_TIME * delay, "age": 0.0,
                              "action": action, "numeric": numeric})

    def shot(self, a, target_pos, style):
        self.shots.append((tile_center(a.gx, a.gy), tile_center(*target_pos), style))
        self.round_flags.add(style)

    def spawn(self, key, team, pos, caster=None):
        s = Soldier(key, team)
        s.summoned = True
        if team == "player" and self.mod_fn:
            mods = self.mod_fn(s.t)
            s.bonus_hp = mods.get("hp", 0)
            s.hp = s.max_hp
            s.apply_mods(mods)
        if caster is not None:
            s.b_att += caster.power // 2
            s.b_dmg += caster.power // 2
        s.disp_hp = s.hp
        s.gx, s.gy = pos
        s.prev = pos
        s.hidden = True
        self.occ[pos] = s
        self.units.append(s)
        self.fighting[team] += 1
        self.version += 1
        self.round_flags.add("summon")

        def show(v=s):
            v.hidden = False
        style = {"nature": C["nature"], "fire": C["fire"], "holy": C["holy"], "stone": C["stone"]}
        self.schedule(s, UNITS[key].name, style.get(UNITS[key].family, C["dark"]), show)
        return s

    def morale_check(self, u, extra=0):
        if u.state != "fight" or {"commander", "static", "undead", "mindless", "construct", "siege"} & set(u.t.tags):
            return
        if u.frenzied:
            return
        bonus = 2 if self.commander_up(u.team) else (-2 if self.had_commander[u.team] else 0)
        if u.mor + bonus + drn() < 7 + int(self.lost_frac(u.team) * 8) + extra + drn():
            self.set_state(u, "rout")
            self.schedule(u, "ROUT", C["white"])
            if u.team == "player":
                self.note(f"Your {u.t.name}{' ' + u.name if u.name else ''} flees!", C["gold"])
            elif u.t.tier >= 3:
                self.note(f"An enemy {u.t.name} flees!")

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
        if dealt:
            self.round_hits += 1
        else:
            self.round_blocks += 1
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

        self.schedule(d, str(dealt), color, act, numeric=True)
        if dead:
            self.set_state(d, "dead")
            if a is not None and a.team != d.team:
                a.xp += 3
                a.stats["kills"] += 1
                a.kills_total += 1
            self.round_slain.append(f"{self.side_name(d.team)} {d.t.name}" + (" (poison)" if source == "Poison" else ""))
            if d.team == "player" and not d.summoned and "static" not in d.t.tags:
                self.fallen.append(d)
                if d.rank >= 2 or d.t.tier >= 3:
                    self.note(f"{d.name or 'Your'} the {d.rank_name} {d.t.name} (T{d.t.tier}) has fallen!",
                              RANK_COLORS[d.rank])
                    self.schedule(d, "FALLEN", RANK_COLORS[d.rank], delay=0.7)
            elif d.team == "enemy" and d.t.tier >= 4:
                self.note(f"The enemy {d.t.name} is slain!", C["gold"])
            if stray and a is not None and a.team == d.team:
                self.note(f"A stray shot killed one of {'your' if a.team == 'player' else 'their'} own!")
        elif d.hp * 2 < d.max_hp:
            self.morale_check(d)
        return dealt

    def on_hit(self, a, d, w, dealt):
        if d.state == "dead" or dealt <= 0:
            return
        if "stun" in w.tags and random.randint(1, 100) <= w.chance and "static" not in d.t.tags:
            d.slowed = max(d.slowed, 1)
            self.schedule(d, "stunned", C["holy"], delay=0.6)
        if "poison" in w.tags and not ({"undead", "plant", "construct"} & set(d.t.tags)):
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
        harass = max(0, len(self.adjacent_foes(d)) - 1)
        defense = d.defense - harass - (4 if d.state == "rout" else 0) + (2 if self.guarded(d) else 0)
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
                self.note(f"{'Your' if d.team == 'player' else 'Enemy'} {d.t.name} breaks a {a.t.name}'s charge!")
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
                others = [f for f in self.adjacent_foes(a) if f is not target]
                if others:
                    self.strike(a, random.choice(others), w)

    def area(self, center, radius=1):
        cx, cy = center
        return [self.occ[(cx + dx, cy + dy)] for dx in range(-radius, radius + 1)
                for dy in range(-radius, radius + 1) if (cx + dx, cy + dy) in self.occ]

    def shoot(self, a, d, idx):
        w = a.t.weapons[idx]
        a.ammo[idx] -= 1
        dist = cheb(a, d)
        ap = "ap" in w.tags or (a.b_ranged_ap and "thrown" not in w.tags)
        kw = dict(ap=ap, an="an" in w.tags, magic="magic" in w.tags, source=w.name)
        style = "fire" if "magic" in w.tags else ("boulder" if "area" in w.tags else "arrow")
        hit = a.att + w.att + drn() - dist // 3 > 6 + d.defense // 3 + drn()
        if "area" in w.tags:
            center = d.pos if hit else (d.gx + random.randint(-2, 2), d.gy + random.randint(-2, 2))
            self.shot(a, center, style)
            self.blasts.append((tile_center(*center), TILE * 1.5, C["stone"]))
            for v in self.area(center):
                self.damage(a, v, w.dmg + a.dmg_bonus, stray=v.team == a.team, **kw)
            return
        if hit:
            self.shot(a, d.pos, style)
            a.stats["hits"] += 1
            self.on_hit(a, d, w, self.damage(a, d, w.dmg + a.dmg_bonus, **kw))
            return
        tx, ty = d.gx + random.randint(-1, 1), d.gy + random.randint(-1, 1)
        self.shot(a, (tx, ty), style)
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
                k = (u.team, sp.name)
                self.spell_counts[k] = self.spell_counts.get(k, 0) + 1
                self.round_flags.add(sp.style)
                return True
        return False

    def pick_target(self, u, rng, prefer=None, min_rng=0):
        ux, uy = u.gx, u.gy
        foes = []
        for f in self.foes(u):
            d = abs(f.gx - ux)
            dy = abs(f.gy - uy)
            if dy > d:
                d = dy
            if min_rng <= d <= rng:
                foes.append((d, f))
        if prefer:
            preferred = [df for df in foes if prefer(df[1])]
            foes = preferred or foes
        fighting = [df for df in foes if df[1].state == "fight"] or foes
        if not fighting:
            return None
        fighting.sort(key=lambda df: df[0])
        return random.choice(fighting[:4])[1]

    def sp_bolt(self, u, sp):
        d = self.pick_target(u, sp.rng, (lambda f: "undead" in f.t.tags) if sp.holy else None)
        if d is None:
            return False
        self.shot(u, d.pos, sp.style)
        if 10 + u.power + drn() > 5 + d.defense // 3 + drn():
            dealt = self.damage(u, d, sp.dmg + u.power, ap=sp.ap, an=sp.an, magic=True, holy=sp.holy,
                                source=sp.name)
            if sp.slow and dealt and d.state == "fight":
                d.slowed = max(d.slowed, sp.slow)
                self.schedule(d, "chilled", C["lightning"], delay=0.6)
        return True

    def best_area(self, u, rng, radius, ally_penalty, want):
        best, best_score = None, 0
        for f in self.foes(u):
            if cheb(u, f) > rng:
                continue
            score = 0
            for v in self.area(f.pos, radius):
                if v.team != u.team:
                    score += 1 if want(v) else 0
                else:
                    score -= ally_penalty
            if score > best_score:
                best, best_score = f.pos, score
        return best, best_score

    def sp_blast(self, u, sp):
        center, score = self.best_area(u, sp.rng, sp.area, 2, lambda v: True)
        need = 2 if len(self.foes(u)) > 3 else 1
        if sp.area > 1:
            need = 4 if len(self.foes(u)) > 8 else 1
        if center is None or score < need:
            return False
        self.shot(u, center, sp.style)
        self.blasts.append((tile_center(*center), TILE * (sp.area + 0.5), C[sp.style]))
        for v in self.area(center, sp.area):
            self.damage(u, v, sp.dmg + u.power, magic=True, source=sp.name, stray=v.team == u.team)
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
            self.damage(u, d, sp.dmg + u.power - 2 * (len(hit) - 1), ap=True, magic=True, source=sp.name)
            nxt = [f for f in self.foes(u) if f not in hit and self.active(f) and cheb(last, f) <= 2]
            d = min(nxt, key=lambda f: cheb(last, f)) if nxt else None
        self.round_flags.add("lightning")
        return True

    def sp_entangle(self, u, sp):
        center, score = self.best_area(u, sp.rng, 1, 0, lambda v: v.state == "fight" and not v.slowed
                                       and "flying" not in v.t.tags)
        if center is None or score < 2:
            return False
        self.shot(u, center, sp.style)
        self.blasts.append((tile_center(*center), TILE * 1.5, C["nature"]))
        for v in self.area(center):
            if v.team != u.team and v.state == "fight" and "flying" not in v.t.tags:
                v.slowed = sp.slow
                self.schedule(v, "rooted", C["nature"])
        return True

    def sp_summon(self, u, sp):
        foes = self.foes(u)
        if not foes or u.summons.get(sp.unit, 0) >= sp.limit + u.b_summon_cap:
            return False
        goal = min(foes, key=lambda f: cheb(u, f))
        spots = [(u.gx + dx, u.gy + dy) for dx in range(-2, 3) for dy in range(-2, 3)]
        spots = [p for p in spots if self.free(p)]
        if not spots:
            return False
        pos = min(spots, key=lambda p: math.hypot(p[0] - goal.gx, p[1] - goal.gy))
        u.summons[sp.unit] = u.summons.get(sp.unit, 0) + 1
        self.spawn(sp.unit, u.team, pos, caster=u)
        self.blasts.append((tile_center(*pos), TILE * 0.8, C[sp.style]))
        return True

    def heal_unit(self, u, a, amount):
        amount = min(amount, a.max_hp - a.hp)
        if amount <= 0:
            return 0
        a.hp += amount
        a.poison = 0
        self.round_heals += amount
        u.stats["healed"] += amount

        def act(v=a, hp=a.hp):
            v.disp_hp = hp
        self.schedule(a, f"+{amount}", C["green"], act, delay=0.3, numeric=True)
        return amount

    def sp_heal(self, u, sp):
        hurt = [a for a in self.allies(u) if a.max_hp - a.hp >= 3 and cheb(u, a) <= sp.rng]
        if not hurt:
            return False
        a = min(hurt, key=lambda v: v.hp / v.max_hp)
        self.heal_unit(u, a, sp.dmg + u.power + random.randint(0, 2))
        self.round_flags.add("heal")
        return True

    def sp_massheal(self, u, sp):
        hurt = [a for a in self.allies(u) if a.max_hp - a.hp >= 3 and cheb(u, a) <= sp.rng]
        if len(hurt) < 2:
            return False
        for a in hurt:
            self.heal_unit(u, a, sp.dmg + u.power)
        self.blasts.append((tile_center(u.gx, u.gy), TILE * (sp.rng + 0.5), C[sp.style]))
        self.round_flags.add("heal")
        return True

    def buff(self, u, sp, flag, label, apply, need=2):
        near = [a for a in self.allies(u) if cheb(u, a) <= sp.rng and not getattr(a, flag)
                and "static" not in a.t.tags and a is not u]
        if len(near) < need:
            return False
        for a in near:
            setattr(a, flag, True)
            apply(a)
            self.schedule(a, label, C[sp.style], delay=0.3)
        self.blasts.append((tile_center(u.gx, u.gy), TILE * (sp.rng + 0.5), C[sp.style]))
        return True

    def sp_bless(self, u, sp):
        def apply(a):
            a.b_att += 2
            a.b_def += 2
        return self.buff(u, sp, "blessed", "blessed", apply)

    def sp_haste(self, u, sp):
        return self.buff(u, sp, "hasted", "hasted", lambda a: None, need=3)

    def sp_stoneskin(self, u, sp):
        def apply(a):
            a.b_prot += 3
        return self.buff(u, sp, "stoned", "stoneskin", apply)

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

    def sp_wail(self, u, sp):
        living = [f for f in self.foes(u) if f.state == "fight" and cheb(u, f) <= sp.rng
                  and not ({"undead", "mindless", "construct", "commander"} & set(f.t.tags))]
        if len(living) < 3:
            return False
        self.blasts.append((tile_center(u.gx, u.gy), TILE * (sp.rng + 0.5), C["dark"]))
        for f in living:
            self.morale_check(f, extra=3)
        return True

    def sp_raise(self, u, sp):
        if u.summons.get(sp.unit, 0) >= 6 + u.b_summon_cap:
            return False
        corpses = [v for v in self.units if v.state == "dead" and not v.raised and self.free(v.pos)
                   and cheb(u, v) <= sp.rng and "static" not in v.t.tags and "construct" not in v.t.tags]
        if not corpses:
            return False
        v = min(corpses, key=lambda c: cheb(u, c))
        v.raised = True
        u.summons[sp.unit] = u.summons.get(sp.unit, 0) + 1

        def hide(c=v):
            c.hidden = True
        self.schedule(v, "", C["dark"], hide, delay=0.45)
        self.shot(u, v.pos, "dark")
        self.spawn(sp.unit, u.team, v.pos, caster=u)
        self.blasts.append((tile_center(*v.pos), TILE * 0.8, C["dark"]))
        return True

    # ---- movement ----------------------------------------------------------
    def step_toward(self, u, goal):
        best, best_key = None, (cheb(u, goal), math.hypot(u.gx - goal.gx, u.gy - goal.gy))
        for dx, dy in DIRS:
            p = (u.gx + dx, u.gy + dy)
            if not self.free(p):
                continue
            key = (max(abs(p[0] - goal.gx), abs(p[1] - goal.gy)), math.hypot(p[0] - goal.gx, p[1] - goal.gy))
            if key < best_key:
                best, best_key = p, key
        if best is None:
            return False
        self.move_to(u, best)
        return True

    def fly_toward(self, u, goal, stop_range):
        def key(p):
            d = max(abs(p[0] - goal.gx), abs(p[1] - goal.gy))
            return (0, stop_range - d) if d <= stop_range else (1, d)
        best, best_key = None, key(u.pos)
        r = u.move
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                p = (u.gx + dx, u.gy + dy)
                if (dx or dy) and self.free(p):
                    k = key(p)
                    if k < best_key:
                        best, best_key = p, k
        if best is None:
            return False
        self.move_to(u, best)
        return True

    def advance(self, u, foes, stop_range=1):
        if "stalker" in u.t.tags:
            soft = [f for f in foes if (f.t.spells or f.t.rng) and cheb(u, f) <= 12]
            if soft:
                foes = soft
        ux, uy = u.gx, u.gy
        goal, best = None, 1 << 30
        for f in foes:
            d = abs(f.gx - ux)
            dy = abs(f.gy - uy)
            if dy > d:
                d = dy
            if f.state == "rout":
                d += 3
            if d < best:
                goal, best = f, d
        if cheb(u, goal) <= stop_range:
            return False
        if "flying" in u.t.tags:
            return self.fly_toward(u, goal, stop_range)
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
                p = (u.gx + dx, u.gy + ddy)
                if self.free(p):
                    self.move_to(u, p)
                    break
        if u.gx == edge:
            self.set_state(u, "fled")

    def retreat(self, u, foes):
        for _ in range(u.move):
            here = min(cheb(u, f) for f in foes)
            best, best_d = None, here
            for dx, dy in DIRS:
                p = (u.gx + dx, u.gy + dy)
                if not self.free(p):
                    continue
                dd = min(max(abs(p[0] - f.gx), abs(p[1] - f.gy)) for f in foes)
                if dd > best_d:
                    best, best_d = p, dd
            if best is None:
                return
            self.move_to(u, best)

    def ranged_weapon(self, u, thrown=False):
        for i, w in enumerate(u.t.weapons):
            if w.rng and ("thrown" in w.tags) == thrown and u.ammo[i] > 0:
                return i, w
        return None, None

    # ---- one unit's turn ---------------------------------------------------
    def act(self, u):
        t = u.t
        if "regen" in t.tags and u.hp < u.max_hp:
            u.hp = min(u.max_hp, u.hp + 2)

            def act(v=u, hp=u.hp):
                v.disp_hp = hp
            self.schedule(u, "+2", C["green"], act, delay=0.2, numeric=True)
        if u.slowed > 0:
            u.slowed -= 1
            return
        foes = self.foes(u)
        if not foes:
            return
        adj = self.adjacent_foes(u)
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
                elif not any(SPELLS[s].kind in ("heal", "massheal") for s in t.spells):
                    self.advance(u, foes, stop_range=4)
                return

        idx, w = self.ranged_weapon(u)
        if w is not None:
            rng = w.rng + (u.b_rng if "siege" in t.tags else 0)
            min_rng = 3 if "area" in w.tags else 0
            if adj and "skirmish" in t.tags:
                self.retreat(u, foes)
                adj = self.adjacent_foes(u)
            if not adj:
                if u.reload > 0:
                    u.reload -= 1
                    return
                d = self.pick_target(u, rng, min_rng=min_rng)
                if d is not None:
                    self.shoot(u, d, idx)
                    if "reload" in w.tags:
                        u.reload = 1
                elif "static" not in t.tags:
                    self.advance(u, foes, stop_range=rng)
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
            d = self.pick_target(u, tw.rng, min_rng=2)
            if d is not None:
                self.shoot(u, d, ti)
                self.advance(u, foes)
                return
        moved = self.advance(u, foes)
        adj = self.adjacent_foes(u)
        if adj:
            self.melee(u, min(adj, key=lambda f: f.hp), moved=moved)

    def resolve_round(self):
        self.round += 1
        self.shots, self.strikes, self.blasts = [], {}, []
        self.round_hits = self.round_heals = self.round_blocks = 0
        self.round_slain, self.round_notes = [], []
        self.round_flags = set()
        for u in self.units:
            u.prev = u.pos
            if u.state == "fight" and u.t.regen:
                u.mana = min(u.max_mana, u.mana + u.t.regen)
        for u in list(self.units):
            if u.poison > 0 and self.active(u):
                dmg = 1 + u.poison // 3
                u.poison -= 1
                self.poison_dmg[u.team] += dmg
                src = u.poisoner if u.poisoner is not None and u.poisoner.team != u.team else None
                self.apply_damage(src, u, dmg, "Poison", C["nature"])
        for u in list(self.units):
            if u.state != "fight":
                continue
            if "aura_fire" in u.t.tags:
                for f in self.adjacent_foes(u):
                    self.damage(u, f, 4, ap=True, magic=True, source="Burning Aura")
                self.round_flags.add("fire")
            if "fear" in u.t.tags:
                for f in self.adjacent_foes(u):
                    self.morale_check(f, extra=2)
        for team in ("player", "enemy"):
            lost = self.lost_frac(team)
            for mark in (0.5, 0.75):
                if lost >= mark and mark not in self.morale_marks[team]:
                    self.morale_marks[team].add(mark)
                    self.note(("Your" if team == "player" else "The enemy") + " army wavers after heavy losses.",
                              C["gold"] if team == "player" else C["paper"])
                    for u in list(self.active_of(team)):
                        self.morale_check(u, extra=-2)
        order = list(self.active_of("player")) + list(self.active_of("enemy"))
        random.shuffle(order)
        order.sort(key=lambda u: -u.move)
        for u in order:
            if u.state == "rout":
                self.flee(u)
            elif u.state == "fight":
                self.act(u)

        line = f"Round {self.round}: {self.round_hits} wounds"
        if self.round_heals:
            line += f", {self.round_heals} healed"
        if self.round_slain:
            line += ". Slain: " + ", ".join(self.round_slain[:4]) + (
                f" and {len(self.round_slain) - 4} more" if len(self.round_slain) > 4 else "")
        self.log.append((line, C["paper"]))
        self.log.extend(self.round_notes[:4])
        if not self.instant:
            self.queue_sounds()

        def how(loser):
            fled = sum(1 for u in self.units if u.team == loser and u.state in ("fled", "rout"))
            dead = sum(1 for u in self.units if u.team == loser and u.state == "dead")
            who = "Your army" if loser == "player" else "The enemy"
            if not fled:
                return f"{who} was wiped out"
            return f"{who} broke and fled" if fled >= dead else f"{who} was cut down, the last few fleeing"
        if self.fighting["player"] <= 0:
            self.result, self.reason = "enemy", how("player")
        elif self.fighting["enemy"] <= 0:
            self.result, self.reason = "player", how("enemy")
        elif self.round >= self.max_rounds:
            self.result = self.defender
            self.reason = "Night fell and the attackers withdrew"
            self.log.append(("Night falls. The attackers withdraw.", C["gold"]))
        if self.result:
            self.conclude()

    def queue_sounds(self):
        f = self.round_flags
        now = []
        if "arrow" in f:
            now.append("arrow")
        if "boulder" in f:
            now.append("hit")
        if "fire" in f:
            now.append("fire")
        if "lightning" in f:
            now.append("lightning")
        if f & {"dark", "holy", "nature", "stone"}:
            now.append("magic")
        for i, s in enumerate(now):
            self.pending_sounds.append([0.1 + i * 0.06, s])
        if self.round_hits:
            self.pending_sounds.append([ROUND_TIME * 0.5, "hit"])
        elif self.round_blocks:
            self.pending_sounds.append([ROUND_TIME * 0.5, "block"])
        if self.round_slain:
            self.pending_sounds.append([ROUND_TIME * 0.6, "death"])
        if "summon" in f:
            self.pending_sounds.append([ROUND_TIME * 0.4, "summon"])
        if "heal" in f:
            self.pending_sounds.append([ROUND_TIME * 0.3, "heal"])

    def conclude(self):
        self.log.append(("Victory!", C["gold"]) if self.result == "player" else ("Your army is beaten.", C["red"]))
        for u in self.units:
            if u.summoned or "static" in u.t.tags:
                continue
            if u.state != "dead":
                u.xp += 2 + (2 if u.team == self.result else 0)
            cap = XP_PER_BATTLE if (self.kind == "attack") == (u.team == "player") else XP_PER_BATTLE // 2
            u.xp = min(u.xp, u.start_xp + cap)
            u.battles += 1
        self.promotions = [u for u in self.units if u.team == "player" and u.state != "dead"
                           and not u.summoned and u.rank > u.start_rank]
        if not self.instant:
            SOUND.play("victory" if self.result == "player" else "defeat")
            if self.promotions:
                self.pending_sounds.append([1.2, "promote"])

    def skip(self):
        for f in self.floaters:
            if f["action"] and f["delay"] > 0:
                f["action"]()
        self.floaters.clear()
        self.pending_sounds.clear()
        self.instant = True
        while not self.result:
            self.resolve_round()
        self.instant = False
        SOUND.play("victory" if self.result == "player" else "defeat")
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
        elif key == pygame.K_TAB and self.finished:
            tabs = ["Summary", "Casualties", "Honours"]
            self.report_tab = tabs[(tabs.index(self.report_tab) + 1) % 3]

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
        for s in self.pending_sounds:
            s[0] -= bdt
            if s[0] <= 0:
                SOUND.play(s[1], 0.7)
        self.pending_sounds = [s for s in self.pending_sounds if s[0] > 0]
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
        if "flying" in u.t.tags and (ax, ay) != (bx, by):
            y -= math.sin(p * math.pi) * TILE * 0.5
        tgt = self.strikes.get(u.uid)
        if tgt and 0.45 <= self.anim_t <= 0.8:
            k = math.sin((self.anim_t - 0.45) / 0.35 * math.pi) * TILE * 0.18
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
            arc = {"arrow": 30, "boulder": 70}.get(style, 12)
            x = start[0] + (end[0] - start[0]) * q
            y = start[1] + (end[1] - start[1]) * q - math.sin(q * math.pi) * arc
            if style == "arrow":
                dx, dy = end[0] - start[0], end[1] - start[1]
                d = math.hypot(dx, dy) or 1
                pygame.draw.line(surf, C["white"], (x - dx / d * 9, y - dy / d * 9), (x, y), 2)
            elif style == "boulder":
                pygame.draw.circle(surf, C["stone"], (x, y), 6)
                pygame.draw.circle(surf, C["ink"], (x, y), 6, 1)
            else:
                col = C.get(style, C["fire"])
                draw_glow(surf, (x, y), 10, col, 90)
                pygame.draw.circle(surf, mix(col, C["white"], 0.4), (x, y), 5)
        for pos, radius, col in self.blasts:
            q = (self.anim_t - 0.45) / 0.45
            if 0 <= q <= 1:
                draw_glow(surf, pos, radius * (0.5 + q * 0.5), col, 150 * (1 - q))

    def draw(self, surf, mouse, continue_cb, menu_cb=None):
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

        scale = TILE / 54
        cs = max(4, int(9 * scale))
        for u in self.units:
            if u.disp_dead and not u.hidden:
                x, y = tile_center(u.gx, u.gy)
                base = C["blue"] if u.team == "player" else (u.t.tint or C["red"])
                col = mix(base, C["field"], 0.6)
                pygame.draw.line(surf, col, (x - cs, y - cs), (x + cs, y + cs), 4)
                pygame.draw.line(surf, col, (x - cs, y + cs), (x + cs, y - cs), 4)

        hover = None
        for u in sorted(self.units, key=lambda v: (("flying" in v.t.tags), v.gy)):
            if u.disp_dead or u.hidden or (u.state == "fled" and self.anim_t >= 0.45):
                continue
            pos = self.unit_screen_pos(u)
            mana = u.mana / u.max_mana if u.max_mana else None
            r = max(9, int((20 if u.t.big else 16) * scale))
            draw_token(surf, u.t, u.team, pos, u.disp_hp / u.max_hp, u.flash > 0,
                       u.state in ("rout", "fled"), radius=r, rank=u.rank, mana_frac=mana)
            if u.slowed:
                pygame.draw.circle(surf, C["nature"], pos, r + 5, 2)
            if u.poison:
                pygame.draw.circle(surf, (120, 200, 60), (pos[0] - r, pos[1]), 3)
            if u.cursed:
                pygame.draw.circle(surf, C["dark"], (pos[0] - r, pos[1] + r * 0.7), 3)
            if u.blessed or u.stoned or u.hasted:
                col = C["holy"] if u.blessed else (C["stone"] if u.stoned else C["lightning"])
                pygame.draw.circle(surf, col, (pos[0] + r, pos[1] + r * 0.7), 3)
            if math.hypot(mouse[0] - pos[0], mouse[1] - pos[1]) < r + 2:
                hover = u

        self.draw_shots(surf)
        show_numbers = SETTINGS["damage_numbers"]
        for f in self.floaters:
            if f["delay"] <= 0 and f["label"] and (show_numbers or not f["numeric"]):
                a = f["age"]
                img = FONTS["bold" if TILE > 40 else "smallb"].render(f["label"], True, f["color"])
                img.set_alpha(int(255 * (1 - max(0, a - 0.5) * 2)))
                surf.blit(img, img.get_rect(center=(f["x"], f["y"] - a * 26)))

        pygame.draw.rect(surf, C["panel"], (0, 0, W, 56))
        pygame.draw.line(surf, C["edge"], (0, 56), (W, 56), 2)
        text(surf, fit(self.title, "title", 470), (16, 13), "title")
        for team, x, col, label in (("player", 500, C["blue"], "Yours"), ("enemy", 620, C["red"], "Foes")):
            routed = sum(1 for u in self.units if u.team == team and u.state in ("rout", "fled"))
            text(surf, f"{label} {self.fighting[team]}", (x, 10), "bold", col)
            text(surf, f"{routed} fleeing", (x, 30), "small", C["muted"])
        text(surf, f"Round {self.round}/{self.max_rounds}", (730, 19), "bold")
        bx = 850
        for sp in (1, 2, 4):
            self.ui.button(surf, (bx, 14, 40, 28), f"{sp}x", lambda s=sp: setattr(self, "speed", s),
                           accent=self.speed == sp)
            bx += 44
        self.ui.button(surf, (bx, 14, 66, 28), "Play" if self.paused else "Pause",
                       lambda: setattr(self, "paused", not self.paused), accent=self.paused)
        self.ui.button(surf, (bx + 70, 14, 56, 28), "Skip", self.skip, enabled=not self.result)
        if menu_cb:
            self.ui.button(surf, (bx + 130, 14, 90, 28), "Menu (Esc)", menu_cb)

        ly = FIELD_Y + ROWS * TILE + 6
        pygame.draw.rect(surf, C["panel"], (0, ly, W, H - ly))
        lines = self.log[-4:]
        for i, (line, col) in enumerate(lines):
            text(surf, fit(line, "small", 980), (20, ly + 4 + i * 18), "small",
                 col if (i == len(lines) - 1 or col != C["paper"]) else C["muted"])
        text(surf, "SPACE pause · 1/2/3 speed · S skip · hover for details", (W - 16, ly + 4), "tiny",
             C["dim"], right=True)
        if self.paused and not self.finished:
            text(surf, "PAUSED", (W // 2, FIELD_Y + 26), "title", C["gold"], center=True)
        if hover and not self.finished:
            self.draw_tooltip(surf, hover, mouse)
        if self.finished:
            self.draw_result(surf, continue_cb)

    def draw_tooltip(self, surf, u, mouse):
        t = u.t
        head = f"{u.name + ' — ' if u.name else ''}{t.name}  ({'yours' if u.team == 'player' else 'enemy'})"
        lines = [(head, "bold", C["paper"]),
                 (f"T{t.tier} · {u.rank_name} ({u.xp} xp)" + (" · summoned" if u.summoned else ""),
                  "smallb", RANK_COLORS[u.rank]),
                 (f"HP {u.disp_hp}/{u.max_hp}   Att {u.att}  Def {u.defense}  Prot {u.prot}  Mor {u.mor}"
                  f"  Move {u.move}" + (f"  Mana {u.mana}/{u.max_mana}" if u.max_mana else ""), "small", C["paper"])]
        for i, w in enumerate(t.weapons):
            extra = f"  ×{u.ammo[i]}" if w.rng else ""
            lines.append(("• " + w.describe() + extra, "small", C["paper"]))
        if t.spells:
            lines.append(("• Spells: " + ", ".join(SPELLS[s].name for s in t.spells), "small", C["mana"]))
        for tag in t.tags:
            if tag in TAG_TEXT and tag != "static":
                lines.append(("• " + TAG_TEXT[tag], "small", C["muted"]))
        status = [s for s, on in (("blessed", u.blessed), ("hexed", u.cursed), ("stunned/rooted", u.slowed),
                                  ("poisoned", u.poison), ("hasted", u.hasted), ("stoneskin", u.stoned),
                                  ("frenzied", u.frenzied)) if on]
        if u.state in ("rout", "fled"):
            status.insert(0, "FLEEING")
        if status:
            lines.append((", ".join(status), "smallb", C["gold"]))
        if u.stats["dmg"] or u.stats["kills"] or u.stats["healed"]:
            lines.append((f"This battle: {u.stats['kills']} kills, {u.stats['dmg']} damage"
                          + (f", {u.stats['healed']} healed" if u.stats["healed"] else ""), "small", C["muted"]))
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
            r = rows.setdefault((u.t.key, u.summoned), {"t": u.t, "summoned": u.summoned, "start": 0, "lost": 0,
                                                        "fled": 0, "kills": 0, "dmg": 0, "worst": -1})
            r["start"] += 1
            if u.state == "dead":
                r["lost"] += 1
                r["worst"] = max(r["worst"], u.rank)
            r["fled"] += u.state in ("fled", "rout")
            r["kills"] += u.stats["kills"]
            r["dmg"] += u.stats["dmg"]
        return sorted(rows.values(), key=lambda r: (r["summoned"], -r["t"].tier, -r["dmg"]))

    def draw_table(self, surf, team, x0, y, color, label, max_rows=12):
        text(surf, label, (x0, y), "head", color)
        cols = [("Start", 225), ("Lost", 270), ("Fled", 315), ("Kills", 360), ("Damage", 420)]
        y += 28
        for name, cx in cols:
            text(surf, name, (x0 + cx, y), "tiny", C["muted"], center=True)
        pygame.draw.line(surf, C["edge"], (x0, y + 9), (x0 + 450, y + 9))
        y += 13
        rows = self.team_rows(team)
        totals = {"start": 0, "lost": 0, "fled": 0, "kills": 0, "dmg": 0}
        for i, r in enumerate(rows):
            for k in totals:
                if not r["summoned"] or k in ("kills", "dmg"):
                    totals[k] += r[k]
            if i >= max_rows:
                continue
            draw_token(surf, r["t"], team, (x0 + 9, y + 9), radius=8, bar=False)
            name = r["t"].name + (" (summoned)" if r["summoned"] else "")
            text(surf, fit(name, "small", 150), (x0 + 22, y + 1), "small")
            tier_badge(surf, r["t"].tier, (x0 + 178, y + 3))
            vals = [r["start"], r["lost"], r["fled"], r["kills"], r["dmg"]]
            for (cname, cx), v in zip(cols, vals):
                col = C["paper"] if v else C["dim"]
                if cname == "Lost" and v:
                    col = RANK_COLORS[r["worst"]] if r["worst"] >= 1 else C["red"]
                elif cname == "Fled" and v:
                    col = C["gold"]
                text(surf, v, (x0 + cx, y + 9), "smallb" if cname == "Lost" and v else "small", col, center=True)
            y += 19
        if len(rows) > max_rows:
            text(surf, f"+{len(rows) - max_rows} more types", (x0 + 22, y + 1), "tiny", C["muted"])
            y += 15
        pygame.draw.line(surf, C["edge"], (x0, y + 1), (x0 + 450, y + 1))
        text(surf, "Total", (x0 + 22, y + 4), "bold")
        for (cname, cx), k in zip(cols, ["start", "lost", "fled", "kills", "dmg"]):
            text(surf, totals[k], (x0 + cx, y + 12), "bold", center=True)
        return y + 26

    def best_unit(self, team):
        pool = [u for u in self.units if u.team == team and (u.stats["dmg"] or u.stats["kills"] or u.stats["healed"])]
        if not pool:
            return "—"
        u = max(pool, key=lambda v: v.stats["kills"] * 10 + v.stats["dmg"] + v.stats["healed"])
        who = f"{u.name}, {u.rank_name} {u.t.name}" if u.name else f"{u.t.name} ({u.rank_name})"
        s = f"{who}: {u.stats['kills']} kills, {u.stats['dmg']} dmg"
        if u.stats["healed"]:
            s += f", {u.stats['healed']} healed"
        return s + (" (fell)" if u.state == "dead" else "")

    def top_attacks(self, team):
        items = sorted(((v, k[1]) for k, v in self.weapon_dmg.items() if k[0] == team and v), reverse=True)
        return ", ".join(f"{name} {v}" for v, name in items[:3]) or "—"

    def spells_text(self, team):
        items = sorted(((v, k[1]) for k, v in self.spell_counts.items() if k[0] == team), reverse=True)
        return ", ".join(f"{name} ×{v}" for v, name in items[:4]) or "none"

    def draw_result(self, surf, continue_cb):
        shade(surf, 190)
        won = self.result == "player"
        card = pygame.Rect(120, 16, 1040, 728)
        panel(surf, card, C["gold"] if won else C["red"])
        text(surf, "VICTORY" if won else "DEFEAT", (W // 2, 54), "big", C["gold"] if won else C["red"], center=True)
        text(surf, fit(f"{self.title}  ·  {self.reason} after {self.round} rounds.", "body", 980),
             (W // 2, 96), "body", C["muted"], center=True)
        self.ui.tabs(surf, card.x + 30, 114, ["Summary", "Casualties", "Honours"], self.report_tab,
                     lambda t: setattr(self, "report_tab", t), w=130)
        text(surf, "TAB switches pages", (card.right - 30, 121), "tiny", C["dim"], right=True)
        pygame.draw.line(surf, C["edge"], (card.x + 20, 148), (card.right - 20, 148))
        body = pygame.Rect(card.x + 30, 158, card.w - 60, card.h - 220)
        {"Summary": self.draw_summary, "Casualties": self.draw_casualties,
         "Honours": self.draw_honours}[self.report_tab](surf, body)
        y = card.bottom - 92
        pygame.draw.line(surf, C["edge"], (card.x + 20, y), (card.right - 20, y))
        outcome = self.spoils[0] if won else self.spoils[1]
        for i, line in enumerate(wrap(outcome, "bold", card.w - 60)[:2]):
            text(surf, line, (card.x + 30, y + 8 + i * 19), "bold", C["gold"] if won else C["red"])
        self.ui.button(surf, (W // 2 - 100, card.bottom - 46, 200, 36), "Continue (Enter)", continue_cb, accent=True)

    def draw_summary(self, surf, body):
        left, right = body.x, body.centerx + 20
        y1 = self.draw_table(surf, "player", left, body.y, C["blue"], "Your army")
        y2 = self.draw_table(surf, "enemy", right, body.y, C["red"], "The enemy")
        y = max(y1, y2) + 4
        pygame.draw.line(surf, C["edge"], (body.x - 10, y), (body.right + 10, y))
        y += 8
        heal = sum(u.stats["healed"] for u in self.units if u.team == "player")
        eheal = sum(u.stats["healed"] for u in self.units if u.team == "enemy")
        rows = [
            (("Hero of the day", self.best_unit("player")), ("Deadliest foe", self.best_unit("enemy"))),
            (("Best attacks", self.top_attacks("player")), ("Their attacks", self.top_attacks("enemy"))),
            (("Spells cast", self.spells_text("player")), ("Their spells", self.spells_text("enemy"))),
            (("Heal / poison", f"{heal} healed, {self.poison_dmg['enemy']} poison dealt"),
             ("Heal / poison", f"{eheal} healed, {self.poison_dmg['player']} poison dealt")),
        ]
        for (l1, v1), (l2, v2) in rows:
            for x, lab, val in ((left, l1, v1), (right, l2, v2)):
                text(surf, lab, (x, y), "smallb", C["gold"])
                text(surf, fit(val, "small", 350), (x + 110, y), "small")
            y += 20
        y += 4
        fallen = sorted(self.fallen, key=lambda u: -u.value)
        if fallen:
            u = fallen[0]
            text(surf, "Heaviest loss:", (left, y), "smallb", C["red"])
            r = text(surf, f"{u.name}, T{u.t.tier} {u.t.name}", (left + 110, y), "smallb")
            rank_text(surf, u.rank, (r.right + 8, y))
            vets = sum(1 for v in fallen if v.rank >= 2)
            text(surf, f"{len(fallen)} soldiers fell, {vets} of them Veteran or better. See Casualties.",
                 (right, y), "small", C["muted"])
        else:
            text(surf, "Not a single soldier of yours fell.", (left, y), "smallb", C["green"])

    def draw_casualties(self, surf, body):
        x0, y = body.x, body.y
        fallen = sorted(self.fallen, key=lambda u: -u.value)
        text(surf, f"Your fallen ({len(fallen)})", (x0, y), "head", C["blue"])
        y += 30
        heads = [("Soldier", 0), ("Tier", 250), ("Rank", 300), ("XP", 385), ("Kills", 430), ("Battles", 480)]
        for h, dx in heads:
            text(surf, h, (x0 + dx, y), "tiny", C["muted"])
        y += 16
        if not fallen:
            text(surf, "None. Every soldier came home.", (x0, y + 4), "body", C["green"])
        for i, u in enumerate(fallen[:21]):
            yy = y + i * 21
            if i % 2 == 0:
                pygame.draw.rect(surf, (36, 39, 44), (x0 - 4, yy - 2, 540, 20))
            draw_token(surf, u.t, "player", (x0 + 8, yy + 8), radius=8, bar=False)
            text(surf, fit(f"{u.name} — {u.t.name}", "small", 220), (x0 + 22, yy), "small")
            tier_badge(surf, u.t.tier, (x0 + 252, yy + 2))
            rank_text(surf, u.rank, (x0 + 300, yy))
            text(surf, u.xp, (x0 + 385, yy), "small")
            text(surf, u.kills_total, (x0 + 430, yy), "small")
            text(surf, u.battles, (x0 + 480, yy), "small")
        if len(fallen) > 21:
            text(surf, f"+{len(fallen) - 21} more — see the Chronicle (H) for everyone.", (x0, y + 21 * 21 + 2),
                 "small", C["muted"])

        rx = body.x + 590
        y = body.y
        text(surf, "Enemy losses", (rx, y), "head", C["red"])
        y += 32
        dead = [u for u in self.units if u.team == "enemy" and u.state == "dead"]
        text(surf, "By rank", (rx, y), "smallb", C["gold"])
        y += 20
        for i in range(len(RANKS)):
            n = sum(1 for u in dead if u.rank == i and not u.summoned)
            rank_text(surf, i, (rx, y), "small")
            pygame.draw.rect(surf, RANK_COLORS[i], (rx + 80, y + 3, min(250, n * 8), 10))
            text(surf, n, (rx + 90 + min(250, n * 8), y), "small")
            y += 18
        y += 8
        text(surf, "By tier", (rx, y), "smallb", C["gold"])
        y += 20
        for tier in (1, 2, 3, 4):
            n = sum(1 for u in dead if u.t.tier == tier and not u.summoned)
            tier_badge(surf, tier, (rx + 2, y + 2))
            pygame.draw.rect(surf, TIER_COLORS[tier], (rx + 80, y + 3, min(250, n * 8), 10))
            text(surf, n, (rx + 90 + min(250, n * 8), y), "small")
            y += 18
        summ = sum(1 for u in dead if u.summoned)
        if summ:
            text(surf, f"Plus {summ} summoned or raised creatures destroyed.", (rx, y + 4), "small", C["muted"])
            y += 20
        y += 10
        notable = sorted([u for u in dead if u.t.tier >= 3 or u.rank >= 3], key=lambda u: -u.value)
        text(surf, "Notable enemy dead", (rx, y), "smallb", C["gold"])
        y += 20
        for u in notable[:8]:
            draw_token(surf, u.t, "enemy", (rx + 8, y + 8), radius=8, bar=False)
            r = text(surf, u.t.name, (rx + 22, y), "small")
            tier_badge(surf, u.t.tier, (r.right + 6, y + 2))
            rank_text(surf, u.rank, (r.right + 40, y), "small")
            y += 20
        if not notable:
            text(surf, "Nothing remarkable.", (rx, y), "small", C["muted"])

    def draw_honours(self, surf, body):
        x0, y = body.x, body.y
        mine = [u for u in self.units if u.team == "player" and not u.summoned and "static" not in u.t.tags]
        top = sorted(mine, key=lambda v: -(v.stats["kills"] * 10 + v.stats["dmg"] + v.stats["healed"]))[:18]
        text(surf, "Top performers", (x0, y), "head", C["blue"])
        y += 30
        heads = [("Soldier", 0), ("Rank", 220), ("Kills", 310), ("Dmg", 360), ("Healed", 410), ("Spells", 470),
                 ("XP +", 525)]
        for h, dx in heads:
            text(surf, h, (x0 + dx, y), "tiny", C["muted"])
        y += 16
        for i, u in enumerate(top):
            yy = y + i * 21
            if i % 2 == 0:
                pygame.draw.rect(surf, (36, 39, 44), (x0 - 4, yy - 2, 570, 20))
            draw_token(surf, u.t, "player", (x0 + 8, yy + 8), radius=8, bar=False)
            col = C["dim"] if u.state == "dead" else C["paper"]
            text(surf, fit(f"{u.name} — {u.t.name}" + (" †" if u.state == "dead" else ""), "small", 190),
                 (x0 + 22, yy), "small", col)
            rank_text(surf, u.rank, (x0 + 220, yy), "small")
            for dx, v in ((310, u.stats["kills"]), (360, u.stats["dmg"]), (410, u.stats["healed"]),
                          (470, u.stats["spells"]), (525, u.xp - u.start_xp)):
                text(surf, v, (x0 + dx, yy), "small", col if v else C["dim"])
        rx = body.x + 610
        y = body.y
        text(surf, f"Promotions ({len(self.promotions)})", (rx, y), "head", C["gold"])
        y += 32
        survivors = [u for u in mine if u.state != "dead"]
        xp = sum(u.xp - u.start_xp for u in survivors)
        text(surf, f"{len(survivors)} survivors earned {xp} XP.", (rx, y), "small", C["muted"])
        y += 22
        for u in sorted(self.promotions, key=lambda v: -v.value)[:20]:
            text(surf, fit(f"{u.name} — {u.t.name}", "small", 170), (rx, y), "small")
            rank_text(surf, u.start_rank, (rx + 180, y), "small")
            text(surf, "→", (rx + 245, y), "small")
            rank_text(surf, u.rank, (rx + 262, y), "smallb")
            y += 19
        if not self.promotions:
            text(surf, "No promotions this time.", (rx, y), "small", C["muted"])


# --------------------------------------------------------------------------
# The game: town (real time), war map, regions
# --------------------------------------------------------------------------
class Plot:
    def __init__(self, idx, rect):
        self.idx, self.rect = idx, pygame.Rect(rect)
        self.key = None
        self.level = 0
        self.building = None      # {"target", "remaining", "total"}
        self.queue = []           # [unit_key, remaining, total]


TOWN_RECT = pygame.Rect(20, 72, 780, 474)
PLOT_COLS, PLOT_ROWS = 6, 4
HALL_PLOT = 8
MERC_POOL = ["sellsword", "crossbow", "knight", "ogre_merc", "assassin", "monk", "berserker"]


def comp_text(keys):
    counts = {}
    for k in keys:
        counts[k] = counts.get(k, 0) + 1
    return ", ".join(f"{n} {UNITS[k].name}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1]))


class Game:
    def __init__(self, mode="campaign", difficulty="Normal", seed=None):
        self.mode, self.difficulty = mode, difficulty
        self.diff = DIFFICULTY[difficulty]
        self.seed = seed if seed is not None else random.randrange(1, 10 ** 6)
        self.gold, self.iron, self.essence = 160.0, 20.0, 10.0
        self.plots = []
        pw, ph = 122, 110
        for i in range(PLOT_COLS * PLOT_ROWS):
            r, c = divmod(i, PLOT_COLS)
            self.plots.append(Plot(i, (TOWN_RECT.x + 8 + c * (pw + 6), TOWN_RECT.y + 8 + r * (ph + 6), pw, ph)))
        hall = self.plots[HALL_PLOT]
        hall.key, hall.level = "hall", 1
        hc = hall.rect.center
        order = sorted(range(len(self.plots)), key=lambda i: (math.hypot(self.plots[i].rect.centerx - hc[0],
                                                                         (self.plots[i].rect.centery - hc[1]) * 1.3), i))
        self.plot_rank = {idx: n for n, idx in enumerate(order)}
        self.captain = Soldier("captain", "player")
        self.captain.name = "Captain " + make_name()
        self.army = [self.captain] + [Soldier("militia", "player") for _ in range(3)]
        self.captain_down = 0.0
        self.integrity = 3
        self.integrity_bonus = 0
        self.time = 0.0
        self.region_no = 1
        self.region = Region(1, mode, difficulty, self.seed)
        self.raid_timer, self.raid_count, self.raid_warned = 200.0, 0, False
        self.growth_timer, self.growth_ticks = 90.0, 0
        self.drill_timer = 0.0
        self.bonus_income = self.bonus_iron = self.bonus_ess = 0.0
        self.global_mods = []
        self.researched = set()
        self.fallen = []
        self.records = {"battles_won": 0, "battles_lost": 0, "enemies_slain": 0, "conquests": 0,
                        "raids_repelled": 0, "soldiers_lost": 0, "regions_cleared": 0, "promotions": 0,
                        "summons": 0}
        self.scene, self.return_scene, self.battle = "town", "town", None
        self.selected = HALL_PLOT
        self.side_tab = "Train"
        self.build_tab = "Economy"
        self.map_sel = self.region.open_targets()[0].idx
        self.toasts = []
        self.over = None
        self.paused = False
        self.region_clear = None
        self.want_autosave = False
        self.odds = {"key": None, "n": 0, "w": 0}
        self.ui = UI()
        self.peons = [{"x": 400.0, "y": 300.0, "tx": 400.0, "ty": 300.0} for _ in range(7)]

    # ---- persistence -----------------------------------------------------
    def __getstate__(self):
        d = dict(self.__dict__)
        d["ui"] = None
        d["battle"] = None
        if d["scene"] == "battle":
            d["scene"] = "town"
        return d

    def __setstate__(self, d):
        self.__dict__.update(d)
        self.ui = UI()

    # ---- economy ---------------------------------------------------------
    def level(self, key):
        return max((p.level for p in self.plots if p.key == key), default=0)

    def econ(self, name):
        return sum(v for tk in self.researched for n, v in TECH_BY_KEY[tk].econ if n == name)

    def gold_rate(self):
        base = 1.5 + 0.5 * (self.level("hall") - 1) + 1.2 * self.level("market") + self.bonus_income + self.econ("gold_flat")
        return base * (1 + 0.1 * self.level("treasury") + self.econ("gold_mult"))

    def iron_rate(self):
        return (0.3 + 0.7 * self.level("mine") + self.bonus_iron + self.econ("iron_flat")) * (1 + self.econ("iron_mult"))

    def ess_rate(self):
        return (0.1 + 0.4 * self.level("well") + self.bonus_ess + self.econ("ess_flat")) * (1 + self.econ("ess_mult"))

    def army_cap(self):
        return int(6 + 2 * self.level("hall") + 4 * self.level("longhouse") + 2 * self.level("farm") + self.econ("cap"))

    def max_integrity(self):
        return min(8, 3 + (1 if self.level("walls") >= 3 else 0) + int(self.econ("integrity")) + self.integrity_bonus)

    def plots_open(self):
        return 12 + 3 * (self.level("hall") - 1)

    def plot_locked(self, plot):
        return self.plot_rank[plot.idx] >= self.plots_open()

    def builders(self):
        hall = self.level("hall")
        return 1 + (hall >= 3) + (hall >= 5)

    def builds_running(self):
        return sum(1 for p in self.plots if p.building)

    def troops(self):
        return [s for s in self.army if s is not self.captain]

    def queued(self):
        return sum(len(p.queue) for p in self.plots)

    def have(self):
        return {"gold": self.gold, "iron": self.iron, "essence": self.essence}

    def afford(self, g, i=0, e=0):
        return self.gold >= g and self.iron >= i and self.essence >= e

    def pay(self, g, i=0, e=0):
        self.gold -= g
        self.iron -= i
        self.essence -= e

    def toast(self, msg, color=None, sound=None):
        self.toasts.append([msg, 4.5, color or C["paper"]])
        if sound:
            SOUND.play(sound)

    def unit_mods(self, t):
        mods = {}
        for tk in self.researched:
            for group, stat, val in TECH_BY_KEY[tk].mods:
                if in_group(t, group):
                    mods[stat] = mods.get(stat, 0) + val
        for group, stat, val in self.global_mods:
            if in_group(t, group):
                mods[stat] = mods.get(stat, 0) + val
        forge = self.level("forge")
        if forge and "static" not in t.tags:
            mods["prot"] = mods.get("prot", 0) + (2 if forge >= 4 else 1)
            if forge >= 2:
                mods["dmg"] = mods.get("dmg", 0) + 1
        return mods

    def refresh_perm(self):
        for s in self.army:
            s.bonus_hp = self.unit_mods(s.t).get("hp", 0)
            s.hp = min(s.hp, s.max_hp)

    def req_met(self, req):
        if req[0] == "building":
            return self.level(req[1]) >= req[2]
        return self.region_no >= req[1]

    @staticmethod
    def req_text(req):
        if req[0] == "building":
            return f"Needs {BUILDINGS[req[1]].name} Lv{req[2]}"
        return f"Reach region {req[1]}"

    def can_build(self, plot, key):
        b = BUILDINGS[key]
        if self.plot_locked(plot):
            return False, "Plot locked"
        target = plot.level + 1
        if plot.key is None and any(p.key == key for p in self.plots):
            return False, "Already built"
        if target > b.max_level:
            return False, "Max level"
        for req in building_reqs(key, target):
            if not self.req_met(req):
                return False, self.req_text(req)
        if plot.building:
            return False, "Under construction"
        if self.builds_running() >= self.builders():
            return False, "Builders busy"
        if not self.afford(*building_cost(key, target)):
            return False, "Can't afford"
        return True, ""

    def build(self, plot, key):
        if not self.can_build(plot, key)[0]:
            SOUND.play("error")
            return
        target = plot.level + 1
        self.pay(*building_cost(key, target))
        plot.key = key
        t = building_time(key, target)
        plot.building = {"target": target, "remaining": t, "total": t}
        SOUND.play("build", 0.6)

    def unit_cost(self, t):
        g = t.gold
        if t.building == "guild":
            g = int(g * (1 - self.econ("merc_discount")))
        return g, t.iron, t.essence

    def can_recruit(self, plot, ukey):
        t = UNITS[ukey]
        if plot.level < t.req_level:
            return False, f"Needs Lv{t.req_level}"
        if len(self.troops()) + self.queued() >= self.army_cap():
            return False, "Army full"
        if len(plot.queue) >= 5:
            return False, "Queue full"
        if not self.afford(*self.unit_cost(t)):
            return False, "Can't afford"
        return True, ""

    def recruit(self, plot, ukey):
        if not self.can_recruit(plot, ukey)[0]:
            SOUND.play("error")
            return
        t = UNITS[ukey]
        self.pay(*self.unit_cost(t))
        plot.queue.append([ukey, t.train, t.train])

    def start_xp(self, t):
        xp = self.econ("start_xp")
        if t.building == "barracks":
            xp = max(xp, self.econ("xp_barracks"))
        if t.building == "guild":
            xp = max(xp, self.econ("xp_guild"))
        return int(xp)

    def can_research(self, tk):
        t = TECH_BY_KEY[tk]
        if tk in self.researched:
            return False, "Researched"
        if self.level(t.building) < t.level:
            return False, f"Needs {BUILDINGS[t.building].name} Lv{t.level}"
        if not self.afford(t.gold, t.iron, t.essence):
            return False, "Can't afford"
        return True, ""

    def research(self, tk):
        if not self.can_research(tk)[0]:
            SOUND.play("error")
            return
        t = TECH_BY_KEY[tk]
        self.pay(t.gold, t.iron, t.essence)
        self.researched.add(tk)
        self.refresh_perm()
        self.toast(f"Researched {t.name}.", C["gold"], "promote")

    def available(self):
        units = self.troops()
        if self.captain_down <= 0:
            units = [self.captain] + units
        return units

    def army_strength(self):
        total = 0.0
        cache = {}
        for s in self.available():
            if s.t.key not in cache:
                cache[s.t.key] = self.unit_mods(s.t)
            total += unit_power(s.t, s.rank, cache[s.t.key]) * (0.4 + 0.6 * s.hp / s.max_hp)
        return total

    # ---- odds: simulate the fight a few times in the background ------------
    def odds_key(self, t):
        return (self.region_no, t.idx, len(t.garrison), sum(u.xp for u in t.garrison),
                tuple((s.uid, s.hp, s.xp) for s in self.available()),
                len(self.researched), self.level("forge"), len(self.global_mods))

    def simulate(self, t):
        def clone(s):
            c = Soldier(s.t.key, s.team, s.xp, named=False)
            c.bonus_hp = s.bonus_hp
            c.hp = min(s.hp, c.max_hp)
            return c
        players = [clone(s) for s in self.available()]
        enemies = [clone(u) for u in t.garrison]
        for u in enemies:
            u.hp = u.max_hp
        b = Battle("attack", "sim", players, enemies, attacker="player", bonuses=t.bonuses(),
                   mod_fn=self.unit_mods)
        b.instant = True
        while not b.result:
            b.resolve_round()
        return b.result == "player"

    def update_odds(self, t, budget_ms=8.0):
        runs = 24 if len(t.garrison) + len(self.army) < 90 else 12
        key = self.odds_key(t)
        if self.odds.get("key") != key:
            self.odds = {"key": key, "n": 0, "w": 0}
        if not self.available():
            return
        start = time.perf_counter()
        while self.odds["n"] < runs and (time.perf_counter() - start) * 1000 < budget_ms:
            self.odds["w"] += self.simulate(t)
            self.odds["n"] += 1

    # ---- war -------------------------------------------------------------
    def open_targets(self):
        return self.region.open_targets()

    def attack(self, target):
        if self.captain_down > 0 or target not in self.open_targets() or self.over:
            SOUND.play("error")
            return
        self.return_scene = self.scene
        if target.final:
            win = "Ironveil falls. You have won the war!"
        else:
            win = f"{target.name} is yours. Spoils: " + "; ".join(target.reward_lines()).rstrip(".") + "."
        lose = f"The survivors of {target.name} will heal and hold against your next attempt."
        self.battle = Battle("attack", f"Assault on {target.name}", self.available(), target.garrison,
                             attacker="player", target=target, bonuses=target.bonuses(),
                             spoils=(win, lose), mod_fn=self.unit_mods)
        self.scene = "battle"
        SOUND.play("march")

    def next_raid(self):
        n = self.raid_count + 1
        r = self.region_no
        rng = random.Random(self.seed * 31 + n * 7 + r * 1009)
        faction = self.region.factions[n % 2]
        mult = region_mult(r)
        budget = min((3 + 2.5 * n) * mult, 40 * mult) * self.diff["raid"]
        comp = pick_units(faction, budget, 2 if (r == 1 and n < 4) else 3, rng, r)
        xp = max(0, (r - 1) * 15 + n + self.diff["xp"])
        return faction, comp, xp

    def raid_interval(self):
        return max(90.0, 170.0 - 6 * self.raid_count)

    def start_raid(self):
        faction, comp, xp = self.next_raid()
        self.raid_count += 1
        enemies = [Soldier(k, "enemy", xp + random.randint(0, 2)) for k in comp]
        towers = [Soldier("tower", "player") for _ in range(self.level("tower"))]
        defenders = self.available()
        self.raid_timer = self.raid_interval()
        self.raid_warned = False
        if not defenders and not towers:
            self.lose_raid()
            return
        self.return_scene = self.scene if self.scene != "battle" else "town"
        loot = 25 + 10 * min(self.raid_count, 16) * self.region_no
        lost_gold = int(self.gold * 0.3)
        fall = " This will be the end of your town!" if self.integrity <= 1 else ""
        spoils = (f"The {faction} raid is broken. You loot {loot} gold from the fallen.",
                  f"The raiders will sack the town: -1 town strength and {lost_gold} gold stolen.{fall}")
        walls = self.level("walls")
        bonuses = {"enemy": region_stats(self.region_no - 1)}
        if walls:
            bonuses["player"] = {"def": walls}
        self.battle = Battle("defense", f"{faction} raid on your town", defenders + towers, enemies,
                             attacker="enemy", bonuses=bonuses,
                             spoils=spoils, mod_fn=self.unit_mods)
        self.pending_loot = loot
        self.scene = "battle"
        SOUND.play("horn")

    def lose_raid(self):
        self.integrity -= 1
        stolen = int(self.gold * 0.3)
        self.gold -= stolen
        self.toast(f"Raiders sacked the town and stole {stolen} gold!", C["red"], "defeat")
        if self.integrity <= 0:
            self.over = "defeat"

    def apply_special(self, t):
        sp = t.special
        r = self.region_no
        if sp == "relic":
            self.global_mods.append(("casters", "power", 1))
        elif sp == "armory":
            self.global_mods.append(("all", "prot", 1))
        elif sp == "banner":
            self.global_mods.append(("all", "mor", 2))
        elif sp == "mercs":
            n = random.randint(2, 3)
            joined = []
            for _ in range(n):
                s = Soldier(random.choice(MERC_POOL), "player", 30 + 10 * (r - 1))
                self.army.append(s)
                joined.append(s.t.name)
            self.toast("Mercenaries join: " + ", ".join(joined), C["gold"])
        elif sp == "vault":
            self.gold += 250 * r
            self.iron += 80 * r
            self.essence += 40 * r
        elif sp == "shrine":
            self.integrity_bonus += 1
            self.integrity = min(self.max_integrity(), self.integrity + 1)
        self.refresh_perm()

    def finish_battle(self):
        b = self.battle
        won = b.result == "player"
        losses = []
        for s in list(self.army):
            if s.state == "dead":
                if s is self.captain:
                    self.captain_down = 45.0
                    self.captain.hp = 0
                    self.toast("Your Captain was carried from the field, badly hurt.", C["red"])
                else:
                    self.army.remove(s)
                    losses.append(s)
                    self.fallen.append({"name": s.name, "unit": s.t.name, "key": s.t.key, "tier": s.t.tier,
                                        "rank": s.rank, "xp": s.xp, "kills": s.kills_total,
                                        "battles": s.battles, "where": b.title, "time": self.time,
                                        "region": self.region_no})
        heal = self.econ("heal_after")
        for s in self.army:
            if s.state != "dead" and heal:
                s.hp = min(s.max_hp, s.hp + int((s.max_hp - s.hp) * heal))
        rec = self.records
        rec["battles_won" if won else "battles_lost"] += 1
        rec["enemies_slain"] += sum(1 for u in b.units if u.team == "enemy" and u.state == "dead")
        rec["soldiers_lost"] += len(losses)
        rec["promotions"] += len(b.promotions)
        rec["summons"] += sum(1 for u in b.units if u.team == "player" and u.summoned)
        if losses:
            vets = [s for s in losses if s.rank >= 2]
            worst = max(losses, key=lambda s: s.value)
            msg = f"Lost {len(losses)} soldiers"
            if vets:
                msg += f" ({len(vets)} Veteran or better)"
            msg += f". Heaviest loss: {worst.name}, {worst.rank_name} {worst.t.name}."
            self.toast(msg, RANK_COLORS[worst.rank] if worst.rank >= 2 else C["red"])
        if b.kind == "attack":
            t = b.target
            if won:
                t.conquered = True
                rec["conquests"] += 1
                self.gold += t.gold
                self.bonus_income += t.income
                self.bonus_iron += t.iron_income
                self.bonus_ess += t.ess_income
                if t.special:
                    self.apply_special(t)
                SOUND.play("coin")
                if t.final:
                    self.over = "victory"
                elif t.boss:
                    rec["regions_cleared"] += 1
                    self.region_clear = {"name": self.region.name, "number": self.region_no,
                                         "taken": sum(x.conquered for x in self.region.targets),
                                         "total": len(self.region.targets), "boss": t.name}
                else:
                    self.toast(f"{t.name} taken!", C["gold"])
                opened = self.open_targets()
                if opened:
                    self.map_sel = opened[0].idx
            else:
                before = len(t.garrison)
                t.garrison = [u for u in t.garrison if u.state != "dead"]
                for u in t.garrison:
                    u.hp = u.max_hp
                refill = int((before - len(t.garrison)) * 0.6)
                t.garrison += [t.new_recruit() for _ in range(refill)]
                self.toast(f"The assault on {t.name} failed. {refill} reinforcements rush in.", C["red"])
        else:
            if won:
                self.gold += self.pending_loot
                rec["raids_repelled"] += 1
                self.toast(f"Raid repelled! Looted {self.pending_loot} gold.", C["gold"], "coin")
            else:
                self.lose_raid()
        if b.promotions:
            n = len(b.promotions)
            self.toast(f"{n} soldier{'s' if n > 1 else ''} earned a promotion!", C["gold"])
        self.battle = None
        self.scene = self.return_scene
        self.want_autosave = True

    def advance_region(self):
        self.region_no += 1
        self.region = Region(self.region_no, self.mode, self.difficulty, self.seed + self.region_no * 7919)
        self.region.name = REGION_NAMES[(self.seed + self.region_no * 5) % len(REGION_NAMES)]
        self.raid_count = 0
        self.raid_timer = 170.0
        self.raid_warned = False
        self.region_clear = None
        self.map_sel = self.open_targets()[0].idx
        self.integrity = self.max_integrity()
        self.scene = "map"
        self.toast(f"Region {self.region_no}: {self.region.name}. The foes here are "
                   f"{' and '.join(self.region.factions)}.", C["gold"], "horn")
        self.want_autosave = True

    def score(self):
        r = self.records
        return r["conquests"] * 10 + r["regions_cleared"] * 50 + r["raids_repelled"] * 3 + r["enemies_slain"] // 5

    # ---- update ----------------------------------------------------------
    def update(self, dt):
        if self.over or self.region_clear:
            return
        if self.scene == "battle":
            self.battle.update(dt)
            return
        for t in self.toasts:
            t[1] -= dt
        self.toasts = [t for t in self.toasts if t[1] > 0]
        if self.paused:
            return
        self.time += dt
        self.gold = min(99999, self.gold + self.gold_rate() * dt)
        self.iron = min(99999, self.iron + self.iron_rate() * dt)
        self.essence = min(99999, self.essence + self.ess_rate() * dt)

        for p in self.plots:
            if p.building:
                p.building["remaining"] -= dt
                if p.building["remaining"] <= 0:
                    p.level = p.building["target"]
                    p.building = None
                    self.refresh_perm()
                    self.toast(f"{BUILDINGS[p.key].name} Lv{p.level} complete.", sound="build")
            if p.queue and p.level > 0 and len(self.troops()) < self.army_cap():
                p.queue[0][1] -= dt
                if p.queue[0][1] <= 0:
                    ukey = p.queue.pop(0)[0]
                    s = Soldier(ukey, "player", self.start_xp(UNITS[ukey]))
                    s.bonus_hp = self.unit_mods(s.t).get("hp", 0)
                    s.hp = s.max_hp
                    self.army.append(s)
                    self.toast(f"{s.name} the {s.t.name} joins the warband.", sound="train")

        rate = (0.25 + 0.12 * self.level("longhouse") + 0.08 * self.level("farm") + 0.15 * self.level("temple"))
        rate *= 1 + self.econ("heal_mult")
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

        self.growth_timer -= dt * self.diff["growth"]
        if self.growth_timer <= 0:
            self.growth_timer = 60.0
            self.growth_ticks += 1
            opened = self.open_targets()
            for t in self.region.targets:
                if t.conquered or (t not in opened and self.growth_ticks % 2):
                    continue
                for _ in range(max(1, len(t.garrison) // 15)):
                    if len(t.garrison) < t.cap:
                        t.garrison.append(t.new_recruit())
                if t.garrison:
                    random.choice(t.garrison).xp += 3

        self.raid_timer -= dt
        if self.raid_timer <= 30 and not self.raid_warned:
            self.raid_warned = True
            faction, comp, _ = self.next_raid()
            self.toast(f"Scouts report a {faction} raid approaching! ({len(comp)} troops)", C["red"], "horn")
            if SETTINGS["raid_pause"]:
                self.paused = True
        if self.raid_timer <= 0:
            self.start_raid()

        for pe in self.peons:
            dx, dy = pe["tx"] - pe["x"], pe["ty"] - pe["y"]
            d = math.hypot(dx, dy)
            if d < 3:
                sites = [p for p in self.plots if p.building] * 3 + [p for p in self.plots if p.key]
                p = random.choice(sites)
                pe["tx"] = p.rect.centerx + random.uniform(-40, 40)
                pe["ty"] = p.rect.bottom - random.uniform(6, 18)
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
        if self.region_clear:
            return
        if self.scene == "town":
            for p in self.plots:
                if p.rect.collidepoint(pos):
                    if p.idx != self.selected:
                        SOUND.play("click", 0.4)
                    self.selected = p.idx
        else:
            for t in self.region.targets:
                x, y = self.node_pos(t.pos)
                if math.hypot(pos[0] - x, pos[1] - y) < 28:
                    self.map_sel = t.idx
                    SOUND.play("click", 0.4)

    def on_key(self, key):
        if self.scene == "battle":
            self.battle.on_key(key)
        elif key in (pygame.K_p, pygame.K_SPACE):
            self.paused = not self.paused
        elif key == pygame.K_m:
            self.scene = "map" if self.scene == "town" else "town"
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.region_clear:
            self.advance_region()

    # ---- drawing ---------------------------------------------------------
    def draw(self, surf, mouse, menu_cb):
        self.ui.reset(mouse)
        if self.scene == "battle":
            self.battle.draw(surf, mouse, self.finish_battle, menu_cb)
            return
        surf.fill(C["bg"])
        self.draw_topbar(surf, menu_cb)
        if self.scene == "town":
            self.draw_town(surf)
            self.draw_side(surf)
            self.draw_army(surf)
            self.draw_campaign(surf)
        else:
            self.draw_map(surf, mouse)
            self.draw_map_panel(surf)
        for i, (msg, ttl, col) in enumerate(self.toasts[-4:]):
            img = FONTS["bold"].render(fit(msg, "bold", 760), True, col)
            img.set_alpha(int(255 * min(1, ttl)))
            r = img.get_rect(center=(410, 100 + i * 30))
            bg = pygame.Surface((r.w + 24, r.h + 8), pygame.SRCALPHA)
            bg.fill((10, 11, 12, int(215 * min(1, ttl))))
            surf.blit(bg, (r.x - 12, r.y - 4))
            surf.blit(img, r)
        if self.paused and not self.region_clear:
            text(surf, "PAUSED  ·  press P to resume", (410, 530), "head", C["gold"], center=True)
        if self.region_clear:
            self.draw_region_clear(surf)

    def draw_topbar(self, surf, menu_cb):
        pygame.draw.rect(surf, C["panel"], (0, 0, W, 60))
        pygame.draw.line(surf, C["edge"], (0, 60), (W, 60), 2)
        text(surf, "WAR ON THE RIM", (16, 8), "head", C["gold"])
        mode = "Endless" if self.mode == "endless" else "Campaign"
        text(surf, f"{mode} · {self.difficulty} · {fmt_time(self.time)}", (16, 34), "tiny", C["muted"])
        x = 206
        for label, val, rate, key in (("Gold", self.gold, self.gold_rate(), "gold"),
                                      ("Iron", self.iron, self.iron_rate(), "iron"),
                                      ("Essence", self.essence, self.ess_rate(), "essence")):
            text(surf, label, (x, 8), "tiny", C["muted"])
            text(surf, int(val), (x, 22), "head", C[key])
            text(surf, f"+{rate:.1f}/s", (x + 58, 30), "tiny", C["muted"])
            x += 118
        text(surf, "Warband", (x, 8), "tiny", C["muted"])
        text(surf, f"{len(self.troops())}/{self.army_cap()}", (x, 22), "head")
        x += 84
        text(surf, "Town", (x, 8), "tiny", C["muted"])
        mi = self.max_integrity()
        for i in range(mi):
            pygame.draw.rect(surf, C["green"] if i < self.integrity else (60, 50, 44),
                             (x + i * (min(16, 96 // mi)), 28, min(13, 96 // mi - 3), 16), border_radius=2)
        x += 110
        text(surf, f"Region {self.region_no}", (x, 8), "tiny", C["muted"])
        text(surf, fit(self.region.name, "smallb", 150), (x, 26), "smallb")
        x += 160
        faction, comp, _ = self.next_raid()
        secs = max(0, int(self.raid_timer))
        col = C["red"] if secs <= 30 else C["paper"]
        text(surf, f"Next raid ({faction}) in {secs // 60}:{secs % 60:02d}", (x, 8), "smallb", col)
        text(surf, fit(comp_text(comp), "tiny", 250), (x, 28), "tiny", C["muted"])
        self.ui.button(surf, (W - 150, 14, 64, 32), "Play" if self.paused else "Pause",
                       lambda: setattr(self, "paused", not self.paused), accent=self.paused, font="smallb")
        self.ui.button(surf, (W - 80, 14, 64, 32), "Menu", menu_cb, font="smallb")

    def draw_town(self, surf):
        pygame.draw.rect(surf, C["grass"], TOWN_RECT, border_radius=6)
        rng = random.Random(7)
        for _ in range(140):
            x, y = rng.randint(TOWN_RECT.x + 6, TOWN_RECT.right - 6), rng.randint(TOWN_RECT.y + 6, TOWN_RECT.bottom - 6)
            pygame.draw.circle(surf, C["grass2"], (x, y), rng.randint(2, 5))
        for p in self.plots:
            pygame.draw.rect(surf, C["road"], p.rect.inflate(8, 8), border_radius=6)
        for p in self.plots:
            self.draw_plot(surf, p)
        for pe in self.peons:
            pygame.draw.circle(surf, (210, 190, 150), (int(pe["x"]), int(pe["y"]) - 5), 3)
            pygame.draw.rect(surf, (120, 90, 60), (int(pe["x"]) - 2, int(pe["y"]) - 2, 5, 6))
        pygame.draw.rect(surf, C["edge"], TOWN_RECT, 2, border_radius=6)

    def draw_plot(self, surf, p):
        sel = p.idx == self.selected
        r = p.rect
        locked = self.plot_locked(p)
        pygame.draw.rect(surf, (52, 48, 42) if locked else C["dirt"], r, border_radius=5)
        if locked:
            need = 1 + math.ceil((self.plot_rank[p.idx] + 1 - 12) / 3)
            cx, cy = r.center
            pygame.draw.rect(surf, C["dim"], (cx - 9, cy - 8, 18, 14), border_radius=2)
            pygame.draw.arc(surf, C["dim"], (cx - 7, cy - 20, 14, 18), 0, math.pi, 2)
            text(surf, f"Hall Lv{need}", (cx, cy + 20), "tiny", C["dim"], center=True)
        elif p.key is None:
            text(surf, "+", r.center, "title", C["muted"], center=True)
            text(surf, "Empty plot", (r.centerx, r.bottom - 16), "tiny", C["muted"], center=True)
        else:
            b = BUILDINGS[p.key]
            lvl = max(1, p.level)
            w, h = int((58 + 9 * lvl) * 1.08), int((22 + 5 * lvl) * 0.9)
            base_y = r.bottom - 22
            body = pygame.Rect(r.centerx - w // 2, base_y - h, w, h)
            col = b.color if p.level else mix(b.color, C["dirt"], 0.55)
            pygame.draw.ellipse(surf, (40, 34, 26), (body.x - 4, base_y - 5, w + 8, 10))
            pygame.draw.rect(surf, col, body)
            roof_h = 12 + lvl * 2
            pygame.draw.polygon(surf, mix(col, C["ink"], 0.4),
                                [(body.x - 5, body.y), (body.centerx, body.y - roof_h), (body.right + 5, body.y)])
            if p.key in ("hall", "tower", "walls") and lvl >= 2:
                for side in (-1, 1):
                    tx = body.centerx + side * (w // 2 - 5)
                    pygame.draw.rect(surf, mix(col, C["ink"], 0.2), (tx - 5, body.y - 10 - lvl * 2, 10, h + 10 + lvl * 2))
            pygame.draw.rect(surf, C["ink"], (body.centerx - 4, base_y - 11, 8, 11))
            pygame.draw.circle(surf, C["ink"], (body.centerx, body.y - roof_h // 2 + 2), 11)
            draw_glyph(surf, b.glyph, (body.centerx, body.y - roof_h // 2 + 2), 13, C["paper"])
            if p.building:
                for i in range(3):
                    pygame.draw.line(surf, (160, 130, 90), (body.x + i * w // 3, base_y), (body.x + i * w // 3, body.y - 4), 2)
            text(surf, fit(b.name, "tinyb", r.w - 30), (r.x + 5, r.bottom - 15), "tinyb")
            text(surf, f"{p.level}/{b.max_level}", (r.right - 5, r.bottom - 15), "tiny", C["gold"], right=True)
        if p.building:
            prog = 1 - p.building["remaining"] / p.building["total"]
            pygame.draw.rect(surf, (30, 30, 30), (r.x + 8, r.y + 6, r.w - 16, 6))
            pygame.draw.rect(surf, C["gold"], (r.x + 8, r.y + 6, (r.w - 16) * prog, 6))
        if p.queue:
            ukey, rem, tot = p.queue[0]
            prog = 1 - rem / tot
            pygame.draw.rect(surf, (30, 30, 30), (r.x + 8, r.y + 14, r.w - 16, 5))
            pygame.draw.rect(surf, C["blue"], (r.x + 8, r.y + 14, (r.w - 16) * prog, 5))
            text(surf, f"x{len(p.queue)}", (r.right - 6, r.y + 20), "tinyb", C["blue"], right=True)
        pygame.draw.rect(surf, C["gold"] if sel else (0, 0, 0), r, 3 if sel else 1, border_radius=5)

    def draw_side(self, surf):
        rect = pygame.Rect(812, 72, 448, 474)
        panel(surf, rect)
        p = self.plots[self.selected]
        x, y = rect.x + 14, rect.y + 10
        if self.plot_locked(p):
            text(surf, "Locked plot", (x, y), "title")
            for i, line in enumerate(wrap("Upgrade your Town Hall to clear more land. Each Hall level opens "
                                          "three more building plots.", "body", 420)):
                text(surf, line, (x, y + 40 + i * 20), "body", C["muted"])
            return
        if p.key is None:
            self.draw_build_menu(surf, p, x, y)
            return
        b = BUILDINGS[p.key]
        text(surf, b.name, (x, y), "title")
        text(surf, f"Level {p.level}/{b.max_level}", (rect.right - 14, y + 8), "bold", C["gold"], right=True)
        y += 34
        for line in wrap(b.desc, "small", 420)[:2]:
            text(surf, line, (x, y), "small", C["muted"])
            y += 16
        y += 4
        if p.building:
            left = int(p.building["remaining"])
            text(surf, f"Building level {p.building['target']}... {left}s left", (x, y + 6), "bold", C["gold"])
        elif p.level < b.max_level:
            target = p.level + 1
            ok, why = self.can_build(p, p.key)
            self.ui.button(surf, (x, y, 150, 30), f"Upgrade to Lv{target}", lambda: self.build(p, p.key),
                           enabled=ok, accent=True, font="smallb")
            g, i_, e = building_cost(p.key, target)
            nx = cost_parts(surf, x + 160, y + 7, g, i_, e, "smallb", self.have())
            text(surf, f"{int(building_time(p.key, target))}s", (nx + 4, y + 7), "small", C["muted"])
            if why and why != "Can't afford":
                text(surf, fit(why, "small", 150), (rect.right - 14, y + 7), "small", C["red"], right=True)
        else:
            text(surf, "Fully upgraded.", (x, y + 6), "bold", C["green"])
        y += 38
        units = units_of(p.key)
        techs = techs_of(p.key)
        tabs = (["Train"] if units else []) + (["Research"] if techs else [])
        if not tabs:
            return
        if self.side_tab not in tabs:
            self.side_tab = tabs[0]
        self.ui.tabs(surf, x, y, tabs, self.side_tab, lambda t: setattr(self, "side_tab", t))
        y += 36
        if self.side_tab == "Train":
            self.draw_train(surf, p, units, x, y, rect)
        else:
            self.draw_research(surf, techs, x, y, rect)

    def draw_build_menu(self, surf, p, x, y):
        text(surf, "Empty plot", (x, y), "title")
        busy = self.builds_running()
        text(surf, f"Builders {busy}/{self.builders()} busy", (1246, y + 8), "small", C["muted"], right=True)
        y += 34
        self.ui.tabs(surf, x, y, ["Economy", "Military", "Magic"], self.build_tab,
                     lambda t: setattr(self, "build_tab", t))
        y += 36
        cat = self.build_tab.lower()
        shown = [b for b in BUILDING_LIST if b.category == cat and not any(q.key == b.key for q in self.plots)]
        if not shown:
            text(surf, "Everything in this category is built.", (x, y), "body", C["muted"])
        for b in shown:
            ok, why = self.can_build(p, b.key)
            text(surf, b.name, (x, y), "bold", C["paper"] if ok else C["muted"])
            cost_parts(surf, x + 150, y + 1, *building_cost(b.key, 1), "small", self.have())
            detail = why if why and why != "Can't afford" else b.desc
            text(surf, fit(detail, "tiny", 330), (x, y + 19), "tiny", C["red"] if why and why != "Can't afford" else C["muted"])
            self.ui.button(surf, (1246 - 70, y + 2, 70, 28), "Build", lambda k=b.key: self.build(p, k),
                           enabled=ok, font="smallb")
            y += 40

    def draw_train(self, surf, p, units, x, y, rect):
        for u in units:
            ok, why = self.can_recruit(p, u.key)
            locked = p.level < u.req_level
            draw_token(surf, u, "player", (x + 16, y + 20), radius=15, bar=False)
            r = text(surf, u.name, (x + 38, y - 2), "bold", C["muted"] if locked else C["paper"])
            tier_badge(surf, u.tier, (r.right + 6, y + 1))
            cost_parts(surf, r.right + 36, y, *self.unit_cost(u), "small", self.have())
            mv = f"  Mv {u.move}" if u.move > 1 else ""
            mana = f"  Mana {u.mana}" if u.mana else ""
            text(surf, f"HP {u.hp}  Att {u.att}  Def {u.defense}  Prot {u.prot}  Mor {u.mor}{mv}{mana}",
                 (x + 38, y + 15), "tiny", C["muted"])
            text(surf, fit(u.attack_line(), "tiny", 310), (x + 38, y + 29), "tiny", C["paper"])
            if locked:
                text(surf, f"Upgrade to Lv{u.req_level} to unlock.", (x + 38, y + 43), "tiny", C["red"])
            else:
                text(surf, fit(u.desc, "tiny", 310), (x + 38, y + 43), "tiny", C["muted"])
            self.ui.button(surf, (rect.right - 76, y + 4, 62, 30), "Train", lambda k=u.key: self.recruit(p, k),
                           enabled=ok, font="smallb")
            if why and not locked and why != "Can't afford":
                text(surf, why, (rect.right - 45, y + 40), "tiny", C["red"], center=True)
            y += 62
        if p.queue:
            names = ", ".join(UNITS[q[0]].name for q in p.queue)
            stall = "  (army full!)" if len(self.troops()) >= self.army_cap() else ""
            text(surf, fit(f"Training: {names}{stall}", "small", 420), (x, y), "small", C["blue"])

    def draw_research(self, surf, techs, x, y, rect):
        for t in techs:
            ok, why = self.can_research(t.key)
            done = t.key in self.researched
            col = C["green"] if done else (C["paper"] if why != f"Needs {BUILDINGS[t.building].name} Lv{t.level}" else C["muted"])
            r = text(surf, t.name, (x, y), "bold", col)
            if not done:
                cost_parts(surf, r.right + 10, y + 1, t.gold, t.iron, t.essence, "small", self.have())
            text(surf, fit(t.desc, "small", 330), (x, y + 18), "small", C["muted"])
            if done:
                text(surf, "Done", (rect.right - 45, y + 8), "smallb", C["green"], center=True)
            else:
                self.ui.button(surf, (rect.right - 86, y + 3, 72, 28), "Research", lambda k=t.key: self.research(k),
                               enabled=ok, font="tinyb")
                if why.startswith("Needs"):
                    text(surf, f"Lv{t.level}", (rect.right - 96, y + 10), "tinyb", C["red"], right=True)
            y += 46

    def draw_army(self, surf):
        rect = pygame.Rect(20, 556, 780, 194)
        panel(surf, rect)
        x, y = rect.x + 14, rect.y + 8
        text(surf, f"Warband  {len(self.troops())}/{self.army_cap()}", (x, y), "head")
        rx = 250
        for i, (_, name) in enumerate(RANKS):
            pygame.draw.polygon(surf, RANK_COLORS[i], [(rx, y + 9), (rx + 4, y + 14), (rx + 8, y + 9)])
            r = text(surf, name, (rx + 12, y + 3), "tiny", RANK_COLORS[i])
            rx = r.right + 12
        if self.captain_down > 0:
            text(surf, f"Captain recovering: {int(self.captain_down)}s", (rect.right - 14, y + 4), "smallb",
                 C["red"], right=True)
        else:
            c = self.captain
            text(surf, f"{c.name} · {c.rank_name} · HP {c.hp}/{c.max_hp}", (rect.right - 14, y + 4), "smallb",
                 C["gold"], right=True)
        groups = {}
        for s in self.troops():
            groups.setdefault(s.t.key, []).append(s)
        order = sorted(groups.items(), key=lambda kv: (-kv[1][0].t.tier, -len(kv[1])))
        if not groups:
            text(surf, "No troops yet. Select a building and train some.", (x, y + 50), "body", C["muted"])
        for n, (key, men) in enumerate(order[:16]):
            col, row = n % 4, n // 4
            cx, cy = x + col * 190, y + 34 + row * 37
            t = UNITS[key]
            hp = sum(m.hp for m in men) / sum(m.max_hp for m in men)
            draw_token(surf, t, "player", (cx + 14, cy + 16), hp_frac=hp, radius=12)
            text(surf, fit(f"{len(men)} {t.name}", "smallb", 130), (cx + 32, cy + 2), "smallb")
            tier_badge(surf, t.tier, (cx + 164, cy + 3))
            ranks = [0] * len(RANKS)
            for m in men:
                ranks[m.rank] += 1
            px = cx + 32
            for i, cnt in enumerate(ranks):
                if cnt:
                    r = text(surf, cnt, (px, cy + 18), "tinyb", RANK_COLORS[i])
                    px = r.right + 6
            text(surf, f"{int(hp * 100)}%", (cx + 150, cy + 18), "tiny", C["green"] if hp > .6 else C["gold"])
        if len(order) > 16:
            text(surf, f"+{len(order) - 16} more unit types (press H)", (rect.right - 14, rect.bottom - 18),
                 "tiny", C["muted"], right=True)

    def draw_campaign(self, surf):
        rect = pygame.Rect(812, 556, 448, 194)
        panel(surf, rect)
        x, y = rect.x + 14, rect.y + 8
        reg = self.region
        text(surf, f"Region {self.region_no}: {reg.name}", (x, y), "head")
        taken = sum(t.conquered for t in reg.targets)
        need = reg.boss_needs()
        gate = f"take {need} more to reach the stronghold" if need else f"stronghold: {reg.boss.name}"
        text(surf, fit(f"Taken {taken}/{len(reg.targets)} · Foes: {' & '.join(reg.factions)} · {gate}", "tiny", 420),
             (x, y + 26), "tiny", C["muted"])
        y += 46
        opened = sorted(self.open_targets(), key=lambda t: t.strength())
        for t in opened[:2]:
            draw_token(surf, UNITS[FACTIONS[t.faction]["boss"]], "enemy", (x + 12, y + 16), radius=11, bar=False)
            text(surf, fit(t.name, "bold", 230), (x + 30, y), "bold", FACTIONS[t.faction]["color"])
            text(surf, fit(f"{len(t.garrison)} troops · {t.summary()}", "tiny", 250), (x + 30, y + 19), "tiny",
                 C["muted"])
            self.ui.button(surf, (rect.right - 158, y + 4, 70, 28), "Details",
                           lambda t=t: (setattr(self, "map_sel", t.idx), setattr(self, "scene", "map")),
                           font="smallb")
            self.ui.button(surf, (rect.right - 84, y + 4, 70, 28), "March", lambda t=t: self.attack(t),
                           enabled=self.captain_down <= 0 and bool(self.available()), accent=True, font="smallb")
            y += 42
        self.ui.button(surf, (x, rect.bottom - 40, 200, 30), "War Map (M)", lambda: setattr(self, "scene", "map"),
                       font="smallb")
        text(surf, "The map shows your odds", (rect.right - 14, rect.bottom - 33), "small",
             C["muted"], right=True)

    def draw_map(self, surf, mouse):
        view = surf.subsurface(MAP_RECT)
        reg = self.region
        view.fill(reg.ground)
        rng = random.Random(reg.number * 13)
        for _ in range(180):
            pygame.draw.circle(view, mix(reg.ground, (0, 0, 0), 0.12),
                               (rng.randint(0, MAP_RECT.w), rng.randint(0, MAP_RECT.h)), rng.randint(3, 9))
        pygame.draw.lines(view, (56, 84, 110), False, reg.river, 9)
        pygame.draw.lines(view, (74, 108, 140), False, reg.river, 4)
        for kind, x, y, s in reg.decor:
            if kind == "forest":
                for dx, dy in ((-7, 3), (6, 4), (0, -4)):
                    pygame.draw.polygon(view, (38, 64, 42), [(x + dx, y + dy - 14 * s), (x + dx - 8 * s, y + dy + 6 * s),
                                                             (x + dx + 8 * s, y + dy + 6 * s)])
            elif kind == "mount":
                pygame.draw.polygon(view, (98, 92, 84), [(x, y - 24 * s), (x - 22 * s, y + 10 * s), (x + 22 * s, y + 10 * s)])
                pygame.draw.polygon(view, (200, 198, 190), [(x, y - 24 * s), (x - 6 * s, y - 14 * s), (x + 6 * s, y - 14 * s)])
            elif kind == "hill":
                pygame.draw.ellipse(view, mix(reg.ground, (140, 130, 90), 0.3), (x - 20 * s, y - 8 * s, 40 * s, 16 * s))
            elif kind == "grave":
                pygame.draw.rect(view, (120, 116, 124), (x - 4, y - 10, 8, 12), border_radius=3)
                pygame.draw.line(view, (80, 76, 84), (x - 10, y + 2), (x + 10, y + 2), 2)
            elif kind == "lava":
                pygame.draw.ellipse(view, (150, 60, 30), (x - 14 * s, y - 5 * s, 28 * s, 10 * s))
                pygame.draw.ellipse(view, (240, 140, 50), (x - 7 * s, y - 2 * s, 14 * s, 4 * s))
        opened = self.open_targets()
        for t in reg.targets:
            srcs = [reg.targets[i].pos for i in t.prereq] if t.prereq else [HOME_POS]
            for src in srcs:
                a = src
                on = t in opened or t.conquered
                pygame.draw.line(view, (150, 130, 90) if on else (84, 76, 60), a, t.pos, 5 if on else 3)
        hx, hy = HOME_POS
        pygame.draw.circle(view, C["ink"], (hx, hy), 25)
        pygame.draw.circle(view, C["blue"], (hx, hy), 22)
        draw_glyph(view, "banner", (hx, hy), 24, C["paper"])
        text(view, "Home", (hx, hy + 36), "smallb", center=True)
        for t in reg.targets:
            x, y = t.pos
            sel = t.idx == self.map_sel
            r = 27 if t.boss else 21
            if t in opened:
                draw_glow(view, (x, y), r + 11 + 3 * math.sin(self.time * 3 + t.idx), C["gold"], 70)
            col = C["blue"] if t.conquered else FACTIONS[t.faction]["color"]
            if t not in opened and not t.conquered:
                col = mix(col, (60, 60, 60), 0.5)
            pygame.draw.circle(view, C["ink"], (x, y), r + 3)
            pygame.draw.circle(view, col, (x, y), r)
            glyph = "crown" if t.boss else ("banner" if t.conquered else FACTIONS[t.faction]["glyph"])
            draw_glyph(view, glyph, (x, y), r * 1.1, C["paper"])
            if t.walls and not t.conquered:
                draw_glyph(view, "wall", (x + r - 2, y - r + 2), 12, C["stone"])
            if t.special and not t.conquered:
                pygame.draw.circle(view, C["gold"], (x - r + 3, y - r + 3), 5)
            if sel:
                pygame.draw.circle(view, C["gold"], (x, y), r + 6, 3)
            below = (t.depth % 2 == 0) or t.boss
            ly = y + r + 14 if below else y - r - 26
            text(view, fit(t.name, "smallb", 130), (x, ly), "smallb", center=True)
            if not t.conquered:
                text(view, f"{len(t.garrison)} troops", (x, ly + 14), "tiny",
                     C["muted"] if t not in opened else C["paper"], center=True)
        pygame.draw.rect(surf, C["edge"], MAP_RECT, 2)
        banner = f"Region {reg.number}: {reg.name}"
        pygame.draw.rect(surf, (18, 20, 22), (MAP_RECT.x + 8, MAP_RECT.y + 8, 330, 26), border_radius=4)
        text(surf, banner, (MAP_RECT.x + 16, MAP_RECT.y + 12), "smallb", C["gold"])

    def draw_map_panel(self, surf):
        rect = pygame.Rect(852, 72, 408, 678)
        panel(surf, rect)
        x, y = rect.x + 14, rect.y + 10
        self.ui.button(surf, (x, y, 180, 30), "Back to Town (M)", lambda: setattr(self, "scene", "town"),
                       font="smallb")
        y += 42
        t = self.region.targets[self.map_sel]
        opened = self.open_targets()
        text(surf, fit(t.name, "title", 380), (x, y), "title")
        y += 32
        need = self.region.boss_needs()
        if t.conquered:
            status = "Conquered"
        elif t in opened:
            status = "Can be attacked"
        elif t.boss and need:
            status = f"Take {need} more site{'s' if need > 1 else ''} first"
        else:
            status = "Take a neighbouring site first"
        text(surf, f"{t.faction} · {'Stronghold' if t.boss else 'Depth ' + str(t.depth)}", (x, y), "smallb",
             FACTIONS[t.faction]["color"])
        text(surf, status, (rect.right - 14, y), "smallb",
             C["green"] if t.conquered else (C["gold"] if t in opened else C["muted"]), right=True)
        y += 22
        desc = t.desc
        if t.region_bonus:
            desc += f" Region veterans: +{t.region_bonus} attack, defence and armour."
        for line in wrap(desc, "small", 380)[:3]:
            text(surf, line, (x, y), "small", C["muted"])
            y += 16
        y += 6
        if not t.conquered:
            self.update_odds(t)
            n, w = self.odds["n"], self.odds["w"]
            if not self.available():
                text(surf, "No one is fit to march.", (x, y), "bold", C["red"])
            elif n < 4:
                text(surf, "Scouts are sizing up the garrison" + "." * (1 + int(self.time * 3) % 3), (x, y),
                     "bold", C["muted"])
            else:
                pct = w / n
                verdict, vcol = (("Outmatched", C["red"]) if pct < 0.3 else ("Risky", C["gold"]) if pct < 0.55
                                 else ("Even", C["paper"]) if pct < 0.75 else ("Favourable", C["green"]))
                text(surf, f"Win chance ≈ {int(round(pct * 100))}%  ·  {verdict}", (x, y), "bold", vcol)
                text(surf, f"{n} test battles", (rect.right - 14, y + 2), "small", C["muted"], right=True)
            y += 26
            text(surf, f"Garrison: {len(t.garrison)} (grows to {t.cap})", (x, y), "bold")
            y += 22
            groups = sorted(t.grouped().items(), key=lambda kv: (-UNITS[kv[0]].tier, -len(kv[1])))
            for key, men in groups[:9]:
                u = UNITS[key]
                draw_token(surf, u, "enemy", (x + 12, y + 12), radius=11, bar=False)
                r = text(surf, f"{len(men)} × {u.name}", (x + 30, y), "smallb")
                tier_badge(surf, u.tier, (r.right + 6, y + 2))
                px = x + 30
                ranks = [0] * len(RANKS)
                for m in men:
                    ranks[m.rank] += 1
                for i, cnt in enumerate(ranks):
                    if cnt:
                        rr = text(surf, f"{cnt} {RANKS[i][1]}", (px, y + 15), "tiny", RANK_COLORS[i])
                        px = rr.right + 8
                text(surf, fit(u.attack_line(), "tiny", 170), (rect.right - 14, y + 1), "tiny", C["muted"], right=True)
                y += 34
            if len(groups) > 9:
                text(surf, f"+{len(groups) - 9} more types", (x + 30, y), "tiny", C["muted"])
                y += 16
        y = max(y + 4, rect.bottom - 160)
        text(surf, "Spoils", (x, y), "bold", C["gold"])
        y += 20
        for line in t.reward_lines()[:4]:
            text(surf, fit(line, "small", 380), (x, y), "small")
            y += 17
        ok = t in opened and self.captain_down <= 0 and bool(self.available())
        label = "March!" if ok else ("Captain recovering" if self.captain_down > 0 else
                                     ("Conquered" if t.conquered else "Not reachable yet"))
        self.ui.button(surf, (x, rect.bottom - 50, 380, 38), label, lambda: self.attack(t), enabled=ok, accent=True)

    def draw_region_clear(self, surf):
        shade(surf, 200)
        rc = self.region_clear
        card = pygame.Rect(W // 2 - 330, 170, 660, 400)
        panel(surf, card, C["gold"])
        text(surf, "REGION CLEARED", (W // 2, 220), "big", C["gold"], center=True)
        text(surf, f"{rc['boss']} has fallen. {rc['name']} is yours.", (W // 2, 270), "head", center=True)
        text(surf, f"Sites taken: {rc['taken']}/{rc['total']}   ·   Warband: {len(self.troops())} strong   ·   "
                   f"Time: {fmt_time(self.time)}", (W // 2, 305), "body", C["muted"], center=True)
        nxt = rc["number"] + 1
        lines = [f"Beyond lies region {nxt}: a new land, freshly mapped.",
                 "Its garrisons are larger and more experienced, and raids on your town grow fiercer.",
                 "Your town, army, research and bonuses all come with you."]
        if self.mode == "campaign":
            lines.append("The Ironveil Hold waits in region 3." if nxt == 3 else f"Region {nxt} of 3.")
        else:
            lines.append("Endless War: the Rim never ends. How far can you push?")
        for i, line in enumerate(lines):
            text(surf, line, (W // 2, 350 + i * 24), "body", center=True)
        self.ui.button(surf, (W // 2 - 150, 500, 300, 44), f"March into region {nxt} (Enter)",
                       self.advance_region, accent=True)


# --------------------------------------------------------------------------
# Saving
# --------------------------------------------------------------------------
def save_game(game, path=SAVE_PATH):
    if game is None or game.scene == "battle" or game.over:
        return False
    try:
        with open(path, "wb") as f:
            pickle.dump({"version": SAVE_VERSION, "game": game, "ids": next(Soldier._ids)}, f)
        return True
    except (OSError, pickle.PicklingError, TypeError, AttributeError):
        return False


def load_game(path=SAVE_PATH):
    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
        if data.get("version") != SAVE_VERSION:
            return None
        Soldier._ids = itertools.count(data.get("ids", 100000) + 1)
        return data["game"]
    except Exception:
        return None


def save_info(path=SAVE_PATH):
    if not os.path.exists(path):
        return None
    g = load_game(path)
    if g is None:
        return None
    mode = "Endless" if g.mode == "endless" else "Campaign"
    return f"{mode} · {g.difficulty} · Region {g.region_no} · {fmt_time(g.time)}"


def delete_save(path=SAVE_PATH):
    try:
        os.remove(path)
    except OSError:
        pass


HELP_PAGES = [
    ("Welcome to the Rim", [
        "You rule a small frontier town. Build it up, train a warband and conquer the lands around you.",
        "The town runs in real time. Battles play out on their own: you decide what to build, what to research, "
        "who to train and where to march.",
        "Campaign: clear three regions, then take the final Ironveil stronghold to win.",
        "Endless War: regions never stop coming, each larger and deadlier than the last. Go as far as you can.",
        "You lose if raiders break your town's strength down to zero.",
    ]),
    ("Town and economy", [
        "Click a plot to build or to open a building. Upgrades unlock new units and research.",
        "Gold, iron and essence flow in every second. Markets, mines and Mana Wells raise them; conquered sites add more.",
        "Essence fuels magic: casters, magic buildings and many research topics need it.",
        "Your army cap comes from the Town Hall, Longhouses, Farmsteads and research.",
        "Upgrading the Town Hall opens more building plots and more builder crews (Hall 3 and 5).",
        "Wounded soldiers heal at home. Longhouses, Farmsteads and the Temple speed that up.",
    ]),
    ("Research", [
        "Most buildings have a Research tab. Each topic is a permanent upgrade bought once.",
        "Research can add armour, damage, attack, morale, mana, spell power, ammunition, range, HP, "
        "army cap, income and more.",
        "Higher-level topics need the building upgraded first. The Academy holds the most general upgrades.",
        "Some special sites on the map give permanent bonuses too: relics, armories, banners and shrines.",
    ]),
    ("Battles", [
        "Units deploy by role: soldiers in front, archers behind, casters and healers at the back.",
        "Each round, every unit acts: it casts a spell, shoots, or advances and strikes with every weapon it carries.",
        "Attack roll: attack + d6 against defence + d6 (the dice explode on a 6). "
        "Damage: weapon + d6 against armour + d6.",
        "Surrounded units are easier to hit. Hurt units may flee; big losses shake the whole army.",
        "Your Captain inspires your army. If the Captain falls, morale suffers and they need time to recover.",
        "Battles end when one side is gone, or at nightfall, when the attackers withdraw.",
        "Bigger fights get a bigger battlefield automatically.",
    ]),
    ("Weapons and traits", [
        "Reach: hits from two tiles away.  Charge: only when the unit moved this round.",
        "Repel: long spears strike first and can stop a charge.  Sweep: also hits a second foe.",
        "AP halves armour.  AN ignores it.  Magic weapons can hit ethereal spirits.  Holy hurts the undead.",
        "Stun, poison, drain and fear all do what they say. Slow weapons need a round to reload.",
        "Flying units hop over the lines. Stalkers hunt casters and archers. Guardians protect neighbours.",
        "Hover a unit in battle to see everything about it. The Compendium (C) lists every unit in the game.",
    ]),
    ("Magic and summons", [
        "Casters spend mana on spells and regain some every round.",
        "Druids call wolves, Archdruids call bears. Conjurers call imps, Elementalists fire elementals, "
        "Geomancers earth golems.",
        "High Priestesses call guardian spirits. Gravecallers raise the fallen. Liches bind wraiths.",
        "Summons fight for this battle only, but they benefit from your research.",
        "Fireballs and meteors hit everyone in the blast, friends included.",
    ]),
    ("Ranks, tiers and losses", [
        "Every unit has a tier (T1 to T4): how advanced it is. Every soldier also has a name and a rank:",
        "Recruit, Regular (10 xp), Veteran (30), Elite (65), Champion (115). Each rank adds attack, defence, "
        "HP and morale.",
        "The battle report's Casualties page lists every soldier you lost, with tier, rank, kills and battles.",
        "Losing an Elite or Champion is announced during battle.",
        "The Chronicle (H) keeps your whole warband and a memorial of the fallen.",
    ]),
    ("Tips", [
        "Early on, train a few Spearmen and Archers before attacking anything.",
        "Raids get stronger over time. Walls and Watchtowers help your defenders.",
        "The war map shows rough odds. 'Outmatched' means come back later.",
        "Garrisons grow while you wait, so keep pushing.",
        "Mix your army: tough front line, damage behind it, healers and summoners at the back.",
        "The game autosaves after every battle (you can turn that off in Settings).",
    ]),
]


# --------------------------------------------------------------------------
# App: menus and screens
# --------------------------------------------------------------------------
COMP_TABS = ["Your Army", "Summons", "Ironveil", "Barrow", "Wildkin", "Emberkin"]


def comp_units(tab):
    if tab == "Your Army":
        return [u for u in UNIT_LIST if u.faction == "player"]
    if tab == "Summons":
        return SUMMON_TYPES
    return [u for u in UNIT_LIST if u.faction == tab]


class App:
    def __init__(self, screen):
        self.screen = screen
        self.stack = ["menu"]
        self.game = None
        self.ui = UI()
        self.scroll = 0
        self.t = 0.0
        self.new_mode = "campaign"
        self.new_diff = "Normal"
        self.comp_tab = "Your Army"
        self.comp_sel = "captain"
        self.chron_tab = "Warband"
        self.help_page = 0
        self.flash_msg = ["", 0.0]
        self.running = True
        self.save_label = save_info()
        rng = random.Random(4)
        self.ridges = []
        for layer in range(3):
            pts, x = [], -20
            while x < W + 40:
                pts.append((x, 470 + layer * 70 - rng.randint(20, 130 - layer * 30)))
                x += rng.randint(40, 90)
            self.ridges.append(pts)
        self.embers = [[rng.uniform(0, W), rng.uniform(0, H), rng.uniform(10, 40)] for _ in range(60)]

    @property
    def top(self):
        return self.stack[-1]

    def push(self, name):
        self.scroll = 0
        self.stack.append(name)

    def pop(self):
        if len(self.stack) > 1:
            self.stack.pop()
            self.scroll = 0

    def flash(self, msg):
        self.flash_msg = [msg, 2.5]

    def apply_display(self):
        flags = pygame.SCALED | (pygame.FULLSCREEN if SETTINGS["fullscreen"] else 0)
        try:
            self.screen = pygame.display.set_mode((W, H), flags)
        except pygame.error:
            self.screen = pygame.display.set_mode((W, H))

    # ---- flow ------------------------------------------------------------
    def start_new(self):
        delete_save()
        self.game = Game(self.new_mode, self.new_diff)
        self.stack = ["game"]
        SOUND.play("horn")

    def continue_game(self):
        g = load_game()
        if g is None:
            self.flash("That save could not be loaded.")
            SOUND.play("error")
            return
        self.game = g
        self.stack = ["game"]

    def open_pause(self):
        if self.game and self.game.battle:
            self.game.battle.paused = True
        self.push("pause")

    def do_save(self):
        if save_game(self.game):
            self.flash("Game saved.")
            self.save_label = save_info()
        else:
            self.flash("You can't save during a battle.")
            SOUND.play("error")

    def exit_to_menu(self):
        if self.game and not self.game.over:
            save_game(self.game)
        self.game = None
        self.stack = ["menu"]
        self.save_label = save_info()

    def quit_game(self):
        if self.game and not self.game.over:
            save_game(self.game)
        self.running = False

    # ---- events ----------------------------------------------------------
    def handle(self, event):
        if event.type == pygame.QUIT:
            self.quit_game()
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - event.y * 40)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.top == "game":
                self.game.on_click(event.pos)
            else:
                self.ui.click(event.pos)
        elif event.type == pygame.KEYDOWN:
            self.on_key(event.key)

    def on_key(self, key):
        if key == pygame.K_ESCAPE:
            if self.top == "game":
                self.open_pause()
            elif self.top not in ("menu", "gameover"):
                self.pop()
            return
        if self.top == "game":
            g = self.game
            if g.scene != "battle" and not g.region_clear:
                if key == pygame.K_h:
                    self.push("chronicle")
                    return
                if key == pygame.K_c:
                    self.push("compendium")
                    return
            g.on_key(key)
        elif self.top == "help":
            if key in (pygame.K_RIGHT, pygame.K_d):
                self.help_page = min(len(HELP_PAGES) - 1, self.help_page + 1)
            elif key in (pygame.K_LEFT, pygame.K_a):
                self.help_page = max(0, self.help_page - 1)
        elif self.top == "pause" and key in (pygame.K_p, pygame.K_SPACE):
            self.pop()

    def update(self, dt):
        self.t += dt
        self.flash_msg[1] -= dt
        for e in self.embers:
            e[1] -= e[2] * dt
            e[0] += math.sin(self.t + e[2]) * 8 * dt
            if e[1] < -10:
                e[1], e[0] = H + 10, random.uniform(0, W)
        g = self.game
        if g is None:
            return
        if self.top == "game":
            g.update(dt)
        if g.want_autosave and g.scene != "battle":
            g.want_autosave = False
            if SETTINGS["autosave"] and not g.over:
                save_game(g)
        if g.over and self.top == "game" and g.scene != "battle":
            if g.mode == "endless":
                SETTINGS["best_endless"] = max(SETTINGS["best_endless"], g.score())
            elif g.over == "victory":
                SETTINGS["campaign_wins"] = SETTINGS["campaign_wins"] + 1
            delete_save()
            SOUND.play("victory" if g.over == "victory" else "defeat")
            self.push("gameover")

    # ---- drawing ---------------------------------------------------------
    def draw(self, mouse):
        s = self.screen
        self.ui.reset(mouse)
        base = "game" if "game" in self.stack else "menu"
        if base == "game":
            if self.top == "game":
                self.game.draw(s, mouse, self.open_pause)
            else:
                self.game.draw(s, (-99, -99), lambda: None)
                shade(s, 190)
        else:
            self.draw_backdrop(s)
        screen_fn = {"menu": self.draw_menu, "newgame": self.draw_newgame, "settings": self.draw_settings,
                     "help": self.draw_help, "compendium": self.draw_compendium, "chronicle": self.draw_chronicle,
                     "pause": self.draw_pause, "gameover": self.draw_gameover}.get(self.top)
        if screen_fn:
            screen_fn(s)
        if self.flash_msg[1] > 0:
            r = text(s, self.flash_msg[0], (W // 2, H - 30), "bold", C["gold"], center=True)
            pygame.draw.rect(s, C["gold"], r.inflate(20, 10), 1, border_radius=4)

    def draw_backdrop(self, s):
        for y in range(0, H, 6):
            pygame.draw.rect(s, mix((24, 20, 30), (120, 60, 40), (y / H) ** 1.6), (0, y, W, 6))
        pygame.draw.circle(s, (230, 150, 80), (W - 260, 400), 90)
        for i, pts in enumerate(self.ridges):
            col = mix((40, 30, 36), (14, 12, 16), i / 2)
            pygame.draw.polygon(s, col, pts + [(W + 40, H), (-20, H)])
        for x, y, sp in self.embers:
            pygame.draw.circle(s, (255, 160 + int(sp) % 60, 80), (int(x), int(y)), 2 if sp > 25 else 1)

    def title_block(self, s, title, sub=None, y=70):
        text(s, title, (W // 2, y), "big", C["gold"], center=True)
        if sub:
            text(s, sub, (W // 2, y + 46), "body", C["muted"], center=True)

    def card(self, s, w, h, y=None):
        r = pygame.Rect(W // 2 - w // 2, y if y is not None else H // 2 - h // 2, w, h)
        panel(s, r, C["edge"])
        return r

    def draw_menu(self, s):
        text(s, "WAR ON THE RIM", (W // 2 + 3, 133), "huge", (0, 0, 0), center=True)
        text(s, "WAR ON THE RIM", (W // 2, 130), "huge", C["gold"], center=True)
        text(s, "Build a town. Raise a warband. Conquer the endless frontier.", (W // 2, 190), "head",
             C["paper"], center=True)
        x, y, w = W // 2 - 150, 250, 300

        def new(mode):
            self.new_mode = mode
            self.push("newgame")
        items = [("Continue", self.continue_game, bool(self.save_label), True),
                 ("New Campaign", lambda: new("campaign"), True, not self.save_label),
                 ("Endless War", lambda: new("endless"), True, False),
                 ("Compendium", lambda: self.push("compendium"), True, False),
                 ("Settings", lambda: self.push("settings"), True, False),
                 ("How to Play", lambda: self.push("help"), True, False),
                 ("Quit", self.quit_game, True, False)]
        for label, cb, en, acc in items:
            self.ui.button(s, (x, y, w, 44), label, cb, enabled=en, accent=acc and en, font="head")
            if label == "Continue" and self.save_label:
                text(s, self.save_label, (W // 2, y + 50), "tiny", C["muted"], center=True)
                y += 14
            y += 54
        text(s, f"Best Endless score: {SETTINGS['best_endless']}   ·   Campaigns won: {SETTINGS['campaign_wins']}",
             (W // 2, H - 50), "small", C["muted"], center=True)
        text(s, "v4", (W - 12, H - 20), "tiny", C["dim"], right=True)

    def draw_newgame(self, s):
        card = self.card(s, 720, 520)
        endless = self.new_mode == "endless"
        text(s, "Endless War" if endless else "New Campaign", (W // 2, card.y + 40), "big", C["gold"], center=True)
        desc = ("Region after region, forever. Every region is freshly generated and bigger than the last. "
                "Your score grows with every site you take. How long can your town hold?"
                if endless else
                "Fight across three freshly generated regions. Clear each region's stronghold to push deeper, "
                "then storm the Ironveil stronghold in region 3 to win the war.")
        for i, line in enumerate(wrap(desc, "body", 620)):
            text(s, line, (W // 2, card.y + 100 + i * 22), "body", center=True)
        text(s, "Difficulty", (W // 2, card.y + 190), "head", center=True)
        notes = {"Easy": "Smaller garrisons and raids, slower growth.",
                 "Normal": "The intended challenge.",
                 "Hard": "Bigger, more experienced enemies that grow fast."}
        for i, d in enumerate(("Easy", "Normal", "Hard")):
            self.ui.button(s, (W // 2 - 240 + i * 165, card.y + 225, 150, 40), d,
                           lambda d=d: setattr(self, "new_diff", d), accent=self.new_diff == d)
        text(s, notes[self.new_diff], (W // 2, card.y + 280), "body", C["muted"], center=True)
        if self.save_label:
            text(s, "Starting a new game replaces your saved game:", (W // 2, card.y + 340), "smallb", C["red"],
                 center=True)
            text(s, self.save_label, (W // 2, card.y + 360), "small", C["muted"], center=True)
        self.ui.button(s, (W // 2 - 210, card.bottom - 80, 200, 46), "Back", self.pop)
        self.ui.button(s, (W // 2 + 10, card.bottom - 80, 200, 46), "Begin", self.start_new, accent=True)

    def draw_settings(self, s):
        card = self.card(s, 640, 600)
        text(s, "Settings", (W // 2, card.y + 36), "big", C["gold"], center=True)
        y = card.y + 90
        x0, x1 = card.x + 50, card.x + 330

        def row(label):
            text(s, label, (x0, y + 8), "bold")

        def stepper(key):
            val = SETTINGS[key]
            self.ui.button(s, (x1, y, 36, 32), "-", lambda: self.set_volume(key, -10))
            pygame.draw.rect(s, (30, 32, 36), (x1 + 44, y + 11, 160, 10), border_radius=4)
            pygame.draw.rect(s, C["gold"], (x1 + 44, y + 11, 160 * val / 100, 10), border_radius=4)
            self.ui.button(s, (x1 + 212, y, 36, 32), "+", lambda: self.set_volume(key, 10))
            text(s, f"{val}%", (x1 + 256, y + 8), "bold")

        def toggle(key):
            on = SETTINGS[key]
            self.ui.button(s, (x1, y, 120, 32), "On" if on else "Off", lambda: self.toggle(key), accent=on)

        row("Master volume")
        stepper("master")
        y += 46
        row("Effects volume")
        stepper("sfx")
        y += 46
        row("Mute all sound")
        toggle("mute")
        self.ui.button(s, (x1 + 130, y, 120, 32), "Test sound", lambda: SOUND.play("victory"))
        y += 46
        row("Default battle speed")
        for i, sp in enumerate((1, 2, 4)):
            self.ui.button(s, (x1 + i * 60, y, 52, 32), f"{sp}x", lambda sp=sp: self.set_speed(sp),
                           accent=SETTINGS["battle_speed"] == sp)
        y += 46
        row("Damage numbers in battle")
        toggle("damage_numbers")
        y += 46
        row("Pause when a raid is spotted")
        toggle("raid_pause")
        y += 46
        row("Autosave after battles")
        toggle("autosave")
        y += 46
        row("Fullscreen")
        toggle("fullscreen")
        y += 46
        if not SOUND.ok:
            text(s, "No audio device found: sound is unavailable.", (W // 2, y + 6), "small", C["red"], center=True)
        self.ui.button(s, (W // 2 - 100, card.bottom - 66, 200, 44), "Back", self.pop, accent=True)

    def set_volume(self, key, d):
        SETTINGS[key] = max(0, min(100, SETTINGS[key] + d))
        SOUND.play("click")

    def set_speed(self, sp):
        SETTINGS["battle_speed"] = sp
        if self.game and self.game.battle:
            self.game.battle.speed = sp

    def toggle(self, key):
        SETTINGS[key] = not SETTINGS[key]
        if key == "fullscreen":
            self.apply_display()

    def draw_help(self, s):
        card = self.card(s, 860, 620)
        title, lines = HELP_PAGES[self.help_page]
        text(s, "How to Play", (W // 2, card.y + 30), "head", C["muted"], center=True)
        text(s, title, (W // 2, card.y + 70), "big", C["gold"], center=True)
        y = card.y + 130
        for para in lines:
            for i, line in enumerate(wrap(para, "body", 740)):
                text(s, ("•  " if i == 0 else "    ") + line, (card.x + 50, y), "body")
                y += 22
            y += 10
        self.ui.button(s, (card.x + 40, card.bottom - 64, 140, 40), "< Previous",
                       lambda: setattr(self, "help_page", self.help_page - 1), enabled=self.help_page > 0)
        text(s, f"Page {self.help_page + 1} of {len(HELP_PAGES)}", (W // 2, card.bottom - 52), "bold", center=True)
        self.ui.button(s, (card.right - 180, card.bottom - 64, 140, 40), "Next >",
                       lambda: setattr(self, "help_page", self.help_page + 1),
                       enabled=self.help_page < len(HELP_PAGES) - 1)
        self.ui.button(s, (W // 2 - 60, card.bottom + 10, 120, 36), "Back", self.pop, accent=True)

    def draw_compendium(self, s):
        card = pygame.Rect(30, 20, W - 60, H - 40)
        panel(s, card, C["edge"])
        text(s, "Compendium", (card.x + 20, card.y + 12), "title", C["gold"])
        self.ui.tabs(s, card.x + 220, card.y + 14, COMP_TABS, self.comp_tab, self.set_comp_tab, w=120)
        self.ui.button(s, (card.right - 110, card.y + 12, 90, 32), "Back", self.pop, accent=True)
        units = comp_units(self.comp_tab)
        lst = pygame.Rect(card.x + 16, card.y + 60, 330, card.h - 76)
        pygame.draw.rect(s, (26, 28, 32), lst, border_radius=4)
        row_h = 30
        max_scroll = max(0, len(units) * row_h - lst.h)
        self.scroll = min(self.scroll, max_scroll)
        clip = s.get_clip()
        s.set_clip(lst)
        for i, u in enumerate(units):
            y = lst.y + 4 + i * row_h - self.scroll
            if y < lst.y - row_h or y > lst.bottom:
                continue
            r = pygame.Rect(lst.x + 4, y, lst.w - 8, row_h - 2)
            sel = u.key == self.comp_sel
            if sel or r.collidepoint(self.ui.mouse):
                pygame.draw.rect(s, (70, 58, 36) if sel else (44, 48, 54), r, border_radius=3)
            draw_token(s, u, "enemy" if u.faction not in ("player", "summon") else "player",
                       (r.x + 14, r.centery), radius=11, bar=False)
            text(s, u.name, (r.x + 32, r.y + 6), "bold" if sel else "body")
            tier_badge(s, u.tier, (r.right - 34, r.y + 7))
            if lst.collidepoint(self.ui.mouse):
                self.ui.buttons.append((r.clip(lst), lambda k=u.key: setattr(self, "comp_sel", k)))
        s.set_clip(clip)
        if max_scroll:
            text(s, "scroll for more", (lst.centerx, lst.bottom - 14), "tiny", C["dim"], center=True)
        if self.comp_sel not in [u.key for u in units]:
            self.comp_sel = units[0].key
        self.draw_unit_detail(s, UNITS[self.comp_sel], pygame.Rect(lst.right + 20, lst.y, card.right - lst.right - 36,
                                                                   lst.h))

    def set_comp_tab(self, tab):
        self.comp_tab = tab
        self.scroll = 0
        self.comp_sel = comp_units(tab)[0].key

    def draw_unit_detail(self, s, u, rect):
        x, y = rect.x + 10, rect.y + 6
        team = "enemy" if u.faction not in ("player", "summon") else "player"
        draw_token(s, u, team, (x + 44, y + 48), radius=40, bar=False)
        text(s, u.name, (x + 104, y + 6), "big")
        tier_badge(s, u.tier, (x + 108, y + 72), "bold")
        where = {"player": "Your people", "summon": "Summoned creature"}.get(u.faction, f"Enemy · {u.faction}")
        text(s, where, (x + 150, y + 72), "bold", C["muted"])
        y += 110
        if u.building:
            b = BUILDINGS.get(u.building)
            text(s, f"Trained at: {b.name} level {u.req_level}   ·   Cost: {u.cost_text()}   ·   "
                    f"Training {u.train:.0f}s", (x, y), "body", C["gold"])
            y += 26
        elif u.faction == "summon":
            text(s, "Summoned by: " + ", ".join(SUMMONER_OF.get(u.key, ["—"])), (x, y), "body", C["gold"])
            y += 26
        elif u.key == "captain":
            text(s, "Your commander. Always with the warband.", (x, y), "body", C["gold"])
            y += 26
        for line in wrap(u.desc, "body", rect.w - 20):
            text(s, line, (x, y), "body", C["muted"])
            y += 22
        y += 8
        stats = [("HP", u.hp), ("Attack", u.att), ("Defence", u.defense), ("Armour", u.prot), ("Morale", u.mor),
                 ("Move", u.move)] + ([("Mana", f"{u.mana} (+{u.regen})")] if u.mana else [])
        for i, (k, v) in enumerate(stats):
            bx = x + i * 110
            pygame.draw.rect(s, (36, 39, 44), (bx, y, 100, 52), border_radius=4)
            text(s, k, (bx + 50, y + 13), "small", C["muted"], center=True)
            text(s, v, (bx + 50, y + 35), "head", center=True)
        y += 70
        text(s, "Weapons", (x, y), "head", C["gold"])
        y += 28
        for w in u.weapons:
            text(s, "•  " + w.describe() + (f"  ·  {w.ammo} shots" if w.ammo and w.ammo > 1 else ""),
                 (x + 6, y), "body")
            y += 22
        if not u.weapons:
            text(s, "None", (x + 6, y), "body", C["muted"])
            y += 22
        if u.spells:
            y += 8
            text(s, "Spells", (x, y), "head", C["mana"])
            y += 28
            for k in u.spells:
                sp = SPELLS[k]
                r = text(s, f"•  {sp.name} ({sp.cost} mana)", (x + 6, y), "bold")
                text(s, fit(sp.desc, "body", rect.right - r.right - 20), (r.right + 12, y), "body", C["muted"])
                y += 22
        traits = [TAG_TEXT[t] for t in u.tags if t in TAG_TEXT]
        if u.mounted:
            traits.append("Mounted: vulnerable to anti-rider weapons.")
        if u.big:
            traits.append("Large creature.")
        if traits:
            y += 8
            text(s, "Traits", (x, y), "head", C["gold"])
            y += 28
            for tr in traits:
                text(s, "•  " + tr, (x + 6, y), "body")
                y += 22

    def draw_chronicle(self, s):
        card = pygame.Rect(30, 20, W - 60, H - 40)
        panel(s, card, C["edge"])
        text(s, "Chronicle", (card.x + 20, card.y + 12), "title", C["gold"])
        self.ui.tabs(s, card.x + 200, card.y + 14, ["Warband", "Fallen", "Records"], self.chron_tab,
                     lambda t: (setattr(self, "chron_tab", t), setattr(self, "scroll", 0)), w=120)
        self.ui.button(s, (card.right - 110, card.y + 12, 90, 32), "Back", self.pop, accent=True)
        g = self.game
        body = pygame.Rect(card.x + 20, card.y + 60, card.w - 40, card.h - 76)
        if g is None:
            text(s, "Start a game to keep a chronicle.", body.center, "head", C["muted"], center=True)
            return
        if self.chron_tab == "Records":
            self.draw_records(s, body)
            return
        if self.chron_tab == "Warband":
            heads = [("Name", 0), ("Unit", 170), ("Tier", 350), ("Rank", 410), ("XP", 510), ("Kills", 570),
                     ("Battles", 640), ("HP", 720), ("Status", 820)]
            rows = sorted(g.army, key=lambda v: (-v.xp, -v.t.tier))
        else:
            heads = [("Name", 0), ("Unit", 170), ("Tier", 350), ("Rank", 410), ("XP", 510), ("Kills", 570),
                     ("Battles", 640), ("Fell at", 720), ("Region", 1060)]
            rows = sorted(g.fallen, key=lambda d: (-d["tier"] * 10 - d["rank"] * 8, -d["time"]))
        count = f"{len(rows)} soldiers" if self.chron_tab == "Warband" else f"{len(rows)} fallen"
        text(s, count, (card.x + 580, card.y + 20), "bold", C["muted"])
        for h, dx in heads:
            text(s, h, (body.x + dx, body.y), "smallb", C["muted"])
        lst = pygame.Rect(body.x, body.y + 22, body.w, body.h - 22)
        row_h = 24
        max_scroll = max(0, len(rows) * row_h - lst.h)
        self.scroll = min(self.scroll, max_scroll)
        clip = s.get_clip()
        s.set_clip(lst)
        if not rows:
            text(s, "Nobody yet." if self.chron_tab == "Fallen" else "Your warband is empty.",
                 (lst.x, lst.y + 10), "body", C["muted"])
        for i, row in enumerate(rows):
            y = lst.y + i * row_h - self.scroll
            if y < lst.y - row_h or y > lst.bottom:
                continue
            if i % 2 == 0:
                pygame.draw.rect(s, (36, 39, 44), (lst.x - 4, y, lst.w, row_h - 2))
            if self.chron_tab == "Warband":
                u = row
                vals = [(u.name, C["paper"]), (u.t.name, C["paper"]), None, None, (u.xp, C["paper"]),
                        (u.kills_total, C["paper"]), (u.battles, C["paper"]),
                        (f"{u.hp}/{u.max_hp}", C["green"] if u.hp == u.max_hp else C["gold"]),
                        ("Recovering" if u is g.captain and g.captain_down > 0 else "Ready",
                         C["red"] if u is g.captain and g.captain_down > 0 else C["muted"])]
                tier, rank, t = u.t.tier, u.rank, u.t
            else:
                d = row
                vals = [(d["name"], C["paper"]), (d["unit"], C["paper"]), None, None, (d["xp"], C["paper"]),
                        (d["kills"], C["paper"]), (d["battles"], C["paper"]),
                        (fit(d["where"], "small", 320), C["muted"]), (d["region"], C["muted"])]
                tier, rank, t = d["tier"], d["rank"], UNITS[d["key"]]
            draw_token(s, t, "player", (lst.x + 8, y + 11), radius=8, bar=False)
            for (h, dx), v in zip(heads, vals):
                if v is None:
                    continue
                text(s, fit(v[0], "small", 160) if dx < 350 else v[0],
                     (body.x + dx + (18 if dx == 0 else 0), y + 3), "small", v[1])
            tier_badge(s, tier, (body.x + 352, y + 5))
            rank_text(s, rank, (body.x + 410, y + 3), "smallb")
        s.set_clip(clip)

    def draw_records(self, s, body):
        g = self.game
        r = g.records
        x, y = body.x + 20, body.y + 10
        mode = "Endless War" if g.mode == "endless" else "Campaign"
        lines = [("Mode", f"{mode} · {g.difficulty}"), ("Map seed", g.seed), ("Time played", fmt_time(g.time)),
                 ("Current region", f"{g.region_no}: {g.region.name}"),
                 ("Regions cleared", r["regions_cleared"]), ("Sites conquered", r["conquests"]),
                 ("Battles won / lost", f"{r['battles_won']} / {r['battles_lost']}"),
                 ("Raids repelled", r["raids_repelled"]), ("Enemies slain", r["enemies_slain"]),
                 ("Soldiers lost", r["soldiers_lost"]), ("Promotions earned", r["promotions"]),
                 ("Creatures summoned", r["summons"]), ("Research completed", f"{len(g.researched)}/{len(TECHS)}"),
                 ("Score", g.score())]
        for label, val in lines:
            text(s, label, (x, y), "bold", C["muted"])
            text(s, val, (x + 260, y), "bold")
            y += 30
        rx = body.x + 620
        y = body.y + 10
        text(s, "Warband by rank", (rx, y), "head", C["gold"])
        y += 34
        for i, (_, name) in enumerate(RANKS):
            n = sum(1 for u in g.army if u.rank == i)
            rank_text(s, i, (rx, y), "bold")
            pygame.draw.rect(s, RANK_COLORS[i], (rx + 110, y + 4, min(300, n * 10), 12))
            text(s, n, (rx + 120 + min(300, n * 10), y), "bold")
            y += 26
        y += 20
        text(s, "Fallen by rank", (rx, y), "head", C["red"])
        y += 34
        for i, (_, name) in enumerate(RANKS):
            n = sum(1 for d in g.fallen if d["rank"] == i)
            rank_text(s, i, (rx, y), "bold")
            pygame.draw.rect(s, RANK_COLORS[i], (rx + 110, y + 4, min(300, n * 10), 12))
            text(s, n, (rx + 120 + min(300, n * 10), y), "bold")
            y += 26

    def draw_pause(self, s):
        card = self.card(s, 380, 520)
        text(s, "Paused", (W // 2, card.y + 40), "big", C["gold"], center=True)
        in_battle = self.game.scene == "battle"
        y = card.y + 90
        items = [("Resume", self.pop, True, True),
                 ("Save Game", self.do_save, not in_battle, False),
                 ("Settings", lambda: self.push("settings"), True, False),
                 ("Chronicle", lambda: self.push("chronicle"), True, False),
                 ("Compendium", lambda: self.push("compendium"), True, False),
                 ("How to Play", lambda: self.push("help"), True, False),
                 ("Save & Main Menu", self.exit_to_menu, True, False),
                 ("Save & Quit", self.quit_game, True, False)]
        for label, cb, en, acc in items:
            self.ui.button(s, (card.x + 40, y, card.w - 80, 40), label, cb, enabled=en, accent=acc)
            y += 50
        if in_battle:
            text(s, "Mid-battle: the game saves from before the fight.", (W // 2, card.bottom - 20), "tiny",
                 C["muted"], center=True)

    def draw_gameover(self, s):
        g = self.game
        won = g.over == "victory"
        card = self.card(s, 640, 520)
        text(s, "VICTORY" if won else "THE TOWN HAS FALLEN", (W // 2, card.y + 50), "big",
             C["gold"] if won else C["red"], center=True)
        sub = ("The Ironveil Hold is broken. The Rim is yours." if won else
               f"Your town fell in region {g.region_no}.")
        text(s, sub, (W // 2, card.y + 100), "head", center=True)
        r = g.records
        lines = [f"Time: {fmt_time(g.time)}   ·   Difficulty: {g.difficulty}",
                 f"Sites conquered: {r['conquests']}   ·   Regions cleared: {r['regions_cleared']}",
                 f"Battles won: {r['battles_won']}   ·   lost: {r['battles_lost']}",
                 f"Enemies slain: {r['enemies_slain']}   ·   Soldiers lost: {r['soldiers_lost']}",
                 f"Score: {g.score()}" + (f"   ·   Best: {SETTINGS['best_endless']}" if g.mode == "endless" else "")]
        for i, line in enumerate(lines):
            text(s, line, (W // 2, card.y + 160 + i * 30), "body", center=True)
        vets = sorted(g.army, key=lambda u: -u.xp)[:3]
        if vets:
            text(s, "Finest soldiers: " + ", ".join(f"{u.name} ({u.rank_name} {u.t.name})" for u in vets),
                 (W // 2, card.y + 330), "small", C["muted"], center=True)

        def again():
            self.new_mode = g.mode
            self.new_diff = g.difficulty
            self.start_new()
        self.ui.button(s, (W // 2 - 230, card.bottom - 80, 220, 46), "Main Menu", self.exit_to_menu)
        self.ui.button(s, (W // 2 + 10, card.bottom - 80, 220, 46), "Play Again", again, accent=True)


def main():
    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    pygame.display.set_caption("War on the Rim")
    init_fonts()
    flags = pygame.SCALED | (pygame.FULLSCREEN if SETTINGS["fullscreen"] else 0)
    try:
        screen = pygame.display.set_mode((W, H), flags)
    except pygame.error:
        screen = pygame.display.set_mode((W, H))
    screen.fill(C["bg"])
    text(screen, "Loading...", (W // 2, H // 2), "title", C["gold"], center=True)
    pygame.display.flip()
    SOUND.init()
    clock = pygame.time.Clock()
    app = App(screen)
    while app.running:
        dt = min(clock.tick(FPS) / 1000, 0.05)
        for event in pygame.event.get():
            app.handle(event)
        app.update(dt)
        app.draw(pygame.mouse.get_pos())
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
