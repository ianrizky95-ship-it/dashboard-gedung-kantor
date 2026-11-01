import pandas as pd
import streamlit as st
from data import SISTEM, angka, muat_energi, muat_alarm, waktu_sekarang

sekarang = waktu_sekarang()
st.title("Status Sistem")
st.caption(f"Data per {sekarang:%d %b %Y %H:%M}")

jam_kerja_kini = sekarang.day_of_week < 5 and 7 <= sekarang.hour < 17

def status(kw, ambang):
    if kw < ambang:
        return "⚪ Mati"
    return "🟢 Menyala" if jam_kerja_kini else "🟠 Menyala di luar jam kerja"

# --- Status per lantai dari daya terkini ---
df = muat_energi()
t_kini = df.loc[df["timestamp"] <= sekarang, "timestamp"].max()
kini = df[df["timestamp"] == t_kini].pivot_table(index="lantai", columns="beban", values="kW")
kini.index = "LT" + kini.index.astype(str).str.zfill(2)

tabel = pd.DataFrame({
    "AHU": [status(x, 5) for x in kini["AC"]],
    "Daya AC (kW)": kini["AC"].map(lambda x: angka(x, 1)),
    "Lampu": [status(x, 2) for x in kini["LGT"]],
    "Daya lampu (kW)": kini["LGT"].map(lambda x: angka(x, 1)),
}, index=kini.index).sort_index(ascending=False)

st.subheader("HVAC & pencahayaan per lantai")
st.dataframe(tabel, height=400)

# --- Log alarm ---
st.subheader("Log alarm")
st.info("Kebakaran dan keamanan bersifat **baca-saja**: BMS hanya memantau, "
        "logika keselamatan tetap di panel masing-masing (desain slide 9).")

alarm = muat_alarm()
alarm = alarm[alarm["waktu"] <= sekarang]
f1, f2 = st.columns(2)
pilih_sistem = f1.multiselect("Sistem", SISTEM, default=SISTEM)
pilih_status = f2.multiselect("Status", ["Aktif", "Diakui", "Selesai"], default=["Aktif", "Diakui"])

log = alarm[alarm["sistem"].isin(pilih_sistem) & alarm["status"].isin(pilih_status)]
st.dataframe(log.sort_values("waktu", ascending=False), hide_index=True)