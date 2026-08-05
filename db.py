import hashlib
import json
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "data" / "catatan.json"
LOGIN_FILE = BASE / "data" / "login.json"
ADMIN_FILE = BASE / "data" / "admin.json"

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
STATUS_ABSEN = ["Hadir", "Alpa", "Izin", "Sakit"]
TIPE_TUGAS = ["Harian", "UTS", "UAS"]
STATUS_TUGAS = ["Belum", "Diserahkan"]

_HURUF_HARI = {
    "Senin": 1, "Selasa": 2, "Rabu": 3, "Kamis": 4,
    "Jumat": 5, "Sabtu": 6, "Minggu": 7,
}


def _empty():
    return {"matakuliah": [], "jadwal": [], "absensi": [], "tugas": []}


def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _empty()


def save_data(data):
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _next_id(items):
    return max([x["id"] for x in items], default=0) + 1


# ---------- Login ----------

def _hash_pw(pw):
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def _login_all():
    """Semua akun user (list). Format lama (dict tunggal) otomatis dimigrasi ke list."""
    if not LOGIN_FILE.exists():
        return []
    try:
        d = json.loads(LOGIN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(d, dict):
        akun = [
            {
                "username": d.get("username", ""),
                "nim": d.get("nim", ""),
                "pass_hash": d.get("pass_hash", ""),
            }
        ]
        _save_login_all(akun)
        return akun
    if isinstance(d, list):
        for a in d:
            a.pop("admin", None)
        return d
    return []


def _save_login_all(akun):
    LOGIN_FILE.parent.mkdir(exist_ok=True)
    LOGIN_FILE.write_text(
        json.dumps(akun, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _admin_all():
    """Kredensial admin (dict) atau None jika belum dibuat."""
    if not ADMIN_FILE.exists():
        return None
    try:
        d = json.loads(ADMIN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(d, dict) and d.get("pass_hash"):
        return d
    return None


def _save_admin(d):
    ADMIN_FILE.parent.mkdir(exist_ok=True)
    ADMIN_FILE.write_text(
        json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def admin_exists():
    return _admin_all() is not None


def create_admin_login(password):
    """Buat kredensial admin (pertama kali saja). Kembalikan 'ok' atau pesan kesalahan."""
    if admin_exists():
        return "Admin sudah terdaftar"
    _save_admin({"username": "admin", "pass_hash": _hash_pw(password)})
    return "ok"


def check_admin(username, password):
    """Kembalikan dict akun admin jika cocok, selain itu None."""
    a = _admin_all()
    if not a:
        return None
    if (
        a.get("username", "").strip().lower() == username.strip().lower()
        and a.get("pass_hash") == _hash_pw(password)
    ):
        return {"username": a["username"], "nim": "", "admin": True}
    return None


def login_exists():
    return LOGIN_FILE.exists()


def create_login(username, nim, password):
    """Daftar akun user baru. Kembalikan 'ok' atau pesan kesalahan (Nama/NIM sudah terpakai)."""
    akun = _login_all()
    uname = username.strip()
    unim = nim.strip()
    for a in akun:
        if a.get("username", "").strip().lower() == uname.lower():
            return "Nama sudah terdaftar"
        if a.get("nim", "").strip() == unim:
            return "NIM sudah terdaftar"
    akun.append(
        {
            "username": uname,
            "nim": unim,
            "pass_hash": _hash_pw(password),
        }
    )
    _save_login_all(akun)
    return "ok"


def check_login(username, password):
    """Kembalikan dict akun user jika cocok, selain itu None."""
    for a in _login_all():
        if (
            a.get("username", "").strip().lower() == username.strip().lower()
            and a.get("pass_hash") == _hash_pw(password)
        ):
            return a
    return None


def is_admin(username):
    a = _admin_all()
    return bool(
        a and a.get("username", "").strip().lower() == username.strip().lower()
    )


# ---------- Matakuliah ----------

def get_matakuliah(mid):
    for m in load_data()["matakuliah"]:
        if m["id"] == mid:
            return m
    return None


def add_matakuliah(kode, nama, dosen, sks, jam_masuk="", jam_selesai=""):
    data = load_data()
    for m in data["matakuliah"]:
        if kode and m.get("kode") and m["kode"].lower() == kode.lower():
            return None
    m = {
        "id": _next_id(data["matakuliah"]),
        "kode": kode,
        "nama": nama,
        "dosen": dosen,
        "sks": int(sks),
        "jam_masuk": jam_masuk,
        "jam_selesai": jam_selesai,
    }
    data["matakuliah"].append(m)
    save_data(data)
    return m["id"]


def update_matakuliah(mid, kode, nama, dosen, sks):
    data = load_data()
    for m in data["matakuliah"]:
        if m["id"] == mid:
            m.update(kode=kode, nama=nama, dosen=dosen, sks=int(sks))
    save_data(data)


def delete_matakuliah(mid):
    data = load_data()
    data["matakuliah"] = [m for m in data["matakuliah"] if m["id"] != mid]
    data["jadwal"] = [j for j in data["jadwal"] if j["id_matakuliah"] != mid]
    data["absensi"] = [a for a in data["absensi"] if a["id_matakuliah"] != mid]
    data["tugas"] = [t for t in data["tugas"] if t["id_matakuliah"] != mid]
    save_data(data)


def matakuliah_list():
    data = load_data()
    rows = []
    for m in data["matakuliah"]:
        absen = [a for a in data["absensi"] if a["id_matakuliah"] == m["id"]]
        hadir = sum(1 for a in absen if a["status"] == "Hadir")
        rows.append(
            {
                "id": m["id"],
                "kode": m["kode"],
                "nama": m["nama"],
                "dosen": m["dosen"],
                "sks": m["sks"],
                "jam_masuk": m.get("jam_masuk", ""),
                "jam_selesai": m.get("jam_selesai", ""),
                "total_pertemuan": len(absen),
                "hadir": hadir,
                "alpa": sum(1 for a in absen if a["status"] == "Alpa"),
                "izin_sakit": len(absen) - hadir
                - sum(1 for a in absen if a["status"] == "Alpa"),
            }
        )
    rows.sort(key=lambda r: r["nama"])
    return rows


# ---------- Jadwal ----------

def add_jadwal(id_matakuliah, hari, jam_mulai, jam_selesai, ruang):
    data = load_data()
    j = {
        "id": _next_id(data["jadwal"]),
        "id_matakuliah": id_matakuliah,
        "hari": hari,
        "jam_mulai": jam_mulai,
        "jam_selesai": jam_selesai,
        "ruang": ruang,
    }
    data["jadwal"].append(j)
    save_data(data)


def delete_jadwal(jid):
    data = load_data()
    data["jadwal"] = [j for j in data["jadwal"] if j["id"] != jid]
    save_data(data)


def jadwal_list(hari=None):
    data = load_data()
    mhs = {m["id"]: m for m in data["matakuliah"]}
    rows = []
    for j in data["jadwal"]:
        m = mhs.get(j["id_matakuliah"])
        if not m:
            continue
        if hari and j["hari"] != hari:
            continue
        rows.append(
            {
                "id": j["id"],
                "id_matakuliah": j["id_matakuliah"],
                "matakuliah": m["nama"],
                "kode": m["kode"],
                "dosen": m["dosen"],
                "hari": j["hari"],
                "jam_mulai": j["jam_mulai"],
                "jam_selesai": j["jam_selesai"],
                "ruang": j["ruang"],
            }
        )
    rows.sort(
        key=lambda r: (
            _HURUF_HARI.get(r["hari"], 99),
            r["jam_mulai"] or "",
        )
    )
    return rows


# ---------- Absensi ----------

def add_absensi(id_matakuliah, tanggal, status, catatan):
    data = load_data()
    for a in data["absensi"]:
        if a["id_matakuliah"] == id_matakuliah and a["tanggal"] == tanggal:
            return False
    a = {
        "id": _next_id(data["absensi"]),
        "id_matakuliah": id_matakuliah,
        "tanggal": tanggal,
        "status": status,
        "catatan": catatan or "",
    }
    data["absensi"].append(a)
    save_data(data)
    return True


def set_absensi(id_matakuliah, tanggal, status, catatan=""):
    """Tambah absen, atau ganti status jika absen sudah ada (untuk tanggal yang sama)."""
    data = load_data()
    for a in data["absensi"]:
        if a["id_matakuliah"] == id_matakuliah and a["tanggal"] == tanggal:
            a["status"] = status
            if catatan:
                a["catatan"] = catatan
            save_data(data)
            return True
    a = {
        "id": _next_id(data["absensi"]),
        "id_matakuliah": id_matakuliah,
        "tanggal": tanggal,
        "status": status,
        "catatan": catatan or "",
    }
    data["absensi"].append(a)
    save_data(data)
    return True


def delete_absensi(aid):
    data = load_data()
    data["absensi"] = [a for a in data["absensi"] if a["id"] != aid]
    save_data(data)


def absensi_by_tanggal(tanggal):
    data = load_data()
    return [
        {
            "id": a["id"],
            "id_matakuliah": a["id_matakuliah"],
            "tanggal": a["tanggal"],
            "status": a["status"],
            "catatan": a["catatan"],
        }
        for a in data["absensi"]
        if a["tanggal"] == tanggal
    ]


def absensi_list(id_matakuliah=None):
    data = load_data()
    mhs = {m["id"]: m["nama"] for m in data["matakuliah"]}
    rows = [
        {
            "id": a["id"],
            "matakuliah": mhs.get(a["id_matakuliah"], "-"),
            "tanggal": a["tanggal"],
            "status": a["status"],
            "catatan": a["catatan"],
        }
        for a in data["absensi"]
        if id_matakuliah is None or a["id_matakuliah"] == id_matakuliah
    ]
    rows.sort(key=lambda r: r["tanggal"], reverse=True)
    return rows


# ---------- Tugas ----------

def add_tugas(id_matakuliah, tipe, judul, deskripsi, deadline, status, nilai):
    data = load_data()
    t = {
        "id": _next_id(data["tugas"]),
        "id_matakuliah": id_matakuliah,
        "tipe": tipe,
        "judul": judul,
        "deskripsi": deskripsi or "",
        "deadline": deadline or "",
        "status": status,
        "tanggal_selesai": "",
        "nilai": nilai,
    }
    data["tugas"].append(t)
    save_data(data)
    return t["id"]


def update_tugas(tid, judul=None, deskripsi=None, deadline=None,
                 status=None, tanggal_selesai=None, nilai=None):
    data = load_data()
    for t in data["tugas"]:
        if t["id"] == tid:
            if judul is not None:
                t["judul"] = judul
            if deskripsi is not None:
                t["deskripsi"] = deskripsi
            if deadline is not None:
                t["deadline"] = deadline
            if status is not None:
                t["status"] = status
                if status == "Selesai" and not t["tanggal_selesai"]:
                    t["tanggal_selesai"] = tanggal_selesai or ""
                elif status == "Belum":
                    t["tanggal_selesai"] = ""
            if nilai is not None:
                t["nilai"] = nilai
    save_data(data)


def delete_tugas(tid):
    data = load_data()
    data["tugas"] = [t for t in data["tugas"] if t["id"] != tid]
    save_data(data)


def _status_tampil(t):
    """Status tampil: Diserahkan / Terlambat (lewat deadline, belum diserahkan) / Belum."""
    if t["status"] == "Diserahkan":
        return "Diserahkan"
    if t["deadline"]:
        try:
            dl = datetime.fromisoformat(t["deadline"])
        except ValueError:
            dl = None
        if dl is not None and dl < datetime.now():
            return "Terlambat"
    return "Belum"


def tugas_list(tipe=None, status=None, id_matakuliah=None):
    data = load_data()
    mhs = {m["id"]: m["nama"] for m in data["matakuliah"]}
    rows = []
    for t in data["tugas"]:
        if tipe and t["tipe"] != tipe:
            continue
        if status and t["status"] != status:
            continue
        if id_matakuliah and t["id_matakuliah"] != id_matakuliah:
            continue
        rows.append(
            {
                "id": t["id"],
                "matakuliah": mhs.get(t["id_matakuliah"], "-"),
                "tipe": t["tipe"],
                "judul": t["judul"],
                "deskripsi": t["deskripsi"],
                "deadline": t["deadline"],
                "status": t["status"],
                "status_tampil": _status_tampil(t),
                "tanggal_selesai": t["tanggal_selesai"],
                "nilai": t["nilai"],
            }
        )
    rows.sort(key=lambda r: r["deadline"] or "9999")
    return rows


# ---------- Rekap ----------

def rekap_keseluruhan():
    data = load_data()
    absen = data["absensi"]
    tugas = data["tugas"]
    return {
        "jml_matakuliah": len(data["matakuliah"]),
        "jml_pertemuan": len(absen),
        "jml_hadir": sum(1 for a in absen if a["status"] == "Hadir"),
        "jml_alpa": sum(1 for a in absen if a["status"] == "Alpa"),
        "jml_keterangan": sum(
            1 for a in absen if a["status"] in ("Izin", "Sakit")
        ),
        "jml_tugas": len(tugas),
        "jml_tugas_selesai": sum(1 for t in tugas if t["status"] == "Diserahkan"),
        "jml_harian": sum(1 for t in tugas if t["tipe"] == "Harian"),
        "jml_uts": sum(1 for t in tugas if t["tipe"] == "UTS"),
        "jml_uas": sum(1 for t in tugas if t["tipe"] == "UAS"),
        "jml_uts_selesai": sum(1 for t in tugas if t["tipe"] == "UTS" and t["status"] == "Diserahkan"),
        "jml_uas_selesai": sum(1 for t in tugas if t["tipe"] == "UAS" and t["status"] == "Diserahkan"),
    }


def hadir_per_bulan():
    data = load_data()
    bulan = {}
    for a in data["absensi"]:
        key = a["tanggal"][:7]
        b = bulan.setdefault(key, {"Hadir": 0, "Alpa": 0, "Izin": 0, "Sakit": 0})
        b[a["status"]] = b.get(a["status"], 0) + 1
    return [{"bulan": k, **v} for k, v in sorted(bulan.items(), reverse=True)]
