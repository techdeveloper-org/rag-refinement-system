interface AppHeaderProps {
  documentTitle?: string;
}

/**
 * AppHeader. Top bar present on all screens. When a document is open its
 * `Document.title` is shown as context. The first Tab target is a "Skip to
 * content" link (GIGW v3.0).
 *
 * @param documentTitle - Active document title, if any.
 */
export function AppHeader({ documentTitle }: AppHeaderProps): JSX.Element {
  return (
    <header className="flex h-16 items-center gap-md border-b border-border bg-surface px-md">
      <a href="#main-content" className="sr-only">
        Skip to content
      </a>
      <span className="text-body font-bold text-text-primary">RAG Refinement</span>
      {documentTitle !== undefined ? (
        <>
          <span aria-hidden="true" className="text-text-secondary">
            |
          </span>
          <span className="text-body-sm text-text-secondary truncate">{documentTitle}</span>
        </>
      ) : null}
    </header>
  );
}
