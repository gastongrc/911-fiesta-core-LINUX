# neon_styles.py - 911 Fiesta V12 Neon Pro Style System
# ==========================================================
# Soft neon aesthetic with cyan borders, dark backgrounds
# Professional lighting control UI styling
# ==========================================================

# Color Palette
NEON_CYAN = "#00d4ff"
NEON_CYAN_DARK = "#00a8cc"
NEON_CYAN_GLOW = "rgba(0, 212, 255, 0.3)"
NEON_GREEN = "#00ff88"
NEON_GREEN_DARK = "#00cc6a"
NEON_ORANGE = "#ff9500"
NEON_RED = "#ff3366"
NEON_PURPLE = "#9945ff"
NEON_BLUE = "#4d7cff"

# Background colors
BG_DARK = "#0a0a0f"
BG_PANEL = "#121218"
BG_CARD = "#181820"
BG_HOVER = "#1e1e28"
BG_ACTIVE = "#252530"

# Text colors
TEXT_PRIMARY = "#e0e0e8"
TEXT_SECONDARY = "#a0a0b0"
TEXT_MUTED = "#606070"

# State colors
STATE_BAJADA = "#4CAF50"
STATE_GOLPE = "#2196F3"
STATE_ATAQUE = "#FF5722"
STATE_BRAKE = "#9C27B0"

# Energy colors
ENERGY_BAJA = "#4CAF50"
ENERGY_MEDIA = "#FF9800"
ENERGY_ALTA = "#F44336"

# Main window stylesheet
MAIN_WINDOW_STYLE = f"""
QMainWindow {{
    background: {BG_DARK};
}}
QWidget {{
    background: transparent;
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
}}
"""

# Tab widget stylesheet
TAB_WIDGET_STYLE = f"""
QTabWidget::pane {{
    background: {BG_PANEL};
    border: 1px solid {NEON_CYAN_DARK};
    border-radius: 8px;
    margin-top: -1px;
}}
QTabBar::tab {{
    background: {BG_CARD};
    color: {TEXT_SECONDARY};
    border: 1px solid #2a2a35;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 10px 20px;
    margin-right: 2px;
    font-weight: 600;
    font-size: 11px;
}}
QTabBar::tab:selected {{
    background: {BG_PANEL};
    color: {NEON_CYAN};
    border: 1px solid {NEON_CYAN_DARK};
    border-bottom: 1px solid {BG_PANEL};
}}
QTabBar::tab:hover:!selected {{
    background: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}
"""

# Frame/Panel stylesheet
PANEL_STYLE = f"""
QFrame {{
    background: {BG_PANEL};
    border: 1px solid #2a2a35;
    border-radius: 8px;
}}
QFrame:hover {{
    border: 1px solid {NEON_CYAN_DARK};
}}
"""

# Card widget stylesheet (for analyzer cards)
CARD_STYLE = f"""
QFrame#AnalyzerCard {{
    background: {BG_CARD};
    border: 1px solid #2a2a35;
    border-radius: 10px;
    padding: 8px;
}}
QFrame#AnalyzerCard:hover {{
    border: 1px solid {NEON_CYAN};
    background: {BG_HOVER};
}}
"""

# Button stylesheet
BUTTON_STYLE = f"""
QPushButton {{
    background: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid #3a3a45;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 11px;
}}
QPushButton:hover {{
    background: {BG_HOVER};
    border: 1px solid {NEON_CYAN};
    color: {NEON_CYAN};
}}
QPushButton:pressed {{
    background: {BG_ACTIVE};
    border: 1px solid {NEON_CYAN};
}}
QPushButton:disabled {{
    background: {BG_DARK};
    color: {TEXT_MUTED};
    border: 1px solid #1a1a20;
}}
"""

# Primary action button (GO, TAP, etc.)
BUTTON_PRIMARY_STYLE = f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {NEON_CYAN_DARK}, stop:1 #006688);
    color: #ffffff;
    border: 1px solid {NEON_CYAN};
    border-radius: 6px;
    padding: 10px 20px;
    font-weight: 700;
    font-size: 12px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {NEON_CYAN}, stop:1 {NEON_CYAN_DARK});
    border: 1px solid #40e0ff;
}}
QPushButton:pressed {{
    background: {NEON_CYAN_DARK};
}}
"""

# Danger button (STOP, KILL, etc.)
BUTTON_DANGER_STYLE = f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #cc2244, stop:1 #991133);
    color: #ffffff;
    border: 1px solid {NEON_RED};
    border-radius: 6px;
    padding: 10px 20px;
    font-weight: 700;
    font-size: 12px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {NEON_RED}, stop:1 #cc2244);
}}
"""

# Progress bar stylesheet
PROGRESS_BAR_STYLE = f"""
QProgressBar {{
    background: {BG_DARK};
    border: 1px solid #2a2a35;
    border-radius: 6px;
    text-align: center;
    color: {TEXT_SECONDARY};
    font-size: 10px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {NEON_CYAN_DARK}, stop:1 {NEON_CYAN});
    border-radius: 5px;
}}
"""

# Slider stylesheet (Neon style)
SLIDER_STYLE = f"""
QSlider::groove:horizontal {{
    background: {BG_DARK};
    border: 1px solid #2a2a35;
    height: 8px;
    border-radius: 4px;
}}
QSlider::handle:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {NEON_CYAN}, stop:1 {NEON_CYAN_DARK});
    border: 1px solid {NEON_CYAN};
    width: 18px;
    height: 18px;
    margin: -6px 0;
    border-radius: 9px;
}}
QSlider::handle:horizontal:hover {{
    background: {NEON_CYAN};
    border: 2px solid #40e0ff;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {NEON_CYAN_DARK}, stop:1 {NEON_CYAN});
    border-radius: 4px;
}}
QSlider::groove:vertical {{
    background: {BG_DARK};
    border: 1px solid #2a2a35;
    width: 8px;
    border-radius: 4px;
}}
QSlider::handle:vertical {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {NEON_CYAN}, stop:1 {NEON_CYAN_DARK});
    border: 1px solid {NEON_CYAN};
    width: 18px;
    height: 18px;
    margin: 0 -6px;
    border-radius: 9px;
}}
QSlider::sub-page:vertical {{
    background: qlineargradient(x1:0, y1:1, x2:0, y2:0,
        stop:0 {NEON_CYAN_DARK}, stop:1 {NEON_CYAN});
    border-radius: 4px;
}}
"""

# ComboBox stylesheet
COMBOBOX_STYLE = f"""
QComboBox {{
    background: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid #3a3a45;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 11px;
    min-width: 100px;
}}
QComboBox:hover {{
    border: 1px solid {NEON_CYAN};
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
    background: {BG_PANEL};
    color: {TEXT_PRIMARY};
    border: 1px solid {NEON_CYAN_DARK};
    border-radius: 6px;
    selection-background-color: {BG_ACTIVE};
    selection-color: {NEON_CYAN};
}}
"""

# LineEdit stylesheet
LINEEDIT_STYLE = f"""
QLineEdit {{
    background: {BG_DARK};
    color: {TEXT_PRIMARY};
    border: 1px solid #2a2a35;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 11px;
}}
QLineEdit:focus {{
    border: 1px solid {NEON_CYAN};
}}
QLineEdit:hover {{
    border: 1px solid {NEON_CYAN_DARK};
}}
"""

# SpinBox stylesheet
SPINBOX_STYLE = f"""
QSpinBox, QDoubleSpinBox {{
    background: {BG_DARK};
    color: {TEXT_PRIMARY};
    border: 1px solid #2a2a35;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 11px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {NEON_CYAN};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    background: {BG_CARD};
    border: none;
    border-left: 1px solid #2a2a35;
    border-top-right-radius: 5px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: {BG_CARD};
    border: none;
    border-left: 1px solid #2a2a35;
    border-bottom-right-radius: 5px;
}}
"""

# Label styles
LABEL_TITLE_STYLE = f"""
QLabel {{
    color: {NEON_CYAN};
    font-weight: 700;
    font-size: 14px;
    background: transparent;
    border: none;
}}
"""

LABEL_SECTION_STYLE = f"""
QLabel {{
    color: {TEXT_PRIMARY};
    font-weight: 600;
    font-size: 12px;
    background: transparent;
    border: none;
}}
"""

LABEL_NORMAL_STYLE = f"""
QLabel {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
    background: transparent;
    border: none;
}}
"""

# GroupBox stylesheet
GROUPBOX_STYLE = f"""
QGroupBox {{
    background: {BG_PANEL};
    border: 1px solid #2a2a35;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: 600;
    font-size: 11px;
}}
QGroupBox::title {{
    color: {NEON_CYAN};
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 8px;
    background: {BG_PANEL};
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
    width: 10px;
    border-radius: 5px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BG_ACTIVE};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {NEON_CYAN_DARK};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {BG_DARK};
    height: 10px;
    border-radius: 5px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BG_ACTIVE};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {NEON_CYAN_DARK};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
"""

# LED indicator styles
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

# State indicator styles
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
        font-weight: 700;
        font-size: 24px;
        background: {BG_DARK};
        border: 2px solid {color};
        border-radius: 8px;
        padding: 12px;
    }}
    """

# Energy indicator style
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
        font-weight: 700;
        font-size: 18px;
        background: {BG_DARK};
        border: 1px solid {color};
        border-radius: 6px;
        padding: 8px;
    }}
    """

# Analyzer card active/inactive styles
ANALYZER_ACTIVE_STYLE = f"""
QFrame {{
    background: {BG_CARD};
    border: 1px solid {NEON_GREEN};
    border-radius: 8px;
}}
"""

ANALYZER_INACTIVE_STYLE = f"""
QFrame {{
    background: {BG_CARD};
    border: 1px solid #2a2a35;
    border-radius: 8px;
}}
"""

ANALYZER_PLACEHOLDER_STYLE = f"""
QFrame {{
    background: {BG_DARK};
    border: 1px dashed #3a3a45;
    border-radius: 8px;
    opacity: 0.5;
}}
"""

# VU Meter styles
VU_METER_STYLE = f"""
QProgressBar {{
    background: {BG_DARK};
    border: 1px solid #2a2a35;
    border-radius: 10px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {NEON_GREEN}, stop:0.7 {NEON_ORANGE}, stop:1 {NEON_RED});
    border-radius: 9px;
}}
"""

# Waveform widget style
WAVEFORM_STYLE = f"""
QFrame {{
    background: {BG_DARK};
    border: 1px solid #2a2a35;
    border-radius: 6px;
}}
"""

# Complete application stylesheet
def get_full_stylesheet() -> str:
    """Returns the complete application stylesheet"""
    return f"""
    {MAIN_WINDOW_STYLE}
    {TAB_WIDGET_STYLE}
    {BUTTON_STYLE}
    {PROGRESS_BAR_STYLE}
    {SLIDER_STYLE}
    {COMBOBOX_STYLE}
    {LINEEDIT_STYLE}
    {SPINBOX_STYLE}
    {GROUPBOX_STYLE}
    {SCROLLAREA_STYLE}
    """


# Module analyzer card style builder
def build_analyzer_card_style(is_active: bool, is_placeholder: bool = False) -> str:
    """Build stylesheet for analyzer module card"""
    if is_placeholder:
        return ANALYZER_PLACEHOLDER_STYLE
    elif is_active:
        return ANALYZER_ACTIVE_STYLE
    else:
        return ANALYZER_INACTIVE_STYLE


# Health monitor widget styles
HEALTH_PANEL_STYLE = f"""
QFrame {{
    background: {BG_PANEL};
    border: 1px solid #2a2a35;
    border-radius: 8px;
}}
"""

HEALTH_SECTION_STYLE = f"""
QFrame {{
    background: {BG_CARD};
    border: 1px solid #2a2a35;
    border-radius: 6px;
}}
"""

# Clock/TAP widget styles
TAP_BUTTON_STYLE = f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2266aa, stop:1 #114488);
    color: #ffffff;
    border: 2px solid {NEON_BLUE};
    border-radius: 30px;
    font-weight: 700;
    font-size: 16px;
    min-width: 60px;
    min-height: 60px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {NEON_BLUE}, stop:1 #2266aa);
    border: 2px solid #6699ff;
}}
QPushButton:pressed {{
    background: #114488;
}}
"""

PULSE_LED_STYLE = led_style(NEON_BLUE, 16, True)
KICK_LED_STYLE = led_style(NEON_GREEN, 16, True)

# Export all styles
__all__ = [
    'NEON_CYAN', 'NEON_GREEN', 'NEON_ORANGE', 'NEON_RED', 'NEON_PURPLE', 'NEON_BLUE',
    'BG_DARK', 'BG_PANEL', 'BG_CARD', 'BG_HOVER', 'BG_ACTIVE',
    'TEXT_PRIMARY', 'TEXT_SECONDARY', 'TEXT_MUTED',
    'STATE_BAJADA', 'STATE_GOLPE', 'STATE_ATAQUE', 'STATE_BRAKE',
    'ENERGY_BAJA', 'ENERGY_MEDIA', 'ENERGY_ALTA',
    'MAIN_WINDOW_STYLE', 'TAB_WIDGET_STYLE', 'PANEL_STYLE', 'CARD_STYLE',
    'BUTTON_STYLE', 'BUTTON_PRIMARY_STYLE', 'BUTTON_DANGER_STYLE',
    'PROGRESS_BAR_STYLE', 'SLIDER_STYLE', 'COMBOBOX_STYLE',
    'LINEEDIT_STYLE', 'SPINBOX_STYLE', 'GROUPBOX_STYLE', 'SCROLLAREA_STYLE',
    'LABEL_TITLE_STYLE', 'LABEL_SECTION_STYLE', 'LABEL_NORMAL_STYLE',
    'VU_METER_STYLE', 'WAVEFORM_STYLE',
    'TAP_BUTTON_STYLE', 'PULSE_LED_STYLE', 'KICK_LED_STYLE',
    'HEALTH_PANEL_STYLE', 'HEALTH_SECTION_STYLE',
    'ANALYZER_ACTIVE_STYLE', 'ANALYZER_INACTIVE_STYLE', 'ANALYZER_PLACEHOLDER_STYLE',
    'led_style', 'state_indicator_style', 'energy_indicator_style',
    'build_analyzer_card_style', 'get_full_stylesheet',
]
