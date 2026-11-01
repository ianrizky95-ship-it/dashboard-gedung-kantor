import altair as alt
import pandas as pd
import streamlit as st
from data import TARIF, LUAS, SISTEM, angka, rp, muat_energi, muat_alarm, waktu_sekarang
df = muat_energi()
sekarang = waktu_sekarang()
df = df[df["timestamp"] <= sekarang]                 # sembunyikan "masa depan"
def muat_alarm():
    return pd.read_parquet("data/processed/alarm.parquet")

alarm = muat_alarm()
alarm = alarm[alarm["waktu"] <= sekarang]
aktif = alarm[alarm["status"] != "Selesai"]      # Aktif + Diakui = belum selesai
total = df.groupby("timestamp")["kW"].sum()          # kW gedung per 15 menit
ts = total.index
hari_ini = total[ts.normalize() == sekarang.normalize()]
kemarin = total[ts.normalize() == sekarang.normalize() - pd.Timedelta(days=1)]

jam_kerja = (ts.day_of_week < 5) & (ts.hour >= 7) & (ts.hour < 17)
bulan_ini = (ts.year == sekarang.year) & (ts.month == sekarang.month)
kwh_bulan = total[bulan_ini].sum() * 0.25
kwh_luar = total[bulan_ini & ~jam_kerja].sum() * 0.25

st.title("Ringkasan Gedung")
st.caption(f"Data per {sekarang:%d %b %Y %H:%M} · energi dummy (akan diganti proxy CU-BEMS)")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("kWh hari ini", angka(hari_ini.sum() * 0.25))
k2.metric("Beban kini", f"{angka(total.iloc[-1])} kW")
k3.metric("IKE berjalan", f"{angka(total.sum() * 0.25 / LUAS, 1)} kWh/m²")
k4.metric("Luar jam kerja (bulan ini)", f"{angka(100 * kwh_luar / kwh_bulan, 1)}%")
k4.caption(f"≈ {rp(kwh_luar * TARIF)} bulan ini")
k5.metric("Alarm aktif", len(aktif))
k5.caption(f"{(aktif['prioritas'] == 'Tinggi').sum()} prioritas tinggi")

kiri, kanan = st.columns([3, 2])

with kiri:
    st.subheader("Beban 24 jam")
    grafik = pd.DataFrame({
        "Kemarin": pd.Series(kemarin.values, index=kemarin.index.strftime("%H:%M")),
        "Hari ini": pd.Series(hari_ini.values, index=hari_ini.index.strftime("%H:%M")),
    })
    st.line_chart(grafik, y_label="kW")

with kanan:
    st.subheader("Heatmap lantai × jam")
    pilihan = st.radio("Rata-rata 4 minggu terakhir", ["Hari kerja", "Akhir pekan"], horizontal=True)

    empat_minggu = df[df["timestamp"] > sekarang - pd.Timedelta(days=28)]
    hari_ke = empat_minggu["timestamp"].dt.day_of_week
    subset = empat_minggu[hari_ke < 5] if pilihan == "Hari kerja" else empat_minggu[hari_ke >= 5]

    per_jam = (subset.assign(jam=subset["timestamp"].dt.hour)
               .groupby(["lantai", "jam"])["kW"].mean().reset_index())
    per_jam["lantai"] = "LT" + per_jam["lantai"].astype(str).str.zfill(2)

    heat = alt.Chart(per_jam).mark_rect().encode(
        x=alt.X("jam:O", title="Jam"),
        y=alt.Y("lantai:O", title=None, sort="descending"),
        color=alt.Color("kW:Q", title="kW rata-rata", scale=alt.Scale(scheme="oranges")),
        tooltip=["lantai", "jam", alt.Tooltip("kW:Q", format=".1f")],
    )
    st.altair_chart(heat.properties(height=320))
    st.subheader("Status sistem")
for kol, s in zip(st.columns(6), SISTEM):
    a = aktif[aktif["sistem"] == s]
    if (a["prioritas"] == "Tinggi").any():
        ikon = "🔴"
    elif len(a) > 0:
        ikon = "🟡"
    else:
        ikon = "🟢"
    with kol.container(border=True):
        st.markdown(f"{ikon} **{s}**")
        st.caption(f"{len(a)} alarm aktif")