import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from data import TARIF, angka, rp, muat_energi, waktu_sekarang

LUAS_LANTAI = 1_100  # m²

sekarang = waktu_sekarang()
df = muat_energi()
df = df[df["timestamp"] <= sekarang]

st.title("Energi per Lantai")
hari = st.radio("Periode", [7, 30], format_func=lambda h: f"{h} hari terakhir", horizontal=True)

d = df[df["timestamp"] > sekarang - pd.Timedelta(days=hari)].copy()
ts = d["timestamp"]
kerja = (ts.dt.day_of_week < 5) & (ts.dt.hour >= 7) & (ts.dt.hour < 17)
d["waktu"] = np.where(kerja, "Jam kerja", "Luar jam kerja")
d["kWh"] = d["kW"] * 0.25
d["lantai"] = "LT" + d["lantai"].astype(str).str.zfill(2)

# --- Jam kerja vs luar jam kerja per lantai ---
per_waktu = d.groupby(["lantai", "waktu"], as_index=False)["kWh"].sum()
bar = alt.Chart(per_waktu).mark_bar().encode(
    y=alt.Y("lantai:N", sort="descending", title=None),
    x=alt.X("kWh:Q", title="kWh"),
    color=alt.Color("waktu:N", title=None,
                    scale=alt.Scale(domain=["Jam kerja", "Luar jam kerja"],
                                    range=["#9ca3af", "#ea580c"])),
    tooltip=["lantai", "waktu", alt.Tooltip("kWh:Q", format=",.0f")],
).properties(height=320)

# --- Ranking lantai ---
rank = d.pivot_table(index="lantai", columns="waktu", values="kWh", aggfunc="sum")
rank["Total kWh"] = rank["Jam kerja"] + rank["Luar jam kerja"]
rank["kWh/m²"] = rank["Total kWh"] / LUAS_LANTAI
rank["% luar jam kerja"] = 100 * rank["Luar jam kerja"] / rank["Total kWh"]
rank["Biaya luar jam kerja"] = rank["Luar jam kerja"] * TARIF
rank = rank.sort_values("% luar jam kerja", ascending=False)
tampil = rank[["Total kWh", "kWh/m²", "% luar jam kerja", "Biaya luar jam kerja"]]

kiri, kanan = st.columns([3, 2])
with kiri:
    st.subheader("Jam kerja vs luar jam kerja")
    st.altair_chart(bar)
with kanan:
    st.subheader("Ranking lantai")
    st.dataframe(tampil.style.format({
        "Total kWh": angka,
        "kWh/m²": lambda x: angka(x, 1),
        "% luar jam kerja": lambda x: angka(x, 1),
        "Biaya luar jam kerja": rp,
    }), height=320)

# --- Komposisi beban satu lantai ---
st.subheader("Komposisi beban")
pilih = st.selectbox("Pilih lantai", sorted(d["lantai"].unique()))
lt = d[d["lantai"] == pilih]
komposisi = (lt.groupby([pd.Grouper(key="timestamp", freq="1h"), "beban"])["kW"]
             .mean().unstack()
             .rename(columns={"LGT": "Lampu", "PLG": "Stopkontak"}))
st.area_chart(komposisi, y_label="kW", stack=True)