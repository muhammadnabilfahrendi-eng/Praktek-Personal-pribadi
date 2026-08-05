import base64
import html
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import db
import sync

try:
    from pandas.io.formats.style import Styler
except Exception:  # pragma: no cover
    Styler = None

# Penanda proses: sinkronisasi cloud cukup sekali (lihat blok "Utama").
_SYNC_DONE = {}


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


_TIME_PICKER = components.declare_component(
    "time_picker", path=str(Path(__file__).resolve().parent / "components" / "time_picker")
)


def _time_picker_ui(label, value, key):
    """Picker jam popup (native browser). Mengembalikan 'HH:MM' atau ''."""
    res = _TIME_PICKER(value=value, label=label, key=key)
    return value if res is None else (res or "")


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
    """Jam real-time WIB: jam besar + label WIB kecil sejajar, tanggal di bawah."""
    tpl = """<div style="text-align:center;max-width:420px;margin:0 auto;padding:14px 18px;border-radius:14px;border:1px solid rgba(96,165,250,.35);background:linear-gradient(120deg,rgba(59,130,246,.16),rgba(6,182,212,.12));font-family:'Segoe UI',sans-serif">
<div id="clk_jam_UID" style="font-size:2.1rem;font-weight:800;color:#f8fafc;letter-spacing:1px;font-variant-numeric:tabular-nums">--:--:--</div>
<div style="font-size:.8rem;color:#7f8ea3;margin-top:2px">WIB (UTC+7)</div>
</div>
<div id="clk_tgl_UID" style="text-align:center;margin-top:6px;font-size:.95rem;font-weight:700;color:#e2e8f0;font-family:'Segoe UI',sans-serif">-</div>
<script>
(function() {
  var HARI = ['Minggu','Senin','Selasa','Rabu','Kamis','Jumat','Sabtu'];
  var BLN = ['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'];
  function p(n) { return (n < 10 ? '0' : '') + n; }
  function tick() {
    var d = new Date(Date.now() + 7 * 3600 * 1000);
    var jam = p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ':' + p(d.getUTCSeconds());
    var tgl = HARI[d.getUTCDay()] + ', ' + d.getUTCDate() + ' ' + BLN[d.getUTCMonth()] + ' ' + d.getUTCFullYear();
    document.getElementById('clk_jam_UID').textContent = jam;
    document.getElementById('clk_tgl_UID').textContent = tgl;
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
.block-container { padding-top: 0.1rem; }
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
    "Pengaturan": ("Pengaturan", "Pengisian jadwal kuliah (periode & buka/tutup) dan kelola akun user (khusus admin)."),
    "Tugas Massal": ("Tugas Massal", "Tambah tugas ke banyak akun sekaligus (khusus admin)."),
    "Data Mahasiswa": ("Data Mahasiswa", "Lihat dan kelola data akun terpilih (khusus admin)."),
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
    "Terlambat": "#fbbf24", "Belum": "#f87171", "Diserahkan": "#34d399",
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
    components.html(_clock_html(), height=130)
    st.markdown(
        f'<div class="welcome-card">'
        f'<div class="welcome-title">Welcome back, {html.escape(st.session_state.get("username", ""))}!</div>'
        f'<div class="welcome-sub">Your personal academic tracker is ready.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    page_header(*PAGE_TITLES["Dashboard"])
    flash()

    sesi = db.absen_sesi_aktif(_user, _now_wib().strftime("%Y-%m-%d %H:%M"))
    if sesi:
        info_batas = f" (batas {sesi['batas']})" if sesi["batas"] else ""
        st.warning(
            f"📢 Absensi **{sesi['matakuliah']}** dibuka oleh admin{info_batas} — "
            "jangan sampai terlewat, absen sekarang!"
        )
        if st.button("Absen Sekarang", type="primary", width="stretch"):
            db.set_absensi(_user, sesi["id_matakuliah"], _now_wib().date().isoformat(), "Hadir")
            st.session_state["flash"] = f"Absen {sesi['matakuliah']} → Hadir ✔"
            sync.push()
            st.rerun()

    notif_belum = db.notif_belum_dibaca(_user)
    if notif_belum:
        st.markdown(f'<div class="panel"><div class="panel-title">Notifikasi ({len(notif_belum)})</div>', unsafe_allow_html=True)
        for n in notif_belum:
            ikon = {"absen": "📢", "tugas": "📝", "info": "ℹ️"}.get(n["jenis"], "ℹ️")
            st.markdown(
                f'<div class="absen-rule">{ikon} <b>{html.escape(n["pesan"])}</b>'
                f'<br><small>{html.escape(n["tanggal"])}</small></div>',
                unsafe_allow_html=True,
            )
        if st.button("Tandai semua dibaca", width="stretch"):
            db.tandai_notifikasi_dibaca(_user)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    r = db.rekap_keseluruhan(_user)
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
        rows = db.matakuliah_list(_user)
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
        bulan = db.hadir_per_bulan(_user)
        if bulan:
            dfb = pd.DataFrame(bulan)
            st.bar_chart(dfb.set_index("bulan"), color=["#10b981", "#ef4444", "#f59e0b", "#94a3b8"])
        else:
            st.info("Belum ada data absen.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="panel-title">Tugas yang Sudah Diserahkan</div>', unsafe_allow_html=True)
    done = [t for t in db.tugas_list(_user) if t["status"] in ("Diserahkan", "Terlambat")]
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
            ),            height=250,
        )
    else:
        st.info("Belum ada tugas yang diserahkan. Semangat!")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="panel-title">Tugas yang Belum Diserahkan / Tidak Diserahkan</div>', unsafe_allow_html=True)
    belum = [t for t in db.tugas_list(_user) if t["status"] == "Belum"]
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

    if _is_admin:
        st.markdown('<div class="panel"><div class="panel-title">Rekap Semua Akun</div>', unsafe_allow_html=True)
        ak_rows = db.akun_list()
        if ak_rows:
            dfr = []
            for r in ak_rows:
                d = db.rekap_keseluruhan(r["username"])
                pct_r = round(d["jml_hadir"] / d["jml_pertemuan"] * 100) if d["jml_pertemuan"] else 0
                dfr.append(
                    {
                        "Nama": r["username"],
                        "NIM": r["nim"],
                        "Matakuliah": r["jml_matakuliah"],
                        "Jadwal": r["jml_jadwal"],
                        "Absen": r["jml_absen"],
                        "Hadir": d["jml_hadir"],
                        "Kehadiran": f"{pct_r}%",
                        "Tugas Selesai": f"{d['jml_tugas_selesai']}/{d['jml_tugas']}",
                    }
                )
            tabel_html(pd.DataFrame(dfr), height=260)
        else:
            st.info("Belum ada akun user terdaftar.")
        st.markdown("</div>", unsafe_allow_html=True)


# ---------- Jadwal Kuliah ----------

def page_jadwal(head=True):
    if head:
        page_header(*PAGE_TITLES["Jadwal Kuliah"])
    flash()

    tgl_ini = _now_wib().date()
    w = db.jadwal_window()
    boleh_isi = _is_admin or db.jadwal_boleh_isi(tgl_ini.isoformat())

    if boleh_isi:
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
            with t1:
                jam_masuk = _time_picker_ui("Jam Masuk", "08:00", f"jm_pick_mulai_{ver}")
            with t2:
                jam_selesai = _time_picker_ui("Jam Selesai", "12:40", f"jm_pick_selesai_{ver}")
            c5, c6 = st.columns(2)
            hari = c5.selectbox("Hari", db.HARI, key=f"hari_mk_{ver}")
            ruang = c6.text_input("Ruang", key=f"ruang_mk_{ver}")
            st.caption("Jam selesai diisi manual sesuai jadwal kampus.")
            if st.button("Simpan", type="primary", width="stretch", key=f"jdwl_simpan_{ver}"):
                jm = jam_masuk
                js = jam_selesai
                if not nama.strip():
                    st.error("Nama matakuliah wajib diisi.")
                elif not jm or not js:
                    st.error("Jam masuk dan jam selesai wajib diisi.")
                elif js <= jm:
                    st.error("Jam selesai harus setelah jam masuk.")
                else:
                    mid = db.add_matakuliah(
                        _user,
                        kode.strip(), nama.strip(), dosen.strip(), int(sks), jm, js,
                    )
                    if mid is None:
                        st.error(f"Matakuliah dengan kode '{kode}' sudah ada.")
                    else:
                        db.add_jadwal(
                            _user,
                            mid, hari, jm, js, ruang.strip(),
                        )
                        st.session_state["flash"] = f"Matakuliah '{nama}' + jadwal ditambahkan."
                        st.session_state["_mk_form_ver"] = ver + 1
                        st.session_state["_mk_form_tutup"] = True
                        sync.push()
                        st.rerun()
    else:
        if db.jadwal_locked():
            st.info("🔒 Pengisian jadwal **dinonaktifkan oleh admin** — kamu hanya bisa melihat jadwalmu. Tunggu admin membukanya kembali.")
        else:
            st.info(f"🔒 Pengisian jadwal ditutup. Admin membuka periode pengisian: **{w['mulai']} s/d {w['selesai']}**. Di luar periode itu kamu hanya bisa melihat jadwal.")

    mk_list = db.matakuliah_list(_user)

    st.markdown(f'<div class="panel"><div class="panel-title">Daftar Jadwal ({len(db.jadwal_list(_user))})</div>', unsafe_allow_html=True)
    jdwl = db.jadwal_list(_user)
    if jdwl:
        df = pd.DataFrame(jdwl)[["matakuliah", "hari", "jam_mulai", "jam_selesai", "ruang", "dosen"]].rename(
            columns={
                "matakuliah": "Matakuliah", "hari": "Hari",
                "jam_mulai": "Mulai", "jam_selesai": "Selesai",
                "ruang": "Ruang", "dosen": "Dosen",
            }
        )
        if _is_admin:
            sel, pos = select_table(df, "tbl_jdwl", height=300)
            if sel:
                jid = jdwl[pos]["id"]
                if st.button("Hapus Jadwal", width="stretch", key="jdwl_hapus"):
                    hapus_dialog(f"jadwal {sel['Matakuliah']} {sel['Hari']} {sel['Mulai']}", lambda: db.delete_jadwal(_user, jid))
        else:
            tabel_html(df, height=300)
            st.caption("🔒 Hapus data hanya bisa dilakukan oleh Admin.")
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
        if _is_admin:
            selm, posm = select_table(dfm, "tbl_mk", height=260)
            if selm:
                mid_sel = mk_list[posm]["id"]
                st.caption("Menghapus matakuliah ikut menghapus jadwal, absen, dan tugasnya.")
                if st.button("Hapus Matakuliah", width="stretch", key="mk_hapus"):
                    hapus_dialog(selm["Matakuliah"], lambda: db.delete_matakuliah(_user, mid_sel))
        else:
            tabel_html(dfm, height=260)
            st.caption("🔒 Hapus data hanya bisa dilakukan oleh Admin.")
    else:
        st.info("Belum ada matakuliah.")
    st.markdown("</div>", unsafe_allow_html=True)


# ---------- Absen ----------

def page_absen(head=True):
    if head:
        page_header(*PAGE_TITLES["Absen"])
    flash()

    mk_list = db.matakuliah_list(_user)
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
    jdwl = db.jadwal_list(_user, hari=hari_nama)
    if not jdwl:
        st.info(f"Tidak ada jadwal kuliah hari {hari_nama}.")
    else:
        catat = {a["id_matakuliah"]: a for a in db.absensi_by_tanggal(_user, tgl_hari.isoformat())}
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
                        db.set_absensi(_user, j["id_matakuliah"], tgl_hari.isoformat(), stt)
                        st.session_state["flash"] = f"{j['matakuliah']} · {hari_nama} → {stt} ✔"
                        sync.push()
                        st.rerun()
            elif not ada:
                st.markdown(
                    f'<div class="absen-lock">Locked · {ket}</div>',
                    unsafe_allow_html=True,
                )
    # Sesi absen yang dibuka admin: tampil di Absen Cepat dan bisa diabsen
    # langsung, walau di luar jam jadwal normal (selama sesi masih aktif).
    sesi = db.absen_sesi_aktif(_user, _now_wib().strftime("%Y-%m-%d %H:%M"))
    if sesi:
        info_sesi = f" — batas {sesi['batas']}" if sesi["batas"] else ""
        st.markdown(
            f'<div class="absen-rule" style="color:#10b981">📢 Sesi absen dibuka admin'
            f'{html.escape(info_sesi)} — absen sekarang!</div>',
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns([1.2, 2.9, 1.5])
        c1.markdown("**Sesi admin**")
        c2.markdown(
            f"**{html.escape(sesi['matakuliah'])}**<br><small class='absen-sub'>dibuka admin{html.escape(info_sesi)}</small>",
            unsafe_allow_html=True,
        )
        c3.markdown(
            '<span class="tbl-badge" style="color:#10b981">Bisa absen</span>',
            unsafe_allow_html=True,
        )
        kb = st.columns(4)
        for stt, kol in zip(db.STATUS_ABSEN, kb):
            if kol.button(
                stt, width="stretch",
                key=f"sk_{sesi['id_matakuliah']}_{stt}_{tgl_hari.isoformat()}",
            ):
                db.set_absensi(_user, sesi["id_matakuliah"], tgl_hari.isoformat(), stt)
                st.session_state["flash"] = f"{sesi['matakuliah']} · Sesi admin → {stt} ✔"
                sync.push()
                st.rerun()
    else:
        sesi_terbuka = db.absen_sesi_info(_user, _now_wib().strftime("%Y-%m-%d %H:%M"))
        if sesi_terbuka:
            st.caption(
                f"📢 Sesi absen **{sesi_terbuka['matakuliah']}** dibuka admin, tapi kamu sudah absen hari ini — sesi tidak tampil karena sudah terisi."
            )
    st.markdown("</div>", unsafe_allow_html=True)

    if _is_admin:
        st.markdown('<div class="panel"><div class="panel-title">Buka Absensi (Admin)</div>', unsafe_allow_html=True)
        sesi = db.absen_sesi_info(_user, _now_wib().strftime("%Y-%m-%d %H:%M"))
        if sesi:
            sudah = db.absen_sesi_aktif(_user, _now_wib().strftime("%Y-%m-%d %H:%M")) is None
            ket = " — user sudah absen hari ini, sesi tidak tampil di Absen Cepat." if sudah else ""
            st.caption(f"Sesi aktif: **{sesi['matakuliah']}**{' (batas ' + sesi['batas'] + ')' if sesi['batas'] else ''}{ket}")
            if st.button("Tutup Absensi", width="stretch", key="absen_tutup"):
                db.tutup_absen(_user)
                st.session_state["flash"] = f"Sesi absensi '{sesi['matakuliah']}' ditutup."
                sync.push()
                st.rerun()
        else:
            labels2 = [f"{m['nama']} ({m['kode']})" if m["kode"] else m["nama"] for m in mk_list]
            lbl2 = st.selectbox("Matakuliah yang dibuka", labels2, key="adm_buka_mk")
            m2 = mk_list[labels2.index(lbl2)]
            c1, c2 = st.columns(2)
            with c1:
                batas_tgl = st.date_input("Batas absen (tanggal)", value=date.today())
            with c2:
                batas_jam = _time_picker_ui("Batas absen (jam)", "23:55", "adm_buka_jam")
            if st.button("Buka Absensi", type="primary", width="stretch", key="absen_buka"):
                if not batas_jam:
                    st.error("Jam batas absen wajib diisi.")
                else:
                    batas = datetime.combine(
                        batas_tgl, datetime.strptime(batas_jam, "%H:%M").time()
                    ).strftime("%Y-%m-%d %H:%M")
                    db.buka_absen(_user, m2["id"], batas)
                    db.tambah_notifikasi(
                        _user,
                        f"Absensi '{m2['nama']}' dibuka oleh admin — segera absen sebelum {batas}.",
                        "absen",
                    )
                    st.session_state["flash"] = f"Absensi '{m2['nama']}' dibuka untuk akun {_user}."
                    sync.push()
                    st.rerun()
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

    with st.expander("Lihat Riwayat Absensi", expanded=False):
        st.caption(
            f"Riwayat absensi **{m['nama']}** — tampil hanya saat kamu membuka bagian ini."
        )
        rows = db.absensi_list(_user, id_matakuliah=m["id"])
        if rows:
            detil = []
            for r in rows:
                try:
                    tgl = date.fromisoformat(r["tanggal"])
                    hari = db.HARI[tgl.weekday()]
                except (ValueError, TypeError):
                    hari = "-"
                detil.append(
                    {
                        "matakuliah": m["nama"],
                        "kode": m.get("kode", ""),
                        "hari": hari,
                        "tanggal": r["tanggal"],
                        "jam": r.get("jam", "") or "-",
                        "status": r["status"],
                        "catatan": r["catatan"],
                    }
                )
            df = pd.DataFrame(detil).rename(
                columns={
                    "matakuliah": "Matakuliah", "kode": "Kode", "hari": "Hari",
                    "tanggal": "Tanggal", "jam": "Jam", "status": "Status",
                    "catatan": "Catatan",
                }
            )
            tabel_html(df, height=300)
        else:
            st.info(f"Belum ada catatan absen untuk {m['nama']}.")

    st.markdown('<div class="panel"><div class="panel-title">Rekap Semua Matakuliah</div>', unsafe_allow_html=True)
    all_mk = db.matakuliah_list(_user)
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
def edit_tugas(t, tid, user):
    with st.form("edit_tugas"):
        judul = st.text_input("Judul", value=t["judul"])
        deskripsi = st.text_area("Deskripsi", value=t["deskripsi"])
        try:
            _dl = datetime.fromisoformat(t["deadline"]) if t["deadline"] else None
        except ValueError:
            _dl = None
        c1, c2 = st.columns(2)
        deadline = c1.date_input("Deadline", value=_dl.date() if _dl else date.today())
        with c2:
            jam_dl = _time_picker_ui("Pukul", _dl.strftime("%H:%M") if _dl else "23:55", f"dlg_jam_{tid}")
        c3, c4 = st.columns(2)
        status = c3.selectbox("Status", db.STATUS_TUGAS, index=db.STATUS_TUGAS.index(t["status"]))
        nilai = c4.number_input("Nilai (jika sudah dinilai)", min_value=0.0, max_value=100.0,
                                value=float(t["nilai"]) if t["nilai"] is not None else 0.0)
        submitted = st.form_submit_button("Simpan Perubahan", type="primary", width="stretch")
    if submitted:
        if not judul.strip():
            st.error("Judul wajib diisi.")
        elif not jam_dl:
            st.error("Pukul wajib diisi.")
        else:
            db.update_tugas(
                user, tid, judul=judul.strip(), deskripsi=deskripsi.strip(),
                deadline=datetime.combine(deadline, datetime.strptime(jam_dl, "%H:%M").time()).strftime("%Y-%m-%d %H:%M"),
                status=status,
                tanggal_selesai=date.today().isoformat(),
                nilai=nilai if nilai else None,
            )
            if _is_admin:
                db.tambah_notifikasi(
                    user,
                    f"Tugas '{judul.strip()}' diperbarui oleh admin.",
                    "tugas",
                )
            st.session_state["flash"] = "Tugas diperbarui."
            sync.push()
            st.rerun()


def page_tugas(tipe_filter, head=True):
    is_ujian = tipe_filter is None
    tipe_nama = "UTS/UAS" if is_ujian else "Tugas Harian"
    if head:
        page_header(
            "UTS & UAS" if is_ujian else "Tugas Harian",
            "Catat tugas " + ("ujian" if is_ujian else "harian") + " yang kamu buat.",
        )
    flash()

    mk_list = db.matakuliah_list(_user)
    if not mk_list:
        st.info("Tambahkan matakuliah dulu di menu Jadwal Kuliah.")
        return

    tgs_ver = st.session_state.get("_tgs_ver", 0)
    ukey = tgs_ver * 2 + (1 if is_ujian else 0)
    with st.expander("Tambah Tugas", expanded=True):
        with st.form(f"frm_tgs_{ukey}"):
            mk = st.selectbox(
                "Matakuliah",
                [f"{m['nama']} ({m['kode']})" if m["kode"] else m["nama"] for m in mk_list],
                key=f"tgs_mk_{ukey}",
            )
            c1, c2 = st.columns(2)
            if is_ujian:
                tipe = c1.selectbox("Tipe", ["UTS", "UAS"], key=f"tgs_tipe_{ukey}")
            else:
                tipe = "Harian"
            d1, d2 = c2.columns(2)
            deadline = d1.date_input("Deadline", value=date.today(), key=f"tgs_dl_{ukey}")
            with d2:
                jam_dl = _time_picker_ui("Pukul", "23:55", f"tgs_pick_jam_{ukey}")
            judul = st.text_input("Judul", key=f"tgs_judul_{ukey}")
            deskripsi = st.text_area("Deskripsi (opsional)", key=f"tgs_desk_{ukey}")
            c3, c4 = st.columns(2)
            status = c3.selectbox(
                "Status", db.STATUS_TUGAS if _is_admin else ["Belum", "Diserahkan"],
                key=f"tgs_status_{ukey}",
            )
            nilai = c4.number_input("Nilai (jika sudah dinilai)", min_value=0.0, max_value=100.0, value=0.0, key=f"tgs_nilai_{ukey}")
            submitted = st.form_submit_button("Simpan", type="primary", width="stretch", key=f"tgs_simpan_{ukey}")
        if submitted:
            if not judul.strip():
                st.error("Judul wajib diisi.")
            elif not jam_dl:
                st.error("Pukul wajib diisi.")
            else:
                mid = mk_list[mk.index(mk)]["id"]
                db.add_tugas(
                    _user, mid, tipe, judul.strip(), deskripsi.strip(),
                    datetime.combine(deadline, datetime.strptime(jam_dl, "%H:%M").time()).strftime("%Y-%m-%d %H:%M"),
                    status,
                    nilai if nilai else None,
                )
                if _is_admin:
                    db.tambah_notifikasi(
                        _user,
                        f"Tugas {tipe} '{judul.strip()}' ditambahkan oleh admin.",
                        "tugas",
                    )
                st.session_state["flash"] = f"Tugas {tipe} '{judul}' ditambahkan."
                st.session_state["_tgs_ver"] = tgs_ver + 1
                sync.push()
                st.rerun()

    st.markdown("Filter status:", unsafe_allow_html=True)
    f_status = st.segmented_control(
        "f_status", ["Semua", "Belum", "Terlambat", "Diserahkan"], default="Semua",
        key=f"filt_tugas_{ukey}", label_visibility="collapsed",
    )

    rows = db.tugas_list(_user, tipe=tipe_filter)
    if is_ujian:
        rows = [r for r in rows if r["tipe"] in ("UTS", "UAS")]
    diserahkan = sum(1 for t in rows if t["status"] in ("Diserahkan", "Terlambat"))
    terlambat = [t for t in rows if t["status_tampil"] == "Terlambat" and t["status"] != "Terlambat"]
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

        if _is_admin:
            sel, pos = select_table(df, "tbl_tgs", height=320)
            if sel:
                tid = rows_tampil[pos]["id"]
                t = rows_tampil[pos]
                c1, c2, c3 = st.columns(3)
                if c1.button("Tandai Diserahkan", type="primary", width="stretch", disabled=t["status"] in ("Diserahkan", "Terlambat")):
                    stt = db.serahkan_tugas(_user, tid)
                    st.session_state["flash"] = f"'{t['judul']}' ditandai {'terlambat' if stt == 'Terlambat' else 'diserahkan'}."
                    sync.push()
                    st.rerun()
                if c2.button("Ubah", width="stretch"):
                    edit_tugas(t, tid, _user)
                if c3.button("Hapus", width="stretch"):
                    hapus_dialog(t["judul"], lambda: db.delete_tugas(_user, tid))
        else:
            st.caption("Klik **Tandai Diserahkan** langsung pada matakuliahnya — tanpa perlu memilih baris dulu.")
            for t in rows_tampil:
                sudah = t["status"] in ("Diserahkan", "Terlambat")
                warna = _WARNA_STATUS.get(t["status_tampil"], "#94a3b8")
                sub = f"<small class='absen-sub'>Deadline: {t['deadline'] or '-'}"
                if t.get("nilai") is not None:
                    sub += f" · Nilai: {t['nilai']:g}"
                sub += "</small>"
                c1, c2, c3 = st.columns([2.3, 1.2, 1.3])
                c1.markdown(f"**{t['matakuliah']}** — {t['judul']}<br>{sub}", unsafe_allow_html=True)
                c2.markdown(f'<span class="tbl-badge" style="color:{warna}">{t["status_tampil"]}</span>', unsafe_allow_html=True)
                with c3:
                    if t.get("dikunci"):
                        st.caption('<span class="tbl-badge" style="color:#f87171">Deadline selesai</span>', unsafe_allow_html=True)
                    elif sudah:
                        if st.button("Tandai Belum", width="stretch", key=f"tgs_batal_{t['id']}"):
                            db.batal_tugas(_user, t["id"])
                            st.session_state["flash"] = f"'{t['judul']}' ditandai belum diserahkan."
                            sync.push()
                            st.rerun()
                    else:
                        if st.button("Tandai Diserahkan", type="primary", width="stretch", key=f"tgs_serah_{t['id']}"):
                            stt = db.serahkan_tugas(_user, t["id"])
                            if stt == "Terlambat":
                                st.session_state["flash"] = f"⚠️ '{t['judul']}' diserahkan TERLAMBAT (lewat deadline)."
                            else:
                                st.session_state["flash"] = f"'{t['judul']}' ditandai diserahkan."
                            sync.push()
                            st.rerun()
    else:
        st.info("Belum ada tugas.")
    st.markdown("</div>", unsafe_allow_html=True)


# ---------- Kelola Akun (khusus admin) ----------

def page_kelola():
    page_header(*PAGE_TITLES["Pengaturan"])
    flash()

    st.markdown('<div class="panel"><div class="panel-title">Pengisian Jadwal Kuliah</div>', unsafe_allow_html=True)
    w = db.jadwal_window()
    if w:
        st.caption(f"Periode aktif: **{w['mulai']} s/d {w['selesai']}** — di luar periode itu, user hanya bisa melihat jadwalnya.")
    else:
        st.caption("Periode: **bebas** — semua user bisa mengisi jadwal kapan saja.")
    now = date.today()
    c1, c2 = st.columns(2)
    mulai = c1.date_input("Periode mulai", value=date.fromisoformat(w["mulai"]) if w else now)
    selesai = c2.date_input("Periode selesai", value=date.fromisoformat(w["selesai"]) if w else now + timedelta(days=7))
    b1, b2 = st.columns(2)
    if b1.button("Simpan Periode", type="primary", width="stretch"):
        if selesai < mulai:
            st.error("Tanggal selesai harus setelah tanggal mulai.")
        else:
            db.set_jadwal_window(mulai.isoformat(), selesai.isoformat())
            sync.push()
            st.session_state["flash"] = f"Periode pengisian jadwal: {mulai.isoformat()} s/d {selesai.isoformat()}."
            st.rerun()
    if b2.button("Bebaskan (hapus periode)", width="stretch"):
        db.clear_jadwal_window()
        sync.push()
        st.session_state["flash"] = "Periode pengisian jadwal dihapus — semua user bebas mengisi jadwal."
        st.rerun()
    st.divider()
    if db.jadwal_locked():
        st.caption("Status pengisian jadwal: **terkunci** — semua user hanya bisa melihat jadwalnya.")
        if st.button("Aktifkan Kembali Pengisian Jadwal", width="stretch"):
            db.set_jadwal_locked(False)
            sync.push()
            st.session_state["flash"] = "Pengisian jadwal kuliah diaktifkan kembali."
            st.rerun()
    else:
        st.caption("Status pengisian jadwal: **bebas** — semua user bisa mengisi jadwal.")
        if st.button("Tutup Pengisian Jadwal Kuliah", width="stretch"):
            db.set_jadwal_locked(True)
            sync.push()
            st.session_state["flash"] = "Pengisian jadwal kuliah ditutup — user hanya bisa melihat jadwal."
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    rows = db.akun_list()
    if not rows:
        st.info("Belum ada akun user terdaftar.")
        return

    st.markdown(f'<div class="panel"><div class="panel-title">Akun Terdaftar ({len(rows)})</div>', unsafe_allow_html=True)
    df = pd.DataFrame(rows).rename(
        columns={
            "username": "Nama", "nim": "NIM",
            "jml_matakuliah": "Matakuliah", "jml_jadwal": "Jadwal",
            "jml_absen": "Absen", "jml_tugas": "Tugas",
        }
    )
    df["NIM"] = df["NIM"].astype(str)
    sel, pos = select_table(df, "tbl_akun", height=320)
    st.markdown("</div>", unsafe_allow_html=True)

    if sel:
        target = rows[pos]["username"]
        target_nim = str(rows[pos]["nim"])
        st.caption(f"Akun **{target}** (NIM {target_nim}) — pilih akun di sidebar untuk melihat datanya (Jadwal/Absen/Tugas).")
        c1, c2 = st.columns(2)
        with c1:
            nama_baru = st.text_input("Nama baru", key="k_nama_baru")
            if st.button("Ubah Nama", width="stretch", key="kelola_ubah_nama"):
                hasil = db.ubah_nama(target_nim, nama_baru)
                if hasil == "ok":
                    st.session_state["flash"] = f"Nama akun '{target}' diubah menjadi '{nama_baru.strip()}'."
                    st.rerun()
                else:
                    st.error(hasil)
        with c2:
            sandi_baru = st.text_input("Password baru (kosongkan = NIM)", type="password", key="k_sandi_baru")
            if st.button("Reset Sandi", width="stretch", key="kelola_reset"):
                pw = sandi_baru.strip() or target_nim
                if len(pw) < 4:
                    st.error("Password minimal 4 karakter.")
                else:
                    hasil = db.admin_reset_sandi(target_nim, pw)
                    if hasil == "ok":
                        st.session_state["flash"] = f"Password akun '{target}' direset."
                        sync.push()
                        st.rerun()
                    else:
                        st.error(hasil)
        st.caption("Reset sandi tidak memerlukan jawaban keamanan — admin punya akses penuh.")
        if st.button("Hapus Akun", type="secondary", width="stretch", key="kelola_hapus"):
            hapus_dialog(f"akun '{target}' beserta seluruh datanya", lambda: db.delete_akun(target))


# ---------- Tugas Massal (admin) ----------

def page_tugas_massal():
    page_header(*PAGE_TITLES["Tugas Massal"])
    flash()

    rows = db.akun_list()
    if not rows:
        st.info("Belum ada akun user terdaftar.")
        return

    labels_akun = [f"{r['username']} ({r['nim']})" for r in rows]
    pilih = st.multiselect("Pilih akun", labels_akun)
    dipilih = [rows[labels_akun.index(l)] for l in pilih]

    nama_mk_set = {}
    for r in dipilih:
        for m in db.data_user(r["username"])["matakuliah"]:
            nama_mk_set.setdefault(m["nama"].strip().lower(), m["nama"].strip())
    if not dipilih:
        st.caption("Belum ada akun dipilih — pilih akun dulu untuk melihat daftar matakuliah.")
        return

    mk_labels = list(nama_mk_set.values())
    if not mk_labels:
        st.warning("Akun terpilih belum punya matakuliah — tambahkan dulu lewat Data Mahasiswa → Jadwal Kuliah.")
        return
    mk_pilih = st.selectbox("Matakuliah", mk_labels)

    tgs_ver = st.session_state.get("_ms_ver", 0)
    with st.form("frm_massal"):
        c1, c2 = st.columns(2)
        tipe = c1.selectbox("Tipe", ["Harian", "UTS", "UAS"], key=f"ms_tipe_{tgs_ver}")
        d1, d2 = c2.columns(2)
        deadline = d1.date_input("Deadline", value=date.today(), key=f"ms_dl_{tgs_ver}")
        with d2:
            jam_dl = _time_picker_ui("Pukul", "23:55", f"ms_pick_jam_{tgs_ver}")
        judul = st.text_input("Judul", key=f"ms_judul_{tgs_ver}")
        deskripsi = st.text_area("Deskripsi (opsional)", key=f"ms_desk_{tgs_ver}")
        c3, c4 = st.columns(2)
        status = c3.selectbox("Status", db.STATUS_TUGAS, key=f"ms_status_{tgs_ver}")
        nilai = c4.number_input("Nilai (jika sudah dinilai)", min_value=0.0, max_value=100.0, value=0.0, key=f"ms_nilai_{tgs_ver}")
        kirim = st.form_submit_button(
            f"Kirim ke {len(dipilih)} Akun", type="primary", width="stretch",
            key=f"ms_kirim_{tgs_ver}",
        )
    if kirim:
        if not judul.strip():
            st.error("Judul wajib diisi.")
        elif not jam_dl:
            st.error("Pukul wajib diisi.")
        else:
            dl = datetime.combine(deadline, datetime.strptime(jam_dl, "%H:%M").time()).strftime("%Y-%m-%d %H:%M")
            ok, skip = db.add_tugas_batch(
                [r["username"] for r in dipilih], mk_pilih, tipe, judul.strip(),
                deskripsi.strip(), dl, status, nilai if nilai else None,
            )
            for u in ok:
                db.tambah_notifikasi(u, f"Tugas {tipe} '{judul.strip()}' ditambahkan oleh admin.", "tugas")
            if ok:
                sync.push()
            pesan = f"Tugas {tipe} '{judul.strip()}' dikirim ke {len(ok)} akun."
            if skip:
                pesan += f" Dilewati {len(skip)} akun (tidak punya matakuliah '{mk_pilih}'): {', '.join(skip)}."
            st.session_state["flash"] = pesan
            st.session_state["_ms_ver"] = tgs_ver + 1
            st.rerun()


# ---------- Data Mahasiswa (admin) ----------

def page_data_mahasiswa():
    page_header(*PAGE_TITLES["Data Mahasiswa"])
    flash()

    if not _user:
        st.info("Belum ada akun user — daftarkan dulu lewat halaman login.")
        return
    st.caption(f"Data akun: **{_user}** — pilih akun lain di sidebar 'Lihat data akun'.")
    tabs = st.tabs(["Jadwal Kuliah", "Absen", "Tugas Harian", "UTS & UAS"])
    with tabs[0]:
        page_jadwal(head=False)
    with tabs[1]:
        page_absen(head=False)
    with tabs[2]:
        page_tugas("Harian", head=False)
    with tabs[3]:
        page_tugas(None, head=False)


# ---------- Login ----------

def page_login():
    db.ensure_admin_default()
    st.markdown(
        '<div class="login-card">'
        '<div class="user-avatar login-avatar">NF</div>'
        '<div class="login-title">SIKAD PRIBADI</div>'
        '<div class="login-sub">Masuk untuk melanjutkan</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    col = st.columns([1, 1, 1])[1]

    _pesan = st.session_state.pop("_pesan", None)
    if _pesan:
        col.success(_pesan)

    mode = st.session_state.get("_hal", "masuk")

    if not db.login_exists():
        # Pertama kali: buat akun (form ditampilkan di atas form login)
        col.info("Buat akun dulu (pertama kali).")
        with col.form("frm_buat_akun"):
            u = st.text_input("Nama Lengkap")
            nim = st.text_input("NIM")
            p1 = st.text_input("Password (opsional, kosongkan = pakai NIM)", type="password")
            p2 = st.text_input("Ulangi Password (jika diisi)", type="password")
            pert = st.text_input("Pertanyaan keamanan (untuk lupa password)")
            jwb = st.text_input("Jawaban", type="password")
            buat = st.form_submit_button("Buat Akun", type="primary", width="stretch")
        if buat:
            if not u.strip() or not nim.strip():
                col.error("Nama lengkap dan NIM wajib diisi.")
            elif (p1 or p2) and p1 != p2:
                col.error("Password tidak sama.")
            elif p1 and len(p1) < 4:
                col.error("Password minimal 4 karakter.")
            elif not pert.strip() or not jwb:
                col.error("Pertanyaan keamanan dan jawaban wajib diisi.")
            else:
                hasil = db.create_login(u.strip(), nim.strip(), p1, pert, jwb)
                if hasil == "ok":
                    st.session_state["_pesan"] = f"Akun '{u.strip()}' dibuat. Silakan masuk."
                    st.rerun()
                else:
                    col.error(hasil)

    elif mode == "daftar":
        # Daftar akun baru (diakses lewat tombol di bawah form login)
        col.caption("Nama dan NIM harus berbeda dari akun yang sudah ada.")
        with col.form("frm_buat_akun"):
            u = st.text_input("Nama Lengkap")
            nim = st.text_input("NIM")
            p1 = st.text_input("Password (opsional, kosongkan = pakai NIM)", type="password")
            p2 = st.text_input("Ulangi Password (jika diisi)", type="password")
            pert = st.text_input("Pertanyaan keamanan (untuk lupa password)")
            jwb = st.text_input("Jawaban", type="password")
            buat = st.form_submit_button("Daftar", type="primary", width="stretch")
        if buat:
            if not u.strip() or not nim.strip():
                col.error("Nama lengkap dan NIM wajib diisi.")
            elif (p1 or p2) and p1 != p2:
                col.error("Password tidak sama.")
            elif p1 and len(p1) < 4:
                col.error("Password minimal 4 karakter.")
            elif not pert.strip() or not jwb:
                col.error("Pertanyaan keamanan dan jawaban wajib diisi.")
            else:
                hasil = db.create_login(u.strip(), nim.strip(), p1, pert, jwb)
                if hasil == "ok":
                    st.session_state["_pesan"] = f"Akun '{u.strip()}' berhasil didaftarkan. Silakan masuk."
                    st.session_state["_hal"] = "masuk"
                    st.rerun()
                else:
                    col.error(hasil)
        if col.button("← Kembali ke login", width="stretch", type="tertiary"):
            st.session_state["_hal"] = "masuk"
            st.rerun()
        return

    elif mode == "lupa":
        # Lupa password (dengan pertanyaan keamanan)
        col.caption("Masukkan nama lengkap atau NIM akunmu untuk melihat pertanyaan keamanan.")
        with col.form("frm_lupa"):
            ident = st.text_input("Nama lengkap / NIM")
            cari = st.form_submit_button("Lanjut", type="primary", width="stretch")
        if cari:
            st.session_state["_q_ident"] = ident.strip()
            st.session_state["_q"] = db.get_pertanyaan(ident.strip()) or ""
            st.session_state["_q_done"] = True
            st.rerun()
        q = st.session_state.get("_q", "")
        if st.session_state.get("_q_done") and not q:
            col.info("Akun tidak ditemukan atau belum mengatur pertanyaan keamanan — hubungi admin.")
        if q:
            _q_ident = st.session_state.get("_q_ident", "")
            col.markdown(
                f'<div class="absen-rule">Pertanyaan keamanan: <b>{html.escape(q)}</b></div>',
                unsafe_allow_html=True,
            )
            with col.form("frm_lupa2"):
                jwb = st.text_input("Jawaban", type="password")
                n1 = st.text_input("Password Baru", type="password")
                n2 = st.text_input("Ulangi Password Baru", type="password")
                reset = st.form_submit_button("Reset", type="primary", width="stretch")
            if reset:
                if not jwb or not n1:
                    col.error("Jawaban dan password baru wajib diisi.")
                elif n1 != n2:
                    col.error("Password baru tidak sama.")
                elif len(n1) < 4:
                    col.error("Password minimal 4 karakter.")
                else:
                    hasil = db.reset_password(_q_ident, jwb, n1)
                    if hasil == "ok":
                        st.session_state["_pesan"] = f"Password akun '{_q_ident}' berhasil direset. Silakan masuk dengan password baru."
                        st.session_state["_hal"] = "masuk"
                        st.session_state.pop("_q", None)
                        st.session_state.pop("_q_ident", None)
                        st.session_state.pop("_q_done", None)
                        st.rerun()
                    else:
                        col.error(hasil)
        if col.button("← Kembali ke login", width="stretch", type="tertiary"):
            st.session_state["_hal"] = "masuk"
            st.session_state.pop("_q", None)
            st.session_state.pop("_q_ident", None)
            st.session_state.pop("_q_done", None)
            st.rerun()
        return

    # Form login (admin dikenali dari username 'admin', tidak ditampilkan)
    with col.form("frm_login"):
        u = st.text_input("Nama Lengkap / NIM")
        p = st.text_input("Password", type="password")
        st.caption("Login pakai nama lengkap — password pakai NIM.")
        masuk = st.form_submit_button("Masuk", type="primary", width="stretch")
    if masuk:
        uname = u.strip()
        akun = db.check_admin(uname, p) if uname.lower() == "admin" else db.check_login(uname, p)
        if akun:
            st.session_state["logged_in"] = True
            st.session_state["username"] = akun["username"]
            st.session_state["akun"] = akun
            st.rerun()
        else:
            col.error("Nama atau password salah.")

    if db.login_exists() and col.button("Daftar Akun Baru", width="stretch"):
        st.session_state["_hal"] = "daftar"
        st.rerun()
    if db.login_exists() and col.button("Lupa Password?", width="stretch", type="tertiary"):
        st.session_state["_hal"] = "lupa"
        st.rerun()


# ---------- Utama ----------

# Pengecekan integritas: app.py butuh fungsi-fungsi tertentu di db.py.
# Kalau server menjalankan db.py yang kuno/tidak lengkap (build basi di Cloud),
# tampilkan pesan jelas daripada AttributeError misterius.
_DB_FUNCS = [
    "absen_sesi_aktif", "akun_list", "add_absensi", "add_jadwal",
    "add_matakuliah", "add_tugas", "add_tugas_batch", "buka_absen",
    "check_login", "delete_akun", "delete_jadwal", "delete_matakuliah",
    "delete_tugas", "get_pertanyaan", "is_admin", "jadwal_list",
    "matakuliah_list", "notif_belum_dibaca", "reset_password",
    "tambah_notifikasi", "tandai_notifikasi_dibaca", "tugas_list",
]
_MISSING_DB = [n for n in _DB_FUNCS if not hasattr(db, n)]
if _MISSING_DB:
    st.error(
        "⚠️ **Server menjalankan db.py versi lama** — fungsi yang hilang: "
        + ", ".join(_MISSING_DB)
        + ". Buka share.streamlit.io → Manage app → Rebuild (atau hapus & deploy "
        "ulang dari repo) agar versi file lengkap ikut terpasang."
    )
    st.stop()

# Sinkronisasi cloud dilakukan SEKALI per proses aplikasi, bukan per sesi.
# Di Streamlit Cloud setiap reload membuka sesi baru; kalau pull() jalan tiap
# sesi, halaman bisa macet lama menunggu GitHub. Pakai penanda proses + timeout
# pendek agar halaman tidak pernah menggantung.
if not _SYNC_DONE.get("done"):
    try:
        sync.pull()
    except Exception:
        sync.STATUS["mode"] = "error"
        sync.STATUS["pesan"] = "Sinkronisasi cloud bermasalah - lanjut mode lokal."
    _SYNC_DONE["done"] = True

if not st.session_state.get("logged_in"):
    page_login()
    st.stop()

st.sidebar.markdown('<div class="sidebar-brand">SIKAD PRIBADI</div>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="sidebar-sub">Catatan pribadi kuliah</div>', unsafe_allow_html=True)
_akun = st.session_state.get("akun")
_nama = _akun.get("username", "") if _akun else st.session_state.get("username", "")
_is_admin = bool(_akun.get("admin")) if _akun else db.is_admin(_nama)
_inisial = "".join([w[0].upper() for w in _nama.split()[:2]]) or "U"
_role = "Admin" if _is_admin else "Mahasiswa"
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

# Data yang sedang dilihat: akun sendiri (user) atau akun pilihan (admin)
if _is_admin:
    _daftar_akun = [a["username"] for a in db.akun_list()]
    if not _daftar_akun:
        _user = ""
        st.sidebar.info("Belum ada akun user terdaftar.")
    else:
        _user = st.sidebar.selectbox("Lihat data akun", _daftar_akun, key="adm_view_user")
else:
    _user = _nama

_MENU_ADMIN = ["Dashboard", "Pengaturan", "Tugas Massal", "Data Mahasiswa"]
_MENU_USER = ["Dashboard", "Jadwal Kuliah", "Absen", "Tugas Harian", "UTS & UAS"]
_menu = _MENU_ADMIN if _is_admin else _MENU_USER
page = st.sidebar.radio("Menu", list(_menu), label_visibility="collapsed")

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
elif page == "Pengaturan":
    page_kelola()
elif page == "Tugas Massal":
    page_tugas_massal()
elif page == "Data Mahasiswa":
    page_data_mahasiswa()

st.sidebar.markdown(
    '<div class="sidebar-foot">Aplikasi pribadi — data tersimpan otomatis.</div>',
    unsafe_allow_html=True,
)

