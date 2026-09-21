"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { describeAuthError } from "@/components/auth/errors";
import { Field, PasswordField } from "@/components/auth/field";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { fieldErrors, isApiError } from "@/lib/api/http";
import { register as registerAccount } from "@/lib/auth/session";
import { registerSchema, type RegisterValues } from "@/lib/validation";

const FIELDS = ["email", "username", "password"] as const;

export function RegisterForm() {
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });

  async function onSubmit(values: RegisterValues) {
    setFormError(null);
    try {
      await registerAccount(values);
      toast.success("Welcome to SahuCodeX", { description: "We sent a link to verify your email address." });
      router.replace("/dashboard");
    } catch (error) {
      if (isApiError(error)) {
        if (error.code === "EMAIL_TAKEN") return setError("email", { message: error.message });
        if (error.code === "USERNAME_TAKEN") return setError("username", { message: error.message });
        if (error.code === "VALIDATION_ERROR") {
          const byField = fieldErrors(error);
          const matched = FIELDS.filter((name) => byField[name]);
          matched.forEach((name) => setError(name, { message: byField[name] }));
          if (matched.length) return;
        }
      }
      setFormError(describeAuthError(error));
    }
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
      <Field
        label="Username"
        autoComplete="username"
        autoCapitalize="none"
        spellCheck={false}
        hint="3–30 characters: letters, numbers, _ or -"
        error={errors.username?.message}
        {...register("username")}
      />
      <PasswordField
        label="Password"
        autoComplete="new-password"
        hint="At least 10 characters. A few random words make a strong passphrase."
        error={errors.password?.message}
        {...register("password")}
      />
      <Button type="submit" variant="gradient" className="w-full" loading={isSubmitting}>
        {isSubmitting ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
