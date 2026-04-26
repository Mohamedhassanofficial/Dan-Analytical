import { NavLink } from "react-router-dom";

/**
 * DAN Analytical brand mark.
 *
 * The product is named after Loay's 10-year-old son Dan ("تيمناً بيه و
 * عشان يكون وش السعد"). Loay asked for the logo to live prominently in
 * every screen header rather than being tucked into the sidebar — this
 * component is the single source of truth for that. Two size variants
 * keep the medallion legible whether it's in the TopBar or in the dark
 * sidebar header.
 *
 * Source asset: `public/dan-logo.svg`. When a higher-res official asset
 * lands in the repo, swap the `src` here in one place.
 */

interface BrandLogoProps {
  /** "lg" lives in the TopBar; "md" lives in the sidebar. */
  size?: "lg" | "md";
  /** Wraps the logo in a NavLink to "/" when truthy (default true). */
  linked?: boolean;
  /** Forces the wordmark / subtitle to render in white over a dark surface. */
  inverse?: boolean;
  className?: string;
}

export default function BrandLogo({
  size = "lg",
  linked = true,
  inverse = false,
  className = "",
}: BrandLogoProps) {
  const heightClass = size === "lg" ? "h-12 sm:h-14" : "h-10";
  const content = (
    <span
      className={`inline-flex items-center gap-1 ${className}`}
      aria-label="DAN Analytical Applications"
    >
      <img
        src="/dan-logo.svg"
        alt="DAN Analytical Applications"
        className={`${heightClass} w-auto select-none drop-shadow-sm`}
        draggable={false}
        style={inverse ? { filter: "drop-shadow(0 0 1px rgba(255,255,255,0.4))" } : undefined}
      />
    </span>
  );

  if (!linked) return content;

  return (
    <NavLink to="/" className="inline-flex items-center" aria-label="DAN Analytical home">
      {content}
    </NavLink>
  );
}
