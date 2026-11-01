import streamlit as st

st.set_page_config(page_title="Dashboard Gedung Kantor", layout="wide")

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
halaman.run()