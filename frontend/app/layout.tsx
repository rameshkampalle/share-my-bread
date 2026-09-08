import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Share My Bread",
  description: "Community grocery inventory with an AI shopping assistant.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
