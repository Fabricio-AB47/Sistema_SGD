// Silencia warnings de Dart Sass (legacy-js-api, color-functions, etc.).
process.env.SASS_SILENCE_DEPRECATIONS = "all";
// Oculta deprecations de Node (fs.Stats) que provienen de dependencias de gulp.
process.noDeprecation = true;

/**
 * Pipeline de build de assets para el SIG.
 * - SCSS -> CSS con autoprefixer + sourcemaps (dev) y minificación (build).
 * - JS -> concat + terser (build).
 * - Imágenes / fuentes -> copia optimizada.
 * Salida: ../static/assets/{css,js,images,fonts}
 */

const { src, dest, series, parallel, watch } = require("gulp");
const dartSass = require("sass");
const through = require("through2");
const applySourceMap = require("vinyl-sourcemaps-apply");
const postcss = require("gulp-postcss");
const autoprefixer = require("autoprefixer");
const cssnano = require("cssnano");
const sourcemaps = require("gulp-sourcemaps");
const rename = require("gulp-rename");
const concat = require("gulp-concat");
const terser = require("gulp-terser");
// gulp-imagemin expone default en CJS cuando se instala con ESM >=8
const imagemin = require("gulp-imagemin").default || require("gulp-imagemin");
const gulpIf = require("gulp-if");
// del@7 es ESM: usamos deleteAsync vía require con desestructuración.
const { deleteAsync } = require("del");

const paths = {
  styles: "src/scss/app.scss", // punto de entrada único
  scripts: "src/js/**/*.js",
  images: "src/images/**/*",
  fonts: "src/fonts/**/*",
  // Salida ahora vive dentro de frontend/static para servir assets compilados
  output: "./static",
};

const isProd = process.env.NODE_ENV === "production";

function clean() {
  // Limpia la carpeta de salida antes de compilar.
  return deleteAsync([`${paths.output}/**/*`], { force: true });
}

function styles() {
  return src(paths.styles)
    .pipe(gulpIf(!isProd, sourcemaps.init()))
    .pipe(
      through.obj(async (file, _, cb) => {
        try {
          // Compila Sass de entrada única (app.scss)
          const result = await dartSass.compileStringAsync(file.contents.toString(), {
            style: "expanded",
            sourceMap: !isProd,
            url: new URL(`file://${file.path.replace(/\\/g, "/")}`),
          });
          file.contents = Buffer.from(result.css);
          if (!isProd && result.sourceMap) {
            const map =
              typeof result.sourceMap === "string"
                ? JSON.parse(result.sourceMap)
                : result.sourceMap;
            map.file = map.file || file.relative;
            applySourceMap(file, map);
          }
          cb(null, file);
        } catch (err) {
          cb(err);
        }
      })
    )
    // app.css (no min)
    .pipe(rename("app.css"))
    .pipe(dest(`${paths.output}/css`, { sourcemaps: !isProd }))
    // app.min.css (minificado)
    .pipe(postcss([autoprefixer(), cssnano()]))
    .pipe(rename("app.min.css"))
    .pipe(dest(`${paths.output}/css`));
}

function scripts() {
  return src(paths.scripts, { sourcemaps: !isProd })
    .pipe(concat(isProd ? "app.min.js" : "app.js"))
    .pipe(gulpIf(isProd, terser()))
    .pipe(dest(`${paths.output}/js`, { sourcemaps: !isProd }));
}

function images() {
  return src(paths.images)
    .pipe(gulpIf(isProd, imagemin()))
    .pipe(dest(`${paths.output}/images`));
}

function fonts() {
  return src(paths.fonts).pipe(dest(`${paths.output}/fonts`));
}

function watcher() {
  watch(paths.styles, styles);
  watch(paths.scripts, scripts);
  watch(paths.images, images);
  watch(paths.fonts, fonts);
}

const build = series(clean, parallel(styles, scripts, images, fonts));          // Build one-shot.
const dev = series(clean, parallel(styles, scripts, images, fonts), watcher);   // Dev queda en watch.

exports.clean = clean;
exports.styles = styles;
exports.scripts = scripts;
exports.images = images;
exports.fonts = fonts;
exports.build = build;
exports.dev = dev;
exports.watch = series(dev, watcher);
