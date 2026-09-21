import { PageChrome } from "@/components/layout/page-chrome";

export default function BrowseLayout({ children }: { children: React.ReactNode }) {
  return <PageChrome>{children}</PageChrome>;
}
