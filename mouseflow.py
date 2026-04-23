"""
MouseFlow v2.0 - Automatisation avancée de la souris
Corrections : fond écran réel, point souris fixé, touches d'urgence
"""

import tkinter as tk
from tkinter import messagebox, colorchooser, simpledialog
import threading
import time
import json
import math
import pyautogui
import os
from PIL import Image, ImageTk, ImageGrab

pyautogui.FAILSAFE = True

# ─────────────────────────────────────────────
#  MODÈLES DE DONNÉES
# ─────────────────────────────────────────────

class Action:
    def __init__(self, action_type, **kwargs):
        self.type = action_type
        self.data = kwargs

    def to_dict(self):
        return {"type": self.type, "data": self.data}

    @staticmethod
    def from_dict(d):
        return Action(d["type"], **d["data"])


# ─────────────────────────────────────────────
#  MOTEUR D'EXÉCUTION
# ─────────────────────────────────────────────

class ExecutionEngine:
    def __init__(self, actions, on_log, on_done):
        self.actions = actions
        self.on_log = on_log
        self.on_done = on_done
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.running = False

    def _run(self):
        try:
            for i, action in enumerate(self.actions):
                if not self.running:
                    break
                self.on_log(f"[{i+1}/{len(self.actions)}] {action.type}")
                self._execute(action)
                time.sleep(0.05)
        except Exception as e:
            self.on_log(f"Erreur : {e}")
        finally:
            self.running = False
            self.on_done()

    def _execute(self, action):
        d = action.data
        t = action.type

        if t == "move":
            pyautogui.moveTo(int(d["x"]), int(d["y"]), duration=d.get("duration", 0.3))

        elif t == "click":
            pyautogui.moveTo(int(d["x"]), int(d["y"]), duration=d.get("speed", 0.3))
            pyautogui.click(button=d.get("button", "left"), clicks=d.get("clicks", 1))

        elif t in ("line", "drag_line"):
            pts = d.get("points", [])
            spd = d.get("speed", 500)
            if t == "drag_line" and pts:
                pyautogui.moveTo(int(pts[0][0]), int(pts[0][1]), duration=0.2)
                pyautogui.mouseDown()
            for i in range(len(pts) - 1):
                if not self.running:
                    if t == "drag_line": pyautogui.mouseUp()
                    return
                p1, p2 = pts[i], pts[i+1]
                dist = math.hypot(p2[0]-p1[0], p2[1]-p1[1])
                pyautogui.moveTo(int(p2[0]), int(p2[1]),
                                 duration=dist/spd if spd > 0 else 0.01)
            if t == "drag_line":
                pyautogui.mouseUp()

        elif t == "input_text":
            pyautogui.typewrite(d.get("text", ""), interval=d.get("delay", 0.05))

        elif t == "key_press":
            pyautogui.press(d.get("key", ""))

        elif t == "wait":
            time.sleep(d.get("duration", 1.0))

        elif t == "condition_color":
            x, y = int(d["x"]), int(d["y"])
            target = tuple(d.get("color", [255, 0, 0]))
            tolerance = d.get("tolerance", 30)
            px = pyautogui.pixel(x, y)
            match = all(abs(px[i] - target[i]) <= tolerance for i in range(3))
            self.on_log(f"Pixel ({x},{y})={px} cible={target} {'OK' if match else 'NON'}")
            if match:
                for sub in [Action.from_dict(a) for a in d.get("then", [])]:
                    if not self.running: return
                    self._execute(sub)


# ─────────────────────────────────────────────
#  APPLICATION PRINCIPALE
# ─────────────────────────────────────────────

class MouseFlowApp:
    CANVAS_W = 900
    CANVAS_H = 560

    def __init__(self, root):
        self.root = root
        self.root.title("MouseFlow v2.0 - Automatisation souris")
        self.root.configure(bg="#0d1117")
        self.root.geometry("1340x720")
        self.root.minsize(1000, 600)

        # État
        self.actions = []
        self.selected_tool = tk.StringVar(value="move")
        self.line_points = []
        self.current_speed = tk.DoubleVar(value=500)
        self.engine = None
        self.live_pos = tk.StringVar(value="Souris : -")
        self.bg_active = tk.BooleanVar(value=False)
        self.bg_photo = None
        self.bg_image_id = None
        self.emergency_key = tk.StringVar(value="F8")
        self._last_custom_key = "F8"
        self.repeat_var = tk.IntVar(value=1)
        self.cbv = tk.StringVar(value="left")

        # Dimensions écran réel
        self.screen_w, self.screen_h = pyautogui.size()
        self.scale_x = self.CANVAS_W / self.screen_w
        self.scale_y = self.CANVAS_H / self.screen_h

        self.C = {
            "bg":     "#0d1117", "panel":  "#161b22",
            "border": "#30363d", "accent": "#58a6ff",
            "green":  "#3fb950", "red":    "#f85149",
            "orange": "#d29922", "text":   "#e6edf3",
            "muted":  "#8b949e",
        }

        self._build_ui()
        self._bind_keys()
        self._track_mouse()

    # ── COORDONNÉES ───────────────────────────

    def _tc(self, rx, ry):
        """Écran réel → Canvas"""
        return rx * self.scale_x, ry * self.scale_y

    def _tr(self, cx, cy):
        """Canvas → Écran réel"""
        return cx / self.scale_x, cy / self.scale_y

    # ── TOUCHES D'URGENCE ─────────────────────

    def _bind_keys(self):
        self.root.bind("<Escape>", lambda e: self._emergency_stop())
        self._bind_custom_key()

    def _bind_custom_key(self):
        try:
            self.root.unbind(f"<{self._last_custom_key}>")
        except:
            pass
        key = self.emergency_key.get()
        self._last_custom_key = key
        try:
            self.root.bind(f"<{key}>", lambda e: self._emergency_stop())
        except:
            pass

    def _emergency_stop(self):
        if self.engine:
            self.engine.stop()
        self.log("ARRET D'URGENCE !")

    def _set_custom_key(self):
        d = tk.Toplevel(self.root)
        d.title("Touche d'urgence")
        d.configure(bg=self.C["panel"])
        d.geometry("340x160")
        d.grab_set()

        tk.Label(d, text="Appuie sur la touche voulue :",
                 font=("Consolas", 11), fg=self.C["text"],
                 bg=self.C["panel"]).pack(pady=16)

        kv = tk.StringVar(value=self.emergency_key.get())
        e = tk.Entry(d, textvariable=kv, font=("Consolas", 14),
                     bg=self.C["bg"], fg=self.C["accent"],
                     insertbackground=self.C["text"], width=12, justify="center")
        e.pack(pady=4)
        e.focus()

        def on_key(evt):
            kv.set(evt.keysym)
            return "break"
        e.bind("<Key>", on_key)

        def ok():
            self.emergency_key.set(kv.get())
            self._bind_custom_key()
            self.log(f"Touche urgence : {kv.get()}")
            d.destroy()

        tk.Button(d, text="Confirmer", command=ok,
                  font=("Consolas", 10, "bold"), fg="#000",
                  bg=self.C["green"], relief="flat", pady=6
                  ).pack(pady=12, padx=20, fill="x")

    # ── FOND ÉCRAN ────────────────────────────

    def _toggle_bg(self):
        if self.bg_active.get():
            self._capture_screen()
        else:
            self._clear_bg()

    def _capture_screen(self):
        self.log("Capture ecran dans 0.5s...")
        self.root.iconify()
        self.root.after(500, self._do_capture)

    def _do_capture(self):
        try:
            shot = ImageGrab.grab()
            shot = shot.resize((self.CANVAS_W, self.CANVAS_H), Image.LANCZOS)
            self.bg_photo = ImageTk.PhotoImage(shot)
            if self.bg_image_id:
                self.canvas.delete(self.bg_image_id)
            self.bg_image_id = self.canvas.create_image(
                0, 0, anchor="nw", image=self.bg_photo, tags="bg")
            self.canvas.tag_lower("bg")
            self.canvas.tag_raise("grid")
            self.canvas.tag_raise("drawing")
            self.canvas.tag_raise("dot")
            self.root.deiconify()
            self.log("Fond ecran actif - place tes points avec precision !")
        except Exception as ex:
            self.root.deiconify()
            self.log(f"Erreur capture : {ex}")
            self.bg_active.set(False)

    def _clear_bg(self):
        if self.bg_image_id:
            self.canvas.delete(self.bg_image_id)
            self.bg_image_id = None
        self.bg_photo = None
        self.log("Fond ecran desactive")

    def _redraw_grid(self):
        self.canvas.delete("grid")
        for x in range(0, self.CANVAS_W, 90):
            self.canvas.create_line(x, 0, x, self.CANVAS_H,
                                     fill="#1a1f28", width=1, tags="grid")
        for y in range(0, self.CANVAS_H, 56):
            self.canvas.create_line(0, y, self.CANVAS_W, y,
                                     fill="#1a1f28", width=1, tags="grid")
        self.canvas.create_text(4, 4, text="0,0", fill="#3d444d",
                                  font=("Consolas", 7), anchor="nw", tags="grid")
        self.canvas.create_text(self.CANVAS_W-4, self.CANVAS_H-4,
                                  text=f"{self.screen_w},{self.screen_h}",
                                  fill="#3d444d", font=("Consolas", 7),
                                  anchor="se", tags="grid")

    # ── CONSTRUCTION UI ───────────────────────

    def _section(self, parent, title):
        tk.Label(parent, text=title, font=("Consolas", 9, "bold"),
                 fg=self.C["muted"], bg=self.C["panel"]
                 ).pack(anchor="w", padx=10, pady=(10,2))
        tk.Frame(parent, bg=self.C["border"], height=1
                 ).pack(fill="x", padx=8, pady=(0,5))

    def _build_ui(self):
        C = self.C
        top = tk.Frame(self.root, bg=C["panel"], height=48)
        top.pack(fill="x")
        tk.Label(top, text="MouseFlow v2", font=("Consolas", 16, "bold"),
                 fg=C["accent"], bg=C["panel"]).pack(side="left", padx=16, pady=8)
        tk.Label(top, textvariable=self.live_pos, font=("Consolas", 10),
                 fg=C["muted"], bg=C["panel"]).pack(side="right", padx=16)

        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=C["panel"], width=230)
        left.pack(side="left", fill="y", padx=(8,0), pady=8)
        left.pack_propagate(False)
        self._build_tools(left)

        center = tk.Frame(body, bg=C["bg"])
        center.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        self._build_canvas(center)

        right = tk.Frame(body, bg=C["panel"], width=240)
        right.pack(side="right", fill="y", padx=(0,8), pady=8)
        right.pack_propagate(False)
        self._build_sequence(right)

        self._build_bottom()

    def _build_tools(self, p):
        C = self.C
        tk.Label(p, text="OUTILS", font=("Consolas", 10, "bold"),
                 fg=C["accent"], bg=C["panel"]).pack(pady=(14,4))

        for label, val in [
            ("Deplacement",     "move"),
            ("Clic",            "click"),
            ("Ligne (glisser)", "drag_line"),
            ("Ligne (clics)",   "line"),
            ("Texte / Touche",  "input"),
            ("Attente",         "wait"),
            ("Condition couleur","condition"),
        ]:
            tk.Radiobutton(
                p, text=label, variable=self.selected_tool, value=val,
                font=("Consolas", 10), fg=C["text"], bg=C["panel"],
                selectcolor=C["bg"], activebackground=C["panel"],
                activeforeground=C["accent"], indicatoron=False,
                relief="flat", padx=10, pady=6, anchor="w", width=20,
                command=lambda: self.line_points.clear()
            ).pack(fill="x", padx=8, pady=2)

        self._section(p, "VITESSE (px/s)")
        sf = tk.Frame(p, bg=C["panel"]); sf.pack(fill="x", padx=10)
        self.spd_lbl = tk.Label(sf, text="500 px/s", font=("Consolas", 10),
                                 fg=C["accent"], bg=C["panel"])
        self.spd_lbl.pack(side="right")
        tk.Scale(sf, from_=50, to=3000, orient="horizontal",
                 variable=self.current_speed, bg=C["panel"], fg=C["text"],
                 troughcolor=C["border"], highlightthickness=0, showvalue=False,
                 command=lambda v: self.spd_lbl.config(text=f"{int(float(v))} px/s")
                 ).pack(side="left", fill="x", expand=True)

        self._section(p, "BOUTON CLIC")
        bf = tk.Frame(p, bg=C["panel"]); bf.pack(fill="x", padx=8)
        for lbl, val in [("Gauche","left"),("Droit","right"),("Double","double")]:
            tk.Radiobutton(bf, text=lbl, variable=self.cbv, value=val,
                           font=("Consolas", 9), fg=C["text"], bg=C["panel"],
                           selectcolor=C["bg"], activebackground=C["panel"]
                           ).pack(side="left")

        self._section(p, "REPETITION")
        rf = tk.Frame(p, bg=C["panel"]); rf.pack(fill="x", padx=10)
        tk.Label(rf, text="x", font=("Consolas", 9), fg=C["muted"],
                 bg=C["panel"]).pack(side="left")
        tk.Spinbox(rf, from_=1, to=999, textvariable=self.repeat_var,
                   width=5, font=("Consolas", 10), bg=C["bg"], fg=C["text"],
                   buttonbackground=C["border"], insertbackground=C["text"]
                   ).pack(side="left", padx=4)

        self._section(p, "FOND ECRAN REEL")
        tk.Checkbutton(p, text="Afficher mon ecran en fond",
                       variable=self.bg_active, command=self._toggle_bg,
                       font=("Consolas", 9), fg=C["text"], bg=C["panel"],
                       selectcolor=C["bg"], activebackground=C["panel"]
                       ).pack(anchor="w", padx=12, pady=2)
        tk.Button(p, text="Rafraichir capture",
                  font=("Consolas", 9), fg=C["text"], bg=C["border"],
                  relief="flat", padx=8, pady=3,
                  command=lambda: [self.bg_active.set(True), self._capture_screen()]
                  ).pack(fill="x", padx=8, pady=2)

        self._section(p, "TOUCHES D'URGENCE")
        tk.Label(p, text="Echap  = stop execution",
                 font=("Consolas", 8), fg=C["green"], bg=C["panel"]
                 ).pack(anchor="w", padx=12)
        tk.Label(p, text="Alt+F4 = quitter MouseFlow",
                 font=("Consolas", 8), fg=C["green"], bg=C["panel"]
                 ).pack(anchor="w", padx=12)
        kf = tk.Frame(p, bg=C["panel"]); kf.pack(fill="x", padx=8, pady=4)
        tk.Label(kf, text="Perso:", font=("Consolas", 8),
                 fg=C["muted"], bg=C["panel"]).pack(side="left")
        tk.Label(kf, textvariable=self.emergency_key,
                 font=("Consolas", 9, "bold"), fg=C["orange"],
                 bg=C["panel"]).pack(side="left", padx=4)
        tk.Button(kf, text="Changer", font=("Consolas", 8),
                  fg=C["text"], bg=C["border"], relief="flat", padx=4,
                  command=self._set_custom_key).pack(side="left")

    def _build_canvas(self, p):
        C = self.C
        tk.Label(p, text="Canvas — representation de ton ecran  |  Clic gauche = ajouter  |  Clic droit = valider ligne",
                 font=("Consolas", 9), fg=C["muted"], bg=C["bg"]).pack(anchor="w")

        cf = tk.Frame(p, bg=C["border"], padx=1, pady=1)
        cf.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(cf, width=self.CANVAS_W, height=self.CANVAS_H,
                                 bg="#010409", cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self._redraw_grid()

        # Point souris — toujours au-dessus de tout
        self.live_dot = self.canvas.create_oval(
            -10, -10, -4, -4,
            fill=self.C["green"], outline="white", width=1, tags="dot"
        )

        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>",   self._on_motion)
        self.canvas.bind("<Button-3>", self._on_rclick)

    def _build_sequence(self, p):
        C = self.C
        tk.Label(p, text="SEQUENCE", font=("Consolas", 10, "bold"),
                 fg=C["accent"], bg=C["panel"]).pack(pady=(14,4))

        f = tk.Frame(p, bg=C["panel"]); f.pack(fill="both", expand=True, padx=6)
        sb = tk.Scrollbar(f); sb.pack(side="right", fill="y")
        self.seq_list = tk.Listbox(f, yscrollcommand=sb.set,
                                    bg=C["bg"], fg=C["text"],
                                    selectbackground=C["accent"],
                                    font=("Consolas", 9), relief="flat", bd=0,
                                    selectforeground="#000", activestyle="none")
        self.seq_list.pack(fill="both", expand=True)
        sb.config(command=self.seq_list.yview)

        bf = tk.Frame(p, bg=C["panel"]); bf.pack(fill="x", padx=6, pady=4)
        for txt, cmd, col in [
            ("Monter",    self._seq_up,     C["border"]),
            ("Descendre", self._seq_down,   C["border"]),
            ("Editer",    self._seq_edit,   C["orange"]),
            ("Supprimer", self._seq_delete, C["red"]),
        ]:
            tk.Button(bf, text=txt, command=cmd, font=("Consolas", 9),
                      fg=C["text"], bg=col, relief="flat", padx=4, pady=4
                      ).pack(fill="x", pady=1)

    def _build_bottom(self):
        C = self.C
        bar = tk.Frame(self.root, bg=C["panel"], height=52)
        bar.pack(fill="x", padx=8, pady=(0,8))

        for txt, cmd, bg in [
            ("EXECUTER",    self._execute,  C["green"]),
            ("STOP",        self._stop,     C["red"]),
            ("Sauvegarder", self._save,     C["border"]),
            ("Charger",     self._load,     C["border"]),
            ("Tout effacer",self._clear_all,C["border"]),
        ]:
            tk.Button(bar, text=txt, command=cmd,
                      font=("Consolas", 10, "bold"), fg=C["text"], bg=bg,
                      relief="flat", padx=14, pady=8).pack(side="left", padx=4, pady=8)

        self.log_var = tk.StringVar(value="Pret  |  Echap = stop  |  Alt+F4 = quitter")
        tk.Label(bar, textvariable=self.log_var, font=("Consolas", 9),
                 fg=C["muted"], bg=C["panel"], anchor="w"
                 ).pack(side="left", padx=12, fill="x", expand=True)

    # ── EVENTS CANVAS ─────────────────────────

    def _on_motion(self, e):
        rx, ry = self._tr(e.x, e.y)
        self.live_pos.set(f"Canvas ({e.x},{e.y})  ->  Ecran ({int(rx)}, {int(ry)})")
        if self.selected_tool.get() in ("line", "drag_line") and self.line_points:
            self.canvas.delete("preview")
            lx, ly = self._tc(*self.line_points[-1])
            self.canvas.create_line(lx, ly, e.x, e.y,
                                     fill="#58a6ff", dash=(4,4),
                                     tags=("preview","drawing"))

    def _on_click(self, e):
        t = self.selected_tool.get()
        rx, ry = self._tr(e.x, e.y)

        if t == "move":
            self._add_action(Action("move", x=rx, y=ry, duration=0.3))
            self._dot(e.x, e.y, "#58a6ff", "MOVE")

        elif t == "click":
            btn = self.cbv.get()
            cl = 2 if btn == "double" else 1
            rb = "left" if btn == "double" else btn
            self._add_action(Action("click", x=rx, y=ry, button=rb,
                                    clicks=cl, speed=self.current_speed.get()/1000))
            self._dot(e.x, e.y, "#f85149", "CLIC")

        elif t in ("line", "drag_line"):
            self.line_points.append((rx, ry))
            cx, cy = self._tc(rx, ry)
            self._dot(cx, cy, "#3fb950", size=4)
            if len(self.line_points) > 1:
                p1 = self._tc(*self.line_points[-2])
                p2 = self._tc(*self.line_points[-1])
                self.canvas.create_line(*p1, *p2, fill="#3fb950",
                                         width=2, tags="drawing")

        elif t == "input":
            self._input_dialog()

        elif t == "wait":
            dur = simpledialog.askfloat("Attente", "Duree (secondes) :",
                                         minvalue=0.1, maxvalue=60.0,
                                         initialvalue=1.0, parent=self.root)
            if dur:
                self._add_action(Action("wait", duration=dur))
                self._dot(e.x, e.y, "#d29922", f"WAIT {dur}s")

        elif t == "condition":
            self._condition_dialog(rx, ry, e.x, e.y)

    def _on_rclick(self, e):
        t = self.selected_tool.get()
        if t in ("line", "drag_line") and len(self.line_points) >= 2:
            self.canvas.delete("preview")
            self._add_action(Action(t, points=list(self.line_points),
                                    speed=self.current_speed.get()))
            self.log(f"Ligne ajoutee : {len(self.line_points)} points")
            self.line_points = []
        else:
            self.line_points = []
            self.canvas.delete("preview")

    # ── DESSIN ────────────────────────────────

    def _dot(self, cx, cy, color="#58a6ff", label=None, size=7):
        r = size
        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                  fill=color, outline="white",
                                  width=1, tags="drawing")
        if label:
            self.canvas.create_text(cx+10, cy, text=label, fill=color,
                                     font=("Consolas", 7), anchor="w",
                                     tags="drawing")
        self.canvas.tag_raise("dot")

    # ── DIALOGUES ─────────────────────────────

    def _input_dialog(self):
        d = tk.Toplevel(self.root)
        d.title("Texte / Touche")
        d.configure(bg=self.C["panel"])
        d.geometry("360x210")
        d.grab_set()

        tv = tk.StringVar(value="text")
        for lbl, val in [("Ecrire un texte","text"),("Appuyer une touche","key")]:
            tk.Radiobutton(d, text=lbl, variable=tv, value=val,
                           font=("Consolas", 10), fg=self.C["text"],
                           bg=self.C["panel"], selectcolor=self.C["bg"],
                           activebackground=self.C["panel"]
                           ).pack(anchor="w", padx=20, pady=5)

        tk.Label(d, text="Contenu (ex: bonjour  ou  ctrl+c  ou  f5) :",
                 font=("Consolas", 9), fg=self.C["muted"],
                 bg=self.C["panel"]).pack()
        entry = tk.Entry(d, font=("Consolas", 12), bg=self.C["bg"],
                         fg=self.C["text"], insertbackground=self.C["text"],
                         width=28)
        entry.pack(padx=20, ipady=4, pady=4)
        entry.focus()

        def ok():
            v = entry.get().strip()
            if not v: return
            if tv.get() == "text":
                self._add_action(Action("input_text", text=v, delay=0.05))
            else:
                self._add_action(Action("key_press", key=v))
            d.destroy()

        tk.Button(d, text="Ajouter", command=ok,
                  font=("Consolas", 10, "bold"), fg="#000",
                  bg=self.C["green"], relief="flat", pady=6
                  ).pack(pady=8, padx=20, fill="x")
        d.bind("<Return>", lambda e: ok())

    def _condition_dialog(self, rx, ry, cx, cy):
        d = tk.Toplevel(self.root)
        d.title("Condition couleur")
        d.configure(bg=self.C["panel"])
        d.geometry("380x270")
        d.grab_set()

        tk.Label(d, text=f"Position : ({int(rx)}, {int(ry)})",
                 font=("Consolas", 10), fg=self.C["accent"],
                 bg=self.C["panel"]).pack(pady=(12,4))

        cv = tk.StringVar(value="#ff0000")
        pf = tk.Frame(d, bg=self.C["panel"]); pf.pack()
        cp = tk.Label(pf, bg="#ff0000", width=6, height=2); cp.pack(side="left", padx=8)

        def pick():
            c = colorchooser.askcolor(color=cv.get(), parent=d)
            if c[1]: cv.set(c[1]); cp.config(bg=c[1])

        tk.Button(pf, text="Choisir couleur", command=pick,
                  font=("Consolas", 9), fg=self.C["text"],
                  bg=self.C["border"], relief="flat", padx=8).pack(side="left")

        tk.Label(d, text="Tolerance (0=exact, 100=souple) :",
                 font=("Consolas", 9), fg=self.C["muted"],
                 bg=self.C["panel"]).pack(pady=(8,2))
        tv = tk.IntVar(value=30)
        tk.Scale(d, from_=0, to=100, orient="horizontal", variable=tv,
                 bg=self.C["panel"], fg=self.C["text"],
                 troughcolor=self.C["border"], highlightthickness=0
                 ).pack(fill="x", padx=20)

        def ok():
            h = cv.get().lstrip("#")
            rgb = [int(h[i:i+2], 16) for i in (0,2,4)]
            then = [Action("click", x=rx, y=ry, button="left",
                           clicks=1, speed=0.1).to_dict()]
            self._add_action(Action("condition_color", x=rx, y=ry,
                                    color=rgb, tolerance=tv.get(), then=then))
            self._dot(cx, cy, "#d29922", "COND")
            d.destroy()

        tk.Button(d, text="Ajouter", command=ok,
                  font=("Consolas", 10, "bold"), fg="#000",
                  bg=self.C["green"], relief="flat", pady=6
                  ).pack(pady=10, padx=20, fill="x")

    # ── SÉQUENCE ──────────────────────────────

    def _add_action(self, action):
        self.actions.append(action)
        self._refresh_seq()

    def _refresh_seq(self):
        self.seq_list.delete(0, tk.END)
        icons = {
            "move":"->", "click":"CLIC", "line":"LINE",
            "drag_line":"DRAG", "input_text":"TXT", "key_press":"KEY",
            "wait":"WAIT", "condition_color":"IF"
        }
        for i, a in enumerate(self.actions):
            ic = icons.get(a.type, "?")
            d = a.data
            if a.type in ("move","click"):
                det = f"({int(d.get('x',0))},{int(d.get('y',0))})"
            elif a.type in ("line","drag_line"):
                det = f"{len(d.get('points',[]))}pts {d.get('speed',500):.0f}px/s"
            elif a.type == "input_text":
                det = f"'{d.get('text','')[:16]}'"
            elif a.type == "key_press":
                det = d.get("key","")
            elif a.type == "wait":
                det = f"{d.get('duration',1)}s"
            elif a.type == "condition_color":
                det = f"RGB{tuple(d.get('color',[]))} tol={d.get('tolerance',30)}"
            else:
                det = ""
            self.seq_list.insert(tk.END, f"  {i+1:02d}  {ic}  {a.type}  {det}")

    def _seq_up(self):
        s = self.seq_list.curselection()
        if s and s[0] > 0:
            i = s[0]
            self.actions[i-1], self.actions[i] = self.actions[i], self.actions[i-1]
            self._refresh_seq(); self.seq_list.selection_set(i-1)

    def _seq_down(self):
        s = self.seq_list.curselection()
        if s and s[0] < len(self.actions)-1:
            i = s[0]
            self.actions[i], self.actions[i+1] = self.actions[i+1], self.actions[i]
            self._refresh_seq(); self.seq_list.selection_set(i+1)

    def _seq_delete(self):
        s = self.seq_list.curselection()
        if s: self.actions.pop(s[0]); self._refresh_seq()

    def _seq_edit(self):
        s = self.seq_list.curselection()
        if not s: return
        a = self.actions[s[0]]
        if a.type in ("line","drag_line"):
            v = simpledialog.askinteger("Vitesse","px/s :",
                                         initialvalue=int(a.data.get("speed",500)),
                                         minvalue=10, maxvalue=5000, parent=self.root)
            if v: a.data["speed"] = v; self._refresh_seq()
        elif a.type == "wait":
            v = simpledialog.askfloat("Attente","Duree (s) :",
                                       initialvalue=a.data.get("duration",1),
                                       minvalue=0.1, maxvalue=60, parent=self.root)
            if v: a.data["duration"] = v; self._refresh_seq()
        elif a.type in ("move","click"):
            x = simpledialog.askinteger("X","Position X :",
                                         initialvalue=int(a.data.get("x",0)),
                                         parent=self.root)
            y = simpledialog.askinteger("Y","Position Y :",
                                         initialvalue=int(a.data.get("y",0)),
                                         parent=self.root)
            if x is not None and y is not None:
                a.data["x"], a.data["y"] = x, y; self._refresh_seq()

    # ── EXÉCUTION ─────────────────────────────

    def _execute(self):
        if not self.actions:
            messagebox.showinfo("Vide","Aucune action !")
            return
        if not messagebox.askyesno("Confirmer",
                f"Lancer {len(self.actions)} action(s) x{self.repeat_var.get()} ?\n\n"
                f"Arret d'urgence :\n"
                f"  Echap\n"
                f"  {self.emergency_key.get()}\n"
                f"  Coin haut-gauche de l'ecran"):
            return
        self.engine = ExecutionEngine(
            self.actions * self.repeat_var.get(), self.log, self._on_done)
        self.log("Demarrage dans 2 secondes...")
        self.root.after(2000, self.engine.start)

    def _stop(self):
        if self.engine: self.engine.stop()
        self.log("Arrete.")

    def _on_done(self):
        self.log("Sequence terminee.")

    def _save(self):
        from tkinter.filedialog import asksaveasfilename
        p = asksaveasfilename(defaultextension=".json",
                               filetypes=[("MouseFlow","*.json")],
                               title="Sauvegarder")
        if p:
            with open(p, "w") as f:
                json.dump([a.to_dict() for a in self.actions], f, indent=2)
            self.log(f"Sauvegarde : {os.path.basename(p)}")

    def _load(self):
        from tkinter.filedialog import askopenfilename
        p = askopenfilename(filetypes=[("MouseFlow","*.json")], title="Charger")
        if p:
            with open(p) as f:
                self.actions = [Action.from_dict(d) for d in json.load(f)]
            self._refresh_seq()
            self.log(f"Charge : {len(self.actions)} actions")

    def _clear_all(self):
        if messagebox.askyesno("Effacer","Supprimer toutes les actions ?"):
            self.actions.clear()
            self._refresh_seq()
            self.canvas.delete("drawing")
            self.canvas.delete("preview")
            self.log("Tout efface.")

    # ── TRACKING SOURIS ───────────────────────

    def _track_mouse(self):
        """
        Affiche le point vert à la position RÉELLE de la souris sur l'écran,
        convertie en coordonnées canvas. Ce point suit donc la vraie souris
        même quand elle est hors de la fenêtre MouseFlow.
        """
        try:
            rx, ry = pyautogui.position()
            cx, cy = self._tc(rx, ry)
            r = 6
            self.canvas.coords(self.live_dot, cx-r, cy-r, cx+r, cy+r)
            self.canvas.tag_raise("dot")
        except:
            pass
        self.root.after(50, self._track_mouse)

    def log(self, msg):
        self.log_var.set(msg)
        print(msg)


# ─────────────────────────────────────────────
#  POINT D'ENTRÉE
# ─────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    app = MouseFlowApp(root)
    root.mainloop()
