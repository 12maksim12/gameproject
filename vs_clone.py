import pygame
import random
import math
import sys
from collections import deque

SCREEN_W, SCREEN_H = 960, 640
FPS = 60

PLAYER_SPEED = 160
PLAYER_SPRINT_MULT = 1.6

BASE_FIRE_COOLDOWN = 0.45 
BASE_PROJECTILE_SPEED = 320
BASE_PROJECTILE_DAMAGE = 6

ENEMY_BASE_HP = 6
ENEMY_BASE_SPEED = 45
ENEMY_SPAWN_INTERVAL = 1.0 
ENEMY_SPAWN_ACCEL = 0.98  

MAX_ENEMIES = 220

XP_PER_KILL = 8
XP_TO_LEVEL_BASE = 30

POOL_PROJECTILES = 120
POOL_XP = 80
POOL_ENEMIES = 220
C_BG = (18, 18, 28)
C_PLAYER = (170, 200, 255)
C_PROJECTILE = (255, 155, 60)
C_ENEMY = (220, 90, 90)
C_XP = (200, 240, 120)
C_UI = (210, 210, 230)

pygame.init()
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
clock = pygame.time.Clock()
font = pygame.font.SysFont("consolas", 18)
bigfont = pygame.font.SysFont("consolas", 36)

CHAR_SHEET = pygame.image.load("character-sheet.png").convert_alpha()

def vec(x=0, y=0):
    return pygame.math.Vector2(x, y)

def clamp(n, a, b):
    return max(a, min(b, n))

def rand_edge_pos(margin=30):
    side = random.choice(['top', 'bottom', 'left', 'right'])
    if side == 'top':
        return vec(random.uniform(-margin, SCREEN_W + margin), -margin)
    if side == 'bottom':
        return vec(random.uniform(-margin, SCREEN_W + margin), SCREEN_H + margin)
    if side == 'left':
        return vec(-margin, random.uniform(-margin, SCREEN_H + margin))
    return vec(SCREEN_W + margin, random.uniform(-margin, SCREEN_H + margin))

class ObjectPool:
    def __init__(self, cls, size, *args, **kwargs):
        self.cls = cls
        self.free = []
        self.all = []
        for _ in range(size):
            o = cls(*args, **kwargs)
            o.active = False
            self.free.append(o)
            self.all.append(o)

    def acquire(self, *args, **kwargs):
        if self.free:
            o = self.free.pop()
            o.reset(*args, **kwargs)
            o.active = True
            return o
        else:
            o = self.cls(*args, **kwargs)
            o.active = True
            self.all.append(o)
            return o

    def release(self, o):
        o.active = False
        self.free.append(o)

class Projectile:
    def __init__(self):
        self.active = False
        self.pos = vec()
        self.vel = vec()
        self.speed = BASE_PROJECTILE_SPEED
        self.life = 0.0
        self.max_life = 2.4
        self.damage = BASE_PROJECTILE_DAMAGE
        self.radius = 6
        self.pierce = 0

    def reset(self, pos=(0,0), direction=(1,0), speed=None, damage=None, life=None):
        self.pos = vec(pos)
        d = vec(direction)
        if d.length() == 0:
            d = vec(1,0)
        d = d.normalize()
        self.vel = d * (speed if speed is not None else self.speed)
        self.speed = float(speed if speed is not None else self.speed)
        self.damage = int(damage if damage is not None else self.damage)
        self.max_life = life if life is not None else self.max_life
        self.life = self.max_life
        self.radius = 6
        self.pierce = getattr(self, "pierce", 0)

    def update(self, dt):
        if not self.active: return
        self.pos += self.vel * dt
        self.life -= dt
        if self.life <= 0:
            self.active = False

    def draw(self, surf, cam):
        if not self.active: return
        p = self.pos - cam
        pygame.draw.circle(surf, C_PROJECTILE, (int(p.x), int(p.y)), self.radius)

class XP:
    def __init__(self):
        self.active = False
        self.pos = vec()
        self.radius = 6
        self.value = 1
        self.life = 10.0

    def reset(self, pos=(0,0), value=1):
        self.pos = vec(pos)
        self.value = value
        self.life = 12.0
        self.radius = 6
        self.active = True

    def update(self, dt):
        if not self.active: return
        self.life -= dt
        if self.life <= 0:
            self.active = False

    def draw(self, surf, cam):
        if not self.active: return
        p = self.pos - cam
        pygame.draw.circle(surf, C_XP, (int(p.x), int(p.y)), self.radius)

class Enemy:
    def __init__(self):
        self.active = False
        self.pos = vec()
        self.vel = vec()
        self.speed = ENEMY_BASE_SPEED
        self.hp = ENEMY_BASE_HP
        self.max_hp = ENEMY_BASE_HP
        self.radius = 12
        self.score = 1
        self.xp = XP_PER_KILL

    def reset(self, pos=(0,0), hp=None, speed=None, radius=None, score=None, xp=None):
        self.pos = vec(pos)
        self.vel = vec()
        self.speed = speed if speed is not None else ENEMY_BASE_SPEED
        self.max_hp = hp if hp is not None else ENEMY_BASE_HP
        self.hp = self.max_hp
        self.radius = radius if radius is not None else 12
        self.score = score if score is not None else 1
        self.xp = xp if xp is not None else XP_PER_KILL
        self.active = True

    def update(self, dt, player_pos):
        if not self.active: return
        to = player_pos - self.pos
        dist = to.length()
        if dist > 0:
            self.vel = to.normalize() * self.speed
            jitter = vec(random.uniform(-8,8), random.uniform(-8,8))
            self.pos += (self.vel + jitter) * dt

    def draw(self, surf, cam):
        if not self.active: return
        p = self.pos - cam
        pygame.draw.circle(surf, C_ENEMY, (int(p.x), int(p.y)), self.radius)
        ratio = clamp(self.hp / self.max_hp, 0, 1)
        if ratio < 1:
            w = int(self.radius*2 * ratio)
            rect = pygame.Rect(int(p.x - self.radius), int(p.y - self.radius - 8), w, 5)
            pygame.draw.rect(surf, (80, 200, 80), rect)
            outline = pygame.Rect(int(p.x - self.radius), int(p.y - self.radius - 8), self.radius*2, 5)
            pygame.draw.rect(surf, (50,50,50), outline, 1)

class Player:
    def __init__(self, pos):
        self.pos = vec(pos)
        self.radius = 14
        self.speed = float(PLAYER_SPEED)
        self.sprint_mult = PLAYER_SPRINT_MULT
        self.hp = 100
        self.max_hp = 100
        self.fire_cooldown = float(BASE_FIRE_COOLDOWN)
        self.fire_timer = 0.0
        self.projectile_speed = float(BASE_PROJECTILE_SPEED)
        self.projectile_damage = int(BASE_PROJECTILE_DAMAGE)
        self.projectile_count = 1
        self.spread_deg = 0 
        self.pierce = 0
        self.xp = 0
        self.level = 1
        self.xp_to_next = XP_TO_LEVEL_BASE
        self.xp_boost = 0.0
        self.kills = 0

    def update(self, dt, keys):
        dir = vec(0,0)
        if keys[pygame.K_w] or keys[pygame.K_UP]: dir.y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]: dir.y += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]: dir.x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: dir.x += 1
        if dir.length() > 0:
            dir = dir.normalize()
        sprint = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        spd = self.speed * (self.sprint_mult if sprint else 1.0)
        self.pos += dir * spd * dt
        self.pos.x = clamp(self.pos.x, -2000, 2000)
        self.pos.y = clamp(self.pos.y, -2000, 2000)

        if self.fire_timer > 0:
            self.fire_timer -= dt

    def try_fire(self, projectiles_pool, cam_center):
        if self.fire_timer > 0: return []
        self.fire_timer = self.fire_cooldown
        ret = []
        mouse_screen = vec(pygame.mouse.get_pos())
        mouse_world = mouse_screen + cam_center
        base_dir = (mouse_world - self.pos)
        if base_dir.length() == 0:
            base_dir = vec(1,0)
        base_dir = base_dir.normalize()
        n = max(1, self.projectile_count)
        if n == 1:
            proj = projectiles_pool.acquire(pos=self.pos, direction=base_dir,
                                            speed=self.projectile_speed, damage=self.projectile_damage)
            ret.append(proj)
        else:
            spread = self.spread_deg
            mid = (n - 1) / 2.0
            for i in range(n):
                angle = (i - mid) * (spread / max(1, n-1))
                rad = math.radians(angle)
                d = base_dir.rotate_rad(rad)
                proj = projectiles_pool.acquire(pos=self.pos, direction=d,
                                                speed=self.projectile_speed, damage=self.projectile_damage)
                ret.append(proj)
        return ret

    def gain_xp(self, amount):
        self.xp += amount
        leveled = False
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.level += 1
            self.xp_to_next = int(self.xp_to_next * 1.35)
            leveled = True
        return leveled

    def draw(self, surf, cam):
        p = self.pos - cam
        pygame.draw.circle(surf, C_PLAYER, (int(p.x), int(p.y)), self.radius)
        ratio = clamp(self.hp / self.max_hp, 0, 1)
        w = 60
        rect = pygame.Rect(int(p.x - w/2), int(p.y + self.radius + 8), int(w*ratio), 6)
        pygame.draw.rect(surf, (160, 60, 60), rect)
        outline = pygame.Rect(int(p.x - w/2), int(p.y + self.radius + 8), w, 6)
        pygame.draw.rect(surf, (40,40,40), outline, 1)

def upgrade_faster_fire(pl):
    pl.fire_cooldown = max(0.05, pl.fire_cooldown * 0.80)

def upgrade_damage(pl):
    pl.projectile_damage = int(pl.projectile_damage + 3)

def upgrade_more_orbs(pl):
    pl.projectile_count = int(pl.projectile_count + 1)

def upgrade_spread(pl):
    pl.spread_deg = float(pl.spread_deg + 18.0)

def upgrade_pierce(pl):
    pl.pierce = int(getattr(pl, "pierce", 0) + 1)

def upgrade_speed(pl):
    pl.speed = float(pl.speed * 1.10)

def upgrade_maxhp(pl):
    pl.max_hp = int(pl.max_hp + 20)
    pl.hp = int(pl.hp + 20)

def upgrade_proj_speed(pl):
    pl.projectile_speed = float(pl.projectile_speed * 1.20)

def upgrade_xp_boost(pl):
    pl.xp_boost = float(getattr(pl, "xp_boost", 0.0) + 0.25)

UPGRADES = [
    ("Faster Fire", "Fire rate -20%", upgrade_faster_fire),
    ("Damage Up", "Projectile damage +3", upgrade_damage),
    ("More Orbs", "Projectiles count +1", upgrade_more_orbs),
    ("Spread Shot", "Projectile spread +18°", upgrade_spread),
    ("Pierce", "Projectiles pierce +1", upgrade_pierce),
    ("Speed Up", "Move speed +10%", upgrade_speed),
    ("Max HP+", "Max HP +20 (also heals +20)", upgrade_maxhp),
    ("Proj Speed", "Projectile speed +20%", upgrade_proj_speed),
    ("XP Boost", "Gain +25% XP from kills", upgrade_xp_boost),
]

def choose_upgrades(n=3):
    return random.sample(UPGRADES, n)

class SpawnSystem:
    def __init__(self):
        self.timer = 0.0
        self.interval = ENEMY_SPAWN_INTERVAL
        self.time_elapsed = 0.0

    def update(self, dt, game):
        if len(game.enemies) >= MAX_ENEMIES:
            return
        self.timer -= dt
        self.time_elapsed += dt
        if self.timer <= 0:
            self.spawn_enemy(game)
            self.interval = max(0.12, ENEMY_SPAWN_INTERVAL * (0.98 ** (self.time_elapsed / 10.0)))
            self.timer = self.interval

    def spawn_enemy(self, game):
        pos = rand_edge_pos(margin=24) + game.cam_world_offset()
        difficulty_multiplier = 1.0 + (self.time_elapsed / 60.0)  
        e = game.enemy_pool.acquire(
            pos=pos,
            hp=int(ENEMY_BASE_HP * difficulty_multiplier),
            speed=ENEMY_BASE_SPEED * difficulty_multiplier,
            radius=12
        )
        game.enemies.append(e)

class Game:
    def __init__(self):
        self.reset()

    def reset(self):
        self.player = Player(vec(0,0))
        self.projectile_pool = ObjectPool(Projectile, POOL_PROJECTILES)
        self.xp_pool = ObjectPool(XP, POOL_XP)
        self.enemy_pool = ObjectPool(Enemy, POOL_ENEMIES)
        self.projectiles = []
        self.xps = []
        self.enemies = []
        self.spawn = SpawnSystem()
        self.elapsed = 0.0
        self.running = True
        self.paused = False
        self.game_over = False
        self.cam = vec(0,0) 
        self.level_up_pending = False
        self.levelup_options = []
        self.show_levelup = False
        self.best_time = 0.0

    def cam_world_offset(self):
        return self.player.pos

    def world_to_screen(self, pos):
        return pos - self.cam

    def update_cam(self):
        self.cam = self.player.pos - vec(SCREEN_W/2, SCREEN_H/2)

    def spawn_xp(self, pos, value=1):
        xp = self.xp_pool.acquire(pos=pos, value=value)
        self.xps.append(xp)

    def update(self, dt, events):
        if self.paused or self.show_levelup:
            return
        if self.game_over:
            return

        keys = pygame.key.get_pressed()
        self.player.update(dt, keys)
        self.update_cam()
        self.elapsed += dt
        self.spawn.update(dt, self)

        for p in list(self.projectiles):
            p.update(dt)
            if not p.active:
                self.projectile_pool.release(p)
                self.projectiles.remove(p)

        for e in list(self.enemies):
            if not e.active:
                self.enemy_pool.release(e)
                self.enemies.remove(e)
                continue
            e.update(dt, self.player.pos)
            if (e.pos - self.player.pos).length() <= (e.radius + self.player.radius):
                
                self.player.hp -= 12 * dt  
                if self.player.hp <= 0:
                    self.player.hp = 0
                    self.game_over = True
                    self.running = False
                    self.best_time = max(self.best_time, self.elapsed)
           

        for x in list(self.xps):
            x.update(dt)
            if not x.active:
                self.xp_pool.release(x)
                self.xps.remove(x)
                continue
            if (x.pos - self.player.pos).length() <= (x.radius + self.player.radius):
                gained = x.value
                boost = getattr(self.player, "xp_boost", 0.0)
                gained = int(gained * (1.0 + boost))
                leveled = self.player.gain_xp(gained)
                if leveled:
                    self.open_levelup()
                self.xp_pool.release(x)
                self.xps.remove(x)

        for p in list(self.projectiles):
            if not p.active: continue
            for e in list(self.enemies):
                if not e.active: continue
                if (p.pos - e.pos).length() <= (p.radius + e.radius):
                    e.hp -= p.damage
                    if getattr(p, "pierce", 0) <= 0:
                        p.active = False
                    else:
                        p.pierce = getattr(p, "pierce", 0) - 1
                    if e.hp <= 0:
                        e.active = False
                        self.player.kills += 1
                        self.spawn_xp(e.pos, value=e.xp)
                    break  
        fired = []
        if self.player.fire_timer <= 0 and not self.show_levelup:
            newproj = self.player.try_fire(self.projectile_pool, self.cam)
            for pr in newproj:
                pr.pierce = getattr(self.player, "pierce", 0)
                self.projectiles.append(pr)

        

    def open_levelup(self):
        self.show_levelup = True
        self.levelup_options = choose_upgrades(3)

    def apply_upgrade(self, index):
        if not self.show_levelup: return
        if index < 0 or index >= len(self.levelup_options): return
        name, desc, func = self.levelup_options[index]
        try:
            func(self.player)
        except Exception as ex:
            print(f"Error applying upgrade {name}: {ex}")
        self.player.fire_cooldown = max(0.05, float(self.player.fire_cooldown))
        self.player.speed = float(self.player.speed)
        self.player.projectile_speed = float(self.player.projectile_speed)
        self.player.projectile_damage = int(max(0, self.player.projectile_damage))
        self.player.projectile_count = int(max(1, self.player.projectile_count))
        self.player.pierce = int(max(0, getattr(self.player, "pierce", 0)))
        self.player.xp_boost = float(max(0.0, getattr(self.player, "xp_boost", 0.0)))
        self.player.max_hp = int(max(1, self.player.max_hp))
        self.player.hp = int(clamp(self.player.hp, 0, self.player.max_hp))
        self.show_levelup = False

    def draw(self, surf):
        surf.fill(C_BG)

        for x in self.xps:
            x.draw(surf, self.cam)
        for e in self.enemies:
            e.draw(surf, self.cam)
        for p in self.projectiles:
            p.draw(surf, self.cam)
        self.player.draw(surf, self.cam)

        hud = font.render(f"Time: {int(self.elapsed)}s   Level: {self.player.level}   XP: {self.player.xp}/{self.player.xp_to_next}   Kills: {self.player.kills}   Enemies: {len(self.enemies)}", True, C_UI)
        surf.blit(hud, (12, 12))

        hint = font.render("WASD move • Mouse aim (auto-shoot) • SHIFT sprint • P pause • R restart", True, (120,120,140))
        surf.blit(hint, (12, SCREEN_H-26))

        if self.show_levelup:
            self.draw_levelup(surf)

        if self.paused and not self.show_levelup:
            txt = bigfont.render("PAUSED", True, (220,220,220))
            surf.blit(txt, (SCREEN_W//2 - txt.get_width()//2, SCREEN_H//2 - txt.get_height()//2))

        if self.game_over:
            txt = bigfont.render("YOU DIED - Press R to restart", True, (250,180,180))
            surf.blit(txt, (SCREEN_W//2 - txt.get_width()//2, SCREEN_H//2 - txt.get_height()//2))

    def draw_levelup(self, surf):
        w = 640; h = 220
        rect = pygame.Rect(SCREEN_W//2 - w//2, SCREEN_H//2 - h//2, w, h)
        pygame.draw.rect(surf, (26,26,36), rect)
        pygame.draw.rect(surf, (100,100,140), rect, 3)
        title = bigfont.render("LEVEL UP! Choose an upgrade", True, (220,220,220))
        surf.blit(title, (rect.x + 18, rect.y + 12))
        for i, (name, desc, func) in enumerate(self.levelup_options):
            x = rect.x + 24 + i * (w//3)
            y = rect.y + 72
            opt_rect = pygame.Rect(x, y, w//3 - 36, 110)
            pygame.draw.rect(surf, (36,36,46), opt_rect)
            pygame.draw.rect(surf, (80,80,110), opt_rect, 2)
            t1 = font.render(f"{i+1}. {name}", True, (220,220,220))
            t2 = font.render(desc, True, (190,190,200))
            surf.blit(t1, (opt_rect.x + 8, opt_rect.y + 8))
            surf.blit(t2, (opt_rect.x + 8, opt_rect.y + 38))
            k = bigfont.render(str(i+1), True, (150,200,250))
            surf.blit(k, (opt_rect.x + opt_rect.w - 42, opt_rect.y + 8))

    def handle_event(self, ev):
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_p:
                if not self.game_over:
                    self.paused = not self.paused
            if ev.key == pygame.K_r:
                # restart
                self.reset()
            if self.show_levelup:
                if ev.key == pygame.K_1:
                    self.apply_upgrade(0)
                elif ev.key == pygame.K_2:
                    self.apply_upgrade(1)
                elif ev.key == pygame.K_3:
                    self.apply_upgrade(2)

def main():
    game = Game()
    running = True
    accum = 0.0

    while running:
        dt = clock.tick(FPS) / 1000.0
        accum += dt
        events = pygame.event.get()
        for ev in events:
            if ev.type == pygame.QUIT:
                running = False
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
            game.handle_event(ev)

        
        keys = pygame.key.get_pressed()

        if not game.paused and not game.show_levelup and not game.game_over:
            
            game.update(dt, events)

        game.draw(screen)
        pygame.display.flip()

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
