import os
import subprocess

APP_VERSION = "2.8.5"
RELEASE_DATE = "2026-11-09"
RELEASE_CODENAME = "Audit Stabilitas Fitur Baru"

_BULAN_ID = (
    "",
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)

RELEASE_HISTORY = [
    {
        "version": "2.8.5",
        "date_id": "9 November 2026",
        "title": "Perbaikan Stabilitas Fitur Terbaru",
        "highlights": [
            "Nominal berdesimal (misal Rp 12.500,5) tidak lagi berubah menjadi 10x/100x lipat saat mengedit transaksi.",
            "Kategori dengan tanda petik (misal Jum'at Berkah) kini bisa diedit dan dihapus tanpa error.",
            "Tombol Passkey / Biometrik dikunci saat proses verifikasi agar tidak gagal karena ketukan ganda.",
            "Perhitungan Kurang Lagi pada Target Finansial lebih presisi serta pesan validasi yang lebih jelas.",
            "Ikon periode, tombol kelola kartu di HP, dan grafik saat berpindah tab Performa Keuangan kini tampil rapi.",
        ],
    },
    {
        "version": "2.8.4",
        "date_id": "9 November 2026",
        "title": "Penyegaran Performa Keuangan & Tips Target Tabungan",
        "highlights": [
            "Merapikan tata letak Analytics, Arus Kas, dan navigasi tab Performa Keuangan di layar HP maupun desktop serta memperbaiki kedipan awal tab Arus Kas.",
            "Menampilkan sisa kekurangan dana (Kurang Lagi) secara jelas pada setiap target finansial serta ringkasan seluruh target.",
            "Menghadirkan kalkulasi Tips Menabung otomatis (Per Hari, Per Minggu, Per Bulan) sesuai nominal kekurangan dan tanggal tenggat dengan pengisian cepat ke Tambah Dana.",
        ],
    },
    {
        "version": "2.8.3",
        "date_id": "8 November 2026",
        "title": "Tab Khusus Versi Aplikasi",
        "highlights": [
            "Menambahkan menu khusus Versi Aplikasi di Pengaturan untuk melihat info versi dan riwayat pembaruan.",
            "Menyederhanakan tampilan informasi versi agar lebih bersih, ringkas, dan bebas dari kode teknis.",
            "Menampilkan logo resmi Treasury Flow dengan tata letak kartu informasi yang lebih rapi.",
        ],
    },
    {
        "version": "2.8.2",
        "date_id": "8 November 2026",
        "title": "Kerapian Kategori Transaksi",
        "highlights": [
            "Menghilangkan duplikasi kategori 'Lainnya' pada menu Pemasukan dan Pengeluaran.",
            "Mengurutkan daftar kategori secara alfabetis (A-Z) dengan pilihan 'Lainnya' selalu di posisi paling bawah.",
            "Memisahkan tampilan Kategori Bawaan Sistem dan Kategori Kustom di halaman Pengaturan.",
        ],
    },
    {
        "version": "2.8.1",
        "date_id": "8 November 2026",
        "title": "Stabilitas Dropdown & Kalender Finansial",
        "highlights": [
            "Memperbaiki dropdown kategori pengeluaran agar tidak menutup sendiri pada layar HP.",
            "Menjaga popup modal tetap terbuka saat memilih opsi dropdown di dalamnya.",
            "Merapikan validasi Split Bill saat berganti jenis transaksi serta tautan agenda di Kalender Finansial.",
        ],
    },
    {
        "version": "2.8.0",
        "date_id": "8 November 2026",
        "title": "Kecepatan Aplikasi & Keamanan Biometrik",
        "highlights": [
            "Mempercepat respons muat halaman dan transaksi melalui optimasi koneksi database.",
            "Memperbaiki penyimpanan dan login Biometrik / Passkey agar persisten di server.",
            "Memisahkan kategori Pemasukan dan Pengeluaran serta menyelaraskan tema terang dan gelap.",
        ],
    },
]


def _format_release_date_id(iso_date: str) -> str:
    try:
        y, m, d = [int(p) for p in str(iso_date)[:10].split("-")]
        if 1 <= m <= 12:
            return f"{d} {_BULAN_ID[m]} {y}"
    except Exception:
        pass
    return iso_date


def _detect_build_sha() -> str:
    env_sha = (
        os.environ.get("VERCEL_GIT_COMMIT_SHA")
        or os.environ.get("GIT_COMMIT_SHA")
        or os.environ.get("RENDER_GIT_COMMIT")
        or ""
    ).strip()
    if env_sha:
        return env_sha[:7]
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stderr=subprocess.DEVNULL,
            timeout=1.5,
        )
        sha = out.decode("utf-8", errors="ignore").strip()
        if sha:
            return sha[:7]
    except Exception:
        pass
    return "stable"


BUILD_SHA = _detect_build_sha()


def get_version_info() -> dict:
    return {
        "version": APP_VERSION,
        "build": BUILD_SHA,
        "release_date": RELEASE_DATE,
        "release_date_id": _format_release_date_id(RELEASE_DATE),
        "codename": RELEASE_CODENAME,
        "display": f"v{APP_VERSION}",
        "full_display": f"v{APP_VERSION} ({BUILD_SHA})",
        "history": RELEASE_HISTORY,
    }
