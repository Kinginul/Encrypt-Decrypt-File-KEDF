import os
import sys
import io
import json
import secrets
import string
import time
import base64
from getpass import getpass
from colorama import init, Fore, Style
import pyzipper
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

init(autoreset=True)

APPNAME = "Kinginul Enc-Dec File"
VERSION = "1.0.1-alpha"
TOTAL_LAYERS = 10
PBKDF2_ITERATIONS = 600000
MAGIC = b'KEDF'
FORMAT_VERSION = 3  # bumped: filename-bound key derivation for .kedf
PROGRESS_SUFFIX = ".kedf.progress"
LAYER_EXT = ".kf"  # "Kinginul File" - disguised, not an obvious .zip

# Obfuscation key for hiding ZIP magic bytes (PK\x03\x04) inside .kf files.
# NOTE: this is obscurity, not cryptographic strength -- the real security
# is the AES-256 encryption pyzipper already applies inside the archive.
OBFUSCATION_KEY = b"KinginulEncDec-ObfuscationLayer-2024-DoNotShareThisConstant"


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header():
    clear_screen()
    print(Fore.CYAN + "=" * 60)
    print(Fore.YELLOW + Style.BRIGHT + f"[{APPNAME} v{VERSION}]".center(60))
    print(Fore.CYAN + "=" * 60)
    print(Fore.RED + Style.BRIGHT + "Alpha build - backup only, use at own risk".center(60))
    print(Fore.CYAN + "-" * 60)


def type_out(text, delay=0.015):
    for ch in text:
        sys.stdout.write(Fore.WHITE + ch)
        sys.stdout.flush()
        time.sleep(delay)
    print()


def spinner(seconds, message="Processing"):
    frames = ['|', '/', '-', '\\']
    end = time.time() + seconds
    i = 0
    while time.time() < end:
        sys.stdout.write(f'\r{Fore.MAGENTA}[{frames[i % 4]}] {message}...')
        sys.stdout.flush()
        time.sleep(0.1)
        i += 1
    sys.stdout.write('\r' + ' ' * 60 + '\r')


def ok(msg):   print(Fore.GREEN + Style.BRIGHT + "[+] " + msg)
def err(msg):  print(Fore.RED + Style.BRIGHT + "[-] " + msg)
def info(msg): print(Fore.BLUE + "[*] " + msg)
def warn(msg): print(Fore.YELLOW + "[!] " + msg)


def press_enter():
    input(Fore.WHITE + "\nTekan Enter untuk lanjut...")


# ---------------------------------------------------------------------------
# Crypto helpers
# ---------------------------------------------------------------------------

def random_password(length=64):
    """Cryptographically secure random password (secrets, not random)."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?/~`"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def random_filename_part(k=10):
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(k))


def derive_key(password, salt, filename_binding, iterations=PBKDF2_ITERATIONS):
    """
    Derive a Fernet key from the master password AND the current filename.

    Binding the filename into the KDF input means the derived key only
    comes out correct if the file is still named exactly what it was when
    it was encrypted. Rename it, and you silently get the wrong key --
    decryption fails the same way a wrong password would. There is no
    separate "check the name" step to bypass; it's baked into the math.
    """
    combined = password.encode('utf-8') + b'::' + filename_binding.encode('utf-8')
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return base64.urlsafe_b64encode(kdf.derive(combined))


def encrypt_keyfile(layer_data, master_password, keyfile_name):
    salt = secrets.token_bytes(16)
    key = derive_key(master_password, salt, os.path.basename(keyfile_name))
    fernet = Fernet(key)
    payload = fernet.encrypt(json.dumps(layer_data).encode('utf-8'))
    header = MAGIC + bytes([FORMAT_VERSION]) + PBKDF2_ITERATIONS.to_bytes(4, 'big') + salt
    return header + payload


def decrypt_keyfile(filepath, master_password):
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except FileNotFoundError:
        err(f"File {filepath} tidak ditemukan.")
        return None

    min_len = 4 + 1 + 4 + 16
    if len(data) < min_len:
        err("File kunci terlalu pendek atau rusak.")
        return None

    if data[:4] != MAGIC:
        err("Bukan file .kedf yang valid.")
        return None

    file_version = data[4]
    if file_version != FORMAT_VERSION:
        err(f"Versi file .kedf ({file_version}) tidak didukung oleh build ini ({FORMAT_VERSION}).")
        return None

    iterations = int.from_bytes(data[5:9], 'big')
    salt = data[9:25]
    ciphertext = data[25:]

    try:
        key = derive_key(master_password, salt, os.path.basename(filepath), iterations)
        fernet = Fernet(key)
        plaintext = fernet.decrypt(ciphertext)
        return json.loads(plaintext.decode('utf-8'))
    except InvalidToken:
        # Deliberately the same message whether the cause is a wrong
        # password OR the file having been renamed -- no clue is given
        # about which one it is.
        err("Password master salah, atau file kunci rusak/dipalsukan.")
        return None
    except Exception as e:
        err(f"Gagal mendekripsi: {e}")
        return None


def xor_obfuscate(data, key=OBFUSCATION_KEY):
    """Symmetric XOR stream over the whole file. Hides the ZIP magic bytes
    (PK\\x03\\x04) and general ZIP structure from casual inspection tools
    (file, hex viewers, signature scanners). Call again with the same key
    to reverse it. This is obscurity, not encryption strength."""
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


# ---------------------------------------------------------------------------
# Zip-slip safe extraction
# ---------------------------------------------------------------------------

def safe_extract_all(zf, dest_dir="."):
    """Extract while rejecting any member that would escape dest_dir."""
    dest_dir = os.path.abspath(dest_dir)
    for member in zf.namelist():
        target_path = os.path.abspath(os.path.join(dest_dir, member))
        if not (target_path == dest_dir or target_path.startswith(dest_dir + os.sep)):
            raise ValueError(f"Entry berbahaya terdeteksi (zip-slip): {member}")
    zf.extractall(path=dest_dir)


# ---------------------------------------------------------------------------
# Progress file (so a crash mid-run doesn't strand undocumented layers)
# ---------------------------------------------------------------------------

def write_progress(progress_path, layer_data):
    tmp_path = progress_path + ".tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(layer_data, f)
    os.replace(tmp_path, progress_path)


def delete_progress(progress_path):
    if os.path.exists(progress_path):
        os.remove(progress_path)


# ---------------------------------------------------------------------------
# Main operations
# ---------------------------------------------------------------------------

def lock_target():
    print_header()
    type_out(f"MENU: ENCRYPT & COMPRESS ({TOTAL_LAYERS} LAYERS)")
    target = input(Fore.WHITE + "Masukkan nama folder/file yang ingin dikunci: ").strip()

    if not os.path.exists(target):
        err("Target tidak ditemukan.")
        press_enter()
        return

    target = os.path.abspath(target)
    original_target = target
    progress_path = target + PROGRESS_SUFFIX
    layer_data = []
    current = target
    is_first_layer = True
    original_removed = False

    for i in range(TOTAL_LAYERS):
        password = random_password()
        out_name = f"kedf_layer_{i}_{random_filename_part()}{LAYER_EXT}"
        info(f"Layer {i + 1}/{TOTAL_LAYERS} ...")
        spinner(0.3, "Mengompres dan mengenkripsi")

        with pyzipper.AESZipFile(out_name, 'w',
                                  compression=pyzipper.ZIP_DEFLATED,
                                  encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(password.encode('utf-8'))
            if is_first_layer and os.path.isdir(current):
                base_dir = os.path.dirname(current)
                for root, _dirs, files in os.walk(current):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, start=base_dir)
                        zf.write(file_path, arcname)
            else:
                zf.write(current, os.path.basename(current))

        # Hide ZIP magic bytes (PK\x03\x04) -- file looks like random data
        with open(out_name, 'rb') as f:
            raw = f.read()
        with open(out_name, 'wb') as f:
            f.write(xor_obfuscate(raw))

        layer_data.append({
            "layer": i + 1,
            "filename": out_name,
            "internal_name": os.path.basename(current),
            "password": password,
        })
        # persist progress after every layer, in case the process dies later
        write_progress(progress_path, layer_data)

        # remove whatever we just zipped -- including the ORIGINAL target on
        # layer 0. This was the critical bug in the previous build: the
        # original file/folder was never deleted because the check skipped
        # the first layer.
        if is_first_layer:
            if os.path.isdir(current):
                import shutil as _shutil
                _shutil.rmtree(current)
            else:
                os.remove(current)
            original_removed = True
        else:
            os.remove(current)

        current = out_name
        is_first_layer = False
        ok(f"Layer {i + 1} selesai -> {out_name}")

    print("\n" + Fore.MAGENTA + "=" * 60)
    print(Fore.YELLOW + "Buat PASSWORD MASTER untuk melindungi file kunci (.kedf).")
    warn("Password ini WAJIB diingat. Tidak ada pemulihan jika lupa.")
    warn("Tanpa file .kedf DAN password master, data TIDAK BISA dibuka. Titik.")
    while True:
        pw1 = getpass(Fore.WHITE + "Password master: ")
        pw2 = getpass(Fore.WHITE + "Konfirmasi password master: ")
        if len(pw1) < 12:
            err("Minimal 12 karakter. Ini kunci satu-satunya, jangan diremehkan.")
            continue
        if pw1 != pw2:
            err("Password tidak cocok.")
            continue
        break

    keyfile_name = f"secret_data_{random_filename_part()}.kedf"
    blob = encrypt_keyfile(layer_data, pw1, keyfile_name)
    with open(keyfile_name, 'wb') as f:
        f.write(blob)

    # progress file no longer needed once the real .kedf exists
    delete_progress(progress_path)

    ok(f"File kunci tersimpan sebagai: {keyfile_name}")
    if original_removed:
        ok("File/folder asli sudah dihapus dari lokasi semula.")
    warn("HANYA dengan file .kedf ini + password master data bisa dibuka kembali.")
    ok("PROSES KUNCI SELESAI")
    press_enter()


def unlock_target():
    print_header()
    type_out("MENU: DECRYPT & EXTRACT")
    keyfile = input(Fore.WHITE + "Masukkan lokasi file kunci (.kedf): ").strip()

    if not os.path.exists(keyfile):
        err("File kunci tidak ditemukan.")
        press_enter()
        return

    master_pw = getpass(Fore.WHITE + "Password master: ")
    info("Memverifikasi dan mendekripsi data kunci...")
    spinner(0.6, "Memproses kunci")

    layer_data = decrypt_keyfile(keyfile, master_pw)
    if not layer_data:
        press_enter()
        return

    ok("Kunci berhasil dibaca. Mulai ekstraksi lapisan...")
    for item in reversed(layer_data):
        layer = item["layer"]
        zip_name = item["filename"]
        password = item["password"]
        info(f"Ekstrak Layer {layer} ({zip_name})")
        if not os.path.exists(zip_name):
            err(f"File {zip_name} hilang. Proses dihentikan.")
            break
        try:
            with open(zip_name, 'rb') as f:
                zip_bytes = xor_obfuscate(f.read())
            with pyzipper.AESZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                zf.setpassword(password.encode('utf-8'))
                safe_extract_all(zf, dest_dir=".")
            os.remove(zip_name)
            ok(f"Layer {layer} berhasil diekstrak dan dihapus.")
        except RuntimeError:
            err(f"Password salah untuk layer {layer} atau file korup.")
            break
        except ValueError as e:
            err(f"Ekstraksi dibatalkan: {e}")
            break
        except Exception as e:
            err(f"Gagal mengekstrak {zip_name}: {e}")
            break

    ok("PROSES BUKA KUNCI SELESAI")
    print(Fore.CYAN + "Folder/File asli Anda telah dikembalikan (jika semua layer berhasil).")
    press_enter()


def main():
    while True:
        print_header()
        print(Fore.WHITE + Style.BRIGHT + f"  1. Kunci Folder/File ({TOTAL_LAYERS} Layer ZIP)")
        print(Fore.WHITE + Style.BRIGHT + "  2. Buka Kunci (Ekstrak semua Layer)")
        print(Fore.WHITE + Style.BRIGHT + "  3. Keluar")
        print(Fore.CYAN + "-" * 60)

        try:
            choice = input(Fore.WHITE + "  Pilih menu (1/2/3): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSelesai.")
            break

        if choice == '1':
            lock_target()
        elif choice == '2':
            unlock_target()
        elif choice == '3':
            print_header()
            print(Fore.YELLOW + "Keluar dari tool.")
            time.sleep(0.5)
            sys.exit(0)
        else:
            err("Pilihan tidak valid.")
            time.sleep(0.6)


if __name__ == "__main__":
    main()
