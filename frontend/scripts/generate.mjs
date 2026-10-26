import { readFile, writeFile } from 'node:fs/promises';
import openapiTS, { astToString } from 'openapi-typescript';

const contract = new URL('../../contracts/openapi.json', import.meta.url);
const target = new URL('../src/api/schema.d.ts', import.meta.url);
const output = '// Generated from contracts/openapi.json. Do not edit.\n' + astToString(await openapiTS(contract));
if (process.argv.includes('--check')) {
  if (await readFile(target, 'utf8') !== output) throw new Error('API types are stale. Run npm run generate.');
} else {
  await writeFile(target, output);
}
