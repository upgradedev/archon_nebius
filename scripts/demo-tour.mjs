// Records a beat-aligned screen-capture tour for the Archon-Nebius demo video.
//
// The public app (https://archon-pnl.web.app) gates the dashboard behind Google
// sign-in, which a CI runner does not have — so a naive capture only ever shows
// the login page. Instead this tour opens the app in DEMO MODE (APP_URL with
// ?demo=1: the real dashboard rendered from seeded fixtures, no backend, no
// auth) and records the ACTUAL dashboard for the opening app segment — the P&L,
// the payroll-gap insight (bank net vs true employer cost), and the R1–R4
// validation ledger. It then combines that with:
//   * rendered VISUAL SLIDES (scripts/slides/*.html) that carry the substance —
//     the 3-document fusion / 72% gap, the anatomy of the full ~72% understatement,
//     the Nebius architecture, the evaluation methodology, the measured results,
//     the R1–R4 cross-document validation, and the reproducibility story.
//
// The browser records one continuous webm whose timeline is locked to FIXED
// absolute beat windows (BEATS below), matched 1:1 to scripts/captions.txt and
// the ElevenLabs voiceover (docs/narration.txt), so burned captions and VO line
// up frame-for-frame. Render is deviceScaleFactor 2 (supersampled text) at a
// 1920x1080 record size — no ffmpeg upscaling (that blurs and isn't verifiable).
//
// This is the LONGER, more ANALYTICAL cut: ~5–6 min (the Nebius target is 3–10 min).
//
// Every interaction is best-effort (safe()) so a missing element on the live
// page never aborts the tour — the timeline still lands on every beat.
import { chromium } from "playwright";
import { pathToFileURL } from "node:url";
import path from "node:path";

// The app to record for the opening segment. In CI this is a locally-built,
// locally-served frontend in demo mode (http://127.0.0.1:4173/?demo=1) so the
// REAL dashboard renders without auth or a backend. Falls back to the live app
// in demo mode for a local dry-run.
const APP_URL = process.env.APP_URL || "https://archon-pnl.web.app/?demo=1";
// Absolute end of the closing beat. The fixed beats below never move; only the
// final CTA stretches to TARGET so the recording is always at least as long as
// the (regenerated) voiceover. The default mirrors the workflow's duration FLOOR
// (CTA_START 300 + CTA_HOLD 14) so a local dry-run records the full scripted tour
// even with a silent voiceover stand-in.
const TARGET = parseFloat(process.env.TARGET_SECONDS || "314");

// Slides live next to this script (scripts/slides/*.html). pathToFileURL keeps
// Windows-authored paths valid on the Linux CI runner (no backslash strings).
const slidesDir = path.resolve(process.cwd(), "scripts", "slides");
const slideUrl = (name) => pathToFileURL(path.join(slidesDir, name)).href;

// Fixed absolute beat boundaries (seconds), matched 1:1 to scripts/captions.txt.
const BEATS = {
  LANDING_END: 24, //    0–24   Problem — the LIVE landing page
  FUSION_END: 60, //    24–60   3-doc fusion + the 72% headline    (fusion.html)
  MECH_END: 96, //      60–96   Anatomy of the ~72% gap            (fusion-mechanics.html)
  ARCH_END: 138, //     96–138  Nebius Serverless AI architecture  (architecture.html)
  EVALM_END: 180, //   138–180  How the eval harness measures      (eval-method.html)
  RESULTS_END: 222, // 180–222  Measured evaluation results        (results.html)
  VALID_END: 264, //   222–264  Cross-document validation R1–R4    (validation.html)
  REPRO_END: 300, //   264–300  Reproducible by design             (reproducibility.html)
  // 300–TARGET  CTA (cta.html)
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const t0 = Date.now();
const elapsed = () => (Date.now() - t0) / 1000;

async function safe(label, fn) {
  try {
    await fn();
  } catch (e) {
    console.log(`step skipped [${label}]: ${e.message}`);
  }
}

// Sleep until the tour clock reaches `sec` (no-op if already past it).
async function waitUntil(sec) {
  const ms = sec * 1000 - (Date.now() - t0);
  if (ms > 0) await sleep(ms);
}

// Smoothly scroll the window to an absolute Y over `ms` (ease-in-out).
async function smoothScrollTo(page, y, ms) {
  await page.evaluate(
    ([targetY, dur]) =>
      new Promise((res) => {
        const startY = window.scrollY;
        const dist = targetY - startY;
        const start = performance.now();
        function step(now) {
          const p = Math.min((now - start) / dur, 1);
          const eased = 0.5 - Math.cos(p * Math.PI) / 2;
          window.scrollTo(0, startY + dist * eased);
          if (p < 1) requestAnimationFrame(step);
          else res();
        }
        requestAnimationFrame(step);
      }),
    [y, ms],
  );
}

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  deviceScaleFactor: 2, // supersample text; record stays 1920x1080
  recordVideo: { dir: "video", size: { width: 1920, height: 1080 } },
});
const page = await ctx.newPage();

// Helper: jump to a slide and hold until the tour clock reaches `until`.
async function showSlide(label, file, until) {
  await safe(`goto ${label}`, async () => {
    await page.goto(slideUrl(file), { waitUntil: "load", timeout: 20000 });
  });
  await waitUntil(until);
}

// ============================================================================
// 0–24s — PROBLEM: the REAL dashboard in demo mode (P&L → payroll-gap → R1–R4).
// This is the app segment. Unlike the slides, the dashboard MUST actually render
// — a blank capture here is the whole failure we are fixing — so this beat is
// HARD-CHECKED (throws, not safe()) and saves a proof screenshot for the CI run.
// ============================================================================
await page.goto(APP_URL, { waitUntil: "networkidle", timeout: 45000 });
// Hard-gate: the dashboard's own elements must be present, or fail the tour.
await page.getByText("True employer cost").first().waitFor({ timeout: 25000 });
await page.getByText("Cross-document validation", { exact: false }).first()
  .waitFor({ timeout: 25000 });
// A Recharts series must have actually drawn an SVG path (not an empty box).
await page.waitForFunction(
  () => document.querySelectorAll("svg.recharts-surface path").length > 0,
  { timeout: 25000 },
);
await sleep(1500); // let chart animations settle before the proof frame
await page.screenshot({ path: "video/dashboard-proof.png" }); // uploaded by CI
console.log("dashboard beat verified: P&L + payroll-gap + R1–R4 all rendered");

// Walk the dashboard within the opening beat: top (P&L + payroll gap) → charts
// → the R1–R4 validation ledger at the bottom. Timings fit inside [0, 24].
await sleep(3500); // hold the top — metrics + payroll-gap headline
await safe("scroll to charts", async () => {
  await smoothScrollTo(page, 640, 3500); // P&L bars + expense breakdown
});
await sleep(2600);
await safe("scroll to ledger", async () => {
  await smoothScrollTo(page, 1500, 3500); // cash flow + exec summary + R1–R4
});
await sleep(2400);
await safe("scroll back to top", async () => {
  await smoothScrollTo(page, 0, 2500);
});
await waitUntil(BEATS.LANDING_END);

// ============================================================================
// 24–60s   — 3-DOC FUSION + THE 72% HEADLINE (slide).
// 60–96s   — ANATOMY OF THE FULL ~72% GAP (slide).
// 96–138s  — NEBIUS SERVERLESS AI ARCHITECTURE (slide).
// 138–180s — HOW THE EVAL HARNESS MEASURES (slide).
// 180–222s — MEASURED EVALUATION RESULTS (slide).
// 222–264s — CROSS-DOCUMENT VALIDATION R1–R4 (slide).
// 264–300s — REPRODUCIBLE BY DESIGN (slide).
// ============================================================================
await showSlide("fusion slide", "fusion.html", BEATS.FUSION_END);
await showSlide("fusion-mechanics slide", "fusion-mechanics.html", BEATS.MECH_END);
await showSlide("architecture slide", "architecture.html", BEATS.ARCH_END);
await showSlide("eval-method slide", "eval-method.html", BEATS.EVALM_END);
await showSlide("results slide", "results.html", BEATS.RESULTS_END);
await showSlide("validation slide", "validation.html", BEATS.VALID_END);
await showSlide("reproducibility slide", "reproducibility.html", BEATS.REPRO_END);

// ============================================================================
// 300s–end — CTA (slide); hold until the clock reaches TARGET.
// ============================================================================
await showSlide("cta slide", "cta.html", TARGET);

console.log(`tour wall-time: ${elapsed().toFixed(1)}s`);
await ctx.close(); // flushes the webm
await browser.close();
