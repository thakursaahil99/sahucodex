"use client";

import { useTheme } from "next-themes";
import { Toaster as Sonner, type ToasterProps } from "sonner";

export function Toaster(props: ToasterProps) {
  const { theme = "dark" } = useTheme();
  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast: "!bg-popover !text-popover-foreground !border-border !rounded-xl",
          description: "!text-muted-foreground",
        },
      }}
      {...props}
    />
  );
}
