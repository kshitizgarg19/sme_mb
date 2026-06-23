import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/Nav";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "SME Multibagger Scanner",
  description: "Fundamentals-first ranking of NSE Emerge & BSE SME stocks by multibagger potential.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <Nav />
        <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">{children}</main>
        <footer className="border-t border-zinc-900 px-6 py-5 text-center text-xs text-zinc-600">
          <p>Research tooling, not investment advice. SME equities are illiquid and carry elevated risk.</p>
          <p className="mt-1.5 text-zinc-500">Engineered by <span className="font-medium text-zinc-300">Kshitiz Garg</span></p>
        </footer>
      </body>
    </html>
  );
}
