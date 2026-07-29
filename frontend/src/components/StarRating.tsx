import { useState } from "react";

interface StarRatingProps {
  value: number | null;
  onChange: (rating: number) => void;
  disabled?: boolean;
}

export default function StarRating({ value, onChange, disabled }: StarRatingProps) {
  const [hover, setHover] = useState(0);

  const display = hover || value || 0;

  return (
    <span
      className="star-rating"
      onMouseLeave={() => setHover(0)}
      style={{ display: "inline-flex", gap: "2px", cursor: disabled ? "default" : "pointer" }}
    >
      {[1, 2, 3, 4, 5].map((star) => (
        <span
          key={star}
          role="button"
          tabIndex={disabled ? -1 : 0}
          onMouseEnter={() => !disabled && setHover(star)}
          onClick={() => !disabled && onChange(star)}
          onKeyDown={(e) => {
            if (!disabled && (e.key === "Enter" || e.key === " ")) onChange(star);
          }}
          style={{
            fontSize: "1.5rem",
            color: star <= display ? "#f5b731" : "var(--border)",
            transition: "color 0.15s",
          }}
        >
          ★
        </span>
      ))}
    </span>
  );
}
