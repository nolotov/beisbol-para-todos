# Beisbol Para Todos · Wiki

Toolkit de datos y visualización de **@mbp.deportes**: análisis sabermétrico de MLB y LVBP.

## Páginas

- [Arquitectura del agente de resultados](Arquitectura-del-agente-de-resultados): cómo funciona el pipeline diario (datos, láminas, redacción con Claude, validación y entrega por Telegram), las decisiones de diseño, la operación y los costos.
- [Publicación en Instagram](Publicacion-en-Instagram): el botón de Telegram que publica una pieza aprobada (Fase 4), su configuración inicial, la operación y la seguridad.

## Enlaces rápidos

- Instalación y comandos: [README](https://github.com/nolotov/beisbol-para-todos#readme)
- Workflows: `.github/workflows/resultados-mlb.yml`, `resultados-lvbp.yml`, `publicar.yml` e `instagram-token.yml`
- Relé de Telegram: `infra/telegram-relay/worker.js`
