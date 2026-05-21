/**
 * useStreamSession — unit tests (Phase 3.2).
 *
 * Covers the loading lifecycle helpers: startStream flips loading=true and
 * cancelStream brings it back down without touching history.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useStreamSession } from './useStreamSession';

describe('useStreamSession', () => {
  it('startStream marks the session as loading and clears prior error', () => {
    const { result } = renderHook(() => useStreamSession());

    expect(result.current.streamSession.loading).toBe(false);

    act(() => {
      result.current.failStream('previous failure');
    });

    expect(result.current.streamSession.loading).toBe(false);
    expect(result.current.streamSession.streamError).toBe('previous failure');

    act(() => {
      result.current.startStream();
    });

    expect(result.current.streamSession.loading).toBe(true);
    expect(result.current.streamSession.streamError).toBe('');
    expect(result.current.streamSession.isInterrupted).toBe(false);
  });

  it('cancelStream flips loading back to false while leaving the rest of the slice intact', () => {
    const { result } = renderHook(() => useStreamSession());

    act(() => {
      result.current.startStream();
    });
    expect(result.current.streamSession.loading).toBe(true);

    act(() => {
      result.current.setStreamSession((prev) => ({
        ...prev,
        currentNode: 'supervisor',
        history: ['supervisor'],
      }));
    });

    act(() => {
      result.current.cancelStream();
    });

    expect(result.current.streamSession.loading).toBe(false);
    expect(result.current.streamSession.currentNode).toBe('supervisor');
    expect(result.current.streamSession.history).toEqual(['supervisor']);
  });
});
