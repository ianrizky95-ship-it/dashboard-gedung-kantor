import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from data import TARIF, angka, rp, kartu, muat_energi, waktu_sekarang

LUAS_LANTAI = 1_100  # m²
WARNA_WAKTU = alt.Scale(domain=["Jam kerja", "Luar jam kerja"], range=["#64748B", "#F97316"])
WARNA_BEBAN = alt.Scale(domain=["AC", "Lampu", "Stopkontak"], range=["#10B981", "#FBBF24", "#60A5FA"])

sekarang = waktu_sekarang()
df = muat_energi()
df = df[df["timestamp"] <= sekarang]

st.header("Energi per Lantai")
hari = st.radio("Periode", [7, 30], format_func=lambda h: f"{h} hari terakhir", horizontal=True)

d = df[df["timestamp"] > sekarang - pd.Timedelta(days=hari)].copy()
ts = d["timestamp"]
kerja = (ts.dt.day_of_week < 5) & (ts.dt.hour >= 7) & (ts.dt.hour < 17)
d["waktu"] = np.where(kerja, "Jam kerja", "Luar jam kerja")
d["kWh"] = d["kW"] * 0.25
d["lantai"] = "LT" + d["lantai"].astype(str).str.zfill(2)
d["beban"] = d["beban"].replace({"LGT": "Lampu", "PLG": "Stopkontak"})

# --- Olahan per lantai ---
rank = d.pivot_table(index="lantai", columns="waktu", values="kWh", aggfunc="sum")
rank["Total kWh"] = rank["Jam kerja"] + rank["Luar jam kerja"]
rank["kWh/m²"] = rank["Total kWh"] / LUAS_LANTAI
rank["% luar jam kerja"] = 100 * rank["Luar jam kerja"] / rank["Total kWh"]
rank = rank.sort_values("% luar jam kerja", ascending=False)

total_kwh = rank["Total kWh"].sum()
luar_kwh = rank["Luar jam kerja"].sum()

# --- Baris KPI ---
k1, k2, k3, k4 = st.columns(4)
kartu(k1, ":material/bolt: Total energi", f"{angka(total_kwh)} kWh",
      keterangan=f"{hari} hari terakhir, 10 lantai")
kartu(k2, ":material/nightlight: Luar jam kerja", f"{angka(100 * luar_kwh / total_kwh, 1)}%",
      keterangan=f"≈ {rp(luar_kwh * TARIF)}")
kartu(k3, ":material/trending_up: Paling boros", rank.index[0],
      keterangan=f"{angka(rank['% luar jam kerja'].iloc[0], 1)}% di luar jam kerja")
kartu(k4, ":material/square_foot: Intensitas rata-rata", f"{angka(rank['kWh/m²'].mean(), 1)} kWh/m²",
      keterangan="per lantai, periode terpilih")

# --- Grafik + tabel ranking ---
per_waktu = d.groupby(["lantai", "waktu"], as_index=False)["kWh"].sum()
bar = alt.Chart(per_waktu).mark_bar().encode(
    y=alt.Y("lantai:N", sort="descending", title=None),
    x=alt.X("kWh:Q", title="kWh"),
    color=alt.Color("waktu:N", title=None, scale=WARNA_WAKTU, legend=alt.Legend(orient="top")),
    tooltip=["lantai", "waktu", alt.Tooltip("kWh:Q", format=",.0f")],
).properties(height=400)

tampil = pd.DataFrame({
    "Total kWh": rank["Total kWh"].map(angka),
    "kWh/m²": rank["kWh/m²"].map(lambda x: angka(x, 1)),
    "% luar jam kerja": rank["% luar jam kerja"],
    "Biaya luar jam kerja": (rank["Luar jam kerja"] * TARIF).map(rp),
}, index=rank.index)

kiri, kanan = st.columns([3, 2])
with kiri:
    st.subheader("Jam kerja vs luar jam kerja")
    st.altair_chart(bar)
with kanan:
    st.subheader("Ranking lantai")
    st.dataframe(tampil, height=400, column_config={
        "% luar jam kerja": st.column_config.ProgressColumn(
            min_value=0, max_value=100, format="%.0f%%"),
    })

# --- Komposisi beban satu lantai ---
st.subheader("Komposisi beban")
pilih = st.selectbox("Pilih lantai", sorted(d["lantai"].unique()))
lt = d[d["lantai"] == pilih]
komposisi = (lt.groupby([pd.Grouper(key="timestamp", freq="1h"), "beban"])["kW"]
             .mean().reset_index())
area = alt.Chart(komposisi).mark_area(opacity=0.85).encode(
    x=alt.X("timestamp:T", title=None),
    y=alt.Y("kW:Q", stack="zero", title="kW"),
    color=alt.Color("beban:N", title=None, scale=WARNA_BEBAN, legend=alt.Legend(orient="top")),
    tooltip=[alt.Tooltip("timestamp:T", format="%a %d %b %H:%M"), "beban",
             alt.Tooltip("kW:Q", format=".1f")],
)
st.altair_chart(area.properties(height=300))