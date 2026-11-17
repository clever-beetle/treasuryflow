import os
import re
import subprocess

_BASE_VERSION = "2.8.8"
_BASE_RELEASE_DATE = "2026-11-17"
_BASE_CODENAME = "Perbaikan Navigasi Tab & Sinkronisasi Versi Otomatis"

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

_BASE_RELEASE_HISTORY = [
    {
        "version": "2.8.8",
        "date_id": "17 November 2026",
        "title": "Perbaikan Navigasi Tab Performa Keuangan & Sinkronisasi Versi Otomatis",
        "highlights": [
            "Memperbaiki warna ikon tab pada Performa Keuangan (Analytics, Arus Kas, Kewajiban & Langganan, Portofolio Aset, Target Finansial) agar tidak menyangkut setelah diklik dan berpindah ke tab lain.",
            "Memisahkan pengikatan kelas warna aktif dari elemen ikon SVG sehingga pergantian tab selalu mereset tab sebelumnya kembali ke warna netral.",
            "Menambahkan sistem sinkronisasi versi otomatis agar nomor versi aplikasi dan riwayat pembaruan di Pengaturan selalu terbarui setiap ada pembaruan.",
        ],
    },
    {
        "version": "2.8.7",
        "date_id": "11 November 2026",
        "title": "Penyelarasan Tema & Tampilan Mobile Rutinan Target Finansial",
        "highlights": [
            "Menyelaraskan tampilan kotak Rutinan Menabung dengan tema kartu Target Finansial menggunakan tile netral dan aksen biru yang seragam.",
            "Merapikan tampilan rutinan menabung di layar HP menjadi baris ringkas yang mudah dibaca tanpa memotong angka nominal besar.",
            "Menyeragamkan tombol isi cepat (Harian, Mingguan, Bulanan, dan Kejar Sisa) pada modal Tambah Dana.",
        ],
    },
    {
        "version": "2.8.6",
        "date_id": "9 November 2026",
        "title": "Rutinan Menabung Target Finansial Konsisten",
        "highlights": [
            "Kalkulasi rutinan menabung (per hari, per minggu, dan per bulan) kini dihitung dari nominal target penuh (misal Rp 5.000.000) bukan dari sisa kekurangan.",
            "Nominal rutinan tabungan tetap stabil dan tidak berubah saat dana target bertambah / disetor, menjaga disiplin rencana menabung awal.",
            "Estimasi rutinan menabung kini tampil langsung secara interaktif saat membuat atau mengedit target finansial.",
            "Sisa kekurangan target (Kurang Lagi) tetap ditampilkan jelas dengan estimasi sisa hari rutinan hingga target tercapai.",
        ],
    },
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


def _bump_semver_patch(ver_str: str, step: int = 1) -> str:
    parts = [int(p) if p.isdigit() else 0 for p in str(ver_str).split(".")]
    while len(parts) < 3:
        parts.append(0)
    parts[2] += max(0, int(step))
    return f"{parts[0]}.{parts[1]}.{parts[2]}"


def _clean_commit_subject(subject: str) -> str:
    cleaned = re.sub(
        r"^(?:release\s+v?\d+\.\d+\.\d+\s*[:\-]\s*|[a-zA-Z]+(?:\([^)]+\))?\s*:\s*)",
        "",
        str(subject or "").strip(),
        flags=re.IGNORECASE,
    ).strip()
    return cleaned or str(subject or "Pembaruan Aplikasi").strip()


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


def _resolve_version_state() -> dict:
    """
    Mengembalikan state versi aplikasi. Jika ada commit Git baru setelah
    commit terakhir yang memperbarui version.py, nomor versi dan riwayat
    pembaruan otomatis bertambah sehingga versi aplikasi tidak pernah tertinggal.
    """
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    history = [dict(item, highlights=list(item.get("highlights", []))) for item in _BASE_RELEASE_HISTORY]
    version = _BASE_VERSION
    release_date = _BASE_RELEASE_DATE
    codename = _BASE_CODENAME

    try:
        # Jika version.py sedang dimodifikasi di working tree (belum di-commit),
        # gunakan _BASE_VERSION yang baru saja diedit secara langsung.
        diff_out = subprocess.check_output(
            ["git", "status", "--porcelain", "--", "version.py"],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL,
            timeout=1.5,
        ).decode("utf-8", errors="ignore").strip()

        if not diff_out:
            last_ver_sha = subprocess.check_output(
                ["git", "log", "-n", "1", "--format=%H", "--", "version.py"],
                cwd=repo_dir,
                stderr=subprocess.DEVNULL,
                timeout=1.5,
            ).decode("utf-8", errors="ignore").strip()

            if last_ver_sha:
                new_commits_raw = subprocess.check_output(
                    ["git", "log", "--reverse", "--date=short", "--format=%ad|%s", f"{last_ver_sha}..HEAD"],
                    cwd=repo_dir,
                    stderr=subprocess.DEVNULL,
                    timeout=1.5,
                ).decode("utf-8", errors="ignore").strip()

                if new_commits_raw:
                    for line in new_commits_raw.splitlines():
                        if "|" not in line:
                            continue
                        c_date, c_subj = line.split("|", 1)
                        c_date = c_date.strip()
                        c_title = _clean_commit_subject(c_subj)
                        version = _bump_semver_patch(version, 1)
                        release_date = c_date or release_date
                        codename = c_title[:68]
                        history.insert(
                            0,
                            {
                                "version": version,
                                "date_id": _format_release_date_id(release_date),
                                "title": c_title,
                                "highlights": [c_title if c_title.endswith(".") else f"{c_title}."],
                            },
                        )
    except Exception:
        pass

    return {
        "version": version,
        "release_date": release_date,
        "codename": codename,
        "history": history,
    }


_INITIAL_STATE = _resolve_version_state()
APP_VERSION = _INITIAL_STATE["version"]
RELEASE_DATE = _INITIAL_STATE["release_date"]
RELEASE_CODENAME = _INITIAL_STATE["codename"]
RELEASE_HISTORY = _INITIAL_STATE["history"]
BUILD_SHA = _detect_build_sha()


def get_version_info() -> dict:
    state = _resolve_version_state()
    ver = state["version"]
    r_date = state["release_date"]
    sha = _detect_build_sha()
    return {
        "version": ver,
        "build": sha,
        "release_date": r_date,
        "release_date_id": _format_release_date_id(r_date),
        "codename": state["codename"],
        "display": f"v{ver}",
        "full_display": f"v{ver} ({sha})",
        "history": state["history"],
    }
