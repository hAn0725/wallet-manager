import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "小账本 · 本地个人记账",
  description: "简单、私密、只属于你的本地个人财务管理工具",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
