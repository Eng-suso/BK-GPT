# G3: SIMOD contro paper e gemello ingenuo (seed 20261124, 10 repliche)

Media ± semiampiezza dell'IC 95%, distanze in ore sul log di test (più basso è meglio). "pari": lo scarto fra le medie è minore della somma degli intervalli.

| Log | Scenario | RED | AED | W1 cycle time | CAR |
| --- | --- | --- | --- | --- | --- |
| AcademicCredentials | SIMOD 5.2.1, calendari fissi | 6649.07 ± 2135.72 | 6903.53 ± 2196.15 | 295.35 ± 29.66 | 254.17 ± 36.40 |
| AcademicCredentials | diagnosi: fissi, ciclo riaperto | 77.87 ± 0.45 | 233.37 ± 41.93 | 176.27 ± 0.70 | 254.16 ± 36.39 |
| AcademicCredentials | SIMOD 5.2.1, calendari FUZZY | 10074.22 ± 3042.15 | 10371.84 ± 3061.36 | 323.96 ± 67.17 | 270.05 ± 41.48 |
| AcademicCredentials | diagnosi: FUZZY, ciclo riaperto | 80.25 ± 4.61 | 398.07 ± 48.51 | 119.59 ± 7.44 | 270.30 ± 41.92 |
| AcademicCredentials | scenario SIMOD del paper, in DeliR (B2) | 77.46 ± 0.21 | 121.40 ± 23.25 | 174.84 ± 0.42 | 130.95 ± 25.91 |
| AcademicCredentials | paper, pubblicato | 77.21 ± 0.35 | 132.82 ± 26.75 | 174.66 ± 0.96 | — |
| AcademicCredentials | gemello ingenuo (train) | 23.98 ± 0.00 | 164.85 ± 0.00 | 26.17 ± 0.00 | 85.55 ± 0.00 |
| BPIC_2012_W | SIMOD 5.2.1, calendari fissi | 177.99 ± 0.05 | 172.60 ± 9.20 | 175.30 ± 0.04 | 41.54 ± 6.45 |
| BPIC_2012_W | SIMOD 5.2.1, calendari FUZZY | 87.54 ± 9.76 | 123.00 ± 9.59 | 307.36 ± 50.11 | 65.95 ± 9.13 |
| BPIC_2012_W | scenario SIMOD del paper, in DeliR (B2) | 178.54 ± 0.02 | 221.45 ± 8.15 | 175.71 ± 0.04 | 85.77 ± 8.12 |
| BPIC_2012_W | paper, pubblicato | 178.55 ± 0.01 | 223.84 ± 8.44 | 175.72 ± 0.03 | — |
| BPIC_2012_W | gemello ingenuo (train) | 9.74 ± 0.00 | 26.75 ± 0.00 | 27.99 ± 0.00 | 38.51 ± 0.00 |
| BPIC_2017_W | scenario SIMOD del paper, in DeliR (B2) | 183.54 ± 0.02 | 303.35 ± 9.74 | 253.31 ± 0.03 | 169.62 ± 9.36 |
| BPIC_2017_W | paper, pubblicato | 183.55 ± 0.02 | 296.04 ± 9.53 | 253.33 ± 0.02 | — |
| BPIC_2017_W | gemello ingenuo (train) | 10.96 ± 0.00 | 43.21 ± 0.00 | 30.89 ± 0.00 | 35.96 ± 0.00 |

## Esito

| Log | Scenario | contro | RED | AED | W1 cycle time | CAR |
| --- | --- | --- | --- | --- | --- | --- |
| AcademicCredentials | SIMOD 5.2.1, calendari fissi | paper in DeliR | peggio | peggio | peggio | peggio |
| AcademicCredentials | SIMOD 5.2.1, calendari fissi | ingenuo | peggio | peggio | peggio | peggio |
| AcademicCredentials | diagnosi: fissi, ciclo riaperto | paper in DeliR | pari | peggio | peggio | peggio |
| AcademicCredentials | diagnosi: fissi, ciclo riaperto | ingenuo | peggio | peggio | peggio | peggio |
| AcademicCredentials | SIMOD 5.2.1, calendari FUZZY | paper in DeliR | peggio | peggio | peggio | peggio |
| AcademicCredentials | SIMOD 5.2.1, calendari FUZZY | ingenuo | peggio | peggio | peggio | peggio |
| AcademicCredentials | diagnosi: FUZZY, ciclo riaperto | paper in DeliR | pari | peggio | meglio | peggio |
| AcademicCredentials | diagnosi: FUZZY, ciclo riaperto | ingenuo | peggio | peggio | peggio | peggio |
| BPIC_2012_W | SIMOD 5.2.1, calendari fissi | paper in DeliR | meglio | meglio | meglio | meglio |
| BPIC_2012_W | SIMOD 5.2.1, calendari fissi | ingenuo | peggio | peggio | peggio | pari |
| BPIC_2012_W | SIMOD 5.2.1, calendari FUZZY | paper in DeliR | meglio | meglio | peggio | meglio |
| BPIC_2012_W | SIMOD 5.2.1, calendari FUZZY | ingenuo | peggio | peggio | peggio | peggio |

## Discovery e import

| Log | Variante | Discovery (s) | Note d'import |
| --- | --- | --- | --- |
| AcademicCredentials | diff | 126 | info: instant_activity ×16 |
| AcademicCredentials | diff-loopfix | 126 | info: instant_activity ×16 |
| AcademicCredentials | fuzz | 453 | info: instant_activity ×5; info: probabilistic_calendars ×1 |
| AcademicCredentials | fuzz-loopfix | 453 | info: instant_activity ×5; info: probabilistic_calendars ×1 |
| BPIC_2012_W | diff | 750 | nessuna |
| BPIC_2012_W | fuzz | 456 | info: probabilistic_calendars ×1 |
