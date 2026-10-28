from flask import Blueprint, jsonify, request, session, Response, url_for
from utils import get_db, login_required
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
)
from webauthn.helpers import options_to_json, base64url_to_bytes
from webauthn.helpers.structs import PublicKeyCredentialDescriptor
import os

auth_biometric_bp = Blueprint('auth_biometric', __name__)

RP_NAME = "Treasury Flow"


def _get_rp_id():
    host = (request.host or 'localhost').split(':')[0]
    if host == '127.0.0.1':
        return 'localhost'
    return host


def _get_origin():
    return (request.host_url or 'http://localhost:5000').rstrip('/')


@auth_biometric_bp.route('/api/webauthn/register/generate', methods=['POST'])
@login_required
def register_generate():
    user_id = session['user_id']
    db = get_db()
    user = db.execute("SELECT username, email, fullname FROM users WHERE id = ?", (user_id,)).fetchone()
    u_name = (user['email'] or user['username'] or f"user_{user_id}") if user else f"user_{user_id}"
    u_display = (user['fullname'] or u_name) if user else f"User {user_id}"

    options = generate_registration_options(
        rp_id=_get_rp_id(),
        rp_name=RP_NAME,
        user_id=str(user_id).encode('utf-8'),
        user_name=u_name,
        user_display_name=u_display,
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
            return jsonify({"status": "error", "message": "Sesi registrasi Passkey kedaluwarsa. Silakan coba lagi."}), 400
        expected_challenge = bytes.fromhex(raw_challenge) if isinstance(raw_challenge, str) else raw_challenge

        verification = verify_registration_response(
            credential=data,
            expected_challenge=expected_challenge,
            expected_origin=_get_origin(),
            expected_rp_id=_get_rp_id(),
        )

        cred_id_hex = verification.credential_id.hex()
        pub_key_hex = verification.credential_public_key.hex() if isinstance(verification.credential_public_key, (bytes, bytearray)) else str(verification.credential_public_key)

        db.execute(
            "INSERT INTO webauthn_credentials (user_id, credential_id, public_key, sign_count) VALUES (?, ?, ?, ?)",
            (session['user_id'], cred_id_hex, pub_key_hex, verification.sign_count)
        )
        db.commit()
        return jsonify({"status": "ok"})
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"status": "error", "message": str(e)}), 400


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
            return jsonify({"status": "error", "message": "Sesi autentikasi kedaluwarsa. Silakan coba lagi."}), 400
        expected_challenge = bytes.fromhex(raw_challenge) if isinstance(raw_challenge, str) else raw_challenge

        raw_id_b64 = data.get('rawId') or data.get('id') or ''
        cred_bytes = base64url_to_bytes(raw_id_b64)
        cred_hex = cred_bytes.hex()

        cred_row = db.execute(
            "SELECT user_id, credential_id, public_key, sign_count FROM webauthn_credentials WHERE credential_id = ?",
            (cred_hex,)
        ).fetchone()
        if not cred_row:
            return jsonify({"status": "error", "message": "Passkey belum terdaftar di akun mana pun."}), 400

        pub_key = cred_row['public_key']
        if isinstance(pub_key, str):
            pub_key_bytes = bytes.fromhex(pub_key)
        elif isinstance(pub_key, memoryview):
            pub_key_bytes = bytes(pub_key)
        else:
            pub_key_bytes = pub_key

        verification = verify_authentication_response(
            credential=data,
            expected_challenge=expected_challenge,
            expected_origin=_get_origin(),
            expected_rp_id=_get_rp_id(),
            credential_public_key=pub_key_bytes,
            credential_current_sign_count=int(cred_row['sign_count'] or 0),
        )

        db.execute(
            "UPDATE webauthn_credentials SET sign_count = ? WHERE credential_id = ?",
            (verification.new_sign_count, cred_hex)
        )
        db.commit()

        user = db.execute("SELECT id, username, fullname, role FROM users WHERE id = ?", (cred_row['user_id'],)).fetchone()
        if not user:
            return jsonify({"status": "error", "message": "Akun pengguna tidak ditemukan."}), 404

        session['user_id'] = user['id']
        session['username'] = user['username']
        session['fullname'] = user['fullname']
        session['role'] = user['role'] if 'role' in user.keys() and user['role'] else 'user'
        session.permanent = True

        return jsonify({"status": "ok", "redirect": url_for('dashboard.dashboard')})
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"status": "error", "message": str(e)}), 400
