import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "个人智能助手",
  description: "个人智能助手 - 对话、自动化与管理",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full bg-background text-foreground">{children}</body>
    </html>
  );
}
