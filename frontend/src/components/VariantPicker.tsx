import CopyPreview from "./CopyPreview";

interface Variant {
  id: string;
  label: string;
  html: string;
  shortDescription: string;
  selected?: boolean;
}

interface VariantPickerProps {
  variants: Variant[];
  onSelect: (id: string) => void;
}

export default function VariantPicker({ variants, onSelect }: VariantPickerProps) {
  if (variants.length === 0) return null;

  return (
    <div className="variant-grid">
      {variants.map((v) => (
        <div
          key={v.id}
          className={`variant-card ${v.selected ? "selected" : ""}`}
        >
          <h3>{v.label}</h3>
          <p className="muted">{v.shortDescription.slice(0, 120)}…</p>
          <CopyPreview html={v.html.slice(0, 500)} />
          <div className="actions">
            <button type="button" onClick={() => onSelect(v.id)}>
              Use this version
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
