interface ImagePreviewProps {
  src: string;
  alt?: string;
  needsReview?: boolean;
}

export default function ImagePreview({ src, alt = "", needsReview }: ImagePreviewProps) {
  return (
    <div className="image-preview-wrap">
      <div
        className="image-preview-canvas"
        style={{ background: "var(--checker)" }}
      >
        <img src={src} alt={alt} />
      </div>
      {needsReview && <span className="review-flag">Needs review</span>}
      <style>{`
        .image-preview-wrap { text-align: center; }
        .image-preview-canvas {
          border-radius: 6px;
          overflow: hidden;
          border: 1px solid var(--border);
          aspect-ratio: 1;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .image-preview-canvas img {
          max-width: 100%;
          max-height: 100%;
          object-fit: contain;
        }
        .review-flag {
          display: block;
          font-size: 0.75rem;
          color: var(--danger);
          margin-top: 0.25rem;
        }
      `}</style>
    </div>
  );
}
