import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsForm } from "@/components/settings/settings-form";
import { useAuthStore } from "@/lib/auth/store";
import { sampleUser } from "@/test-utils";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const updateProfile = vi.fn();
vi.mock("@/lib/api/hooks", () => ({ updateProfile: (...args: unknown[]) => updateProfile(...args) }));

let queryClient: QueryClient;

function renderForm() {
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsForm />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  updateProfile.mockReset();
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  useAuthStore.setState({ status: "authenticated", accessToken: "t", user: sampleUser, expiresAt: Date.now() + 900_000 });
});

describe("SettingsForm", () => {
  it("renders nothing before the signed-in user is known", () => {
    useAuthStore.setState({ status: "loading", accessToken: null, user: null, expiresAt: null });
    const { container } = renderForm();
    expect(container).toBeEmptyDOMElement();
  });

  it("pre-fills the form from the current profile", () => {
    useAuthStore.setState({
      user: { ...sampleUser, profile: { ...sampleUser.profile, bio: "Hello", country: "IN", website: "https://ada.dev" } },
    });
    renderForm();
    expect(screen.getByLabelText("Bio")).toHaveValue("Hello");
    expect(screen.getByLabelText("Country code")).toHaveValue("IN");
    expect(screen.getByLabelText("Website")).toHaveValue("https://ada.dev");
  });

  it("disables Save until something changes", async () => {
    renderForm();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Bio"), "New bio");
    expect(screen.getByRole("button", { name: "Save changes" })).not.toBeDisabled();
  });

  it("shows a validation error for a bad website and does not submit", async () => {
    updateProfile.mockResolvedValue(sampleUser);
    renderForm();
    await userEvent.type(screen.getByLabelText("Website"), "javascript:alert(1)");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Must be an http(s) URL")).toBeInTheDocument();
    expect(updateProfile).not.toHaveBeenCalled();
  });

  it("saves, trimming blanks to null, updates the store and invalidates the profile caches", async () => {
    const updated = { ...sampleUser, profile: { ...sampleUser.profile, bio: "Updated" } };
    updateProfile.mockResolvedValue(updated);
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    renderForm();

    const bio = screen.getByLabelText("Bio");
    await userEvent.clear(bio);
    await userEvent.type(bio, "  Updated  ");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    const { toast } = await import("sonner");
    expect(await screen.findByRole("button", { name: "Save changes" })).toBeDisabled(); // clean again after save
    expect(updateProfile).toHaveBeenCalledWith({
      bio: "Updated",
      country: null,
      website: null,
      github_url: null,
      avatar_url: null,
    });
    expect(toast.success).toHaveBeenCalledWith("Settings saved");
    expect(useAuthStore.getState().user).toEqual(updated);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["profile", updated.username] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["profile-stats", updated.username] });
  });

  it("shows an error toast when saving fails", async () => {
    updateProfile.mockRejectedValue(new Error("network down"));
    renderForm();
    await userEvent.type(screen.getByLabelText("Bio"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    const { toast } = await import("sonner");
    await vi.waitFor(() => expect(toast.error).toHaveBeenCalledWith("Couldn't save your settings", expect.anything()));
  });
});
