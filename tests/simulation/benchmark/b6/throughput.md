# Throughput del simulatore (B6)

What-if: 10 ripetizioni x 1000 casi, scenario Loan_Application, seed 20261124. Meta: meno di 60 s dalla richiesta al risultato riletto (KPI e log di tutte le ripetizioni).
Tempi dall'invio della richiesta; le fasi sono la media per run.

| Worker | Giro | Totale (s) | Run/min | Accettato (s) | Tutti completati (s) | KPI letti (s) | in coda (s) | motore (s) | analisi (s) | salvataggio (s) | Meta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 22.9 | 26.2 | 0.14 | 19.9 | 20.0 | 8.72 | 1.63 | 0.17 | 0.08 | raggiunta |
| 1 | 2 | 26.1 | 23.0 | 0.11 | 21.9 | 22.1 | 9.43 | 1.84 | 0.21 | 0.08 | raggiunta |
| 1 | 3 | 24.9 | 24.1 | 0.15 | 20.8 | 20.9 | 9.13 | 1.77 | 0.19 | 0.07 | raggiunta |
| 2 | 1 | 14.3 | 42.0 | 0.13 | 10.6 | 10.7 | 4.02 | 1.64 | 0.18 | 0.11 | raggiunta |
| 2 | 2 | 14.5 | 41.3 | 0.11 | 10.9 | 11.0 | 4.35 | 1.76 | 0.20 | 0.09 | raggiunta |
| 2 | 3 | 14.5 | 41.4 | 0.12 | 10.7 | 10.8 | 4.17 | 1.72 | 0.20 | 0.13 | raggiunta |
| 4 | 1 | 11.5 | 52.2 | 0.14 | 8.0 | 8.1 | 2.33 | 1.95 | 0.37 | 0.15 | raggiunta |
| 4 | 2 | 11.5 | 52.2 | 0.10 | 8.0 | 8.1 | 2.13 | 1.92 | 0.33 | 0.20 | raggiunta |
| 4 | 3 | 11.3 | 53.1 | 0.12 | 7.9 | 8.1 | 2.18 | 1.82 | 0.53 | 0.20 | raggiunta |
