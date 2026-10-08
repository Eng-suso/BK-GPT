# Compatibilità del BPMN con il motore (SIM-05)

Prima di un run, `backend/simulation/bpmn_normalizer.py` riduce il BPMN del consulente al vocabolario di Prosimos. Il report di compatibilità dice, elemento per elemento, che cosa è successo e quanto pesa sui KPI.

```
POST /v1/workspace/bpmn-models/{id}/simulation-compatibility
{ "current_bpmn_xml": "<opzionale: il BPMN in modifica>" }
```

Senza `current_bpmn_xml` si usa il BPMN salvato. Se non c'è nessun BPMN la risposta è 400, se il modello non esiste è 404.

## Come nasce

Il report (`backend/simulation/compatibility.py`) non duplica le regole del normalizer: normalizza il BPMN e lo confronta con l'originale. Un elemento sparito, che ha cambiato tipo o un flusso ricollegato finisce sempre nel report. Le regole servono solo a spiegare il motivo e a stimare l'impatto.

`undeclared` conta i cambi senza una voce che li spieghi. Deve valere sempre zero: se una regola nuova del normalizer non viene descritta, il test `test_nothing_the_normalizer_changes_goes_undeclared` fallisce.

## Stati

| Stato | Significato | Esempi |
|---|---|---|
| `preserved` | Il motore lo esegue così com'è. Un cambio di tipo innocuo ha una nota. | task, gateway esclusivi e paralleli, `userTask` simulato come task |
| `approximated` | Il motore lo esegue in una forma più semplice. | attività con ciclo o multi-istanza, `receiveTask`, `callActivity`, `complexGateway`, inizi e fini uniti, flussi ricollegati |
| `flattened` | Ridotto a una scatola nera. | sottoprocesso; i suoi passi interni hanno `parent_id` |
| `removed` | Non arriva al motore. | eventi di bordo e ramo d'eccezione, eventi intermedi, lane, annotazioni |

## Impatto sui KPI

- `high`: sposta cycle time, attese, costi o percorsi in modo sistematico. Esempi: sottoprocesso appiattito, timer intermedio saltato, ramo d'eccezione mai percorso, ciclo eseguito una volta.
- `medium`: cambia il comportamento di alcuni casi. Esempi: attesa di un messaggio, gateway complesso trattato come esclusivo.
- `low`: effetto piccolo o indiretto. Esempi: più inizi uniti in uno, evento di bordo senza ramo.
- `none`: nessun effetto sui KPI. Esempi: lane (restano risorse lette dal BPMN originale), annotazioni, flussi assorbiti.

`kpi_affecting` conta gli elementi non preservati con impatto diverso da `none`: è il numero da mostrare al consulente prima del run.
