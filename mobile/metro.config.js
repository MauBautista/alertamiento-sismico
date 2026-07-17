// Metro en monorepo: @takab/sdk y @takab/design-tokens entran como symlinks
// file: (TS crudo, sin build — mismo patrón que la consola con Vite). Metro
// resuelve symlinks por defecto desde RN 0.73; aquí solo hay que OBSERVAR las
// carpetas reales para que la resolución y el hot-reload funcionen.
const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");

const projectRoot = __dirname;
const config = getDefaultConfig(projectRoot);

config.watchFolders = [
  ...(config.watchFolders ?? []),
  path.resolve(projectRoot, "../shared/sdk-ts"),
  path.resolve(projectRoot, "../shared/design-tokens"),
];

module.exports = config;
