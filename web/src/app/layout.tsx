import type { Metadata, Viewport } from "next";
import { Inter, Space_Grotesk } from "next/font/google";

import { Toaster } from "@/components/ui/Toaster";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-body", display: "swap" });
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-heading",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Barterly",
  description: "Barterly vendor console: find talent for your stay, café or tour.",
};

export const viewport: Viewport = {
  themeColor: "#FBF8F3",
  colorScheme: "light",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-IN" className={`${inter.variable} ${spaceGrotesk.variable}`}>
      <body>
        {children}
        <Toaster />
      </body>
    </html>
  );
}
