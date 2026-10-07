from flask import Blueprint, jsonify, request, session, Response
from utils import get_db, login_required
from webauthn import generate_registration_options, verify_registration_response
from webauthn.helpers import options_to_json
from webauthn.helpers.structs import RegistrationCredential
from webauthn import generate_authentication_options, verify_authentication_response
from webauthn.helpers.structs import AuthenticationCredential
import os

auth_biometric_bp = Blueprint('auth_biometric', __name__)

RP_ID = "www.treasuryflow.web.id" if os.environ.get("VERCEL") else "localhost"
RP_NAME = "Finance Tracker"
ORIGIN = "https://www.treasuryflow.web.id" if os.environ.get("VERCEL") else "http://localhost:5000"

@auth_biometric_bp.route('/api/webauthn/register/generate', methods=['POST'])
@login_required
def register_generate():
    user_id = session['user_id']
    db = get_db()
    user = db.execute("SELECT email, fullname FROM users WHERE id = ?", (user_id,)).fetchone()
    
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=str(user_id).encode('utf-8'),
        user_name=(user['email'] if user and user['email'] else f"user_{user_id}@treasuryflow.web.id"),
        user_display_name=(user['fullname'] if user and user['fullname'] else (user['email'] if user and user['email'] else f"User {user_id}")),
    )
    
    session['registration_challenge'] = options.challenge
    return Response(options_to_json(options), mimetype='application/json')

@auth_biometric_bp.route('/api/webauthn/register/verify', methods=['POST'])
@login_required
def register_verify():
    db = get_db()
    try:
        data = request.get_json(silent=True) or {}
        challenge = session.get('registration_challenge')
        
        verification = verify_registration_response(
            credential=data,
            expected_challenge=challenge,
            expected_origin=ORIGIN,
            expected_rp_id=RP_ID,
        )
        
        db.execute(
            "INSERT INTO webauthn_credentials (user_id, credential_id, public_key, sign_count) VALUES (?, ?, ?, ?)",
            (session['user_id'], verification.credential_id.hex(), verification.credential_public_key, verification.sign_count)
        )
        db.commit()
        return jsonify({"status": "ok"})
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"status": "error", "message": str(e)}), 400

# Authentication logic would go here similarly...
