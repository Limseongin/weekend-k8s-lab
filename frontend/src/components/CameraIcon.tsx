type Props = { className?: string };

export function CameraIcon({ className }: Props) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 7.5h3.5l1.8-2.5h7.4l1.8 2.5H21v11.5H3V7.5z" />
      <circle cx="12" cy="13.2" r="4.2" />
      <circle cx="17.8" cy="10" r="0.55" fill="currentColor" stroke="none" />
    </svg>
  );
}
