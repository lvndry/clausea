import AsymmetricGrid from "@/components/clausea/AsymmetricGrid";
import ComplexityToClarity from "@/components/clausea/ComplexityToClarity";
import GSAPInit from "@/components/clausea/GSAPInit";
import { Header } from "@/components/clausea/Header";
import Hero from "@/components/clausea/Hero";
import { Footer, Pricing } from "@/components/clausea/PricingAndFooter";
import { apiEndpoints } from "@lib/config";

// Live count of analyzed products for the hero. Returns null on failure so the
// hero omits the stat rather than showing a stale or fabricated number.
async function getAnalyzedCount(): Promise<number | null> {
  try {
    const res = await fetch(apiEndpoints.productStats(), {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { analyzed_count?: number };
    return typeof data.analyzed_count === "number" ? data.analyzed_count : null;
  } catch {
    return null;
  }
}

export default async function LandingPage() {
  const analyzedCount = await getAnalyzedCount();
  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-foreground selection:text-background w-full overflow-x-hidden overflow-y-visible">
      <GSAPInit />
      <div className="grid grid-cols-12 max-w-[1600px] mx-auto border-x border-border min-h-screen overflow-visible">
        <Header />
        <main className="col-span-12 flex flex-col w-full pb-8 overflow-visible">
          <Hero analyzedCount={analyzedCount} />
          <ComplexityToClarity />
          <AsymmetricGrid />
          <Pricing />
        </main>
        <Footer />
      </div>
    </div>
  );
}
