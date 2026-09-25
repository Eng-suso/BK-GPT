import { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ErrorState } from "./ErrorState";

type ErrorBoundaryProps = {
  children: ReactNode;
  /**
   * Quando cambia, la schermata rotta viene riprovata da sola. Di solito è il
   * percorso corrente: navigare altrove non deve lasciare l'errore sullo
   * schermo.
   */
  resetKey?: string;
  /** Cosa mostrare al posto della schermata. Il default è {@link CrashState}. */
  fallback?: (error: Error, retry: () => void) => ReactNode;
};

type ErrorBoundaryState = {
  error: Error | null;
};

/**
 * La rete sotto il render.
 *
 * Senza, un errore in un componente smonta l'intero albero React e la pagina
 * resta bianca: nessun messaggio, nessuna navigazione, nessun modo di uscirne
 * se non ricaricare. E ricaricare, in questo prodotto, costa il turno di chat
 * in corso, perché il turno vive nella memoria del browser.
 *
 * Non sostituisce la gestione degli errori delle query — quella resta dove
 * l'errore succede, con il suo `ErrorState` e il suo "Riprova". Questa prende
 * quello che nessuno ha previsto.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // In produzione questo è l'unico posto dove l'errore esiste ancora: il
    // render è già stato buttato via.
    console.error("[ui] schermata interrotta", error, info.componentStack);
  }

  componentDidUpdate(previous: ErrorBoundaryProps): void {
    if (this.state.error && previous.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  private retry = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (this.props.fallback) return this.props.fallback(error, this.retry);
    return <CrashState onRetry={this.retry} />;
  }
}

/**
 * Cosa si legge al posto di una schermata che si è fermata.
 *
 * Sta fuori dalla classe perché le traduzioni vivono in un hook, e un
 * componente a classe non ne ha.
 */
function CrashState({ onRetry }: { onRetry: () => void }): React.JSX.Element {
  const { t } = useTranslation("common");
  return (
    <div className="flex h-full min-h-0 items-center justify-center p-6">
      <ErrorState
        title={t("state.crash")}
        description={t("state.crashBody")}
        onRetry={onRetry}
        retryLabel={t("actions.retryScreen")}
      />
    </div>
  );
}
