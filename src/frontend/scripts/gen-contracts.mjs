// Generuje TypeScript ze sdílených kontraktů v src/contracts (výstup generuje backend).
//
//   npm run gen:contracts     # přepíše src/shared/api/generated/*
//   npm run check:contracts   # selže, pokud vygenerované soubory neodpovídají kontraktům
//
// Frontend tak nepíše typy API ani slovník stavů zakázky ručně: změna na backendu
// se projeví změnou kontraktu a typová kontrola ukáže všechna dotčená místa.
import { mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import openapiTS, { astToString } from 'openapi-typescript'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const contractsRoot = resolve(frontendRoot, '..', 'contracts')
const outDir = resolve(frontendRoot, 'src', 'shared', 'api', 'generated')
const check = process.argv.includes('--check')

const HEADER =
  '// VYGENEROVÁNO z src/contracts – NEUPRAVOVAT RUČNĚ.\n' +
  '// Přegenerování: npm run gen:contracts (kontrakty generuje backend: python -m scripts.export_contracts).\n\n'

function readJson(relativePath) {
  return JSON.parse(readFileSync(resolve(contractsRoot, relativePath), 'utf8'))
}

function renderWorkflow(workflow) {
  const actions = [...new Set(workflow.humanActions.map((a) => a.action))]
  return (
    HEADER +
    `export const CASE_STATUSES = ${JSON.stringify(workflow.statuses)} as const\n\n` +
    'export type CaseStatus = (typeof CASE_STATUSES)[number]\n\n' +
    `export const TERMINAL_CASE_STATUSES: readonly CaseStatus[] = ${JSON.stringify(workflow.terminalStatuses)}\n\n` +
    `export const LOCKED_CASE_STATUSES: readonly CaseStatus[] = ${JSON.stringify(workflow.lockedStatuses)}\n\n` +
    `export const CASE_ACTIONS = ${JSON.stringify(actions)} as const\n\n` +
    'export type CaseActionName = (typeof CASE_ACTIONS)[number]\n'
  )
}

async function render() {
  const openapi = readJson('openapi/openapi.json')
  const ast = await openapiTS(openapi, { alphabetize: true })
  return {
    'openapi.ts': HEADER + astToString(ast),
    'caseWorkflow.ts': renderWorkflow(readJson('workflow/case-workflow.json')),
  }
}

const outputs = await render()
const stale = []
for (const [name, content] of Object.entries(outputs)) {
  const target = resolve(outDir, name)
  if (check) {
    const current = existsSync(target) ? readFileSync(target, 'utf8').replace(/\r\n/g, '\n') : ''
    if (current !== content) stale.push(name)
    continue
  }
  mkdirSync(outDir, { recursive: true })
  writeFileSync(target, content, 'utf8')
  console.log(`wrote src/shared/api/generated/${name}`)
}
if (stale.length > 0) {
  console.error(`Zastaralé vygenerované kontrakty: ${stale.join(', ')} – spusť npm run gen:contracts`)
  process.exit(1)
}
