import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";
import { ContentFrame } from "./content-frame";

export function AppShell({
  children,
  title,
}: {
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <div className="flex h-screen overflow-hidden bg-surface">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar title={title} />
        <ContentFrame>{children}</ContentFrame>
      </div>
    </div>
  );
}
