import pandas as pd
import streamlit as st
from data import TARIF, muat_energi, muat_jadwal, tambah_usulan, ubah_status, waktu_sekarang
from olah import status_kontrol, estimasi_tambahan

st.title("Kontrol & Jadwal")
st.caption("Kontrol dilakukan lewat jadwal per lantai. Setiap perubahan diajukan dulu, "
           "lalu disetujui operator. Kebakaran dan keamanan hanya bisa dipantau.")

if "pesan_kontrol" in st.session_state:
    st.success(st.session_state.pop("pesan_kontrol"))

sekarang = waktu_sekarang()
jadwal = muat_jadwal()

# ---------- 1. Status saat ini ----------
st.subheader(f"Status saat ini · {sekarang:%d %b %Y, %H.%M}")
s = status_kontrol(jadwal, sekarang)
s["status"] = s["nyala"].map({True: "🟢 ON", False: "⚫ OFF"})
tabel = s.pivot(index="lantai", columns="sistem", values="status").reset_index()
khusus = s[s["khusus"] != "-"][["lantai", "sistem", "khusus"]]

kiri, kanan = st.columns([3, 2])
kiri.dataframe(tabel, hide_index=True, width="stretch", column_config={"lantai": "Lantai"})
with kanan:
    st.caption("Jadwal rutin berlaku Senin–Jumat. Lembur dan manual berlaku hari ini saja.")
    if len(khusus):
        st.markdown("**Jadwal khusus hari ini**")
        st.dataframe(khusus, hide_index=True, width="stretch")
    else:
        st.caption("Tidak ada lembur atau kontrol manual hari ini.")
    st.markdown("**Sistem baca-saja**")
    st.toggle("Kebakaran (fire alarm)", value=True, disabled=True, key="ro_kebakaran",
              help="Dikendalikan panel kebakaran sendiri, tidak bisa diubah dari dashboard.")
    st.toggle("Keamanan (CCTV & akses)", value=True, disabled=True, key="ro_keamanan",
              help="Hanya pemantauan, sesuai desain BAS.")

# ---------- 2. Ajukan perubahan ----------
st.subheader("Ajukan perubahan")
with st.form("form_usulan", clear_on_submit=True):
    a, b, c = st.columns(3)
    sistem = a.selectbox("Sistem", ["HVAC", "Pencahayaan"])
    lantai = b.selectbox("Lantai", list(range(1, 11)))
    mode = c.selectbox("Mode", ["lembur", "manual", "jadwal"],
                       help="lembur/manual: hari ini saja · jadwal: mengganti jadwal rutin")
    d, e = st.columns(2)
    mulai = d.time_input("Mulai", value=pd.Timestamp("17:00").time(), step=1800)
    selesai = e.time_input("Selesai", value=pd.Timestamp("20:00").time(), step=1800)
    kirim = st.form_submit_button("Ajukan", type="primary")

if kirim:
    jm, js = mulai.strftime("%H:%M"), selesai.strftime("%H:%M")
    if js <= jm:
        st.warning("Jam selesai harus setelah jam mulai.")
    else:
        tambah_usulan({"sistem": sistem, "lantai": lantai, "zona": None, "mode": mode,
                       "jam_mulai": jm, "jam_selesai": js, "status": "usulan",
                       "diusulkan_oleh": "operator", "waktu": sekarang})
        st.session_state["pesan_kontrol"] = (f"Usulan {sistem} lantai {lantai} ({mode} {jm}–{js}) "
                                             "menunggu persetujuan.")
        st.rerun()

# ---------- 3. Antrean persetujuan ----------
st.subheader("Menunggu persetujuan")
antre = jadwal[jadwal["status"] == "usulan"]
if antre.empty:
    st.caption("Tidak ada usulan.")
energi = muat_energi()
for i, r in antre.iterrows():
    with st.container(border=True):
        info, ok, tolak = st.columns([6, 1, 1])
        teks = (f"**{r['sistem']} lantai {r['lantai']}** · {r['mode']} "
                f"{r['jam_mulai']}–{r['jam_selesai']} · diusulkan oleh {r['diusulkan_oleh']}")
        if r["mode"] in ("lembur", "manual"):
            kwh, rp = estimasi_tambahan(energi, r["lantai"], r["jam_mulai"], r["jam_selesai"],
                                        sekarang, TARIF)
            teks += f"  \nPerkiraan tambahan energi: **{kwh} kWh** (≈ Rp {rp:,})".replace(",", ".")
        info.markdown(teks)
        if ok.button("Setujui", key=f"ok_{i}", type="primary"):
            ubah_status(i, "disetujui")
            st.session_state["pesan_kontrol"] = "Usulan disetujui dan langsung berlaku."
            st.rerun()
        if tolak.button("Tolak", key=f"tolak_{i}"):
            ubah_status(i, "ditolak")
            st.session_state["pesan_kontrol"] = "Usulan ditolak."
            st.rerun()

# ---------- 4. Riwayat ----------
st.subheader("Riwayat jadwal")
riwayat = jadwal[jadwal["diusulkan_oleh"] != "sistem"].sort_values("waktu", ascending=False)
if riwayat.empty:
    st.caption("Belum ada perubahan jadwal.")
else:
    st.dataframe(riwayat, hide_index=True, width="stretch")