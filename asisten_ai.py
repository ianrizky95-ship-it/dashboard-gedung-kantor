"""Perantara antara dashboard dan ai_asisten.py (Mas Rifai).

Halaman Asisten hanya memanggil file ini. Kalau ai_asisten.py belum ada, API key belum
diisi, atau panggilan AI gagal, file ini otomatis beralih ke MODE CADANGAN: jawaban dihitung
langsung dari data dashboard, jadi halaman tetap bisa didemokan.
"""
import json
import os
import re

import pandas as pd
import streamlit as st

from data import (KOLOM_JADWAL, TARIF, muat_energi, muat_unit, kondisi_terkini, reset_aktif,
                  muat_kondisi, muat_prediksi, muat_backtest, muat_prediksi_maintenance,
                  muat_threshold, waktu_sekarang)
from olah import LEVEL_URUT, insight, kalimat_prediksi, metode_terbaik, jadwal_maintenance, _id

KOLOM_KONDISI = ["tanggal", "id_unit", "id_aset", "jam_nyala", "jam_kumulatif", "persen_umur",
                 "suhu_motor_maks_C", "rasio_daya", "health_index", "level"]
PRESET = {                                   # sama dengan PERTANYAAN di notebook Mas Rifai
    "ringkasan":   "Ringkas kondisi gedung hari ini dan 7 hari terakhir.",
    "maintenance": "Unit mana yang perlu maintenance paling dulu? Buat tabel berurutan prioritas.",
    "anomali":     "Ada anomali hari ini? Buat tabel berurutan prioritas beserta penyebabnya.",
}
TOMBOL = {"ringkasan": "📋 Ringkasan kondisi", "maintenance": "🔧 Prioritas maintenance",
          "anomali": "⚠️ Anomali hari ini"}
CADANGAN = "jawaban_cadangan.json"


# ================= 1. Pengaturan dan koneksi =================
def _rahasia(nama, bawaan=None):
    """Baca .streamlit/secrets.toml (laptop) atau Secrets Streamlit Cloud; aman kalau belum ada."""
    try:
        return st.secrets.get(nama, bawaan)
    except Exception:
        return bawaan


@st.cache_resource(show_spinner=False)
def _sambung(penyedia, model):
    """Coba impor ai_asisten.py dan buat klien. Hasil: (modul, klien, pesan_galat)."""
    if not model:
        return None, None, "AI_MODEL belum diisi di secrets"
    try:
        import ai_asisten
        return ai_asisten, ai_asisten.buat_klien(penyedia), None
    except ModuleNotFoundError as e:
        hilang = "ai_asisten.py belum ada" if e.name == "ai_asisten" else f"paket {e.name} belum terpasang"
        return None, None, hilang
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"


def _ai():
       for kunci in ("GEMINI_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY"):   # Secrets -> environment
        nilai = _rahasia(kunci)
        if nilai:
            os.environ[kunci] = nilai
        penyedia, model = _rahasia("AI_PENYEDIA", "openrouter"), _rahasia("AI_MODEL")
        modul, klien, galat = _sambung(penyedia, model)
        return modul, klien, model, penyedia, galat


def status():
    modul, _, model, penyedia, galat = _ai()
    if modul is None:
        return {"mode": "cadangan", "keterangan": galat}
    return {"mode": "AI", "keterangan": f"{penyedia} · {model}"}


# ================= 2. Konteks =================
def konteks_tambahan(sekarang):
    """Prediksi energi dan jadwal maintenance dari file Mas Hasan, sebagai teks untuk AI."""
    baris = [f"CATATAN: kWh hari ini ({sekarang:%d-%m}) baru sampai pukul {sekarang:%H.%M}, "
             "jadi angkanya belum satu hari penuh."]
    pred, bt = muat_prediksi(), muat_backtest()
    if pred is not None and bt is not None:
        m = metode_terbaik(bt)
        p = pred[(pred["metode"] == m) & (pred["tanggal"] >= sekarang.normalize())].head(7)
        mape = bt.set_index("metode").loc[m, "MAPE_persen"]
        baris += ["", f"PREDIKSI ENERGI 7 HARI (metode {m}, MAPE backtest {_id(mape, 1)}%):"]
        baris += [f"{r.tanggal:%a %d-%m}: {r.kWh:.0f} kWh (rentang {r.bawah:.0f}-{r.atas:.0f})"
                  for r in p.itertuples()]
    pm, thr = muat_prediksi_maintenance(), muat_threshold()
    if pm is not None and thr is not None:
        jm = jadwal_maintenance(kondisi_terkini(), pm, thr, sekarang, reset_aktif(sekarang))
        dekat = jm[(jm["hari_ke_siaga"] <= 30) | (jm["hari_ke_kritis"] <= 30)].head(12)
        baris += ["", "PERKIRAAN MAINTENANCE 30 HARI (dari jam pakai):"]
        baris += [f"{r.id_unit}: level {r.level}, Siaga {r.tgl_siaga:%d-%m-%Y}, "
                  f"Kritis {r.tgl_kritis:%d-%m-%Y} {('(' + r.keterangan + ')') if r.keterangan else ''}"
                  for r in dekat.itertuples()] or ["(tidak ada)"]
    baris += konteks_biaya(sekarang)
    baris += konteks_prognosa(sekarang)
    return "\n".join(baris)


def _angka(x, d=0):
    return f"{x:,.{d}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def konteks_biaya(sekarang):
    """Energi & biaya harian (bulan lalu + bulan ini) dan total per bulan, untuk pertanyaan biaya."""
    from data import TARIF
    energi = muat_energi()
    energi = energi[energi["timestamp"] <= sekarang]
    kwh = (energi["kW"] * 0.25).groupby(energi["timestamp"].dt.normalize()).sum()
    awal = (sekarang.normalize() - pd.DateOffset(months=1)).replace(day=1)
    baris = ["", f"TARIF LISTRIK: Rp {_angka(TARIF, 2)}/kWh (biaya = kWh x tarif).",
             f"ENERGI & BIAYA HARIAN sejak {awal:%d-%m-%Y}. Kolom kumulatif = biaya sejak tanggal 1 bulan itu.",
             "Biaya rentang tanggal dalam satu bulan = kumulatif tanggal akhir - kumulatif sehari sebelum tanggal awal."]
    h = kwh[kwh.index >= awal]
    kum = h.groupby(h.index.to_period("M")).cumsum()
    baris += [f"{t:%a %d-%m-%Y}: {_angka(v)} kWh = Rp {_angka(v * TARIF)} | kumulatif Rp {_angka(kum[t] * TARIF)}"
              for t, v in h.items()]
    bulan = kwh.groupby(kwh.index.to_period("M")).agg(["sum", "count"])
    bulan = bulan[(bulan["count"] >= 28) | (bulan.index == sekarang.to_period("M"))]   # buang bulan terpotong
    baris += ["", "TOTAL PER BULAN:"]
    baris += [f"{p.strftime('%m-%Y')}: {_angka(r['sum'])} kWh = Rp {_angka(r['sum'] * TARIF)}"
              for p, r in bulan.iterrows()]
    baris.append(f"(Bulan {sekarang:%m-%Y} baru sampai {sekarang:%d-%m %H.%M}.)")
    return baris

def konteks_prognosa(sekarang):
    """Prognosa energi & biaya s.d. akhir bulan depan: data aktual + prediksi model + profil harian."""
    from data import TARIF
    energi = muat_energi()
    energi = energi[energi["timestamp"] <= sekarang]
    kwh = (energi["kW"] * 0.25).groupby(energi["timestamp"].dt.normalize()).sum()
    hari_ini = sekarang.normalize()
    # Profil: rata-rata kWh per hari (Senin..Minggu) dari 4 minggu terakhir yang sudah lengkap
    lalu = kwh[(kwh.index >= hari_ini - pd.Timedelta(days=28)) & (kwh.index < hari_ini)]
    profil = lalu.groupby(lalu.index.dayofweek).mean()
    pred, bt = muat_prediksi(), muat_backtest()
    model = {}
    if pred is not None and bt is not None:
        m = metode_terbaik(bt)
        model = pred[pred["metode"] == m].set_index("tanggal")["kWh"].to_dict()
    akhir = (hari_ini + pd.DateOffset(months=2)).replace(day=1) - pd.Timedelta(days=1)
    baris = []
    for t in pd.date_range(hari_ini.replace(day=1), akhir, freq="D"):
        if t < hari_ini:
            baris.append((t, kwh.get(t, 0.0), "aktual"))
        elif t == hari_ini:   # hari ini belum selesai: pakai yang lebih besar (aktual sementara vs profil)
            baris.append((t, max(kwh.get(t, 0.0), profil[t.dayofweek]), "aktual+profil"))
        elif pd.Timestamp(t) in model:
            baris.append((t, model[pd.Timestamp(t)], "prediksi model"))
        else:
            baris.append((t, profil[t.dayofweek], "profil harian"))
    df = pd.DataFrame(baris, columns=["tanggal", "kWh", "sumber"])
    out = ["", "PROGNOSA ENERGI & BIAYA PER BULAN (sampai akhir bulan depan).",
           "Cara hitung: hari yang sudah lewat = aktual; hari dengan prediksi model = prediksi; "
           "sisanya = rata-rata kWh per hari (Senin..Minggu) 4 minggu terakhir. Belum memperhitungkan hari libur nasional."]
    for p, d in df.groupby(df["tanggal"].dt.to_period("M")):
        porsi = d.groupby("sumber")["kWh"].sum()
        rincian = ", ".join(f"{s} {_angka(v)} kWh" for s, v in porsi.items())
        out.append(f"{p.strftime('%m-%Y')}: prognosa {_angka(d['kWh'].sum())} kWh = Rp {_angka(d['kWh'].sum() * TARIF)} "
                   f"({rincian})")
    return out

def konteks(sekarang=None):
    """Konteks lengkap: buat_konteks() Mas Rifai dari kondisi terkini + tambahan prediksi."""
    sekarang = sekarang or waktu_sekarang()
    modul = _ai()[0]
    if modul is None:
        return "(AI belum tersambung)\n" + konteks_tambahan(sekarang)
    energi = muat_energi()
    energi = energi[energi["timestamp"] <= sekarang]              # tanpa data "masa depan"
    k = kondisi_terkini()[KOLOM_KONDISI].assign(tanggal=sekarang.normalize())  # + reset + Mode demo
    return modul.buat_konteks(energi, k, muat_unit(), sekarang) + "\n" + konteks_tambahan(sekarang)


# ================= 3. Tanya-jawab =================
def _tabel(df):
    kepala = "| " + " | ".join(df.columns) + " |"
    garis = "| " + " | ".join("---" for _ in df.columns) + " |"
    isi = ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([kepala, garis] + isi)


def jawaban_tiruan(kunci, sekarang):
    """Jawaban tanpa AI, dihitung langsung dari data (ikut reset dan Mode demo)."""
    k = kondisi_terkini()
    k = k[k["status_unit"] == "Aktif"].assign(urut=lambda d: d["level"].map(LEVEL_URUT))
    if kunci == "ringkasan":
        poin = insight(muat_energi(), muat_kondisi(), muat_unit(), sekarang, TARIF)
        pred = kalimat_prediksi(muat_prediksi(), muat_backtest(), sekarang, TARIF)
        jumlah = k["level"].value_counts()
        poin = list(poin) + ([pred] if pred else []) + [
            "Unit per level: " + ", ".join(f"{lv} {int(jumlah.get(lv, 0))}"
                                           for lv in ["Kritis", "Waspada", "Siaga", "Normal"])]
        return "\n".join(f"- {p}" for p in poin)
    if kunci == "maintenance":
        u = k[k["level"].isin(["Kritis", "Waspada", "Siaga"])].sort_values(["urut", "health_index"]).head(10)
        if u.empty:
            return "Tidak ada unit yang perlu maintenance segera; semua unit aktif berlevel Normal."
        t = u.assign(No=range(1, len(u) + 1), HI=u["health_index"].round(0).astype(int))
        return ("Unit berikut perlu maintenance, urut dari yang paling mendesak:\n\n"
                + _tabel(t[["No", "id_unit", "level", "HI", "penyebab"]]
                         .rename(columns={"id_unit": "Unit", "level": "Level", "penyebab": "Penyebab"})))
    if kunci == "anomali":
        a = k[(k["rasio_daya"] >= 1.4) | (k["suhu_motor_maks_C"] >= 75)].sort_values(["urut", "health_index"])
        if a.empty:
            return "Tidak ada anomali daya AC maupun suhu motor pompa hari ini."
        a = a.assign(Indikator=[f"rasio daya {r:.2f}" if pd.notna(r) and r >= 1.4 else f"suhu motor {s:.1f} °C"
                                for r, s in zip(a["rasio_daya"], a["suhu_motor_maks_C"])])
        return ("Anomali hari ini, urut dari yang paling mendesak:\n\n"
                + _tabel(a[["id_unit", "level", "Indikator", "penyebab"]]
                         .rename(columns={"id_unit": "Unit", "level": "Level", "penyebab": "Penyebab"})))
    return None


def jawab(pertanyaan, kunci=None):
    """Hasil: {'teks': ..., 'sumber': ...}. Urutan: AI -> jawaban cadangan -> jawaban tiruan."""
    sekarang = waktu_sekarang()
    modul, klien, model, _, galat = _ai()
    if modul is not None:
        try:
            return {"teks": modul.tanya(klien, model, pertanyaan, konteks(sekarang)),
                    "sumber": f"🤖 AI · {model}"}
        except Exception as e:
            galat = f"panggilan AI gagal ({type(e).__name__})"
    if kunci in PRESET:
        demo_aktif = bool(st.session_state.get("skenario")) or bool(st.session_state.get("reset"))
        if os.path.exists(CADANGAN) and not demo_aktif:
            with open(CADANGAN, encoding="utf-8") as f:
                isi = json.load(f).get(kunci)
            if isi:
                return {"teks": isi["jawaban"], "sumber": f"💾 Jawaban cadangan · {galat}"}
        return {"teks": jawaban_tiruan(kunci, sekarang), "sumber": f"🧰 Dihitung dari data · {galat}"}
    return {"teks": "AI belum tersambung, jadi pertanyaan bebas belum bisa dijawab. "
                    'Pakai tombol di atas, atau minta jadwal (mis. "lantai 7 lembur sampai jam 8 malam").',
            "sumber": f"🧰 Mode cadangan · {galat}"}


# ================= 4. Usulan jadwal =================
MODE_BOLEH = {"jadwal", "manual", "lembur"}
ZONA_BOLEH = {"Z1", "Z2", "Z3", "Z4", "Z5"}
SISTEM_BOLEH = {"hvac": "HVAC", "pencahayaan": "Pencahayaan"}


def minta_jadwal(teks):
    """Apakah teks operator berupa permintaan jadwal (bukan pertanyaan)?"""
    t = teks.lower()
    if re.search(r"maintenance|servis|perawatan|pemeliharaan", t):
        return False
    if re.search(r"\b(lembur\w*|nyalakan|hidupkan|matikan|(di)?jadwal\w*)\b", t):
        return True
    # Lanjutan usulan sebelumnya, mis. "mulai jam 19:00 sampai 22:00"
    return bool(st.session_state.get("jadwal_terakhir")) and bool(
        re.search(r"(mulai|sampai|hingga|s\.?d\.?)\s*(jam\s*)?\d", t))

def _jam(teks):
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", str(teks))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def periksa_usulan(u):
    """Pemeriksaan ulang di sisi dashboard (berlaku walaupun ai_asisten.py belum diperbarui)."""
    if not isinstance(u, dict):
        return {"ditolak": "Jawaban AI tidak berbentuk usulan."}
    if "ditolak" in u:
        return {"ditolak": str(u["ditolak"])}
    u = dict(u)
    u.setdefault("zona", None)
    if not all(k in u for k in KOLOM_JADWAL[:6]):
        return {"ditolak": "Usulan dari AI tidak lengkap."}
    sistem = SISTEM_BOLEH.get(str(u["sistem"]).lower())
    if sistem is None:
        return {"ditolak": "Hanya HVAC dan pencahayaan yang boleh dijadwalkan."}
    try:
        lantai = int(u["lantai"])
    except (TypeError, ValueError):
        return {"ditolak": "Lantai tidak jelas."}
    if not 1 <= lantai <= 10:
        return {"ditolak": "Lantai harus 1 sampai 10."}
    mode = str(u["mode"]).lower()
    if mode not in MODE_BOLEH:
        return {"ditolak": "Mode harus jadwal, manual, atau lembur."}
    zona = None if u["zona"] in (None, "", "null", "None") else str(u["zona"]).upper()
    if zona is not None and zona not in ZONA_BOLEH:
        return {"ditolak": "Zona harus Z1 sampai Z5, atau kosong untuk satu lantai."}
    mulai, selesai = _jam(u["jam_mulai"]), _jam(u["jam_selesai"])
    if mulai is None or selesai is None:
        return {"ditolak": "Jam harus berformat HH:MM."}
    if selesai <= mulai:
        return {"ditolak": "Jam selesai harus setelah jam mulai."}
    return {"sistem": sistem, "lantai": lantai, "zona": zona, "mode": mode,
            "jam_mulai": mulai, "jam_selesai": selesai, "status": "usulan",
            "diusulkan_oleh": "AI", "waktu": waktu_sekarang()}


def usulan_tiruan(teks):
    """Pengurai sederhana tanpa AI, untuk mode cadangan."""
    t = teks.lower()
    if re.search(r"kebakaran|alarm|sprinkler|hidran|cctv|kamera|keamanan|pintu", t):
        return {"ditolak": "Sistem kebakaran dan keamanan hanya bisa dipantau dari dashboard."}
    lt = re.search(r"lantai\s*(\d+)", t)
    if not lt:
        return {"ditolak": 'Sebutkan lantainya, mis. "lantai 7".'}
    jam = []
    for h, mnt, bag in re.findall(r"jam\s*(\d{1,2})(?:[:.](\d{2}))?\s*(pagi|siang|sore|malam)?", t):
        h = int(h)
        if (bag in ("sore", "malam") and h < 12) or (bag == "siang" and h < 11):
            h += 12
        jam.append(f"{h:02d}:{mnt or '00'}")
    if not jam:
        return {"ditolak": 'Sebutkan jamnya, mis. "sampai jam 8 malam".'}
    mulai, selesai = (("17:00", jam[0]) if len(jam) == 1 else (jam[0], jam[1]))
    zona = re.search(r"zona\s*(\d)", t)
    return {"sistem": "Pencahayaan" if re.search(r"lampu|pencahayaan", t) else "HVAC",
            "lantai": int(lt.group(1)), "zona": f"Z{zona.group(1)}" if zona else None,
            "mode": "lembur" if "lembur" in t else "manual",
            "jam_mulai": mulai, "jam_selesai": selesai}


def usulan(teks):
    """Hasil: {'usulan': dict} atau {'ditolak': alasan}, plus 'sumber'."""
    modul, klien, model, _, galat = _ai()
    if modul is not None:
        try:
            hasil, sumber = modul.usulkan_jadwal(klien, model, teks), f"🤖 AI · {model}"
        except Exception as e:
            hasil, sumber = usulan_tiruan(teks), f"🧰 Pengurai cadangan · panggilan AI gagal ({type(e).__name__})"
    else:
        hasil, sumber = usulan_tiruan(teks), f"🧰 Pengurai cadangan · {galat}"
    hasil = periksa_usulan(hasil)
    if "ditolak" in hasil:
        return {"ditolak": hasil["ditolak"], "sumber": sumber}
    return {"usulan": hasil, "sumber": sumber}