"""Asisten AI dashboard gedung: konteks data, tanya-jawab, dan usulan jadwal.

Satu kode untuk empat penyedia yang kompatibel dengan format OpenAI:
Google AI Studio (Gemini API, mis. Gemma 4), OpenRouter, DeepSeek, atau Ollama di laptop sendiri.
Semua fungsi menerima DataFrame dari luar, jadi bisa dipakai di notebook
maupun di dashboard Streamlit.
"""
import json
import os
import re
import time

import pandas as pd
from openai import (APIConnectionError, APITimeoutError, BadRequestError, InternalServerError,
                    OpenAI, RateLimitError)

# ---------- 1. Koneksi ke penyedia AI ----------
PENYEDIA = {
    "gemini":     {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                   "env_key": "GEMINI_API_KEY"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "env_key": "OPENROUTER_API_KEY"},
    "deepseek":   {"base_url": "https://api.deepseek.com",     "env_key": "DEEPSEEK_API_KEY"},
    "ollama":     {"base_url": "http://localhost:11434/v1",    "env_key": None},
}

BATAS_WAKTU = 40                                    # detik maksimal per panggilan AI
BATAS_WAKTU_UTAMA = 15                              # kalau ada cadangan: model utama diberi 15 detik

def buat_klien(penyedia="openrouter", api_key=None):
    """Buat koneksi. API key dibaca dari environment, bukan ditulis di kode.

    Batas waktu 40 detik per panggilan, dan percobaan ulang bawaan pustaka dimatikan
    (percobaan ulang untuk error 429 sudah diatur di _kirim), supaya tidak menggantung lama.
    """
    cfg = PENYEDIA[penyedia]
    atur = {"timeout": BATAS_WAKTU, "max_retries": 0}
    if cfg["env_key"] is None:                      # Ollama tidak butuh key
        return OpenAI(base_url=cfg["base_url"], api_key="ollama", **atur)
    key = api_key or os.getenv(cfg["env_key"])
    if not key:
        raise ValueError(f"API key belum ada. Isi {cfg['env_key']} di .streamlit/secrets.toml (atau .env)")
    return OpenAI(base_url=cfg["base_url"], api_key=key, **atur)


# ---------- 2. Ringkasan konteks dari data ----------
JAM_MULAI, JAM_SELESAI = 7, 17                      # jam kerja Senin-Jumat
URUTAN_LEVEL = {"Kritis": 0, "Waspada": 1, "Siaga": 2}

def _penyebab(r):
    alasan = []
    if pd.notna(r["rasio_daya"]) and r["rasio_daya"] >= 1.4:
        alasan.append(f"daya {r['rasio_daya']:.2f}x batas normal")
    if pd.notna(r["suhu_motor_maks_C"]) and r["suhu_motor_maks_C"] >= 75:
        alasan.append(f"suhu motor {r['suhu_motor_maks_C']:.1f} C")
    if r["persen_umur"] >= 70:
        alasan.append(f"{r['persen_umur']:.0f}% dari umur/interval servis")
    return "; ".join(alasan) or "-"

def buat_konteks(energi, kondisi, unit, hari_ini):
    """Ringkasan teks pendek tentang kondisi gedung, hanya dari data sampai hari_ini."""
    hari_ini = pd.Timestamp(hari_ini).normalize()
    akhir = hari_ini + pd.Timedelta(days=1)

    e = energi[(energi["timestamp"] >= akhir - pd.Timedelta(days=7))
               & (energi["timestamp"] < akhir)].copy()
    e["kWh"] = e["kW"] * 0.25
    per_hari = e.groupby(e["timestamp"].dt.strftime("%a %d-%m"), sort=False)["kWh"].sum().round()
    per_lantai = e.groupby("lantai")["kWh"].sum().sort_values(ascending=False)
    jam = e["timestamp"].dt.hour
    kerja = (e["timestamp"].dt.day_of_week < 5) & (jam >= JAM_MULAI) & (jam < JAM_SELESAI)
    persen_luar = e.loc[~kerja, "kWh"].sum() / e["kWh"].sum() * 100

    k = kondisi[kondisi["tanggal"] == hari_ini].merge(
        unit[["id_unit", "jenis", "lantai"]], on="id_unit")
    jumlah = k["level"].value_counts().to_dict()
    perlu = k[k["level"].isin(URUTAN_LEVEL)].copy()
    perlu["urut"] = perlu["level"].map(URUTAN_LEVEL)
    perlu = perlu.sort_values(["urut", "health_index"])
    perlu["penyebab"] = perlu.apply(_penyebab, axis=1)
    tabel = perlu[["id_unit", "jenis", "lantai", "level", "health_index", "penyebab"]].head(15)
    n_ac_tidak = int(((unit["jenis"] == "AC") & (unit["status_unit"] == "Tidak aktif")).sum())

    baris = [
        f"TANGGAL HARI INI: {hari_ini:%d-%m-%Y}",
        "",
        "ENERGI 7 HARI TERAKHIR (kWh per hari):",
        per_hari.to_string(),
        f"Total 7 hari: {e['kWh'].sum():.0f} kWh",
        f"Lantai paling boros: Lantai {per_lantai.index[0]} "
        f"({per_lantai.iloc[0]:.0f} kWh, {per_lantai.iloc[0] / per_lantai.sum() * 100:.0f}% dari gedung)",
        f"Porsi energi di luar jam kerja (Senin-Jumat 07.00-17.00): {persen_luar:.0f}%",
        "",
        f"JUMLAH UNIT PER LEVEL HARI INI: {jumlah}",
        f"AC tidak aktif (hampir tidak pernah menyala): {n_ac_tidak} unit",
        "UNIT YANG PERLU PERHATIAN (urut paling mendesak):",
        tabel.to_string(index=False) if len(tabel) else "(tidak ada)",
    ]
    return "\n".join(baris)


# ---------- 3. Tanya-jawab ----------
SYSTEM_PROMPT = """Kamu adalah asisten operator untuk gedung kantor 10 lantai (studi kasus BMS).
Aturan:
1. Jawab HANYA berdasarkan KONTEKS DATA yang diberikan. Jangan mengarang angka atau unit.
2. Selalu tulis id_unit persis seperti di konteks.
3. Untuk daftar unit atau anomali, pakai tabel markdown, urut dari yang paling mendesak.
4. Jawab dalam Bahasa Indonesia, ringkas dan jelas.
5. Kalau datanya tidak cukup untuk menjawab, katakan terus terang.
6. Keputusan tetap di tangan operator; kamu hanya memberi saran.
7. Sistem kebakaran dan keamanan hanya bisa dibaca. Tolak permintaan untuk mengubahnya."""

JEDA_ULANG = (2, 8)                                 # detik tunggu sebelum mencoba lagi
MODEL_TERAKHIR = None                               # model yang benar-benar menjawab panggilan terakhir
RIWAYAT = []                                        # percobaan panggilan terakhir: (model, hasil, detik)
LEWATI_MENIT = 5                                    # model utama yang error dilewati selama 5 menit
_lewati_sampai = {}                                 # {model: waktu (time.time()) boleh dicoba lagi}

def daftar_model(model):
    """'gemma-4-31b-it, gemini-flash-latest' -> ['gemma-4-31b-it', 'gemini-flash-latest']"""
    return [m.strip() for m in str(model).split(",") if m.strip()]


def _kirim(klien, model, temperature, pesan):
    """Panggil model. `model` boleh berisi beberapa nama dipisah koma (model utama, lalu cadangan).

    - Server penuh atau gangguan (429, 500, 503, timeout, koneksi): langsung pindah ke model berikutnya.
    - Selama masih ada cadangan, model diberi batas waktu BATAS_WAKTU_UTAMA (15 detik).
    - Model utama yang baru saja error dilewati selama LEWATI_MENIT, supaya tidak menunggu berulang.
    - Setiap percobaan dicatat di RIWAYAT: (model, hasil, detik).
    - Model terakhir yang kena 429: tunggu sebentar lalu coba lagi, maksimal 3 kali.
    """
    global MODEL_TERAKHIR
    daftar = daftar_model(model)
    galat = None
    for i, m in enumerate(daftar):
        terakhir = i == len(daftar) - 1
        if not terakhir and _lewati_sampai.get(m, 0) > time.time():
            RIWAYAT.append((m, "dilewati (baru saja error)", 0.0))
            continue
        k = klien if terakhir or not hasattr(klien, "with_options") else klien.with_options(timeout=BATAS_WAKTU_UTAMA)
        for jeda in ((*JEDA_ULANG, None) if terakhir else (None,)):
            t = time.time()
            try:
                respons = k.chat.completions.create(model=m, temperature=temperature, messages=pesan)
                RIWAYAT.append((m, "OK", round(time.time() - t, 1)))
                _lewati_sampai.pop(m, None)
                MODEL_TERAKHIR = m
                return respons
            except (RateLimitError, InternalServerError, APITimeoutError, APIConnectionError) as e:
                RIWAYAT.append((m, type(e).__name__, round(time.time() - t, 1)))
                galat = e
                if not terakhir:                    # model utama error: lewati sementara
                    _lewati_sampai[m] = time.time() + LEWATI_MENIT * 60
                    break
                if not isinstance(e, RateLimitError) or jeda is None:
                    break
                time.sleep(jeda)
            except BadRequestError as e:
                RIWAYAT.append((m, "BadRequestError", round(time.time() - t, 1)))
                raise
    raise galat


def _minta(klien, model, aturan, isi, temperature):
    """Kirim satu permintaan chat dan kembalikan teks jawabannya.

    Sebagian model Gemma di Gemini API menolak pesan "system". Kalau ditolak (error 400),
    permintaan diulang sekali dengan aturan digabung ke pesan user.
    """
    RIWAYAT.clear()
    pesan = [{"role": "system", "content": aturan}, {"role": "user", "content": isi}]
    try:
        respons = _kirim(klien, model, temperature, pesan)
    except BadRequestError:
        gabung = [{"role": "user", "content": f"{aturan}\n\n{isi}"}]
        respons = _kirim(klien, model, temperature, gabung)
    return (respons.choices[0].message.content or "").strip()


def tanya(klien, model, pertanyaan, konteks):
    return _minta(klien, model, SYSTEM_PROMPT,
                  f"KONTEKS DATA:\n{konteks}\n\nPERTANYAAN: {pertanyaan}", 0.2)


# ---------- 4. Usulan jadwal (aksi dengan konfirmasi operator) ----------
PROMPT_JADWAL = """Ubah permintaan operator menjadi SATU usulan jadwal dalam format JSON, tanpa teks lain.
Kunci wajib:
- "sistem": "HVAC" atau "Pencahayaan"
- "lantai": angka 1 sampai 10
- "zona": null, atau "Z1" sampai "Z5"
- "mode": "jadwal", "manual", atau "lembur"
- "jam_mulai" dan "jam_selesai": format "HH:MM"
Aturan jam:
- Selalu format 24 jam: "jam 8 malam" = "20:00", "jam 7 pagi" = "07:00".
   - Lembur tanpa jam mulai: pakai "17:00" (akhir jam kerja). Lembur tanpa jam selesai: pakai "20:00". Satu lantai penuh: "zona": null.
- Kalau ada "Revisi dari operator", pakai jam dan lantai dari revisi itu (yang terbaru).
   Kalau permintaan menyangkut kebakaran, keamanan, atau tidak bisa dijadikan jadwal, balas:
{"ditolak": "<alasan singkat>"}"""

SISTEM_BOLEH = {"hvac": "HVAC", "pencahayaan": "Pencahayaan"}
KOLOM_JADWAL = ["sistem", "lantai", "zona", "mode", "jam_mulai", "jam_selesai",
                "status", "diusulkan_oleh", "waktu"]
MODE_BOLEH = {"jadwal", "manual", "lembur"}
ZONA_BOLEH = {"Z1", "Z2", "Z3", "Z4", "Z5"}

def _jam(teks):
    """'8:00', '08.00', '20:00' -> 'HH:MM'; selain itu None."""
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", str(teks))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"

def usulkan_jadwal(klien, model, permintaan):
    teks = _minta(klien, model, PROMPT_JADWAL, permintaan, 0)
    cocok = re.search(r"\{.*\}", teks, re.S)
    if not cocok:
        return {"ditolak": "Jawaban AI tidak berformat JSON."}
    try:
        data = json.loads(cocok.group())
    except json.JSONDecodeError:
        return {"ditolak": "JSON dari AI tidak valid."}
    if "ditolak" in data:
        return data
    data.setdefault("zona", None)
    if not all(k in data for k in KOLOM_JADWAL[:6]):
        return {"ditolak": "Usulan dari AI tidak lengkap."}

    # Pemeriksaan oleh kode, tidak hanya mengandalkan AI
    sistem = SISTEM_BOLEH.get(str(data["sistem"]).lower())
    if sistem is None:
        return {"ditolak": "Hanya HVAC dan pencahayaan yang boleh dijadwalkan."}
    try:
        lantai = int(data["lantai"])
    except (TypeError, ValueError):
        return {"ditolak": "Lantai tidak jelas."}
    if not 1 <= lantai <= 10:
        return {"ditolak": "Lantai harus 1 sampai 10."}
    mode = str(data["mode"]).lower()
    if mode not in MODE_BOLEH:
        return {"ditolak": "Mode harus jadwal, manual, atau lembur."}
    zona = data["zona"]
    zona = None if zona in (None, "", "null", "None") else str(zona).upper()
    if zona is not None and zona not in ZONA_BOLEH:
        return {"ditolak": "Zona harus Z1 sampai Z5, atau kosong untuk satu lantai."}
    mulai, selesai = _jam(data["jam_mulai"]), _jam(data["jam_selesai"])
    if mulai is None or selesai is None:
        return {"ditolak": "Jam harus berformat HH:MM."}
    if selesai <= mulai:
        return {"ditolak": "Jam selesai harus setelah jam mulai."}
    data.update(mode=mode, zona=zona, jam_mulai=mulai, jam_selesai=selesai)

    data.update(sistem=sistem, lantai=lantai,
                status="usulan",                    # AI hanya boleh mengusulkan
                diusulkan_oleh="AI",
                waktu=pd.Timestamp.now().floor("min").isoformat())
    return {k: data[k] for k in KOLOM_JADWAL}