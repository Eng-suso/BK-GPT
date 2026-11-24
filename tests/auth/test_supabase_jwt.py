"""Il verifier degli access token Supabase, senza rete e senza Supabase.

Le chiavi sono generate qui; il JWKS e' un dict servito da una funzione finta;
l'orologio della cache e' un contatore. Ogni test rompe una sola cosa di un
token altrimenti valido.
"""

from __future__ import annotations

import json
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from backend.auth.supabase_jwt import (
    UNKNOWN_KID_REFRESH_SECONDS,
    IdentityProviderUnavailable,
    InvalidAccessToken,
    JwksCache,
    SupabaseTokenVerifier,
)

SUPABASE_URL = "https://progetto.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
SUBJECT = str(uuid.uuid4())


def _ec_key(kid: str):
    private = ec.generate_private_key(ec.SECP256R1())
    public = json.loads(ECAlgorithm.to_jwk(private.public_key()))
    public.update({"kid": kid, "alg": "ES256", "use": "sig"})
    return private, public


class FakeJwks:
    """Il JWKS del progetto: si puo' cambiare, spegnere e contare."""

    def __init__(self, *keys: dict) -> None:
        self.keys = list(keys)
        self.down = False
        self.calls = 0

    def __call__(self, url: str) -> dict:
        assert url == f"{ISSUER}/.well-known/jwks.json"
        self.calls += 1
        if self.down:
            raise OSError("supabase non risponde")
        return {"keys": self.keys}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def keys():
    return _ec_key("kid-1")


@pytest.fixture()
def jwks(keys):
    return FakeJwks(keys[1])


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def verifier(jwks, clock):
    cache = JwksCache(
        f"{ISSUER}/.well-known/jwks.json",
        ttl_seconds=600,
        max_stale_seconds=3600,
        fetch=jwks,
        clock=clock,
    )
    return SupabaseTokenVerifier(SUPABASE_URL, audience="authenticated", jwks=cache)


def _claims(**overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": "authenticated",
        "sub": SUBJECT,
        "role": "authenticated",
        "is_anonymous": False,
        "email": "consulente@example.com",
        "session_id": "sessione-1",
        "iat": now,
        "exp": now + 1800,
    }
    claims.update(overrides)
    return {key: value for key, value in claims.items() if value is not None}


def _token(private, kid="kid-1", **overrides) -> str:
    return jwt.encode(_claims(**overrides), private, algorithm="ES256", headers={"kid": kid})


def test_a_valid_token_proves_who_is_calling(verifier, keys):
    identity = verifier.verify(_token(keys[0]))

    assert identity.subject == SUBJECT
    assert identity.session_id == "sessione-1"
    assert identity.email == "consulente@example.com"


@pytest.mark.parametrize(
    ("overrides", "why"),
    [
        ({"exp": int(time.time()) - 120}, "scaduto oltre la tolleranza"),
        ({"iss": "https://altro.supabase.co/auth/v1"}, "un altro progetto Supabase"),
        ({"aud": "service_role"}, "audience sbagliata"),
        ({"role": "anon"}, "ruolo anon: la chiave pubblica del progetto"),
        ({"role": "service_role"}, "ruolo service_role: non e' un utente"),
        ({"is_anonymous": True}, "sessione anonima"),
        ({"is_anonymous": None}, "is_anonymous assente: non si presume"),
        ({"sub": "admin"}, "sub non UUID"),
        ({"exp": None}, "senza scadenza"),
        ({"iat": None}, "senza iat"),
    ],
)
def test_a_token_that_does_not_prove_an_identity_is_refused(verifier, keys, overrides, why):
    with pytest.raises(InvalidAccessToken):
        verifier.verify(_token(keys[0], **overrides))


def test_clock_skew_within_a_minute_is_tolerated(verifier, keys):
    assert verifier.verify(_token(keys[0], exp=int(time.time()) - 30)).subject == SUBJECT


def test_a_token_signed_by_another_key_with_the_same_kid_is_refused(verifier):
    impostor, _ = _ec_key("kid-1")

    with pytest.raises(InvalidAccessToken):
        verifier.verify(_token(impostor))


@pytest.mark.parametrize("algorithm", ["HS256", "none"])
def test_only_es256_is_accepted(verifier, algorithm):
    """HS256 firmato con un segreto qualunque, o nessuna firma: rifiutati prima di guardare la chiave."""
    key = "segreto-condiviso-lungo-abbastanza-32b" if algorithm == "HS256" else None
    token = jwt.encode(_claims(), key, algorithm=algorithm, headers={"kid": "kid-1"})

    with pytest.raises(InvalidAccessToken, match="algoritmo"):
        verifier.verify(token)


def test_garbage_and_missing_kid_are_refused(verifier, keys):
    with pytest.raises(InvalidAccessToken):
        verifier.verify("non-un-jwt")
    token = jwt.encode(_claims(), keys[0], algorithm="ES256")
    with pytest.raises(InvalidAccessToken, match="kid"):
        verifier.verify(token)


def test_a_non_ec_key_in_the_jwks_never_verifies_anything(jwks, clock):
    """Una chiave RSA pubblicata per errore non diventa un modo di firmare."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    public.update({"kid": "rsa-1", "alg": "RS256"})
    jwks.keys = [public]
    cache = JwksCache("x", ttl_seconds=600, max_stale_seconds=3600, fetch=lambda _: {"keys": [public]}, clock=clock)
    verifier = SupabaseTokenVerifier(SUPABASE_URL, audience="authenticated", jwks=cache)
    token = jwt.encode(_claims(), private, algorithm="RS256", headers={"kid": "rsa-1"})

    with pytest.raises(InvalidAccessToken):
        verifier.verify(token)


def test_keys_are_cached_and_reread_after_the_ttl(verifier, keys, jwks, clock):
    token = _token(keys[0])
    verifier.verify(token)
    verifier.verify(token)
    assert jwks.calls == 1

    clock.now += 600
    verifier.verify(token)
    assert jwks.calls == 2


def test_a_rotated_key_is_picked_up_at_once(verifier, keys, jwks, clock):
    verifier.verify(_token(keys[0]))
    new_private, new_public = _ec_key("kid-2")
    jwks.keys.append(new_public)
    clock.now += UNKNOWN_KID_REFRESH_SECONDS

    assert verifier.verify(_token(new_private, kid="kid-2")).subject == SUBJECT
    assert jwks.calls == 2


def test_unknown_kids_cannot_turn_every_request_into_a_call_to_supabase(verifier, keys, jwks):
    verifier.verify(_token(keys[0]))
    stranger, _ = _ec_key("inventato")

    for _ in range(20):
        with pytest.raises(InvalidAccessToken):
            verifier.verify(_token(stranger, kid="inventato"))

    assert jwks.calls == 1


def test_a_supabase_outage_is_survived_with_the_keys_already_read(verifier, keys, jwks, clock):
    token = _token(keys[0])
    verifier.verify(token)
    jwks.down = True

    clock.now += 600 + 1  # chiavi scadute, Supabase giu': si usano quelle lette
    assert verifier.verify(token).subject == SUBJECT
    calls = jwks.calls
    for _ in range(10):
        verifier.verify(token)
    # Un tentativo ogni 30 secondi, non uno per richiesta.
    assert jwks.calls == calls


def test_after_the_stale_limit_every_token_is_refused(verifier, keys, jwks, clock):
    token = _token(keys[0])
    verifier.verify(token)
    jwks.down = True

    clock.now += 3600
    with pytest.raises(IdentityProviderUnavailable):
        verifier.verify(token)


def test_without_ever_reading_the_keys_nothing_is_accepted(verifier, keys, jwks):
    jwks.down = True

    with pytest.raises(IdentityProviderUnavailable):
        verifier.verify(_token(keys[0]))
