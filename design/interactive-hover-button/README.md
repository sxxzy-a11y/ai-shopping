# Interactive Hover Button

magicui / `user_magicui` 风格的悬停按钮：一枚 `primary` 圆点从左侧膨胀铺满整颗按钮，旧标签滑走淡出，新一层「标签 + ArrowRight」从右侧滑入。

```bash
# 官方 registry 安装
npx shadcn@latest add https://motionsites.org/r/user_magicui/interactive-hover-button.json
```

本目录是可直接复制进 v0 / Lovable / Bolt / Cursor 的版本：

| 文件 | 用途 |
|---|---|
| `interactive-hover-button.tsx` | 组件本体（无副作用，`"use client"`） |
| `demo.tsx` | 响应式容器 + 各种 props 组合的用法示例 |

依赖：`tailwindcss`、`lucide-react`、`@/lib/utils` 里的 `cn()`（`clsx` + `tailwind-merge`）。
颜色只用 shadcn/ui 的语义令牌（`bg-background`、`bg-primary`、`text-primary-foreground`、`border`、`ring`），明暗主题自动跟随。

## Props

| 名称 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `children` | `React.ReactNode` | — | 按钮文字，会被渲染两层（静止层 + 悬停层） |
| `icon` | `React.ReactNode \| null` | `<ArrowRight />` | 悬停层右侧图标；传 `null` 隐藏 |
| `className` | `string` | — | 合并到根节点，可覆写尺寸、圆角、配色 |
| `...props` | `ButtonHTMLAttributes` | — | `onClick`、`disabled`、`type`、`aria-*` 等透传 |

响应式交给外层容器（`grid` / `flex` + 断点），组件本身是 `inline-flex`、宽度由 `className` 的 `w-full` / `w-auto` 决定。

## 在没有 React 的界面里复用同一套动效

本项目主站是 Streamlit（`app.py`），没有 React 运行时，所以同一套交互用 CSS 落地了一份等价实现：

- `src/ui/hover_button.py` —— `hover_button(label, key=..., variant=...)`，key 自动加 `zg-hover-` 前缀；
- `src/ui/backend_theme.py` 里「悬停按钮」一节 —— `::before` 是那枚圆点（`scale(160)` 铺满），`::after` 是 Lucide ArrowRight 的 mask 箭头。

差异只有一处：Streamlit 按钮只有一层标签，无法像 React 版那样叠第二层文字，所以文字不滑走，而是换成深色、向左让出箭头的宽度，圆点膨胀与箭头滑入的节奏一致。
