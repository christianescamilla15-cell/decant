# ADR 0012 · Sin autenticación en el alcance de la demo; contrato de errores sí

- Estado: aceptada · Fecha: 2026-11-25

## Contexto
La API del TO-BE (`src/Decant.Api`) publica la pantalla de consulta, el reporte de órdenes y la configuración del
ambiente sobre datos inventados de un banco ficticio. Es de SÓLO LECTURA: cinco rutas GET y ninguna escritura (la
carga y el replay son lotes de la línea de órdenes). La retro pide probar la autorización por rol y los 401/403 por
ruta; aquí no hay identidad que probar, e inventar una sólo para tener esas pruebas sería decorado.

## Decisión
- **Sin autenticación en el alcance de la demo.** No hay `AddAuthentication` ni `[Authorize]`; las pruebas no simulan
  usuarios. La superficie queda FIJA en una prueba (`La_superficie_es_la_del_adr_de_solo_lectura`): una ruta o un
  verbo nuevo la rompe hasta que se decida su autorización aquí.
- **Contrato de errores, probado:** todo error (400 de validación o de enlace de parámetros, 404 de recurso o de
  ruta, 405, 500) sale como `application/problem+json` con `status` y `title`. Un 500 no lleva `detail`, ni el tipo
  de la excepción, ni la pila, ni datos de la conexión (`ContratoDeErroresTests`). Antes de este ADR seis de esas
  respuestas salían con cuerpo vacío (control negativo: sin `UseStatusCodePages` fallan esas seis).

## Qué se haría con usuarios reales
1. Identidad del banco por OIDC (código con PKCE para la pantalla; credenciales de cliente para los lotes) y
   `AddAuthentication().AddJwtBearer(...)` validando emisor, audiencia, firma y vigencia.
2. Política de respaldo `RequireAuthenticatedUser` para todo, salvo `/salud`, que queda anónima.
3. Roles y rutas: `consulta` para `/api/operaciones*` y `/api/reportes/ordenes`; `operaciones` además para
   `/api/configuracion` (expone destinos aunque no secretos). Separación de funciones: nadie de `consulta` dispara
   lotes; los lotes corren con su propia identidad de servicio.
4. Pruebas por ruta y por rol con un manejador de autenticación de prueba: sin token → 401 con el mismo contrato
   `problem+json`; con token sin el rol → 403; con el rol → 200. La prueba de superficie pasaría a listar el rol
   exigido por cada ruta.
5. Bitácora de acceso (quién consultó qué operación) y límites de tasa por identidad.

## Alternativas descartadas
- **Autenticación de juguete (una llave fija en un encabezado):** daría verdes a 401/403 sin proteger nada y
  enseñaría el patrón equivocado.
- **Probar 401/403 con un esquema simulado sin que la API lo use:** probaría el andamio de la prueba, no la API.

## Consecuencias
El repositorio no debe desplegarse con datos reales tal cual. Agregar una ruta exige actualizar este ADR y la prueba
de superficie; la autorización entra con el primer consumidor real, con las pruebas del punto 4.

## Actualización (ADR 0017)
La superficie suma `POST /graphql`, de SÓLO LECTURA. Se enruta con todos los verbos y HotChocolate sólo ejecuta POST
con JSON. La prueba de superficie lo lista como `* /graphql`, y `GraphQL.ContratoTests` prueba que GET no ejecuta
consultas. Su contrato de errores lleva `extensions.code` y no filtra nada interno, igual que el `problem+json` de
esta API. Con usuarios reales, cada campo raíz lleva los mismos roles que su ruta REST equivalente.
