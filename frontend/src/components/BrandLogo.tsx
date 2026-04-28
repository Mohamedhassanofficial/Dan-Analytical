import { NavLink } from "react-router-dom";
import { useLocale } from "@/contexts/LocaleContext";

/**
 * DAN Analytical brand mark.
 *
 * The product is named after Loay's 10-year-old son Dan ("تيمناً بيه و
 * عشان يكون وش السعد"). Loay asked for the logo to live prominently in
 * every screen header and to render in the user's chosen language —
 * Arabic users see the Arabic wordmark "دان التحليلي", English users
 * see "DAN ANALYTICAL APPLICATIONS". The medallion itself stays the same
 * gold seal in both versions.
 *
 * Source assets: `public/dan-logo.svg` (EN) + `public/dan-logo-ar.svg`
 * (AR). When higher-res official assets land, swap them in the same
 * filenames — every header picks them up automatically.
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
  const { locale } = useLocale();
  const src = locale === "ar" ? "/dan-logo-ar.svg" : "/dan-logo.svg";
  const alt = locale === "ar" ? "دان التحليلي" : "DAN Analytical Applications";

  // Loay asked for the brand mark to read prominently on every screen.
  // Sidebar (md) → 80-96 px, legacy top-bar slot (lg) → 96-112 px.
  // All four classes ship in the default Tailwind scale; sm:h-22 doesn't
  // exist so the prior pass would have collapsed md to h-20 on sm+.
  const heightClass = size === "lg" ? "h-24 sm:h-28" : "h-20 sm:h-24";
  const content = (
    <span className={`inline-flex items-center gap-1 ${className}`} aria-label={alt}>
      <img
        src={src}
        alt={alt}
        className={`${heightClass} w-auto select-none drop-shadow-sm`}
        draggable={false}
        style={inverse ? { filter: "drop-shadow(0 0 1px rgba(255,255,255,0.4))" } : undefined}
      />
    </span>
  );

  if (!linked) return content;

  return (
    <NavLink to="/" className="inline-flex items-center" aria-label={alt}>
      {content}
    </NavLink>
  );
}
