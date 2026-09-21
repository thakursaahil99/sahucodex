"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { Field } from "@/components/auth/field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { isApiError } from "@/lib/api/http";
import { updateProfile } from "@/lib/api/hooks";
import { useAuthStore } from "@/lib/auth/store";
import { profileSchema, type ProfileValues } from "@/lib/validation";

export function SettingsForm() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const queryClient = useQueryClient();
  const {
    register,
    handleSubmit,
    formState: { errors, isDirty },
  } = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    values: user
      ? {
          bio: user.profile.bio ?? "",
          country: user.profile.country ?? "",
          website: user.profile.website ?? "",
          github_url: user.profile.github_url ?? "",
          avatar_url: user.profile.avatar_url ?? "",
        }
      : undefined,
  });

  const save = useMutation({
    mutationFn: (values: ProfileValues) =>
      updateProfile({
        bio: values.bio.trim() || null,
        country: values.country.trim() || null,
        website: values.website.trim() || null,
        github_url: values.github_url.trim() || null,
        avatar_url: values.avatar_url.trim() || null,
      }),
    onSuccess: async (updated) => {
      setUser(updated);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["profile", updated.username] }),
        queryClient.invalidateQueries({ queryKey: ["profile-stats", updated.username] }),
      ]);
      toast.success("Settings saved");
    },
    onError: (error) => {
      toast.error("Couldn't save your settings", { description: isApiError(error) ? error.message : undefined });
    },
  });

  if (!user) return null;

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 text-muted-foreground">
          Update how your profile looks at{" "}
          <span className="font-mono text-foreground">/profile/{user.username}</span>.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>Anyone can see this — it is never used for sign-in.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit((values) => save.mutate(values))} className="space-y-4" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="bio">Bio</Label>
              <Textarea
                id="bio"
                rows={3}
                maxLength={500}
                aria-invalid={errors.bio ? true : undefined}
                {...register("bio")}
              />
              {errors.bio && <p className="text-xs font-medium text-destructive">{errors.bio.message}</p>}
            </div>
            <Field
              label="Country code"
              placeholder="US"
              maxLength={2}
              error={errors.country?.message}
              hint="Two letters, e.g. US, IN, GB"
              {...register("country")}
            />
            <Field
              label="Website"
              placeholder="https://example.com"
              error={errors.website?.message}
              {...register("website")}
            />
            <Field
              label="GitHub URL"
              placeholder="https://github.com/you"
              error={errors.github_url?.message}
              {...register("github_url")}
            />
            <Field
              label="Avatar URL"
              placeholder="https://…"
              hint="A direct link to an image. There is no upload yet."
              error={errors.avatar_url?.message}
              {...register("avatar_url")}
            />
            <Button type="submit" variant="gradient" loading={save.isPending} disabled={!isDirty}>
              Save changes
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
