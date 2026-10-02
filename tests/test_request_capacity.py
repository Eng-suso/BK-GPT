"""Quante richieste il processo regge insieme, e cosa risponde quando e' pieno.

B5. Settantatre rotte su settantasei sono `def` e non `async def`, quindi
girano nel threadpool di anyio. Il suo default e' 40 e non lo aveva scelto
nessuno; un turno di chat ne occupa un posto fino a novanta secondi. Due
conseguenze, e qui si copre la seconda: `/health` era anch'essa sincrona,
quindi con i posti occupati non rispondeva - e il processo veniva dichiarato
morto proprio mentre stava lavorando.
"""

import asyncio
import inspect
import threading

import pytest
from anyio import to_thread

from backend.app import health, size_request_threadpool
from backend.settings import settings


def test_health_does_not_queue_behind_the_slow_routes():
    """`/health` gira nell'event loop, non nel threadpool delle rotte lente."""
    assert inspect.iscoroutinefunction(health), (
        "una `/health` sincrona aspetta il threadpool, cioe' aspetta proprio "
        "i turni di chat che rendono utile chiederlo"
    )


def test_health_answers_while_every_worker_thread_is_busy():
    """La prova vera: tutti i posti occupati, e la risposta arriva lo stesso."""

    async def scenario() -> dict:
        size_request_threadpool()
        limiter = to_thread.current_default_thread_limiter()
        # Un evento di `threading`, non di `asyncio`: i thread occupati devono
        # aspettare fermi. Con un'attesa attiva il test terrebbe impegnate
        # sessantaquattro CPU per dimostrare una cosa che non c'entra.
        release = threading.Event()

        def occupy() -> None:
            release.wait(timeout=30)

        # Occupa ogni posto del threadpool con lavoro che non finisce da solo.
        busy = [
            asyncio.create_task(to_thread.run_sync(occupy, abandon_on_cancel=True))
            for _ in range(limiter.total_tokens)
        ]
        await asyncio.sleep(0.2)

        try:
            return await asyncio.wait_for(health(), timeout=2.0)
        finally:
            release.set()
            await asyncio.gather(*busy, return_exceptions=True)

    assert asyncio.run(scenario()) == {"status": "ok"}


def test_the_number_of_places_is_declared_not_inherited(monkeypatch):
    """Il numero si sceglie, e si puo' alzare senza toccare il codice."""

    async def scenario() -> int:
        return size_request_threadpool()

    monkeypatch.setattr(settings, "api_worker_threads", 96)
    assert asyncio.run(scenario()) == 96

    # Un valore assurdo non porta il processo a zero posti: sotto un minimo
    # ragionevole, il minimo vince.
    monkeypatch.setattr(settings, "api_worker_threads", 1)
    assert asyncio.run(scenario()) == 8


@pytest.mark.parametrize("value", [64, 128])
def test_the_limiter_really_takes_the_value(monkeypatch, value):
    async def scenario() -> float:
        size_request_threadpool()
        return to_thread.current_default_thread_limiter().total_tokens

    monkeypatch.setattr(settings, "api_worker_threads", value)
    assert asyncio.run(scenario()) == value
