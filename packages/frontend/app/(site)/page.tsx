import AsymmetricGrid from "@/components/clausea/AsymmetricGrid";
import ComplexityToClarity from "@/components/clausea/ComplexityToClarity";
import GSAPInit from "@/components/clausea/GSAPInit";
import { Header } from "@/components/clausea/Header";
import Hero from "@/components/clausea/Hero";
import { Footer, Pricing } from "@/components/clausea/PricingAndFooter";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-primary/20 w-full overflow-hidden">
      <GSAPInit />
      <Header />
      <main className="flex-1 w-full">
        <Hero />
        <ComplexityToClarity />
        <AsymmetricGrid />
        <Pricing />
      </main>
      <Footer />
    </div>
  );
}
