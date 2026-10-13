import { DelirLogo } from "@/components/brand/DelirLogo";

/** DeliR in the Review: the same "D." mark as the sidebar, on a quiet disc.
 *  It used to be a third "D" with eyes and feet; one identity reads as a product. */
export function ReviewMascot() {
  return <span className="review-mascot" aria-hidden="true"><DelirLogo compact /></span>;
}
