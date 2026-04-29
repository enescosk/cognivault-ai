interface SkeletonProps {
  className?: string
  width?: string
  height?: string
}

export function Skeleton({ className = "", width, height }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse bg-gray-200 dark:bg-gray-700 rounded ${className}`}
      style={{ width, height }}
    />
  )
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} height="1rem" width={i === lines - 1 ? "60%" : "100%"} />
      ))}
    </div>
  )
}

export function SkeletonMessage() {
  return (
    <div className="flex gap-3 p-3">
      <Skeleton width="2rem" height="2rem" className="rounded-full shrink-0" />
      <div className="flex-1 space-y-2">
        <Skeleton height="0.75rem" width="30%" />
        <Skeleton height="1rem" width="80%" />
        <Skeleton height="1rem" width="60%" />
      </div>
    </div>
  )
}
