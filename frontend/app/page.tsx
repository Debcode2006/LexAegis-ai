"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  const { token } = useAuth();
  useEffect(() => {
    router.replace(token ? "/dashboard" : "/login");
  }, [token, router]);
  return <p className="text-slate-500">Loading…</p>;
}
