// components/layout/sidebar.tsx — Application sidebar.

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { cn, relativeTime } from '@/lib/utils';
import { LayoutDashboard, Play, Receipt, BarChart3, Settings, Plug, LogOut, Shield } from 'lucide-react';
import { useState, useEffect } from 'react';
import { runs as runsApi } from '@/lib/api';
import type { Run } from '@/types';

const navItems = [
  { href: '/dashboard', label: 'Home', icon: LayoutDashboard },
  { href: '/runs', label: 'Runs', icon: Play },
  { href: '/receipts', label: 'Receipts', icon: Receipt },
  { href: '/metrics', label: 'Metrics', icon: BarChart3 },
  { href: '/integrations', label: 'Integrations', icon: Plug },
  { href: '/settings', label: 'Settings', icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [recentRuns, setRecentRuns] = useState<Run[]>([]);

  useEffect(() => {
    runsApi.list().then(setRecentRuns).catch(() => {});
  }, []);

  return (
    <aside className="w-56 flex-shrink-0 bg-ink-900 border-r border-white/[0.05] flex flex-col h-screen sticky top-0">
      {/* Logo */}
      <div className="h-12 flex items-center gap-2 px-4 border-b border-white/[0.05]">
        <div className="w-7 h-7 rounded-md bg-gradient-to-br from-brand-purple to-brand-cyan flex items-center justify-center text-xs font-black text-white">M</div>
        <span className="font-bold text-sm">Maestro</span>
        <span className="tag tag-gray ml-auto">v1.0</span>
      </div>

      {/* Org switcher */}
      <div className="px-3 py-2.5 border-b border-white/[0.05]">
        <button className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-white/[0.04] text-left">
          <div className="w-6 h-6 rounded bg-gradient-to-br from-brand-purple to-brand-cyan flex items-center justify-center text-[10px] font-bold">
            {user?.org_name?.[0] || 'A'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold truncate">{user?.org_name || 'Workspace'}</div>
            <div className="text-[9px] text-fg-500">{user?.role || 'member'}</div>
          </div>
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-2">
        {navItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
          return (
            <Link key={item.href} href={item.href}
              className={cn('flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-medium transition-all relative',
                isActive ? 'bg-brand-purple/14 text-[#a594ff]' : 'text-fg-400 hover:bg-white/[0.04] hover:text-fg-200')}>
              {isActive && <span className="absolute -left-3 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-brand-purple rounded-r" />}
              <item.icon className="w-4 h-4 flex-shrink-0" />
              {item.label}
            </Link>
          );
        })}

        {/* Recent runs */}
        {recentRuns.length > 0 && (
          <>
            <div className="text-[9px] font-bold text-fg-500 uppercase tracking-wider px-2.5 pt-4 pb-1">Recent</div>
            {recentRuns.slice(0, 4).map((run) => (
              <Link key={run.id} href={`/runs/${run.id}`}
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs text-fg-400 hover:bg-white/[0.04] hover:text-fg-200 transition-all truncate">
                <span className="w-1.5 h-1.5 rounded-full bg-brand-cyan flex-shrink-0" />
                <span className="truncate">{run.goal}</span>
              </Link>
            ))}
          </>
        )}
      </nav>

      {/* User */}
      <div className="px-3 py-2 border-t border-white/[0.05]">
        <div className="flex items-center gap-2 px-2 py-1.5">
          <div className="w-7 h-7 rounded-full bg-brand-purple/20 flex items-center justify-center text-xs font-bold text-[#a594ff]">
            {user?.name?.[0] || user?.email?.[0] || '?'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold truncate">{user?.name || 'User'}</div>
            <div className="text-[9px] text-fg-500 truncate">{user?.email}</div>
          </div>
          <button onClick={logout} className="text-fg-500 hover:text-brand-rose transition-colors" aria-label="Logout">
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
