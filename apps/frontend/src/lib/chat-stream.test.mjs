import test from 'node:test';
import assert from 'node:assert/strict';

import {
  appendAssistantText,
  parseSseBlock,
  pushUniqueHistory,
  splitSseBlocks,
} from './chat-stream.js';

test('splitSseBlocks handles chunked SSE payloads', () => {
  const firstPass = splitSseBlocks(
    'data: {"event_type":"status","status":"running"}\n\n' + 'data: {"event'
  );

  assert.equal(firstPass.blocks.length, 1);
  assert.equal(parseSseBlock(firstPass.blocks[0]).status, 'running');
  assert.equal(firstPass.remainder, 'data: {"event');

  const secondPass = splitSseBlocks(
    firstPass.remainder + '_type":"text","content":"hello"}\n\n'
  );
  assert.equal(secondPass.blocks.length, 1);
  assert.equal(parseSseBlock(secondPass.blocks[0]).content, 'hello');
});

test('appendAssistantText appends to the current assistant bubble', () => {
  const initial = [{ role: 'assistant', content: 'hel', id: 'a1' }];
  const next = appendAssistantText(initial, 'a1', 'lo');

  assert.deepEqual(next, [{ role: 'assistant', content: 'hello', id: 'a1' }]);
});

test('pushUniqueHistory avoids consecutive duplicates', () => {
  assert.deepEqual(pushUniqueHistory(['Research Team'], 'Research Team'), ['Research Team']);
  assert.deepEqual(pushUniqueHistory(['Research Team'], 'Search'), ['Research Team', 'Search']);
});
