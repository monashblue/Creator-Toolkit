# Arsitektur Creator Toolkit

Dokumen ini diperbarui pada setiap milestone.

## Lapisan

- app: inisialisasi aplikasi, konstanta, dan diagnostik
- core: layanan bersama (konfigurasi, logging, kemudian database, file manager, worker)
- ui: jendela utama, sidebar, dashboard, komponen, dan tema (mulai M1)
- modules: fitur independen (qr_generator, background_remover, image_resizer, image_converter)

## Status M0

- app.constants: identitas aplikasi dan jalur data pengguna
- app.application: bootstrap direktori, logging, dan konfigurasi
- app.diagnostics: pemeriksaan dependensi
- core.config_manager: konfigurasi JSON dengan penulisan atomik dan pemulihan berkas rusak
- core.logger: log berputar ke folder logs

## Status M1

- ui.registry: daftar halaman, deskripsi alat, kata kunci pencarian, dan kategori (tanpa Qt)
- ui.icon_data dan ui.icons: ikon SVG garis, dirender menjadi QPixmap dan QIcon
- ui.theme: ThemeManager menerapkan palet Qt dan stylesheet, lalu memancarkan sinyal theme_changed
- ui.styles: light.qss dan dark.qss dengan struktur identik, hanya warna yang berbeda
- ui.sidebar, ui.dashboard, ui.pages, ui.main_window: navigasi, halaman, dan jendela utama
- ui.components: AppButton (primary, secondary, ghost), Card, ToolCard, EmptyState, CardGrid
- Aturan: halaman baru didaftarkan di ui.registry, lalu dipasang di MainWindow._build_pages

## Status M3: modul QR Code Generator

Mesin (tanpa Qt, dapat diuji sendiri):

- modules.qr_generator.payloads: definisi 8 jenis QR, kolom isian (FieldSpec), dan pembuat teks payload
- modules.qr_generator.validator: validasi dan normalisasi per jenis, menghasilkan kesalahan per kolom dan peringatan
- modules.qr_generator.processor: QRSettings, pembuatan matriks (pustaka qrcode), render Pillow, logo, kontras, peringatan keterbacaan
- modules.qr_generator.exporter: ekspor PNG, JPG, SVG, PDF, nama berkas aman, penamaan unik tanpa menimpa

Antarmuka:

- modules.qr_generator.interface: QRGeneratorPage. Form dibentuk dinamis dari FieldSpec, sehingga menambah jenis QR cukup mengubah payloads dan validator.

Alur data: isian dan pengaturan, validator.validate, payloads.build_payload, processor.create_matrix, processor.render_image, lalu exporter.export_qr.

Keputusan desain:

- Zona tenang digambar sendiri (border=0 pada pustaka qrcode) agar ukuran modul bulat dan tepi tajam.
- Ukuran hasil dibulatkan ke kelipatan modul. Ukuran sebenarnya ditampilkan di pratinjau.
- Logo dibatasi 15% (M), 20% (Q), dan 25% (H) dari lebar area modul, tidak diizinkan pada koreksi L, dan diposisikan tepat di tengah kisi modul.

## Status M4 dan M5: modul Background Remover

Fondasi bersama (core), tanpa Qt kecuali worker.py:

- core.tasks: CancelToken, TaskContext, OperationCancelled, dan UserMessageError (dasar semua error ramah pengguna)
- core.worker: TaskWorker dan TaskRunner (QThread), meneruskan progres, item, dan hasil lewat sinyal ke thread utama
- core.file_manager: validasi gambar (ekstensi, format asli, batas piksel), nama berkas aman, penamaan unik tanpa menimpa
- core.model_manager: pengunduh generik berbasis urllib. Wajib consent=True, hanya HTTPS secara bawaan, berkas .part dengan resume lewat header Range, verifikasi checksum opsional, penggantian atomik

Mesin modul (modules.background_remover):

- model_manager: katalog model (bawaan ditambah catalog.json pengguna), status model, dan unduhan
- processor: SegmentationSession (ONNX Runtime CPU), pembacaan gambar, remove_background, latar pengganti, pratinjau, dan process_batch
- errors: hierarki error khusus modul
- cli: alat evaluasi pada foto sendiri

Antarmuka: interface.py (BackgroundRemoverPage) memakai dua TaskRunner, satu untuk unduhan dan satu untuk pemrosesan.

Keputusan desain:

- rembg tidak dipakai sebagai runtime. rembg mengunduh model sendiri bila berkas tidak cocok dengan checksum internalnya, sehingga larangan unduhan tanpa persetujuan tidak dapat dijamin. rembg juga membawa banyak dependensi berat. Aplikasi memakai ONNX Runtime langsung dengan pra dan pascapemrosesan yang sama seperti keluarga U2-Net, sehingga berkas model yang sama dapat dipakai.
- Model dibaca dari folder data aplikasi. Setelah ada, tidak ada kode yang membuka koneksi jaringan saat memuat atau memproses (diuji dengan memblokir socket).
- Satu sesi model disimpan di cache dengan kunci nama, ukuran, dan waktu modifikasi berkas.
- Keluaran selalu PNG RGBA. Mode warna atau gambar menghasilkan alpha 255.
- Output tidak pernah menimpa: nama dicadangkan lewat pembuatan berkas eksklusif, dan berkas setengah jadi dihapus saat gagal atau dibatalkan.

## Model threading (hasil audit)

Prinsip: tidak ada pekerjaan yang dapat memakan lebih dari sekitar 50 ms di thread GUI.

- QR: dua TaskRunner. Pratinjau memakai pola "yang terbaru menang": bila masukan berubah saat worker berjalan, hasil lama dibuang dan worker dijalankan ulang. Penyimpanan membuat QR ukuran penuh dan mengekspornya di worker terpisah.
- Background Remover: tiga TaskRunner (unduhan model, pemrosesan batch, pemuatan pratinjau). Objek Qt (QPixmap) selalu dibuat di thread utama dari gambar Pillow yang dimuat worker.
- Worker hanya menerima salinan data sederhana (dict, jalur, pengaturan). Tidak ada widget yang disentuh dari worker.
- Pembatalan bersifat kooperatif dan efektif di antara tahap. Satu inferensi ONNX tidak dapat diputus.
- Folder keluaran: tiap modul mengingat folder terakhir yang dipakai. Mengubah folder bawaan di Pengaturan menghapus ingatan itu sehingga semua modul mengikuti folder yang baru.

## Status M2: riwayat

- core.database: HistoryDatabase (satu koneksi sqlite3 dengan RLock, check_same_thread=False). Skema versi 1 disimpan di PRAGMA user_version. Semua query berparameter. Kesalahan dibungkus HistoryError dengan pesan Indonesia. Berkas rusak dicadangkan lalu dibuat ulang, sedangkan skema dari versi yang lebih baru ditolak tanpa dianggap rusak.
- AppContext.history bernilai None bila database tidak dapat dibuka. Semua pemakai harus menangani None.
- ui.recent_model: format waktu Indonesia, pemendekan nama, dan describe() yang menentukan status baris (Berhasil, Gagal diproses, Berkas tidak ditemukan) dan apakah folder dapat dibuka. Tanpa Qt sehingga diuji penuh.
- ui.components.recent_list dan ui.pages.RecentProjectsPage: tampilan daftar.
- Pencatatan terpusat di MainWindow: halaman alat hanya memancarkan sinyal (QR: exported dengan jalur, Background Remover: processed dengan daftar dict input, output, status). Halaman alat tidak mengetahui database.
- Isi QR, kata sandi Wi-Fi, dan data gambar tidak pernah disimpan. Entri QR hanya mencatat jalur keluaran.
