"""PixelMate - pikselowy pet na pulpit (Python + PySide6).

Uruchom:  python main.py
"""
import json
import math
import os
import random
import sys
import time

from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import (QAction, QActionGroup, QColor, QCursor, QFont, QFontMetrics,
                           QIcon, QPainter, QPen, QPixmap, QPolygon)
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "assets")
SETTINGS_FILE = os.path.join(BASE, "settings.json")

BOX = 42  # logiczny rozmiar "pola" postaci (w pikselach sprite'a)
SPR_IDLE, SPR_BLINK = "base1.png", "blink1.png"
SPR_FALL = ["falling1.png", "falling2.png", "falling3.png", "falling4.png"]

DEFAULTS = {
    "scale": 4, "mode": "wander", "speech": True, "sleep_idle": True,
    "on_top": True, "water": 0, "stats": {"pets": 0, "throws": 0},
}

PHRASES = {
    "idle": ["Co tam słychać?", "Pamiętaj o wyprostowaniu pleców!", "Nudzi mi się trochę…",
             "Może zrobisz sobie przerwę?", "Fajny ten pulpit!", "Hmm… co by tu zrobić?",
             "Napij się wody 💧", "Mrugam, więc istnieję.", "Dużo dziś pracujesz!",
             "Psst… zapisałeś plik?", "Rozciągnij nadgarstki!"],
    "pat": ["Hihi ♥", "Miło!", "Jeszcze!", "Lubię to ♥", "Mruuu~"],
    "grab": ["Aaa!", "Puść mnie!", "Wiii!", "Hej, ostrożnie!"],
    "thrown": ["WIIIIII!", "Lecę!", "Nie rzucaj mną!"],
    "ouch": ["Au!", "Auć…", "To bolało!"],
}


def now():
    return time.perf_counter()


def clamp(v, a, b):
    return max(a, min(b, v))


def rand(a, b):
    return random.uniform(a, b)


# --------------------------------------------------------------------------- sprite'y
class Sprites:
    def __init__(self):
        self.orig = {}
        self.cache = {}
        for name in [SPR_IDLE, SPR_BLINK, *SPR_FALL]:
            self.orig[name] = QPixmap(os.path.join(ASSETS, name))

    def dim(self, name):
        p = self.orig[name]
        return p.width(), p.height()

    def get(self, name, scale):
        key = (name, scale)
        if key not in self.cache:
            p = self.orig[name]
            self.cache[key] = p.scaled(p.width() * scale, p.height() * scale,
                                       Qt.IgnoreAspectRatio, Qt.FastTransformation)
        return self.cache[key]


# --------------------------------------------------------------------------- okno z peta
class PetWindow(QWidget):
    """Małe okno wielkości postaci – tylko ono łapie kliknięcia myszy."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.apply_flags()

    def apply_flags(self):
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
        if self.app.cfg["on_top"]:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def paintEvent(self, _):
        a = self.app
        p = QPainter(self)
        pm = a.sprites.get(a.current_sprite, a.scale)
        w, h = self.width(), self.height()
        p.translate(w / 2, h)            # punkt zaczepienia: środek podstawy
        p.rotate(a.tilt)
        p.scale(a.sx, a.sy)
        p.drawPixmap(int(-pm.width() / 2), int(-pm.height() + a.bob), pm)

    def mousePressEvent(self, e):
        self.app.on_press(e)

    def mouseMoveEvent(self, e):
        self.app.on_move(e)

    def mouseReleaseEvent(self, e):
        self.app.on_release(e)


# --------------------------------------------------------------------------- nakładka (dymek + efekty)
class Overlay(QWidget):
    """Przezroczysta nakładka na cały ekran – rysuje dymek i serduszka/Zzz. Nie łapie myszy."""

    def __init__(self, app, geo):
        super().__init__()
        self.app = app
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.apply_flags()
        self.setGeometry(geo)
        self.text = None
        self.until = 0
        self.particles = []

    def apply_flags(self):
        flags = (Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
                 | Qt.WindowTransparentForInput)
        if self.app.cfg["on_top"]:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def set_bubble(self, text, seconds):
        self.text, self.until = text, now() + seconds

    def add_particle(self, text, color, x, y, dx):
        self.particles.append({"t": text, "c": color, "x": x, "y": y, "dx": dx, "born": now()})

    def paintEvent(self, _):
        a = self.app
        p = QPainter(self)
        t = now()
        s = a.scale
        # --- cząsteczki
        self.particles = [q for q in self.particles if t - q["born"] < 1.5]
        font = QFont("Courier New")
        font.setBold(True)
        font.setPixelSize(max(12, 4 * s))
        p.setFont(font)
        for q in self.particles:
            k = (t - q["born"]) / 1.5
            p.setOpacity(min(1.0, k / 0.15) * (1 - k))
            x, y = q["x"] + q["dx"] * k, q["y"] - 14 * s * k
            p.setPen(QColor("#2a1a1f"))
            for ox, oy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
                p.drawText(int(x + ox), int(y + oy), q["t"])
            p.setPen(QColor(q["c"]))
            p.drawText(int(x), int(y), q["t"])
        p.setOpacity(1.0)
        # --- dymek
        if self.text and t < self.until:
            self.draw_bubble(p)
        elif self.text:
            self.text = None

    def draw_bubble(self, p):
        a = self.app
        font = QFont("Courier New")
        font.setBold(True)
        font.setPixelSize(15)
        p.setFont(font)
        br = QFontMetrics(font).boundingRect(QRect(0, 0, 240, 1000), Qt.TextWordWrap | Qt.AlignCenter, self.text)
        bw, bh = br.width() + 22, br.height() + 16
        ax, top = a.cx, a.by - a.sprite_h()
        x = clamp(ax - bw / 2, 6, self.width() - bw - 6)
        below = top - bh - 16 < 4
        y = a.by + 12 if below else top - bh - 12
        dark = QColor("#2a1a1f")
        p.fillRect(int(x + 3), int(y + 3), bw, bh, QColor(0, 0, 0, 90))   # cień
        p.fillRect(int(x), int(y), bw, bh, dark)                          # ramka
        p.fillRect(int(x + 3), int(y + 3), bw - 6, bh - 6, QColor("white"))
        tx = clamp(ax, x + 12, x + bw - 12)                                # ogonek
        if below:
            tri = QPolygon([QPoint(int(tx - 7), int(y)), QPoint(int(tx + 7), int(y)), QPoint(int(tx), int(y - 9))])
        else:
            tri = QPolygon([QPoint(int(tx - 7), int(y + bh)), QPoint(int(tx + 7), int(y + bh)), QPoint(int(tx), int(y + bh + 9))])
        p.setPen(Qt.NoPen)
        p.setBrush(dark)
        p.drawPolygon(tri)
        p.setPen(dark)
        p.drawText(QRect(int(x + 11), int(y + 8), br.width(), br.height()), Qt.TextWordWrap | Qt.AlignCenter, self.text)


# --------------------------------------------------------------------------- logika peta
class PixelMate:
    def __init__(self, app):
        self.qapp = app
        self.cfg = self.load_cfg()
        self.sprites = Sprites()

        screen = app.primaryScreen()
        geo, avail = screen.geometry(), screen.availableGeometry()
        self.gx, self.gy = geo.x(), geo.y()
        self.W, self.H = geo.width(), geo.height()
        self.floor = avail.y() + avail.height() - self.gy

        self.win = PetWindow(self)
        self.overlay = Overlay(self, geo)

        # stan
        self.cx = self.W / 2
        self.by = 0.0
        self.vx = self.vy = 0.0
        self.state = "air"
        self.t = 0.0
        self.bounces = 0
        self.walk_dir = 1
        self.target = 0.0
        self.next_t = self.next_talk = self.next_hop = 0.0
        self.blink_at = self.blink_end = 0.0
        self.blinking = False
        self.sleep_reason, self.sleep_until, self.z_at = "", 0.0, 0.0
        self.land_pow = 0.0
        self.last_move = now()
        self.cursor = None
        self.last_cursor = (0, 0)
        self.press = None
        self.last_click = 0.0
        self.current_sprite = SPR_IDLE
        self.sx = self.sy = 1.0
        self.tilt = self.bob = 0.0
        self.ov_was_active = False
        self.pomo = None
        self.pomo_timer = None
        self.water_timer = QTimer()
        self.water_timer.timeout.connect(lambda: self.announce("Czas na szklankę wody 💧"))

        self.apply_scale()
        t0 = now()
        self.blink_at, self.next_talk = t0 + 2, t0 + rand(20, 50)
        self.arm_water()
        self.build_tray()
        self.win.show()
        self.overlay.show()
        self.drop()  # wejście z przytupem

        self.clock = QTimer()
        self.clock.timeout.connect(self.tick)
        self.last_tick = now()
        self.clock.start(16)

    # ---- ustawienia
    def load_cfg(self):
        cfg = json.loads(json.dumps(DEFAULTS))
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            cfg.update({k: v for k, v in saved.items() if k != "stats"})
            cfg["stats"].update(saved.get("stats", {}))
        except (OSError, ValueError):
            pass
        return cfg

    def save_cfg(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=2)
        except OSError:
            pass

    def set_cfg(self, key, value):
        self.cfg[key] = value
        self.save_cfg()
        if key == "scale":
            self.apply_scale()
        elif key == "water":
            self.arm_water()
        elif key == "on_top":
            for w in (self.win, self.overlay):
                w.apply_flags()
                w.show()

    @property
    def scale(self):
        return self.cfg["scale"]

    def apply_scale(self):
        self.win.setFixedSize(BOX * self.scale, BOX * self.scale)
        self.cx = clamp(self.cx, self.half_w(), self.W - self.half_w())
        if self.state not in ("air", "drag"):
            self.by = self.floor

    def sprite_h(self):
        return self.sprites.dim(self.current_sprite)[1] * self.scale

    def half_w(self):
        return self.sprites.dim(self.current_sprite)[0] * self.scale / 2

    def gravity(self):
        return 600 * self.scale

    def set_state(self, s):
        self.state, self.t = s, 0.0
        if s == "idle":
            self.next_t = now() + rand(1.5, 5)

    # ---- dymki i efekty
    def say(self, text, seconds=4.2):
        self.overlay.set_bubble(text, seconds)

    def talk(self):
        self.say(random.choice(PHRASES["idle"]))

    def maybe_say(self, key, chance=1.0):
        if self.cfg["speech"] and random.random() < chance:
            self.say(random.choice(PHRASES[key]), 2.2)

    def announce(self, text):
        if self.state == "sleep":
            self.wake()
        self.say(text, 7)
        self.jump()

    def spawn_fx(self, text, color):
        s = self.scale
        self.overlay.add_particle(text, color, self.cx + rand(-12, 12) * s,
                                  self.by - self.sprite_h() + rand(0, 6) * s, rand(-6, 6) * s)

    # ---- akcje
    def jump(self):
        if self.state == "drag":
            return
        self.vy = -190 * self.scale
        self.vx = self.walk_dir * 40 * self.scale if self.state == "walk" else 0
        self.bounces = 0
        self.set_state("air")

    def sleep_for(self, sec, reason):
        self.sleep_reason = reason
        self.sleep_until = math.inf if sec == math.inf else now() + sec
        self.z_at = 0
        self.set_state("sleep")

    def wake(self, msg=None):
        self.last_move = now()
        self.set_state("idle")
        if msg:
            self.say(msg, 2.5)

    def drop(self):
        self.cx = rand(self.half_w(), self.W - self.half_w())
        self.by, self.vx, self.vy, self.bounces = 0.0, 0.0, 0.0, 0
        self.set_state("air")

    def teleport(self):
        if self.cursor:
            self.cx = clamp(self.cursor[0], self.half_w(), self.W - self.half_w())
            self.by = clamp(self.cursor[1], 8, self.floor)
            self.vx = self.vy = 0.0
            self.bounces = 0
            self.set_state("air")

    def land(self, v):
        self.vx = self.vy = 0.0
        self.bounces = 0
        self.land_pow = clamp(v / (400 * self.scale), 0.3, 1.0)
        if v > 400 * self.scale:
            self.maybe_say("ouch", 0.5)
        self.set_state("land")

    def choose(self):
        t, r = now(), random.random()
        if r < 0.55:
            d = random.choice((-1, 1)) * rand(80, 400)
            self.target = clamp(self.cx + d, self.half_w(), self.W - self.half_w())
            self.set_state("walk")
        elif r < 0.72:
            self.next_t = t + rand(2, 6)
        elif r < 0.82:
            self.jump()
        elif r < 0.90:
            self.sleep_for(rand(15, 40), "timer")
        else:
            if self.cfg["speech"]:
                self.talk()
            self.next_t = t + rand(2, 5)

    # ---- pętla
    def tick(self):
        t = now()
        dt = min(0.05, t - self.last_tick)
        self.last_tick = t
        self.poll_cursor()
        self.update(dt)
        self.render()

    def poll_cursor(self):
        p = QCursor.pos()
        c = (p.x() - self.gx, p.y() - self.gy)
        if math.hypot(c[0] - self.last_cursor[0], c[1] - self.last_cursor[1]) > 3:
            self.last_move = now()
            if self.state == "sleep" and self.sleep_reason == "idle":
                self.wake("Hm? Wróciłeś!")
        self.last_cursor = c
        self.cursor = c

    def update(self, dt):
        t, s, cfg = now(), self.scale, self.cfg
        self.t += dt

        if not self.blinking and t >= self.blink_at:
            self.blinking, self.blink_end, self.blink_at = True, t + 0.14, t + rand(2.5, 5.5)
        elif self.blinking and t >= self.blink_end:
            self.blinking = False

        active = self.state in ("idle", "walk")
        if cfg["sleep_idle"] and active and t - self.last_move > 300:
            self.sleep_for(math.inf, "idle")
        if cfg["speech"] and active and t >= self.next_talk:
            self.talk()
            self.next_talk = t + rand(45, 120)

        if cfg["mode"] == "follow" and self.state in ("idle", "walk") and self.cursor:
            dx = self.cursor[0] - self.cx
            if abs(dx) > 30 * s:
                self.target = clamp(self.cursor[0], self.half_w(), self.W - self.half_w())
                if self.state != "walk":
                    self.set_state("walk")
            elif self.state == "walk":
                self.set_state("idle")
            if (self.cursor[1] < self.by - BOX * s * 1.3 and abs(dx) < 60 * s and t > self.next_hop):
                self.jump()
                self.next_hop = t + rand(3, 7)
        if cfg["mode"] == "stay" and self.state == "walk":
            self.set_state("idle")

        st = self.state
        if st == "air":
            self.vy += self.gravity() * dt
            self.cx += self.vx * dt
            self.by += self.vy * dt
            hw = self.half_w()
            if self.cx - hw < 0:
                self.cx, self.vx = hw, abs(self.vx) * 0.6
            if self.cx + hw > self.W:
                self.cx, self.vx = self.W - hw, -abs(self.vx) * 0.6
            if self.vy < 0 and self.by - BOX * s < 0:
                self.by, self.vy = BOX * s, abs(self.vy) * 0.3
            if self.by >= self.floor:
                self.by = self.floor
                v = self.vy
                if v > 160 * s and self.bounces < 2:
                    self.vy, self.vx = -v * 0.32, self.vx * 0.7
                    self.bounces += 1
                else:
                    self.land(v)
        elif st == "land":
            if self.t > 0.2:
                self.set_state("idle")
        elif st == "walk":
            dx = self.target - self.cx
            self.walk_dir = 1 if dx >= 0 else -1
            step = (46 if cfg["mode"] == "follow" else 20) * s * dt
            if abs(dx) <= step:
                self.cx = self.target
                self.set_state("idle")
            else:
                self.cx += self.walk_dir * step
        elif st == "idle":
            self.by = self.floor
            if cfg["mode"] == "wander" and t >= self.next_t:
                self.choose()
        elif st == "sleep":
            self.by = self.floor
            if t >= self.z_at:
                self.spawn_fx("Z", "#cfe3ff")
                self.z_at = t + 1.4
            if self.sleep_reason == "timer" and t >= self.sleep_until:
                self.wake()

    def choose_sprite(self):
        if self.state == "drag":
            return SPR_FALL[int(self.t / 0.18) % 4]
        if self.state == "air":
            return SPR_FALL[int(self.t / 0.11) % 4]
        if self.state == "sleep":
            return SPR_BLINK
        return SPR_BLINK if self.blinking else SPR_IDLE

    def render(self):
        s = self.scale
        self.current_sprite = self.choose_sprite()
        self.sx = self.sy = 1.0
        self.tilt = self.bob = 0.0
        if self.state == "land":
            k = math.sin(math.pi * clamp(self.t / 0.2, 0, 1)) * self.land_pow
            self.sy, self.sx = 1 - 0.22 * k, 1 + 0.18 * k
        elif self.state == "sleep":
            self.sy = 1 - 0.02 * (math.sin(now() * 1.7) + 1) / 2
        elif self.state == "walk":
            phase = int(self.t / 0.18) % 2
            self.bob = -2 * s * phase
            self.tilt = self.walk_dir * 2 + (4 if phase else -4)
        self.win.move(int(self.gx + self.cx - BOX * s / 2), int(self.gy + self.by - BOX * s))
        self.win.update()
        ov = self.overlay
        active = bool((ov.text and now() < ov.until) or any(now() - q["born"] < 1.5 for q in ov.particles))
        if active or self.ov_was_active:  # nakładka na cały ekran – odświeżamy tylko, gdy trzeba
            ov.update()
        self.ov_was_active = active

    # ---- mysz
    def gpos(self, e):
        p = e.globalPosition()
        return p.x() - self.gx, p.y() - self.gy

    def on_press(self, e):
        if e.button() == Qt.RightButton:
            self.show_menu(QCursor.pos())
            return
        if e.button() != Qt.LeftButton:
            return
        x, y = self.gpos(e)
        self.press = {"sx": x, "sy": y, "moved": False, "gx": x - self.cx, "gy": y - self.by, "samples": []}

    def on_move(self, e):
        pr = self.press
        if not pr:
            return
        x, y = self.gpos(e)
        if not pr["moved"] and math.hypot(x - pr["sx"], y - pr["sy"]) > 5:
            pr["moved"] = True
            self.set_state("drag")
            self.maybe_say("grab", 0.5)
        if pr["moved"]:
            self.cx = clamp(x - pr["gx"], self.half_w(), self.W - self.half_w())
            self.by = clamp(y - pr["gy"], 8, self.H)
            t = now()
            pr["samples"].append((x, y, t))
            pr["samples"] = [q for q in pr["samples"] if t - q[2] < 0.12]

    def on_release(self, e):
        pr, self.press = self.press, None
        if not pr or e.button() != Qt.LeftButton:
            return
        if not pr["moved"]:
            return self.click()
        sm, vx, vy = pr["samples"], 0.0, 0.0
        if len(sm) >= 2 and now() - sm[-1][2] < 0.08:
            a, b = sm[0], sm[-1]
            dt = b[2] - a[2]
            if dt > 0.01:
                vx, vy = (b[0] - a[0]) / dt, (b[1] - a[1]) / dt
        self.vx, self.vy = clamp(vx, -3000, 3000), clamp(vy, -3000, 3000)
        self.bounces = 0
        self.set_state("air")
        if math.hypot(self.vx, self.vy) > 1200:
            self.maybe_say("thrown", 0.8)
            self.cfg["stats"]["throws"] += 1
            self.save_cfg()

    def click(self):
        t = now()
        if self.state == "sleep":
            self.wake("Hm? Już nie śpię…")
        elif t - self.last_click < 0.35:
            self.jump()
        else:
            self.pat()
        self.last_click = t

    def pat(self):
        for i in range(3):
            QTimer.singleShot(i * 120, lambda: self.spawn_fx("♥", "#ff5fa2"))
        self.maybe_say("pat", 0.7)
        self.cfg["stats"]["pets"] += 1
        self.save_cfg()

    # ---- Pomodoro / woda
    def arm_water(self):
        self.water_timer.stop()
        if self.cfg["water"] > 0:
            self.water_timer.start(self.cfg["water"] * 60_000)

    def start_pomodoro(self, work, brk):
        self.stop_pomodoro()
        self.run_phase("work", work, brk)

    def run_phase(self, phase, work, brk):
        minutes = work if phase == "work" else brk
        self.pomo = {"phase": phase, "end": time.time() + minutes * 60}
        self.pomo_timer = QTimer()
        self.pomo_timer.setSingleShot(True)

        def done():
            if phase == "work":
                self.announce(f"Koniec skupienia! Czas na {brk} min przerwy ☕")
                self.run_phase("break", work, brk)
            else:
                self.announce("Przerwa skończona – wracamy do pracy! 💪")
                self.run_phase("work", work, brk)

        self.pomo_timer.timeout.connect(done)
        self.pomo_timer.start(minutes * 60_000)
        self.announce(f"Start! {minutes} min skupienia 🍅" if phase == "work"
                      else f"Przerwa {minutes} min – rozprostuj nogi!")

    def stop_pomodoro(self):
        if self.pomo_timer:
            self.pomo_timer.stop()
        self.pomo = self.pomo_timer = None

    # ---- menu
    def build_tray(self):
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self.populate_menu)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            icon = QIcon(os.path.join(ASSETS, "tray.png"))
            self.tray = QSystemTrayIcon(icon)
            self.tray.setToolTip("PixelMate")
            self.tray.setContextMenu(self.menu)
            self.tray.show()

    def show_menu(self, pos):
        self.populate_menu()
        self.menu.exec(pos)

    def populate_menu(self):
        m, cfg = self.menu, self.cfg
        m.clear()
        m.addAction("PixelMate").setEnabled(False)
        m.addAction(f"Pogłaskano: {cfg['stats']['pets']}×  •  Rzucono: {cfg['stats']['throws']}×").setEnabled(False)
        m.addSeparator()

        def radio_menu(title, key, options):
            sub = m.addMenu(title)
            group = QActionGroup(sub)
            group.setExclusive(True)
            for label, value in options:
                act = QAction(label, sub, checkable=True)
                act.setChecked(cfg[key] == value)
                act.triggered.connect(lambda _=False, k=key, v=value: self.set_cfg(k, v))
                group.addAction(act)
                sub.addAction(act)

        radio_menu("Tryb", "mode", [("Wędruje sam", "wander"), ("Chodzi za kursorem", "follow"), ("Stoi w miejscu", "stay")])
        radio_menu("Rozmiar", "scale", [(f"{n}×", n) for n in (2, 3, 4, 5, 6, 8)])

        acts = m.addMenu("Akcje")
        for label, fn in (("Skocz", self.jump), ("Zrzuć z góry ekranu", self.drop),
                          ("Teleport do kursora", self.teleport),
                          ("Zaśnij", lambda: self.sleep_for(math.inf, "manual")),
                          ("Powiedz coś", self.talk)):
            acts.addAction(label, lambda _=False, f=fn: (self.wake() if self.state == "sleep" else None, f()))

        pm = m.addMenu("Pomodoro")
        if self.pomo:
            end = time.strftime("%H:%M", time.localtime(self.pomo["end"]))
            pm.addAction(f"{'🍅 Praca' if self.pomo['phase'] == 'work' else '☕ Przerwa'} – do {end}").setEnabled(False)
            pm.addAction("Zatrzymaj", self.stop_pomodoro)
        else:
            pm.addAction("Start 25 min / przerwa 5 min", lambda: self.start_pomodoro(25, 5))
            pm.addAction("Start 50 min / przerwa 10 min", lambda: self.start_pomodoro(50, 10))

        radio_menu("Przypomnienie o piciu wody", "water", [("Wyłączone", 0), ("Co 30 minut", 30), ("Co 60 minut", 60)])
        m.addSeparator()

        for label, key in (("Dymki z tekstem", "speech"), ("Zasypia przy bezczynności (5 min)", "sleep_idle"),
                           ("Zawsze na wierzchu", "on_top")):
            act = QAction(label, m, checkable=True)
            act.setChecked(cfg[key])
            act.triggered.connect(lambda checked=False, k=key: self.set_cfg(k, checked))
            m.addAction(act)
        m.addSeparator()
        visible = self.win.isVisible()
        m.addAction("Ukryj pet" if visible else "Pokaż pet", self.toggle_visible)
        m.addAction("Zamknij", self.qapp.quit)

    def toggle_visible(self):
        on = not self.win.isVisible()
        self.win.setVisible(on)
        self.overlay.setVisible(on)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(os.path.join(ASSETS, "icon.png")))
    mate = PixelMate(app)  # noqa: F841 (trzymamy referencję, żeby nie zniknął)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
