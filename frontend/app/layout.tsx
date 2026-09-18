import "./globals.css";

export const metadata = {
  title: "Northstar Bank | Employee AI",
  description: "AI workspace for Northstar Bank employees",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
