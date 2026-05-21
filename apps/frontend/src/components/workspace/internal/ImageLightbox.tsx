import React, { useEffect } from 'react';
import NextImage from 'next/image';
import { X } from 'lucide-react';

import { ChatAttachment } from '@/types/agent';

export interface ImageLightboxProps {
  attachment: ChatAttachment | null;
  onClose: () => void;
}

export const ImageLightbox = ({ attachment, onClose }: ImageLightboxProps) => {
  useEffect(() => {
    if (!attachment) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [attachment, onClose]);

  if (!attachment?.url) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-[rgba(7,9,13,0.84)] px-6 py-6 backdrop-blur-md"
      role="dialog"
      aria-modal="true"
      aria-label={`${attachment.alt} 확대 보기`}
      onClick={onClose}
    >
      <div
        className="relative flex max-h-full w-full max-w-[1200px] items-center justify-center"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close image preview"
          className="absolute right-0 top-0 z-10 inline-flex h-11 w-11 items-center justify-center rounded-full border border-[rgba(255,255,255,0.12)] bg-[rgba(12,14,20,0.76)] text-[#e7e7f0] transition hover:border-[rgba(143,245,255,0.32)] hover:text-[#8ff5ff]"
        >
          <X size={18} />
        </button>
        <div className="relative max-h-[88vh] w-full overflow-hidden rounded-[24px] border border-[rgba(255,255,255,0.08)] bg-[rgba(12,14,20,0.94)] p-4 shadow-[0px_30px_80px_rgba(0,0,0,0.55)]">
          <div className="mb-3 pr-14 text-[12px] font-semibold uppercase tracking-[0.18em] text-[rgba(170,170,179,0.74)]">
            {attachment.file_name || attachment.alt}
          </div>
          <div className="relative flex max-h-[78vh] min-h-[320px] items-center justify-center overflow-hidden rounded-[18px] bg-black/40">
            <NextImage
              src={attachment.url}
              alt={attachment.alt}
              width={1400}
              height={1000}
              className="max-h-[78vh] w-auto max-w-full object-contain"
              unoptimized
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default ImageLightbox;
