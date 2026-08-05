import base64
import html
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import db
import sync

try:
    from pandas.io.formats.style import Styler
except Exception:  # pragma: no cover
    Styler = None


def _norm_jam(s):
    """Terima '10:10', '10.10', atau '1010' -> '10:10'; None kalau tidak valid."""
    import re

    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", str(s).strip())
    if not m:
        return None
    j, mnt = int(m.group(1)), int(m.group(2))
    if j > 23 or mnt > 59:
        return None
    return f"{j:02d}:{mnt:02d}"


def _now_wib():
    """Waktu sekarang dalam zona WIB (UTC+7) tanpa info zona."""
    from datetime import timezone

    return datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None)


def _window_absen(j):
    """Status window absen untuk satu jadwal.
    Mengembalikan (status, keterangan, epoch_buka, epoch_tutup);
    status: "aktif"|"belum"|"lewat", epoch = detik (Unix time) atau None."""
    if not j["jam_mulai"] or not j["jam_selesai"]:
        return "aktif", "", None, None
    try:
        t1 = datetime.strptime(j["jam_mulai"], "%H:%M")
        t2 = datetime.strptime(j["jam_selesai"], "%H:%M")
    except ValueError:
        return "aktif", "", None, None
    tgl = _now_wib().date()
    mulai = datetime.combine(tgl, t1.time()) - timedelta(minutes=10)
    akhir = datetime.combine(tgl, t2.time()) + timedelta(hours=1)
    now = _now_wib()
    from datetime import timezone

    wib = timezone(timedelta(hours=7))
    buka_ep = int(mulai.replace(tzinfo=wib).timestamp())
    tutup_ep = int(akhir.replace(tzinfo=wib).timestamp())
    if now < mulai:
        return (
            "belum",
            f"bisa absen {mulai.strftime('%H:%M')} s/d {akhir.strftime('%H:%M')} "
            "(H-10 menit, +1 jam setelah MK)",
            buka_ep, tutup_ep,
        )
    if now > akhir:
        return (
            "lewat",
            f"absen sudah ditutup pukul {akhir.strftime('%H:%M')} "
            "(H-10 menit s/d +1 jam setelah MK)",
            buka_ep, tutup_ep,
        )
    return "aktif", f"ditutup pukul {akhir.strftime('%H:%M')}", buka_ep, tutup_ep


def _timer_html(uid, end_epoch, badge_html, txt_awal, txt_selesai):
    """Badge status + jam hitung mundur real-time dalam satu baris (JS),
    sampai epoch habis lalu berubah jadi teks merah."""
    tpl = """<div style="display:flex;align-items:center;gap:6px;justify-content:flex-end;font-family:'Segoe UI',sans-serif">
{badge}
<span id="tmx_{uid}" style="color:#7f8ea3;font-size:.78rem">{txt_awal}</span>
</div>
<script>
(function() {
  var end = {end} * 1000;
  var tx = document.getElementById('tmx_{uid}');
  function p(n) { return (n < 10 ? '0' : '') + n; }
  function fmt(s) {
    s = Math.max(0, Math.floor(s));
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
    return (h > 0 ? h + ':' : '') + p(m) + ':' + p(ss);
  }
  function tick() {
    var sisa = (end - Date.now()) / 1000;
    if (sisa <= 0) {
      tx.textContent = '{txt_selesai}';
      tx.style.color = '#ef4444';
      tx.style.fontWeight = '700';
    } else {
      tx.textContent = '{txt_awal} ' + fmt(sisa);
    }
  }
  tick();
  setInterval(tick, 1000);
})();
</script>"""
    return (
        tpl.replace("{uid}", uid)
        .replace("{end}", str(end_epoch))
        .replace("{badge}", badge_html)
        .replace("{txt_awal}", txt_awal)
        .replace("{txt_selesai}", txt_selesai)
    )


def _clock_html():
    """Jam real-time WIB (hari, tanggal, jam) — berdetak tiap detik."""
    tpl = """<div class="clock-box">
<div id="clk_tgl_UID" class="clock-tgl">-</div>
<div id="clk_jam_UID" class="clock-jam">--:--:--</div>
<div class="clock-wib">WIB (UTC+7)</div>
</div>
<script>
(function() {
  var HARI = ['Minggu','Senin','Selasa','Rabu','Kamis','Jumat','Sabtu'];
  var BLN = ['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'];
  function p(n) { return (n < 10 ? '0' : '') + n; }
  function tick() {
    var d = new Date(Date.now() + 7 * 3600 * 1000);
    var tgl = HARI[d.getUTCDay()] + ', ' + d.getUTCDate() + ' ' + BLN[d.getUTCMonth()] + ' ' + d.getUTCFullYear();
    var jam = p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ':' + p(d.getUTCSeconds());
    document.getElementById('clk_tgl_UID').textContent = tgl;
    document.getElementById('clk_jam_UID').textContent = jam;
  }
  tick();
  setInterval(tick, 1000);
})();
</script>"""
    return tpl.replace("UID", "dsb")

st.set_page_config(page_title="Catatan Semester 5", layout="wide", initial_sidebar_state="expanded")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], [data-testid="stAppViewContainer"] {
    font-family: 'Plus Jakarta Sans', 'Segoe UI', sans-serif;
    color: #e2e8f0;
}

#MainMenu, footer, [data-testid="stMainMenu"], [data-testid="stToolbarActionButton"] { visibility: hidden; }
[data-testid="stExpandSidebarButton"] {
    visibility: visible !important;
    color: #ffffff !important;
    background: rgba(255,255,255,.14);
    border: 1px solid rgba(255,255,255,.25);
    border-radius: 10px;
    backdrop-filter: blur(12px);
}
[data-testid="stHeader"] { background: transparent; }

.stApp {
    background:
        radial-gradient(1000px 520px at 8% -12%, rgba(59,130,246,.55), transparent 62%),
        radial-gradient(900px 480px at 108% 4%, rgba(168,85,247,.5), transparent 58%),
        radial-gradient(820px 560px at 50% 118%, rgba(6,182,212,.4), transparent 60%),
        linear-gradient(160deg, #0b1120 0%, #101b3c 42%, #1e1b4b 100%);
    background-attachment: fixed;
}

[data-testid="stSidebar"] {
    background: rgba(15, 23, 42, .55);
    backdrop-filter: blur(28px) saturate(150%);
    -webkit-backdrop-filter: blur(28px) saturate(150%);
    border-right: 1px solid rgba(255,255,255,.10);
}
[data-testid="stSidebar"] .block-container { padding-top: 1.2rem; }
[data-testid="stSidebar"] [role="radiogroup"] label {
    background: rgba(255,255,255,.06);
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 14px;
    padding: 11px 14px;
    margin-bottom: 8px;
    transition: all .18s ease;
    backdrop-filter: blur(10px);
}
[data-testid="stSidebar"] [role="radiogroup"] label p {
    color: #e2e8f0 !important;
    font-weight: 600;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {
    background: rgba(255,255,255,.13);
    border-color: rgba(255,255,255,.28);
    transform: translateX(3px);
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background: linear-gradient(120deg, rgba(59,130,246,.85), rgba(14,165,233,.75));
    border: 1px solid rgba(255,255,255,.25);
    box-shadow: 0 8px 22px rgba(37, 99, 235, .45), inset 0 1px 0 rgba(255,255,255,.25);
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {
    color: #ffffff !important;
    font-weight: 700;
}

.sidebar-brand {
    color: #f8fafc;
    font-size: 1.25rem;
    font-weight: 800;
    letter-spacing: .5px;
    padding: 4px 6px 2px 6px;
    text-shadow: 0 2px 12px rgba(59,130,246,.5);
}
.sidebar-sub { color: rgba(226,232,240,.65); font-size: .8rem; padding: 0 6px 10px 6px; }

.user-box {
    display: flex;
    align-items: center;
    gap: 12px;
    background: rgba(255,255,255,.07);
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 16px;
    padding: 12px 14px;
    margin: 12px 0 8px 0;
    backdrop-filter: blur(10px);
}
.user-avatar {
    width: 42px;
    height: 42px;
    border-radius: 50%;
    background: linear-gradient(135deg, #3b82f6, #06b6d4);
    color: #ffffff;
    font-weight: 800;
    font-size: 1rem;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 0 16px rgba(59,130,246,.5);
    flex-shrink: 0;
}
.user-name { color: #f1f5f9; font-weight: 700; font-size: .92rem; }
.user-role { color: rgba(226,232,240,.6); font-size: .75rem; }

.login-card { text-align: center; padding: 48px 0 24px 0; max-width: 340px; margin: 0 auto; }
.welcome-card {
    background: linear-gradient(135deg, rgba(59,130,246,.25), rgba(6,182,212,.25));
    border: 1px solid rgba(255,255,255,.14);
    border-radius: 18px;
    padding: 18px 22px;
    margin-bottom: 18px;
    backdrop-filter: blur(10px);
}
.welcome-title { color: #f1f5f9; font-weight: 800; font-size: 1.15rem; }
.welcome-sub { color: rgba(226,232,240,.6); font-size: .8rem; margin-top: 2px; }

.tbl-wrap {
    overflow: auto;
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 14px;
    background: rgba(255,255,255,.04);
}
.tbl-wrap::-webkit-scrollbar { width: 8px; height: 8px; }
.tbl-wrap::-webkit-scrollbar-thumb { background: rgba(255,255,255,.18); border-radius: 8px; }
.tbl-custom {
    width: 100%;
    border-collapse: collapse;
    font-size: .85rem;
    white-space: nowrap;
}
.tbl-custom th {
    position: sticky;
    top: 0;
    background: #1e293b;
    color: #93c5fd;
    text-align: left;
    padding: 9px 12px;
    font-weight: 700;
    z-index: 1;
}
.tbl-custom td {
    padding: 8px 12px;
    color: #e2e8f0;
    border-top: 1px solid rgba(255,255,255,.06);
}
.tbl-custom tbody tr:hover { background: rgba(59,130,246,.12); }
.tbl-badge { font-weight: 700; }

[data-testid="stTextInputRootElement"],
[data-testid="stTextAreaRootElement"],
[data-testid="stNumberInputContainer"],
[data-testid="stDateInput"] [data-baseweb="input"],
[data-testid="stTimeInputTimeDisplay"],
[data-testid="stSelectbox"] div:has(> input) {
    background: linear-gradient(180deg, rgba(148,184,255,.16), rgba(59,130,246,.09)) !important;
    border: 1px solid rgba(165,200,255,.22) !important;
    border-radius: 14px !important;
    color: #e2e8f0 !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.09) !important;
    backdrop-filter: blur(10px) !important;
    -webkit-backdrop-filter: blur(10px) !important;
    outline: none !important;
    transition: background .15s ease, box-shadow .15s ease;
}
[data-testid="stTextInputRootElement"]:hover,
[data-testid="stTextAreaRootElement"]:hover,
[data-testid="stNumberInputContainer"]:hover,
[data-testid="stDateInput"] [data-baseweb="input"]:hover,
[data-testid="stTimeInputTimeDisplay"]:hover,
[data-testid="stSelectbox"] div:has(> input):hover {
    background: linear-gradient(180deg, rgba(148,184,255,.24), rgba(59,130,246,.15)) !important;
}
[data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stTextAreaRootElement"]:focus-within,
[data-testid="stNumberInputContainer"]:focus-within,
[data-testid="stDateInput"] [data-baseweb="input"]:focus-within,
[data-testid="stTimeInputTimeDisplay"]:focus-within,
[data-testid="stSelectbox"] div:has(> input):focus-within {
    background: linear-gradient(180deg, rgba(148,184,255,.2), rgba(59,130,246,.12)) !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.12), 0 0 0 2px rgba(96,165,250,.35) !important;
}
[data-testid="stNumberInputField"],
[data-testid="stTextInput"] [data-baseweb="base-input"],
[data-testid="stTextArea"] [data-baseweb="base-input"],
[data-testid="stDateInput"] [data-baseweb="base-input"],
[data-testid="stDateInputField"],
[data-testid="stTimeInputTimeDisplay"] *,
[data-testid="stSelectbox"] input {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: #e2e8f0 !important;
}
[data-testid="stSelectbox"] [role="button"],
[data-testid="stDateInput"] [data-baseweb="input"] [role="button"],
[data-testid="stTimeInputClearButton"],
[data-testid="stNumberInputStepUp"],
[data-testid="stNumberInputStepDown"],
[data-testid="stNumberInputClearButton"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}
[data-testid="stSelectboxVirtualDropdown"] {
    background: rgba(22,35,60,.85) !important;
    border: 1px solid rgba(165,200,255,.18) !important;
    border-radius: 14px !important;
    backdrop-filter: blur(14px) !important;
    -webkit-backdrop-filter: blur(14px) !important;
    overflow: hidden;
}
[data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover {
    background-color: rgba(59,130,246,.25) !important;
}

.login-avatar { width: 72px; height: 72px; font-size: 1.7rem; margin: 0 auto 16px auto; }

.login-avatar { width: 72px; height: 72px; font-size: 1.7rem; margin: 0 auto 16px auto; }
.login-title { color: #f1f5f9; font-weight: 800; font-size: 1.35rem; }
.login-sub { color: rgba(226,232,240,.55); font-size: .85rem; margin-top: 4px; }

.sync-box {
    background: rgba(255,255,255,.07);
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 14px;
    padding: 10px 12px;
    color: #e2e8f0;
    font-size: .78rem;
    margin: 10px 0;
    backdrop-filter: blur(10px);
}

.siakad-banner {
    position: relative;
    overflow: hidden;
    background: linear-gradient(120deg, rgba(37,99,235,.55), rgba(14,165,233,.35), rgba(168,85,247,.45));
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
    border: 1px solid rgba(255,255,255,.18);
    border-radius: 22px;
    padding: 20px 26px;
    margin-bottom: 20px;
    box-shadow: 0 12px 36px rgba(2, 6, 23, .45), inset 0 1px 0 rgba(255,255,255,.25);
}
.siakad-banner::before {
    content: "";
    position: absolute;
    top: -70px; left: 8%;
    width: 260px; height: 260px;
    background: radial-gradient(circle, rgba(255,255,255,.28), transparent 70%);
    border-radius: 50%;
    filter: blur(4px);
}
.siakad-banner::after {
    content: "";
    position: absolute;
    bottom: -80px; right: -30px;
    width: 240px; height: 240px;
    background: radial-gradient(circle, rgba(165, 243, 252, .3), transparent 70%);
    border-radius: 50%;
    filter: blur(6px);
}
.banner-title { color: #ffffff; font-size: 1.4rem; font-weight: 800; text-shadow: 0 2px 14px rgba(2,6,23,.35); }
.banner-sub { color: rgba(255,255,255,.88); font-size: .9rem; margin-top: 4px; }

.stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 14px;
    margin-bottom: 22px;
}
.stat-card {
    position: relative;
    overflow: hidden;
    background: rgba(255,255,255,.08);
    backdrop-filter: blur(20px) saturate(150%);
    -webkit-backdrop-filter: blur(20px) saturate(150%);
    border: 1px solid rgba(255,255,255,.14);
    border-radius: 20px;
    padding: 18px 20px;
    box-shadow: 0 10px 30px rgba(2, 6, 23, .35), inset 0 1px 0 rgba(255,255,255,.18);
    transition: transform .18s ease, box-shadow .18s ease;
}
.stat-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--accent, #3b82f6), transparent 85%);
    box-shadow: 0 0 14px var(--accent, #3b82f6);
}
.stat-card:hover {
    transform: translateY(-4px) scale(1.01);
    box-shadow: 0 16px 40px rgba(2, 6, 23, .5), inset 0 1px 0 rgba(255,255,255,.22);
}
.stat-label {
    color: rgba(226,232,240,.75);
    font-size: .74rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .6px;
}
.stat-label::before {
    content: "";
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 6px;
    background: var(--accent, #3b82f6);
    box-shadow: 0 0 8px var(--accent, #3b82f6);
    vertical-align: 0;
}
.stat-value { font-size: 2.1rem; font-weight: 800; margin-top: 4px; text-shadow: 0 2px 12px rgba(2,6,23,.4); }

.panel {
    background: rgba(255,255,255,.07);
    backdrop-filter: blur(22px) saturate(150%);
    -webkit-backdrop-filter: blur(22px) saturate(150%);
    border: 1px solid rgba(255,255,255,.13);
    border-radius: 20px;
    padding: 18px 20px;
    box-shadow: 0 10px 32px rgba(2, 6, 23, .35), inset 0 1px 0 rgba(255,255,255,.15);
    margin-bottom: 18px;
}
.panel-title {
    font-size: 1.05rem;
    font-weight: 800;
    color: #f1f5f9;
    margin: 8px 0 12px 0;
}
.panel-title::before {
    content: "";
    display: inline-block;
    width: 5px;
    height: 16px;
    border-radius: 3px;
    margin-right: 9px;
    background: linear-gradient(180deg, #60a5fa, #22d3ee);
    box-shadow: 0 0 10px rgba(56,189,248,.6);
    vertical-align: -2px;
}
.absen-hari {
    margin-top: 30px;
    padding: 8px 12px;
    border: 1px solid rgba(96,165,250,.35);
    border-radius: 12px;
    background: rgba(59,130,246,.12);
    color: #bfdbfe;
    font-size: .9rem;
    text-align: center;
}
.absen-sub {
    color: #7f8ea3;
    font-size: .78rem;
}
.absen-rule {
    color: #7f8ea3;
    font-size: .78rem;
    margin: -4px 0 10px 0;
}
.absen-lock {
    margin: 2px 0 6px 0;
    padding: 6px 12px;
    border: 1px dashed rgba(100,116,139,.45);
    border-radius: 10px;
    color: #64748b;
    font-size: .78rem;
}
.clock-box {
    padding: 12px 18px;
    border-radius: 14px;
    border: 1px solid rgba(96,165,250,.35);
    background: linear-gradient(120deg, rgba(59,130,246,.16), rgba(6,182,212,.12));
    text-align: center;
    margin: 4px 0 16px 0;
}
.clock-tgl {
    font-size: .95rem;
    font-weight: 700;
    color: #e2e8f0;
}
.clock-jam {
    font-size: 1.9rem;
    font-weight: 800;
    color: #f8fafc;
    letter-spacing: 1px;
    font-variant-numeric: tabular-nums;
}
.clock-wib {
    font-size: .72rem;
    color: #7f8ea3;
}

[data-testid="stButton"] button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] {
    background: linear-gradient(120deg, #3b82f6, #06b6d4);
    border: none;
    box-shadow: 0 10px 26px rgba(59, 130, 246, .5), inset 0 1px 0 rgba(255,255,255,.3);
    transition: transform .15s ease, box-shadow .15s ease;
}
[data-testid="stButton"] button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 14px 32px rgba(59, 130, 246, .6), inset 0 1px 0 rgba(255,255,255,.3);
}

[data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button {
    border-radius: 12px !important;
    font-weight: 700 !important;
}

[data-testid="stSidebar"] button[kind="secondary"] {
    background: rgba(239,68,68,.15) !important;
    border: 1px solid rgba(239,68,68,.45) !important;
    color: #fca5a5 !important;
    box-shadow: none !important;
    backdrop-filter: blur(8px);
}
[data-testid="stSidebar"] button[kind="secondary"]:hover {
    background: rgba(239,68,68,.28) !important;
    border-color: rgba(239,68,68,.7) !important;
    color: #fecaca !important;
}

[data-testid="stDataFrame"] {
    border-radius: 14px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,.12);
    --st-default-background-color: rgba(255,255,255,.04);
    --st-header-background-color: rgba(255,255,255,.10);
    --st-header-text-color: #f8fafc;
    --st-default-text-color: #e2e8f0;
    --st-row-selection-background-color: rgba(59,130,246,.35);
    --st-grid-border-color: rgba(255,255,255,.08);
}
[data-testid="stDataFrame"] [role="columnheader"] {
    background: rgba(255,255,255,.09);
    color: #f8fafc;
    font-weight: 700;
}

[data-testid="stExpander"] details {
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 16px;
    background: rgba(255,255,255,.05);
    backdrop-filter: blur(16px);
}
[data-testid="stExpander"] summary { font-weight: 700; color: #f1f5f9; }
[data-testid="stExpander"] summary p { color: #f1f5f9; }

[data-testid="stDialog"] {
    background: rgba(15, 23, 42, .92);
    backdrop-filter: blur(30px) saturate(150%);
    -webkit-backdrop-filter: blur(30px) saturate(150%);
    border: 1px solid rgba(255,255,255,.14);
    border-radius: 22px;
}

[data-testid="stAlert"] {
    border-radius: 14px !important;
    border: 1px solid rgba(255,255,255,.14) !important;
    backdrop-filter: blur(12px);
}
[data-testid="stAlert"] p { color: #f1f5f9 !important; }

[data-testid="stSegmentedControl"] button {
    border-radius: 12px !important;
    color: #e2e8f0 !important;
}
[data-testid="stSegmentedControl"] button[aria-checked="true"] {
    background: linear-gradient(120deg, #3b82f6, #06b6d4) !important;
    color: #ffffff !important;
}

[data-testid="stWidgetLabel"], [data-testid="stMarkdownContainer"] p { color: #e2e8f0; }

.sidebar-foot {
    color: rgba(148,163,184,.7);
    font-size: .72rem;
    text-align: center;
    margin-top: 14px;
    padding-top: 10px;
    border-top: 1px solid rgba(255,255,255,.10);
}
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)

PAGE_TITLES = {
    "Dashboard": ("Dashboard", "Rekap kehadiran dan tugas — Muhammad Nabiel Fahrendi."),
    "Jadwal Kuliah": ("Jadwal Kuliah", "Matakuliah dan jadwal semester 5."),
    "Absen": ("Absen", "Catat kehadiranmu setiap masuk kelas."),
    "Tugas Harian": ("Tugas Harian", "Tugas harian yang kamu buat."),
    "UTS & UAS": ("UTS & UAS", "Jadwal, nilai, dan status ujian."),
}


def page_header(title, subtitle=""):
    st.markdown(
        f'<div class="siakad-banner"><div class="banner-title">{html.escape(title)}</div>'
        f'<div class="banner-sub">{html.escape(subtitle)}</div></div>',
        unsafe_allow_html=True,
    )


def stat_cards(items):
    cards = "".join(
        f'<div class="stat-card" style="--accent:{color}">'
        f'<div class="stat-label">{html.escape(label)}</div>'
        f'<div class="stat-value" style="color:{color}">{html.escape(str(value))}</div></div>'
        for label, value, color in items
    )
    st.markdown(f'<div class="stat-grid">{cards}</div>', unsafe_allow_html=True)


def flash():
    msg = st.session_state.pop("flash", None)
    if msg:
        st.success(msg)


_WARNA_STATUS = {
    "Terlambat": "#f87171", "Belum": "#fbbf24", "Diserahkan": "#34d399",
    "Hadir": "#34d399", "Alpa": "#f87171", "Izin": "#fbbf24", "Sakit": "#fbbf24",
}


def tabel_html(df, height=300):
    """Tabel HTML statis - tidak bisa di-resize, tampilan kaca."""
    cols = list(df.columns)
    thead = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
    trs = []
    for _, r in df.iterrows():
        tds = []
        for c in cols:
            v = r[c]
            txt = "-" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
            if c == "Status" and txt in _WARNA_STATUS:
                tds.append(
                    f'<td><span class="tbl-badge" style="color:{_WARNA_STATUS[txt]}">{html.escape(txt)}</span></td>'
                )
            else:
                tds.append(f"<td>{html.escape(txt)}</td>")
        trs.append("<tr>" + "".join(tds) + "</tr>")
    st.markdown(
        f'<div class="tbl-wrap" style="max-height:{height}px">'
        f'<table class="tbl-custom"><thead><tr>{thead}</tr></thead>'
        f'<tbody>{"".join(trs)}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def select_table(df, key, height=380):
    base = df.data if (Styler is not None and isinstance(df, Styler)) else df
    tabel_html(base, height=height)
    labels = [f"{i + 1}. " + " | ".join(str(v) for v in r[:3]) for i, r in base.iterrows()]
    pilihan = st.selectbox("Pilih baris untuk aksi", [""] + labels, key=f"{key}_sel")
    if pilihan:
        pos = labels.index(pilihan)
        return base.iloc[pos].to_dict(), pos
    return None, None


@st.dialog("Konfirmasi Hapus")
def hapus_dialog(label, aksi):
    st.warning(f'Anda akan menghapus "{label}". Tindakan ini tidak dapat dibatalkan.')
    c1, c2 = st.columns(2)
    if c1.button("Ya, Hapus", type="primary", width="stretch"):
        aksi()
        st.session_state["flash"] = "Data berhasil dihapus."
        sync.push()
        st.rerun()
    if c2.button("Batal", width="stretch"):
        st.rerun()


# ---------- Dashboard ----------

def page_dashboard():
    st.markdown(
        f'<div class="welcome-card">'
        f'<div class="welcome-title">Welcome back, {html.escape(st.session_state.get("username", ""))}!</div>'
        f'<div class="welcome-sub">Your personal academic tracker is ready.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    page_header(*PAGE_TITLES["Dashboard"])
    flash()
    components.html(_clock_html(), height=110)
    r = db.rekap_keseluruhan()
    pct = round(r["jml_hadir"] / r["jml_pertemuan"] * 100) if r["jml_pertemuan"] else 0
    stat_cards(
        [
            ("Matakuliah", r["jml_matakuliah"], "#2563eb"),
            ("Total Pertemuan", r["jml_pertemuan"], "#0ea5e9"),
            ("Hadir", r["jml_hadir"], "#10b981"),
            ("Alpa", r["jml_alpa"], "#ef4444"),
            ("Izin / Sakit", r["jml_keterangan"], "#f59e0b"),
            ("Kehadiran", f"{pct}%", "#8b5cf6"),
            ("Tugas Diserahkan", f"{r['jml_tugas_selesai']}/{r['jml_tugas']}", "#06b6d4"),
            ("Total UTS SELESAI", r["jml_uts_selesai"], "#f472b6"),
            ("Total UAS SELESAI", r["jml_uas_selesai"], "#a78bfa"),
        ]
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="panel"><div class="panel-title">Rekap per Matakuliah</div>', unsafe_allow_html=True)
        rows = db.matakuliah_list()
        if rows:
            df = pd.DataFrame(rows)
            df["kehadiran"] = df.apply(
                lambda x: f"{round(x['hadir'] / x['total_pertemuan'] * 100)}%" if x["total_pertemuan"] else "-",
                axis=1,
            )
            tabel_html(
                df[["nama", "total_pertemuan", "hadir", "alpa", "kehadiran"]].rename(
                    columns={
                        "nama": "Matakuliah",
                        "total_pertemuan": "Pertemuan",
                        "hadir": "Hadir",
                        "alpa": "Alpa",
                    }
                ),
                height=300,
            )
        else:
            st.info("Belum ada matakuliah. Tambahkan di menu Jadwal Kuliah.")
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="panel"><div class="panel-title">Kehadiran per Semester</div>', unsafe_allow_html=True)
        bulan = db.hadir_per_bulan()
        if bulan:
            dfb = pd.DataFrame(bulan)
            st.bar_chart(dfb.set_index("bulan"), color=["#10b981", "#ef4444", "#f59e0b", "#94a3b8"])
        else:
            st.info("Belum ada data absen.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="panel-title">Tugas yang Sudah Diserahkan</div>', unsafe_allow_html=True)
    done = db.tugas_list(status="Diserahkan")
    if done:
        tabel_html(
            pd.DataFrame(done)[["matakuliah", "tipe", "judul", "deadline", "tanggal_selesai", "nilai"]].rename(
                columns={
                    "matakuliah": "Matakuliah",
                    "tipe": "Tipe",
                    "judul": "Judul Tugas",
                    "deadline": "Deadline",
                    "tanggal_selesai": "Diserahkan",
                    "nilai": "Nilai",
                }
            ),
            height=250,
        )
    else:
        st.info("Belum ada tugas yang diserahkan. Semangat!")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="panel-title">Tugas yang Belum Diserahkan / Tidak Diserahkan</div>', unsafe_allow_html=True)
    belum = [t for t in db.tugas_list() if t["status"] != "Diserahkan"]
    jml_terlambat = sum(1 for t in belum if t["status_tampil"] == "Terlambat")
    if belum:
        dfu = pd.DataFrame(belum)[["matakuliah", "tipe", "judul", "deadline", "status_tampil"]].rename(
            columns={
                "matakuliah": "Matakuliah",
                "tipe": "Tipe",
                "judul": "Judul Tugas",
                "deadline": "Deadline",
                "status_tampil": "Status",
            }
        )
        tabel_html(dfu, height=300)
        if jml_terlambat:
            st.warning(f"{jml_terlambat} tugas di antaranya sudah melewati deadline (Terlambat).")
    else:
        st.success("Semua tugas sudah diserahkan. Mantap!")
    st.markdown("</div>", unsafe_allow_html=True)


# ---------- Jadwal Kuliah ----------

def page_jadwal():
    page_header(*PAGE_TITLES["Jadwal Kuliah"])
    flash()

    ver = st.session_state.get("_mk_form_ver", 0)
    tutup_form = st.session_state.pop("_mk_form_tutup", False)
    with st.expander("Tambah Matakuliah + Jadwal", expanded=not tutup_form):
        c1, c2 = st.columns(2)
        kode = c1.text_input("Kode MK", key=f"kode_mk_{ver}")
        nama = c2.text_input("Matakuliah", key=f"nama_mk_{ver}")
        c3, c4 = st.columns(2)
        dosen = c3.text_input("Dosen", key=f"dosen_mk_{ver}")
        sks = c4.number_input("SKS", min_value=1, max_value=6, value=3, key=f"sks_mk_{ver}")
        t1, t2 = st.columns(2)
        jam_masuk = t1.text_input("Jam Masuk", value="08:00", key=f"jm_mulai_{ver}")
        jam_selesai = t2.text_input("Jam Selesai", value="12:40", key=f"jm_selesai_{ver}")
        c5, c6 = st.columns(2)
        hari = c5.selectbox("Hari", db.HARI, key=f"hari_mk_{ver}")
        ruang = c6.text_input("Ruang", key=f"ruang_mk_{ver}")
        st.caption("Jam selesai diisi manual sesuai jadwal kampus.")
        if st.button("Simpan", type="primary", width="stretch"):
            jm = _norm_jam(jam_masuk)
            js = _norm_jam(jam_selesai)
            if not nama.strip():
                st.error("Nama matakuliah wajib diisi.")
            elif jm is None:
                st.error("Jam masuk tidak valid (contoh: 10:10).")
            elif js is None:
                st.error("Jam selesai tidak valid (contoh: 12:40).")
            elif js <= jm:
                st.error("Jam selesai harus setelah jam masuk.")
            else:
                mid = db.add_matakuliah(
                    kode.strip(), nama.strip(), dosen.strip(), int(sks), jm, js,
                )
                if mid is None:
                    st.error(f"Matakuliah dengan kode '{kode}' sudah ada.")
                else:
                    db.add_jadwal(
                        mid, hari, jm, js, ruang.strip(),
                    )
                    st.session_state["flash"] = f"Matakuliah '{nama}' + jadwal ditambahkan."
                    st.session_state["_mk_form_ver"] = ver + 1
                    st.session_state["_mk_form_tutup"] = True
                    sync.push()
                    st.rerun()

    mk_list = db.matakuliah_list()

    st.markdown(f'<div class="panel"><div class="panel-title">Daftar Jadwal ({len(db.jadwal_list())})</div>', unsafe_allow_html=True)
    jdwl = db.jadwal_list()
    if jdwl:
        df = pd.DataFrame(jdwl)[["matakuliah", "hari", "jam_mulai", "jam_selesai", "ruang", "dosen"]].rename(
            columns={
                "matakuliah": "Matakuliah", "hari": "Hari",
                "jam_mulai": "Mulai", "jam_selesai": "Selesai",
                "ruang": "Ruang", "dosen": "Dosen",
            }
        )
        sel, pos = select_table(df, "tbl_jdwl", height=300)
        if sel:
            jid = jdwl[pos]["id"]
            if st.button("Hapus Jadwal", width="stretch"):
                hapus_dialog(f"jadwal {sel['Matakuliah']} {sel['Hari']} {sel['Mulai']}", lambda: db.delete_jadwal(jid))
    else:
        st.info("Belum ada jadwal.")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(f'<div class="panel"><div class="panel-title">Daftar Matakuliah ({len(mk_list)})</div>', unsafe_allow_html=True)
    dfm = pd.DataFrame(mk_list)
    if not dfm.empty:
        dfm["jam"] = dfm.apply(
            lambda x: f"{x['jam_masuk']} - {x['jam_selesai']}" if x["jam_masuk"] else "-",
            axis=1,
        )
        dfm = dfm[["nama", "kode", "dosen", "sks", "jam"]].rename(
            columns={"nama": "Matakuliah", "kode": "Kode", "dosen": "Dosen", "sks": "SKS", "jam": "Jam Masuk"}
        )
        selm, posm = select_table(dfm, "tbl_mk", height=260)
        if selm:
            mid_sel = mk_list[posm]["id"]
            st.caption("Menghapus matakuliah ikut menghapus jadwal, absen, dan tugasnya.")
            if st.button("Hapus Matakuliah", width="stretch"):
                hapus_dialog(selm["Matakuliah"], lambda: db.delete_matakuliah(mid_sel))
    else:
        st.info("Belum ada matakuliah.")
    st.markdown("</div>", unsafe_allow_html=True)


# ---------- Absen ----------

def page_absen():
    page_header(*PAGE_TITLES["Absen"])
    flash()

    mk_list = db.matakuliah_list()
    if not mk_list:
        st.info("Tambahkan matakuliah dulu di menu Jadwal Kuliah.")
        return

    # ---------- Absen Cepat Hari Ini (otomatis dari jadwal + window waktu) ----------
    st.markdown(
        '<div class="panel"><div class="panel-title">Absen Cepat · Jadwal Hari Ini</div>'
        '<div class="absen-rule">MK muncul otomatis H-10 menit sebelum mulai, '
        'bisa diabsen sampai +1 jam setelah selesai.</div>',
        unsafe_allow_html=True,
    )
    tgl_hari = _now_wib().date()
    hari_nama = db.HARI[tgl_hari.weekday()]
    st.markdown(
        f'<div class="absen-hari">Hari: <b>{hari_nama}</b> · {tgl_hari.isoformat()}</div>',
        unsafe_allow_html=True,
    )
    jdwl = db.jadwal_list(hari=hari_nama)
    if not jdwl:
        st.info(f"Tidak ada jadwal kuliah hari {hari_nama}.")
    else:
        catat = {a["id_matakuliah"]: a for a in db.absensi_by_tanggal(tgl_hari.isoformat())}
        for j in jdwl:
            sub = j["kode"] or "-"
            if j["ruang"]:
                sub += f" · {j['ruang']}"
            ada = catat.get(j["id_matakuliah"])
            win, ket, buka_ep, tutup_ep = _window_absen(j)
            if ada:
                badge = (
                    f'<span class="tbl-badge" style="color:{_WARNA_STATUS.get(ada["status"], "#94a3b8")}">'
                    f'{ada["status"]}</span>'
                )
            elif win == "aktif":
                badge = '<span class="tbl-badge" style="color:#60a5fa">Bisa absen</span>'
            elif win == "belum":
                badge = '<span class="tbl-badge" style="color:#94a3b8">Belum waktunya</span>'
            else:
                badge = '<span class="tbl-badge" style="color:#ef4444">Terlewat</span>'
            c1, c2, c3 = st.columns([1.2, 2.9, 1.5])
            c1.markdown(f"**{j['jam_mulai'] or '-'}**")
            c2.markdown(
                f"**{j['matakuliah']}**<br><small class='absen-sub'>{sub}</small>",
                unsafe_allow_html=True,
            )
            uid_t = f"tm_{j['id_matakuliah']}_{win}_{tgl_hari.isoformat()}"
            if win == "belum" and buka_ep:
                with c3:
                    components.html(
                        _timer_html(uid_t, buka_ep, badge, "Buka dalam", "Sudah buka"),
                        height=30,
                    )
            elif win in ("aktif", "lewat") and tutup_ep:
                with c3:
                    components.html(
                        _timer_html(uid_t, tutup_ep, badge, "Locked dalam", "Absensi ditutup"),
                        height=30,
                    )
            else:
                c3.markdown(badge, unsafe_allow_html=True)
            if win == "aktif":
                kb = st.columns(4)
                for stt, kol in zip(db.STATUS_ABSEN, kb):
                    kunci = f"ck_{j['id_matakuliah']}_{stt}_{tgl_hari.isoformat()}"
                    dis = ada is not None and ada["status"] == stt
                    if kol.button(stt, width="stretch", key=kunci, disabled=dis):
                        db.set_absensi(j["id_matakuliah"], tgl_hari.isoformat(), stt)
                        st.session_state["flash"] = f"{j['matakuliah']} · {hari_nama} → {stt} ✔"
                        sync.push()
                        st.rerun()
            elif not ada:
                st.markdown(
                    f'<div class="absen-lock">Locked · {ket}</div>',
                    unsafe_allow_html=True,
                )
    st.markdown("</div>", unsafe_allow_html=True)

    labels = [f"{m['nama']} ({m['kode']})" if m["kode"] else m["nama"] for m in mk_list]
    lbl = st.selectbox("Pilih Matakuliah", labels)
    m = mk_list[labels.index(lbl)]

    pct = round(m["hadir"] / m["total_pertemuan"] * 100) if m["total_pertemuan"] else 0
    stat_cards(
        [
            ("Total Pertemuan", m["total_pertemuan"], "#0ea5e9"),
            ("Hadir", m["hadir"], "#10b981"),
            ("Alpa", m["alpa"], "#ef4444"),
            ("Izin / Sakit", m["izin_sakit"], "#f59e0b"),
            ("Kehadiran", f"{pct}%", "#8b5cf6"),
        ]
    )

    ab_ver = st.session_state.get("_absen_ver", 0)
    with st.expander("Input Kehadiran", expanded=True):
        tgl_hari_ini = _now_wib().date()
        c1, c2 = st.columns(2)
        with c1:
            tanggal = st.date_input(
                "Tanggal", value=tgl_hari_ini, key=f"absen_tgl_{ab_ver}",
                min_value=tgl_hari_ini, max_value=tgl_hari_ini,
            )
        with c2:
            status = st.selectbox("Status", db.STATUS_ABSEN, key=f"absen_status_{ab_ver}")
        catatan = st.text_input("Catatan (opsional)", key=f"absen_cat_{ab_ver}")
        st.markdown(f"**Hari: {db.HARI[tgl_hari_ini.weekday()]}**")
        jdwl_mk = [
            j for j in db.jadwal_list(hari=db.HARI[tgl_hari_ini.weekday()])
            if j["id_matakuliah"] == m["id"]
        ]
        win_mk = [_window_absen(j) for j in jdwl_mk]
        boleh = bool(jdwl_mk) and any(w[0] == "aktif" for w in win_mk)
        if not jdwl_mk:
            st.warning(
                f"Tidak ada jadwal {m['nama']} hari ini. Absen hanya bisa dicatat "
                "saat MK berlangsung (H-10 menit sampai +1 jam setelah selesai)."
            )
        elif not boleh:
            rincian = " · ".join(
                f"{j['jam_mulai']}-{j['jam_selesai']}: {w[1]}"
                for j, w in zip(jdwl_mk, win_mk) if w[0] != "aktif"
            )
            st.warning(f"Window absen {m['nama']} hari ini sedang tidak terbuka. {rincian}")
        if st.button("Simpan", type="primary", width="stretch", disabled=not boleh):
            ok = db.add_absensi(
                m["id"], tanggal.isoformat(), status, catatan.strip()
            )
            if not ok:
                st.error(f"Absen untuk {tanggal.isoformat()} sudah tercatat.")
            else:
                st.session_state["flash"] = f"Absen {status} untuk {m['nama']} tanggal {tanggal.isoformat()} ({db.HARI[tanggal.weekday()]}) tersimpan."
                st.session_state["_absen_ver"] = ab_ver + 1
                sync.push()
                st.rerun()

    rows = db.absensi_list(id_matakuliah=m["id"])
    st.markdown(f'<div class="panel"><div class="panel-title">Riwayat Absen ({len(rows)})</div>', unsafe_allow_html=True)
    if rows:
        df = pd.DataFrame(rows)[["tanggal", "status", "catatan"]].rename(
            columns={"tanggal": "Tanggal", "status": "Status", "catatan": "Catatan"}
        )
        sel, pos = select_table(df, "tbl_absen", height=300)
        if sel:
            aid = rows[pos]["id"]
            if st.button("Hapus Absen", width="stretch"):
                hapus_dialog(f"absen {sel['Tanggal']} ({sel['Status']})", lambda: db.delete_absensi(aid))
    else:
        st.info("Belum ada catatan absen untuk matakuliah ini.")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="panel-title">Rekap Semua Matakuliah</div>', unsafe_allow_html=True)
    all_mk = db.matakuliah_list()
    if all_mk:
        dfr = pd.DataFrame(all_mk)
        dfr["kehadiran"] = dfr.apply(
            lambda x: f"{round(x['hadir'] / x['total_pertemuan'] * 100)}%" if x["total_pertemuan"] else "-",
            axis=1,
        )
        tabel_html(
            dfr[["nama", "total_pertemuan", "hadir", "alpa", "izin_sakit", "kehadiran"]].rename(
                columns={
                    "nama": "Matakuliah", "total_pertemuan": "Pertemuan",
                    "hadir": "Hadir", "alpa": "Alpa",
                    "izin_sakit": "Izin/Sakit",
                }
            ),
            height=300,
        )
    st.markdown("</div>", unsafe_allow_html=True)


# ---------- Tugas (Harian & UTS/UAS) ----------

@st.dialog("Ubah Tugas")
def edit_tugas(t, tid):
    with st.form("edit_tugas"):
        judul = st.text_input("Judul", value=t["judul"])
        deskripsi = st.text_area("Deskripsi", value=t["deskripsi"])
        try:
            _dl = datetime.fromisoformat(t["deadline"]) if t["deadline"] else None
        except ValueError:
            _dl = None
        c1, c2 = st.columns(2)
        deadline = c1.date_input("Deadline", value=_dl.date() if _dl else date.today())
        jam_dl = c2.time_input(
            "Pukul", value=_dl.time() if _dl else time(23, 59), step=timedelta(minutes=5)
        )
        c3, c4 = st.columns(2)
        status = c3.selectbox("Status", db.STATUS_TUGAS, index=db.STATUS_TUGAS.index(t["status"]))
        nilai = c4.number_input("Nilai (jika sudah dinilai)", min_value=0.0, max_value=100.0,
                                value=float(t["nilai"]) if t["nilai"] is not None else 0.0)
        submitted = st.form_submit_button("Simpan Perubahan", type="primary", width="stretch")
    if submitted:
        if not judul.strip():
            st.error("Judul wajib diisi.")
        else:
            db.update_tugas(
                tid, judul=judul.strip(), deskripsi=deskripsi.strip(),
                deadline=datetime.combine(deadline, jam_dl).strftime("%Y-%m-%d %H:%M"),
                status=status,
                tanggal_selesai=date.today().isoformat(),
                nilai=nilai if nilai else None,
            )
            st.session_state["flash"] = "Tugas diperbarui."
            sync.push()
            st.rerun()


def page_tugas(tipe_filter):
    is_ujian = tipe_filter is None
    tipe_nama = "UTS/UAS" if is_ujian else "Tugas Harian"
    page_header(
        "UTS & UAS" if is_ujian else "Tugas Harian",
        "Catat tugas " + ("ujian" if is_ujian else "harian") + " yang kamu buat.",
    )
    flash()

    mk_list = db.matakuliah_list()
    if not mk_list:
        st.info("Tambahkan matakuliah dulu di menu Jadwal Kuliah.")
        return

    tgs_ver = st.session_state.get("_tgs_ver", 0)
    with st.expander("Tambah Tugas", expanded=True):
        with st.form("frm_tgs"):
            mk = st.selectbox(
                "Matakuliah",
                [f"{m['nama']} ({m['kode']})" if m["kode"] else m["nama"] for m in mk_list],
                key=f"tgs_mk_{tgs_ver}",
            )
            c1, c2 = st.columns(2)
            if is_ujian:
                tipe = c1.selectbox("Tipe", ["UTS", "UAS"], key=f"tgs_tipe_{tgs_ver}")
            else:
                tipe = "Harian"
            d1, d2 = c2.columns(2)
            deadline = d1.date_input("Deadline", value=date.today(), key=f"tgs_dl_{tgs_ver}")
            jam_dl = d2.time_input("Pukul", value=time(23, 59), step=timedelta(minutes=5), key=f"tgs_jam_{tgs_ver}")
            judul = st.text_input("Judul", key=f"tgs_judul_{tgs_ver}")
            deskripsi = st.text_area("Deskripsi (opsional)", key=f"tgs_desk_{tgs_ver}")
            c3, c4 = st.columns(2)
            status = c3.selectbox("Status", db.STATUS_TUGAS, key=f"tgs_status_{tgs_ver}")
            nilai = c4.number_input("Nilai (jika sudah dinilai)", min_value=0.0, max_value=100.0, value=0.0, key=f"tgs_nilai_{tgs_ver}")
            submitted = st.form_submit_button("Simpan", type="primary", width="stretch")
        if submitted:
            if not judul.strip():
                st.error("Judul wajib diisi.")
            else:
                mid = mk_list[mk.index(mk)]["id"]
                db.add_tugas(
                    mid, tipe, judul.strip(), deskripsi.strip(),
                    datetime.combine(deadline, jam_dl).strftime("%Y-%m-%d %H:%M"),
                    status,
                    nilai if nilai else None,
                )
                st.session_state["flash"] = f"Tugas {tipe} '{judul}' ditambahkan."
                st.session_state["_tgs_ver"] = tgs_ver + 1
                sync.push()
                st.rerun()

    st.markdown("Filter status:", unsafe_allow_html=True)
    f_status = st.segmented_control(
        "f_status", ["Semua", "Belum", "Terlambat", "Diserahkan"], default="Semua",
        key="filt_tugas", label_visibility="collapsed",
    )

    rows = db.tugas_list(tipe=tipe_filter)
    if is_ujian:
        rows = [r for r in rows if r["tipe"] in ("UTS", "UAS")]
    diserahkan = sum(1 for t in rows if t["status"] == "Diserahkan")
    terlambat = [t for t in rows if t["status_tampil"] == "Terlambat"]
    if f_status == "Semua":
        rows_tampil = rows
    else:
        rows_tampil = [t for t in rows if t["status_tampil"] == f_status]

    if terlambat:
        st.warning(
            f"{len(terlambat)} tugas sudah melewati deadline dan belum diserahkan: "
            + ", ".join(f"'{t['judul']}'" for t in terlambat)
        )

    st.markdown(f'<div class="panel"><div class="panel-title">Daftar {tipe_nama} ({diserahkan} diserahkan / {len(rows_tampil)} tampil)</div>', unsafe_allow_html=True)
    if rows_tampil:
        df = pd.DataFrame(rows_tampil)[["matakuliah", "judul", "deadline", "status_tampil", "nilai"]].rename(
            columns={
                "matakuliah": "Matakuliah", "judul": "Judul",
                "deadline": "Deadline", "status_tampil": "Status", "nilai": "Nilai",
            }
        )
        df["Nilai"] = df["Nilai"].fillna("-").apply(lambda v: f"{v:g}" if v != "-" else "-")

        sel, pos = select_table(df, "tbl_tgs", height=320)
        if sel:
            tid = rows_tampil[pos]["id"]
            t = rows_tampil[pos]
            c1, c2, c3 = st.columns(3)
            if c1.button("Tandai Diserahkan", type="primary", width="stretch", disabled=t["status"] == "Diserahkan"):
                db.update_tugas(tid, status="Diserahkan", tanggal_selesai=date.today().isoformat())
                st.session_state["flash"] = f"'{t['judul']}' ditandai diserahkan."
                sync.push()
                st.rerun()
            if c2.button("Ubah", width="stretch"):
                edit_tugas(t, tid)
            if c3.button("Hapus", width="stretch"):
                hapus_dialog(t["judul"], lambda: db.delete_tugas(tid))
    else:
        st.info("Belum ada tugas.")
    st.markdown("</div>", unsafe_allow_html=True)


# ---------- Login ----------

def page_login():
    st.markdown(
        '<div class="login-card">'
        '<div class="user-avatar login-avatar">NF</div>'
        '<div class="login-title">SIKAD PRIBADI</div>'
        '<div class="login-sub">Masuk untuk melanjutkan</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    col = st.columns([1, 1, 1])[1]
    if not db.login_exists():
        col.info("Buat akun dulu (pertama kali):")
        with col.form("frm_buat_akun"):
            u = st.text_input("Nama Lengkap")
            p1 = st.text_input("NIM (Password)", type="password")
            p2 = st.text_input("Ulangi NIM", type="password")
            buat = st.form_submit_button("Buat Akun", type="primary", width="stretch")
        if buat:
            if not u.strip() or not p1:
                col.error("Nama lengkap dan NIM wajib diisi.")
            elif p1 != p2:
                col.error("NIM tidak sama.")
            elif len(p1) < 4:
                col.error("NIM minimal 4 karakter.")
            else:
                db.create_login(u.strip(), p1, p1)
                col.success(f"Akun '{u.strip()}' dibuat. Silakan masuk.")
                st.rerun()
    else:
        with col.form("frm_login"):
            u = st.text_input("Nama Lengkap")
            p = st.text_input("NIM (Password)", type="password")
            masuk = st.form_submit_button("Masuk", type="primary", width="stretch")
        if masuk:
            nama = db.check_login(u.strip(), p)
            if nama:
                st.session_state["logged_in"] = True
                st.session_state["username"] = nama
                st.rerun()
            else:
                col.error("Nama atau NIM salah.")


# ---------- Utama ----------

if "synced_once" not in st.session_state:
    sync.pull()
    st.session_state["synced_once"] = True

if not st.session_state.get("logged_in"):
    page_login()
    st.stop()

st.sidebar.markdown('<div class="sidebar-brand">SIKAD PRIBADI</div>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="sidebar-sub">Catatan pribadi kuliah</div>', unsafe_allow_html=True)
_akun = db.get_login()
_nama = _akun.get("username", "") if _akun else st.session_state.get("username", "")
_inisial = "".join([w[0].upper() for w in _nama.split()[:2]]) or "U"
_role = "Mahasiswa"
if _akun and _akun.get("nim"):
    _role += f" | {_akun['nim']}"
st.sidebar.markdown(
    f'<div class="user-box">'
    f'<div class="user-avatar">{html.escape(_inisial)}</div>'
    f'<div><div class="user-name">{html.escape(_nama)}</div>'
    f'<div class="user-role">{html.escape(_role)}</div></div>'
    f'</div>',
    unsafe_allow_html=True,
)

page = st.sidebar.radio("Menu", list(PAGE_TITLES), label_visibility="collapsed")

if st.sidebar.button("Keluar", width="stretch"):
    st.session_state["logged_in"] = False
    st.session_state.pop("username", None)
    st.rerun()

mode = sync.STATUS["mode"]
warna = {"online": "🟢", "lokal": "🟡", "error": "🔴"}.get(mode, "🟡")
st.sidebar.markdown(
    f'<div class="sync-box">{warna} {html.escape(sync.STATUS["pesan"])}</div>',
    unsafe_allow_html=True,
)

if page == "Dashboard":
    page_dashboard()
elif page == "Jadwal Kuliah":
    page_jadwal()
elif page == "Absen":
    page_absen()
elif page == "Tugas Harian":
    page_tugas("Harian")
elif page == "UTS & UAS":
    page_tugas(None)

st.sidebar.markdown(
    '<div class="sidebar-foot">Aplikasi pribadi — data tersimpan otomatis.</div>',
    unsafe_allow_html=True,
)

