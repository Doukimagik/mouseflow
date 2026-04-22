"""
MouseFlow - Automatisation avancée de la souris
Application complète avec canvas de dessin de trajectoires
"""

import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, simpledialog
import threading
import time
import json
import math
import pyautogui
import os
import sys

pyautogui.FAILSAFE = True  # Coin haut-gauche = arrêt d'urgence

# ─────────────────────────────────────────────
#  MODÈLES DE DONNÉES
# ─────────────────────────────────────────────

class Action:
    """Représente une action dans la séquence"""
    def __init__(self, action_type, **kwargs):
        self.type = action_type  # 'point', 'line', 'click', 'input', 'condition'
        self.data = kwargs

    def to_dict(self):
        return {"type": self.type, "data": self.data}

    @staticmethod
    def from_dict(d):
        return Action(d["type"], **d["data"])


class Segment:
    """Segment d'une ligne avec sa propre vitesse"""
    def __init__(self, x1, y1, x2, y2, speed=500, steps=50):
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.speed = speed   # pixels/seconde
        self.steps = steps   # nombre d'interpolations


# ─────────────────────────────────────────────
#  MOTEUR D'EXÉCUTION
# ─────────────────────────────────────────────

class ExecutionEngine:
    def __init__(self, actions, on_log, on_done):
        self.actions = actions
        self.on_log = on_log
        self.on_done = on_done
        self.running = False
        self._thread = None

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    def _run(self):
        try:
            for i, action in enumerate(self.actions):
                if not self.running:
                    break
                self.on_log(f"[{i+1}/{len(self.actions)}] Exécution : {action.type}")
                self._execute(action)
                time.sleep(0.05)
        except Exception as e:
            self.on_log(f"❌ Erreur : {e}")
        finally:
            self.running = False
            self.on_done()

    def _execute(self, action):
        d = action.data
        t = action.type

        if t == "move":
            x, y = int(d["x"]), int(d["y"])
            dur = d.get("duration", 0.3)
            pyautogui.moveTo(x, y, duration=dur)

        elif t == "click":
            x, y = int(d["x"]), int(d["y"])
            btn = d.get("button", "left")
            speed = d.get("speed", 0.3)
            clicks = d.get("clicks", 1)
            pyautogui.moveTo(x, y, duration=speed)
            pyautogui.click(button=btn, clicks=clicks)
            self.on_log(f"   → Clic {btn} x{clicks} en ({x},{y})")

        elif t == "line":
            points = d.get("points", [])
            segments = d.get("segments", [])
            if segments:
                for seg in segments:
                    if not self.running:
                        return
                    self._move_segment(
                        seg["x1"], seg["y1"], seg["x2"], seg["y2"],
                        seg.get("speed", 500), seg.get("steps", 50)
                    )
            elif len(points) >= 2:
                speed = d.get("speed", 500)
                for i in range(len(points) - 1):
                    if not self.running:
                        return
                    p1, p2 = points[i], points[i+1]
                    self._move_segment(p1[0], p1[1], p2[0], p2[1], speed, 50)

        elif t == "drag_line":
            points = d.get("points", [])
            if not points:
                return
            speed = d.get("speed", 500)
            pyautogui.moveTo(int(points[0][0]), int(points[0][1]), duration=0.2)
            pyautogui.mouseDown()
            for i in range(1, len(points)):
                if not self.running:
                    pyautogui.mouseUp()
                    return
                p1, p2 = points[i-1], points[i]
                self._move_segment(p1[0], p1[1], p2[0], p2[1], speed, 30)
            pyautogui.mouseUp()

        elif t == "input_text":
            text = d.get("text", "")
            delay = d.get("delay", 0.05)
            pyautogui.typewrite(text, interval=delay)
            self.on_log(f"   → Texte tapé : '{text}'")

        elif t == "key_press":
            key = d.get("key", "")
            pyautogui.press(key)
            self.on_log(f"   → Touche : {key}")

        elif t == "wait":
            dur = d.get("duration", 1.0)
            self.on_log(f"   → Attente {dur}s")
            time.sleep(dur)

        elif t == "condition_color":
            x, y = int(d["x"]), int(d["y"])
            target = tuple(d.get("color", [255, 0, 0]))
            tolerance = d.get("tolerance", 30)
            then_actions = [Action.from_dict(a) for a in d.get("then", [])]
            px = pyautogui.pixel(x, y)
            match = all(abs(px[i] - target[i]) <= tolerance for i in range(3))
            self.on_log(f"   → Pixel ({x},{y}) = {px}, cible = {target} → {'✅ match' if match else '❌ no match'}")
            if match:
                for sub in then_actions:
                    if not self.running:
                        return
                    self._execute(sub)

        elif t == "sequence":
            sub_actions = [Action.from_dict(a) for a in d.get("actions", [])]
            repeat = d.get("repeat", 1)
            for _ in range(repeat):
                for sub in sub_actions:
                    if not self.running:
                        return
                    self._execute(sub)

    def _move_segment(self, x1, y1, x2, y2, speed, steps):
        dist = math.hypot(x2 - x1, y2 - y1)
        duration = dist / speed if speed > 0 else 0.01
        pyautogui.moveTo(int(x2), int(y2), duration=duration)


# ─────────────────────────────────────────────
#  INTERFACE GRAPHIQUE
# ─────────────────────────────────────────────

class MouseFlowApp:
    CANVAS_W = 900
    CANVAS_H = 560
    SCALE = 1.0  # ratio canvas / écran réel

    def __init__(self, root):
        self.root = root
        self.root.title("🖱️ MouseFlow — Automatisation avancée")
        self.root.configure(bg="#0d1117")
        self.root.resizable(True, True)

        # État
        self.actions = []          # liste d'Action
        self.selected_tool = tk.StringVar(value="move")
        self.drawing_line = False
        self.line_points = []
        self.drag_mode = False
        self.current_speed = tk.DoubleVar(value=500)
        self.engine = None
        self.canvas_items = []    # (canvas_id, action_index)
        self.screen_w = pyautogui.size().width
        self.screen_h = pyautogui.size().height
        self._update_scale()

        # Récupère les coordonnées en direct
        self.live_pos = tk.StringVar(value="Souris : —")

        self._build_ui()
        self._track_mouse()

    def _update_scale(self):
        self.scale_x = self.CANVAS_W / self.screen_w
        self.scale_y = self.CANVAS_H / self.screen_h

    def _to_canvas(self, rx, ry):
        return rx * self.scale_x, ry * self.scale_y

    def _to_real(self, cx, cy):
        return cx / self.scale_x, cy / self.scale_y

    # ── UI BUILD ──────────────────────────────

    def _build_ui(self):
        # Palette couleurs
        C = {
            "bg":       "#0d1117",
            "panel":    "#161b22",
            "border":   "#30363d",
            "accent":   "#58a6ff",
            "green":    "#3fb950",
            "red":      "#f85149",
            "orange":   "#d29922",
            "text":     "#e6edf3",
            "muted":    "#8b949e",
        }
        self.C = C

        # Barre du haut
        topbar = tk.Frame(self.root, bg=C["panel"], height=48)
        topbar.pack(fill="x")
        tk.Label(topbar, text="🖱️ MouseFlow", font=("Consolas", 16, "bold"),
                 fg=C["accent"], bg=C["panel"]).pack(side="left", padx=16, pady=8)
        tk.Label(topbar, textvariable=self.live_pos, font=("Consolas", 10),
                 fg=C["muted"], bg=C["panel"]).pack(side="right", padx=16)

        # Corps principal
        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True)

        # ── Panneau gauche : outils ──
        left = tk.Frame(body, bg=C["panel"], width=220, relief="flat")
        left.pack(side="left", fill="y", padx=(8,0), pady=8)
        left.pack_propagate(False)
        self._build_tools(left)

        # ── Canvas central ──
        center = tk.Frame(body, bg=C["bg"])
        center.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        self._build_canvas(center)

        # ── Panneau droit : séquence ──
        right = tk.Frame(body, bg=C["panel"], width=240)
        right.pack(side="right", fill="y", padx=(0,8), pady=8)
        right.pack_propagate(False)
        self._build_sequence(right)

        # ── Barre du bas ──
        self._build_bottom()

    def _section(self, parent, title):
        tk.Label(parent, text=title, font=("Consolas", 9, "bold"),
                 fg=self.C["muted"], bg=self.C["panel"]).pack(anchor="w", padx=10, pady=(12,2))
        sep = tk.Frame(parent, bg=self.C["border"], height=1)
        sep.pack(fill="x", padx=8, pady=(0,6))

    def _build_tools(self, parent):
        C = self.C
        tk.Label(parent, text="OUTILS", font=("Consolas", 10, "bold"),
                 fg=C["accent"], bg=C["panel"]).pack(pady=(14,4))

        tools = [
            ("➡️  Déplacement",    "move"),
            ("🖱️  Clic simple",    "click"),
            ("✏️  Ligne (glisser)","drag_line"),
            ("📍 Ligne (clics)",   "line"),
            ("⌨️  Texte / Touche", "input"),
            ("⏱️  Attente",        "wait"),
            ("🎨 Condition couleur","condition"),
        ]
        for label, val in tools:
            rb = tk.Radiobutton(
                parent, text=label, variable=self.selected_tool, value=val,
                font=("Consolas", 10), fg=C["text"], bg=C["panel"],
                selectcolor=C["bg"], activebackground=C["panel"],
                activeforeground=C["accent"], indicatoron=False,
                relief="flat", padx=10, pady=6, anchor="w", width=20,
                command=self._on_tool_change
            )
            rb.pack(fill="x", padx=8, pady=2)

        self._section(parent, "VITESSE (px/s)")
        spd_frame = tk.Frame(parent, bg=C["panel"])
        spd_frame.pack(fill="x", padx=10)
        self.spd_label = tk.Label(spd_frame, text="500 px/s",
                                   font=("Consolas", 10), fg=C["accent"], bg=C["panel"])
        self.spd_label.pack(side="right")
        tk.Scale(spd_frame, from_=50, to=3000, orient="horizontal",
                 variable=self.current_speed, bg=C["panel"], fg=C["text"],
                 troughcolor=C["border"], highlightthickness=0, showvalue=False,
                 command=lambda v: self.spd_label.config(text=f"{int(float(v))} px/s")
                 ).pack(side="left", fill="x", expand=True)

        self._section(parent, "OPTIONS CLIC")
        self.click_btn_var = tk.StringVar(value="left")
        btn_frame = tk.Frame(parent, bg=C["panel"])
        btn_frame.pack(fill="x", padx=8)
        for lbl, val in [("Gauche","left"), ("Droit","right"), ("Double","double")]:
            tk.Radiobutton(btn_frame, text=lbl, variable=self.click_btn_var,
                           value=val, font=("Consolas", 9), fg=C["text"],
                           bg=C["panel"], selectcolor=C["bg"],
                           activebackground=C["panel"]).pack(side="left")

        self._section(parent, "RÉPÉTITION")
        rep_frame = tk.Frame(parent, bg=C["panel"])
        rep_frame.pack(fill="x", padx=10)
        tk.Label(rep_frame, text="Répéter :", font=("Consolas", 9),
                 fg=C["muted"], bg=C["panel"]).pack(side="left")
        self.repeat_var = tk.IntVar(value=1)
        tk.Spinbox(rep_frame, from_=1, to=999, textvariable=self.repeat_var,
                   width=5, font=("Consolas", 10), bg=C["bg"], fg=C["text"],
                   buttonbackground=C["border"], insertbackground=C["text"]
                   ).pack(side="left", padx=4)

        self._section(parent, "CAPTURE LIVE")
        self.capture_btn = tk.Button(
            parent, text="📸 Capturer position réelle",
            font=("Consolas", 9), fg=C["text"], bg=C["border"],
            relief="flat", padx=8, pady=4,
            command=self._capture_real_pos
        )
        self.capture_btn.pack(fill="x", padx=8, pady=4)
        self.captured_label = tk.Label(parent, text="", font=("Consolas", 8),
                                        fg=C["green"], bg=C["panel"])
        self.captured_label.pack()

    def _build_canvas(self, parent):
        C = self.C
        tk.Label(parent, text="📺  Zone de visualisation (représentation de votre écran)",
                 font=("Consolas", 9), fg=C["muted"], bg=C["bg"]).pack(anchor="w")

        canvas_frame = tk.Frame(parent, bg=C["border"], padx=1, pady=1)
        canvas_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            canvas_frame, width=self.CANVAS_W, height=self.CANVAS_H,
            bg="#010409", cursor="crosshair", highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        # Grille
        for x in range(0, self.CANVAS_W, 90):
            self.canvas.create_line(x, 0, x, self.CANVAS_H, fill="#1a1f28", width=1)
        for y in range(0, self.CANVAS_H, 56):
            self.canvas.create_line(0, y, self.CANVAS_W, y, fill="#1a1f28", width=1)

        # Labels coins
        self.canvas.create_text(4, 4, text="0,0", fill="#2d333b",
                                  font=("Consolas", 7), anchor="nw")
        self.canvas.create_text(self.CANVAS_W-4, self.CANVAS_H-4,
                                  text=f"{self.screen_w},{self.screen_h}",
                                  fill="#2d333b", font=("Consolas", 7), anchor="se")

        # Événements
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Button-3>", self._on_canvas_right_click)

        # Curseur live
        self.live_dot = self.canvas.create_oval(0,0,0,0, fill=C["green"],
                                                  outline="white", width=1)

    def _build_sequence(self, parent):
        C = self.C
        tk.Label(parent, text="SÉQUENCE", font=("Consolas", 10, "bold"),
                 fg=C["accent"], bg=C["panel"]).pack(pady=(14,4))

        frame = tk.Frame(parent, bg=C["panel"])
        frame.pack(fill="both", expand=True, padx=6)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")

        self.seq_list = tk.Listbox(
            frame, yscrollcommand=scrollbar.set,
            bg=C["bg"], fg=C["text"], selectbackground=C["accent"],
            font=("Consolas", 9), relief="flat", bd=0,
            selectforeground="#000", activestyle="none"
        )
        self.seq_list.pack(fill="both", expand=True)
        scrollbar.config(command=self.seq_list.yview)

        btn_frame = tk.Frame(parent, bg=C["panel"])
        btn_frame.pack(fill="x", padx=6, pady=4)
        for txt, cmd, color in [
            ("⬆ Monter",   self._seq_up,     C["border"]),
            ("⬇ Descendre",self._seq_down,   C["border"]),
            ("✏️ Éditer",   self._seq_edit,   C["orange"]),
            ("🗑 Supprimer",self._seq_delete, C["red"]),
        ]:
            tk.Button(btn_frame, text=txt, command=cmd,
                      font=("Consolas", 8), fg=C["text"], bg=color,
                      relief="flat", padx=4, pady=3
                      ).pack(fill="x", pady=1)

    def _build_bottom(self):
        C = self.C
        bar = tk.Frame(self.root, bg=C["panel"], height=52)
        bar.pack(fill="x", padx=8, pady=(0,8))

        btns = [
            ("▶  EXÉCUTER",   self._execute,     C["green"]),
            ("⏹  STOP",        self._stop,        C["red"]),
            ("💾 Sauvegarder", self._save,         C["border"]),
            ("📂 Charger",     self._load,         C["border"]),
            ("🗑 Tout effacer", self._clear_all,   C["border"]),
        ]
        for txt, cmd, bg in btns:
            tk.Button(bar, text=txt, command=cmd,
                      font=("Consolas", 10, "bold"), fg=C["text"], bg=bg,
                      relief="flat", padx=16, pady=8
                      ).pack(side="left", padx=4, pady=8)

        self.log_var = tk.StringVar(value="Prêt. Choisissez un outil et cliquez sur le canvas.")
        tk.Label(bar, textvariable=self.log_var, font=("Consolas", 9),
                 fg=C["muted"], bg=C["panel"], anchor="w"
                 ).pack(side="left", padx=12, fill="x", expand=True)

    # ── OUTILS ────────────────────────────────

    def _on_tool_change(self):
        self.drawing_line = False
        self.line_points = []

    def _on_canvas_motion(self, e):
        rx, ry = self._to_real(e.x, e.y)
        self.live_pos.set(f"Canvas ({e.x},{e.y}) → Écran ({int(rx)},{int(ry)})")
        r = 5
        self.canvas.coords(self.live_dot, e.x-r, e.y-r, e.x+r, e.y+r)

        # Prévisualisation ligne
        if self.selected_tool.get() in ("line", "drag_line") and self.line_points:
            self.canvas.delete("preview")
            lx, ly = self._to_canvas(*self.line_points[-1])
            self.canvas.create_line(lx, ly, e.x, e.y,
                                     fill="#58a6ff", dash=(4,4), tags="preview")

    def _on_canvas_click(self, e):
        tool = self.selected_tool.get()
        rx, ry = self._to_real(e.x, e.y)

        if tool == "move":
            action = Action("move", x=rx, y=ry, duration=0.3)
            self._add_action(action)
            self._draw_point(e.x, e.y, color="#58a6ff", label="MOVE")

        elif tool == "click":
            btn = self.click_btn_var.get()
            clicks = 2 if btn == "double" else 1
            real_btn = "left" if btn == "double" else btn
            action = Action("click", x=rx, y=ry, button=real_btn,
                            clicks=clicks, speed=self.current_speed.get()/1000)
            self._add_action(action)
            self._draw_point(e.x, e.y, color="#f85149", label="CLICK")

        elif tool in ("line", "drag_line"):
            self.line_points.append((rx, ry))
            cx, cy = self._to_canvas(rx, ry)
            self._draw_point(cx, cy, color="#3fb950", size=4)
            if len(self.line_points) > 1:
                p1 = self._to_canvas(*self.line_points[-2])
                p2 = self._to_canvas(*self.line_points[-1])
                self.canvas.create_line(*p1, *p2, fill="#3fb950", width=2)

        elif tool == "input":
            self._add_input_dialog(rx, ry)

        elif tool == "wait":
            dur = simpledialog.askfloat("Attente", "Durée (secondes) :",
                                         minvalue=0.1, maxvalue=60.0,
                                         initialvalue=1.0, parent=self.root)
            if dur:
                action = Action("wait", duration=dur)
                self._add_action(action)
                self._draw_point(e.x, e.y, color="#d29922", label=f"WAIT {dur}s")

        elif tool == "condition":
            self._add_condition_dialog(rx, ry)

    def _on_canvas_drag(self, e):
        pass  # drag géré par release

    def _on_canvas_release(self, e):
        pass

    def _on_canvas_right_click(self, e):
        tool = self.selected_tool.get()
        if tool in ("line", "drag_line") and len(self.line_points) >= 2:
            self.canvas.delete("preview")
            action_type = tool
            action = Action(action_type,
                            points=list(self.line_points),
                            speed=self.current_speed.get())
            self._add_action(action)
            self.log(f"✅ {action_type} ajouté avec {len(self.line_points)} points")
            self.line_points = []
        elif tool in ("line", "drag_line"):
            self.line_points = []
            self.canvas.delete("preview")

    def _add_input_dialog(self, rx, ry):
        dialog = tk.Toplevel(self.root)
        dialog.title("Action texte/touche")
        dialog.configure(bg=self.C["panel"])
        dialog.grab_set()
        dialog.geometry("360x220")

        tk.Label(dialog, text="Type d'action :", font=("Consolas", 10),
                 fg=self.C["text"], bg=self.C["panel"]).pack(pady=(12,4))
        type_var = tk.StringVar(value="text")
        for lbl, val in [("Écrire un texte", "text"), ("Appuyer une touche", "key")]:
            tk.Radiobutton(dialog, text=lbl, variable=type_var, value=val,
                           font=("Consolas", 10), fg=self.C["text"],
                           bg=self.C["panel"], selectcolor=self.C["bg"],
                           activebackground=self.C["panel"]).pack(anchor="w", padx=20)

        tk.Label(dialog, text="Contenu :", font=("Consolas", 10),
                 fg=self.C["text"], bg=self.C["panel"]).pack(pady=(8,2))
        entry = tk.Entry(dialog, font=("Consolas", 11), bg=self.C["bg"],
                         fg=self.C["text"], insertbackground=self.C["text"], width=30)
        entry.pack(padx=20, ipady=4)
        tk.Label(dialog, text="(Pour une touche : enter, space, ctrl+c, f5…)",
                 font=("Consolas", 8), fg=self.C["muted"], bg=self.C["panel"]).pack()

        def confirm():
            val = entry.get().strip()
            if not val:
                return
            if type_var.get() == "text":
                action = Action("input_text", text=val, delay=0.05)
                self._add_action(action)
                self.log(f"✅ Texte : '{val}'")
            else:
                action = Action("key_press", key=val)
                self._add_action(action)
                self.log(f"✅ Touche : {val}")
            dialog.destroy()

        tk.Button(dialog, text="✅ Ajouter", command=confirm,
                  font=("Consolas", 10, "bold"), fg="#000",
                  bg=self.C["green"], relief="flat", pady=6
                  ).pack(pady=10, padx=20, fill="x")

    def _add_condition_dialog(self, rx, ry):
        dialog = tk.Toplevel(self.root)
        dialog.title("Condition couleur")
        dialog.configure(bg=self.C["panel"])
        dialog.grab_set()
        dialog.geometry("380x280")

        tk.Label(dialog, text=f"Position vérifiée : ({int(rx)}, {int(ry)})",
                 font=("Consolas", 10), fg=self.C["accent"], bg=self.C["panel"]).pack(pady=(12,4))

        color_var = tk.StringVar(value="#ff0000")
        preview_frame = tk.Frame(dialog, bg=self.C["panel"])
        preview_frame.pack()
        color_preview = tk.Label(preview_frame, bg="#ff0000", width=6, height=2, relief="flat")
        color_preview.pack(side="left", padx=8)

        def pick_color():
            c = colorchooser.askcolor(color=color_var.get(), parent=dialog)
            if c[1]:
                color_var.set(c[1])
                color_preview.config(bg=c[1])

        tk.Button(preview_frame, text="🎨 Choisir couleur", command=pick_color,
                  font=("Consolas", 9), fg=self.C["text"], bg=self.C["border"],
                  relief="flat", padx=8).pack(side="left")

        tk.Label(dialog, text="Tolérance (0-255) :", font=("Consolas", 9),
                 fg=self.C["muted"], bg=self.C["panel"]).pack(pady=(8,2))
        tol_var = tk.IntVar(value=30)
        tk.Scale(dialog, from_=0, to=100, orient="horizontal", variable=tol_var,
                 bg=self.C["panel"], fg=self.C["text"],
                 troughcolor=self.C["border"], highlightthickness=0).pack(fill="x", padx=20)

        tk.Label(dialog, text="Action si match → clic gauche sur la position",
                 font=("Consolas", 8), fg=self.C["muted"], bg=self.C["panel"]).pack(pady=4)

        def confirm():
            hex_c = color_var.get().lstrip("#")
            rgb = [int(hex_c[i:i+2], 16) for i in (0,2,4)]
            then = [Action("click", x=rx, y=ry, button="left", clicks=1, speed=0.1).to_dict()]
            action = Action("condition_color", x=rx, y=ry,
                            color=rgb, tolerance=tol_var.get(), then=then)
            self._add_action(action)
            self.log(f"✅ Condition couleur en ({int(rx)},{int(ry)})")
            dialog.destroy()

        tk.Button(dialog, text="✅ Ajouter", command=confirm,
                  font=("Consolas", 10, "bold"), fg="#000",
                  bg=self.C["green"], relief="flat", pady=6
                  ).pack(pady=10, padx=20, fill="x")

    # ── SÉQUENCE ──────────────────────────────

    def _add_action(self, action):
        self.actions.append(action)
        self._refresh_seq_list()

    def _refresh_seq_list(self):
        self.seq_list.delete(0, tk.END)
        icons = {
            "move": "➡️", "click": "🖱️", "line": "📍",
            "drag_line": "✏️", "input_text": "⌨️", "key_press": "🔑",
            "wait": "⏱️", "condition_color": "🎨", "sequence": "🔁"
        }
        for i, a in enumerate(self.actions):
            icon = icons.get(a.type, "•")
            d = a.data
            if a.type in ("move", "click"):
                detail = f"({int(d.get('x',0))},{int(d.get('y',0))})"
            elif a.type in ("line", "drag_line"):
                detail = f"{len(d.get('points',[]))} pts, {d.get('speed',500):.0f}px/s"
            elif a.type == "input_text":
                detail = f"'{d.get('text','')[:20]}'"
            elif a.type == "key_press":
                detail = d.get("key", "")
            elif a.type == "wait":
                detail = f"{d.get('duration',1)}s"
            elif a.type == "condition_color":
                detail = f"couleur={d.get('color')} en ({int(d.get('x',0))},{int(d.get('y',0))})"
            else:
                detail = str(d)[:30]
            self.seq_list.insert(tk.END, f"  {i+1:02d}  {icon} {a.type}  {detail}")

    def _seq_up(self):
        sel = self.seq_list.curselection()
        if sel and sel[0] > 0:
            i = sel[0]
            self.actions[i-1], self.actions[i] = self.actions[i], self.actions[i-1]
            self._refresh_seq_list()
            self.seq_list.selection_set(i-1)

    def _seq_down(self):
        sel = self.seq_list.curselection()
        if sel and sel[0] < len(self.actions)-1:
            i = sel[0]
            self.actions[i], self.actions[i+1] = self.actions[i+1], self.actions[i]
            self._refresh_seq_list()
            self.seq_list.selection_set(i+1)

    def _seq_delete(self):
        sel = self.seq_list.curselection()
        if sel:
            self.actions.pop(sel[0])
            self._refresh_seq_list()

    def _seq_edit(self):
        sel = self.seq_list.curselection()
        if not sel:
            return
        a = self.actions[sel[0]]
        # Édition simple : vitesse pour lines
        if a.type in ("line", "drag_line"):
            new_spd = simpledialog.askinteger("Vitesse", f"Vitesse (px/s) :",
                                               initialvalue=int(a.data.get("speed",500)),
                                               minvalue=10, maxvalue=5000, parent=self.root)
            if new_spd:
                a.data["speed"] = new_spd
                self._refresh_seq_list()
        elif a.type == "wait":
            dur = simpledialog.askfloat("Attente", "Durée (s) :",
                                         initialvalue=a.data.get("duration",1),
                                         minvalue=0.1, maxvalue=60, parent=self.root)
            if dur:
                a.data["duration"] = dur
                self._refresh_seq_list()
        elif a.type in ("move","click"):
            new_x = simpledialog.askinteger("X", "Position X :", initialvalue=int(a.data.get("x",0)), parent=self.root)
            new_y = simpledialog.askinteger("Y", "Position Y :", initialvalue=int(a.data.get("y",0)), parent=self.root)
            if new_x is not None and new_y is not None:
                a.data["x"], a.data["y"] = new_x, new_y
                self._refresh_seq_list()

    # ── DESSIN CANVAS ─────────────────────────

    def _draw_point(self, cx, cy, color="#58a6ff", size=7, label=None):
        r = size
        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                  fill=color, outline="white", width=1)
        if label:
            self.canvas.create_text(cx+10, cy, text=label,
                                     fill=color, font=("Consolas", 7), anchor="w")

    # ── EXÉCUTION ────────────────────────────

    def _execute(self):
        if not self.actions:
            messagebox.showinfo("Vide", "Aucune action dans la séquence !")
            return
        if not messagebox.askyesno("Confirmer",
            f"Lancer {len(self.actions)} actions ?\n\n"
            "⚠️ Déplacez la souris en haut-gauche pour arrêter d'urgence."):
            return

        repeat = self.repeat_var.get()
        all_actions = self.actions * repeat

        self.engine = ExecutionEngine(all_actions, self.log, self._on_exec_done)
        self.log("▶ Démarrage dans 2 secondes…")
        self.root.after(2000, self.engine.start)

    def _stop(self):
        if self.engine:
            self.engine.stop()
            self.log("⏹ Arrêté.")

    def _on_exec_done(self):
        self.log("✅ Séquence terminée.")

    # ── SAUVEGARDE ───────────────────────────

    def _save(self):
        from tkinter.filedialog import asksaveasfilename
        path = asksaveasfilename(defaultextension=".json",
                                  filetypes=[("MouseFlow", "*.json")],
                                  title="Sauvegarder la séquence")
        if path:
            data = [a.to_dict() for a in self.actions]
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            self.log(f"💾 Sauvegardé : {os.path.basename(path)}")

    def _load(self):
        from tkinter.filedialog import askopenfilename
        path = askopenfilename(filetypes=[("MouseFlow", "*.json")],
                                title="Charger une séquence")
        if path:
            with open(path) as f:
                data = json.load(f)
            self.actions = [Action.from_dict(d) for d in data]
            self._refresh_seq_list()
            self.log(f"📂 Chargé : {os.path.basename(path)} ({len(self.actions)} actions)")

    def _clear_all(self):
        if messagebox.askyesno("Effacer tout", "Supprimer toutes les actions ?"):
            self.actions.clear()
            self._refresh_seq_list()
            self.canvas.delete("all")
            # Redessine la grille
            for x in range(0, self.CANVAS_W, 90):
                self.canvas.create_line(x, 0, x, self.CANVAS_H, fill="#1a1f28", width=1)
            for y in range(0, self.CANVAS_H, 56):
                self.canvas.create_line(0, y, self.CANVAS_W, y, fill="#1a1f28", width=1)
            self.live_dot = self.canvas.create_oval(0,0,0,0, fill=self.C["green"],
                                                      outline="white", width=1)
            self.log("🗑 Tout effacé.")

    # ── CAPTURE ──────────────────────────────

    def _capture_real_pos(self):
        self.log("📸 Placez la souris puis appuyez Entrée dans 3s…")
        def do():
            time.sleep(3)
            rx, ry = pyautogui.position()
            self.captured_label.config(text=f"Capturé : ({rx}, {ry})")
            self.log(f"📸 Position capturée : ({rx}, {ry})")
            cx, cy = self._to_canvas(rx, ry)
            self._draw_point(cx, cy, color="#d29922", label=f"({rx},{ry})")
        threading.Thread(target=do, daemon=True).start()

    # ── TRACKING ─────────────────────────────

    def _track_mouse(self):
        try:
            rx, ry = pyautogui.position()
            cx, cy = self._to_canvas(rx, ry)
            r = 5
            self.canvas.coords(self.live_dot, cx-r, cy-r, cx+r, cy+r)
        except:
            pass
        self.root.after(100, self._track_mouse)

    # ── LOG ──────────────────────────────────

    def log(self, msg):
        self.log_var.set(msg)
        print(msg)


# ─────────────────────────────────────────────
#  POINT D'ENTRÉE
# ─────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.geometry("1340x720")
    root.minsize(1000, 600)
    app = MouseFlowApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
