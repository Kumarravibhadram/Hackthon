import "./globals.css";

export const metadata = {
  title: "Nexa Bank | Employee AI",
  description: "AI workspace for Nexa Bank employees",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
