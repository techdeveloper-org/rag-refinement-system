/** Shape of the skeleton placeholder to render. */
export type SkeletonVariant = "card-grid" | "bar" | "bubble";

interface LoadingSkeletonProps {
  variant: SkeletonVariant;
}

/** A single shimmering placeholder block. */
function Shimmer({ className }: { className: string }): JSX.Element {
  return <div className={`animate-pulse rounded-md bg-surface-alt ${className}`} />;
}

/**
 * LoadingSkeleton. Placeholder shown while data loads. Exposes `aria-busy` and a
 * polite live region so the loading state is announced without focus movement.
 *
 * @param variant - Which skeleton layout to render.
 */
export function LoadingSkeleton({ variant }: LoadingSkeletonProps): JSX.Element {
  return (
    <div role="status" aria-busy="true" aria-live="polite" className="w-full">
      <span className="sr-only">Loading…</span>
      {variant === "card-grid" ? (
        <div className="grid grid-cols-1 gap-md sm:grid-cols-2 lg:grid-cols-3">
          <Shimmer className="h-32" />
          <Shimmer className="h-32" />
          <Shimmer className="h-32" />
        </div>
      ) : null}
      {variant === "bar" ? <Shimmer className="h-6 w-full" /> : null}
      {variant === "bubble" ? <Shimmer className="h-20 w-3/4" /> : null}
    </div>
  );
}
