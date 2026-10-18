"""Signer in minisign format: Ed25519 over the BLAKE2b-512 hash of the message (algorithm `ED`).

Signatures and public keys are byte-compatible with minisign, which the app verifies
(contracts/README.md). The secret key file is our own plain format, not minisign's encrypted one:
it lives outside the repository with owner-only permissions (docs/security.md).

    stronk signing key v1
    key_id=<16 upper-case hex>
    seed=<base64 of the 32-byte Ed25519 seed>
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.ports import Signer, StoreError

KEY_HEADER = "stronk signing key v1"
PUBLIC_ALGORITHM = b"Ed"
PREHASHED = b"ED"


def key_id_hex(keynum: bytes) -> str:
    """minisign prints its 8-byte key number as a little-endian u64 in upper-case hex."""
    return keynum[::-1].hex().upper()


@dataclass(frozen=True)
class MinisignSigner:
    keynum: bytes
    private_key: Ed25519PrivateKey

    @property
    def key_id(self) -> str:
        return key_id_hex(self.keynum)

    def public_key(self) -> str:
        """The public key file, as `minisign -G` writes it."""
        raw = self.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        line = base64.b64encode(PUBLIC_ALGORITHM + self.keynum + raw).decode()
        return f"untrusted comment: minisign public key {self.key_id}\n{line}\n"

    def sign(self, message: bytes, trusted_comment: str) -> bytes:
        """The `.minisig` file for `message`. `trusted_comment` is signed too (one line)."""
        if "\n" in trusted_comment or "\r" in trusted_comment:
            raise ValueError("trusted comment must be one line")
        signature = self.private_key.sign(hashlib.blake2b(message).digest())
        global_signature = self.private_key.sign(signature + trusted_comment.encode())
        return (
            "untrusted comment: signature from stronk secret key\n"
            f"{base64.b64encode(PREHASHED + self.keynum + signature).decode()}\n"
            f"trusted comment: {trusted_comment}\n"
            f"{base64.b64encode(global_signature).decode()}\n"
        ).encode()


def generate(path: Path) -> Result[MinisignSigner, StoreError]:
    """A new key, written to `path` (owner read/write only). Never overwrites a key."""
    signer = MinisignSigner(secrets.token_bytes(8), Ed25519PrivateKey.generate())
    seed = signer.private_key.private_bytes_raw()
    text = f"{KEY_HEADER}\nkey_id={signer.key_id}\nseed={base64.b64encode(seed).decode()}\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(text)
    except FileExistsError:
        return Err(StoreError("invalid", f"{path} exists; refusing to overwrite a signing key"))
    except OSError as e:
        return Err(StoreError("invalid", f"cannot write {path}: {e}"))
    return Ok(signer)


def load(path: Path) -> Result[MinisignSigner, StoreError]:
    if not path.is_file():
        return Err(StoreError("not_found", f"no signing key at {path}"))
    try:
        lines = path.read_text().splitlines()
    except OSError as e:
        return Err(StoreError("invalid", f"cannot read {path}: {e}"))
    fields = dict(line.split("=", 1) for line in lines[1:] if "=" in line)
    try:
        if not lines or lines[0] != KEY_HEADER:
            raise ValueError("not a stronk signing key")
        keynum = bytes.fromhex(fields["key_id"])[::-1]
        seed = base64.b64decode(fields["seed"], validate=True)
        if len(keynum) != 8 or len(seed) != 32:
            raise ValueError("wrong key length")
        return Ok(MinisignSigner(keynum, Ed25519PrivateKey.from_private_bytes(seed)))
    except (KeyError, ValueError, binascii.Error) as e:
        # The message never includes the file's contents.
        return Err(StoreError("invalid", f"{path} is not a valid signing key ({type(e).__name__})"))


def verify(public_key: str, message: bytes, signature: bytes) -> Result[str, str]:
    """The trusted comment if `signature` (a `.minisig` file) is valid for `message`."""
    try:
        pk_line = public_key.splitlines()[1]
        pk = base64.b64decode(pk_line, validate=True)
        lines = signature.decode().splitlines()
        sig = base64.b64decode(lines[1], validate=True)
        comment_line, global_sig = lines[2], base64.b64decode(lines[3], validate=True)
    except (IndexError, ValueError, binascii.Error):
        return Err("malformed public key or signature")
    if len(pk) != 42 or pk[:2] != PUBLIC_ALGORITHM or len(sig) != 74 or sig[:2] != PREHASHED:
        return Err("unsupported key or signature algorithm")
    if sig[2:10] != pk[2:10]:
        return Err("signed by another key")
    if not comment_line.startswith("trusted comment: "):
        return Err("no trusted comment")
    comment = comment_line.removeprefix("trusted comment: ")
    key = Ed25519PublicKey.from_public_bytes(pk[10:])
    try:
        key.verify(sig[10:], hashlib.blake2b(message).digest())
        key.verify(global_sig, sig[10:] + comment.encode())
    except InvalidSignature:
        return Err("bad signature")
    return Ok(comment)


class MinisignKeys:
    """`SigningKeys` on key files."""

    def generate(self, path: Path) -> Result[Signer, StoreError]:
        match generate(path):
            case Err() as e:
                return e
            case Ok(value=signer):
                pass
        public = path.with_name(path.name + ".pub")
        try:
            public.write_text(signer.public_key())
        except OSError as e:
            return Err(StoreError("invalid", f"cannot write {public}: {e}"))
        return Ok(signer)

    def load(self, path: Path) -> Result[Signer, StoreError]:
        match load(path):
            case Err() as e:
                return e
            case Ok(value=signer):
                return Ok(signer)
