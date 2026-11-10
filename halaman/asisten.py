import pandas as pd
import streamlit as st
from data import TARIF, angka, rp, muat_energi, muat_jadwal, tambah_usulan, ubah_status, waktu_sekarang
from olah import estimasi_tambahan
import asisten_ai as asisten

st.title("Asisten Operator")
st.caption("AI sebagai pendukung keputusan: merangkum kondisi, menyusun prioritas maintenance, "
           "menemukan anomali, dan mengusulkan jadwal. Keputusan tetap di tangan operator.")

sekarang = waktu_sekarang()
s = asisten.status()
if s["mode"] == "AI":
    st.success(f"🤖 AI tersambung · {s['keterangan']}")
else:
    st.info(f"🧰 Mode cadangan · {s['keterangan']}. Tombol di bawah tetap dijawab langsung dari data dashboard.")

st.session_state.setdefault("chat", [])


def proses(teks, kunci=None):
    st.session_state["chat"].append({"role": "user", "content": teks})
    with st.spinner("Asisten sedang menyiapkan jawaban…"):
        if kunci is None and asisten.minta_jadwal(teks):
            h = asisten.usulan(teks)
            if "ditolak" in h:
                isi = f"Permintaan ini tidak bisa dijadikan jadwal: **{h['ditolak']}**"
            else:
                st.session_state["usulan_ai"] = h["usulan"]
                isi = "Usulan jadwalnya saya susun di bawah. Periksa dulu, lalu **Setujui** atau **Tolak**."
        else:
            h = asisten.jawab(teks, kunci)
            isi = h["teks"]
    st.session_state["chat"].append({"role": "assistant", "content": isi, "sumber": h["sumber"]})


# ---------- 1. Tombol pertanyaan cepat ----------
for kol, (kunci, label) in zip(st.columns(3), asisten.TOMBOL.items()):
    if kol.button(label, key=f"preset_{kunci}"):
        proses(asisten.PRESET[kunci], kunci)

teks = st.chat_input('Tanya kondisi gedung, atau minta jadwal (mis. "lantai 7 lembur sampai jam 8 malam")')
if teks:
    proses(teks)

# ---------- 2. Percakapan ----------
for m in st.session_state["chat"]:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("sumber"):
            st.caption(m["sumber"])

# ---------- 3. Kartu usulan jadwal (konfirmasi operator) ----------
u = st.session_state.get("usulan_ai")
if u:
    with st.container(border=True):
        st.markdown("**Usulan jadwal dari asisten**")
        tampil = pd.DataFrame([u]).fillna({"zona": "seluruh lantai"})
        st.dataframe(tampil[["sistem", "lantai", "zona", "mode", "jam_mulai", "jam_selesai"]],
                     hide_index=True, width="stretch",
                     column_config={"sistem": "Sistem", "lantai": "Lantai", "zona": "Zona", "mode": "Mode",
                                    "jam_mulai": "Mulai", "jam_selesai": "Selesai"})
        if u["mode"] in ("lembur", "manual"):
            kwh, biaya = estimasi_tambahan(muat_energi(), u["lantai"], u["jam_mulai"], u["jam_selesai"],
                                           sekarang, TARIF)
            st.caption(f"Perkiraan tambahan energi: {angka(kwh)} kWh ≈ {rp(biaya)}")
        kiri, kanan, _ = st.columns([1, 1, 3])
        setuju = kiri.button("✅ Setujui", type="primary", key="ai_setuju")
        tolak = kanan.button("✖ Tolak", key="ai_tolak")
        if setuju or tolak:
            status = "disetujui" if setuju else "ditolak"
            tambah_usulan(u)
            ubah_status(len(muat_jadwal()) - 1, status)
            st.session_state.pop("usulan_ai")
            st.session_state["chat"].append({
                "role": "assistant", "sumber": "Operator",
                "content": f"Usulan {u['sistem']} lantai {u['lantai']} {u['mode']} "
                           f"{u['jam_mulai']}–{u['jam_selesai']} **{status}** dan tercatat di riwayat jadwal."})
            st.rerun()
        st.caption("Setelah diputuskan, usulan tercatat di halaman Kontrol & Jadwal dengan diusulkan_oleh = AI.")

# ---------- 4. Alat bantu ----------
kiri, kanan = st.columns([4, 1])
with kiri.expander("Data yang dikirim ke AI (konteks)"):
    st.code(asisten.konteks(sekarang), language=None)
if kanan.button("Hapus percakapan"):
    st.session_state["chat"] = []
    st.session_state.pop("usulan_ai", None)
    st.rerun()