import { cn } from "@/lib/utils";

interface ProfileAvatarProps {
  username: string;
  avatarUrl: string | null;
  className?: string;
}

/** An image if the profile has one, otherwise the same gradient-initial circle used in the account menu. */
export function ProfileAvatar({ username, avatarUrl, className }: ProfileAvatarProps) {
  if (avatarUrl) {
    return (
      // An arbitrary external host chosen by the user — next/image can't optimise an unconfigured domain, and
      // pre-registering every possible host isn't practical, so this is a plain <img>.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={avatarUrl}
        alt=""
        className={cn("size-16 rounded-full object-cover", className)}
        referrerPolicy="no-referrer"
      />
    );
  }
  return (
    <span
      aria-hidden
      className={cn(
        "bg-brand-gradient flex size-16 items-center justify-center rounded-full text-2xl font-semibold text-white",
        className,
      )}
    >
      {username.slice(0, 1).toUpperCase()}
    </span>
  );
}
