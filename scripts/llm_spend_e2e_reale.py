"""Un'ingestione vera, col modello vero, per vedere la misura funzionare.

    uv run python scripts/llm_spend_e2e_reale.py --conferma

**Questo script spende soldi veri.** Senza `--conferma` non chiama niente e si
limita a dire cosa farebbe e quanto costerebbe, coi prezzi configurati.

Perche' esiste. Tutto P1 e' verificato contro un confine di rete finto: i test
dimostrano che, dato un fornitore che risponde cosi', la riga nel registro viene
cosi'. Quello che nessun test con un doppio puo' dimostrare e' che le risposte
vere abbiano la forma che ci aspettiamo - che `usage_metadata` arrivi davvero,
che i token siano dove crediamo, che il modello configurato esista. Finche' non
gira una chiamata pagata, P1 e' verificato come codice e non come misura.

Il percorso e' quello del prodotto, non una simulazione: `build_process_
understanding` estrae il piano dall'intervista e ne fa valutare la qualita',
esattamente come quando un consulente carica una fonte. L'unica cosa aggiunta e'
l'operazione attorno, che nel prodotto la apre il worker.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Prima di importare qualunque cosa che tocchi langchain: il tracing va spento.
# Alla prima esecuzione vera il tenant LangSmith aveva gia' superato il suo
# limite mensile di 5.000 tracce, e ogni chiamata ha prodotto un muro di 429 che
# sommergeva l'output. Uno strumento che serve a misurare non puo' dipendere da
# un servizio esterno per funzionare, e P0.5 del piano dice comunque di spegnerlo.
# `--con-tracing` lo riaccende per chi lo vuole.
if "--con-tracing" not in sys.argv:
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.llm import OperationKind, operation  # noqa: E402
from backend.llm import ledger  # noqa: E402
from backend.settings import settings  # noqa: E402

# Un'intervista corta ma vera: un processo con attori, decisioni, un'eccezione e
# un paio di buchi. Serve a far lavorare l'estrazione come lavora davvero, non a
# farle produrre il risultato piu' bello.
INTERVISTA = """
Allora, il ciclo dell'ordine da noi parte quando arriva la richiesta dal cliente,
di solito via mail all'ufficio commerciale. Maria del commerciale la prende in
carico e per prima cosa controlla se il cliente e' gia' a sistema: se e' nuovo
bisogna aprire l'anagrafica, e li' serve il benestare dell'amministrazione
perche' vogliono verificare il fido.

Se il cliente c'e' gia', Maria prepara l'offerta. Sotto i diecimila euro la firma
lei, sopra deve passare dal direttore commerciale. Il direttore a volte e' in
viaggio e lì si perde qualche giorno, e' uno dei punti dove ci lamentiamo di piu'.

Quando l'offerta torna firmata la mandiamo al cliente e aspettiamo la conferma.
Se il cliente conferma, si apre l'ordine di produzione: lo fa Luca della
produzione, che controlla la disponibilita' dei materiali a magazzino. Se manca
qualcosa parte una richiesta di acquisto all'ufficio acquisti.

La produzione poi schedula, e a fine lavorazione il collaudo verifica. Se il
collaudo non passa il pezzo torna in lavorazione, e se non passa due volte si
apre una non conformita' formale che va avanti con un'altra procedura.

Alla fine si spedisce e l'amministrazione fattura. La fattura la emettono a fine
mese tutte insieme, non ordine per ordine.
""".strip()

TITOLO = "Order to Cash - intervista di prova (spesa reale)"


def _stima() -> None:
    """Quanto costera', per quel poco che si puo' dire prima di farlo.

    **Lezione della prima esecuzione vera, 25/09.** Stimando i token
    dall'intervista (1.244 caratteri, ~311 token) veniva ~$0.0011. Il registro
    ne ha contati **20.670 in ingresso** e il costo vero e' stato $0.0132: dodici
    volte tanto. L'intervista non e' l'input - lo sono il prompt di sistema, lo
    schema di risposta e il piano gia' estratto che il giudizio di qualita' si
    rilegge. Una stima a priori sui caratteri della fonte sbaglia di un ordine di
    grandezza, e per P3 (budget con prenotazione) conta: la prenotazione non puo'
    basarsi sulla lunghezza dell'input.

    Resta stampata perche' mostrare la distanza fra la stima e il registro e' piu'
    utile che non stimare affatto.
    """
    from backend.llm.prices import price_for

    prezzo = price_for(settings.openai_model)
    caratteri = len(INTERVISTA)
    token_in = caratteri // 4
    print(f"\nModello: {settings.openai_model}")
    print(f"Intervista: {caratteri} caratteri, ~{token_in} token")
    if prezzo is None:
        print("Prezzo non configurato: il costo reale lo dira' la fattura, non questo script.")
        return
    ingenua = (token_in * 2 * prezzo.input + token_in * 4 * prezzo.output) / 1_000_000
    print(f"Stima ingenua sui soli caratteri della fonte: ~${ingenua:.4f}")
    print("Il 25/09 il costo vero e' stato ~12x questa stima: l'input e' il prompt,")
    print("non l'intervista. Il numero che conta e' quello del registro, sotto.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--conferma",
        action="store_true",
        help="Esegue davvero le chiamate al fornitore. Senza, e' solo una stima.",
    )
    parser.add_argument(
        "--con-tracing",
        action="store_true",
        help="Lascia acceso LangSmith (di default e' spento: la quota e' esaurita).",
    )
    args = parser.parse_args()

    if not settings.openai_api_key:
        print("OPENAI_API_KEY non configurata: non c'e' niente da provare.")
        raise SystemExit(1)

    _stima()

    if not args.conferma:
        print("\nProva a vuoto. Per eseguire davvero: --conferma")
        return

    from backend.process_understanding import build_process_understanding

    inizio = datetime.now(UTC).isoformat()
    print("\nChiamo il modello vero...")

    # L'operazione la apre il worker, nel prodotto. Qui la apre lo script, con lo
    # stesso tipo: senza, il gateway rifiuta - ed e' il comportamento giusto.
    with operation(OperationKind.PLAN_SYNTHESIS, project_id="e2e-reale", process_id="e2e-reale"):
        risultato = build_process_understanding(TITOLO, INTERVISTA, with_quality_report=True)

    if risultato.process is None:
        print(f"\nEstrazione non riuscita: {risultato.failure}")
    else:
        processo = risultato.process
        print("\nEstrazione riuscita.")
        # I nomi dei campi sono quelli dello schema (`steps`, `unknowns`), non
        # quelli che verrebbero in mente: alla prima esecuzione questo blocco
        # leggeva `activities` e `open_questions`, che non esistono, e stampava
        # zero su un'estrazione andata benissimo. Un difetto dello script che
        # sembrava un difetto del prodotto.
        for campo in ("steps", "actors", "decisions", "exceptions", "unknowns", "flow_edges"):
            print(f"  {campo}: {len(getattr(processo, campo, []) or [])}")

    fine = datetime.now(UTC).isoformat()
    print("\n--- Il registro, per questa finestra ---")
    totale = ledger.totale(since=inizio, until=fine)
    print(f"  righe: {totale.righe}, chiamate: {totale.chiamate}, fallite: {totale.fallite}")
    print(f"  token: {totale.input} in, {totale.output} out ({totale.reasoning} di ragionamento)")
    print(f"  costo: ${totale.costo_noto}")
    quota = totale.copertura_prezzo
    print(f"  copertura prezzo: {'-' if quota is None else f'{quota:.0%}'}")

    for voce in ledger.per("task", since=inizio, until=fine):
        t = voce.totale
        print(f"    {voce.chiave}: ${t.costo_noto} su {t.token_totali} token")

    for voce in ledger.per("prompt_version", since=inizio, until=fine):
        print(f"    prompt {voce.chiave}: {voce.totale.righe} righe")


if __name__ == "__main__":
    main()
