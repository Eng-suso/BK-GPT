type IdleWindow = Window & {
  requestIdleCallback?: (callback: () => void) => number;
};

/**
 * Porta avanti le schermate su cui si atterra, appena il browser è libero.
 *
 * Caricare a richiesta (`src/app/screens.tsx`) paga sul peso del primo
 * caricamento e si fa pagare sulla prima apertura di ogni sezione. Su
 * `/projects` — dove arriva chiunque apra il prodotto — quell'attesa è
 * garantita, quindi non è un compromesso, è solo un ritardo: il pezzo si chiede
 * subito dopo il primo disegno, mentre la persona sta ancora leggendo la barra
 * laterale.
 *
 * Il canvas BPMN e la Simulazione restano fuori di proposito: sono i due pezzi
 * pesanti, e chi apre Clienti non deve scaricarli mai.
 */
export function warmLandingScreens(): void {
  if (typeof window === "undefined") return;

  const warm = () => {
    void import("@/features/projects");
    void import("@/features/clients");
  };

  const idle = (window as IdleWindow).requestIdleCallback;
  if (idle) {
    idle(warm);
  } else {
    window.setTimeout(warm, 0);
  }
}
