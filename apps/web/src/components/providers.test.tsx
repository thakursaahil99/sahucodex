import { render, screen, waitFor } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";

import { Providers } from "@/components/providers";
import { useAuthStore } from "@/lib/auth/store";
import { sampleUser } from "@/test-utils";

beforeAll(() => {
  // next-themes reads the OS colour scheme, which jsdom does not implement.
  window.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
    onchange: null,
  })) as typeof window.matchMedia;
});

beforeEach(() => {
  document.cookie = "sahucodex_session=; Max-Age=0; path=/";
  useAuthStore.setState({ status: "loading", accessToken: null, expiresAt: null, user: null });
});

function Slow({ value }: { value: string }) {
  const { data, isPending } = useQuery({
    queryKey: ["slow", value],
    queryFn: async () => {
      await new Promise((resolve) => setTimeout(resolve, 60));
      return value;
    },
  });
  return <p>{isPending ? "loading" : `loaded:${data}`}</p>;
}

describe("session manager and the query cache", () => {
  it("does not orphan queries a public page started while the visitor's auth state was still resolving", async () => {
    // A visitor (no session hint cookie) goes loading -> anonymous immediately after the first render.
    render(
      <Providers>
        <Slow value="problems" />
      </Providers>,
    );
    await waitFor(() => expect(screen.getByText("loaded:problems")).toBeInTheDocument());
    expect(useAuthStore.getState().status).toBe("anonymous");
  });

  it("keeps public data working after a sign-out (queries refetch instead of hanging)", async () => {
    useAuthStore.setState({ status: "authenticated", accessToken: "t", user: sampleUser, expiresAt: Date.now() + 900_000 });
    render(
      <Providers>
        <Slow value="after-logout" />
      </Providers>,
    );
    await waitFor(() => expect(screen.getByText("loaded:after-logout")).toBeInTheDocument());

    useAuthStore.getState().clear(); // signing out while a public page is open
    await waitFor(() => expect(screen.getByText("loaded:after-logout")).toBeInTheDocument());
  });
});
