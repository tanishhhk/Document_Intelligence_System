import { useEffect, useRef } from "react";

// The guruCool guru: floats on his halo and reacts to the sign-in form.
// mood: "watch" | "shy" (eyes covered) | "peek" | "oops" | "bliss"
// look: { x, y } in -1..1 to aim his eyes; null follows the pointer.
// lit: how many of the four halo rings are lit (0 to 4).
// close: frame only his head and shoulders, for small screens.
const RINGS = [178, 238, 298, 358];
const INK = "#2a0f45";
const OUTLINE = { stroke: INK, strokeWidth: 4, strokeLinejoin: "round", strokeLinecap: "round" };
const SILHOUETTE = { ...OUTLINE, strokeWidth: 6 };
const LINE = { ...OUTLINE, strokeWidth: 3.5 };

// A stroke drawn twice, ink under white, so hair reads as outlined.
function Hair({ d, width = 9 }) {
  return (
    <g fill="none" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} stroke={INK} strokeWidth={width + 7} />
      <path d={d} stroke="#fff6e8" strokeWidth={width} />
    </g>
  );
}

export default function Guru({ mood = "watch", look = null, lit = 4, close = false }) {
  const svg = useRef(null);

  useEffect(() => {
    const node = svg.current;
    if (!node) return undefined;
    if (look) {
      node.style.setProperty("--look-x", look.x.toFixed(2));
      node.style.setProperty("--look-y", look.y.toFixed(2));
      return undefined;
    }
    const follow = (event) => {
      const box = node.getBoundingClientRect();
      // The head sits about a third of the way down the drawing.
      const dx = event.clientX - (box.left + box.width / 2);
      const dy = event.clientY - (box.top + box.height * (close ? 0.4 : 0.35));
      const reach = Math.max(window.innerWidth, window.innerHeight) / 2;
      node.style.setProperty("--look-x", Math.max(-1, Math.min(1, dx / reach)).toFixed(2));
      node.style.setProperty("--look-y", Math.max(-1, Math.min(1, dy / reach)).toFixed(2));
    };
    window.addEventListener("pointermove", follow, { passive: true });
    return () => window.removeEventListener("pointermove", follow);
  }, [look, close]);

  return (
    <svg
      ref={svg}
      className="gc-guru"
      data-mood={mood}
      viewBox={close ? "140 130 320 300" : "0 0 600 690"}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <clipPath id="gc-eye-l">
          <ellipse cx="272" cy="246" rx="15" ry="13" />
        </clipPath>
        <clipPath id="gc-eye-r">
          <ellipse cx="328" cy="246" rx="15" ry="13" />
        </clipPath>
      </defs>

      <g className="gc-halo">
        {RINGS.map((radius, index) => (
          <circle
            key={radius}
            className={`gc-ring${index < lit ? " is-lit" : ""}`}
            data-ring={index}
            cx="300"
            cy="255"
            r={radius}
            fill="none"
            strokeWidth="30"
          />
        ))}
        <circle className="gc-sun" cx="300" cy="255" r="124" />
      </g>

      <ellipse className="gc-shadow" cx="300" cy="662" rx="150" ry="14" />

      <g className="gc-float">
        <g className="gc-body">
          <path
            className="gc-robe"
            d="M200 382C210 346 250 330 300 330s90 16 100 52l30 178H170Z"
            {...SILHOUETTE}
          />
          <path className="gc-sash" d="M258 336c42 44 82 132 122 224h-42c-30-78-62-148-104-210Z" />
          <path
            className="gc-robe"
            d="M130 562c0-40 70-46 170-32 100-14 170-8 170 32s-70 54-170 44c-100 10-170-4-170-44Z"
            {...SILHOUETTE}
          />
          <path className="gc-fold" d="M300 532c-4 28 0 52 0 72M214 548c18 8 36 10 52 8M386 548c-18 8-36 10-52 8" />
          <ellipse className="gc-skin" cx="222" cy="586" rx="30" ry="13" transform="rotate(8 222 586)" {...LINE} />
          <ellipse className="gc-skin" cx="378" cy="586" rx="30" ry="13" transform="rotate(-8 378 586)" {...LINE} />
          <path className="gc-robe" d="M206 380c-26 52-22 108 26 136l30-22c-32-22-34-62-24-94Z" {...SILHOUETTE} />
          <path className="gc-robe" d="M394 380c26 52 22 108-26 136l-30-22c32-22 34-62 24-94Z" {...SILHOUETTE} />

          {/* The book in his lap is the guruCool page. */}
          <g className="gc-book">
            <path d="M262 466h58l18 18v62a3 3 0 0 1-3 3h-73a3 3 0 0 1-3-3v-77a3 3 0 0 1 3-3Z" fill="#fff" {...LINE} />
            <path d="M320 466v18h18" fill="none" {...LINE} />
            <path d="M268 501l60-5 2 13-60 5Z" fill="#ffd23f" />
            <path d="M272 488h30M272 508h48M272 528h40" fill="none" stroke={INK} strokeWidth="3.5" strokeLinecap="round" />
          </g>
          <circle className="gc-skin" cx="258" cy="512" r="17" {...LINE} />
          <circle className="gc-skin" cx="342" cy="512" r="17" {...LINE} />
        </g>

        <g className="gc-head">
          <circle className="gc-skin" cx="222" cy="262" r="16" {...SILHOUETTE} />
          <circle className="gc-skin" cx="378" cy="262" r="16" {...SILHOUETTE} />
          <circle className="gc-skin" cx="300" cy="250" r="80" {...SILHOUETTE} />
          <ellipse cx="270" cy="200" rx="20" ry="9" transform="rotate(-24 270 200)" fill="#fff" opacity="0.45" />
          <path className="gc-skin-shade" d="M300 252c-9 18-9 28 0 32 6 2 11 0 13-5" fill="none" {...LINE} />

          <path
            className="gc-beard"
            d="M232 280c4 50 18 100 36 130 16-10 24 18 24 18 12-24 24-2 24-2 14-28 20-16 20-16 16-30 30-80 32-130-18 20-38 26-68 26s-50-6-68-26Z"
            {...SILHOUETTE}
          />
          <Hair d="M300 300c-22-12-40-6-48 4-6 8-14 6-16-2M300 300c22-12 40-6 48 4 6 8 14 6 16-2" width={8} />

          <path className="gc-mouth gc-mouth-smile" d="M287 316q13 11 26 0" fill="none" {...LINE} />
          <ellipse className="gc-mouth gc-mouth-o" cx="300" cy="318" rx="6" ry="8" fill={INK} />
          <path className="gc-mouth gc-mouth-grin" d="M282 312q18 22 36 0Z" fill={INK} {...LINE} />

          <g className="gc-eyes">
            <ellipse cx="272" cy="246" rx="15" ry="13" fill="#fff" />
            <ellipse cx="328" cy="246" rx="15" ry="13" fill="#fff" />
            <g clipPath="url(#gc-eye-l)">
              <circle className="gc-pupil" cx="272" cy="247" r="6.5" fill={INK} />
            </g>
            <g clipPath="url(#gc-eye-r)">
              <circle className="gc-pupil" cx="328" cy="247" r="6.5" fill={INK} />
            </g>
            <ellipse cx="272" cy="246" rx="15" ry="13" fill="none" {...LINE} />
            <ellipse cx="328" cy="246" rx="15" ry="13" fill="none" {...LINE} />
          </g>

          <g className="gc-brows">
            <Hair d="M254 224q17-14 36-4" />
            <Hair d="M346 224q-17-14-36-4" />
          </g>

          <g className="gc-shades">
            <path d="M246 268 222 262M354 268l24-6M294 272q6-6 12 0" fill="none" {...LINE} />
            <rect x="244" y="262" width="50" height="30" rx="12" fill={INK} />
            <rect x="306" y="262" width="50" height="30" rx="12" fill={INK} />
            <path d="M253 272l12-5M315 272l12-5" stroke="#fff" strokeWidth="3.5" strokeLinecap="round" opacity="0.85" />
          </g>
        </g>
      </g>
    </svg>
  );
}
