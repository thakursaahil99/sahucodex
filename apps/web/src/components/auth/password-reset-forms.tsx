"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";

import { describeAuthError } from "@/components/auth/errors";
import { Field, PasswordField } from "@/components/auth/field";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { http } from "@/lib/api/http";
import type { MessageResponse } from "@/lib/api/types";
import {
  forgotPasswordSchema,
  resetPasswordSchema,
  type ForgotPasswordValues,
  type ResetPasswordValues,
} from "@/lib/validation";

export function ForgotPasswordForm() {
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotPasswordValues>({ resolver: zodResolver(forgotPasswordSchema) });

  async function onSubmit(values: ForgotPasswordValues) {
    setFormError(null);
    try {
      await http<MessageResponse>("/auth/password/forgot", { method: "POST", body: values });
      setSent(true);
    } catch (error) {
      setFormError(describeAuthError(error));
    }
  }

  if (sent) {
    return (
      <Alert tone="success" title="Check your inbox">
        If that email is registered, a reset link is on its way. It expires in one hour.
      </Alert>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      {formError && <Alert tone="error">{formError}</Alert>}
      <Field
        label="Email"
        type="email"
        autoComplete="email"
        autoFocus
        error={errors.email?.message}
        {...register("email")}
      />
      <Button type="submit" variant="gradient" className="w-full" loading={isSubmitting}>
        Send reset link
      </Button>
    </form>
  );
}

export function ResetPasswordForm() {
  const token = useSearchParams().get("token");
  const [done, setDone] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetPasswordValues>({ resolver: zodResolver(resetPasswordSchema) });

  if (!token) {
    return (
      <Alert tone="error" title="This link is incomplete">
        <Link href="/forgot-password" className="text-link underline">
          Request a new reset link
        </Link>
        .
      </Alert>
    );
  }

  if (done) {
    return (
      <div className="space-y-4">
        <Alert tone="success" title="Password updated">
          You were signed out everywhere for safety. Sign in with your new password.
        </Alert>
        <Button asChild variant="gradient" className="w-full">
          <Link href="/login">Go to sign in</Link>
        </Button>
      </div>
    );
  }

  async function onSubmit(values: ResetPasswordValues) {
    setFormError(null);
    try {
      await http<MessageResponse>("/auth/password/reset", {
        method: "POST",
        body: { token, new_password: values.password },
      });
      setDone(true);
    } catch (error) {
      setFormError(describeAuthError(error));
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      {formError && <Alert tone="error">{formError}</Alert>}
      <PasswordField
        label="New password"
        autoComplete="new-password"
        autoFocus
        hint="At least 10 characters."
        error={errors.password?.message}
        {...register("password")}
      />
      <PasswordField
        label="Confirm new password"
        autoComplete="new-password"
        error={errors.confirm?.message}
        {...register("confirm")}
      />
      <Button type="submit" variant="gradient" className="w-full" loading={isSubmitting}>
        Update password
      </Button>
    </form>
  );
}

export function VerifyEmailView() {
  const token = useSearchParams().get("token");
  const started = useRef(false);
  const [state, setState] = useState<"working" | "ok" | "failed">(token ? "working" : "failed");
  const [message, setMessage] = useState<string>("This link is incomplete.");

  useEffect(() => {
    // The link is single-use, so guard against React StrictMode running this effect twice in dev.
    if (!token || started.current) return;
    started.current = true;
    http<MessageResponse>("/auth/verify-email", { method: "POST", body: { token } })
      .then(() => setState("ok"))
      .catch((error) => {
        setMessage(describeAuthError(error));
        setState("failed");
      });
  }, [token]);

  if (state === "working") return <p role="status">Verifying your email…</p>;
  if (state === "ok") {
    return (
      <div className="space-y-4">
        <Alert tone="success" title="Email verified">
          Thanks — your address is confirmed.
        </Alert>
        <Button asChild variant="gradient" className="w-full">
          <Link href="/dashboard">Continue to SahuCodeX</Link>
        </Button>
      </div>
    );
  }
  return (
    <Alert tone="error" title="We couldn't verify that link">
      {message}
    </Alert>
  );
}
