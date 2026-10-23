import '@testing-library/jest-dom';

import { i18n, loadProcessTranslations } from '@/lib/i18n';

// `process.json` non sta piu' nel pacchetto d'ingresso (src/lib/i18n): i test
// rendono le schermate senza passare dal router, quindi lo portano giu' qui,
// in entrambe le lingue, prima del primo render.
await loadProcessTranslations();
await i18n.loadLanguages(['it', 'en']);
