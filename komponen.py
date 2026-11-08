"""Komponen tampilan yang dipakai beberapa halaman."""
import streamlit as st
from olah import alarm_hari_ini, IKON

WARNA = {"Kritis": "#DC2626", "Waspada": "#EA580C", "Siaga": "#CA8A04", "Normal": "#15803D"}
JENIS = [("AC", "AC"), ("LAMPU", "Lampu"), ("CCTV", "CCTV"), ("POMPA", "Pompa")]
CSS = "<style>@keyframes kedip {50% {opacity: .35;}} .kedip {animation: kedip 1s infinite;}</style>"


def annunciator(k, maks=6):
    """Panel alarm ringkas: ubin per jenis alat + daftar alarm teratas."""
    alarm = alarm_hari_ini(k)
    diakui = st.session_state.setdefault("diakui", set())
    baru = alarm[~alarm["kunci"].isin(diakui)]

    st.markdown(CSS, unsafe_allow_html=True)
    with st.container(border=True):
        judul, tombol = st.columns([4, 1])
        judul.subheader("🔔 Annunciator: kondisi peralatan")
        if tombol.button("Akui semua", disabled=baru.empty, key="akui_semua", width="stretch"):
            diakui.update(alarm["kunci"])
            st.rerun()

        # Ubin per jenis alat, warnanya mengikuti alarm terburuk
        for kol, (kode, nama) in zip(st.columns(4), JENIS):
            a = alarm[alarm["jenis"] == kode]
            level = a["level"].iloc[0] if len(a) else "Normal"
            n_baru = int((~a["kunci"].isin(diakui)).sum())
            if len(a):
                teks = f"{len(a)} alarm" + (f" · {n_baru} baru" if n_baru else "")
            else:
                teks = "Normal"
            kedip = "kedip" if (level == "Kritis" and n_baru) else ""
            kol.markdown(
                f"<div class='{kedip}' style='background:{WARNA[level]};color:white;"
                f"padding:10px 14px;border-radius:8px;'><b>{nama}</b><br>{teks}</div>",
                unsafe_allow_html=True)

        # Daftar alarm teratas
        if alarm.empty:
            st.caption("Tidak ada alarm aktif.")
        else:
            baris = []
            for r in alarm.head(maks).itertuples():
                tanda = " **BARU**" if r.kunci not in diakui else ""
                baris.append(f"- {IKON[r.level]}{tanda} `{r.id_unit}`: {r.penyebab}")
            st.markdown("\n".join(baris))
            if len(alarm) > maks:
                st.caption(f"+{len(alarm) - maks} alarm lain. Detailnya di halaman Health Index.")