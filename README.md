# Catatan Semester 5

Aplikasi catatan pribadi kuliah: absen mandiri, tugas harian, UTS/UAS, dan rekap hadir/alpa.
Berbasis Streamlit, data disimpan di file lokal dan otomatis tersinkron ke **GitHub Gist**
supaya bisa diakses dari mana saja via link permanen (Streamlit Community Cloud).

## Fitur

- **Jadwal Kuliah** - kelola matakuliah semester 5 dan jadwalnya
- **Absen** - input kehadiran sendiri setiap masuk kelas (Hadir/Alpa/Izin/Sakit), rekap otomatis
- **Tugas Harian** - catat tugas yang kamu buat: judul, deadline, status
- **UTS & UAS** - jadwal, status, dan nilai ujian
- **Dashboard** - ringkasan kehadiran, persentase, dan tugas selesai

## Cara menjalankan (di PC)

```bash
pip install -r requirements.txt
streamlit run app.py
```

atau klik dua kali `run.bat`.

Tanpa konfigurasi cloud, aplikasi berjalan dalam **mode lokal** (data di `data/catatan.json`).

## Setup sinkronisasi cloud (supaya bisa diakses dari HP via link)

### 1. Buat Personal Access Token (PAT) GitHub

1. Buka https://github.com/settings/tokens lalu klik **Generate new token (classic)**
2. Nama token: bebas (misal `catatan-s5`)
3. Centang scope: **gist** saja
4. Klik **Generate token**, lalu **salin** token-nya (mulai `ghp_...`)

### 2. Buat Gist (tempat penyimpanan data)

Jalankan perintah ini di PowerShell (ganti `TOKEN_KAMU` dengan token tadi):

```powershell
$token = "TOKEN_KAMU"
$body = '{"description":"catatan semester 5","public":false,"files":{"catatan.json":{"content":"{}"}}}'
(Invoke-RestMethod -Uri "https://api.github.com/gists" -Method Post -Headers @{Authorization="Bearer $token"} -ContentType "application/json" -Body $body).id
```

Hasilnya berupa ID gist (32 karakter) — salin.

### 3. Aktifkan sinkronisasi di aplikasi

1. Salin `.streamlit/secrets.toml.example` menjadi `.streamlit/secrets.toml`
2. Isi:

```toml
[github]
pat = "ghp_..."
gist_id = "ID_GIST_KAMU"
```

3. Jalankan ulang aplikasi — indikator di sidebar berubah menjadi hijau "Tersinkron dengan cloud".

### 4. Deploy ke Streamlit Community Cloud (link permanen)

1. Buat repo baru di https://github.com/new (nama bebas, misal `catatan-semester5`, **Public**)
2. Di folder ini jalankan:

```bash
git init
git add .
git commit -m "catatan semester 5"
git branch -M main
git remote add origin https://github.com/USERNAME/REPO.git
git push -u origin main
```

   (ganti USERNAME/REPO; browser akan minta login GitHub)

3. Buka https://share.streamlit.io → **Create app** → pilih repo tadi → **Deploy**
4. Setelah jadi, buka menu **Settings** aplikasi → isi **Secrets** dengan isi `secrets.toml` di atas → **Save**, lalu **Rerun** aplikasi.

Link aplikasi (misal `https://nama-kamu-catatan-semester5.streamlit.app`) bisa dibuka kapan saja dari HP.

## Struktur file

| File | Keterangan |
|------|-----------|
| `app.py` | Aplikasi utama (UI Streamlit) |
| `db.py` | Penyimpanan data (file JSON lokal) |
| `sync.py` | Sinkronisasi ke GitHub Gist |
| `requirements.txt` | Dependensi |
| `run.bat` | Script menjalankan di Windows |
