"use client";

import {
  Conflicts,
  GoodToKnow,
  RightsByRegion,
  SilentOn,
  WhatYouCanDo,
} from "./action-sections";
import { WhatTheyCollect, WhoGetsYourData } from "./data-sections";
import { GradeHero } from "./grade-hero";
import {
  type ConsumerExplainer,
  resolveRegionVerdicts,
  resolveTlDr,
  resolveWatchOutFor,
} from "./types";
import { WatchOutFor } from "./watch-out-for";

interface ConsumerExplainerViewProps {
  explainer: ConsumerExplainer;
}

export function ConsumerExplainerView({
  explainer,
}: ConsumerExplainerViewProps) {
  const watchOutFor = resolveWatchOutFor(explainer);
  const regionVerdicts = resolveRegionVerdicts(explainer);
  const tlDr = resolveTlDr(explainer);

  return (
    <div className="space-y-6">
      <GradeHero explainer={explainer} tlDr={tlDr} />

      {explainer.the_deal && (
        <div className="border border-border bg-background p-8 md:p-10">
          <span className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground block mb-4">
            The Deal You&apos;re Making
          </span>
          <p className="text-base md:text-lg text-foreground/90 leading-relaxed max-w-3xl font-serif">
            {explainer.the_deal}
          </p>
        </div>
      )}

      <GoodToKnow items={explainer.good_to_know ?? []} />

      <WatchOutFor cases={watchOutFor} />

      <WhatTheyCollect items={explainer.what_they_collect ?? []} />

      <WhoGetsYourData items={explainer.who_gets_your_data ?? []} />

      <RightsByRegion verdicts={regionVerdicts} />

      <WhatYouCanDo items={explainer.what_you_can_do ?? []} />

      <SilentOn items={explainer.silent_on ?? []} />

      <Conflicts
        items={explainer.contradictions ?? explainer.conflicts ?? []}
      />
    </div>
  );
}
