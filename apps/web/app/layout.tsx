import type { Metadata, Viewport } from "next";
import { Montserrat } from "next/font/google";

import { WakePing } from "@/components/brand/WakePing";
import { institution } from "@/lib/institution";

import "./globals.css";

const montserrat = Montserrat({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-montserrat",
  display: "swap",
});

export const metadata: Metadata = {
  title: institution.productName,
  description: `Verified answers to student questions at ${institution.name}.`,
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={montserrat.variable}>
      <body className="bg-bg text-text antialiased">
        <WakePing />
        {children}
      </body>
    </html>
  );
}
