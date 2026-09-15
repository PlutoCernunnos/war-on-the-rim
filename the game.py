"""
War on the Rim
--------------
Build your town and train a warband in real time, then send it to war.
Battles play out automatically in rounds, in the spirit of Conquest of
Elysium: troops deploy in formation, advance, shoot, strike, break and
flee on their own. Your choices are what you build and who you bring.

Controls
  Town:   click a plot to select it, use the buttons in the side panel
  Battle: SPACE pause, 1/2/3 speed, S skip to the end, ENTER continue
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
}
FONTS = {}


def init_fonts():
    sans, serif = "segoeui,dejavusans,arial", "georgia,dejavuserif,times"
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
# Unit and building data
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class UnitType:
    key: str
    name: str
    hp: int
    att: int
    defense: int
    dmg: int
    prot: int
    mor: int
    move: int = 1
    rng: int = 0
    ammo: int = 0
    heal: int = 0
    gold: int = 0
    iron: int = 0
    train: float = 5.0
    building: str = ""
    req_level: int = 1
    glyph: str = "sword"
    big: bool = False
    mounted: bool = False
    tags: tuple = ()
    desc: str = ""


UNITS = {u.key: u for u in [
    # Player
    UnitType("captain", "Captain", 17, 11, 11, 6, 3, 15, glyph="banner", big=True,
             tags=("commander",), desc="Leads the warband. Allies fight bravely while the Captain stands."),
    UnitType("militia", "Militia", 9, 8, 8, 4, 1, 8, gold=10, train=4, building="hall",
             glyph="fork", desc="Cheap levies. Break easily."),
    UnitType("spearman", "Spearman", 11, 10, 12, 5, 4, 10, gold=18, iron=4, train=6,
             building="barracks", glyph="spear", tags=("anti_mount",),
             desc="Steady line troops. Bonus damage against riders."),
    UnitType("swordsman", "Swordsman", 13, 12, 12, 7, 6, 11, gold=24, iron=12, train=8,
             building="barracks", req_level=2, glyph="sword", desc="Armoured veterans who hold the centre."),
    UnitType("archer", "Archer", 8, 10, 7, 5, 1, 9, rng=9, ammo=10, gold=20, train=6,
             building="range", glyph="bow", desc="Long range volleys. Stray arrows can hit anyone in a melee."),
    UnitType("crossbow", "Crossbowman", 9, 11, 8, 9, 3, 9, rng=8, ammo=8, gold=26, iron=10,
             train=8, building="range", req_level=2, glyph="xbow", tags=("ap", "reload"),
             desc="Armour-piercing bolts. Shoots every other round."),
    UnitType("knight", "Knight", 20, 13, 13, 9, 9, 13, move=2, gold=50, iron=25, train=14,
             building="stables", glyph="lance", big=True, mounted=True, tags=("charge",),
             desc="Fast heavy cavalry. Hits hard on the charge."),
    UnitType("priest", "Priest", 8, 6, 6, 3, 0, 12, heal=5, gold=32, train=10,
             building="temple", glyph="cross", desc="Heals wounded allies during battle."),
    UnitType("tower", "Tower Archer", 12, 11, 9, 6, 5, 20, rng=10, ammo=12,
             glyph="tower", tags=("static",), desc="Fires from the walls. Never moves."),
    # Ironveil
    UnitType("raider", "Raider", 9, 10, 8, 6, 2, 9, glyph="axe", desc="Ironveil footman."),
    UnitType("slinger", "Slinger", 7, 9, 7, 4, 0, 8, rng=7, ammo=12, glyph="sling",
             desc="Skirmisher with a sling."),
    UnitType("brute", "Brute", 24, 10, 7, 12, 3, 11, glyph="club", big=True,
             desc="Huge and brutal. Hard to put down."),
    UnitType("ironguard", "Ironguard", 14, 12, 12, 8, 6, 12, glyph="helm",
             desc="Ironveil's armoured elite."),
    UnitType("warg", "Warg Rider", 12, 11, 10, 7, 2, 9, move=2, glyph="fang", mounted=True,
             tags=("charge",), desc="Fast raiders on wolfback."),
    UnitType("shaman", "Ash Shaman", 9, 10, 6, 6, 0, 10, rng=6, ammo=6, glyph="star",
             tags=("ap",), desc="Hurls armour-burning cinders."),
    UnitType("warlord", "Warlord", 34, 15, 13, 12, 9, 16, glyph="crown", big=True,
             tags=("commander",), desc="Master of Ironveil."),
]}


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
    BuildingType("hall", "Town Hall", 120, 30, 25, 3,
                 "Heart of the town. Each level adds gold income and 2 army cap. Trains Militia.",
                 (150, 116, 72), "banner"),
    BuildingType("market", "Market", 60, 0, 12, 3, "+1.2 gold per second per level.",
                 (178, 136, 62), "coin"),
    BuildingType("mine", "Iron Mine", 50, 0, 12, 3, "+0.7 iron per second per level.",
                 (112, 118, 128), "pick"),
    BuildingType("longhouse", "Longhouse", 50, 10, 10, 3,
                 "+4 army cap per level. Wounded soldiers recover faster.", (128, 96, 70), "bed"),
    BuildingType("barracks", "Barracks", 70, 15, 15, 2,
                 "Trains Spearmen. Level 2 unlocks Swordsmen.", (132, 72, 60), "sword"),
    BuildingType("range", "Archery Range", 70, 10, 15, 2,
                 "Trains Archers. Level 2 unlocks Crossbowmen.", (90, 120, 70), "bow"),
    BuildingType("stables", "Stables", 110, 40, 22, 1, "Trains Knights.",
                 (120, 100, 60), "lance", (("hall", 2), ("barracks", 1))),
    BuildingType("temple", "Temple", 90, 20, 18, 1, "Trains Priests. Speeds healing at home.",
                 (170, 164, 150), "cross", (("hall", 2),)),
    BuildingType("tower", "Watchtower", 60, 25, 14, 3,
                 "Each level adds a Tower Archer when your town is raided.", (100, 100, 110), "tower"),
]}


def building_cost(key, target_level):
    b = BUILDINGS[key]
    steps = target_level - 2 if key == "hall" else target_level - 1
    mult = 1 + 0.8 * steps
    return int(b.gold * mult), int(b.iron * mult)


def building_time(key, target_level):
    b = BUILDINGS[key]
    steps = target_level - 2 if key == "hall" else target_level - 1
    return b.time * (1 + 0.6 * steps)


def raid_force(n):
    comp = [("raider", 2 + n), ("slinger", 1 + n // 2)]
    if n >= 2:
        comp.append(("brute", n // 2))
    if n >= 3:
        comp.append(("warg", (n - 1) // 2))
        comp.append(("ironguard", (n - 1) // 2))
    if n >= 4:
        comp.append(("shaman", n // 4))
    return comp


class Target:
    def __init__(self, name, desc, garrison, pool, cap, reward, income, final=False):
        self.name, self.desc = name, desc
        self.garrison = [Soldier(k, "enemy") for k, n in garrison for _ in range(n)]
        self.pool, self.cap = pool, cap
        self.reward, self.income, self.final = reward, income, final
        self.conquered = False

    def summary(self):
        counts = {}
        for u in self.garrison:
            counts[u.t.name] = counts.get(u.t.name, 0) + 1
        return ", ".join(f"{n} {k}" for k, n in counts.items())


def make_targets():
    return [
        Target("Rim Outpost", "A palisade watching the road.",
               [("raider", 4), ("slinger", 2)], ["raider", "slinger"], 9, 120, 0.8),
        Target("Ashfang Warcamp", "Wolf pens and war tents.",
               [("raider", 6), ("ironguard", 2), ("brute", 2), ("slinger", 3), ("warg", 2)],
               ["raider", "warg", "slinger", "brute", "ironguard"], 24, 220, 1.2),
        Target("Ironveil Hold", "The Warlord's fortress. Take it to win.",
               [("warlord", 1), ("ironguard", 6), ("brute", 4), ("raider", 6), ("slinger", 5),
                ("warg", 3), ("shaman", 3)],
               ["raider", "brute", "slinger", "warg", "shaman", "ironguard"], 40, 0, 0, final=True),
    ]


# --------------------------------------------------------------------------
# Soldiers
# --------------------------------------------------------------------------
class Soldier:
    _ids = itertools.count(1)

    def __init__(self, key, team):
        self.t = UNITS[key]
        self.team = team
        self.hp = self.t.hp
        self.heal_acc = 0.0
        self.uid = next(Soldier._ids)
        self.reset_for_battle()

    @property
    def max_hp(self):
        return self.t.hp

    @property
    def pos(self):
        return (self.gx, self.gy)

    def reset_for_battle(self):
        self.state = "fight"          # fight / rout / fled / dead
        self.ammo = self.t.ammo
        self.reload = 0
        self.gx = self.gy = 0
        self.prev = (0, 0)
        self.disp_hp = self.hp
        self.disp_dead = False
        self.flash = 0.0


# --------------------------------------------------------------------------
# Drawing helpers
# --------------------------------------------------------------------------
def draw_glyph(surf, glyph, c, s, col):
    x, y = c
    L = pygame.draw.line
    if glyph == "sword":
        L(surf, col, (x - s * .45, y + s * .45), (x + s * .45, y - s * .45), 3)
        L(surf, col, (x - s * .35, y - s * .05), (x + s * .05, y + s * .35), 2)
    elif glyph == "spear":
        L(surf, col, (x - s * .5, y + s * .5), (x + s * .35, y - s * .35), 2)
        pygame.draw.polygon(surf, col, [(x + s * .55, y - s * .55), (x + s * .2, y - s * .38), (x + s * .38, y - s * .2)])
    elif glyph == "fork":
        L(surf, col, (x, y + s * .55), (x, y - s * .2), 2)
        L(surf, col, (x - s * .3, y - s * .2), (x + s * .3, y - s * .2), 2)
        for dx in (-.3, 0, .3):
            L(surf, col, (x + s * dx, y - s * .2), (x + s * dx, y - s * .55), 2)
    elif glyph == "bow":
        pygame.draw.arc(surf, col, (x - s * .55, y - s * .55, s * .9, s * 1.1), -1.3, 1.3, 2)
        L(surf, col, (x - s * .05, y - s * .5), (x - s * .05, y + s * .5), 1)
    elif glyph == "xbow":
        L(surf, col, (x - s * .5, y - s * .1), (x + s * .5, y - s * .1), 3)
        L(surf, col, (x, y - s * .1), (x, y + s * .55), 3)
        pygame.draw.arc(surf, col, (x - s * .5, y - s * .45, s, s * .6), 0.2, 2.94, 2)
    elif glyph == "lance":
        L(surf, col, (x - s * .55, y + s * .55), (x + s * .5, y - s * .5), 3)
        pygame.draw.polygon(surf, col, [(x - s * .1, y + s * .05), (x + s * .15, y - s * .2), (x - s * .35, y - s * .2)])
    elif glyph == "cross":
        L(surf, col, (x, y - s * .55), (x, y + s * .55), 3)
        L(surf, col, (x - s * .35, y - s * .15), (x + s * .35, y - s * .15), 3)
    elif glyph == "banner":
        L(surf, col, (x - s * .35, y + s * .55), (x - s * .35, y - s * .55), 2)
        pygame.draw.polygon(surf, col, [(x - s * .35, y - s * .55), (x + s * .5, y - s * .35), (x - s * .35, y - s * .1)])
    elif glyph == "axe":
        L(surf, col, (x - s * .3, y + s * .55), (x + s * .2, y - s * .5), 2)
        pygame.draw.polygon(surf, col, [(x + s * .1, y - s * .3), (x + s * .55, y - s * .45), (x + s * .45, y)])
    elif glyph == "club":
        L(surf, col, (x - s * .4, y + s * .5), (x + s * .2, y - s * .2), 4)
        pygame.draw.circle(surf, col, (x + s * .25, y - s * .25), s * .28)
    elif glyph == "sling":
        pygame.draw.arc(surf, col, (x - s * .5, y - s * .5, s, s), 3.4, 6.0, 2)
        pygame.draw.circle(surf, col, (x + s * .1, y + s * .3), s * .18)
    elif glyph == "fang":
        pygame.draw.polygon(surf, col, [(x - s * .5, y - s * .4), (x - s * .1, y - s * .4), (x - s * .3, y + s * .5)])
        pygame.draw.polygon(surf, col, [(x + s * .1, y - s * .4), (x + s * .5, y - s * .4), (x + s * .3, y + s * .5)])
    elif glyph == "star":
        for a in range(4):
            ang = a * math.pi / 4
            L(surf, col, (x - math.cos(ang) * s * .55, y - math.sin(ang) * s * .55),
              (x + math.cos(ang) * s * .55, y + math.sin(ang) * s * .55), 2)
    elif glyph == "crown":
        pygame.draw.polygon(surf, col, [(x - s * .55, y + s * .35), (x - s * .55, y - s * .4), (x - s * .25, y - s * .05),
                                         (x, y - s * .5), (x + s * .25, y - s * .05), (x + s * .55, y - s * .4),
                                         (x + s * .55, y + s * .35)])
    elif glyph == "tower":
        pygame.draw.rect(surf, col, (x - s * .35, y - s * .25, s * .7, s * .8))
        for dx in (-.35, -.05, .25):
            pygame.draw.rect(surf, col, (x + s * dx, y - s * .5, s * .15, s * .25))
    elif glyph == "helm":
        pygame.draw.polygon(surf, col, [(x - s * .45, y + s * .45), (x - s * .45, y - s * .15), (x, y - s * .55),
                                         (x + s * .45, y - s * .15), (x + s * .45, y + s * .45)])
        pygame.draw.line(surf, C["ink"], (x - s * .3, y), (x + s * .3, y), 3)
    elif glyph == "coin":
        pygame.draw.circle(surf, col, (x, y), s * .5, 2)
        pygame.draw.circle(surf, col, (x, y), s * .2)
    elif glyph == "pick":
        pygame.draw.arc(surf, col, (x - s * .55, y - s * .55, s * 1.1, s * .8), 0.3, 2.84, 3)
        L(surf, col, (x, y - s * .55), (x, y + s * .55), 3)
    elif glyph == "bed":
        pygame.draw.polygon(surf, col, [(x - s * .55, y), (x, y - s * .5), (x + s * .55, y)], 2)
        pygame.draw.rect(surf, col, (x - s * .4, y, s * .8, s * .45), 2)


def draw_token(surf, t, team, center, hp_frac=1.0, flash=False, routed=False, radius=None, bar=True):
    r = radius or (20 if t.big else 16)
    team_col = C["blue"] if team == "player" else C["red"]
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
    if routed:
        pygame.draw.line(surf, C["paper"], (x + r - 2, y - r), (x + r - 2, y - r - 16), 2)
        pygame.draw.rect(surf, C["white"], (x + r - 1, y - r - 16, 9, 6))


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
MAX_ROUNDS = 40
DIRS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


def tile_center(gx, gy):
    return (FIELD_X + gx * TILE + TILE / 2, FIELD_Y + gy * TILE + TILE / 2)


def cheb(a, b):
    return max(abs(a.gx - b.gx), abs(a.gy - b.gy))


class Battle:
    def __init__(self, kind, title, players, enemies, attacker, target=None):
        self.kind, self.title, self.attacker, self.target = kind, title, attacker, target
        self.defender = "enemy" if attacker == "player" else "player"
        self.units = players + enemies
        self.occ = {}
        for u in self.units:
            u.reset_for_battle()
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
        self.shots, self.strikes, self.floaters = [], {}, []
        self.instant = False
        self.log = [f"The armies deploy: {len(players)} against {len(enemies)}."]
        self.result = None
        self.finished = False
        self.ui = UI()
        self.continue_cb = None

    # ---- setup -----------------------------------------------------------
    def deploy(self, units, team):
        def role(u):
            t = u.t
            if "static" in t.tags:
                return 0
            if "commander" in t.tags or t.heal:
                return 1
            if t.rng:
                return 2
            return 3

        front = sorted([u for u in units if role(u) == 3], key=lambda u: u.t.mounted)
        plan = [(u, [0, 1]) for u in units if role(u) == 0]
        plan += [(u, [1, 0, 2]) for u in units if role(u) == 1]
        plan += [(u, [3, 2, 1]) for u in units if role(u) == 2]
        plan += [(u, [6, 5, 4, 3]) for u in front]
        order = sorted(range(ROWS), key=lambda r: (abs(r - ROWS // 2), r))
        for u, cols in plan:
            spots = [(c, r) for c in cols for r in order] + [(c, r) for c in range(7) for r in order]
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
        return 1 - fighting / max(1, self.start[team])

    def commander_up(self, team):
        return any(v.team == team and v.state == "fight" and "commander" in v.t.tags for v in self.units)

    # ---- effects ---------------------------------------------------------
    def schedule(self, u, label, color, action=None, delay=0.5):
        if self.instant:
            if action:
                action()
            return
        x, y = tile_center(u.gx, u.gy)
        self.floaters.append({"x": x + random.uniform(-6, 6), "y": y - 22, "label": label,
                              "color": color, "delay": ROUND_TIME * delay, "age": 0.0,
                              "action": action})

    def morale_check(self, u, extra=0):
        if u.state != "fight" or "commander" in u.t.tags or "static" in u.t.tags:
            return
        bonus = 2 if self.commander_up(u.team) else (-2 if self.had_commander[u.team] else 0)
        if u.t.mor + bonus + drn() < 7 + int(self.lost_frac(u.team) * 8) + extra + drn():
            u.state = "rout"
            self.schedule(u, "ROUT", C["white"])
            self.round_notes.append(f"{u.t.name} ({'yours' if u.team == 'player' else 'foe'}) flees!")

    def damage(self, a, d, bonus=0, stray=False):
        prot = d.t.prot // 2 if "ap" in a.t.tags else d.t.prot
        dealt = max(0, a.t.dmg + bonus + drn() - (prot + drn()))
        d.hp = max(0, d.hp - dealt)
        dead = d.hp <= 0
        self.round_hits += 1

        def act(u=d, hp=d.hp, dead=dead, dealt=dealt):
            u.disp_hp = hp
            if dealt:
                u.flash = 0.18
            if dead:
                u.disp_dead = True

        label = str(dealt) if dealt else "0"
        color = (255, 214, 120) if bonus else (C["white"] if dealt else C["muted"])
        self.schedule(d, label, color, act)
        if dead:
            d.state = "dead"
            self.occ.pop(d.pos, None)
            who = "your" if d.team == "player" else "enemy"
            self.round_slain.append(f"{who} {d.t.name}")
            if stray and a.team == d.team:
                self.round_notes.append(f"A stray shot killed one of {'your' if a.team == 'player' else 'their'} own!")
        elif d.hp * 2 < d.max_hp:
            self.morale_check(d)

    def melee(self, a, d, charge=False):
        harass = max(0, sum(1 for f in self.foes(d) if cheb(f, d) == 1) - 1)
        defense = d.t.defense - harass - (4 if d.state == "rout" else 0)
        self.strikes[a.uid] = tile_center(d.gx, d.gy)
        if a.t.att + drn() > defense + drn():
            bonus = (4 if charge else 0) + (5 if "anti_mount" in a.t.tags and d.t.mounted else 0)
            self.damage(a, d, bonus)

    def shoot(self, a, d):
        dist = cheb(a, d)
        start = tile_center(a.gx, a.gy)
        if a.t.att + drn() - dist // 3 > 6 + d.t.defense // 3 + drn():
            self.shots.append((start, tile_center(d.gx, d.gy), a.t.glyph))
            self.damage(a, d)
            return
        tx, ty = d.gx + random.randint(-1, 1), d.gy + random.randint(-1, 1)
        self.shots.append((start, tile_center(tx, ty), a.t.glyph))
        victim = self.occ.get((tx, ty))
        if victim is not None and victim is not d and victim is not a:
            self.damage(a, victim, stray=True)

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
        for _ in range(u.t.move):
            if cheb(u, goal) <= stop_range:
                break
            if not self.step_toward(u, goal):
                break
            moved = True
        return moved

    def flee(self, u):
        edge, dx = (0, -1) if u.team == "player" else (COLS - 1, 1)
        for _ in range(u.t.move + 1):
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
    def act(self, u):
        foes = self.foes(u)
        if not foes:
            return
        t = u.t
        adj = [f for f in foes if cheb(u, f) == 1]
        if t.heal:
            hurt = [a for a in self.allies(u) if a.hp < a.max_hp and cheb(u, a) <= 4]
            if hurt:
                a = min(hurt, key=lambda v: v.hp / v.max_hp)
                amount = min(t.heal + random.randint(0, 2), a.max_hp - a.hp)
                a.hp += amount

                def act(v=a, hp=a.hp):
                    v.disp_hp = hp
                self.schedule(a, f"+{amount}", C["green"], act, delay=0.3)
                self.round_heals += amount
            elif adj:
                self.melee(u, random.choice(adj))
            return
        if t.rng and u.ammo > 0 and not adj:
            if u.reload > 0:
                u.reload -= 1
                return
            fighting = [f for f in foes if f.state == "fight" and cheb(u, f) <= t.rng]
            in_range = fighting or [f for f in foes if cheb(u, f) <= t.rng]
            if in_range:
                in_range.sort(key=lambda f: cheb(u, f))
                self.shoot(u, random.choice(in_range[:4]))
                u.ammo -= 1
                if "reload" in t.tags:
                    u.reload = 1
            elif "static" not in t.tags:
                self.advance(u, foes, stop_range=t.rng)
            return
        if "static" in t.tags:
            if adj:
                self.melee(u, random.choice(adj))
            return
        if adj:
            self.melee(u, min(adj, key=lambda f: f.hp))
            return
        moved = self.advance(u, foes)
        adj = [f for f in foes if self.active(f) and cheb(u, f) == 1]
        if adj:
            self.melee(u, min(adj, key=lambda f: f.hp), charge=moved and "charge" in t.tags)

    def resolve_round(self):
        self.round += 1
        self.shots, self.strikes = [], {}
        self.round_hits, self.round_heals = 0, 0
        self.round_slain, self.round_notes = [], []
        for u in self.units:
            u.prev = u.pos
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
        order.sort(key=lambda u: -u.t.move)
        for u in order:
            if u.state == "rout":
                self.flee(u)
            elif u.state == "fight":
                self.act(u)

        line = f"Round {self.round}: {self.round_hits} wounds dealt"
        if self.round_heals:
            line += f", {self.round_heals} healed"
        if self.round_slain:
            line += ". Slain: " + ", ".join(self.round_slain[:5]) + ("..." if len(self.round_slain) > 5 else "")
        self.log.append(line)
        self.log.extend(self.round_notes[:3])

        alive = {team: any(u.team == team and u.state == "fight" for u in self.units) for team in ("player", "enemy")}
        if not alive["player"]:
            self.result = "enemy"
        elif not alive["enemy"]:
            self.result = "player"
        elif self.round >= MAX_ROUNDS:
            self.result = self.defender
            self.log.append("Night falls. The attackers withdraw.")
        if self.result:
            self.log.append("Victory!" if self.result == "player" else "Your army is beaten.")

    def skip(self):
        for f in self.floaters:
            if f["action"] and f["delay"] > 0:
                f["action"]()
        self.floaters.clear()
        self.instant = True
        while not self.result:
            self.resolve_round()
        self.shots, self.strikes = [], {}
        for u in self.units:
            u.prev = u.pos
            u.disp_hp = u.hp
            u.disp_dead = u.state == "dead"
        self.anim_t = 1.0

    # ---- loop --------------------------------------------------------------
    def on_key(self, key):
        if key == pygame.K_SPACE:
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
            if u.disp_dead:
                x, y = tile_center(u.gx, u.gy)
                col = mix(C["blue"] if u.team == "player" else C["red"], C["field"], 0.6)
                pygame.draw.line(surf, col, (x - 9, y - 9), (x + 9, y + 9), 4)
                pygame.draw.line(surf, col, (x - 9, y + 9), (x + 9, y - 9), 4)

        hover = None
        for u in sorted(self.units, key=lambda v: v.gy):
            if u.disp_dead or (u.state == "fled" and self.anim_t >= 0.45):
                continue
            pos = self.unit_screen_pos(u)
            draw_token(surf, u.t, u.team, pos, u.disp_hp / u.max_hp, u.flash > 0, u.state in ("rout", "fled"))
            if math.hypot(mouse[0] - pos[0], mouse[1] - pos[1]) < 20:
                hover = u

        for start, end, glyph in self.shots:
            q = (self.anim_t - 0.15) / 0.4
            if 0 <= q <= 1:
                x = start[0] + (end[0] - start[0]) * q
                y = start[1] + (end[1] - start[1]) * q - math.sin(q * math.pi) * 30
                dx, dy = end[0] - start[0], end[1] - start[1]
                d = math.hypot(dx, dy) or 1
                col = (255, 140, 60) if glyph == "star" else C["white"]
                pygame.draw.line(surf, col, (x - dx / d * 9, y - dy / d * 9), (x, y), 2)

        for f in self.floaters:
            if f["delay"] <= 0:
                a = f["age"]
                img = FONTS["bold"].render(f["label"], True, f["color"])
                img.set_alpha(int(255 * (1 - max(0, a - 0.5) * 2)))
                surf.blit(img, img.get_rect(center=(f["x"], f["y"] - a * 26)))

        # top bar
        pygame.draw.rect(surf, C["panel"], (0, 0, W, 56))
        pygame.draw.line(surf, C["edge"], (0, 56), (W, 56), 2)
        text(surf, self.title, (20, 13), "title")
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
        for i, line in enumerate(self.log[-4:]):
            text(surf, line, (24, ly + 4 + i * 18), "small", C["paper"] if i == len(self.log[-4:]) - 1 else C["muted"])
        text(surf, "SPACE pause · 1/2/3 speed · S skip", (W - 24, ly + 4), "small", C["dim"], right=True)

        if hover and not self.finished:
            t = hover.t
            lines = [f"{t.name}  ({'yours' if hover.team == 'player' else 'enemy'})",
                     f"HP {hover.disp_hp}/{hover.max_hp}   Att {t.att}  Def {t.defense}",
                     f"Dmg {t.dmg}  Prot {t.prot}  Mor {t.mor}"
                     + (f"   Ammo {hover.ammo}" if t.rng else ""),
                     {"rout": "Fleeing!", "fled": "Fled"}.get(hover.state, t.desc)]
            bw = max(FONTS["small"].size(s)[0] for s in lines) + 20
            bx, by = min(mouse[0] + 16, W - bw - 6), min(mouse[1] + 16, H - 90)
            pygame.draw.rect(surf, (18, 20, 22), (bx, by, bw, 80), border_radius=4)
            pygame.draw.rect(surf, C["edge"], (bx, by, bw, 80), 1, border_radius=4)
            for i, s in enumerate(lines):
                text(surf, s, (bx + 10, by + 6 + i * 17), "bold" if i == 0 else "small")

        if self.finished:
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((8, 9, 10, 170))
            surf.blit(shade, (0, 0))
            won = self.result == "player"
            card = pygame.Rect(W // 2 - 260, 150, 520, 250)
            pygame.draw.rect(surf, C["panel"], card, border_radius=8)
            pygame.draw.rect(surf, C["gold"] if won else C["red"], card, 2, border_radius=8)
            text(surf, "VICTORY" if won else "DEFEAT", (W // 2, 200), "big",
                 C["gold"] if won else C["red"], center=True)
            lost = {}
            for u in self.units:
                if u.team == "player" and u.state == "dead" and "static" not in u.t.tags:
                    lost[u.t.name] = lost.get(u.t.name, 0) + 1
            slain = sum(1 for u in self.units if u.team == "enemy" and u.state == "dead")
            fled = sum(1 for u in self.units if u.team == "enemy" and u.state in ("fled", "rout"))
            text(surf, f"Enemies slain: {slain}    Enemies fled: {fled}", (W // 2, 270), "body", center=True)
            loss = ", ".join(f"{n} {k}" for k, n in lost.items()) or "none"
            text(surf, f"Your losses: {loss}", (W // 2, 296), "body", center=True)
            self.ui.button(surf, (W // 2 - 90, 340, 180, 40), "Continue (Enter)", continue_cb, accent=True)


# --------------------------------------------------------------------------
# Town (real time)
# --------------------------------------------------------------------------
class Plot:
    def __init__(self, idx, rect):
        self.idx, self.rect = idx, pygame.Rect(rect)
        self.key = None
        self.level = 0
        self.building = None      # {"target", "remaining", "total"}
        self.queue = []           # [unit_key, remaining, total]


class Game:
    TOWN = pygame.Rect(20, 72, 780, 474)

    def __init__(self):
        self.gold, self.iron = 160.0, 20.0
        self.plots = []
        for i in range(9):
            r, c = divmod(i, 3)
            self.plots.append(Plot(i, (self.TOWN.x + 10 + c * 257, self.TOWN.y + 8 + r * 154, 247, 146)))
        self.plots[4].key, self.plots[4].level = "hall", 1
        self.captain = Soldier("captain", "player")
        self.army = [self.captain] + [Soldier("militia", "player") for _ in range(3)]
        self.captain_down = 0.0
        self.integrity = 3
        self.time = 0.0
        self.raid_timer, self.raid_count, self.raid_warned = 150.0, 0, False
        self.growth_timer = 40.0
        self.targets = make_targets()
        self.bonus_income = 0.0
        self.scene, self.battle = "town", None
        self.selected = 4
        self.toasts = []
        self.over = None
        self.ui = UI()
        self.peons = [{"x": 400.0, "y": 300.0, "tx": 400.0, "ty": 300.0} for _ in range(5)]

    # ---- economy ---------------------------------------------------------
    def level(self, key):
        return max((p.level for p in self.plots if p.key == key), default=0)

    def gold_rate(self):
        return 1.5 + 0.5 * (self.level("hall") - 1) + 1.2 * self.level("market") + self.bonus_income

    def iron_rate(self):
        return 0.3 + 0.7 * self.level("mine")

    def army_cap(self):
        return 6 + 2 * self.level("hall") + 4 * self.level("longhouse")

    def troops(self):
        return [s for s in self.army if s is not self.captain]

    def queued(self):
        return sum(len(p.queue) for p in self.plots)

    def builders_busy(self):
        return any(p.building for p in self.plots)

    def toast(self, msg, color=None):
        self.toasts.append([msg, 4.0, color or C["paper"]])

    def can_build(self, plot, key):
        b = BUILDINGS[key]
        target = plot.level + 1
        if plot.key is None and any(p.key == key for p in self.plots):
            return False, "Already built"
        if target > b.max_level:
            return False, "Max level"
        for rk, rl in b.requires:
            if self.level(rk) < rl:
                return False, f"Needs {BUILDINGS[rk].name} Lv{rl}"
        if self.builders_busy():
            return False, "Builders busy"
        g, i = building_cost(key, target)
        if self.gold < g or self.iron < i:
            return False, "Can't afford"
        return True, ""

    def build(self, plot, key):
        ok, _ = self.can_build(plot, key)
        if not ok:
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
    def next_target(self):
        return next((t for t in self.targets if not t.conquered), None)

    def attack(self, target):
        if self.captain_down > 0 or target is not self.next_target():
            return
        self.battle = Battle("attack", f"Assault on {target.name}", self.available(),
                             target.garrison, attacker="player", target=target)
        self.scene = "battle"

    def start_raid(self):
        self.raid_count += 1
        enemies = [Soldier(k, "enemy") for k, n in raid_force(self.raid_count) for _ in range(n)]
        towers = [Soldier("tower", "player") for _ in range(self.level("tower"))]
        defenders = self.available()
        if not defenders and not towers:
            self.lose_raid()
            return
        self.battle = Battle("defense", f"Raid #{self.raid_count} on your town",
                             defenders + towers, enemies, attacker="enemy")
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
                self.gold += t.reward
                self.bonus_income += t.income
                if t.final:
                    self.over = "victory"
                else:
                    self.toast(f"{t.name} taken! +{t.reward} gold, +{t.income} gold/s.", C["gold"])
            else:
                t.garrison = [u for u in t.garrison if u.state != "dead"]
                for u in t.garrison:
                    u.hp = u.max_hp
                self.toast(f"The assault on {t.name} failed.", C["red"])
        else:
            if won:
                loot = 25 + 10 * self.raid_count
                self.gold += loot
                self.toast(f"Raid repelled! Looted {loot} gold from the fallen.", C["gold"])
            else:
                self.lose_raid()
            self.raid_timer = max(75.0, 130.0 - 6 * self.raid_count)
            self.raid_warned = False
        self.battle = None
        self.scene = "town"

    # ---- update ----------------------------------------------------------
    def update(self, dt):
        if self.over:
            return
        if self.scene == "battle":
            self.battle.update(dt)
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

        self.growth_timer -= dt
        if self.growth_timer <= 0:
            self.growth_timer = 40.0
            for t in self.targets:
                if not t.conquered and len(t.garrison) < t.cap:
                    t.garrison.append(Soldier(random.choice(t.pool), "enemy"))

        self.raid_timer -= dt
        if self.raid_timer <= 30 and not self.raid_warned:
            self.raid_warned = True
            self.toast("Scouts report an Ironveil raid approaching!", C["red"])
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
                pe["tx"] = p.rect.centerx + random.uniform(-60, 60)
                pe["ty"] = p.rect.bottom - random.uniform(8, 24)
            else:
                pe["x"] += dx / d * 45 * dt
                pe["y"] += dy / d * 45 * dt

    # ---- input -----------------------------------------------------------
    def on_click(self, pos):
        if self.scene == "battle":
            self.battle.on_click(pos)
            return
        if self.ui.click(pos):
            return
        for p in self.plots:
            if p.rect.collidepoint(pos):
                self.selected = p.idx

    def on_key(self, key):
        if self.scene == "battle":
            self.battle.on_key(key)

    # ---- drawing ---------------------------------------------------------
    def draw(self, surf, mouse):
        if self.scene == "battle":
            self.battle.draw(surf, mouse, self.finish_battle)
        else:
            self.ui.reset(mouse)
            surf.fill(C["bg"])
            self.draw_topbar(surf)
            self.draw_town(surf)
            self.draw_side(surf)
            self.draw_army(surf)
            self.draw_campaign(surf)
            for i, (msg, life, col) in enumerate(self.toasts[-4:]):
                img = FONTS["bold"].render(msg, True, col)
                img.set_alpha(int(255 * min(1, life)))
                r = img.get_rect(center=(self.TOWN.centerx, 92 + i * 24))
                pygame.draw.rect(surf, (16, 18, 20), r.inflate(20, 6), border_radius=4)
                surf.blit(img, r)
        if self.over:
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((8, 9, 10, 200))
            surf.blit(shade, (0, 0))
            won = self.over == "victory"
            text(surf, "IRONVEIL HAS FALLEN" if won else "YOUR TOWN IS LOST", (W // 2, 300), "big",
                 C["gold"] if won else C["red"], center=True)
            text(surf, f"Time: {int(self.time // 60)}m {int(self.time % 60)}s    Press R to play again",
                 (W // 2, 370), "body", center=True)

    def draw_topbar(self, surf):
        pygame.draw.rect(surf, C["panel"], (0, 0, W, 60))
        pygame.draw.line(surf, C["edge"], (0, 60), (W, 60), 2)
        text(surf, "WAR ON THE RIM", (20, 15), "title")
        x = 290
        pygame.draw.circle(surf, C["gold"], (x, 30), 8)
        text(surf, f"{int(self.gold)}", (x + 14, 14), "head", C["gold"])
        text(surf, f"+{self.gold_rate():.1f}/s", (x + 14, 38), "small", C["muted"])
        x = 420
        pygame.draw.rect(surf, C["iron"], (x - 8, 23, 16, 14), border_radius=2)
        text(surf, f"{int(self.iron)}", (x + 14, 14), "head", C["iron"])
        text(surf, f"+{self.iron_rate():.1f}/s", (x + 14, 38), "small", C["muted"])
        text(surf, f"Warband {len(self.troops())}/{self.army_cap()}", (560, 20), "bold", C["blue"])
        text(surf, "Town", (740, 20), "bold")
        for i in range(3):
            col = C["green"] if i < self.integrity else (60, 60, 60)
            x = 790 + i * 24
            pygame.draw.polygon(surf, col, [(x, 20), (x + 16, 20), (x + 16, 30), (x + 8, 40), (x, 30)])
        col = C["red"] if self.raid_timer < 30 else C["paper"]
        text(surf, f"Next raid in {int(self.raid_timer)}s", (900, 12), "head", col)
        text(surf, f"Raid #{self.raid_count + 1}: " + ", ".join(f"{n} {UNITS[k].name}" for k, n in
                                                                raid_force(self.raid_count + 1)),
             (900, 38), "small", C["muted"])

    def draw_town(self, surf):
        pygame.draw.rect(surf, C["grass"], self.TOWN, border_radius=6)
        for i in range(0, self.TOWN.w, 34):
            for j in range(0, self.TOWN.h, 34):
                if (i * 7 + j * 3) % 5 == 0:
                    pygame.draw.circle(surf, C["grass2"], (self.TOWN.x + i + 10, self.TOWN.y + j + 12), 3)
        hall = self.plots[4].rect.center
        for p in self.plots:
            if p.idx != 4:
                pygame.draw.line(surf, C["road"], hall, p.rect.center, 10)
        for p in self.plots:
            self.draw_plot(surf, p)
        for pe in self.peons:
            pygame.draw.circle(surf, (40, 34, 28), (pe["x"], pe["y"] + 1), 4)
            pygame.draw.circle(surf, (190, 160, 120), (pe["x"], pe["y"] - 5), 3)
        pygame.draw.rect(surf, C["edge"], self.TOWN, 2, border_radius=6)

    def draw_plot(self, surf, p):
        r = p.rect
        sel = p.idx == self.selected
        hover = r.collidepoint(self.ui.mouse)
        pygame.draw.rect(surf, C["dirt"] if p.key else mix(C["grass"], C["dirt"], 0.35), r.inflate(-16, -16), border_radius=8)
        if p.key and (p.level or p.building):
            b = BUILDINGS[p.key]
            lvl = max(p.level, 1)
            cx, base = r.centerx, r.bottom - 38
            w, h = 80 + 14 * lvl, 36 + 6 * lvl
            wall = mix(b.color, C["ink"], 0.25)
            if p.level == 0:
                wall = mix(wall, C["dirt"], 0.6)
            pygame.draw.rect(surf, wall, (cx - w / 2, base - h, w, h))
            roof = mix(b.color, C["ink"], 0.55) if p.level else mix(b.color, C["dirt"], 0.7)
            pygame.draw.polygon(surf, roof, [(cx - w / 2 - 8, base - h), (cx, base - h - 34), (cx + w / 2 + 8, base - h)])
            pygame.draw.rect(surf, C["ink"], (cx - 8, base - 20, 16, 20))
            if p.key in ("hall", "tower"):
                for side in (-1, 1):
                    pygame.draw.rect(surf, wall, (cx + side * w / 2 - 10, base - h - 22, 20, h + 22))
            if b.glyph:
                pygame.draw.circle(surf, mix(b.color, C["paper"], 0.3), (cx, base - h - 12), 13)
                draw_glyph(surf, b.glyph, (cx, base - h - 12), 14, C["ink"])
            if p.building:
                for k in range(4):
                    x = cx - w / 2 - 6 + k * (w + 12) / 3
                    pygame.draw.line(surf, (160, 130, 90), (x, base), (x, base - h - 10), 2)
                pygame.draw.line(surf, (160, 130, 90), (cx - w / 2 - 6, base - h / 2), (cx + w / 2 + 6, base - h / 2), 2)
            text(surf, b.name, (r.x + 14, r.bottom - 32), "bold")
            text(surf, f"Lv {p.level}/{b.max_level}", (r.right - 14, r.bottom - 32), "small",
                 C["muted"], right=True)
            bar = None
            if p.building:
                bar = (1 - p.building["remaining"] / p.building["total"], C["gold"])
            elif p.queue:
                q = p.queue[0]
                bar = (1 - q[1] / q[2], C["blue"])
                text(surf, f"Training {UNITS[q[0]].name}" + (f" +{len(p.queue) - 1}" if len(p.queue) > 1 else ""),
                     (r.x + 14, r.y + 12), "small")
            if bar:
                pygame.draw.rect(surf, (30, 30, 30), (r.x + 14, r.bottom - 14, r.w - 28, 5))
                pygame.draw.rect(surf, bar[1], (r.x + 14, r.bottom - 14, (r.w - 28) * bar[0], 5))
        else:
            text(surf, "+ Empty plot", r.center, "bold", C["muted"], center=True)
        edge = C["gold"] if sel else ((140, 140, 120) if hover else None)
        if edge:
            pygame.draw.rect(surf, edge, r.inflate(-10, -10), 2, border_radius=8)

    def draw_side(self, surf):
        box = pygame.Rect(812, 72, 448, 474)
        pygame.draw.rect(surf, C["panel"], box, border_radius=6)
        pygame.draw.rect(surf, C["edge"], box, 1, border_radius=6)
        p = self.plots[self.selected]
        x, y = box.x + 16, box.y + 12
        if p.key is None:
            text(surf, "Empty plot — choose a building", (x, y), "head")
            y += 34
            options = [k for k in BUILDINGS if k != "hall" and not any(q.key == k for q in self.plots)]
            if not options:
                text(surf, "Every building is already in your town.", (x, y), "body", C["muted"])
            for key in options:
                b = BUILDINGS[key]
                ok, why = self.can_build(p, key)
                g, i = building_cost(key, 1)
                text(surf, b.name, (x, y), "bold")
                cost = f"{g}g" + (f"  {i}i" if i else "")
                text(surf, cost, (x + 150, y), "small", C["gold"])
                text(surf, b.desc if not why or why == "Can't afford" else why,
                     (x, y + 18), "small", C["muted"])
                self.ui.button(surf, (box.right - 84, y + 2, 68, 28), "Build",
                               lambda k=key: self.build(p, k), enabled=ok)
                y += 49
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
            text(surf, f"Building Lv{p.building['target']}... {int(p.building['remaining'])}s", (x, y), "bold", C["gold"])
            pygame.draw.rect(surf, (30, 30, 30), (x, y + 24, box.w - 32, 6))
            pygame.draw.rect(surf, C["gold"], (x, y + 24, (box.w - 32) * pr, 6))
            y += 42
        elif p.level < b.max_level:
            ok, why = self.can_build(p, p.key)
            g, i = building_cost(p.key, p.level + 1)
            label = f"Upgrade to Lv{p.level + 1}   {g}g" + (f" {i}i" if i else "")
            self.ui.button(surf, (x, y, 260, 32), label, lambda: self.build(p, p.key), enabled=ok, accent=ok)
            if why:
                text(surf, why, (x + 272, y + 8), "small", C["red"])
            y += 44
        else:
            text(surf, "Fully upgraded", (x, y), "bold", C["green"])
            y += 30

        units = [u for u in UNITS.values() if u.building == p.key]
        if units:
            pygame.draw.line(surf, C["edge"], (x, y), (box.right - 16, y))
            y += 8
            text(surf, "Train", (x, y), "head")
            y += 30
            for t in units:
                ok, why = self.can_recruit(p, t.key)
                locked = p.level < t.req_level
                draw_token(surf, t, "player", (x + 18, y + 22), radius=15, bar=False)
                text(surf, t.name, (x + 44, y + 2), "bold", C["dim"] if locked else C["paper"])
                cost = f"{t.gold}g" + (f" {t.iron}i" if t.iron else "") + f"  {int(t.train)}s"
                text(surf, cost, (x + 170, y + 3), "small", C["gold"])
                stats = f"HP {t.hp}  Att {t.att}  Def {t.defense}  Dmg {t.dmg}  Prot {t.prot}  Mor {t.mor}"
                if t.rng:
                    stats += f"  Rng {t.rng}"
                text(surf, stats, (x + 44, y + 21), "small", C["muted"])
                text(surf, why if why else t.desc[:52], (x + 44, y + 37), "small",
                     C["red"] if why else C["dim"])
                self.ui.button(surf, (box.right - 84, y + 8, 68, 28), "Train",
                               lambda k=t.key: self.recruit(p, k), enabled=ok)
                y += 60
            if p.queue:
                text(surf, "Queue:", (x, y), "small", C["muted"])
                for i, q in enumerate(p.queue):
                    draw_token(surf, UNITS[q[0]], "player", (x + 70 + i * 36, y + 8), radius=11,
                               hp_frac=1 - q[1] / q[2])

    def draw_army(self, surf):
        box = pygame.Rect(20, 556, 780, 194)
        pygame.draw.rect(surf, C["panel"], box, border_radius=6)
        pygame.draw.rect(surf, C["edge"], box, 1, border_radius=6)
        text(surf, f"Warband  {len(self.troops())}/{self.army_cap()}", (box.x + 16, box.y + 10), "head")
        text(surf, "Wounded soldiers heal while at home.", (box.right - 16, box.y + 16), "small", C["muted"], right=True)
        groups = {}
        for s in self.troops():
            groups.setdefault(s.t.key, []).append(s)
        chips = [("captain", [self.captain])] + list(groups.items())
        for i, (key, members) in enumerate(chips[:12]):
            cx = box.x + 16 + (i % 3) * 252
            cy = box.y + 46 + (i // 3) * 36
            t = UNITS[key]
            hp = sum(m.hp for m in members) / sum(m.max_hp for m in members)
            if key == "captain" and self.captain_down > 0:
                draw_token(surf, t, "player", (cx + 14, cy + 14), 0, routed=True, radius=13)
                text(surf, f"Captain — recovering {int(self.captain_down)}s", (cx + 36, cy + 5), "bold", C["red"])
                continue
            draw_token(surf, t, "player", (cx + 14, cy + 14), hp, radius=13)
            label = t.name if key == "captain" else f"{len(members)} × {t.name}"
            text(surf, label, (cx + 36, cy + 5), "bold")
            text(surf, f"{int(hp * 100)}%", (cx + 236, cy + 7), "small",
                 C["green"] if hp > .8 else C["gold"], right=True)

    def draw_campaign(self, surf):
        box = pygame.Rect(812, 556, 448, 194)
        pygame.draw.rect(surf, C["panel"], box, border_radius=6)
        pygame.draw.rect(surf, C["edge"], box, 1, border_radius=6)
        text(surf, "Campaign", (box.x + 16, box.y + 10), "head")
        nxt = self.next_target()
        y = box.y + 42
        for t in self.targets:
            col = C["green"] if t.conquered else (C["paper"] if t is nxt else C["dim"])
            text(surf, t.name, (box.x + 16, y), "bold", col)
            if t.conquered:
                text(surf, "Taken", (box.right - 16, y + 8), "bold", C["green"], right=True)
            else:
                info = f"{len(t.garrison)} troops: {t.summary()}"
                if FONTS["small"].size(info)[0] > 320:
                    info = info[:52] + "..."
                text(surf, info, (box.x + 16, y + 19), "small", C["muted"])
                if t is nxt:
                    down = self.captain_down > 0
                    self.ui.button(surf, (box.right - 96, y + 4, 80, 30), "March",
                                   lambda tt=t: self.attack(tt), enabled=not down, accent=not down)
            y += 46
        hint = "Your Captain must lead the march." if self.captain_down > 0 else \
            "Garrisons grow over time. Strike when ready."
        text(surf, hint, (box.x + 16, box.bottom - 22), "small", C["dim"])


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
