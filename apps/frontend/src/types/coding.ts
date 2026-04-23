// Typed mirror of apps/backend/schemas/coding.py — snake_case preserved to match API wire format.
// Update both sides together; see .claude/skills/integration-qa-protocol/SKILL.md.

export interface ChangedFileEntry {
  path: string;
  status?: string | null;
}

export type VerificationKind = 'test' | 'lint' | 'build' | 'runtime' | string;
export type VerificationStatus =
  | 'passed'
  | 'failed'
  | 'skipped'
  | 'unverified'
  | string;

export interface VerificationResult {
  kind: VerificationKind;
  label: string;
  status: VerificationStatus;
  command?: string | null;
  summary?: string | null;
}

export type PermissionTier =
  | 'read_only'
  | 'workspace_write'
  | 'workspace_execute'
  | 'browser_verify'
  | 'external_mcp'
  | 'dangerous';

export type FileChangeStatus = 'M' | 'A' | 'D' | 'R' | '?';

export interface FileEntry {
  path: string;
  kind: 'file' | 'dir';
  size_bytes?: number | null;
  changed_status?: FileChangeStatus | null;
}

export interface DiffSnippet {
  path: string;
  unified_diff: string;
  truncated?: boolean;
}

export interface CodingSummary {
  workspace_job_id?: string | null;
  repo_binding_id?: string | null;
  repo_commit_sha?: string | null;
  permission_mode?: PermissionTier | string | null;
  approval_required: boolean;
  approval_state?: string | null;
  changed_files: ChangedFileEntry[];
  git_status?: string | null;
  diff_available: boolean;
  verification_results: VerificationResult[];
  failure_summary?: string | null;
  completed_at?: string | null;
  tree?: FileEntry[];
  diffs?: DiffSnippet[];
}
