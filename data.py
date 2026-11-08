import pandas as pd
import streamlit as st
from olah import kondisi_hari_ini
import os

TARIF = 1114.74      # Rp/kWh, B-3/TM
LUAS = 11_000        # m², 10 lantai × 1.100 m²
SISTEM = ["HVAC", "Listrik", "Pencahayaan", "Air bersih", "Kebakaran", "Keamanan"]

def angka(x, d=0):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")

def rp(x):
    return "Rp " + angka(x)

def waktu_sekarang():
    return pd.Timestamp.now(tz="Asia/Jakarta").tz_localize(None).floor("15min")

@st.cache_data
def muat_energi():
    return pd.read_parquet("data/processed/energi.parquet")

@st.cache_data
def muat_alarm():
    return pd.read_parquet("data/processed/alarm.parquet")
@st.cache_data
def muat_kondisi():
    return pd.read_parquet("data/processed/kondisi_unit_harian.parquet")

@st.cache_data
def muat_unit():
    return pd.read_parquet("data/processed/unit.parquet")
LOG = "data/processed/log_maintenance.parquet"

@st.cache_data
def muat_log():
    return pd.read_parquet(LOG)

def catat_log(id_unit, catatan, operator="operator dashboard"):
    """Tambah satu baris reset ke log. Di Streamlit Cloud file bisa tidak tersimpan permanen."""
    baru = pd.DataFrame([{"waktu": waktu_sekarang(), "id_unit": id_unit, "aksi": "reset",
                          "operator": operator, "catatan": catatan or "-"}])
    baru["waktu"] = baru["waktu"].astype("datetime64[us]")
    try:
        log = pd.concat([pd.read_parquet(LOG), baru], ignore_index=True)
        log.to_parquet(LOG, index=False)
        muat_log.clear()                 # buang cache supaya log baru langsung terbaca
    except Exception:
        pass                             # reset tetap berlaku selama sesi berjalan
def reset_aktif(sekarang):
    """Reset dari dashboard yang tercatat di log + reset di sesi ini."""
    log = muat_log()
    dari_log = (log[(log["operator"] == "operator dashboard") & (log["waktu"] <= sekarang)]
                .groupby("id_unit")["waktu"].max().to_dict())
    return {**dari_log, **st.session_state.get("reset", {})}


def kondisi_terkini():
    """Satu sumber kondisi unit untuk semua halaman: file + reset + skenario mode demo."""
    sekarang = waktu_sekarang()
    return kondisi_hari_ini(muat_kondisi(), muat_unit(), sekarang,
                            reset_aktif(sekarang), st.session_state.get("skenario", []))
# ---------- Jadwal kontrol ----------
JADWAL = "data/processed/jadwal.parquet"
KOLOM_JADWAL = ["sistem", "lantai", "zona", "mode", "jam_mulai", "jam_selesai",
                "status", "diusulkan_oleh", "waktu"]


def jadwal_awal():
    """Jadwal rutin bawaan: HVAC dan pencahayaan tiap lantai, Senin-Jumat 07.00-17.00."""
    baris = [{"sistem": s, "lantai": lt, "zona": None, "mode": "jadwal",
              "jam_mulai": "07:00", "jam_selesai": "17:00", "status": "disetujui",
              "diusulkan_oleh": "sistem", "waktu": pd.Timestamp("2026-01-01")}
             for lt in range(1, 11) for s in ("HVAC", "Pencahayaan")]
    return pd.DataFrame(baris, columns=KOLOM_JADWAL)


def muat_jadwal():
    """Jadwal disimpan di sesi; kalau file belum ada, mulai dari jadwal bawaan."""
    if "jadwal" not in st.session_state:
        try:
            st.session_state["jadwal"] = pd.read_parquet(JADWAL)
        except Exception:
            st.session_state["jadwal"] = jadwal_awal()
    return st.session_state["jadwal"]


def simpan_jadwal(df):
    st.session_state["jadwal"] = df.reset_index(drop=True)
    try:
        st.session_state["jadwal"].to_parquet(JADWAL, index=False)
    except Exception:
        pass                                # di Streamlit Cloud tetap berlaku selama sesi


def tambah_usulan(usulan):
    """usulan = dict dengan kunci KOLOM_JADWAL (format sama dengan keluaran AI Mas Rifai)."""
    baru = pd.DataFrame([usulan], columns=KOLOM_JADWAL)
    baru["waktu"] = pd.to_datetime(baru["waktu"])
    simpan_jadwal(pd.concat([muat_jadwal(), baru], ignore_index=True))


def ubah_status(indeks, status):
    j = muat_jadwal().copy()
    j.loc[indeks, "status"] = status
    simpan_jadwal(j)

def tanda(x):
    return None if pd.isna(x) else f"{'+' if x >= 0 else ''}{angka(x, 1)}%"

def kartu(kol, label, nilai, delta=None, keterangan=None, bantu=None):
    with kol.container(border=True):
        st.metric(label, nilai, delta, delta_color="inverse", help=bantu)
        if keterangan:
            st.caption(keterangan)
            
def _baca_kalau_ada(nama):
    """Kembalikan None kalau file belum dikirim, supaya halaman tidak error."""
    path = f"data/processed/{nama}"
    if not os.path.exists(path):
        return None
    return pd.read_csv(path) if nama.endswith(".csv") else pd.read_parquet(path)

@st.cache_data
def muat_prediksi():
    return _baca_kalau_ada("prediksi.parquet")

@st.cache_data
def muat_backtest():
    return _baca_kalau_ada("backtest.parquet")

@st.cache_data
def muat_prediksi_maintenance():
    return _baca_kalau_ada("prediksi_maintenance.parquet")

@st.cache_data
def muat_threshold():
    return _baca_kalau_ada("threshold_hi.csv")