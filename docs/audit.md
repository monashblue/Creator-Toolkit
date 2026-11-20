# Laporan audit Creator Toolkit

Audit dilakukan pada kode setelah M5. Tidak ada fitur baru yang ditambahkan.

## Metode

- Pemeriksaan statis berbasis AST: struktur terhadap spesifikasi, impor tak terpakai dan tak terselesaikan, atribut privat tanpa definisi, tombol tanpa handler, kode mati, dependensi, dan pola berisiko.
- Pengukuran waktu dan memori pada QR ukuran besar dan gambar 12 dan 48 megapiksel.
- Fuzzing sekitar 750 masukan ekstrem pada validator, mesin QR, pembacaan gambar, dan nama berkas.
- Perhitungan kontras WCAG untuk pasangan warna kedua tema.
- Uji alur halaman memakai Qt tiruan, mesin asli, server HTTP lokal, dan runner sinkron.

## Hal yang BELUM dapat dibuktikan di lingkungan audit

- Aplikasi belum pernah dijalankan dengan PySide6 asli. Tampilan, QSS, QThread, dialog, drag and drop, dan lukisan CompareView belum teruji.
- Pustaka qrcode asli dan model AI asli belum dipakai. Pengujian memakai tiruan API qrcode berbasis OpenCV dan model ONNX sintetis.
- Pemindaian dengan kamera ponsel belum dilakukan.
- Pengujian belum dijalankan di Windows.

## Masalah yang belum selesai

Kritis untuk rilis:

1. Image Resizer dan Image Converter belum ada (M6). Dua dari empat alat yang dijanjikan belum berfungsi.
2. Seluruh antarmuka (termasuk halaman Proyek Terbaru yang baru) belum diverifikasi dengan Qt asli.
3. Alamat dan ukuran model belum diverifikasi, dan checksum belum diisi.
4. Installer, build PyInstaller, ikon aplikasi, dokumen lisensi pihak ketiga, panduan instalasi, dan panduan pengguna belum ada (M9).

Tidak kritis:

- Kunci konfigurasi language, notifications, dan window disimpan tetapi belum dipakai antarmuka. recent_projects_limit kini dipakai oleh halaman Proyek Terbaru.
- Transisi animasi pada hover belum ada (QSS tidak mendukungnya).
- Warna RGB di bawah area transparan tetap berasal dari gambar asli, sehingga tepi dapat berbayang tipis pada latar baru. Belum ada pembersihan warna tepi.
- Gaya QSS pada QSpinBox belum terlihat dan dapat memengaruhi tombol naik dan turun.
- pyinstaller di requirements-dev.txt belum dipakai sampai M9. pytest opsional karena pengujian memakai unittest.

## Pembaruan setelah audit: M2 (riwayat)

- core/database.py dibuat, dengan 27 pengujian: skema sesuai spesifikasi, urutan terbaru dahulu, filter, zona waktu, karakter Unicode dan percobaan injeksi SQL, validasi, batch atomik, pemangkasan, 8 thread menulis bersamaan tanpa kehilangan baris, berkas rusak dipulihkan, lokasi tidak dapat dibuka, skema versi lebih baru ditolak, dan operasi setelah ditutup.
- Pencatatan dari QR dan Background Remover, halaman Proyek Terbaru, dan daftar di Dashboard. Diuji dengan Qt tiruan dan database asli. Belum dijalankan dengan Qt asli.
- Masalah kritis nomor 1 pada daftar awal (database belum ada) sudah selesai. Daftar di atas sudah disesuaikan.
