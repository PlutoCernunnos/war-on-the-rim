import math
import random
import sys
from dataclasses import dataclass

import pygame


pygame.init()
SCREEN_WIDTH, SCREEN_HEIGHT = 1280, 760
WORLD_RECT = pygame.Rect(0, 0, SCREEN_WIDTH, 650)
PANEL_RECT = pygame.Rect(0, 650, SCREEN_WIDTH, 110)
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Ashen Marches")
clock = pygame.time.Clock()

FONT = pygame.font.SysFont("segoeui", 16)
SMALL_FONT = pygame.font.SysFont("segoeui", 13)
TITLE_FONT = pygame.font.SysFont("georgia", 27, bold=True)

COLORS = {
    "ink": (24, 27, 31),
    "paper": (226, 218, 194),
    "muted": (151, 147, 132),
    "panel": (30, 34, 38),
    "panel_edge": (84, 76, 61),
    "grass": (49, 69, 55),
    "grass_light": (58, 79, 61),
    "gold": (211, 164, 67),
    "red": (191, 73, 59),
    "blue": (80, 145, 182),
    "white": (245, 239, 216),
}


def draw_text(surface, text, position, font=FONT, color=COLORS["paper"]):
    surface.blit(font.render(text, True, color), position)


def distance(first, second):
    return math.hypot(first[0] - second[0], first[1] - second[1])


@dataclass
class Unit:
    position: pygame.Vector2
    team: str
    kind: str = "soldier"
    hp: int = 100
    max_hp: int = 100
    target: object = None
    destination: object = None
    attack_timer: float = 0
    flash_timer: float = 0

    @property
    def speed(self):
        return 82 if self.kind == "soldier" else 48

    @property
    def radius(self):
        return 11 if self.kind == "soldier" else 17

    @property
    def damage(self):
        return 18 if self.kind == "soldier" else 11

    @property
    def attack_range(self):
        return 25 if self.kind == "soldier" else 125

    def alive(self):
        return self.hp > 0

    def update(self, game, dt):
        self.attack_timer = max(0, self.attack_timer - dt)
        self.flash_timer = max(0, self.flash_timer - dt)
        if self.target is not None and not self.target.alive():
            self.target = None

        if self.target is None:
            if self.team == "player":
                candidates = [unit for unit in game.enemies if unit.alive()]
                nearby = min(candidates, key=lambda item: distance(self.position, item.position), default=None)
                if nearby and distance(self.position, nearby.position) < self.attack_range + 36:
                    self.target = nearby
            else:
                candidates = game.player_units + [game.base]
                self.target = min(candidates, key=lambda item: distance(self.position, item.position))

        if self.target is not None:
            target_position = self.target.position
            target_distance = distance(self.position, target_position)
            if target_distance <= self.attack_range + self.target.radius:
                if self.attack_timer <= 0:
                    self.target.hp -= self.damage
                    self.target.flash_timer = 0.12
                    self.attack_timer = 0.78 if self.kind == "soldier" else 1.15
            else:
                self.move_toward(target_position, dt)
        elif self.destination is not None:
            if distance(self.position, self.destination) < 7:
                self.destination = None
            else:
                self.move_toward(self.destination, dt)

    def move_toward(self, destination, dt):
        direction = pygame.Vector2(destination) - self.position
        if direction.length_squared():
            self.position += direction.normalize() * self.speed * dt
            self.position.x = max(20, min(WORLD_RECT.right - 20, self.position.x))
            self.position.y = max(20, min(WORLD_RECT.bottom - 20, self.position.y))

    def draw(self, surface, selected=False):
        if selected:
            pygame.draw.circle(surface, COLORS["gold"], self.position, self.radius + 5, 2)
        if self.flash_timer:
            body_color = COLORS["white"]
        elif self.team == "player":
            body_color = COLORS["blue"]
        else:
            body_color = COLORS["red"]
        pygame.draw.circle(surface, COLORS["ink"], self.position, self.radius + 2)
        pygame.draw.circle(surface, body_color, self.position, self.radius)
        if self.kind == "soldier":
            pygame.draw.line(surface, COLORS["paper"], (self.position.x - 5, self.position.y - 4),
                             (self.position.x + 7, self.position.y + 6), 2)
        else:
            pygame.draw.circle(surface, COLORS["gold"], self.position, 5)
        bar_width = self.radius * 2 + 8
        pygame.draw.rect(surface, (37, 35, 31), (self.position.x - bar_width / 2, self.position.y - self.radius - 9, bar_width, 4))
        pygame.draw.rect(surface, (104, 184, 92), (self.position.x - bar_width / 2, self.position.y - self.radius - 9, bar_width * max(0, self.hp) / self.max_hp, 4))


@dataclass
class Base:
    position: pygame.Vector2
    hp: int = 700
    max_hp: int = 700
    production: float = 0
    flash_timer: float = 0

    radius: int = 38

    def alive(self):
        return self.hp > 0

    def update(self, game, dt):
        self.production += dt
        self.flash_timer = max(0, self.flash_timer - dt)
        if self.production >= 3.5 and game.gold >= 25:
            self.production -= 3.5
            game.gold -= 25
            offset = pygame.Vector2(random.randint(-42, 42), random.randint(-42, 42))
            game.player_units.append(Unit(self.position + offset, "player"))

    def draw(self, surface):
        color = COLORS["white"] if self.flash_timer else (76, 122, 124)
        pygame.draw.circle(surface, COLORS["ink"], self.position, self.radius + 5)
        pygame.draw.circle(surface, color, self.position, self.radius)
        pygame.draw.polygon(surface, COLORS["gold"], [
            (self.position.x - 25, self.position.y - 14),
            (self.position.x, self.position.y - 52),
            (self.position.x + 25, self.position.y - 14),
        ])
        pygame.draw.rect(surface, (35, 45, 47), (self.position.x - 40, self.position.y + 47, 80, 7))
        pygame.draw.rect(surface, (104, 184, 92), (self.position.x - 40, self.position.y + 47, 80 * max(0, self.hp) / self.max_hp, 7))


class Game:
    def __init__(self):
        self.base = Base(pygame.Vector2(170, 330))
        self.player_units = []
        self.enemies = [
            Unit(pygame.Vector2(1030, 180), "enemy", "brute", 170, 170),
            Unit(pygame.Vector2(1100, 230), "enemy", "brute", 170, 170),
            Unit(pygame.Vector2(1035, 255), "enemy", "soldier"),
            Unit(pygame.Vector2(1085, 300), "enemy", "soldier"),
        ]
        self.gold = 160
        self.morale = 100
        self.selected = []
        self.drag_start = None
        self.message = "Raise a warband. Destroy the enemy camp."
        self.message_timer = 5
        self.wave_timer = 18
        self.game_over = False
        self.victory = False

    def living_units(self, team):
        return [unit for unit in (self.player_units if team == "player" else self.enemies) if unit.alive()]

    def update(self, dt):
        if self.game_over:
            return
        self.gold = min(999, self.gold + dt * 3.5)
        self.wave_timer -= dt
        self.message_timer = max(0, self.message_timer - dt)
        self.base.update(self, dt)
        for unit in self.player_units + self.enemies:
            if unit.alive():
                unit.update(self, dt)
        self.player_units = [unit for unit in self.player_units if unit.alive()]
        self.enemies = [unit for unit in self.enemies if unit.alive()]

        if self.wave_timer <= 0 and self.enemies:
            self.wave_timer = 24
            self.enemies.append(Unit(pygame.Vector2(1160, random.randint(90, 560)), "enemy"))
            self.message = "The enemy sends reinforcements."
            self.message_timer = 3
        if not self.enemies:
            self.game_over = True
            self.victory = True
            self.message = "Victory. The pass belongs to your banner."
        elif not self.base.alive():
            self.game_over = True
            self.message = "Your home base has fallen. Press R to try again."

    def command_selected(self, position):
        for unit in self.selected:
            if unit.alive():
                unit.destination = pygame.Vector2(position)
                unit.target = None

    def attack_at(self, position):
        target = min(self.enemies, key=lambda unit: distance(unit.position, position), default=None)
        if target and distance(target.position, position) < target.radius + 18:
            for unit in self.selected:
                unit.target = target
                unit.destination = None
            return True
        return False

    def select_box(self, rectangle):
        self.selected = [unit for unit in self.player_units if rectangle.collidepoint(unit.position)]

    def draw_world(self, surface):
        surface.fill(COLORS["grass"])
        for x in range(0, WORLD_RECT.width, 48):
            pygame.draw.line(surface, COLORS["grass_light"], (x, 0), (x, WORLD_RECT.bottom), 1)
        for y in range(0, WORLD_RECT.height, 48):
            pygame.draw.line(surface, COLORS["grass_light"], (0, y), (WORLD_RECT.right, y), 1)
        pygame.draw.rect(surface, (42, 51, 46), (880, 75, 290, 285), 2)
        draw_text(surface, "IRONVEIL CAMP", (900, 92), SMALL_FONT, COLORS["muted"])
        pygame.draw.rect(surface, (75, 58, 45), (620, 450, 150, 60))
        pygame.draw.rect(surface, (115, 88, 56), (635, 465, 120, 10))
        draw_text(surface, "old road", (664, 525), SMALL_FONT, COLORS["muted"])
        self.base.draw(surface)
        for enemy in self.enemies:
            enemy.draw(surface)
        for unit in self.player_units:
            unit.draw(surface, unit in self.selected)
        if self.drag_start:
            current = pygame.mouse.get_pos()
            selection_rect = pygame.Rect(
                self.drag_start,
                (current[0] - self.drag_start[0], current[1] - self.drag_start[1]),
            )
            selection_rect.normalize()
            pygame.draw.rect(surface, (117, 177, 191), selection_rect, 1)
            overlay = pygame.Surface(selection_rect.size, pygame.SRCALPHA)
            overlay.fill((117, 177, 191, 35))
            surface.blit(overlay, selection_rect.topleft)

    def draw_panel(self, surface):
        pygame.draw.rect(surface, COLORS["panel"], PANEL_RECT)
        pygame.draw.line(surface, COLORS["panel_edge"], (0, 650), (SCREEN_WIDTH, 650), 2)
        draw_text(surface, "ASHEN MARCHES", (24, 665), TITLE_FONT, COLORS["paper"])
        draw_text(surface, "HOLD THE PASS", (27, 699), SMALL_FONT, COLORS["muted"])
        draw_text(surface, f"GOLD  {int(self.gold):03d}", (290, 673), FONT, COLORS["gold"])
        draw_text(surface, f"WARband  {len(self.player_units)}", (410, 673), FONT, COLORS["blue"])
        draw_text(surface, f"HOSTILES  {len(self.enemies)}", (565, 673), FONT, COLORS["red"])
        draw_text(surface, "Left click: select   Right click: move / attack   R: restart", (290, 704), SMALL_FONT, COLORS["muted"])
        if self.message_timer > 0 or self.game_over:
            pygame.draw.rect(surface, (45, 43, 38), (820, 674, 430, 47), border_radius=3)
            draw_text(surface, self.message, (837, 690), SMALL_FONT, COLORS["paper"])

    def draw(self, surface):
        self.draw_world(surface)
        self.draw_panel(surface)
        if self.game_over:
            shade = pygame.Surface(WORLD_RECT.size, pygame.SRCALPHA)
            shade.fill((10, 12, 14, 135))
            surface.blit(shade, (0, 0))
            headline = "VICTORY" if self.victory else "DEFEAT"
            draw_text(surface, headline, (SCREEN_WIDTH // 2 - 75, 270), TITLE_FONT, COLORS["gold"] if self.victory else COLORS["red"])
            draw_text(surface, "Press R to restart", (SCREEN_WIDTH // 2 - 69, 310), FONT, COLORS["paper"])


def restart_game():
    return Game()


game = Game()
running = True
while running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            game = restart_game()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and event.pos[1] < WORLD_RECT.bottom:
            game.drag_start = event.pos
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and event.pos[1] < WORLD_RECT.bottom:
            if game.drag_start:
                selection_rect = pygame.Rect(
                    game.drag_start,
                    (event.pos[0] - game.drag_start[0], event.pos[1] - game.drag_start[1]),
                )
                selection_rect.normalize()
                if selection_rect.width < 8 and selection_rect.height < 8:
                    clicked = min(game.player_units, key=lambda unit: distance(unit.position, event.pos), default=None)
                    game.selected = [clicked] if clicked and distance(clicked.position, event.pos) < clicked.radius + 12 else []
                else:
                    game.select_box(selection_rect)
                game.drag_start = None
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and event.pos[1] < WORLD_RECT.bottom:
            if not game.attack_at(event.pos):
                game.command_selected(event.pos)

    game.update(dt)
    game.draw(screen)
    pygame.display.flip()

pygame.quit()
sys.exit()