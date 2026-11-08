import altair as alt
import pandas as pd
import streamlit as st
from data import (TARIF, angka, rp, muat_energi, muat_prediksi, muat_backtest,
                  muat_prediksi_maintenance, muat_threshold, kondisi_terkini,
                  reset_aktif, waktu_sekarang)
from olah import HARI_ID, IKON, metode_terbaik, kwh_harian, jadwal_maintenance

st.title("Prediksi")
st.caption("Hasil prediktor dihitung offline di notebook prediktor.ipynb (Mas Hasan); "
           "dashboard hanya membaca file hasilnya.")

sekarang = waktu_sekarang()
prediksi, backtest = muat_prediksi(), muat_backtest()

tab_energi, tab_mt = st.tabs(["⚡ Energi 14 hari", "🔧 Jadwal maintenance"])

# ======================= Tab 1: energi =======================
with tab_energi:
    if prediksi is None or backtest is None:
        st.info("Menunggu file prediksi.parquet dan backtest.parquet di data/processed.")
    else:
        terbaik = metode_terbaik(backtest)
        urutan = [terbaik] + [m for m in backtest["metode"] if m != terbaik]
        metode = st.radio("Metode", urutan, horizontal=True,
                          format_func=lambda m: f"{m} (terbaik)" if m == terbaik else m)
        p = prediksi[prediksi["metode"] == metode].sort_values("tanggal")
        nilai = backtest.set_index("metode").loc[metode]
        latih_sampai = prediksi["tanggal"].min() - pd.Timedelta(days=1)
        depan = p[p["tanggal"] >= sekarang.normalize()]
        if depan.empty:
            depan = p

        # ---------- Kartu ringkas ----------
        k1, k2, k3, k4 = st.columns(4)
        b = depan.iloc[0]
        k1.metric(f"Prediksi {HARI_ID[b['tanggal'].dayofweek]} {b['tanggal']:%d/%m}",
                  f"{angka(b['kWh'])} kWh", help=f"Rentang 95%: {angka(b['bawah'])}–{angka(b['atas'])} kWh")
        tujuh = depan.head(7)
        k2.metric("7 hari ke depan", f"{angka(tujuh['kWh'].sum())} kWh",
                  help="Jumlah prediksi 7 hari pertama mulai hari ini")
        k3.metric("Perkiraan biaya 7 hari", rp(tujuh["kWh"].sum() * TARIF), help=f"Tarif Rp {TARIF}/kWh")
        k4.metric(f"MAPE backtest {metode}", f"{angka(nilai['MAPE_persen'], 2)}%",
                  help="Rata-rata selisih prediksi vs aktual di 14 hari uji. Makin kecil makin baik.")

        # ---------- Grafik aktual + prediksi ----------
        aktual = kwh_harian(muat_energi(), sekarang)
        lain = prediksi[prediksi["metode"] != metode]
        x = alt.X("tanggal:T", title=None, axis=alt.Axis(format="%d/%m"))
        pita = alt.Chart(p).mark_area(opacity=0.18, color="#10B981").encode(
            x=x, y=alt.Y("bawah:Q", title="kWh per hari"), y2="atas:Q",
            tooltip=[alt.Tooltip("tanggal:T", format="%a %d %b"),
                     alt.Tooltip("bawah:Q", format=",.0f"), alt.Tooltip("atas:Q", format=",.0f")])
        garis_p = alt.Chart(p).mark_line(point=alt.OverlayMarkDef(color="#10B981"), color="#10B981").encode(
            x=x, y="kWh:Q",
            tooltip=[alt.Tooltip("tanggal:T", title="Tanggal", format="%a %d %b"),
                     alt.Tooltip("kWh:Q", title=f"Prediksi {metode}", format=",.0f")])
        garis_lain = alt.Chart(lain).mark_line(strokeDash=[4, 4], color="#64748B").encode(
            x=x, y="kWh:Q", detail="metode:N",
            tooltip=[alt.Tooltip("tanggal:T", format="%a %d %b"), "metode:N",
                     alt.Tooltip("kWh:Q", format=",.0f")])
        garis_a = alt.Chart(aktual[aktual["lengkap"]]).mark_line(
            point=alt.OverlayMarkDef(color="#E5E7EB"), color="#E5E7EB").encode(
            x=x, y="kWh:Q",
            tooltip=[alt.Tooltip("tanggal:T", title="Tanggal", format="%a %d %b"),
                     alt.Tooltip("kWh:Q", title="Aktual", format=",.0f")])
        berjalan = alt.Chart(aktual[~aktual["lengkap"]]).mark_point(
            shape="circle", size=70, filled=False, color="#E5E7EB").encode(
            x=x, y="kWh:Q",
            tooltip=[alt.Tooltip("tanggal:T", title="Hari ini (berjalan)", format="%a %d %b"),
                     alt.Tooltip("kWh:Q", title="kWh sejauh ini", format=",.0f")])
        awal = alt.Chart(pd.DataFrame({"t": [p["tanggal"].min()]})).mark_rule(
            strokeDash=[2, 3], color="#94A3B8").encode(x=alt.X("t:T", title=None))
        st.altair_chart((pita + garis_lain + garis_a + berjalan + garis_p + awal)
                        .properties(height=340), width="stretch")
        st.caption(f"Putih = aktual (6 minggu terakhir) · hijau = prediksi {metode} dengan pita 95% · "
                   f"abu putus-putus = metode lain · lingkaran kosong = hari ini, belum lengkap. "
                   f"Model dilatih dengan data sampai {latih_sampai:%d %b %Y}.")

        # ---------- Tabel harian ----------
        with st.expander("Tabel prediksi harian"):
            t = p.assign(hari=p["tanggal"].dt.dayofweek.map(dict(enumerate(HARI_ID))),
                         biaya=p["kWh"] * TARIF)
            st.dataframe(
                t[["tanggal", "hari", "kWh", "bawah", "atas", "biaya"]], hide_index=True, width="stretch",
                column_config={
                    "tanggal": st.column_config.DateColumn("Tanggal", format="DD MMM YYYY"),
                    "hari": "Hari",
                    "kWh": st.column_config.NumberColumn("Prediksi (kWh)", format="%.0f"),
                    "bawah": st.column_config.NumberColumn("Batas bawah", format="%.0f"),
                    "atas": st.column_config.NumberColumn("Batas atas", format="%.0f"),
                    "biaya": st.column_config.NumberColumn("Biaya (Rp)", format="%.0f"),
                })

        # ---------- Backtest ----------
        st.subheader("Uji akurasi (backtest 14 hari)")
        kiri, kanan = st.columns([3, 2])
        with kiri:
            bt = backtest.assign(metode=backtest["metode"].map(
                lambda m: f"★ {m}" if m == terbaik else m)).sort_values("MAPE_persen")
            st.dataframe(bt, hide_index=True, width="stretch", column_config={
                "metode": "Metode",
                "MAE_kWh": st.column_config.NumberColumn("MAE (kWh)", format="%.1f"),
                "RMSE_kWh": st.column_config.NumberColumn("RMSE (kWh)", format="%.1f"),
                "MAPE_persen": st.column_config.NumberColumn("MAPE (%)", format="%.2f"),
            })
        with kanan:
            st.caption("14 hari terakhir data disembunyikan, model dilatih dari data sebelumnya, lalu "
                       "tebakannya dibandingkan dengan data asli. Metode dengan MAPE terkecil (★) otomatis "
                       "menjadi metode utama di halaman ini.")
        with st.expander("Tentang model"):
            st.markdown(
                "- **SARIMA(1,0,1)(1,1,1)₇**: membaca pola deret kWh harian, termasuk pola mingguan "
                "hari kerja vs akhir pekan. Interval 95% dari model.\n"
                "- **LightGBM**: machine learning dengan fitur hari dalam minggu, penanda akhir pekan, "
                "lag 14/21/28 hari, dan rata-rata 7 hari (lag 14). Interval ≈ ±1,96 × RMSE backtest.\n"
                "- Prediksi dihitung ulang di notebook bila data bertambah; dashboard tidak melatih model.")

# ======================= Tab 2: maintenance =======================
with tab_mt:
    pm, threshold = muat_prediksi_maintenance(), muat_threshold()
    if pm is None or threshold is None:
        st.info("Menunggu file prediksi_maintenance.parquet dan threshold_hi.csv di data/processed.")
    else:
        jm = jadwal_maintenance(kondisi_terkini(), pm, threshold, sekarang, reset_aktif(sekarang))
        rentang = st.slider("Tampilkan unit yang jatuh tempo dalam (hari)", 7, 180, 30, 7)
        dekat = jm[(jm["hari_ke_siaga"] <= rentang) | (jm["hari_ke_kritis"] <= rentang)
                   | jm["level"].isin(["Siaga", "Waspada", "Kritis"])].copy()
        dekat["level"] = dekat["level"].map(IKON) + " " + dekat["level"]

        c1, c2, c3 = st.columns(3)
        c1.metric("Umur sudah lewat batas Kritis", int((jm["hari_ke_kritis"] == 0).sum()))
        c2.metric(f"Masuk Kritis ≤ {rentang} hari", int(jm["hari_ke_kritis"].between(1, rentang).sum()))
        c3.metric(f"Masuk Siaga ≤ {rentang} hari", int(jm["hari_ke_siaga"].between(1, rentang).sum()))

        st.dataframe(
            dekat[["id_unit", "jenis", "lantai", "level", "persen_umur", "jam_nyala_rata_harian",
                   "tgl_siaga", "tgl_kritis", "keterangan"]],
            hide_index=True, width="stretch", column_config={
                "id_unit": "Unit", "jenis": "Jenis", "lantai": "Lantai", "level": "Level sekarang",
                "persen_umur": st.column_config.NumberColumn("% umur", format="%.0f%%"),
                "jam_nyala_rata_harian": st.column_config.NumberColumn("Jam nyala/hari", format="%.1f"),
                "tgl_siaga": st.column_config.DateColumn("Perkiraan Siaga", format="DD MMM YYYY"),
                "tgl_kritis": st.column_config.DateColumn("Perkiraan Kritis", format="DD MMM YYYY"),
                "keterangan": "Keterangan",
            })
        st.caption("Perkiraan dari sisa jam ÷ rata-rata jam nyala 28 hari terakhir (Mas Hasan). Hanya "
                   "berdasarkan jam pakai; lonjakan daya AC dan suhu motor pompa tidak bisa diperkirakan "
                   "dengan cara ini dan ditangkap oleh pemantauan harian serta annunciator.")