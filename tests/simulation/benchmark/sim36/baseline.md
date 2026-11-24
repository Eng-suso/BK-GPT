# Baseline SIM-36 e SIM-36b, gemello ingenuo "B = A"

Seed e repliche: 20261124 × 10.

## Log train/test del paper (SIM-36b): A = train, B = test

| Scenario | W1 cycle time (ore) | NGD | RED (ore) | AED (ore) | CED (ore) | CAR (ore) |
| --- | --- | --- | --- | --- | --- | --- |
| AcademicCredentials | 28.827 ± 3.601 | 0.179 ± 0.006 | 25.856 ± 2.223 | 62.309 ± 6.194 | 1.391 ± 0.116 | 95.460 ± 17.106 |
| BPIC_2012_W | 28.061 ± 2.000 | 0.083 ± 0.005 | 10.140 ± 2.565 | 29.710 ± 4.414 | 0.800 ± 0.155 | 38.215 ± 4.309 |
| BPIC_2017_W | 30.602 ± 1.481 | 0.079 ± 0.001 | 11.359 ± 1.570 | 42.785 ± 4.042 | 0.660 ± 0.011 | 35.916 ± 3.821 |

## "B = A" contro lo scenario SIMOD del paper (B2)

Distanza dal test, piu' bassa e' meglio. Migliore: chi ha la media minore con intervalli al 95% che non si sovrappongono; altrimenti pari.

| Log | Metrica | B = A (train) | SIMOD del paper (B2) | Migliore |
| --- | --- | --- | --- | --- |
| AcademicCredentials | W1 cycle time (ore) | 28.827 ± 3.601 | 174.837 ± 0.421 | B = A |
| AcademicCredentials | NGD | 0.179 ± 0.006 | 0.763 ± 0.006 | B = A |
| AcademicCredentials | RED (ore) | 25.856 ± 2.223 | 77.464 ± 0.210 | B = A |
| AcademicCredentials | AED (ore) | 62.309 ± 6.194 | 121.397 ± 23.249 | B = A |
| AcademicCredentials | CED (ore) | 1.391 ± 0.116 | 3.329 ± 0.069 | B = A |
| AcademicCredentials | CAR (ore) | 95.460 ± 17.106 | 130.955 ± 25.910 | pari |
| BPIC_2012_W | W1 cycle time (ore) | 28.061 ± 2.000 | 175.710 ± 0.036 | B = A |
| BPIC_2012_W | NGD | 0.083 ± 0.005 | 0.814 ± 0.001 | B = A |
| BPIC_2012_W | RED (ore) | 10.140 ± 2.565 | 178.538 ± 0.020 | B = A |
| BPIC_2012_W | AED (ore) | 29.710 ± 4.414 | 221.446 ± 8.148 | B = A |
| BPIC_2012_W | CED (ore) | 0.800 ± 0.155 | 1.251 ± 0.056 | B = A |
| BPIC_2012_W | CAR (ore) | 38.215 ± 4.309 | 85.775 ± 8.122 | B = A |
| BPIC_2017_W | W1 cycle time (ore) | 30.602 ± 1.481 | 253.314 ± 0.033 | B = A |
| BPIC_2017_W | NGD | 0.079 ± 0.001 | 0.615 ± 0.001 | B = A |
| BPIC_2017_W | RED (ore) | 11.359 ± 1.570 | 183.545 ± 0.019 | B = A |
| BPIC_2017_W | AED (ore) | 42.785 ± 4.042 | 303.353 ± 9.738 | B = A |
| BPIC_2017_W | CED (ore) | 0.660 ± 0.011 | 0.928 ± 0.020 | B = A |
| BPIC_2017_W | CAR (ore) | 35.916 ± 3.821 | 169.620 ± 9.361 | B = A |

## Log BPIC divisi a meta' dei casi (SIM-36)

| Scenario | W1 cycle time (ore) | NGD | RED (ore) | AED (ore) | CED (ore) | CAR (ore) |
| --- | --- | --- | --- | --- | --- | --- |
| bpic2012 | 16.931 ± 1.518 | 0.055 ± 0.002 | 16.554 ± 1.567 | 60.281 ± 3.275 | 0.222 ± 0.013 | 48.697 ± 2.653 |
| bpic2013_incidents | 383.995 ± 7.811 | 0.329 ± 0.004 | 176.788 ± 3.981 | 334.396 ± 16.091 | 1.751 ± 0.079 | 290.944 ± 6.383 |

- bpic2013_incidents: non adatto al confronto A → B, foto degli incidenti aperti a maggio 2012, non un flusso: con ogni taglio il 100% dei casi di B e' troncato dalla fine del log (decisione di Sohayb, 2026-11-24).
