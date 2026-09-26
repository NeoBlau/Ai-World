import { AgentProfile } from "@/features/agents/AgentProfile";

export default async function AgentPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <AgentProfile slug={slug} />;
}
