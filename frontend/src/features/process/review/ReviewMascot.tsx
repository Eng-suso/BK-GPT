/** DeliR's folded-D companion: a process sheet, rather than a stock robot. */
export function ReviewMascot() {
  return <svg className="review-mascot" viewBox="0 0 64 64" aria-hidden="true" focusable="false">
    <ellipse className="review-mascot-shadow" cx="32" cy="57" rx="17" ry="2.5" />
    <g className="review-mascot-character">
      <path className="review-mascot-feet" d="m24 49-3 6h7m10-6 3 6h-7" />
      <path className="review-mascot-arm" d="M14 32c-5 0-7 3-7 7m45-9c5-1 6-5 5-9" />
      <path className="review-mascot-body" d="M18 9h16c12 0 20 8 20 21v4c0 12-8 18-20 18H18a5 5 0 0 1-5-5V14a5 5 0 0 1 5-5Z" />
      <path className="review-mascot-spine" d="M18 9h6v43h-6a5 5 0 0 1-5-5V14a5 5 0 0 1 5-5Z" />
      <path className="review-mascot-fold" d="M35 9v11h15C47 14 42 10 35 9Z" />
      <path className="review-mascot-seam" d="M35 10v10h14" />
      <g className="review-mascot-eyes"><ellipse cx="33" cy="31" rx="2" ry="3" /><ellipse cx="43" cy="31" rx="2" ry="3" /></g>
      <path className="review-mascot-smile" d="M34 40q4 3 8-1" />
    </g>
  </svg>;
}
