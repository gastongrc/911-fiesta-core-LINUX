# neon_styles.py - 911 Fiesta V12 Glass Pro Style System
# ==========================================================
# WEB-aligned design language: glassmorphism, green accent,
# modern typography (Inter / Space Grotesk / JetBrains Mono)
# ==========================================================

# ── Color Palette (aligned to WEB control-room.css) ──────────────────────────

# Primary accent
NEON_GREEN = "#00e676"
NEON_GREEN_DARK = "#00c864"
NEON_GREEN_GLOW = "rgba(0, 230, 118, 0.25)"

# Secondary accents
NEON_CYAN = "#4dd0e1"
NEON_CYAN_DARK = "#3bb8c9"
NEON_CYAN_GLOW = "rgba(77, 208, 225, 0.25)"
NEON_BLUE = "#42a5f5"
NEON_ORANGE = "#ff9800"
NEON_RED = "#ff5252"
NEON_PURPLE = "#9945ff"
NEON_YELLOW = "#ffd740"

# Background colors
BG_DARK = "#0a0a0f"
BG_PANEL = "rgba(255, 255, 255, 0.04)"
BG_CARD = "rgba(255, 255, 255, 0.05)"
BG_HOVER = "rgba(255, 255, 255, 0.08)"
BG_ACTIVE = "rgba(255, 255, 255, 0.10)"

# Solid fallbacks (for widgets that need solid bg)
BG_PANEL_SOLID = "#111116"
BG_CARD_SOLID = "#141419"
BG_HOVER_SOLID = "#1c1c22"
BG_ACTIVE_SOLID = "#222228"

# Text colors (4-level hierarchy from WEB)
TEXT_PRIMARY = "#f0f0f0"
TEXT_SECONDARY = "rgba(240, 240, 240, 0.65)"
TEXT_MUTED = "rgba(240, 240, 240, 0.38)"
TEXT_FAINT = "rgba(240, 240, 240, 0.20)"

# Borders (glass-style)
BORDER_DEFAULT = "rgba(255, 255, 255, 0.12)"
BORDER_MEDIUM = "rgba(255, 255, 255, 0.15)"
BORDER_STRONG = "rgba(255, 255, 255, 0.20)"
BORDER_GREEN = "rgba(0, 230, 118, 0.30)"

# ── Reusable card / inset CSS fragments ───────────────────────────────────────
# Use these in inline setStyleSheet() calls for consistency.

CARD_CSS = (
    "background: rgba(255,255,255,0.04);"
    "border: 1px solid rgba(255,255,255,0.12);"
    "border-radius: 14px;"
)

CARD_HOVER_CSS = (
    "background: rgba(255,255,255,0.06);"
    "border: 1px solid rgba(255,255,255,0.15);"
    "border-radius: 14px;"
)

INSET_CSS = (
    "background: rgba(255,255,255,0.03);"
    "border: 1px solid rgba(255,255,255,0.08);"
    "border-radius: 10px;"
)

# Convenience functions for inline use
def card_frame_css(extra: str = "") -> str:
    """QFrame card style for setStyleSheet(). Pass extra CSS if needed."""
    return f"QFrame{{{CARD_CSS} {extra}}}"

def inset_frame_css(extra: str = "") -> str:
    """QFrame inset panel style for setStyleSheet()."""
    return f"QFrame{{{INSET_CSS} {extra}}}"

# State colors (unchanged — architectural)
STATE_BAJADA = "#4CAF50"
STATE_GOLPE = "#2196F3"
STATE_ATAQUE = "#FF5722"
STATE_BRAKE = "#9C27B0"

# Energy colors (unchanged — architectural)
ENERGY_BAJA = "#4CAF50"
ENERGY_MEDIA = "#FF9800"
ENERGY_ALTA = "#F44336"

# Disabled / off
OFF_COLOR = "#8a8a8a"

# ── Spacing scale (4px base) ─────────────────────────────────────────────────

SP_XS = 4
SP_SM = 8
SP_MD = 12
SP_BASE = 16
SP_LG = 20
SP_XL = 24
SP_2XL = 32

# ── Border-radius scale ──────────────────────────────────────────────────────

RAD_SM = 8
RAD_MD = 12
RAD_LG = 14
RAD_XL = 16
RAD_2XL = 20

# ── Typography ────────────────────────────────────────────────────────────────

FONT_BODY = "'Inter', 'Segoe UI', 'SF Pro Display', sans-serif"
FONT_TITLE = "'Space Grotesk', 'Inter', 'Segoe UI', sans-serif"
FONT_MONO = "'JetBrains Mono', 'Consolas', monospace"

FONT_SIZE_XS = "10px"
FONT_SIZE_SM = "11px"
FONT_SIZE_BASE = "13px"
FONT_SIZE_MD = "14px"
FONT_SIZE_LG = "16px"
FONT_SIZE_XL = "18px"
FONT_SIZE_2XL = "20px"

# ══════════════════════════════════════════════════════════════════════════════
# STYLESHEET DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

# Main window stylesheet
MAIN_WINDOW_STYLE = f"""
QMainWindow {{
    background: {BG_DARK};
}}
QWidget {{
    background: transparent;
    color: {TEXT_PRIMARY};
    font-family: {FONT_BODY};
    font-size: {FONT_SIZE_BASE};
}}
"""

# Tab widget stylesheet — pill-style tabs with green active accent
TAB_WIDGET_STYLE = f"""
QTabWidget::pane {{
    background: {BG_DARK};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RAD_LG}px;
    margin-top: -1px;
}}
QTabBar::tab {{
    background: {BG_PANEL_SOLID};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER_DEFAULT};
    border-bottom: none;
    border-top-left-radius: {RAD_MD}px;
    border-top-right-radius: {RAD_MD}px;
    padding: {SP_MD}px {SP_LG}px;
    margin-right: 2px;
    font-family: {FONT_BODY};
    font-weight: 500;
    font-size: {FONT_SIZE_BASE};
}}
QTabBar::tab:selected {{
    background: rgba(0, 230, 118, 0.08);
    color: {NEON_GREEN};
    border: 1px solid {BORDER_GREEN};
    border-bottom: 1px solid {BG_DARK};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    background: {BG_HOVER_SOLID};
    color: {TEXT_PRIMARY};
    border-color: {BORDER_MEDIUM};
}}
"""

# Frame/Panel stylesheet — glass card appearance (global default)
PANEL_STYLE = f"""
QFrame {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: {RAD_LG}px;
}}
"""

# Card widget stylesheet (for analyzer cards) — glass card
CARD_STYLE = f"""
QFrame#AnalyzerCard {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: {RAD_LG}px;
    padding: {SP_BASE}px;
}}
QFrame#AnalyzerCard:hover {{
    border: 1px solid {BORDER_MEDIUM};
    background: rgba(255,255,255,0.06);
}}
"""

# Button stylesheet — matches WEB "key" buttons
BUTTON_STYLE = f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255,255,255,0.08), stop:1 rgba(255,255,255,0.04));
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_MEDIUM};
    border-radius: 10px;
    padding: {SP_SM}px {SP_BASE}px;
    font-family: {FONT_BODY};
    font-weight: 600;
    font-size: {FONT_SIZE_BASE};
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255,255,255,0.12), stop:1 rgba(255,255,255,0.06));
    border: 1px solid {BORDER_STRONG};
    color: {TEXT_PRIMARY};
}}
QPushButton:pressed {{
    background: rgba(255,255,255,0.04);
    border: 1px solid {BORDER_MEDIUM};
    padding-top: {SP_SM + 1}px;
    padding-bottom: {SP_SM - 1}px;
}}
QPushButton:disabled {{
    background: rgba(255,255,255,0.02);
    color: {TEXT_MUTED};
    border: 1px solid {BORDER_DEFAULT};
}}
"""

# Primary action button (green accent — like WEB .key)
BUTTON_PRIMARY_STYLE = f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(0,230,118,0.25), stop:1 rgba(0,200,100,0.18));
    color: {NEON_GREEN};
    border: 1px solid rgba(0,230,118,0.30);
    border-radius: 10px;
    padding: 10px {SP_LG}px;
    font-family: {FONT_BODY};
    font-weight: 700;
    font-size: {FONT_SIZE_MD};
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(0,230,118,0.35), stop:1 rgba(0,200,100,0.25));
    border: 1px solid rgba(0,230,118,0.45);
}}
QPushButton:pressed {{
    background: rgba(0,230,118,0.15);
    padding-top: 11px;
    padding-bottom: 9px;
}}
"""

# Danger button (red accent — like WEB .key-danger)
BUTTON_DANGER_STYLE = f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255,82,82,0.25), stop:1 rgba(255,82,82,0.15));
    color: {NEON_RED};
    border: 1px solid rgba(255,82,82,0.30);
    border-radius: 10px;
    padding: 10px {SP_LG}px;
    font-family: {FONT_BODY};
    font-weight: 700;
    font-size: {FONT_SIZE_MD};
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255,82,82,0.35), stop:1 rgba(255,82,82,0.25));
    border: 1px solid rgba(255,82,82,0.45);
}}
QPushButton:pressed {{
    background: rgba(255,82,82,0.15);
}}
"""

# Progress bar stylesheet — thin, gradient fill (WEB gauge style)
PROGRESS_BAR_STYLE = f"""
QProgressBar {{
    background: rgba(255,255,255,0.04);
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 4px;
    text-align: center;
    color: {TEXT_MUTED};
    font-family: {FONT_MONO};
    font-size: {FONT_SIZE_XS};
    max-height: 8px;
    min-height: 8px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {NEON_GREEN}, stop:1 {NEON_CYAN});
    border-radius: 3px;
}}
"""

# Slider stylesheet
SLIDER_STYLE = f"""
QSlider::groove:horizontal {{
    background: rgba(255,255,255,0.04);
    border: 1px solid {BORDER_DEFAULT};
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
    border: 2px solid rgba(0,230,118,0.6);
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {NEON_GREEN_DARK}, stop:1 {NEON_GREEN});
    border-radius: 3px;
}}
QSlider::groove:vertical {{
    background: rgba(255,255,255,0.04);
    border: 1px solid {BORDER_DEFAULT};
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

# ComboBox stylesheet
COMBOBOX_STYLE = f"""
QComboBox {{
    background: {BG_CARD_SOLID};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_MEDIUM};
    border-radius: 10px;
    padding: 8px {SP_BASE}px;
    font-family: {FONT_MONO};
    font-size: {FONT_SIZE_BASE};
    min-width: 100px;
}}
QComboBox:hover {{
    border: 1px solid {BORDER_STRONG};
}}
QComboBox:focus {{
    border: 1px solid rgba(0,230,118,0.40);
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_SECONDARY};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {BG_CARD_SOLID};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_MEDIUM};
    border-radius: 10px;
    selection-background-color: rgba(0,230,118,0.10);
    selection-color: {NEON_GREEN};
}}
"""

# LineEdit stylesheet
LINEEDIT_STYLE = f"""
QLineEdit {{
    background: rgba(0,0,0,0.20);
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 10px;
    padding: {SP_SM}px {SP_MD}px;
    font-family: {FONT_MONO};
    font-size: {FONT_SIZE_BASE};
}}
QLineEdit:focus {{
    border: 1px solid rgba(0,230,118,0.40);
}}
QLineEdit:hover {{
    border: 1px solid {BORDER_MEDIUM};
}}
"""

# SpinBox stylesheet
SPINBOX_STYLE = f"""
QSpinBox, QDoubleSpinBox {{
    background: rgba(0,0,0,0.20);
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 10px;
    padding: 6px 10px;
    font-family: {FONT_MONO};
    font-size: {FONT_SIZE_BASE};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid rgba(0,230,118,0.40);
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    background: {BG_HOVER_SOLID};
    border: none;
    border-left: 1px solid {BORDER_DEFAULT};
    border-top-right-radius: 9px;
    width: 20px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: {BG_HOVER_SOLID};
    border: none;
    border-left: 1px solid {BORDER_DEFAULT};
    border-bottom-right-radius: 9px;
    width: 20px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 4px solid {TEXT_SECONDARY};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid {TEXT_SECONDARY};
}}
"""

# Label styles
LABEL_TITLE_STYLE = f"""
QLabel {{
    color: {NEON_GREEN};
    font-family: {FONT_TITLE};
    font-weight: 700;
    font-size: {FONT_SIZE_MD};
    background: transparent;
    border: none;
}}
"""

LABEL_SECTION_STYLE = f"""
QLabel {{
    color: {TEXT_PRIMARY};
    font-family: {FONT_TITLE};
    font-weight: 600;
    font-size: {FONT_SIZE_BASE};
    background: transparent;
    border: none;
}}
"""

LABEL_NORMAL_STYLE = f"""
QLabel {{
    color: {TEXT_SECONDARY};
    font-family: {FONT_BODY};
    font-size: {FONT_SIZE_BASE};
    background: transparent;
    border: none;
}}
"""

# GroupBox stylesheet
GROUPBOX_STYLE = f"""
QGroupBox {{
    background: {BG_PANEL_SOLID};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RAD_LG}px;
    margin-top: {SP_MD}px;
    padding-top: {SP_SM}px;
    font-family: {FONT_TITLE};
    font-weight: 600;
    font-size: {FONT_SIZE_BASE};
}}
QGroupBox::title {{
    color: {NEON_GREEN};
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: {SP_MD}px;
    padding: 0 {SP_SM}px;
    background: {BG_PANEL_SOLID};
}}
"""

# Scroll area stylesheet
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
    background: rgba(255,255,255,0.12);
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(0,230,118,0.30);
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
    background: rgba(255,255,255,0.12);
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: rgba(0,230,118,0.30);
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
"""

# QCheckBox and QRadioButton
CHECKBOX_STYLE = f"""
QCheckBox, QRadioButton {{
    color: {TEXT_PRIMARY};
    font-family: {FONT_BODY};
    font-size: {FONT_SIZE_BASE};
    spacing: {SP_SM}px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER_MEDIUM};
    border-radius: 4px;
    background: rgba(0,0,0,0.20);
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: rgba(0,230,118,0.25);
    border: 1px solid rgba(0,230,118,0.40);
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}
QRadioButton::indicator:checked {{
    border-radius: 8px;
}}
"""

# ── LED indicator styles ──────────────────────────────────────────────────────

def led_style(color: str, size: int = 12, glow: bool = True) -> str:
    """Generate LED indicator style"""
    glow_effect = f"box-shadow: 0 0 8px {color};" if glow else ""
    return f"""
    QLabel {{
        background: qradialgradient(cx:0.4, cy:0.4, radius:0.5, fx:0.3, fy:0.3,
            stop:0 #ffffff, stop:0.3 {color}, stop:1 {color}88);
        border: 1px solid {color};
        border-radius: {size // 2}px;
        min-width: {size}px;
        max-width: {size}px;
        min-height: {size}px;
        max-height: {size}px;
        {glow_effect}
    }}
    """

# ── State indicator styles ────────────────────────────────────────────────────

def state_indicator_style(state: str) -> str:
    """Generate state indicator style based on state name"""
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
        font-family: {FONT_TITLE};
        font-weight: 700;
        font-size: {FONT_SIZE_2XL};
        background: rgba(0,0,0,0.25);
        border: 1px solid {color};
        border-radius: {RAD_MD}px;
        padding: {SP_MD}px;
    }}
    """

def energy_indicator_style(energy: str) -> str:
    """Generate energy indicator style based on energy name"""
    colors = {
        "BAJA": ENERGY_BAJA,
        "MEDIA": ENERGY_MEDIA,
        "ALTA": ENERGY_ALTA,
    }
    color = colors.get(energy.upper(), TEXT_SECONDARY)
    return f"""
    QLabel {{
        color: {color};
        font-family: {FONT_MONO};
        font-weight: 700;
        font-size: {FONT_SIZE_XL};
        background: rgba(0,0,0,0.25);
        border: 1px solid {color};
        border-radius: {RAD_MD}px;
        padding: {SP_SM}px;
    }}
    """

# ── Analyzer card active/inactive styles ─────────────────────────────────────

ANALYZER_ACTIVE_STYLE = f"""
QFrame {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(0,230,118,0.30);
    border-radius: {RAD_LG}px;
    padding: {SP_BASE}px;
}}
"""

ANALYZER_INACTIVE_STYLE = f"""
QFrame {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: {RAD_LG}px;
    padding: {SP_BASE}px;
}}
"""

ANALYZER_PLACEHOLDER_STYLE = f"""
QFrame {{
    background: rgba(255,255,255,0.02);
    border: 1px dashed rgba(255,255,255,0.12);
    border-radius: {RAD_LG}px;
    padding: {SP_BASE}px;
}}
"""

# ── VU Meter styles ───────────────────────────────────────────────────────────

VU_METER_STYLE = f"""
QProgressBar {{
    background: rgba(0,0,0,0.25);
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 4px;
    max-height: 8px;
    min-height: 8px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {NEON_GREEN}, stop:0.7 {NEON_ORANGE}, stop:1 {NEON_RED});
    border-radius: 3px;
}}
"""

# ── Waveform widget style ────────────────────────────────────────────────────

WAVEFORM_STYLE = f"""
QFrame {{
    background: rgba(0,0,0,0.25);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: {RAD_MD}px;
}}
"""

# ── Health monitor widget styles ─────────────────────────────────────────────

HEALTH_PANEL_STYLE = f"""
QFrame {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: {RAD_LG}px;
}}
"""

HEALTH_SECTION_STYLE = f"""
QFrame {{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: {RAD_MD}px;
}}
"""

# ── Clock / TAP widget styles ────────────────────────────────────────────────

TAP_BUTTON_STYLE = f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(66,165,245,0.30), stop:1 rgba(66,165,245,0.18));
    color: #ffffff;
    border: 2px solid rgba(66,165,245,0.40);
    border-radius: 30px;
    font-family: {FONT_TITLE};
    font-weight: 700;
    font-size: {FONT_SIZE_LG};
    min-width: 60px;
    min-height: 60px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(66,165,245,0.40), stop:1 rgba(66,165,245,0.25));
    border: 2px solid rgba(66,165,245,0.60);
}}
QPushButton:pressed {{
    background: rgba(66,165,245,0.15);
}}
"""

PULSE_LED_STYLE = led_style(NEON_BLUE, 16, True)
KICK_LED_STYLE = led_style(NEON_GREEN, 16, True)


# ══════════════════════════════════════════════════════════════════════════════
# COMPLETE STYLESHEET ASSEMBLER
# ══════════════════════════════════════════════════════════════════════════════

def get_full_stylesheet() -> str:
    """Returns the complete application stylesheet"""
    return f"""
    {MAIN_WINDOW_STYLE}
    {TAB_WIDGET_STYLE}
    {PANEL_STYLE}
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


def build_analyzer_card_style(is_active: bool, is_placeholder: bool = False) -> str:
    """Build stylesheet for analyzer module card"""
    if is_placeholder:
        return ANALYZER_PLACEHOLDER_STYLE
    elif is_active:
        return ANALYZER_ACTIVE_STYLE
    else:
        return ANALYZER_INACTIVE_STYLE


# ── Export all styles ─────────────────────────────────────────────────────────

__all__ = [
    # Colors
    'NEON_CYAN', 'NEON_GREEN', 'NEON_ORANGE', 'NEON_RED', 'NEON_PURPLE',
    'NEON_BLUE', 'NEON_YELLOW', 'NEON_GREEN_DARK', 'NEON_GREEN_GLOW',
    'NEON_CYAN_DARK', 'NEON_CYAN_GLOW',
    'BG_DARK', 'BG_PANEL', 'BG_CARD', 'BG_HOVER', 'BG_ACTIVE',
    'BG_PANEL_SOLID', 'BG_CARD_SOLID', 'BG_HOVER_SOLID', 'BG_ACTIVE_SOLID',
    'TEXT_PRIMARY', 'TEXT_SECONDARY', 'TEXT_MUTED', 'TEXT_FAINT',
    'BORDER_DEFAULT', 'BORDER_MEDIUM', 'BORDER_STRONG', 'BORDER_GREEN',
    'OFF_COLOR',
    'CARD_CSS', 'CARD_HOVER_CSS', 'INSET_CSS',
    'card_frame_css', 'inset_frame_css',
    # State / Energy
    'STATE_BAJADA', 'STATE_GOLPE', 'STATE_ATAQUE', 'STATE_BRAKE',
    'ENERGY_BAJA', 'ENERGY_MEDIA', 'ENERGY_ALTA',
    # Spacing & radius
    'SP_XS', 'SP_SM', 'SP_MD', 'SP_BASE', 'SP_LG', 'SP_XL', 'SP_2XL',
    'RAD_SM', 'RAD_MD', 'RAD_LG', 'RAD_XL', 'RAD_2XL',
    # Typography
    'FONT_BODY', 'FONT_TITLE', 'FONT_MONO',
    'FONT_SIZE_XS', 'FONT_SIZE_SM', 'FONT_SIZE_BASE', 'FONT_SIZE_MD',
    'FONT_SIZE_LG', 'FONT_SIZE_XL', 'FONT_SIZE_2XL',
    # Stylesheets
    'MAIN_WINDOW_STYLE', 'TAB_WIDGET_STYLE', 'PANEL_STYLE', 'CARD_STYLE',
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
]
