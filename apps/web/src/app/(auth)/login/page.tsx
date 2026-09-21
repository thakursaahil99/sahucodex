import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <AuthCard
      title="Welcome back"
      description="Sign in to keep solving."
      footer={
        <>
          New to SahuCodeX?{" "}
          <Link href="/register" className="font-medium text-link hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      {/* useSearchParams() (for ?next=) needs a Suspense boundary */}
      <Suspense>
        <LoginForm />
      </Suspense>
    </AuthCard>
  );
}
