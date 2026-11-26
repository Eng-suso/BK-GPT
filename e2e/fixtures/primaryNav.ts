import type { Page } from "@playwright/test";

/** La navigazione principale: sul telefono sta in un cassetto che si apre dal menu. */
export async function primaryNav(page: Page) {
  // Prima la shell: il cancello di accesso chiede al backend come entrare, e
  // finche' non risponde il pulsante del menu non c'e'. Guardarlo subito
  // diceva "non visibile" sul telefono e il cassetto restava chiuso.
  await page.getByRole("banner").waitFor();
  const menu = page.getByRole("button", { name: "Apri la navigazione" });
  if (await menu.isVisible()) await menu.click();
  return page.getByRole("complementary", { name: "Navigazione principale" });
}
