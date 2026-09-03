import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Resale Automator",
  description: "Local clothing-listing assistant",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
