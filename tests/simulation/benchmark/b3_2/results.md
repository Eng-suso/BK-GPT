# B3.2: discovery delle attese

Generato da `tests/simulation/benchmark/b3_2/report.py`. Distanze di B2 (ore, NGD in [0, 1]), media ±
semiampiezza IC 95% su 10 repliche; (NV) = NOT VALIDATED. Più basso è meglio. Regole di `g3b/report.py`.

## Verdetti

| Scheda | Componente | Fase | Verdetto | V / P / P | Motivi |
| --- | --- | --- | --- | --- | --- |
| 1 | Ablazione dei ritardi estranei | validation | **NO-GO** | 1 / 2 / 4 | contro simod: RED vince su 1/7 log; contro simod: RED perde su Insurance_Claims, Insurance_Claims_1_timer, Insurance_Claims_3_timers, Insurance_Claims_5_timers_after; contro simod: guardia W1 perde su 5 log; contro simod: guardia NGD perde su 5 log; contro simod: guardia CAR perde su 2 log |
| 3 | Attese attribuite: W1 | validation | **NOT VALIDATED** | — | W1 identificabile in 1 log |
| 3 | Attese attribuite: RED | validation | **NOT VALIDATED** | — | RED identificabile in 1 log |

## Metriche, fase validation

### AcademicCredentials

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 104 ± 1.4 (NV) | 0.313 ± 0.0076 (NV) | 39.9 ± 0.61 (NV) | 268 ± 11 | 5.56 ± 0.37 | 220 ± 12 (NV) | 134 s, 1102 MB, 0.2 s/replica | — |
| simod_fixed_extr | 227 ± 27 (NV) | 0.337 ± 0.0086 (NV) | 117 ± 12 (NV) | 215 ± 14 | 5.03 ± 0.63 | 220 ± 12 (NV) | 168 s, 1102 MB, 0.2 s/replica | Avanzar recepcion documentos: 346983, Cancelar Solicitud: 45360, Cancelar curso: 919164, Evaluacion curso: 1102 … |
| simod_attr_extr | 221 ± 31 (NV) | 0.305 ± 0.0099 (NV) | 100 ± 14 (NV) | 171 ± 9.9 | 4.55 ± 0.88 | 219 ± 12 (NV) | 134 s, 1102 MB, 0.2 s/replica | Validar solicitud: 48537, Evaluacion curso: 27799, Notificacion estudiante cancelacion soli: 692785, Validacion final: 387295 … |

### BPIC_2012_W

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 54.9 ± 0.11 | 0.652 ± 0.0076 | 73 ± 0.15 | 130 ± 3.9 | 3.77 ± 0.058 | 96.1 ± 3.5 | 527 s, 1215 MB, 0.9 s/replica | — |
| simod_fixed_extr | 116 ± 6.4 | 0.588 ± 0.0064 | 61.3 ± 7.3 | 68.3 ± 2.9 | 4.55 ± 0.038 | 93.9 ± 3.5 | 818 s, 1215 MB, 2.0 s/replica | W_Afhandelen leads: 648, W_Beoordelen fraude: 41875, W_Completeren aanvraag: 25621, W_Nabellen incomplete dossiers: 37975 … |
| simod_attr_extr | 126 ± 6.3 | 0.582 ± 0.0041 | 61.9 ± 7.3 | 65.1 ± 2.9 | 4.67 ± 0.027 | 92.4 ± 3.5 | 533 s, 1215 MB, 2.0 s/replica | W_Nabellen offertes: 257375, W_Valideren aanvraag: 122892, W_Completeren aanvraag: 34884, W_Nabellen incomplete dossiers: 38640 … |

### Insurance_Claims

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 0 ± 0 | 0.162 ± 0 | 0 ± 0 | 163 ± 1.1 | 0.281 ± 0.0014 | 163 ± 1.1 | 116 s, 1057 MB, 0.1 s/replica | — |
| simod_fixed_extr | 0 ± 0 | 0.162 ± 0 | 0 ± 0 | 163 ± 1.1 | 0.281 ± 0.0014 | 163 ± 1.1 | 126 s, 1057 MB, 0.1 s/replica | — |

### Insurance_Claims_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 0 ± 0 | 0.127 ± 0 | 0 ± 0 | 146 ± 1.9 | 0.28 ± 0.0031 | 146 ± 1.9 | 120 s, 1052 MB, 0.2 s/replica | — |
| simod_fixed_extr | 0 ± 0 | 0.127 ± 0 | 0 ± 0 | 146 ± 1.9 | 0.28 ± 0.0031 | 146 ± 1.9 | 152 s, 1052 MB, 0.1 s/replica | — |

### Insurance_Claims_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 0.17 ± 0 | 0.177 ± 0 | 0.0472 ± 0 | 161 ± 1 | 0.302 ± 0.0011 | 161 ± 1 | 135 s, 1059 MB, 0.1 s/replica | — |
| simod_fixed_extr | 0.17 ± 0 | 0.177 ± 0 | 0.0472 ± 0 | 161 ± 1 | 0.302 ± 0.0011 | 161 ± 1 | 175 s, 1059 MB, 0.2 s/replica | — |

### Insurance_Claims_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 53 ± 1.8 | 0.185 ± 0 | 17.5 ± 0.98 | 17.6 ± 0.99 | 0.0795 ± 0.0019 | 0 ± 0 | 147 s, 1058 MB, 0.2 s/replica | — |
| simod_fixed_extr | 53 ± 1.8 | 0.185 ± 0 | 17.5 ± 0.98 | 17.6 ± 0.99 | 0.0795 ± 0.0019 | 0 ± 0 | 185 s, 1058 MB, 0.2 s/replica | — |

### Insurance_Claims_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 0.58 ± 0 | 0.213 ± 2.1e-17 | 0.113 ± 0 | 166 ± 0.0042 | 0.312 ± 0.00061 | 166 ± 0 | 113 s, 1058 MB, 0.1 s/replica | — |
| simod_fixed_extr | 0.58 ± 0 | 0.213 ± 2.1e-17 | 0.113 ± 0 | 166 ± 0.0042 | 0.312 ± 0.00061 | 166 ± 0 | 145 s, 1058 MB, 0.1 s/replica | — |

### Loan_Application

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 33.4 ± 2.5 | 0.117 ± 0.021 | 21 ± 2.2 | 15.6 ± 4.1 | 0.628 ± 0.081 | 4.83 ± 1.8 | 126 s, 1091 MB, 0.2 s/replica | — |
| simod_fixed_extr | 33.2 ± 2.5 | 0.166 ± 0.013 | 23 ± 2.5 | 17.6 ± 2.9 | 0.67 ± 0.048 | 4.97 ± 1.7 | 180 s, 1091 MB, 0.2 s/replica | Approve application: 13635, Cancel application: 2671, Prepare home insurance quote: 929, Reject application: 220 |


## Metriche, fase test
