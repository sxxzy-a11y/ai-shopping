"use client";

/**
 * Interactive Hover Button
 * ------------------------
 * Magic UI / user_magicui 风格的悬停按钮：一枚 primary 圆点从左侧膨胀铺满整颗
 * 按钮，旧标签向右滑走并淡出，新一层「标签 + ArrowRight」从右侧滑入。
 *
 * 安装（shadcn registry）：
 *   npx shadcn@latest add https://motionsites.org/r/user_magicui/interactive-hover-button.json
 *
 * 依赖：tailwindcss、lucide-react、class-variance-authority（本文件只用 cn()）。
 * 主题色全部走 shadcn/ui 的 CSS 变量（bg-background / bg-primary /
 * text-primary-foreground / border / ring），所以明暗主题自动跟随，不需要额外配色。
 */

import * as React from "react";
import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";

export interface InteractiveHoverButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** 按钮文字。会被渲染两次（静止层 + 悬停层），不要放交互元素。 */
  children: React.ReactNode;
  /** 箭头图标，默认 Lucide 的 ArrowRight；传 null 可隐藏。 */
  icon?: React.ReactNode | null;
}

export function InteractiveHoverButton({
  children,
  className,
  icon,
  ...props
}: InteractiveHoverButtonProps) {
  const arrow = icon === null ? null : (icon ?? <ArrowRight className="size-4" />);

  return (
    <button
      type="button"
      className={cn(
        // 布局与尺寸
        "group relative inline-flex w-auto cursor-pointer items-center justify-center overflow-hidden rounded-full border p-2 px-6 text-center font-semibold",
        // 主题令牌
        "border-border bg-background text-foreground",
        // 可访问性：键盘聚焦、禁用态
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:pointer-events-none disabled:opacity-50",
        className,
      )}
      {...props}
    >
      {/* 静止层：圆点 + 标签 */}
      <span className="flex items-center justify-center gap-2">
        <span
          aria-hidden="true"
          className="h-2 w-2 shrink-0 rounded-full bg-primary transition-transform duration-500 ease-[cubic-bezier(.3,.9,.3,1)] group-hover:scale-[160] group-focus-visible:scale-[160]"
        />
        <span className="inline-block transition-all duration-300 group-hover:translate-x-12 group-hover:opacity-0 group-focus-visible:translate-x-12 group-focus-visible:opacity-0">
          {children}
        </span>
      </span>

      {/* 悬停层：标签 + 箭头，从右侧滑入 */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-10 flex translate-x-12 items-center justify-center gap-2 text-primary-foreground opacity-0 transition-all duration-300 group-hover:-translate-x-5 group-hover:opacity-100 group-focus-visible:-translate-x-5 group-focus-visible:opacity-100"
      >
        <span>{children}</span>
        {arrow}
      </span>
    </button>
  );
}

export default InteractiveHoverButton;
