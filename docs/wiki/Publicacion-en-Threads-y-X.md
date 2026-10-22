# Publicación en Threads y X (Fase 4)

Desde la versión 0.8.0 el botón de publicar de cada pieza se convierte en un **menú por red**: Instagram, Threads, X y "Todas". Cada red se enciende por separado; si solo está encendida Instagram, todo se ve y funciona exactamente como antes.

| Red | Qué se publica | Texto |
| --- | --- | --- |
| 📸 Instagram | El carrusel de láminas (o la historia del día) | El caption de Instagram del redactor |
| 🧵 Threads | Primer post con el carrusel completo (hasta 20 láminas) y el resto del hilo como respuestas encadenadas | El hilo de X del redactor (cada parte cabe en los 500 caracteres de Threads) |
| 𝕏 X | Primer tuit con hasta 4 láminas y el resto del hilo como respuestas | El hilo de X del redactor |

La historia del día solo va a Instagram (ni Threads ni X tienen historias por API), así que su botón sigue siendo uno solo.

## Cómo se ve en Telegram

```
📸 LVBP · Jornada del 2026-10-20

¿Dónde la publico? Te pido confirmación antes.
[📸 Instagram] [🧵 Threads]
[𝕏 X]
[🚀 Todas]
```

1. Tocar una red (o **Todas**) cambia el mensaje a "¿Seguro? Se publica en X ya mismo." con **✅ Sí / ↩️ No**.
2. Con **Sí**, esas redes salen del menú y se dispara `publicar.yml`. Las demás siguen disponibles en el mismo mensaje.
3. El resultado llega como **respuesta** a ese mensaje (si todavía quedaban otras redes en el menú) o **en el mismo mensaje** (si ya no quedaba ninguna): una línea por red con su enlace.
4. Si una red falla, su línea dice por qué y trae **🔁 Reintentar en X**. Las demás no se ven afectadas: cada red se publica por separado.
5. Si un hilo queda a medias (salió el primer post pero falló una respuesta), se marca con ⚠️ y **no** se ofrece reintentar, porque repetiría el primer post. Se completa a mano desde el enlace.

## Encender cada red

Variables del repositorio (**Settings → Secrets and variables → Actions → Variables**):

| Variable | Efecto |
| --- | --- |
| `PUBLICAR_INSTAGRAM = 1` | Botón de Instagram (ya existente) |
| `PUBLICAR_THREADS = 1` | Botón de Threads |
| `PUBLICAR_X = 1` | Botón de X |

**Antes de encender Threads o X hay que actualizar el relé**: pegar el `infra/telegram-relay/worker.js` nuevo en el editor del Worker `mbp-telegram-relay` en Cloudflare y desplegar (o `npx wrangler deploy`). El relé viejo solo entiende los botones de Instagram.

## Threads: configuración

Se usa la misma aplicación de Meta (**MBP Publicador**).

1. En [developers.facebook.com](https://developers.facebook.com/), en la app, **Casos de uso → Agregar caso de uso → Acceder a la API de Threads**.
2. En ese caso de uso, **Permisos**: agregar `threads_basic` y `threads_content_publish`.
3. **Roles de la app → Roles → Agregar personas → Evaluador de Threads**, invitar al perfil de Threads `mbp.deportes`.
4. En la app de Threads: **Configuración → Cuenta → Permisos de sitios web → Invitaciones**, aceptar.
5. En el caso de uso de Threads, **Configuración → Generador de tokens de usuario**: generar el token para `mbp.deportes`.
6. Guardarlo en el `.env` como `THREADS_ACCESS_TOKEN=...` y verificar con `python -m bpt threads-prueba` (muestra la cuenta, el `THREADS_USER_ID` y la cuota; no publica).
7. En GitHub, secretos `THREADS_ACCESS_TOKEN` y, opcional, `THREADS_USER_ID`.

El token dura 60 días. El workflow **Renovar tokens de Instagram y Threads** (cada lunes) lo renueva igual que el de Instagram, con el mismo `GH_PAT_SECRETOS`. Como en Instagram, Meta exige que el token tenga al menos 24 horas antes de renovarlo.

Límites: 250 publicaciones cada 24 horas (un carrusel cuenta como una), imágenes JPEG o PNG de hasta 8 MB, 500 caracteres por post.

## X: configuración

X cobra por uso: no hay plan gratis para cuentas nuevas. Referencia de octubre de 2026: cada post cuesta del orden de US$0,015 y un post **con enlace** cuesta mucho más (alrededor de US$0,20). Un hilo de 4 tuits ronda los US$0,06. Por eso el cliente **rechaza los tuits con URL** antes de llamar a la API, y la publicación en X va con botón propio, para decidir pieza por pieza.

1. Con la sesión de la cuenta de la marca abierta en X, entrar a [console.x.com](https://console.x.com) y crear el proyecto y la app.
2. En la app, **User authentication settings**: permisos **Read and write**, tipo *Web App, Automated App or Bot*, y cualquier URL válida de callback y de sitio (no se usan).
3. En **Keys and tokens**: copiar **API Key** y **API Key Secret**, y luego generar **Access Token** y **Access Token Secret**. Los tokens de acceso deben generarse **después** de dar el permiso *Read and write*; si se generaron antes, regenerarlos.
4. Cargar créditos en la consola (pago por uso).
5. Guardar en el `.env` y como secretos de GitHub: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`.
6. Verificar con `python -m bpt x-prueba` (lee la cuenta; esa lectura también se cobra, aunque poco).

Estos tokens (OAuth 1.0a) no vencen: no hay renovación. Si se filtran, se regeneran en la misma pantalla.

## Especiales

Además del paquete diario, el workflow **Especial MBP** (a mano) arma una publicación desde un JSON de `content/especiales/` (portada, rosters y textos) y la manda a Telegram con el mismo menú de redes. `publicar.yml` acepta sus runs igual que los de resultados. El primero fue `latinos-serie-mundial.json`: el mejor latino por posición entre los que jugaron una Serie Mundial, un roster por liga.

Un especial con `"tipo": "historia"` es una historia de Instagram (una lámina 1080x1920, sin caption): sale por el mismo workflow y llega con el botón 📲, solo para Instagram. La primera fue `rays-banderin-2026.json` (Rays a la Serie Mundial, 19-oct-2026).

Un especial con `laminas` (y `equipos` A/B) es un carrusel por bloques: portada, cifras, barras, cara a cara, camino y figuras. El primero fue `previa-serie-mundial-2026.json` (Rays vs. Cerveceros, 9 láminas).

## Fallas habituales

| Mensaje | Causa | Acción |
| --- | --- | --- |
| "faltan los secretos X_API_KEY…" / "falta el secreto THREADS_ACCESS_TOKEN" | La red se encendió sin cargar sus secretos | Cargar los secretos en GitHub |
| "X rechazó las credenciales" (401) | Claves mal copiadas o regeneradas | Volver a copiar las cuatro |
| "X no permite la acción" (403) | Tokens generados antes del permiso *Read and write*, o tuit repetido | Regenerar Access Token y Secret |
| "la cuenta de desarrollador de X no tiene créditos" (402) | Saldo agotado | Recargar en console.x.com |
| "el tuit N trae un enlace" | El redactor puso una URL en el hilo | Publicar ese hilo a mano o quitar el enlace |
| "el token de Threads venció o es inválido" | Pasaron 60 días sin renovar | Generar uno nuevo y actualizar `THREADS_ACCESS_TOKEN` |
| "hilo incompleto: salieron N de M" | Falló una respuesta del hilo | Completar a mano desde el enlace |
| Botón "Botón desconocido" al tocar Threads o X | El relé en Cloudflare es la versión anterior | Desplegar el `worker.js` nuevo |

## Diseño

- **El relé no guarda estado.** Cada botón lleva todo lo necesario: `pub:<run>:<pieza>:<destino>:<quedan>`, con letras de red (`i`, `t`, `x`). "Quedan" son las redes que tenía el menú, para poder rearmarlo al cancelar o al publicar una sola. Con solo Instagram se usa el formato corto de siempre, `pub:<run>:<pieza>`.
- **Resultado como respuesta.** El workflow no puede leer el mensaje de Telegram, así que, si en el menú quedan otras redes, no lo edita (borraría sus botones): responde debajo.
- **Cada red por separado.** Una red sin secretos o caída no frena a las otras; sus clientes se crean recién al publicar.
- **Duplicados.** Instagram y Threads comparan con los posts recientes y, si ya estaba, devuelven el enlace sin volver a publicar. En X, el rechazo por contenido repetido se informa como tal.
- **Imágenes.** Instagram y Threads descargan los JPEG desde la rama `publicaciones`; a X se le suben los archivos directamente (no necesita la rama si solo se publica en X).

Archivos: `src/bpt/publicar/redes.py` (letras, menú y textos), `threads.py`, `x.py`, `flujo.py` (`publicar_redes`, `avisar_resultados`), el comando `bpt publicar-redes` y `.github/workflows/publicar.yml` (entradas `destino` y `quedan`).
