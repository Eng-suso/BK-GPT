/** A small working companion. Motion is finite and follows explicit selection. */
export function ReviewMascot() {
  return <svg className="review-mascot" viewBox="0 0 48 48" aria-hidden="true" focusable="false">
    <ellipse className="review-mascot-shadow" cx="24" cy="43" rx="11" ry="2" />
    <g className="review-mascot-character">
      <path className="review-mascot-antenna" d="M24 10V5" />
      <circle className="review-mascot-signal" cx="24" cy="4" r="2" />
      <path className="review-mascot-body" d="M8 23C8 14 14 10 24 10s16 4 16 13v8c0 7-7 11-16 11S8 38 8 31Z" />
      <path className="review-mascot-arm" d="M8 26c-5 0-5 7 0 7M40 26c5 0 5 7 0 7" />
      <rect className="review-mascot-visor" x="12" y="17" width="24" height="14" rx="7" />
      <g className="review-mascot-eyes"><ellipse cx="19" cy="24" rx="2" ry="3" /><ellipse cx="29" cy="24" rx="2" ry="3" /></g>
      <path className="review-mascot-smile" d="M21 35q3 2 6 0" />
    </g>
  </svg>;
}
