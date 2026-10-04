"""Il giudice degli eval L2: un modello che legge il lavoro dell'agente e decide.

Serve dove una regola in Python non basta (la domanda di discovery era
necessaria? il riepilogo e' chiaro per un COO?) e solo li': tutto cio' che si
puo' verificare alla lettera resta a L0 e L1.

Due forme di giudizio, scelte in base alla domanda:

- **bounded** (`judge_bounded`): una domanda chiusa, si' o no, con una
  confidenza. E' la forma piu' stabile, perche' il giudice sceglie fra due
  risposte invece di scrivere un parere. E' la stessa idea di JevEval.
- **rubrica** (`judge_rubric`): un criterio soggettivo, con i passi con cui un
  valutatore umano lo applicherebbe, e un voto da 1 a 5. E' la stessa idea di
  G-Eval: i passi scritti rendono il voto ripetibile.

Il giudice passa dal gateway (compito `eval_judge`), quindi gira sul modello
dei test e i suoi consumi stanno nel registro sotto l'operazione EVAL. Un
giudice non vale niente finche' non e' calibrato: `agreement` lo confronta con
le etichette di un umano.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from backend.llm import LlmTask
from backend.llm import run as llm_run
from backend.llm.prompts import prompt_version, schema_part

# --- bounded -----------------------------------------------------------------


class BoundedVerdict(BaseModel):
    """La risposta del giudice a una domanda chiusa."""

    answer: Literal["si", "no"] = Field(description="La risposta alla domanda.")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Quanto sei sicuro, da 0 a 1. Sotto 0.6 vuol dire che il materiale non basta per decidere.",
    )
    reason: str = Field(description="Una frase: il passo del materiale su cui si regge la risposta.")

    @property
    def yes(self) -> bool:
        return self.answer == "si"


BOUNDED_SYSTEM = """Sei il valutatore di DeliR, un prodotto che ricostruisce processi aziendali
da interviste e documenti. Ricevi una domanda chiusa, il materiale di riferimento
e un elemento prodotto dall'agente.

Rispondi alla domanda con "si" o "no", basandoti solo sul materiale di
riferimento: non usare conoscenze tue sul dominio, non premiare un elemento
perche' suona plausibile. Se il materiale non basta per decidere, scegli la
risposta piu' prudente e abbassa la confidenza."""


def judge_bounded(*, question: str, context: str, item: str) -> BoundedVerdict:
    """Una domanda chiusa su un elemento, decisa sul materiale di riferimento."""
    from langchain_core.messages import HumanMessage, SystemMessage

    user = f"DOMANDA\n{question}\n\nMATERIALE DI RIFERIMENTO\n{context}\n\nELEMENTO DA GIUDICARE\n{item}"
    return llm_run(
        task=LlmTask.EVAL_JUDGE,
        messages=[SystemMessage(content=BOUNDED_SYSTEM), HumanMessage(content=user)],
        output=BoundedVerdict,
        input_characters=len(user),
        prompt_version=prompt_version("eval_judge_bounded", BOUNDED_SYSTEM, schema_part(BoundedVerdict)),
    )


# --- rubrica -----------------------------------------------------------------


@dataclass(frozen=True)
class Criterion:
    """Un criterio soggettivo, scritto come lo applicherebbe un valutatore umano."""

    name: str
    description: str
    steps: tuple[str, ...]


class RubricVerdict(BaseModel):
    """Il voto del giudice su un criterio."""

    score: int = Field(ge=1, le=5, description="1 = per niente, 5 = pienamente.")
    reason: str = Field(description="Una o due frasi: cosa ha deciso il voto.")


RUBRIC_SYSTEM = """Sei il valutatore di DeliR, un prodotto che ricostruisce processi aziendali
da interviste e documenti. Ricevi un criterio, i passi con cui applicarlo, il
materiale di riferimento e un elemento prodotto dall'agente.

Segui i passi nell'ordine, poi dai un voto da 1 a 5 sul solo criterio indicato.
1 vuol dire che l'elemento non soddisfa il criterio, 5 che lo soddisfa
pienamente. Giudica sul materiale di riferimento, non su conoscenze tue."""


def judge_rubric(*, criterion: Criterion, context: str, item: str) -> RubricVerdict:
    """Un voto da 1 a 5 su un criterio soggettivo, seguendo i suoi passi."""
    from langchain_core.messages import HumanMessage, SystemMessage

    steps = "\n".join(f"{index}. {step}" for index, step in enumerate(criterion.steps, start=1))
    user = (
        f"CRITERIO: {criterion.name}\n{criterion.description}\n\nPASSI\n{steps}\n\n"
        f"MATERIALE DI RIFERIMENTO\n{context}\n\nELEMENTO DA GIUDICARE\n{item}"
    )
    return llm_run(
        task=LlmTask.EVAL_JUDGE,
        messages=[SystemMessage(content=RUBRIC_SYSTEM), HumanMessage(content=user)],
        output=RubricVerdict,
        input_characters=len(user),
        prompt_version=prompt_version("eval_judge_rubric", RUBRIC_SYSTEM, schema_part(RubricVerdict)),
    )


# --- calibrazione --------------------------------------------------------------


def agreement(judge: list[bool], human: list[bool]) -> dict[str, float]:
    """Quanto il giudice concorda con un umano sulle stesse domande chiuse.

    | numero | cosa dice |
    | --- | --- |
    | accuracy | la quota di risposte uguali |
    | kappa | l'accordo al netto di quello che si avrebbe per caso (Cohen): 0 = un giudice che tira a indovinare, 1 = accordo pieno |

    L'accuracy da sola inganna su un campione sbilanciato: un giudice che dice
    sempre "si" su 9 casi "si" e 1 "no" fa 0.9 senza aver capito niente. Il
    kappa lo smaschera.
    """
    if len(judge) != len(human):
        raise ValueError("giudice e umano devono rispondere alle stesse domande")
    total = len(human)
    if not total:
        return {"accuracy": 0.0, "kappa": 0.0}
    agree = sum(1 for a, b in zip(judge, human, strict=True) if a == b)
    observed = agree / total
    p_judge_yes = sum(judge) / total
    p_human_yes = sum(human) / total
    expected = p_judge_yes * p_human_yes + (1 - p_judge_yes) * (1 - p_human_yes)
    kappa = 1.0 if expected == 1 else (observed - expected) / (1 - expected)
    return {"accuracy": round(observed, 4), "kappa": round(kappa, 4)}
