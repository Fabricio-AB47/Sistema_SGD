process.env.SASS_SILENCE_DEPRECATIONS = "all";
process.noDeprecation = true;

/**
 * Pipeline de build de assets para el SIG.
 * - SCSS -> CSS con autoprefixer + sourcemaps (dev) y minificación (build).
 * - JS -> concat + terser (build).
 * - Imágenes / fuentes -> copia optimizada.
 * Salida: ../static/assets/{css,js,images,fonts}
 */

const { src, dest, series, parallel, watch } = require("gulp");
const { pathToFileURL } = require("url");
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
const gulpIf = require("gulp-if");
const { deleteAsync } = require("del");

const paths = {
  styles: "src/scss/app.scss",
  scripts: "src/js/**/*.js",
  images: "src/images/**/*",
  fonts: "src/fonts/**/*",
  output: "./static",
};

const isProd = process.env.NODE_ENV === "production";

function getImagemin() {
  try {
    const module = require("gulp-imagemin");
    return module.default || module;
  } catch (error) {
    if (error.code !== "MODULE_NOT_FOUND") {
      throw error;
    }

    // En desarrollo no bloqueamos el pipeline si la optimizacion de imagenes no esta instalada.
    return null;
  }
}

function clean() {
  return deleteAsync([`${paths.output}/**/*`], { force: true });
}

function styles() {
  return src(paths.styles)
    .pipe(gulpIf(!isProd, sourcemaps.init()))
    .pipe(
      through.obj(async (file, _, cb) => {
        try {
          const result = await dartSass.compileStringAsync(file.contents.toString(), {
            style: "expanded",
            sourceMap: !isProd,
            url: pathToFileURL(file.path),
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
    .pipe(rename("app.css"))
    .pipe(dest(`${paths.output}/css`, { sourcemaps: !isProd }))
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
  const imagemin = getImagemin();
  const imagePipeline =
    isProd && imagemin
      ? imagemin()
      : through.obj((file, _, cb) => cb(null, file));

  return src(paths.images)
    .pipe(imagePipeline)
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

const build = series(clean, parallel(styles, scripts, images, fonts));
const dev = series(clean, parallel(styles, scripts, images, fonts), watcher);

exports.clean = clean;
exports.styles = styles;
exports.scripts = scripts;
exports.images = images;
exports.fonts = fonts;
exports.build = build;
exports.dev = dev;
exports.watch = series(dev, watcher);
