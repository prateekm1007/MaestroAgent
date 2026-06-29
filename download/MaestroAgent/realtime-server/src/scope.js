// scope.js — Maestro's hierarchical execution context.
//
// THE INSIGHT:
//   Learning should be HIERARCHICAL, not global.
//
//   Global Laws          — "Requirements should precede implementation."
//     ↓
//   Industry Laws        — "Healthcare: compliance review before release."
//     ↓
//   Company Playbooks    — "Acme: security review before legal."
//     ↓
//   Department Patterns  — "Platform team: RFCs before coding."
//     ↓
//   Team Preferences     — "Backend team: prefers async over sync APIs."
//     ↓
//   Individual Prefs     — "Sarah likes architecture diagrams before PRDs."
//
// This hierarchy lets the same engine adapt from a solo founder to a
// Fortune 100 company without changing its core architecture.
//
// Every Learning Object and Execution Pattern is scoped. Retrieval
// cascades up the hierarchy — your individual preferences override
// team patterns, which override company playbooks, which override
// global laws.
//
// Scope shape:
//   {
//     organization: 'acme-corp',      // null = no org (solo user)
//     industry: 'technology',          // derived from org or explicit
//     department: 'engineering',       // null = no department
//     team: 'platform',                // null = no team
//     userId: 'user-123',              // always set
//   }

const DEFAULT_SCOPE = {
  organization: null,
  industry: null,
  department: null,
  team: null,
  userId: 'default-user',
};

// In-memory current scope. In production this would come from auth/session.
let currentScope = { ...DEFAULT_SCOPE };

export function getCurrentScope() {
  return { ...currentScope };
}

export function setCurrentScope(scope = {}) {
  currentScope = { ...DEFAULT_SCOPE, ...scope };
  console.log('[scope] set:', JSON.stringify(currentScope));
  return currentScope;
}

// Compute the scope hierarchy for retrieval.
// Returns an ordered list from most specific (individual) to least
// specific (global). Retrieval cascades through these levels.
//
// Example output:
//   [
//     { level: 'individual',  org: 'acme', industry: 'tech', dept: 'eng', team: 'platform', user: 'user-123' },
//     { level: 'team',        org: 'acme', industry: 'tech', dept: 'eng', team: 'platform' },
//     { level: 'department',  org: 'acme', industry: 'tech', dept: 'eng' },
//     { level: 'company',     org: 'acme', industry: 'tech' },
//     { level: 'industry',    industry: 'tech' },
//     { level: 'global' },
//   ]
export function getScopeHierarchy(scope = currentScope) {
  const levels = [];

  // Individual (most specific)
  if (scope.userId) {
    levels.push({
      level: 'individual',
      organization: scope.organization,
      industry: scope.industry,
      department: scope.department,
      team: scope.team,
      userId: scope.userId,
    });
  }

  // Team
  if (scope.team) {
    levels.push({
      level: 'team',
      organization: scope.organization,
      industry: scope.industry,
      department: scope.department,
      team: scope.team,
    });
  }

  // Department
  if (scope.department) {
    levels.push({
      level: 'department',
      organization: scope.organization,
      industry: scope.industry,
      department: scope.department,
    });
  }

  // Company
  if (scope.organization) {
    levels.push({
      level: 'company',
      organization: scope.organization,
      industry: scope.industry,
    });
  }

  // Industry
  if (scope.industry) {
    levels.push({
      level: 'industry',
      industry: scope.industry,
    });
  }

  // Global (least specific)
  levels.push({ level: 'global' });

  return levels;
}

// Compute a scope key for storage. Objects with the same scope key
// are in the same "bucket." This is how we partition Learning Objects
// and Patterns by scope.
//
// Example: "org:acme|dept:eng|team:platform"
//          "global"
//          "industry:tech"
export function scopeKey(scope) {
  if (!scope || scope.level === 'global') return 'global';
  const parts = [];
  if (scope.industry) parts.push('industry:' + scope.industry);
  if (scope.organization) parts.push('org:' + scope.organization);
  if (scope.department) parts.push('dept:' + scope.department);
  if (scope.team) parts.push('team:' + scope.team);
  if (scope.userId) parts.push('user:' + scope.userId);
  return parts.join('|') || 'global';
}

// Format the scope hierarchy for the conductor's context.
// This tells the conductor WHICH level of knowledge it's drawing from.
export function formatScopeContext(scope = currentScope) {
  const levels = getScopeHierarchy(scope);
  const active = levels.filter(l => l.level !== 'global');
  if (active.length === 0) return '';
  const parts = active.map(l => {
    switch (l.level) {
      case 'individual': return `Individual (${l.userId})`;
      case 'team': return `Team ${l.team}`;
      case 'department': return `Department ${l.department}`;
      case 'company': return `Company ${l.organization}`;
      case 'industry': return `Industry ${l.industry}`;
      default: return '';
    }
  });
  return `Execution context: ${parts.join(' → ')}`;
}
