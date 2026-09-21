import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/login-form";
import { RegisterForm } from "@/components/auth/register-form";
import { useAuthStore } from "@/lib/auth/store";
import { apiError, jsonResponse, mockFetch, sampleUser, tokenBody } from "@/test-utils";

const replace = vi.fn();
let nextParam: string | null = null;

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(nextParam ? { next: nextParam } : {}),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

beforeEach(() => {
  replace.mockReset();
  nextParam = null;
  useAuthStore.setState({ status: "anonymous", accessToken: null, expiresAt: null, user: null });
});
afterEach(() => vi.unstubAllGlobals());

describe("LoginForm", () => {
  it("shows accessible validation messages and does not call the API for empty input", async () => {
    const fetchMock = mockFetch();
    render(<LoginForm />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const identifier = await screen.findByLabelText("Email or username");
    expect(identifier).toHaveAttribute("aria-invalid", "true");
    expect(identifier).toHaveAccessibleDescription("Enter your email or username");
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("signs in and redirects to the dashboard by default", async () => {
    mockFetch().mockResolvedValue(jsonResponse(200, tokenBody()));
    render(<LoginForm />);

    await userEvent.type(screen.getByLabelText("Email or username"), "ada");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    expect(useAuthStore.getState().user?.username).toBe(sampleUser.username);
  });

  it("follows a safe ?next= target but ignores an off-site one", async () => {
    mockFetch().mockResolvedValue(jsonResponse(200, tokenBody()));
    nextParam = "https://evil.example/steal";
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText("Email or username"), "ada");
    await userEvent.type(screen.getByLabelText("Password"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
  });

  it("announces bad credentials in an alert without revealing which field was wrong", async () => {
    mockFetch().mockResolvedValue(apiError(401, "INVALID_CREDENTIALS"));
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText("Email or username"), "ada");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/don't match/i);
    expect(replace).not.toHaveBeenCalled();
  });

  it("tells the user how long to wait when rate limited", async () => {
    mockFetch().mockResolvedValue(apiError(429, "RATE_LIMITED", "Too many", { "Retry-After": "30" }));
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText("Email or username"), "ada");
    await userEvent.type(screen.getByLabelText("Password"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("30 seconds");
  });

  it("toggles password visibility with an accessible button", async () => {
    render(<LoginForm />);
    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");

    await userEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("RegisterForm", () => {
  async function fill(email: string, username: string, password: string) {
    await userEvent.type(screen.getByLabelText("Email"), email);
    await userEvent.type(screen.getByLabelText("Username"), username);
    await userEvent.type(screen.getByLabelText("Password"), password);
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
  }

  it("validates locally before hitting the API", async () => {
    const fetchMock = mockFetch();
    render(<RegisterForm />);
    await fill("not-an-email", "a", "short");

    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(screen.getByText(/3–30 characters/, { selector: "p.text-destructive" })).toBeInTheDocument();
    expect(screen.getByText("Use at least 10 characters")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("creates the account, signs in and goes to the dashboard", async () => {
    mockFetch()
      .mockResolvedValueOnce(jsonResponse(201, { user: sampleUser }))
      .mockResolvedValueOnce(jsonResponse(200, tokenBody()));
    render(<RegisterForm />);
    await fill("ada@example.com", "ada", "correct-horse-battery");

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
  });

  it("attaches a server-side EMAIL_TAKEN error to the email field", async () => {
    mockFetch().mockResolvedValue(apiError(409, "EMAIL_TAKEN", "An account with that email already exists"));
    render(<RegisterForm />);
    await fill("ada@example.com", "ada", "correct-horse-battery");

    const email = await screen.findByLabelText("Email");
    await waitFor(() => expect(email).toHaveAccessibleDescription("An account with that email already exists"));
    expect(replace).not.toHaveBeenCalled();
  });
});
