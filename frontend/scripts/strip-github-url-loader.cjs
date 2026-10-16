/**
 * Visitor JS must not contain a GitHub URL. Dependencies such as MapLibre
 * and core-js embed license links. Rewrite those URLs before they ship.
 */
module.exports = function stripGithubUrlLoader(source) {
  if (!/github\.com/i.test(source)) return source;
  return source.replace(/https?:\/\/github\.com/gi, "https://example.invalid");
};
