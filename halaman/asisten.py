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
            hasil = asisten.usulan_banyak(teks)          # AC + lampu sekaligus -> 2 usulan
            usul = [h["usulan"] for h in hasil if "usulan" in h]
            alasan = [h["ditolak"] for h in hasil if "ditolak" in h]
            if usul:
                st.session_state["usulan_ai"] = usul
            bagian = []
            if usul:
                bagian.append(f"{len(usul)} usulan jadwal saya susun di bawah. "
                              "Periksa dulu, lalu **Setujui** atau **Tolak**.")
            bagian += [f"Permintaan ini tidak bisa dijadikan jadwal: **{a}**" for a in alasan]
            isi = "\n\n".join(bagian)
            h = hasil[0]
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
daftar = st.session_state.get("usulan_ai") or []
if isinstance(daftar, dict):                             # sisa format lama (satu usulan)
    daftar = [daftar]
for i, u in enumerate(daftar):
    judul = "Usulan jadwal dari asisten" + (f" ({i + 1}/{len(daftar)})" if len(daftar) > 1 else "")
    with st.container(border=True):
        st.markdown(f"**{judul}**")
        tampil = pd.DataFrame([u]).fillna({"zona": "seluruh lantai"})
        st.dataframe(tampil[["sistem", "lantai", "zona", "mode", "jam_mulai", "jam_selesai"]],
                     hide_index=True, width="stretch",
                     column_config={"sistem": "Sistem", "lantai": "Lantai", "zona": "Zona", "mode": "Mode",
                                    "jam_mulai": "Mulai", "jam_selesai": "Selesai"})
        if u["mode"] in ("lembur", "manual"):
            beban, nama = ("AC", "AC") if u["sistem"] == "HVAC" else ("LGT", "lampu")   # hanya beban sistem ini
            e = muat_energi()
            kwh, biaya = estimasi_tambahan(e[e["beban"] == beban], u["lantai"], u["jam_mulai"], u["jam_selesai"],
                                           sekarang, TARIF)
            st.caption(f"Perkiraan tambahan energi {nama}: {angka(kwh)} kWh ≈ {rp(biaya)}")
        kiri, kanan, _ = st.columns([1, 1, 3])
        setuju = kiri.button("✅ Setujui", type="primary", key=f"ai_setuju_{i}")
        tolak = kanan.button("✖ Tolak", key=f"ai_tolak_{i}")
        if setuju or tolak:
            status = "disetujui" if setuju else "ditolak"
            tambah_usulan(u)
            ubah_status(len(muat_jadwal()) - 1, status)
            sisa = daftar[:i] + daftar[i + 1:]
            if sisa:
                st.session_state["usulan_ai"] = sisa
            else:
                st.session_state.pop("usulan_ai", None)
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
    st.session_state.pop("jadwal_terakhir", None)
    st.rerun()