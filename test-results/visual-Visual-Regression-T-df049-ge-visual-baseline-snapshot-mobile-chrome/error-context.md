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
    - generic [ref=e5]: A
    - navigation "Sezioni principali" [ref=e7]:
      - button "Home" [ref=e8] [cursor=pointer]:
        - generic [ref=e9]: H
      - button "Consulente" [ref=e10] [cursor=pointer]:
        - generic [ref=e11]: Co
      - button "Clienti" [ref=e12] [cursor=pointer]:
        - generic [ref=e13]: Cl
      - button "Progetti" [ref=e14] [cursor=pointer]:
        - generic [ref=e15]: P
      - button "Modelli" [ref=e16] [cursor=pointer]:
        - generic [ref=e17]: M
      - button "Archivio" [ref=e18] [cursor=pointer]:
        - generic [ref=e19]: A
    - button "Riduci navigazione" [ref=e20] [cursor=pointer]:
      - generic [ref=e21]: <
      - generic [ref=e22]: Riduci
  - generic [ref=e23]:
    - banner [ref=e24]:
      - generic [ref=e25]:
        - paragraph [ref=e26]: Area lavoro
        - heading "Consulente" [level=1] [ref=e27]
      - generic [ref=e28]:
        - button "Cerca" [ref=e29] [cursor=pointer]
        - button "Profilo utente" [ref=e30] [cursor=pointer]: MB
    - main [ref=e31]:
      - main "Chat consulente" [ref=e33]:
        - generic [ref=e34]:
          - generic [ref=e35]:
            - generic [ref=e36]:
              - button "Apri conversazioni" [ref=e37] [cursor=pointer]
              - strong [ref=e39]: Chat consulente
              - generic [ref=e40]: Locale
            - generic [ref=e41]:
              - button "Configurazione API" [ref=e42] [cursor=pointer]
              - button "Condividi chat" [ref=e46] [cursor=pointer]
          - heading "Ciao! Come posso aiutarti oggi?" [level=1] [ref=e58]
          - generic [ref=e59]:
            - generic [ref=e60]:
              - textbox "Scrivi un messaggio..." [ref=e61]
              - generic [ref=e62]:
                - combobox "Modello AI" [ref=e63] [cursor=pointer]:
                  - option "gpt-5.6-luna" [selected]
                - generic [ref=e64]:
                  - button "Carica audio da trascrivere" [ref=e65] [cursor=pointer]
                  - button "Avvia intervista live" [ref=e68] [cursor=pointer]
                  - button "Invia" [disabled] [ref=e72]
            - generic [ref=e76]: Il modello puo commettere errori. Verifica sempre le risposte importanti.
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