import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";

/**
 * L'utente simulato dei test, senza l'attesa fra un tasto e l'altro.
 *
 * `userEvent.setup()` cede il controllo all'event loop a ogni carattere. Su una
 * macchina scarica non si nota; quando la suite gira in parallelo con il resto
 * (o in CI su un runner condiviso) ogni cessione costa molto piu' del nominale,
 * e digitare una frase di trenta caratteri consumava da sola i cinque secondi
 * che `waitFor` aveva per verificare la scrittura. I test che fallivano non
 * erano quelli sbagliati: erano quelli che digitavano di piu'.
 *
 * `delay: null` toglie la cessione, non la simulazione: gli eventi di tastiera
 * restano quelli veri, uno per carattere, e le asserzioni non cambiano. Serve
 * un'attesa reale fra i tasti solo per testare debounce o throttle - in quel
 * caso si passa un `delay` esplicito, dichiarando perche'.
 */
export function setupUser(
  options: Parameters<typeof userEvent.setup>[0] = {},
): UserEvent {
  return userEvent.setup({ delay: null, ...options });
}
