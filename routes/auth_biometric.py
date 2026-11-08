from flask import Blueprint, jsonify, request, session, Response, url_for
import psycopg2
import utils
from utils import get_db, login_required
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
)
from webauthn.helpers import options_to_json, base64url_to_bytes
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

auth_biometric_bp = Blueprint('auth_biometric', __name__)

RP_NAME = "Treasury Flow"


def _get_raw_host() -> str:
    host = (request.host or 'localhost').split(':')[0].strip().lower()
    if host == '127.0.0.1':
        return 'localhost'
    return host


def _get_rp_id() -> str:
    host = _get_raw_host()
    if host.startswith('www.') and host.count('.') >= 2:
        return host[4:]
    return host


def _get_candidate_rp_ids() -> list:
    primary = _get_rp_id()
    raw = _get_raw_host()
    if raw != primary:
        return [primary, raw]
    return [primary]


def _get_origin() -> str:
    return (request.host_url or 'http://localhost:5000').rstrip('/')


def _decode_stored_public_key(pub_key) -> bytes:
    """Decode public_key stored across SQLite (TEXT/BLOB) and PostgreSQL (BYTEA).

    Handles:
    1. Hex strings ('a50102...')
    2. PostgreSQL BYTEA memoryview/bytes that stored ASCII hex bytes (b'a50102...')
    3. Raw binary CBOR COSE_Key bytes (first byte 0xa1..0xbf >= 0x80)
    """
    if isinstance(pub_key, str):
        s = pub_key.strip()
        if s.startswith('\\x'):
            s = s[2:]
        return bytes.fromhex(s)

    raw = bytes(pub_key) if isinstance(pub_key, (memoryview, bytearray)) else pub_key
    if not isinstance(raw, bytes):
        raise ValueError("Format kunci publik Passkey tidak valid.")

    if raw.startswith(b'\\x') and len(raw) > 2:
        try:
            return bytes.fromhex(raw[2:].decode('ascii'))
        except Exception:
            pass

    if raw and len(raw) % 2 == 0 and all(b in b'0123456789abcdefABCDEF' for b in raw):
        return bytes.fromhex(raw.decode('ascii'))

    return raw


@auth_biometric_bp.route('/api/webauthn/register/generate', methods=['POST'])
@login_required
def register_generate():
    user_id = session['user_id']
    db = get_db()
    user = db.execute("SELECT username, email, fullname FROM users WHERE id = ?", (user_id,)).fetchone()
    u_name = (user['email'] or user['username'] or f"user_{user_id}") if user else f"user_{user_id}"
    u_display = (user['fullname'] or u_name) if user else f"User {user_id}"

    existing_rows = db.execute("SELECT credential_id FROM webauthn_credentials WHERE user_id = ?", (user_id,)).fetchall()
    exclude_creds = []
    for r in existing_rows:
        try:
            exclude_creds.append(PublicKeyCredentialDescriptor(id=bytes.fromhex(r['credential_id'])))
        except Exception:
            pass

    options = generate_registration_options(
        rp_id=_get_rp_id(),
        rp_name=RP_NAME,
        user_id=str(user_id).encode('utf-8'),
        user_name=u_name,
        user_display_name=u_display,
        exclude_credentials=exclude_creds if exclude_creds else None,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    session['registration_challenge'] = options.challenge.hex() if isinstance(options.challenge, (bytes, bytearray)) else str(options.challenge)
    return Response(options_to_json(options), mimetype='application/json')


@auth_biometric_bp.route('/api/webauthn/register/verify', methods=['POST'])
@login_required
def register_verify():
    db = get_db()
    try:
        data = request.get_json(silent=True) or {}
        raw_challenge = session.get('registration_challenge')
        if not raw_challenge:
            return jsonify({"status": "error", "message": "Sesi registrasi Passkey kedaluwarsa. Silakan muat ulang halaman dan coba lagi."}), 400
        expected_challenge = bytes.fromhex(raw_challenge) if isinstance(raw_challenge, str) else raw_challenge

        verification = None
        last_err = None
        for rp_candidate in _get_candidate_rp_ids():
            try:
                verification = verify_registration_response(
                    credential=data,
                    expected_challenge=expected_challenge,
                    expected_origin=_get_origin(),
                    expected_rp_id=rp_candidate,
                )
                break
            except Exception as err:
                last_err = err
        if verification is None:
            raise last_err or ValueError("Verifikasi registrasi Passkey gagal.")

        cred_id_hex = verification.credential_id.hex()
        raw_pub_key = bytes(verification.credential_public_key)
        db_pub_val = psycopg2.Binary(raw_pub_key) if utils.DATABASE_URL else raw_pub_key

        existing = db.execute(
            "SELECT id FROM webauthn_credentials WHERE credential_id = ?",
            (cred_id_hex,)
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE webauthn_credentials SET user_id = ?, public_key = ?, sign_count = ? WHERE id = ?",
                (session['user_id'], db_pub_val, int(verification.sign_count or 0), existing['id'])
            )
        else:
            db.execute(
                "INSERT INTO webauthn_credentials (user_id, credential_id, public_key, sign_count) VALUES (?, ?, ?, ?)",
                (session['user_id'], cred_id_hex, db_pub_val, int(verification.sign_count or 0))
            )
        db.commit()
        session.pop('registration_challenge', None)

        total_keys = db.execute(
            "SELECT COUNT(*) AS c FROM webauthn_credentials WHERE user_id = ?",
            (session['user_id'],)
        ).fetchone()['c']
        return jsonify({"status": "ok", "passkey_count": int(total_keys or 1)})
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"status": "error", "message": f"Gagal mendaftarkan Passkey: {str(e)}"}), 400


@auth_biometric_bp.route('/api/webauthn/login/generate', methods=['POST'])
def login_generate():
    db = get_db()
    data = request.get_json(silent=True) or {}
    identifier = (data.get('username') or '').strip()

    allow_credentials = []
    if identifier:
        user = db.execute(
            "SELECT id FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)",
            (identifier, identifier)
        ).fetchone()
        if user:
            rows = db.execute("SELECT credential_id FROM webauthn_credentials WHERE user_id = ?", (user['id'],)).fetchall()
            for r in rows:
                try:
                    allow_credentials.append(PublicKeyCredentialDescriptor(id=bytes.fromhex(r['credential_id'])))
                except Exception:
                    pass

    options = generate_authentication_options(
        rp_id=_get_rp_id(),
        allow_credentials=allow_credentials if allow_credentials else None,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    session['authentication_challenge'] = options.challenge.hex() if isinstance(options.challenge, (bytes, bytearray)) else str(options.challenge)
    return Response(options_to_json(options), mimetype='application/json')


@auth_biometric_bp.route('/api/webauthn/login/verify', methods=['POST'])
def login_verify():
    db = get_db()
    try:
        data = request.get_json(silent=True) or {}
        raw_challenge = session.get('authentication_challenge')
        if not raw_challenge:
            return jsonify({"status": "error", "message": "Sesi autentikasi kedaluwarsa. Silakan klik tombol Passkey sekali lagi."}), 400
        expected_challenge = bytes.fromhex(raw_challenge) if isinstance(raw_challenge, str) else raw_challenge

        raw_id_b64 = data.get('rawId') or data.get('id') or ''
        cred_bytes = base64url_to_bytes(raw_id_b64)
        cred_hex = cred_bytes.hex()

        cred_row = db.execute(
            "SELECT id, user_id, credential_id, public_key, sign_count FROM webauthn_credentials WHERE credential_id = ?",
            (cred_hex,)
        ).fetchone()
        if not cred_row:
            return jsonify({"status": "error", "message": "Passkey belum terdaftar di akun mana pun. Silakan masuk dengan password lalu aktifkan Passkey di Pengaturan."}), 400

        pub_key_bytes = _decode_stored_public_key(cred_row['public_key'])

        verification = None
        last_err = None
        for rp_candidate in _get_candidate_rp_ids():
            try:
                verification = verify_authentication_response(
                    credential=data,
                    expected_challenge=expected_challenge,
                    expected_origin=_get_origin(),
                    expected_rp_id=rp_candidate,
                    credential_public_key=pub_key_bytes,
                    credential_current_sign_count=int(cred_row['sign_count'] or 0),
                )
                break
            except Exception as err:
                last_err = err
        if verification is None:
            raise last_err or ValueError("Tanda tangan biometrik tidak valid.")

        db.execute(
            "UPDATE webauthn_credentials SET sign_count = ? WHERE credential_id = ?",
            (int(verification.new_sign_count or 0), cred_hex)
        )
        db.commit()
        session.pop('authentication_challenge', None)

        user = db.execute("SELECT id, username, fullname, role FROM users WHERE id = ?", (cred_row['user_id'],)).fetchone()
        if not user:
            return jsonify({"status": "error", "message": "Akun pengguna tidak ditemukan."}), 404

        session['user_id'] = user['id']
        session['username'] = user['username']
        session['fullname'] = user['fullname']
        session['role'] = user['role'] if 'role' in user.keys() and user['role'] else 'user'
        session.permanent = True

        next_url = (data.get('next') or '').strip()
        if not next_url or not next_url.startswith('/') or next_url.startswith('//'):
            next_url = url_for('dashboard.dashboard')

        return jsonify({"status": "ok", "redirect": next_url})
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"status": "error", "message": f"Verifikasi biometrik gagal: {str(e)}"}), 400
