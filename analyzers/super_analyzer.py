# analyzers/super_analyzer.py — SUPER ANALYZER (911 Fiesta)
# v2025-09-03 — motor híbrido (STFT+HPS, cepstrum fallback) + OddHarm + perfiles + gate + vista
# Reqs: numpy, PySide6, pyqtgraph (solo para la vista; corre sin ella)

from __future__ import annotations
import numpy as np

# ---- UI deps (opcionales) ----
try:
    from PySide6 import QtWidgets, QtCore
    import pyqtgraph as pg
except Exception:
    QtWidgets = None
    QtCore = None
    pg = None

# ---- Card host (usa la tuya si existe; si no, fallback mini) ----
try:
    from module_card import ModuleCard  # tu implementación real
except Exception:
    class ModuleCard(QtWidgets.QFrame if QtWidgets else object):
        """Fallback mínimo para no romper si no está tu ModuleCard."""
        def __init__(self, title="Module"):
            if QtWidgets:
                super().__init__()
                self.setObjectName("MiniCard")
                self.setStyleSheet("QFrame{background:#151515;border:1px solid #333;border-radius:6px;} QLabel{color:#ccc}")
                lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(8,8,8,8); lay.setSpacing(6)
                self.lbl = QtWidgets.QLabel(title); self.lbl.setStyleSheet("font-weight:700; color:#ddd;")
                self.status = QtWidgets.QLabel("—"); self.status.setStyleSheet("color:#999")
                self.vu = QtWidgets.QProgressBar(); self.vu.setRange(0,1000); self.vu.setTextVisible(False)
                self.vu.setStyleSheet("QProgressBar{background:#1e1e1e;border:1px solid #333;border-radius:7px;height:10px;} QProgressBar::chunk{background:#22aa88;border-radius:7px;}")
                lay.addWidget(self.lbl); lay.addWidget(self.vu); lay.addWidget(self.status)
                self._sl = {}; self._leds = {}; self._on=False
            else:
                self._sl = {}; self._leds = {}; self._on=False
        def add_slider(self, key, label, vmin, vmax, vdef): self._sl[key] = float(vdef)
        def get_value(self, key): return float(self._sl.get(key, 0.0))
        def add_led(self, key, label): self._leds[key] = False
        def set_led(self, key, on): self._leds[key] = bool(on)
        def set_value(self, v):
            if hasattr(self, "vu"): self.vu.setValue(int(max(0,min(1,float(v)))*1000))
        def set_on(self, on): self._on = bool(on)
        def is_on(self): return bool(self._on)
        def get_thresholds(self): return (0.0, 1.0)
        def get_match(self): return 100.0
        def set_status(self, text):
            if hasattr(self, "status"): self.status.setText(str(text))
        def add_custom_widget(self, w):
            if QtWidgets and hasattr(self, "layout"): self.layout().addWidget(w)
        def to_preset(self): return {"sliders": self._sl}
        def from_preset(self, cfg:dict):
            for k,v in (cfg.get("sliders") or {}).items(): self._sl[k]=float(v)

EPS = 1e-12

# ---------------- Estabilidad ----------------
class StableGate:
    def __init__(self, on_th=0.62, off_th=0.48, min_on_ms=180, min_off_ms=220,
                 cooldown_ms=250, min_conf=0.55, max_toggles=3, window_s=10.0):
        self.on_th=float(on_th); self.off_th=float(off_th)
        self.min_on=float(min_on_ms)/1000.0; self.min_off=float(min_off_ms)/1000.0
        self.cooldown=float(cooldown_ms)/1000.0
        self.min_conf=float(min_conf); self.max_toggles=int(max_toggles); self.window_s=float(window_s)
        self.state=False; self.t_above=0.0; self.t_below=0.0; self.cool=0.0
        self.toggles=[]; self.t_now=0.0
    def update(self, v, conf, dt):
        v=float(np.clip(v,0,1)); conf=float(np.clip(conf,0,1)); dt=max(1e-4,float(dt)); self.t_now+=dt
        self.toggles=[t for t in self.toggles if (self.t_now - t) <= self.window_s]
        if self.cool>0: self.cool=max(0.0,self.cool-dt)
        if conf < self.min_conf:
            self.t_above=0.0; self.t_below=0.0; return self.state
        if v>=self.on_th: self.t_above+=dt; self.t_below=0.0
        elif v<=self.off_th: self.t_below+=dt; self.t_above=0.0
        else: self.t_above=0.0; self.t_below=0.0
        if len(self.toggles)>=self.max_toggles or self.cool>0.0: return self.state
        changed=False
        if not self.state and v>=self.on_th and self.t_above>=self.min_on: self.state=True; changed=True
        elif self.state and v<=self.off_th and self.t_below>=self.min_off: self.state=False; changed=True
        if changed:
            self.toggles.append(self.t_now); self.cool=self.cooldown; self.t_above=0.0; self.t_below=0.0
        return self.state

# ---------------- Vista ----------------
class SuperView(QtWidgets.QWidget if QtWidgets else object):
    def __init__(self, parent=None):
        if not QtWidgets: return
        super().__init__(parent)
        if pg: pg.setConfigOptions(antialias=True)
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)

        self.glw = pg.GraphicsLayoutWidget() if pg else None
        lay.addWidget(self.glw)

        # A) Spectrum + armónicos
        self.p_spec = self.glw.addPlot(row=0, col=0, title="Spectrum + Harmonics") if pg else None
        if self.p_spec:
            self.p_spec.showGrid(x=True,y=True,alpha=0.2)
            self.p_spec.setLabel("bottom","Hz"); self.p_spec.setLabel("left","dB")
            self.curve_spec = self.p_spec.plot([],[], pen=pg.mkPen(width=1))
            self.vlines=[]; self.shades=[]

        # B) Odd bars + plantilla
        self.p_harm = self.glw.addPlot(row=1, col=0, title="Odd Harmonics vs 1/k") if pg else None
        if self.p_harm:
            self.p_harm.showGrid(x=True,y=True,alpha=0.2)
            self.p_harm.setLabel("bottom","k (1,3,5,...)"); self.p_harm.setLabel("left","E (norm)")
            self.bar_odd = pg.BarGraphItem(x=[], height=[], width=0.6, brush=(150,200,255,180))
            self.p_harm.addItem(self.bar_odd)
            self.curve_tmpl = self.p_harm.plot([],[], pen=pg.mkPen((255,180,0), width=2))
            self.txt_corr = pg.TextItem("", anchor=(1,0)); self.p_harm.addItem(self.txt_corr)
            self.txt_corr.setPos(0.98,0.02); self.txt_corr.setParentItem(self.p_harm.getViewBox())

        # C) Timeline (valor efectivo) + thresholds
        self.p_gate = self.glw.addPlot(row=0, col=1, rowspan=2, title="Value (v_eff) + Gate (20 s)") if pg else None
        if self.p_gate:
            self.p_gate.showGrid(x=True,y=True,alpha=0.2)
            self.p_gate.setLabel("bottom","frames"); self.p_gate.setLabel("left","value")
            self.curve_val=self.p_gate.plot([],[], pen=pg.mkPen((80,220,120), width=2))
            self.line_on=pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen((240,80,80), style=QtCore.Qt.DashLine))
            self.line_off=pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen((240,160,80), style=QtCore.Qt.DashLine))
            self.p_gate.addItem(self.line_on); self.p_gate.addItem(self.line_off)
            self.bufN=400; self.buf_v=np.zeros(self.bufN,dtype=np.float32); self.i=0

    def update_from_debug(self, d):
        if not (QtWidgets and pg) or not d: return
        freqs=d.get("freqs"); db=d.get("db")
        if isinstance(freqs,np.ndarray) and isinstance(db,np.ndarray) and len(freqs)==len(db) and len(freqs)>8:
            self.curve_spec.setData(freqs, db)
            self.p_spec.setXRange(max(20,freqs[1]), min(20000,freqs[-1]), padding=0.02)
            self.p_spec.setYRange(np.nanmin(db)-3, np.nanmax(db)+3, padding=0.02)
            for it in getattr(self,"vlines",[]): self.p_spec.removeItem(it)
            for it in getattr(self,"shades",[]): self.p_spec.removeItem(it)
            self.vlines=[]; self.shades=[]
            klist=d.get("k_list",[]); f0=float(d.get("f0",0.0)); cents=float(d.get("tolc",35.0))
            tol_ratio=2.0**(cents/1200.0)
            for k in klist:
                fk=k*f0
                if fk<=0 or fk>=freqs[-1]*0.98: continue
                col=(80,180,255) if (k%2==1) else (160,160,160)
                ln=pg.InfiniteLine(pos=fk, angle=90, pen=pg.mkPen(col, width=1))
                self.p_spec.addItem(ln); self.vlines.append(ln)
                lo,hi=fk/tol_ratio, fk*tol_ratio
                shade=pg.LinearRegionItem([lo,hi]); shade.setZValue(-10)
                shade.setBrush(pg.mkBrush(80,180,255,40) if (k%2==1) else pg.mkBrush(160,160,160,30))
                self.p_spec.addItem(shade); self.shades.append(shade)

        odd_bins=d.get("odd_bins",[]); tmpl=d.get("tmpl",[])
        if odd_bins:
            x=np.arange(1, 2*len(odd_bins)+1, 2)
            y=np.array(odd_bins, dtype=float); y=y/max(y.max(),1e-9)
            self.bar_odd.setOpts(x=x, height=y)
            t=np.array(tmpl if tmpl else [1.0/kk for kk in x], dtype=float); t=t/max(t.max(),1e-9)
            self.curve_tmpl.setData(x,t)
            self.p_harm.setXRange(0, x[-1]+2, padding=0.02); self.p_harm.setYRange(0,1.05,padding=0.02)
            self.txt_corr.setText(f"corr={d.get('corr',0.0):.2f}  odd={d.get('odd_ratio',0.0):.2f}")

        v=float(d.get("v_eff", 0.0))
        self.buf_v[self.i % self.bufN]=v; self.i+=1
        idx=(np.arange(self.bufN)+self.i)%self.bufN
        vv=self.buf_v[idx]; self.curve_val.setData(np.arange(self.bufN), vv)
        self.p_gate.setYRange(-0.05,1.05,padding=0.02)
        self.line_on.setPos(d.get("on_th",0.62)); self.line_off.setPos(d.get("off_th",0.48))

# ---------------- Súper Analizador ----------------
class SuperAnalyzer:
    """
    Analizador único con motor espectral + f0 robusto + odd/even + perfiles + gate + vista.
    Perfiles: BAJADA | BASE_GOLPE | ATAQUE | BRAKE
    API: process(block, sr) / tick == process
    """
    name = "SUPER ANALYZER"

    def __init__(self, profile: str = "BASE_GOLPE", card=None):
        self.profile = (profile or "BASE_GOLPE").upper()

        # Card + controles
        self.card = card or ModuleCard(f"{self.name} [{self.profile}]")
        self.card.add_slider("minacc","Min. accuracy",0.20,0.90,0.60)
        self.card.add_slider("harmn","N impares (3–9)",3.00,9.00,5.00)
        self.card.add_slider("tolc","Tol (cents)",10.00,60.00,35.00)
        self.card.add_slider("tilt","Tilt (dB/dec)",0.00,12.00,6.00)
        self.card.add_slider("smooth","Suavizado",0.00,0.95,0.25)
        self.card.add_slider("sil_db","Gate silencio (dB)",40.00,70.00,60.00)
        self.card.add_slider("backend","Backend (0=STFT,1=Hybrid)",0,1,0)

        try:
            self.card.add_led("odd","ODD"); self.card.add_led("atk","ATK"); self.card.add_led("brk","BRK")
        except Exception: pass

        # Vista
        self._view=None
        if QtWidgets and pg:
            try:
                self._view = SuperView()
                if hasattr(self.card,"add_custom_widget"): self.card.add_custom_widget(self._view)
                elif hasattr(self.card,"set_extra_widget"): self.card.set_extra_widget(self._view)
                elif hasattr(self.card,"layout"): self.card.layout().addWidget(self._view)
            except Exception: self._view=None

        # Estados
        self._vu=0.0; self._lp_state=0.0
        self._win=None; self._nfft=0; self._freqs=None
        self._odd_bins=[]; self._tmpl=[]
        self._v_prev=0.0; self._burst=0.0; self._trend_buf=np.zeros(20,dtype=np.float32); self._ti=0; self._last_dt=0.05
        self._gate = StableGate(on_th=0.62, off_th=0.48, min_on_ms=180, min_off_ms=220, cooldown_ms=250, min_conf=0.55)
        self._dbg_ctr=0

    # ---------- helpers ----------
    def _prep_fft(self, n, sr):
        nfft=1
        while nfft<n: nfft<<=1
        nfft=min(nfft,4096)
        if nfft!=self._nfft:
            self._nfft=nfft
            self._win=np.hanning(nfft).astype(np.float32)
            self._freqs=np.fft.rfftfreq(nfft, 1.0/float(sr)).astype(np.float32)
    def _mag(self, x, sr):
        n=len(x); self._prep_fft(n,sr)
        if n<self._nfft:
            xw=np.zeros(self._nfft,dtype=np.float32); xw[:n]=x; xw*=self._win
        else:
            xw=(x[-self._nfft:]*self._win).astype(np.float32,copy=False)
        X=np.fft.rfft(xw); mag=np.abs(X).astype(np.float32)+1e-12
        return mag, self._freqs
    def _lp1(self, x, sr, fc=300.0):
        a=1.0-np.exp(-2.0*np.pi*fc/float(sr))
        y=np.empty_like(x,dtype=np.float32); s=self._lp_state
        for i,xi in enumerate(x): s=s+a*(xi-s); y[i]=s
        self._lp_state=float(s); return y

    # f0: HPS + fallback cepstrum
    def _hps_f0_acc(self, mag, freqs, fmin=40.0, fmax=240.0, max_h=4):
        band=(freqs>=fmin)&(freqs<=fmax)
        if not np.any(band): return 0.0, 0.0
        S=mag[band].astype(np.float64); F=freqs[band].astype(np.float64)
        if S.size<8: return 0.0, 0.0
        H=S.copy()
        for h in range(2,max_h+1): H[:len(H)//h]*=S[::h][:len(H)//h]
        H=np.nan_to_num(H, nan=0.0, posinf=0.0, neginf=0.0)
        k=int(np.argmax(H)); f0=float(F[k])
        nb=max(6,int(0.03*len(H))); a=max(0,k-nb); b=min(len(H),k+nb+1)
        med=float(np.median(H[a:b])+1e-12); acc=float(np.clip((float(H[k])/med)-1.0,0.0,1.0))
        return f0, acc
    def _cepstrum_f0(self, mag, freqs, sr, fmin=40.0, fmax=240.0):
        # cepstrum de log-magnitude para estimar T0
        logS=np.log(np.maximum(mag,1e-12))
        cep=np.fft.irfft(logS)
        q_min=int(np.floor(sr/fmax)); q_max=int(np.ceil(sr/fmin))
        if q_max>len(cep)-1: q_max=len(cep)-1
        if q_min<1 or q_min>=q_max: return 0.0
        q_idx = q_min + int(np.argmax(cep[q_min:q_max]))
        f0 = float(sr / max(q_idx,1))
        return f0 if (fmin<=f0<=fmax) else 0.0

    @staticmethod
    def _cents_to_ratio(c): return float(np.power(2.0, c/1200.0))

    def _odd_even_corr(self, mag, freqs, f0, n_impares, tolc, tilt):
        if f0<=0.0: return 0.0,0.0,0.0
        nyq=float(freqs[-1]); tol_ratio=self._cents_to_ratio(tolc)-1.0
        if tilt!=0.0:
            f_safe=np.maximum(freqs,1e-3)
            w=np.power(10.0,(tilt*np.log10(f_safe/max(f0,1e-3)))/10.0)
            mag_w=mag*w.astype(np.float32)
        else:
            mag_w=mag
        odd_E=0.0; even_E=0.0; self._odd_bins=[]; self._tmpl=[]
        K=int(np.clip(n_impares,1,15)); k_max=int(np.floor(0.90*nyq/f0))
        max_k=min(max(2*K,2), k_max)
        for k in range(1,max_k+1):
            fk=k*f0
            if fk>=0.90*nyq: break
            bw=fk*tol_ratio; lo=fk-bw; hi=fk+bw
            m=(freqs>=lo)&(freqs<=hi)
            e=float((mag_w[m]**2).sum()) if np.any(m) else 0.0
            if k%2==1 and (1+(k-1)//2)<=K:
                odd_E+=e; self._odd_bins.append(e); self._tmpl.append(1.0/k)
            elif k%2==0:
                even_E+=e
        if len(self._odd_bins)==0: corr=0.0
        else:
            x=np.asarray(self._odd_bins,dtype=np.float64); t=np.asarray(self._tmpl,dtype=np.float64)
            num=float(np.dot(x,t)); den=float(np.linalg.norm(x)*np.linalg.norm(t))
            corr=float(np.clip(num/(den+1e-20),0.0,1.0))
        return odd_E, even_E, corr

    def _smooth(self, v_raw, dt, acc=None, minacc=0.60):
        smooth=float(np.clip(self.card.get_value("smooth"),0.0,0.95))
        tau_ms=80.0+(600.0-80.0)*(smooth**2)
        if acc is not None and acc < float(minacc): tau_ms *= 1.5
        a=np.exp(-dt/(tau_ms/1000.0)); self._vu=(1.0-a)*v_raw + a*self._vu
        return float(np.clip(self._vu,0.0,1.0))

    def _trend(self, v):
        d=float(v - getattr(self, "_v_last", 0.0)); self._v_last=v
        self._trend_buf[self._ti % self._trend_buf.size]=d; self._ti+=1
        m=float(np.mean(self._trend_buf))
        return "up" if m>0.05 else ("down" if m<-0.05 else "flat")

    def _burst_smooth(self, x, dt):
        a=np.exp(-dt/0.08)  # 80 ms
        self._burst=(1-a)*x + a*self._burst
        return self._burst

    def _profile_map(self, v, dbfs, trend, dt):
        dv=v - self._v_prev; self._v_prev=v
        p=self.profile
        if p=="BASE_GOLPE":
            v_eff=v; atk= dv>0; brk= dv<0
        elif p=="BAJADA":
            v_eff=1.0 - v; atk= dv<0; brk= dv>0
        elif p=="ATAQUE":
            raw=max(0.0, dv)*4.0
            v_eff=self._burst_smooth(raw, dt)
            if v<0.5: v_eff*=0.5
            atk=(dv>0); brk=False
        elif p=="BRAKE":
            raw=max(0.0, -dv)*4.0
            v_eff=self._burst_smooth(raw, dt)
            if trend=="down" or dbfs<-30.0: v_eff=min(1.0, v_eff*1.2)
            atk=False; brk=(dv<0)
        else:
            v_eff=v; atk=False; brk=False
        return float(np.clip(v_eff,0.0,1.0)), atk, brk

    def _downsample_spec(self, freqs, mag, n=800):
        fmin, fmax = max(20.0,freqs[1]), min(freqs[-1],20000.0)
        edges=np.geomspace(fmin,fmax,n+1); out_f=0.5*(edges[1:]+edges[:-1])
        out_m=np.zeros(n,dtype=np.float32)
        for i in range(n):
            m=(freqs>=edges[i])&(freqs<edges[i+1])
            out_m[i]=float(np.max(mag[m]) if np.any(m) else 1e-12)
        db=20.0*np.log10(out_m+1e-12)
        return out_f, db

    # ---------- core ----------
    def process(self, block, sr):
        if block is None or sr is None or sr<=0: return
        x=np.asarray(block, dtype=np.float32)
        if x.ndim==2: x=x.mean(axis=1).astype(np.float32, copy=False)  # mono
        n=x.size
        if n==0: return
        dt=n/float(sr); self._last_dt=dt

        # Nivel
        rms=float(np.sqrt(np.mean(x*x))+EPS); dbfs=20.0*np.log10(rms+EPS)
        sil_db=float(np.clip(self.card.get_value("sil_db"),30.0,80.0))
        if dbfs < -sil_db:
            self._render(0.0,0.0,0.0,0.0,"flat",dbfs,0.0)
            return

        # Espectros
        xl=self._lp1(x, sr, fc=300.0)
        mag_l, freqs = self._mag(xl, sr)   # f0/acc
        mag,   freqs = self._mag(x,  sr)   # medición

        # Sliders
        minacc=float(np.clip(self.card.get_value("minacc"),0.0,1.0))
        harmn=int(round(self.card.get_value("harmn"))); harmn = harmn + (harmn%2==0); harmn=int(np.clip(harmn,3,9))
        tolc=float(np.clip(self.card.get_value("tolc"),5.0,80.0))
        tilt=float(np.clip(self.card.get_value("tilt"),0.0,12.0))
        backend=int(round(self.card.get_value("backend")))  # 0=STFT, 1=hybrid (cepstrum fallback on low acc)

        # f0 + acc (HPS)
        f0, acc = self._hps_f0_acc(mag_l, freqs, fmin=40.0, fmax=240.0, max_h=4)
        if backend==1 and (acc < 0.35):  # híbrido: si HPS flojo, intentá cepstrum
            f0_c = self._cepstrum_f0(mag_l, freqs, sr, fmin=40.0, fmax=240.0)
            if f0_c>0.0:
                f0 = f0_c
                acc = max(acc, 0.35)  # piso de confianza cuando entra fallback

        if f0<=0.0 or acc < 0.20:
            self._render(0.0,0.0,acc,0.0,"flat",dbfs,0.0)
            return

        # Prueba de octava (f0, 2f0, 0.5f0)
        candidates=[f0]
        if 2.0*f0 < (freqs[-1]*0.90): candidates.append(2.0*f0)
        if 0.5*f0 > 20.0: candidates.append(0.5*f0)

        best={"score":-1.0,"ratio":0.0,"corr":0.0,"f":f0}
        for ftest in candidates:
            odd_E, even_E, corr = self._odd_even_corr(mag, freqs, ftest, harmn, tolc, tilt)
            ratio = odd_E / max(odd_E + even_E, 1e-12)
            pre = 0.6*ratio + 0.4*corr
            if pre > best["score"]: best={"score":pre,"ratio":ratio,"corr":corr,"f":ftest}

        ratio=float(np.clip(best["ratio"],0.0,1.0))
        corr=float(np.clip(best["corr"],0.0,1.0))
        penal = 1.0 if acc>=minacc else 0.5*(acc/max(minacc,1e-6))
        fused=(0.6*ratio + 0.4*corr)*penal
        v=self._smooth(fused, dt, acc=acc, minacc=minacc)
        trend=self._trend(v)

        # Perfil → valor efectivo y LEDs ATK/BRK
        v_eff, led_atk, led_brk = self._profile_map(v, dbfs, trend, dt)

        # Render + vista
        self._render(v_eff, best["f"], acc, ratio, trend, dbfs, corr, led_atk, led_brk)
        try:
            f_vis, db_vis = self._downsample_spec(freqs, mag, n=800)
            dbg={"freqs":f_vis,"db":db_vis,"k_list":list(range(1,2*harmn)),
                 "f0":best["f"],"tolc":tolc,"odd_bins":self._odd_bins,"tmpl":self._tmpl,
                 "corr":corr,"odd_ratio":ratio,"v_eff":v_eff,"on_th":self._gate.on_th,"off_th":self._gate.off_th}
            if self._view is not None: self._view.update_from_debug(dbg)
        except Exception:
            pass

    def _render(self, v_eff, f0, acc, ratio, trend, dbfs, corr=0.0, led_atk=False, led_brk=False):
        if hasattr(self.card,"set_value"): self.card.set_value(v_eff)
        on_state=self._gate.update(v_eff, conf=acc, dt=self._last_dt)
        # compat de estado
        if   hasattr(self.card,"set_estado"): self.card.set_estado(on_state)
        elif hasattr(self.card,"set_state"):  self.card.set_state(on_state)
        elif hasattr(self.card,"set_on"):     self.card.set_on(on_state)
        # LEDs
        try:
            self.card.set_led("odd", ratio>=0.5 and acc>=float(self.card.get_value("minacc")))
            self.card.set_led("atk", bool(led_atk)); self.card.set_led("brk", bool(led_brk))
        except Exception: pass
        # Status
        try:
            self.card.set_status(f"[{self.profile}] f0={f0:.1f}Hz acc={acc:.2f} odd={ratio:.2f} corr={corr:.2f} v={v_eff:.2f} {dbfs:.1f}dBFS")
        except Exception: pass

    tick = process
