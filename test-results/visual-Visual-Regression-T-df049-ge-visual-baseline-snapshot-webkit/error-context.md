# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: visual.spec.ts >> Visual Regression Tests >> Full page visual baseline snapshot
- Location: e2e\visual.spec.ts:4:7

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: page.waitForLoadState: Test timeout of 30000ms exceeded.
```

# Page snapshot

```yaml
- generic [ref=e3]:
  - complementary "Navigazione principale" [ref=e4]:
    - generic [ref=e5]:
      - generic [ref=e6]: A
      - generic [ref=e7]:
        - strong [ref=e8]: Area lavoro
        - generic [ref=e9]: Processi
    - navigation "Sezioni principali" [ref=e10]:
      - button "Home" [ref=e11] [cursor=pointer]:
        - generic [ref=e12]: H
      - button "Consulente" [ref=e14] [cursor=pointer]:
        - generic [ref=e15]: Co
      - button "Clienti" [ref=e17] [cursor=pointer]:
        - generic [ref=e18]: Cl
      - button "Progetti" [ref=e20] [cursor=pointer]:
        - generic [ref=e21]: P
      - button "Modelli" [ref=e23] [cursor=pointer]:
        - generic [ref=e24]: M
      - button "Archivio" [ref=e26] [cursor=pointer]:
        - generic [ref=e27]: A
    - button "Riduci navigazione" [ref=e29] [cursor=pointer]:
      - generic [ref=e30]: <
      - generic [ref=e31]: Riduci
  - generic [ref=e32]:
    - banner [ref=e33]:
      - generic [ref=e34]:
        - paragraph [ref=e35]: Area lavoro
        - heading "Consulente" [level=1] [ref=e36]
      - generic [ref=e37]:
        - button "Cerca" [ref=e38] [cursor=pointer]
        - button "Profilo utente" [ref=e39] [cursor=pointer]: MB
    - main [ref=e40]:
      - main "Chat consulente" [ref=e42]:
        - complementary "Conversazioni recenti" [ref=e43]:
          - generic [ref=e44]:
            - heading "Chat" [level=2] [ref=e45]
            - button "Cerca conversazione" [ref=e46] [cursor=pointer]
          - button "+ Nuova chat" [ref=e50] [cursor=pointer]:
            - generic [ref=e51]: +
            - generic [ref=e52]: Nuova chat
          - generic [ref=e53]:
            - generic [ref=e54]: Recenti
            - generic [ref=e55]: "0"
          - list [ref=e56]
          - button "Pulisci cronologia" [ref=e57] [cursor=pointer]
        - generic [ref=e58]:
          - generic [ref=e59]:
            - generic [ref=e60]:
              - strong [ref=e61]: Chat consulente
              - generic [ref=e62]: Locale
            - generic [ref=e63]:
              - button "Configurazione" [ref=e64] [cursor=pointer]
              - button "Condividi" [ref=e69] [cursor=pointer]
          - heading "Ciao! Come posso aiutarti oggi?" [level=1] [ref=e82]
          - generic [ref=e83]:
            - generic [ref=e84]:
              - textbox "Scrivi un messaggio..." [ref=e85]
              - generic [ref=e86]:
                - combobox "Modello AI" [ref=e87] [cursor=pointer]:
                  - option "gpt-5.6-luna" [selected]
                - generic [ref=e88]:
                  - button "Audio" [ref=e89] [cursor=pointer]
                  - button "Intervista" [ref=e93] [cursor=pointer]
                  - button "Invia" [disabled] [ref=e98]
            - generic [ref=e102]: Il modello puo commettere errori. Verifica sempre le risposte importanti.
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test.describe('Visual Regression Tests', () => {
  4  |   test('Full page visual baseline snapshot', async ({ page }) => {
  5  |     await page.goto('/');
> 6  |     await page.waitForLoadState('networkidle').catch(() => page.waitForLoadState('domcontentloaded'));
     |                                                                 ^ Error: page.waitForLoadState: Test timeout of 30000ms exceeded.
  7  | 
  8  |     // Capture visual snapshot of the page
  9  |     await expect(page).toHaveScreenshot('homepage-layout.png', {
  10 |       fullPage: true,
  11 |       // Mask dynamic elements if present (e.g. timestamps, live tickers)
  12 |       mask: [page.locator('.dynamic-timestamp, [data-testid="live-timer"]')],
  13 |     });
  14 |   });
  15 | 
  16 |   test('Component-level visual baseline snapshot', async ({ page }) => {
  17 |     await page.goto('/');
  18 |     await page.waitForLoadState('domcontentloaded');
  19 | 
  20 |     // Snapshot the top bar — a stable, bounded element present on all sections
  21 |     const header = page.locator('.product-topbar');
  22 |     if (await header.isVisible()) {
  23 |       await expect(header).toHaveScreenshot('header-component.png');
  24 |     }
  25 |   });
  26 | });
  27 | 
```