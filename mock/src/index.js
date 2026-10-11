// Mock of Freya Bank's statement services for the final case, on Cloudflare Workers. Paths, field names and shapes
// follow the bank's service contract (`sources/documents/2026-10-01-service-contract.md`: request {data, call},
// response {data, result}); every test customer answers exactly what `test-environment/test-customers.json` lists,
// HTTP status and delay included. Hand-written by the team; the phone agent's tools call only this Worker.

import { routes } from "./routes.js";

const CORS = { "Access-Control-Allow-Origin": "*" };

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { ...CORS, "content-type": "application/json; charset=utf-8" } });
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: { ...CORS, "Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Access-Control-Allow-Headers": "*" } });
    }
    if (path === "/health" || path === "/") return json({ ok: true, durum: "ok", service: "freya-bank-mock", time: new Date().toISOString() });
    let body = null;
    if (request.method !== "GET") {
      try { body = await request.json(); } catch (e) { body = null; }
    }
    for (const r of routes) {
      if (r.method === request.method && r.paths.includes(path)) {
        try { return await r.handle({ query: url.searchParams, body, json }); }
        catch (e) { return json({ result: { returnCode: "FBE00099", messageText: "Teknik hata: " + String(e), code: "FBE00099", message: "Teknik hata" } }, 500); }
      }
    }
    return json({ result: { returnCode: "FB_IVR_CHANNEL_404", messageText: "Servis bulunamadı: " + request.method + " " + path, code: "FB_IVR_CHANNEL_404", message: "Servis bulunamadı" },
                  yollar: routes.map((r) => r.method + " " + r.paths[0]) }, 404);
  },
};
