const path = require('node:path');
const os = require('node:os');
const { createRequire } = require('node:module');
function runtimeModule(name) {
  const roots = [process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, process.env.RUNTIME_NODE_MODULES,
    ...String(process.env.NODE_PATH || '').split(path.delimiter),
    path.join(os.homedir(), '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'node', 'node_modules')].filter(Boolean);
  try { return require(name); } catch (e) { if (e.code !== 'MODULE_NOT_FOUND') throw e; }
  for (const root of roots) {
    try { return createRequire(path.join(root, '__runtime__.cjs'))(name); }
    catch (e) { if (e.code !== 'MODULE_NOT_FOUND') throw e; }
  }
  throw new Error(`缺少 ${name}；請執行 npm install 或設定 NODE_PATH／CODEX_PRIMARY_RUNTIME_NODE_MODULES。`);
}
module.exports = { runtimeModule };
