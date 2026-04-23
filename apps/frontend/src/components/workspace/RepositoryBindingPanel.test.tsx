import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';

import RepositoryBindingPanel from '@/components/workspace/RepositoryBindingPanel';


test('binds a URL and surfaces the active repository binding', async () => {
  const user = userEvent.setup();
  const onBindUrl = vi.fn();
  const onBindZip = vi.fn();
  const onDeleteBinding = vi.fn();
  const onMaterialize = vi.fn();

  const { rerender } = render(
    <RepositoryBindingPanel
      binding={null}
      disabled={false}
      loading={false}
      error=""
      onBindUrl={onBindUrl}
      onBindZip={onBindZip}
      onDeleteBinding={onDeleteBinding}
      onMaterialize={onMaterialize}
    />
  );

  await user.type(
    screen.getByPlaceholderText(/paste github url or git url/i),
    'https://github.com/example/sample-repo'
  );
  await user.click(screen.getByRole('button', { name: /bind github url/i }));

  expect(onBindUrl).toHaveBeenCalledWith(
    'github_url',
    'https://github.com/example/sample-repo'
  );

  // Zip upload path is only available in the unbound state (new binding form hidden once active).
  const zipFile = new File(['zip'], 'sample.zip', { type: 'application/zip' });
  const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
  await user.upload(fileInput, zipFile);
  expect(onBindZip).toHaveBeenCalled();

  rerender(
    <RepositoryBindingPanel
      binding={{
        id: 'binding-1',
        thread_id: 'thread-1',
        source_type: 'github_url',
        source_label: 'https://github.com/example/sample-repo',
        display_name: 'sample-repo',
        status: 'active',
      }}
      disabled={false}
      loading={false}
      error=""
      onBindUrl={onBindUrl}
      onBindZip={onBindZip}
      onDeleteBinding={onDeleteBinding}
      onMaterialize={onMaterialize}
    />
  );

  expect(screen.getByText('sample-repo')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /refresh repo/i }));
  expect(onMaterialize).toHaveBeenCalled();

  await user.click(screen.getByRole('button', { name: /unbind repo/i }));
  expect(onDeleteBinding).toHaveBeenCalled();
});
