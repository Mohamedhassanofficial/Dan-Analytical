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

  const heightClass = size === "lg" ? "h-12 sm:h-14" : "h-10";
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
