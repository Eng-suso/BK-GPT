# Landing DeliR

Pagina statica con l'hero e il video del prodotto (docs/launch/hero-video.md).

    python3 -m http.server 4310 --directory landing   # http://127.0.0.1:4310

- `media/`: il loop hero (WebM + MP4) e il poster, rigenerati da `npm run media:hero`.
- `fonts/`: Geist (OFL-1.1, vedi `GEIST-OFL.txt`).
- Verifica: `npx playwright test -c playwright.launch.config.ts landing.spec`.
