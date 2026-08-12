# Kinginul Enc-Dec File

![Banner](assets/banner.png)

Multi-layer file encryption and compression tool berbasis Python. Bikin file atau folder lu aman banget pakai proteksi tingkat tinggi 🔐

## 📌 Preview & Demo

![Screenshot Contoh](screenshot/contoh.png)

🎥 **Demo Video:** [Lihat Video Demo (tes.mp4)](screenshot/tes.mp4)

---

## 🚀 Tentang Project Ini

Kinginul Enc-Dec File bukan tool enkripsi ecek-ecek. Sistem ini membungkus file ke dalam 10 lapis file ZIP yang masing-masing dienkripsi pakai password acak 64 karakter. Semua informasi password per layer disimpan aman di satu file kunci khusus berekstensi `.kedf`.

> ⚠️ **PENTING:** Tanpa file `.kedf` dan Master Password yang benar, file target **gabisa ditembus mau 1 abad pun**! Keamanannya bener-bener absolut.

---

## ⚡ Keuntungan Pake Tool Ini

- 🛡️ **Keamanan Berlapis (10 Layer)**: Nembus 1 lapis ZIP AES-256 aja pusing, apalagi 10 lapis berturut-turut.
- 🔒 **Anti Brute-Force**: Master password dilindungi pakai PBKDF2HMAC dengan 600.000 iterasi. Bikin proses tebak password super lambat dan mustahil buat hacker.
- 🔑 **Format File Kunci Kustom (.kedf)**: Menggunakan magic bytes `KEDF` buat mastiin file kunci valid dan ga gampang dipalsukan.
- 💻 **Tampilan Interaktif**: Interface terminal (CLI) yang bersih + animasi loading cool.

---

## 🔄 Alur Kerja (Cara Kerja)

Proses enkripsi berjalan dengan alur yang lumayan panjang tapi super aman:

1. **Input File Target**: Lu masukin lokasi file atau folder yang mau dikunci.
2. **Proses Looping 10 Lapis**:
   - Program generate password random 64 karakter.
   - File target dikompres jadi ZIP dan dikunci (AES-256 via PyZipper).
   - File ZIP layer 1 dibungkus lagi ke ZIP layer 2 dengan password beda. Bikin terus sampe 10 layer.
3. **Pembuatan File .kedf**:
   - Data riwayat layer dan 10 password tadi dikumpulin.
   - Lu masukin Master Password.
   - Data dienkripsi pakai Master Password (Kombinasi PBKDF2 & Fernet).
   - Hasilnya disimpan jadi file `.kedf`.
4. **Selesai**: File asli dihapus, sisa file layer 10 dan file `.kedf`.

### 🔓 Cara Dekripsi (Buka Kunci):
Tinggal masukin file `.kedf` dan Master Password. Program bakal baca data layer dari dalam terus mengekstrak ZIP dari layer 10 mundur sampai layer 1 secara otomatis.

---

## 🛠️ Teknologi yang Dipakai

- **Python 3**
- **PyZipper**: Kompresi & AES-256 ZIP encryption.
- **Cryptography (Fernet & PBKDF2HMAC)**: Enkripsi data di dalam file `.kedf`.
- **Colorama**: Pewarnaan teks di terminal.

---

## ⚠️ Catatan Keamanan

- Kalau lupa Master Password, mending ikhlasin aja datanya wkwk.
- Kalau file `.kedf` hilang atau rusak, data gabakal bisa balik.
- Selalu backup data penting sebelum nyoba encrypt.

---

## 👨‍💻 Developer

Dibuat oleh: **Kinginul**

Dilarang keras menghapus credit atau mengakui project ini sebagai milik pribadi.
