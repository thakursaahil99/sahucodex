import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NotificationBell } from "@/components/community/notification-bell";
import { useAuthStore } from "@/lib/auth/store";
import { sampleUser } from "@/test-utils";

function renderBell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <NotificationBell />
    </QueryClientProvider>,
  );
}

const useNotifications = vi.fn();
const useUnreadCount = vi.fn();

vi.mock("@/lib/community/api", () => ({
  useNotifications: (...args: unknown[]) => useNotifications(...args),
  useUnreadCount: (...args: unknown[]) => useUnreadCount(...args),
  markAllNotificationsRead: vi.fn(),
  markNotificationRead: vi.fn(),
}));

beforeEach(() => {
  useNotifications.mockReset().mockReturnValue({ data: [] });
  useUnreadCount.mockReset().mockReturnValue({ data: { count: 0 } });
  useAuthStore.setState({ status: "anonymous", accessToken: null, user: null, expiresAt: null });
});

describe("NotificationBell", () => {
  // Regression: both hooks used to run unconditionally, which fired an authenticated-only /notifications
  // request (and the session-refresh attempt behind it) on every anonymous page view.
  it("never queries notifications for a signed-out viewer", () => {
    const { container } = renderBell();
    expect(container).toBeEmptyDOMElement();
    expect(useNotifications).toHaveBeenCalledWith(false, false);
    expect(useUnreadCount).toHaveBeenCalledWith(false);
  });

  it("queries notifications once a viewer is signed in", () => {
    useAuthStore.setState({
      status: "authenticated",
      accessToken: "t",
      user: sampleUser,
      expiresAt: Date.now() + 900_000,
    });
    renderBell();
    expect(useNotifications).toHaveBeenCalledWith(false, true);
    expect(useUnreadCount).toHaveBeenCalledWith(true);
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });
});
