/**
 * useStreamSession — unit tests.
 *
 * One consolidated case covers the full session lifecycle:
 * failStream → startStream → cancelStream, asserting loading flips while
 * unrelated slice fields are preserved.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useStreamSession } from './useStreamSession';

describe('useStreamSession', () => {
  it('startStream / cancelStream toggle loading without clobbering history; startStream clears prior error', () => {
    const { result } = renderHook(() => useStreamSession());

    act(() => result.current.failStream('previous failure'));
    expect(result.current.streamSession.streamError).toBe('previous failure');

    act(() => result.current.startStream());
    expect(result.current.streamSession.loading).toBe(true);
    expect(result.current.streamSession.streamError).toBe('');
    expect(result.current.streamSession.isInterrupted).toBe(false);

    act(() =>
      result.current.setStreamSession((prev) => ({
        ...prev,
        currentNode: 'supervisor',
        history: ['supervisor'],
      })),
    );

    act(() => result.current.cancelStream());
    expect(result.current.streamSession.loading).toBe(false);
    expect(result.current.streamSession.currentNode).toBe('supervisor');
    expect(result.current.streamSession.history).toEqual(['supervisor']);
  });
});
