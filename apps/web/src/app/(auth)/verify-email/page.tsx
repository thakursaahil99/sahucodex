import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { VerifyEmailView } from "@/components/auth/password-reset-forms";

export const metadata: Metadata = { title: "Verify your email" };

export default function VerifyEmailPage() {
  return (
    <AuthCard title="Verify your email">
      <Suspense>
        <VerifyEmailView />
      </Suspense>
    </AuthCard>
  );
}
