import streamlit as st

st.set_page_config(page_title="PLN Trunojoyo Green Building", page_icon="🌿", layout="wide")

halaman = st.navigation({
    "Pemantauan": [
        st.Page("halaman/ringkasan.py", title="Ringkasan Gedung", icon="🏢", default=True),
        st.Page("halaman/energi_lantai.py", title="Energi per Lantai", icon="⚡"),
        st.Page("halaman/status_sistem.py", title="Status Sistem", icon="🚦"),
    ],
    "Analitik": [
        st.Page("halaman/prediksi.py", title="Prediksi", icon="📈"),
        st.Page("halaman/simulasi.py", title="Simulasi Retrofit", icon="💡"),
    ],
    "Asisten": [
        st.Page("halaman/asisten.py", title="Asisten Operator", icon="🤖"),
    ],
})

# --- Header identitas (tampil di semua halaman) ---
kiri, kanan = st.columns([5, 2], vertical_alignment="center")
with kiri:
    st.markdown("#### 🌿 PLN Trunojoyo Green Building")
    st.caption("Gedung kantor 10 lantai + basement · ±11.000 m² · "
               "Lapisan Enterprise: data BMS dibaca via OPC UA")
with kanan:
    st.badge("Studi kasus tugas kuliah · data simulasi", icon=":material/science:", color="green")
st.divider()

# --- Footer sidebar ---
st.sidebar.caption("Mata kuliah Gedung dan Rumah Cerdas · S2 ITS")
st.sidebar.caption("Energi: data simulasi")

halaman.run()
