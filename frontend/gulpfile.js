const gulp = require("gulp");
const sass = require("gulp-sass")(require("sass"));
const cleanCSS = require("gulp-clean-css");
const autoprefixer = require("gulp-autoprefixer").default;
const sourcemaps = require("gulp-sourcemaps");
const rename = require("gulp-rename");
const terser = require("gulp-terser");

// Rutas
const paths = {
    scss: "./src/**/*.scss",
    js: "./src/js/**/*.js",
    images: "./src/image/**/*.{png,jpg,jpeg,gif,svg}",
    cssDest: "./static/dist/css",
    jsDest: "./static/dist/js",
    imgDest: "./static/dist/img",
};

// Compilar Sass
function styles() {
    return gulp.src(paths.scss)
        .pipe(sourcemaps.init())
        .pipe(sass().on("error", sass.logError))
        .pipe(autoprefixer())
        .pipe(cleanCSS())
        .pipe(rename({ suffix: ".min" }))
        .pipe(sourcemaps.write("."))
        .pipe(gulp.dest(paths.cssDest));
}

// JS
function scripts() {
    return gulp.src(paths.js)
        .pipe(sourcemaps.init())
        .pipe(terser())
        .pipe(rename({ suffix: ".min" }))
        .pipe(sourcemaps.write("."))
        .pipe(gulp.dest(paths.jsDest));
}

// Imágenes
async function images() {
    const { default: imagemin } = await import("gulp-imagemin");
    return gulp.src(paths.images)
        .pipe(imagemin())
        .pipe(gulp.dest(paths.imgDest));
}

// Watch
function watchFiles() {
    gulp.watch(paths.scss, styles);
    gulp.watch(paths.js, scripts);
    gulp.watch(paths.images, images);
}

exports.styles = styles;
exports.scripts = scripts;
exports.images = images;
exports.watch = gulp.series(gulp.parallel(styles, scripts, images), watchFiles);
exports.build = gulp.parallel(styles, scripts, images);
