// Records a beat-aligned screen-capture tour for the Archon-Nebius demo video.
//
// The public app (https://archon-pnl.web.app) gates the dashboard behind Google
// sign-in, which a CI runner does not have. So this tour COMBINES:
//   * the LIVE public landing page (proves the app is really deployed), and
//   * rendered VISUAL SLIDES (scripts/slides/*.html) that carry the substance —
//     the 3-document fusion / 28% gap, the Nebius architecture, and the measured
//     evaluation results.
//
// The browser records one continuous webm whose timeline is locked to FIXED
// absolute beat windows (BEATS below), matched 1:1 to scripts/captions.txt and
// the ElevenLabs voiceover (docs/narration.txt), so burned captions and VO line
// up frame-for-frame. Render is deviceScaleFactor 2 (supersampled text) at a
// 1920x1080 record size — no ffmpeg upscaling (that blurs and isn't verifiable).
//
// Every interaction is best-effort (safe()) so a missing element on the live
// page never aborts the tour — the timeline still lands on every beat.
import { chromium } from "playwright";
import { pathToFileURL } from "node:url";
import path from "node:path";

const BASE = process.env.BASE_URL || "https://archon-pnl.web.app";
// Absolute end of the closing beat. The fixed beats below never move; only the
// final CTA stretches to TARGET so the recording is always at least as long as
// the (regenerated) voiceover.
const TARGET = parseFloat(process.env.TARGET_SECONDS || "158");

// Slides live next to this script (scripts/slides/*.html). pathToFileURL keeps
// Windows-authored paths valid on the Linux CI runner (no backslash strings).
const slidesDir = path.resolve(process.cwd(), "scripts", "slides");
const slideUrl = (name) => pathToFileURL(path.join(slidesDir, name)).href;

// Fixed absolute beat boundaries (seconds), matched 1:1 to scripts/captions.txt.
const BEATS = {
  LANDING_END: 20, //   0–20   Problem — the LIVE landing page
  FUSION_END: 58, //   20–58   3-doc fusion + the 28% gap  (fusion.html)
  ARCH_END: 98, //   58–98   Nebius Serverless AI architecture (architecture.html)
  RESULTS_END: 138, //  98–138  Measured evaluation results (results.html)
  // 138–TARGET  CTA (cta.html)
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

// ============================================================================
// 0–20s — PROBLEM: the LIVE public landing page (proves real deployment).
// goto + gentle scroll only — DOM-agnostic, no clicks against guessed elements.
// ============================================================================
await safe("goto landing", async () => {
  await page.goto(BASE, { waitUntil: "networkidle", timeout: 45000 });
});
await sleep(3500); // let the SPA mount
await safe("scroll landing", async () => {
  await smoothScrollTo(page, 700, 4000);
  await sleep(700);
  await smoothScrollTo(page, 0, 2500);
});
await waitUntil(BEATS.LANDING_END);

// ============================================================================
// 20–58s — 3-DOC FUSION + THE 28% GAP (slide).
// ============================================================================
await safe("goto fusion slide", async () => {
  await page.goto(slideUrl("fusion.html"), { waitUntil: "load", timeout: 20000 });
});
await waitUntil(BEATS.FUSION_END);

// ============================================================================
// 58–98s — NEBIUS SERVERLESS AI ARCHITECTURE (slide).
// ============================================================================
await safe("goto architecture slide", async () => {
  await page.goto(slideUrl("architecture.html"), { waitUntil: "load", timeout: 20000 });
});
await waitUntil(BEATS.ARCH_END);

// ============================================================================
// 98–138s — MEASURED EVALUATION RESULTS (slide).
// ============================================================================
await safe("goto results slide", async () => {
  await page.goto(slideUrl("results.html"), { waitUntil: "load", timeout: 20000 });
});
await waitUntil(BEATS.RESULTS_END);

// ============================================================================
// 138s–end — CTA (slide); hold until the clock reaches TARGET.
// ============================================================================
await safe("goto cta slide", async () => {
  await page.goto(slideUrl("cta.html"), { waitUntil: "load", timeout: 20000 });
});
await waitUntil(TARGET);

console.log(`tour wall-time: ${elapsed().toFixed(1)}s`);
await ctx.close(); // flushes the webm
await browser.close();
