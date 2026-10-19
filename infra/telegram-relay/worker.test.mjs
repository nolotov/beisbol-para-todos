// Pruebas del relé sin red: node --test infra/telegram-relay/worker.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import worker, { atender, menu, nombres, menos } from "./worker.js";

const ENV = {
  TELEGRAM_BOT_TOKEN: "123:abc",
  TELEGRAM_WEBHOOK_SECRET: "s3creto",
  TELEGRAM_CHAT_ID: "42",
  GITHUB_TOKEN: "github_pat_x",
  GITHUB_REPO: "nolotov/beisbol-para-todos",
};

function httpFalso(estadoGithub = 204) {
  const llamadas = [];
  const http = async (url, opts) => {
    const cuerpo = opts && opts.body ? JSON.parse(opts.body) : null;
    llamadas.push({ url, cuerpo, headers: opts && opts.headers });
    if (url.includes("api.github.com")) {
      return { status: estadoGithub, text: async () => "detalle" };
    }
    return { status: 200, json: async () => ({ ok: true, result: {} }) };
  };
  return { http, llamadas };
}

const toque = (data, from = 42) => ({
  id: "cb1",
  from: { id: from },
  data,
  message: { message_id: 7, chat: { id: 42 }, text: "📸 LVBP · Jornada\n\n¿La subo a Instagram?" },
});

test("rechaza a quien no es el dueño del chat", async () => {
  const { http, llamadas } = httpFalso();
  assert.equal(await atender(toque("ok:1:jornada", 99), ENV, http), "no-autorizado");
  assert.ok(!llamadas.some((l) => l.url.includes("github")));
});

test("Publicar pide confirmación sin disparar nada", async () => {
  const { http, llamadas } = httpFalso();
  assert.equal(await atender(toque("pub:123:jornada"), ENV, http), "confirmar");
  const ed = llamadas.find((l) => l.url.endsWith("editMessageText"));
  assert.match(ed.cuerpo.text, /^📸 LVBP · Jornada\n\n¿Seguro\?/);
  assert.deepEqual(ed.cuerpo.reply_markup.inline_keyboard[0].map((b) => b.callback_data),
    ["ok:123:jornada", "no:123:jornada"]);
  assert.ok(!llamadas.some((l) => l.url.includes("github")));
});

test("Sí dispara publicar.yml con la pieza y quita los botones antes", async () => {
  const { http, llamadas } = httpFalso();
  assert.equal(await atender(toque("ok:123:2"), ENV, http), "disparado");
  const iEd = llamadas.findIndex((l) => l.url.endsWith("editMessageText"));
  const iGh = llamadas.findIndex((l) => l.url.includes("api.github.com"));
  assert.ok(iEd < iGh, "primero se editan los botones");
  assert.deepEqual(llamadas[iEd].cuerpo.reply_markup.inline_keyboard, []);
  const gh = llamadas[iGh];
  assert.match(gh.url, /actions\/workflows\/publicar\.yml\/dispatches$/);
  assert.deepEqual(gh.cuerpo, { ref: "main", inputs: { run_id: "123", pieza: "2", message_id: "7" } });
  assert.equal(gh.headers.Authorization, "Bearer github_pat_x");
});

test("si GitHub falla, ofrece reintentar", async () => {
  const { http, llamadas } = httpFalso(403);
  assert.equal(await atender(toque("ok:123:jornada"), ENV, http), "error-github");
  const ultima = llamadas.filter((l) => l.url.endsWith("editMessageText")).pop();
  assert.match(ultima.cuerpo.text, /HTTP 403/);
  assert.equal(ultima.cuerpo.reply_markup.inline_keyboard[0][0].callback_data, "pub:123:jornada");
});

test("callback con forma rara se ignora", async () => {
  const { http, llamadas } = httpFalso();
  assert.equal(await atender(toque("ok:123:../../x"), ENV, http), "desconocido");
  assert.ok(!llamadas.some((l) => l.url.includes("github")));
});

test("el webhook sin la cabecera secreta devuelve 401", async () => {
  const req = new Request("https://relay.example/", { method: "POST", body: "{}" });
  assert.equal((await worker.fetch(req, ENV)).status, 401);
});

// --- Varias redes (Instagram, Threads, X) ----------------------------------------

test("menú de varias redes: de a dos por fila y Todas abajo", () => {
  const filas = menu("123", "2", "itx");
  assert.deepEqual(filas.map((f) => f.map((b) => b.callback_data)), [
    ["pub:123:2:i:itx", "pub:123:2:t:itx"],
    ["pub:123:2:x:itx"],
    ["pub:123:2:itx:itx"],
  ]);
  assert.equal(nombres("xti"), "Instagram, Threads y X");
  assert.equal(menos("itx", "t"), "ix");
  assert.deepEqual(menu("1", "jornada", "i", true)[0][0],
    { text: "📲 Publicar historia en Instagram", callback_data: "pub:1:jornada" });
});

test("confirmación de X conserva destino y quedan", async () => {
  const { http, llamadas } = httpFalso();
  assert.equal(await atender(toque("pub:123:2:x:itx"), ENV, http), "confirmar");
  const ed = llamadas.find((l) => l.url.endsWith("editMessageText"));
  assert.match(ed.cuerpo.text, /Se publica en X ya mismo/);
  assert.deepEqual(ed.cuerpo.reply_markup.inline_keyboard[0].map((b) => b.callback_data),
    ["ok:123:2:x:itx", "no:123:2:x:itx"]);
});

test("Sí en X deja Instagram y Threads en el menú y manda destino/quedan", async () => {
  const { http, llamadas } = httpFalso();
  assert.equal(await atender(toque("ok:123:2:x:itx"), ENV, http), "disparado");
  const ed = llamadas.find((l) => l.url.endsWith("editMessageText"));
  assert.match(ed.cuerpo.text, /Publicando en X… el resultado te llega abajo/);
  assert.deepEqual(ed.cuerpo.reply_markup.inline_keyboard.flat().map((b) => b.callback_data),
    ["pub:123:2:i:it", "pub:123:2:t:it", "pub:123:2:it:it"]);
  const gh = llamadas.find((l) => l.url.includes("api.github.com"));
  assert.deepEqual(gh.cuerpo.inputs,
    { run_id: "123", pieza: "2", message_id: "7", destino: "x", quedan: "itx" });
});

test("Todas no deja botones y avisa en el mismo mensaje", async () => {
  const { http, llamadas } = httpFalso();
  await atender(toque("ok:9:jornada:itx:itx"), ENV, http);
  const ed = llamadas.find((l) => l.url.endsWith("editMessageText"));
  assert.match(ed.cuerpo.text, /Instagram, Threads y X… te aviso aquí mismo/);
  assert.deepEqual(ed.cuerpo.reply_markup.inline_keyboard, []);
});

test("No vuelve al menú de las redes que quedaban", async () => {
  const { http, llamadas } = httpFalso();
  assert.equal(await atender(toque("no:5:1:t:tx"), ENV, http), "cancelado");
  const ed = llamadas.find((l) => l.url.endsWith("editMessageText"));
  assert.match(ed.cuerpo.text, /¿Dónde la publico\?/);
  assert.equal(ed.cuerpo.reply_markup.inline_keyboard.flat().length, 3);
});

test("letras de red raras se rechazan", async () => {
  const { http } = httpFalso();
  assert.equal(await atender(toque("pub:1:2:z:itx"), ENV, http), "desconocido");
  assert.equal(await atender(toque("pub:1:2:i:"), ENV, http), "desconocido");
});
