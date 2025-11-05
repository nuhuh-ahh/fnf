from __future__ import annotations

import os
import sys
import json
import math
import random
import subprocess
import argparse
import pygame
from typing import Any, Callable, Dict, List, Optional, Tuple, TypedDict

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")


# ------------------------------ Paths & Loader ------------------------------ #

ROOT = os.path.abspath(os.path.dirname(__file__))
MODS_DIR = os.path.join(ROOT, "mods")
SETTINGS_FILE = os.path.join(ROOT, "settings.json")
MODS_ENABLED_FILE = os.path.join(ROOT, "mods_enabled.json")


def _load_settings() -> Dict[str, Any]:
    default = {
        "note_bar_pos": "center",
        "note_bar_style": "split",
        "note_skin": "rect",
        "ghost_tap": True,
        "hp_loss_mult": 1.0,
        "audio_overrides": {},  # { songId: 'auto'|'song'|'bg+voice' }
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default.update(data or {})
        except Exception:
            pass
    return default


def _save_settings(settings: Dict[str, Any]) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass


def _load_enabled_mods() -> Optional[List[str]]:
    if not os.path.exists(MODS_ENABLED_FILE):
        return None
    try:
        with open(MODS_ENABLED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [str(x) for x in data]
    except Exception:
        return None
    return None


def _save_enabled_mods(mods: List[str]) -> None:
    try:
        with open(MODS_ENABLED_FILE, "w", encoding="utf-8") as f:
            json.dump(mods, f, indent=2)
    except Exception:
        pass


def ensure_mod_structure() -> None:
    os.makedirs(MODS_DIR, exist_ok=True)
    # Example mod scaffold
    example = os.path.join(MODS_DIR, "example_mod")
    for sub in ("data", "music", "scripts", "characters", "event", "note", "plugins"):
        os.makedirs(os.path.join(example, sub), exist_ok=True)
    # Seed demo chart if not present
    demo_chart = os.path.join(example, "data", "tutorial.json")
    if not os.path.exists(demo_chart):
        with open(demo_chart, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "id": "tutorial",
                    "title": "Tutorial",
                    "artist": "Unknown",
                    "bpm": 120,
                    "lanes": 4,
                    "notes": [
                        {"time": 1000, "lane": 0},
                        {"time": 1250, "lane": 1},
                        {"time": 1500, "lane": 2},
                        {"time": 1750, "lane": 3},
                        {"time": 2200, "lane": 0, "sustain": 400},
                        {"time": 3000, "lane": 1},
                        {"time": 3250, "lane": 2},
                        {"time": 3500, "lane": 3},
                    ],
                },
                f,
                indent=2,
            )
    # Template mod scaffold
    template = os.path.join(MODS_DIR, "mod_template")
    for sub in ("data", "music", "scripts", "characters", "event", "note", "plugins"):
        os.makedirs(os.path.join(template, sub), exist_ok=True)
    readme = os.path.join(template, "README.txt")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write("Place your charts in data/*.json and audio in music/<songId>/.\n")


def list_mods() -> List[str]:
    if not os.path.isdir(MODS_DIR):
        return []
    mods = sorted([d for d in os.listdir(MODS_DIR) if os.path.isdir(os.path.join(MODS_DIR, d))])
    enabled = _load_enabled_mods()
    if enabled is None:
        return mods
    # keep order of mods but filter to enabled
    return [m for m in mods if m in enabled]


def _find_in_mods(relative_path: str) -> Optional[str]:
    # Last mod wins (end of sorted list)
    mods = list_mods()
    for mod in reversed(mods):
        candidate = os.path.join(MODS_DIR, mod, relative_path)
        if os.path.exists(candidate):
            return candidate
    return None


def load_json_from_mods(relative_path: str) -> Optional[Dict[str, Any]]:
    p = _find_in_mods(relative_path)
    if not p:
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_songs() -> List[str]:
    # Load from (in precedence order):
    # - mods/<mod>/data/<map>/chart.json (folder style)
    # - mods/<mod>/data/chart-<map>.json (file style with prefix)
    # - mods/<mod>/data/<map>.json (legacy file style)
    songs: List[str] = []
    seen = set()
    for mod in list_mods():
        data_dir = os.path.join(MODS_DIR, mod, "data")
        if not os.path.isdir(data_dir):
            continue
        for entry in os.listdir(data_dir):
            path = os.path.join(data_dir, entry)
            # Folder style
            if os.path.isdir(path) and os.path.exists(os.path.join(path, "chart.json")):
                if entry not in seen:
                    seen.add(entry)
                    songs.append(entry)
            # File style: chart-<name>.json
            if os.path.isfile(path) and entry.lower().startswith("chart-") and entry.lower().endswith(".json"):
                name = entry[6:-5]  # remove 'chart-' and '.json'
                if name and name not in seen:
                    seen.add(name)
                    songs.append(name)
            # Legacy: <name>.json
            if os.path.isfile(path) and entry.lower().endswith(".json") and not entry.lower().startswith("chart-"):
                name = os.path.splitext(entry)[0]
                if name and name not in seen:
                    seen.add(name)
                    songs.append(name)
    songs.sort()
    return songs


def load_song_meta(song_id: str) -> Dict[str, Any]:
    # Prefer folder style, fallback to file styles chart-<songId>.json or <songId>.json
    data = load_json_from_mods(f"data/{song_id}/chart.json")
    if data is None:
        data = load_json_from_mods(f"data/chart-{song_id}.json")
    if data is None:
        data = load_json_from_mods(f"data/{song_id}.json")
    data = data or {}
    return {
        "id": song_id,
        "title": data.get("title", song_id),
        "artist": data.get("artist", "Unknown"),
        "bpm": float(data.get("bpm", 120)),
        "audioMode": data.get("audioMode", "auto"),
    }


class Note(TypedDict):
    time: float
    lane: int
    sustain: float


class Chart(TypedDict):
    lanes: int
    notes: List[Note]
    title: str
    artist: str
    bpm: float


def _parse_simple_chart(data: Dict[str, Any]) -> Chart:
    lanes = int(data.get("lanes", 4))
    notes: List[Note] = []
    for n in data.get("notes", []):
        notes.append({
            "time": float(n.get("time", 0.0)),
            "lane": int(n.get("lane", 0)),
            "sustain": float(n.get("sustain", 0.0)),
        })
    notes.sort(key=lambda x: x["time"])
    return {
        "lanes": lanes,
        "notes": notes,
        "title": data.get("title", "Unknown"),
        "artist": data.get("artist", "Unknown"),
        "bpm": float(data.get("bpm", 120)),
    }


def _parse_psych_chart(data: Dict[str, Any]) -> Chart:
    song = data.get("song", {})
    sections = song.get("notes", [])
    notes: List[Note] = []
    for sec in sections:
        for entry in sec.get("sectionNotes", []):
            if not isinstance(entry, list) or len(entry) < 2:
                continue
            t = float(entry[0])
            lane = int(entry[1]) % 4
            sustain = float(entry[3]) if len(entry) > 3 else 0.0
            notes.append({"time": t, "lane": lane, "sustain": sustain})
    notes.sort(key=lambda x: x["time"])
    return {
        "lanes": 4,
        "notes": notes,
        "title": song.get("song", "Unknown"),
        "artist": song.get("artist", "Unknown"),
        "bpm": float(song.get("bpm", 120)),
    }


def load_chart(song_id: str) -> Chart:
    # Try folder style, then file style chart-<songId>.json, then legacy <songId>.json
    data = load_json_from_mods(f"data/{song_id}/chart.json")
    if data is None:
        data = load_json_from_mods(f"data/chart-{song_id}.json")
    if data is None:
        data = load_json_from_mods(f"data/{song_id}.json") or {}
    if "song" in data and isinstance(data["song"], dict):
        return _parse_psych_chart(data)
    # Ensure metadata merged
    simple = _parse_simple_chart(data)
    meta = load_song_meta(song_id)
    simple["title"] = simple.get("title") or meta["title"]
    simple["artist"] = simple.get("artist") or meta["artist"]
    simple["bpm"] = simple.get("bpm") or meta["bpm"]
    return simple


def find_music(song_id: str, mode: str = 'auto') -> Tuple[Optional[str], Optional[str]]:
    # support aliases in music folder and inside data/<songId>/
    song_single = (
        _find_in_mods(f"data/{song_id}/song.ogg")
        or _find_in_mods(f"music/{song_id}/song.ogg")
    )
    inst = (
        _find_in_mods(f"music/{song_id}/inst.ogg")
        or _find_in_mods(f"music/{song_id}/background.ogg")
        or _find_in_mods(f"data/{song_id}/inst.ogg")
        or _find_in_mods(f"data/{song_id}/background.ogg")
    )
    voices = (
        _find_in_mods(f"music/{song_id}/voices.ogg")
        or _find_in_mods(f"music/{song_id}/voice.ogg")
        or _find_in_mods(f"data/{song_id}/voices.ogg")
        or _find_in_mods(f"data/{song_id}/voice.ogg")
    )
    if mode == 'song' and song_single:
        return song_single, None
    if mode == 'bg+voice' and (inst or song_single) and voices:
        # prefer inst/background + voices; fallback to song only if voices missing
        return inst or song_single, voices
    # auto mode: detect available
    if song_single and not voices:
        return song_single, None
    if (inst or song_single) and voices:
        return inst or song_single, voices
    return inst or song_single, voices


# ------------------------------- Audio Manager ------------------------------ #


class AudioManager:
    def __init__(self) -> None:
        self.music_volume = 0.8
        self.voices_channel = None  # lazy init after mixer
        self.voices_sound: Optional[pygame.mixer.Sound] = None

    def init_channels(self) -> None:
        if self.voices_channel is None and pygame.mixer.get_init():
            self.voices_channel = pygame.mixer.Channel(5)

    def set_volume(self, volume: float) -> None:
        self.music_volume = max(0.0, min(1.0, volume))
        try:
            pygame.mixer.music.set_volume(self.music_volume)
        except Exception:
            pass
        if self.voices_channel is not None:
            self.voices_channel.set_volume(self.music_volume)

    def play_song(self, song_id: str, mode: str = 'auto') -> None:
        inst_path, voices_path = find_music(song_id, mode)
        try:
            if inst_path and pygame.mixer.get_init():
                pygame.mixer.music.load(inst_path)
                pygame.mixer.music.set_volume(self.music_volume)
                pygame.mixer.music.play()
        except Exception:
            pass
        try:
            if voices_path and pygame.mixer.get_init():
                self.init_channels()
                self.voices_sound = pygame.mixer.Sound(voices_path)
                if self.voices_channel:
                    self.voices_channel.set_volume(self.music_volume)
                    self.voices_channel.play(self.voices_sound)
        except Exception:
            self.voices_sound = None

    def stop(self) -> None:
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        if self.voices_channel:
            self.voices_channel.stop()


# --------------------------------- UI Utils -------------------------------- #


Color = Tuple[int, int, int]


def draw_title(surface: pygame.Surface, font: pygame.font.Font, text: str, y: int) -> None:
    shadow = font.render(text, True, (20, 20, 30))
    rect = shadow.get_rect(center=(surface.get_width() // 2 + 2, y + 2))
    surface.blit(shadow, rect)
    title = font.render(text, True, (250, 250, 255))
    rect = title.get_rect(center=(surface.get_width() // 2, y))
    surface.blit(title, rect)


class Button:
    def __init__(self, rect: pygame.Rect, text: str, on_click: Callable[[], None]) -> None:
        self.rect = rect
        self.text = text
        self.on_click = on_click
        self.hover = False

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.on_click()

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        top = (60, 60, 90) if self.hover else (45, 45, 65)
        bottom = (85, 85, 120) if self.hover else (65, 65, 95)
        r = self.rect
        grad = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
        for i in range(r.height):
            t = i / max(1, r.height - 1)
            col = (
                int(top[0] * (1 - t) + bottom[0] * t),
                int(top[1] * (1 - t) + bottom[1] * t),
                int(top[2] * (1 - t) + bottom[2] * t),
                230,
            )
            pygame.draw.line(grad, col, (0, i), (r.width, i))
        pygame.draw.rect(surface, (20, 20, 30), r.inflate(6, 6), border_radius=12)
        surface.blit(grad, r)
        pygame.draw.rect(surface, (150, 150, 200), r, width=2, border_radius=10)
        label_s = font.render(self.text, True, (20, 20, 30))
        surface.blit(label_s, label_s.get_rect(center=(self.rect.centerx + 1, self.rect.centery + 1)))
        label = font.render(self.text, True, (235, 235, 245))
        surface.blit(label, label.get_rect(center=self.rect.center))


# --------------------------------- Core/Scenes ------------------------------ #


class Scene:
    def on_enter(self, game: "Game") -> None:
        pass

    def on_exit(self, game: "Game") -> None:
        pass

    def handle_event(self, game: "Game", event: pygame.event.Event) -> None:
        pass

    def update(self, game: "Game", dt: float) -> None:
        pass

    def draw(self, game: "Game", surface: pygame.Surface) -> None:
        pass
# Loading popup scene
class LoadingScene(Scene):
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.mods_count = 0
        self.files_count = 0
        self._walkers: List[Any] = []
        self._phase = 0.0
        self._done = False
        self._stage = "count"  # count | scan
        self._total_files_target = 0
        self._processed_files = 0
        self._min_display = 0.6
        self._max_timeout = 3.0

    def on_enter(self, game: Game) -> None:
        self.mods_count = len(list_mods())
        self.files_count = 0
        self._walkers = []
        for mod in list_mods():
            root = os.path.join(MODS_DIR, mod)
            try:
                self._walkers.append(os.walk(root))
            except Exception:
                continue
        if not self._walkers:
            # nothing to scan; mark done so we transition quickly
            self._done = True
            self._stage = "scan"

    def update(self, game: Game, dt: float) -> None:
        self.elapsed += dt
        self._phase += dt
        # Process a limited amount of filesystem work per frame to avoid blocking
        budget_steps = 12
        i = 0
        while i < budget_steps and self._walkers:
            walker = self._walkers[0]
            try:
                _root, _dirs, files = next(walker)
                if self._stage == "count":
                    self._total_files_target += len(files)
                else:
                    self._processed_files += len(files)
                    self.files_count = self._processed_files
                i += 1
            except StopIteration:
                self._walkers.pop(0)
            except Exception:
                self._walkers.pop(0)
        if not self._walkers and not self._done:
            if self._stage == "count":
                # Counting done -> start scan phase
                self._stage = "scan"
                self._processed_files = 0
                # rebuild walkers for actual scan pass
                for mod in list_mods():
                    root = os.path.join(MODS_DIR, mod)
                    try:
                        self._walkers.append(os.walk(root))
                    except Exception:
                        continue
                # If still none, mark done
                if not self._walkers:
                    self._done = True
            else:
                # finished scanning
                self._done = True
        # After finishing or small timeout, proceed
        if self._done and self.elapsed >= self._min_display:
            game.replace_scene(MainMenuScene())
        elif self.elapsed >= self._max_timeout:
            # safety timeout
            game.replace_scene(MainMenuScene())

    def handle_event(self, game: Game, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
            game.replace_scene(MainMenuScene())

    def draw(self, game: Game, surface: pygame.Surface) -> None:
        draw_title(surface, game.font, "Loading Mods", surface.get_height() // 2 - 100)
        # modal popup
        w, h = surface.get_size()
        # darken background slightly for readability
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 90))
        surface.blit(dim, (0, 0))
        box = pygame.Rect(0, 0, 620, 200)
        box.center = (w // 2, h // 2 + 10)
        pygame.draw.rect(surface, (26, 26, 42), box, border_radius=14)
        pygame.draw.rect(surface, (150, 150, 210), box, width=2, border_radius=14)
        info1 = game.font.render(f"Detected mods: {self.mods_count}", True, (240, 240, 255))
        if self._stage == "count":
            info2 = game.font.render("Counting files...", True, (220, 220, 240))
        else:
            pct = 0
            if self._total_files_target > 0:
                pct = int(100 * min(1.0, self._processed_files / max(1, self._total_files_target)))
            info2 = game.font.render(f"Scanning files: {self.files_count} / {self._total_files_target} ({pct}%)", True, (220, 220, 240))
        surface.blit(info1, info1.get_rect(center=(box.centerx, box.top + 56)))
        surface.blit(info2, info2.get_rect(center=(box.centerx, box.top + 90)))
        # Progress bar (indeterminate stripes)
        bar = pygame.Rect(box.left + 40, box.bottom - 56, box.width - 80, 22)
        pygame.draw.rect(surface, (55, 55, 85), bar, border_radius=8)
        pygame.draw.rect(surface, (130, 130, 180), bar, width=2, border_radius=8)
        if self._stage == "count" or self._total_files_target == 0:
            # animated stripes (indeterminate)
            stripe_w = 36
            offset = int((self._phase * 120) % stripe_w)
            stripe = pygame.Surface((stripe_w, bar.height - 6), pygame.SRCALPHA)
            pygame.draw.rect(stripe, (200, 200, 255, 120), stripe.get_rect())
            x = bar.left + 3 - offset
            while x < bar.right - 3:
                surface.blit(stripe, (x, bar.top + 3))
                x += stripe_w
        else:
            # determinate fill based on processed/total
            pct = min(1.0, self._processed_files / max(1, self._total_files_target))
            fill = pygame.Rect(bar.left + 3, bar.top + 3, int((bar.width - 6) * pct), bar.height - 6)
            pygame.draw.rect(surface, (200, 200, 255), fill, border_radius=6)
        hint = game.font.render("Press Enter to skip", True, (210, 210, 235))
        surface.blit(hint, hint.get_rect(center=(box.centerx, box.bottom - 18)))

    # end LoadingScene


class Game:
    def __init__(self, width: int, height: int, window_title: str, target_fps: int = 144) -> None:
        ensure_mod_structure()
        pygame.init()
        try:
            pygame.mixer.init()
        except Exception:
            pass
        self.size = (width, height)
        self.screen = pygame.display.set_mode(self.size)
        pygame.display.set_caption(window_title)
        self.clock = pygame.time.Clock()
        self.target_fps = target_fps
        self.font = self._load_font(size=24)
        self.scenes: List[Scene] = []
        self.bg_phase = 0.0  # for animated gradient
        self.settings = _load_settings()
        self.bg_particles: List[Tuple[float, float, float, float]] = []  # x,y,vy,size
        self.push_scene(MainMenuScene())

    def _load_font(self, size: int) -> pygame.font.Font:
        # try custom font from mods/*/plugins/*.ttf|*.otf
        for mod in list_mods():
            plug_dir = os.path.join(MODS_DIR, mod, "plugins")
            if not os.path.isdir(plug_dir):
                continue
            for f in os.listdir(plug_dir):
                if f.lower().endswith((".ttf", ".otf")):
                    try:
                        return pygame.font.Font(os.path.join(plug_dir, f), size)
                    except Exception:
                        continue
        return pygame.font.SysFont("Segoe UI", size)

    def push_scene(self, scene: Scene) -> None:
        if self.scenes:
            self.scenes[-1].on_exit(self)
        self.scenes.append(scene)
        scene.on_enter(self)

    def pop_scene(self) -> None:
        if self.scenes:
            self.scenes[-1].on_exit(self)
            self.scenes.pop()
        if self.scenes:
            self.scenes[-1].on_enter(self)

    def replace_scene(self, scene: Scene) -> None:
        if self.scenes:
            self.scenes[-1].on_exit(self)
            self.scenes.pop()
        self.scenes.append(scene)
        scene.on_enter(self)

    @property
    def current_scene(self) -> Scene:
        return self.scenes[-1]

    def _draw_animated_background(self) -> None:
        w, h = self.size
        self.bg_phase += 0.01
        t = (math.sin(self.bg_phase) + 1) * 0.5
        c1 = (int(18 + 18 * t), int(18 + 18 * t), int(34 + 22 * t))
        c2 = (int(34 + 28 * (1 - t)), int(32 + 26 * (1 - t)), int(64 + 34 * (1 - t)))
        grad = pygame.Surface((w, h))
        for y in range(h):
            alpha = y / max(1, h - 1)
            col = (
                int(c1[0] * (1 - alpha) + c2[0] * alpha),
                int(c1[1] * (1 - alpha) + c2[1] * alpha),
                int(c1[2] * (1 - alpha) + c2[2] * alpha),
            )
            pygame.draw.line(grad, col, (0, y), (w, y))
        self.screen.blit(grad, (0, 0))
        # floating particles
        if len(self.bg_particles) < 40:
            import random
            for _ in range(40 - len(self.bg_particles)):
                x = random.uniform(0, w)
                y = random.uniform(0, h)
                vy = random.uniform(8, 22)
                size = random.uniform(2, 5)
                self.bg_particles.append((x, y, vy, size))
        new_particles: List[Tuple[float, float, float, float]] = []
        for (x, y, vy, size) in self.bg_particles:
            y2 = y + vy * 0.016
            if y2 > h:
                y2 = 0
            pygame.draw.rect(self.screen, (255, 255, 255, 20), (x, y2, size, size))
            new_particles.append((x, y2, vy, size))
        self.bg_particles = new_particles

    def run(self) -> None:
        running = True
        while running and self.scenes:
            dt_ms = self.clock.tick(self.target_fps)
            dt = dt_ms / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break
                self.current_scene.handle_event(self, event)

            self.current_scene.update(self, dt)
            self._draw_animated_background()
            self.current_scene.draw(self, self.screen)
            pygame.display.flip()
        pygame.quit()


# --------------------------------- Scenes ---------------------------------- #


class EditorApp:
    def __init__(self, song_id: str) -> None:
        self.song_id = song_id
        pygame.init()
        try:
            pygame.mixer.init()
        except Exception:
            pass
        self.size = (1200, 700)
        self.screen = pygame.display.set_mode(self.size)
        pygame.display.set_caption(f"Chart Editor - {song_id}")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Segoe UI", 20)
        self.chart = load_chart(song_id)
        self.time_ms = 0.0
        self.playing = False
        self.audio = AudioManager()
        # Read audioMode from chart metadata
        try:
            meta = load_song_meta(song_id)
            self.audio_mode = str(meta.get('audioMode', 'auto'))
        except Exception:
            self.audio_mode = 'auto'
        self.audio.play_song(song_id, self.audio_mode)
        pygame.mixer.music.pause()
        # timeline state
        self.drag_timeline = False
        self.total_ms = self._compute_total_ms()

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_SPACE:
                        self.playing = not self.playing
                        if self.playing:
                            pygame.mixer.music.unpause()
                        else:
                            pygame.mixer.music.pause()
                    elif event.key == pygame.K_s and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                        self._save()
                    elif event.key == pygame.K_l:
                        # reload chart from disk
                        self.chart = load_chart(self.song_id)
                        self.total_ms = self._compute_total_ms()
                    elif event.key == pygame.K_a:
                        # reload audio
                        try:
                            pygame.mixer.music.stop()
                        except Exception:
                            pass
                        self.audio.play_song(self.song_id, self.audio_mode)
                        pygame.mixer.music.pause()
                    elif event.key == pygame.K_m:
                        # cycle audio mode
                        order = ['auto', 'song', 'bg+voice']
                        try:
                            idx = order.index(self.audio_mode)
                        except ValueError:
                            idx = 0
                        self.audio_mode = order[(idx + 1) % len(order)]
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    x, y = event.pos
                    self._handle_click(x, y, event.button)
                    # start dragging timeline if within bar
                    if self._timeline_rect().collidepoint(event.pos):
                        self.drag_timeline = True
                        self._scrub_to(event.pos[0])
                elif event.type == pygame.MOUSEBUTTONUP:
                    self.drag_timeline = False
                elif event.type == pygame.MOUSEMOTION and self.drag_timeline:
                    self._scrub_to(event.pos[0])
                elif event.type == pygame.MOUSEWHEEL:
                    # scroll time with wheel (positive y is up)
                    self.time_ms = max(0.0, min(self.total_ms, self.time_ms - event.y * 200.0))
            if self.playing:
                self.time_ms += dt * 1000.0
                if self.time_ms > self.total_ms:
                    self.time_ms = self.total_ms
            self._draw()
        pygame.quit()

    def _lane_from_x(self, x: int, lanes: int, left_x: int, lane_w: int) -> int:
        rel = x - left_x
        if rel < 0:
            return 0
        idx = int(rel // lane_w)
        return max(0, min(lanes - 1, idx))

    def _handle_click(self, x: int, y: int, button: int) -> None:
        lanes = self.chart.get("lanes", 4)
        left_x = 100
        lane_w = (self.size[0] - 200) // lanes
        hit_y = int(self.size[1] * 0.8)
        lane = self._lane_from_x(x, lanes, left_x, lane_w)
        # y to time conversion
        scroll_speed = 0.6
        t_until = (y - hit_y) / -scroll_speed
        t = max(0.0, self.time_ms + t_until)
        if button == 1:
            sustain = 600.0 if (pygame.key.get_mods() & pygame.KMOD_SHIFT) else 0.0
            self.chart.setdefault("notes", []).append({"time": t, "lane": lane, "sustain": sustain})
            self.chart["notes"].sort(key=lambda n: n["time"])
        elif button == 3:
            # remove nearest
            if not self.chart.get("notes"):
                return
            nearest = min(range(len(self.chart["notes"])), key=lambda i: abs(self.chart["notes"][i]["time"] - t))
            if abs(self.chart["notes"][nearest]["time"] - t) <= 120.0:
                self.chart["notes"].pop(nearest)

    def _draw(self) -> None:
        self.screen.fill((22, 22, 32))
        lanes = self.chart.get("lanes", 4)
        lane_w = (self.size[0] - 200) // lanes
        left_x = 100
        hit_y = int(self.size[1] * 0.8)
        # lanes
        for i in range(lanes):
            x = left_x + i * lane_w
            pygame.draw.rect(self.screen, (40, 40, 60), (x + 6, 60, lane_w - 12, self.size[1] - 120), border_radius=10)
            pygame.draw.rect(self.screen, (180, 180, 220), (x + 10, hit_y, lane_w - 20, 14), border_radius=6)
        # notes
        scroll_speed = 0.6
        for n in self.chart.get("notes", []):
            lane = n["lane"]
            x = left_x + lane * lane_w
            y = hit_y - int((n["time"] - self.time_ms) * scroll_speed)
            if 60 <= y <= self.size[1] + 200:
                pygame.draw.rect(self.screen, (120, 200, 255), (x + 18, y - 8, lane_w - 36, 16), border_radius=4)
                if n.get("sustain", 0.0) > 0:
                    length_px = int(n["sustain"] * scroll_speed)
                    pygame.draw.rect(self.screen, (120, 200, 255), (x + 24, y - length_px, lane_w - 48, length_px), border_radius=4)
        # HUD
        title = self.font.render(f"Editing: {self.song_id}   Space: Play/Pause   Ctrl+S: Save   Shift+Click: Hold   L: Reload Chart   A: Reload Audio", True, (235, 235, 245))
        self.screen.blit(title, (20, 20))
        # timeline (scroll bar)
        bar = self._timeline_rect()
        pygame.draw.rect(self.screen, (40, 40, 60), bar, border_radius=6)
        pygame.draw.rect(self.screen, (120, 120, 160), bar, width=2, border_radius=6)
        # scrubber
        if self.total_ms <= 0:
            progress = 0.0
        else:
            progress = min(1.0, max(0.0, self.time_ms / self.total_ms))
        x_scrub = int(bar.left + 2 + (bar.width - 4) * progress)
        pygame.draw.rect(self.screen, (200, 200, 255), (bar.left + 2, bar.top + 2, x_scrub - (bar.left + 2), bar.height - 4), border_radius=6)
        pygame.draw.rect(self.screen, (240, 240, 255), (x_scrub - 2, bar.top, 4, bar.height), border_radius=2)
        pygame.display.flip()

    def _resolve_chart_write_path(self) -> str:
        # Prefer existing path; otherwise create in first enabled mod
        existing = (
            _find_in_mods(f"data/{self.song_id}/chart.json")
            or _find_in_mods(f"data/chart-{self.song_id}.json")
            or _find_in_mods(f"data/{self.song_id}.json")
        )
        if existing and os.path.commonpath([existing, MODS_DIR]) == MODS_DIR:
            return existing
        enabled = _load_enabled_mods() or list_mods()
        target_mod = enabled[0] if enabled else "example_mod"
        target_dir = os.path.join(MODS_DIR, target_mod, "data", self.song_id)
        os.makedirs(target_dir, exist_ok=True)
        return os.path.join(target_dir, "chart.json")

    def _save(self) -> None:
        notes_sorted = sorted(self.chart.get("notes", []), key=lambda n: n["time"]) if self.chart.get("notes") else []
        to_save = {
            "id": self.song_id,
            "title": self.chart.get("title", self.song_id),
            "artist": self.chart.get("artist", "Unknown"),
            "bpm": self.chart.get("bpm", 120),
            "lanes": self.chart.get("lanes", 4),
            "audioMode": self.audio_mode,
            "notes": [
                {"time": float(n.get("time", 0.0)), "lane": int(n.get("lane", 0)), "sustain": float(n.get("sustain", 0.0))}
                for n in notes_sorted
            ],
            "events": self.chart.get("events", []),
        }
        path = self._resolve_chart_write_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(to_save, f, indent=2)
        except Exception:
            pass

    def _compute_total_ms(self) -> float:
        last_note = 0.0
        for n in self.chart.get("notes", []):
            end_t = float(n.get("time", 0.0)) + float(n.get("sustain", 0.0))
            if end_t > last_note:
                last_note = end_t
        return max(60000.0, last_note + 4000.0)

    def _timeline_rect(self) -> pygame.Rect:
        return pygame.Rect(80, self.size[1] - 36, self.size[0] - 160, 12)

    def _scrub_to(self, x: int) -> None:
        bar = self._timeline_rect()
        if bar.width <= 0:
            return
        t = (x - bar.left) / max(1, bar.width)
        self.time_ms = max(0.0, min(self.total_ms, t * self.total_ms))


class MainMenuScene(Scene):
    def __init__(self) -> None:
        self.buttons: List[Button] = []
        self.audio = AudioManager()
        self.items: List[Tuple[str, Callable[[], None]]] = []
        self.selected = 0
        self._toast: Optional[Tuple[str, float]] = None  # (text, timeLeft)

    def on_enter(self, game: Game) -> None:
        w, h = game.size
        btn_w, btn_h, gap = 380, 58, 18
        start_y = h // 2 - 2 * (btn_h + gap)
        self.items = [
            ("Freeplay", lambda: game.push_scene(FreeplayScene(self.audio))),
            ("Story Mode", lambda: game.push_scene(StoryScene(self.audio))),
            ("Settings", lambda: game.push_scene(SettingsScene(self.audio))),
            ("Mods", lambda: game.push_scene(ModsManagerScene())),
            ("Plugins", lambda: game.push_scene(PluginsScene())),
            ("Credits", lambda: game.push_scene(CreditsScene())),
            ("Quit", lambda: pygame.event.post(pygame.event.Event(pygame.QUIT))),
        ]
        self.buttons = []
        for i, (label, cb) in enumerate(self.items):
            rect = pygame.Rect(0, 0, btn_w, btn_h)
            rect.center = (w // 2, start_y + i * (btn_h + gap))
            self.buttons.append(Button(rect, label, cb))

    def handle_event(self, game: Game, event: pygame.event.Event) -> None:
        for b in self.buttons:
            b.handle_event(event)
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % len(self.buttons)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % len(self.buttons)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if 0 <= self.selected < len(self.items):
                    # Activate selected
                    self.items[self.selected][1]()
            elif event.key in (pygame.K_LCTRL, pygame.K_RCTRL):
                # Toggle HP loss multiplier between 1x and 2x
                cur = float(game.settings.get("hp_loss_mult", 1.0))
                new_val = 2.0 if cur < 2.0 else 1.0
                game.settings["hp_loss_mult"] = new_val
                _save_settings(game.settings)
                self._toast = (f"HP Loss Mult: {int(new_val)}x", 1.0)

    def draw(self, game: Game, surface: pygame.Surface) -> None:
        # animated title pulse
        pulse = 0.5 + 0.5 * math.sin(game.bg_phase * 3)
        title = "FNF Application (Single-file)"
        shadow = game.font.render(title, True, (20, 20, 30))
        rect = shadow.get_rect(center=(surface.get_width() // 2 + 2, 118 + 2))
        surface.blit(shadow, rect)
        title_surf = game.font.render(title, True, (230, 230, int(240 - 20 * pulse)))
        surface.blit(title_surf, title_surf.get_rect(center=(surface.get_width() // 2, 118)))
        for i, b in enumerate(self.buttons):
            # Pulsing selection highlight
            if i == self.selected:
                glow = int(40 + 20 * (0.5 + 0.5 * math.sin(game.bg_phase * 3)))
                sel_rect = b.rect.inflate(16, 10)
                pygame.draw.rect(surface, (90, 90, 130), sel_rect, border_radius=12)
                pygame.draw.rect(surface, (120 + glow, 120 + glow, 180), sel_rect, width=2, border_radius=12)
                # animated arrow
                ax = sel_rect.left - 26 + int(4 * math.sin(game.bg_phase * 6))
                ay = sel_rect.centery
                pygame.draw.polygon(surface, (200, 200, 240), [(ax, ay), (ax + 14, ay - 10), (ax + 14, ay + 10)])
            b.draw(surface, game.font)
        # Show hint and toast
        hint = game.font.render(f"Ctrl: toggle HP loss (current {int(game.settings.get('hp_loss_mult',1.0))}x)", True, (210, 210, 230))
        surface.blit(hint, (20, surface.get_height() - 36))
        if self._toast:
            text, tleft = self._toast
            self._toast = (text, max(0.0, tleft - 1/60))
            toast = game.font.render(text, True, (255, 255, 255))
            surface.blit(toast, (20, surface.get_height() - 64))


class FreeplayScene(Scene):
    def __init__(self, audio: AudioManager) -> None:
        self.audio = audio
        self.songs: List[str] = []
        self.selected = 0
        self.difficulties = ["Easy", "Normal", "Hard"]
        self.diff_index = 1

    def on_enter(self, game: Game) -> None:
        self.songs = list_songs()
        # audio mode selection now handled inside the editor, not Freeplay

    def handle_event(self, game: Game, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                game.pop_scene()
            elif event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % max(1, len(self.songs))
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % max(1, len(self.songs))
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                self.diff_index = (self.diff_index - 1) % len(self.difficulties)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self.diff_index = (self.diff_index + 1) % len(self.difficulties)
            elif event.key == pygame.K_7:
                if self.songs:
                    # Launch external editor process in a new window
                    song_id = self.songs[self.selected]
                    try:
                        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--editor", song_id], close_fds=True)
                    except Exception:
                        pass
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.songs:
                    diff = self.difficulties[self.diff_index].lower()
                    game.push_scene(GameplayScene(self.songs[self.selected], self.audio, difficulty=diff))

    def draw(self, game: Game, surface: pygame.Surface) -> None:
        draw_title(surface, game.font, "Freeplay", 80)
        if not self.songs:
            msg = game.font.render("No charts found in mods/*/data.", True, (230, 230, 245))
            surface.blit(msg, (40, 160))
            return
        y = 160
        for i, sid in enumerate(self.songs):
            meta = load_song_meta(sid)
            display = f"{meta['title']} — {meta['artist']}"
            color = (255, 255, 255) if i == self.selected else (200, 200, 210)
            text = game.font.render(display, True, color)
            surface.blit(text, (80, y))
            y += 40
        hint = game.font.render("7: Open editor  Enter: Play  Left/Right: Difficulty", True, (210, 210, 230))
        surface.blit(hint, (80, y + 16))
        diff_text = game.font.render(f"Difficulty: {self.difficulties[self.diff_index]}  (Left/Right)", True, (220, 220, 240))
        surface.blit(diff_text, (80, y + 16))


class StoryScene(Scene):
    def __init__(self, audio: AudioManager) -> None:
        self.audio = audio
        self.week: List[str] = []
        self.index = 0

    def on_enter(self, game: Game) -> None:
        self.week = list_songs()
        self.index = 0

    def handle_event(self, game: Game, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            game.pop_scene()
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.week:
                game.push_scene(GameplayScene(self.week[self.index], self.audio, on_finish=self._advance))

    def _advance(self, game: Game) -> None:
        self.index += 1
        if self.index >= len(self.week):
            game.pop_scene()
        else:
            game.push_scene(GameplayScene(self.week[self.index], self.audio, on_finish=self._advance))

    def draw(self, game: Game, surface: pygame.Surface) -> None:
        draw_title(surface, game.font, "Story Mode", 80)
        hint = game.font.render("Press Enter to start week.", True, (220, 220, 240))
        surface.blit(hint, (80, 160))


class SettingsScene(Scene):
    def __init__(self, audio: AudioManager) -> None:
        self.audio = audio
        self.options: List[Tuple[str, List[str], Callable[[str, Dict[str, Any]], None]]] = []
        self.selected = 0

    def handle_event(self, game: Game, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                game.pop_scene()
            elif event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % len(self._ensure_options(game))
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % len(self._ensure_options(game))
            elif event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                opts = self._ensure_options(game)
                name, values, apply_fn = opts[self.selected]
                # Determine current value
                current = None
                if name == "Volume":
                    # handle volume specially in 5% steps
                    delta = -0.05 if event.key in (pygame.K_LEFT, pygame.K_a) else 0.05
                    self.audio.set_volume(self.audio.music_volume + delta)
                else:
                    if name == "Note Bar Position":
                        current = game.settings.get("note_bar_pos", "bottom")
                    elif name == "Note Skin":
                        current = game.settings.get("note_skin", "rect")
                    elif name == "Ghost Tapping":
                        current = "On" if game.settings.get("ghost_tap", True) else "Off"
                    idx = values.index(current)
                    idx = (idx - 1) % len(values) if event.key in (pygame.K_LEFT, pygame.K_a) else (idx + 1) % len(values)
                    apply_fn(values[idx], game.settings)
                    _save_settings(game.settings)

    def draw(self, game: Game, surface: pygame.Surface) -> None:
        draw_title(surface, game.font, "Settings", 80)
        y = 160
        for i, (name, values, _) in enumerate(self._ensure_options(game)):
            is_sel = i == self.selected
            value_str = self._get_value_display(game, name)
            color = (255, 255, 255) if is_sel else (200, 200, 210)
            line = game.font.render(f"{name}: {value_str}", True, color)
            if is_sel:
                glow = int(30 + 20 * (0.5 + 0.5 * math.sin(game.bg_phase * 4)))
                bar = pygame.Rect(70, y - 6, line.get_width() + 20, line.get_height() + 12)
                pygame.draw.rect(surface, (70, 70, 110), bar, border_radius=10)
                pygame.draw.rect(surface, (120 + glow, 120 + glow, 190), bar, width=2, border_radius=10)
            surface.blit(line, (80, y))
            y += 40

        help_line = game.font.render("Up/Down: select  Left/Right: change  Esc: back", True, (220, 220, 240))
        surface.blit(help_line, (80, y + 10))

    def _ensure_options(self, game: Game) -> List[Tuple[str, List[str], Callable[[str, Dict[str, Any]], None]]]:
        if not self.options:
            self.options = [
                ("Volume", [], lambda v, s: None),
                ("Note Bar Position", ["bottom", "middle", "top"], lambda v, s: s.__setitem__("note_bar_pos", v)),
                ("Note Skin", ["rect", "circle"], lambda v, s: s.__setitem__("note_skin", v)),
                ("Ghost Tapping", ["On", "Off"], lambda v, s: s.__setitem__("ghost_tap", v == "On")),
            ]
        return self.options

    def _get_value_display(self, game: Game, name: str) -> str:
        if name == "Volume":
            return f"{int(self.audio.music_volume * 100)}%"
        if name == "Note Bar Position":
            return str(game.settings.get("note_bar_pos", "bottom"))
        if name == "Note Skin":
            return str(game.settings.get("note_skin", "rect"))
        if name == "Ghost Tapping":
            return "On" if game.settings.get("ghost_tap", True) else "Off"
        return ""


class PluginsScene(Scene):
    def __init__(self) -> None:
        self.plugins: List[Tuple[str, str]] = []  # (mod, plugin file)

    def on_enter(self, game: Game) -> None:
        self.plugins = []
        for mod in list_mods():
            plug_dir = os.path.join(MODS_DIR, mod, "plugins")
            if not os.path.isdir(plug_dir):
                continue
            for f in os.listdir(plug_dir):
                if f.lower().endswith((".py", ".json", ".txt")):
                    self.plugins.append((mod, f))

    def handle_event(self, game: Game, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            game.pop_scene()

    def draw(self, game: Game, surface: pygame.Surface) -> None:
        draw_title(surface, game.font, "Plugins", 80)
        if not self.plugins:
            msg = game.font.render("No plugins found in mods/*/plugins.", True, (230, 230, 245))
            surface.blit(msg, (80, 160))
            return
        y = 160
        for mod, f in self.plugins:
            line = game.font.render(f"{mod}/plugins/{f}", True, (220, 220, 240))
            surface.blit(line, (80, y))
            y += 32


class ModsManagerScene(Scene):
    def __init__(self) -> None:
        self.all_mods: List[str] = []
        self.enabled: List[str] = []
        self.selected = 0

    def on_enter(self, game: Game) -> None:
        self.all_mods = sorted([d for d in os.listdir(MODS_DIR) if os.path.isdir(os.path.join(MODS_DIR, d))])
        cur = _load_enabled_mods()
        self.enabled = cur if cur is not None else list(self.all_mods)

    def handle_event(self, game: Game, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                _save_enabled_mods(self.enabled)
                game.pop_scene()
            elif event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % max(1, len(self.all_mods))
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % max(1, len(self.all_mods))
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if not self.all_mods:
                    return
                mod = self.all_mods[self.selected]
                if mod in self.enabled:
                    self.enabled.remove(mod)
                else:
                    self.enabled.append(mod)
            elif event.key == pygame.K_F5:
                _save_enabled_mods(self.enabled)

    def draw(self, game: Game, surface: pygame.Surface) -> None:
        draw_title(surface, game.font, "Mods Manager", 80)
        hint = game.font.render("Enter: toggle  |  F5: save  |  Esc: back", True, (220, 220, 240))
        surface.blit(hint, (80, 120))
        y = 160
        for i, m in enumerate(self.all_mods):
            enabled = m in self.enabled
            marker = "[x]" if enabled else "[ ]"
            color = (255, 255, 255) if i == self.selected else (200, 200, 210)
            text = game.font.render(f"{marker} {m}", True, color)
            surface.blit(text, (80, y))
            y += 34


class CreditsScene(Scene):
    def handle_event(self, game: Game, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            game.pop_scene()

    def draw(self, game: Game, surface: pygame.Surface) -> None:
        draw_title(surface, game.font, "Credits", 80)
        lines = ["FNF Application (Single-file)", "Built with Pygame", "Drop mods into mods/<mod>/*"]
        y = 160
        for line in lines:
            t = game.font.render(line, True, (220, 220, 240))
            surface.blit(t, (80, y))
            y += 36


class PauseScene(Scene):
    def __init__(self, gameplay: 'GameplayScene') -> None:
        self.gameplay = gameplay
        self.items = ["Resume", "Settings", "Exit to Menu"]
        self.selected = 0

    def handle_event(self, game: Game, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._resume(game)
            elif event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % len(self.items)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % len(self.items)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._activate(game)

    def _resume(self, game: Game) -> None:
        pygame.mixer.music.unpause()
        game.pop_scene()

    def _activate(self, game: Game) -> None:
        choice = self.items[self.selected]
        if choice == "Resume":
            self._resume(game)
        elif choice == "Settings":
            game.push_scene(SettingsScene(self.gameplay.audio))
        else:
            # Exit to menu
            self.gameplay.audio.stop()
            game.pop_scene()  # close pause
            game.pop_scene()  # close gameplay

    def draw(self, game: Game, surface: pygame.Surface) -> None:
        # Dim overlay
        w, h = surface.get_size()
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 120))
        surface.blit(dim, (0, 0))
        draw_title(surface, game.font, "Paused", 120)
        y = 200
        for i, s in enumerate(self.items):
            color = (255, 255, 255) if i == self.selected else (210, 210, 220)
            t = game.font.render(s, True, color)
            surface.blit(t, (w//2 - 80, y))
            y += 40


# ------------------------------- Gameplay ---------------------------------- #


# Remapped: Blue=A=Left, Green=S=Down, Orange=W=Up, Pink=D=Right
LANE_KEYS = [pygame.K_a, pygame.K_s, pygame.K_w, pygame.K_d]
LANE_COLORS = [(90, 160, 255), (120, 220, 120), (255, 170, 80), (255, 110, 150)]


class GameplayScene(Scene):
    def __init__(self, song_id: str, audio: AudioManager, on_finish: Optional[Callable[[Game], None]] = None, difficulty: str = "normal", start_in_editor: bool = False) -> None:
        self.song_id = song_id
        self.audio = audio
        self.on_finish = on_finish
        self.difficulty = difficulty
        self.start_in_editor = start_in_editor
        self.chart: Optional[Chart] = None
        self.scroll_speed = 1.0
        self.time_ms = 0.0
        self.hits = 0
        self.misses = 0
        self.hit_window = 120.0
        self.play_started = False
        self.health = 0.5
        self.editor_mode = False
        self._splashes: List[Tuple[int, float]] = []  # (lane_index, life)
        self._sustain_end: List[float] = [0.0, 0.0, 0.0, 0.0]
        self._sustain_start: List[float] = [0.0, 0.0, 0.0, 0.0]  # when sustain started
        self._hp_multiplier = 1.0  # Ctrl modifier for HP changes
        self._opponent_notes: List[Note] = []  # opponent notes coming from top
        self._particles: List[Tuple[float, float, float, float, Tuple[int, int, int]]] = []  # x,y,vx,vy,color

    def on_enter(self, game: Game) -> None:
        self.chart = load_chart(self.song_id)
        # keep a backreference to the Game for audio mode lookup
        self.game_ref = game
        self.meta = load_song_meta(self.song_id)
        self.time_ms = 0.0
        self.hits = 0
        self.misses = 0
        self.play_started = False
        bpm = self.chart.get("bpm", 120) if self.chart else 120
        base_speed = 0.45 + (float(bpm) / 300.0)
        if self.difficulty == "easy":
            self.hit_window = 160.0
            self.scroll_speed = base_speed * 0.9
        elif self.difficulty == "hard":
            self.hit_window = 90.0
            self.scroll_speed = base_speed * 1.1
        else:
            self.hit_window = 120.0
            self.scroll_speed = base_speed
        self.health = 0.5
        self.editor_mode = bool(self.start_in_editor)
        if self.editor_mode:
            try:
                pygame.mixer.music.pause()
            except Exception:
                pass
        self._sustain_end = [0.0, 0.0, 0.0, 0.0]
        self._sustain_start = [0.0, 0.0, 0.0, 0.0]
        self._hp_multiplier = 1.0
        # Generate opponent notes from same chart (offset lanes)
        if self.chart:
            lanes = self.chart.get("lanes", 4)
            self._opponent_notes = []
            for n in self.chart["notes"]:
                opp_note = {"time": n["time"], "lane": (n["lane"] + 2) % lanes, "sustain": n.get("sustain", 0.0)}
                self._opponent_notes.append(opp_note)
        self._particles = []

    def _ensure_music(self) -> None:
        if not self.play_started:
            # prefer chart-defined audioMode
            mode = str(getattr(self, 'meta', {}).get('audioMode', 'auto')) if hasattr(self, 'meta') else 'auto'
            self.audio.play_song(self.song_id, mode)
            self.play_started = True

    def handle_event(self, game: Game, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            pygame.mixer.music.pause()
            game.push_scene(PauseScene(self))
            return
        # in-game editor disabled; external editor is launched from Freeplay (7)
        if event.type == pygame.KEYDOWN:
            for lane_index, key in enumerate(LANE_KEYS):
                if event.key == key:
                    if not self._attempt_hit(lane_index, game) and not game.settings.get("ghost_tap", True):
                        # Penalize ghost tap when disabled
                        self.misses += 1
                        self.health = max(0.0, self.health - 0.05 * self._hp_multiplier)
        if event.type == pygame.MOUSEBUTTONDOWN and (pygame.key.get_mods() & pygame.KMOD_CTRL):
            if event.button == 1:
                self.health = min(1.0, self.health + 0.05 * self._hp_multiplier)
            elif event.button == 3:
                self.health = max(0.0, self.health - 0.05 * self._hp_multiplier)

    def _attempt_hit(self, lane_index: int, game: Game) -> bool:
        if not self.chart:
            return False
        for note in self.chart["notes"]:
            if note["lane"] != lane_index:
                continue
            delta = abs(note["time"] - self.time_ms)
            if delta <= self.hit_window:
                note["time"] = -1e9
                self.hits += 1
                self.health = min(1.0, self.health + 0.03 * self._hp_multiplier)
                self._splashes.append((lane_index, 0.5))
                # Generate particles on hit
                w, h = game.size
                lanes = self.chart.get("lanes", 4)
                lane_w = min(160, max(80, w // (lanes + 2)))
                left = (w - lanes * lane_w) // 2
                pos = game.settings.get("note_bar_pos", "bottom")
                hit_y = int(h * 0.8) if pos != "top" else int(h * 0.2)
                px = left + lane_index * lane_w + lane_w // 2
                py = hit_y
                for _ in range(8):
                    self._particles.append((
                        px, py,
                        (random.random() - 0.5) * 120, (random.random() - 0.5) * 120,
                        LANE_COLORS[lane_index % len(LANE_COLORS)]
                    ))
                # simple combo
                self.combo = getattr(self, "combo", 0) + 1
                # sustain handling: record start time and end time
                sustain_end = note.get("sustain", 0.0)
                if sustain_end > 0:
                    self._sustain_start[lane_index] = self.time_ms
                    self._sustain_end[lane_index] = self.time_ms + sustain_end
                return True
        return False

    def update(self, game: Game, dt: float) -> None:
        self._ensure_music()
        self.time_ms += dt * 1000.0
        # HP multiplier from settings (menu-toggle)
        self._hp_multiplier = float(getattr(game, 'settings', {}).get('hp_loss_mult', 1.0))
        if self._splashes:
            self._splashes = [(lane, life - dt) for (lane, life) in self._splashes if life - dt > 0]
        # Update particles
        if self._particles:
            new_parts = []
            for (x, y, vx, vy, col) in self._particles:
                x2 = x + vx * dt
                y2 = y + vy * dt
                vx2 = vx * 0.95
                vy2 = vy * 0.95
                # Remove if velocity too low
                if abs(vx2) > 0.1 or abs(vy2) > 0.1:
                    new_parts.append((x2, y2, vx2, vy2, col))
            self._particles = new_parts
        if self.chart:
            for note in self.chart["notes"]:
                if 0 <= note["time"] < self.time_ms - self.hit_window and note["lane"] >= 0:
                    note["time"] = -1e9
                    self.misses += 1
                    self.health = max(0.0, self.health - 0.06 * self._hp_multiplier)
                    self.combo = 0
        # Opponent hits: when opponent note reaches receptor, player loses HP
        for note in self._opponent_notes:
            t = note.get("time", -1)
            if t < 0:
                continue
            if abs(t - self.time_ms) <= self.hit_window:
                note["time"] = -1e9
                self.health = max(0.0, self.health - 0.03 * self._hp_multiplier)
        # sustain check: reward when holding; drain when not
        keys = pygame.key.get_pressed()
        for lane_index, end_time in enumerate(self._sustain_end):
            if end_time > self.time_ms:
                if keys[LANE_KEYS[lane_index]]:
                    # small continuous heal while correctly holding
                    self.health = min(1.0, self.health + 0.004 * self._hp_multiplier * dt * 60)
                else:
                    # continuous damage while not holding
                    self.health = max(0.0, self.health - 0.01 * self._hp_multiplier * dt * 60)
            elif end_time > 0:
                # sustain completed
                self._sustain_end[lane_index] = 0.0
                self._sustain_start[lane_index] = 0.0
        if self.chart and all(n["time"] < 0 for n in self.chart["notes"]):
            if self.time_ms > 5000:
                self.audio.stop()
                if self.on_finish:
                    self.on_finish(game)
                else:
                    game.pop_scene()

    def draw(self, game: Game, surface: pygame.Surface) -> None:
        w, h = game.size
        lanes = self.chart["lanes"] if self.chart else 4
        lane_w = min(140, max(70, (w // 2 - 120) // lanes))
        # Two columns: opponent on left, player on right
        margin = 60
        left_col_x = margin
        right_col_x = w - margin - lanes * lane_w
        pos = game.settings.get("note_bar_pos", "bottom")
        if pos == "top":
            hit_y = int(h * 0.2)
        elif pos == "middle":
            hit_y = int(h * 0.5)
        else:
            hit_y = int(h * 0.8)
        # Determine scroll direction toward receptor based on bar position
        # future notes (t_until > 0):
        # - bottom: render above receptor (y < hit_y) so they scroll down -> sign = -1
        # - top: render below receptor (y > hit_y) so they scroll up -> sign = +1
        # - middle: use bottom-style for consistency
        scroll_sign = 1 if pos == "top" else -1

        # Opponent receptor at top (kept) but moved to left column
        opp_hit_y = int(h * 0.2) if pos == "bottom" else int(h * 0.8)
        opp_scroll_sign = -1 if pos == "bottom" else 1
        
        # Lanes and receptors
        for i in range(lanes):
            x = right_col_x + i * lane_w
            pygame.draw.rect(surface, (35, 35, 50), (x + 6, 60, lane_w - 12, h - 120), border_radius=10)
            color = LANE_COLORS[i % len(LANE_COLORS)]
            # Player receptor
            rect = pygame.Rect(x + 10, hit_y, lane_w - 20, 16)
            grad = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            for yy in range(rect.height):
                t = yy / max(1, rect.height - 1)
                c = (int(color[0]*(0.8+t*0.2)), int(color[1]*(0.8+t*0.2)), int(color[2]*(0.8+t*0.2)), 255)
                pygame.draw.line(grad, c, (0, yy), (rect.width, yy))
            surface.blit(grad, rect)
            pressed = pygame.key.get_pressed()[LANE_KEYS[i]]
            if pressed:
                glow = pygame.Surface((rect.width + 18, rect.height + 18), pygame.SRCALPHA)
                pygame.draw.ellipse(glow, (*color, 90), glow.get_rect())
                surface.blit(glow, glow.get_rect(center=rect.center))
            pygame.draw.rect(surface, (255,255,255), rect, width=2, border_radius=6)
            # Opponent receptor at top
            opp_x = left_col_x + i * lane_w
            opp_rect = pygame.Rect(opp_x + 10, opp_hit_y, lane_w - 20, 16)
            opp_grad = pygame.Surface((opp_rect.width, opp_rect.height), pygame.SRCALPHA)
            for yy in range(opp_rect.height):
                t = yy / max(1, opp_rect.height - 1)
                opp_col = (int(color[0]*0.5), int(color[1]*0.5), int(color[2]*0.5), 255)
                pygame.draw.line(opp_grad, opp_col, (0, yy), (opp_rect.width, yy))
            surface.blit(opp_grad, opp_rect)
            pygame.draw.rect(surface, (180,180,180), opp_rect, width=2, border_radius=6)
            # Sustain bar extending from receptor (when holding)
            if self._sustain_end[i] > self.time_ms and self._sustain_start[i] > 0:
                remaining = self._sustain_end[i] - self.time_ms
                total = self._sustain_end[i] - self._sustain_start[i]
                if total > 0:
                    length_px = int(remaining * self.scroll_speed)
                    if scroll_sign == -1:
                        # bottom: extend upward
                        sustain_rect = pygame.Rect(x + 22, hit_y - length_px, lane_w - 44, length_px)
                    else:
                        # top: extend downward
                        sustain_rect = pygame.Rect(x + 22, hit_y + 16, lane_w - 44, length_px)
                    pygame.draw.rect(surface, (*color, 200), sustain_rect, border_radius=6)
                    pygame.draw.rect(surface, (255,255,255), sustain_rect, width=2, border_radius=6)

        # Player notes (smaller to fit opponent)
        if self.chart:
            for note in self.chart["notes"]:
                if note["time"] < 0:
                    continue
                lane = note["lane"]
                x = right_col_x + lane * lane_w
                t_until = note["time"] - self.time_ms
                y = hit_y + scroll_sign * int(t_until * self.scroll_speed)
                if y < 40 or y > h + 1000:
                    continue
                color = LANE_COLORS[lane % len(LANE_COLORS)]
                # Smaller notes
                note_size = max(8, (lane_w - 28) // 4)
                if game.settings.get("note_skin", "rect") == "circle":
                    pygame.draw.circle(surface, color, (x + lane_w // 2, y), note_size)
                    pygame.draw.circle(surface, (255,255,255), (x + lane_w // 2, y), note_size, width=1)
                else:
                    body = pygame.Rect(x + 18, y - 8, lane_w - 36, 16)
                    pygame.draw.rect(surface, color, body, border_radius=4)
                    pygame.draw.rect(surface, (255,255,255), body, width=1, border_radius=4)
                # Note sustain preview (before hitting)
                if note.get("sustain", 0.0) > 0:
                    length_px = int(note["sustain"] * self.scroll_speed)
                    if scroll_sign == -1:
                        pygame.draw.rect(surface, (*color, 150), (x + 24, y - length_px, lane_w - 48, length_px), border_radius=4)
                    else:
                        pygame.draw.rect(surface, (*color, 150), (x + 24, y, lane_w - 48, length_px), border_radius=4)
        
        # Opponent notes (from top)
        for note in self._opponent_notes:
            if note.get("time", -1) < 0:
                continue
            lane = note.get("lane", 0)
            x = left_col_x + lane * lane_w
            t_until = note["time"] - self.time_ms
            y = opp_hit_y + opp_scroll_sign * int(t_until * self.scroll_speed)
            if y < 40 or y > h + 1000:
                continue
            opp_color = tuple(max(0, c - 80) for c in LANE_COLORS[lane % len(LANE_COLORS)])
            note_size = max(8, (lane_w - 28) // 4)
            if game.settings.get("note_skin", "rect") == "circle":
                pygame.draw.circle(surface, opp_color, (x + lane_w // 2, y), note_size)
                pygame.draw.circle(surface, (150,150,150), (x + lane_w // 2, y), note_size, width=1)
            else:
                body = pygame.Rect(x + 18, y - 8, lane_w - 36, 16)
                pygame.draw.rect(surface, opp_color, body, border_radius=4)
                pygame.draw.rect(surface, (150,150,150), body, width=1, border_radius=4)

        # Particles
        for (x, y, vx, vy, col) in self._particles:
            speed = math.sqrt(vx*vx + vy*vy)
            alpha = int(200 * min(1.0, speed / 50.0))
            size = max(2, int(4 * min(1.0, speed / 50.0)))
            if alpha > 0 and size > 0:
                particle = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                pygame.draw.circle(particle, (*col, alpha), (size, size), size)
                surface.blit(particle, (x - size, y - size))
        
        # Splash effects at receptors (player column on right)
        for (lane, life) in self._splashes:
            cx = right_col_x + lane * lane_w + lane_w // 2
            cy = hit_y + 8
            alpha = int(180 * max(0.0, life))
            rad = int(12 + (0.5 - max(0.0, life)) * 24)
            splash = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA)
            pygame.draw.circle(splash, (255, 255, 255, alpha), (rad, rad), rad, width=3)
            surface.blit(splash, (cx - rad, cy - rad))

        # HUD and placeholder character
        # Health bar
        hb_w, hb_h = 300, 18
        hb_x, hb_y = w - hb_w - 20, 16
        pygame.draw.rect(surface, (60, 60, 80), (hb_x, hb_y, hb_w, hb_h), border_radius=6)
        pygame.draw.rect(surface, (120, 120, 160), (hb_x, hb_y, hb_w, hb_h), width=2, border_radius=6)
        fill_w = int(hb_w * self.health)
        fill_color = (80, 220, 120) if self.health >= 0.3 else (230, 90, 90)
        pygame.draw.rect(surface, fill_color, (hb_x + 2, hb_y + 2, max(0, fill_w - 4), hb_h - 4), border_radius=6)
        # Opponent bar (mirror left, using player's health mirror for display only)
        ob_w, ob_h = 200, 12
        ob_x, ob_y = 20, 20
        pygame.draw.rect(surface, (60, 60, 80), (ob_x, ob_y, ob_w, ob_h), border_radius=6)
        pygame.draw.rect(surface, (120, 120, 160), (ob_x, ob_y, ob_w, ob_h), width=2, border_radius=6)
        # For now, show inverse of player health to indicate pressure
        ob_fill = int(ob_w * (1.0 - self.health))
        pygame.draw.rect(surface, (220, 120, 120), (ob_x + 2, ob_y + 2, max(0, ob_fill - 4), ob_h - 4), border_radius=6)
        # HUD text
        if self.chart:
            combo = getattr(self, "combo", 0)
            ctrl_text = " [2x HP]" if self._hp_multiplier > 1.0 else ""
            hud = game.font.render(
                f"{self.chart['title']}  H:{self.hits} M:{self.misses} C:{combo}{ctrl_text} {'[EDIT]' if self.editor_mode else ''}", True, (235, 235, 245)
            )
            surface.blit(hud, (20, 16))
        # Editor overlay GUI
        if self.editor_mode and self.chart:
            # timeline
            last_t = self.chart['notes'][-1]['time'] if self.chart['notes'] else 60000
            total = max(1.0, last_t)
            bar = pygame.Rect(80, h - 40, w - 160, 10)
            pygame.draw.rect(surface, (40, 40, 60), bar, border_radius=6)
            pygame.draw.rect(surface, (120, 120, 160), bar, width=2, border_radius=6)
            progress = min(1.0, self.time_ms / total)
            fill = pygame.Rect(bar.left + 2, bar.top + 2, int((bar.width - 4) * progress), bar.height - 4)
            pygame.draw.rect(surface, (200, 200, 255), fill, border_radius=6)
            # hints
            help1 = "Editor: Space pause | Lane=add | Shift+Lane=hold | E=event | Del=remove | S=save"
            thelp = game.font.render(help1, True, (220, 220, 240))
            surface.blit(thelp, (80, h - 70))
        bob = int(6 * (1 + math.sin(self.time_ms / 200.0)))
        char_w, char_h = 120, 200
        char_x = max(20, right_col_x - char_w - 40)
        char_y = hit_y - char_h - 20 - bob
        pygame.draw.rect(surface, (80, 120, 200), (char_x, char_y, char_w, char_h), border_radius=12)
        pygame.draw.rect(surface, (140, 180, 240), (char_x, char_y, char_w, char_h), width=3, border_radius=12)

    def _save_chart(self) -> None:
        if not self.chart:
            return
        # Save into first enabled mod or create basic_mod
        enabled = _load_enabled_mods()
        target_mod = None
        if enabled:
            target_mod = enabled[0]
        else:
            mods = list_mods()
            target_mod = mods[0] if mods else "basic_mod"
        mod_dir = os.path.join(MODS_DIR, target_mod)
        os.makedirs(os.path.join(mod_dir, "data"), exist_ok=True)
        path = os.path.join(mod_dir, "data", f"{self.song_id}.json")
        to_save = {
            "id": self.song_id,
            "title": self.chart.get("title", self.song_id),
            "artist": self.chart.get("artist", "Unknown"),
            "bpm": self.chart.get("bpm", 120),
            "lanes": self.chart.get("lanes", 4),
            "notes": [
                {"time": float(n["time"] if n["time"] >= 0 else 0.0), "lane": int(n["lane"]), "sustain": float(n["sustain"]) }
                for n in sorted(self.chart["notes"], key=lambda x: x["time"])
            ],
            "events": self.chart.get("events", []),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(to_save, f, indent=2)
        except Exception:
            pass


# -------------------------------- Entrypoint -------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--editor", dest="editor", nargs="?")
    args, _ = parser.parse_known_args()
    if args.editor:
        EditorApp(args.editor).run()
        return
    game = Game(width=1280, height=720, window_title="FNF Application (Single-file)", target_fps=144)
    game.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)


