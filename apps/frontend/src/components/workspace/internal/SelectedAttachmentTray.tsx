import React from 'react';
import NextImage from 'next/image';
import { X } from 'lucide-react';

import { cn } from '@/lib/cn';

import {
  attachmentIcon,
  formatAttachmentBytes,
  inferDraftAttachmentKind,
  type DraftAttachmentItem,
  type DraftAttachmentStatusMap,
} from './attachment-utils';

export interface SelectedAttachmentTrayProps {
  files: DraftAttachmentItem[];
  statuses: DraftAttachmentStatusMap;
  uploadState: 'idle' | 'uploading' | 'error';
  error: string;
  onRemove: (index: number) => void;
}

export const SelectedAttachmentTray = ({
  files,
  statuses,
  uploadState,
  error,
  onRemove,
}: SelectedAttachmentTrayProps) => {
  if (files.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-2 rounded-[12px] border border-[rgba(255,255,255,0.06)] bg-[rgba(29,31,40,0.4)] p-3">
      {files.map((item, i) => {
        const { file, localKey } = item;
        const kind = inferDraftAttachmentKind(file);
        const isImage = kind === 'image';
        const state = statuses[localKey]?.status || 'ready';
        const stateError = statuses[localKey]?.error;
        const stateLabel =
          state === 'uploading' ? 'UPLOADING' : state === 'failed' ? 'FAILED' : 'READY';
        const stateClassName =
          state === 'uploading'
            ? 'text-[#8ff5ff]'
            : state === 'failed'
              ? 'text-red-300'
              : 'text-emerald-300';

        return (
          <div
            key={`${localKey}_${i}`}
            className={cn(
              'relative overflow-hidden rounded-[12px] border border-[rgba(255,255,255,0.08)] bg-[rgba(7,9,13,0.72)]',
              isImage ? 'h-16 w-16' : 'flex min-w-[168px] max-w-[240px] items-center gap-3 px-3 py-3'
            )}
          >
            {isImage ? (
              <NextImage
                src={URL.createObjectURL(file)}
                alt={file.name}
                width={64}
                height={64}
                className="h-full w-full object-cover"
                unoptimized
              />
            ) : (
              <>
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] bg-[rgba(143,245,255,0.12)] text-[#8ff5ff]">
                  {attachmentIcon({
                    kind: kind || 'artifact',
                    alt: file.name,
                    file_name: file.name,
                    size_bytes: file.size,
                  })}
                </div>
                <div className="min-w-0 flex-1 pr-6">
                  <div className="truncate text-[12px] font-semibold text-[#e7e7f0]">
                    {file.name}
                  </div>
                  <div className="text-[10px] uppercase tracking-[0.16em] text-[rgba(170,170,179,0.72)]">
                    {(kind || 'file').toUpperCase()} · {formatAttachmentBytes(file.size)}
                  </div>
                  <div className={cn('mt-1 text-[10px] font-bold uppercase tracking-[0.18em]', stateClassName)}>
                    {stateLabel}
                  </div>
                  {stateError ? (
                    <div className="mt-1 text-[11px] leading-4 text-red-300">{stateError}</div>
                  ) : null}
                </div>
              </>
            )}
            <button
              type="button"
              onClick={() => onRemove(i)}
              className="absolute right-1 top-1 rounded-full bg-[rgba(7,9,13,0.84)] p-1 text-white transition hover:bg-red-500"
            >
              <X size={10} />
            </button>
          </div>
        );
      })}
      <div className="w-full pt-1 text-[10px] uppercase tracking-[0.16em] text-[rgba(170,170,179,0.72)]">
        {uploadState === 'uploading' ? 'Uploading files...' : 'Files ready to send'}
      </div>
      {error ? <div className="w-full text-[12px] text-red-300">{error}</div> : null}
    </div>
  );
};

export default SelectedAttachmentTray;
