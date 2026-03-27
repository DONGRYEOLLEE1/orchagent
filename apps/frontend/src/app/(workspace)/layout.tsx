import type { ReactNode } from 'react';

import WorkspaceRouteRoot from '@/components/workspace/WorkspaceRouteRoot';

export default function WorkspaceLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <>
      <WorkspaceRouteRoot />
      {children}
    </>
  );
}
