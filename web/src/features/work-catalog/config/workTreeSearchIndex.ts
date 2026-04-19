/**
 * Pre-built flat search index derived from WORK_TREE at module load time.
 *
 * This is purely structural — no case status, no allowed/recommended logic.
 * Phase-binding overlay is the responsibility of the consuming hook/container.
 */
import { WORK_TREE } from './workTreeConfig'
import { flattenWorkTree } from '../utils/flattenWorkTree'

export type { WorkTreeLeafIndexItem } from '../utils/flattenWorkTree'
export const WORK_TREE_SEARCH_INDEX = flattenWorkTree(WORK_TREE)
