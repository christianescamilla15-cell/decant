#!/usr/bin/env bash
# Ciclo completo del legado y su radiografía, con tiempos por paso. Es exactamente lo que corre el CI.
#
#   DECANT_SA_PASSWORD='…' ./ciclo.sh
#
# Levanta el legado (docker compose), crea el esquema, genera y carga 3 años (con sus archivos de interfaz),
# arranca la pantalla, toma el respaldo FECHADO con lo que el legado publicaba, inyecta el delta del mismo día
# (legado vivo), extrae ese delta también por la pantalla, restaura el respaldo en un contenedor LIMPIO, lo
# radiografía, mide cada hallazgo fuera del catálogo y la detección contra el catálogo de trampas.
set -euo pipefail
: "${DECANT_SA_PASSWORD:?define DECANT_SA_PASSWORD (contraseña de sa del contenedor del legado)}"
PY=${PYTHON:-python}
PUERTO_PANTALLA=${DECANT_PUERTO_PANTALLA:-8080}
mkdir -p legado/datos
TIEMPOS=legado/datos/tiempos.txt
: > "$TIEMPOS"

paso() {
  local nombre=$1; shift
  echo "── $nombre"
  local t0; t0=$(date +%s%N)
  "$@"
  local ms=$(( ($(date +%s%N) - t0) / 1000000 ))
  printf '%-30s %7d.%01d s\n' "$nombre" $((ms / 1000)) $(((ms % 1000) / 100)) | tee -a "$TIEMPOS"
}

pantalla() {
  "$PY" -m legado pantalla --puerto "$PUERTO_PANTALLA" > legado/datos/pantalla.log 2>&1 &
  echo $! > legado/datos/pantalla.pid
  for _ in $(seq 1 30); do
    if "$PY" -c "import http.client as h; c = h.HTTPConnection('127.0.0.1', $PUERTO_PANTALLA, timeout=2); \
c.request('GET', '/salud'); raise SystemExit(c.getresponse().status != 200)" 2>/dev/null; then return 0; fi
    sleep 1
  done
  cat legado/datos/pantalla.log; return 1
}

ultimo_manifiesto() {
  local manifiestos=(respaldos/respaldo_*.json)          # el glob sale ordenado: el último es el más reciente
  echo "${manifiestos[-1]}"
}

delta_por_pantalla() {
  local fecha; fecha=$(basename "$(ultimo_manifiesto)" .json); fecha=${fecha#respaldo_}
  "$PY" -m legado.extraer_pantalla --pantalla "http://127.0.0.1:$PUERTO_PANTALLA/" --fecha "$fecha" \
    --salida "legado/datos/delta_por_pantalla_$fecha.jsonl"
}

detener_pantalla() {
  if [ -f legado/datos/pantalla.pid ]; then kill "$(cat legado/datos/pantalla.pid)" 2>/dev/null || true; fi
}
trap detener_pantalla EXIT

paso 'levantar legado'           docker compose -f legado/docker-compose.yml up -d --wait
paso 'esquema'                   "$PY" -m legado esquema --recrear
paso 'generar y cargar'          "$PY" -m legado cargar
paso 'pantalla'                  pantalla
paso 'respaldar'                 "$PY" -m legado respaldar --pantalla "http://127.0.0.1:$PUERTO_PANTALLA/"
paso 'legado vivo'               "$PY" -m legado.vivo
paso 'delta por la pantalla'     delta_por_pantalla
paso 'restaurar y radiografiar'  "$PY" -m radiografia --manifiesto "$(ultimo_manifiesto)"
paso 'veredictos medidos'        "$PY" -m radiografia.veredictos --manifiesto "$(ultimo_manifiesto)"
paso 'medir contra los catálogos' "$PY" -m radiografia.medicion --minimo 88 --trampas legado/TRAMPAS.md \
  --trampas legado/TRAMPAS_CIEGAS.md --conocido legado/TRAMPAS_CIEGAS.md \
  --trampas legado/TRAMPAS_CIEGAS_2.md --conocido legado/TRAMPAS_CIEGAS_2.md
paso 'daño de bcp -c'            "$PY" -m legado bcp
echo
echo 'Tiempos:'
cat "$TIEMPOS"
