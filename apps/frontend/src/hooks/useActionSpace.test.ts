/**
 * useActionSpace — unit tests.
 *
 * Single consolidated case exercises both the right-tab switch and the
 * suggested-queries lifecycle (begin → apply → fail) so each transition is
 * still covered without paying for two renders.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useActionSpace } from './useActionSpace';

describe('useActionSpace', () => {
  it('switches right tabs and walks the suggested-queries lifecycle (begin → apply → fail)', () => {
    const { result } = renderHook(() => useActionSpace());

    expect(result.current.actionSpace.activeRightTab).toBe('reasoning');

    act(() => result.current.setActiveRightTab('coding'));
    expect(result.current.actionSpace.activeRightTab).toBe('coding');

    act(() => result.current.beginSuggestedQueriesLoad());
    expect(result.current.actionSpace.suggestedQueriesState).toBe('loading');

    act(() => result.current.applySuggestedQueries(['What is next?']));
    expect(result.current.actionSpace.suggestedQueriesState).toBe('success');
    expect(result.current.actionSpace.suggestedQueries).toEqual(['What is next?']);

    act(() => result.current.failSuggestedQueries('network down'));
    expect(result.current.actionSpace.suggestedQueriesState).toBe('error');
    expect(result.current.actionSpace.suggestedQueriesError).toBe('network down');
  });
});
