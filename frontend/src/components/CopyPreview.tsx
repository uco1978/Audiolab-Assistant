interface CopyPreviewProps {
  html: string;
  className?: string;
}

export default function CopyPreview({ html, className = "" }: CopyPreviewProps) {
  return (
    <div
      className={`rtl-preview ${className}`}
      dir="rtl"
      lang="he"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
