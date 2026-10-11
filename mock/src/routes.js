// Data-driven routes: every service answers exactly what the pack lists for the test customer (status, body, delay).
import data from "./data.json";

const sleep = (s) => new Promise((r) => setTimeout(r, s * 1000));

function failure(status, code, text) {
  return { result: { guid: "mock-" + Date.now().toString(16), returnCode: code, messageText: text, code, message: text, type: null,
                     details: { guid: "mock", rootCause: null, errorOrigin: null } } };
}

function field(body, query, name) {
  const v = body && body[name] !== undefined ? body[name] : query.get(name);
  return v === null || v === undefined ? "" : String(v);
}

export const routes = Object.entries(data.services).map(([name, svc]) => ({
  method: svc.method,
  pattern: new RegExp("^" + svc.path.replace(/\//g, "\\/") + "$"),
  async handle({ query, body, json }) {
    const no = field(body, query, svc.keys[0]);
    const customer = data.customers[no];
    if (!customer) return json(failure("FB_IVR_CHANNEL_001", "FB_IVR_CHANNEL_001", "Müşteri bulunamadı."), 404);
    const table = customer.services[name];
    if (!table) return json(failure("FB_IVR_CHANNEL_002", "FB_IVR_CHANNEL_002", "Servis bu müşteri için tanımlı değil."), 404);
    const key = svc.keys.slice(1).map((k) => field(body, query, k)).join("|");
    let answer = table[key];
    if (!answer && svc.keys.length > 1) {
      // tolerate a card given by its last four digits or without the mask, and a week given as a number
      const want = svc.keys.slice(1).map((k) => field(body, query, k));
      for (const [k, a] of Object.entries(table)) {
        const parts = k.split("|");
        const ok = parts.every((p, i) => p === want[i] || (p.endsWith(want[i]) && want[i].length >= 4) || p.replace(/\D/g, "").endsWith(want[i].replace(/\D/g, "")) && want[i].replace(/\D/g, "").length >= 4);
        if (ok) { answer = a; break; }
      }
    }
    if (!answer) return json(failure("FB_IVR_CHANNEL_003", "FB_IVR_CHANNEL_003", "Kayıt bulunamadı."), 404);
    if (answer.delay) await sleep(Math.min(answer.delay, 25));
    return json(answer.body, answer.http);
  },
}));
