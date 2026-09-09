import { execFileSync } from 'node:child_process';
import {
  cp,
  mkdir,
  readFile,
  realpath,
  rm,
  stat,
  writeFile,
} from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const source = fileURLToPath(new URL('..', import.meta.url));
const destination = process.argv[2];
if (!destination || process.argv.length !== 3) {
  throw new Error(
    'Usage: npm run stage-pages -- /path/to/existing/gh-pages-checkout',
  );
}
const target = await realpath(resolve(destination));
const git = (...args) =>
  execFileSync('git', ['-C', target, ...args], { encoding: 'utf8' }).trim();
if (
  git('branch', '--show-current') !== 'gh-pages' ||
  (await realpath(git('rev-parse', '--show-toplevel'))) !== target
) {
  throw new Error(
    'Destination must be the root of an existing gh-pages checkout.',
  );
}
if (git('status', '--porcelain')) {
  throw new Error(
    'Destination has uncommitted work; review it before staging a new publication.',
  );
}
await stat(join(target, 'viewer', 'index.html'));
await stat(join(target, 'golden'));
const output = join(source, 'dist');
const html = await readFile(join(output, 'index.html'), 'utf8');
if (!html.includes('./assets/') || !html.includes('Architecture Explorer')) {
  throw new Error(
    'Build the relative-path static explorer with npm run build first.',
  );
}
const assets = await stat(join(output, 'assets'));
if (!assets.isDirectory()) throw new Error('Missing built assets.');
const explorer = join(target, 'explorer');
if (dirname(explorer) !== target)
  throw new Error('Invalid explorer destination.');
await rm(explorer, { recursive: true, force: true });
await mkdir(explorer);
await cp(output, explorer, { recursive: true });
await cp(join(source, 'pages-index.html'), join(target, 'index.html'));
await writeFile(join(target, '.nojekyll'), '\n');
console.log(
  `Staged ${explorer} and the landing page. Existing viewer/ and golden/ are unchanged.`,
);
console.log('Review git diff, then commit and push gh-pages to publish.');
