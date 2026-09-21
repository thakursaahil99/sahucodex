import { Logo } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/layout/theme-toggle";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative isolate flex min-h-dvh flex-col overflow-hidden">
      <div className="bg-grid pointer-events-none absolute inset-0 -z-10" aria-hidden />
      <div className="glow-blue pointer-events-none absolute -top-32 left-1/2 -z-10 h-[420px] w-[560px] -translate-x-[90%] opacity-50" aria-hidden />
      <div className="glow-violet pointer-events-none absolute -top-24 left-1/2 -z-10 h-[400px] w-[520px] -translate-x-[5%] opacity-50" aria-hidden />
      <header className="flex h-16 items-center justify-between px-4 sm:px-6">
        <Logo />
        <ThemeToggle />
      </header>
      <main id="main" className="flex flex-1 items-start justify-center px-4 pt-6 pb-16 sm:items-center sm:pt-0">
        {children}
      </main>
    </div>
  );
}
