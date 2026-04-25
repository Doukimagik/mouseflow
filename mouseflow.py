"""
MouseFlow v4.0
"""

import tkinter as tk
from tkinter import messagebox, colorchooser, simpledialog
import threading, time, json, math, pyautogui, os, base64, io
from PIL import Image, ImageTk, ImageGrab, ImageDraw

pyautogui.FAILSAFE = True

# ── PALETTE ──────────────────────────────────────────────────────────────────

C = {
    "bg":"#0d1117","panel":"#161b22","panel2":"#1c2128",
    "border":"#30363d","accent":"#58a6ff","green":"#3fb950",
    "red":"#f85149","orange":"#d29922","purple":"#bc8cff",
    "cyan":"#39d353","text":"#e6edf3","muted":"#8b949e","sel":"#1f3550",
}

TOOLS = [
    ("➡","Deplacement","move"),
    ("🖱","Clic","click"),
    ("✏","Ligne glisser","drag_line"),
    ("📍","Ligne clics","line"),
    ("⌨","Texte / Touche","input"),
    ("⏱","Attente","wait"),
    ("🎨","Condition couleur","condition"),
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
    "move":"➡","click":"🖱","line":"📍","drag_line":"✏",
    "input_text":"⌨","key_press":"🔑","wait":"⏱","condition_color":"🎨",
}

# ── ICÔNE APP (SVG → PNG en mémoire) ────────────────────────────────────────

def make_icon():
    """Crée une icône 64x64 pour la barre des tâches"""
    try:
        img = Image.new("RGBA",(64,64),(0,0,0,0))
        d = ImageDraw.Draw(img)
        # Fond rond dégradé bleu
        for i in range(32):
            alpha = int(255*(1-i/32))
            col = (int(88*(1-i/32)+13*(i/32)), int(166*(1-i/32)+17*(i/32)), 255, alpha)
            d.ellipse([i,i,63-i,63-i], fill=col)
        # Cercle intérieur
        d.ellipse([8,8,55,55], fill=(22,27,34,240))
        # Flèche curseur
        pts = [(20,18),(20,42),(26,36),(30,46),(34,44),(30,34),(38,34)]
        d.polygon(pts, fill=(88,166,255,255))
        return img
    except:
        return None

# ── MODÈLE ───────────────────────────────────────────────────────────────────

class Action:
    def __init__(self, action_type, **kwargs):
        self.type = action_type
        self.data = kwargs

    def to_dict(self):
        return {"type":self.type,"data":self.data}

    @staticmethod
    def from_dict(d):
        return Action(d["type"],**d["data"])

    def label(self):
        d = self.data
        ic = ACTION_ICONS.get(self.type,"?")
        if self.type == "move":
            return f"{ic} MOVE ({int(d.get('x',0))},{int(d.get('y',0))}) {d.get('move_speed',0.3):.2f}s"
        elif self.type == "click":
            ct = d.get("click_type","Gauche")
            return f"{ic} {ct} ({int(d.get('x',0))},{int(d.get('y',0))})"
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
            beh = d.get("on_fail","stop")
            return f"{ic} IF ({int(d.get('x',0))},{int(d.get('y',0))}) fail={beh}"
        return f"{ic} {self.type}"

# ── MOTEUR ───────────────────────────────────────────────────────────────────

class ExecutionEngine:
    def __init__(self, actions, on_log, on_done, loop=False):
        self.actions = actions
        self.on_log = on_log
        self.on_done = on_done
        self.loop = loop
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.running = False

    def _run(self):
        try:
            iteration = 0
            while self.running:
                iteration += 1
                if self.loop:
                    self.on_log(f"=== Boucle #{iteration} ===")
                for i, a in enumerate(self.actions):
                    if not self.running: break
                    self.on_log(f"[{i+1}/{len(self.actions)}] {a.label()}")
                    result = self._exec(a)
                    if result == "stop":
                        self.on_log("Condition non remplie → STOP")
                        self.running = False
                        break
                    time.sleep(0.03)
                if not self.loop:
                    break
        except Exception as e:
            self.on_log(f"Erreur: {e}")
        finally:
            self.running = False
            self.on_done()

    def _exec(self, a):
        d = a.data
        t = a.type

        if t == "move":
            pyautogui.moveTo(int(d["x"]),int(d["y"]),duration=d.get("move_speed",0.3))

        elif t == "click":
            ct = d.get("click_type","Gauche")
            pyautogui.moveTo(int(d["x"]),int(d["y"]),duration=d.get("move_speed",0.3))
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
            if t=="drag_line" and pts:
                pyautogui.moveTo(int(pts[0][0]),int(pts[0][1]),duration=0.15)
                pyautogui.mouseDown()
            for i in range(len(pts)-1):
                if not self.running:
                    if t=="drag_line": pyautogui.mouseUp()
                    return
                p1,p2=pts[i],pts[i+1]
                dist=math.hypot(p2[0]-p1[0],p2[1]-p1[1])
                pyautogui.moveTo(int(p2[0]),int(p2[1]),
                    duration=dist/spd if spd>0 else 0.01)
            if t=="drag_line": pyautogui.mouseUp()

        elif t == "input_text":
            pyautogui.typewrite(d.get("text",""),interval=d.get("delay",0.05))

        elif t == "key_press":
            pyautogui.press(d.get("key",""))

        elif t == "wait":
            time.sleep(d.get("duration",1.0))

        elif t == "condition_color":
            x,y = int(d["x"]),int(d["y"])
            target = tuple(d.get("color",[255,0,0]))
            tol = d.get("tolerance",30)
            on_fail = d.get("on_fail","stop")   # "stop" ou "wait"
            wait_timeout = d.get("wait_timeout", 10.0)

            if on_fail == "wait":
                deadline = time.time() + wait_timeout
                self.on_log(f"Attente couleur (max {wait_timeout}s)...")
                while time.time() < deadline and self.running:
                    px = pyautogui.pixel(x,y)
                    if all(abs(px[i]-target[i])<=tol for i in range(3)):
                        self.on_log("Condition remplie !")
                        for sub in [Action.from_dict(s) for s in d.get("then",[])]:
                            if not self.running: return
                            self._exec(sub)
                        return
                    time.sleep(0.1)
                self.on_log("Timeout condition → stop")
                return "stop"
            else:
                # Mode instantané
                px = pyautogui.pixel(x,y)
                match = all(abs(px[i]-target[i])<=tol for i in range(3))
                self.on_log(f"  pixel={px} {'OK' if match else 'FAIL'}")
                if match:
                    for sub in [Action.from_dict(s) for s in d.get("then",[])]:
                        if not self.running: return
                        self._exec(sub)
                else:
                    return "stop"

# ── PANNEAU REDIMENSIONNABLE ─────────────────────────────────────────────────

class ResizablePanel:
    def __init__(self, parent, side, min_w, max_w, init_w, bg, on_resize=None):
        self.parent = parent
        self.side = side
        self.min_w = min_w
        self.max_w = max_w
        self.width = init_w
        self.on_resize = on_resize
        self._dragging = False

        self.frame = tk.Frame(parent, bg=bg, width=init_w)
        self.frame.pack_propagate(False)

        hs = "right" if side=="left" else "left"
        self.handle = tk.Frame(self.frame, bg=C["accent"], width=4,
                                cursor="sb_h_double_arrow")
        self.handle.pack(side=hs, fill="y")

        self.content = tk.Frame(self.frame, bg=bg)
        self.content.pack(fill="both", expand=True)

        self.handle.bind("<ButtonPress-1>", self._start)
        self.handle.bind("<B1-Motion>",     self._drag)
        self.handle.bind("<ButtonRelease-1>",self._stop)
        self.handle.bind("<Enter>", lambda e: self.handle.config(bg=C["green"]))
        self.handle.bind("<Leave>", lambda e: self.handle.config(bg=C["accent"]))

    def pack(self, **kw): self.frame.pack(**kw)

    def _start(self, e):
        self._dragging=True; self._sx=e.x_root; self._sw=self.width

    def _drag(self, e):
        if not self._dragging: return
        dx = e.x_root - self._sx
        if self.side=="right": dx=-dx
        nw = max(self.min_w, min(self.max_w, self._sw+dx))
        self.width = nw
        self.frame.config(width=nw)
        if self.on_resize: self.on_resize()

    def _stop(self, e):
        self._dragging=False
        if self.on_resize: self.on_resize()

# ── DIALOGUE ÉDITION ─────────────────────────────────────────────────────────

class EditDialog:
    def __init__(self, parent, action, on_save):
        self.action = action
        self.on_save = on_save
        self.d = tk.Toplevel(parent)
        self.d.title(f"Configurer : {action.label()}")
        self.d.configure(bg=C["panel"])
        self.d.grab_set()
        self.d.resizable(False,False)

        t = action.type
        if t in ("move","click"): self._move_click()
        elif t in ("line","drag_line"): self._line()
        elif t == "input_text": self._text()
        elif t == "key_press": self._key()
        elif t == "wait": self._wait()
        elif t == "condition_color": self._condition()
        else:
            tk.Label(self.d,text="Rien a configurer.",
                font=("Consolas",10),fg=C["text"],bg=C["panel"]).pack(padx=20,pady=20)
            self._ok()

        self.d.update_idletasks()
        w,h=self.d.winfo_reqwidth(),self.d.winfo_reqheight()
        px=parent.winfo_rootx()+(parent.winfo_width()-w)//2
        py=parent.winfo_rooty()+(parent.winfo_height()-h)//2
        self.d.geometry(f"+{max(0,px)}+{max(0,py)}")

    def _lbl(self,txt):
        tk.Label(self.d,text=txt,font=("Consolas",9),fg=C["muted"],
            bg=C["panel"],anchor="w").pack(fill="x",padx=16,pady=(7,1))

    def _ent(self,var,w=22):
        e=tk.Entry(self.d,textvariable=var,font=("Consolas",11),
            bg=C["bg"],fg=C["text"],insertbackground=C["text"],
            relief="flat",width=w)
        e.pack(padx=16,ipady=3,pady=(0,2),fill="x")
        return e

    def _slider(self,var,lo,hi,res,fmt):
        f=tk.Frame(self.d,bg=C["panel"]); f.pack(fill="x",padx=16,pady=2)
        lbl=tk.Label(f,text=fmt(var.get()),font=("Consolas",9),
            fg=C["accent"],bg=C["panel"])
        lbl.pack(side="right")
        tk.Scale(f,from_=lo,to=hi,resolution=res,orient="horizontal",
            variable=var,bg=C["panel"],fg=C["text"],
            troughcolor=C["border"],highlightthickness=0,showvalue=False,
            command=lambda v:lbl.config(text=fmt(float(v)))
            ).pack(side="left",fill="x",expand=True)

    def _ok(self,cmd=None):
        tk.Button(self.d,text="✅  Sauvegarder",command=cmd or self.d.destroy,
            font=("Consolas",10,"bold"),fg="#000",
            bg=C["green"],relief="flat",pady=8
            ).pack(fill="x",padx=16,pady=12)

    def _sep(self):
        tk.Frame(self.d,bg=C["border"],height=1).pack(fill="x",padx=16,pady=6)

    def _move_click(self):
        a=self.action; d=a.data
        h=520 if a.type=="click" else 290
        self.d.geometry(f"420x{h}")

        self._lbl("Position X (ecran, pixels) :")
        self.xv=tk.StringVar(value=str(int(d.get("x",0))))
        self._ent(self.xv)

        self._lbl("Position Y (ecran, pixels) :")
        self.yv=tk.StringVar(value=str(int(d.get("y",0))))
        self._ent(self.yv)

        self._lbl("Vitesse deplacement vers la position (s) :")
        self.sv=tk.DoubleVar(value=d.get("move_speed",0.3))
        self._slider(self.sv,0.01,3.0,0.01,lambda v:f"{float(v):.2f}s")

        if a.type=="click":
            self._sep()
            self._lbl("Type de clic :")
            self.ctv=tk.StringVar(value=d.get("click_type","Gauche"))
            for row in [CLICK_TYPES[:3],CLICK_TYPES[3:5],CLICK_TYPES[5:]]:
                rf=tk.Frame(self.d,bg=C["panel"]); rf.pack(fill="x",padx=12,pady=1)
                for lbl_t,btn,cl in row:
                    tk.Radiobutton(rf,text=lbl_t,variable=self.ctv,value=lbl_t,
                        font=("Consolas",9),fg=C["text"],bg=C["panel"],
                        selectcolor=C["bg"],activebackground=C["panel"]
                        ).pack(side="left",padx=6)

            self._sep()
            self._lbl("Intervalle entre clics multiples (s) :")
            self.iv=tk.DoubleVar(value=d.get("click_interval",0.0))
            self._slider(self.iv,0.0,2.0,0.01,lambda v:f"{float(v):.2f}s")

        def save():
            try:
                a.data["x"]=float(self.xv.get())
                a.data["y"]=float(self.yv.get())
                a.data["move_speed"]=self.sv.get()
                if a.type=="click":
                    ct=self.ctv.get(); a.data["click_type"]=ct
                    a.data["click_interval"]=self.iv.get()
                    for lbl_t,btn,cl in CLICK_TYPES:
                        if lbl_t==ct:
                            a.data["button"]=btn; a.data["clicks"]=cl; break
                self.on_save(); self.d.destroy()
            except Exception as e:
                messagebox.showerror("Erreur",str(e),parent=self.d)

        self._ok(save)

    def _line(self):
        a=self.action; d=a.data
        self.d.geometry("420x210")
        self._lbl(f"Nombre de points : {len(d.get('points',[]))}")
        self._lbl("Vitesse (pixels/seconde) :")
        self.sv=tk.DoubleVar(value=d.get("speed",500))
        self._slider(self.sv,10,5000,10,lambda v:f"{float(v):.0f} px/s")
        def save():
            a.data["speed"]=self.sv.get(); self.on_save(); self.d.destroy()
        self._ok(save)

    def _text(self):
        a=self.action; d=a.data
        self.d.geometry("420x250")
        self._lbl("Texte a ecrire :")
        self.tv=tk.StringVar(value=d.get("text",""))
        self._ent(self.tv)
        self._lbl("Delai entre chaque lettre (s) :")
        self.dv=tk.DoubleVar(value=d.get("delay",0.05))
        self._slider(self.dv,0.0,0.5,0.005,lambda v:f"{float(v):.3f}s")
        def save():
            a.data["text"]=self.tv.get(); a.data["delay"]=self.dv.get()
            self.on_save(); self.d.destroy()
        self._ok(save)

    def _key(self):
        a=self.action
        self.d.geometry("420x200")
        self._lbl("Touche (appuie sur la touche ou tape: enter,ctrl+c,f5...):")
        self.kv=tk.StringVar(value=a.data.get("key",""))
        e=self._ent(self.kv); e.focus()
        def cap(evt):
            self.kv.set(evt.keysym); return "break"
        e.bind("<Key>",cap)
        def save():
            a.data["key"]=self.kv.get(); self.on_save(); self.d.destroy()
        self._ok(save)
        self.d.bind("<Return>",lambda e:save())

    def _wait(self):
        a=self.action
        self.d.geometry("420x190")
        self._lbl("Duree d attente (secondes) :")
        self.wv=tk.DoubleVar(value=a.data.get("duration",1.0))
        self._slider(self.wv,0.1,60.0,0.1,lambda v:f"{float(v):.1f}s")
        def save():
            a.data["duration"]=self.wv.get(); self.on_save(); self.d.destroy()
        self._ok(save)

    def _condition(self):
        a=self.action; d=a.data
        self.d.geometry("440x460")

        self._lbl("Position X a surveiller :")
        self.xv=tk.StringVar(value=str(int(d.get("x",0))))
        self._ent(self.xv)
        self._lbl("Position Y a surveiller :")
        self.yv=tk.StringVar(value=str(int(d.get("y",0))))
        self._ent(self.yv)

        self._sep()
        rgb=d.get("color",[255,0,0])
        hex_c="#{:02x}{:02x}{:02x}".format(*rgb)
        self.cv=tk.StringVar(value=hex_c)
        self._lbl("Couleur cible :")
        pf=tk.Frame(self.d,bg=C["panel"]); pf.pack(fill="x",padx=16,pady=4)
        self.cp=tk.Label(pf,bg=hex_c,width=5,height=1)
        self.cp.pack(side="left",padx=(0,8))
        def pick():
            c=colorchooser.askcolor(color=self.cv.get(),parent=self.d)
            if c[1]: self.cv.set(c[1]); self.cp.config(bg=c[1])
        tk.Button(pf,text="Choisir",command=pick,font=("Consolas",9),
            fg=C["text"],bg=C["border"],relief="flat",padx=6).pack(side="left")

        self._lbl("Tolerance (0=exact, 100=souple) :")
        self.tov=tk.IntVar(value=d.get("tolerance",30))
        self._slider(self.tov,0,100,1,lambda v:f"+/-{int(float(v))}")

        self._sep()
        self._lbl("Si la couleur N'est PAS trouvee :")
        self.fv=tk.StringVar(value=d.get("on_fail","stop"))
        ff=tk.Frame(self.d,bg=C["panel"]); ff.pack(fill="x",padx=16,pady=4)
        tk.Radiobutton(ff,text="Stopper la sequence",variable=self.fv,value="stop",
            font=("Consolas",9),fg=C["text"],bg=C["panel"],
            selectcolor=C["bg"],activebackground=C["panel"]
            ).pack(anchor="w")
        tk.Radiobutton(ff,text="Attendre jusqu'a ce qu'elle apparaisse",
            variable=self.fv,value="wait",
            font=("Consolas",9),fg=C["text"],bg=C["panel"],
            selectcolor=C["bg"],activebackground=C["panel"]
            ).pack(anchor="w")

        self._lbl("Timeout si mode Attente (s) :")
        self.toutv=tk.DoubleVar(value=d.get("wait_timeout",10.0))
        self._slider(self.toutv,1.0,120.0,1.0,lambda v:f"{float(v):.0f}s")

        def save():
            try:
                a.data["x"]=float(self.xv.get())
                a.data["y"]=float(self.yv.get())
                h=self.cv.get().lstrip("#")
                a.data["color"]=[int(h[i:i+2],16) for i in (0,2,4)]
                a.data["tolerance"]=self.tov.get()
                a.data["on_fail"]=self.fv.get()
                a.data["wait_timeout"]=self.toutv.get()
                if "then" not in a.data: a.data["then"]=[]
                self.on_save(); self.d.destroy()
            except Exception as e:
                messagebox.showerror("Erreur",str(e),parent=self.d)
        self._ok(save)

# ── SIMULATEUR ───────────────────────────────────────────────────────────────

class SimulatorWindow:
    """Fenetre de simulation visuelle des actions"""

    SIMW, SIMH = 800, 500

    def __init__(self, parent, actions, screen_w, screen_h):
        self.actions = actions
        self.sw, self.sh = screen_w, screen_h
        self.running = False

        self.win = tk.Toplevel(parent)
        self.win.title("Simulateur MouseFlow")
        self.win.configure(bg=C["bg"])
        self.win.geometry("900x620")
        self.win.resizable(True,True)

        self._build()

    def _build(self):
        # En-tête
        hdr=tk.Frame(self.win,bg=C["panel"],height=44)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr,text="Simulateur — aucune action reelle",
            font=("Consolas",12,"bold"),fg=C["orange"],bg=C["panel"]
            ).pack(side="left",padx=14,pady=10)
        tk.Button(hdr,text="▶ Lancer simulation",command=self._run_sim,
            font=("Consolas",10,"bold"),fg="#000",bg=C["green"],
            relief="flat",padx=12,pady=4).pack(side="right",padx=8,pady=6)
        tk.Button(hdr,text="⏹ Stop",command=self._stop,
            font=("Consolas",10,"bold"),fg=C["text"],bg=C["red"],
            relief="flat",padx=8,pady=4).pack(side="right",padx=4,pady=6)
        tk.Button(hdr,text="🗑 Effacer",command=self._clear,
            font=("Consolas",9),fg=C["text"],bg=C["border"],
            relief="flat",padx=8,pady=4).pack(side="right",padx=4,pady=6)

        body=tk.Frame(self.win,bg=C["bg"])
        body.pack(fill="both",expand=True,padx=8,pady=8)

        # Canvas simulation
        left=tk.Frame(body,bg=C["bg"])
        left.pack(side="left",fill="both",expand=True)
        tk.Label(left,text="Visualisation (proportionnel a votre ecran)",
            font=("Consolas",8),fg=C["muted"],bg=C["bg"]).pack(anchor="w")
        cf=tk.Frame(left,bg=C["border"],padx=1,pady=1)
        cf.pack(fill="both",expand=True)
        self.canvas=tk.Canvas(cf,bg="#010409",highlightthickness=0)
        self.canvas.pack(fill="both",expand=True)
        self.canvas.bind("<Configure>",self._on_resize)

        # Test couleur + log
        right=tk.Frame(body,bg=C["panel"],width=240)
        right.pack(side="right",fill="y",padx=(8,0))
        right.pack_propagate(False)

        tk.Label(right,text="TEST COULEUR",font=("Consolas",9,"bold"),
            fg=C["accent"],bg=C["panel"]).pack(pady=(12,4))
        tk.Label(right,text="Clic sur le canvas = tester\ncouleur a cette position",
            font=("Consolas",8),fg=C["muted"],bg=C["panel"]).pack(padx=8)

        # Couleur cible configurable
        self.test_color=tk.StringVar(value="#ff0000")
        pf=tk.Frame(right,bg=C["panel"]); pf.pack(fill="x",padx=8,pady=8)
        self.color_preview=tk.Label(pf,bg="#ff0000",width=4,height=2)
        self.color_preview.pack(side="left",padx=(0,6))
        tk.Button(pf,text="Choisir couleur cible",command=self._pick_test_color,
            font=("Consolas",8),fg=C["text"],bg=C["border"],
            relief="flat",padx=6,pady=3).pack(side="left")

        self.tol_v=tk.IntVar(value=30)
        tk.Label(right,text="Tolerance :",font=("Consolas",8),
            fg=C["muted"],bg=C["panel"]).pack(anchor="w",padx=8)
        self.tol_lbl=tk.Label(right,text="30",font=("Consolas",9,"bold"),
            fg=C["accent"],bg=C["panel"])
        self.tol_lbl.pack(anchor="e",padx=8)
        tk.Scale(right,from_=0,to=100,orient="horizontal",variable=self.tol_v,
            bg=C["panel"],fg=C["text"],troughcolor=C["border"],
            highlightthickness=0,showvalue=False,
            command=lambda v:self.tol_lbl.config(text=str(int(float(v))))
            ).pack(fill="x",padx=8)

        self.result_lbl=tk.Label(right,text="",font=("Consolas",9,"bold"),
            fg=C["text"],bg=C["panel"],wraplength=200,justify="center")
        self.result_lbl.pack(pady=8,padx=8)

        tk.Frame(right,bg=C["border"],height=1).pack(fill="x",padx=8,pady=8)

        tk.Label(right,text="LOG SIMULATION",font=("Consolas",9,"bold"),
            fg=C["accent"],bg=C["panel"]).pack()
        lf=tk.Frame(right,bg=C["panel"]); lf.pack(fill="both",expand=True,padx=4,pady=4)
        sb=tk.Scrollbar(lf); sb.pack(side="right",fill="y")
        self.log_box=tk.Listbox(lf,yscrollcommand=sb.set,
            bg=C["bg"],fg=C["text"],font=("Consolas",8),
            relief="flat",bd=0,activestyle="none",selectbackground=C["sel"])
        self.log_box.pack(fill="both",expand=True)
        sb.config(command=self.log_box.yview)

        # Curseur simulé
        self.sim_dot=self.canvas.create_oval(-10,-10,-4,-4,
            fill=C["green"],outline="white",width=2,tags="dot")
        self.sim_x=0; self.sim_y=0

        self.canvas.bind("<Button-1>",self._canvas_color_test)

    def _on_resize(self,e):
        self._redraw_grid()
        self._redraw_actions()

    def _tc(self,rx,ry):
        cw=max(self.canvas.winfo_width(),100)
        ch=max(self.canvas.winfo_height(),100)
        return rx*cw/self.sw, ry*ch/self.sh

    def _redraw_grid(self):
        self.canvas.delete("grid")
        cw=max(self.canvas.winfo_width(),100)
        ch=max(self.canvas.winfo_height(),100)
        for x in range(0,cw,90):
            self.canvas.create_line(x,0,x,ch,fill="#1a1f28",tags="grid")
        for y in range(0,ch,56):
            self.canvas.create_line(0,y,cw,y,fill="#1a1f28",tags="grid")
        self.canvas.create_text(4,4,text="0,0",fill="#3d444d",
            font=("Consolas",7),anchor="nw",tags="grid")
        self.canvas.create_text(cw-4,ch-4,text=f"{self.sw},{self.sh}",
            fill="#3d444d",font=("Consolas",7),anchor="se",tags="grid")

    def _redraw_actions(self):
        self.canvas.delete("action")
        for a in self.actions:
            self._draw_action(a)
        self.canvas.tag_raise("dot")

    def _draw_action(self, a, color=None):
        d=a.data
        def tc(rx,ry): return self._tc(rx,ry)

        if a.type == "move":
            cx,cy=tc(d.get("x",0),d.get("y",0))
            col=color or C["accent"]
            self.canvas.create_oval(cx-6,cy-6,cx+6,cy+6,
                fill=col,outline="white",tags="action")
            self.canvas.create_text(cx+9,cy,text="MOVE",
                fill=col,font=("Consolas",7),anchor="w",tags="action")

        elif a.type == "click":
            cx,cy=tc(d.get("x",0),d.get("y",0))
            col=color or C["red"]
            ct=d.get("click_type","G")
            self.canvas.create_oval(cx-8,cy-8,cx+8,cy+8,
                fill=col,outline="white",width=2,tags="action")
            self.canvas.create_text(cx,cy,text=ct[0],
                fill="white",font=("Consolas",7,"bold"),tags="action")

        elif a.type in ("line","drag_line"):
            pts=d.get("points",[])
            col=color or (C["green"] if a.type=="drag_line" else C["purple"])
            if len(pts)>=2:
                coords=[]
                for pt in pts:
                    cx,cy=tc(*pt); coords+=[cx,cy]
                self.canvas.create_line(*coords,fill=col,width=2,
                    arrow="last",arrowshape=(8,10,4),tags="action")
            for pt in pts:
                cx,cy=tc(*pt)
                self.canvas.create_oval(cx-3,cy-3,cx+3,cy+3,
                    fill=col,tags="action")

        elif a.type == "condition_color":
            cx,cy=tc(d.get("x",0),d.get("y",0))
            rgb=d.get("color",[255,0,0])
            col=color or "#{:02x}{:02x}{:02x}".format(*rgb)
            for r in [18,10]:
                self.canvas.create_oval(cx-r,cy-r,cx+r,cy+r,
                    outline=col,width=2,tags="action")
            self.canvas.create_text(cx,cy,text="IF",
                fill=col,font=("Consolas",7,"bold"),tags="action")

        elif a.type == "wait":
            self.canvas.create_text(
                self.canvas.winfo_width()//2,
                self.canvas.winfo_height()//2,
                text=f"⏱ WAIT {d.get('duration',1)}s",
                fill=C["orange"],font=("Consolas",10,"bold"),tags="action")

        elif a.type in ("input_text","key_press"):
            cw=max(self.canvas.winfo_width(),100)
            ch=max(self.canvas.winfo_height(),100)
            txt=d.get("text","") or d.get("key","")
            self.canvas.create_text(cw//2,ch//2,
                text=f"⌨ {txt[:20]}",fill=C["cyan"],
                font=("Consolas",10,"bold"),tags="action")

    def _pick_test_color(self):
        c=colorchooser.askcolor(color=self.test_color.get(),parent=self.win)
        if c[1]:
            self.test_color.set(c[1])
            self.color_preview.config(bg=c[1])

    def _canvas_color_test(self, e):
        """Test de couleur sur le canvas simulé"""
        try:
            cw=max(self.canvas.winfo_width(),100)
            ch=max(self.canvas.winfo_height(),100)
            rx=int(e.x*self.sw/cw)
            ry=int(e.y*self.sh/ch)
            real_px=pyautogui.pixel(rx,ry)
            target_hex=self.test_color.get().lstrip("#")
            target=(int(target_hex[0:2],16),int(target_hex[2:4],16),int(target_hex[4:6],16))
            tol=self.tol_v.get()
            match=all(abs(real_px[i]-target[i])<=tol for i in range(3))
            col_hex="#{:02x}{:02x}{:02x}".format(*real_px[:3])
            res=f"Ecran ({rx},{ry})\nPixel: {col_hex}\nRGB{real_px[:3]}\n{'MATCH ✅' if match else 'NO MATCH ❌'}"
            self.result_lbl.config(text=res,fg=C["green"] if match else C["red"])
            # Point sur canvas
            self.canvas.delete("test_dot")
            r=10
            col=C["green"] if match else C["red"]
            self.canvas.create_oval(e.x-r,e.y-r,e.x+r,e.y+r,
                outline=col,width=3,tags="test_dot")
        except Exception as ex:
            self.result_lbl.config(text=f"Erreur: {ex}",fg=C["red"])

    def _run_sim(self):
        self.running=True
        self.canvas.delete("action")
        self._log("=== Simulation ===")
        threading.Thread(target=self._sim_thread,daemon=True).start()

    def _sim_thread(self):
        for i,a in enumerate(self.actions):
            if not self.running: break
            self._log(f"[{i+1}] {a.label()}")
            # Déplace le curseur simulé
            d=a.data
            if a.type in ("move","click"):
                tx,ty=self._tc(d.get("x",0),d.get("y",0))
                steps=20
                for s in range(steps+1):
                    if not self.running: break
                    cx=self.sim_x+(tx-self.sim_x)*s/steps
                    cy=self.sim_y+(ty-self.sim_y)*s/steps
                    r=7
                    self.canvas.coords(self.sim_dot,cx-r,cy-r,cx+r,cy+r)
                    time.sleep(d.get("move_speed",0.3)/steps)
                self.sim_x,self.sim_y=tx,ty
                # Flash sur la position
                col=C["red"] if a.type=="click" else C["accent"]
                self.canvas.after(0,lambda a=a:self._draw_action(a,col))
                time.sleep(0.3)

            elif a.type in ("line","drag_line"):
                pts=d.get("points",[])
                for pt in pts:
                    if not self.running: break
                    tx,ty=self._tc(*pt)
                    self.sim_x,self.sim_y=tx,ty
                    r=7
                    self.canvas.coords(self.sim_dot,tx-r,ty-r,tx+r,ty+r)
                    time.sleep(0.05)
                self.canvas.after(0,lambda a=a:self._draw_action(a))

            elif a.type=="wait":
                dur=d.get("duration",1)
                self._log(f"  Attente {dur}s (simulee en 0.5s)")
                time.sleep(min(dur,0.5))
                self.canvas.after(0,lambda a=a:self._draw_action(a))

            elif a.type=="condition_color":
                self.canvas.after(0,lambda a=a:self._draw_action(a))
                beh=d.get("on_fail","stop")
                self._log(f"  Condition (simulation: toujours OK si mode attente, stop sinon)")
                time.sleep(0.2)

            else:
                self.canvas.after(0,lambda a=a:self._draw_action(a))
                time.sleep(0.2)

            self.canvas.tag_raise("dot")
        self._log("=== Fin simulation ===")
        self.running=False

    def _stop(self):
        self.running=False
        self._log("Simulation stoppee.")

    def _clear(self):
        self.canvas.delete("action")
        self.log_box.delete(0,"end")
        self._redraw_grid()

    def _log(self, msg):
        self.log_box.insert("end", msg)
        self.log_box.see("end")

# ── APPLICATION PRINCIPALE ───────────────────────────────────────────────────

class MouseFlowApp:
    MARGIN = 6      # marge autour du canvas

    def __init__(self, root):
        self.root = root
        self.root.title("MouseFlow v4.0")
        self.root.configure(bg=C["bg"])
        self.root.geometry("1440x800")
        self.root.minsize(900,600)

        # Icône
        try:
            ico=make_icon()
            if ico:
                self._ico_photo=ImageTk.PhotoImage(ico)
                self.root.iconphoto(True,self._ico_photo)
        except: pass

        self.actions=[]
        self.selected_tool=tk.StringVar(value="move")
        self.line_points=[]
        self.current_speed=tk.DoubleVar(value=500)
        self.engine=None
        self.live_pos=tk.StringVar(value="Ecran : -")
        self.bg_active=tk.BooleanVar(value=False)
        self.bg_photo=None
        self.bg_image_id=None
        self.emergency_key=tk.StringVar(value="F8")
        self._last_custom_key="F8"
        self.repeat_var=tk.IntVar(value=1)
        self.cbv=tk.StringVar(value="Gauche")
        self.tools_collapsed=False
        self.seq_collapsed=False
        self.log_var=tk.StringVar(value="Pret")
        self.loop_mode=tk.BooleanVar(value=False)

        self.screen_w,self.screen_h=pyautogui.size()

        self._build_ui()
        self._bind_keys()
        self._track_mouse()

    # ── COORDS ───────────────────────────────────

    def _tc(self,rx,ry):
        cw=max(self.canvas.winfo_width(),100)
        ch=max(self.canvas.winfo_height(),100)
        return rx*cw/self.screen_w, ry*ch/self.screen_h

    def _tr(self,cx,cy):
        cw=max(self.canvas.winfo_width(),100)
        ch=max(self.canvas.winfo_height(),100)
        return cx*self.screen_w/cw, cy*self.screen_h/ch

    # ── URGENCE ──────────────────────────────────

    def _bind_keys(self):
        self.root.bind("<Escape>",lambda e:self._estop())
        self._bind_custom()

    def _bind_custom(self):
        try: self.root.unbind(f"<{self._last_custom_key}>")
        except: pass
        k=self.emergency_key.get(); self._last_custom_key=k
        try: self.root.bind(f"<{k}>",lambda e:self._estop())
        except: pass

    def _estop(self):
        if self.engine: self.engine.stop()
        self.log("ARRET URGENCE")

    def _set_key(self):
        dlg=tk.Toplevel(self.root)
        dlg.title("Touche urgence"); dlg.configure(bg=C["panel"])
        dlg.geometry("320x150"); dlg.grab_set()
        tk.Label(dlg,text="Appuie sur la touche :",
            font=("Consolas",11),fg=C["text"],bg=C["panel"]).pack(pady=14)
        kv=tk.StringVar(value=self.emergency_key.get())
        e=tk.Entry(dlg,textvariable=kv,font=("Consolas",13),
            bg=C["bg"],fg=C["accent"],insertbackground=C["text"],
            width=12,justify="center")
        e.pack(pady=4); e.focus()
        def cap(evt): kv.set(evt.keysym); return "break"
        e.bind("<Key>",cap)
        def ok():
            self.emergency_key.set(kv.get()); self._bind_custom()
            self.log(f"Touche urgence: {kv.get()}"); dlg.destroy()
        tk.Button(dlg,text="OK",command=ok,font=("Consolas",10,"bold"),
            fg="#000",bg=C["green"],relief="flat",pady=5
            ).pack(pady=10,padx=20,fill="x")

    # ── FOND ECRAN ───────────────────────────────

    def _toggle_bg(self):
        if self.bg_active.get(): self._capture()
        else: self._clear_bg()

    def _capture(self):
        self.log("Capture dans 0.5s...")
        self.root.iconify()
        self.root.after(500,self._do_capture)

    def _do_capture(self):
        try:
            cw=max(self.canvas.winfo_width(),100)
            ch=max(self.canvas.winfo_height(),100)
            shot=ImageGrab.grab().resize((cw,ch),Image.LANCZOS)
            self.bg_photo=ImageTk.PhotoImage(shot)
            if self.bg_image_id: self.canvas.delete(self.bg_image_id)
            self.bg_image_id=self.canvas.create_image(0,0,anchor="nw",
                image=self.bg_photo,tags="bg")
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
            self.bg_image_id=None
        self.bg_photo=None

    def _redraw_grid(self):
        self.canvas.delete("grid")
        cw=max(self.canvas.winfo_width(),100)
        ch=max(self.canvas.winfo_height(),100)
        for x in range(0,cw,90):
            self.canvas.create_line(x,0,x,ch,fill="#1a1f28",tags="grid")
        for y in range(0,ch,56):
            self.canvas.create_line(0,y,cw,y,fill="#1a1f28",tags="grid")
        self.canvas.create_text(4,4,text="0,0",fill="#3d444d",
            font=("Consolas",7),anchor="nw",tags="grid")
        self.canvas.create_text(cw-4,ch-4,
            text=f"{self.screen_w},{self.screen_h}",fill="#3d444d",
            font=("Consolas",7),anchor="se",tags="grid")

    # ── UI PRINCIPALE ────────────────────────────

    def _build_ui(self):
        top=tk.Frame(self.root,bg=C["panel"],height=44)
        top.pack(fill="x"); top.pack_propagate(False)
        tk.Label(top,text="MouseFlow v4",font=("Consolas",15,"bold"),
            fg=C["accent"],bg=C["panel"]).pack(side="left",padx=14,pady=8)
        tk.Label(top,textvariable=self.live_pos,font=("Consolas",9),
            fg=C["muted"],bg=C["panel"]).pack(side="right",padx=14)

        self.body=tk.Frame(self.root,bg=C["bg"])
        self.body.pack(fill="both",expand=True)

        self.left_panel=ResizablePanel(self.body,"left",54,320,220,C["panel"],
            on_resize=self._on_panel_resize)
        self.left_panel.pack(side="left",fill="y",
            padx=(self.MARGIN,0),pady=self.MARGIN)

        self.right_panel=ResizablePanel(self.body,"right",54,420,270,C["panel"],
            on_resize=self._on_panel_resize)
        self.right_panel.pack(side="right",fill="y",
            padx=(0,self.MARGIN),pady=self.MARGIN)

        self.center=tk.Frame(self.body,bg=C["bg"])
        self.center.pack(side="left",fill="both",expand=True,
            padx=self.MARGIN,pady=self.MARGIN)
        self._build_canvas_area()

        self._build_bottom()
        self._build_tools()
        self._build_seq()

    def _build_canvas_area(self):
        for w in self.center.winfo_children(): w.destroy()
        info=tk.Frame(self.center,bg=C["bg"])
        info.pack(fill="x")
        tk.Label(info,text="Clic gauche: ajouter  |  Clic droit: valider ligne",
            font=("Consolas",8),fg=C["muted"],bg=C["bg"]).pack(side="left")
        cf=tk.Frame(self.center,bg=C["border"],padx=1,pady=1)
        cf.pack(fill="both",expand=True)
        self.canvas=tk.Canvas(cf,bg="#010409",cursor="crosshair",highlightthickness=0)
        self.canvas.pack(fill="both",expand=True)
        self.live_dot=self.canvas.create_oval(-14,-14,-6,-6,
            fill=C["green"],outline="white",width=2,tags="dot")
        self.canvas.bind("<Button-1>",self._on_click)
        self.canvas.bind("<Motion>",self._on_motion)
        self.canvas.bind("<Button-3>",self._on_rclick)
        self.canvas.bind("<Configure>",self._on_canvas_resize)

    def _on_canvas_resize(self,e):
        self._redraw_grid()
        if self.bg_active.get():
            self.root.after(100,self._capture)

    def _on_panel_resize(self):
        """Appele quand un panneau est redimensionne — le canvas se reajuste automatiquement"""
        self.root.after(50,self._redraw_grid)

    # ── TOOLS PANEL ──────────────────────────────

    def _build_tools(self):
        p=self.left_panel.content
        for w in p.winfo_children(): w.destroy()

        hdr=tk.Frame(p,bg=C["panel"]); hdr.pack(fill="x",padx=4,pady=(8,4))
        if not self.tools_collapsed:
            tk.Label(hdr,text="OUTILS",font=("Consolas",9,"bold"),
                fg=C["accent"],bg=C["panel"]).pack(side="left",padx=6)
        tk.Button(hdr,text="◀◀" if not self.tools_collapsed else "▶▶",
            font=("Consolas",8),fg=C["text"],bg=C["border"],
            relief="flat",padx=3,pady=2,
            command=self._toggle_tools).pack(side="right",padx=4)

        if self.tools_collapsed:
            for icon,label,val in TOOLS:
                b=tk.Radiobutton(p,text=icon,variable=self.selected_tool,
                    value=val,font=("Consolas",13),fg=C["text"],bg=C["panel"],
                    selectcolor=C["accent"],activebackground=C["panel"],
                    indicatoron=False,relief="flat",padx=2,pady=5,width=3,
                    command=lambda:self.line_points.clear())
                b.pack(fill="x",padx=4,pady=1)
            return

        for icon,label,val in TOOLS:
            tk.Radiobutton(p,text=f"{icon}  {label}",
                variable=self.selected_tool,value=val,
                font=("Consolas",10),fg=C["text"],bg=C["panel"],
                selectcolor=C["bg"],activebackground=C["panel"],
                activeforeground=C["accent"],indicatoron=False,
                relief="flat",padx=8,pady=5,anchor="w",
                command=lambda:self.line_points.clear()
                ).pack(fill="x",padx=6,pady=1)

        def sep(): tk.Frame(p,bg=C["border"],height=1).pack(fill="x",padx=8,pady=5)
        def lbl(t): tk.Label(p,text=t,font=("Consolas",8,"bold"),
            fg=C["muted"],bg=C["panel"]).pack(anchor="w",padx=8)

        sep(); lbl("VITESSE LIGNE (px/s)")
        sf=tk.Frame(p,bg=C["panel"]); sf.pack(fill="x",padx=8,pady=2)
        self.spd_lbl=tk.Label(sf,text=f"{int(self.current_speed.get())} px/s",
            font=("Consolas",9),fg=C["accent"],bg=C["panel"])
        self.spd_lbl.pack(side="right")
        tk.Scale(sf,from_=10,to=3000,orient="horizontal",
            variable=self.current_speed,bg=C["panel"],fg=C["text"],
            troughcolor=C["border"],highlightthickness=0,showvalue=False,
            command=lambda v:self.spd_lbl.config(text=f"{int(float(v))} px/s")
            ).pack(side="left",fill="x",expand=True)

        sep(); lbl("CLIC PAR DEFAUT")
        for lbl_t,btn,cl in CLICK_TYPES[:5]:
            tk.Radiobutton(p,text=lbl_t,variable=self.cbv,value=lbl_t,
                font=("Consolas",9),fg=C["text"],bg=C["panel"],
                selectcolor=C["bg"],activebackground=C["panel"]
                ).pack(anchor="w",padx=10,pady=1)

        sep(); lbl("REPETITION")
        rf=tk.Frame(p,bg=C["panel"]); rf.pack(fill="x",padx=8,pady=2)
        tk.Label(rf,text="x",font=("Consolas",9),fg=C["muted"],
            bg=C["panel"]).pack(side="left")
        tk.Spinbox(rf,from_=1,to=9999,textvariable=self.repeat_var,
            width=6,font=("Consolas",10),bg=C["bg"],fg=C["text"],
            buttonbackground=C["border"],insertbackground=C["text"]
            ).pack(side="left",padx=4)

        sep(); lbl("BOUCLE INFINIE")
        tk.Checkbutton(p,text="Tourner en boucle sans fin",
            variable=self.loop_mode,
            font=("Consolas",9),fg=C["text"],bg=C["panel"],
            selectcolor=C["bg"],activebackground=C["panel"]
            ).pack(anchor="w",padx=10,pady=2)
        tk.Label(p,text="(Echap pour arreter)",
            font=("Consolas",7),fg=C["muted"],bg=C["panel"]
            ).pack(anchor="w",padx=14)

        sep(); lbl("FOND ECRAN")
        tk.Checkbutton(p,text="Afficher ecran en fond",
            variable=self.bg_active,command=self._toggle_bg,
            font=("Consolas",9),fg=C["text"],bg=C["panel"],
            selectcolor=C["bg"],activebackground=C["panel"]
            ).pack(anchor="w",padx=10,pady=2)
        tk.Button(p,text="Rafraichir capture",font=("Consolas",8),
            fg=C["text"],bg=C["border"],relief="flat",padx=6,pady=2,
            command=lambda:[self.bg_active.set(True),self._capture()]
            ).pack(fill="x",padx=8,pady=2)

        sep(); lbl("URGENCE")
        tk.Label(p,text="Echap = stop | Alt+F4 = quitter",
            font=("Consolas",8),fg=C["green"],bg=C["panel"]).pack(anchor="w",padx=10)
        kf=tk.Frame(p,bg=C["panel"]); kf.pack(fill="x",padx=8,pady=2)
        tk.Label(kf,text="Perso:",font=("Consolas",8),
            fg=C["muted"],bg=C["panel"]).pack(side="left")
        tk.Label(kf,textvariable=self.emergency_key,
            font=("Consolas",9,"bold"),fg=C["orange"],bg=C["panel"]
            ).pack(side="left",padx=4)
        tk.Button(kf,text="✏",font=("Consolas",9),fg=C["text"],
            bg=C["border"],relief="flat",padx=4,
            command=self._set_key).pack(side="left")

    def _toggle_tools(self):
        self.tools_collapsed=not self.tools_collapsed
        w=54 if self.tools_collapsed else 220
        self.left_panel.frame.config(width=w)
        self.left_panel.width=w
        self._build_tools()
        self.root.after(60,self._redraw_grid)

    # ── SEQUENCE PANEL ───────────────────────────

    def _build_seq(self):
        p=self.right_panel.content
        for w in p.winfo_children(): w.destroy()

        hdr=tk.Frame(p,bg=C["panel"]); hdr.pack(fill="x",padx=4,pady=(8,4))
        tk.Button(hdr,text="▶▶" if self.seq_collapsed else "◀◀",
            font=("Consolas",8),fg=C["text"],bg=C["border"],
            relief="flat",padx=3,pady=2,
            command=self._toggle_seq).pack(side="left",padx=4)
        if not self.seq_collapsed:
            tk.Label(hdr,text="SEQUENCE",font=("Consolas",9,"bold"),
                fg=C["accent"],bg=C["panel"]).pack(side="left",padx=4)
            tk.Label(hdr,text=f"({len(self.actions)})",
                font=("Consolas",8),fg=C["muted"],bg=C["panel"]).pack(side="left")

        if self.seq_collapsed:
            for i,a in enumerate(self.actions[:40]):
                tk.Label(p,text=ACTION_ICONS.get(a.type,"?"),
                    font=("Consolas",10),fg=C["text"],bg=C["panel"]).pack(pady=1)
            return

        lf=tk.Frame(p,bg=C["panel"]); lf.pack(fill="both",expand=True,padx=4)
        sb=tk.Scrollbar(lf); sb.pack(side="right",fill="y")
        self.seq_list=tk.Listbox(lf,yscrollcommand=sb.set,
            bg=C["bg"],fg=C["text"],selectbackground=C["sel"],
            selectforeground=C["accent"],font=("Consolas",9),
            relief="flat",bd=0,activestyle="none")
        self.seq_list.pack(fill="both",expand=True)
        sb.config(command=self.seq_list.yview)
        self.seq_list.bind("<<ListboxSelect>>",self._on_sel)
        self.seq_list.bind("<Double-Button-1>",lambda e:self._seq_edit())

        self._fill_seq()

        # Boutons UP/DN/EDIT/DEL — avec vraies flèches
        bf=tk.Frame(p,bg=C["panel"]); bf.pack(fill="x",padx=4,pady=(4,2))
        for txt,cmd,col in [
            ("↑ Haut",   self._seq_up,  C["border"]),
            ("↓ Bas",    self._seq_dn,  C["border"]),
            ("✏ Editer", self._seq_edit,C["orange"]),
            ("✕ Supp",   self._seq_del, C["red"]),
        ]:
            tk.Button(bf,text=txt,command=cmd,font=("Consolas",8,"bold"),
                fg=C["text"],bg=col,relief="flat",pady=5
                ).pack(side="left",padx=2,expand=True,fill="x")

        tk.Label(p,text="Double-clic = editer  |  Derniere action auto-selectionnee",
            font=("Consolas",7),fg=C["muted"],bg=C["panel"],wraplength=220
            ).pack(pady=(2,6))

    def _toggle_seq(self):
        self.seq_collapsed=not self.seq_collapsed
        w=54 if self.seq_collapsed else 270
        self.right_panel.frame.config(width=w)
        self.right_panel.width=w
        self._build_seq()
        self.root.after(60,self._redraw_grid)

    def _fill_seq(self):
        if not hasattr(self,"seq_list"): return
        self.seq_list.delete(0,"end")
        for i,a in enumerate(self.actions):
            self.seq_list.insert("end",f"  {i+1:02d}  {a.label()}")
        if self.actions:
            idx=len(self.actions)-1
            self.seq_list.selection_clear(0,"end")
            self.seq_list.selection_set(idx)
            self.seq_list.see(idx)

    def _refresh_seq(self):
        if self.seq_collapsed: self._build_seq(); return
        self._fill_seq()
        if hasattr(self,"seq_list"):
            hdr_text=f"SEQUENCE ({len(self.actions)})"
            _ = hdr_text  # update handled by rebuild on collapse toggle

    def _on_sel(self,event):
        if not hasattr(self,"seq_list"): return
        s=self.seq_list.curselection()
        if not s or s[0]>=len(self.actions): return
        self._highlight(self.actions[s[0]])

    def _highlight(self,a):
        self.canvas.delete("highlight")
        d=a.data
        def tc(rx,ry):
            cw=max(self.canvas.winfo_width(),100)
            ch=max(self.canvas.winfo_height(),100)
            return rx*cw/self.screen_w, ry*ch/self.screen_h

        if a.type in ("move","click"):
            cx,cy=tc(d.get("x",0),d.get("y",0))
            col=C["accent"] if a.type=="move" else C["red"]
            for r,w in [(22,3),(14,2),(5,0)]:
                self.canvas.create_oval(cx-r,cy-r,cx+r,cy+r,
                    outline=col,width=w,fill="" if w else col,tags="highlight")
            self.canvas.create_text(cx,cy-30,text=a.label(),
                fill=col,font=("Consolas",8,"bold"),tags="highlight")
        elif a.type in ("line","drag_line"):
            pts=d.get("points",[])
            col=C["green"] if a.type=="drag_line" else C["purple"]
            if len(pts)>=2:
                for i in range(len(pts)-1):
                    p1=tc(*pts[i]); p2=tc(*pts[i+1])
                    self.canvas.create_line(*p1,*p2,fill=col,width=3,tags="highlight")
            for pt in pts:
                cx,cy=tc(*pt)
                self.canvas.create_oval(cx-6,cy-6,cx+6,cy+6,
                    fill=col,tags="highlight")
        elif a.type=="condition_color":
            cx,cy=tc(d.get("x",0),d.get("y",0))
            rgb=d.get("color",[255,0,0])
            col="#{:02x}{:02x}{:02x}".format(*rgb)
            self.canvas.create_oval(cx-24,cy-24,cx+24,cy+24,
                outline=col,width=3,tags="highlight")
            self.canvas.create_text(cx,cy-32,text=a.label(),
                fill=col,font=("Consolas",7,"bold"),tags="highlight")
        self.canvas.tag_raise("dot")

    # ── EVENTS CANVAS ────────────────────────────

    def _on_motion(self,e):
        rx,ry=self._tr(e.x,e.y)
        self.live_pos.set(f"Ecran ({int(rx)}, {int(ry)})")
        if self.selected_tool.get() in ("line","drag_line") and self.line_points:
            self.canvas.delete("preview")
            lx,ly=self._tc(*self.line_points[-1])
            self.canvas.create_line(lx,ly,e.x,e.y,
                fill=C["accent"],dash=(4,4),tags=("preview","drawing"))

    def _on_click(self,e):
        t=self.selected_tool.get()
        rx,ry=self._tr(e.x,e.y)

        if t=="move":
            a=Action("move",x=rx,y=ry,move_speed=0.3)
            self._add(a)
            EditDialog(self.root,a,self._refresh_seq)
            self._dot(e.x,e.y,C["accent"],"MOVE")

        elif t=="click":
            ct=self.cbv.get(); btn,cl="left",1
            for lbl_t,b,c in CLICK_TYPES:
                if lbl_t==ct: btn,cl=b,c; break
            a=Action("click",x=rx,y=ry,click_type=ct,button=btn,
                      clicks=cl,move_speed=0.3,click_interval=0.0)
            self._add(a)
            EditDialog(self.root,a,self._refresh_seq)
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

        elif t=="input":
            a=Action("input_text",text="",delay=0.05)
            self._add(a)
            EditDialog(self.root,a,self._refresh_seq)

        elif t=="wait":
            a=Action("wait",duration=1.0)
            self._add(a)
            EditDialog(self.root,a,self._refresh_seq)

        elif t=="condition":
            a=Action("condition_color",x=rx,y=ry,
                color=[255,0,0],tolerance=30,on_fail="stop",
                wait_timeout=10.0,then=[])
            self._add(a)
            EditDialog(self.root,a,self._refresh_seq)
            self._dot(e.x,e.y,C["orange"],"COND")

    def _on_rclick(self,e):
        t=self.selected_tool.get()
        if t in ("line","drag_line") and len(self.line_points)>=2:
            self.canvas.delete("preview")
            a=Action(t,points=list(self.line_points),speed=self.current_speed.get())
            self._add(a)
            EditDialog(self.root,a,self._refresh_seq)
            self.log(f"{t}: {len(self.line_points)} pts")
            self.line_points=[]
        else:
            self.line_points=[]; self.canvas.delete("preview")

    def _dot(self,cx,cy,col=None,label=None,size=7):
        col=col or C["accent"]; r=size
        self.canvas.create_oval(cx-r,cy-r,cx+r,cy+r,
            fill=col,outline="white",width=1,tags="drawing")
        if label:
            self.canvas.create_text(cx+r+3,cy,text=label,fill=col,
                font=("Consolas",7),anchor="w",tags="drawing")
        self.canvas.tag_raise("dot")

    # ── SÉQUENCE ACTIONS ─────────────────────────

    def _add(self,action):
        self.actions.append(action)
        self._refresh_seq()

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
        EditDialog(self.root,self.actions[s[0]],self._refresh_seq)

    # ── EXÉCUTION ────────────────────────────────

    def _execute(self):
        if not self.actions:
            messagebox.showinfo("Vide","Aucune action!"); return
        loop=self.loop_mode.get()
        rep=self.repeat_var.get() if not loop else 1
        msg=(f"Lancer {len(self.actions)} action(s)"
             f"{' EN BOUCLE INFINIE' if loop else f' x{rep}'}?\n\n"
             f"Arret: Echap | {self.emergency_key.get()} | coin haut-gauche")
        if not messagebox.askyesno("Confirmer",msg): return
        acts=self.actions*rep if not loop else self.actions
        self.engine=ExecutionEngine(acts,self.log,self._on_done,loop=loop)
        self.log(f"Demarrage dans 2s {'(BOUCLE)' if loop else ''}...")
        self.root.after(2000,self.engine.start)

    def _stop(self):
        if self.engine: self.engine.stop()
        self.log("Arrete.")

    def _on_done(self):
        self.log("Sequence terminee.")

    def _simulate(self):
        if not self.actions:
            messagebox.showinfo("Vide","Aucune action a simuler!"); return
        SimulatorWindow(self.root,self.actions,self.screen_w,self.screen_h)

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
        if messagebox.askyesno("Effacer","Supprimer toutes les actions?"):
            self.actions.clear(); self._refresh_seq()
            self.canvas.delete("drawing","preview","highlight")
            self.log("Tout efface.")

    # ── BARRE DU BAS ─────────────────────────────

    def _build_bottom(self):
        bar=tk.Frame(self.root,bg=C["panel"],height=52)
        bar.pack(fill="x",padx=self.MARGIN,pady=(0,self.MARGIN))
        bar.pack_propagate(False)
        for txt,cmd,bg in [
            ("▶ EXECUTER",  self._execute,  C["green"]),
            ("⏹ STOP",      self._stop,     C["red"]),
            ("🧪 SIMULER",  self._simulate, C["purple"]),
            ("💾 Sauv.",    self._save,     C["border"]),
            ("📂 Charger",  self._load,     C["border"]),
            ("🗑 Effacer",  self._clear_all,C["border"]),
        ]:
            tk.Button(bar,text=txt,command=cmd,
                font=("Consolas",10,"bold"),fg=C["text"],bg=bg,
                relief="flat",padx=12,pady=6
                ).pack(side="left",padx=3,pady=6)
        tk.Label(bar,textvariable=self.log_var,font=("Consolas",9),
            fg=C["muted"],bg=C["panel"],anchor="w"
            ).pack(side="left",padx=10,fill="x",expand=True)

    # ── TRACKING ─────────────────────────────────

    def _track_mouse(self):
        try:
            rx,ry=pyautogui.position()
            cx,cy=self._tc(rx,ry)
            r=7
            self.canvas.coords(self.live_dot,cx-r,cy-r,cx+r,cy+r)
            self.canvas.tag_raise("dot")
        except: pass
        self.root.after(50,self._track_mouse)

    def log(self,msg):
        self.log_var.set(msg); print(msg)


if __name__ == "__main__":
    root=tk.Tk()
    app=MouseFlowApp(root)
    root.mainloop()
