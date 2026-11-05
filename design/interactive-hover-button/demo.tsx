"use client";

/**
 * InteractiveHoverButton 的用法示例：响应式容器 + 可定制 props。
 *
 * 直接复制到 v0 / Lovable / Bolt / Cursor 里都能跑；需要的只有
 * `interactive-hover-button.tsx`、`@/lib/utils` 的 cn() 和 lucide-react。
 */

import * as React from "react";
import { ShoppingCart } from "lucide-react";

import { InteractiveHoverButton } from "./interactive-hover-button";

export function InteractiveHoverButtonDemo() {
  const [lastClicked, setLastClicked] = React.useState<string | null>(null);

  return (
    // 响应式容器：手机上堆叠、平板起并排，最大宽度跟着断点走
    <section className="mx-auto w-full max-w-3xl px-6 py-16">
      <div className="mb-8 space-y-2 text-center">
        <h2 className="text-2xl font-semibold tracking-tight">选择你的下一步</h2>
        <p className="text-sm text-muted-foreground">
          悬停或键盘聚焦任意按钮，圆点会铺满整颗按钮并滑出箭头。
        </p>
      </div>

      {/* 1 列 → 2 列 → 3 列，gap 随断点收紧 */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
        <InteractiveHoverButton
          className="w-full sm:w-auto"
          onClick={() => setLastClicked("开始分析")}
        >
          开始分析
        </InteractiveHoverButton>

        <InteractiveHoverButton
          className="w-full sm:w-auto"
          onClick={() => setLastClicked("查看商品")}
        >
          查看商品
        </InteractiveHoverButton>

        {/* 换图标：任何 Lucide 图标都能塞进来 */}
        <InteractiveHoverButton
          className="w-full sm:w-auto"
          icon={<ShoppingCart className="size-4" />}
          onClick={() => setLastClicked("加入对比")}
        >
          加入对比
        </InteractiveHoverButton>

        {/* 传 icon={null} 只保留文字 + 填充动效 */}
        <InteractiveHoverButton
          className="w-full sm:w-auto"
          icon={null}
          onClick={() => setLastClicked("了解更多")}
        >
          了解更多
        </InteractiveHoverButton>

        {/* 禁用态：动效关闭、透明度降低 */}
        <InteractiveHoverButton className="w-full sm:w-auto" disabled>
          暂不可用
        </InteractiveHoverButton>

        {/* 自定义尺寸与配色：className 覆盖默认令牌 */}
        <InteractiveHoverButton
          className="w-full border-primary/40 bg-primary/10 px-8 text-primary sm:w-auto"
          onClick={() => setLastClicked("立即咨询")}
        >
          立即咨询
        </InteractiveHoverButton>
      </div>

      {lastClicked && (
        <p className="mt-6 text-center text-sm text-muted-foreground">
          上一次点击：{lastClicked}
        </p>
      )}
    </section>
  );
}

export default InteractiveHoverButtonDemo;
