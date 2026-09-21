import type { ReactNode } from "react";

import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";

interface AuthCardProps {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function AuthCard({ title, description, children, footer }: AuthCardProps) {
  return (
    <div className="w-full max-w-md">
      <Card className="border-border/80 bg-card/90 shadow-xl backdrop-blur">
        <CardHeader className="space-y-2 pb-4 text-center">
          <h1 className="text-2xl leading-none font-semibold tracking-tight">{title}</h1>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
      {footer && <p className="mt-6 text-center text-sm text-muted-foreground">{footer}</p>}
    </div>
  );
}
