# neon_styles.py - 911 Fiesta V14 Glass Pro Style System
# ==========================================================
# WEB-aligned glass-morphism design with green accent (#00e676)
# Matches the webapp control-room.css design tokens exactly
# ==========================================================

# ---------------------------------------------------------------------------
# Color Palette — aligned with webapp/src/styles/control-room.css
# ---------------------------------------------------------------------------

# Primary accent (green) — WEB: --green: #00e676
NEON_CYAN = "#00e676"          # Renamed for backward compat; now GREEN accent
NEON_CYAN_DARK = "#00c864"
NEON_CYAN_GLOW = "rgba(0, 230, 118, 0.35)"

NEON_GREEN = "#00e676"         # WEB: --green
NEON_GREEN_DARK = "#00c864"
NEON_ORANGE = "#ff9800"        # WEB: --orange
NEON_RED = "#ff5252"           # WEB: --red
NEON_PURPLE = "#9945ff"
NEON_BLUE = "#42a5f5"          # WEB: --blue
NEON_YELLOW = "#ffd740"        # WEB: --yellow
NEON_CYAN_REAL = "#4dd0e1"     # WEB: --cyan (true cyan for info)

# Background colors — WEB glass system
BG_DARK = "#0a0a0f"
BG_PANEL = "rgba(255, 255, 255, 0.05)"    # WEB: --glass
BG_CARD = "rgba(255, 255, 255, 0.05)"     # WEB: --glass
BG_HOVER = "rgba(255, 255, 255, 0.08)"
BG_ACTIVE = "rgba(255, 255, 255, 0.12)"   # WEB: --glass-top

# Solid fallbacks (Qt doesn't always handle rgba in all contexts)
BG_PANEL_SOLID = "#141418"
BG_CARD_SOLID = "#141418"
BG_HOVER_SOLID = "#1c1c22"
BG_INSET_SOLID = "#0e0e14"

# Border colors — WEB glass borders
BORDER = "rgba(255, 255, 255, 0.18)"       # WEB: --glass-b
BORDER_HOVER = "rgba(255, 255, 255, 0.25)" # WEB: --glass-bh
BORDER_SUBTLE = "rgba(255, 255, 255, 0.08)"
BORDER_SOLID = "#2e2e38"

# Text hierarchy — WEB: --t1 through --t4
TEXT_PRIMARY = "#f0f0f0"       # WEB: --t1
TEXT_SECONDARY = "#a6a6a6"     # WEB: --t2 (~65% of f0f0f0)
TEXT_MUTED = "#616161"         # WEB: --t3 (~38%)

# State colors (unchanged — domain-specific)
STATE_BAJADA = "#4CAF50"
STATE_GOLPE = "#2196F3"
STATE_ATAQUE = "#FF5722"
STATE_BRAKE = "#9C27B0"

# Energy colors
ENERGY_BAJA = "#4CAF50"
ENERGY_MEDIA = "#FF9800"
ENERGY_ALTA = "#F44336"

# Status colors — from WEB
STATUS_OK = "#00e676"
STATUS_WARN = "#ffd740"
STATUS_ERR = "#ff5252"
STATUS_OFF = "#8a8a8a"         # WEB: --off

# ---------------------------------------------------------------------------
# Typography — WEB: Space Grotesk / Inter / JetBrains Mono
# ---------------------------------------------------------------------------
FONT_TITLE = "'Space Grotesk', 'Inter', 'Segoe UI', sans-serif"
FONT_BODY = "'Inter', 'Segoe UI', 'SF Pro Display', sans-serif"
FONT_MONO = "'JetBrains Mono', 'Consolas', 'Fira Code', monospace"

# ---------------------------------------------------------------------------
# Spacing — WEB: 4px base scale
# ---------------------------------------------------------------------------
S_XS = 4
S_SM = 8
S_MD = 12
S_BASE = 16
S_LG = 20
S_XL = 24
S_2XL = 32

# Border radius — WEB scale
R_SM = 8
R_MD = 12
R_LG = 16
R_XL = 20
R_2XL = 24

# ---------------------------------------------------------------------------
# Card / Grid — WEB: .g card tokens for workspace layout
# ---------------------------------------------------------------------------
CARD_BACKGROUND = BG_CARD_SOLID        # WEB: --glass solid fallback
CARD_BORDER = BORDER_SOLID             # WEB: --glass-b solid fallback
CARD_PADDING = S_XL                    # 24px — WEB: .g padding
CARD_RADIUS = R_XL                     # 20px — WEB: .g border-radius
GRID_SPACING = S_LG                    # 20px — WEB: card grid gap

# ---------------------------------------------------------------------------
# Main Window Stylesheet — dark canvas
# ---------------------------------------------------------------------------
MAIN_WINDOW_STYLE = f"""
QMainWindow {{
    background: {BG_DARK};
}}
QWidget {{
    background: transparent;
    color: {TEXT_PRIMARY};
    font-family: {FONT_BODY};
    font-size: 12px;
}}
"""

# ---------------------------------------------------------------------------
# Tab Widget — WEB: .tab / .tab.on
# Pill-shaped tabs with green active indicator
# ---------------------------------------------------------------------------
TAB_WIDGET_STYLE = f"""
QTabWidget::pane {{
    background: {BG_PANEL_SOLID};
    border: 1px solid {BORDER_SOLID};
    border-radius: {R_MD}px;
    margin-top: -1px;
}}
QTabBar::tab {{
    background: {BG_PANEL_SOLID};
    color: {TEXT_MUTED};
    border: 1px solid {BORDER_SOLID};
    border-bottom: none;
    border-top-left-radius: {R_MD}px;
    border-top-right-radius: {R_MD}px;
    padding: 11px 18px;
    margin-right: 2px;
    font-weight: 500;
    font-size: 13px;
    font-family: {FONT_BODY};
}}
QTabBar::tab:selected {{
    background: #0d1a10;
    color: {NEON_GREEN};
    border: 1px solid rgba(0, 230, 118, 0.30);
    border-bottom: 2px solid {NEON_GREEN};
}}
QTabBar::tab:hover:!selected {{
    background: {BG_HOVER_SOLID};
    color: {TEXT_SECONDARY};
    border-color: #3a3a45;
}}
"""

# ---------------------------------------------------------------------------
# Frame/Panel — WEB: .g (glass card)
# ---------------------------------------------------------------------------
PANEL_STYLE = f"""
QFrame {{
    background: {BG_PANEL_SOLID};
    border: 1px solid {BORDER_SOLID};
    border-radius: {R_XL}px;
}}
QFrame:hover {{
    border: 1px solid #3e5e3e;
}}
"""

# ---------------------------------------------------------------------------
# Card — WEB: .g (glass card) with hover lift
# ---------------------------------------------------------------------------
CARD_STYLE = f"""
QFrame#AnalyzerCard {{
    background: {BG_CARD_SOLID};
    border: 1px solid {BORDER_SOLID};
    border-radius: {R_XL}px;
    padding: {S_SM}px;
}}
QFrame#AnalyzerCard:hover {{
    border: 1px solid #3e5e3e;
    background: {BG_HOVER_SOLID};
}}
"""

# ---------------------------------------------------------------------------
# Button — WEB: .key (keycap style with green gradient)
# ---------------------------------------------------------------------------
BUTTON_STYLE = f"""
QPushButton {{
    background: {BG_CARD_SOLID};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SOLID};
    border-radius: 10px;
    padding: {S_MD}px {S_XL}px;
    font-weight: 600;
    font-size: 12px;
    font-family: {FONT_BODY};
}}
QPushButton:hover {{
    background: {BG_HOVER_SOLID};
    border: 1px solid #3e5e3e;
    color: {NEON_GREEN};
}}
QPushButton:pressed {{
    background: #0d1a10;
    border: 1px solid {NEON_GREEN};
}}
QPushButton:disabled {{
    background: {BG_DARK};
    color: {TEXT_MUTED};
    border: 1px solid #1a1a20;
}}
"""

# ---------------------------------------------------------------------------
# Primary Button — WEB: .key (green keycap with glow)
# ---------------------------------------------------------------------------
BUTTON_PRIMARY_STYLE = f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(0, 230, 118, 0.25), stop:1 rgba(0, 200, 100, 0.20));
    color: {NEON_GREEN};
    border: 1px solid rgba(0, 230, 118, 0.30);
    border-radius: 10px;
    padding: {S_MD}px {S_XL}px;
    font-weight: 700;
    font-size: 13px;
    font-family: {FONT_BODY};
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(0, 230, 118, 0.35), stop:1 rgba(0, 200, 100, 0.30));
    border: 1px solid rgba(0, 230, 118, 0.50);
}}
QPushButton:pressed {{
    background: rgba(0, 230, 118, 0.15);
}}
"""

# ---------------------------------------------------------------------------
# Danger Button — WEB: .key-danger
# ---------------------------------------------------------------------------
BUTTON_DANGER_STYLE = f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(255, 82, 82, 0.25), stop:1 rgba(200, 50, 50, 0.20));
    color: {NEON_RED};
    border: 1px solid rgba(255, 82, 82, 0.30);
    border-radius: 10px;
    padding: {S_MD}px {S_XL}px;
    font-weight: 700;
    font-size: 13px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(255, 82, 82, 0.35), stop:1 rgba(200, 50, 50, 0.30));
    border: 1px solid rgba(255, 82, 82, 0.50);
}}
"""

# ---------------------------------------------------------------------------
# Progress Bar — WEB: .gauge / .gauge-fill (green→cyan gradient)
# ---------------------------------------------------------------------------
PROGRESS_BAR_STYLE = f"""
QProgressBar {{
    background: {BG_DARK};
    border: 1px solid {BORDER_SOLID};
    border-radius: 4px;
    text-align: center;
    color: {TEXT_SECONDARY};
    font-size: 10px;
    max-height: 6px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {NEON_GREEN}, stop:1 #4dd0e1);
    border-radius: 3px;
}}
"""

# ---------------------------------------------------------------------------
# Slider — WEB: green accent, smooth handle
# ---------------------------------------------------------------------------
SLIDER_STYLE = f"""
QSlider::groove:horizontal {{
    background: {BG_DARK};
    border: 1px solid {BORDER_SOLID};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {NEON_GREEN}, stop:1 {NEON_GREEN_DARK});
    border: 1px solid {NEON_GREEN};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    background: {NEON_GREEN};
    border: 2px solid #40ff90;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {NEON_GREEN_DARK}, stop:1 {NEON_GREEN});
    border-radius: 3px;
}}
QSlider::groove:vertical {{
    background: {BG_DARK};
    border: 1px solid {BORDER_SOLID};
    width: 6px;
    border-radius: 3px;
}}
QSlider::handle:vertical {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {NEON_GREEN}, stop:1 {NEON_GREEN_DARK});
    border: 1px solid {NEON_GREEN};
    width: 16px;
    height: 16px;
    margin: 0 -6px;
    border-radius: 8px;
}}
QSlider::sub-page:vertical {{
    background: qlineargradient(x1:0, y1:1, x2:0, y2:0,
        stop:0 {NEON_GREEN_DARK}, stop:1 {NEON_GREEN});
    border-radius: 3px;
}}
"""

# ---------------------------------------------------------------------------
# ComboBox — WEB: input styles
# ---------------------------------------------------------------------------
COMBOBOX_STYLE = f"""
QComboBox {{
    background: {BG_INSET_SOLID};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SOLID};
    border-radius: 10px;
    padding: {S_MD}px {S_BASE}px;
    font-size: 13px;
    font-family: {FONT_MONO};
    min-width: 100px;
}}
QComboBox:hover {{
    border: 1px solid #3e5e3e;
}}
QComboBox:focus {{
    border: 1px solid rgba(0, 230, 118, 0.40);
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {TEXT_SECONDARY};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {BG_PANEL_SOLID};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SOLID};
    border-radius: 10px;
    selection-background-color: #0d1a10;
    selection-color: {NEON_GREEN};
}}
"""

# ---------------------------------------------------------------------------
# LineEdit — WEB: input with focus green glow
# ---------------------------------------------------------------------------
LINEEDIT_STYLE = f"""
QLineEdit {{
    background: {BG_INSET_SOLID};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SOLID};
    border-radius: 10px;
    padding: {S_MD}px {S_BASE}px;
    font-size: 13px;
    font-family: {FONT_MONO};
}}
QLineEdit:focus {{
    border: 1px solid rgba(0, 230, 118, 0.40);
    background: #0c0c12;
}}
QLineEdit:hover {{
    border: 1px solid #3e5e3e;
}}
"""

# ---------------------------------------------------------------------------
# SpinBox — WEB: input style
# ---------------------------------------------------------------------------
SPINBOX_STYLE = f"""
QSpinBox, QDoubleSpinBox {{
    background: {BG_INSET_SOLID};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SOLID};
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 13px;
    font-family: {FONT_MONO};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid rgba(0, 230, 118, 0.40);
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    background: {BG_CARD_SOLID};
    border: none;
    border-left: 1px solid {BORDER_SOLID};
    border-top-right-radius: 9px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: {BG_CARD_SOLID};
    border: none;
    border-left: 1px solid {BORDER_SOLID};
    border-bottom-right-radius: 9px;
}}
"""

# ---------------------------------------------------------------------------
# Labels — WEB typography hierarchy
# ---------------------------------------------------------------------------
LABEL_TITLE_STYLE = f"""
QLabel {{
    color: {NEON_GREEN};
    font-weight: 700;
    font-size: 14px;
    font-family: {FONT_TITLE};
    background: transparent;
    border: none;
}}
"""

LABEL_SECTION_STYLE = f"""
QLabel {{
    color: {TEXT_PRIMARY};
    font-weight: 600;
    font-size: 12px;
    font-family: {FONT_TITLE};
    background: transparent;
    border: none;
    letter-spacing: 1px;
}}
"""

LABEL_NORMAL_STYLE = f"""
QLabel {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
    font-family: {FONT_BODY};
    background: transparent;
    border: none;
}}
"""

# ---------------------------------------------------------------------------
# GroupBox — WEB: panel title style
# ---------------------------------------------------------------------------
GROUPBOX_STYLE = f"""
QGroupBox {{
    background: {BG_PANEL_SOLID};
    border: 1px solid {BORDER_SOLID};
    border-radius: {R_LG}px;
    margin-top: {S_MD}px;
    padding-top: {S_SM}px;
    font-weight: 600;
    font-size: 11px;
    font-family: {FONT_TITLE};
}}
QGroupBox::title {{
    color: {NEON_GREEN};
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: {S_MD}px;
    padding: 0 {S_SM}px;
    background: {BG_PANEL_SOLID};
    font-family: {FONT_TITLE};
    letter-spacing: 1px;
}}
"""

# ---------------------------------------------------------------------------
# ScrollArea — minimal, dark
# ---------------------------------------------------------------------------
SCROLLAREA_STYLE = f"""
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: {BG_DARK};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #2e2e38;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(0, 230, 118, 0.30);
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {BG_DARK};
    height: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #2e2e38;
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: rgba(0, 230, 118, 0.30);
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
"""

# ---------------------------------------------------------------------------
# Checkbox — WEB: toggle-like with green checked state
# ---------------------------------------------------------------------------
CHECKBOX_STYLE = f"""
QCheckBox {{
    color: {TEXT_PRIMARY};
    font-size: 12px;
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {BORDER_SOLID};
    border-radius: 4px;
    background: {BG_INSET_SOLID};
}}
QCheckBox::indicator:checked {{
    background: rgba(0, 230, 118, 0.25);
    border: 1px solid {NEON_GREEN};
}}
QCheckBox::indicator:hover {{
    border: 1px solid #3e5e3e;
}}
"""

# ---------------------------------------------------------------------------
# LED Indicator — WEB: .led with glow
# ---------------------------------------------------------------------------
def led_style(color: str, size: int = 12, glow: bool = True) -> str:
    """Generate LED indicator style — matches WEB .led component."""
    return f"""
    QLabel {{
        background: qradialgradient(cx:0.4, cy:0.4, radius:0.5, fx:0.3, fy:0.3,
            stop:0 #ffffff, stop:0.3 {color}, stop:1 {color}88);
        border: 2px solid rgba(255, 255, 255, 0.10);
        border-radius: {size // 2}px;
        min-width: {size}px;
        max-width: {size}px;
        min-height: {size}px;
        max-height: {size}px;
    }}
    """


# ---------------------------------------------------------------------------
# State Indicator — WEB: badge with state color and inset style
# ---------------------------------------------------------------------------
def state_indicator_style(state: str) -> str:
    """Generate state indicator style — matches WEB state badge."""
    colors = {
        "BAJADA": STATE_BAJADA,
        "BASE_GOLPE": STATE_GOLPE,
        "ATAQUE": STATE_ATAQUE,
        "BRAKE": STATE_BRAKE,
    }
    color = colors.get(state.upper(), TEXT_SECONDARY)
    return f"""
    QLabel {{
        color: {color};
        font-weight: 700;
        font-size: 24px;
        font-family: {FONT_TITLE};
        background: {BG_INSET_SOLID};
        border: 2px solid {color};
        border-radius: {R_MD}px;
        padding: {S_MD}px;
    }}
    """


# ---------------------------------------------------------------------------
# Energy Indicator — WEB: badge with energy color
# ---------------------------------------------------------------------------
def energy_indicator_style(energy: str) -> str:
    """Generate energy indicator style — matches WEB energy badge."""
    colors = {
        "BAJA": ENERGY_BAJA,
        "MEDIA": ENERGY_MEDIA,
        "ALTA": ENERGY_ALTA,
    }
    color = colors.get(energy.upper(), TEXT_SECONDARY)
    return f"""
    QLabel {{
        color: {color};
        font-weight: 700;
        font-size: 18px;
        font-family: {FONT_MONO};
        background: {BG_INSET_SOLID};
        border: 1px solid {color};
        border-radius: {R_SM}px;
        padding: {S_SM}px;
    }}
    """


# ---------------------------------------------------------------------------
# Analyzer Card States — WEB: .g with green/neutral border
# ---------------------------------------------------------------------------
ANALYZER_ACTIVE_STYLE = f"""
QFrame {{
    background: {BG_CARD_SOLID};
    border: 1px solid {NEON_GREEN};
    border-radius: {R_XL}px;
}}
"""

ANALYZER_INACTIVE_STYLE = f"""
QFrame {{
    background: {BG_CARD_SOLID};
    border: 1px solid {BORDER_SOLID};
    border-radius: {R_XL}px;
}}
"""

ANALYZER_PLACEHOLDER_STYLE = f"""
QFrame {{
    background: {BG_DARK};
    border: 1px dashed #3a3a45;
    border-radius: {R_XL}px;
}}
"""

# ---------------------------------------------------------------------------
# VU Meter — WEB: gauge with green→orange→red gradient
# ---------------------------------------------------------------------------
VU_METER_STYLE = f"""
QProgressBar {{
    background: {BG_DARK};
    border: 1px solid {BORDER_SOLID};
    border-radius: 10px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {NEON_GREEN}, stop:0.7 {NEON_ORANGE}, stop:1 {NEON_RED});
    border-radius: 9px;
}}
"""

# ---------------------------------------------------------------------------
# Waveform — WEB: inset panel style
# ---------------------------------------------------------------------------
WAVEFORM_STYLE = f"""
QFrame {{
    background: {BG_INSET_SOLID};
    border: 1px solid {BORDER_SOLID};
    border-radius: {R_MD}px;
}}
"""

# ---------------------------------------------------------------------------
# Sidebar Navigation — WEB: .side (glass nav panel, 68px)
# ---------------------------------------------------------------------------
SIDEBAR_WIDTH = 170          # px – slightly wider than WEB 68px to fit labels
SIDEBAR_STYLE = f"""
#Sidebar {{
    background: {BG_PANEL_SOLID};
    border-right: 1px solid {BORDER_SOLID};
    min-width: {SIDEBAR_WIDTH}px;
    max-width: {SIDEBAR_WIDTH}px;
}}
#Sidebar QLabel[role="section"] {{
    color: {TEXT_MUTED};
    font-size: 10px;
    font-weight: 700;
    font-family: {FONT_TITLE};
    letter-spacing: 1px;
    padding: 18px 14px 6px 14px;
    border: none;
    background: transparent;
}}
#Sidebar QPushButton {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    border-radius: 0px;
    text-align: left;
    padding: 9px 14px;
    font-size: 12px;
    font-weight: 500;
    font-family: {FONT_BODY};
    margin: 0px 6px;
    border-radius: {R_SM}px;
}}
#Sidebar QPushButton:hover {{
    background: {BG_HOVER_SOLID};
    color: {TEXT_PRIMARY};
}}
#Sidebar QPushButton[active="true"] {{
    background: rgba(0, 230, 118, 0.08);
    color: {NEON_GREEN};
    border-left: 3px solid {NEON_GREEN};
    border-radius: 0 {R_SM}px {R_SM}px 0;
    margin-left: 0px;
    padding-left: 11px;
}}
"""

# ---------------------------------------------------------------------------
# Workspace Card — WEB: .g (glass card) wrapper for module containers
# ---------------------------------------------------------------------------
WORKSPACE_CARD_STYLE = f"""
#WorkspaceCard {{
    background: {CARD_BACKGROUND};
    border: 1px solid {CARD_BORDER};
    border-radius: {CARD_RADIUS}px;
    padding: 0px;
}}
#WorkspaceCard > QLabel[role="card-title"] {{
    color: {TEXT_PRIMARY};
    font-weight: 600;
    font-size: 14px;
    font-family: {FONT_TITLE};
    padding: {S_BASE}px {CARD_PADDING}px {S_SM}px {CARD_PADDING}px;
    border: none;
    background: transparent;
}}
"""

# ---------------------------------------------------------------------------
# Header / TopBar — WEB: header flex row
# ---------------------------------------------------------------------------
HEADER_STYLE = f"""
#TopBar {{
    background: {BG_PANEL_SOLID};
    border-bottom: 1px solid {BORDER_SOLID};
    min-height: 48px;
    max-height: 48px;
}}
#TopBar QLabel {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
    font-family: {FONT_BODY};
    border: none;
    background: transparent;
}}
"""

# ---------------------------------------------------------------------------
# Complete Application Stylesheet — get_full_stylesheet()
# ---------------------------------------------------------------------------
def get_full_stylesheet() -> str:
    """Returns the complete application stylesheet aligned with WEB UI."""
    return f"""
    {MAIN_WINDOW_STYLE}
    {TAB_WIDGET_STYLE}
    {SIDEBAR_STYLE}
    {WORKSPACE_CARD_STYLE}
    {HEADER_STYLE}
    {BUTTON_STYLE}
    {PROGRESS_BAR_STYLE}
    {SLIDER_STYLE}
    {COMBOBOX_STYLE}
    {LINEEDIT_STYLE}
    {SPINBOX_STYLE}
    {GROUPBOX_STYLE}
    {SCROLLAREA_STYLE}
    {CHECKBOX_STYLE}
    """


# ---------------------------------------------------------------------------
# Analyzer Card Style Builder
# ---------------------------------------------------------------------------
def build_analyzer_card_style(is_active: bool, is_placeholder: bool = False) -> str:
    """Build stylesheet for analyzer module card."""
    if is_placeholder:
        return ANALYZER_PLACEHOLDER_STYLE
    elif is_active:
        return ANALYZER_ACTIVE_STYLE
    else:
        return ANALYZER_INACTIVE_STYLE


# ---------------------------------------------------------------------------
# Health Monitor Styles — WEB: .g and .gp panels
# ---------------------------------------------------------------------------
HEALTH_PANEL_STYLE = f"""
QFrame {{
    background: {BG_PANEL_SOLID};
    border: 1px solid {BORDER_SOLID};
    border-radius: {R_XL}px;
}}
"""

HEALTH_SECTION_STYLE = f"""
QFrame {{
    background: {BG_CARD_SOLID};
    border: 1px solid {BORDER_SOLID};
    border-radius: {R_LG}px;
}}
"""

# ---------------------------------------------------------------------------
# TAP Tempo Button — WEB: .key style circular
# ---------------------------------------------------------------------------
TAP_BUTTON_STYLE = f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(66, 165, 245, 0.25), stop:1 rgba(50, 130, 200, 0.20));
    color: #42a5f5;
    border: 2px solid rgba(66, 165, 245, 0.30);
    border-radius: 30px;
    font-weight: 700;
    font-size: 16px;
    font-family: {FONT_TITLE};
    min-width: 60px;
    min-height: 60px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(66, 165, 245, 0.35), stop:1 rgba(50, 130, 200, 0.30));
    border: 2px solid rgba(66, 165, 245, 0.50);
}}
QPushButton:pressed {{
    background: rgba(66, 165, 245, 0.15);
}}
"""

PULSE_LED_STYLE = led_style(NEON_BLUE, 16, True)
KICK_LED_STYLE = led_style(NEON_GREEN, 16, True)

# ---------------------------------------------------------------------------
# Badge helper — WEB: .b badges with color variants
# ---------------------------------------------------------------------------
def badge_style(color: str = NEON_GREEN) -> str:
    """Generate badge/pill style — matches WEB .b component."""
    return f"""
    QLabel {{
        color: {color};
        font-weight: 600;
        font-size: 11px;
        font-family: {FONT_MONO};
        background: {BG_INSET_SOLID};
        border: 1px solid {color};
        border-radius: {R_SM}px;
        padding: 4px 12px;
    }}
    """


# ---------------------------------------------------------------------------
# Card Style helper — for use in health_tab, module_card, etc.
# ---------------------------------------------------------------------------
def glass_card_style(padding: int = S_XL) -> str:
    """Generate glass card style — matches WEB .g component."""
    return (
        f"QFrame{{ background:{BG_CARD_SOLID}; border:1px solid {BORDER_SOLID}; "
        f"border-radius:{R_XL}px; padding:{padding}px; }}"
    )


def glass_panel_style(padding: int = S_BASE) -> str:
    """Generate glass panel style — matches WEB .gp component."""
    return (
        f"QFrame{{ background:{BG_CARD_SOLID}; border:1px solid {BORDER_SOLID}; "
        f"border-radius:{R_LG}px; padding:{padding}px; }}"
    )


def inset_style(padding: int = S_MD) -> str:
    """Generate inset panel style — matches WEB .inset component."""
    return (
        f"QFrame{{ background:{BG_INSET_SOLID}; border:1px solid #1e1e28; "
        f"border-radius:{R_MD}px; padding:{padding}px; }}"
    )


# ---------------------------------------------------------------------------
# Exports — full backward compatibility
# ---------------------------------------------------------------------------
__all__ = [
    # Colors
    'NEON_CYAN', 'NEON_GREEN', 'NEON_ORANGE', 'NEON_RED', 'NEON_PURPLE', 'NEON_BLUE',
    'NEON_YELLOW', 'NEON_CYAN_REAL',
    'BG_DARK', 'BG_PANEL', 'BG_CARD', 'BG_HOVER', 'BG_ACTIVE',
    'BG_PANEL_SOLID', 'BG_CARD_SOLID', 'BG_HOVER_SOLID', 'BG_INSET_SOLID',
    'BORDER', 'BORDER_HOVER', 'BORDER_SOLID',
    'TEXT_PRIMARY', 'TEXT_SECONDARY', 'TEXT_MUTED',
    'STATUS_OK', 'STATUS_WARN', 'STATUS_ERR', 'STATUS_OFF',
    'STATE_BAJADA', 'STATE_GOLPE', 'STATE_ATAQUE', 'STATE_BRAKE',
    'ENERGY_BAJA', 'ENERGY_MEDIA', 'ENERGY_ALTA',
    # Typography
    'FONT_TITLE', 'FONT_BODY', 'FONT_MONO',
    # Spacing
    'S_XS', 'S_SM', 'S_MD', 'S_BASE', 'S_LG', 'S_XL', 'S_2XL',
    'R_SM', 'R_MD', 'R_LG', 'R_XL', 'R_2XL',
    # Card / Grid tokens
    'CARD_BACKGROUND', 'CARD_BORDER', 'CARD_PADDING', 'CARD_RADIUS', 'GRID_SPACING',
    'SIDEBAR_WIDTH',
    # Stylesheets
    'MAIN_WINDOW_STYLE', 'TAB_WIDGET_STYLE', 'PANEL_STYLE', 'CARD_STYLE',
    'SIDEBAR_STYLE', 'WORKSPACE_CARD_STYLE', 'HEADER_STYLE',
    'BUTTON_STYLE', 'BUTTON_PRIMARY_STYLE', 'BUTTON_DANGER_STYLE',
    'PROGRESS_BAR_STYLE', 'SLIDER_STYLE', 'COMBOBOX_STYLE',
    'LINEEDIT_STYLE', 'SPINBOX_STYLE', 'GROUPBOX_STYLE', 'SCROLLAREA_STYLE',
    'CHECKBOX_STYLE',
    'LABEL_TITLE_STYLE', 'LABEL_SECTION_STYLE', 'LABEL_NORMAL_STYLE',
    'VU_METER_STYLE', 'WAVEFORM_STYLE',
    'TAP_BUTTON_STYLE', 'PULSE_LED_STYLE', 'KICK_LED_STYLE',
    'HEALTH_PANEL_STYLE', 'HEALTH_SECTION_STYLE',
    'ANALYZER_ACTIVE_STYLE', 'ANALYZER_INACTIVE_STYLE', 'ANALYZER_PLACEHOLDER_STYLE',
    # Functions
    'led_style', 'state_indicator_style', 'energy_indicator_style',
    'build_analyzer_card_style', 'get_full_stylesheet',
    'badge_style', 'glass_card_style', 'glass_panel_style', 'inset_style',
]
