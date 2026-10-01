// [T-9.70 · D-50] Capa sobre `app.json`, que sigue siendo la configuración: lo leen
// varios tests y censos tal cual. Aquí sólo se añade lo que no puede ser estático:
// el plugin que mete el sonido OFICIAL del SASMEX en la APK sin que entre al
// repositorio, y lo que la compilación trae de verdad (`extra.tonoOficial`).
/* global __dirname */
const { tonoEmpaquetado } = require("./plugins/tonoOficial");

module.exports = ({ config }) => ({
  ...config,
  plugins: [...(config.plugins ?? []), "./plugins/tonoOficial"],
  extra: { ...(config.extra ?? {}), tonoOficial: tonoEmpaquetado(__dirname) },
});
