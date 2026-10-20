"""Light/dark stylesheets."""

PALETTES = {
    "light": dict(bg="#f6f7fb", card="#ffffff", text="#1f2430", muted="#6b7280", border="#dfe3ec",
                  accent="#4f6bed", accent_text="#ffffff", hover="#eef1fb", good="#16a34a", bad="#dc2626"),
    "dark": dict(bg="#161922", card="#1f2330", text="#e8eaf2", muted="#9aa3b5", border="#2f3547",
                 accent="#7c92ff", accent_text="#10131c", hover="#283049", good="#4ade80", bad="#f87171"),
}


def palette(name: str) -> dict:
    return PALETTES.get(name, PALETTES["light"])


def stylesheet(name: str) -> str:
    p = palette(name)
    return f"""
    QWidget {{ background: {p['bg']}; color: {p['text']}; font-size: 14px; }}
    QLabel {{ background: transparent; }}
    QLabel#title {{ font-size: 26px; font-weight: 700; }}
    QLabel#subtitle {{ color: {p['muted']}; font-size: 14px; }}
    QLabel#h2 {{ font-size: 17px; font-weight: 600; }}
    QLabel#muted {{ color: {p['muted']}; }}
    QFrame#card, QGroupBox {{ background: {p['card']}; border: 1px solid {p['border']}; border-radius: 12px; }}
    QGroupBox {{ margin-top: 14px; padding: 12px 10px 8px 10px; font-weight: 600; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; background: {p['bg']}; }}
    QFrame#card QLabel, QGroupBox QLabel {{ background: transparent; }}
    QPushButton {{ background: {p['card']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 7px 14px; }}
    QPushButton:hover {{ background: {p['hover']}; }}
    QPushButton:disabled {{ color: {p['muted']}; }}
    QPushButton#primary {{ background: {p['accent']}; color: {p['accent_text']}; border: none; font-weight: 600; }}
    QPushButton#primary:hover {{ background: {p['accent']}; }}
    QPushButton#primary:disabled {{ background: {p['border']}; color: {p['muted']}; }}
    QPushButton#tile {{ background: {p['card']}; border: 1px solid {p['border']}; border-radius: 14px;
        padding: 18px; text-align: left; font-size: 15px; font-weight: 600; }}
    QPushButton#tile:hover {{ border-color: {p['accent']}; background: {p['hover']}; }}
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QListWidget, QTextBrowser {{
        background: {p['card']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 6px;
        selection-background-color: {p['accent']}; selection-color: {p['accent_text']}; }}
    QListWidget::item {{ padding: 5px; border-radius: 6px; }}
    QListWidget::item:selected {{ background: {p['hover']}; color: {p['text']}; }}
    QTabWidget::pane {{ border: 1px solid {p['border']}; border-radius: 10px; top: -1px; background: {p['card']}; }}
    QTabBar::tab {{ background: transparent; padding: 8px 16px; border-radius: 8px; margin-right: 2px; }}
    QTabBar::tab:selected {{ background: {p['card']}; font-weight: 600; border: 1px solid {p['border']}; }}
    QProgressBar {{ border: 1px solid {p['border']}; border-radius: 6px; text-align: center; height: 16px; }}
    QProgressBar::chunk {{ background: {p['accent']}; border-radius: 5px; }}
    QScrollArea {{ border: none; }}
    QCheckBox, QRadioButton {{ background: transparent; spacing: 8px; }}
    QToolTip {{ background: {p['card']}; color: {p['text']}; border: 1px solid {p['border']}; }}
    """
