# B3.2: discovery delle attese

Generato da `tests/simulation/benchmark/b3_2/report.py`. Distanze di B2 (ore, NGD in [0, 1]), media ±
semiampiezza IC 95% su 10 repliche; (NV) = NOT VALIDATED. Più basso è meglio. Regole di `g3b/report.py`.

## Verdetti

| Scheda | Componente | Fase | Verdetto | V / P / P | Motivi |
| --- | --- | --- | --- | --- | --- |
| 1 | Ablazione dei ritardi estranei | validation | **NO-GO** | 4 / 18 / 0 | contro simod: RED vince su 4/22 log; contro simod: guardia CED perde su 2 log |
| 1 | Ablazione dei ritardi estranei | test | **NO-GO** | 6 / 15 / 2 | contro simod: RED vince su 6/23 log; contro simod: RED perde su AcademicCredentials, Procure_to_Pay_5_timers_after; contro simod: guardia W1 perde su 2 log; contro simod: guardia AED perde su 3 log; contro simod: guardia CED perde su 4 log; candidato non misurato (fallito, fuori budget o non applicabile) su AcademicCredentials |
| 3 | Attese attribuite: W1 | validation | **NO-GO** | 0 / 1 / 1 | contro simod_extr: W1 vince su 0/2 log; contro simod_extr: W1 perde su BPIC_2017_W |
| 3 | Attese attribuite: RED | validation | **NO-GO** | 0 / 1 / 1 | contro simod_extr: RED vince su 0/2 log; contro simod_extr: RED perde su BPIC_2017_W |
| 3b | Attese attribuite v2: W1 | validation | **NO-GO** | 2 / 0 / 0 | contro simod_extr: guardia AED perde su 3 log |
| 3b | Attese attribuite v2: RED | validation | **NO-GO** | 2 / 0 / 0 | contro simod_extr: guardia AED perde su 3 log |
| 3c | Attese attribuite v3: W1 | validation | **NO-GO** | 2 / 0 / 0 | contro simod_extr: guardia AED perde su 2 log |
| 3c | Attese attribuite v3: RED | validation | **NO-GO** | 2 / 0 / 0 | contro simod_extr: guardia AED perde su 2 log |
| 3d | Attese attribuite v4: W1 | validation | **NO-GO** | 2 / 0 / 0 | contro simod_extr: guardia AED perde su 2 log |
| 3d | Attese attribuite v4: RED | validation | **NO-GO** | 2 / 0 / 0 | contro simod_extr: guardia AED perde su 2 log |
| 3e | Attese attribuite v5: W1 | validation | **GO** | 2 / 0 / 0 | — |
| 3e | Attese attribuite v5: W1 | test | **NO-GO** | 1 / 0 / 2 | contro simod_extr: W1 vince su 1/3 log; contro simod_extr: W1 perde su BPIC_2012_W, BPIC_2017_W; contro simod_extr: guardia RED perde su 2 log; contro simod_extr: guardia AED perde su 2 log; VAL-01 non superato su AcademicCredentials |
| 3e | Attese attribuite v5: RED | validation | **GO** | 2 / 0 / 0 | — |
| 3e | Attese attribuite v5: RED | test | **NO-GO** | 1 / 0 / 2 | contro simod_extr: RED vince su 1/3 log; contro simod_extr: RED perde su BPIC_2012_W, BPIC_2017_W; contro simod_extr: guardia W1 perde su 2 log; contro simod_extr: guardia AED perde su 2 log; VAL-01 non superato su AcademicCredentials |

## Metriche, fase validation

### AcademicCredentials

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 104 ± 1.4 (NV) | 0.313 ± 0.0076 (NV) | 39.9 ± 0.61 (NV) | 268 ± 11 | 5.56 ± 0.37 | 220 ± 12 (NV) | 134 s, 1102 MB, 0.2 s/replica | — |
| simod_fixed_extr | 227 ± 27 (NV) | 0.337 ± 0.0086 (NV) | 117 ± 12 (NV) | 215 ± 14 | 5.03 ± 0.63 | 220 ± 12 (NV) | 168 s, 1102 MB, 0.2 s/replica | Avanzar recepcion documentos: 346983, Cancelar Solicitud: 45360, Cancelar curso: 919164, Evaluacion curso: 1102 … |
| simod_attr_extr | 221 ± 31 (NV) | 0.305 ± 0.0099 (NV) | 100 ± 14 (NV) | 171 ± 9.9 | 4.55 ± 0.88 | 219 ± 12 (NV) | 134 s, 1102 MB, 0.2 s/replica | Validar solicitud: 48537, Evaluacion curso: 27799, Notificacion estudiante cancelacion soli: 692785, Validacion final: 387295 … |
| simod_attr_idle | 35.4 ± 2.9 (NV) | 0.295 ± 0.0066 (NV) | 18.4 ± 1.6 (NV) | 220 ± 12 | 5.13 ± 0.73 | 219 ± 12 (NV) | 134 s, 1102 MB, 0.1 s/replica | Validar solicitud: 19743, Evaluacion curso: 10647, Notificacion estudiante cancelacion soli: 247339, Validacion final: 160821 … |
| simod_attr_shift | 38 ± 4.3 (NV) | 0.294 ± 0.013 (NV) | 18.7 ± 1.9 (NV) | 221 ± 14 | 4.89 ± 0.86 | 219 ± 12 (NV) | 134 s, 1102 MB, 0.2 s/replica | Validar solicitud: 20089, Evaluacion curso: 10941, Notificacion estudiante cancelacion soli: 252065, Validacion final: 161781 … |
| simod_attr_closest | 36.7 ± 4.5 (NV) | 0.302 ± 0.013 (NV) | 19.3 ± 2 (NV) | 216 ± 11 | 4.29 ± 0.82 | 219 ± 12 (NV) | 134 s, 1102 MB, 0.1 s/replica | Validar solicitud: 20089, Evaluacion curso: 10941, Notificacion estudiante cancelacion soli: 252065, Validacion final: 161781 … |
| simod_attr_calibrated | 187 ± 13 (NV) | 0.307 ± 0.0092 (NV) | 82.4 ± 3.1 (NV) | 177 ± 12 | 4.19 ± 0.81 | 219 ± 12 (NV) | 141 s, 1102 MB, 0.1 s/replica | Validar solicitud: 41425, Evaluacion curso: 23584, Notificacion estudiante cancelacion soli: 582605, Validacion final: 330917 … |
| simod_extr | 231 ± 19 (NV) | 0.3 ± 0.011 (NV) | 99.4 ± 16 (NV) | 173 ± 12 | 4.35 ± 0.8 | 220 ± 12 (NV) | 224 s, 1102 MB, 0.3 s/replica | — |

### BPIC_2012_W

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 54.9 ± 0.11 | 0.652 ± 0.0076 | 73 ± 0.15 | 130 ± 3.9 | 3.77 ± 0.058 | 96.1 ± 3.5 | 527 s, 1215 MB, 0.9 s/replica | — |
| simod_fixed_extr | 116 ± 6.4 | 0.588 ± 0.0064 | 61.3 ± 7.3 | 68.3 ± 2.9 | 4.55 ± 0.038 | 93.9 ± 3.5 | 818 s, 1215 MB, 2.0 s/replica | W_Afhandelen leads: 648, W_Beoordelen fraude: 41875, W_Completeren aanvraag: 25621, W_Nabellen incomplete dossiers: 37975 … |
| simod_attr_extr | 126 ± 6.3 | 0.582 ± 0.0041 | 61.9 ± 7.3 | 65.1 ± 2.9 | 4.67 ± 0.027 | 92.4 ± 3.5 | 533 s, 1215 MB, 2.0 s/replica | W_Nabellen offertes: 257375, W_Valideren aanvraag: 122892, W_Completeren aanvraag: 34884, W_Nabellen incomplete dossiers: 38640 … |
| simod_attr_idle | 28.1 ± 1.1 | 0.596 ± 0.0066 | 24.2 ± 1.3 | 73.4 ± 2.9 | 4.3 ± 0.049 | 94.6 ± 3.5 | 529 s, 1215 MB, 1.0 s/replica | W_Nabellen offertes: 108192, W_Valideren aanvraag: 51205, W_Completeren aanvraag: 15965, W_Nabellen incomplete dossiers: 13894 … |
| simod_attr_shift | 36.7 ± 4 | 0.602 ± 0.007 | 22.1 ± 1.5 | 66.7 ± 2.6 | 4.35 ± 0.044 | 94.3 ± 3.5 | 529 s, 1215 MB, 1.1 s/replica | W_Nabellen offertes: 126193, W_Valideren aanvraag: 64370, W_Completeren aanvraag: 19479, W_Nabellen incomplete dossiers: 16708 … |
| simod_attr_closest | 36.7 ± 4 | 0.602 ± 0.007 | 22.1 ± 1.5 | 66.7 ± 2.6 | 4.35 ± 0.044 | 94.3 ± 3.5 | 529 s, 1215 MB, 1.1 s/replica | W_Nabellen offertes: 126193, W_Valideren aanvraag: 64370, W_Completeren aanvraag: 19479, W_Nabellen incomplete dossiers: 16708 … |
| simod_attr_calibrated | 82.2 ± 5.2 | 0.588 ± 0.0074 | 38.1 ± 2.7 | 61 ± 2.3 | 4.55 ± 0.034 | 93.2 ± 3.5 | 546 s, 1215 MB, 1.0 s/replica | W_Nabellen offertes: 191784, W_Valideren aanvraag: 93631, W_Completeren aanvraag: 27182, W_Nabellen incomplete dossiers: 27674 … |
| simod_extr | 113 ± 9.3 | 0.587 ± 0.0072 | 57.5 ± 6.5 | 62 ± 3.9 | 4.75 ± 0.044 | 82.6 ± 4.9 | 1042 s, 1215 MB, 1.6 s/replica | — |

### BPIC_2017_W

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 199 ± 0.043 | 0.371 ± 0.0031 | 130 ± 0.057 | 184 ± 4.6 | 1.09 ± 0.062 | 78.8 ± 4.5 | 1608 s, 8775 MB, 2.0 s/replica | — |
| simod_fixed_extr | 97.4 ± 3.7 | 0.369 ± 0.0025 | 66.2 ± 2.8 | 50.7 ± 2 | 1.98 ± 0.018 | 68.8 ± 4.4 | 2383 s, 8775 MB, 4.0 s/replica | W_Assess potential fraud: 81620, W_Call after offers: 190754, W_Call incomplete files: 94720, W_Complete application: 36015 … |
| simod_attr_extr | 111 ± 4.4 | 0.371 ± 0.0035 | 79.7 ± 5.5 | 54.5 ± 3.9 | 2.1 ± 0.017 | 59.9 ± 3.9 | 1621 s, 8775 MB, 3.6 s/replica | W_Call after offers: 198671, W_Shortened completion: 29003, W_Assess potential fraud: 81751, W_Call incomplete files: 94537 … |
| simod_attr_idle | 74.1 ± 1.4 | 0.371 ± 0.0034 | 48.1 ± 0.74 | 88.6 ± 4.1 | 1.82 ± 0.022 | 69.3 ± 4.4 | 1613 s, 8775 MB, 2.3 s/replica | W_Call after offers: 86327, W_Shortened completion: 15829, W_Assess potential fraud: 24678, W_Call incomplete files: 36857 … |
| simod_attr_shift | 62.9 ± 2.8 | 0.371 ± 0.0039 | 42.6 ± 1.8 | 82.4 ± 3.9 | 1.85 ± 0.02 | 68.4 ± 4.3 | 1614 s, 8775 MB, 2.4 s/replica | W_Call after offers: 92820, W_Shortened completion: 17270, W_Assess potential fraud: 25595, W_Call incomplete files: 40816 … |
| simod_attr_closest | 62.9 ± 2.8 | 0.371 ± 0.0039 | 42.6 ± 1.8 | 82.4 ± 3.9 | 1.85 ± 0.02 | 68.4 ± 4.3 | 1614 s, 8775 MB, 2.4 s/replica | W_Call after offers: 92820, W_Shortened completion: 17270, W_Assess potential fraud: 25595, W_Call incomplete files: 40816 … |
| simod_attr_calibrated | 73.2 ± 2.8 | 0.371 ± 0.0028 | 52.8 ± 2.2 | 41.7 ± 1.4 | 2.05 ± 0.022 | 61.8 ± 4.1 | 1648 s, 8775 MB, 2.4 s/replica | W_Call after offers: 172208, W_Shortened completion: 26070, W_Assess potential fraud: 67712, W_Call incomplete files: 81107 … |
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

### AcademicCredentials

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 306 ± 1.4 | 0.487 ± 0.068 | 6.58e+03 ± 1.4e+03 | 6.84e+03 ± 1.4e+03 | 4.31 ± 0.19 | 227 ± 58 | 128 s, 1097 MB, 0.8 s/replica | — |
| simod_fixed_extr | fallito | fallito | fallito | fallito | fallito | fallito | 12 s, 834 MB, 0.0 s/replica | — |
| simod_attr_calibrated | 628 ± 2.4e+02 | 0.396 ± 0.061 | 2.83e+04 ± 8.8e+03 | 2.86e+04 ± 8.8e+03 | 3.84 ± 0.12 | 229 ± 57 | 146 s, 1097 MB, 1.5 s/replica | Validar solicitud / pre-homologacion: 351408, Cancelar Solicitud: 23140, Notificacion estudiante cancelacion soli: 293702, Cancelar curso: 212128 … |
| simod_extr | fallito | fallito | fallito | fallito | fallito | fallito | 74 s, 1102 MB, 0.0 s/replica | — |

### BPIC_2012_W

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 175 ± 0.051 | 0.531 ± 0.0034 | 178 ± 0.072 | 202 ± 12 | 1.24 ± 0.083 | 67.3 ± 11 | 613 s, 1242 MB, 3.3 s/replica | — |
| simod_fixed_extr | 42.1 ± 1.8 | 0.501 ± 0.0022 | 63.7 ± 2 | 91.6 ± 12 | 1.99 ± 0.015 | 65.8 ± 10 | 889 s, 1242 MB, 5.0 s/replica | W_Afhandelen leads: 552, W_Beoordelen fraude: 38211, W_Completeren aanvraag: 24213, W_Nabellen incomplete dossiers: 36650 … |
| simod_attr_calibrated | 99.3 ± 1.5 | 0.505 ± 0.0032 | 113 ± 1.3 | 135 ± 14 | 1.76 ± 0.015 | 65.9 ± 10 | 652 s, 1242 MB, 5.1 s/replica | W_Nabellen incomplete dossiers: 16743, W_Afhandelen leads: 2004, W_Beoordelen fraude: 14266, W_Completeren aanvraag: 18555 … |
| simod_extr | 43.2 ± 2 | 0.502 ± 0.0046 | 66 ± 1.5 | 69.7 ± 8.8 | 2 ± 0.025 | 38.5 ± 6.2 | 1079 s, 1242 MB, 5.2 s/replica | — |

### BPIC_2017_W

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 253 ± 0.029 | 0.279 ± 0.0015 | 183 ± 0.041 | 276 ± 6.9 | 0.922 ± 0.026 | 144 ± 6.6 | 1723 s, 10823 MB, 7.3 s/replica | — |
| simod_fixed_extr | 17.9 ± 1.6 | 0.28 ± 0.001 | 7.82 ± 0.3 | 85.6 ± 6.5 | 2.32 ± 0.013 | 133 ± 6.1 | 2441 s, 10823 MB, 11.4 s/replica | W_Assess potential fraud: 80716, W_Call after offers: 189637, W_Call incomplete files: 91314, W_Complete application: 33290 … |
| simod_attr_calibrated | 50 ± 1.4 | 0.28 ± 0.0019 | 45.4 ± 1.5 | 118 ± 9.4 | 2.38 ± 0.012 | 130 ± 6.1 | 1808 s, 10823 MB, 11.7 s/replica | W_Call after offers: 146591, W_Handle leads: 2120, W_Validate application: 167228, W_Assess potential fraud: 54789 … |
| simod_extr | 19.2 ± 2.3 | 0.279 ± 0.0012 | 8.57 ± 0.81 | 77.4 ± 6.8 | 2.32 ± 0.0088 | 125 ± 6 | 2823 s, 10823 MB, 12.3 s/replica | — |

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

### Loan_Application_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 37.5 ± 4.4 | 0.192 ± 0.0093 | 24.5 ± 3 | 18.2 ± 3.2 | 0.158 ± 0.015 | 6.26 ± 1.6 | 875 s, 2152 MB, 0.6 s/replica | — |
| simod_fixed_extr | 23.2 ± 3.9 | 0.198 ± 0.012 | 16.5 ± 3 | 9.16 ± 1.4 | 0.156 ± 0.0092 | 6.18 ± 1.7 | 924 s, 2152 MB, 0.7 s/replica | Approve application: 8186, Assess loan risk: 25658, Cancel application: 3282, Prepare home insurance quote: 1892 … |

### Loan_Application_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 37.3 ± 4.6 | 0.205 ± 0.0066 | 24.1 ± 2.7 | 35.9 ± 2.6 | 0.311 ± 0.028 | 11.1 ± 2.8 | 133 s, 1076 MB, 0.6 s/replica | — |
| simod_fixed_extr | 17.7 ± 2.5 | 0.201 ± 0.0063 | 13.4 ± 2.2 | 23.7 ± 3.4 | 0.329 ± 0.038 | 11.9 ± 2.9 | 182 s, 1076 MB, 0.7 s/replica | Applicant completes form: 10737, Approve application: 28323, Assess loan risk: 45822, Cancel application: 2765 … |

### Loan_Application_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 29.5 ± 2.2 | 0.217 ± 0.0048 | 20.2 ± 1.6 | 21.4 ± 1.9 | 0.423 ± 0.018 | 12.2 ± 2 | 120 s, 1086 MB, 0.5 s/replica | — |
| simod_fixed_extr | 20.5 ± 2.1 | 0.215 ± 0.0088 | 16.7 ± 1.8 | 16.5 ± 2.2 | 0.423 ± 0.027 | 12.3 ± 2 | 163 s, 1086 MB, 0.6 s/replica | Applicant completes form: 12263, Approve application: 32757, Assess loan risk: 8182, Cancel application: 2666 … |

### Loan_Application_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 56.7 ± 4.9 | 0.159 ± 0.0061 | 35.8 ± 3.6 | 40.2 ± 2.5 | 0.232 ± 0.028 | 7.2 ± 2.2 | 112 s, 1092 MB, 0.7 s/replica | — |
| simod_fixed_extr | 24.9 ± 4.2 | 0.171 ± 0.0063 | 20.8 ± 3 | 21.2 ± 3.6 | 0.305 ± 0.021 | 6.75 ± 1.8 | 165 s, 1092 MB, 0.8 s/replica | Approve application: 50719, Assess loan risk: 33716, Cancel application: 24221, Check  application  form completeness: 2687 … |

### Pharmacy

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 1.71 ± 0.2 | 0.0349 ± 0.0014 | 0.788 ± 0.15 | 133 ± 0.13 | 7.43 ± 0.0025 | 132 ± 0.11 | 82 s, 1047 MB, 0.3 s/replica | — |
| simod_fixed_extr | 1.71 ± 0.2 | 0.0349 ± 0.0014 | 0.788 ± 0.15 | 133 ± 0.13 | 7.43 ± 0.0025 | 132 ± 0.11 | 95 s, 1047 MB, 0.4 s/replica | — |

### Pharmacy_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 1.75 ± 0.23 | 0.0351 ± 0.0031 | 0.771 ± 0.12 | 133 ± 0.092 | 7.43 ± 0.002 | 132 ± 0.11 | 82 s, 1047 MB, 0.4 s/replica | — |
| simod_fixed_extr | 1.82 ± 0.18 | 0.0341 ± 0.0015 | 0.868 ± 0.13 | 133 ± 0.096 | 7.43 ± 0.0036 | 132 ± 0.11 | 114 s, 1047 MB, 0.4 s/replica | Pick-up: 67 |

### Pharmacy_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 1.48 ± 0.099 | 0.0367 ± 0.0029 | 0.636 ± 0.079 | 133 ± 0.06 | 7.43 ± 0.0021 | 133 ± 0.00045 | 95 s, 1042 MB, 0.4 s/replica | — |
| simod_fixed_extr | 1.48 ± 0.099 | 0.0367 ± 0.0029 | 0.636 ± 0.079 | 133 ± 0.06 | 7.43 ± 0.0021 | 133 ± 0.00045 | 129 s, 1042 MB, 0.4 s/replica | — |

### Pharmacy_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 1.38 ± 0.23 | 0.0291 ± 0.0031 | 0.661 ± 0.14 | 133 ± 0.11 | 7.44 ± 0.0042 | 132 ± 0.12 | 96 s, 1047 MB, 0.4 s/replica | — |
| simod_fixed_extr | 1.38 ± 0.23 | 0.0291 ± 0.0031 | 0.661 ± 0.14 | 133 ± 0.11 | 7.44 ± 0.0042 | 132 ± 0.12 | 128 s, 1047 MB, 0.4 s/replica | — |

### Pharmacy_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 1.04 ± 0.016 | 0.0302 ± 0.0035 | 0.378 ± 0.066 | 133 ± 0.091 | 7.44 ± 0.0016 | 133 ± 0 | 110 s, 1047 MB, 0.4 s/replica | — |
| simod_fixed_extr | 1.04 ± 0.016 | 0.0302 ± 0.0035 | 0.378 ± 0.066 | 133 ± 0.091 | 7.44 ± 0.0016 | 133 ± 0 | 144 s, 1047 MB, 0.4 s/replica | — |

### Procure_to_Pay

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 556 ± 32 | 0.242 ± 0.0018 | 299 ± 16 | 283 ± 15 | 0.187 ± 0.012 | 13.7 ± 2.8 | 157 s, 1094 MB, 0.8 s/replica | — |
| simod_fixed_extr | 557 ± 39 | 0.242 ± 0.0017 | 299 ± 20 | 284 ± 18 | 0.186 ± 0.012 | 13.8 ± 2.8 | 208 s, 1094 MB, 0.8 s/replica | Settle dispute with supplier Purchasing Agent: 14918 |

### Procure_to_Pay_1_timer

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 351 ± 26 | 0.25 ± 0.0014 | 180 ± 17 | 162 ± 13 | 0.145 ± 0.016 | 15.6 ± 4.8 | 111 s, 1101 MB, 0.7 s/replica | — |
| simod_fixed_extr | 366 ± 28 | 0.248 ± 0.00083 | 188 ± 16 | 170 ± 13 | 0.144 ± 0.018 | 15.6 ± 4.6 | 162 s, 1101 MB, 0.8 s/replica | Send invoice: 4063 |

### Procure_to_Pay_3_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 318 ± 14 | 0.219 ± 0.00069 | 160 ± 5.5 | 138 ± 4.2 | 0.165 ± 0.018 | 14.5 ± 3.8 | 128 s, 1086 MB, 0.8 s/replica | — |
| simod_fixed_extr | 349 ± 36 | 0.22 ± 0.0017 | 173 ± 19 | 152 ± 19 | 0.159 ± 0.015 | 14.2 ± 4 | 188 s, 1086 MB, 0.9 s/replica | Analyze Purchase Requisition: 2485, Confirm Purchase Order: 6316, Send invoice: 16789 |

### Procure_to_Pay_5_timers

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 360 ± 41 | 0.228 ± 0.0019 | 186 ± 24 | 180 ± 21 | 0.164 ± 0.013 | 14.7 ± 3.7 | 120 s, 1091 MB, 0.7 s/replica | — |
| simod_fixed_extr | 360 ± 41 | 0.228 ± 0.0019 | 186 ± 24 | 180 ± 21 | 0.164 ± 0.013 | 14.7 ± 3.7 | 180 s, 1091 MB, 0.7 s/replica | — |

### Procure_to_Pay_5_timers_after

| Configurazione | W1 | NGD | RED | AED | CED | CAR | Costo | Ritardi (s, media) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| simod | 372 ± 36 | 0.25 ± 0.0026 | 190 ± 22 | 174 ± 20 | 0.155 ± 0.017 | 15.3 ± 2.3 | 136 s, 1099 MB, 0.7 s/replica | — |
| simod_fixed_extr | 510 ± 17 | 0.247 ± 0.0021 | 233 ± 9.8 | 218 ± 9.5 | 0.176 ± 0.023 | 15.5 ± 2.2 | 198 s, 1099 MB, 1.3 s/replica | Amend Purchase Requisition: 3487, Amend Request for Quotation Requester: 14077, Amend Request for Quotation Requester Manager: 47894, Confirm Purchase Order: 41763 … |
