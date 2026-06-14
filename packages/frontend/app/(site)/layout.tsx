import { LenisProvider } from "@/components/providers/lenis-provider";

export default function Layout(props: { children: React.ReactNode }) {
  return <LenisProvider>{props.children}</LenisProvider>;
}
