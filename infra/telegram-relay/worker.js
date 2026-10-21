// Relé de Telegram para MBP (Cloudflare Worker).
//
// Telegram le avisa aquí (webhook) cada vez que se toca un botón del bot. El relé:
//   1. Comprueba que el aviso viene de Telegram (cabecera secreta) y que quien tocó es Noel.
//   2. Botón de una red (o "Todas") -> cambia el mensaje a "¿Seguro?" con Sí / No.
//   3. "Sí"        -> dispara publicar.yml con la pieza y las redes elegidas. Si no quedan
//                     otras redes, el workflow edita este mensaje con el enlace o el error;
//                     si quedan, sus botones siguen aquí y el resultado llega como respuesta.
//   4. "No"        -> vuelve a dejar el menú de redes.
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
// accion:run:pieza  (formato corto: solo Instagram)  o  accion:run:pieza:destino:quedan
// destino y quedan son letras de red: i = Instagram, t = Threads, x = X.
// La pieza "r1", "rjornada"... es el Reel de esa pieza (solo Instagram).
const DATA = /^(pub|ok|no):(\d{1,20}):(r?(?:\d{1,2}|jornada))(?::([itx]{1,3}):([itx]{1,3}))?$/;

// Mismo menú que src/bpt/publicar/redes.py: si cambias un texto allá, cámbialo aquí.
const ORDEN = "itx";
const NOMBRES = { i: "Instagram", t: "Threads", x: "X" };
const BOTON = { i: "📸 Instagram", t: "🧵 Threads", x: "𝕏 X" };

export const normalizar = (s) => [...ORDEN].filter((c) => (s || "").includes(c)).join("");
export const menos = (a, b) => normalizar([...a].filter((c) => !b.includes(c)).join(""));

export function nombres(letras) {
  const n = [...normalizar(letras)].map((c) => NOMBRES[c]);
  return n.length === 1 ? n[0] : `${n.slice(0, -1).join(", ")} y ${n[n.length - 1]}`;
}

export function callback(accion, runId, pieza, destino, quedan) {
  return quedan === "i" && destino === "i"
    ? `${accion}:${runId}:${pieza}`
    : `${accion}:${runId}:${pieza}:${destino}:${quedan}`;
}

export function menu(runId, pieza, quedan, historia = false) {
  quedan = normalizar(quedan);
  if (!quedan) return [];
  if (quedan.length === 1) {
    const texto =
      quedan === "i"
        ? String(pieza).startsWith("r")
          ? "🎬 Publicar Reel en Instagram"
          : historia ? "📲 Publicar historia en Instagram" : "📸 Publicar en Instagram"
        : `${BOTON[quedan]}: publicar`;
    return [[{ text: texto, callback_data: callback("pub", runId, pieza, quedan, quedan) }]];
  }
  const botones = [...quedan].map((c) => ({
    text: BOTON[c],
    callback_data: callback("pub", runId, pieza, c, quedan),
  }));
  const filas = [];
  for (let k = 0; k < botones.length; k += 2) filas.push(botones.slice(k, k + 2));
  filas.push([{ text: "🚀 Todas", callback_data: callback("pub", runId, pieza, quedan, quedan) }]);
  return filas;
}

export const pregunta = (quedan) =>
  normalizar(quedan).length === 1
    ? `¿La subo a ${NOMBRES[normalizar(quedan)]}? Te pido confirmación antes.`
    : "¿Dónde la publico? Te pido confirmación antes.";

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
  const destino = normalizar(m[4] || "i");
  const quedan = normalizar(m[5] || "i");
  const base = String(msg.text || "📸 Pieza").split("\n\n")[0];
  const historia = base.startsWith("📲");
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
    await editar(`${base}\n\n¿Seguro? Se publica en ${nombres(destino)} ya mismo.`, [
      [
        { text: "✅ Sí, publicar", callback_data: callback("ok", runId, pieza, destino, quedan) },
        { text: "↩️ No", callback_data: callback("no", runId, pieza, destino, quedan) },
      ],
    ]);
    return "confirmar";
  }

  if (accion === "no") {
    await tg("answerCallbackQuery", { callback_query_id: cq.id, text: "Cancelado" });
    await editar(`${base}\n\n${pregunta(quedan)}`, menu(runId, pieza, quedan, historia));
    return "cancelado";
  }

  // accion === "ok": primero se quitan esos botones (evita el doble toque) y luego se dispara.
  // Las redes que no se eligieron siguen en el menú; el resultado llega como respuesta.
  const resto = menos(quedan, destino);
  await tg("answerCallbackQuery", { callback_query_id: cq.id, text: "Publicando…" });
  await editar(
    resto
      ? `${base}\n\n⏳ Publicando en ${nombres(destino)}… el resultado te llega abajo.\n\n${pregunta(resto)}`
      : `${base}\n\n⏳ Publicando en ${nombres(destino)}… te aviso aquí mismo.`,
    menu(runId, pieza, resto, historia),
  );
  const inputs = { run_id: runId, pieza, message_id: String(msg.message_id) };
  if (!(destino === "i" && quedan === "i")) {
    inputs.destino = destino;
    inputs.quedan = quedan;
  }
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
      body: JSON.stringify({ ref: env.GITHUB_REF || "main", inputs }),
    },
  );
  if (r.status !== 204) {
    const detalle = (await r.text()).slice(0, 200);
    await editar(`${base}\n\n❌ No pude disparar la publicación en GitHub (HTTP ${r.status}). ${detalle}`, [
      [{ text: "🔁 Reintentar", callback_data: callback("pub", runId, pieza, destino, quedan) }],
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
