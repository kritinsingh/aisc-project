"""Small UI toolkit: fonts, gradients, glows, buttons, toggle, slider."""
from __future__ import annotations

import pygame

from . import config as C


# ---------------------------------------------------------------- maths
def clamp(v, a, b):
    return max(a, min(b, v))


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def ease_out_back(t):
    t = clamp(t, 0.0, 1.0)
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# ---------------------------------------------------------------- fonts
class Fonts:
    """Loads fonts once and caches rendered text."""

    NAMES = "segoeui,helveticaneue,helvetica,arial,dejavusans"

    def __init__(self):
        self._fonts = {}
        self._text = {}

    def get(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            try:
                font = pygame.font.SysFont(self.NAMES, size, bold=bold)
            except Exception:
                font = pygame.font.Font(None, size + 6)
            self._fonts[key] = font
        return self._fonts[key]

    def render(self, text, size, color, bold=False):
        key = (text, size, color, bold)
        surf = self._text.get(key)
        if surf is None:
            if len(self._text) > 800:
                self._text.clear()
            surf = self.get(size, bold).render(text, True, color)
            self._text[key] = surf
        return surf

    def draw(self, target, text, size, color, pos, bold=False, anchor="topleft"):
        surf = self.render(text, size, color, bold)
        rect = surf.get_rect(**{anchor: pos})
        target.blit(surf, rect)
        return rect


# ---------------------------------------------------------------- drawing helpers
_grad_cache = {}
_glow_cache = {}


def gradient_surface(w, h, c1, c2, vertical=True, radius=0):
    key = (w, h, c1, c2, vertical, radius)
    cached = _grad_cache.get(key)
    if cached is not None:
        return cached
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    n = h if vertical else w
    for i in range(n):
        color = lerp_color(c1, c2, i / max(1, n - 1))
        if vertical:
            pygame.draw.line(surf, color, (0, i), (w, i))
        else:
            pygame.draw.line(surf, color, (i, 0), (i, h))
    if radius:
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=radius)
        surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    _grad_cache[key] = surf
    return surf


def glow_surface(radius, color):
    key = (radius, color)
    cached = _glow_cache.get(key)
    if cached is not None:
        return cached
    surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for r in range(radius, 0, -1):
        alpha = int(255 * (1 - r / radius) ** 2)
        pygame.draw.circle(surf, (*color, alpha), (radius, radius), r)
    _glow_cache[key] = surf
    return surf


def draw_glow(target, pos, radius, color, strength=1.0):
    surf = glow_surface(radius, color)
    surf.set_alpha(int(255 * clamp(strength, 0, 1)))
    target.blit(surf, surf.get_rect(center=(int(pos[0]), int(pos[1]))))


# ---------------------------------------------------------------- widgets
class Button:
    def __init__(self, rect, label, on_click, kind="normal", icon=None,
                 swatch=None, size=13):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.kind = kind            # "normal" | "primary"
        self.icon = icon            # "play" | None
        self.swatch = swatch        # small colour square before the label
        self.size = size
        self.active = False
        self.hover = 0.0
        self.pressed = False

    def handle(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
            self.pressed = True
            return True
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            was, self.pressed = self.pressed, False
            if was and self.rect.collidepoint(e.pos):
                self.on_click()
                return True
        return False

    def update(self, mouse, dt):
        target = 1.0 if self.rect.collidepoint(mouse) else 0.0
        self.hover += (target - self.hover) * min(1.0, dt * 16)

    def draw(self, surf, fonts):
        r = self.rect.move(0, 1) if self.pressed else self.rect
        if self.kind == "primary":
            surf.blit(gradient_surface(r.w, r.h, C.PRIMARY_A, C.PRIMARY_B, False, 11), r.topleft)
            if self.hover > 0.01:
                lift = pygame.Surface(r.size, pygame.SRCALPHA)
                pygame.draw.rect(lift, (255, 255, 255, int(46 * self.hover)),
                                 lift.get_rect(), border_radius=11)
                surf.blit(lift, r.topleft)
            color, bold = (8, 14, 30), True
        else:
            base = lerp_color(C.PANEL, C.PANEL_HI, self.hover)
            if self.active:
                base = (18, 58, 88)
            border = C.CYAN if self.active else lerp_color(C.BORDER, (86, 106, 160), self.hover)
            pygame.draw.rect(surf, base, r, border_radius=9)
            pygame.draw.rect(surf, border, r, 1, border_radius=9)
            color, bold = (255, 255, 255) if self.active else C.TEXT, self.active

        text = fonts.render(self.label, self.size, color, bold or self.kind == "primary")
        extra = 0
        if self.icon in ("play", "pause", "step"):
            extra = 18
        elif self.swatch:
            extra = 16
        total = text.get_width() + extra
        x = r.centerx - total // 2
        if self.icon == "play":
            cy = r.centery
            pygame.draw.polygon(surf, color, [(x, cy - 6), (x, cy + 6), (x + 11, cy)])
        elif self.icon == "pause":
            cy = r.centery
            pygame.draw.rect(surf, color, (x, cy - 6, 3, 12), border_radius=1)
            pygame.draw.rect(surf, color, (x + 6, cy - 6, 3, 12), border_radius=1)
        elif self.icon == "step":
            cy = r.centery
            pygame.draw.polygon(surf, color, [(x, cy - 5), (x, cy + 5), (x + 7, cy)])
            pygame.draw.rect(surf, color, (x + 9, cy - 5, 2, 10))
        elif self.swatch:
            pygame.draw.rect(surf, self.swatch, (x, r.centery - 5, 10, 10), border_radius=3)
        surf.blit(text, (x + extra, r.centery - text.get_height() // 2))


class Toggle:
    def __init__(self, rect, label, value, on_change):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.value = value
        self.on_change = on_change
        self.anim = 1.0 if value else 0.0

    def handle(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
            self.value = not self.value
            self.on_change(self.value)
            return True
        return False

    def update(self, mouse, dt):
        target = 1.0 if self.value else 0.0
        self.anim += (target - self.anim) * min(1.0, dt * 14)

    def draw(self, surf, fonts):
        r = self.rect
        fonts.draw(surf, self.label, 13, C.TEXT, (r.x, r.centery), anchor="midleft")
        track = pygame.Rect(r.right - 44, r.centery - 11, 44, 22)
        color = lerp_color(C.PANEL_HI, (24, 120, 150), self.anim)
        pygame.draw.rect(surf, color, track, border_radius=11)
        pygame.draw.rect(surf, lerp_color(C.BORDER, C.CYAN, self.anim), track, 1, border_radius=11)
        kx = int(lerp(track.x + 11, track.right - 11, self.anim))
        pygame.draw.circle(surf, (255, 255, 255), (kx, track.centery), 8)


class Slider:
    def __init__(self, rect, label, vmin, vmax, value, on_change):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.vmin, self.vmax = vmin, vmax
        self.value = value
        self.on_change = on_change
        self.dragging = False

    @property
    def track(self):
        return pygame.Rect(self.rect.x, self.rect.y + 28, self.rect.w, 6)

    def _set_from_x(self, x):
        t = clamp((x - self.rect.x) / self.rect.w, 0, 1)
        self.value = int(round(lerp(self.vmin, self.vmax, t)))
        self.on_change(self.value)

    def handle(self, e):
        hit = self.track.inflate(16, 22)
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and hit.collidepoint(e.pos):
            self.dragging = True
            self._set_from_x(e.pos[0])
            return True
        if e.type == pygame.MOUSEMOTION and self.dragging:
            self._set_from_x(e.pos[0])
            return True
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.dragging:
            self.dragging = False
            return True
        return False

    def update(self, mouse, dt):
        pass

    def draw(self, surf, fonts):
        r, tr = self.rect, self.track
        fonts.draw(surf, self.label, 13, C.TEXT, (r.x, r.y + 2))
        fonts.draw(surf, str(self.value), 13, C.MUTED, (r.right, r.y + 2), anchor="topright")
        pygame.draw.rect(surf, C.PANEL_HI, tr, border_radius=3)
        t = (self.value - self.vmin) / (self.vmax - self.vmin)
        fill = pygame.Rect(tr.x, tr.y, max(6, int(tr.w * t)), tr.h)
        surf.blit(gradient_surface(fill.w, fill.h, C.PRIMARY_A, C.PRIMARY_B, False, 3), fill.topleft)
        kx = tr.x + int(tr.w * t)
        pygame.draw.circle(surf, (255, 255, 255), (kx, tr.centery), 8)
        pygame.draw.circle(surf, C.CYAN, (kx, tr.centery), 8, 2)
