# G3b: benchmark dei motori scientifici

Generato da `tests/simulation/benchmark/g3b/report.py` dai file in `results/`.
Distanze di B2 (tempi in ore, NGD in [0, 1]): media ± semiampiezza IC 95% su 10 repliche;
(NV) = NOT VALIDATED sul periodo (PROTOCOL.md §4): calcolata, non conta. Più basso è meglio.

## Verdetti delle schede

| Componente | Fase | Verdetto | Motivi |
| --- | --- | --- | --- |
| Arrivi (AT-KDE) | validation | **NOT VALIDATED** | CAR identificabile in 1 log |
| Arrivi (AT-KDE) | test | **NOT VALIDATED** | CAR identificabile in 0 log |
| Attese (ritardi estranei) | validation | **NOT VALIDATED** | RED identificabile in 1 log |
| Attese (ritardi estranei) | test | **NOT VALIDATED** | RED identificabile in 0 log |
| Calendari delle risorse | validation | **NOT VALIDATED** | CED identificabile in 1 log |
| Calendari delle risorse | test | **NOT VALIDATED** | CED identificabile in 0 log |
| Control flow e risorse condizionali | validation | **NOT VALIDATED** | NGD identificabile in 1 log |
| Control flow e risorse condizionali | test | **NOT VALIDATED** | NGD identificabile in 0 log |
| Approccio intero: ProSiT | validation | **NOT VALIDATED** | W1 identificabile in 1 log |
| Approccio intero: ProSiT | test | **NOT VALIDATED** | W1 identificabile in 0 log |
| Approccio intero: AgentSimulator | validation | **NOT VALIDATED** | W1 identificabile in 1 log |
| Approccio intero: AgentSimulator | test | **NOT VALIDATED** | W1 identificabile in 0 log |

## Metriche, fase validation

### Loan_Application

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 31.2 ± 1.9 | 0.108 ± 0.023 | 22.4 ± 2.2 | 110 ± 7.1 | 0.501 ± 0.065 | 96.6 ± 4.8 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 36.5 ± 3.2 | 0.121 ± 0.02 | 21.9 ± 2.7 | 16.4 ± 2.7 | 0.64 ± 0.069 | 5.13 ± 1.7 | 138 s, 1071 MB, 0.2 s/replica |
| SIMOD con ritardi estranei | 32.8 ± 3.3 | 0.174 ± 0.015 | 22.9 ± 2.4 | 17.7 ± 2 | 0.688 ± 0.049 | 4.98 ± 1.9 | 237 s, 1071 MB, 0.3 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | fallito | fallito | fallito | fallito | fallito | fallito | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 22.2 ± 2.6 | 0.155 ± 0.017 | 17.1 ± 1.2 | 20.7 ± 2 | 0.532 ± 0.052 | 22.5 ± 0.81 | 237 s, 1071 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 73.2 ± 0.36 | 0.199 ± 0.0082 | 52.5 ± 0.21 | 47.3 ± 3.7 | 6.45 ± 1.3 | 4.83 ± 1.7 | 237 s, 1071 MB, 0.2 s/replica |
| ProSiT con regole (profondita' 3) | 24.2 ± 2.5 | 0.266 ± 0.018 | 15.6 ± 1.6 | 12.8 ± 3.5 | 0.552 ± 0.068 | 5.38 ± 2.2 | 7 s, 938 MB, 0.1 s/replica |
| ProSiT senza regole (profondita' 0) | 24.2 ± 2.8 | 0.334 ± 0.011 | 16.4 ± 2.2 | 13.4 ± 3.8 | 0.487 ± 0.086 | 4.25 ± 1.7 | 4 s, 904 MB, 0.0 s/replica |
| AgentSimulator (scelta automatica) | 41.2 ± 3.1 | 0.0759 ± 0.012 | 31.2 ± 2.7 | 19.6 ± 1.7 | 3.68 ± 0.022 | 10.7 ± 1.7 | 30 s, 730 MB, 0.6 s/replica |


## Metriche, fase test

### Loan_Application

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
