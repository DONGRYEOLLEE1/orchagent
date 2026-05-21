/**
 * useActionSpace — unit tests (Phase 3.2).
 *
 * Covers the right-side tab switch + suggested-queries lifecycle helpers
 * (selectToolExecution lives on the slice via setActionSpace; we exercise it
 * through setActiveRightTab to validate the action-space slice transitions).
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useActionSpace } from './useActionSpace';

describe('useActionSpace', () => {
  it('setActiveRightTab switches the currently-active right aside tab', () => {
    const { result } = renderHook(() => useActionSpace());

    expect(result.current.actionSpace.activeRightTab).toBe('reasoning');

    act(() => {
      result.current.setActiveRightTab('coding');
    });

    expect(result.current.actionSpace.activeRightTab).toBe('coding');

    act(() => {
      result.current.setActiveRightTab('reasoning');
    });

    expect(result.current.actionSpace.activeRightTab).toBe('reasoning');
  });

  it('suggested-queries lifecycle: begin → apply transitions state to success', () => {
    const { result } = renderHook(() => useActionSpace());

    act(() => {
      result.current.beginSuggestedQueriesLoad();
    });
    expect(result.current.actionSpace.suggestedQueriesState).toBe('loading');
    expect(result.current.actionSpace.suggestedQueriesError).toBe('');

    act(() => {
      result.current.applySuggestedQueries(['What is next?', 'Summarize results']);
    });
    expect(result.current.actionSpace.suggestedQueries).toEqual([
      'What is next?',
      'Summarize results',
    ]);
    expect(result.current.actionSpace.suggestedQueriesState).toBe('success');

    act(() => {
      result.current.failSuggestedQueries('network down');
    });
    expect(result.current.actionSpace.suggestedQueriesState).toBe('error');
    expect(result.current.actionSpace.suggestedQueriesError).toBe('network down');
  });
});
