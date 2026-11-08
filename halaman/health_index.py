import streamlit as st
import pandas as pd
from data import (muat_kondisi, muat_unit, muat_log, catat_log, waktu_sekarang, kondisi_terkini,
                  reset_aktif, muat_prediksi_maintenance, muat_threshold)
from olah import ringkas_aset, IKON, LEVEL_URUT, jadwal_maintenance

st.title("Health Index Peralatan")

if "reset" not in st.session_state:
    st.session_state["reset"] = {}
if "pesan" in st.session_state:
    st.success(st.session_state.pop("pesan"))

sekarang = waktu_sekarang()
kondisi, unit, log = muat_kondisi(), muat_unit(), muat_log()

k = kondisi_terkini()                # file + reset + skenario mode demo
st.caption(f"Kondisi per {k['tanggal'].max():%d %b %Y} · {len(k)} unit · "
           "level zona/lantai = unit terburuk di dalamnya")

# ---------- 1. Jumlah unit per level ----------
jumlah = k["level"].value_counts()
for kol, lv in zip(st.columns(5), LEVEL_URUT):
    kol.metric(f"{IKON[lv]} {lv}", int(jumlah.get(lv, 0)))

# ---------- 2. Tabel per zona / lantai ----------
st.subheader("Per zona / lantai")
jenis = st.multiselect("Jenis peralatan", ["AC", "LAMPU", "CCTV", "POMPA"],
                       default=["AC", "LAMPU", "CCTV", "POMPA"])
aset = ringkas_aset(k[k["jenis"].isin(jenis)])
aset["status"] = aset["level"].map(IKON) + " " + aset["level"]
aset["zona"] = aset["zona"].fillna("-")
tabel = aset[["status", "id_aset", "jenis", "lantai", "zona", "perlu_perhatian", "unit", "hi_terendah"]]

st.caption("Klik satu baris untuk melihat unit di dalamnya. Paling mendesak di atas.")
pilih = st.dataframe(
    tabel, hide_index=True, width="stretch", height=320,
    on_select="rerun", selection_mode="single-row",
    column_config={
        "status": "Level", "id_aset": "Aset", "jenis": "Jenis", "lantai": "Lantai",
        "zona": "Zona", "perlu_perhatian": "Perlu perhatian", "unit": "Jumlah unit",
        "hi_terendah": st.column_config.ProgressColumn(
            "HI terendah", min_value=0, max_value=100, format="%.0f"),
    })

if not pilih.selection.rows:
    st.info("Pilih satu baris di tabel untuk melihat daftar unit.")
    st.stop()
id_aset = tabel.iloc[pilih.selection.rows[0]]["id_aset"]

# ---------- 3. Daftar unit di aset terpilih ----------
st.subheader(f"Unit di {id_aset}")
u = (k[k["id_aset"] == id_aset]
     .assign(urut=lambda d: d["level"].map(LEVEL_URUT))
     .sort_values(["urut", "health_index"]))
pm, threshold = muat_prediksi_maintenance(), muat_threshold()
if pm is not None and threshold is not None:
    jm = jadwal_maintenance(k, pm, threshold, sekarang, reset_aktif(sekarang))
    u = u.merge(jm[["id_unit", "tgl_siaga", "tgl_kritis"]], on="id_unit", how="left")
else:
    u["tgl_siaga"] = u["tgl_kritis"] = pd.NaT
u["status"] = u["level"].map(IKON) + " " + u["level"]
st.dataframe(
    u[["status", "id_unit", "health_index", "persen_umur", "jam_kumulatif",
       "rasio_daya", "suhu_motor_maks_C", "tgl_siaga", "tgl_kritis", "penyebab"]],
    hide_index=True, width="stretch",
    column_config={
        "status": "Level", "id_unit": "Unit",
        "health_index": st.column_config.ProgressColumn(
            "Health index", min_value=0, max_value=100, format="%.0f"),
        "persen_umur": st.column_config.NumberColumn("% umur", format="%.0f%%"),
        "jam_kumulatif": st.column_config.NumberColumn("Jam sejak servis", format="%.0f"),
        "rasio_daya": st.column_config.NumberColumn("Rasio daya", format="%.2f"),
        "suhu_motor_maks_C": st.column_config.NumberColumn("Suhu motor (°C)", format="%.1f"),
        "tgl_siaga": st.column_config.DateColumn("Perkiraan Siaga", format="DD MMM YYYY"),
        "tgl_kritis": st.column_config.DateColumn("Perkiraan Kritis", format="DD MMM YYYY"),
        "penyebab": "Penyebab",
    })

# ---------- 4. Tren dan reset per unit ----------
uid = st.selectbox("Pilih unit", u["id_unit"])
kiri, kanan = st.columns([3, 2])
with kiri:
    tren = (kondisi[(kondisi["id_unit"] == uid) & (kondisi["tanggal"] <= sekarang)]
            .tail(60).set_index("tanggal")["health_index"])
    st.caption("Health index 60 hari terakhir (data harian, sebelum reset di dashboard)")
    st.line_chart(tren, y_label="Health index", color="#10B981")
with kanan:
    with st.form("form_reset", clear_on_submit=True):
        st.markdown(f"**Catat pemeliharaan {uid}**")
        catatan = st.text_input("Catatan", placeholder="mis. servis rutin, ganti filter")
        yakin = st.checkbox("Unit ini sudah dipelihara atau diganti")
        kirim = st.form_submit_button("Reset counter jam nyala", type="primary")
    if kirim:
        if not yakin:
            st.warning("Centang konfirmasi dulu sebelum reset.")
        else:
            st.session_state["reset"][uid] = sekarang
            catat_log(uid, catatan)
            st.session_state["pesan"] = f"Counter {uid} direset. Health index dihitung ulang."
            st.rerun()

# ---------- 5. Riwayat pemeliharaan ----------
st.subheader("Riwayat pemeliharaan")
riwayat = (log[log["id_unit"].isin(u["id_unit"]) & (log["waktu"] <= sekarang)]
           .sort_values("waktu", ascending=False).head(10))
if len(riwayat):
    st.dataframe(riwayat, hide_index=True, width="stretch")
else:
    st.caption("Belum ada riwayat pemeliharaan untuk aset ini.")