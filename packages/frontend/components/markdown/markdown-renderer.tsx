"use client";

import Link from "next/link";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownRendererProps {
  children: string;
}

const components: Components = {
  a: ({ href, children }) => (
    <Link
      href={href as string}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-500 underline hover:text-blue-600"
    >
      {children}
    </Link>
  ),
  p: ({ children }) => <p className="mb-3 leading-relaxed">{children}</p>,
  strong: ({ children }) => <strong className="font-bold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => (
    <ul className="list-disc pl-5 mb-3 space-y-1">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal pl-5 mb-3 space-y-1">{children}</ol>
  ),
  li: ({ children }) => <li>{children}</li>,
  h1: ({ children }) => (
    <h1 className="text-3xl font-bold mt-6 mb-4">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-2xl font-bold mt-6 mb-4">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-xl font-bold mt-5 mb-3">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-lg font-bold mt-4 mb-2">{children}</h4>
  ),
  h5: ({ children }) => (
    <h5 className="text-base font-bold mt-4 mb-2">{children}</h5>
  ),
  h6: ({ children }) => (
    <h6 className="text-sm font-bold mt-4 mb-2 text-muted-foreground">
      {children}
    </h6>
  ),
  blockquote: ({ children }) => (
    <blockquote className="pl-4 border-l-4 border-gray-300 dark:border-gray-700 text-muted-foreground my-4 italic">
      {children}
    </blockquote>
  ),
  code: ({ className, children, ...props }: any) => {
    const isBlock =
      typeof className === "string" && className.includes("language-");
    if (isBlock) {
      return (
        <pre className="overflow-x-auto p-4 bg-gray-900 text-gray-100 rounded-md mb-4">
          <code className={className} {...props}>
            {children}
          </code>
        </pre>
      );
    }
    return (
      <code
        className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono"
        {...props}
      >
        {children}
      </code>
    );
  },
  table: ({ children }) => (
    <div className="overflow-x-auto mb-4">
      <table className="min-w-full divide-y divide-border text-sm">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted/50">{children}</thead>,
  tbody: ({ children }) => (
    <tbody className="divide-y divide-border bg-background">{children}</tbody>
  ),
  tr: ({ children }) => <tr>{children}</tr>,
  th: ({ children }) => (
    <th className="px-3 py-2 text-left font-medium text-muted-foreground">
      {children}
    </th>
  ),
  td: ({ children }) => <td className="px-3 py-2">{children}</td>,
  hr: () => <hr className="my-6 border-border" />,
};

export function MarkdownRenderer({ children }: MarkdownRendererProps) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </ReactMarkdown>
  );
}

export default MarkdownRenderer;
