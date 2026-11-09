#!/usr/bin/env python
"""hoi4.py: a bridge that lets Claude watch and play Hearts of Iron IV.

How it works
  * The "Claude Bridge" mod (bridge_mod/claude_bridge) writes the player's state
    and world news into game.log. This script reads and summarizes those lines.
  * Screenshots of the game window are saved as PNG files with a coordinate grid.
  * Mouse and keyboard input is sent to the game window with SendInput.

Coordinates are always game-window pixels at full resolution. The grid labels
on screenshots show these numbers even when the image is scaled down.

Run with the project venv:
  .venv\\Scripts\\python.exe hoi4.py <command> [args]      (see --help)
Chain several commands in one call:
  hoi4.py do "key y ; wait 0.5 ; look"
"""
__version__ = "0.1.7"

import argparse
import ctypes
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
SHOTS_DIR = ROOT / "shots"
MOD_SRC = ROOT / "bridge_mod" / "claude_bridge"
GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Hearts of Iron IV")
USER_DIR = Path.home() / "Documents" / "Paradox Interactive" / "Hearts of Iron IV"
LOG_PATH = USER_DIR / "logs" / "game.log"
DLC_LOAD = USER_DIR / "dlc_load.json"
MOD_ENTRY = "mod/claude_bridge.mod"
MAX_SHOTS = 200

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if __name__ == "__main__":
    # Helper modules (hoi4_actions) do `import hoi4`: give them this same module, not a second copy.
    sys.modules.setdefault("hoi4", sys.modules["__main__"])


class BridgeError(Exception):
    """A problem worth a one-line message instead of a traceback."""


# --------------------------------------------------------------------------
# Win32 plumbing
# --------------------------------------------------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Use physical pixels everywhere, so screenshots and clicks agree.
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        user32.SetProcessDPIAware()

ULONG_PTR = ctypes.c_size_t
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
user32.VkKeyScanW.restype = ctypes.c_short
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = ctypes.c_short
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x4, 0x8
MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_VIRTUALDESK = 0x1, 0x8000, 0x4000
MOUSEEVENTF_WHEEL = 0x0800
MOUSE_BUTTONS = {"left": (0x2, 0x4), "right": (0x8, 0x10), "middle": (0x20, 0x40)}


def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    if user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)) != len(inputs):
        raise BridgeError(f"SendInput was blocked (error {ctypes.get_last_error()}). "
                          "Is a window with higher privileges (e.g. an admin app) in front?")


def _mouse_input(dx=0, dy=0, flags=0, data=0):
    return INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(dx=dx, dy=dy, mouseData=data & 0xFFFFFFFF, dwFlags=flags))


def _key_input(scan, up=False, extended=False, unicode_char=None):
    if unicode_char is not None:
        flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
        return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=ord(unicode_char), dwFlags=flags))
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags))


def _process_name(pid):
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def find_window():
    """Return the HWND of the main HOI4 window, or None."""
    found = []

    @WNDENUMPROC
    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if _process_name(pid.value) == "hoi4.exe":
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                found.append(((rect.right - rect.left) * (rect.bottom - rect.top), hwnd))
        return True

    user32.EnumWindows(callback, 0)
    return max(found)[1] if found else None


_GAME = {"hwnd": None}  # set by need_window(); input helpers re-focus it before acting


def need_window():
    hwnd = find_window()
    if not hwnd:
        raise BridgeError("Hearts of Iron IV is not running (no hoi4.exe window). Use: hoi4.py launch")
    _GAME["hwnd"] = hwnd
    return hwnd


def ensure_front():
    """Bring the game back to the front if something else took focus (cheap when it is already in front)."""
    hwnd = _GAME["hwnd"]
    if hwnd and user32.GetForegroundWindow() != hwnd:
        focus(hwnd)


def client_rect(hwnd):
    """(left, top, width, height) of the game's drawable area, in screen pixels."""
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, rect.right, rect.bottom


def focus(hwnd, tries=8):
    """Bring the game to the front so it receives input. Windows refuses now and then (for example while the
    user is typing in another window), so try a few times over about 5 seconds before giving up."""
    for attempt in range(tries):
        try:
            return _focus_once(hwnd)
        except BridgeError:
            if attempt == tries - 1:
                raise
            time.sleep(0.6)


def _focus_once(hwnd):
    if user32.GetForegroundWindow() == hwnd:
        return
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    # Windows only lets the process that sent the last input change the
    # foreground window, so send a harmless zero-pixel mouse move first.
    _send(_mouse_input(0, 0, MOUSEEVENTF_MOVE))
    user32.SetForegroundWindow(hwnd)
    if user32.GetForegroundWindow() != hwnd:
        fg = user32.GetForegroundWindow()
        me = kernel32.GetCurrentThreadId()
        other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        if other:
            user32.AttachThreadInput(me, other, True)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if other:
            user32.AttachThreadInput(me, other, False)
    if user32.GetForegroundWindow() != hwnd:
        # A lone Alt tap also counts as "last input" and is the classic way past the foreground lock.
        alt = (0x38, False)
        _send(_key_input(alt[0]), _key_input(alt[0], up=True))
        user32.SetForegroundWindow(hwnd)
    if user32.GetForegroundWindow() != hwnd:
        user32.SwitchToThisWindow(hwnd, True)
    time.sleep(0.3)
    if user32.GetForegroundWindow() != hwnd:
        raise BridgeError("Could not bring the HOI4 window to the front.")


# --------------------------------------------------------------------------
# Mouse and keyboard
# --------------------------------------------------------------------------
VK = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B, "space": 0x20, "pgup": 0x21, "pageup": 0x21, "pgdn": 0x22,
    "pagedown": 0x22, "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27,
    "down": 0x28, "insert": 0x2D, "delete": 0x2E, "del": 0x2E,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12,
    "minus": 0xBD, "equals": 0xBB, "plus": 0xBB, "comma": 0xBC, "period": 0xBE, "slash": 0xBF,
    "semicolon": 0xBA, "quote": 0xDE, "lbracket": 0xDB, "rbracket": 0xDD, "backslash": 0xDC,
}
VK.update({f"f{i}": 0x6F + i for i in range(1, 13)})
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}
# Keys addressed directly by scan code (layout independent).
SCAN_KEYS = {
    "kp_plus": (0x4E, False), "kp_minus": (0x4A, False), "kp_enter": (0x1C, True),
    "kp_multiply": (0x37, False), "kp_divide": (0x35, True),
    "console": (0x29, False), "grave": (0x29, False), "tilde": (0x29, False),
    "shift": (0x2A, False), "ctrl": (0x1D, False), "control": (0x1D, False), "alt": (0x38, False),
}
SCAN_KEYS.update({f"kp_{i}": (s, False) for i, s in
                  zip(range(10), (0x52, 0x4F, 0x50, 0x51, 0x4B, 0x4C, 0x4D, 0x47, 0x48, 0x49))})


def key_scan(name):
    """Map a key name ("y", "esc", "f1", "kp_plus", "console") to (scan code, extended)."""
    n = name.lower()
    if n in SCAN_KEYS:
        return SCAN_KEYS[n]
    if n in VK:
        vk = VK[n]
    elif len(name) == 1:
        res = user32.VkKeyScanW(name)
        if res == -1:
            raise BridgeError(f"Unknown key: {name}")
        vk = res & 0xFF
    else:
        raise BridgeError(f"Unknown key: {name}")
    return user32.MapVirtualKeyW(vk, 0), vk in EXTENDED_VKS


def _release(keys):
    """Release (scan, extended) keys in reverse order, ignoring errors so nothing stays held."""
    for scan, ext in reversed(keys):
        try:
            _send(_key_input(scan, up=True, extended=ext))
        except BridgeError:
            pass


def press_combo(combo, times=1, hold=0.05):
    """Press a combo like "y", "alt+q", "ctrl+shift+s". Use "plus"/"minus" for those keys."""
    names = [p for p in combo.split("+") if p]
    if not names:
        raise BridgeError(f"Bad key combo: {combo!r} (write the + key as 'plus')")
    *mods, main = names
    mod_scans = [key_scan(m) for m in mods]
    main_scan = key_scan(main)
    for _ in range(times):
        ensure_front()
        held = []
        try:
            for scan, ext in mod_scans:
                _send(_key_input(scan, extended=ext))
                held.append((scan, ext))
            time.sleep(0.02 if mods else 0)
            _send(_key_input(main_scan[0], extended=main_scan[1]))
            held.append(main_scan)
            time.sleep(hold)
        finally:
            _release(held)
        time.sleep(0.06)


def type_text(text, delay=0.02):
    ensure_front()
    shift = key_scan("shift")
    caps = bool(user32.GetKeyState(0x14) & 1)  # Caps Lock flips the case of letters
    for ch in text:
        if ch == "\n":
            press_combo("enter")
            continue
        res = user32.VkKeyScanW(ch)
        mods = (res >> 8) & 0xFF if res != -1 else 0
        if res == -1 or mods & 0b110:  # unmapped, or needs Ctrl/Alt (AltGr): send as unicode
            _send(_key_input(0, unicode_char=ch), _key_input(0, up=True, unicode_char=ch))
        else:
            scan = user32.MapVirtualKeyW(res & 0xFF, 0)
            use_shift = bool(mods & 1) != (caps and ch.isascii() and ch.isalpha())
            held = []
            try:
                if use_shift:
                    _send(_key_input(shift[0]))
                    held.append(shift)
                _send(_key_input(scan), _key_input(scan, up=True))
            finally:
                _release(held)
        time.sleep(delay)


def to_screen(hwnd, x, y):
    left, top, width, height = client_rect(hwnd)
    if not (0 <= x < width and 0 <= y < height):
        raise BridgeError(f"({x}, {y}) is outside the game window (size {width}x{height}).")
    return left + int(round(x)), top + int(round(y))


def move_mouse(sx, sy):
    """Move the cursor to screen pixel (sx, sy)."""
    user32.SetCursorPos(sx, sy)
    vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
    vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
    nx = int(round((sx - vx) * 65535 / max(vw - 1, 1)))
    ny = int(round((sy - vy) * 65535 / max(vh - 1, 1)))
    _send(_mouse_input(nx, ny, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK))


def hold_mods(mods):
    """Press modifier keys down; returns the list to pass to _release()."""
    held = []
    try:
        for m in mods:
            scan, ext = key_scan(m)
            _send(_key_input(scan, extended=ext))
            held.append((scan, ext))
    except BridgeError:
        _release(held)
        raise
    return held


def _button_up(flag):
    try:
        _send(_mouse_input(flags=flag))
    except BridgeError:
        pass


def click(hwnd, x, y, button="left", double=False, mods=()):
    ensure_front()
    sx, sy = to_screen(hwnd, x, y)
    down, up = MOUSE_BUTTONS[button]
    move_mouse(sx, sy)
    time.sleep(0.08)
    held = hold_mods(mods)
    try:
        for _ in range(2 if double else 1):
            try:
                _send(_mouse_input(flags=down))
                time.sleep(0.05)
            finally:
                _button_up(up)
            time.sleep(0.07)
    finally:
        _release(held)


def drag(hwnd, x1, y1, x2, y2, button="left", mods=(), steps=15):
    ensure_front()
    sx1, sy1 = to_screen(hwnd, x1, y1)
    sx2, sy2 = to_screen(hwnd, x2, y2)
    down, up = MOUSE_BUTTONS[button]
    move_mouse(sx1, sy1)
    time.sleep(0.08)
    held = hold_mods(mods)
    try:
        _send(_mouse_input(flags=down))
        time.sleep(0.08)
        for i in range(1, steps + 1):
            move_mouse(round(sx1 + (sx2 - sx1) * i / steps), round(sy1 + (sy2 - sy1) * i / steps))
            time.sleep(0.02)
        time.sleep(0.08)
    finally:
        _button_up(up)
        _release(held)


def scroll(hwnd, x, y, clicks):
    ensure_front()
    sx, sy = to_screen(hwnd, x, y)
    move_mouse(sx, sy)
    time.sleep(0.05)
    step = 1 if clicks > 0 else -1
    for _ in range(abs(clicks)):
        _send(_mouse_input(flags=MOUSEEVENTF_WHEEL, data=120 * step))
        time.sleep(0.05)


# --------------------------------------------------------------------------
# Screenshots
# --------------------------------------------------------------------------
def grab(hwnd):
    from PIL import ImageGrab
    left, top, width, height = client_rect(hwnd)
    return ImageGrab.grab(bbox=(left, top, left + width, top + height), all_screens=True)


def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def annotate(img, origin=(0, 0), scale=1.0, grid=100, marks=()):
    """Scale a window crop and draw a coordinate grid in window pixels."""
    from PIL import Image, ImageDraw
    ox, oy = origin
    w, h = img.size
    if scale != 1.0:
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    font = _font(max(11, round(13 * max(scale, 0.8))))
    if grid:
        label_every = 1 if grid * scale >= 55 else 2
        for axis in ("x", "y"):
            start, length = (ox, w) if axis == "x" else (oy, h)
            first = math.ceil(start / grid) * grid
            for n, g in enumerate(range(first, start + length, grid)):
                pos = (g - start) * scale
                strong = g % (grid * 5) == 0
                color = (255, 230, 0, 110 if strong else 55)
                if axis == "x":
                    draw.line([(pos, 0), (pos, img.height)], fill=color, width=1)
                else:
                    draw.line([(0, pos), (img.width, pos)], fill=color, width=1)
                if (g // grid) % label_every:
                    continue
                text = str(g)
                tw = draw.textlength(text, font=font)
                if axis == "x":
                    box = (pos + 2, 1, pos + 4 + tw, 3 + font.size)
                else:
                    box = (1, pos + 1, 3 + tw, pos + 3 + font.size)
                draw.rectangle(box, fill=(0, 0, 0, 170))
                draw.text((box[0] + 1, box[1]), text, fill=(255, 235, 60, 255), font=font)
    for mx, my in marks:
        px, py = (mx - ox) * scale, (my - oy) * scale
        r = 9
        draw.ellipse((px - r, py - r, px + r, py + r), outline=(255, 40, 40, 255), width=2)
        draw.line([(px - r - 5, py), (px + r + 5, py)], fill=(255, 40, 40, 255), width=1)
        draw.line([(px, py - r - 5), (px, py + r + 5)], fill=(255, 40, 40, 255), width=1)
        text = f"{mx},{my}"
        draw.rectangle((px + r + 2, py - 8, px + r + 6 + draw.textlength(text, font=font), py + 8),
                       fill=(0, 0, 0, 170))
        draw.text((px + r + 4, py - 8), text, fill=(255, 90, 90, 255), font=font)
    return img


def save_shot(img, tag="look"):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOTS_DIR / f"{datetime.now():%Y%m%d_%H%M%S_%f}"[:-3]
    path = path.with_name(path.name + f"_{tag}.png")
    img.save(path)
    shots = sorted(SHOTS_DIR.glob("*.png"))
    for old in shots[:-MAX_SHOTS]:
        old.unlink(missing_ok=True)
    return path


def take_look(hwnd, scale=0.6, grid=100, region=None, marks=(), tag="look"):
    focus(hwnd)
    img = grab(hwnd)
    if img.getbbox() is None or max(img.convert("L").getextrema()) < 8:
        print("warning: the screenshot is black. The game may be minimized or in exclusive fullscreen.")
    origin = (0, 0)
    if region:
        x0, y0, x1, y1 = region
        img = img.crop((x0, y0, x1, y1))
        origin = (x0, y0)
    shot = annotate(img, origin=origin, scale=scale, grid=grid, marks=marks)
    path = save_shot(shot, tag)
    full_w, full_h = client_rect(hwnd)[2:]
    where = f"region {region}" if region else f"window {full_w}x{full_h}"
    print(f"screenshot: {path}  ({where}, image {shot.width}x{shot.height}, scale {scale})")
    return path


# --------------------------------------------------------------------------
# game.log reading
# --------------------------------------------------------------------------
# Lines look like "[10:02:18][1936.01.01.12][effectbase.cpp:1783]: msg"; the date and the
# source tag are each optional (log effect lines often have no source tag).
LINE_RE = re.compile(r"^\[(?P<clock>\d\d:\d\d:\d\d)\](?:\[(?P<date>\d+\.\d+\.\d+\.\d+)\])?(?:\[[^\]]*\])?: (?P<msg>.*)$")


def log_size():
    try:
        return LOG_PATH.stat().st_size
    except FileNotFoundError:
        return 0


def read_log(start=0):
    """Complete lines of game.log from byte offset `start`. Returns (lines, new_offset)."""
    if not LOG_PATH.exists():
        return [], 0
    if start > log_size():  # the game restarted and truncated the log
        start = 0
    with open(LOG_PATH, "rb") as f:
        f.seek(start)
        data = f.read()
    cut = data.rfind(b"\n")
    if cut < 0:
        return [], start
    return data[:cut + 1].decode("utf-8", "replace").splitlines(), start + cut + 1


def parse_cb(line):
    """Parse a Claude Bridge line into a dict, or return None."""
    m = LINE_RE.match(line)
    if not m or not m["msg"].startswith("@CB;"):
        return None
    parts = m["msg"].split(";")
    rec = {"kind": parts[1] if len(parts) > 1 else "", "date": m["date"] or "", "clock": m["clock"]}
    for part in parts[2:]:
        if "=" in part:
            key, value = part.split("=", 1)
            if key in rec:  # never let a field overwrite kind/date/clock
                key = "_" + key
            rec[key] = value.strip()
    return rec


def records(start=0):
    lines, end = read_log(start)
    return [r for r in map(parse_cb, lines) if r], end


def last_report(recs):
    """The most recent complete rep_begin..rep_end block."""
    end = None
    for i in range(len(recs) - 1, -1, -1):
        if recs[i]["kind"] == "rep_end" and end is None:
            end = i
        elif recs[i]["kind"] == "rep_begin" and end is not None:
            return recs[i:end + 1]
    return None


def last_kind(recs, kind):
    for r in reversed(recs):
        if r["kind"] == kind:
            return r
    return None


def game_date(date):
    """'1936.01.07.24' -> datetime.date (hour 24 counts as the next day)."""
    from datetime import date as _date, timedelta
    y, m, d, h = (int(v) for v in date.split("."))
    return _date(y, m, d) + timedelta(days=1 if h >= 24 else 0)


def days_between(a, b):
    try:
        return (game_date(b["date"]) - game_date(a["date"])).days
    except (KeyError, ValueError):
        return "?"


def nice_date(date):
    if not date:
        return "?"
    try:
        hour = int(date.split(".")[3])
        return f"{game_date(date):%Y-%m-%d} {hour % 24:02d}:00"
    except (ValueError, IndexError):
        return date


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def fnum(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def f0(value):
    n = fnum(value)
    return "?" if n is None else f"{n:,.0f}"


def f1(value):
    n = fnum(value)
    return "?" if n is None else f"{n:,.1f}"


def pct(value):
    """0-1 ratios as percentages (values already above 1 are taken as percent)."""
    n = fnum(value)
    if n is None:
        return "?"
    return f"{n:.0f}%" if n > 1.0001 else f"{n * 100:.0f}%"


def signed(value, digits=2):
    n = fnum(value)
    return "?" if n is None else f"{n:+.{digits}f}"


def heartbeat_line(hb):
    if not hb:
        return "no daily heartbeat in game.log yet (unpause for one day, or the mod is not loaded)"
    return (f"{nice_date(hb['date'])} | {hb.get('tag')} | PP {f1(hb.get('pp'))} ({signed(hb.get('ppd'))}/day) | "
            f"stability {pct(hb.get('stab'))} | war support {pct(hb.get('ws'))} | "
            f"manpower {f1(hb.get('mpk'))}k | divisions {f0(hb.get('divs'))} | command power {f1(hb.get('cp'))}")


def format_report(block):
    g = defaultdict(list)
    for r in block:
        g[r["kind"]].append(r)
    one = lambda k: g[k][0] if g[k] else {}
    c, p, ind, ter, res, army, war = (one(k) for k in
                                      ("country", "politics", "industry", "territory", "resources", "army", "war"))
    out = [f"== {c.get('name', '?')} ({c.get('tag', '?')}) | {nice_date(block[0]['date'])} =="]
    out.append(f"Leader {c.get('leader', '?')} | {c.get('ideology', '?')} ({c.get('party', '?')}) | "
               f"faction: {c.get('faction') or 'none'}")
    out.append(f"Political power {f1(p.get('pp'))} ({signed(p.get('ppd'))}/day) | stability {pct(p.get('stab'))} | "
               f"war support {pct(p.get('ws'))} | command power {f1(p.get('cp'))} ({signed(p.get('cpd'))}/day)"
               + (f" | election in {f0(p.get('election_days'))} days" if (fnum(p.get('election_days')) or 0) > 0 else ""))
    out.append(f"Factories: civilian {f0(ind.get('civ'))} ({f0(ind.get('civ_free'))} available) | "
               f"military {f0(ind.get('mil'))} ({f0(ind.get('mil_free'))} available) | "
               f"dockyards {f0(ind.get('nav'))} ({f0(ind.get('nav_free'))} available)")
    out.append(f"Research slots {f0(ind.get('research_slots'))} | technologies {f0(ind.get('techs'))} | "
               f"fuel {f0(ind.get('fuel_k'))}k / {f0(ind.get('max_fuel_k'))}k")
    out.append(f"States: owned {f0(ter.get('owned'))}, controlled {f0(ter.get('controlled'))}, "
               f"occupied {f0(ter.get('occupied'))}, cores {f0(ter.get('cores'))} | subjects {f0(ter.get('subjects'))}")
    if res:
        out.append("Resources (net): " + ", ".join(f"{k} {f0(v)}" for k, v in res.items()
                                             if k not in ("kind", "date", "clock")))
    # (max_manpower_k is left out: it reads like total population, not a recruitable cap.)
    out.append(f"Manpower {f1(army.get('mpk'))}k available | deployed {f1(army.get('deployed_k'))}k | "
               f"divisions {f0(army.get('divs'))} ({f0(army.get('armies'))} separate stacks/armies) | "
               f"casualties {f1(army.get('casualties_k'))}k")
    rows = []
    for e in g["equip"]:
        stock, fielded, target = (fnum(e.get(k)) or 0 for k in ("stock", "fielded", "target"))
        if stock or fielded or target:
            short = max(0.0, target - fielded)
            rows.append(f"  {e.get('type', '?'):<22}{stock:>10,.0f}{fielded:>10,.0f}{target:>10,.0f}"
                        f"{(f'{short:>10,.0f}' if short else ''):>10}")
    if rows:
        out.append(f"Equipment{'':<15}{'stock':>8}{'in units':>10}{'wanted':>10}{'short':>10}")
        out.extend(rows)
    if g["enemy"]:
        out.append(f"AT WAR | our surrender progress {pct(war.get('surrender'))} | "
                   f"strength vs enemies {f1(war.get('enemy_strength_ratio'))} | "
                   f"alliance vs enemies {f1(war.get('alliance_strength_ratio'))} | "
                   f"longest war {f0(war.get('longest_war_months', war.get('longest_war_days')))} months")
        for e in g["enemy"]:
            out.append(f"  enemy {e.get('tag')} {e.get('name')}: surrender {pct(e.get('surrender'))}, "
                       f"{f0(e.get('divs'))} divisions, {f0(e.get('mil'))} mil / {f0(e.get('civ'))} civ factories")
    else:
        out.append("At peace.")
    for a in g["ally"]:
        out.append(f"  ally {a.get('tag')} {a.get('name')}: {f0(a.get('divs'))} divisions, "
                   f"{f0(a.get('mil'))} mil factories, surrender {pct(a.get('surrender'))}")
    if g["general"]:
        out.append("Armies:")
        for a in g["general"]:
            out.append(f"  {a.get('name')} (skill {f0(a.get('skill'))}): {f0(a.get('units'))} divisions, "
                       f"{f0(a.get('in_combat'))} in combat, planning {pct(a.get('planning'))}, "
                       f"entrenchment {pct(a.get('entrench'))}, battle plans {f0(a.get('plans'))}")
    if g["front"]:
        names = [f"{s.get('state')} [{s.get('id')}]" for s in g["front"]]
        out.append(f"Front-line states ({len(names)}): " + ", ".join(names))
    if g["major"]:
        out.append("Major powers:")
        for m in g["major"]:
            out.append(f"  {m.get('tag')} {m.get('name')}: {m.get('ideology')}, faction {m.get('faction') or 'none'}, "
                       f"{f0(m.get('divs'))} divs, {f0(m.get('mil'))} mil / {f0(m.get('civ'))} civ"
                       + (f", surrender {pct(m.get('surrender'))}" if fnum(m.get('surrender')) else ""))
    if g["neighbor"]:
        out.append("Neighbors: " + "; ".join(
            f"{n.get('tag')} {n.get('name')} ({n.get('ideology')}, {f0(n.get('divs'))} divs"
            + (f", {n.get('faction')}" if n.get('faction') else "") + ")" for n in g["neighbor"]))
    return "\n".join(out)


NEWS_TEXT = {
    "war_declared": "{a_name} declared war on {b_name}",
    "capitulated": "{a_name} capitulated to {b_name}",
    "annexed": "{a_name} annexed {b_name}",
    "puppeted": "{a_name} became a puppet of {b_name}",
    "peace": "peace deal: {a_name} won against {b_name}",
    "faction_created": "{a_name} created the faction {faction}",
    "joined_faction": "{a_name} joined {faction} (led by {b_name})",
    "government_change": "{a_name} has a new government: {ideology}, led by {leader}",
}


def format_news(recs, limit=40):
    seen, out = set(), []
    peace = {}  # date -> (winners, losers); the game logs one line per winner/loser pair
    for r in recs:
        if r["kind"] != "news":
            continue
        what = r.get("what", "")
        day = nice_date(r["date"])[:10]
        if what == "peace":
            if day not in peace:
                peace[day] = ([], [])
                out.append(("peace", day))
            winners, losers = peace[day]
            if r.get("a_name") not in winners:
                winners.append(r.get("a_name"))
            if r.get("b_name") not in losers:
                losers.append(r.get("b_name"))
            continue
        key = (what, r.get("a"), r.get("b"), day)
        if key in seen:
            continue
        seen.add(key)
        template = NEWS_TEXT.get(what, "{a_name}: " + what)
        out.append(f"  {day}  {template.format_map(defaultdict(str, r))}")
    for i, item in enumerate(out):
        if isinstance(item, tuple):
            winners, losers = peace[item[1]]
            out[i] = f"  {item[1]}  peace deal: {', '.join(winners)} won against {', '.join(losers)}"
    if len(out) > limit:
        out = [f"  ... {len(out) - limit} earlier items not shown"] + out[-limit:]
    return out


def load_cursor():
    try:
        return json.loads((STATE_DIR / "cursor.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cursor(cur):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "cursor.json").write_text(json.dumps(cur))


def log_identity():
    """First line of game.log. It carries the session's start time, so it changes on every game launch."""
    try:
        with open(LOG_PATH, "rb") as f:
            return f.readline(300).decode("utf-8", "replace").strip()
    except FileNotFoundError:
        return ""


def take_news(limit=40, mark_read=True):
    cur = load_cursor()
    ident = log_identity()
    start = cur.get("news_offset", 0)
    if cur.get("log_id") != ident or start > log_size():
        start = 0  # new game session: read the new log from the top
    recs, end = records(start)
    if mark_read:
        save_cursor({"news_offset": end, "log_id": ident})
    return format_news(recs, limit)


# --------------------------------------------------------------------------
# Time control
# --------------------------------------------------------------------------
def clock_box(hwnd):
    """Screen box around the in-game clock ("22:00, 1 Jan, 1936"), anchored to the top-right corner."""
    left, top, width, _ = client_rect(hwnd)
    return (left + width - 380, top + 2, left + width - 170, top + 38)


def pause_stripe_share(hwnd):
    """Share of brown-orange pixels in the lower band of the clock. While paused, HOI4 draws
    hazard stripes behind the clock that pulse between about 0.04 and 0.28 every ~1.6 s; while
    running the band stays black (about 0.04). Calibrated at 1920x1200 with UI scale 1.0."""
    from PIL import ImageGrab
    ensure_front()
    img = ImageGrab.grab(bbox=clock_box(hwnd), all_screens=True).convert("RGB")
    px = img.load()
    w, h = img.size
    hit = total = 0
    for y in range(22, min(36, h)):
        for x in range(w):
            r, g, b = px[x, y]
            total += 1
            if r >= 40 and r > g > b and r - b >= 20:
                hit += 1
    return hit / max(total, 1)


def is_paused(hwnd, window=1.3):
    """Watch the clock for up to `window` seconds (one pulse of the pause stripes).
    Any strong stripe reading means paused; a steady dark band means running."""
    deadline = time.time() + window
    while True:
        if pause_stripe_share(hwnd) > 0.12:
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.07)


def is_running(hwnd, window=1.3):
    return not is_paused(hwnd, window)


def set_speed(n):
    n = max(1, min(5, int(n)))
    press_combo("kp_minus", times=4)
    if n > 1:
        press_combo("kp_plus", times=n - 1)


# Both helpers press Space at most once. If the reading does not change after that press,
# the detector may be blind (tooltip over the clock, other resolution, a menu), so they stop
# and report failure instead of toggling again and maybe leaving the opposite state.
def ensure_paused(hwnd, window=1.3):
    if is_paused(hwnd, window):
        return True
    press_combo("space")
    time.sleep(0.15)
    return is_paused(hwnd, window)


def ensure_running(hwnd, window=1.3):
    if not is_paused(hwnd, window):
        return True
    press_combo("space")
    time.sleep(0.15)
    return not is_paused(hwnd, window)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
def install_mod():
    if not MOD_SRC.exists():
        raise BridgeError(f"Mod source missing: {MOD_SRC}")
    dest = USER_DIR / "mod" / "claude_bridge"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(MOD_SRC, dest)
    descriptor = (MOD_SRC / "descriptor.mod").read_text(encoding="utf-8").rstrip()
    (USER_DIR / "mod" / "claude_bridge.mod").write_text(
        descriptor + f'\npath="{dest.as_posix()}"\n', encoding="utf-8")
    return dest


def cmd_install_mod(args):
    dest = install_mod()
    print(f"Claude Bridge mod installed at {dest}")


def cmd_launch(args):
    if find_window():
        print("HOI4 is already running.")
        return
    install_mod()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads(DLC_LOAD.read_text(encoding="utf-8")) if DLC_LOAD.exists() else {}
    backup = STATE_DIR / f"dlc_load.backup.{datetime.now():%Y%m%d_%H%M%S}.json"
    backup.write_text(json.dumps(data), encoding="utf-8")
    mods = [m for m in data.get("enabled_mods", []) if m != MOD_ENTRY]
    data["enabled_mods"] = ([] if args.only_bridge else mods) + [MOD_ENTRY]
    data.setdefault("disabled_dlcs", [])
    DLC_LOAD.write_text(json.dumps(data), encoding="utf-8")
    print(f"Enabled mods: {', '.join(data['enabled_mods'])}  (previous list saved to {backup.name})")
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(GAME_DIR / "hoi4.exe"), "-gdpr-compliant"], cwd=str(GAME_DIR), creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Started hoi4.exe. Waiting for its window...")
    deadline = time.time() + args.wait
    while time.time() < deadline:
        if find_window():
            print("Game window is up. The main menu may take a little longer to finish loading.")
            return
        time.sleep(1)
    print("No game window yet. It may still be loading; check with: hoi4.py status")


def cmd_restore_mods(args):
    backups = sorted(STATE_DIR.glob("dlc_load.backup.*.json"))
    if not backups:
        raise BridgeError("No dlc_load backup found.")
    shutil.copyfile(backups[0] if args.oldest else backups[-1], DLC_LOAD)
    print(f"Restored {DLC_LOAD} from {(backups[0] if args.oldest else backups[-1]).name}")


def cmd_status(args):
    hwnd = find_window()
    if hwnd:
        left, top, w, h = client_rect(hwnd)
        front = user32.GetForegroundWindow() == hwnd
        print(f"Game: running, window {w}x{h} at ({left},{top}), {'in front' if front else 'in background'}")
    else:
        print("Game: not running")
    installed = (USER_DIR / "mod" / "claude_bridge.mod").exists()
    enabled = DLC_LOAD.exists() and MOD_ENTRY in DLC_LOAD.read_text(encoding="utf-8")
    print(f"Bridge mod: {'installed' if installed else 'NOT installed'}, "
          f"{'enabled' if enabled else 'NOT enabled'} in dlc_load.json")
    recs, _ = records(0)
    print("Last heartbeat: " + heartbeat_line(last_kind(recs, "day")))
    rep = last_report(recs)
    print(f"Last full report: {nice_date(rep[0]['date']) if rep else 'none yet'}")
    if hwnd and args.running:
        focus(hwnd)
        print("Time is " + ("RUNNING" if is_running(hwnd, args.window) else "PAUSED"))


def cmd_look(args):
    hwnd = need_window()
    marks = []
    for m in args.mark or []:
        parts = m.split(",")
        if len(parts) != 2:
            raise BridgeError(f"--mark wants X,Y, got {m!r}")
        marks.append((int(parts[0]), int(parts[1])))
    take_look(hwnd, scale=args.scale, grid=0 if args.no_grid else args.grid,
              region=tuple(args.region) if args.region else None, marks=marks)
    if not args.quiet:
        recs, _ = records(0)
        print("State: " + heartbeat_line(last_kind(recs, "day")))
        news = take_news(limit=40)
        if news:
            print("News since last check:")
            print("\n".join(news))


def cmd_zoom(args):
    if args.x1 <= args.x0 or args.y1 <= args.y0:
        raise BridgeError("zoom wants x0 y0 x1 y1 with x1 > x0 and y1 > y0")
    hwnd = need_window()
    take_look(hwnd, scale=args.scale, grid=args.grid, region=(args.x0, args.y0, args.x1, args.y1), tag="zoom")


def _mods(args):
    return [m for m in (args.mods or "").split("+") if m]


def cmd_click(args):
    hwnd = need_window()
    focus(hwnd)
    click(hwnd, args.x, args.y, button=args.button, double=args.double, mods=_mods(args))
    print(f"{'double-' if args.double else ''}{args.button} click at ({args.x}, {args.y})"
          + (f" with {args.mods}" if args.mods else ""))


def cmd_move(args):
    hwnd = need_window()
    focus(hwnd)
    move_mouse(*to_screen(hwnd, args.x, args.y))
    print(f"mouse at ({args.x}, {args.y})")


def cmd_drag(args):
    hwnd = need_window()
    focus(hwnd)
    drag(hwnd, args.x1, args.y1, args.x2, args.y2, button=args.button, mods=_mods(args))
    print(f"{args.button} drag ({args.x1}, {args.y1}) -> ({args.x2}, {args.y2})")


def cmd_scroll(args):
    hwnd = need_window()
    focus(hwnd)
    scroll(hwnd, args.x, args.y, args.clicks)
    print(f"scrolled {args.clicks} at ({args.x}, {args.y})  (positive = zoom in / up)")


def cmd_key(args):
    hwnd = need_window()
    focus(hwnd)
    for combo in args.combos:
        press_combo(combo, times=args.times)
    print("pressed " + ", ".join(args.combos) + (f" x{args.times}" if args.times > 1 else ""))


def cmd_type(args):
    hwnd = need_window()
    focus(hwnd)
    type_text(args.text)
    print(f"typed {args.text!r}")


def cmd_wait(args):
    time.sleep(args.seconds)


def console_open(hwnd):
    """The console is a dark, flat box at the top-left (x 0-620, y 205-680). When open, a strip
    near its right edge (x 560-590, left of the scrollbar) reads mean ~24 / spread ~6 and the input
    bar is dark too; over the map those read ~85 / ~27. Calibrated at 1920x1200, UI scale 1.0."""
    from PIL import ImageGrab, ImageStat
    ensure_front()
    left, top, _, _ = client_rect(hwnd)
    # Two strips of the console's dark body: either being flat and dark counts (its text and scrollbar can make
    # one of them busy), and the input bar must be dark too.
    def stat(x0, y0, x1, y1):
        return ImageStat.Stat(ImageGrab.grab(bbox=(left + x0, top + y0, left + x1, top + y1),
                                             all_screens=True).convert("L"))
    strips = [stat(560, 215, 590, 330), stat(560, 240, 590, 620)]
    bar = stat(10, 640, 610, 675)
    return any(s.mean[0] < 45 and s.stddev[0] < 14 for s in strips) and bar.mean[0] < 50


def wait_console(hwnd, want_open, timeout=1.5):
    """Poll until the console is open/closed. It animates, so one reading right after
    the key press can still show the old state."""
    deadline = time.time() + timeout
    while True:
        if console_open(hwnd) == want_open:
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.1)


def clear_console_line(count=40):
    """Backspace away anything left in the console's input line."""
    ensure_front()
    scan, _ = key_scan("backspace")
    for _ in range(count):
        _send(_key_input(scan), _key_input(scan, up=True))
        time.sleep(0.01)


def close_console(hwnd):
    if console_open(hwnd):
        press_combo("console")  # one press only: a second press would reopen it
        if not wait_console(hwnd, False):
            print("warning: the console still looks open; check with look")
            return False
    return True


def run_console(hwnd, command):
    focus(hwnd)
    # A full-screen view fading out (the focus tree just closed) is dark and flat like the console for a moment,
    # and typing then lands as hotkeys. Trust "already open" only if it still reads open after the screen settles.
    if console_open(hwnd):
        time.sleep(0.8)
    if not console_open(hwnd):
        press_combo("console")
        if not wait_console(hwnd, True):
            raise BridgeError("The console did not open, so nothing was typed. (Ironman games have no "
                              "console; the console key is the one left of 1.)")
    try:
        clear_console_line()
        type_text(command)
        time.sleep(0.1)
        press_combo("enter")
        time.sleep(0.3)
    finally:
        close_console(hwnd)


def cmd_console(args):
    hwnd = need_window()
    run_console(hwnd, args.command)
    print(f"console: {args.command}")


def cmd_report(args):
    hwnd = need_window()
    start = log_size()
    # "effect <tag> <scripted effect>" runs the report directly. (Firing the hidden event
    # claude_bridge.1 from the console also works but opens a debug popup.)
    # Without a tag the console runs the effect for the player's country.
    # Without a tag the console's scope is whatever is selected (a general, a state), so always name the country:
    # the player's tag from the latest heartbeat.
    tag = args.tag
    if not tag:
        recs, _ = records(max(0, log_size() - 2_000_000))
        hb = last_kind(recs, "day")
        tag = hb.get("tag") if hb else None
    run_console(hwnd, f"effect {tag} claude_bridge_report" if tag else "effect claude_bridge_report")
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        recs, _ = records(start)
        block = last_report(recs)
        if block:
            print(format_report(block))
            return
        time.sleep(0.2)
    raise BridgeError("No report came back. Check that the Claude Bridge mod is enabled and a country is selected. "
                      "(The console key is the one left of 1; see shots for what happened.)")


def cmd_state(args):
    recs, _ = records(0)
    block = last_report(recs)
    print("Latest heartbeat: " + heartbeat_line(last_kind(recs, "day")))
    print(format_report(block) if block else "No full report yet. Use 'report', or let a week pass.")


def cmd_news(args):
    news = take_news(limit=args.limit, mark_read=not args.peek)
    print("\n".join(news) if news else "No news since last check.")


def cmd_pause(args):
    hwnd = need_window()
    focus(hwnd)
    print("paused" if ensure_paused(hwnd, args.window) else "could not confirm pause")


def cmd_resume(args):
    hwnd = need_window()
    focus(hwnd)
    print("running" if ensure_running(hwnd, args.window)
          else "time did not start moving (a menu or popup may be open: use look)")


def cmd_speed(args):
    hwnd = need_window()
    focus(hwnd)
    set_speed(args.n)
    print(f"speed set to {args.n}")


def cmd_advance(args):
    """Let N in-game days pass, then pause and summarize."""
    hwnd = need_window()
    focus(hwnd)
    recs, _ = records(0)
    before = last_kind(recs, "day")
    set_speed(args.speed)
    off = log_size()
    try:  # a leftover popup, notice or the Esc menu would stop time at once
        import hoi4_actions
        hoi4_actions.dismiss_notices(hwnd)
    except Exception as exc:  # never let the helper block time control
        print(f"(popup check skipped: {exc})")
    if not ensure_running(hwnd, args.window):
        raise BridgeError("Time will not start. A menu or popup may be open: use 'look'.")
    seen, last_change, stopped, timed_out = 0, time.time(), False, False
    started = time.time()
    while seen < args.days:
        new, off = records(off)
        days = sum(r["kind"] == "day" for r in new)
        if days:
            seen += days
            last_change = time.time()
        elif time.time() - last_change > args.stall:
            # No new day for a while: check the clock before deciding time has stopped.
            if not is_running(hwnd, args.window):
                stopped = True
                break
            last_change = time.time()
        if time.time() - started > args.timeout:
            timed_out = True
            break
        time.sleep(0.1)
    if stopped:
        paused = True
    else:
        press_combo("space")  # time is known to be running: pause at once, then confirm
        time.sleep(0.15)
        paused = ensure_paused(hwnd, args.window)
    recs, _ = records(0)
    after = last_kind(recs, "day")
    passed = days_between(before, after) if before and after else seen
    if not isinstance(passed, int) or passed < 0:  # e.g. an earlier save was loaded: the log holds a later date
        passed = seen
    print(f"Advanced {passed} day(s) in {time.time() - started:.0f}s"
          + (" | time STOPPED on its own (popup or event?), use 'look'" if stopped else "")
          + (" | hit the --timeout" if timed_out else "")
          + ("" if paused else " | WARNING: could not confirm pause"))
    print("Now:    " + heartbeat_line(after))
    if before and after:
        diff = []
        for key, label in (("pp", "PP"), ("mpk", "manpower k"), ("divs", "divisions")):
            a, b = fnum(before.get(key)), fnum(after.get(key))
            if a is not None and b is not None and abs(b - a) > 1e-6:
                diff.append(f"{label} {b - a:+,.1f}")
        if diff:
            print("Change: " + ", ".join(diff))
    news = take_news(limit=20)
    if news:
        print("News:")
        print("\n".join(news))


def cmd_tail(args):
    lines, _ = read_log(max(0, log_size() - 400_000))
    if args.grep:
        lines = [l for l in lines if re.search(args.grep, l, re.I)]
    print("\n".join(lines[-args.n:]))


def cmd_do(args):
    """Run several commands separated by ';' in one call."""
    for part in split_batch(args.script):
        try:
            argv = shlex.split(part, posix=True)
        except ValueError as exc:
            raise BridgeError(f"could not parse {part.strip()!r}: {exc}")
        if not argv:
            continue
        print(f"> {part.strip()}")
        run(argv)


def split_batch(script):
    parts, buf, quote = [], [], None
    for ch in script:
        if quote:
            if ch == quote:
                quote = None
            buf.append(ch)
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ";":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p for p in parts if p.strip()]


def build_parser():
    p = argparse.ArgumentParser(prog="hoi4.py", description="Let Claude watch and play Hearts of Iron IV.")
    p.add_argument("--version", action="version", version=f"hoi4-claude {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("launch", help="install the bridge mod, enable it, and start the game")
    s.add_argument("--only-bridge", action="store_true", help="disable your other mods for this launch")
    s.add_argument("--wait", type=float, default=90, help="seconds to wait for the window")
    s.set_defaults(fn=cmd_launch)
    s = sub.add_parser("install-mod", help="copy the bridge mod into the HOI4 mod folder")
    s.set_defaults(fn=cmd_install_mod)
    s = sub.add_parser("restore-mods", help="put back the mod list from before 'launch'")
    s.add_argument("--oldest", action="store_true", help="restore the very first backup instead of the latest")
    s.set_defaults(fn=cmd_restore_mods)
    s = sub.add_parser("status", help="is the game running, is the mod loaded, latest state")
    s.add_argument("--running", action="store_true", help="also check whether time is moving")
    s.add_argument("--window", type=float, default=1.3)
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("look", help="screenshot the game (with grid), plus state and news")
    s.add_argument("--scale", type=float, default=0.6)
    s.add_argument("--grid", type=int, default=100)
    s.add_argument("--no-grid", action="store_true")
    s.add_argument("--region", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    s.add_argument("--mark", action="append", metavar="X,Y", help="draw a crosshair (repeatable)")
    s.add_argument("--quiet", action="store_true", help="screenshot only")
    s.set_defaults(fn=cmd_look)
    s = sub.add_parser("zoom", help="screenshot one region at higher scale")
    for name in ("x0", "y0", "x1", "y1"):
        s.add_argument(name, type=int)
    s.add_argument("--scale", type=float, default=1.0)
    s.add_argument("--grid", type=int, default=50)
    s.set_defaults(fn=cmd_zoom)

    s = sub.add_parser("click", help="click at window coordinates")
    s.add_argument("x", type=int)
    s.add_argument("y", type=int)
    s.add_argument("--button", choices=list(MOUSE_BUTTONS), default="left")
    s.add_argument("--right", dest="button", action="store_const", const="right")
    s.add_argument("--double", action="store_true")
    s.add_argument("--mods", help="modifier keys held during the click, e.g. shift or ctrl+shift")
    s.set_defaults(fn=cmd_click)
    s = sub.add_parser("move", help="move the mouse (for tooltips)")
    s.add_argument("x", type=int)
    s.add_argument("y", type=int)
    s.set_defaults(fn=cmd_move)
    s = sub.add_parser("drag", help="drag from one point to another")
    for name in ("x1", "y1", "x2", "y2"):
        s.add_argument(name, type=int)
    s.add_argument("--button", choices=list(MOUSE_BUTTONS), default="left")
    s.add_argument("--right", dest="button", action="store_const", const="right")
    s.add_argument("--mods")
    s.set_defaults(fn=cmd_drag)
    s = sub.add_parser("scroll", help="mouse wheel at a point (positive = up / zoom in)")
    s.add_argument("x", type=int)
    s.add_argument("y", type=int)
    s.add_argument("clicks", type=int)
    s.set_defaults(fn=cmd_scroll)
    s = sub.add_parser("key", help="press keys or combos, e.g. y, esc, alt+q, kp_plus")
    s.add_argument("combos", nargs="+")
    s.add_argument("--times", type=int, default=1)
    s.set_defaults(fn=cmd_key)
    s = sub.add_parser("type", help="type text")
    s.add_argument("text")
    s.set_defaults(fn=cmd_type)
    s = sub.add_parser("wait", help="sleep for some seconds (useful inside 'do')")
    s.add_argument("seconds", type=float)
    s.set_defaults(fn=cmd_wait)
    s = sub.add_parser("console", help="run a console command")
    s.add_argument("command")
    s.set_defaults(fn=cmd_console)

    s = sub.add_parser("report", help="ask the game for a full state report now (uses the console)")
    s.add_argument("--timeout", type=float, default=6)
    s.add_argument("--tag", help="report on this country tag instead of the player, e.g. POL")
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("state", help="print the latest report already in game.log (does not touch the game)")
    s.set_defaults(fn=cmd_state)
    s = sub.add_parser("news", help="world news since the last check")
    s.add_argument("--limit", type=int, default=40)
    s.add_argument("--peek", action="store_true", help="do not mark as read")
    s.set_defaults(fn=cmd_news)
    s = sub.add_parser("tail", help="raw game.log lines (debugging)")
    s.add_argument("n", type=int, nargs="?", default=30)
    s.add_argument("--grep")
    s.set_defaults(fn=cmd_tail)

    s = sub.add_parser("pause", help="make sure time is paused")
    s.add_argument("--window", type=float, default=1.3, help="seconds to watch the clock")
    s.set_defaults(fn=cmd_pause)
    s = sub.add_parser("resume", help="make sure time is running")
    s.add_argument("--window", type=float, default=1.3, help="seconds to watch the clock")
    s.set_defaults(fn=cmd_resume)
    s = sub.add_parser("speed", help="set game speed 1-5")
    s.add_argument("n", type=int)
    s.set_defaults(fn=cmd_speed)
    s = sub.add_parser("advance", help="let N days pass, then pause and summarize")
    s.add_argument("days", type=int)
    s.add_argument("--speed", type=int, default=5)
    s.add_argument("--window", type=float, default=1.3, help="seconds to watch the clock when checking for pause")
    s.add_argument("--stall", type=float, default=5, help="check the clock if no day passes for this long")
    s.add_argument("--timeout", type=float, default=300)
    s.set_defaults(fn=cmd_advance)

    s = sub.add_parser("do", help='run several commands: do "key y ; wait 0.5 ; look"')
    s.add_argument("script")
    s.set_defaults(fn=cmd_do)

    # EX1: checked actions and text readers live in hoi4_actions.py.
    s = sub.add_parser("act", help="checked actions, no screenshots: research, production, open, close, "
                                   "calibrate-research (see hoi4_actions.py)")
    s.add_argument("rest", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_act)
    s = sub.add_parser("read", help="read the screen as text: research, production, date, techs")
    s.add_argument("rest", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_read)
    return p


def _actions(argv):
    import hoi4_actions
    try:
        hoi4_actions.main(argv)
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise BridgeError(f"bad action: {' '.join(argv)}")


def cmd_act(args):
    _actions(args.rest)


def cmd_read(args):
    _actions(["read"] + args.rest)


def run(argv):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise BridgeError(f"bad command: {' '.join(argv)}")
        return
    try:
        args.fn(args)
    except (ValueError, re.error) as exc:
        raise BridgeError(f"{args.cmd}: {exc}")


def main():
    try:
        run(sys.argv[1:])
    except BridgeError as exc:
        print(f"error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
