# Changelog

Format mengikuti Keep a Changelog dan penomoran versi Semantic Versioning.

## [Belum dirilis]

### Ditambahkan
- M2 (riwayat): core.database (SQLite, tabel history dengan kolom id, tool_name, input_file, output_file, status, created_at, versi skema, pemangkasan, pemulihan berkas rusak, aman antar thread). Pencatatan otomatis dari QR Code Generator dan Background Remover. Halaman Proyek Terbaru yang berfungsi (menggantikan halaman Segera Hadir), daftar berkas terakhir di Dashboard, deteksi berkas dan folder yang hilang, dan tombol Buka folder.
- M4: mesin Background Remover (ONNX Runtime CPU langsung), katalog dan pengelola model, pengunduh model dengan persetujuan eksplisit, progres, resume, dan pemeriksaan keabsahan, pemrosesan batch dengan pembatalan, latar transparan, warna, atau gambar, serta alat evaluasi baris perintah. Fondasi bersama: core.tasks, core.worker (QThread), core.file_manager, dan core.model_manager.
- M5: halaman Background Remover dengan unduhan model berkonfirmasi, drag and drop, daftar gambar, pratinjau sebelum dan sesudah yang dapat digeser, kotak-kotak transparansi, progres, dan tombol batal. Komponen bersama baru: DropZone, ProgressPanel, CompareView, dan ColorPicker (dipindah dari modul QR).
- M3: QR Code Generator dengan 8 jenis QR, validasi input, pratinjau langsung, pengaturan warna, ukuran, koreksi kesalahan, dan zona tenang, logo di tengah dengan batas keamanan, ekspor PNG, JPG, SVG, dan PDF, pemilih folder keluaran, dan penamaan berkas yang tidak menimpa. Mesin QR (payloads, validator, processor, exporter) terpisah dari antarmuka dan diuji dengan decoder QR nyata.
- M1: jendela utama 1200 x 800 (minimum 900 x 650), sidebar 230 px dengan 8 menu yang berfungsi, dashboard dengan pencarian alat, kartu akses cepat, kartu kategori, dan keadaan kosong, tema terang dan gelap, halaman Pengaturan (tema, folder keluaran, folder log) dan Tentang.
- M0: struktur proyek, konstanta dan jalur data aplikasi, ConfigManager (JSON), sistem logging, titik masuk main.py, pemeriksaan dependensi, dan pengujian dasar.

- M1: halaman Segera Hadir yang informatif untuk empat alat dan Proyek Terbaru, berisi daftar fitur yang direncanakan dan tombol kembali yang berfungsi.

### Diubah
- Dependensi: rembg dihapus dari requirements.txt dan numpy ditambahkan. Inferensi memakai ONNX Runtime langsung.

### Diperbaiki (audit)
- Pemeriksaan dependensi (--check) masih meminta rembg. Kini memeriksa numpy.
- Dialog persetujuan unduhan model tidak lagi bergantung pada identitas objek Qt, yang dapat membuat unduhan tidak pernah dimulai.
- Pratinjau dan penyimpanan QR dipindah ke worker thread. Pratinjau dirender maksimal 640 piksel (turun dari 307 MB menjadi 52 MB pada ukuran 4096 piksel) dan matriks QR di-cache. Hasil pratinjau tidak dapat diekspor.
- Pratinjau Background Remover dipindah ke worker thread (sebelumnya 0,5 sampai 1,8 detik membekukan GUI untuk PNG besar) dan tidak mengulang tanpa henti bila gagal.
- Memori Background Remover: salinan gambar yang tidak perlu dihapus. Puncak pada 48 megapiksel turun dari 613 MB menjadi 484 MB (transparan) dan dari 803 MB menjadi 619 MB (warna solid).
- Kontras tema: teks aksen pada tema gelap (2,8 sampai 3,9 banding 1) dan teks redup pada tema terang (4,3 banding 1) dinaikkan ke minimal 4,5 banding 1. Ditambahkan pengujian kontras dan konsistensi palet.
- Keadaan nonaktif untuk radio, kotak centang, dan DropZone. Tampilan perbandingan mengikuti pergantian tema.
- Kegagalan startup (folder data tidak dapat ditulis) kini menampilkan pesan jelas, bukan traceback.
- Folder keluaran bawaan di Pengaturan kini benar-benar berlaku untuk semua modul.
- Pengunduh: pengalihan ke skema yang tidak diizinkan diblokir, dan kesalahan SSL saat membaca data mendapat pesan yang benar.
- Menunggu thread saat aplikasi ditutup diperpanjang menjadi 30 detik. Kode mati dan impor tak terpakai dihapus.

### Diperbaiki
- M0: ConfigManager kini memvalidasi tipe nilai dan menghapus berkas sementara saat penyimpanan gagal.
