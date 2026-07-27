import { cn } from "@/lib/utils";
import { forwardRef } from "react";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "destructive" | "outline";
  size?: "xs" | "sm" | "md" | "lg";
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ children, className, variant = "primary", size = "md", loading, disabled, ...props }, ref) => {
    const variants = {
      primary:
        "bg-emerald-500 text-white hover:bg-emerald-400 shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30",
      secondary:
        "bg-white/[0.05] text-gray-200 border border-white/[0.1] hover:bg-white/[0.08] hover:border-white/[0.15]",
      ghost:
        "text-gray-400 hover:text-gray-200 hover:bg-white/[0.05]",
      destructive:
        "bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 hover:border-red-500/30",
      outline:
        "border border-white/[0.1] text-gray-300 hover:bg-white/[0.05] hover:border-white/[0.2]",
    };

    const sizes = {
      xs: "h-7 px-2.5 text-[11px] rounded-md gap-1",
      sm: "h-8 px-3 text-xs rounded-lg gap-1.5",
      md: "h-9 px-4 text-sm rounded-lg gap-2",
      lg: "h-11 px-6 text-sm rounded-lg gap-2",
    };

    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          "inline-flex items-center justify-center font-medium transition-all duration-200",
          "disabled:opacity-40 disabled:pointer-events-none",
          "active:scale-[0.98]",
          variants[variant],
          sizes[size],
          className
        )}
        {...props}
      >
        {loading && (
          <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        )}
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";
