# Changelog — Treasury Flow

Seluruh perubahan penting, perbaikan bug, peningkatan keamanan, dan pembaruan antarmuka pada **Treasury Flow** didokumentasikan pada berkas ini mengikuti standar [Semantic Versioning](https://semver.org/lang/id/) (`MAJOR.MINOR.PATCH`).

---

## [2.8.3] — 2026-11-08 — *Versi Aplikasi & Penyempurnaan Pengaturan*

### Peningkatan Antarmuka & Kebersihan Informasi
- **Tab Khusus `Versi Aplikasi` (`settings.html` & `version.py`)**:
  - Memindahkan informasi versi dari `Integrasi & Data` ke tab khusus **`Versi Aplikasi`** di menu **Pengaturan**, lengkap dengan bagian **Riwayat Pembaruan** berurutan (`v2.8.3`, `v2.8.2`, `v2.8.1`, `v2.8.0`) dalam bahasa yang mudah dibaca.
  - Menampilkan logo resmi **Treasury Flow**, versi aktif, serta tanggal pembaruan tanpa detail teknis internal (`ID Deployment`, badge `Stabil`, maupun tombol `Detail Rilis` JSON mentah) sehingga tampilan jauh lebih bersih dan aman dari pengungkapan info teknis build.
- **Validasi Tab Pengaturan (`routes/settings.py`)**: Menambahkan whitelist parameter `?tab=` untuk memastikan perpindahan tab berjalan aman dan konsisten.

---

## [2.8.2] — 2026-11-08 — *Category Hygiene & UI Polish*

### Perbaikan & Peningkatan Antarmuka
- **Pembersihan Duplikasi Kategori & Pengurutan Rapi (`get_user_categories`)**:
  - Menghilangkan duplikasi kategori bawaan (termasuk munculnya dua opsi `Lainnya (Pemasukan)` / `Lainnya (Pengeluaran)` maupun `Lainnya`) yang berasal dari baris warisan tabel `user_categories` pada halaman **Catat Transaksi**, **Edit Transaksi**, **Riwayat Transaksi**, **Dashboard**, dan **Pengaturan**.
  - Menata urutan kategori secara alfabetis `A–Z` dengan kategori kustom tampil rapi sebelum opsi **`Lainnya (Pemasukan)` / `Lainnya (Pengeluaran)`** yang selalu ditempatkan di posisi paling akhir daftar.
  - Mencegah penambahan kategori kustom bernama `Lainnya` atau `Transfer` serta memisahkan tampilan **Kategori Bawaan Sistem** dan **Kategori Kustom** pada halaman Pengaturan.
- **Penyegaran Tampilan Badge Versi di Pengaturan (`settings.html` & `version.py`)**:
  - Mengganti badge mentah `v2.8.x (commit_sha)` di bagian atas Pengaturan menjadi pil status modern **`v2.8.2 • Rilis Terbaru`** yang dapat diklik langsung menuju kartu **Tentang Aplikasi** di tab **Integrasi & Data**, lengkap dengan format tanggal Indonesia dan ID Deployment.

---

## [2.8.1] — 2026-11-08 — *Post-Release Deep Audit & Dropdown Stability Hotfix*

### Perbaikan Bug & Stabilitas Antarmuka
- **Perbaikan Dropdown Kategori Pengeluaran Menutup Sendiri (`#shadcn-select-portal`)**:
  - Mengganti listener `window.resize` yang sebelumnya memanggil `closePortal()` menjadi `positionPortal()` (termasuk dukungan `visualViewport`), sehingga munculnya keyboard virtual maupun perubahan tinggi bar alamat browser di HP **tidak lagi menutup dropdown secara tiba-tiba**.
  - Menonaktifkan auto-focus input pencarian pada perangkat layar sentuh/mobile, menaikkan ambang kotak pencarian ke `>= 12` opsi, serta menggunakan ukuran font `16px` (`text-base sm:text-xs`) di mobile untuk mencegah auto-zoom pada iOS Safari & Android Chrome.
  - Menambahkan `stopPropagation()` pada `#shadcn-select-portal` dan sinkronisasi event `close-modal` agar pemilihan dropdown di dalam modal Alpine (`@click.outside`) tidak pernah menutup modal secara tidak sengaja.
- **Validasi Form Kustom untuk Dropdown Wajib (`required`)**: Menambahkan penanganan event `invalid` pada seluruh `<select required>` bertema Shadcn agar menampilkan highlight merah, notifikasi toast Bahasa Indonesia yang jelas, dan membuka pilihan dropdown secara otomatis.
- **Perbaikan Validasi Tersembunyi Split Bill (`add_transaction.html`)**: Menghapus atribut `required` otomatis pada kolom Split Bill saat pengguna berpindah tab ke `Pemasukan` atau `Transfer`, serta mengunci mode tampilan saat mengedit transaksi pasangan `Transfer`.
- **Perbaikan Tautan Aksi Kalender Finansial (`/api/calendar_events`)**: Mengarahkan tombol aksi Utang & Cicilan Rutin pada modal detail Kalender Finansial langsung ke tab `?tab=liabilities` di Performa Keuangan.
- **Keamanan Koneksi Pool PostgreSQL (`init_db` & `handle_500`)**: Memastikan `autocommit = False` selalu dipulihkan setelah bootstrap database dan menutup koneksi error-logger pada blok `finally`.

---

## [2.8.0] — 2026-11-08 — *Precision & Speed*

### Performa & Infrastruktur Database
- **Connection Pooling PostgreSQL (`ThreadedConnectionPool`)**: Menggantikan pembuatan koneksi TLS baru di setiap request dengan pool koneksi aktif untuk memangkas latensi klik dan perpindahan halaman secara drastis.
- **Sinkronisasi Replica Non-Blocking**: Replikasi penulisan ke `REPLICA_DATABASE_URL` kini dijalankan di background thread agar respons ke pengguna tidak tertahan dua kali round-trip jaringan.
- **Smart Self-Healing Saldo (`recalculate_account_balances`)**: Hanya melakukan `UPDATE` dan `COMMIT` pada tabel `accounts` apabila terdapat selisih saldo aktual (`> 0.009`), menghilangkan penulisan disk/WAL yang tidak perlu pada request `GET`.
- **Optimasi Query & Indeks Komposit**: Menggabungkan N+1 query anggaran bulanan di Dashboard, menggabungkan 4 query agregasi rentang waktu di Performa Keuangan, menyatukan query notifikasi navbar, serta menambahkan indeks komposit pada `transactions`, `accounts`, dan `notifications`.

### Biometrik / Passkey (WebAuthn)
- **Perbaikan Korupsi `BYTEA` PostgreSQL**: Memperbaiki pembacaan `public_key` pada PostgreSQL (`memoryview` hex vs raw CBOR bytes) yang sebelumnya menyebabkan verifikasi Passkey gagal saat login.
- **Status Passkey Persisten dari Database Server**: Status aktif dan jumlah Passkey terdaftar di halaman Pengaturan kini dibaca langsung dari database (`webauthn_credentials`), tidak lagi bergantung pada `localStorage` browser yang mudah hilang, dilengkapi fitur hapus/reset Passkey.
- **Dukungan Discoverable Passkey & Domain Normalization**: Menambahkan `ResidentKeyRequirement.PREFERRED`, `exclude_credentials`, serta normalisasi RP ID agar login biometrik berjalan mulus lintas perangkat dan subdomain.

### Antarmuka & Pengalaman Pengguna (Shadcn UI)
- **Tab Segmented Catat Transaksi**: Merombak toggle `Pemasukan | Pengeluaran | Transfer` menjadi grid 3 kolom proporsional yang responsif di layar HP maupun desktop tanpa saling bertabrakan.
- **Pemisahan Ketat Kategori Pemasukan & Pengeluaran**: Mengganti penyembunyian `<optgroup>` bawaan browser yang tidak efektif dengan pemuatan opsi dinamis terpisah sehingga kategori Pemasukan dan Pengeluaran tidak pernah tercampur.
- **Global Shadcn Custom Select Dropdown**: Mengubah seluruh komponen `<select>` (Kategori Akun, Institusi, Dompet, Akun Tujuan, Filter Periode, Kategori, Jatuh Tempo) menjadi komponen Popover bertema Shadcn yang mendukung Light & Dark Mode, pencarian cepat, dan navigasi keyboard.
- **Modernisasi Kalender Finansial**: Merapikan tata letak `/calendar` (toolbar responsif, tampilan Bulan & Daftar Agenda, modal detail jadwal interaktif, format Rupiah bertitik, serta jadwal jatuh tempo Kartu Kredit/Paylater) dan tampilan kalender pada `/transactions?view=calendar` (header hari Bahasa Indonesia `Sen–Min` dan tampilan sel mobile yang rapi).
- **Sistem Versioning & Auditabilitas**: Menambahkan penanda versi terpusat (`version.py`), endpoint audit `/api/version`, badge versi pada menu navigasi & Pengaturan, serta lokalisasi Bahasa Indonesia penuh pada halaman Pengaturan.

---

## [2.7.0] — 2026-11-08 — *Cross-Module Balance Sync & Auth Hardening*
- Sinkronisasi saldo menyeluruh lintas Dashboard, Performa Keuangan, Kelola Akun, dan AI Assistant (`(account_type = 'asset' OR account_type IS NULL)`).
- Sinkronisasi dua arah otomatis antara edit/hapus transaksi dengan Target Tabungan (`financial_goals`) dan Cicilan Utang/Piutang (`debts_receivables`).
- Perbaikan Auto-Sync cicilan ke akun liabilitas (Kartu Kredit/Paylater) menggunakan pasangan transaksi Transfer yang terhubung serta anti-dobel tagihan.
- Pembersihan kredensial SMTP hardcoded dari kode sumber dan validasi kadaluarsa token reset password berbasis WIB (`wib_now()`).

---

## [2.6.0] — 2026-11-08 — *Security, Timezone & Theme Parity*
- Perlindungan ekspor CSV & Excel dari *Spreadsheet Formula Injection* (`spreadsheet_safe`).
- Penyeragaman zona waktu server ke WIB (`UTC+7`) melalui helper `wib_now()`.
- Perbaikan fallback penghapusan kategori kustom (`Lainnya (Pemasukan)` / `Lainnya (Pengeluaran)`).
- Perbaikan 16 isu tema Dark Mode (anti-FOUC), scope modal Alpine.js, Driver.js onboarding, dan halaman 404.
