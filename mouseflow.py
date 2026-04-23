"""
MouseFlow v3.0
- Panneaux redimensionnables avec limites min/max
- Panneau outils collapse (icones seules)
- Panneau sequence collapse
- Selection auto derniere action
- Clic sur action = highlight canvas
- Edition complete de toutes les actions
- Clics configurables avec vitesse individuelle
- Point vert = position exacte ecran
"""

import tkinter as tk
from tkinter import messagebox, colorchooser, simpledialog
import threading, time, json, math, pyautogui, os
from PIL import Image, ImageTk, ImageGrab

pyautogui.FAILSAFE = True

C = {
    "bg":"#0d1117","panel":"#161b22","panel2":"#1c2128",
    "border":"#30363d","accent":"#58a6ff","green":"#3fb950",
    "red":"#f85149","orange":"#d29922","purple":"#bc8cff",
    "text":"#e6edf3","muted":"#8b949e","sel":"#1f3550",
}

TOOLS = [
    ("->","Deplacement","move"),
    ("@","Clic","click"),
    ("~","Ligne glisser","drag_line"),
    ("*","Ligne clics","line"),
    ("K","Texte/Touche","input"),
    ("T","Attente","wait"),
    ("?","Condition couleur","condition"),
]

CLICK_TYPES = [
    ("Gauche","left",1),
    ("Droit","right",1),
    ("Double gauche","left",2),
    ("Double droit","right",2),
    ("Milieu","middle",1),
    ("Molette haut","scrollUp",1),
    ("Molette bas","scrollDown",1),
]

ACTION_ICONS = {
    "move":"->","click":"@","line":"*","drag_line":"~",
    "input_text":"K","key_press":"[K]","wait":"T","condition_color":"?",
}


class Action:
    def __init__(self, action_type, **kwargs):
        self.type = action_type
        self.data = kwargs

    def to_dict(self):
        return {"type": self.type, "data": self.data}

    @staticmethod
    def from_dict(d):
        return Action(d["type"], **d["data"])

    def label(self):
        d = self.data
        ic = ACTION_ICONS.get(self.type, "?")
        if self.type == "move":
            return f"{ic} MOVE ({int(d.get('x',0))},{int(d.get('y',0))}) {d.get('move_speed',0.3):.2f}s"
        elif self.type == "click":
            ct = d.get("click_type","Gauche")
            return f"{ic} {ct} ({int(d.get('x',0))},{int(d.get('y',0))}) mv={d.get('move_speed',0.3):.2f}s"
        elif self.type in ("line","drag_line"):
            n = len(d.get("points",[]))
            return f"{ic} {self.type.upper()} {n}pts {d.get('speed',500):.0f}px/s"
        elif self.type == "input_text":
            return f"{ic} TXT '{d.get('text','')[:14]}'"
        elif self.type == "key_press":
            return f"{ic} KEY {d.get('key','')}"
        elif self.type == "wait":
            return f"{ic} WAIT {d.get('duration',1)}s"
        elif self.type == "condition_color":
            return f"{ic} IF ({int(d.get('x',0))},{int(d.get('y',0))})"
        return f"{ic} {self.type}"


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
            for i, a in enumerate(self.actions):
                if not self.running: break
                self.on_log(f"[{i+1}/{len(self.actions)}] {a.label()}")
                self._exec(a)
                time.sleep(0.03)
        except Exception as e:
            self.on_log(f"Erreur: {e}")
        finally:
            self.running = False
            self.on_done()

    def _exec(self, a):
        d = a.data
        t = a.type
        if t == "move":
            pyautogui.moveTo(int(d["x"]), int(d["y"]), duration=d.get("move_speed",0.3))
        elif t == "click":
            ct = d.get("click_type","Gauche")
            pyautogui.moveTo(int(d["x"]), int(d["y"]), duration=d.get("move_speed",0.3))
            if ct == "Molette haut":
                pyautogui.scroll(3)
            elif ct == "Molette bas":
                pyautogui.scroll(-3)
            else:
                pyautogui.click(button=d.get("button","left"),
                                clicks=d.get("clicks",1),
                                interval=d.get("click_interval",0.0))
        elif t in ("line","drag_line"):
            pts = d.get("points",[])
            spd = d.get("speed",500)
            if t == "drag_line" and pts:
                pyautogui.moveTo(int(pts[0][0]),int(pts[0][1]),duration=0.15)
                pyautogui.mouseDown()
            for i in range(len(pts)-1):
                if not self.running:
                    if t == "drag_line": pyautogui.mouseUp()
                    return
                p1,p2 = pts[i],pts[i+1]
                dist = math.hypot(p2[0]-p1[0],p2[1]-p1[1])
                pyautogui.moveTo(int(p2[0]),int(p2[1]),
                                 duration=dist/spd if spd>0 else 0.01)
            if t == "drag_line": pyautogui.mouseUp()
        elif t == "input_text":
            pyautogui.typewrite(d.get("text",""), interval=d.get("delay",0.05))
        elif t == "key_press":
            pyautogui.press(d.get("key",""))
        elif t == "wait":
            time.sleep(d.get("duration",1.0))
        elif t == "condition_color":
            x,y = int(d["x"]),int(d["y"])
            target = tuple(d.get("color",[255,0,0]))
            tol = d.get("tolerance",30)
            px = pyautogui.pixel(x,y)
            if all(abs(px[i]-target[i])<=tol for i in range(3)):
                for sub in [Action.from_dict(x) for x in d.get("then",[])]:
                    if not self.running: return
                    self._exec(sub)


class ResizablePanel:
    def __init__(self, parent, side, min_w, max_w, init_w, bg):
        self.parent = parent
        self.side = side
        self.min_w = min_w
        self.max_w = max_w
        self.width = init_w
        self._dragging = False

        self.frame = tk.Frame(parent, bg=bg, width=init_w)
        self.frame.pack_propagate(False)

        handle_side = "right" if side == "left" else "left"
        self.handle = tk.Frame(self.frame, bg=C["border"], width=5,
                                cursor="sb_h_double_arrow")
        self.handle.pack(side=handle_side, fill="y")

        self.content = tk.Frame(self.frame, bg=bg)
        self.content.pack(fill="both", expand=True)

        self.handle.bind("<ButtonPress-1>", self._start)
        self.handle.bind("<B1-Motion>", self._drag)
        self.handle.bind("<ButtonRelease-1>", self._stop)

    def pack(self, **kw):
        self.frame.pack(**kw)

    def _start(self, e):
        self._dragging = True
        self._sx = e.x_root
        self._sw = self.width

    def _drag(self, e):
        if not self._dragging: return
        dx = e.x_root - self._sx
        if self.side == "right": dx = -dx
        nw = max(self.min_w, min(self.max_w, self._sw + dx))
        self.width = nw
        self.frame.config(width=nw)

    def _stop(self, e):
        self._dragging = False


class EditDialog:
    def __init__(self, parent, action, on_save):
        self.action = action
        self.on_save = on_save
        self.d = tk.Toplevel(parent)
        self.d.title(f"Editer : {action.type}")
        self.d.configure(bg=C["panel"])
        self.d.grab_set()
        self.d.resizable(False, False)

        t = action.type
        if t in ("move","click"): self._move_click()
        elif t in ("line","drag_line"): self._line()
        elif t == "input_text": self._text()
        elif t == "key_press": self._key()
        elif t == "wait": self._wait()
        elif t == "condition_color": self._condition()
        else:
            tk.Label(self.d, text="Rien a configurer.",
                     font=("Consolas",10), fg=C["text"], bg=C["panel"]).pack(padx=20,pady=20)
            self._ok()

        self.d.update_idletasks()
        w,h = self.d.winfo_reqwidth(), self.d.winfo_reqheight()
        px = parent.winfo_rootx()+(parent.winfo_width()-w)//2
        py = parent.winfo_rooty()+(parent.winfo_height()-h)//2
        self.d.geometry(f"+{px}+{py}")

    def _lbl(self, txt):
        tk.Label(self.d, text=txt, font=("Consolas",9), fg=C["muted"],
                 bg=C["panel"], anchor="w").pack(fill="x", padx=16, pady=(7,1))

    def _ent(self, var, w=22):
        e = tk.Entry(self.d, textvariable=var, font=("Consolas",11),
                     bg=C["bg"], fg=C["text"], insertbackground=C["text"],
                     relief="flat", width=w)
        e.pack(padx=16, ipady=3, pady=(0,2), fill="x")
        return e

    def _slider(self, var, lo, hi, res, fmt, parent=None):
        p = parent or self.d
        f = tk.Frame(p, bg=C["panel"]); f.pack(fill="x", padx=16, pady=2)
        lbl = tk.Label(f, text=fmt(var.get()), font=("Consolas",9),
                       fg=C["accent"], bg=C["panel"])
        lbl.pack(side="right")
        tk.Scale(f, from_=lo, to=hi, resolution=res, orient="horizontal",
                 variable=var, bg=C["panel"], fg=C["text"],
                 troughcolor=C["border"], highlightthickness=0, showvalue=False,
                 command=lambda v: lbl.config(text=fmt(float(v)))
                 ).pack(side="left", fill="x", expand=True)
        return f

    def _ok(self, cmd=None):
        tk.Button(self.d, text="Sauvegarder", command=cmd or self.d.destroy,
                  font=("Consolas",10,"bold"), fg="#000",
                  bg=C["green"], relief="flat", pady=7
                  ).pack(fill="x", padx=16, pady=12)

    def _move_click(self):
        a = self.action; d = a.data
        h = 500 if a.type=="click" else 280
        self.d.geometry(f"400x{h}")

        self._lbl("Position X (ecran) :")
        self.xv = tk.StringVar(value=str(int(d.get("x",0))))
        self._ent(self.xv)

        self._lbl("Position Y (ecran) :")
        self.yv = tk.StringVar(value=str(int(d.get("y",0))))
        self._ent(self.yv)

        self._lbl("Vitesse de deplacement vers la position (s) :")
        self.sv = tk.DoubleVar(value=d.get("move_speed",d.get("duration",0.3)))
        self._slider(self.sv, 0.01, 3.0, 0.01, lambda v: f"{float(v):.2f}s")

        if a.type == "click":
            self._lbl("Type de clic :")
            self.ctv = tk.StringVar(value=d.get("click_type","Gauche"))
            for row in [CLICK_TYPES[:3], CLICK_TYPES[3:6], CLICK_TYPES[6:]]:
                rf = tk.Frame(self.d, bg=C["panel"]); rf.pack(fill="x", padx=12, pady=1)
                for lbl_t, btn, cl in row:
                    tk.Radiobutton(rf, text=lbl_t, variable=self.ctv, value=lbl_t,
                                   font=("Consolas",9), fg=C["text"], bg=C["panel"],
                                   selectcolor=C["bg"], activebackground=C["panel"]
                                   ).pack(side="left", padx=6)

            self._lbl("Intervalle entre clics (s) :")
            self.iv = tk.DoubleVar(value=d.get("click_interval",0.0))
            self._slider(self.iv, 0.0, 2.0, 0.01, lambda v: f"{float(v):.2f}s")

        def save():
            try:
                a.data["x"] = float(self.xv.get())
                a.data["y"] = float(self.yv.get())
                a.data["move_speed"] = self.sv.get()
                if a.type == "click":
                    ct = self.ctv.get()
                    a.data["click_type"] = ct
                    a.data["click_interval"] = self.iv.get()
                    for lbl_t,btn,cl in CLICK_TYPES:
                        if lbl_t == ct:
                            a.data["button"]=btn; a.data["clicks"]=cl; break
                self.on_save(); self.d.destroy()
            except Exception as e:
                messagebox.showerror("Erreur", str(e), parent=self.d)

        self._ok(save)

    def _line(self):
        a = self.action; d = a.data
        self.d.geometry("400x200")
        self._lbl(f"Points actuels : {len(d.get('points',[]))}")
        self._lbl("Vitesse (px/s) :")
        self.sv = tk.DoubleVar(value=d.get("speed",500))
        self._slider(self.sv, 10, 5000, 10, lambda v: f"{float(v):.0f} px/s")
        def save():
            a.data["speed"] = self.sv.get()
            self.on_save(); self.d.destroy()
        self._ok(save)

    def _text(self):
        a = self.action; d = a.data
        self.d.geometry("400x240")
        self._lbl("Texte a ecrire :")
        self.tv = tk.StringVar(value=d.get("text",""))
        self._ent(self.tv)
        self._lbl("Delai entre chaque lettre (s) :")
        self.dv = tk.DoubleVar(value=d.get("delay",0.05))
        self._slider(self.dv, 0.0, 0.5, 0.005, lambda v: f"{float(v):.3f}s")
        def save():
            a.data["text"] = self.tv.get()
            a.data["delay"] = self.dv.get()
            self.on_save(); self.d.destroy()
        self._ok(save)

    def _key(self):
        a = self.action
        self.d.geometry("380x190")
        self._lbl("Touche (ex: enter, ctrl+c, f5, space, tab) :")
        self.kv = tk.StringVar(value=a.data.get("key",""))
        e = self._ent(self.kv); e.focus()
        def cap(evt):
            self.kv.set(evt.keysym); return "break"
        e.bind("<Key>", cap)
        def save():
            a.data["key"] = self.kv.get()
            self.on_save(); self.d.destroy()
        self._ok(save)
        self.d.bind("<Return>", lambda e: save())

    def _wait(self):
        a = self.action
        self.d.geometry("380x180")
        self._lbl("Duree d attente (secondes) :")
        self.wv = tk.DoubleVar(value=a.data.get("duration",1.0))
        self._slider(self.wv, 0.1, 60.0, 0.1, lambda v: f"{float(v):.1f}s")
        def save():
            a.data["duration"] = self.wv.get()
            self.on_save(); self.d.destroy()
        self._ok(save)

    def _condition(self):
        a = self.action; d = a.data
        self.d.geometry("400x360")
        self._lbl("Position X :")
        self.xv = tk.StringVar(value=str(int(d.get("x",0))))
        self._ent(self.xv)
        self._lbl("Position Y :")
        self.yv = tk.StringVar(value=str(int(d.get("y",0))))
        self._ent(self.yv)
        rgb = d.get("color",[255,0,0])
        hex_c = "#{:02x}{:02x}{:02x}".format(*rgb)
        self.cv = tk.StringVar(value=hex_c)
        self._lbl("Couleur cible :")
        pf = tk.Frame(self.d, bg=C["panel"]); pf.pack(fill="x", padx=16, pady=4)
        self.cp = tk.Label(pf, bg=hex_c, width=5, height=1)
        self.cp.pack(side="left", padx=(0,8))
        def pick():
            c = colorchooser.askcolor(color=self.cv.get(), parent=self.d)
            if c[1]: self.cv.set(c[1]); self.cp.config(bg=c[1])
        tk.Button(pf, text="Choisir", command=pick, font=("Consolas",9),
                  fg=C["text"], bg=C["border"], relief="flat", padx=6).pack(side="left")
        self._lbl("Tolerance (0=exact, 100=souple) :")
        self.tov = tk.IntVar(value=d.get("tolerance",30))
        self._slider(self.tov, 0, 100, 1, lambda v: f"+/-{int(float(v))}")
        def save():
            try:
                a.data["x"] = float(self.xv.get())
                a.data["y"] = float(self.yv.get())
                h = self.cv.get().lstrip("#")
                a.data["color"] = [int(h[i:i+2],16) for i in (0,2,4)]
                a.data["tolerance"] = self.tov.get()
                self.on_save(); self.d.destroy()
            except Exception as e:
                messagebox.showerror("Erreur", str(e), parent=self.d)
        self._ok(save)


class MouseFlowApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MouseFlow v3.0")
        self.root.configure(bg=C["bg"])
        self.root.geometry("1400x760")
        self.root.minsize(900, 580)

        self.actions = []
        self.selected_tool = tk.StringVar(value="move")
        self.line_points = []
        self.current_speed = tk.DoubleVar(value=500)
        self.engine = None
        self.live_pos = tk.StringVar(value="Ecran : -")
        self.bg_active = tk.BooleanVar(value=False)
        self.bg_photo = None
        self.bg_image_id = None
        self.emergency_key = tk.StringVar(value="F8")
        self._last_custom_key = "F8"
        self.repeat_var = tk.IntVar(value=1)
        self.cbv = tk.StringVar(value="Gauche")
        self.tools_collapsed = False
        self.seq_collapsed = False
        self.log_var = tk.StringVar(value="Pret")

        self.screen_w, self.screen_h = pyautogui.size()

        self._build_ui()
        self._bind_keys()
        self._track_mouse()

    def _tc(self, rx, ry):
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        return rx * cw / self.screen_w, ry * ch / self.screen_h

    def _tr(self, cx, cy):
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        return cx * self.screen_w / cw, cy * self.screen_h / ch

    def _bind_keys(self):
        self.root.bind("<Escape>", lambda e: self._estop())
        self._bind_custom()

    def _bind_custom(self):
        try: self.root.unbind(f"<{self._last_custom_key}>")
        except: pass
        k = self.emergency_key.get()
        self._last_custom_key = k
        try: self.root.bind(f"<{k}>", lambda e: self._estop())
        except: pass

    def _estop(self):
        if self.engine: self.engine.stop()
        self.log("ARRET URGENCE")

    def _set_key(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Touche urgence")
        dlg.configure(bg=C["panel"])
        dlg.geometry("320x150")
        dlg.grab_set()
        tk.Label(dlg, text="Appuie sur la touche :",
                 font=("Consolas",11), fg=C["text"], bg=C["panel"]).pack(pady=14)
        kv = tk.StringVar(value=self.emergency_key.get())
        e = tk.Entry(dlg, textvariable=kv, font=("Consolas",13),
                     bg=C["bg"], fg=C["accent"], insertbackground=C["text"],
                     width=12, justify="center")
        e.pack(pady=4); e.focus()
        def cap(evt): kv.set(evt.keysym); return "break"
        e.bind("<Key>", cap)
        def ok():
            self.emergency_key.set(kv.get()); self._bind_custom()
            self.log(f"Touche urgence: {kv.get()}"); dlg.destroy()
        tk.Button(dlg, text="OK", command=ok, font=("Consolas",10,"bold"),
                  fg="#000", bg=C["green"], relief="flat", pady=5
                  ).pack(pady=10, padx=20, fill="x")

    def _toggle_bg(self):
        if self.bg_active.get(): self._capture()
        else: self._clear_bg()

    def _capture(self):
        self.log("Capture dans 0.5s...")
        self.root.iconify()
        self.root.after(500, self._do_capture)

    def _do_capture(self):
        try:
            cw = max(self.canvas.winfo_width(), 400)
            ch = max(self.canvas.winfo_height(), 300)
            shot = ImageGrab.grab().resize((cw,ch), Image.LANCZOS)
            self.bg_photo = ImageTk.PhotoImage(shot)
            if self.bg_image_id: self.canvas.delete(self.bg_image_id)
            self.bg_image_id = self.canvas.create_image(0,0,anchor="nw",
                image=self.bg_photo, tags="bg")
            self.canvas.tag_lower("bg")
            for t in ("grid","drawing","highlight","dot"):
                try: self.canvas.tag_raise(t)
                except: pass
            self.root.deiconify()
            self.log("Fond ecran actif !")
        except Exception as ex:
            self.root.deiconify()
            self.log(f"Erreur capture: {ex}")
            self.bg_active.set(False)

    def _clear_bg(self):
        if self.bg_image_id:
            self.canvas.delete(self.bg_image_id)
            self.bg_image_id = None
        self.bg_photo = None
        self.log("Fond desactive")

    def _redraw_grid(self):
        self.canvas.delete("grid")
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        for x in range(0, cw, 90):
            self.canvas.create_line(x,0,x,ch, fill="#1a1f28", tags="grid")
        for y in range(0, ch, 56):
            self.canvas.create_line(0,y,cw,y, fill="#1a1f28", tags="grid")
        self.canvas.create_text(4,4, text="0,0", fill="#3d444d",
            font=("Consolas",7), anchor="nw", tags="grid")
        self.canvas.create_text(cw-4,ch-4,
            text=f"{self.screen_w},{self.screen_h}", fill="#3d444d",
            font=("Consolas",7), anchor="se", tags="grid")

    def _build_ui(self):
        top = tk.Frame(self.root, bg=C["panel"], height=44)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text="MouseFlow v3", font=("Consolas",15,"bold"),
                 fg=C["accent"], bg=C["panel"]).pack(side="left", padx=14, pady=8)
        tk.Label(top, textvariable=self.live_pos, font=("Consolas",9),
                 fg=C["muted"], bg=C["panel"]).pack(side="right", padx=14)

        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True)

        self.left_panel = ResizablePanel(body,"left",52,300,220,C["panel"])
        self.left_panel.pack(side="left", fill="y", padx=(6,0), pady=6)

        self.right_panel = ResizablePanel(body,"right",52,400,260,C["panel"])
        self.right_panel.pack(side="right", fill="y", padx=(0,6), pady=6)

        center = tk.Frame(body, bg=C["bg"])
        center.pack(side="left", fill="both", expand=True, padx=6, pady=6)

        tk.Label(center,
            text="Clic gauche: ajouter  |  Clic droit: valider ligne  |  Canvas adaptatif",
            font=("Consolas",8), fg=C["muted"], bg=C["bg"]).pack(anchor="w")
        cf = tk.Frame(center, bg=C["border"], padx=1, pady=1)
        cf.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(cf, bg="#010409", cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.live_dot = self.canvas.create_oval(-10,-10,-4,-4,
            fill=C["green"], outline="white", width=2, tags="dot")
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Button-3>", self._on_rclick)
        self.canvas.bind("<Configure>", lambda e: self._redraw_grid())

        self._build_bottom()
        self._build_tools()
        self._build_seq()

    def _build_tools(self):
        p = self.left_panel.content
        for w in p.winfo_children(): w.destroy()

        hdr = tk.Frame(p, bg=C["panel"]); hdr.pack(fill="x", padx=4, pady=(8,4))
        if not self.tools_collapsed:
            tk.Label(hdr, text="OUTILS", font=("Consolas",9,"bold"),
                     fg=C["accent"], bg=C["panel"]).pack(side="left", padx=6)
        btn_char = "<<" if not self.tools_collapsed else ">>"
        tk.Button(hdr, text=btn_char, font=("Consolas",8), fg=C["text"],
                  bg=C["border"], relief="flat", padx=3, pady=2,
                  command=self._toggle_tools).pack(side="right", padx=4)

        if self.tools_collapsed:
            for icon, label, val in TOOLS:
                b = tk.Radiobutton(p, text=icon, variable=self.selected_tool,
                                    value=val, font=("Consolas",13),
                                    fg=C["text"], bg=C["panel"],
                                    selectcolor=C["accent"],
                                    activebackground=C["panel"],
                                    indicatoron=False, relief="flat",
                                    padx=2, pady=5, width=3,
                                    command=lambda: self.line_points.clear())
                b.pack(fill="x", padx=4, pady=1)
            return

        for icon, label, val in TOOLS:
            tk.Radiobutton(p, text=f"{icon}  {label}",
                            variable=self.selected_tool, value=val,
                            font=("Consolas",10), fg=C["text"], bg=C["panel"],
                            selectcolor=C["bg"], activebackground=C["panel"],
                            activeforeground=C["accent"], indicatoron=False,
                            relief="flat", padx=8, pady=5, anchor="w",
                            command=lambda: self.line_points.clear()
                            ).pack(fill="x", padx=6, pady=1)

        sep = lambda: tk.Frame(p, bg=C["border"], height=1).pack(fill="x", padx=8, pady=6)
        lbl = lambda t: tk.Label(p, text=t, font=("Consolas",8,"bold"),
                                  fg=C["muted"], bg=C["panel"]).pack(anchor="w", padx=8)
        sep()
        lbl("VITESSE LIGNE (px/s)")
        sf = tk.Frame(p, bg=C["panel"]); sf.pack(fill="x", padx=8, pady=2)
        self.spd_lbl = tk.Label(sf, text=f"{int(self.current_speed.get())} px/s",
                                 font=("Consolas",9), fg=C["accent"], bg=C["panel"])
        self.spd_lbl.pack(side="right")
        tk.Scale(sf, from_=10, to=3000, orient="horizontal",
                 variable=self.current_speed, bg=C["panel"], fg=C["text"],
                 troughcolor=C["border"], highlightthickness=0, showvalue=False,
                 command=lambda v: self.spd_lbl.config(text=f"{int(float(v))} px/s")
                 ).pack(side="left", fill="x", expand=True)

        sep()
        lbl("CLIC PAR DEFAUT")
        for lbl_t, btn, cl in CLICK_TYPES[:5]:
            tk.Radiobutton(p, text=lbl_t, variable=self.cbv, value=lbl_t,
                           font=("Consolas",9), fg=C["text"], bg=C["panel"],
                           selectcolor=C["bg"], activebackground=C["panel"]
                           ).pack(anchor="w", padx=10, pady=1)

        sep()
        lbl("REPETITION")
        rf = tk.Frame(p, bg=C["panel"]); rf.pack(fill="x", padx=8, pady=2)
        tk.Label(rf, text="x", font=("Consolas",9), fg=C["muted"],
                 bg=C["panel"]).pack(side="left")
        tk.Spinbox(rf, from_=1, to=999, textvariable=self.repeat_var,
                   width=5, font=("Consolas",10), bg=C["bg"], fg=C["text"],
                   buttonbackground=C["border"], insertbackground=C["text"]
                   ).pack(side="left", padx=4)

        sep()
        lbl("FOND ECRAN")
        tk.Checkbutton(p, text="Afficher ecran en fond",
                       variable=self.bg_active, command=self._toggle_bg,
                       font=("Consolas",9), fg=C["text"], bg=C["panel"],
                       selectcolor=C["bg"], activebackground=C["panel"]
                       ).pack(anchor="w", padx=10, pady=2)
        tk.Button(p, text="Rafraichir", font=("Consolas",8),
                  fg=C["text"], bg=C["border"], relief="flat", padx=6, pady=2,
                  command=lambda: [self.bg_active.set(True), self._capture()]
                  ).pack(fill="x", padx=8, pady=2)

        sep()
        lbl("URGENCE")
        tk.Label(p, text="Echap = stop", font=("Consolas",8),
                 fg=C["green"], bg=C["panel"]).pack(anchor="w", padx=10)
        tk.Label(p, text="Alt+F4 = quitter", font=("Consolas",8),
                 fg=C["green"], bg=C["panel"]).pack(anchor="w", padx=10)
        kf = tk.Frame(p, bg=C["panel"]); kf.pack(fill="x", padx=8, pady=2)
        tk.Label(kf, text="Perso:", font=("Consolas",8),
                 fg=C["muted"], bg=C["panel"]).pack(side="left")
        tk.Label(kf, textvariable=self.emergency_key,
                 font=("Consolas",9,"bold"), fg=C["orange"],
                 bg=C["panel"]).pack(side="left", padx=4)
        tk.Button(kf, text="[ed]", font=("Consolas",8),
                  fg=C["text"], bg=C["border"], relief="flat", padx=3,
                  command=self._set_key).pack(side="left")

    def _toggle_tools(self):
        self.tools_collapsed = not self.tools_collapsed
        w = 54 if self.tools_collapsed else 220
        self.left_panel.frame.config(width=w)
        self.left_panel.width = w
        self._build_tools()

    def _build_seq(self):
        p = self.right_panel.content
        for w in p.winfo_children(): w.destroy()

        hdr = tk.Frame(p, bg=C["panel"]); hdr.pack(fill="x", padx=4, pady=(8,4))
        btn_char = ">>" if self.seq_collapsed else "<<"
        tk.Button(hdr, text=btn_char, font=("Consolas",8), fg=C["text"],
                  bg=C["border"], relief="flat", padx=3, pady=2,
                  command=self._toggle_seq).pack(side="left", padx=4)
        if not self.seq_collapsed:
            tk.Label(hdr, text="SEQUENCE", font=("Consolas",9,"bold"),
                     fg=C["accent"], bg=C["panel"]).pack(side="left", padx=4)
            tk.Label(hdr, text=f"({len(self.actions)})", font=("Consolas",8),
                     fg=C["muted"], bg=C["panel"]).pack(side="left")

        if self.seq_collapsed:
            for i in range(min(len(self.actions), 40)):
                a = self.actions[i]
                ic = ACTION_ICONS.get(a.type,"?")
                tk.Label(p, text=ic, font=("Consolas",10),
                         fg=C["text"], bg=C["panel"]).pack(pady=1)
            return

        lf = tk.Frame(p, bg=C["panel"]); lf.pack(fill="both", expand=True, padx=4)
        sb = tk.Scrollbar(lf); sb.pack(side="right", fill="y")
        self.seq_list = tk.Listbox(lf, yscrollcommand=sb.set,
                                    bg=C["bg"], fg=C["text"],
                                    selectbackground=C["sel"],
                                    selectforeground=C["accent"],
                                    font=("Consolas",9), relief="flat", bd=0,
                                    activestyle="none")
        self.seq_list.pack(fill="both", expand=True)
        sb.config(command=self.seq_list.yview)
        self.seq_list.bind("<<ListboxSelect>>", self._on_sel)

        self._fill_seq()

        bf = tk.Frame(p, bg=C["panel"]); bf.pack(fill="x", padx=4, pady=4)
        for txt, cmd, col, w in [
            ("UP",   self._seq_up,   C["border"],4),
            ("DN",   self._seq_dn,   C["border"],4),
            ("EDIT", self._seq_edit, C["orange"],6),
            ("DEL",  self._seq_del,  C["red"],   4),
        ]:
            tk.Button(bf, text=txt, command=cmd, font=("Consolas",8,"bold"),
                      fg=C["text"], bg=col, relief="flat", pady=4, width=w
                      ).pack(side="left", padx=2, expand=True, fill="x")

        tk.Label(p, text="Derniere action auto-selectionnee",
                 font=("Consolas",7), fg=C["muted"], bg=C["panel"]).pack(pady=(0,4))

    def _toggle_seq(self):
        self.seq_collapsed = not self.seq_collapsed
        w = 54 if self.seq_collapsed else 260
        self.right_panel.frame.config(width=w)
        self.right_panel.width = w
        self._build_seq()

    def _fill_seq(self):
        if not hasattr(self,"seq_list"): return
        self.seq_list.delete(0,"end")
        for i,a in enumerate(self.actions):
            self.seq_list.insert("end", f"  {i+1:02d}  {a.label()}")
        if self.actions:
            idx = len(self.actions)-1
            self.seq_list.selection_clear(0,"end")
            self.seq_list.selection_set(idx)
            self.seq_list.see(idx)

    def _refresh_seq(self):
        if self.seq_collapsed: self._build_seq(); return
        self._fill_seq()

    def _on_sel(self, event):
        if not hasattr(self,"seq_list"): return
        s = self.seq_list.curselection()
        if not s or s[0] >= len(self.actions): return
        self._highlight(self.actions[s[0]])

    def _highlight(self, a):
        self.canvas.delete("highlight")
        d = a.data
        def tc(rx,ry):
            cw = max(self.canvas.winfo_width(),100)
            ch = max(self.canvas.winfo_height(),100)
            return rx*cw/self.screen_w, ry*ch/self.screen_h

        if a.type in ("move","click"):
            cx,cy = tc(d.get("x",0), d.get("y",0))
            col = C["accent"] if a.type=="move" else C["red"]
            for r,w in [(20,3),(8,2),(3,0)]:
                self.canvas.create_oval(cx-r,cy-r,cx+r,cy+r,
                    outline=col,width=w,tags="highlight")
            self.canvas.create_text(cx,cy-26,text=a.label(),fill=col,
                font=("Consolas",8,"bold"),tags="highlight")

        elif a.type in ("line","drag_line"):
            pts = d.get("points",[])
            col = C["green"] if a.type=="drag_line" else C["purple"]
            if len(pts)>=2:
                for i in range(len(pts)-1):
                    p1=tc(*pts[i]); p2=tc(*pts[i+1])
                    self.canvas.create_line(*p1,*p2,fill=col,width=3,tags="highlight")
            for pt in pts:
                cx,cy=tc(*pt)
                self.canvas.create_oval(cx-5,cy-5,cx+5,cy+5,
                    fill=col,tags="highlight")

        elif a.type == "condition_color":
            cx,cy = tc(d.get("x",0),d.get("y",0))
            rgb = d.get("color",[255,0,0])
            col = "#{:02x}{:02x}{:02x}".format(*rgb)
            self.canvas.create_oval(cx-22,cy-22,cx+22,cy+22,
                outline=col,width=3,tags="highlight")
            self.canvas.create_text(cx,cy-30,text="IF couleur",
                fill=col,font=("Consolas",8,"bold"),tags="highlight")

        self.canvas.tag_raise("dot")

    def _on_motion(self, e):
        rx,ry = self._tr(e.x,e.y)
        self.live_pos.set(f"Ecran ({int(rx)}, {int(ry)})")
        if self.selected_tool.get() in ("line","drag_line") and self.line_points:
            self.canvas.delete("preview")
            lx,ly = self._tc(*self.line_points[-1])
            self.canvas.create_line(lx,ly,e.x,e.y,
                fill=C["accent"],dash=(4,4),tags=("preview","drawing"))

    def _on_click(self, e):
        t = self.selected_tool.get()
        rx,ry = self._tr(e.x,e.y)

        if t == "move":
            self._add(Action("move",x=rx,y=ry,move_speed=0.3))
            self._dot(e.x,e.y,C["accent"],"MOVE")

        elif t == "click":
            ct = self.cbv.get()
            btn,cl = "left",1
            for lbl_t,b,c in CLICK_TYPES:
                if lbl_t==ct: btn,cl=b,c; break
            self._add(Action("click",x=rx,y=ry,click_type=ct,
                              button=btn,clicks=cl,move_speed=0.3,click_interval=0.0))
            self._dot(e.x,e.y,C["red"],ct)

        elif t in ("line","drag_line"):
            self.line_points.append((rx,ry))
            cx,cy=self._tc(rx,ry)
            self._dot(cx,cy,C["green"],size=4)
            if len(self.line_points)>1:
                p1=self._tc(*self.line_points[-2])
                p2=self._tc(*self.line_points[-1])
                self.canvas.create_line(*p1,*p2,fill=C["green"],
                    width=2,tags="drawing")

        elif t == "input":
            self._input_dlg()

        elif t == "wait":
            dur=simpledialog.askfloat("Attente","Duree (s):",
                minvalue=0.1,maxvalue=60,initialvalue=1.0,parent=self.root)
            if dur:
                self._add(Action("wait",duration=dur))
                self._dot(e.x,e.y,C["orange"],f"WAIT {dur}s")

        elif t == "condition":
            self._cond_dlg(rx,ry,e.x,e.y)

    def _on_rclick(self, e):
        t = self.selected_tool.get()
        if t in ("line","drag_line") and len(self.line_points)>=2:
            self.canvas.delete("preview")
            self._add(Action(t,points=list(self.line_points),
                              speed=self.current_speed.get()))
            self.log(f"{t}: {len(self.line_points)} pts")
            self.line_points=[]
        else:
            self.line_points=[]
            self.canvas.delete("preview")

    def _dot(self, cx, cy, col=None, label=None, size=7):
        col = col or C["accent"]
        r=size
        self.canvas.create_oval(cx-r,cy-r,cx+r,cy+r,
            fill=col,outline="white",width=1,tags="drawing")
        if label:
            self.canvas.create_text(cx+r+3,cy,text=label,fill=col,
                font=("Consolas",7),anchor="w",tags="drawing")
        self.canvas.tag_raise("dot")

    def _input_dlg(self):
        dlg=tk.Toplevel(self.root)
        dlg.title("Texte / Touche")
        dlg.configure(bg=C["panel"])
        dlg.geometry("360x210")
        dlg.grab_set()
        tv=tk.StringVar(value="text")
        for lb,vl in [("Ecrire un texte","text"),("Appuyer une touche","key")]:
            tk.Radiobutton(dlg,text=lb,variable=tv,value=vl,
                font=("Consolas",10),fg=C["text"],bg=C["panel"],
                selectcolor=C["bg"],activebackground=C["panel"]
                ).pack(anchor="w",padx=20,pady=5)
        tk.Label(dlg,text="Contenu :",font=("Consolas",9),
                 fg=C["muted"],bg=C["panel"]).pack()
        entry=tk.Entry(dlg,font=("Consolas",12),bg=C["bg"],fg=C["text"],
            insertbackground=C["text"],width=28)
        entry.pack(padx=20,ipady=4,pady=4)
        entry.focus()
        def cap(evt):
            if tv.get()=="key":
                entry.delete(0,"end"); entry.insert(0,evt.keysym)
                return "break"
        entry.bind("<Key>",cap)
        def ok():
            v=entry.get().strip()
            if not v: return
            if tv.get()=="text": self._add(Action("input_text",text=v,delay=0.05))
            else: self._add(Action("key_press",key=v))
            dlg.destroy()
        tk.Button(dlg,text="Ajouter",command=ok,
            font=("Consolas",10,"bold"),fg="#000",
            bg=C["green"],relief="flat",pady=6
            ).pack(pady=8,padx=20,fill="x")
        dlg.bind("<Return>",lambda e:ok())

    def _cond_dlg(self, rx, ry, cx, cy):
        dlg=tk.Toplevel(self.root)
        dlg.title("Condition couleur")
        dlg.configure(bg=C["panel"])
        dlg.geometry("380x270")
        dlg.grab_set()
        tk.Label(dlg,text=f"Position: ({int(rx)}, {int(ry)})",
                 font=("Consolas",10),fg=C["accent"],bg=C["panel"]).pack(pady=(12,4))
        cv=tk.StringVar(value="#ff0000")
        pf=tk.Frame(dlg,bg=C["panel"]); pf.pack()
        cp=tk.Label(pf,bg="#ff0000",width=6,height=2); cp.pack(side="left",padx=8)
        def pick():
            c=colorchooser.askcolor(color=cv.get(),parent=dlg)
            if c[1]: cv.set(c[1]); cp.config(bg=c[1])
        tk.Button(pf,text="Choisir couleur",command=pick,
            font=("Consolas",9),fg=C["text"],bg=C["border"],
            relief="flat",padx=8).pack(side="left")
        tk.Label(dlg,text="Tolerance:",font=("Consolas",9),
                 fg=C["muted"],bg=C["panel"]).pack(pady=(8,2))
        tov=tk.IntVar(value=30)
        tk.Scale(dlg,from_=0,to=100,orient="horizontal",variable=tov,
            bg=C["panel"],fg=C["text"],troughcolor=C["border"],
            highlightthickness=0).pack(fill="x",padx=20)
        def ok():
            h=cv.get().lstrip("#")
            rgb=[int(h[i:i+2],16) for i in (0,2,4)]
            then=[Action("click",x=rx,y=ry,button="left",clicks=1,
                move_speed=0.1,click_type="Gauche",click_interval=0.0).to_dict()]
            self._add(Action("condition_color",x=rx,y=ry,
                color=rgb,tolerance=tov.get(),then=then))
            self._dot(cx,cy,C["orange"],"COND")
            dlg.destroy()
        tk.Button(dlg,text="Ajouter",command=ok,
            font=("Consolas",10,"bold"),fg="#000",
            bg=C["green"],relief="flat",pady=6
            ).pack(pady=10,padx=20,fill="x")

    def _add(self, action):
        self.actions.append(action)
        self._refresh_seq()
        self.log(f"+ {action.label()}")

    def _seq_up(self):
        if not hasattr(self,"seq_list"): return
        s=self.seq_list.curselection()
        if s and s[0]>0:
            i=s[0]
            self.actions[i-1],self.actions[i]=self.actions[i],self.actions[i-1]
            self._fill_seq()
            self.seq_list.selection_clear(0,"end")
            self.seq_list.selection_set(i-1)

    def _seq_dn(self):
        if not hasattr(self,"seq_list"): return
        s=self.seq_list.curselection()
        if s and s[0]<len(self.actions)-1:
            i=s[0]
            self.actions[i],self.actions[i+1]=self.actions[i+1],self.actions[i]
            self._fill_seq()
            self.seq_list.selection_clear(0,"end")
            self.seq_list.selection_set(i+1)

    def _seq_del(self):
        if not hasattr(self,"seq_list"): return
        s=self.seq_list.curselection()
        if s:
            self.actions.pop(s[0])
            self.canvas.delete("highlight")
            self._refresh_seq()

    def _seq_edit(self):
        if not hasattr(self,"seq_list"): return
        s=self.seq_list.curselection()
        if not s: return
        EditDialog(self.root, self.actions[s[0]], self._refresh_seq)

    def _execute(self):
        if not self.actions:
            messagebox.showinfo("Vide","Aucune action!"); return
        if not messagebox.askyesno("Confirmer",
            f"Lancer {len(self.actions)} action(s) x{self.repeat_var.get()}?\n\n"
            f"Arret: Echap | {self.emergency_key.get()} | coin haut-gauche"):
            return
        self.engine=ExecutionEngine(
            self.actions*self.repeat_var.get(),self.log,self._on_done)
        self.log("Demarrage dans 2s...")
        self.root.after(2000,self.engine.start)

    def _stop(self):
        if self.engine: self.engine.stop()
        self.log("Arrete.")

    def _on_done(self):
        self.log("Sequence terminee.")

    def _save(self):
        from tkinter.filedialog import asksaveasfilename
        p=asksaveasfilename(defaultextension=".json",
            filetypes=[("MouseFlow","*.json")])
        if p:
            with open(p,"w") as f:
                json.dump([a.to_dict() for a in self.actions],f,indent=2)
            self.log(f"Sauvegarde: {os.path.basename(p)}")

    def _load(self):
        from tkinter.filedialog import askopenfilename
        p=askopenfilename(filetypes=[("MouseFlow","*.json")])
        if p:
            with open(p) as f:
                self.actions=[Action.from_dict(d) for d in json.load(f)]
            self._refresh_seq()
            self.log(f"Charge: {len(self.actions)} actions")

    def _clear_all(self):
        if messagebox.askyesno("Effacer","Supprimer tout?"):
            self.actions.clear()
            self._refresh_seq()
            self.canvas.delete("drawing","preview","highlight")
            self.log("Tout efface.")

    def _build_bottom(self):
        bar=tk.Frame(self.root,bg=C["panel"],height=50)
        bar.pack(fill="x",padx=6,pady=(0,6))
        bar.pack_propagate(False)
        for txt,cmd,bg in [
            ("EXECUTER",self._execute,C["green"]),
            ("STOP",self._stop,C["red"]),
            ("Sauvegarder",self._save,C["border"]),
            ("Charger",self._load,C["border"]),
            ("Effacer tout",self._clear_all,C["border"]),
        ]:
            tk.Button(bar,text=txt,command=cmd,
                font=("Consolas",10,"bold"),fg=C["text"],bg=bg,
                relief="flat",padx=12,pady=6
                ).pack(side="left",padx=3,pady=6)
        tk.Label(bar,textvariable=self.log_var,font=("Consolas",9),
                 fg=C["muted"],bg=C["panel"],anchor="w"
                 ).pack(side="left",padx=10,fill="x",expand=True)

    def _track_mouse(self):
        try:
            rx,ry=pyautogui.position()
            cx,cy=self._tc(rx,ry)
            r=7
            self.canvas.coords(self.live_dot,cx-r,cy-r,cx+r,cy+r)
            self.canvas.tag_raise("dot")
        except: pass
        self.root.after(50,self._track_mouse)

    def log(self, msg):
        self.log_var.set(msg)
        print(msg)


if __name__ == "__main__":
    root = tk.Tk()
    app = MouseFlowApp(root)
    root.mainloop()
