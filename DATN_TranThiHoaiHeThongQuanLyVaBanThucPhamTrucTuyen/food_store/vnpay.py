"""
vnpay.py - Helper tao URL thanh toan va xac thuc callback VNPAY.
"""
import hashlib
import hmac
from urllib.parse import quote_plus, urlencode


def _normalize_params(params):
    return {
        key: str(value)
        for key, value in params.items()
        if value is not None and str(value) != ""
    }


def build_hash_data(params):
    data = _normalize_params(params)
    return urlencode(sorted(data.items()), quote_via=quote_plus)


def hmac_sha512(secret_key, data):
    return hmac.new(
        secret_key.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha512
    ).hexdigest()


def build_payment_url(payment_url, params, secret_key):
    hash_data = build_hash_data(params)
    secure_hash = hmac_sha512(secret_key, hash_data)
    return f"{payment_url}?{hash_data}&vnp_SecureHash={secure_hash}"


def verify_response(params, secret_key):
    data = _normalize_params(params)
    secure_hash = data.pop("vnp_SecureHash", "")
    data.pop("vnp_SecureHashType", None)

    if not secure_hash:
        return False

    signed = hmac_sha512(secret_key, build_hash_data(data))
    return hmac.compare_digest(signed.lower(), secure_hash.lower())
