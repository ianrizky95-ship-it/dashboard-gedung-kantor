import pandas as pd
import streamlit as st

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
def tanda(x):
    return None if pd.isna(x) else f"{'+' if x >= 0 else ''}{angka(x, 1)}%"

def kartu(kol, label, nilai, delta=None, keterangan=None, bantu=None):
    with kol.container(border=True):
        st.metric(label, nilai, delta, delta_color="inverse", help=bantu)
        if keterangan:
            st.caption(keterangan)