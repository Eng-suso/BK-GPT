"""Dove sono andati i soldi. Il registro dei consumi, letto.

    uv run python scripts/llm_spend.py                 # gli ultimi 7 giorni
    uv run python scripts/llm_spend.py ieri
    uv run python scripts/llm_spend.py per task        # o model, operation_kind, ...
    uv run python scripts/llm_spend.py retry
    uv run python scripts/llm_spend.py ragionamento
    uv run python scripts/llm_spend.py as-is

Perche' esiste. Il gateway scrive una riga per ogni chiamata dal 24/09, ma
scrivere non e' sapere: finche' nessuno legge quella tabella, "dove sono andati
i soldi ieri" resta un'indagine dentro psql, cioe' esattamente la cosa che il
18/09 non siamo riusciti a fare quando il credito e' finito.

**Come leggere quello che stampa.** Ogni totale porta una riga di copertura, ed
e' la prima da guardare. `cost_estimate` e' `NULL` per i modelli senza prezzo
configurato, e quei modelli esistono davvero (la trascrizione si paga al minuto,
non a token). Con una copertura del 40% il costo stampato e' meno della meta'
della spesa vera: il numero non e' sbagliato, e' parziale, e la differenza fra
le due cose e' tutta nella riga che te lo dice.

I prezzi si configurano in `LLM_PRICES_JSON` (`.env`), per milione di token.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.llm import ledger  # noqa: E402


def _soldi(valore: Decimal) -> str:
    """Il denaro con quattro decimali: le singole chiamate costano millesimi."""
    return f"{valore:.4f}"


def _token(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _copertura(totale: ledger.Totale) -> str:
    """La riga che impedisce di leggere un totale parziale come se fosse tutto."""
    quota = totale.copertura_prezzo
    if quota is None:
        return "  copertura prezzo: nessun token nella finestra"
    if totale.righe_senza_prezzo == 0:
        return "  copertura prezzo: 100% (ogni modello ha un prezzo configurato)"
    return (
        f"  copertura prezzo: {quota:.0%} dei token - "
        f"{totale.righe_senza_prezzo} righe senza prezzo, "
        f"{_token(totale.token_senza_prezzo)} token non valorizzati"
    )


def _stampa_totale(titolo: str, totale: ledger.Totale) -> None:
    print(f"\n{titolo}")
    print(f"  costo noto: {_soldi(totale.costo_noto)}")
    print(
        f"  {totale.righe} righe - {totale.chiamate} chiamate, "
        f"{totale.evitate} evitate dalla cache, {totale.fallite} fallite"
    )
    print(
        f"  token: {_token(totale.input)} in ({_token(totale.cached)} da cache), "
        f"{_token(totale.output)} out ({_token(totale.reasoning)} di ragionamento)"
    )
    print(_copertura(totale))


def _stampa_voci(titolo: str, voci: list[ledger.Voce], limite: int = 15) -> None:
    print(f"\n{titolo}")
    if not voci:
        print("  (nessuna riga nella finestra)")
        return
    larghezza = max(len(v.chiave) for v in voci[:limite])
    for voce in voci[:limite]:
        t = voce.totale
        nota = "" if t.righe_senza_prezzo == 0 else f"  [{t.righe_senza_prezzo} senza prezzo]"
        print(
            f"  {voce.chiave.ljust(larghezza)}  {_soldi(t.costo_noto):>10}  "
            f"{_token(t.token_totali):>12} tok  {t.righe:>5} righe{nota}"
        )
    if len(voci) > limite:
        print(f"  ... e altre {len(voci) - limite}")


def _comando_riepilogo(args) -> None:
    _stampa_totale(f"Ultimi {args.giorni} giorni", ledger.totale(giorni=args.giorni))
    _stampa_voci("Per giorno", ledger.per_giorno(giorni=args.giorni))
    _stampa_voci("Per compito", ledger.per("task", giorni=args.giorni))
    _stampa_voci("Per modello", ledger.per("model", giorni=args.giorni))
    _stampa_voci("Per tipo di lavoro", ledger.per("operation_kind", giorni=args.giorni))


def _comando_ieri(_args) -> None:
    giorni = ledger.per_giorno(giorni=2)
    if not giorni:
        print("Nessuna riga: o non si e' speso niente, o il registro non ha ricevuto scritture.")
        return
    _stampa_totale(f"Giorno {giorni[0].chiave}", giorni[0].totale)
    if len(giorni) > 1:
        _stampa_totale(f"Giorno precedente ({giorni[1].chiave}), per confronto", giorni[1].totale)
    _stampa_voci("Per compito", ledger.per("task", giorni=2))


def _comando_per(args) -> None:
    if args.dimensione not in ledger.DIMENSIONI:
        print(f"Dimensione sconosciuta. Disponibili: {', '.join(sorted(ledger.DIMENSIONI))}")
        raise SystemExit(2)
    _stampa_voci(
        f"Per {args.dimensione}, ultimi {args.giorni} giorni",
        ledger.per(args.dimensione, giorni=args.giorni),
    )


def _comando_retry(args) -> None:
    r = ledger.costo_dei_retry(giorni=args.giorni)
    print(f"\nRitentativi, ultimi {args.giorni} giorni")
    print(f"  primi tentativi: {r.primi_tentativi}")
    print(f"  ritentativi:     {r.ritentativi}")
    print(f"  costo dei soli ritentativi: {_soldi(r.costo_ritentativi)}")
    print(f"  token dei soli ritentativi: {_token(r.token_ritentativi)}")
    if r.ritentativi == 0:
        print("  (nessun retry: o non servono, o `retry` e' spento dove dovrebbe essere acceso)")


def _comando_ragionamento(args) -> None:
    pesi = ledger.peso_del_ragionamento(giorni=args.giorni)
    print(f"\nQuanto ragionamento paga ogni compito, ultimi {args.giorni} giorni")
    if not pesi:
        print("  (nessuna riga nella finestra)")
        return
    larghezza = max(len(p.task) for p in pesi)
    for p in pesi:
        quota = "-" if p.quota is None else f"{p.quota:.0%}"
        print(
            f"  {p.task.ljust(larghezza)}  effort={str(p.reasoning_effort or '?'):<7} "
            f"ragionamento {quota:>5} di {_token(p.output_tokens)} token di uscita"
        )
    print(
        "\n  Una quota alta su un compito che risponde dentro uno schema strict e'"
        "\n  il primo posto dove abbassare l'effort: li' lo schema fa il lavoro."
    )


def _comando_as_is(args) -> None:
    k = ledger.costo_per_as_is_validato(giorni=args.giorni)
    print(f"\nCosto per AS-IS validato, ultimi {args.giorni} giorni")
    print(f"  validazioni misurabili: {k.validazioni}")
    if k.non_misurabili:
        print(
            f"  non misurabili: {k.non_misurabili} "
            "(approvate prima che il registro esistesse: spesa che non abbiamo,"
            " non spesa zero)"
        )
    medio = k.costo_medio
    print(f"  costo medio: {'-' if medio is None else _soldi(medio)}")
    print(f"  costo attribuito in totale: {_soldi(k.costo_noto)} su {_token(k.token)} token")
    if k.righe_senza_prezzo:
        print(f"  di cui {k.righe_senza_prezzo} righe senza prezzo configurato")
    if k.senza_attribuzione:
        print(
            f"  attenzione: {k.senza_attribuzione} righe della finestra non hanno `process_id`."
            "\n  Non entrano in questo KPI, quindi il costo per AS-IS e' sottostimato:"
            "\n  il numero da sistemare e' l'attribuzione, non il KPI."
        )


def _comando_listino(args) -> None:
    import json

    modelli = ledger.modelli_da_prezzare(giorni=args.giorni)
    print(f"\nModelli che hanno girato, ultimi {args.giorni} giorni")
    if not modelli:
        print("  (nessuna riga nella finestra)")
        return

    larghezza = max(len(m.model) for m in modelli)
    mancanti = [m for m in modelli if not m.prezzato]
    for m in modelli:
        segno = "ok   " if m.prezzato else "MANCA"
        print(f"  {segno}  {m.model.ljust(larghezza)}  {_token(m.token):>12} tok  {m.righe:>5} righe")

    if not mancanti:
        print("\n  Ogni modello che ha girato ha un prezzo: i totali sono completi.")
        return

    print(
        f"\n  {len(mancanti)} modelli senza prezzo: le loro righe hanno `cost_estimate` NULL,"
        "\n  quindi il costo stampato altrove e' parziale. Da incollare in `LLM_PRICES_JSON`"
        "\n  (.env), in valuta per MILIONE di token, coi prezzi veri del fornitore:"
    )
    scheletro = {
        m.model: {"input": 0.0, "output": 0.0, "cached_input": 0.0}
        for m in mancanti
        # Un modello che si paga al minuto non va a listino: a zero token
        # darebbe un costo di zero, plausibile e falso.
        if m.token > 0
    }
    print("\n" + json.dumps(scheletro, indent=2))
    al_minuto = [m.model for m in mancanti if m.token == 0]
    if al_minuto:
        print(
            "\n  Fuori dallo scheletro perche' non dichiarano token (si pagano a tempo,"
            f"\n  non a token): {', '.join(al_minuto)}."
            "\n  Per questi il costo resta NULL di proposito: lo dice la fattura."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--giorni", type=int, default=7, help="Ampiezza della finestra (default 7).")
    sub = parser.add_subparsers(dest="comando")

    sub.add_parser("riepilogo", help="Totale, per giorno, per compito, per modello (default).")
    sub.add_parser("ieri", help="Il giorno piu' recente, col precedente per confronto.")
    p_per = sub.add_parser("per", help="Raggruppa per una dimensione.")
    p_per.add_argument("dimensione", help=f"Una fra: {', '.join(sorted(ledger.DIMENSIONI))}")
    sub.add_parser("retry", help="Quanto costano i ritentativi.")
    sub.add_parser("ragionamento", help="Quanta uscita e' ragionamento, per compito.")
    sub.add_parser("as-is", help="Il KPI: quanto costa un AS-IS validato.")
    sub.add_parser("listino", help="Quali modelli hanno girato e quali prezzi mancano.")

    args = parser.parse_args()
    comandi = {
        None: _comando_riepilogo,
        "riepilogo": _comando_riepilogo,
        "ieri": _comando_ieri,
        "per": _comando_per,
        "retry": _comando_retry,
        "ragionamento": _comando_ragionamento,
        "as-is": _comando_as_is,
        "listino": _comando_listino,
    }
    comandi[args.comando](args)
    print()


if __name__ == "__main__":
    main()
