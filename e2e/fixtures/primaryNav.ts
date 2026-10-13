import type { Page } from "@playwright/test";

/** La navigazione principale: sul telefono sta in un cassetto che si apre dal menu. */
export async function primaryNav(page: Page) {
  const menu = page.getByRole("button", { name: "Apri la navigazione" });
  if (await menu.isVisible()) await menu.click();
  return page.getByRole("complementary", { name: "Navigazione principale" });
}
