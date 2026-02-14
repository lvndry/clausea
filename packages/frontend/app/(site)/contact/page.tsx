"use client";

import * as z from "zod";
import { Mail, MapPin, Send } from "lucide-react";
import posthog from "posthog-js";
import { useForm } from "react-hook-form";

import { Header } from "@/components/clausea/Header";
import { Footer } from "@/components/clausea/PricingAndFooter";
import { Button } from "@/components/ui/button";
import { zodResolver } from "@hookform/resolvers/zod";

const contactSchema = z.object({
  name: z.string().min(2, "Name is too short"),
  email: z.email("Invalid email address"),
  company: z.string().optional(),
  message: z.string().min(10, "Message must be at least 10 characters"),
});

type ContactFormValues = z.infer<typeof contactSchema>;

export default function ContactPage() {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ContactFormValues>({
    resolver: zodResolver(contactSchema),
  });

  const onSubmit = async (data: ContactFormValues) => {
    // Track contact form submission
    posthog.capture("contact_form_submitted", {
      has_company: !!data.company,
      message_length: data.message.length,
      email_domain: data.email.split("@")[1],
    });

    // Simulate API call
    await new Promise((resolve) => setTimeout(resolve, 1500));
    alert("Message sent! We'll get back to you soon.");
  };

  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-secondary/30 w-full overflow-hidden">
      <Header />

      <main className="pt-32 pb-24 px-4 md:px-8">
        <div className="max-w-7xl mx-auto flex flex-col lg:flex-row gap-20">
          {/* Info Side */}
          <div className="flex-1 space-y-12">
            <div>
              <h1 className="text-5xl md:text-7xl font-display font-bold text-primary mb-8">
                Let&apos;s talk <br />
                <span className="text-secondary italic">Clarity.</span>
              </h1>
              <p className="text-xl text-muted-foreground leading-relaxed max-w-lg">
                Have questions about our enterprise features? Want to share
                feedback? Our team is here to assist.
              </p>
            </div>

            <div className="space-y-8">
              <div className="flex items-center gap-4 group">
                <div className="w-12 h-12 rounded-2xl bg-secondary/10 text-secondary flex items-center justify-center group-hover:scale-110 transition-transform">
                  <Mail className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-xs font-bold uppercase tracking-widest text-primary/40">
                    Email Us
                  </p>
                  <p className="text-lg font-bold text-primary">
                    contact@clausea.co
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-4 group">
                <div className="w-12 h-12 rounded-2xl bg-secondary/10 text-secondary flex items-center justify-center group-hover:scale-110 transition-transform">
                  <MapPin className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-xs font-bold uppercase tracking-widest text-primary/40">
                    Headquarters
                  </p>
                  <p className="text-lg font-bold text-primary">
                    Paris, France
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Form Side */}
          <div className="flex-1 bg-white p-8 md:p-12 rounded-[2.5rem] border border-primary/5 shadow-2xl">
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <label className="text-xs font-bold uppercase tracking-widest text-primary/60 px-4">
                    Full Name
                  </label>
                  <input
                    {...register("name")}
                    placeholder="John Doe"
                    className="w-full h-14 bg-neutral rounded-2xl px-6 outline-none focus:ring-2 ring-secondary/50 transition-all"
                  />
                  {errors.name && (
                    <p className="text-xs text-red-500 px-4">
                      {errors.name.message}
                    </p>
                  )}
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-bold uppercase tracking-widest text-primary/60 px-4">
                    Email Address
                  </label>
                  <input
                    {...register("email")}
                    placeholder="john@example.com"
                    className="w-full h-14 bg-neutral rounded-2xl px-6 outline-none focus:ring-2 ring-secondary/50 transition-all"
                  />
                  {errors.email && (
                    <p className="text-xs text-red-500 px-4">
                      {errors.email.message}
                    </p>
                  )}
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-widest text-primary/60 px-4">
                  Company (Optional)
                </label>
                <input
                  {...register("company")}
                  placeholder="ACME Corp"
                  className="w-full h-14 bg-neutral rounded-2xl px-6 outline-none focus:ring-2 ring-secondary/50 transition-all"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-widest text-primary/60 px-4">
                  Message
                </label>
                <textarea
                  {...register("message")}
                  placeholder="How can we help you?"
                  className="w-full h-40 bg-neutral rounded-2xl p-6 outline-none focus:ring-2 ring-secondary/50 transition-all resize-none"
                />
                {errors.message && (
                  <p className="text-xs text-red-500 px-4">
                    {errors.message.message}
                  </p>
                )}
              </div>

              <Button
                disabled={isSubmitting}
                className="w-full h-16 rounded-full text-lg font-bold uppercase tracking-widest gap-3 shadow-lg group"
              >
                {isSubmitting ? "Sending..." : "Send Message"}
                <Send className="w-5 h-5 group-hover:translate-x-1 group-hover:-translate-y-1 transition-transform" />
              </Button>
            </form>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
