"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/upload", label: "Upload" },
  { href: "/chat", label: "Legal Chat" },
  { href: "/documents", label: "Documents" },
  { href: "/evaluation", label: "Evaluation" },
];

export function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const { token, email, logout } = useAuth();

  if (pathname === "/login") return null;

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <div className="flex items-center gap-6">
          <Link href="/dashboard" className="text-lg font-bold text-brand">
            ⚖️ LexAegis AI
          </Link>
          <nav className="hidden gap-1 md:flex">
            {LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm",
                  pathname === link.href
                    ? "bg-brand text-white"
                    : "text-slate-600 hover:bg-slate-100"
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-slate-500">{email ?? (token ? "authenticated" : "guest")}</span>
          <button
            className="rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-100"
            onClick={() => {
              logout();
              router.push("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
