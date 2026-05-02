"""
Farmvates - Drone Mission Planner
A tkinter app with TkinterMapView for planning drone survey missions.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import math
import threading
import urllib.request
import urllib.parse
import json
import os
import sys

try:
    import tkintermapview
    MAP_AVAILABLE = True
except ImportError:
    MAP_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# App State  (instantiated AFTER Tk root exists)
# ─────────────────────────────────────────────────────────────────────────────
class AppState:
    def __init__(self):
        self.ground_station_address = tk.StringVar()
        self.ground_station_lat     = None
        self.ground_station_lon     = None
        self.drone_path_points      = []
        self.geofence_points        = []
        self.loop_count             = tk.IntVar(value=1)
        self.adv_speed              = tk.DoubleVar(value=10.0)
        self.adv_min_altitude       = tk.DoubleVar(value=30.0)
        self.adv_start_landing_at   = tk.DoubleVar(value=25.0)
        self.adv_emerg_land_at      = tk.DoubleVar(value=5.0)
        self.adv_loop_until_low_batt = tk.BooleanVar(value=False)
        self.adv_log_battery        = tk.BooleanVar(value=True)
        self.adv_log_hours          = tk.BooleanVar(value=False)
        self.adv_alert_battery      = tk.BooleanVar(value=True)
        self.est_distance_m         = 0.0
        self.est_time_min           = 0.0
        self.est_battery_loops      = 0

# ─────────────────────────────────────────────────────────────────────────────
# Colours — Agricultural / earthy greens & browns
# ─────────────────────────────────────────────────────────────────────────────
BG      = "#1C1A0F"
CARD    = "#2A2415"
ACCENT  = "#6B8F3E"
ACCENT2 = "#A8C060"
TEXT    = "#EDE8D5"
MUTED   = "#8A8060"
DANGER  = "#B5451B"
WARN    = "#C48A2A"
BORDER  = "#3D3318"

TILE_STREET    = "https://mt0.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}&s=Ga"
TILE_SATELLITE = "https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}&s=Ga"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def style_btn(btn, primary=True, warn=False):
    if warn:
        bg, fg = WARN, BG
    elif primary:
        bg, fg = ACCENT, BG
    else:
        bg, fg = CARD, TEXT
    btn.configure(bg=bg, fg=fg, activebackground=ACCENT2, activeforeground=BG,
                  relief="flat", bd=0, padx=20, pady=8,
                  font=("Courier", 11, "bold"), cursor="hand2")

def make_tile_toggle(parent, map_widget):
    _state = {"satellite": False}
    def toggle():
        _state["satellite"] = not _state["satellite"]
        if _state["satellite"]:
            map_widget.set_tile_server(TILE_SATELLITE, max_zoom=22)
            btn.config(text="🗺  Street View")
        else:
            map_widget.set_tile_server(TILE_STREET, max_zoom=22)
            btn.config(text="🛰  Satellite")
    btn = tk.Button(parent, text="🛰  Satellite", command=toggle)
    style_btn(btn, primary=False)
    return btn

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def compute_stats(STATE):
    pts = STATE.drone_path_points
    if len(pts) < 2:
        STATE.est_distance_m    = 0
        STATE.est_time_min      = 0
        STATE.est_battery_loops = 0
        return
    dist = sum(haversine(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
               for i in range(len(pts)-1))
    dist += haversine(pts[-1][0], pts[-1][1], pts[0][0], pts[0][1])
    STATE.est_distance_m    = dist * STATE.loop_count.get()
    spd = STATE.adv_speed.get() or 10
    STATE.est_time_min      = (STATE.est_distance_m / spd) / 60
    STATE.est_battery_loops = max(1, int(STATE.est_distance_m / 5000) + 1)

def add_header(parent, title, subtitle=""):
    hdr = tk.Frame(parent, bg=BG, pady=14)
    hdr.pack(fill="x", side="top")
    tk.Label(hdr, text="✦ FARMVATES", bg=BG, fg=ACCENT,
             font=("Courier", 9, "bold")).pack()
    tk.Label(hdr, text=title, bg=BG, fg=TEXT,
             font=("Courier", 20, "bold")).pack()
    if subtitle:
        tk.Label(hdr, text=subtitle, bg=BG, fg=MUTED,
                 font=("Courier", 10)).pack()
    tk.Frame(parent, bg=BORDER, height=1).pack(fill="x")

# ─────────────────────────────────────────────────────────────────────────────
# Geofence dropdown menu
# ─────────────────────────────────────────────────────────────────────────────
# MODE constants
MODE_WAYPOINT  = "waypoint"
MODE_GEOFENCE  = "geofence"

class DrawingMenu:
    """
    Unified dropdown that switches between Waypoint and Geofence drawing modes
    and provides undo/clear actions for each layer.
    """
    def __init__(self, parent, map_widget, STATE, on_mode_change=None):
        self.map_widget      = map_widget
        self.STATE           = STATE
        self._on_mode_change = on_mode_change
        self.mode            = MODE_WAYPOINT   # current drawing mode
        self._gf_markers     = []
        self._gf_polygon     = None

        self._btn = tk.Button(parent, text="✏  Draw: Waypoints ▾",
                              command=self._popup)
        style_btn(self._btn, primary=True)
        self._btn.pack(side="left", padx=(8, 0))

        self._menu = tk.Menu(parent, tearoff=0,
                             bg=CARD, fg=TEXT, activebackground=ACCENT,
                             activeforeground=BG, font=("Courier", 10),
                             relief="flat", bd=0)

        # Mode selection only
        self._menu.add_command(label="🛤  Waypoints",
                               command=lambda: self._set_mode(MODE_WAYPOINT))
        self._menu.add_command(label="⬡  Geofence",
                               command=lambda: self._set_mode(MODE_GEOFENCE))

    # ── public ────────────────────────────────────────────────────────────────
    def on_map_click(self, coords):
        """Call from Step2Page._on_map_click; routes to the active layer."""
        if self.mode == MODE_GEOFENCE:
            self._add_geofence_point(coords)
        else:
            return False   # let Step2Page handle waypoint placement
        return True

    def add_geofence_point_external(self, coords):
        self._add_geofence_point(coords)

    def clear_geofence(self):
        self.STATE.geofence_points.clear()
        for m in self._gf_markers:
            m.delete()
        self._gf_markers.clear()
        if self._gf_polygon:
            self._gf_polygon.delete()
            self._gf_polygon = None

    # ── private ───────────────────────────────────────────────────────────────
    def _popup(self):
        try:
            x = self._btn.winfo_rootx()
            y = self._btn.winfo_rooty() + self._btn.winfo_height()
            self._menu.tk_popup(x, y)
        finally:
            self._menu.grab_release()

    def _set_mode(self, mode):
        self.mode = mode
        if mode == MODE_WAYPOINT:
            self._btn.config(text="✏  Draw: Waypoints ▾")
            style_btn(self._btn, primary=True)
        else:
            self._btn.config(text="✏  Draw: Geofence ▾")
            style_btn(self._btn, warn=True)
        if self._on_mode_change:
            self._on_mode_change(mode)

    def _undo(self):
        if self.mode == MODE_GEOFENCE:
            if self.STATE.geofence_points:
                self.STATE.geofence_points.pop()
            if self._gf_markers:
                self._gf_markers[-1].delete()
                self._gf_markers.pop()
            self._redraw_polygon()
        else:
            if self._on_mode_change:
                self._on_mode_change("undo_waypoint")

    def _clear(self):
        if self.mode == MODE_GEOFENCE:
            self.clear_geofence()
        else:
            if self._on_mode_change:
                self._on_mode_change("clear_waypoints")

    def _add_geofence_point(self, coords):
        lat, lon = coords
        self.STATE.geofence_points.append((lat, lon))
        m = self.map_widget.set_marker(lat, lon,
                                        text=f"GF{len(self.STATE.geofence_points)}",
                                        marker_color_circle=WARN,
                                        marker_color_outside=WARN)
        self._gf_markers.append(m)
        self._redraw_polygon()

    def _redraw_polygon(self):
        if self._gf_polygon:
            self._gf_polygon.delete()
            self._gf_polygon = None
        pts = self.STATE.geofence_points
        if len(pts) >= 3:
            self._gf_polygon = self.map_widget.set_path(
                pts + [pts[0]], color=WARN, width=2)
        elif len(pts) == 2:
            self._gf_polygon = self.map_widget.set_path(pts, color=WARN, width=2)

# ─────────────────────────────────────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────────────────────────────────────
class SplashPage(tk.Frame):
    def __init__(self, parent, controller, STATE):
        super().__init__(parent, bg=BG)

        body = tk.Frame(self, bg=BG)
        body.pack(expand=True)

        tk.Label(body, text="✦", bg=BG, fg=ACCENT,
                 font=("Courier", 48)).pack(pady=(0, 4))
        tk.Label(body, text="FARMVATES", bg=BG, fg=TEXT,
                 font=("Courier", 42, "bold")).pack()
        tk.Label(body, text="Autonomous Drone Mission Planner", bg=BG, fg=MUTED,
                 font=("Courier", 12)).pack(pady=(8, 48))

        btn = tk.Button(body, text="GET STARTED  →",
                        command=lambda: controller.show(HowItWorksPage))
        style_btn(btn)
        btn.pack(ipadx=20, ipady=6)


class HowItWorksPage(tk.Frame):
    def __init__(self, parent, controller, STATE):
        super().__init__(parent, bg=BG)
        add_header(self, "How It Works")
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=50, pady=20)

        canvas = tk.Canvas(outer, bg=CARD, bd=0, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=CARD, padx=24, pady=20)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        steps = [
            ("🛰  Step 1 — Ground Station",
             "Enter your ground station address. The map will centre on this "
             "location and pre-load the surrounding area for your mission. "
             "Toggle between Street and Satellite view at any time."),
            ("🗺  Step 2 — Draw Drone Path",
             "Click on the map to place waypoints. Use the Geofence menu to "
             "draw a restricted boundary zone shown in amber. Farmvates "
             "computes flight path, loop count, estimated time, and battery usage."),
            ("⚙  Step 3 — Advanced Options",
             "Fine-tune speed, altitude, landing thresholds, and "
             "logging preferences (battery events, flight hours, etc.)."),
            ("🚀  Step 4 — Finalize",
             "Review the mission summary, confirm take-off, and the app will "
             "log every loop automatically in real time."),
        ]
        for title, body in steps:
            tk.Label(inner, text=title, bg=CARD, fg=ACCENT,
                     font=("Courier", 12, "bold"), anchor="w").pack(fill="x", pady=(14, 2))
            tk.Label(inner, text=body, bg=CARD, fg=TEXT,
                     font=("Courier", 10), wraplength=560, justify="left",
                     anchor="w").pack(fill="x", padx=12)

        btn = tk.Button(self, text="NEXT  →",
                        command=lambda: controller.show(Step1Page))
        style_btn(btn)
        btn.pack(pady=18)


class Step1Page(tk.Frame):
    def __init__(self, parent, controller, STATE):
        super().__init__(parent, bg=BG)
        self.controller = controller
        self.STATE = STATE
        self._marker = None

        add_header(self, "Step 1", "Select Approximate Ground Station Location")

        top = tk.Frame(self, bg=BG, pady=10)
        top.pack(fill="x", padx=20)
        tk.Label(top, text="Address:", bg=BG, fg=MUTED,
                 font=("Courier", 10)).pack(side="left", padx=(0, 8))
        entry = tk.Entry(top, textvariable=STATE.ground_station_address,
                         bg=CARD, fg=TEXT, insertbackground=TEXT,
                         font=("Courier", 11), relief="flat", bd=6)
        entry.pack(side="left", fill="x", expand=True, ipady=4)
        search_btn = tk.Button(top, text="🔍 Search", command=self._search)
        style_btn(search_btn, primary=False)
        search_btn.pack(side="left", padx=(8, 0))

        map_frame = tk.Frame(self, bg=BG)
        map_frame.pack(fill="both", expand=True, padx=20, pady=(0, 4))

        if MAP_AVAILABLE:
            self.map_widget = tkintermapview.TkinterMapView(map_frame, corner_radius=8)
            self.map_widget.pack(fill="both", expand=True)
            self.map_widget.set_tile_server(TILE_STREET, max_zoom=22)
            self.map_widget.set_position(39.5, -98.35)
            self.map_widget.set_zoom(4)
            self.map_widget.add_left_click_map_command(self._map_click)
            # Remove built-in canvas zoom buttons — they trigger spurious map clicks
            self.map_widget.canvas.delete("button")
            tile_btn = make_tile_toggle(top, self.map_widget)
            tile_btn.pack(side="left", padx=(8, 0))
            zoom_in_btn = tk.Button(top, text="＋",
                                    command=lambda: self.map_widget.set_zoom(int(self.map_widget.zoom) + 1),
                                    bg=CARD, fg=TEXT, font=("Courier", 11, "bold"),
                                    relief="flat", bd=0, padx=10, cursor="hand2")
            zoom_in_btn.pack(side="left", padx=(8, 0))
            zoom_out_btn = tk.Button(top, text="－",
                                     command=lambda: self.map_widget.set_zoom(int(self.map_widget.zoom) - 1),
                                     bg=CARD, fg=TEXT, font=("Courier", 11, "bold"),
                                     relief="flat", bd=0, padx=10, cursor="hand2")
            zoom_out_btn.pack(side="left", padx=(2, 0))
        else:
            tk.Label(map_frame,
                     text="⚠  tkintermapview not installed.\nRun: pip install tkintermapview",
                     bg=CARD, fg=DANGER, font=("Courier", 12),
                     pady=60).pack(fill="both", expand=True)
            self.map_widget = None

        self._status = tk.Label(self, text="Click the map or search an address.",
                                bg=BG, fg=MUTED, font=("Courier", 9))
        self._status.pack()

        btn = tk.Button(self, text="NEXT  →", command=self._next)
        style_btn(btn)
        btn.pack(pady=12)

    def on_show(self):
        if not self.map_widget:
            return
        if self.STATE.ground_station_lat is not None:
            lat = self.STATE.ground_station_lat
            lon = self.STATE.ground_station_lon
            # Restore marker for existing ground station
            if self._marker:
                self._marker.delete()
            self._marker = self.map_widget.set_marker(lat, lon, text="Ground Station")
            self.map_widget.set_position(lat, lon)
            self.map_widget.set_zoom(10)
            self._status.config(
                text=f"📍  {lat:.5f}, {lon:.5f} — press NEXT to continue or click to change",
                fg=ACCENT2)
        else:
            self.map_widget.set_position(39.5, -98.35)
            self.map_widget.set_zoom(4)
            self._status.config(text="Click the map or search an address.", fg=MUTED)

    def _search(self):
        addr = self.STATE.ground_station_address.get().strip()
        if not addr or not self.map_widget:
            return
        self._status.config(text="Searching…", fg=MUTED)
        # Run geocoding in a background thread so the UI stays responsive
        threading.Thread(target=self._geocode, args=(addr,), daemon=True).start()

    def _geocode(self, addr):
        try:
            params = urllib.parse.urlencode({
                "q": addr, "format": "jsonv2",
                "addressdetails": "1", "limit": "1"
            })
            url = f"https://nominatim.openstreetmap.org/search?{params}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Farmvates/1.0 (drone mission planner)"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                results = json.loads(resp.read().decode())
            if results:
                lat = float(results[0]["lat"])
                lon = float(results[0]["lon"])
                self.after(0, self._on_geocode_result, lat, lon)
            else:
                self.after(0, self._status.config,
                           {"text": "Address not found.", "fg": DANGER})
        except Exception as e:
            self.after(0, self._status.config,
                       {"text": f"Search error: {e}", "fg": DANGER})

    def _on_geocode_result(self, lat, lon):
        self.STATE.ground_station_lat = lat
        self.STATE.ground_station_lon = lon
        if self._marker:
            self._marker.delete()
        self._marker = self.map_widget.set_marker(lat, lon, text="Ground Station")
        self.map_widget.set_position(lat, lon)
        self.map_widget.set_zoom(10)
        self._status.config(text=f"📍  {lat:.5f}, {lon:.5f}", fg=ACCENT2)

    def _map_click(self, coords):
        # Guard: ignore if pointer is not actually over the map canvas
        mx = self.map_widget.winfo_rootx()
        my = self.map_widget.winfo_rooty()
        mw = self.map_widget.winfo_width()
        mh = self.map_widget.winfo_height()
        px = self.map_widget.winfo_pointerx()
        py = self.map_widget.winfo_pointery()
        if not (mx <= px <= mx + mw and my <= py <= my + mh):
            return
        lat, lon = coords
        self.STATE.ground_station_lat = lat
        self.STATE.ground_station_lon = lon
        if self._marker:
            self._marker.delete()
        self._marker = self.map_widget.set_marker(lat, lon, text="Ground Station")
        self._status.config(text=f"📍  {lat:.5f}, {lon:.5f}", fg=ACCENT2)

    def _next(self):
        if self.STATE.ground_station_lat is None and MAP_AVAILABLE:
            messagebox.showwarning("No Location", "Please select a ground station location.")
            return
        if not MAP_AVAILABLE:
            self.STATE.ground_station_lat = 37.7749
            self.STATE.ground_station_lon = -122.4194
        self.controller.show(Step2Page)


class Step2Page(tk.Frame):
    def __init__(self, parent, controller, STATE):
        super().__init__(parent, bg=BG)
        self.controller    = controller
        self.STATE         = STATE
        self._path_markers   = []
        self._path_line      = None
        self._drawing_menu   = None
        self._map_click_enabled = True

        add_header(self, "Step 2", "Mark Out Drone Path & Geofence")

        ctrl = tk.Frame(self, bg=BG, pady=6)
        ctrl.pack(fill="x", padx=20)

        self._loops_label = tk.Label(ctrl, text="Loops before recharging:", bg=BG, fg=MUTED,
                 font=("Courier", 10))
        self._loops_label.pack(side="left")
        # Custom +/- counter — avoids tkintermapview click bleed from native Spinbox buttons
        counter_frame = tk.Frame(ctrl, bg=CARD)
        counter_frame.pack(side="left", padx=(4, 8))

        def _dec():
            v = STATE.loop_count.get()
            if v > 1:
                STATE.loop_count.set(v - 1)
            self._refresh_stats()

        def _inc():
            v = STATE.loop_count.get()
            if v < 99:
                STATE.loop_count.set(v + 1)
            self._refresh_stats()

        dec_btn = tk.Button(counter_frame, text="−", command=_dec,
                            bg=BORDER, fg=TEXT, font=("Courier", 10, "bold"),
                            relief="flat", bd=0, width=2, cursor="hand2")
        dec_btn.pack(side="left")

        self._loop_count_lbl = tk.Label(counter_frame, textvariable=STATE.loop_count,
                                         bg=CARD, fg=TEXT, font=("Courier", 11),
                                         width=3, anchor="center")
        self._loop_count_lbl.pack(side="left")

        self._inc_btn = tk.Button(counter_frame, text="+", command=_inc,
                            bg=BORDER, fg=TEXT, font=("Courier", 10, "bold"),
                            relief="flat", bd=0, width=2, cursor="hand2")
        self._inc_btn.pack(side="left")
        self._dec_btn = dec_btn
        self._counter_frame = counter_frame

        def _toggle_loop_mode():
            if STATE.adv_loop_until_low_batt.get():
                self._loop_count_lbl.config(fg=MUTED)
                self._dec_btn.config(state="disabled", bg=BORDER, fg=BORDER)
                self._inc_btn.config(state="disabled", bg=BORDER, fg=BORDER)
                self._loops_label.config(fg=BORDER)
            else:
                self._loop_count_lbl.config(fg=TEXT)
                self._dec_btn.config(state="normal", bg=BORDER, fg=TEXT)
                self._inc_btn.config(state="normal", bg=BORDER, fg=TEXT)
                self._loops_label.config(fg=MUTED)
            self._refresh_stats()

        tk.Checkbutton(ctrl, text="Until low battery", variable=STATE.adv_loop_until_low_batt,
                       bg=BG, fg=TEXT, selectcolor=ACCENT,
                       activebackground=BG, activeforeground=ACCENT,
                       font=("Courier", 10), cursor="hand2",
                       command=_toggle_loop_mode).pack(side="left", padx=(0, 12))

        map_frame = tk.Frame(self, bg=BG)
        map_frame.pack(fill="both", expand=True, padx=20, pady=(0, 4))

        if MAP_AVAILABLE:
            self.map_widget = tkintermapview.TkinterMapView(map_frame, corner_radius=8)
            self.map_widget.pack(fill="both", expand=True)
            self.map_widget.set_tile_server(TILE_STREET, max_zoom=22)
            self.map_widget.add_left_click_map_command(self._on_map_click)
            # Remove built-in canvas zoom buttons — they trigger spurious map clicks
            self.map_widget.canvas.delete("button")
            tile_btn = make_tile_toggle(ctrl, self.map_widget)
            tile_btn.pack(side="left", padx=(12, 0))
            zoom_in_btn = tk.Button(ctrl, text="＋",
                                    command=lambda: self.map_widget.set_zoom(int(self.map_widget.zoom) + 1),
                                    bg=CARD, fg=TEXT, font=("Courier", 11, "bold"),
                                    relief="flat", bd=0, padx=10, cursor="hand2")
            zoom_in_btn.pack(side="left", padx=(4, 0))
            zoom_out_btn = tk.Button(ctrl, text="－",
                                     command=lambda: self.map_widget.set_zoom(int(self.map_widget.zoom) - 1),
                                     bg=CARD, fg=TEXT, font=("Courier", 11, "bold"),
                                     relief="flat", bd=0, padx=10, cursor="hand2")
            zoom_out_btn.pack(side="left", padx=(2, 0))
            self._drawing_menu = DrawingMenu(ctrl, self.map_widget, STATE,
                                             on_mode_change=self._on_mode_change)
            undo_btn = tk.Button(ctrl, text="↩ Undo", command=self._undo_active)
            style_btn(undo_btn, primary=False)
            undo_btn.pack(side="left", padx=(8, 0))
        else:
            tk.Label(map_frame,
                     text="⚠  tkintermapview not installed.\nRun: pip install tkintermapview",
                     bg=CARD, fg=DANGER, font=("Courier", 12),
                     pady=60).pack(fill="both", expand=True)
            self.map_widget = None

        legend = tk.Frame(self, bg=BG)
        legend.pack(fill="x", padx=24, pady=(0, 2))
        tk.Label(legend, text="●", bg=BG, fg=ACCENT, font=("Courier", 10)).pack(side="left")
        tk.Label(legend, text=" Flight path    ", bg=BG, fg=MUTED, font=("Courier", 9)).pack(side="left")
        tk.Label(legend, text="●", bg=BG, fg=WARN, font=("Courier", 10)).pack(side="left")
        tk.Label(legend, text=" Geofence boundary", bg=BG, fg=MUTED, font=("Courier", 9)).pack(side="left")

        stats_frame = tk.Frame(self, bg=CARD, pady=8)
        stats_frame.pack(fill="x", padx=20, pady=(0, 4))
        self._stat_dist = self._stat_lbl(stats_frame, "Distance",      "0 m")
        self._stat_time = self._stat_lbl(stats_frame, "Est. Time",     "0 min")
        self._stat_batt = self._stat_lbl(stats_frame, "Battery Swaps", "0")
        self._stat_pts  = self._stat_lbl(stats_frame, "Waypoints",     "0")
        self._stat_gf   = self._stat_lbl(stats_frame, "Geofence Pts",  "0")

        btn = tk.Button(self, text="NEXT  →", command=self._next)
        style_btn(btn)
        btn.pack(pady=8)

    def _stat_lbl(self, parent, key, val):
        f = tk.Frame(parent, bg=CARD)
        f.pack(side="left", expand=True)
        tk.Label(f, text=key, bg=CARD, fg=MUTED, font=("Courier", 8)).pack()
        v = tk.Label(f, text=val, bg=CARD, fg=ACCENT, font=("Courier", 12, "bold"))
        v.pack()
        return v

    def on_show(self):
        if not self.map_widget:
            return
        # Clear leftover markers and paths from previous mission
        for m in self._path_markers:
            m.delete()
        self._path_markers.clear()
        if self._path_line:
            self._path_line.delete()
            self._path_line = None
        if self._drawing_menu:
            self._drawing_menu.clear_geofence()
        self._refresh_stats()
        lat = self.STATE.ground_station_lat or 39.5
        lon = self.STATE.ground_station_lon or -98.35
        self.map_widget.set_position(lat, lon)
        self.map_widget.set_zoom(17)

    def _undo_active(self):
        """Undo the last point on whichever layer is currently active."""
        if self._drawing_menu and self._drawing_menu.mode == MODE_GEOFENCE:
            self._drawing_menu._undo()
        else:
            self._undo_waypoint()

    def _on_map_click(self, coords):
        if not self._map_click_enabled:
            return
        if self._drawing_menu and self._drawing_menu.on_map_click(coords):
            self._refresh_stats()
            return
        self._add_waypoint(coords)

    def _on_mode_change(self, action):
        """Callback from DrawingMenu for undo/clear on the waypoint layer."""
        if action == "undo_waypoint":
            self._undo_waypoint()
        elif action == "clear_waypoints":
            self._clear_waypoints()

    def _add_waypoint(self, coords):
        lat, lon = coords
        self.STATE.drone_path_points.append((lat, lon))
        m = self.map_widget.set_marker(lat, lon,
                                        text=f"WP{len(self.STATE.drone_path_points)}")
        self._path_markers.append(m)
        self._draw_path()
        self._refresh_stats()

    def _draw_path(self):
        if self._path_line:
            self._path_line.delete()
            self._path_line = None
        pts = self.STATE.drone_path_points
        if len(pts) >= 2:
            self._path_line = self.map_widget.set_path(pts + [pts[0]], color=ACCENT, width=3)

    def _undo_waypoint(self):
        if self.STATE.drone_path_points:
            self.STATE.drone_path_points.pop()
        if self._path_markers:
            self._path_markers[-1].delete()
            self._path_markers.pop()
        self._draw_path()
        self._refresh_stats()

    def _clear_waypoints(self):
        self.STATE.drone_path_points.clear()
        for m in self._path_markers:
            m.delete()
        self._path_markers.clear()
        if self._path_line:
            self._path_line.delete()
            self._path_line = None
        self._refresh_stats()

    def _refresh_stats(self):
        compute_stats(self.STATE)
        self._stat_dist.config(text=f"{self.STATE.est_distance_m:.0f} m")
        self._stat_time.config(text=f"{self.STATE.est_time_min:.1f} min")
        self._stat_batt.config(text=str(self.STATE.est_battery_loops))
        self._stat_pts.config(text=str(len(self.STATE.drone_path_points)))
        self._stat_gf.config(text=str(len(self.STATE.geofence_points)))

    def _next(self):
        if len(self.STATE.drone_path_points) < 2 and MAP_AVAILABLE:
            messagebox.showwarning("No Path", "Place at least 2 waypoints on the map.")
            return
        compute_stats(self.STATE)
        self.controller.show(Step3Page)


class Step3Page(tk.Frame):
    def __init__(self, parent, controller, STATE):
        super().__init__(parent, bg=BG)
        add_header(self, "Step 3", "Mission Config & Characteristics")
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=60, pady=20)

        def section(title):
            tk.Label(body, text=title, bg=BG, fg=ACCENT,
                     font=("Courier", 11, "bold"), anchor="w").pack(fill="x", pady=(16, 4))
            tk.Frame(body, bg=BORDER, height=1).pack(fill="x")

        def slider_row(label, var, lo, hi, unit):
            row = tk.Frame(body, bg=BG)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, bg=BG, fg=TEXT,
                     font=("Courier", 10), width=22, anchor="w").pack(side="left")
            tk.Scale(row, from_=lo, to=hi, variable=var, orient="horizontal",
                     bg=BG, fg=TEXT, troughcolor=CARD, highlightthickness=0,
                     activebackground=ACCENT, sliderrelief="flat",
                     resolution=0.5, length=220).pack(side="left")
            tk.Label(row, textvariable=var, bg=BG, fg=ACCENT,
                     font=("Courier", 10), width=6).pack(side="left")
            tk.Label(row, text=unit, bg=BG, fg=MUTED,
                     font=("Courier", 9)).pack(side="left")

        def check_row(label, var):
            row = tk.Frame(body, bg=BG)
            row.pack(fill="x", pady=3)
            tk.Checkbutton(row, text=label, variable=var, bg=BG, fg=TEXT,
                           selectcolor=ACCENT, activebackground=BG,
                           activeforeground=ACCENT,
                           font=("Courier", 10), anchor="w").pack(side="left")

        section("⚡ Flight Characteristics")
        slider_row("Cruise speed",         STATE.adv_speed,            1,   30,  "m/s")
        slider_row("Min safe altitude",    STATE.adv_min_altitude,     10,  120, "m")

        section("🛬 Landing Configuration")
        slider_row("Begin landing at",     STATE.adv_start_landing_at, 10,  60,  "% battery")
        slider_row("Emergency land at",    STATE.adv_emerg_land_at,    1,   20,  "% battery")
        tk.Label(body, text="  ↑ Begin landing triggers a controlled return & land sequence\n"
                             "  ↑ Emergency land triggers immediate descent, overrides begin landing",
                 bg=BG, fg=MUTED, font=("Courier", 8), justify="left").pack(anchor="w", padx=4)

        section("📋 Logging & Alerts")
        check_row("Log battery drain events",      STATE.adv_log_battery)
        check_row("Log hours between landings",    STATE.adv_log_hours)
        check_row("Alert on low battery (< 20%)",  STATE.adv_alert_battery)

        tk.Frame(body, bg=BG).pack(expand=True)
        btn = tk.Button(self, text="NEXT  →",
                        command=lambda: controller.show(FinalizePage))
        style_btn(btn)
        btn.pack(pady=18)


class FinalizePage(tk.Frame):
    def __init__(self, parent, controller, STATE):
        super().__init__(parent, bg=BG)
        self.controller = controller
        self.STATE = STATE

        add_header(self, "Finalize & Launch")

        # ── Summary card ──────────────────────────────────────────────────────
        self._summary_frame = tk.Frame(self, bg=CARD)
        self._summary_frame.pack(fill="x", padx=40, pady=(16, 12))
        self._summary_lbl = tk.Label(self._summary_frame, text="", bg=CARD, fg=TEXT,
                                     font=("Courier", 10), justify="left",
                                     padx=20, pady=16)
        self._summary_lbl.pack(fill="x")

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(pady=16)

        export_btn = tk.Button(btn_row, text="💾  Export JSON", command=self._export_json)
        style_btn(export_btn, primary=False)
        export_btn.pack(side="left", padx=8)

        restart_btn = tk.Button(btn_row, text="↩  New Mission", command=self._restart)
        style_btn(restart_btn, primary=False)
        restart_btn.pack(side="left", padx=8)

        # ── Export status label ───────────────────────────────────────────────
        self._export_status = tk.Label(self, text="", bg=BG, fg=ACCENT2,
                                       font=("Courier", 9))
        self._export_status.pack()

    def on_show(self):
        compute_stats(self.STATE)
        S = self.STATE
        gf_pts = len(S.geofence_points)
        summary = (
            f"  Ground Station : {S.ground_station_lat:.5f}, {S.ground_station_lon:.5f}\n"
            f"  Waypoints      : {len(S.drone_path_points)}\n"
            f"  Loops          : {S.loop_count.get()}\n"
            f"  Total Distance : {S.est_distance_m:.0f} m  ({S.est_distance_m/1000:.2f} km)\n"
            f"  Est. Flight Time: {S.est_time_min:.1f} min\n"
            f"  Battery Swaps  : {S.est_battery_loops}\n"
            f"  Geofence       : {'Yes (' + str(gf_pts) + ' pts)' if gf_pts >= 3 else 'None'}\n"
            f"  Cruise Speed   : {S.adv_speed.get()} m/s\n"
            f"  Min Altitude   : {S.adv_min_altitude.get()} m\n"
            f"  Begin Landing  : {S.adv_start_landing_at.get()}% battery\n"
            f"  Emergency Land : {S.adv_emerg_land_at.get()}% battery\n"
            f"  Loop Until Low Batt: {'Yes' if S.adv_loop_until_low_batt.get() else 'No'}\n"
            f"  Log Battery    : {'Yes' if S.adv_log_battery.get() else 'No'}\n"
            f"  Log Hours      : {'Yes' if S.adv_log_hours.get() else 'No'}\n"
            f"  Low Batt Alert : {'Yes' if S.adv_alert_battery.get() else 'No'}"
        )
        self._summary_lbl.config(text=summary)
        self._export_status.config(text="")

    def _build_json(self):
        """Build the full mission dict."""
        S = self.STATE
        compute_stats(S)
        import datetime
        return {
            "mission": {
                "exported_at": datetime.datetime.now().isoformat(),
                "ground_station": {
                    "address": S.ground_station_address.get(),
                    "lat": S.ground_station_lat,
                    "lon": S.ground_station_lon,
                },
                "flight_path": {
                    "waypoints": [
                        {"index": i + 1, "lat": lat, "lon": lon}
                        for i, (lat, lon) in enumerate(S.drone_path_points)
                    ],
                    "loops": S.loop_count.get(),
                    "total_distance_m": round(S.est_distance_m, 2),
                    "total_distance_km": round(S.est_distance_m / 1000, 3),
                    "est_flight_time_min": round(S.est_time_min, 2),
                    "est_battery_swaps": S.est_battery_loops,
                },
                "geofence": {
                    "enabled": len(S.geofence_points) >= 3,
                    "points": [
                        {"index": i + 1, "lat": lat, "lon": lon}
                        for i, (lat, lon) in enumerate(S.geofence_points)
                    ],
                },
                "advanced": {
                    "cruise_speed_ms": S.adv_speed.get(),
                    "min_altitude_m": S.adv_min_altitude.get(),
                    "begin_landing_pct": S.adv_start_landing_at.get(),
                    "emergency_land_pct": S.adv_emerg_land_at.get(),
                    "loop_until_low_battery": S.adv_loop_until_low_batt.get(),
                    "log_battery_events": S.adv_log_battery.get(),
                    "log_flight_hours": S.adv_log_hours.get(),
                    "low_battery_alert": S.adv_alert_battery.get(),
                },
            }
        }

    @staticmethod
    def _get_removable_drives():
        """Return list of (label, path) for removable/external drives."""
        drives = []
        if sys.platform == "win32":
            import ctypes
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                if bitmask & 1:
                    root = f"{letter}:\\"
                    drive_type = ctypes.windll.kernel32.GetDriveTypeW(root)
                    # 2 = DRIVE_REMOVABLE, 5 = DRIVE_CDROM
                    if drive_type == 2:
                        try:
                            vol_buf  = ctypes.create_unicode_buffer(261)
                            ctypes.windll.kernel32.GetVolumeInformationW(
                                root, vol_buf, 261, None, None, None, None, 0)
                            label = vol_buf.value or "Removable"
                        except Exception:
                            label = "Removable"
                        drives.append((f"{label} ({letter}:)", root))
                bitmask >>= 1
        elif sys.platform == "darwin":
            volumes = "/Volumes"
            for name in os.listdir(volumes):
                full = os.path.join(volumes, name)
                if name != "Macintosh HD" and os.path.ismount(full):
                    drives.append((name, full))
        else:
            # Linux — look in /media and /run/media
            for base in [f"/media/{os.getenv('USER','')}", "/media", "/run/media"]:
                if os.path.isdir(base):
                    for name in os.listdir(base):
                        full = os.path.join(base, name)
                        if os.path.ismount(full):
                            drives.append((name, full))
        return drives

    def _export_json(self):
        import datetime
        drives = self._get_removable_drives()

        if not drives:
            # No removable device found — warn and offer fallback
            if not messagebox.askyesno(
                "No Removable Device Found",
                "No removable drive detected.\n\n"
                "It is recommended to export directly to your drone's SD card or USB drive.\n\n"
                "Export to a local folder instead?",
                icon="warning"
            ):
                return
            # Fallback to regular save dialog
            default_name = f"farmvates_mission_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialfile=default_name,
                title="Export Mission JSON — Local Fallback"
            )
            if not path:
                return
            self._write_json(path)
            return

        # Show drive picker dialog
        self._show_drive_picker(drives)

    def _show_drive_picker(self, drives):
        import datetime
        win = tk.Toplevel(self)
        win.title("Select Removable Device")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.grab_set()

        tk.Label(win, text="Select export destination:", bg=BG, fg=TEXT,
                 font=("Courier", 11, "bold"), pady=10).pack(padx=24)
        tk.Label(win, text="Export directly to a removable device (SD card / USB drive)",
                 bg=BG, fg=MUTED, font=("Courier", 9)).pack(padx=24)

        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=16, pady=8)

        selected = tk.StringVar(value=drives[0][1])
        for label, path in drives:
            rb = tk.Radiobutton(win, text=f"  💾  {label}", variable=selected, value=path,
                                bg=CARD, fg=TEXT, selectcolor=ACCENT,
                                activebackground=CARD, activeforeground=ACCENT,
                                font=("Courier", 11), indicatoron=False,
                                width=32, pady=8, relief="flat", bd=0, cursor="hand2")
            rb.pack(padx=24, pady=3, fill="x")

        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=16, pady=8)

        default_name = f"farmvates_mission_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        def confirm():
            dest = os.path.join(selected.get(), default_name)
            win.destroy()
            try:
                self._write_json(dest)
            except Exception as e:
                self._export_status.config(text=f"❌  Export failed: {e}", fg=DANGER)

        def cancel():
            win.destroy()

        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(pady=(0, 16))
        ok_btn = tk.Button(btn_row, text="Export  →", command=confirm)
        style_btn(ok_btn)
        ok_btn.pack(side="left", padx=8)
        cancel_btn = tk.Button(btn_row, text="Cancel", command=cancel)
        style_btn(cancel_btn, primary=False)
        cancel_btn.pack(side="left", padx=8)

        # Centre over main window
        win.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{x}+{y}")

    def _write_json(self, path):
        import os
        try:
            data = self._build_json()
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            self._export_status.config(
                text=f"✅  Saved → {os.path.basename(path)}", fg=ACCENT2)
        except Exception as e:
            self._export_status.config(
                text=f"❌  Export failed: {e}", fg=DANGER)

    def _restart(self):
        S = self.STATE
        S.drone_path_points.clear()
        S.geofence_points.clear()
        # Keep ground station so user doesn't have to re-enter it
        self.controller.show(SplashPage)


# ─────────────────────────────────────────────────────────────────────────────
# Main application
# ─────────────────────────────────────────────────────────────────────────────
class FarmVatesApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.STATE = AppState()

        self.title("Farmvates ✦ Drone Mission Planner")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.geometry("900x700")
        self.minsize(800, 600)

        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self._frames = {}
        for PageClass in (SplashPage, HowItWorksPage, Step1Page,
                          Step2Page, Step3Page, FinalizePage):
            page = PageClass(container, self, self.STATE)
            self._frames[PageClass] = page
            page.grid(row=0, column=0, sticky="nsew")

        self.show(SplashPage)

    def show(self, page_class):
        frame = self._frames[page_class]
        if hasattr(frame, "on_show"):
            frame.on_show()
        frame.tkraise()


if __name__ == "__main__":
    app = FarmVatesApp()
    app.mainloop()