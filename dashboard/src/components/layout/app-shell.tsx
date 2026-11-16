import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";
import { ContentFrame } from "./content-frame";
import { AppAtmosphere } from "./app-atmosphere";

export function AppShell({
  children,
  title,
}: {
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <div className="app-shell relative flex h-screen overflow-hidden bg-surface">
      <AppAtmosphere />
      <div className="relative z-10 flex min-h-0 min-w-0 flex-1">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col bg-transparent">
          <TopBar title={title} />
          <ContentFrame>{children}</ContentFrame>
        </div>
      </div>
    </div>
  );
}
