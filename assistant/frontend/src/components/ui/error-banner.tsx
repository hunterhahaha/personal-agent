import { AlertCircle } from "lucide-react";

interface ErrorBannerProps {
  message: string | null;
}

export function ErrorBanner({ message }: ErrorBannerProps) {
  if (!message) return null;
  return (
    <div className="flex items-center gap-2 text-destructive text-sm mb-4">
      <AlertCircle className="w-4 h-4" />
      {message}
    </div>
  );
}
