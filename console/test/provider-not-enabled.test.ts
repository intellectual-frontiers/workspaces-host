import test from 'node:test';
import assert from 'node:assert/strict';
import { makeRepo } from './support/fake-launcher';
import { Repository } from '../src/services/repository';

const load = async (stdout: string, exit: number): Promise<Repository> => {
  const fake = makeRepo({ docs: { 'command list': { doc: stdout, exit } }, launcherName: 'agora' });
  const repo = new Repository({ folder: { name: 'x', uri: { toString: () => 'file:///x' } } as never, root: fake.root, file: fake.file, program: './agora', source: 'declared' });
  await repo.load();
  fake.cleanup();
  return repo;
};

test('a launcher that says ws-host has not enabled its repository is recognized, and its own words are kept for the person', async () => {
  const repo = await load("No enabled provider is called 'agora'. None is enabled yet. Enable the repository that holds it with: ws-host provider add PATH\n", 3);
  assert.equal(repo.state, 'unavailable');
  assert.equal(repo.needsProvider, true);
  assert.equal(repo.missing, true);
  assert.match(repo.reason, /It said: No enabled provider is called 'agora'/);
});

test('a launcher that is missing something else is not mistaken for an unenabled provider', async () => {
  const repo = await load('agora: ws-host is needed and is not on PATH\n', 3);
  assert.equal(repo.needsProvider, false);
  assert.equal(repo.missing, true);
  assert.match(repo.said, /ws-host is needed/);
});
