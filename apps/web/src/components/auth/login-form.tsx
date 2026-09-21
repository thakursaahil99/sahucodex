"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { describeAuthError } from "@/components/auth/errors";
import { Field, PasswordField } from "@/components/auth/field";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { login } from "@/lib/auth/session";
import { safeRedirect } from "@/lib/utils";
import { loginSchema, type LoginValues } from "@/lib/validation";

export function LoginForm() {
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });

  async function onSubmit(values: LoginValues) {
    setFormError(null);
    try {
      await login(values.identifier, values.password);
      router.replace(safeRedirect(next));
    } catch (error) {
      setFormError(describeAuthError(error));
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      {formError && <Alert tone="error">{formError}</Alert>}
      <Field
        label="Email or username"
        autoComplete="username"
        autoFocus
        error={errors.identifier?.message}
        {...register("identifier")}
      />
      <PasswordField
        label="Password"
        autoComplete="current-password"
        error={errors.password?.message}
        {...register("password")}
      />
      <div className="flex justify-end">
        <Link href="/forgot-password" className="text-sm text-link hover:underline">
          Forgot your password?
        </Link>
      </div>
      <Button type="submit" variant="gradient" className="w-full" loading={isSubmitting}>
        {isSubmitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
