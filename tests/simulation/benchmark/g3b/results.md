# G3b: benchmark dei motori scientifici

Generato da `tests/simulation/benchmark/g3b/report.py` dai file in `results/`.
Distanze di B2 (tempi in ore, NGD in [0, 1]): media ± semiampiezza IC 95% su 10 repliche;
(NV) = NOT VALIDATED sul periodo (PROTOCOL.md §4): calcolata, non conta. Più basso è meglio.

## Verdetti delle schede

| Componente | Fase | Verdetto | Motivi |
| --- | --- | --- | --- |
| Arrivi (AT-KDE) | validation | **NO-GO** | contro naive: CAR vince su 7/23 log; contro naive: CAR perde su 16 log (bpic2012, Insurance_Claims, Insurance_Claims_1_timer, ...); contro naive: guardia W1 perde su 21 log; contro naive: guardia NGD perde su 23 log; contro naive: guardia RED perde su 21 log; contro naive: guardia AED perde su 16 log; contro naive: guardia CED perde su 21 log; contro simod_extr: CAR vince su 0/23 log; contro simod_extr: CAR perde su 17 log (BPIC_2012_W, BPIC_2017_W, Insurance_Claims, ...); contro simod_extr: guardia W1 perde su 15 log; contro simod_extr: guardia NGD perde su 15 log; contro simod_extr: guardia RED perde su 15 log; contro simod_extr: guardia AED perde su 17 log; contro simod_extr: guardia CED perde su 16 log; candidato non misurato (fallito, fuori budget o non applicabile) su 16 log (bpic2012, Insurance_Claims, Insurance_Claims_1_timer, ...); VAL-01 non superato su bpic2013_incidents |
| Arrivi (AT-KDE) | test | **INCOMPLETO** | contro naive: CAR vince su 6/24 log; contro naive: CAR perde su 14 log (AcademicCredentials, BPIC_2012_W, BPIC_2017_W, ...); contro naive: guardia W1 perde su 17 log; contro naive: guardia NGD perde su 23 log; contro naive: guardia RED perde su 17 log; contro naive: guardia AED perde su 20 log; contro naive: guardia CED perde su 24 log; contro simod_extr: base mancante su bpic2012; contro simod_extr: CAR vince su 3/24 log; contro simod_extr: CAR perde su 12 log (BPIC_2012_W, BPIC_2017_W, Insurance_Claims, ...); contro simod_extr: guardia W1 perde su 10 log; contro simod_extr: guardia NGD perde su 10 log; contro simod_extr: guardia RED perde su 10 log; contro simod_extr: guardia AED perde su 12 log; contro simod_extr: guardia CED perde su 12 log; candidato non misurato (fallito, fuori budget o non applicabile) su 13 log (AcademicCredentials, bpic2012, bpic2013_incidents, ...) |
| Attese (ritardi estranei) | validation | **NO-GO** | contro naive: RED vince su 5/23 log; contro naive: RED perde su 16 log (bpic2012, Insurance_Claims, Insurance_Claims_1_timer, ...); contro naive: guardia W1 perde su 16 log; contro naive: guardia NGD perde su 16 log; contro naive: guardia AED perde su 11 log; contro naive: guardia CED perde su 11 log; contro naive: guardia CAR perde su 10 log; contro simod: RED vince su 4/23 log; contro simod: RED perde su 6 log (Insurance_Claims, Insurance_Claims_1_timer, Insurance_Claims_3_timers, ...); contro simod: guardia W1 perde su 7 log; contro simod: guardia NGD perde su 5 log; contro simod: guardia AED perde su 3 log; contro simod: guardia CED perde su 5 log; contro simod: guardia CAR perde su 3 log; contro simod: tempo o memoria oltre il doppio su 2 log; candidato non misurato (fallito, fuori budget o non applicabile) su bpic2012; VAL-01 non superato su bpic2013_incidents |
| Attese (ritardi estranei) | test | **NO-GO** | contro naive: RED vince su 6/23 log; contro naive: RED perde su 17 log (AcademicCredentials, BPIC_2012_W, Insurance_Claims, ...); contro naive: guardia W1 perde su 17 log; contro naive: guardia NGD perde su 22 log; contro naive: guardia AED perde su 20 log; contro naive: guardia CED perde su 16 log; contro naive: guardia CAR perde su 14 log; contro simod: RED vince su 4/23 log; contro simod: RED perde su AcademicCredentials, Procure_to_Pay_5_timers, Procure_to_Pay_5_timers_after; contro simod: guardia W1 perde su 4 log; contro simod: guardia NGD perde su 6 log; contro simod: guardia AED perde su 5 log; contro simod: guardia CED perde su 5 log; contro simod: guardia CAR perde su 4 log; contro simod: tempo o memoria oltre il doppio su 3 log; candidato non misurato (fallito, fuori budget o non applicabile) su AcademicCredentials, bpic2012, bpic2013_incidents |
| Calendari delle risorse | validation | **NO-GO** | contro naive: CED vince su 6/25 log; contro naive: CED perde su 11 log (AcademicCredentials, BPIC_2012_W, BPIC_2017_W, ...); contro naive: guardia W1 perde su 16 log; contro naive: guardia NGD perde su 16 log; contro naive: guardia RED perde su 16 log; contro naive: guardia AED perde su 11 log; contro naive: guardia CAR perde su 10 log; contro simod_extr_247: CED perde su 7 log (AcademicCredentials, Insurance_Claims_5_timers, Pharmacy, ...); contro simod_extr_247: guardia W1 perde su 17 log; contro simod_extr_247: guardia NGD perde su 4 log; contro simod_extr_247: guardia RED perde su 14 log; contro simod_extr_247: guardia AED perde su 9 log; contro simod_extr_247: guardia CAR perde su 4 log; candidato non misurato (fallito, fuori budget o non applicabile) su bpic2012; VAL-01 non superato su bpic2013_incidents |
| Calendari delle risorse | test | **INCOMPLETO** | contro naive: CED vince su 2/25 log; contro naive: CED perde su 16 log (AcademicCredentials, BPIC_2012_W, BPIC_2017_W, ...); contro naive: guardia W1 perde su 17 log; contro naive: guardia NGD perde su 22 log; contro naive: guardia RED perde su 17 log; contro naive: guardia AED perde su 20 log; contro naive: guardia CAR perde su 14 log; contro simod_extr_247: base mancante su bpic2012, bpic2013_incidents; contro simod_extr_247: CED vince su 12/25 log; contro simod_extr_247: CED perde su 10 log (Insurance_Claims, Insurance_Claims_1_timer, Insurance_Claims_3_timers, ...); contro simod_extr_247: guardia W1 perde su 16 log; contro simod_extr_247: guardia NGD perde su 4 log; contro simod_extr_247: guardia RED perde su 15 log; contro simod_extr_247: guardia AED perde su 15 log; contro simod_extr_247: guardia CAR perde su 3 log; candidato non misurato (fallito, fuori budget o non applicabile) su AcademicCredentials, bpic2012, bpic2013_incidents |
| Control flow e risorse condizionali | validation | **NO-GO** | contro naive: NGD vince su 0/23 log; contro naive: NGD perde su 7 log (BPIC_2017_W, bpic2012, Loan_Application, ...); contro naive: guardia W1 perde su 12 log; contro naive: guardia RED perde su 12 log; contro naive: guardia AED perde su 11 log; contro naive: guardia CED perde su 5 log; contro naive: guardia CAR perde su 7 log; contro simod_extr: NGD perde su 5 log (Loan_Application, Loan_Application_1_timer, Loan_Application_3_timers, ...); contro simod_extr: guardia W1 perde su 8 log; contro simod_extr: guardia RED perde su 7 log; contro simod_extr: guardia AED perde su 6 log; contro simod_extr: guardia CED perde su 5 log; contro simod_extr: guardia CAR perde su 2 log; contro prosit_norules: NGD vince su 6/23 log; contro prosit_norules: guardia AED perde su 2 log; contro prosit_norules: guardia CED perde su 3 log; contro prosit_norules: guardia CAR perde su 4 log; contro prosit_norules: tempo o memoria oltre il doppio su 4 log; candidato non misurato (fallito, fuori budget o non applicabile) su AcademicCredentials, bpic2013_incidents |
| Control flow e risorse condizionali | test | **NO-GO** | contro naive: NGD vince su 0/23 log; contro naive: NGD perde su 7 log (AcademicCredentials, BPIC_2017_W, Loan_Application, ...); contro naive: guardia W1 perde su 16 log; contro naive: guardia RED perde su 14 log; contro naive: guardia AED perde su 14 log; contro naive: guardia CED perde su 11 log; contro naive: guardia CAR perde su 13 log; contro simod_extr: NGD perde su 6 log (BPIC_2017_W, Loan_Application, Loan_Application_1_timer, ...); contro simod_extr: guardia W1 perde su 13 log; contro simod_extr: guardia RED perde su 13 log; contro simod_extr: guardia AED perde su 5 log; contro simod_extr: guardia CED perde su 7 log; contro prosit_norules: guardia W1 perde su 4 log; contro prosit_norules: guardia AED perde su 2 log; contro prosit_norules: guardia CED perde su 3 log; contro prosit_norules: guardia CAR perde su 4 log; contro prosit_norules: tempo o memoria oltre il doppio su 5 log; candidato non misurato (fallito, fuori budget o non applicabile) su bpic2012, bpic2013_incidents |
| Approccio intero: ProSiT | validation | **NO-GO** | contro naive: W1 vince su 4/23 log; contro naive: W1 perde su 12 log (BPIC_2017_W, bpic2012, Insurance_Claims, ...); contro naive: guardia NGD perde su 7 log; contro naive: guardia RED perde su 12 log; contro naive: guardia AED perde su 11 log; contro naive: guardia CED perde su 5 log; contro naive: guardia CAR perde su 7 log; contro simod_extr: W1 vince su 8/23 log; contro simod_extr: W1 perde su 8 log (BPIC_2017_W, Insurance_Claims, Insurance_Claims_3_timers, ...); contro simod_extr: guardia NGD perde su 5 log; contro simod_extr: guardia RED perde su 7 log; contro simod_extr: guardia AED perde su 6 log; contro simod_extr: guardia CED perde su 5 log; contro simod_extr: guardia CAR perde su 2 log; candidato non misurato (fallito, fuori budget o non applicabile) su AcademicCredentials, bpic2013_incidents |
| Approccio intero: ProSiT | test | **NO-GO** | contro naive: W1 vince su 0/23 log; contro naive: W1 perde su 16 log (AcademicCredentials, BPIC_2017_W, Insurance_Claims, ...); contro naive: guardia NGD perde su 7 log; contro naive: guardia RED perde su 14 log; contro naive: guardia AED perde su 14 log; contro naive: guardia CED perde su 11 log; contro naive: guardia CAR perde su 13 log; contro simod_extr: W1 vince su 7/23 log; contro simod_extr: W1 perde su 13 log (BPIC_2017_W, Insurance_Claims, Insurance_Claims_1_timer, ...); contro simod_extr: guardia NGD perde su 6 log; contro simod_extr: guardia RED perde su 13 log; contro simod_extr: guardia AED perde su 5 log; contro simod_extr: guardia CED perde su 7 log; candidato non misurato (fallito, fuori budget o non applicabile) su bpic2012, bpic2013_incidents |
| Approccio intero: AgentSimulator | validation | **NO-GO** | contro naive: W1 vince su 5/23 log; contro naive: W1 perde su 12 log (bpic2012, Insurance_Claims, Insurance_Claims_1_timer, ...); contro naive: guardia NGD perde su 11 log; contro naive: guardia RED perde su 13 log; contro naive: guardia AED perde su 14 log; contro naive: guardia CED perde su 16 log; contro naive: guardia CAR perde su 12 log; contro simod_extr: W1 perde su 9 log (Insurance_Claims, Insurance_Claims_1_timer, Insurance_Claims_3_timers, ...); contro simod_extr: guardia NGD perde su 10 log; contro simod_extr: guardia RED perde su 9 log; contro simod_extr: guardia AED perde su 15 log; contro simod_extr: guardia CED perde su 16 log; contro simod_extr: guardia CAR perde su 15 log; candidato non misurato (fallito, fuori budget o non applicabile) su 9 log (AcademicCredentials, bpic2012, bpic2013_incidents, ...); VAL-01 non verificabile: nessun modello di processo |
| Approccio intero: AgentSimulator | test | **NO-GO** | contro naive: W1 vince su 1/23 log; contro naive: W1 perde su 20 log (AcademicCredentials, BPIC_2012_W, Insurance_Claims, ...); contro naive: guardia NGD perde su 19 log; contro naive: guardia RED perde su 19 log; contro naive: guardia AED perde su 15 log; contro naive: guardia CED perde su 19 log; contro naive: guardia CAR perde su 18 log; contro simod_extr: W1 vince su 11/23 log; contro simod_extr: W1 perde su 11 log (BPIC_2012_W, Insurance_Claims, Insurance_Claims_1_timer, ...); contro simod_extr: guardia NGD perde su 10 log; contro simod_extr: guardia RED perde su 11 log; contro simod_extr: guardia AED perde su 14 log; contro simod_extr: guardia CED perde su 15 log; contro simod_extr: guardia CAR perde su 16 log; candidato non misurato (fallito, fuori budget o non applicabile) su 10 log (AcademicCredentials, BPIC_2012_W, bpic2012, ...); VAL-01 non verificabile: nessun modello di processo |

## Primaria contro ogni base

Log dove la primaria è identificabile: vince / pari / perde.

| Componente | Primaria | Base | Validazione | Test |
| --- | --- | --- | --- | --- |
| Arrivi (AT-KDE) | CAR | naive | 7 / 0 / 16 | 6 / 4 / 14 |
| Arrivi (AT-KDE) | CAR | simod_extr | 0 / 6 / 17 | 3 / 8 / 12 |
| Attese (ritardi estranei) | RED | naive | 5 / 2 / 16 | 6 / 0 / 17 |
| Attese (ritardi estranei) | RED | simod | 4 / 13 / 6 | 4 / 16 / 3 |
| Calendari delle risorse | CED | naive | 6 / 8 / 11 | 2 / 7 / 16 |
| Calendari delle risorse | CED | simod_extr_247 | 13 / 5 / 7 | 12 / 1 / 10 |
| Control flow e risorse condizionali | NGD | naive | 0 / 16 / 7 | 0 / 16 / 7 |
| Control flow e risorse condizionali | NGD | simod_extr | 14 / 4 / 5 | 17 / 0 / 6 |
| Control flow e risorse condizionali | NGD | prosit_norules | 6 / 17 / 0 | 12 / 11 / 0 |
| Approccio intero: ProSiT | W1 | naive | 4 / 7 / 12 | 0 / 7 / 16 |
| Approccio intero: ProSiT | W1 | simod_extr | 8 / 7 / 8 | 7 / 3 / 13 |
| Approccio intero: AgentSimulator | W1 | naive | 5 / 6 / 12 | 1 / 2 / 20 |
| Approccio intero: AgentSimulator | W1 | simod_extr | 12 / 2 / 9 | 11 / 1 / 11 |

## Metriche, fase validation

### AcademicCredentials

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 97.5 ± 23 (NV) | 0.237 ± 0.011 (NV) | 45.1 ± 20 (NV) | 201 ± 28 | 2.43 ± 0.17 | 153 ± 12 (NV) | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 112 ± 0.96 (NV) | 0.28 ± 0.013 (NV) | 43.2 ± 0.41 (NV) | 260 ± 12 | 5.95 ± 0.13 | 210 ± 12 (NV) | 143 s, 1085 MB, 0.1 s/replica |
| SIMOD con ritardi estranei | 130 ± 14 (NV) | 0.291 ± 0.019 (NV) | 53.3 ± 9.3 (NV) | 186 ± 15 | 5.63 ± 0.73 | 208 ± 12 (NV) | 214 s, 1085 MB, 0.2 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 134 ± 17 (NV) | 0.288 ± 0.016 (NV) | 57.8 ± 7.9 (NV) | 142 ± 24 | 5.42 ± 0.86 | 156 ± 27 (NV) | 312 s, 1085 MB, 0.1 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 135 ± 12 (NV) | 0.29 ± 0.012 (NV) | 57.5 ± 7.9 (NV) | 199 ± 11 | 5.19 ± 0.88 | 150 ± 12 (NV) | 214 s, 1085 MB, 0.1 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 107 ± 23 (NV) | 0.298 ± 0.014 (NV) | 43.2 ± 9 (NV) | 201 ± 14 | 4.5 ± 0.17 | 215 ± 13 (NV) | 214 s, 1085 MB, 0.1 s/replica |
| ProSiT con regole (profondita' 3) | fallito | fallito | fallito | fallito | fallito | fallito | — |
| ProSiT senza regole (profondita' 0) | 81.1 ± 19 (NV) | 0.695 ± 0.017 (NV) | 105 ± 27 (NV) | 176 ± 13 | 3.32 ± 0.25 | 211 ± 16 (NV) | 6 s, 943 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | fallito | fallito | fallito | fallito | fallito | fallito | — |

### BPIC_2012_W

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 118 ± 6 | 0.292 ± 0.017 | 109 ± 7.1 | 179 ± 8 | 3.33 ± 0.73 | 133 ± 3.4 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 54.9 ± 0.081 | 0.652 ± 0.0078 | 73 ± 0.14 | 118 ± 5.1 | 3.94 ± 0.089 | 84.5 ± 4.9 | 428 s, 1198 MB, 0.9 s/replica |
| SIMOD con ritardi estranei | 117 ± 6 | 0.585 ± 0.0036 | 59.6 ± 5.1 | 62.7 ± 3.8 | 4.7 ± 0.053 | 82.4 ± 4.9 | 880 s, 1198 MB, 1.3 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 116 ± 6.3 | 0.586 ± 0.0063 | 58.8 ± 6.8 | 73.6 ± 4.9 | 4.73 ± 0.04 | 105 ± 4.9 | 923 s, 1198 MB, 1.3 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 122 ± 5 | 0.587 ± 0.0046 | 63.9 ± 4.6 | 158 ± 7.7 | 4.6 ± 0.055 | 82.8 ± 4.2 | 880 s, 1198 MB, 1.3 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 97 ± 7.9 | 0.583 ± 0.0062 | 46 ± 5.7 | 61.8 ± 3.4 | 5.71 ± 0.039 | 83.5 ± 4.9 | 880 s, 1198 MB, 1.3 s/replica |
| ProSiT con regole (profondita' 3) | 105 ± 4.3 | 0.283 ± 0.0084 | 109 ± 6.2 | 66.8 ± 5.6 | 5.14 ± 0.024 | 90 ± 5 | 19 s, 1074 MB, 0.5 s/replica |
| ProSiT senza regole (profondita' 0) | 115 ± 4.3 | 0.322 ± 0.012 | 94.2 ± 7.5 | 66.1 ± 7.1 | 5.23 ± 0.03 | 69 ± 3.6 | 11 s, 1002 MB, 0.3 s/replica |
| AgentSimulator (scelta automatica) | 86.1 ± 4.8 | 0.26 ± 0.016 | 81.1 ± 6 | 67.4 ± 3.7 | 4.54 ± 0.046 | 72 ± 0.16 | 81 s, 838 MB, 1.4 s/replica |

### BPIC_2017_W

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 106 ± 3 | 0.143 ± 0.0026 | 76.9 ± 2.6 | 257 ± 5.4 | 0.654 ± 0.018 | 251 ± 6.1 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 199 ± 0.036 | 0.362 ± 0.0028 | 130 ± 0.04 | 182 ± 5 | 1.07 ± 0.05 | 77.1 ± 5 | 1760 s, 8740 MB, 2.0 s/replica |
| SIMOD con ritardi estranei | 95.8 ± 4.8 | 0.361 ± 0.0033 | 65.9 ± 4.2 | 51.4 ± 3.1 | 1.98 ± 0.02 | 68.4 ± 3.5 | 3406 s, 8740 MB, 4.2 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 99 ± 5 | 0.364 ± 0.0038 | 66.8 ± 4.3 | 68.8 ± 3.3 | 2.04 ± 0.0097 | 107 ± 3.4 | 3483 s, 8740 MB, 3.8 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 97.1 ± 3 | 0.363 ± 0.0029 | 67.3 ± 2.3 | 219 ± 6.6 | 1.91 ± 0.029 | 167 ± 3.3 | 3405 s, 8740 MB, 3.7 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 83.5 ± 3.7 | 0.363 ± 0.0038 | 56.2 ± 3.6 | 52.4 ± 3.3 | 3.72 ± 0.034 | 70.9 ± 3.5 | 3408 s, 8740 MB, 4.3 s/replica |
| ProSiT con regole (profondita' 3) | 191 ± 4.7 | 0.366 ± 0.0046 | 70 ± 3.1 | 76.5 ± 3.1 | 2.82 ± 0.034 | 79.6 ± 4.6 | 161 s, 1843 MB, 6.5 s/replica |
| ProSiT senza regole (profondita' 0) | 190 ± 6 | 0.447 ± 0.0037 | 124 ± 7.1 | 105 ± 5.9 | 2.88 ± 0.032 | 47.6 ± 3.6 | 70 s, 1380 MB, 3.5 s/replica |
| AgentSimulator (scelta automatica) | 72.9 ± 4.2 | 0.165 ± 0.0067 | 42.6 ± 3.6 | 51.7 ± 1.4 | 1.93 ± 0.015 | 54.7 ± 0.28 | 316 s, 1102 MB, 5.7 s/replica |

### bpic2012

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 10.4 ± 1.8 | 0.0505 ± 0.005 | 9.28 ± 1.9 | 196 ± 5.1 | 0.382 ± 0.028 | 250 ± 3.2 | 0 s, 0 MB, 0.2 s/replica |
| SIMOD, calendari fissi | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | 1048 s, 12421 MB, 0.0 s/replica |
| SIMOD con ritardi estranei | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | 1048 s, 12421 MB, 0.0 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | 1048 s, 12421 MB, 0.0 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | 1048 s, 12421 MB, 0.0 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | 1048 s, 12421 MB, 0.0 s/replica |
| ProSiT con regole (profondita' 3) | 267 ± 23 | 0.29 ± 0.005 | 200 ± 16 | 193 ± 14 | 2.11 ± 0.053 | 17.8 ± 5.2 | 178 s, 1882 MB, 1.9 s/replica |
| ProSiT senza regole (profondita' 0) | 217 ± 8.9 | 0.463 ± 0.0028 | 309 ± 19 | 290 ± 21 | 2.58 ± 0.016 | 22.7 ± 3.5 | 151 s, 1365 MB, 1.4 s/replica |
| AgentSimulator (scelta automatica) | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | 13200 s, 2665 MB, 0.0 s/replica |

### bpic2013_incidents

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 467 ± 23 (NV) | 0.349 ± 0.01 (NV) | 202 ± 13 (NV) | 381 ± 42 | 1.84 ± 0.095 | 345 ± 23 (NV) | 0 s, 0 MB, 0.2 s/replica |
| SIMOD, calendari fissi | 133 ± 4.9 (NV) | 0.723 ± 0.0046 (NV) | 129 ± 5.9 (NV) | 188 ± 5.5 | 3.4 ± 0.056 | 58.6 ± 2.7 (NV) | 1728 s, 1565 MB, 1.8 s/replica |
| SIMOD con ritardi estranei | 139 ± 6.6 (NV) | 0.721 ± 0.0049 (NV) | 133 ± 4.9 (NV) | 190 ± 5.1 | 3.4 ± 0.046 | 57.8 ± 2 (NV) | 4206 s, 1565 MB, 3.3 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 133 ± 11 (NV) | 0.722 ± 0.0052 (NV) | 122 ± 9.5 (NV) | 151 ± 9.8 | 3.34 ± 0.059 | 29.6 ± 1.7 (NV) | 4386 s, 1565 MB, 2.2 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 137 ± 6.9 (NV) | 0.723 ± 0.0031 (NV) | 133 ± 11 (NV) | 186 ± 12 | 3.16 ± 0.049 | 54.4 ± 1.7 (NV) | 4197 s, 1565 MB, 2.1 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 57.7 ± 1.2 (NV) | 0.723 ± 0.0058 (NV) | 25.3 ± 1.6 (NV) | 78.3 ± 3.3 | 4.05 ± 0.066 | 55.5 ± 2 (NV) | 4202 s, 1565 MB, 3.1 s/replica |
| ProSiT con regole (profondita' 3) | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | 13200 s, 11543 MB, 0.0 s/replica |

### Insurance_Claims

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0 ± 0 | 0.0534 ± 0.017 | 0 ± 0 | 1.32 ± 0.027 | 0.189 ± 0.0038 | 1.44 ± 0.028 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 0 ± 0 | 0.162 ± 0 | 0 ± 0 | 163 ± 1.1 | 0.281 ± 0.0013 | 163 ± 1.1 | 122 s, 1037 MB, 0.1 s/replica |
| SIMOD con ritardi estranei | 0 ± 0 | 0.162 ± 0 | 0 ± 0 | 163 ± 1.1 | 0.281 ± 0.0012 | 163 ± 1.1 | 180 s, 1037 MB, 0.1 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 41.9 ± 1.1 | 0.162 ± 0 | 12.9 ± 0.08 | 13 ± 0.079 | 0.0442 ± 0.00014 | 0.25 ± 0 | 180 s, 1037 MB, 0.1 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0 ± 0 | 0.162 ± 0 | 0 ± 0 | 163 ± 1.1 | 0.281 ± 0.0012 | 163 ± 1.1 | 180 s, 1037 MB, 0.1 s/replica |
| ProSiT con regole (profondita' 3) | 1.49 ± 0.67 | 0.0552 ± 0.012 | 1.16 ± 0.62 | 72.3 ± 44 | 0.146 ± 0.075 | 71.4 ± 44 | 8 s, 924 MB, 0.0 s/replica |
| ProSiT senza regole (profondita' 0) | 3.97 ± 3.6 | 0.0528 ± 0.016 | 1.69 ± 0.85 | 76.3 ± 39 | 0.15 ± 0.068 | 75.2 ± 40 | 3 s, 895 MB, 0.0 s/replica |
| AgentSimulator (scelta automatica) | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |

### Insurance_Claims_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0 ± 0 | 0.0644 ± 0.015 | 0 ± 0 | 1.33 ± 0.032 | 0.19 ± 0.0046 | 1.44 ± 0.028 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 0 ± 0 | 0.127 ± 0 | 0 ± 0 | 146 ± 1.9 | 0.28 ± 0.0031 | 146 ± 1.9 | 100 s, 1038 MB, 0.1 s/replica |
| SIMOD con ritardi estranei | 7.61 ± 1.8 | 0.127 ± 0 | 2.23 ± 0.47 | 148 ± 1.8 | 0.239 ± 0.0037 | 146 ± 1.9 | 172 s, 1038 MB, 0.1 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 135 ± 4.1 | 0.127 ± 0 | 59.6 ± 1.9 | 59.5 ± 1.9 | 0.161 ± 0.0031 | 0.94 ± 8.4e-17 | 172 s, 1038 MB, 0.1 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.511 ± 0.048 | 0.127 ± 0 | 0.184 ± 0.017 | 146 ± 1.9 | 0.234 ± 0.0032 | 146 ± 1.9 | 172 s, 1038 MB, 0.1 s/replica |
| ProSiT con regole (profondita' 3) | 12.8 ± 6.9 | 0.0898 ± 0.011 | 3.19 ± 1.8 | 33.2 ± 33 | 0.106 ± 0.052 | 29.5 ± 33 | 10 s, 926 MB, 0.0 s/replica |
| ProSiT senza regole (profondita' 0) | 12.4 ± 5.1 | 0.0968 ± 0.025 | 3.53 ± 1.8 | 19.3 ± 17 | 0.0785 ± 0.03 | 16.2 ± 19 | 5 s, 896 MB, 0.0 s/replica |
| AgentSimulator (scelta automatica) | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |

### Insurance_Claims_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.158 ± 0.0056 | 0.0387 ± 0.012 | 0.0404 ± 0.0009 | 1.36 ± 0.024 | 0.194 ± 0.0034 | 1.45 ± 0.028 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 0.17 ± 0 | 0.177 ± 0 | 0.0472 ± 0 | 161 ± 1 | 0.302 ± 0.0011 | 161 ± 1 | 104 s, 1042 MB, 0.1 s/replica |
| SIMOD con ritardi estranei | 0.17 ± 0 | 0.177 ± 0 | 0.0472 ± 0 | 161 ± 1 | 0.294 ± 0.0013 | 161 ± 1 | 182 s, 1042 MB, 0.1 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 66.2 ± 0.0079 | 0.177 ± 0 | 21.9 ± 0.5 | 22 ± 0.49 | 0.0845 ± 0.00086 | 0.26 ± 0 | 182 s, 1042 MB, 0.1 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.17 ± 0 | 0.177 ± 0 | 0.0472 ± 0 | 161 ± 1 | 0.294 ± 0.0013 | 161 ± 1 | 182 s, 1042 MB, 0.1 s/replica |
| ProSiT con regole (profondita' 3) | 44.3 ± 8 | 0.0345 ± 0.011 | 15.1 ± 3.3 | 20.4 ± 9.1 | 0.0748 ± 0.016 | 5.22 ± 12 | 12 s, 925 MB, 0.0 s/replica |
| ProSiT senza regole (profondita' 0) | 38.1 ± 14 | 0.0368 ± 0.01 | 13.4 ± 5.8 | 41.9 ± 25 | 0.112 ± 0.042 | 28.1 ± 30 | 6 s, 897 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |

### Insurance_Claims_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.045 ± 0.026 | 0.0387 ± 0.012 | 0.0944 ± 0.0071 | 1.36 ± 0.04 | 0.195 ± 0.0057 | 1.48 ± 0.03 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 53.3 ± 2.2 | 0.185 ± 0 | 17.7 ± 0.68 | 17.9 ± 0.68 | 0.0796 ± 0.0015 | 0 ± 0 | 105 s, 1041 MB, 0.1 s/replica |
| SIMOD con ritardi estranei | 69.3 ± 0.07 | 0.185 ± 0 | 27.9 ± 0.76 | 28 ± 0.77 | 0.0709 ± 0.0019 | 0 ± 0 | 187 s, 1041 MB, 0.3 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 69.6 ± 0.019 | 0.185 ± 0 | 25.7 ± 0.68 | 25.6 ± 0.68 | 0.0685 ± 0.0014 | 0 ± 0 | 187 s, 1041 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.076 ± 0.038 | 0.185 ± 0 | 0.143 ± 0.017 | 0.0133 ± 0.0036 | 0.0019 ± 0.00051 | 0 ± 0 | 187 s, 1041 MB, 0.1 s/replica |
| ProSiT con regole (profondita' 3) | 62.9 ± 7.4 | 0.0467 ± 0.016 | 24.1 ± 2.7 | 24.2 ± 2.7 | 0.0838 ± 0.0045 | 0 ± 0 | 10 s, 925 MB, 0.0 s/replica |
| ProSiT senza regole (profondita' 0) | 53.9 ± 3.5 | 0.0462 ± 0.0073 | 20.6 ± 1.3 | 20.8 ± 1.3 | 0.0769 ± 0.0021 | 0 ± 0 | 4 s, 897 MB, 0.0 s/replica |
| AgentSimulator (scelta automatica) | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |

### Insurance_Claims_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.038 ± 0.024 | 0.062 ± 0.014 | 0.0049 ± 0.0015 | 1.33 ± 0.028 | 0.19 ± 0.004 | 1.51 ± 0.036 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 0.58 ± 0 | 0.213 ± 2.1e-17 | 0.113 ± 0 | 166 ± 0.0044 | 0.312 ± 0.00063 | 166 ± 0 | 90 s, 1027 MB, 0.1 s/replica |
| SIMOD con ritardi estranei | 0.58 ± 0 | 0.213 ± 2.1e-17 | 0.113 ± 0 | 166 ± 0.0048 | 0.307 ± 0.00068 | 166 ± 0 | 167 s, 1036 MB, 0.1 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 49.6 ± 2.6 | 0.213 ± 2.1e-17 | 13.1 ± 0.58 | 13.3 ± 0.58 | 0.0636 ± 0.0015 | 0 ± 0 | 167 s, 1036 MB, 0.1 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.58 ± 0 | 0.213 ± 2.1e-17 | 0.113 ± 0 | 166 ± 0.0048 | 0.307 ± 0.00068 | 166 ± 0 | 167 s, 1036 MB, 0.1 s/replica |
| ProSiT con regole (profondita' 3) | 23.9 ± 19 | 0.0504 ± 0.0095 | 8.6 ± 7.8 | 110 ± 35 | 0.214 ± 0.056 | 102 ± 43 | 9 s, 933 MB, 0.0 s/replica |
| ProSiT senza regole (profondita' 0) | 64.2 ± 4.7 | 0.0514 ± 0.0094 | 22.5 ± 1.9 | 22.6 ± 1.8 | 0.0733 ± 0.0037 | 0 ± 0 | 7 s, 898 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |

### Loan_Application

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 31.2 ± 1.9 | 0.108 ± 0.023 | 22.4 ± 2.2 | 110 ± 7.1 | 0.501 ± 0.065 | 96.6 ± 4.8 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 36.5 ± 3.2 | 0.121 ± 0.02 | 21.9 ± 2.7 | 16.4 ± 2.7 | 0.64 ± 0.069 | 5.13 ± 1.7 | 138 s, 1071 MB, 0.2 s/replica |
| SIMOD con ritardi estranei | 32.8 ± 3.3 | 0.174 ± 0.015 | 22.9 ± 2.4 | 17.7 ± 2 | 0.688 ± 0.049 | 4.98 ± 1.9 | 238 s, 1071 MB, 0.3 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | 2 s, 178 MB, 0.0 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 22.2 ± 2.6 | 0.155 ± 0.017 | 17.1 ± 1.2 | 20.7 ± 2 | 0.532 ± 0.052 | 22.5 ± 0.81 | 237 s, 1071 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 73.2 ± 0.36 | 0.199 ± 0.0082 | 52.5 ± 0.21 | 47.3 ± 3.7 | 6.45 ± 1.3 | 4.83 ± 1.7 | 237 s, 1071 MB, 0.2 s/replica |
| ProSiT con regole (profondita' 3) | 24.7 ± 2.4 | 0.266 ± 0.014 | 17.6 ± 1.1 | 13.9 ± 4 | 0.518 ± 0.083 | 5.38 ± 2.2 | 10 s, 541 MB, 0.1 s/replica |
| ProSiT senza regole (profondita' 0) | 23.6 ± 2.8 | 0.336 ± 0.014 | 16.6 ± 2.3 | 13.3 ± 2.3 | 0.572 ± 0.074 | 4.27 ± 1.7 | 6 s, 908 MB, 0.0 s/replica |
| AgentSimulator (scelta automatica) | 41.2 ± 3.1 | 0.0759 ± 0.012 | 31.2 ± 2.7 | 19.6 ± 1.7 | 3.68 ± 0.022 | 10.7 ± 1.7 | 27 s, 725 MB, 0.6 s/replica |

### Loan_Application_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 32.1 ± 1.3 | 0.213 ± 0.014 | 20.6 ± 1.7 | 105 ± 6.1 | 0.555 ± 0.074 | 97.1 ± 4.8 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 35.3 ± 2.3 | 0.144 ± 0.018 | 19.9 ± 2.4 | 16.9 ± 3.4 | 0.533 ± 0.084 | 3.91 ± 1.5 | 781 s, 1937 MB, 0.2 s/replica |
| SIMOD con ritardi estranei | 26 ± 3.3 | 0.116 ± 0.029 | 18.4 ± 3 | 15.6 ± 3.9 | 0.479 ± 0.072 | 3.92 ± 1.5 | 896 s, 1937 MB, 0.3 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 18.9 ± 2.1 | 0.108 ± 0.019 | 12.2 ± 1.9 | 14.7 ± 2.9 | 0.392 ± 0.061 | 22.2 ± 0.69 | 896 s, 1937 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 70.4 ± 0.47 | 0.102 ± 0.016 | 49 ± 0.27 | 45.3 ± 4.4 | 6.3 ± 1 | 3.87 ± 1.6 | 896 s, 1937 MB, 0.2 s/replica |
| ProSiT con regole (profondita' 3) | 24.2 ± 2.3 | 0.382 ± 0.017 | 14 ± 2.5 | 12.1 ± 3.6 | 0.458 ± 0.08 | 4.9 ± 2.1 | 7 s, 939 MB, 0.0 s/replica |
| ProSiT senza regole (profondita' 0) | 22.2 ± 1.6 | 0.4 ± 0.011 | 12.1 ± 2.6 | 9.25 ± 3.5 | 0.46 ± 0.12 | 4.29 ± 1.7 | 4 s, 909 MB, 0.0 s/replica |
| AgentSimulator (scelta automatica) | 28.9 ± 3.6 | 0.18 ± 0.015 | 19.6 ± 2.6 | 12 ± 2.8 | 3.46 ± 0.044 | 6.29 ± 1.9 | 31 s, 735 MB, 0.7 s/replica |

### Loan_Application_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 34.3 ± 2.7 | 0.148 ± 0.014 | 23.9 ± 2.6 | 107 ± 6.3 | 0.603 ± 0.076 | 96.9 ± 4.6 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 40.2 ± 2.4 | 0.141 ± 0.02 | 24.2 ± 3 | 19 ± 3.2 | 0.822 ± 0.076 | 5.14 ± 1.9 | 111 s, 1069 MB, 0.2 s/replica |
| SIMOD con ritardi estranei | 24.5 ± 4.1 | 0.172 ± 0.02 | 18.3 ± 3 | 9.86 ± 3.4 | 0.731 ± 0.11 | 8.21 ± 1.7 | 201 s, 1072 MB, 0.2 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 20.5 ± 2.6 | 0.164 ± 0.021 | 12.7 ± 1.7 | 14.7 ± 2.3 | 0.797 ± 0.072 | 22.6 ± 0.69 | 202 s, 1072 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 65 ± 2.3 | 0.204 ± 0.023 | 49.4 ± 0.47 | 38.5 ± 3.1 | 7.51 ± 0.35 | 8 ± 1.6 | 202 s, 1072 MB, 0.2 s/replica |
| ProSiT con regole (profondita' 3) | 28.8 ± 4.1 | 0.337 ± 0.0069 | 17.2 ± 3.4 | 16.2 ± 3.4 | 0.735 ± 0.096 | 3.07 ± 1.7 | 7 s, 935 MB, 0.0 s/replica |
| ProSiT senza regole (profondita' 0) | 26.4 ± 3.3 | 0.372 ± 0.016 | 15.4 ± 1.8 | 12.3 ± 2.4 | 0.652 ± 0.065 | 6.88 ± 2.1 | 4 s, 905 MB, 0.0 s/replica |
| AgentSimulator (scelta automatica) | 36.7 ± 3.2 | 0.106 ± 0.012 | 21 ± 2.4 | 16.4 ± 1.9 | 0.813 ± 0.17 | 8.03 ± 1.5 | 25 s, 729 MB, 0.6 s/replica |

### Loan_Application_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 36.3 ± 0.58 | 0.0835 ± 0.015 | 23.1 ± 1.5 | 109 ± 6.3 | 1.28 ± 0.92 | 97.5 ± 4.9 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 46.1 ± 2.9 | 0.237 ± 0.016 | 30 ± 1.5 | 27.9 ± 2.9 | 3.18 ± 1 | 5.08 ± 1.5 | 151 s, 1082 MB, 0.2 s/replica |
| SIMOD con ritardi estranei | 16.3 ± 2.1 | 0.237 ± 0.021 | 17.4 ± 1.8 | 19.6 ± 1.9 | 2.84 ± 1.1 | 2.94 ± 1.2 | 263 s, 1082 MB, 0.2 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 18.6 ± 3.4 | 0.243 ± 0.015 | 15.5 ± 1.4 | 16.6 ± 2.1 | 3.64 ± 0.68 | 23.2 ± 0.71 | 263 s, 1082 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 58.9 ± 0.68 | 0.233 ± 0.01 | 44.8 ± 0.68 | 47.4 ± 2 | 7.4 ± 0.25 | 2.86 ± 1.3 | 263 s, 1082 MB, 0.2 s/replica |
| ProSiT con regole (profondita' 3) | 29 ± 2.4 | 0.295 ± 0.016 | 17.4 ± 2 | 17.2 ± 3.1 | 0.693 ± 0.1 | 2.82 ± 1.3 | 8 s, 933 MB, 0.1 s/replica |
| ProSiT senza regole (profondita' 0) | 28.8 ± 2 | 0.327 ± 0.021 | 17 ± 2.1 | 13.8 ± 2.2 | 0.655 ± 0.12 | 6.02 ± 1.9 | 5 s, 903 MB, 0.0 s/replica |
| AgentSimulator (scelta automatica) | fallito | fallito | fallito | fallito | fallito | fallito | — |

### Loan_Application_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 33.7 ± 2.2 | 0.102 ± 0.013 | 25 ± 3.6 | 106 ± 5.7 | 0.559 ± 0.058 | 97.7 ± 4.8 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 18.9 ± 4.1 | 0.162 ± 0.013 | 11.8 ± 2 | 10.8 ± 1.2 | 0.674 ± 0.033 | 4.95 ± 1.8 | 141 s, 1075 MB, 0.2 s/replica |
| SIMOD con ritardi estranei | 19.3 ± 3.2 | 0.162 ± 0.013 | 10.7 ± 1.9 | 9.7 ± 2.1 | 0.701 ± 0.021 | 4.95 ± 1.8 | 260 s, 1075 MB, 0.3 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 17.8 ± 2 | 0.154 ± 0.01 | 11.9 ± 0.77 | 8.28 ± 2 | 0.781 ± 0.035 | 23.4 ± 0.6 | 260 s, 1075 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 96.5 ± 0.13 | 0.148 ± 0.0065 | 66.9 ± 0.14 | 67.3 ± 3.9 | 7.5 ± 1 | 4.18 ± 1.8 | 260 s, 1075 MB, 0.3 s/replica |
| ProSiT con regole (profondita' 3) | 34.1 ± 2.7 | 0.255 ± 0.0096 | 21.8 ± 2.2 | 24 ± 4.4 | 0.562 ± 0.08 | 3.53 ± 1.4 | 10 s, 934 MB, 0.1 s/replica |
| ProSiT senza regole (profondita' 0) | 33.3 ± 2.3 | 0.301 ± 0.01 | 21.8 ± 2.5 | 20.3 ± 4.5 | 0.515 ± 0.082 | 5.76 ± 2.1 | 5 s, 904 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | 54.4 ± 4.8 | 0.109 ± 0.019 | 38.3 ± 2.8 | 30.2 ± 2.4 | 3.63 ± 0.047 | 10.9 ± 1.9 | 27 s, 730 MB, 0.9 s/replica |

### Pharmacy

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.24 ± 0.11 | 0.0365 ± 0.0095 | 0.117 ± 0.062 | 18.1 ± 0.34 | 3.68 ± 0.017 | 18.3 ± 0.33 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 10.7 ± 2.6 | 0.0369 ± 0.005 | 4.74 ± 0.96 | 118 ± 0.92 | 3.51 ± 3.3e-16 | 113 ± 0.58 | 104 s, 1033 MB, 0.1 s/replica |
| SIMOD con ritardi estranei | 11.4 ± 1.7 | 0.0445 ± 0.0061 | 5.07 ± 1.1 | 118 ± 0.82 | 3.51 ± 3.3e-16 | 113 ± 0.43 | 151 s, 1033 MB, 0.1 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 143 ± 0.11 | 0.0389 ± 0.004 | 88 ± 4.1 | 87.3 ± 4.1 | 3.51 ± 3.3e-16 | 1.5 ± 0 | 151 s, 1033 MB, 0.1 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0 ± 0 | 0.0344 ± 0.0058 | 0 ± 0 | 113 ± 0.5 | 3.49 ± 0.0045 | 113 ± 0.43 | 151 s, 1033 MB, 0.1 s/replica |
| ProSiT con regole (profondita' 3) | 11.8 ± 0.96 | 0.028 ± 0.0062 | 5.57 ± 0.38 | 118 ± 0.66 | 3.51 ± 0.0022 | 112 ± 0.32 | 5 s, 906 MB, 0.1 s/replica |
| ProSiT senza regole (profondita' 0) | 11.2 ± 1.5 | 0.0361 ± 0.006 | 6.15 ± 1.3 | 118 ± 1.3 | 3.51 ± 0.0025 | 112 ± 1.1e-14 | 4 s, 887 MB, 0.2 s/replica |
| AgentSimulator (scelta automatica) | 0.008 ± 0.0088 | 0.0465 ± 0.0082 | 0.00241 ± 0.0029 | 141 ± 0.097 | 3.51 ± 3.3e-16 | 141 ± 0 | 15 s, 685 MB, 0.3 s/replica |

### Pharmacy_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.264 ± 0.11 | 0.0425 ± 0.0063 | 0.0926 ± 0.046 | 18.1 ± 0.37 | 3.68 ± 0.017 | 18.3 ± 0.33 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 11.1 ± 2.1 | 0.0545 ± 0.01 | 5.1 ± 0.82 | 118 ± 0.73 | 3.51 ± 0 | 113 ± 0.43 | 120 s, 1034 MB, 0.1 s/replica |
| SIMOD con ritardi estranei | 10.8 ± 2 | 0.0516 ± 0.0061 | 4.76 ± 1.1 | 118 ± 0.82 | 3.51 ± 0 | 113 ± 0.43 | 186 s, 1034 MB, 0.1 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 143 ± 0.087 | 0.0589 ± 0.01 | 86.5 ± 2.9 | 85.7 ± 2.9 | 3.51 ± 0 | 1.5 ± 0 | 186 s, 1034 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0 ± 0 | 0.0515 ± 0.0078 | 0 ± 0 | 113 ± 0.6 | 3.49 ± 0.0052 | 113 ± 0.43 | 186 s, 1034 MB, 0.1 s/replica |
| ProSiT con regole (profondita' 3) | 12.5 ± 0.8 | 0.0457 ± 0.0076 | 5.95 ± 1.1 | 119 ± 1 | 3.51 ± 0.0016 | 112 ± 1.1e-14 | 6 s, 906 MB, 0.0 s/replica |
| ProSiT senza regole (profondita' 0) | 13.9 ± 1 | 0.0452 ± 0.0056 | 6.54 ± 0.34 | 119 ± 0.56 | 3.51 ± 0.0023 | 112 ± 1.1e-14 | 4 s, 887 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | 0.002 ± 0.003 | 0.0653 ± 0.0075 | 0.00217 ± 0.0013 | 141 ± 0.12 | 3.51 ± 0 | 141 ± 0 | 17 s, 687 MB, 0.3 s/replica |

### Pharmacy_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.504 ± 0.17 | 0.0414 ± 0.0082 | 0.274 ± 0.099 | 18 ± 0.41 | 3.7 ± 0.017 | 18.3 ± 0.33 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 10.2 ± 2 | 0.0501 ± 0.0052 | 4.09 ± 0.82 | 118 ± 0.73 | 3.52 ± 0 | 114 ± 0 | 114 s, 1033 MB, 0.1 s/replica |
| SIMOD con ritardi estranei | 19.2 ± 0.98 | 0.0493 ± 0.0064 | 8.56 ± 1.2 | 122 ± 1 | 3.52 ± 0 | 114 ± 0 | 179 s, 1033 MB, 0.2 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 143 ± 0.037 | 0.05 ± 0.0076 | 88.1 ± 5.1 | 87.3 ± 5.1 | 3.52 ± 0 | 1.5 ± 0 | 178 s, 1033 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.055 ± 0.025 | 0.0489 ± 0.0064 | 0.021 ± 0.009 | 113 ± 0.26 | 3.48 ± 0.0054 | 114 ± 0 | 179 s, 1033 MB, 0.2 s/replica |
| ProSiT con regole (profondita' 3) | 17.2 ± 1.6 | 0.0355 ± 0.0072 | 7.3 ± 0.5 | 120 ± 0.5 | 3.52 ± 0.0011 | 112 ± 1.1e-14 | 5 s, 906 MB, 0.0 s/replica |
| ProSiT senza regole (profondita' 0) | 15.1 ± 1.3 | 0.0372 ± 0.0057 | 7.32 ± 1.4 | 120 ± 1.2 | 3.52 ± 0.0017 | 112 ± 1.1e-14 | 3 s, 888 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | 0.144 ± 0.32 | 0.0659 ± 0.0086 | 0.00971 ± 0.019 | 141 ± 0.14 | 3.52 ± 0 | 141 ± 0 | 16 s, 685 MB, 0.3 s/replica |

### Pharmacy_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.622 ± 0.22 | 0.0285 ± 0.0076 | 0.23 ± 0.1 | 18.1 ± 0.34 | 3.69 ± 0.017 | 18.3 ± 0.33 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 10.2 ± 0.93 | 0.0281 ± 0.0071 | 4.51 ± 0.42 | 118 ± 0.59 | 3.53 ± 3.3e-16 | 113 ± 0.43 | 133 s, 1029 MB, 0.2 s/replica |
| SIMOD con ritardi estranei | 9.66 ± 1.3 | 0.034 ± 0.008 | 4.1 ± 0.62 | 117 ± 0.47 | 3.53 ± 3.3e-16 | 113 ± 0.49 | 208 s, 1031 MB, 0.2 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 143 ± 0.06 | 0.03 ± 0.0064 | 86.4 ± 4.3 | 85.6 ± 4.3 | 3.53 ± 3.3e-16 | 1.5 ± 0 | 208 s, 1031 MB, 0.1 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0 ± 0 | 0.033 ± 0.0098 | 0 ± 0 | 113 ± 0.45 | 3.51 ± 0.0025 | 113 ± 0.49 | 208 s, 1031 MB, 0.2 s/replica |
| ProSiT con regole (profondita' 3) | 19.7 ± 1.2 | 0.0281 ± 0.0051 | 9.07 ± 0.31 | 121 ± 0.32 | 3.52 ± 0.0017 | 112 ± 1.1e-14 | 7 s, 906 MB, 0.0 s/replica |
| ProSiT senza regole (profondita' 0) | 20 ± 1.2 | 0.0288 ± 0.0053 | 10.1 ± 0.58 | 122 ± 0.44 | 3.52 ± 0.00088 | 112 ± 1.1e-14 | 5 s, 888 MB, 0.0 s/replica |
| AgentSimulator (scelta automatica) | 0.284 ± 0.43 | 0.0486 ± 0.0045 | 0.0877 ± 0.18 | 141 ± 0.091 | 3.53 ± 3.3e-16 | 141 ± 0 | 17 s, 683 MB, 0.2 s/replica |

### Pharmacy_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.42 ± 0.16 | 0.0384 ± 0.0094 | 0.198 ± 0.092 | 18.1 ± 0.38 | 3.7 ± 0.016 | 18.3 ± 0.33 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 8.38 ± 1.2 | 0.0344 ± 0.0049 | 3.82 ± 0.63 | 117 ± 0.65 | 3.52 ± 0 | 114 ± 0.0023 | 82 s, 1034 MB, 0.1 s/replica |
| SIMOD con ritardi estranei | 8.24 ± 0.8 | 0.0358 ± 0.0057 | 3.55 ± 0.42 | 117 ± 0.34 | 3.52 ± 0 | 114 ± 0 | 140 s, 1034 MB, 0.1 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 143 ± 0.09 | 0.0365 ± 0.0058 | 82.5 ± 3.6 | 81.8 ± 3.6 | 3.52 ± 0 | 1.5 ± 0 | 140 s, 1034 MB, 0.1 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0 ± 0 | 0.0433 ± 0.0062 | 0 ± 0 | 114 ± 0.28 | 3.51 ± 0.0019 | 114 ± 0 | 140 s, 1034 MB, 0.1 s/replica |
| ProSiT con regole (profondita' 3) | 16.3 ± 1.2 | 0.039 ± 0.0084 | 8.05 ± 0.62 | 120 ± 0.36 | 3.52 ± 0.0011 | 112 ± 1.1e-14 | 5 s, 906 MB, 0.0 s/replica |
| ProSiT senza regole (profondita' 0) | 16.9 ± 1.2 | 0.041 ± 0.0054 | 7.71 ± 0.58 | 120 ± 0.53 | 3.52 ± 0.001 | 112 ± 0.32 | 4 s, 888 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | 0 ± 0 | 0.048 ± 0.0093 | 0 ± 0 | 141 ± 0.077 | 3.52 ± 0 | 141 ± 0 | 14 s, 683 MB, 0.2 s/replica |

### Procure_to_Pay

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 13.1 ± 2.8 | 0.127 ± 0.013 | 3.9 ± 0.77 | 164 ± 5.1 | 0.25 ± 0.024 | 165 ± 5.5 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 114 ± 13 | 0.279 ± 0.0024 | 39 ± 7 | 38.3 ± 6.8 | 0.279 ± 0.028 | 2.21 ± 0.87 | 138 s, 1077 MB, 0.2 s/replica |
| SIMOD con ritardi estranei | 104 ± 8.7 | 0.277 ± 0.0024 | 38 ± 5.2 | 38.2 ± 5.5 | 0.24 ± 0.028 | 2.4 ± 1.5 | 210 s, 1077 MB, 0.3 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 104 ± 17 | 0.281 ± 0.0031 | 37.2 ± 5.8 | 40.3 ± 3.8 | 0.211 ± 0.017 | 4.14 ± 1.4 | 232 s, 1077 MB, 0.2 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 128 ± 18 | 0.277 ± 0.0022 | 41.6 ± 4.9 | 104 ± 2.9 | 0.255 ± 0.02 | 78.6 ± 5.3 | 209 s, 1077 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 32.3 ± 0.15 | 0.279 ± 0.0024 | 25.3 ± 0.074 | 26.1 ± 2.4 | 4.95 ± 1 | 2.63 ± 1.9 | 209 s, 1077 MB, 0.2 s/replica |
| ProSiT con regole (profondita' 3) | 11.3 ± 2.3 | 0.117 ± 0.017 | 3.05 ± 0.61 | 6.78 ± 1.6 | 0.185 ± 0.026 | 1.76 ± 0.94 | 7 s, 937 MB, 0.0 s/replica |
| ProSiT senza regole (profondita' 0) | 8.93 ± 2.9 | 0.122 ± 0.019 | 3.55 ± 1.1 | 5.29 ± 1.7 | 0.179 ± 0.016 | 2.35 ± 0.99 | 4 s, 898 MB, 0.0 s/replica |
| AgentSimulator (scelta automatica) | 34.2 ± 7.9 | 0.102 ± 0.018 | 28.2 ± 5.2 | 28.9 ± 5 | 0.657 ± 0.75 | 0.56 ± 0 | 23 s, 711 MB, 0.3 s/replica |

### Procure_to_Pay_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 8.37 ± 1.5 | 0.0838 ± 0.019 | 3.06 ± 0.38 | 155 ± 5.4 | 0.206 ± 0.043 | 165 ± 5.5 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 70 ± 9.4 | 0.28 ± 0.0037 | 21.5 ± 4.3 | 26.4 ± 4.1 | 0.226 ± 0.018 | 2.17 ± 0.75 | 128 s, 1088 MB, 0.3 s/replica |
| SIMOD con ritardi estranei | 71 ± 8.8 | 0.277 ± 0.006 | 20.1 ± 4.1 | 25.6 ± 3.6 | 0.219 ± 0.022 | 1.58 ± 0.59 | 247 s, 1088 MB, 0.4 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 75.7 ± 11 | 0.277 ± 0.0071 | 19.1 ± 3.5 | 27.2 ± 2.8 | 0.243 ± 0.022 | 2.52 ± 1.5 | 270 s, 1088 MB, 0.3 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 103 ± 16 | 0.282 ± 0.0047 | 31 ± 5.5 | 99.8 ± 3 | 0.295 ± 0.043 | 78.3 ± 5.4 | 247 s, 1088 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 40.2 ± 0.15 | 0.276 ± 0.0065 | 29.1 ± 0.059 | 24.7 ± 1 | 5.76 ± 0.054 | 2 ± 0.96 | 247 s, 1088 MB, 0.3 s/replica |
| ProSiT con regole (profondita' 3) | 8.2 ± 1.6 | 0.076 ± 0.021 | 3.75 ± 0.87 | 8.16 ± 2.5 | 0.203 ± 0.03 | 2.11 ± 0.93 | 7 s, 936 MB, 0.1 s/replica |
| ProSiT senza regole (profondita' 0) | 7.51 ± 1.5 | 0.0988 ± 0.019 | 3.88 ± 0.9 | 8.57 ± 3.1 | 0.191 ± 0.024 | 2.73 ± 1.2 | 4 s, 896 MB, 0.0 s/replica |
| AgentSimulator (scelta automatica) | 10.3 ± 2.4 | 0.0794 ± 0.014 | 9.66 ± 2.6 | 15.6 ± 2.8 | 0.282 ± 0.031 | 1.13 ± 0 | 22 s, 704 MB, 0.2 s/replica |

### Procure_to_Pay_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 7.07 ± 1.9 | 0.0539 ± 0.013 | 4.1 ± 1.2 | 165 ± 8.7 | 0.232 ± 0.032 | 165 ± 5.5 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 85.2 ± 10 | 0.238 ± 0.0018 | 30.5 ± 5.3 | 29.2 ± 5.5 | 0.18 ± 0.027 | 1.77 ± 1 | 143 s, 1076 MB, 0.2 s/replica |
| SIMOD con ritardi estranei | 95.5 ± 8.1 | 0.237 ± 0.0036 | 34.5 ± 4.4 | 32.6 ± 3.6 | 0.182 ± 0.02 | 2.4 ± 0.97 | 268 s, 1076 MB, 0.2 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 90.8 ± 9.8 | 0.238 ± 0.0019 | 30.8 ± 5.6 | 33.5 ± 5.5 | 0.165 ± 0.024 | 2.84 ± 1.1 | 291 s, 1076 MB, 0.3 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 121 ± 10 | 0.238 ± 0.0028 | 41.8 ± 4.3 | 104 ± 5.1 | 0.207 ± 0.029 | 78.6 ± 5.3 | 268 s, 1076 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 34.7 ± 0.29 | 0.24 ± 0.0024 | 23.8 ± 0.15 | 26.4 ± 1.5 | 5.85 ± 0.061 | 3.15 ± 1.2 | 268 s, 1076 MB, 0.3 s/replica |
| ProSiT con regole (profondita' 3) | 6.64 ± 1.5 | 0.0586 ± 0.014 | 3.88 ± 1.5 | 5.21 ± 2.2 | 0.174 ± 0.02 | 1.68 ± 0.8 | 7 s, 932 MB, 0.0 s/replica |
| ProSiT senza regole (profondita' 0) | 6.53 ± 1.3 | 0.0878 ± 0.019 | 4.1 ± 1.3 | 5.47 ± 1.7 | 0.165 ± 0.028 | 2.35 ± 1.3 | 4 s, 896 MB, 0.0 s/replica |
| AgentSimulator (scelta automatica) | 33.7 ± 4.2 | 0.0501 ± 0.017 | 29.8 ± 3.3 | 25.1 ± 4.1 | 0.639 ± 0.75 | 4.3 ± 0 | 23 s, 708 MB, 0.3 s/replica |

### Procure_to_Pay_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 7.7 ± 2.3 | 0.0727 ± 0.013 | 3.11 ± 0.92 | 155 ± 6.6 | 0.227 ± 0.025 | 165 ± 5.5 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 68.3 ± 7.1 | 0.248 ± 0.0053 | 17.5 ± 3.5 | 18.5 ± 3.4 | 0.238 ± 0.02 | 2.12 ± 1.3 | 139 s, 1076 MB, 0.3 s/replica |
| SIMOD con ritardi estranei | 73.3 ± 7.9 | 0.25 ± 0.0041 | 22.3 ± 4.5 | 21.4 ± 4.3 | 0.246 ± 0.041 | 2.21 ± 0.87 | 260 s, 1076 MB, 0.2 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 71.3 ± 13 | 0.245 ± 0.0036 | 22.1 ± 6.8 | 24.4 ± 6.5 | 0.246 ± 0.023 | 3.33 ± 1.7 | 283 s, 1076 MB, 0.2 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 86.2 ± 13 | 0.251 ± 0.004 | 24.8 ± 4.2 | 88.5 ± 5.2 | 0.288 ± 0.034 | 78.6 ± 5.3 | 260 s, 1076 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 57.8 ± 0.11 | 0.249 ± 0.007 | 37.4 ± 0.058 | 39.5 ± 0.75 | 5.69 ± 0.043 | 3.36 ± 0.8 | 260 s, 1076 MB, 0.2 s/replica |
| ProSiT con regole (profondita' 3) | 10.2 ± 1.4 | 0.0845 ± 0.014 | 5.66 ± 1.4 | 4.77 ± 1.5 | 0.189 ± 0.014 | 2.09 ± 0.91 | 7 s, 934 MB, 0.1 s/replica |
| ProSiT senza regole (profondita' 0) | 8.39 ± 1.5 | 0.0922 ± 0.011 | 3.84 ± 0.69 | 4.96 ± 2.8 | 0.195 ± 0.025 | 2.71 ± 1.3 | 6 s, 900 MB, 0.0 s/replica |
| AgentSimulator (scelta automatica) | 22.6 ± 6.3 | 0.0648 ± 0.0093 | 23.2 ± 3.8 | 21.5 ± 4.7 | 0.944 ± 0.97 | 1.46 ± 0 | 27 s, 705 MB, 0.3 s/replica |

### Procure_to_Pay_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 8.49 ± 2.4 | 0.0719 ± 0.015 | 4.24 ± 0.81 | 161 ± 7.3 | 0.186 ± 0.026 | 165 ± 5.5 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 86.6 ± 8.1 | 0.276 ± 0.0026 | 29.8 ± 4.8 | 28.4 ± 3.2 | 0.205 ± 0.031 | 2.25 ± 1.7 | 147 s, 1077 MB, 0.3 s/replica |
| SIMOD con ritardi estranei | 98.7 ± 13 | 0.274 ± 0.0031 | 33.5 ± 5.6 | 31.3 ± 4.6 | 0.224 ± 0.025 | 2.23 ± 1.8 | 269 s, 1077 MB, 0.3 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 106 ± 24 | 0.276 ± 0.0039 | 38 ± 13 | 39.2 ± 12 | 0.235 ± 0.02 | 2.57 ± 0.9 | 293 s, 1077 MB, 0.3 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 115 ± 13 | 0.274 ± 0.0031 | 34.9 ± 3.4 | 97 ± 5.5 | 0.2 ± 0.023 | 78.5 ± 5.4 | 268 s, 1077 MB, 0.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 48.9 ± 0.17 | 0.275 ± 0.0027 | 30.9 ± 0.092 | 35.1 ± 2 | 5.12 ± 0.99 | 3.98 ± 2.1 | 269 s, 1077 MB, 0.3 s/replica |
| ProSiT con regole (profondita' 3) | 8.33 ± 1.6 | 0.0755 ± 0.016 | 3.67 ± 1.1 | 3.72 ± 1.8 | 0.175 ± 0.031 | 2 ± 1.1 | 8 s, 932 MB, 0.1 s/replica |
| ProSiT senza regole (profondita' 0) | 6.28 ± 1.5 | 0.0999 ± 0.013 | 3.98 ± 0.82 | 4.63 ± 1.5 | 0.165 ± 0.024 | 2.45 ± 1.3 | 5 s, 897 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | 10.6 ± 1.3 | 0.0698 ± 0.0064 | 5.61 ± 1 | 9.37 ± 0.97 | 0.345 ± 0.039 | 4.2 ± 0 | 23 s, 706 MB, 0.3 s/replica |


## Metriche, fase test

### AcademicCredentials

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 28.8 ± 3.6 | 0.179 ± 0.0056 | 25.9 ± 2.2 | 62.3 ± 6.2 | 1.39 ± 0.12 | 95.5 ± 17 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 282 ± 40 | 0.378 ± 0.056 | 6.38e+03 ± 2.6e+03 | 6.59e+03 ± 2.6e+03 | 4.34 ± 0.085 | 132 ± 16 | 133 s, 1097 MB, 0.6 s/replica |
| SIMOD con ritardi estranei | fallito | fallito | fallito | fallito | fallito | fallito | — |
| SIMOD con ritardi estranei + arrivi AT-KDE | fallito | fallito | fallito | fallito | fallito | fallito | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | fallito | fallito | fallito | fallito | fallito | fallito | — |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | fallito | fallito | fallito | fallito | fallito | fallito | — |
| ProSiT con regole (profondita' 3) | 65.8 ± 8.5 | 0.307 ± 0.0073 | 66.6 ± 10 | 145 ± 21 | 1.81 ± 0.14 | 104 ± 13 | 15 s, 1084 MB, 0.4 s/replica |
| ProSiT senza regole (profondita' 0) | 19.8 ± 4.1 | 0.733 ± 0.0064 | 70.1 ± 7.7 | 214 ± 46 | 1.98 ± 0.14 | 124 ± 28 | 9 s, 1000 MB, 0.3 s/replica |
| AgentSimulator (scelta automatica) | fallito | fallito | fallito | fallito | fallito | fallito | — |

### BPIC_2012_W

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 28.1 ± 2 | 0.0831 ± 0.005 | 10.1 ± 2.6 | 29.7 ± 4.4 | 0.8 ± 0.15 | 38.2 ± 4.3 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 175 ± 0.04 | 0.531 ± 0.0047 | 178 ± 0.079 | 169 ± 12 | 1.31 ± 0.092 | 39.5 ± 6.5 | 579 s, 1243 MB, 3.8 s/replica |
| SIMOD con ritardi estranei | 44 ± 0.99 | 0.503 ± 0.0046 | 63.3 ± 1.6 | 91.5 ± 11 | 2.09 ± 0.016 | 65.7 ± 10 | 1177 s, 1243 MB, 7.8 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 43.3 ± 2.5 | 0.503 ± 0.0062 | 62.9 ± 3.1 | 127 ± 17 | 2.18 ± 0.023 | 105 ± 20 | 1237 s, 1243 MB, 7.2 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 43 ± 2.3 | 0.502 ± 0.0042 | 62.1 ± 2.1 | 46 ± 3.3 | 2.1 ± 0.018 | 39.5 ± 4.5 | 1172 s, 1243 MB, 7.2 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 51.3 ± 1.9 | 0.496 ± 0.0042 | 71.4 ± 2.1 | 101 ± 11 | 3.17 ± 0.015 | 66.6 ± 10 | 1183 s, 1243 MB, 8.8 s/replica |
| ProSiT con regole (profondita' 3) | 32 ± 2.3 | 0.0849 ± 0.0051 | 11.7 ± 1.3 | 67.9 ± 9.9 | 2.64 ± 0.024 | 91 ± 13 | 35 s, 1104 MB, 1.7 s/replica |
| ProSiT senza regole (profondita' 0) | 35.1 ± 1.5 | 0.127 ± 0.0029 | 31 ± 1.9 | 99.3 ± 16 | 2.81 ± 0.016 | 76.9 ± 12 | 20 s, 1025 MB, 1.6 s/replica |
| AgentSimulator (scelta automatica) | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | fuori budget | — |

### BPIC_2017_W

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 30.6 ± 1.5 | 0.0788 ± 0.0015 | 11.4 ± 1.6 | 42.8 ± 4 | 0.66 ± 0.011 | 35.9 ± 3.8 | 1 s, 0 MB, 0.4 s/replica |
| SIMOD, calendari fissi | 253 ± 0.036 | 0.279 ± 0.0013 | 183 ± 0.023 | 244 ± 14 | 0.924 ± 0.024 | 113 ± 12 | 4426 s, 11496 MB, 119.8 s/replica |
| SIMOD con ritardi estranei | 18.8 ± 1.2 | 0.277 ± 0.0013 | 8.07 ± 0.65 | 68.3 ± 6.8 | 2.32 ± 0.01 | 117 ± 7.7 | 5669 s, 11496 MB, 14.1 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 17.7 ± 1.2 | 0.279 ± 0.0015 | 8.13 ± 0.49 | 232 ± 9.2 | 2.4 ± 0.01 | 281 ± 9.2 | 5760 s, 11496 MB, 13.1 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 19.5 ± 1.1 | 0.28 ± 0.0014 | 7.86 ± 0.47 | 39.1 ± 6.8 | 2.24 ± 0.0098 | 30.2 ± 2.5 | 5653 s, 11496 MB, 12.6 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 10.3 ± 0.33 | 0.279 ± 0.0021 | 15.9 ± 1.3 | 82.2 ± 7.4 | 3.43 ± 0.013 | 118 ± 7.8 | 5662 s, 11496 MB, 13.7 s/replica |
| ProSiT con regole (profondita' 3) | 116 ± 2 | 0.333 ± 0.002 | 28 ± 1.3 | 42.7 ± 4.9 | 2.56 ± 0.012 | 90.1 ± 5.5 | 185 s, 2067 MB, 11.1 s/replica |
| ProSiT senza regole (profondita' 0) | 104 ± 2.1 | 0.4 ± 0.0015 | 58.5 ± 1.5 | 202 ± 11 | 2.68 ± 0.012 | 97.2 ± 7.7 | 92 s, 1582 MB, 5.4 s/replica |
| AgentSimulator (scelta automatica) | 12.3 ± 0.6 | 0.133 ± 0.0019 | 24.8 ± 1.2 | 22.1 ± 1.3 | 1.74 ± 0.0086 | 25.6 ± 0.23 | 582 s, 1164 MB, 26.0 s/replica |

### bpic2012

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 16.9 ± 1.5 (NV) | 0.0546 ± 0.0016 (NV) | 16.6 ± 1.6 (NV) | 60.3 ± 3.3 | 0.222 ± 0.013 | 48.7 ± 2.7 | 3 s, 0 MB, 0.6 s/replica |

### bpic2013_incidents

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 384 ± 7.8 (NV) | 0.329 ± 0.0037 (NV) | 177 ± 4 (NV) | 334 ± 16 | 1.75 ± 0.079 | 291 ± 6.4 (NV) | 1 s, 0 MB, 0.3 s/replica |

### Insurance_Claims

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0 ± 0 | 0.0145 ± 0.0048 | 0 ± 0 | 2.57 ± 0.02 | 0.367 ± 0.0028 | 2.39 ± 0.018 | 0 s, 0 MB, 0.1 s/replica |
| SIMOD, calendari fissi | 14.9 ± 1.1 | 0.187 ± 0 | 10.8 ± 0.9 | 144 ± 0.19 | 0.363 ± 0.00084 | 133 ± 1 | 107 s, 1060 MB, 0.4 s/replica |
| SIMOD con ritardi estranei | 16.1 ± 1.9 | 0.187 ± 0 | 11.9 ± 1.7 | 144 ± 0.48 | 0.363 ± 0.00091 | 132 ± 2.1 | 162 s, 1060 MB, 0.3 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 160 ± 0 | 0.187 ± 0 | 134 ± 0.00021 | 133 ± 0.00035 | 0.354 ± 5e-05 | 1.18 ± 0 | 161 s, 1060 MB, 0.3 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.0022 ± 0.005 | 0.187 ± 0 | 0.0005 ± 0.0011 | 129 ± 3.1 | 0.336 ± 0.0026 | 129 ± 3.1 | 162 s, 1060 MB, 0.4 s/replica |
| ProSiT con regole (profondita' 3) | 68.1 ± 14 | 0.0119 ± 0.0043 | 59.6 ± 12 | 125 ± 2.3 | 0.38 ± 0.0063 | 65.9 ± 13 | 9 s, 937 MB, 0.2 s/replica |
| ProSiT senza regole (profondita' 0) | 61 ± 16 | 0.0177 ± 0.0079 | 52.9 ± 15 | 126 ± 2 | 0.39 ± 0.0062 | 74.2 ± 16 | 4 s, 902 MB, 0.2 s/replica |
| AgentSimulator (scelta automatica) | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |

### Insurance_Claims_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.04 ± 0 | 0.034 ± 0.0045 | 0.0156 ± 0 | 2.52 ± 0.027 | 0.361 ± 0.0039 | 2.39 ± 0.018 | 0 s, 0 MB, 0.2 s/replica |
| SIMOD, calendari fissi | 13.3 ± 1.3 | 0.206 ± 2.1e-17 | 10.2 ± 1.1 | 141 ± 0.44 | 0.372 ± 0.00097 | 131 ± 1.3 | 111 s, 1063 MB, 0.4 s/replica |
| SIMOD con ritardi estranei | 13.4 ± 1.3 | 0.206 ± 2.1e-17 | 10.3 ± 1.1 | 141 ± 0.43 | 0.372 ± 0.00085 | 131 ± 1.3 | 192 s, 1063 MB, 0.4 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 158 ± 0 | 0.206 ± 2.1e-17 | 134 ± 0.00031 | 133 ± 0.00054 | 0.367 ± 7.7e-05 | 1.18 ± 0 | 191 s, 1063 MB, 0.3 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.04 ± 0 | 0.206 ± 2.1e-17 | 0.0156 ± 0 | 128 ± 2.6 | 0.348 ± 0.0025 | 129 ± 2.6 | 192 s, 1063 MB, 0.4 s/replica |
| ProSiT con regole (profondita' 3) | 70.9 ± 14 | 0.0285 ± 0.0047 | 61.7 ± 13 | 124 ± 3.8 | 0.389 ± 0.0096 | 62.8 ± 16 | 11 s, 936 MB, 0.2 s/replica |
| ProSiT senza regole (profondita' 0) | 59.3 ± 7.8 | 0.029 ± 0.0062 | 51.4 ± 7.2 | 125 ± 1.3 | 0.399 ± 0.0043 | 74 ± 7.3 | 7 s, 902 MB, 0.2 s/replica |
| AgentSimulator (scelta automatica) | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |

### Insurance_Claims_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.496 ± 0.0064 | 0.0168 ± 0.0057 | 0.136 ± 0.0011 | 2.54 ± 0.022 | 0.362 ± 0.0032 | 2.38 ± 0.018 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 13.6 ± 0.48 | 0.199 ± 0 | 10.3 ± 0.39 | 143 ± 0.15 | 0.374 ± 0.00056 | 133 ± 0.36 | 125 s, 1065 MB, 0.4 s/replica |
| SIMOD con ritardi estranei | 14.1 ± 0.5 | 0.199 ± 0 | 10.6 ± 0.41 | 143 ± 0.13 | 0.361 ± 0.00068 | 133 ± 0.37 | 214 s, 1065 MB, 0.6 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 158 ± 0.13 | 0.199 ± 0 | 134 ± 0.039 | 133 ± 0.038 | 0.354 ± 0.00027 | 1.17 ± 0 | 214 s, 1065 MB, 0.5 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.468 ± 0.042 | 0.199 ± 0 | 0.136 ± 0.0087 | 130 ± 1.1 | 0.337 ± 0.0013 | 130 ± 1.1 | 214 s, 1065 MB, 0.5 s/replica |
| ProSiT con regole (profondita' 3) | 28.1 ± 4.1 | 0.0157 ± 0.0028 | 23.4 ± 4 | 132 ± 1.7 | 0.397 ± 0.0038 | 108 ± 4.6 | 14 s, 935 MB, 0.3 s/replica |
| ProSiT senza regole (profondita' 0) | 31.5 ± 3.8 | 0.0113 ± 0.0039 | 26.5 ± 3.9 | 131 ± 1.3 | 0.4 ± 0.0031 | 104 ± 4 | 7 s, 902 MB, 0.2 s/replica |
| AgentSimulator (scelta automatica) | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |

### Insurance_Claims_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.035 ± 0.012 | 0.0228 ± 0.0053 | 0.155 ± 0.0028 | 2.56 ± 0.026 | 0.366 ± 0.0037 | 2.37 ± 0.02 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 12.3 ± 1.1 | 0.189 ± 0 | 9.77 ± 0.92 | 143 ± 0.37 | 0.387 ± 0.00093 | 134 ± 1.2 | 112 s, 1063 MB, 0.3 s/replica |
| SIMOD con ritardi estranei | 17.6 ± 2.1 | 0.189 ± 0 | 10 ± 1.6 | 145 ± 0.43 | 0.358 ± 0.00068 | 135 ± 1.8 | 196 s, 1063 MB, 0.5 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 162 ± 0.56 | 0.189 ± 0 | 134 ± 0.073 | 133 ± 0.074 | 0.349 ± 0.00024 | 1.18 ± 0 | 196 s, 1063 MB, 0.6 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.376 ± 0.00045 | 0.189 ± 0 | 0.0322 ± 0.013 | 133 ± 2.6 | 0.335 ± 0.0024 | 133 ± 2.6 | 196 s, 1063 MB, 0.6 s/replica |
| ProSiT con regole (profondita' 3) | 14.8 ± 2.3 | 0.0259 ± 0.0088 | 12.5 ± 1.9 | 136 ± 1.5 | 0.406 ± 0.0027 | 123 ± 3.1 | 11 s, 936 MB, 0.3 s/replica |
| ProSiT senza regole (profondita' 0) | 68.9 ± 16 | 0.0255 ± 0.0072 | 61.1 ± 14 | 123 ± 1.8 | 0.387 ± 0.008 | 62.8 ± 16 | 5 s, 902 MB, 0.3 s/replica |
| AgentSimulator (scelta automatica) | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |

### Insurance_Claims_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.065 ± 0.016 | 0.0171 ± 0.0038 | 0.0707 ± 0.0023 | 2.55 ± 0.026 | 0.364 ± 0.0038 | 2.36 ± 0.021 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 12.8 ± 0.75 | 0.184 ± 0 | 9.94 ± 0.65 | 141 ± 0.25 | 0.376 ± 0.00093 | 131 ± 0.7 | 124 s, 1059 MB, 0.4 s/replica |
| SIMOD con ritardi estranei | 12.8 ± 0.82 | 0.184 ± 0 | 9.93 ± 0.71 | 141 ± 0.28 | 0.376 ± 0.00089 | 131 ± 0.77 | 224 s, 1059 MB, 0.4 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 156 ± 0 | 0.184 ± 0 | 133 ± 0.0002 | 132 ± 0.00059 | 0.371 ± 8.5e-05 | 1.15 ± 0 | 224 s, 1059 MB, 0.4 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.632 ± 0 | 0.184 ± 0 | 0.178 ± 0 | 128 ± 1.8 | 0.353 ± 0.0019 | 128 ± 1.9 | 225 s, 1059 MB, 0.6 s/replica |
| ProSiT con regole (profondita' 3) | 31.5 ± 2.8 | 0.0162 ± 0.0061 | 28.1 ± 2.8 | 127 ± 2.3 | 0.394 ± 0.0053 | 98.8 ± 5 | 15 s, 936 MB, 0.5 s/replica |
| ProSiT senza regole (profondita' 0) | 92.7 ± 6.1 | 0.0161 ± 0.006 | 83.5 ± 6.1 | 115 ± 1.3 | 0.374 ± 0.0032 | 32.1 ± 6.4 | 8 s, 902 MB, 0.2 s/replica |
| AgentSimulator (scelta automatica) | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |

### Loan_Application

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 43.4 ± 1.1 | 0.103 ± 0.0057 | 28.2 ± 1.1 | 44.6 ± 3.6 | 0.161 ± 0.034 | 9.03 ± 2.6 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 31.1 ± 7.4 | 0.142 ± 0.011 | 21.4 ± 4.5 | 18.9 ± 2.2 | 0.346 ± 0.021 | 6.25 ± 1.4 | 162 s, 1100 MB, 1.1 s/replica |
| SIMOD con ritardi estranei | 36.8 ± 6.6 | 0.116 ± 0.01 | 22.2 ± 4.3 | 21.9 ± 3.2 | 0.337 ± 0.031 | 6.9 ± 1.2 | 290 s, 1100 MB, 0.8 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 30.4 ± 7.2 | 0.121 ± 0.0088 | 17.7 ± 4.7 | 20.7 ± 4.9 | 0.331 ± 0.029 | 7.92 ± 2.2 | 312 s, 1100 MB, 0.8 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 32.4 ± 7.1 | 0.116 ± 0.0096 | 19 ± 5.7 | 17.3 ± 5 | 0.328 ± 0.018 | 8.51 ± 1 | 290 s, 1100 MB, 0.8 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 95.6 ± 0.26 | 0.139 ± 0.0039 | 66.6 ± 0.076 | 72.1 ± 5.1 | 4.97 ± 1.2 | 6.17 ± 2.4 | 290 s, 1100 MB, 0.8 s/replica |
| ProSiT con regole (profondita' 3) | 44.7 ± 1.5 | 0.222 ± 0.0047 | 29.7 ± 1.4 | 32.2 ± 5.3 | 0.205 ± 0.036 | 6.29 ± 2 | 9 s, 948 MB, 0.5 s/replica |
| ProSiT senza regole (profondita' 0) | 47 ± 1.4 | 0.307 ± 0.0073 | 31.1 ± 1.3 | 31.5 ± 6.2 | 0.21 ± 0.047 | 5.77 ± 2.6 | 5 s, 914 MB, 0.2 s/replica |
| AgentSimulator (scelta automatica) | 49.9 ± 1.8 | 0.106 ± 0.0054 | 34.9 ± 1.4 | 18.7 ± 1.4 | 3.35 ± 0.0058 | 49.2 ± 2.7 | 150 s, 739 MB, 9.3 s/replica |

### Loan_Application_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 40.2 ± 1.2 | 0.0761 ± 0.0061 | 28.7 ± 1.2 | 31.6 ± 4.2 | 0.174 ± 0.014 | 7.79 ± 2.8 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 30.4 ± 5 | 0.208 ± 0.013 | 18.7 ± 2.9 | 12.3 ± 3.1 | 0.285 ± 0.022 | 6.49 ± 1.8 | 882 s, 2055 MB, 0.7 s/replica |
| SIMOD con ritardi estranei | 26.5 ± 3.7 | 0.197 ± 0.011 | 17.6 ± 2.3 | 9.66 ± 2.4 | 0.155 ± 0.013 | 6.37 ± 1.6 | 990 s, 2055 MB, 1.0 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 30.1 ± 2.7 | 0.197 ± 0.0094 | 19.9 ± 2 | 12.1 ± 2.4 | 0.144 ± 0.0058 | 10.6 ± 3.5 | 1013 s, 2055 MB, 0.8 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 23.9 ± 3 | 0.201 ± 0.0094 | 16.7 ± 2.2 | 15.4 ± 3.9 | 0.175 ± 0.032 | 7.07 ± 2.4 | 989 s, 2055 MB, 0.8 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 82.2 ± 0.47 | 0.201 ± 0.01 | 59.1 ± 0.35 | 51.7 ± 3.3 | 7.03 ± 0.098 | 6.15 ± 1.6 | 989 s, 2055 MB, 0.8 s/replica |
| ProSiT con regole (profondita' 3) | 39.7 ± 1.1 | 0.261 ± 0.0066 | 26.6 ± 1.2 | 12.2 ± 3.1 | 0.163 ± 0.039 | 10.5 ± 4.5 | 9 s, 950 MB, 0.3 s/replica |
| ProSiT senza regole (profondita' 0) | 38.4 ± 1.5 | 0.316 ± 0.0069 | 25.1 ± 1.3 | 12.7 ± 4.6 | 0.227 ± 0.035 | 9.83 ± 3.7 | 5 s, 916 MB, 0.3 s/replica |
| AgentSimulator (scelta automatica) | 51.4 ± 1.9 | 0.0757 ± 0.0072 | 37 ± 1.1 | 24.5 ± 2.5 | 3.36 ± 0.0067 | 50.6 ± 3.3 | 123 s, 745 MB, 8.2 s/replica |

### Loan_Application_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 47.2 ± 1.2 | 0.0983 ± 0.0047 | 32.4 ± 0.97 | 46.2 ± 6 | 0.205 ± 0.039 | 7.81 ± 2.1 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 56.4 ± 5.6 | 0.182 ± 0.0087 | 36 ± 3.8 | 25.6 ± 3.6 | 0.345 ± 0.036 | 11.8 ± 4.4 | 126 s, 1076 MB, 0.8 s/replica |
| SIMOD con ritardi estranei | 36.6 ± 4.2 | 0.206 ± 0.012 | 22 ± 2.8 | 9.65 ± 3.3 | 0.301 ± 0.021 | 11.6 ± 4.4 | 257 s, 1076 MB, 1.1 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 32 ± 4.6 | 0.199 ± 0.0099 | 19.7 ± 2.8 | 15.5 ± 4.3 | 0.281 ± 0.0098 | 9.82 ± 4.3 | 282 s, 1076 MB, 1.0 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 29.6 ± 4.2 | 0.211 ± 0.0056 | 18.5 ± 3 | 21 ± 5 | 0.289 ± 0.01 | 6.82 ± 1.7 | 257 s, 1076 MB, 0.9 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 87.1 ± 0.7 | 0.239 ± 0.007 | 58.3 ± 0.6 | 50.1 ± 4.3 | 6.64 ± 0.13 | 11.1 ± 3.9 | 258 s, 1076 MB, 1.0 s/replica |
| ProSiT con regole (profondita' 3) | 48.2 ± 0.79 | 0.288 ± 0.0073 | 29.9 ± 1 | 27.5 ± 5.3 | 0.177 ± 0.021 | 7.95 ± 2.4 | 11 s, 950 MB, 0.3 s/replica |
| ProSiT senza regole (profondita' 0) | 48.1 ± 1 | 0.305 ± 0.0066 | 29.6 ± 1.1 | 23.8 ± 6.7 | 0.206 ± 0.025 | 9.69 ± 3.8 | 7 s, 914 MB, 0.2 s/replica |
| AgentSimulator (scelta automatica) | 44.9 ± 2.5 | 0.0882 ± 0.0065 | 25.9 ± 2.2 | 20.7 ± 4.1 | 0.178 ± 0.052 | 41.7 ± 2.3 | 130 s, 739 MB, 8.4 s/replica |

### Loan_Application_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 46.6 ± 1 | 0.0548 ± 0.0057 | 29.7 ± 0.92 | 33 ± 4.6 | 0.286 ± 0.048 | 7.77 ± 2.1 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 25 ± 2.7 | 0.214 ± 0.0071 | 19.9 ± 1.5 | 25.5 ± 2.3 | 0.486 ± 0.039 | 10.9 ± 2.6 | 162 s, 1087 MB, 0.7 s/replica |
| SIMOD con ritardi estranei | 29.3 ± 4.6 | 0.21 ± 0.0052 | 23.9 ± 2.6 | 22.2 ± 2.7 | 0.382 ± 0.025 | 6.77 ± 2.8 | 283 s, 1087 MB, 1.0 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 32.5 ± 3.2 | 0.213 ± 0.0082 | 25.9 ± 1.7 | 17.6 ± 2.7 | 0.361 ± 0.02 | 3.79 ± 0.8 | 310 s, 1087 MB, 0.8 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 31 ± 3.3 | 0.209 ± 0.0042 | 25.1 ± 2 | 22.7 ± 5.3 | 0.354 ± 0.024 | 7.27 ± 1.7 | 282 s, 1087 MB, 0.8 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 95.2 ± 0.43 | 0.214 ± 0.0081 | 65.8 ± 0.058 | 66.9 ± 4.2 | 6.89 ± 0.17 | 7.27 ± 3.1 | 282 s, 1087 MB, 0.7 s/replica |
| ProSiT con regole (profondita' 3) | 46.5 ± 1.4 | 0.274 ± 0.0071 | 29.9 ± 1.4 | 26.6 ± 5.7 | 0.224 ± 0.06 | 6.32 ± 2.9 | 13 s, 944 MB, 0.4 s/replica |
| ProSiT senza regole (profondita' 0) | 48.4 ± 1.1 | 0.28 ± 0.009 | 29.8 ± 0.7 | 21 ± 4 | 0.213 ± 0.037 | 7.27 ± 2.5 | 7 s, 912 MB, 0.2 s/replica |
| AgentSimulator (scelta automatica) | fallito | fallito | fallito | fallito | fallito | fallito | — |

### Loan_Application_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 45.6 ± 1.5 | 0.0797 ± 0.0066 | 30.2 ± 0.9 | 38.5 ± 7.6 | 0.191 ± 0.033 | 8.14 ± 2.2 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 55.5 ± 5.3 | 0.164 ± 0.012 | 35.1 ± 3.7 | 38.8 ± 5.3 | 0.215 ± 0.02 | 7.23 ± 1.9 | 160 s, 1088 MB, 1.0 s/replica |
| SIMOD con ritardi estranei | 25.4 ± 5.7 | 0.174 ± 0.0097 | 21.2 ± 4 | 20.8 ± 3.8 | 0.278 ± 0.025 | 7.08 ± 2.1 | 295 s, 1088 MB, 1.1 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 28.2 ± 4.4 | 0.163 ± 0.0057 | 23.1 ± 3 | 18.9 ± 5.1 | 0.277 ± 0.021 | 7.28 ± 4.8 | 319 s, 1088 MB, 1.0 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 28.2 ± 2.9 | 0.166 ± 0.0045 | 23.3 ± 2.3 | 23.7 ± 4.7 | 0.26 ± 0.02 | 6.81 ± 1.2 | 292 s, 1088 MB, 0.8 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 94.7 ± 1.1 | 0.22 ± 0.0088 | 68.1 ± 0.58 | 71.6 ± 6.5 | 6.99 ± 0.088 | 7.66 ± 2.1 | 293 s, 1088 MB, 0.9 s/replica |
| ProSiT con regole (profondita' 3) | 50.9 ± 1.3 | 0.215 ± 0.0062 | 33.2 ± 1.8 | 34.9 ± 9.2 | 0.157 ± 0.028 | 9.76 ± 4 | 12 s, 947 MB, 0.4 s/replica |
| ProSiT senza regole (profondita' 0) | 52.9 ± 1.1 | 0.261 ± 0.0049 | 33.3 ± 1.5 | 25.8 ± 6.6 | 0.172 ± 0.044 | 9.42 ± 3.6 | 7 s, 914 MB, 0.2 s/replica |
| AgentSimulator (scelta automatica) | 59.1 ± 3.1 | 0.0854 ± 0.003 | 39.5 ± 2.5 | 19.7 ± 1.6 | 3.06 ± 0.44 | 48.9 ± 1.3 | 148 s, 744 MB, 9.8 s/replica |

### Pharmacy

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.0768 ± 0.025 | 0.0158 ± 0.0046 | 0.0265 ± 0.0097 | 31.9 ± 0.31 | 7.44 ± 0.011 | 32 ± 0.32 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 1.6 ± 0.21 | 0.0374 ± 0.0019 | 0.792 ± 0.14 | 133 ± 0.11 | 7.43 ± 0.0041 | 132 ± 0.12 | 119 s, 1047 MB, 0.6 s/replica |
| SIMOD con ritardi estranei | 1.7 ± 0.28 | 0.0354 ± 0.0022 | 0.784 ± 0.15 | 133 ± 0.09 | 7.43 ± 0.0042 | 132 ± 0.12 | 171 s, 1047 MB, 0.5 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 65.3 ± 0.57 | 0.0347 ± 0.0011 | 51.1 ± 0.28 | 123 ± 0.084 | 7.39 ± 0.0079 | 73.2 ± 0.24 | 170 s, 1047 MB, 0.5 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.192 ± 0 | 0.0364 ± 0.0013 | 0.0635 ± 0 | 132 ± 0.14 | 7.42 ± 0.0028 | 132 ± 0.12 | 173 s, 1047 MB, 0.8 s/replica |
| ProSiT con regole (profondita' 3) | 1.63 ± 0.11 | 0.0185 ± 0.004 | 0.709 ± 0.077 | 133 ± 0.12 | 7.43 ± 0.0032 | 132 ± 0.00045 | 8 s, 911 MB, 0.3 s/replica |
| ProSiT senza regole (profondita' 0) | 1.62 ± 0.19 | 0.0173 ± 0.004 | 0.9 ± 0.2 | 133 ± 0.22 | 7.43 ± 0.0018 | 132 ± 0.008 | 4 s, 890 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | 0.395 ± 0.36 | 0.0374 ± 0.0031 | 0.188 ± 0.15 | 136 ± 0.15 | 7.42 ± 0.0032 | 136 ± 0 | 34 s, 698 MB, 1.9 s/replica |

### Pharmacy_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.113 ± 0.041 | 0.0202 ± 0.0033 | 0.0365 ± 0.018 | 31.9 ± 0.3 | 7.43 ± 0.011 | 32 ± 0.32 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 1.6 ± 0.2 | 0.0364 ± 0.0034 | 0.731 ± 0.19 | 133 ± 0.15 | 7.43 ± 0.0023 | 133 ± 0.00045 | 122 s, 1048 MB, 0.5 s/replica |
| SIMOD con ritardi estranei | 1.87 ± 0.24 | 0.0329 ± 0.0025 | 0.799 ± 0.11 | 133 ± 0.083 | 7.43 ± 0.0025 | 132 ± 0.11 | 197 s, 1049 MB, 0.6 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 44.5 ± 0.35 | 0.0322 ± 0.0017 | 32 ± 0.17 | 126 ± 0.078 | 7.53 ± 0.0055 | 94 ± 0.17 | 196 s, 1049 MB, 0.4 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.264 ± 0 | 0.0349 ± 0.0027 | 0.0828 ± 0 | 132 ± 0.14 | 7.41 ± 0.0034 | 132 ± 0.11 | 196 s, 1049 MB, 0.5 s/replica |
| ProSiT con regole (profondita' 3) | 2.53 ± 0.091 | 0.0201 ± 0.0027 | 1.15 ± 0.16 | 133 ± 0.16 | 7.43 ± 0.0015 | 132 ± 0.00045 | 5 s, 912 MB, 0.1 s/replica |
| ProSiT senza regole (profondita' 0) | 2.25 ± 0.19 | 0.0185 ± 0.0036 | 1.03 ± 0.083 | 133 ± 0.1 | 7.42 ± 0.002 | 132 ± 0 | 4 s, 891 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | 0.398 ± 0.23 | 0.0406 ± 0.0025 | 0.0934 ± 0.088 | 136 ± 0.069 | 7.43 ± 0.0015 | 136 ± 0 | 34 s, 693 MB, 1.6 s/replica |

### Pharmacy_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.149 ± 0.089 | 0.0216 ± 0.0035 | 0.0487 ± 0.029 | 32 ± 0.31 | 7.44 ± 0.011 | 32 ± 0.32 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 1.43 ± 0.15 | 0.035 ± 0.0043 | 0.611 ± 0.071 | 133 ± 0.071 | 7.43 ± 0.002 | 133 ± 0 | 122 s, 1048 MB, 0.5 s/replica |
| SIMOD con ritardi estranei | 1.38 ± 0.13 | 0.0356 ± 0.0033 | 0.585 ± 0.046 | 133 ± 0.08 | 7.43 ± 0.0022 | 133 ± 0 | 205 s, 1048 MB, 0.5 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 76.2 ± 0.41 | 0.0376 ± 0.0037 | 61.3 ± 0.23 | 121 ± 0.14 | 7.34 ± 0.012 | 64.4 ± 0.22 | 205 s, 1048 MB, 0.5 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.456 ± 4.2e-17 | 0.0368 ± 0.002 | 0.168 ± 0 | 132 ± 0.048 | 7.42 ± 0.00094 | 133 ± 0.00045 | 206 s, 1048 MB, 0.6 s/replica |
| ProSiT con regole (profondita' 3) | 2.31 ± 0.14 | 0.0184 ± 0.002 | 1.13 ± 0.11 | 133 ± 0.16 | 7.43 ± 0.003 | 132 ± 0 | 7 s, 915 MB, 0.3 s/replica |
| ProSiT senza regole (profondita' 0) | 1.92 ± 0.24 | 0.0198 ± 0.004 | 0.86 ± 0.13 | 133 ± 0.16 | 7.43 ± 0.0024 | 132 ± 0 | 5 s, 890 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | 0.449 ± 0.12 | 0.0509 ± 0.0038 | 0.165 ± 0.064 | 135 ± 0.087 | 7.42 ± 0.0012 | 136 ± 0 | 37 s, 694 MB, 1.8 s/replica |

### Pharmacy_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.0838 ± 0.046 | 0.0228 ± 0.0024 | 0.0495 ± 0.026 | 32 ± 0.31 | 7.43 ± 0.0097 | 32 ± 0.32 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 1.35 ± 0.19 | 0.0421 ± 0.0026 | 0.698 ± 0.11 | 133 ± 0.097 | 7.44 ± 0.0029 | 132 ± 0.12 | 157 s, 1047 MB, 0.5 s/replica |
| SIMOD con ritardi estranei | 1.14 ± 0.19 | 0.0448 ± 0.0029 | 0.582 ± 0.16 | 133 ± 0.18 | 7.44 ± 0.0014 | 133 ± 0 | 239 s, 1047 MB, 0.5 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 96.6 ± 0.39 | 0.0427 ± 0.0016 | 79.8 ± 0.32 | 118 ± 0.18 | 7.25 ± 0.022 | 49.1 ± 0.28 | 239 s, 1047 MB, 0.4 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.432 ± 4.2e-17 | 0.0443 ± 0.0032 | 0.176 ± 0 | 132 ± 0.031 | 7.42 ± 0.0016 | 133 ± 0 | 239 s, 1047 MB, 0.5 s/replica |
| ProSiT con regole (profondita' 3) | 2.5 ± 0.13 | 0.0234 ± 0.0022 | 1.31 ± 0.066 | 134 ± 0.091 | 7.43 ± 0.001 | 132 ± 0 | 5 s, 914 MB, 0.1 s/replica |
| ProSiT senza regole (profondita' 0) | 2.36 ± 0.29 | 0.0207 ± 0.0041 | 1.49 ± 0.14 | 134 ± 0.14 | 7.43 ± 0.002 | 132 ± 0 | 3 s, 891 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | 0.442 ± 0.14 | 0.047 ± 0.0037 | 0.15 ± 0.055 | 136 ± 0.12 | 7.42 ± 0.0034 | 136 ± 0 | 30 s, 695 MB, 1.2 s/replica |

### Pharmacy_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 0.118 ± 0.051 | 0.0248 ± 0.0033 | 0.0495 ± 0.02 | 32 ± 0.28 | 7.44 ± 0.012 | 32 ± 0.32 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 1.02 ± 0.061 | 0.0349 ± 0.0027 | 0.44 ± 0.099 | 133 ± 0.14 | 7.44 ± 0.0031 | 132 ± 0.12 | 138 s, 1047 MB, 0.5 s/replica |
| SIMOD con ritardi estranei | 1.01 ± 0.065 | 0.0342 ± 0.0027 | 0.44 ± 0.1 | 133 ± 0.12 | 7.44 ± 0.0017 | 132 ± 0.11 | 216 s, 1047 MB, 0.7 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | non applicabile | — |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 86.8 ± 0.51 | 0.0343 ± 0.0023 | 70.8 ± 0.23 | 119 ± 0.15 | 7.29 ± 0.02 | 56.6 ± 0.16 | 215 s, 1047 MB, 0.5 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 0.24 ± 0.00045 | 0.0353 ± 0.0024 | 0.109 ± 0.0003 | 132 ± 0.11 | 7.43 ± 0.0026 | 132 ± 0.12 | 216 s, 1047 MB, 0.6 s/replica |
| ProSiT con regole (profondita' 3) | 1.45 ± 0.15 | 0.026 ± 0.0029 | 0.694 ± 0.18 | 133 ± 0.17 | 7.43 ± 0.0021 | 132 ± 0.00045 | 4 s, 911 MB, 0.2 s/replica |
| ProSiT senza regole (profondita' 0) | 1.33 ± 0.15 | 0.0226 ± 0.0034 | 0.614 ± 0.1 | 133 ± 0.091 | 7.43 ± 0.0019 | 132 ± 0 | 3 s, 891 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | 0.476 ± 0.16 | 0.0602 ± 0.0029 | 0.131 ± 0.073 | 137 ± 0.075 | 7.42 ± 0.0017 | 137 ± 0 | 29 s, 693 MB, 1.2 s/replica |

### Procure_to_Pay

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 6.41 ± 1.4 | 0.0327 ± 0.01 | 4.34 ± 0.66 | 52.7 ± 9.1 | 0.107 ± 0.016 | 40.3 ± 8.9 | 0 s, 0 MB, 0.1 s/replica |
| SIMOD, calendari fissi | 516 ± 17 | 0.241 ± 0.0012 | 282 ± 8.9 | 267 ± 7.7 | 0.181 ± 0.016 | 13.7 ± 4.4 | 174 s, 1092 MB, 1.3 s/replica |
| SIMOD con ritardi estranei | 509 ± 48 | 0.243 ± 0.0018 | 269 ± 28 | 252 ± 25 | 0.195 ± 0.012 | 15 ± 4 | 324 s, 1093 MB, 1.2 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 448 ± 29 | 0.243 ± 0.0029 | 232 ± 16 | 234 ± 15 | 0.2 ± 0.014 | 7.17 ± 2.6 | 351 s, 1093 MB, 1.9 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 540 ± 24 | 0.242 ± 0.0017 | 284 ± 14 | 248 ± 13 | 0.186 ± 0.014 | 34.7 ± 7.9 | 321 s, 1093 MB, 0.9 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 34.7 ± 0.068 | 0.242 ± 0.0015 | 24.3 ± 0.033 | 42 ± 3.9 | 5.58 ± 0.018 | 16.2 ± 4 | 324 s, 1093 MB, 0.9 s/replica |
| ProSiT con regole (profondita' 3) | 9.61 ± 1.8 | 0.0381 ± 0.0066 | 6.28 ± 0.82 | 9.71 ± 3 | 0.0976 ± 0.011 | 4.31 ± 2 | 9 s, 940 MB, 0.3 s/replica |
| ProSiT senza regole (profondita' 0) | 10.1 ± 2 | 0.0692 ± 0.0092 | 6.73 ± 0.82 | 10.7 ± 2.9 | 0.0928 ± 0.011 | 4.33 ± 1.9 | 5 s, 901 MB, 0.1 s/replica |
| AgentSimulator (scelta automatica) | 19.6 ± 2.9 | 0.0588 ± 0.0055 | 22.7 ± 3.4 | 30.7 ± 6.2 | 1.51 ± 1.2 | 13.7 ± 1.3e-15 | 46 s, 724 MB, 1.5 s/replica |

### Procure_to_Pay_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 3.6 ± 0.55 | 0.0253 ± 0.0069 | 1.7 ± 0.38 | 43.5 ± 9.3 | 0.108 ± 0.018 | 40.3 ± 8.9 | 0 s, 0 MB, 0.2 s/replica |
| SIMOD, calendari fissi | 419 ± 20 | 0.248 ± 0.0013 | 221 ± 9.1 | 208 ± 7.2 | 0.24 ± 0.023 | 11 ± 4.2 | 168 s, 1101 MB, 1.1 s/replica |
| SIMOD con ritardi estranei | 390 ± 28 | 0.25 ± 0.0017 | 200 ± 16 | 181 ± 18 | 0.154 ± 0.016 | 17.1 ± 2.6 | 300 s, 1101 MB, 1.2 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 372 ± 26 | 0.248 ± 0.0011 | 191 ± 15 | 195 ± 12 | 0.163 ± 0.017 | 8.11 ± 4.2 | 328 s, 1101 MB, 1.0 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 437 ± 35 | 0.247 ± 0.00098 | 222 ± 20 | 185 ± 12 | 0.156 ± 0.01 | 35.4 ± 8.3 | 299 s, 1101 MB, 0.9 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 40.9 ± 0.24 | 0.249 ± 0.00071 | 29.9 ± 0.058 | 49.9 ± 2.7 | 8.28 ± 0.98 | 18 ± 2.7 | 299 s, 1101 MB, 1.1 s/replica |
| ProSiT con regole (profondita' 3) | 4.92 ± 0.95 | 0.0247 ± 0.0091 | 2.18 ± 0.6 | 15.6 ± 4.5 | 0.12 ± 0.014 | 5.1 ± 2.6 | 10 s, 941 MB, 0.3 s/replica |
| ProSiT senza regole (profondita' 0) | 4.12 ± 0.93 | 0.0531 ± 0.0039 | 1.63 ± 0.5 | 13 ± 3.2 | 0.0992 ± 0.014 | 6.09 ± 1.8 | 6 s, 900 MB, 0.2 s/replica |
| AgentSimulator (scelta automatica) | 7.61 ± 0.82 | 0.0692 ± 0.0056 | 6.63 ± 1.9 | 15.4 ± 1.8 | 3.16 ± 0.74 | 1.58 ± 0 | 43 s, 720 MB, 1.5 s/replica |

### Procure_to_Pay_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 7.8 ± 1.3 | 0.0289 ± 0.0098 | 4.23 ± 0.47 | 58.5 ± 11 | 0.104 ± 0.01 | 40.3 ± 8.9 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 352 ± 29 | 0.219 ± 0.0021 | 184 ± 17 | 159 ± 16 | 0.172 ± 0.024 | 18.1 ± 1.9 | 161 s, 1087 MB, 1.0 s/replica |
| SIMOD con ritardi estranei | 324 ± 28 | 0.22 ± 0.0016 | 165 ± 15 | 146 ± 16 | 0.167 ± 0.012 | 12.4 ± 3.8 | 292 s, 1087 MB, 0.9 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 299 ± 31 | 0.222 ± 0.003 | 153 ± 18 | 149 ± 18 | 0.151 ± 0.013 | 6.71 ± 2.1 | 315 s, 1087 MB, 0.9 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 400 ± 22 | 0.22 ± 0.0017 | 205 ± 13 | 164 ± 13 | 0.148 ± 0.0096 | 33.3 ± 8.2 | 292 s, 1087 MB, 0.9 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 50.4 ± 0.053 | 0.222 ± 0.0013 | 33.4 ± 0.036 | 54.9 ± 3.9 | 5.69 ± 0.023 | 14.2 ± 3.9 | 293 s, 1087 MB, 1.4 s/replica |
| ProSiT con regole (profondita' 3) | 10.8 ± 0.96 | 0.0341 ± 0.0078 | 4.41 ± 0.58 | 15.4 ± 4 | 0.115 ± 0.011 | 4.44 ± 1.8 | 10 s, 942 MB, 0.3 s/replica |
| ProSiT senza regole (profondita' 0) | 10 ± 0.93 | 0.0613 ± 0.0056 | 4.29 ± 0.4 | 16 ± 5.8 | 0.106 ± 0.0064 | 6.2 ± 1.7 | 5 s, 901 MB, 0.2 s/replica |
| AgentSimulator (scelta automatica) | 10.8 ± 1.1 | 0.0905 ± 0.0072 | 8.45 ± 2.5 | 11.5 ± 3.8 | 1.47 ± 1.2 | 8.8 ± 0 | 44 s, 718 MB, 1.5 s/replica |

### Procure_to_Pay_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 3.23 ± 0.66 | 0.0238 ± 0.0051 | 2.35 ± 0.51 | 39 ± 11 | 0.0897 ± 0.01 | 40.3 ± 8.9 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 330 ± 21 | 0.228 ± 0.0031 | 162 ± 13 | 159 ± 12 | 0.181 ± 0.016 | 13.4 ± 2.4 | 182 s, 1092 MB, 1.2 s/replica |
| SIMOD con ritardi estranei | 403 ± 25 | 0.226 ± 0.0024 | 209 ± 17 | 205 ± 15 | 0.166 ± 0.014 | 13.2 ± 4.8 | 344 s, 1092 MB, 1.6 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 348 ± 18 | 0.227 ± 0.0027 | 176 ± 12 | 189 ± 9.4 | 0.164 ± 0.01 | 6.06 ± 4.4 | 368 s, 1092 MB, 1.3 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 435 ± 16 | 0.226 ± 0.0017 | 225 ± 10 | 196 ± 8.4 | 0.154 ± 0.01 | 37.8 ± 8.6 | 341 s, 1092 MB, 1.3 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 52.2 ± 0.67 | 0.226 ± 0.0026 | 34.8 ± 0.28 | 38.4 ± 5.6 | 8.96 ± 0.039 | 13.6 ± 4.9 | 341 s, 1092 MB, 1.3 s/replica |
| ProSiT con regole (profondita' 3) | 5.71 ± 0.95 | 0.0306 ± 0.0068 | 2.54 ± 0.47 | 8.77 ± 1 | 0.124 ± 0.015 | 4.82 ± 2 | 9 s, 948 MB, 0.2 s/replica |
| ProSiT senza regole (profondita' 0) | 4.38 ± 1.2 | 0.052 ± 0.0057 | 2.54 ± 0.67 | 11.9 ± 3.8 | 0.11 ± 0.011 | 7.09 ± 2 | 5 s, 901 MB, 0.2 s/replica |
| AgentSimulator (scelta automatica) | 13.9 ± 1.2 | 0.0774 ± 0.009 | 15.3 ± 2.7 | 25.4 ± 4.2 | 2.46 ± 1.1 | 7.03 ± 6.7e-16 | 52 s, 720 MB, 2.8 s/replica |

### Procure_to_Pay_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo (tempo, picco, replica più lenta) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| "B = A" (gemello ingenuo di SIM-36) | 3.37 ± 0.84 | 0.0324 ± 0.006 | 1.66 ± 0.47 | 41.9 ± 11 | 0.104 ± 0.013 | 40.3 ± 8.9 | 0 s, 0 MB, 0.0 s/replica |
| SIMOD, calendari fissi | 477 ± 32 | 0.246 ± 0.0028 | 256 ± 17 | 236 ± 18 | 0.133 ± 0.014 | 20.1 ± 3.3 | 170 s, 1099 MB, 0.9 s/replica |
| SIMOD con ritardi estranei | 571 ± 33 | 0.247 ± 0.0039 | 304 ± 17 | 283 ± 15 | 0.255 ± 0.016 | 20.7 ± 4.4 | 358 s, 1099 MB, 1.4 s/replica |
| SIMOD con ritardi estranei + arrivi AT-KDE | 492 ± 25 | 0.248 ± 0.0024 | 260 ± 13 | 263 ± 11 | 0.238 ± 0.016 | 7.5 ± 2.3 | 392 s, 1099 MB, 2.0 s/replica |
| SIMOD con ritardi estranei + arrivi di A rigiocati (diagnosi) | 579 ± 41 | 0.248 ± 0.0017 | 308 ± 21 | 270 ± 15 | 0.245 ± 0.015 | 38.4 ± 8.6 | 356 s, 1099 MB, 1.4 s/replica |
| SIMOD con ritardi estranei, calendari 24/7 (ablazione) | 37 ± 0.6 | 0.249 ± 0.0025 | 29.4 ± 0.4 | 50.1 ± 4.8 | 9.19 ± 0.033 | 20.9 ± 4.4 | 363 s, 1099 MB, 2.2 s/replica |
| ProSiT con regole (profondita' 3) | 3.92 ± 0.66 | 0.0266 ± 0.0095 | 1.6 ± 0.48 | 12.3 ± 2.3 | 0.121 ± 0.011 | 4.67 ± 2.3 | 16 s, 944 MB, 0.5 s/replica |
| ProSiT senza regole (profondita' 0) | 2.56 ± 0.57 | 0.059 ± 0.0035 | 1.71 ± 0.36 | 12.4 ± 2.6 | 0.108 ± 0.011 | 6.01 ± 1.8 | 9 s, 900 MB, 0.4 s/replica |
| AgentSimulator (scelta automatica) | 13.7 ± 1.2 | 0.0982 ± 0.0061 | 11 ± 1.9 | 14.1 ± 1.7 | 2.17 ± 1.2 | 8.07 ± 0 | 67 s, 721 MB, 2.2 s/replica |
