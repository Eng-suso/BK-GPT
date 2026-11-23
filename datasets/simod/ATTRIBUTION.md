# SIMOD — configurazioni e log di esempio

Fonte: [AutomatedProcessImprovement/Simod](https://github.com/AutomatedProcessImprovement/Simod),
commit `7e5de02e1b81ca4abb8d8dcd28b0ad315520b43e` (23 settembre 2026). Licenza
Apache-2.0, copia in `LICENSE`. Paper: Chapela-Campa, López-Pintado, Suvorau,
Dumas, "SIMOD: Automated discovery of business process simulation models",
*SoftwareX* 30, 102157 (2025).

| File | Origine nel repo SIMOD | Uso in DeliR |
| --- | --- | --- |
| `config/*.yml`, `config/benchmark/` | `resources/config/` | configurazioni di partenza per lo spike G3 (SIMOD come discovery) |
| `event-logs/Insurance_Claims_train.csv`, `_test.csv` | `tests/assets/` | log con la colonna `extraneous_delay` nota: verifica di B5 |
| `event-logs/LoanApp_simplified.csv.gz`, `.bpmn` | `tests/assets/` | caso minimo per i test di import e discovery |

Nessuna modifica ai file. Il resto del repo SIMOD si scarica con
`scripts/fetch_datasets.py simod`.
