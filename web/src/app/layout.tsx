import type { Metadata } from 'next';
import { Roboto } from 'next/font/google';
import './globals.css';

export const metadata: Metadata = {
  title: 'ST.Real Social Console',
  description: 'Theo dõi bài viết, lọc bình luận và quản lý sale đa kênh',
};

const roboto = Roboto({
  subsets: ['latin', 'vietnamese'],
  weight: ['400', '500', '700', '900'],
  display: 'swap',
  variable: '--font-roboto',
});

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi">
      <body className={roboto.variable}>{children}</body>
    </html>
  );
}
