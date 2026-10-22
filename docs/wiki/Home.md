# Beisbol Para Todos · Wiki

Toolkit de datos y visualización de **@mbp.deportes**: análisis sabermétrico de MLB y LVBP.

## Páginas

- [Arquitectura del agente de resultados](Arquitectura-del-agente-de-resultados): cómo funciona el pipeline diario (datos, láminas, redacción con Claude, validación y entrega por Telegram), las decisiones de diseño, la operación y los costos.
- [Publicación en Instagram](Publicacion-en-Instagram): el botón de Telegram que publica una pieza aprobada (Fase 4), su configuración inicial, la operación y la seguridad.
- [Publicación en Threads y X](Publicacion-en-Threads-y-X): el menú de botones por red, cómo se encienden Threads y X, sus credenciales, costos y fallas habituales.
- [Editor, métricas y Reels](Editor-metricas-y-Reels): el verificador de especiales, el agente editor, el circuito de métricas y los Reels con voz (versiones 0.12 a 0.15), con lo que hay que configurar.

## Enlaces rápidos

- Instalación y comandos: [README](https://github.com/nolotov/beisbol-para-todos#readme)
- Workflows: `.github/workflows/resultados-mlb.yml`, `resultados-lvbp.yml`, `publicar.yml`, `instagram-token.yml`, `editor.yml` y `metricas.yml`
- Relé de Telegram: `infra/telegram-relay/worker.js`
