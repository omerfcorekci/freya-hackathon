// Mock of Freya Bank's services for the final case. Paths, field names and shapes follow the bank's integration
// document; the test customers answer exactly as the pack lists them, HTTP status included. Hand-written by the team
// (the brief asks for it); the phone agent's tools call only this Worker.

import { routes } from "./routes.js";

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8" } });
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    if (path === "/health") return json({ ok: true, service: "freya-bank-mock", time: new Date().toISOString() });
    let body = null;
    if (request.method !== "GET") {
      try { body = await request.json(); } catch (e) { body = null; }
    }
    for (const r of routes) {
      const m = path.match(r.pattern);
      if (m && r.method === request.method) {
        try { return r.handle({ params: m.groups || {}, query: url.searchParams, body, json }); }
        catch (e) { return json({ error: "internal", message: String(e) }, 500); }
      }
    }
    return json({ error: "not_found", path, method: request.method }, 404);
  },
};
