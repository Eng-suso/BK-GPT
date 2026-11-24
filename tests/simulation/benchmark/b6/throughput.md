# Throughput del simulatore (B6)

What-if: 10 ripetizioni x 1000 casi, scenario Loan_Application, seed 20261124. Meta: meno di 60 s dalla richiesta al risultato riletto (KPI e log di tutte le ripetizioni).
Tempi dall'invio della richiesta; le fasi sono la media per run.

| Worker | Giro | Totale (s) | Run/min | Accettato (s) | Tutti completati (s) | KPI letti (s) | in coda (s) | motore (s) | analisi (s) | salvataggio (s) | Meta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 21.2 | 28.3 | 0.12 | 18.3 | 18.4 | 8.34 | 1.53 | 0.16 | 0.11 | raggiunta |
| 1 | 2 | 21.1 | 28.4 | 0.10 | 17.9 | 18.0 | 7.99 | 1.51 | 0.17 | 0.07 | raggiunta |
| 1 | 3 | 21.4 | 28.1 | 0.14 | 18.1 | 18.2 | 7.90 | 1.52 | 0.16 | 0.08 | raggiunta |
| 2 | 1 | 12.8 | 47.0 | 0.12 | 10.1 | 10.2 | 3.93 | 1.55 | 0.21 | 0.16 | raggiunta |
| 2 | 2 | 12.8 | 47.0 | 0.10 | 9.9 | 10.0 | 3.81 | 1.52 | 0.22 | 0.17 | raggiunta |
| 2 | 3 | 13.5 | 44.5 | 0.10 | 10.4 | 10.5 | 4.18 | 1.64 | 0.19 | 0.17 | raggiunta |
| 4 | 1 | 10.4 | 57.5 | 0.15 | 7.6 | 7.7 | 2.24 | 1.77 | 0.33 | 0.28 | raggiunta |
| 4 | 2 | 10.4 | 57.8 | 0.10 | 7.0 | 7.1 | 2.12 | 1.76 | 0.28 | 0.27 | raggiunta |
| 4 | 3 | 10.7 | 56.0 | 0.11 | 7.2 | 7.3 | 1.99 | 1.81 | 0.22 | 0.24 | raggiunta |
