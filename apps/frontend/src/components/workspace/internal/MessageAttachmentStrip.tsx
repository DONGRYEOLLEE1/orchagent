import React from 'react';
import NextImage from 'next/image';

import { cn } from '@/lib/cn';
import { ChatAttachment } from '@/types/agent';

import { attachmentIcon, formatAttachmentBytes } from './attachment-utils';

export interface MessageAttachmentStripProps {
  attachments: ChatAttachment[];
  align?: 'start' | 'end';
  onImageSelect?: (attachment: ChatAttachment) => void;
}

export const MessageAttachmentStrip = ({
  attachments,
  align = 'end',
  onImageSelect,
}: MessageAttachmentStripProps) => {
  const imageAttachments = attachments.filter(
    (attachment) =>
      attachment.kind === 'image' || Boolean(attachment.mime_type?.startsWith('image/'))
  );
  const fileAttachments = attachments.filter(
    (attachment) =>
      attachment.kind !== 'image' && !attachment.mime_type?.startsWith('image/')
  );
  if (imageAttachments.length === 0 && fileAttachments.length === 0) {
    return null;
  }

  const visibleAttachments = imageAttachments.slice(0, 4);
  const hiddenCount = imageAttachments.length - visibleAttachments.length;
  const isSingle = visibleAttachments.length === 1;

  return (
    <div className={cn('mb-3 w-[244px] space-y-2', align === 'end' ? 'self-end' : 'self-start')}>
      {visibleAttachments.length > 0 ? (
        <div className={cn('grid gap-2', isSingle ? 'grid-cols-1' : 'grid-cols-2')}>
          {visibleAttachments.map((attachment, index) => (
            <button
              type="button"
              key={`${attachment.url || attachment.alt}_${index}`}
              onClick={() => onImageSelect?.(attachment)}
              className={cn(
                'relative overflow-hidden rounded-[22px] border border-[rgba(255,255,255,0.1)] bg-[rgba(35,38,46,0.46)] shadow-[0px_18px_32px_-24px_rgba(0,0,0,0.9)] transition hover:brightness-110 cursor-zoom-in',
                isSingle ? 'aspect-[4/3]' : 'aspect-square'
              )}
              aria-label={`${attachment.alt} 크게 보기`}
            >
              {attachment.url ? (
                <NextImage
                  src={attachment.url}
                  alt={attachment.alt}
                  fill
                  sizes={isSingle ? '244px' : '118px'}
                  className="object-cover"
                  unoptimized
                />
              ) : null}
              {hiddenCount > 0 && index === visibleAttachments.length - 1 ? (
                <div className="absolute inset-0 flex items-center justify-center bg-[rgba(7,9,13,0.64)] text-[18px] font-semibold text-white">
                  +{hiddenCount}
                </div>
              ) : null}
            </button>
          ))}
        </div>
      ) : null}

      {fileAttachments.map((attachment, index) => (
        <div
          key={`${attachment.file_name || attachment.alt}_${index}`}
          className="flex items-center gap-3 rounded-[16px] border border-[rgba(255,255,255,0.08)] bg-[rgba(35,38,46,0.52)] px-3 py-3 text-[#e7e7f0]"
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] bg-[rgba(143,245,255,0.12)] text-[#8ff5ff]">
            {attachmentIcon(attachment)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[12px] font-semibold leading-5">
              {attachment.file_name || attachment.alt}
            </div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-[rgba(170,170,179,0.72)]">
              {attachment.kind}
              {attachment.size_bytes ? ` · ${formatAttachmentBytes(attachment.size_bytes)}` : ''}
            </div>
          </div>
          {attachment.url ? (
            <a
              href={attachment.url}
              target="_blank"
              rel="noreferrer"
              className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#8ff5ff] transition hover:text-[#c7fbff]"
            >
              Open
            </a>
          ) : null}
        </div>
      ))}
    </div>
  );
};

export default MessageAttachmentStrip;
