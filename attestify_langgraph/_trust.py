"""
Attestify Trust — canonicalization, Ed25519 signing, and key generation.

Duplicated verbatim from sdk/python/attestify/__init__.py's own
_trust_canonicalize / _trust_sign / generate_trust_keypair (the base
Python SDK), not reimplemented — the canonical-JSON + signing algorithm
must byte-for-byte match what the server re-derives and re-verifies
(app/api/trust/v1/evidence/route.ts), and there's no shared cross-language
vectors file to test a fresh reimplementation against. If you change this,
change every copy: sdk/python, sdk/langchain, sdk/crewai, sdk/autogen,
sdk/langgraph, and the TypeScript SDK's canonical.ts.

`cryptography` is imported lazily, only when a signing/keygen function
actually runs, so the base package (langchain-core only) stays installable
without it: ``pip install attestify-langgraph[trust]``.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from ._http import AttestifyError

_TRUST_BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _trust_require_cryptography():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
    except ImportError as exc:
        raise AttestifyError(
            "Attestify Trust needs the 'cryptography' package for Ed25519 "
            "signing. Install it with: pip install attestify-langgraph[trust]"
        ) from exc
    return Ed25519PrivateKey


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def _js_number_to_string(value: float) -> str:
    """Replicates ECMA-262's Number::toString — see sdk/python's copy of
    this function for the full rationale."""
    sign = "-" if value < 0 else ""
    r = repr(abs(value))
    if "e" in r:
        mantissa, exp_str = r.split("e")
        exp = int(exp_str)
    else:
        mantissa, exp = r, 0
    int_part, _, frac_part = mantissa.partition(".")
    all_digits = int_part + frac_part
    stripped_leading = all_digits.lstrip("0")
    leading_zeros = len(all_digits) - len(stripped_leading)
    n = len(int_part) - leading_zeros + exp
    digits = stripped_leading.rstrip("0") or "0"
    k = len(digits)

    if k <= n <= 21:
        s = digits + "0" * (n - k)
    elif 0 < n <= 21:
        s = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        s = "0." + "0" * (-n) + digits
    else:
        exp_val = n - 1
        exp_sign = "+" if exp_val >= 0 else "-"
        mantissa_str = digits if k == 1 else f"{digits[0]}.{digits[1:]}"
        s = f"{mantissa_str}e{exp_sign}{abs(exp_val)}"
    return sign + s


def _trust_canonicalize(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise AttestifyError(f"Trust: non-finite number ({value}) cannot be canonicalized.")
        if value == 0.0:
            return "0"
        return _js_number_to_string(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return f"[{','.join(_trust_canonicalize(item) for item in value)}]"
    if isinstance(value, dict):
        parts = [f"{json.dumps(key)}:{_trust_canonicalize(value[key])}" for key in sorted(value.keys())]
        return f"{{{','.join(parts)}}}"
    raise AttestifyError(f"Trust: value of type {type(value).__name__!r} cannot be canonicalized.")


def _trust_generate_nonce() -> str:
    return "".join(_TRUST_BASE62_ALPHABET[b % 62] for b in os.urandom(16))


def generate_trust_keypair() -> dict:
    """Generates a new local Ed25519 keypair. No network call. Requires
    the 'cryptography' package. Returns {"public_key", "private_key"},
    both base64url-encoded raw 32-byte values."""
    Ed25519PrivateKey = _trust_require_cryptography()
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, PublicFormat,
    )

    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    public_raw = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return {"public_key": _b64url_encode(public_raw), "private_key": _b64url_encode(private_raw)}


def _trust_sign(message: str, private_key_b64url: str) -> str:
    Ed25519PrivateKey = _trust_require_cryptography()
    private_key = Ed25519PrivateKey.from_private_bytes(_b64url_decode(private_key_b64url))
    signature = private_key.sign(message.encode("utf-8"))
    return _b64url_encode(signature)


def sign_trust_evidence(
    agent_id: str,
    schema: str,
    payload: dict,
    private_key: str,
    action_basis: str = "explicit",
    nonce: str = "",
    scope_ref: str = "",
) -> dict:
    """Canonicalizes and signs a Trust evidence event locally. Returns the
    full signed object (including 'signature') ready to POST to
    /api/trust/v1/evidence. The private key never leaves this function."""
    signed_object = {
        "agent_id": agent_id,
        "schema": schema,
        "payload": payload,
        "action_basis": action_basis,
        "nonce": nonce or _trust_generate_nonce(),
        "scope_ref": scope_ref or None,
    }
    canonical_string = _trust_canonicalize(signed_object)
    signature = _trust_sign(canonical_string, private_key)
    return {**signed_object, "signature": signature}


def provision_trust_agent(
    api_key: str,
    display_name: str,
    framework: str,
    base_url: str = "https://attestifyos.com",
) -> dict:
    """
    One-time setup helper — call this yourself, once, outside of any agent
    run, exactly like ``npx attestify trust-init``. NOT exposed as an
    LLM-callable tool: generating a fresh identity mid-conversation would
    both break the agent's verified-active streak and add noise to
    Attestify's public census instead of a real, citable number (see
    attestifyagent/trust-action's README for the same rule applied to CI).

    Creates a new Trust agent, generates its Ed25519 keypair locally, and
    registers the public key — all in one call. Store the returned
    ``agent_id`` and ``private_key`` as environment variables
    (``TRUST_AGENT_ID``, ``TRUST_PRIVATE_KEY``) and pass them to the
    toolkit/toolset/function-map constructor from then on; never call this
    again for the same agent.

    Returns {"agent_id", "public_key", "private_key"}.
    """
    from ._http import _Client

    client = _Client(api_key=api_key, base_url=base_url)
    agent = client.post("/api/trust/v1/agents", {"display_name": display_name, "framework": framework})
    agent_id = agent["agent"]["id"]
    keys = generate_trust_keypair()
    client.post(f"/api/trust/v1/agents/{agent_id}/keys", {"public_key": keys["public_key"]})
    return {"agent_id": agent_id, "public_key": keys["public_key"], "private_key": keys["private_key"]}
