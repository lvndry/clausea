import AsymmetricGrid from "@/components/clausea/AsymmetricGrid";
import ComplexityToClarity from "@/components/clausea/ComplexityToClarity";
import GSAPInit from "@/components/clausea/GSAPInit";
import { Header } from "@/components/clausea/Header";
import Hero from "@/components/clausea/Hero";
import { Footer, Pricing } from "@/components/clausea/PricingAndFooter";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-foreground selection:text-background w-full overflow-x-hidden overflow-y-visible">
      <GSAPInit />
      <div className="grid grid-cols-12 max-w-[1600px] mx-auto border-x border-border min-h-screen overflow-visible">
        <Header />
        <main className="col-span-12 flex flex-col w-full pb-8 overflow-visible">
          <Hero />
          <ComplexityToClarity />
          <AsymmetricGrid />
          <Pricing />
        </main>
        <Footer />
      </div>
    </div>
  );
}
