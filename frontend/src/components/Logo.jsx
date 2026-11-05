// The guruCool mark: a dog-eared page with one line run over by a highlighter.
export function Mark({ size = 32, className = "" }) {
  return (
    <svg
      className={`mark ${className}`}
      width={size}
      height={size}
      viewBox="0 0 40 40"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M9 3.5h16.5L33 11v24.5a1.5 1.5 0 0 1-1.5 1.5h-22.5A1.5 1.5 0 0 1 7.5 35.5V5A1.5 1.5 0 0 1 9 3.5Z"
        fill="#fff"
        stroke="#0e2229"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <path d="M25.5 3.5V11H33" fill="none" stroke="#0e2229" strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M10.2 20.2 30.6 18.4l.9 6.3-20.4 1.9Z" fill="#ffc94d" />
      <path d="M12 15.5h10M12 22.6h16M12 29.5h13" stroke="#0e2229" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

export function Logo({ size = 32, className = "" }) {
  return (
    <span className={`logo ${className}`}>
      <Mark size={size} />
      <span className="logo-word">guruCool</span>
    </span>
  );
}
