import base64
import hashlib
from datetime import datetime
from bson import ObjectId
from cryptography.fernet import Fernet
from config import settings
from database import get_db

# Derive a Fernet-compatible 32-byte key from JWT_SECRET
def _get_encryption_key() -> bytes:
    key_source = settings.JWT_SECRET.encode('utf-8')
    key_hash = hashlib.sha256(key_source).digest()
    return base64.urlsafe_b64encode(key_hash)

def encrypt_value(value: str) -> str:
    """Encrypt a secret string value."""
    if not value:
        return ""
    key = _get_encryption_key()
    f = Fernet(key)
    return f.encrypt(value.encode('utf-8')).decode('utf-8')

def decrypt_value(encrypted_value: str) -> str:
    """Decrypt an encrypted secret string value."""
    if not encrypted_value:
        return ""
    try:
        key = _get_encryption_key()
        f = Fernet(key)
        return f.decrypt(encrypted_value.encode('utf-8')).decode('utf-8')
    except Exception as e:
        print(f"Decryption error: {e}")
        return ""

async def get_branch_secrets(branch_id: str) -> dict:
    """Retrieve and decrypt secrets for a specific branch."""
    db = get_db()
    try:
        b_oid = ObjectId(branch_id) if isinstance(branch_id, str) else branch_id
    except Exception:
        return {}
    
    doc = await db.branch_payment_secrets.find_one({"_id": b_oid})
    if not doc:
        return {}
    
    return {
        "payu_merchant_salt": decrypt_value(doc.get("payu_merchant_salt", "")),
        "razorpay_key_secret": decrypt_value(doc.get("razorpay_key_secret", "")),
        "stripe_secret_key": decrypt_value(doc.get("stripe_secret_key", ""))
    }

async def save_branch_secrets(branch_id: str, tenant_id: str, secrets: dict) -> None:
    """Encrypt and save secrets for a specific branch."""
    db = get_db()
    try:
        b_oid = ObjectId(branch_id) if isinstance(branch_id, str) else branch_id
        t_oid = ObjectId(tenant_id) if isinstance(tenant_id, str) else tenant_id
    except Exception:
        return
    
    update_doc = {
        "tenant_id": t_oid,
        "updated_at": datetime.utcnow()
    }
    
    # Only update and encrypt keys that are explicitly passed
    if "payu_merchant_salt" in secrets:
        update_doc["payu_merchant_salt"] = encrypt_value(secrets["payu_merchant_salt"])
    if "razorpay_key_secret" in secrets:
        update_doc["razorpay_key_secret"] = encrypt_value(secrets["razorpay_key_secret"])
    if "stripe_secret_key" in secrets:
        update_doc["stripe_secret_key"] = encrypt_value(secrets["stripe_secret_key"])
        
    await db.branch_payment_secrets.update_one(
        {"_id": b_oid},
        {"$set": update_doc},
        upsert=True
    )
