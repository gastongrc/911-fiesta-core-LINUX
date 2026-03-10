# WEB UI Audit Report — 911 Fiesta Core

**Date:** 2026-03-10
**Auditor:** Automated code audit
**Scope:** Full WEB frontend (React + Vite) at `webapp/src/`
**Architecture rule:** WEB = remote monitoring + light control. WEB must NOT run system logic. WEB only sends commands and reads state from CORE snapshot.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  WEB Frontend (React + Vite)                            │
│  http://192.168.1.80:8000                               │
│                                                         │
│  Pages: Home, Calendar, ConfigPro, Vision, Analyze,     │
│         Cues, Network, Presets                           │
└────────────────┬────────────────────────────────────────┘
                 │ HTTP / SSE
                 ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI Web Server (Port 8000)                         │
│  /api/v1/*  — Proxies to CORE + Vision                  │
│  /api/v1/stream — SSE (forwards CORE snapshot)          │
└───────┬──────────────────────┬──────────────────────────┘
        │                      │
        ▼                      ▼
┌───────────────────┐  ┌───────────────────┐
│ CORE HTTP Server  │  │ Vision Flask      │
│ Port 8010         │  │ Port 5000         │
│ /core/snapshot    │  │ /vision/*         │
└───────────────────┘  └───────────────────┘
```

**State reading path:**
WEB → FastAPI `:8000/api/v1/status/unified` → fetches `127.0.0.1:8010/core/snapshot` → returns to WEB

The WEB **does NOT** directly call `/core/snapshot`. It goes through the FastAPI proxy layer which forwards to CORE. This is correct architecture.

---

## 2. Pages & Routes

| Route | Page Component | Accessible via | In Router? |
|-------|---------------|----------------|------------|
| `/` | `Home` (Control Room) | Sidebar nav | Yes |
| `/calendar` | `Calendar` | Sidebar nav | Yes |
| `/config` | `ConfigPro` | Sidebar nav | Yes |
| — | `Vision` | Not in router | **No** (orphan) |
| — | `Analyze` | Not in router | **No** (orphan) |
| — | `Cues` | Not in router | **No** (orphan) |
| — | `Network` | Not in router | **No** (orphan) |
| — | `Presets` | Not in router | **No** (orphan) |
| — | `Config` | Not in router | **No** (orphan, replaced by ConfigPro) |

**Router** (`router.jsx`) only defines 3 routes: `/`, `/calendar`, `/config`.
Six pages exist in `src/pages/` but are **not reachable** from the current navigation.

---

## 3. Page-by-Page Audit

### 3.1 Home (Control Room) — `pages/Home.jsx`

**Status: WORKING**

| Aspect | Detail |
|--------|--------|
| **Data source** | SSE to `/api/v1/stream` with fallback to polling `/api/v1/status/unified` (1s) |
| **Snapshot path** | FastAPI forwards to `127.0.0.1:8010/core/snapshot` — **correct** |
| **Real data** | CPU, RAM, BPM, uptime, Avolites status, audio status, network, calendar, vision cameras, modules, transport |
| **Placeholder fallback** | `'---'` via `val()` function when data is null — **acceptable** (graceful degradation) |

**Components:**

| Card | Data Source | Status |
|------|-------------|--------|
| Metrics Bar (CPU, RAM, BPM, Uptime) | `status.system.*`, `status.bpm` | WORKING |
| Consola Avolites | `status.avolites.*` | WORKING |
| Placa de Sonido | `status.audio.*` | WORKING |
| Red Local | `status.network.*` | WORKING |
| Clip de Audio | `status.audio.clipping/peak/clip_l/clip_r/headroom` | WORKING |
| Transport | `status.transport.*` | WORKING |
| Next Block | `status.calendar.*` | WORKING |
| Modules | `status.state`, `status.permissions` | WORKING |
| Vision Pro - Camaras | `status.vision.*` | WORKING |

**Dead buttons:**
| Button | Issue |
|--------|-------|
| **Reconectar** (Avolites) | No `onClick` handler — **DEAD** |
| **Restart** (Vision) | No `onClick` handler — **DEAD** |

**Hardcoded values:**
- Version badge: `v8.0` (hardcoded)
- Camera names: `['HAZE', 'DJ', 'ARTIST']` (hardcoded)
- Module list: `[bajada, base_golpe, ataque, brake]` (hardcoded)
- Red Local LED: always `color="green"` (hardcoded, ignores network status)

---

### 3.2 Calendar — `pages/Calendar.jsx`

**Status: WORKING**

| Aspect | Detail |
|--------|--------|
| **Data source** | `fetch(getApiBase()/calendar/week)` + `fetch(getApiBase()/calendar/status)` (2s polling) |
| **Backend endpoints** | All verified in `api/routers/calendar.py` |

**Sub-tabs:**

| Tab | Status |
|-----|--------|
| Estado (live status + accordion day grid) | WORKING |
| Horarios (schedule editor) | WORKING |
| Control (GO / Extend / Override) | WORKING |

**API calls (all verified against backend):**

| Action | Endpoint | Backend Exists? |
|--------|----------|-----------------|
| Load week schedule | `GET /api/v1/calendar/week` | Yes |
| Load status | `GET /api/v1/calendar/status` | Yes |
| GO (change mode) | `POST /api/v1/calendar/go` | Yes |
| Extend block | `POST /api/v1/calendar/extend` | Yes |
| Override mode | `POST /api/v1/calendar/override` | Yes |
| Stop override | `POST /api/v1/calendar/override/stop` | Yes |
| Toggle auto | `POST /api/v1/calendar/auto` | Yes |
| Set control mode | `POST /api/v1/calendar/control_mode` | Yes |
| Force manual | `POST /api/v1/calendar/force_manual` | Yes |
| Save schedule | `POST /api/v1/calendar/save` | Yes |

**Hardcoded (acceptable — UI constants):**
- `MODE_COLORS`, `CANONICAL_MODES`, `MODE_LABELS` — display constants
- `DAY_ORDER`, `DAY_NAMES` — calendar structure
- `EXTRA_ACTIONS` — vision action list

---

### 3.3 ConfigPro — `pages/ConfigPro.jsx`

**Status: PARTIAL**

| Aspect | Detail |
|--------|--------|
| **Data source** | `getAvolitesConfig()` + `getModulesConfig()` from config API |
| **Backend endpoints** | Config section GET/POST verified |

**Tabs and status:**

| Tab | Content | Status |
|-----|---------|--------|
| Red/Consola | Avolites IP/port, Red Local, Transport, Offset, Vision cameras | PARTIAL |
| Bajada | Module toggles | WORKING |
| Base Golpe | Module toggles | WORKING |
| Ataque | Module toggles | WORKING |
| Brake | Module toggles | WORKING |
| Calendario | Redirect text to Calendar page | WORKING (by design) |

**Red/Consola tab — button audit:**

| Button | Wired? | Backend? | Status |
|--------|--------|----------|--------|
| Guardar y Reconectar (Avolites) | Yes → `handleSaveAvolites()` | Yes | WORKING |
| Aplicar Offset (Cues) | Yes → `handleSaveOffset()` | Yes | WORKING |
| Aplicar NIC (Red Local) | **No onClick** | Yes (`/api/v1/network/interface`) | **DEAD** |
| Guardar (Transport) | **No onClick** | No endpoint for transport config | **DEAD** |
| Test (per camera) | **No onClick** | No endpoint | **DEAD** |
| Guardar Todo (cameras) | **No onClick** | No endpoint for camera config | **DEAD** |
| Test Todas (cameras) | **No onClick** | No endpoint | **DEAD** |

**Hardcoded/mock values:**
- MAC address: hardcoded `'---'` (not read from backend)
- Protocol options: `['HTTP', 'sACN', 'Art-Net', 'DMX']` — local state only, never saved
- NIC options: `['eth0', 'wlan0', 'Auto']` — local state only, never saved
- Camera templates: `['Axis', 'Hikvision', 'Dahua', 'Custom']` — local state only, never saved
- Camera form state: local only, no save endpoint

---

### 3.4 Vision — `pages/Vision.jsx`

**Status: PARTIAL**

| Aspect | Detail |
|--------|--------|
| **Data source** | `fetch(getApiBase()/status/unified)` (5s polling) + frame proxy |
| **Frames** | `getApiBase()/vision/frame/{id}?t={key}` (2s refresh) |
| **Backend** | Vision proxy + Flask endpoints verified |

| Component | Data Source | Status |
|-----------|-------------|--------|
| Camera status (online/offline) | `status.cameras` from unified | WORKING |
| Frame preview | `/api/v1/vision/frame/{id}` proxy | WORKING |
| FPS display | `status.cameras[].fps` | WORKING |
| Zone config | None — text says "Zonas configuradas via Qt UI" | READ-ONLY (by design) |

**Note:** Page is explicitly labeled "SOLO REFERENCIA" (reference only). No edit actions. This is **correct per architecture** — WEB monitors, Qt edits.

**Issue:** Page is **NOT in the router** — unreachable from navigation.

---

### 3.5 Analyze — `pages/Analyze.jsx`

**Status: WORKING** (but unreachable)

| Aspect | Detail |
|--------|--------|
| **Data source** | `useSystemStore` → `getAnalyzers()` → `GET /api/v1/analyzers` (500ms polling) |
| **Backend** | Verified in `api/routers/analyzers.py` |

| Component | Status |
|-----------|--------|
| Stats cards (total, active, matching) | WORKING |
| Energy Detector (level, score, thresholds) | WORKING |
| Analyzer cards by state (BAJADA, BASE_GOLPE, ATAQUE, BRAKE) | WORKING |
| Filter buttons (all/active/matching) | State exists but **no filtering logic** — PARTIAL |

**Issue:** Page is **NOT in the router** — unreachable from navigation.

---

### 3.6 Cues — `pages/Cues.jsx`

**Status: WORKING** (but unreachable)

| Aspect | Detail |
|--------|--------|
| **Data source** | `useSystemStore` → `getCueStatus()` → `GET /api/v1/cues` (1s polling) |
| **Actions** | `fireCue()` → `POST /api/v1/cues/fire`, `killCues()` → `DELETE /api/v1/cues/kill` |
| **Backend** | All verified in `api/routers/cues.py` |

| Component | Status |
|-----------|--------|
| Active cues display | WORKING |
| Engine status (modules_active, total_updates) | WORKING |
| Cue grid (fire/force fire) | WORKING |
| Kill All confirmation dialog | WORKING |

**Issue:** Page is **NOT in the router** — unreachable from navigation.

---

### 3.7 Network — `pages/Network.jsx`

**Status: WORKING** (but unreachable)

| Aspect | Detail |
|--------|--------|
| **Data source** | `getNetworkInterfaces()` → `GET /api/v1/network/interfaces` |
| **Actions** | Set interface, set console target, ping host |
| **Backend** | All verified in `api/routers/network.py` |

| Component | Status |
|-----------|--------|
| Interface list + selection | WORKING |
| Console IP/port configuration | WORKING |
| Ping tool | WORKING |

**Issue:** Page is **NOT in the router** — unreachable from navigation.

---

### 3.8 Presets — `pages/Presets.jsx`

**Status: WORKING** (but unreachable)

| Aspect | Detail |
|--------|--------|
| **Data source** | `listPresets()` → `GET /api/v1/presets` |
| **Actions** | Save preset, load preset with options |
| **Backend** | All verified in `api/routers/presets.py` |

| Component | Status |
|-----------|--------|
| Preset list grid | WORKING |
| Save dialog | WORKING |
| Load dialog (with network/Avolites toggles) | WORKING |

**Issue:** Page is **NOT in the router** — unreachable from navigation.

---

### 3.9 Config (legacy) — `pages/Config.jsx`

**Status: DEAD** (replaced by ConfigPro)

Not referenced in router. ConfigPro serves `/config` route instead.

---

### 3.10 App.jsx (Vision standalone)

**Status: DEAD** (orphan)

Separate vision app using `visionAPI` with CameraSelector, CameraStream, ZoneEditor components. Not mounted by `main.jsx` (which uses RouterProvider). These components exist but are unused in the current app.

---

## 4. Backend Endpoints — Cross-Reference

### 4.1 Endpoints USED by WEB

| Endpoint | Method | Used By | Backend Exists? |
|----------|--------|---------|-----------------|
| `/api/v1/status/unified` | GET | Home, Vision, Calendar | Yes (forwards to `:8010/core/snapshot`) |
| `/api/v1/stream` | GET (SSE) | Home | Yes |
| `/api/v1/calendar/week` | GET | Calendar | Yes |
| `/api/v1/calendar/status` | GET | Calendar | Yes |
| `/api/v1/calendar/go` | POST | Calendar | Yes |
| `/api/v1/calendar/extend` | POST | Calendar | Yes |
| `/api/v1/calendar/override` | POST | Calendar | Yes |
| `/api/v1/calendar/override/stop` | POST | Calendar | Yes |
| `/api/v1/calendar/auto` | POST | Calendar | Yes |
| `/api/v1/calendar/control_mode` | POST | Calendar | Yes |
| `/api/v1/calendar/force_manual` | POST | Calendar | Yes |
| `/api/v1/calendar/save` | POST | Calendar | Yes |
| `/api/v1/config/avolites` | GET/POST | ConfigPro | Yes |
| `/api/v1/config/modules` | GET/POST | ConfigPro | Yes |
| `/api/v1/analyzers` | GET | Analyze | Yes |
| `/api/v1/analyzers/active` | GET | Analyze (defined, unused) | Yes |
| `/api/v1/analyzers/matching` | GET | Analyze (defined, unused) | Yes |
| `/api/v1/cues` | GET | Cues | Yes |
| `/api/v1/cues/fire` | POST | Cues | Yes |
| `/api/v1/cues/kill` | DELETE | Cues | Yes |
| `/api/v1/network/interfaces` | GET | Network | Yes |
| `/api/v1/network/interface` | POST | Network | Yes |
| `/api/v1/network/console` | POST | Network | Yes |
| `/api/v1/network/ping` | POST | Network | Yes |
| `/api/v1/presets` | GET | Presets | Yes |
| `/api/v1/save` | POST | Presets | Yes |
| `/api/v1/load` | POST | Presets | Yes |
| `/api/v1/vision/frame/{id}` | GET | Vision | Yes (proxy to Flask :5000) |
| `/api/v1/status` | GET | useSystemStore (legacy) | Yes |
| `/health` | GET | status.js (defined, unused by pages) | Yes |

### 4.2 Backend Endpoints NOT USED by WEB

| Endpoint | Method | Backend Location |
|----------|--------|-----------------|
| `/api/v1/config/audio` | GET | config router |
| `/api/v1/config/state` | GET | config router |
| `/api/v1/alerts` | GET | alerts router |
| `/api/v1/status/system` | GET | system_health router |
| `/api/v1/status/system/errors` | GET | system_health router |
| `/api/v1/vision/status` | GET | vision proxy |
| `/api/v1/vision/stream/{id}` | GET | vision proxy |
| `/vision/devices` | GET | Flask direct |
| `/vision/zones/{id}` | GET/POST | Flask direct |
| `/vision/detections/{id}` | GET | Flask direct |
| `/vision/camera/{id}/start` | POST | Flask direct |
| `/vision/camera/{id}/stop` | POST | Flask direct |
| `/core/calendar/force_block` | POST | CORE HTTP |

---

## 5. Placeholder & Mock Data Usage

| Location | Value | Type | Issue |
|----------|-------|------|-------|
| Home.jsx `val()` | `'---'` | Fallback | **Acceptable** — graceful null handling |
| Home.jsx version | `v8.0` | Hardcoded | Should read from `status.version` |
| Home.jsx Red Local LED | `color="green"` | Hardcoded | Always green regardless of network state |
| Home.jsx cameras | `['HAZE','DJ','ARTIST']` | Hardcoded | Should derive from `status.vision.cameras` |
| ConfigPro MAC | `'---'` | Hardcoded | Never fetched from backend |
| ConfigPro protocol | `'HTTP'` default | Local state | Never persisted — **MOCK** |
| ConfigPro timeout | Empty string | Local state | Never persisted — **MOCK** |
| ConfigPro NIC | `'Auto'` default | Local state | Never persisted — **MOCK** |
| ConfigPro cameras | Local state object | Local state | Never persisted — **MOCK** |
| Vision camera types | 3 hardcoded types | Hardcoded | Should derive from vision API |

---

## 6. Dead Components

| Component | File | Issue |
|-----------|------|-------|
| `App.jsx` | `src/App.jsx` | Vision standalone app, not mounted |
| `CameraSelector.jsx` | `src/components/` | Only used by orphan App.jsx |
| `CameraStream.jsx` | `src/components/` | Only used by orphan App.jsx |
| `HazeEditor.jsx` | `src/components/` | Only used by orphan App.jsx |
| `PeopleEditor.jsx` | `src/components/` | Only used by orphan App.jsx |
| `TrackingEditor.jsx` | `src/components/` | Only used by orphan App.jsx |
| `ZoneEditor.jsx` | `src/components/` | Only used by orphan App.jsx |
| `ZoneProperties.jsx` | `src/components/` | Only used by orphan App.jsx |
| `Config.jsx` | `src/pages/` | Replaced by ConfigPro |
| `911-fiesta-v7.html` | `webapp/` | Legacy standalone HTML |
| `911-fiesta-calendar-v2.html` | `webapp/` | Legacy standalone HTML |

---

## 7. Specific Section Audits

### 7.1 Control Room Panel (Home)

**Verdict: WORKING with 2 dead buttons**

- All 9 cards read real data from CORE snapshot via unified status API
- SSE connection with automatic fallback to polling — robust
- `Reconectar` button (Avolites) — **DEAD** (no onClick)
- `Restart` button (Vision) — **DEAD** (no onClick)
- Red Local LED hardcoded green — should reflect actual network state

### 7.2 Vision Section

**Verdict: PARTIAL**

- Vision page exists with real data but is **NOT in the router** (unreachable)
- Home page Vision card shows real camera status from snapshot
- Camera frame preview works via proxy
- Zone editing explicitly deferred to Qt UI (correct architecture)
- 8 vision components (`CameraStream`, `ZoneEditor`, etc.) are DEAD — only used by unmounted `App.jsx`

### 7.3 Audio Section

**Verdict: WORKING** (read-only monitoring)

- Audio data displayed in Home page (Placa de Sonido + Clip de Audio cards)
- Real data: device, clipping, silence, level, buffer, latency, peak, clip_l/r, headroom
- Level gauge with clipping indicator
- No audio control actions (correct — CORE controls audio)
- Unused backend endpoints: `/api/v1/config/audio`, `/api/v1/alerts`

### 7.4 Network / Console Section

**Verdict: PARTIAL**

- Dedicated Network page is WORKING but **NOT in the router** (unreachable)
- Home page shows network info (IP, interface, MAC) from snapshot — WORKING
- ConfigPro Red/Consola tab:
  - Avolites IP/port save — WORKING
  - NIC selection — **DEAD** (button not wired)
  - Transport protocol/timeout — **DEAD** (no save endpoint)
  - MAC display — hardcoded `'---'`

### 7.5 Transport Panel

**Verdict: MOCK** (in ConfigPro)

- Home page shows transport protocol, mode, timeout from snapshot — WORKING
- ConfigPro Transport card has protocol selector and timeout input but:
  - No `onClick` on Guardar button
  - No backend endpoint for saving transport config
  - Protocol/timeout are **local state only** — never persisted

### 7.6 Modules Panel

**Verdict: WORKING**

- Home page shows 4 module states (bajada, base_golpe, ataque, brake) — WORKING
- ConfigPro module tabs allow toggling modules ON/OFF — WORKING
- Analyze page shows all analyzers grouped by state with real-time data — WORKING (but unreachable)

---

## 8. State Reading Verification

### How WEB reads system state:

```
Home.jsx
  └─ useUnifiedStatus() hook
      ├─ Primary: EventSource('/api/v1/stream') — SSE
      └─ Fallback: fetch('/api/v1/status/unified') — polling 1s

FastAPI status router
  └─ _fetch_core_snapshot()
      └─ httpx.GET('http://127.0.0.1:8010/core/snapshot')
          └─ Returns full CORE state (cached 100ms)
```

**Verification:** The WEB correctly reads from CORE snapshot. It does NOT generate its own state. The `/api/v1/status/unified` endpoint is a transparent forward of `/core/snapshot` with offline fallback (all nulls when CORE unreachable).

**SSE stream:** Emits CORE snapshot every 500ms. Home page connects via SSE first, falls back to polling with exponential backoff.

---

## 9. Action Triggering Verification

| Action | WEB Trigger | API Endpoint | Backend Implementation |
|--------|-------------|-------------|----------------------|
| Calendar block change | Calendar → GO button | `POST /api/v1/calendar/go` | Forwards to CORE `:8010/core/calendar/go` |
| Calendar extend | Calendar → Extend button | `POST /api/v1/calendar/extend` | Forwards to CORE |
| Calendar override | Calendar → Override button | `POST /api/v1/calendar/override` | Forwards to CORE |
| Calendar save schedule | Calendar → Save button | `POST /api/v1/calendar/save` | Forwards to CORE |
| Toggle auto/manual | Calendar → AUTO button | `POST /api/v1/calendar/auto` | Forwards to CORE |
| Force manual mode | Calendar → Force Manual | `POST /api/v1/calendar/force_manual` | Forwards to CORE |
| Fire cue | Cues → Fire button | `POST /api/v1/cues/fire` | CueEngine.fire() |
| Kill cues | Cues → Kill All | `DELETE /api/v1/cues/kill` | CueEngine.kill() |
| Toggle module | ConfigPro → Module click | `POST /api/v1/config/modules` | Updates module_config |
| Save Avolites | ConfigPro → Guardar | `POST /api/v1/config/avolites` | Updates Avolites config |
| Save offset | ConfigPro → Aplicar Offset | `POST /api/v1/config/avolites` | Updates cue_offset |
| Set network interface | Network → Interface click | `POST /api/v1/network/interface` | Sets active NIC |
| Set console target | Network → Set Console | `POST /api/v1/network/console` | Updates Avolites target |
| Ping host | Network → Ping button | `POST /api/v1/network/ping` | ICMP ping |
| Save preset | Presets → Save | `POST /api/v1/save` | Saves JSON file |
| Load preset | Presets → Load | `POST /api/v1/load` | Loads JSON file |
| Vision restart | Home → Restart button | **None** | **NOT WIRED** |
| Titan reconnect | Home → Reconectar button | **None** | **NOT WIRED** |

---

## 10. Classification Summary

| Page | Status | Notes |
|------|--------|-------|
| **Home** (Control Room) | **WORKING** | 2 dead buttons (Reconectar, Restart). Red Local LED hardcoded. |
| **Calendar** | **WORKING** | Full 3-tab implementation. All 10 API actions verified. |
| **ConfigPro** | **PARTIAL** | Avolites + modules work. Transport/NIC/cameras are MOCK (no save). 5 dead buttons. |
| **Vision** | **PARTIAL** | Real data + frames work. NOT IN ROUTER. Reference-only by design. |
| **Analyze** | **WORKING** | Real-time 500ms polling. NOT IN ROUTER. Filter buttons not wired. |
| **Cues** | **WORKING** | Fire/kill fully functional. NOT IN ROUTER. |
| **Network** | **WORKING** | All 4 API actions work. NOT IN ROUTER. |
| **Presets** | **WORKING** | Save/load fully functional. NOT IN ROUTER. |
| **Config** (legacy) | **DEAD** | Replaced by ConfigPro. Not in router. |
| **App.jsx** (vision standalone) | **DEAD** | Not mounted. 8 components orphaned. |

---

## 11. Priority Fixes

### P0 — Critical (blocking functionality)

| # | Issue | Fix |
|---|-------|-----|
| 1 | **6 pages not in router** — Vision, Analyze, Cues, Network, Presets are fully built but unreachable | Add routes to `router.jsx` and navigation links to `Layout.jsx` |

### P1 — High (dead UI elements)

| # | Issue | Fix |
|---|-------|-----|
| 2 | **Home: Reconectar button** — no onClick handler | Wire to Avolites reconnect API or remove |
| 3 | **Home: Restart button** — no onClick handler | Wire to vision restart API or remove |
| 4 | **ConfigPro: Aplicar NIC** — no onClick handler | Wire to `POST /api/v1/network/interface` |
| 5 | **ConfigPro: Transport Guardar** — no onClick, no backend | Create transport config endpoint or remove |
| 6 | **ConfigPro: Camera Test/Save** — no onClick, no backend | Create camera config endpoints or remove |

### P2 — Medium (mock data in production)

| # | Issue | Fix |
|---|-------|-----|
| 7 | **ConfigPro: Transport** — protocol/timeout are local state, never saved | Wire to backend or mark as read-only |
| 8 | **ConfigPro: NIC select** — local state, never saved | Use network API data |
| 9 | **ConfigPro: Camera forms** — local state, never saved | Create backend endpoint or remove forms |
| 10 | **ConfigPro: MAC** — hardcoded `'---'` | Read from unified status `network.mac` |
| 11 | **Home: Red Local LED** — always green | Use `status.network` to derive actual state |
| 12 | **Home: version** — hardcoded `v8.0` | Read from status/snapshot |
| 13 | **Analyze: filter buttons** — state exists but no filtering logic | Implement filter or remove buttons |

### P3 — Low (cleanup)

| # | Issue | Fix |
|---|-------|-----|
| 14 | **Dead components** — 8 vision components unused | Remove or integrate into Vision page |
| 15 | **Config.jsx** — replaced by ConfigPro | Remove file |
| 16 | **App.jsx** — unmounted vision app | Remove or repurpose |
| 17 | **Legacy HTML files** — `911-fiesta-v7.html`, `911-fiesta-calendar-v2.html` | Remove or archive |
| 18 | **Unused API functions** — `getHealth()`, `getActiveAnalyzers()`, `getMatchingAnalyzers()`, vision API methods | Clean up or wire into UI |
| 19 | **Unused backend endpoints** — `/api/v1/alerts`, `/api/v1/status/system`, `/api/v1/config/audio` | Wire into UI or document as internal-only |

---

## 12. Architecture Compliance

| Rule | Status | Notes |
|------|--------|-------|
| WEB must not run system logic | **PASS** | No DSP, no state machine, no audio processing in WEB |
| WEB only sends commands | **PASS** | All mutations go through API endpoints |
| WEB reads state from CORE snapshot | **PASS** | Via FastAPI proxy → CORE `:8010/core/snapshot` |
| WEB = remote monitoring | **PASS** | Dashboard displays real CORE data |
| WEB = light control | **PASS** | Cue fire/kill, calendar GO/override, module toggles |

**The WEB application correctly follows the CORE/WEB separation architecture.** It does not contain any system logic. All data flows from CORE → FastAPI → WEB, and all commands flow from WEB → FastAPI → CORE.

---

*End of audit report.*
