import "@globalens/ui/tokens.css";
import "@globalens/ui/fonts.css";
import "./globals.css";

import { strings } from "@globalens/ui";
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: strings.meta.title,
  description: strings.meta.description,
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "dark",
  themeColor: "#030509",
};

/** The UI is English and left to right; text in other languages carries its own lang and dir. */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" dir="ltr">
      <body>{children}</body>
    </html>
  );
}
