// Relé de Telegram para MBP (Cloudflare Worker).
//
// Telegram le avisa aquí (webhook) cada vez que se toca un botón del bot. El relé:
//   1. Comprueba que el aviso viene de Telegram (cabecera secreta) y que quien tocó es Noel.
//   2. "Publicar"  -> cambia el mensaje a "¿Seguro?" con dos botones (Sí / No).
//   3. "Sí"        -> dispara el workflow publicar.yml en GitHub y deja el mensaje en
//                     "Publicando…"; el workflow lo edita al final con el enlace o el error.
//   4. "No"        -> vuelve a dejar el botón "Publicar".
// No guarda nada ni publica nada por su cuenta: solo traduce un toque en un workflow_dispatch.
//
// Variables (Settings > Variables and Secrets del Worker, todas como "Secret"):
//   TELEGRAM_BOT_TOKEN      token del bot (@BotFather)
//   TELEGRAM_WEBHOOK_SECRET el mismo valor usado en setWebhook (bpt telegram-webhook)
//   TELEGRAM_CHAT_ID        tu chat: solo tú puedes tocar los botones
//   GITHUB_TOKEN            token fine-grained del repo con permiso Actions: Read and write
//   GITHUB_REPO             nolotov/beisbol-para-todos   (puede ser variable normal)
//   GITHUB_REF              main                         (opcional, por defecto main)

const WORKFLOW = "publicar.yml";
const DATA = /^(pub|ok|no):(\d{1,20}):(\d{1,2}|jornada)$/;

export default {
  async fetch(request, env) {
    if (request.method === "GET") return new Response("MBP relay ok");
    if (request.method !== "POST") return new Response("método no permitido", { status: 405 });

    const secreto = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (!env.TELEGRAM_WEBHOOK_SECRET || secreto !== env.TELEGRAM_WEBHOOK_SECRET) {
      return new Response("no autorizado", { status: 401 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("ok");
    }
    const cq = update.callback_query;
    if (!cq) return new Response("ok"); // mensajes normales: se ignoran

    try {
      await atender(cq, env);
    } catch (e) {
      // Siempre 200: si no, Telegram reintenta el mismo toque una y otra vez.
      console.log("error atendiendo el toque:", String(e && e.message ? e.message : e));
    }
    return new Response("ok");
  },
};

export async function atender(cq, env, http = fetch) {
  const tg = (metodo, cuerpo) => telegram(env, metodo, cuerpo, http);
  const permitido = String(env.TELEGRAM_CHAT_ID || "").trim();

  if (String(cq.from && cq.from.id) !== permitido) {
    await tg("answerCallbackQuery", { callback_query_id: cq.id, text: "No autorizado" });
    return "no-autorizado";
  }

  const m = DATA.exec(cq.data || "");
  const msg = cq.message || {};
  if (!m || !msg.message_id) {
    await tg("answerCallbackQuery", { callback_query_id: cq.id, text: "Botón desconocido" });
    return "desconocido";
  }
  const [, accion, runId, pieza] = m;
  const base = String(msg.text || "📸 Pieza").split("\n\n")[0];
  const editar = (texto, filas) =>
    tg("editMessageText", {
      chat_id: msg.chat.id,
      message_id: msg.message_id,
      text: texto,
      disable_web_page_preview: true,
      reply_markup: { inline_keyboard: filas || [] },
    });

  if (accion === "pub") {
    await tg("answerCallbackQuery", { callback_query_id: cq.id });
    await editar(`${base}\n\n¿Seguro? Se publica en Instagram ya mismo.`, [
      [
        { text: "✅ Sí, publicar", callback_data: `ok:${runId}:${pieza}` },
        { text: "↩️ No", callback_data: `no:${runId}:${pieza}` },
      ],
    ]);
    return "confirmar";
  }

  if (accion === "no") {
    await tg("answerCallbackQuery", { callback_query_id: cq.id, text: "Cancelado" });
    await editar(`${base}\n\n¿La subo a Instagram? Te pido confirmación antes.`, [
      [{ text: "📸 Publicar en Instagram", callback_data: `pub:${runId}:${pieza}` }],
    ]);
    return "cancelado";
  }

  // accion === "ok": primero se quitan los botones (evita el doble toque) y luego se dispara.
  await tg("answerCallbackQuery", { callback_query_id: cq.id, text: "Publicando…" });
  await editar(`${base}\n\n⏳ Publicando en Instagram… te aviso aquí mismo.`);
  const r = await http(
    `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "mbp-telegram-relay",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ref: env.GITHUB_REF || "main",
        inputs: {
          run_id: runId,
          pieza,
          message_id: String(msg.message_id),
        },
      }),
    },
  );
  if (r.status !== 204) {
    const detalle = (await r.text()).slice(0, 200);
    await editar(`${base}\n\n❌ No pude disparar la publicación en GitHub (HTTP ${r.status}). ${detalle}`, [
      [{ text: "🔁 Reintentar", callback_data: `pub:${runId}:${pieza}` }],
    ]);
    return "error-github";
  }
  return "disparado";
}

async function telegram(env, metodo, cuerpo, http) {
  const r = await http(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${metodo}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo),
  });
  const json = await r.json().catch(() => ({}));
  if (!json.ok && !/message is not modified/.test(json.description || "")) {
    throw new Error(`${metodo}: ${json.description || r.status}`);
  }
  return json.result;
}
