"""Pengolahan data dashboard: alpha filter dan insight otomatis.

Semua fungsi menerima DataFrame dan mengembalikan hasil, tanpa membaca file
sendiri. Jadi bisa diuji di notebook dan dipakai di Streamlit dengan cara sama.
"""
import pandas as pd
import numpy as np

JAM_MULAI, JAM_SELESAI = 7, 17          # jam kerja Senin-Jumat 07.00-17.00
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


# ---------- format angka gaya Indonesia ----------
def _angka(x, d=0):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _persen(x, d=0):
    return _angka(x * 100, d) + "%"

def _waktu(ts):
    return f"{HARI[ts.day_of_week]} {ts.day:02d} {BULAN[ts.month - 1]} pukul {ts:%H.%M}"


# ---------- 1. alpha filter ----------
def alpha_filter(seri, alpha=0.3):
    """y_t = alpha * x_t + (1 - alpha) * y_(t-1), dengan y_0 = x_0."""
    return seri.ewm(alpha=alpha, adjust=False).mean()


# ---------- 2. jam kerja ----------
def jam_kerja(waktu):
    """True bila waktu jatuh di Senin-Jumat, JAM_MULAI <= jam < JAM_SELESAI."""
    return ((waktu.dt.day_of_week < 5)
            & (waktu.dt.hour >= JAM_MULAI) & (waktu.dt.hour < JAM_SELESAI))


# ---------- 3. penyebab level sebuah unit ----------
def _penyebab(u):
    alasan = []
    if pd.notna(u["rasio_daya"]) and u["rasio_daya"] >= 1.4:
        alasan.append(f"daya {_angka(u['rasio_daya'], 2)}x batas normal")
    if pd.notna(u["suhu_motor_maks_C"]) and u["suhu_motor_maks_C"] >= 75:
        alasan.append(f"suhu motor {_angka(u['suhu_motor_maks_C'], 1)} °C")
    if u["persen_umur"] >= 70:
        alasan.append(f"{_angka(u['persen_umur'])}% dari umur/interval servis")
    return "; ".join(alasan) if alasan else "health index rendah"


# ---------- 4. insight otomatis ----------
def insight(energi, kondisi, unit, sekarang, tarif, hari=7, k_hari_ini=None):
    """Kembalikan daftar kalimat insight dari data sampai `sekarang`."""
    kalimat = []
    awal = sekarang - pd.Timedelta(days=hari)

    e = energi[(energi["timestamp"] > awal) & (energi["timestamp"] <= sekarang)].copy()
    e["kWh"] = e["kW"] * 0.25
    total = e["kWh"].sum()

    # a. lantai paling boros
    per_lantai = e.groupby("lantai")["kWh"].sum().sort_values(ascending=False)
    kalimat.append(
        f"Lantai {per_lantai.index[0]} paling boros: {_angka(per_lantai.iloc[0])} kWh, "
        f"atau {_persen(per_lantai.iloc[0] / total)} energi gedung dalam {hari} hari terakhir.")

    # b. luar jam kerja
    luar = ~jam_kerja(e["timestamp"])
    kwh_luar = e.loc[luar, "kWh"].sum()
    porsi_luar_lt = e[luar].groupby("lantai")["kWh"].sum() / per_lantai
    kalimat.append(
        f"{_persen(kwh_luar / total)} energi terpakai di luar jam kerja "
        f"(≈ Rp {_angka(kwh_luar * tarif)}). Porsi tertinggi di Lantai {porsi_luar_lt.idxmax()}: "
        f"{_persen(porsi_luar_lt.max())} konsumsinya terjadi di luar jam kerja.")

    # c. beban puncak
    beban = e.groupby("timestamp")["kW"].sum()
    kalimat.append(
        f"Beban puncak {hari} hari terakhir {_angka(beban.max())} kW, "
        f"terjadi {_waktu(beban.idxmax())}.")

    # d. tren dibanding periode sebelumnya
    sebelum = energi[(energi["timestamp"] > awal - pd.Timedelta(days=hari))
                     & (energi["timestamp"] <= awal)]
    ubah = total / (sebelum["kW"].sum() * 0.25) - 1
    kalimat.append(
        f"Total konsumsi {_angka(total)} kWh, {'naik' if ubah > 0 else 'turun'} "
        f"{_persen(abs(ubah), 1)} dibanding {hari} hari sebelumnya.")

    # e. AC tidak aktif
    ac = unit[unit["jenis"] == "AC"]
    n_tidak = int((ac["status_unit"] == "Tidak aktif").sum())
    kalimat.append(
        f"{n_tidak} dari {len(ac)} unit AC hampir tidak pernah menyala sepanjang data "
        f"(< 88 jam setahun). Perlu dicek: unit cadangan atau rusak?")

    # f. health index hari ini
    if k_hari_ini is not None:                 # sudah termasuk reset dan skenario
        k = k_hari_ini
    else:
        tgl = kondisi.loc[kondisi["tanggal"] <= sekarang, "tanggal"].max()
        k = kondisi[kondisi["tanggal"] == tgl]
    jml = k["level"].value_counts()
    n_kritis, n_waspada, n_siaga = (int(jml.get(x, 0)) for x in ["Kritis", "Waspada", "Siaga"])
    perhatian = k[k["level"].isin(["Kritis", "Waspada"])].sort_values("health_index")
    if perhatian.empty:
        kalimat.append(f"Tidak ada unit Waspada atau Kritis hari ini; {n_siaga} unit berstatus Siaga.")
    else:
        u = perhatian.iloc[0]
        kalimat.append(
            f"Hari ini {n_kritis} unit Kritis, {n_waspada} Waspada, dan {n_siaga} Siaga. "
            f"Paling mendesak: {u['id_unit']} ({_penyebab(u)}).")

    # g. suhu motor pompa
    for _, u in k[k["suhu_motor_maks_C"] >= 75].iterrows():
        kalimat.append(
            f"Suhu motor {u['id_unit']} mencapai {_angka(u['suhu_motor_maks_C'], 1)} °C hari ini "
            f"(batas Siaga 75 °C). Periksa pompa sebelum suhunya mencapai batas Waspada 80 °C.")

    return kalimat
# ---------- 5. health index untuk dashboard ----------
LEVEL_URUT = {"Kritis": 0, "Waspada": 1, "Siaga": 2, "Normal": 3, "Tidak aktif": 4}
IKON = {"Kritis": "🔴", "Waspada": "🟠", "Siaga": "🟡", "Normal": "🟢", "Tidak aktif": "⚪"}


def level_dari_hi(hi):
    """HI <= 5 Kritis, <= 15 Waspada, <= 30 Siaga, di atasnya Normal."""
    return np.select([hi <= 5, hi <= 15, hi <= 30], ["Kritis", "Waspada", "Siaga"], "Normal")

SKENARIO = ["Suhu motor Pompa 2 kritis", "AC lantai 4 boros"]


def _terapkan_skenario(k, skenario):
    """Ubah kondisi hari ini sesuai skenario mode demo. File data tidak berubah."""
    for nama in skenario or []:
        if nama == "Suhu motor Pompa 2 kritis":
            k.loc[k["id_unit"] == "GK_LT00_POMPA_02", "suhu_motor_maks_C"] = 92.0
        elif nama == "AC lantai 4 boros":
            ac = k[(k["jenis"] == "AC") & (k["lantai"] == 4) & (k["status_unit"] == "Aktif")]
            if len(ac):
                k.loc[ac["jam_nyala"].idxmax(), "rasio_daya"] = 2.3
    return k


def kondisi_hari_ini(kondisi, unit, sekarang, reset=None, skenario=None):
    """Kondisi tiap unit pada tanggal terakhir <= sekarang, setelah reset dan skenario diterapkan.

    reset = {id_unit: waktu_reset}; skenario = daftar nama dari SKENARIO.
    """
    tgl = kondisi.loc[kondisi["tanggal"] <= sekarang, "tanggal"].max()
    k = kondisi[kondisi["tanggal"] == tgl].merge(
        unit[["id_unit", "jenis", "lantai", "zona", "umur_nominal_jam", "status_unit"]], on="id_unit")

    for uid, waktu in (reset or {}).items():
        sejak = ((kondisi["id_unit"] == uid)
                 & (kondisi["tanggal"] > pd.Timestamp(waktu).normalize())
                 & (kondisi["tanggal"] <= tgl))
        jam = kondisi.loc[sejak, "jam_nyala"].sum()
        b = k["id_unit"] == uid
        k.loc[b, "jam_kumulatif"] = round(jam, 1)
        k.loc[b, "persen_umur"] = (jam / k.loc[b, "umur_nominal_jam"] * 100).round(1)

    k = _terapkan_skenario(k, skenario)

    # Aturan sama dengan notebook 04_cubems: indikator membatasi health index
    r, s = k["rasio_daya"], k["suhu_motor_maks_C"]
    plafon = np.minimum(np.select([r >= 2.0, r >= 1.6, r >= 1.4], [5, 15, 30], 100),
                        np.select([s >= 90, s >= 80, s >= 75], [5, 15, 30], 100))
    k["health_index"] = np.minimum((100 - k["persen_umur"]).clip(0, 100), plafon).round(1)
    k["level"] = level_dari_hi(k["health_index"])
    k.loc[k["status_unit"] == "Tidak aktif", "level"] = "Tidak aktif"

    perlu = k["level"].isin(["Kritis", "Waspada", "Siaga"])
    k["penyebab"] = "-"
    if perlu.any():
        k.loc[perlu, "penyebab"] = k[perlu].apply(_penyebab, axis=1)
    return k

def ringkas_aset(k):
    """Satu baris per zona/lantai: level = unit terburuk, diurutkan dari yang paling mendesak."""
    k = k.assign(urut=k["level"].map(LEVEL_URUT)).sort_values(["urut", "health_index"])
    r = (k.groupby("id_aset", sort=False)
           .agg(jenis=("jenis", "first"), lantai=("lantai", "first"), zona=("zona", "first"),
                level=("level", "first"), hi_terendah=("health_index", "min"),
                unit=("id_unit", "count")))
    r["perlu_perhatian"] = (k[k["urut"] <= 2].groupby("id_aset").size()
                            .reindex(r.index).fillna(0).astype(int))
    r["urut"] = r["level"].map(LEVEL_URUT)
    return r.reset_index().sort_values(["urut", "hi_terendah", "lantai"]).drop(columns="urut")

# ---------- 6. alarm untuk annunciator ----------
PRIORITAS = {"Kritis": 1, "Waspada": 2, "Siaga": 3}


def alarm_hari_ini(k):
    """Alarm dari level health index, urut dari yang paling mendesak."""
    a = k[k["level"].isin(PRIORITAS)].copy()
    a["prioritas"] = a["level"].map(PRIORITAS)
    a["kunci"] = a["id_unit"] + "|" + a["level"]       # alarm yang naik level dianggap baru
    return a.sort_values(["prioritas", "health_index"])[
        ["prioritas", "level", "jenis", "lantai", "id_unit", "penyebab", "health_index", "kunci"]]
# ---------- 7. kontrol berbasis jadwal ----------
def _menit(hhmm):
    jam, menit = str(hhmm).split(":")
    return int(jam) * 60 + int(menit)


def _dalam(mulai, selesai, waktu):
    t = waktu.hour * 60 + waktu.minute
    return _menit(mulai) <= t < _menit(selesai)


def status_kontrol(jadwal, sekarang):
    """Status ON/OFF HVAC dan pencahayaan tiap lantai dari jadwal yang sudah disetujui."""
    ok = jadwal[jadwal["status"] == "disetujui"]
    rutin = ok[ok["mode"] == "jadwal"].sort_values("waktu").groupby(["sistem", "lantai"]).last()
    khusus = ok[(ok["mode"] != "jadwal") & (ok["waktu"].dt.normalize() == sekarang.normalize())]
    hari_kerja = sekarang.day_of_week < 5

    baris = []
    for (sistem, lantai), r in rutin.iterrows():
        nyala = hari_kerja and _dalam(r["jam_mulai"], r["jam_selesai"], sekarang)
        x = khusus[(khusus["sistem"] == sistem) & (khusus["lantai"] == lantai)]
        if any(_dalam(a, b, sekarang) for a, b in zip(x["jam_mulai"], x["jam_selesai"])):
            nyala = True
        baris.append({
            "lantai": lantai, "sistem": sistem, "nyala": nyala,
            "rutin": f"{r['jam_mulai']}–{r['jam_selesai']}",
            "khusus": ", ".join(f"{m} {a}–{b}" for m, a, b in
                                zip(x["mode"], x["jam_mulai"], x["jam_selesai"])) or "-",
        })
    return pd.DataFrame(baris)


def estimasi_tambahan(energi, lantai, mulai, selesai, sekarang, tarif, hari=7):
    """Perkiraan tambahan kWh dan Rupiah kalau lantai menyala seperti jam kerja di luar jadwal."""
    e = energi[(energi["lantai"] == lantai)
               & (energi["timestamp"] > sekarang - pd.Timedelta(days=hari))
               & (energi["timestamp"] <= sekarang)]
    beban = e.groupby("timestamp")["kW"].sum()
    kerja = jam_kerja(beban.index.to_series()).to_numpy()
    selisih = max(beban[kerja].mean() - beban[~kerja].mean(), 0)
    durasi = max(_menit(selesai) - _menit(mulai), 0) / 60
    kwh = selisih * durasi
    return round(kwh), round(kwh * tarif)
# ================= Prediktor (file dari Mas Hasan) =================
HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


def _id(x, d=0):
    """Format angka gaya Indonesia: 34.244 dan 8,7."""
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def metode_terbaik(backtest):
    """Metode dengan MAPE backtest terkecil."""
    return backtest.loc[backtest["MAPE_persen"].idxmin(), "metode"]


def kwh_harian(energi, sekarang, hari=42):
    """kWh harian gedung sampai sekarang. Kolom 'lengkap' = False untuk hari yang sedang berjalan."""
    e = energi[(energi["timestamp"] <= sekarang)
               & (energi["timestamp"] >= sekarang.normalize() - pd.Timedelta(days=hari))]
    h = (e.assign(tanggal=e["timestamp"].dt.normalize())
          .groupby("tanggal")["kW"].sum().mul(0.25).rename("kWh").reset_index())
    h["lengkap"] = h["tanggal"] < sekarang.normalize()
    return h


def kalimat_prediksi(prediksi, backtest, sekarang, tarif):
    """Satu kalimat insight dari prediksi metode terbaik; None kalau file belum ada."""
    if prediksi is None or backtest is None:
        return None
    m = metode_terbaik(backtest)
    p = prediksi[(prediksi["metode"] == m) & (prediksi["tanggal"] >= sekarang.normalize())]
    if p.empty:
        return None
    b = p.iloc[0]
    mape = backtest.set_index("metode").loc[m, "MAPE_persen"]
    tujuh = p.head(7)["kWh"].sum()
    return (f"Prediksi {m}: konsumsi {HARI_ID[b['tanggal'].dayofweek]} {b['tanggal']:%d/%m} sekitar "
            f"**{_id(b['kWh'])} kWh** (rentang {_id(b['bawah'])}–{_id(b['atas'])}); "
            f"7 hari ke depan ≈ {_id(tujuh)} kWh atau Rp {_id(tujuh * tarif / 1e6, 1)} juta "
            f"(MAPE backtest {_id(mape, 1)}%).")


def jadwal_maintenance(k, pm, threshold, sekarang, reset=None):
    """Perkiraan tanggal tiap unit aktif masuk Siaga/Kritis.

    Tanggal diambil dari file Mas Hasan. Unit yang di-reset di dashboard dihitung ulang
    dengan rumus yang sama: sisa jam ÷ rata-rata jam nyala per hari (dari file).
    Unit yang sudah melewati batas diberi tanggal hari ini.
    """
    hari = sekarang.normalize()
    m = k[k["status_unit"] == "Aktif"].merge(
        pm[["id_unit", "jam_nyala_rata_harian", "tgl_perkiraan_siaga", "tgl_perkiraan_kritis"]],
        on="id_unit", how="left")
    batas = threshold.set_index("jenis")
    rata = m["jam_nyala_rata_harian"].where(m["jam_nyala_rata_harian"] > 0)
    di_reset = m["id_unit"].isin(list(reset or {}))

    for lv in ["siaga", "kritis"]:
        persen = m["jenis"].map(batas[f"{lv}_persen"])
        sisa_jam = persen / 100 * m["umur_nominal_jam"] - m["jam_kumulatif"]
        hitung = hari + pd.to_timedelta(np.ceil(sisa_jam / rata), unit="D")
        tgl = m[f"tgl_perkiraan_{lv}"].where(~di_reset, hitung)
        tgl = tgl.where(sisa_jam > 0, hari).clip(lower=hari)
        m[f"tgl_{lv}"] = tgl
        m[f"hari_ke_{lv}"] = (tgl - hari).dt.days

    m["keterangan"] = np.select(
        [m["hari_ke_kritis"] == 0, m["hari_ke_siaga"] == 0,
         m["level"].isin(["Siaga", "Waspada", "Kritis"])],
        ["Umur sudah melewati batas Kritis", "Umur sudah Siaga, menuju Kritis",
         "Level naik karena indikator (daya/suhu), bukan umur"], "")
    m.loc[di_reset, "keterangan"] = "Dihitung ulang setelah reset"
    return m.sort_values(["tgl_kritis", "tgl_siaga"])