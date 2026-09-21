import { z } from "zod";

/** Client-side mirrors of the API's rules, for instant feedback. The API remains the authority. */

export const usernameSchema = z
  .string()
  .regex(/^[A-Za-z0-9_-]{3,30}$/, "3–30 characters: letters, numbers, _ or -");

export const passwordSchema = z
  .string()
  .min(10, "Use at least 10 characters")
  .max(128, "Use at most 128 characters");

export const emailSchema = z.string().trim().pipe(z.email("Enter a valid email address"));

export const loginSchema = z.object({
  identifier: z.string().trim().min(1, "Enter your email or username"),
  password: z.string().min(1, "Enter your password"),
});
export type LoginValues = z.infer<typeof loginSchema>;

export const registerSchema = z.object({
  email: emailSchema,
  username: usernameSchema,
  password: passwordSchema,
});
export type RegisterValues = z.infer<typeof registerSchema>;

export const forgotPasswordSchema = z.object({ email: emailSchema });
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>;

export const resetPasswordSchema = z
  .object({ password: passwordSchema, confirm: z.string() })
  .refine((values) => values.password === values.confirm, {
    path: ["confirm"],
    message: "Passwords do not match",
  });
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>;

/** Mirrors app/modules/users/schemas.py's ProfileUpdate. Blank strings are treated as "clear the field". */
const optionalUrl = z
  .string()
  .trim()
  .max(300, "Keep it under 300 characters")
  .refine((value) => value === "" || /^https?:\/\/.+/i.test(value), "Must be an http(s) URL");

export const profileSchema = z.object({
  bio: z.string().max(500, "Keep it under 500 characters"),
  country: z
    .string()
    .trim()
    .refine((value) => value === "" || /^[A-Za-z]{2}$/.test(value), "Use a two-letter country code, e.g. US"),
  website: optionalUrl,
  github_url: optionalUrl,
  avatar_url: optionalUrl,
});
export type ProfileValues = z.infer<typeof profileSchema>;
