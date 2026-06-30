// app/dashboard/layout.tsx — Dashboard layout with sidebar.

import { DashboardLayout } from '@/components/layout/dashboard-layout';

export default function DashboardRootLayout({ children }: { children: React.ReactNode }) {
  return <DashboardLayout>{children}</DashboardLayout>;
}
