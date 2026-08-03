import base64
import html
from datetime import date

import pandas as pd
import streamlit as st

import db
import sync

st.set_page_config(page_title="Catatan Semester 5", layout="wide", initial_sidebar_state="expanded")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], [data-testid="stAppViewContainer"] {
    font-family: 'Plus Jakarta Sans', 'Segoe UI', sans-serif;
}

#MainMenu, footer, [data-testid="stMainMenu"], [data-testid="stToolbarActionButton"] { visibility: hidden; }
[data-testid="stHeader"] { background: transparent; }

.stApp { background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%); }

[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #e2e8f0;
}
[data-testid="stSidebar"] .block-container { padding-top: 1.2rem; }
[data-testid="stSidebar"] [role="radiogroup"] label {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 10px 14px;
    margin-bottom: 6px;
    transition: all .15s ease;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {
    background: #eef2ff;
    border-color: #c7d2fe;
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background: linear-gradient(120deg, #2563eb, #0ea5e9);
    border-color: transparent;
    box-shadow: 0 6px 16px rgba(37, 99, 235, .28);
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {
    color: #ffffff;
    font-weight: 700;
}

.sidebar-brand {
    color: #1e3a8a;
    font-size: 1.2rem;
    font-weight: 800;
    letter-spacing: .5px;
    padding: 4px 6px 2px 6px;
}
.sidebar-sub { color: #64748b; font-size: .8rem; padding: 0 6px 10px 6px; }

.sync-box {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 10px 12px;
    color: #334155;
    font-size: .78rem;
    margin: 10px 0;
}

.siakad-banner {
    position: relative;
    overflow: hidden;
    background: linear-gradient(120deg, #1e3a8a 0%, #2563eb 55%, #0ea5e9 100%);
    border-radius: 14px;
    padding: 18px 24px;
    margin-bottom: 18px;
    box-shadow: 0 8px 24px rgba(37,99,235,.20);
}
.siakad-banner::after {
    content: "";
    position: absolute;
    top: -60px; right: -40px;
    width: 230px; height: 230px;
    background: radial-gradient(circle, rgba(255,255,255,.20), transparent 70%);
    border-radius: 50%;
}
.banner-title { color: #ffffff; font-size: 1.35rem; font-weight: 800; }
.banner-sub { color: rgba(255,255,255,.85); font-size: .9rem; margin-top: 4px; }

.stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 14px;
    margin-bottom: 22px;
}
.stat-card {
    position: relative;
    overflow: hidden;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 2px 10px rgba(15,23,42,.05);
    transition: transform .15s ease, box-shadow .15s ease;
}
.stat-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, var(--accent, #2563eb), transparent 85%);
}
.stat-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 10px 24px rgba(15,23,42,.10);
}
.stat-label {
    color: #64748b;
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
    background: var(--accent, #2563eb);
    vertical-align: 0;
}
.stat-value { font-size: 2rem; font-weight: 800; margin-top: 4px; }

.panel {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 2px 10px rgba(15, 23, 42, .05);
    margin-bottom: 16px;
}
.panel-title {
    font-size: 1.02rem;
    font-weight: 800;
    color: #0f172a;
    margin: 8px 0 10px 0;
}
.panel-title::before {
    content: "";
    display: inline-block;
    width: 4px;
    height: 15px;
    border-radius: 2px;
    margin-right: 8px;
    background: linear-gradient(180deg, #2563eb, #0ea5e9);
    vertical-align: -2px;
}

[data-testid="stButton"] button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] {
    background: linear-gradient(120deg, #2563eb, #0ea5e9);
    border: none;
    box-shadow: 0 8px 20px rgba(37, 99, 235, .35);
    transition: transform .15s ease, box-shadow .15s ease;
}
[data-testid="stButton"] button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 28px rgba(37, 99, 235, .45);
}

[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input,
[data-testid="stTimeInput"] input, [data-testid="stTextArea"] textarea {
    border-radius: 10px !important;
    border-color: #cbd5e1 !important;
}
[data-testid="stSelectbox"] div[data-baseweb="select"] > div { border-radius: 10px !important; }
[data-testid="stTextInput"] input:focus, [data-testid="stNumberInput"] input:focus,
[data-testid="stTimeInput"] input:focus, [data-testid="stTextArea"] textarea:focus,
[data-testid="stDateInput"] input:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, .15) !important;
}
[data-testid="stSelectbox"] div[data-baseweb="select"] > div:focus-within {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, .15) !important;
}
[data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button {
    border-radius: 10px !important;
    font-weight: 700 !important;
}
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; }
[data-testid="stDataFrame"] [role="columnheader"] {
    background: #f1f5f9;
    color: #0f172a;
    font-weight: 700;
}
[data-testid="stExpander"] details {
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    background: #ffffff;
}
[data-testid="stExpander"] summary { font-weight: 700; color: #0f172a; }
.sidebar-foot {
    color: #94a3b8;
    font-size: .72rem;
    text-align: center;
    margin-top: 14px;
    padding-top: 10px;
    border-top: 1px solid #e2e8f0;
}
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)

PAGE_TITLES = {
    "Dashboard": ("Dashboard", "Rekap kehadiran dan tugas semester 5."),
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


def select_table(df, key, height=380):
    event = st.dataframe(
        df,
        key=key,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        height=height,
        width="stretch",
    )
    rows = event.selection.rows
    if rows:
        pos = int(rows[0])
        return df.iloc[pos].to_dict(), pos
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
    page_header(*PAGE_TITLES["Dashboard"])
    flash()
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
            ("Tugas Selesai", f"{r['jml_tugas_selesai']}/{r['jml_tugas']}", "#06b6d4"),
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
            st.dataframe(
                df[["nama", "total_pertemuan", "hadir", "alpa", "kehadiran"]].rename(
                    columns={
                        "nama": "Matakuliah",
                        "total_pertemuan": "Pertemuan",
                        "hadir": "Hadir",
                        "alpa": "Alpa",
                    }
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("Belum ada matakuliah. Tambahkan di menu Jadwal Kuliah.")
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="panel"><div class="panel-title">Kehadiran per Bulan</div>', unsafe_allow_html=True)
        bulan = db.hadir_per_bulan()
        if bulan:
            dfb = pd.DataFrame(bulan)
            st.bar_chart(dfb.set_index("bulan"), color=["#10b981", "#ef4444", "#f59e0b", "#94a3b8"])
        else:
            st.info("Belum ada data absen.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="panel-title">Tugas yang Sudah Kamu Buat</div>', unsafe_allow_html=True)
    done = db.tugas_list(status="Selesai")
    if done:
        st.dataframe(
            pd.DataFrame(done)[["matakuliah", "tipe", "judul", "deadline", "tanggal_selesai", "nilai"]].rename(
                columns={
                    "matakuliah": "Matakuliah",
                    "tipe": "Tipe",
                    "judul": "Judul Tugas",
                    "deadline": "Deadline",
                    "tanggal_selesai": "Selesai Tanggal",
                    "nilai": "Nilai",
                }
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("Belum ada tugas yang selesai. Semangat!")
    st.markdown("</div>", unsafe_allow_html=True)


# ---------- Jadwal Kuliah ----------

def page_jadwal():
    page_header(*PAGE_TITLES["Jadwal Kuliah"])
    flash()

    with st.expander("Tambah Matakuliah", expanded=False):
        with st.form("frm_mk"):
            c1, c2 = st.columns(2)
            kode = c1.text_input("Kode (opsional)")
            nama = c2.text_input("Nama Matakuliah")
            c3, c4 = st.columns(2)
            dosen = c3.text_input("Dosen")
            sks = c4.number_input("SKS", min_value=1, max_value=6, value=3)
            submitted = st.form_submit_button("Simpan", type="primary", width="stretch")
        if submitted:
            if not nama.strip():
                st.error("Nama matakuliah wajib diisi.")
            else:
                mid = db.add_matakuliah(kode.strip(), nama.strip(), dosen.strip(), int(sks))
                if mid is None:
                    st.error(f"Matakuliah dengan kode '{kode}' sudah ada.")
                else:
                    st.session_state["flash"] = f"Matakuliah '{nama}' ditambahkan."
                    sync.push()
                    st.rerun()

    mk_list = db.matakuliah_list()
    if not mk_list:
        st.info("Tambahkan matakuliah dulu sebelum mengatur jadwal.")
        return

    with st.expander("Tambah Jadwal", expanded=False):
        with st.form("frm_jdwl"):
            mk = st.selectbox(
                "Matakuliah",
                [f"{m['nama']} ({m['kode']})" if m["kode"] else m["nama"] for m in mk_list],
            )
            c1, c2 = st.columns(2)
            hari = c1.selectbox("Hari", db.HARI)
            ruang = c2.text_input("Ruang")
            t1, t2 = st.columns(2)
            mulai = t1.time_input("Jam Mulai", value=__import__("datetime").time(8, 0))
            selesai = t2.time_input("Jam Selesai", value=__import__("datetime").time(9, 40))
            submitted = st.form_submit_button("Simpan", type="primary", width="stretch")
        if submitted:
            if selesai <= mulai:
                st.error("Jam selesai harus setelah jam mulai.")
            else:
                mid = mk_list[mk.index(mk)]["id"]
                db.add_jadwal(
                    mid, hari,
                    f"{mulai.hour:02d}:{mulai.minute:02d}",
                    f"{selesai.hour:02d}:{selesai.minute:02d}",
                    ruang.strip(),
                )
                st.session_state["flash"] = "Jadwal ditambahkan."
                sync.push()
                st.rerun()

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
    dfm = pd.DataFrame(mk_list)[["nama", "kode", "dosen", "sks"]].rename(
        columns={"nama": "Matakuliah", "kode": "Kode", "dosen": "Dosen", "sks": "SKS"}
    )
    selm, posm = select_table(dfm, "tbl_mk", height=260)
    if selm:
        mid_sel = mk_list[posm]["id"]
        st.caption("Menghapus matakuliah ikut menghapus jadwal, absen, dan tugasnya.")
        if st.button("Hapus Matakuliah", width="stretch"):
            hapus_dialog(selm["Matakuliah"], lambda: db.delete_matakuliah(mid_sel))
    st.markdown("</div>", unsafe_allow_html=True)


# ---------- Absen ----------

def page_absen():
    page_header(*PAGE_TITLES["Absen"])
    flash()

    mk_list = db.matakuliah_list()
    if not mk_list:
        st.info("Tambahkan matakuliah dulu di menu Jadwal Kuliah.")
        return

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

    with st.expander("Input Kehadiran", expanded=True):
        with st.form("frm_absen"):
            c1, c2 = st.columns(2)
            tanggal = c1.date_input("Tanggal", value=date.today())
            status = c2.selectbox("Status", db.STATUS_ABSEN)
            catatan = st.text_input("Catatan (opsional)")
            submitted = st.form_submit_button("Simpan", type="primary", width="stretch")
        if submitted:
            ok = db.add_absensi(
                m["id"], tanggal.isoformat(), status, catatan.strip()
            )
            if not ok:
                st.error(f"Absen untuk {tanggal.isoformat()} sudah tercatat.")
            else:
                st.session_state["flash"] = f"Absen {status} untuk {m['nama']} tanggal {tanggal.isoformat()} tersimpan."
                sync.push()
                st.rerun()

    rows = db.absensi_list(id_matakuliah=m["id"])
    st.markdown(f'<div class="panel"><div class="panel-title">Riwayat Absen ({len(rows)})</div>', unsafe_allow_html=True)
    if rows:
        df = pd.DataFrame(rows)[["tanggal", "status", "catatan"]].rename(
            columns={"tanggal": "Tanggal", "status": "Status", "catatan": "Catatan"}
        )

        def warna_status(v):
            if v == "Hadir":
                return "background-color: #dcfce7; color: #15803d; font-weight: 600;"
            if v == "Alpa":
                return "background-color: #fee2e2; color: #b91c1c; font-weight: 600;"
            return "background-color: #fef3c7; color: #b45309; font-weight: 600;"

        sel, pos = select_table(df.style.map(warna_status, subset=["Status"]), "tbl_absen", height=300)
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
        st.dataframe(
            dfr[["nama", "total_pertemuan", "hadir", "alpa", "izin_sakit", "kehadiran"]].rename(
                columns={
                    "nama": "Matakuliah", "total_pertemuan": "Pertemuan",
                    "hadir": "Hadir", "alpa": "Alpa",
                    "izin_sakit": "Izin/Sakit",
                }
            ),
            hide_index=True,
            width="stretch",
        )
    st.markdown("</div>", unsafe_allow_html=True)


# ---------- Tugas (Harian & UTS/UAS) ----------

@st.dialog("Ubah Tugas")
def edit_tugas(t, tid):
    with st.form("edit_tugas"):
        judul = st.text_input("Judul", value=t["judul"])
        deskripsi = st.text_area("Deskripsi", value=t["deskripsi"])
        c1, c2 = st.columns(2)
        deadline = c1.date_input(
            "Deadline", value=date.fromisoformat(t["deadline"]) if t["deadline"] else date.today()
        )
        status = c2.selectbox("Status", db.STATUS_TUGAS, index=db.STATUS_TUGAS.index(t["status"]))
        nilai = st.number_input("Nilai (jika sudah dinilai)", min_value=0.0, max_value=100.0,
                                value=float(t["nilai"]) if t["nilai"] is not None else 0.0)
        submitted = st.form_submit_button("Simpan Perubahan", type="primary", width="stretch")
    if submitted:
        if not judul.strip():
            st.error("Judul wajib diisi.")
        else:
            db.update_tugas(
                tid, judul=judul.strip(), deskripsi=deskripsi.strip(),
                deadline=deadline.isoformat(), status=status,
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

    with st.expander("Tambah Tugas", expanded=True):
        with st.form("frm_tgs"):
            mk = st.selectbox(
                "Matakuliah",
                [f"{m['nama']} ({m['kode']})" if m["kode"] else m["nama"] for m in mk_list],
            )
            c1, c2 = st.columns(2)
            if is_ujian:
                tipe = c1.selectbox("Tipe", ["UTS", "UAS"])
            else:
                tipe = "Harian"
            deadline = c2.date_input("Deadline", value=date.today())
            judul = st.text_input("Judul")
            deskripsi = st.text_area("Deskripsi (opsional)")
            c3, c4 = st.columns(2)
            status = c3.selectbox("Status", db.STATUS_TUGAS)
            nilai = c4.number_input("Nilai (jika sudah dinilai)", min_value=0.0, max_value=100.0, value=0.0)
            submitted = st.form_submit_button("Simpan", type="primary", width="stretch")
        if submitted:
            if not judul.strip():
                st.error("Judul wajib diisi.")
            else:
                mid = mk_list[mk.index(mk)]["id"]
                db.add_tugas(
                    mid, tipe, judul.strip(), deskripsi.strip(),
                    deadline.isoformat(), status,
                    nilai if nilai else None,
                )
                st.session_state["flash"] = f"Tugas {tipe} '{judul}' ditambahkan."
                sync.push()
                st.rerun()

    st.markdown("Filter status:", unsafe_allow_html=True)
    f_status = st.segmented_control(
        "f_status", ["Semua", "Belum", "Selesai"], default="Semua",
        key="filt_tugas", label_visibility="collapsed",
    )
    status_filter = None if f_status == "Semua" else f_status
    rows = db.tugas_list(tipe=tipe_filter, status=status_filter)
    selesai = sum(1 for t in db.tugas_list(tipe=tipe_filter) if t["status"] == "Selesai")

    st.markdown(f'<div class="panel"><div class="panel-title">Daftar {tipe_nama} ({selesai} selesai / {len(rows)} tampil)</div>', unsafe_allow_html=True)
    if rows:
        df = pd.DataFrame(rows)[["matakuliah", "judul", "deadline", "status", "nilai"]].rename(
            columns={
                "matakuliah": "Matakuliah", "judul": "Judul",
                "deadline": "Deadline", "status": "Status", "nilai": "Nilai",
            }
        )
        df["Nilai"] = df["Nilai"].fillna("-").apply(lambda v: f"{v:g}" if v != "-" else "-")

        def warna_status(v):
            return "background-color: #dcfce7; color: #15803d; font-weight: 600;" if v == "Selesai" else ""

        sel, pos = select_table(df.style.map(warna_status, subset=["Status"]), "tbl_tgs", height=320)
        if sel:
            tid = rows[pos]["id"]
            t = rows[pos]
            c1, c2, c3 = st.columns(3)
            if c1.button("Tandai Selesai", type="primary", width="stretch", disabled=t["status"] == "Selesai"):
                db.update_tugas(tid, status="Selesai", tanggal_selesai=date.today().isoformat())
                st.session_state["flash"] = f"'{t['judul']}' ditandai selesai."
                sync.push()
                st.rerun()
            if c2.button("Ubah", width="stretch"):
                edit_tugas(t, tid)
            if c3.button("Hapus", width="stretch"):
                hapus_dialog(t["judul"], lambda: db.delete_tugas(tid))
    else:
        st.info("Belum ada tugas.")
    st.markdown("</div>", unsafe_allow_html=True)


# ---------- Utama ----------

if "synced_once" not in st.session_state:
    sync.pull()
    st.session_state["synced_once"] = True

st.sidebar.markdown('<div class="sidebar-brand">Catatan Semester 5</div>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="sidebar-sub">Catatan pribadi kuliah</div>', unsafe_allow_html=True)

page = st.sidebar.radio("Menu", list(PAGE_TITLES), label_visibility="collapsed")

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
