/**
 * loom-web — public library entry.
 *
 * Components consumers can compose into their own React apps. All have
 * `react`, `react-dom`, `mermaid`, and (where applicable) `react-router-dom`
 * as peer dependencies — consumers control the versions.
 *
 * Usage:
 *   import { LoomPlayer, AdminNav } from 'loom-web'
 *   import 'loom-web/styles.css'   // optional global resets
 */

export { default as LoomPlayer } from './components/LoomPlayer'
export { default as AdminNav }   from './components/AdminNav'

// Page-level views are NOT exported. Pages are app-specific composition;
// consumers build their own pages from the components above. If a third
// consumer asks for a page-level export, revisit then.
