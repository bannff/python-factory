"use client";

import { useEffect, useMemo, useState } from "react";
import { useToolData } from "@companion-x/shared-renderer";
import type { JsonSerializable } from "@copilotkit/react-core/v2";
import { useAgentContext } from "@copilotkit/react-core/v2";
import type { Artifact, ArtifactComment, ArtifactVersion } from "./artifact-types";
import { rows } from "./artifact-types";
import { ArtifactPreview } from "./artifact-preview";
import { ArtifactEditor } from "./artifact-editor";
import { ArtifactHistory } from "./artifact-history";
import { ArtifactComments } from "./artifact-comments";
import { revertArtifact, STALE_ARTIFACT_MESSAGE } from "./artifact-actions";

/** Content over this length is summarized, not sent whole, into the agent
 * prompt context — keeps a large document/widget artifact from ballooning
 * every chat turn's token budget while still letting the agent "see" it. */
const CONTEXT_CONTENT_CAP = 4_000;

export function ArtifactDetail({
  artifact, onClose, onChanged,
}: { artifact: Artifact; onClose: () => void; onChanged: () => void }) {
  const [current, setCurrent] = useState(artifact);
  const [reverting, setReverting] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingAnchor, setPendingAnchor] = useState<string | null>(null);
  useEffect(() => { if (artifact.revision >= current.revision) setCurrent(artifact); }, [artifact, current.revision]);
  const versions = useToolData("artifacts_versions", { slug: current.slug });
  const comments = useToolData("artifacts_get_comments", { slug: current.slug });
  const versionRows = rows<ArtifactVersion>(versions.data, "versions");
  const commentRows = rows<ArtifactComment>(comments.data, "comments");
  const changed = (next: Artifact) => {
    setCurrent(next); onChanged(); versions.refetch();
  };
  const revert = async (version: number) => {
    setReverting(version); setError(null);
    try { changed(await revertArtifact(current, version)); }
    catch { setError(STALE_ARTIFACT_MESSAGE); }
    finally { setReverting(null); }
  };

  // Feature-map row 64's "companion-chat iteration pane": rather than a
  // second, duplicate chat surface embedded in this page, the ALREADY
  // global, always-visible chat sidebar becomes artifact-aware — same
  // mechanism CanvasContextBridge uses for workbench state (bd-vw04).
  // The user iterates through the one real chat they already have open;
  // it just now knows what they're looking at.
  const agentContextValue = useMemo(() => ({
    slug: current.slug, name: current.name, kind: current.kind,
    version: current.version, description: current.description,
    content: current.content.length > CONTEXT_CONTENT_CAP
      ? `${current.content.slice(0, CONTEXT_CONTENT_CAP)}\n…(truncated)` : current.content,
  }), [current]);
  useAgentContext({
    description:
      "The artifact the user currently has open in the Artifact detail " +
      "view. Use `artifacts_update` (slug, expected_revision, content) to " +
      "iterate on it when the user asks for changes.",
    value: agentContextValue as unknown as JsonSerializable,
  });

  return (
    <article className="rounded-xl border border-violet-500/30 bg-violet-500/[0.04] p-4">
      <div className="mb-4 flex items-center justify-between gap-3"><div><h2 className="font-medium">{current.name}</h2><p className="text-xs text-muted-foreground">{current.slug} · v{current.version} · {current.kind}</p></div><button type="button" onClick={onClose} className="text-xs text-muted-foreground hover:text-foreground">Close detail</button></div>
      <div className="mb-5"><ArtifactPreview artifact={current} onAnchorSelect={setPendingAnchor} /></div>
      {error && <div role="alert" className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-200">{error}</div>}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(260px,0.75fr)]">
        <ArtifactEditor artifact={current} onSaved={changed} />
        <div className="space-y-6">
          <ArtifactHistory versions={versionRows} loading={versions.loading} reverting={reverting} currentVersion={current.version} onRevert={revert} />
          {versions.error && <p role="alert" className="text-xs text-destructive">Versions unavailable: {versions.error}</p>}
          <ArtifactComments
            slug={current.slug} comments={commentRows} loading={comments.loading}
            onChanged={comments.refetch} artifactContent={current.content}
            pendingAnchor={pendingAnchor} onClearAnchor={() => setPendingAnchor(null)}
          />
          {comments.error && <p role="alert" className="text-xs text-destructive">Comments unavailable: {comments.error}</p>}
        </div>
      </div>
    </article>
  );
}
