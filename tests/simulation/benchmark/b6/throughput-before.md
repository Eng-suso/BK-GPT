# Throughput del simulatore (B6)

What-if: 10 ripetizioni x 1000 casi, scenario Loan_Application, seed 20261124. Meta: meno di 60 s dalla richiesta al risultato riletto.

| Worker | Giro | Totale (s) | Run/min | Accettato (s) | Tutti completati (s) | in coda media (s) | motore media (s) | analisi media (s) | salvataggio media (s) | Meta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 22.0 | 27.3 | 0.12 | 18.9 | 8.53 | 1.57 | 0.20 | 0.08 | raggiunta |
| 1 | 2 | 21.5 | 27.9 | 0.12 | 18.4 | 8.33 | 1.55 | 0.17 | 0.08 | raggiunta |
| 1 | 3 | 23.6 | 25.4 | 0.10 | 20.4 | 9.17 | 1.72 | 0.19 | 0.09 | raggiunta |
| 2 | 1 | 18.8 | 31.9 | 0.12 | 15.8 | 7.52 | 1.65 | 0.20 | 0.10 | raggiunta |
| 2 | 2 | 14.9 | 40.4 | 0.12 | 11.5 | 4.42 | 1.62 | 0.18 | 0.16 | raggiunta |
| 2 | 3 | 17.1 | 35.0 | 0.11 | 14.2 | 6.48 | 1.65 | 0.21 | 0.12 | raggiunta |
| 4 | 1 | 16.3 | 36.8 | 0.12 | 13.5 | 6.96 | 1.58 | 0.20 | 0.10 | raggiunta |
| 4 | 2 | 11.8 | 50.7 | 0.12 | 8.8 | 4.01 | 1.72 | 0.30 | 0.23 | raggiunta |
| 4 | 3 | 11.5 | 52.3 | 0.10 | 8.7 | 2.99 | 1.72 | 0.35 | 0.19 | raggiunta |
