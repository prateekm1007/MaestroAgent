// components/ui/markdown-renderer.tsx — Safe markdown rendering using react-markdown.
// P0-6 FIX: Replaces dangerouslySetInnerHTML with safe component-based rendering.

'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { memo } from 'react';

export const MarkdownRenderer = memo(function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code: ({ children, className }) => {
            const isBlock = className?.includes('language-');
            if (isBlock) {
              return (
                <pre className="bg-ink-950 border border-white/10 rounded-lg p-3 overflow-x-auto my-2">
                  <code className="font-mono text-xs text-brand-cyan">{children}</code>
                </pre>
              );
            }
            return <code className="bg-brand-purple/15 text-[#a594ff] px-1.5 py-0.5 rounded text-xs font-mono">{children}</code>;
          },
          pre: ({ children }) => <>{children}</>, // pre handled by code component above
          h1: ({ children }) => <h2 className="text-lg font-bold text-fg-100 mt-3 mb-2">{children}</h2>,
          h2: ({ children }) => <h3 className="text-base font-bold text-fg-100 mt-3 mb-1">{children}</h3>,
          h3: ({ children }) => <h4 className="text-sm font-bold text-fg-100 mt-2 mb-1">{children}</h4>,
          strong: ({ children }) => <strong className="text-fg-100 font-semibold">{children}</strong>,
          p: ({ children }) => <p className="text-sm text-fg-300 leading-relaxed my-1">{children}</p>,
          ul: ({ children }) => <ul className="text-sm text-fg-300 list-disc list-inside my-1 space-y-0.5">{children}</ul>,
          ol: ({ children }) => <ol className="text-sm text-fg-300 list-decimal list-inside my-1 space-y-0.5">{children}</ol>,
          a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand-purple hover:underline">{children}</a>,
          blockquote: ({ children }) => <blockquote className="border-l-2 border-brand-purple/30 pl-3 text-fg-400 italic my-1">{children}</blockquote>,
          table: ({ children }) => <table className="w-full text-sm my-2 border-collapse">{children}</table>,
          th: ({ children }) => <th className="border border-white/10 px-2 py-1 text-left text-fg-100 font-semibold bg-white/[0.02]">{children}</th>,
          td: ({ children }) => <td className="border border-white/10 px-2 py-1 text-fg-300">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
