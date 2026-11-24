"""Verifica degli access token di Supabase Auth.

Supabase dice *chi sei*; cosa puoi fare lo decide DeliR (membership, ruoli:
Track B2/B3). Questo modulo fa solo la prima parte, e la fa fail closed:

- firma solo ES256, con le chiavi pubbliche del progetto (JWKS). `none`, HS256
  e ogni altro algoritmo vengono rifiutati, anche se la firma tornerebbe;
- `iss` deve essere esattamente l'Auth del progetto configurato, `aud`
  `authenticated`, `role` `authenticated`, `is_anonymous` falso, `sub` un UUID;
- `exp` e `iat` obbligatori, con 60 secondi di tolleranza sugli orologi.

Le chiavi pubbliche stanno in memoria e si rileggono ogni `ttl` secondi, o
subito quando arriva un `kid` mai visto (rotazione). Se Supabase non risponde
si continua con le chiavi gia' lette per al massimo `max_stale` secondi, poi
si rifiuta tutto: un'identita' che non si puo' verificare non e' un'identita'.
Mai su disco: una cache lunga renderebbe inutile la revoca di una chiave.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import jwt
from jwt import PyJWK

ALGORITHMS = ["ES256"]
LEEWAY_SECONDS = 60
#: Un `kid` sconosciuto rilegge le chiavi, ma non piu' spesso di cosi': un
#: client che manda token con `kid` inventati non deve trasformare ogni sua
#: richiesta in una chiamata a Supabase.
UNKNOWN_KID_REFRESH_SECONDS = 30.0
JWKS_TIMEOUT_SECONDS = 5.0


class InvalidAccessToken(Exception):
    """Il token non prova un'identita'. Il messaggio non contiene il token."""


class IdentityProviderUnavailable(Exception):
    """Le chiavi pubbliche non sono leggibili da troppo tempo: si rifiuta."""


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    """Cio' che un access token valido dice di chi chiama."""

    #: L'id dell'utente in Supabase (`sub`): il legame stabile con la membership.
    subject: str
    #: La sessione Supabase (`session_id`), per log e audit.
    session_id: str | None
    email: str | None


def _fetch_jwks(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=JWKS_TIMEOUT_SECONDS) as response:
        return json.loads(response.read())


class JwksCache:
    """Le chiavi pubbliche del progetto, per `kid`, con le regole del modulo."""

    def __init__(
        self,
        url: str,
        *,
        ttl_seconds: float,
        max_stale_seconds: float,
        fetch: Callable[[str], dict] = _fetch_jwks,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = url
        self._ttl = ttl_seconds
        self._max_stale = max_stale_seconds
        self._fetch = fetch
        self._clock = clock
        self._keys: dict[str, PyJWK] = {}
        self._loaded_at: float | None = None
        self._last_attempt: float | None = None
        self._lock = threading.Lock()

    def _refresh(self) -> None:
        self._last_attempt = self._clock()
        document = self._fetch(self._url)
        keys: dict[str, PyJWK] = {}
        for entry in document.get("keys", []):
            # Solo chiavi di firma ES256: una chiave HS o RSA pubblicata per
            # errore non deve diventare un modo di firmare token accettati.
            if entry.get("kid") and entry.get("kty") == "EC" and entry.get("alg", "ES256") == "ES256":
                keys[entry["kid"]] = PyJWK(entry, algorithm="ES256")
        self._keys = keys
        self._loaded_at = self._clock()

    def key_for(self, kid: str) -> PyJWK:
        with self._lock:
            now = self._clock()
            expired = self._loaded_at is None or now - self._loaded_at >= self._ttl
            unknown = kid not in self._keys
            may_retry = (
                self._last_attempt is None
                or now - self._last_attempt >= UNKNOWN_KID_REFRESH_SECONDS
            )
            failure: Exception | None = None
            # Anche il rinnovo a scadenza rispetta l'intervallo fra tentativi:
            # con Supabase giu' non ogni richiesta deve diventare una chiamata.
            if (expired or unknown) and may_retry:
                try:
                    self._refresh()
                except Exception as exc:  # noqa: BLE001 - rete, JSON, chiavi: tutto e' "non disponibile"
                    failure = exc
            now = self._clock()
            if self._loaded_at is None or now - self._loaded_at >= self._max_stale:
                raise IdentityProviderUnavailable(
                    "chiavi pubbliche di Supabase non leggibili"
                ) from failure
            key = self._keys.get(kid)
            if key is None:
                raise InvalidAccessToken("chiave di firma sconosciuta")
            return key


class SupabaseTokenVerifier:
    def __init__(self, supabase_url: str, *, audience: str, jwks: JwksCache) -> None:
        self.issuer = f"{supabase_url.rstrip('/')}/auth/v1"
        self.audience = audience
        self._jwks = jwks

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise InvalidAccessToken("token illeggibile") from exc
        if header.get("alg") not in ALGORITHMS:
            raise InvalidAccessToken("algoritmo non ammesso")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise InvalidAccessToken("token senza kid")

        key = self._jwks.key_for(kid)
        try:
            claims = jwt.decode(
                token,
                key=key.key,
                algorithms=ALGORITHMS,
                audience=self.audience,
                issuer=self.issuer,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidAccessToken(type(exc).__name__) from exc

        if claims.get("role") != "authenticated":
            raise InvalidAccessToken("ruolo non autenticato")
        if claims.get("is_anonymous") is not False:
            raise InvalidAccessToken("sessione anonima")
        try:
            subject = str(uuid.UUID(str(claims["sub"])))
        except ValueError as exc:
            raise InvalidAccessToken("sub non valido") from exc

        session_id = claims.get("session_id")
        email = claims.get("email")
        return VerifiedIdentity(
            subject=subject,
            session_id=session_id if isinstance(session_id, str) else None,
            email=email if isinstance(email, str) else None,
        )


_verifier: SupabaseTokenVerifier | None = None
_verifier_config: tuple | None = None
_verifier_lock = threading.Lock()


def get_verifier() -> SupabaseTokenVerifier:
    """Il verifier della configurazione corrente, con la sua cache di chiavi.

    Si ricrea se la configurazione cambia (nei test, o dopo un reload), cosi'
    una cache non sopravvive al progetto Supabase a cui apparteneva.
    """
    from backend.llm.egress import Destination, require
    from backend.settings import settings

    global _verifier, _verifier_config
    config = (
        settings.supabase_url.rstrip("/"),
        settings.supabase_jwt_audience,
        settings.supabase_jwks_ttl_seconds,
        settings.supabase_jwks_max_stale_seconds,
    )
    with _verifier_lock:
        if _verifier is None or _verifier_config != config:
            # Le chiavi pubbliche si leggono da un host esterno: passa dal
            # registro dell'egress come ogni altra uscita.
            require(Destination.IDENTITY_PROVIDER)
            url, audience, ttl, max_stale = config
            jwks = JwksCache(
                f"{url}/auth/v1/.well-known/jwks.json",
                ttl_seconds=ttl,
                max_stale_seconds=max_stale,
            )
            _verifier = SupabaseTokenVerifier(url, audience=audience, jwks=jwks)
            _verifier_config = config
        return _verifier
