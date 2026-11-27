# B3.2: discovery delle attese

Generato da `tests/simulation/benchmark/b3_2/report.py`. Distanze di B2 (ore, NGD in [0, 1]), media ±
semiampiezza IC 95% su 10 repliche; (NV) = NOT VALIDATED. Più basso è meglio. Regole di `g3b/report.py`.

## Verdetti

| Scheda | Componente | Fase | Verdetto | V / P / P | Motivi |
| --- | --- | --- | --- | --- | --- |
| 1 | Ablazione dei ritardi estranei | validation | **NO-GO** | 4 / 18 / 0 | contro simod: RED vince su 4/22 log; contro simod: guardia CED perde su 2 log |
| 1 | Ablazione dei ritardi estranei | test | **NO-GO** | 0 / 6 / 0 | contro simod: RED vince su 0/6 log; candidato non misurato (fallito, fuori budget o non applicabile) su 17 log (AcademicCredentials, BPIC_2012_W, BPIC_2017_W, ...) |
| 3 | Attese attribuite: W1 | validation | **NO-GO** | 0 / 1 / 1 | contro simod_extr: W1 vince su 0/2 log; contro simod_extr: W1 perde su BPIC_2017_W |
| 3 | Attese attribuite: RED | validation | **NO-GO** | 0 / 1 / 1 | contro simod_extr: RED vince su 0/2 log; contro simod_extr: RED perde su BPIC_2017_W |

## Metriche, fase validation

### AcademicCredentials

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 104 ± 1.4 (NV) | 0.313 ± 0.0076 (NV) | 39.9 ± 0.61 (NV) | 268 ± 11 | 5.56 ± 0.37 | 220 ± 12 (NV) | 134 s, 1102 MB, 0.2 s/replica | — |
| simod_fixed_extr | 227 ± 27 (NV) | 0.337 ± 0.0086 (NV) | 117 ± 12 (NV) | 215 ± 14 | 5.03 ± 0.63 | 220 ± 12 (NV) | 168 s, 1102 MB, 0.2 s/replica | Avanzar recepcion documentos: 346983, Cancelar Solicitud: 45360, Cancelar curso: 919164, Evaluacion curso: 1102 … |
| simod_attr_extr | 221 ± 31 (NV) | 0.305 ± 0.0099 (NV) | 100 ± 14 (NV) | 171 ± 9.9 | 4.55 ± 0.88 | 219 ± 12 (NV) | 134 s, 1102 MB, 0.2 s/replica | Validar solicitud: 48537, Evaluacion curso: 27799, Notificacion estudiante cancelacion soli: 692785, Validacion final: 387295 … |
| simod_extr | 231 ± 19 (NV) | 0.3 ± 0.011 (NV) | 99.4 ± 16 (NV) | 173 ± 12 | 4.35 ± 0.8 | 220 ± 12 (NV) | 224 s, 1102 MB, 0.3 s/replica | — |

### BPIC_2012_W

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 54.9 ± 0.11 | 0.652 ± 0.0076 | 73 ± 0.15 | 130 ± 3.9 | 3.77 ± 0.058 | 96.1 ± 3.5 | 527 s, 1215 MB, 0.9 s/replica | — |
| simod_fixed_extr | 116 ± 6.4 | 0.588 ± 0.0064 | 61.3 ± 7.3 | 68.3 ± 2.9 | 4.55 ± 0.038 | 93.9 ± 3.5 | 818 s, 1215 MB, 2.0 s/replica | W_Afhandelen leads: 648, W_Beoordelen fraude: 41875, W_Completeren aanvraag: 25621, W_Nabellen incomplete dossiers: 37975 … |
| simod_attr_extr | 126 ± 6.3 | 0.582 ± 0.0041 | 61.9 ± 7.3 | 65.1 ± 2.9 | 4.67 ± 0.027 | 92.4 ± 3.5 | 533 s, 1215 MB, 2.0 s/replica | W_Nabellen offertes: 257375, W_Valideren aanvraag: 122892, W_Completeren aanvraag: 34884, W_Nabellen incomplete dossiers: 38640 … |
| simod_extr | 113 ± 9.3 | 0.587 ± 0.0072 | 57.5 ± 6.5 | 62 ± 3.9 | 4.75 ± 0.044 | 82.6 ± 4.9 | 1042 s, 1215 MB, 1.6 s/replica | — |

### BPIC_2017_W

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 199 ± 0.043 | 0.371 ± 0.0031 | 130 ± 0.057 | 184 ± 4.6 | 1.09 ± 0.062 | 78.8 ± 4.5 | 1608 s, 8775 MB, 2.0 s/replica | — |
| simod_fixed_extr | 97.4 ± 3.7 | 0.369 ± 0.0025 | 66.2 ± 2.8 | 50.7 ± 2 | 1.98 ± 0.018 | 68.8 ± 4.4 | 2383 s, 8775 MB, 4.0 s/replica | W_Assess potential fraud: 81620, W_Call after offers: 190754, W_Call incomplete files: 94720, W_Complete application: 36015 … |
| simod_attr_extr | 111 ± 4.4 | 0.371 ± 0.0035 | 79.7 ± 5.5 | 54.5 ± 3.9 | 2.1 ± 0.017 | 59.9 ± 3.9 | 1621 s, 8775 MB, 3.6 s/replica | W_Call after offers: 198671, W_Shortened completion: 29003, W_Assess potential fraud: 81751, W_Call incomplete files: 94537 … |
| simod_extr | 98.5 ± 3.6 | 0.37 ± 0.002 | 65 ± 2.4 | 48.9 ± 1.9 | 1.94 ± 0.018 | 70.5 ± 3.5 | 2808 s, 8775 MB, 3.1 s/replica | — |

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

### Loan_Application_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 32.8 ± 4.4 | 0.147 ± 0.024 | 17.7 ± 3.1 | 14.2 ± 3.5 | 0.475 ± 0.055 | 3.99 ± 1.6 | 1089 s, 1972 MB, 0.2 s/replica | — |
| simod_fixed_extr | 22.2 ± 4.6 | 0.13 ± 0.035 | 15.1 ± 3.6 | 10.9 ± 3.2 | 0.438 ± 0.066 | 3.99 ± 1.6 | 1147 s, 1972 MB, 0.2 s/replica | Approve application: 2983, Assess loan risk: 7349, Cancel application: 334, Prepare home insurance quote: 121 … |

### Loan_Application_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 41.4 ± 3.6 | 0.146 ± 0.024 | 26.3 ± 2.8 | 20.2 ± 1.9 | 0.932 ± 0.054 | 5.25 ± 1.9 | 139 s, 1088 MB, 0.4 s/replica | — |
| simod_fixed_extr | 26.5 ± 4.5 | 0.166 ± 0.012 | 19 ± 3.2 | 13.4 ± 3.3 | 0.816 ± 0.065 | 5.07 ± 1.9 | 191 s, 1088 MB, 0.3 s/replica | Applicant completes form: 370, Approve application: 23856, Assess loan risk: 12822, Cancel application: 47 … |

### Loan_Application_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 42.3 ± 1.7 | 0.238 ± 0.0093 | 28.5 ± 1.7 | 28.1 ± 2 | 4.08 ± 0.037 | 3.59 ± 1.5 | 135 s, 1093 MB, 0.2 s/replica | — |
| simod_fixed_extr | 17.7 ± 2.7 | 0.233 ± 0.019 | 17.3 ± 1.9 | 17.5 ± 1.7 | 3.35 ± 0.9 | 3.62 ± 1.5 | 184 s, 1093 MB, 0.3 s/replica | Applicant completes form: 16189, Approve application: 47757, Assess loan risk: 44057, Cancel application: 324 … |

### Loan_Application_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 18.7 ± 3.5 | 0.147 ± 0.013 | 11.4 ± 2.4 | 12.2 ± 3 | 0.681 ± 0.027 | 4.69 ± 1.9 | 126 s, 1091 MB, 0.2 s/replica | — |
| simod_fixed_extr | 18.7 ± 3.5 | 0.147 ± 0.013 | 11.4 ± 2.4 | 12.2 ± 3 | 0.681 ± 0.027 | 4.69 ± 1.9 | 186 s, 1091 MB, 0.4 s/replica | — |

### Pharmacy

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 11.1 ± 2 | 0.0366 ± 0.0043 | 4.74 ± 0.71 | 118 ± 0.62 | 3.51 ± 3.3e-16 | 113 ± 0.43 | 91 s, 1050 MB, 0.1 s/replica | — |
| simod_fixed_extr | 11.1 ± 2 | 0.0366 ± 0.0043 | 4.74 ± 0.71 | 118 ± 0.62 | 3.51 ± 3.3e-16 | 113 ± 0.43 | 104 s, 1050 MB, 0.1 s/replica | — |

### Pharmacy_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 10.7 ± 1.9 | 0.0562 ± 0.0084 | 4.53 ± 0.84 | 118 ± 0.88 | 3.51 ± 0 | 114 ± 0 | 93 s, 1052 MB, 0.2 s/replica | — |
| simod_fixed_extr | 10.7 ± 1.9 | 0.0562 ± 0.0084 | 4.53 ± 0.84 | 118 ± 0.88 | 3.51 ± 0 | 114 ± 0 | 126 s, 1052 MB, 0.1 s/replica | — |

### Pharmacy_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 9.23 ± 1.1 | 0.0454 ± 0.0033 | 3.82 ± 0.53 | 117 ± 0.45 | 3.52 ± 0 | 114 ± 0 | 89 s, 1053 MB, 0.2 s/replica | — |
| simod_fixed_extr | 9.23 ± 1.1 | 0.0454 ± 0.0033 | 3.82 ± 0.53 | 117 ± 0.45 | 3.52 ± 0 | 114 ± 0 | 125 s, 1053 MB, 0.1 s/replica | — |

### Pharmacy_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 12.1 ± 2.7 | 0.0327 ± 0.0043 | 5.11 ± 1.1 | 118 ± 1 | 3.53 ± 3.3e-16 | 113 ± 0.43 | 91 s, 1053 MB, 0.2 s/replica | — |
| simod_fixed_extr | 12.1 ± 2.7 | 0.0327 ± 0.0043 | 5.11 ± 1.1 | 118 ± 1 | 3.53 ± 3.3e-16 | 113 ± 0.43 | 129 s, 1053 MB, 0.1 s/replica | — |

### Pharmacy_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 9.51 ± 0.84 | 0.0432 ± 0.0055 | 4.11 ± 0.8 | 118 ± 0.78 | 3.52 ± 0 | 114 ± 0 | 93 s, 1051 MB, 0.2 s/replica | — |
| simod_fixed_extr | 9.51 ± 0.84 | 0.0432 ± 0.0055 | 4.11 ± 0.8 | 118 ± 0.78 | 3.52 ± 0 | 114 ± 0 | 128 s, 1051 MB, 0.1 s/replica | — |

### Procure_to_Pay

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 108 ± 8.6 | 0.278 ± 0.0025 | 41.4 ± 5.6 | 41.2 ± 4.3 | 0.311 ± 0.031 | 2.8 ± 1.7 | 133 s, 1094 MB, 0.3 s/replica | — |
| simod_fixed_extr | 108 ± 8.6 | 0.278 ± 0.0025 | 41.4 ± 5.6 | 41.2 ± 4.3 | 0.311 ± 0.031 | 2.8 ± 1.7 | 156 s, 1094 MB, 0.3 s/replica | — |

### Procure_to_Pay_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 90.4 ± 13 | 0.276 ± 0.006 | 27.5 ± 4.9 | 33.2 ± 4.6 | 0.225 ± 0.038 | 2.17 ± 0.77 | 141 s, 1104 MB, 0.3 s/replica | — |
| simod_fixed_extr | 105 ± 6.4 | 0.276 ± 0.0073 | 29.9 ± 2.7 | 35.7 ± 2.4 | 0.243 ± 0.032 | 2.07 ± 0.55 | 203 s, 1104 MB, 0.3 s/replica | Approve Purchase Order for payment: 30, Release Purchase Order: 34, Send invoice: 28540 |

### Procure_to_Pay_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 93.5 ± 8.7 | 0.243 ± 0.0029 | 35.6 ± 5.7 | 33.7 ± 5.6 | 0.247 ± 0.023 | 2.67 ± 1 | 139 s, 1094 MB, 0.3 s/replica | — |
| simod_fixed_extr | 93.5 ± 8.7 | 0.243 ± 0.0029 | 35.6 ± 5.7 | 33.7 ± 5.6 | 0.247 ± 0.023 | 2.67 ± 1 | 203 s, 1094 MB, 0.4 s/replica | — |

### Procure_to_Pay_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 74.6 ± 11 | 0.249 ± 0.0048 | 23.3 ± 5.2 | 22.5 ± 5.3 | 0.233 ± 0.02 | 2.56 ± 1.3 | 134 s, 1095 MB, 0.3 s/replica | — |
| simod_fixed_extr | 74.6 ± 11 | 0.249 ± 0.0048 | 23.3 ± 5.2 | 22.5 ± 5.3 | 0.233 ± 0.02 | 2.56 ± 1.3 | 201 s, 1095 MB, 0.3 s/replica | — |

### Procure_to_Pay_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 92.7 ± 4.6 | 0.275 ± 0.0026 | 36.9 ± 3.6 | 35 ± 3.7 | 0.2 ± 0.033 | 1.81 ± 0.57 | 150 s, 1092 MB, 0.4 s/replica | — |
| simod_fixed_extr | 92.7 ± 4.6 | 0.275 ± 0.0026 | 36.9 ± 3.6 | 35 ± 3.7 | 0.2 ± 0.033 | 1.81 ± 0.57 | 213 s, 1092 MB, 0.2 s/replica | — |


## Metriche, fase test

### Insurance_Claims

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 14.9 ± 1.1 | 0.187 ± 0 | 10.8 ± 0.97 | 144 ± 0.19 | 0.363 ± 0.0009 | 133 ± 1.1 | 127 s, 1078 MB, 0.5 s/replica | — |
| simod_fixed_extr | 14.9 ± 1.1 | 0.187 ± 0 | 10.8 ± 0.97 | 144 ± 0.19 | 0.363 ± 0.0009 | 133 ± 1.1 | 139 s, 1078 MB, 0.4 s/replica | — |

### Insurance_Claims_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 13.8 ± 0.9 | 0.206 ± 2.1e-17 | 10.7 ± 0.73 | 141 ± 0.42 | 0.372 ± 0.0012 | 130 ± 0.71 | 121 s, 1079 MB, 0.4 s/replica | — |
| simod_fixed_extr | 13.8 ± 0.9 | 0.206 ± 2.1e-17 | 10.7 ± 0.73 | 141 ± 0.42 | 0.372 ± 0.0012 | 130 ± 0.71 | 155 s, 1079 MB, 0.4 s/replica | — |

### Insurance_Claims_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 13.6 ± 0.5 | 0.199 ± 0 | 10.3 ± 0.42 | 143 ± 0.13 | 0.374 ± 0.00056 | 133 ± 0.38 | 120 s, 1076 MB, 0.4 s/replica | — |
| simod_fixed_extr | 14 ± 0.58 | 0.199 ± 0 | 10.4 ± 0.45 | 143 ± 0.12 | 0.361 ± 0.00078 | 133 ± 0.42 | 160 s, 1076 MB, 0.6 s/replica | Close Claim: 153, Determine likelihood of the claim: 475, Initiate Payment: 86 |

### Insurance_Claims_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 12.3 ± 1.1 | 0.189 ± 0 | 9.75 ± 0.94 | 143 ± 0.36 | 0.388 ± 0.00085 | 134 ± 1.2 | 120 s, 1083 MB, 0.5 s/replica | — |
| simod_fixed_extr | 12 ± 1.2 | 0.189 ± 0 | 9.57 ± 0.95 | 143 ± 0.39 | 0.362 ± 0.0011 | 134 ± 1.2 | 161 s, 1083 MB, 0.6 s/replica | Advise Claimant on Reimbursement: 98, Assess Claim: 281, Close Claim: 160, Determine likelihood of the claim: 482 … |

### Insurance_Claims_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 12.9 ± 0.82 | 0.184 ± 0 | 10 ± 0.7 | 141 ± 0.23 | 0.376 ± 0.00095 | 131 ± 0.69 | 112 s, 1077 MB, 0.4 s/replica | — |
| simod_fixed_extr | 12.6 ± 0.75 | 0.184 ± 0 | 9.9 ± 0.62 | 141 ± 0.19 | 0.357 ± 0.00075 | 131 ± 0.65 | 149 s, 1077 MB, 0.5 s/replica | Assess Claim: 263, Close Claim: 400, Determine likelihood of the claim: 474 |

### Loan_Application

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 31.3 ± 7.9 | 0.129 ± 0.0091 | 21 ± 5.5 | 20.1 ± 5.2 | 0.342 ± 0.021 | 7.03 ± 1.3 | 141 s, 1122 MB, 0.8 s/replica | — |
| simod_fixed_extr | 28.9 ± 6.4 | 0.11 ± 0.0076 | 17.2 ± 4.1 | 16.9 ± 1.7 | 0.333 ± 0.02 | 7.08 ± 1.1 | 203 s, 1122 MB, 0.9 s/replica | Approve application: 12732, Cancel application: 6482, Prepare home insurance quote: 333, Reject application: 2423 |
