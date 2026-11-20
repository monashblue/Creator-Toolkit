# Creator Toolkit

Your Everyday Creative Companion.

Creator Toolkit adalah aplikasi desktop Windows untuk kreator konten. Aplikasi ini memproses berkas secara lokal dan dapat dipakai tanpa internet, kecuali saat mengunduh model AI pertama kali.

Status: pengembangan awal (Milestone M5 ditambah M2 riwayat). Kerangka antarmuka sudah ada (jendela utama, sidebar, dashboard, tema terang dan gelap, pengaturan). QR Code Generator dan Background Remover sudah berfungsi. Image Resizer dan Image Converter masih berupa halaman Segera Hadir.

## Fitur yang sudah tersedia

QR Code Generator:

- 8 jenis QR: URL, teks, WhatsApp, Wi-Fi, email, telepon, kontak vCard, dan lokasi Google Maps
- Validasi input per kolom dengan pesan kesalahan berbahasa Indonesia
- Pratinjau langsung yang diperbarui saat mengetik
- Warna depan dan latar, ukuran, tingkat koreksi kesalahan (L, M, Q, H), dan zona tenang
- Logo di tengah dengan batas ukuran otomatis agar kode tetap terbaca
- Peringatan untuk kontras rendah, warna terbalik, zona tenang kecil, modul terlalu kecil, dan kode terlalu padat
- Ekspor PNG, JPG, SVG (vektor), dan PDF ke folder pilihan Anda, tanpa pernah menimpa berkas yang ada

Background Remover:

- Penghapusan latar belakang dengan model AI lokal (ONNX Runtime CPU), tanpa mengirim gambar ke internet
- Model diunduh hanya setelah Anda menyetujui dialog yang menampilkan nama, ukuran perkiraan, sumber, dan lokasi simpan
- Progres unduhan, unduhan dapat dibatalkan dan dilanjutkan, serta pemeriksaan kelengkapan dan keabsahan model
- Setelah model ada, seluruh pemrosesan berjalan offline
- Hasil PNG selalu memiliki kanal alpha. Latar dapat transparan, warna solid, atau gambar lain
- Pemrosesan banyak gambar dengan progres dan tombol batal, semuanya di worker thread
- Pratinjau sebelum dan sesudah dengan pembatas yang dapat digeser, plus kotak-kotak untuk area transparan
- Gambar asli tidak pernah diubah dan hasil tidak pernah menimpa berkas yang sudah ada

Model dapat ditambah atau diganti lewat berkas catalog.json di folder models (%LOCALAPPDATA%\CreatorToolkit\models). Contoh isi:

    {"models": [{"model_id": "saya", "display_name": "Model Saya", "filename": "saya.onnx",
                 "url": "https://contoh.id/saya.onnx", "input_size": 320, "approx_size_mb": 40,
                 "checksum": "sha256:..."}]}

Hanya model dengan keluaran mask satu kanal gaya U2-Net yang kompatibel. Checksum bersifat opsional, isi hanya dengan nilai yang sudah Anda verifikasi dari sumber resmi.

Mengevaluasi kualitas pada foto Anda sendiri:

    python -m modules.background_remover.cli D:\Foto\Uji
    python -m modules.background_remover.cli D:\Foto\Uji --download

Alat ini membuat folder hasil-evaluasi berisi hasil PNG dan lembar perbandingan.png (asli di kiri, hasil di atas kotak-kotak di kanan). Opsi --download meminta konfirmasi sebelum mengunduh.

Riwayat dan Proyek Terbaru:

- Setiap QR yang disimpan dan setiap gambar yang diproses Background Remover (berhasil maupun gagal) dicatat ke database SQLite lokal
- Halaman Proyek Terbaru menampilkan daftar terbaru dengan waktu, status, dan tombol Buka folder. Berkas atau folder yang sudah dihapus ditandai dengan jelas
- Dashboard menampilkan 5 berkas terakhir
- Hanya jalur berkas, nama alat, status, dan waktu yang disimpan. Isi QR, kata sandi Wi-Fi, dan data gambar tidak pernah disimpan
- Jumlah baris yang ditampilkan mengikuti kunci recent_projects_limit di config.json (bawaan 50). Database memangkas otomatis hingga 2000 catatan terbaru
- Bila database rusak, aplikasi mencadangkannya lalu membuat yang baru. Bila tidak dapat dibuka sama sekali, riwayat dinonaktifkan dan fitur lain tetap berjalan

## Rencana fitur

- Generator QR Code
- Penghapus latar belakang gambar dengan AI lokal
- Pengubah ukuran gambar
- Pengonversi format gambar

Screenshot: akan ditambahkan setelah antarmuka selesai.

## Kebutuhan pengembang

- Windows 10 atau 11 64-bit
- Python 3.12

## Menyiapkan lingkungan pengembangan

Perintah di bawah dijalankan di PowerShell dari folder proyek.

    py -3.12 -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -r requirements.txt

Untuk pengujian dan build, pasang juga dependensi pengembangan:

    pip install -r requirements-dev.txt

Bila PowerShell menolak menjalankan Activate.ps1, jalankan perintah berikut sekali untuk pengguna saat ini:

    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

## Menjalankan aplikasi

    python main.py
    python main.py --version
    python main.py --check

Opsi --check menampilkan daftar dependensi yang terpasang.

## Menjalankan pengujian

    python -m unittest discover -s tests -t .

Bila pytest terpasang:

    python -m pytest

Pengujian Background Remover memakai model ONNX sintetis buatan sendiri dan server HTTP lokal, jadi tidak membutuhkan internet maupun model asli.
Pengujian QR memakai decoder OpenCV (opencv-python-headless) dari requirements-dev.txt. Tanpa OpenCV, pengujian decode dilewati.
Pengujian decode PDF memakai pdftoppm (Poppler) dan dilewati bila tidak tersedia.

## Lokasi data pengguna

- Konfigurasi, model, cache, dan log: %LOCALAPPDATA%\CreatorToolkit
- Riwayat: %APPDATA%\CreatorToolkit\history.db

Untuk memindahkan seluruh data ke folder lain (misalnya saat pengujian), atur variabel lingkungan CREATORTOOLKIT_HOME.

## Batasan saat ini

- Image Resizer dan Image Converter belum berfungsi.
- Kualitas Background Remover pada foto nyata belum diuji. Pengujian otomatis memakai model ONNX sintetis dan gambar sintetis, sehingga hanya membuktikan alur, bukan mutu segmentasi.
- Model U2-Net dan turunannya bekerja pada resolusi kecil (320 piksel pada katalog bawaan). Rambut halus, struktur tipis, objek transparan atau berkilau, dan objek yang warnanya mirip latar umumnya menjadi titik lemah model semacam ini. Evaluasi dengan foto Anda sendiri sebelum dipakai untuk pekerjaan penting.
- Pembatalan pemrosesan berlaku setelah inferensi gambar yang sedang berjalan selesai, karena inferensi tidak dapat diputus di tengah jalan.
- Pratinjau Background Remover dimuat di worker thread. Gambar yang sangat besar membuat pratinjau tampil beberapa detik kemudian.
- Gambar 48 megapiksel (batas maksimum) memakai sekitar 480 MB (transparan) sampai 620 MB (warna solid) memori puncak pada pengukuran di sandbox. Gambar 12 megapiksel memakai sekitar seperempatnya.
- Alamat unduhan dan ukuran model pada katalog berasal dari rilis rembg dan belum diverifikasi dari jaringan. Checksum belum diisi karena belum diverifikasi dari sumber resmi.
- Pratinjau dan penyimpanan QR berjalan di worker thread. Pratinjau dirender maksimal 640 piksel, sedangkan ekspor memakai ukuran penuh.
- Ekspor PDF berisi gambar QR 300 dpi, bukan vektor. Gunakan SVG bila butuh vektor.
- Tingkat keterbacaan di dunia nyata (kamera ponsel, cahaya, cetakan) tetap perlu Anda uji sendiri.
- Efek hover sudah ada, tetapi animasi transisi belum diterapkan.
- Ikon digambar sendiri dengan gaya garis dan belum memakai pustaka ikon resmi.
- Cara build executable dan installer akan didokumentasikan pada Milestone M9.

- Pemeriksaan keberadaan berkas pada daftar riwayat berjalan di thread utama. Folder jaringan yang terputus dapat membuat daftar muncul lebih lambat.

## Status audit

Ringkasan temuan, perbaikan, dan masalah yang belum selesai ada di docs/audit.md. Aplikasi belum siap rilis.

## Lisensi

Kode sumber aplikasi berlisensi MIT, lihat berkas LICENSE. Dependensi pihak ketiga dan model AI memiliki lisensi masing-masing. Daftarnya akan didokumentasikan pada Milestone M9.
