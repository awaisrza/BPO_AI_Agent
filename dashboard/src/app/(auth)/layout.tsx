import { Space_Grotesk } from "next/font/google";

const authDisplay = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-auth-display",
  weight: ["500", "600", "700"],
});

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <div className={authDisplay.variable}>{children}</div>;
}
