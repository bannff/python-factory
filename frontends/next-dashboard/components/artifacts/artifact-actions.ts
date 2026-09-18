import { callTool } from "@/lib/api";
import { unwrapToolData } from "@/lib/tool-result-data";
import type { Artifact, ArtifactFolder } from "./artifact-types";

function artifactFrom(raw: unknown): Artifact {
  const data = unwrapToolData(raw) as { result?: { artifact?: Artifact } } | undefined;
  const artifact = data?.result?.artifact;
  if (!artifact) throw new Error("Artifact mutation returned no record");
  return artifact;
}

function folderFrom(raw: unknown): ArtifactFolder {
  const data = unwrapToolData(raw) as { folder?: ArtifactFolder } | undefined;
  const folder = data?.folder;
  if (!folder) throw new Error("Folder mutation returned no record");
  return folder;
}

export async function listFolders(): Promise<ArtifactFolder[]> {
  const data = unwrapToolData(await callTool("artifacts_folder_list", {})) as { folders?: unknown };
  return Array.isArray(data?.folders) ? data.folders as ArtifactFolder[] : [];
}

export async function createFolder(name: string, parentId: string | null): Promise<ArtifactFolder> {
  return folderFrom(await callTool("artifacts_folder_create", {
    name, ...(parentId ? { parent_id: parentId } : {}),
  }));
}

export async function renameFolder(folder: ArtifactFolder, name: string): Promise<ArtifactFolder> {
  return folderFrom(await callTool("artifacts_folder_rename", {
    folder_id: folder.id, expected_revision: folder.revision, name,
  }));
}

export async function moveFolder(folder: ArtifactFolder, parentId: string | null): Promise<ArtifactFolder> {
  return folderFrom(await callTool("artifacts_folder_move", {
    folder_id: folder.id, expected_revision: folder.revision,
    ...(parentId ? { parent_id: parentId } : {}),
  }));
}

export async function deleteFolder(folder: ArtifactFolder): Promise<void> {
  await callTool("artifacts_folder_delete", {
    folder_id: folder.id, expected_revision: folder.revision,
  });
}

export async function moveArtifactToFolder(
  artifact: Artifact, folderId: string | null,
): Promise<Artifact> {
  const data = unwrapToolData(await callTool("artifacts_move", {
    slug: artifact.slug, expected_revision: artifact.revision,
    ...(folderId ? { folder_id: folderId } : {}),
  })) as { artifact?: Artifact };
  if (!data?.artifact) throw new Error("Artifact move returned no record");
  return data.artifact;
}

export async function saveArtifact(input: {
  name: string; content: string; kind: Artifact["kind"];
  description?: string; tags?: string[];
}): Promise<Artifact> {
  return artifactFrom(await callTool("artifacts_save", {
    name: input.name, content: input.content, kind: input.kind,
    description: input.description ?? "", tags: input.tags ?? [],
  }));
}

export async function updateArtifact(
  artifact: Artifact, content: string,
): Promise<Artifact> {
  return artifactFrom(await callTool("artifacts_update", {
    slug: artifact.slug,
    expected_revision: artifact.revision,
    content,
  }));
}

export async function revertArtifact(
  artifact: Artifact, version: number,
): Promise<Artifact> {
  return artifactFrom(await callTool("artifacts_revert", {
    slug: artifact.slug,
    expected_revision: artifact.revision,
    version,
  }));
}

export async function postArtifactComment(
  slug: string, body: string, anchorText?: string | null,
): Promise<void> {
  await callTool("artifacts_post_comment", {
    slug, body, ...(anchorText ? { anchor_text: anchorText } : {}),
  });
}

export async function markArtifactCommentReview(
  slug: string, commentId: string,
): Promise<void> {
  await callTool("artifacts_mark_comment_review", {
    slug,
    comment_id: commentId,
  });
}

export const STALE_ARTIFACT_MESSAGE =
  "This artifact changed since it was opened. Refresh the latest revision and try again.";
