import CompanyPage from "./product-page-client";
import { fetchProductPageShell } from "./product-page-server";

export default async function ProductPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { product, overview, explainer } = await fetchProductPageShell(slug);

  return (
    <CompanyPage
      key={slug}
      initialProduct={product}
      initialData={overview}
      initialExplainer={explainer}
    />
  );
}
