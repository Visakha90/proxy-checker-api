import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "success" | "warning" | "error" | "info" | "premium";
  size?: "sm" | "md";
}

export function Badge({ children, variant = "default", size = "sm" }: BadgeProps) {
  const variants = {
    default: "bg-white/[0.06] text-gray-300 border-white/[0.08]",
    success: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    warning: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    error: "bg-red-500/10 text-red-400 border-red-500/20",
    info: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    premium: "bg-violet-500/10 text-violet-400 border-violet-500/20",
  };

  const sizes = {
    sm: "text-[10px] px-1.5 py-0.5",
    md: "text-xs px-2 py-0.5",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center font-medium rounded-md border",
        variants[variant],
        sizes[size]
      )}
    >
      {children}
    </span>
  );
}

export function StatusDot({ alive }: { alive: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={cn(
          "w-1.5 h-1.5 rounded-full",
          alive ? "bg-emerald-400 shadow-sm shadow-emerald-400/50" : "bg-red-400"
        )}
      />
      <span className={cn("text-xs", alive ? "text-emerald-400" : "text-red-400")}>
        {alive ? "Alive" : "Dead"}
      </span>
    </span>
  );
}
