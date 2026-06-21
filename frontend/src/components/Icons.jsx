// OASIS icon set — original inline SVGs (line style, inherit currentColor) used
// in place of emoji for titles, headings, tabs and cards. 24×24 grid.

function Svg({ size = 18, children, ...rest }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

// OASIS mark — a sun over a horizon (overheating + assessment)
export const IconOasis = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="10" r="3.4" />
    <path d="M12 2.6v1.8M12 15.6v1.2M4.2 10H6M18 10h1.8M6.5 4.5l1.2 1.2M16.3 4.5l-1.2 1.2" />
    <path d="M3 19h18M5.5 21.5h13" />
  </Svg>
);

// Draw & Analyze — pencil
export const IconPencil = (p) => (
  <Svg {...p}>
    <path d="M4 20h4l10.5-10.5a2 2 0 0 0 0-2.8l-1.2-1.2a2 2 0 0 0-2.8 0L4 16v4z" />
    <path d="M13.5 6.5l4 4" />
  </Svg>
);

// 3D Explore — isometric cube
export const IconCube = (p) => (
  <Svg {...p}>
    <path d="M12 2.8 21 7.5v9L12 21.2 3 16.5v-9L12 2.8z" />
    <path d="M3 7.5l9 4.7 9-4.7M12 12.2V21.2" />
  </Svg>
);

// HVI Map — folded map
export const IconMap = (p) => (
  <Svg {...p}>
    <path d="M9 3.5 3.5 5.5v15L9 18.5l6 2 5.5-2v-15L15 5.5l-6-2z" />
    <path d="M9 3.5v15M15 5.5v15" />
  </Svg>
);

// Heatmap & Drivers — thermometer
export const IconThermometer = (p) => (
  <Svg {...p}>
    <path d="M14 14.8V5a2 2 0 0 0-4 0v9.8a4 4 0 1 0 4 0z" />
    <path d="M12 9v6.5" />
  </Svg>
);

// Interventions — lightbulb
export const IconBulb = (p) => (
  <Svg {...p}>
    <path d="M9 18h6M10 21h4" />
    <path d="M12 3a6 6 0 0 0-4 10.5c.7.7 1.2 1.6 1.3 2.5h5.4c.1-.9.6-1.8 1.3-2.5A6 6 0 0 0 12 3z" />
  </Svg>
);

// Building Analysis — building with windows
export const IconBuilding = (p) => (
  <Svg {...p}>
    <path d="M5 21V5a1.5 1.5 0 0 1 1.5-1.5h7A1.5 1.5 0 0 1 15 5v16" />
    <path d="M15 9h3.5A1.5 1.5 0 0 1 20 10.5V21M3 21h18" />
    <path d="M8 7h3M8 11h3M8 15h3" />
  </Svg>
);

// Highest-risk — flame
export const IconFlame = (p) => (
  <Svg {...p}>
    <path d="M12 3s5 4 5 9a5 5 0 0 1-10 0c0-1.6.7-2.8 1.4-3.6.4 1 1.3 1.6 2.1 1.6 0-2.4 1.5-4.3 1.5-7z" />
  </Svg>
);

// Context buildings — cityscape (two buildings)
export const IconCityscape = (p) => (
  <Svg {...p}>
    <path d="M3 21V9l6-3v15M9 21V3l6 3v15M3 21h18M15 21V11l4 1.5V21" />
  </Svg>
);

export default {
  IconOasis, IconPencil, IconCube, IconMap, IconThermometer,
  IconBulb, IconBuilding, IconFlame, IconCityscape,
};
