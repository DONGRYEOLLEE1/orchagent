export function splitSseBlocks(buffer) {
  const normalized = buffer.replace(/\r\n/g, '\n');
  const blocks = [];
  let remainder = normalized;

  while (true) {
    const delimiterIndex = remainder.indexOf('\n\n');
    if (delimiterIndex === -1) {
      break;
    }

    blocks.push(remainder.slice(0, delimiterIndex));
    remainder = remainder.slice(delimiterIndex + 2);
  }

  return { blocks, remainder };
}

export function parseSseBlock(block) {
  const lines = block.split('\n');
  const dataLines = [];

  for (const line of lines) {
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  try {
    return JSON.parse(dataLines.join('\n'));
  } catch (error) {
    console.error('Failed to parse SSE payload', error);
    return null;
  }
}

export function appendAssistantText(messages, assistantId, text) {
  if (!text) {
    return messages;
  }

  const lastMessage = messages[messages.length - 1];
  if (
    lastMessage &&
    lastMessage.role === 'assistant' &&
    lastMessage.id === assistantId
  ) {
    return [
      ...messages.slice(0, -1),
      { ...lastMessage, content: lastMessage.content + text },
    ];
  }

  return [...messages, { role: 'assistant', content: text, id: assistantId }];
}

export function pushUniqueHistory(history, nextItem) {
  if (!nextItem) {
    return history;
  }

  if (history[history.length - 1] === nextItem) {
    return history;
  }

  return [...history, nextItem];
}
