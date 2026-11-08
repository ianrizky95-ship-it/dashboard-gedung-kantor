import altair as alt
import pandas as pd
import streamlit as st
from data import TARIF, LUAS, SISTEM, angka, rp, tanda, kartu, muat_energi, muat_alarm, waktu_sekarang
from olah import alpha_filter, insight
from data import muat_kondisi, muat_unit
from data import kondisi_terkini
from komponen import annunciator
from olah import kalimat_prediksi
from data import muat_prediksi, muat_backtest
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
bulan_ini = ts > sekarang - pd.Timedelta(days=30)
kwh_bulan = total[bulan_ini].sum() * 0.25
kwh_luar = total[bulan_ini & ~jam_kerja].sum() * 0.25

st.header("Ringkasan Gedung")
st.caption(f"Data per {sekarang:%d %b %Y %H:%M} · energi: proxy CU-BEMS")


# Pembanding: kemarin sampai jam yang sama, dan beban minggu lalu di jam yang sama
kwh_hari_ini = hari_ini.sum() * 0.25
jam_kemarin = sekarang - pd.Timedelta(days=1)
kwh_kemarin = total[(ts >= jam_kemarin.normalize()) & (ts <= jam_kemarin)].sum() * 0.25
beban_kini = total.iloc[-1]
beban_lalu = total.get(total.index[-1] - pd.Timedelta(days=7), float("nan"))

k1, k2, k3, k4, k5 = st.columns(5)
kartu(k1, ":material/bolt: kWh hari ini", angka(kwh_hari_ini),
      delta=f"{tanda(100 * (kwh_hari_ini - kwh_kemarin) / kwh_kemarin)} vs kemarin")
kartu(k2, ":material/speed: Beban kini", f"{angka(beban_kini)} kW",
      delta=f"{tanda(100 * (beban_kini - beban_lalu) / beban_lalu)} vs minggu lalu")
kartu(k3, ":material/eco: IKE (kWh/m²)", angka(total.sum() * 0.25 / LUAS, 1),
      keterangan="sejak 30 Des 2025",
      bantu="Intensitas Konsumsi Energi: total kWh dibagi luas lantai")
kartu(k4, ":material/nightlight: Luar jam kerja (30 hari)",
      f"{angka(100 * kwh_luar / kwh_bulan, 1)}%",
      keterangan=f"≈ {rp(kwh_luar * TARIF)}",
      bantu="Di luar Senin–Jumat 07.00–17.00, termasuk akhir pekan")
kartu(k5, ":material/notifications_active: Alarm aktif", len(aktif),
      keterangan=f"{(aktif['prioritas'] == 'Tinggi').sum()} prioritas tinggi")

# ---------- Annunciator + Executive Summary ----------
_k = kondisi_terkini()
annunciator(_k)

with st.container(border=True):
    st.subheader("Executive Summary")
    st.caption("Dihitung otomatis dari data 7 hari terakhir dan kondisi unit hari ini.")
    _sekarang = waktu_sekarang()
    _kalimat = insight(muat_energi(), muat_kondisi(), muat_unit(), _sekarang, TARIF, k_hari_ini=_k)
    _prediksi = kalimat_prediksi(muat_prediksi(), muat_backtest(), _sekarang, TARIF)
if _prediksi:
    _kalimat.append(_prediksi)
    st.markdown("\n".join(f"- {k}" for k in _kalimat))
kiri, kanan = st.columns([3, 2])

with kiri:
    st.subheader("Beban 24 jam")
    def ke_jam(seri, nama):
        return pd.DataFrame({"jam": seri.index.hour + seri.index.minute / 60,
                             "kW": seri.values, "hari": nama})

    data_garis = pd.concat([ke_jam(hari_ini, "Hari ini"), ke_jam(kemarin, "Kemarin")])

    pita = alt.Chart(pd.DataFrame({"mulai": [7], "selesai": [17]})).mark_rect(
        color="#94A3B8", opacity=0.12).encode(x="mulai:Q", x2="selesai:Q")
    label_pita = alt.Chart(pd.DataFrame({"jam": [12], "teks": ["Jam kerja"]})).mark_text(
        color="#94A3B8", dy=-8, fontSize=11).encode(x="jam:Q", y=alt.value(0), text="teks:N")

    garis = alt.Chart(data_garis).mark_line(strokeWidth=2).encode(
        x=alt.X("jam:Q", title="Jam", scale=alt.Scale(domain=[0, 24]),
                axis=alt.Axis(values=list(range(0, 25, 3)))),
        y=alt.Y("kW:Q", title="kW", scale=alt.Scale(zero=True)),
        color=alt.Color("hari:N", title=None, legend=alt.Legend(orient="top"),
                        scale=alt.Scale(domain=["Hari ini", "Kemarin"],
                                        range=["#10B981", "#64748B"])),
        strokeDash=alt.StrokeDash("hari:N", legend=None,
                                  scale=alt.Scale(domain=["Hari ini", "Kemarin"],
                                                  range=[[1, 0], [4, 4]])),
        tooltip=["hari", alt.Tooltip("jam:Q", format=".2f"), alt.Tooltip("kW:Q", format=".0f")],
    )
    st.altair_chart((pita + label_pita + garis).properties(height=320))

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
    a = aktif[aktif["sistem"] == s].sort_values("waktu", ascending=False)
    if len(a) == 0:
        kol.success(f"**{s}**  \nNormal", icon=":material/check_circle:")
    else:
        teks = f"**{s}**  \n{len(a)} alarm · {a.iloc[0]['pesan']}"
        if (a["prioritas"] == "Tinggi").any():
            kol.error(teks, icon=":material/error:")
        else:
            kol.warning(teks, icon=":material/warning:")

st.page_link("halaman/status_sistem.py", label="Lihat log alarm lengkap",
             icon=":material/arrow_forward:")


# ---------- Tren beban 7 hari dengan alpha filter ----------
st.subheader("Tren beban 7 hari")
alpha = st.slider("Alpha filter (makin kecil, makin halus)", 0.05, 1.0, 0.3, 0.05)
_e = muat_energi()
_e = _e[(_e["timestamp"] > _sekarang - pd.Timedelta(days=7)) & (_e["timestamp"] <= _sekarang)]
_beban = _e.groupby("timestamp")["kW"].sum()
st.line_chart(pd.DataFrame({"Asli": _beban, "Dihaluskan": alpha_filter(_beban, alpha)}),
              y_label="kW", color=["#64748B", "#10B981"])