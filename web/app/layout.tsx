import type { Metadata } from "next";
import { Atkinson_Hyperlegible } from "next/font/google";
import "./globals.css";

const atkinson = Atkinson_Hyperlegible({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-atkinson",
});

export const metadata: Metadata = {
  title: "NBT · Startup Breakdowns",
  description: "Editorial startup breakdowns for ambitious young founders.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={atkinson.variable} data-scroll-behavior="smooth">
      <body className="font-body antialiased">{children}</body>
    </html>
  );
}
