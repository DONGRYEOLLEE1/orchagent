import React from 'react';
import {
  FileJson,
  FileSpreadsheet,
  FileText,
  Image as ImageIcon,
} from 'lucide-react';

import { ChatAttachment } from '@/types/agent';
import type { UploadBatchError } from '@/lib/api';

export const SUPPORTED_ATTACHMENT_LABEL = '이미지, PDF, XLSX, CSV, JSON, DOCX만 지원합니다.';
export const ATTACHMENT_MAX_FILES = 5;
export const ATTACHMENT_MAX_TOTAL_BYTES = 30 * 1024 * 1024;
export const ATTACHMENT_MAX_BYTES_BY_KIND: Record<
  Exclude<ChatAttachment['kind'], 'artifact'>,
  number
> = {
  image: 10 * 1024 * 1024,
  pdf: 20 * 1024 * 1024,
  spreadsheet: 20 * 1024 * 1024,
  csv: 10 * 1024 * 1024,
  json: 20 * 1024 * 1024,
  docx: 20 * 1024 * 1024,
};

export type DraftAttachmentStatus = 'ready' | 'uploading' | 'failed';

export type DraftAttachmentItem = {
  file: File;
  localKey: string;
};

export type DraftAttachmentStatusMap = Record<
  string,
  {
    status: DraftAttachmentStatus;
    error?: string;
  }
>;

export function inferDraftAttachmentKind(file: File): ChatAttachment['kind'] | null {
  const extension = file.name.split('.').pop()?.toLowerCase();
  if (file.type.startsWith('image/')) return 'image';
  if (file.type === 'application/pdf' || extension === 'pdf') return 'pdf';
  if (
    file.type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
    extension === 'xlsx'
  ) {
    return 'spreadsheet';
  }
  if (file.type === 'text/csv' || extension === 'csv') return 'csv';
  if (file.type === 'application/json' || extension === 'json') return 'json';
  if (
    file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    extension === 'docx'
  ) {
    return 'docx';
  }
  return null;
}

export function draftAttachmentKey(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

export function formatAttachmentBytes(sizeBytes?: number | null): string {
  if (!sizeBytes || sizeBytes <= 0) return '';
  if (sizeBytes < 1024) return `${sizeBytes}B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)}KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)}MB`;
}

export function maxBytesForDraftKind(
  kind: Exclude<ChatAttachment['kind'], 'artifact'>
): number {
  return ATTACHMENT_MAX_BYTES_BY_KIND[kind];
}

export function summarizeUploadErrors(errors: UploadBatchError[]): string {
  return errors.map((error) => `${error.file_name}: ${error.detail}`).join('\n');
}

export function validateIncomingDraftFiles(params: {
  existingFiles: DraftAttachmentItem[];
  existingStatuses: DraftAttachmentStatusMap;
  incomingFiles: File[];
}): {
  accepted: DraftAttachmentItem[];
  nextStatusPatch: DraftAttachmentStatusMap;
  message: string;
} {
  const { existingFiles, existingStatuses, incomingFiles } = params;
  const accepted: DraftAttachmentItem[] = [];
  const nextStatusPatch: DraftAttachmentStatusMap = {};
  const errors: string[] = [];

  const existingReadyFiles = existingFiles.filter(
    (item) => existingStatuses[item.localKey]?.status !== 'failed'
  );
  let acceptedCount = existingReadyFiles.length;
  let acceptedBytes = existingReadyFiles.reduce((sum, item) => sum + item.file.size, 0);

  for (const file of incomingFiles) {
    const kind = inferDraftAttachmentKind(file);
    if (!kind || kind === 'artifact') {
      errors.push(`${file.name}: ${SUPPORTED_ATTACHMENT_LABEL}`);
      continue;
    }

    if (acceptedCount >= ATTACHMENT_MAX_FILES) {
      errors.push(`${file.name}: 한 번에 최대 ${ATTACHMENT_MAX_FILES}개 파일만 첨부할 수 있습니다.`);
      continue;
    }

    const maxBytes = maxBytesForDraftKind(kind);
    if (file.size > maxBytes) {
      errors.push(
        `${file.name}: ${kind.toUpperCase()} 파일은 ${formatAttachmentBytes(maxBytes)}까지 첨부할 수 있습니다.`
      );
      continue;
    }

    if (acceptedBytes + file.size > ATTACHMENT_MAX_TOTAL_BYTES) {
      errors.push(
        `${file.name}: 첨부 파일 총합은 ${formatAttachmentBytes(ATTACHMENT_MAX_TOTAL_BYTES)}를 넘을 수 없습니다.`
      );
      continue;
    }

    const localKey = draftAttachmentKey(file);
    accepted.push({ file, localKey });
    nextStatusPatch[localKey] = { status: 'ready' };
    acceptedCount += 1;
    acceptedBytes += file.size;
  }

  return {
    accepted,
    nextStatusPatch,
    message: errors.join('\n'),
  };
}

export function attachmentIcon(attachment: ChatAttachment) {
  switch (attachment.kind) {
    case 'spreadsheet':
    case 'csv':
      return <FileSpreadsheet size={15} />;
    case 'json':
      return <FileJson size={15} />;
    case 'image':
      return <ImageIcon size={15} />;
    default:
      return <FileText size={15} />;
  }
}

export const buildOptimisticAttachments = (files: File[]): ChatAttachment[] =>
  files.map((file, index) => {
    const kind = inferDraftAttachmentKind(file) || 'artifact';
    return {
      kind,
      url: kind === 'image' ? URL.createObjectURL(file) : undefined,
      alt: file.name || `첨부 파일 ${index + 1}`,
      file_name: file.name,
      mime_type: file.type || null,
      size_bytes: file.size,
    };
  });
