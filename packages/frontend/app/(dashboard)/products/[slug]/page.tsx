import CompanyPage from "./product-page-client";
import { fetchProductPageData } from "./product-page-server";

export default async function ProductPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { product, overview, explainer, documents, topics } =
    await fetchProductPageData(slug);

  return (
    <CompanyPage
      key={slug}
      initialProduct={product}
      initialData={overview}
      initialExplainer={explainer}
      initialDocuments={documents}
      initialTopics={topics}
    />
  );
}
