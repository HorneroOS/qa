# AI4Devs — HorneroOS Studio en ASUS ROG Strix G16 (pelicano)

Artefactos de producción para el evento. Separación obligatoria:
**release readiness ≠ hardware verificado ≠ evento listo.** Nada acá
afirma compatibilidad física sin evidencia ejecutada en la máquina real.

## Estado (2026-10-30)

| Área | Estado | Evidencia |
| --- | --- | --- |
| A. Studio release readiness | PASS (VM) | preview25: Studio+Hyprland en VM desechable, `horneroctl studio doctor` 5/5, OBS grabó y finalizó archivo H.264/AAC reproducible |
| B. ASUS G615LR hardware | NOT TESTED | falta inventario real: correr `scripts/asus-diagnostic.sh` en pelicano |
| C. Producción A/V AI4Devs | NOT TESTED | Scarlett/Phonic/cámaras/captura HDMI sin conectar todavía |
| D. Aprobación como máquina principal | NO-GO por ahora | usar el fallback conocido hasta que B y C pasen |

## Seguridad de audio (CRÍTICO)

**NUNCA conectar la salida SPEAKER/POWER AMP del Phonic Powerpod a la
Scarlett.** La Scarlett recibe solo nivel de línea: Phonic **REC OUT**
L/R → entradas de línea de la Scarlett (modo LINE, phantom OFF, Air OFF,
ganancia baja al principio). El RØDE NT1 directo a la Scarlett sí usa
phantom 48V en esa entrada puntual; no habilitar 48V sobre la señal del
mixer.

Topología de video: laptop de presentación HDMI → splitter → proyector
y → captura HDMI USB → pelicano (OBS). El puerto HDMI de la ASUS es
salida, no entrada de captura.

## Perfil OBS AI4Devs (base conservadora, sin secretos)

- Lienzo/salida 1920×1080, 30 fps, audio 48 kHz.
- Grabación local MKV (resiliente a cortes), H.264 NVENC solo si se
  verifica en hardware; fallback x264 probado en VM.
- Streaming CBR ~6000 kbps solo tras test privado con red cableada.
- Escenas: Inicio, Diapositivas, Cámara presentador, Diapositivas+PiP,
  Audiencia/Q&A, Pausa, Cierre, Emergencia. Assets locales.

## Runbook corto

1. Boot y login reales; `horneroctl studio doctor`.
2. Conectar Scarlett (verificar en `wpctl status`, 48 kHz).
3. Conectar cámaras/captura; verificar `/dev/video*` y en OBS.
4. Prueba de grabación local: reproducir el archivo completo.
5. Test privado de stream (nunca público sin aprobación).
6. Ensayo sostenido 30–60 min con cambio de escenas y reconexión de una
   fuente no crítica.
7. Si cualquier gate crítico falla: máquina fallback para el evento.

## Fallback

La máquina Arch/OBS ya conocida queda como principal hasta que B y C
sean PASS con evidencia. Este evento no es el primer test de producción
de HorneroOS.
