import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="space-y-12">
      <div className="space-y-4">
        <Skeleton className="h-10 w-64 rounded-none" />
        <Skeleton className="h-4 w-full max-w-2xl rounded-none" />
      </div>
      <Skeleton className="h-16 w-full rounded-none" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} className="h-64 rounded-none" />
        ))}
      </div>
    </div>
  );
}
