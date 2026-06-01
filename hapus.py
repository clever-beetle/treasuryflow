import sqlite3
import os

DB_FILE = 'treasury_flow.db'

def bersihkan_layar():
    os.system('cls' if os.name == 'nt' else 'clear')

def jalankan_penghapusan():
    if not os.path.exists(DB_FILE):
        print(f"File {DB_FILE} tidak ditemukan di folder ini!")
        return

    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()

        # Looping utama biar script nggak langsung mati
        while True:
            bersihkan_layar()
            print("="*50)
            print("DATABASE TREASURY FLOW - PENGHAPUSAN AKUN")
            print("="*50)

            users = cursor.execute("SELECT id, username, email FROM users").fetchall()
            
            if not users:
                print("Database kosong. Belum ada akun pengguna yang terdaftar.")
                break

            for u in users:
                print(f"ID: {u['id']} | Username: {u['username']} | Email: {u['email'] or '-'}")
            
            print("-" * 50)
            
            pilihan = input("Masukkan ID akun yang mau dihapus (ketik 'exit' atau 'batal' untuk keluar): ")
            
            if pilihan.lower() in ['exit', 'batal', 'keluar']:
                print("\nKeluar dari program. Database aman.")
                break
                
            try:
                target_id = int(pilihan)
            except ValueError:
                input("\nError: ID harus berupa angka! Tekan Enter untuk mencoba lagi...")
                continue

            user_target = cursor.execute("SELECT username FROM users WHERE id = ?", (target_id,)).fetchone()
            
            if not user_target:
                input(f"\nGagal! Akun dengan ID {target_id} tidak ditemukan. Tekan Enter untuk mencoba lagi...")
                continue
                
            username = user_target['username']
            
            yakin = input(f"Yakin mau hapus akun '{username}' beserta SEMUA data keuangannya? (y/n): ")
            
            if yakin.lower() == 'y':
                # Eksekusi hapus
                cursor.execute("DELETE FROM debt_payments WHERE debt_id IN (SELECT id FROM debts_receivables WHERE user_id = ?)", (target_id,))
                cursor.execute("DELETE FROM debts_receivables WHERE user_id = ?", (target_id,))
                cursor.execute("DELETE FROM recurring_installments WHERE user_id = ?", (target_id,))
                cursor.execute("DELETE FROM assets WHERE user_id = ?", (target_id,))
                cursor.execute("DELETE FROM transactions WHERE user_id = ?", (target_id,))
                cursor.execute("DELETE FROM accounts WHERE user_id = ?", (target_id,))
                cursor.execute("DELETE FROM financial_goals WHERE user_id = ?", (target_id,))
                
                cursor.execute("DELETE FROM users WHERE id = ?", (target_id,))
                conn.commit()
                
                print(f"\n[SUKSES] Akun '{username}' dan seluruh datanya sudah dihapus permanen.")
            else:
                print("\n[INFO] Penghapusan dibatalkan.")
            
            # Pause sebentar biar lo bisa baca pesan sukses/gagal sebelum layar di-clear
            input("Tekan Enter untuk kembali ke daftar akun...")

    except sqlite3.Error as e:
        print(f"\nTerjadi error pada database: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == '__main__':
    jalankan_penghapusan()