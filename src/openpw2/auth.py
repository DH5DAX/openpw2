"""RS-PW2 1.0.4 login construction, recovered from installed application IL.

Evidence: MethodDef 0x06000174 pads ASCII credentials to 16 bytes;
0x06000175 hashes challenge bytes + FieldRva 1209 + padded password;
FieldRva 1209 is ASCII '4109'. HashData is SHA256. MethodDef 0x060000f0
calls RSACryptoServiceProvider.Encrypt(data, False), i.e. PKCS#1 v1.5.
No credentials, capture data or vendor binaries are included here.
This module constructs bodies only; it does not connect to hardware.
"""

from __future__ import annotations

import hashlib

from cryptography.hazmat.primitives.asymmetric import padding, rsa


def credential_field(value: str) -> bytes:
    """Match .NET Encoding.ASCII and the application's 16-byte copy loop."""
    return value.encode("ascii", errors="replace")[:16].ljust(16, b" ")


def login_digest(password: str, token: bytes) -> bytes:
    """Token is the raw 108-byte challenge field, NOT base64-decoded."""
    if len(token) != 108:
        raise ValueError("PW2 challenge token must contain exactly 108 bytes")
    return hashlib.sha256(token + b"4109" + credential_field(password)).digest()


def login_body(username: str, password: str, challenge_body: bytes) -> bytes:
    """Build the 148-byte control body from a type-1 challenge body.

    Challenge offsets: 4:112 raw token; 112:240 modulus (big endian);
    240:243 exponent (big endian); bytes 243 onward are capability fields.
    """
    if len(challenge_body) < 244 or challenge_body[:4] != b"\x01\x00\x00\x00":
        raise ValueError("Expected a type-1 PW2 challenge of at least 244 bytes")
    token = challenge_body[4:112]
    modulus = int.from_bytes(challenge_body[112:240], "big")
    exponent = int.from_bytes(challenge_body[240:243], "big")
    public_key = rsa.RSAPublicNumbers(exponent, modulus).public_key()
    if public_key.key_size != 1024:
        raise ValueError("Expected a 1024-bit PW2 RSA key")
    encrypted = public_key.encrypt(login_digest(password, token), padding.PKCS1v15())
    return b"\x02\x00\x00\x00" + credential_field(username) + encrypted
