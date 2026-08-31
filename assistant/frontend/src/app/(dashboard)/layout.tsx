import { Sidebar } from "@/components/layout/sidebar";
import { Toaster } from "sonner";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground">
      <Sidebar />
      <main className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden bg-background">
        {children}
      </main>
      <Toaster position="top-right" richColors />
    </div>
  );
}
