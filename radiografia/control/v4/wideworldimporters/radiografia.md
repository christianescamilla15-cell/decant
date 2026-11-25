# Radiografía de `WideWorldImporters`

Generada 2026-11-25T04:15:39+00:00 (UTC) por `python -m radiografia`. Todo lo que sigue se midió sobre el respaldo restaurado en un contenedor limpio.

## Restauración

| Base restaurada | Archivo | sha256 contra el manifiesto | Verificación | Segundos |
|---|---|---|---|---:|
| `WideWorldImporters` | `WideWorldImporters-Full.bak` | sin manifiesto | legible (VERIFYONLY; el respaldo no trae CHECKSUM) | 6.4 |

## Criterio de salida

No aplica: no hay manifiesto con lo que publicaba el legado (base de muestra).

## Corte medido en la fuente

| Tabla | MAX(id) | IDENT_CURRENT | Fecha más reciente |
|---|---:|---:|---|
| `application.cities` | — | — | ValidFrom 2015-07-01 16:00:00, ValidTo 9999-12-31 23:59:59.999999 |
| `application.cities_archive` | — | — | ValidFrom 2013-01-01 00:00:00, ValidTo 2015-07-01 16:00:00 |
| `application.countries` | — | — | ValidFrom 2022-10-07 21:11:44.893009, ValidTo 9999-12-31 23:59:59.999999 |
| `application.countries_archive` | — | — | ValidFrom 2013-07-01 16:00:00, ValidTo 2022-10-07 21:11:44.893009 |
| `application.deliverymethods` | — | — | ValidFrom 2015-01-01 16:00:00, ValidTo 9999-12-31 23:59:59.999999 |
| `application.deliverymethods_archive` | — | — | ValidFrom 2013-01-01 00:00:00, ValidTo 2015-01-01 16:00:00 |
| `application.paymentmethods` | — | — | ValidFrom 2016-01-01 16:00:00, ValidTo 9999-12-31 23:59:59.999999 |
| `application.paymentmethods_archive` | — | — | ValidFrom 2013-01-01 00:00:00, ValidTo 2016-01-01 16:00:00 |
| `application.people` | — | — | ValidFrom 2016-05-31 23:14:00, ValidTo 9999-12-31 23:59:59.999999 |
| `application.people_archive` | — | — | ValidFrom 2016-05-31 23:13:00, ValidTo 2016-05-31 23:14:00 |
| `application.stateprovinces` | — | — | ValidFrom 2015-07-01 16:00:00, ValidTo 9999-12-31 23:59:59.999999 |
| `application.stateprovinces_archive` | — | — | ValidFrom 2015-07-01 16:00:00, ValidTo 2015-07-01 16:00:00 |
| `application.systemparameters` | — | — | LastEditedWhen 2013-01-01 00:00:00 |
| `application.transactiontypes` | — | — | ValidFrom 2016-01-01 16:05:00, ValidTo 9999-12-31 23:59:59.999999 |
| `application.transactiontypes_archive` | — | — | ValidFrom 2016-01-01 16:00:00, ValidTo 2016-01-01 16:05:00 |
| `purchasing.purchaseorderlines` | — | — | LastReceiptDate 2016-05-31, LastEditedWhen 2016-05-31 13:00:00 |
| `purchasing.purchaseorders` | — | — | OrderDate 2016-05-31, ExpectedDeliveryDate 2016-06-20, LastEditedWhen 2016-05-31 13:00:00 |
| `purchasing.suppliercategories` | — | — | ValidFrom 2015-01-01 16:00:00, ValidTo 9999-12-31 23:59:59.999999 |
| `purchasing.suppliercategories_archive` | — | — | ValidFrom 2013-01-01 00:00:00, ValidTo 2015-01-01 16:00:00 |
| `purchasing.suppliers` | — | — | ValidFrom 2013-01-01 00:05:00, ValidTo 9999-12-31 23:59:59.999999 |
| `purchasing.suppliers_archive` | — | — | ValidFrom 2013-01-01 00:00:00, ValidTo 2013-01-01 00:05:00 |
| `purchasing.suppliertransactions` | — | — | TransactionDate 2016-05-31, FinalizationDate 2016-05-30, LastEditedWhen 2016-05-31 07:00:00 |
| `sales.buyinggroups` | — | — | ValidFrom 2013-01-01 00:00:00, ValidTo 9999-12-31 23:59:59.999999 |
| `sales.buyinggroups_archive` | — | — |  |
| `sales.customercategories` | — | — | ValidFrom 2014-01-01 16:15:00, ValidTo 9999-12-31 23:59:59.999999 |
| `sales.customercategories_archive` | — | — | ValidFrom 2014-01-01 16:00:00, ValidTo 2014-01-01 16:15:00 |
| `sales.customers` | — | — | AccountOpenedDate 2016-05-07, ValidFrom 2016-05-07 00:00:00, ValidTo 9999-12-31 23:59:59.999999 |
| `sales.customers_archive` | — | — | AccountOpenedDate 2015-06-12, ValidFrom 2015-06-12 00:00:00, ValidTo 2015-07-01 16:00:00 |
| `sales.customertransactions` | — | — | TransactionDate 2016-05-31, FinalizationDate 2016-05-31, LastEditedWhen 2016-05-31 12:00:00 |
| `sales.invoicelines` | — | — | LastEditedWhen 2016-05-31 12:00:00 |
| `sales.invoices` | — | — | InvoiceDate 2016-05-31, ConfirmedDeliveryTime 2016-05-31 13:30:00, LastEditedWhen 2016-05-31 12:00:00 |
| `sales.orderlines` | — | — | PickingCompletedWhen 2016-05-31 11:00:00, LastEditedWhen 2016-05-31 12:00:00 |
| `sales.orders` | — | — | OrderDate 2016-05-31, ExpectedDeliveryDate 2016-06-01, PickingCompletedWhen 2016-05-31 12:00:00, LastEditedWhen 2016-05-31 12:00:00 |
| `sales.specialdeals` | — | — | StartDate 2016-04-01, EndDate 2016-06-30, LastEditedWhen 2015-12-31 16:00:00 |
| `warehouse.coldroomtemperatures` | 3654740 | 3654740 | RecordedWhen 2016-05-31 23:59:24, ValidFrom 2016-05-31 23:59:24, ValidTo 9999-12-31 23:59:59.999999 |
| `warehouse.coldroomtemperatures_archive` | — | — | RecordedWhen 2016-05-31 23:59:00, ValidFrom 2016-05-31 23:59:00, ValidTo 2016-05-31 23:59:24 |
| `warehouse.colors` | — | — | ValidFrom 2016-01-01 16:00:00, ValidTo 9999-12-31 23:59:59.999999 |
| `warehouse.colors_archive` | — | — | ValidFrom 2013-01-01 00:00:00, ValidTo 2016-01-01 16:00:00 |
| `warehouse.packagetypes` | — | — | ValidFrom 2013-01-01 00:00:00, ValidTo 9999-12-31 23:59:59.999999 |
| `warehouse.packagetypes_archive` | — | — |  |
| `warehouse.stockgroups` | — | — | ValidFrom 2016-01-01 16:00:00, ValidTo 9999-12-31 23:59:59.999999 |
| `warehouse.stockgroups_archive` | — | — | ValidFrom 2013-01-01 00:00:00, ValidTo 2016-01-01 16:00:00 |
| `warehouse.stockitemholdings` | — | — | LastEditedWhen 2016-05-31 12:00:00 |
| `warehouse.stockitems` | — | — | ValidFrom 2016-05-31 23:12:00, ValidTo 9999-12-31 23:59:59.999999 |
| `warehouse.stockitems_archive` | — | — | ValidFrom 2016-05-31 23:09:00, ValidTo 2016-05-31 23:12:00 |
| `warehouse.stockitemstockgroups` | — | — | LastEditedWhen 2016-01-05 00:00:00 |
| `warehouse.stockitemtransactions` | — | — | TransactionOccurredWhen 2016-05-31 12:00:00, LastEditedWhen 2016-05-31 12:00:00 |
| `warehouse.vehicletemperatures` | 65998 | 65998 | RecordedWhen 2016-05-31 15:57:19 |

## Inventario

48 tablas · 4,713,833 filas · 47 módulos · 0 triggers · 0 pasos de job.

| Tabla | Filas |
|---|---:|
| `Warehouse.ColdRoomTemperatures_Archive` | 3,654,736 |
| `Warehouse.StockItemTransactions` | 236,667 |
| `Sales.OrderLines` | 231,412 |
| `Sales.InvoiceLines` | 228,265 |
| `Sales.CustomerTransactions` | 97,147 |
| `Sales.Orders` | 73,595 |
| `Sales.Invoices` | 70,510 |
| `Warehouse.VehicleTemperatures` | 65,998 |
| `Application.Cities` | 37,940 |
| `Purchasing.PurchaseOrderLines` | 8,367 |
| `Purchasing.SupplierTransactions` | 2,438 |
| `Purchasing.PurchaseOrders` | 2,074 |
| `Application.People` | 1,111 |
| `Application.People_Archive` | 961 |
| `Sales.Customers` | 663 |
| `Warehouse.StockItems_Archive` | 444 |
| `Warehouse.StockItemStockGroups` | 442 |
| `Warehouse.StockItemHoldings` | 227 |
| `Warehouse.StockItems` | 227 |
| `Application.Countries` | 190 |
| `Application.StateProvinces_Archive` | 104 |
| `Application.StateProvinces` | 53 |
| `Sales.Customers_Archive` | 51 |
| `Application.Countries_Archive` | 37 |
| `Warehouse.Colors` | 36 |
| `Application.Cities_Archive` | 28 |
| `Warehouse.PackageTypes` | 14 |
| `Application.TransactionTypes` | 13 |
| `Purchasing.Suppliers` | 13 |
| `Purchasing.Suppliers_Archive` | 13 |
| `Application.DeliveryMethods` | 10 |
| `Warehouse.StockGroups` | 10 |
| `Purchasing.SupplierCategories` | 9 |
| `Sales.CustomerCategories` | 8 |
| `Application.PaymentMethods` | 4 |
| `Warehouse.ColdRoomTemperatures` | 4 |
| `Sales.BuyingGroups` | 2 |
| `Sales.SpecialDeals` | 2 |
| `Application.DeliveryMethods_Archive` | 1 |
| `Application.PaymentMethods_Archive` | 1 |
| `Application.SystemParameters` | 1 |
| `Application.TransactionTypes_Archive` | 1 |
| `Purchasing.SupplierCategories_Archive` | 1 |
| `Sales.CustomerCategories_Archive` | 1 |
| `Warehouse.Colors_Archive` | 1 |
| `Warehouse.StockGroups_Archive` | 1 |
| `Sales.BuyingGroups_Archive` | 0 |
| `Warehouse.PackageTypes_Archive` | 0 |

Módulos: 2 funcion, 42 procedimiento, 3 vista.

Jobs: no se restauró msdb, así que no se pueden inventariar (viven ahí, no en la base).


## Hallazgos por patrón

| Patrón | Hallazgos |
|---|---:|
| Selección no determinista: TOP sin ORDER BY, asignación desde varias filas u ORDER BY que no ordena (vista o tabla derivada) | 0 |
| INNER JOIN a una tabla hija | 7 |
| Reloj del servidor (GETDATE y similares) en una regla, directo o por una variable | 0 |
| IF EXISTS sin ELSE que escribe datos (camino silencioso) | 0 |
| IF EXISTS sin ELSE con cuerpo de guarda o DDL (informativo) | 65 |
| Conversión de zona con desfase fijo | 0 |
| ROUND con tercer argumento: trunca en vez de redondear | 0 |
| División entera: entero entre entero (el cociente se trunca) | 0 |
| Centinelas en vez de NULL (por distribución de valores) | 7 |
| Texto con mojibake (UTF-8 leído como latin-1) | 5 |
| Espacios finales que SQL Server ignora al comparar y PostgreSQL no | 11 |
| Re-registro: el mismo documento con otra llave interna | 0 |
| Llave candidata con duplicados (no parece re-registro) | 9 |
| Columnas que ningún módulo lee | 75 |
| Tablas que ningún módulo lee | 7 |
| Literales mágicos (números y códigos en duro) | 87 |

### INNER JOIN a una tabla hija (7)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `integration.getcustomerupdates` | 68 | INNER JOIN de sales.customercategories a su tabla hija sales.customers: descarta los registros de sales.customercategories sin sales.customers | `INNER JOIN Sales.Customers FOR SYSTEM_TIME AS OF @ValidFrom AS bt` |
| `integration.getcustomerupdates` | 116 | INNER JOIN de sales.customercategories a su tabla hija sales.customers: descarta los registros de sales.customercategories sin sales.customers | `INNER JOIN Sales.Customers FOR SYSTEM_TIME AS OF @ValidFrom AS bt` |
| `integration.getcustomerupdates` | 162 | INNER JOIN de sales.customercategories a su tabla hija sales.customers: descarta los registros de sales.customercategories sin sales.customers | `INNER JOIN Sales.Customers FOR SYSTEM_TIME AS OF @ValidFrom AS bt` |
| `integration.getorderupdates` | 31 | INNER JOIN de sales.orders a su tabla hija sales.orderlines: descarta los registros de sales.orders sin sales.orderlines | `INNER JOIN Sales.OrderLines AS ol` |
| `integration.getpurchaseupdates` | 23 | INNER JOIN de purchasing.purchaseorders a su tabla hija purchasing.purchaseorderlines: descarta los registros de purchasing.purchaseorders sin purchasing.purchaseorderlines | `INNER JOIN Purchasing.PurchaseOrderLines AS pol` |
| `integration.getsaleupdates` | 32 | INNER JOIN de sales.invoices a su tabla hija sales.invoicelines: descarta los registros de sales.invoices sin sales.invoicelines | `INNER JOIN Sales.InvoiceLines AS il` |
| `website.invoicecustomerorders` | 91 | INNER JOIN de warehouse.stockitems a su tabla hija warehouse.stockitemholdings: descarta los registros de warehouse.stockitems sin warehouse.stockitemholdings | `INNER JOIN Warehouse.StockItemHoldings AS sih` |

### IF EXISTS sin ELSE con cuerpo de guarda o DDL (informativo) (65)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `application.addrolememberifnonexistent` | 11 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.database_role_members AS drm` |
| `application.configuration_applyauditing` | 17 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.server_audits WHERE name = N'WWI_Audit')` |
| `application.configuration_applyauditing` | 37 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.server_audit_specifications WHERE name = N'WWI_ServerAuditSpecification')` |
| `application.configuration_applyauditing` | 55 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.database_audit_specifications WHERE name = N'WWI_DatabaseAuditSpecification')` |
| `application.configuration_applycolumnstoreindexing` | 27 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'NCCX_Sales_OrderLines')` |
| `application.configuration_applycolumnstoreindexing` | 44 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'NCCX_Sales_InvoiceLines')` |
| `application.configuration_applycolumnstoreindexing` | 61 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'CCX_Warehouse_StockItemTransactions')` |
| `application.configuration_applyfulltextindexing` | 12 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.fulltext_catalogs WHERE name = N'FTCatalog')` |
| `application.configuration_applyfulltextindexing` | 18 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.fulltext_indexes AS fti WHERE fti.object_id = OBJECT_ID(N'[Application].People'))` |
| `application.configuration_applyfulltextindexing` | 28 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.fulltext_indexes AS fti WHERE fti.object_id = OBJECT_ID(N'Sales.Customers'))` |
| `application.configuration_applyfulltextindexing` | 38 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.fulltext_indexes AS fti WHERE fti.object_id = OBJECT_ID(N'Purchasing.Suppliers'))` |
| `application.configuration_applyfulltextindexing` | 49 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.fulltext_indexes AS fti WHERE fti.object_id = OBJECT_ID(N'Warehouse.StockItems'))` |
| `application.configuration_applypartitioning` | 18 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.partition_functions WHERE name = N'PF_TransactionDateTime')` |
| `application.configuration_applypartitioning` | 27 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.partition_functions WHERE name = N'PF_TransactionDate')` |
| `application.configuration_applypartitioning` | 36 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT * FROM sys.partition_schemes WHERE name = N'PS_TransactionDateTime')` |
| `application.configuration_applypartitioning` | 55 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.partition_schemes WHERE name = N'PS_TransactionDate')` |
| `application.configuration_applypartitioning` | 73 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'CX_Sales_CustomerTransactions')` |
| `application.configuration_applypartitioning` | 148 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'CX_Purchasing_SupplierTransactions')` |
| `application.configuration_enableinmemory` | 21 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.filegroups WHERE name = N'WWI_InMemory_Data')` |
| `application.configuration_enableinmemory` | 43 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = N'ColdRoomTemperatures' AND is_memory_optimized <> 0)` |
| `application.configuration_enableinmemory` | 98 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = N'VehicleTemperatures' AND is_memory_optimized <> 0)` |
| `application.configuration_removeauditing` | 19 | IF EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF EXISTS (SELECT 1 FROM sys.database_audit_specifications WHERE name = N'WWI_DatabaseAuditSpecification')` |
| `application.configuration_removeauditing` | 27 | IF EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF EXISTS (SELECT 1 FROM sys.server_audit_specifications WHERE name = N'WWI_ServerAuditSpecification')` |
| `application.configuration_removeauditing` | 36 | IF EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF EXISTS (SELECT 1 FROM sys.server_audits WHERE name = N'WWI_Audit')` |
| `application.createroleifnonexistent` | 10 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = @RoleName AND type = N'R')` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 13 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE name = N'GetAreaCode'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 398 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 452 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 873 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 925 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 1012 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 1063 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 1176 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 1379 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 1542 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 1607 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 1677 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 1800 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 1928 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 1993 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 2102 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 2161 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 2237 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 2332 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 2577 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.procedures WHERE SCHEMA_NAME(schema_id) = N'DataLoadSimulation'` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 7 | IF EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF EXISTS (SELECT 1 FROM sys.procedures WHERE name = N'Configuration_RemoveRowLevelSecurity')` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 108 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 145 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 182 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 219 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 256 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 293 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 330 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 367 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 404 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 441 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 478 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 515 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 552 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 589 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 626 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 663 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 700 | IF NOT EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = @TableName AND is_memory_optimized <> 0)` |
| `dataloadsimulation.reactivatetemporaltablesafterdataload` | 7 | IF EXISTS sin ELSE con cuerpo DDL/EXEC: guarda o configuración idempotente | `IF EXISTS (SELECT 1 FROM sys.procedures WHERE name = N'Configuration_ApplyRowLevelSecurity')` |
| `website.invoicecustomerorders` | 43 | IF EXISTS sin ELSE con cuerpo guarda: guarda o configuración idempotente | `IF EXISTS (SELECT 1 FROM @OrdersToInvoice AS oti WHERE NOT EXISTS (SELECT 1 FROM @InvoicesToGenerate AS itg WHERE itg.OrderID = oti.OrderID))` |

### Centinelas en vez de NULL (por distribución de valores) (7)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `purchasing.suppliertransactions.amountexcludingtax` |  | 366 filas (15.0%) con Decimal('0.00'): 0.00 queda fuera del rango del resto de la columna (76.80 … 1627734.00); la columna no usa NULL |  |
| `purchasing.suppliertransactions.taxamount` |  | 366 filas (15.0%) con Decimal('0.00'): 0.00 queda fuera del rango del resto de la columna (11.52 … 244160.10); la columna no usa NULL |  |
| `purchasing.suppliertransactions.outstandingbalance` |  | 2,436 filas (99.9%) con Decimal('0.00'): 0.00 queda fuera del rango del resto de la columna (849784.11 … 1871894.10); la columna no usa NULL |  |
| `sales.customertransactions.amountexcludingtax` |  | 26,637 filas (27.4%) con Decimal('0.00'): 0.00 queda fuera del rango del resto de la columna (4.80 … 32026.00); la columna no usa NULL |  |
| `sales.customertransactions.taxamount` |  | 26,637 filas (27.4%) con Decimal('0.00'): 0.00 queda fuera del rango del resto de la columna (0.72 … 4803.90); la columna no usa NULL |  |
| `sales.customertransactions.outstandingbalance` |  | 97,063 filas (99.9%) con Decimal('0.00'): 0.00 queda fuera del rango del resto de la columna (44.85 … 28280.80); la columna no usa NULL |  |
| `sales.invoices.totalchilleritems` |  | 69,519 filas (98.6%) con Decimal('0'): 0 queda fuera del rango del resto de la columna (1 … 3); la columna no usa NULL |  |

### Texto con mojibake (UTF-8 leído como latin-1) (5)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `application.people.fullname` |  | 1 filas con secuencias de UTF-8 leído como latin-1; en la muestra, 1 de 1 valores distintos se reparan al revertir la decodificación |  |
| `application.people.searchname` |  | 1 filas con secuencias de UTF-8 leído como latin-1; en la muestra, 1 de 1 valores distintos se reparan al revertir la decodificación |  |
| `sales.customers.deliveryaddressline2` |  | 2 filas con secuencias de UTF-8 leído como latin-1; en la muestra, 2 de 2 valores distintos se reparan al revertir la decodificación |  |
| `sales.customers.postaladdressline2` |  | 2 filas con secuencias de UTF-8 leído como latin-1; en la muestra, 1 de 1 valores distintos se reparan al revertir la decodificación |  |
| `sales.invoices.deliveryinstructions` |  | 213 filas con secuencias de UTF-8 leído como latin-1; en la muestra, 2 de 2 valores distintos se reparan al revertir la decodificación |  |

### Espacios finales que SQL Server ignora al comparar y PostgreSQL no (11)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `application.people.fullname` |  | 1 de 1,111 valores con espacios al final (0.1%), medidos con DATALENGTH en el motor: SQL Server los ignora al comparar (=, DISTINCT, GROUP BY) y LEN no los cuenta; PostgreSQL sí los distingue; ventana en ValidFrom: 2016-05-31 23:14:00 → 2016-05-31 23:14:00 (la tabla va de 2013-01-01 00:00:00 a 2016-05-31 23:14:00); concentrados en esa ventana |  |
| `application.people.preferredname` |  | 8 de 1,111 valores con espacios al final (0.7%), medidos con DATALENGTH en el motor: SQL Server los ignora al comparar (=, DISTINCT, GROUP BY) y LEN no los cuenta; PostgreSQL sí los distingue; ventana en ValidFrom: 2013-01-01 00:00:00 → 2013-06-22 00:00:00 (la tabla va de 2013-01-01 00:00:00 a 2016-05-31 23:14:00); concentrados en esa ventana |  |
| `application.people.searchname` |  | 1 de 1,111 valores con espacios al final (0.1%), medidos con DATALENGTH en el motor: SQL Server los ignora al comparar (=, DISTINCT, GROUP BY) y LEN no los cuenta; PostgreSQL sí los distingue; ventana en ValidFrom: 2016-05-31 23:14:00 → 2016-05-31 23:14:00 (la tabla va de 2013-01-01 00:00:00 a 2016-05-31 23:14:00); concentrados en esa ventana |  |
| `application.people_archive.fullname` |  | 5 de 961 valores con espacios al final (0.5%), medidos con DATALENGTH en el motor: SQL Server los ignora al comparar (=, DISTINCT, GROUP BY) y LEN no los cuenta; PostgreSQL sí los distingue; ventana en ValidTo: 2015-06-14 08:10:00 → 2016-05-31 23:14:00 (la tabla va de 2013-01-01 08:00:00 a 2016-05-31 23:14:00); concentrados en esa ventana |  |
| `application.people_archive.searchname` |  | 5 de 961 valores con espacios al final (0.5%), medidos con DATALENGTH en el motor: SQL Server los ignora al comparar (=, DISTINCT, GROUP BY) y LEN no los cuenta; PostgreSQL sí los distingue; ventana en ValidTo: 2015-06-14 08:10:00 → 2016-05-31 23:14:00 (la tabla va de 2013-01-01 08:00:00 a 2016-05-31 23:14:00); concentrados en esa ventana |  |
| `sales.customers.customername` |  | 1 de 663 valores con espacios al final (0.2%), medidos con DATALENGTH en el motor: SQL Server los ignora al comparar (=, DISTINCT, GROUP BY) y LEN no los cuenta; PostgreSQL sí los distingue; ventana en AccountOpenedDate: 2013-08-15 → 2013-08-15 (la tabla va de 2013-01-01 a 2016-05-07); concentrados en esa ventana |  |
| `sales.customers_archive.customername` |  | 1 de 51 valores con espacios al final (2.0%), medidos con DATALENGTH en el motor: SQL Server los ignora al comparar (=, DISTINCT, GROUP BY) y LEN no los cuenta; PostgreSQL sí los distingue; ventana en AccountOpenedDate: 2013-08-15 → 2013-08-15 (la tabla va de 2013-01-01 a 2015-06-12); concentrados en esa ventana |  |
| `sales.invoices.confirmedreceivedby` |  | 87 de 70,426 valores con espacios al final (0.1%), medidos con DATALENGTH en el motor: SQL Server los ignora al comparar (=, DISTINCT, GROUP BY) y LEN no los cuenta; PostgreSQL sí los distingue; ventana en InvoiceDate: 2013-09-19 → 2016-05-26 (la tabla va de 2013-01-01 a 2016-05-31) |  |
| `warehouse.packagetypes.packagetypename` |  | 1 de 14 valores con espacios al final (7.1%), medidos con DATALENGTH en el motor: SQL Server los ignora al comparar (=, DISTINCT, GROUP BY) y LEN no los cuenta; PostgreSQL sí los distingue; ventana en ValidFrom: 2013-01-01 00:00:00 → 2013-01-01 00:00:00 (la tabla va de 2013-01-01 00:00:00 a 2013-01-01 00:00:00) |  |
| `warehouse.stockitems.searchdetails` |  | 199 de 227 valores con espacios al final (87.7%), medidos con DATALENGTH en el motor: SQL Server los ignora al comparar (=, DISTINCT, GROUP BY) y LEN no los cuenta; PostgreSQL sí los distingue; ventana en ValidFrom: 2016-05-31 23:00:00 → 2016-05-31 23:12:00 (la tabla va de 2016-05-31 23:00:00 a 2016-05-31 23:12:00) |  |
| `warehouse.stockitems_archive.searchdetails` |  | 387 de 444 valores con espacios al final (87.2%), medidos con DATALENGTH en el motor: SQL Server los ignora al comparar (=, DISTINCT, GROUP BY) y LEN no los cuenta; PostgreSQL sí los distingue; ventana en ValidFrom: 2013-01-01 00:00:00 → 2016-05-31 23:09:00 (la tabla va de 2013-01-01 00:00:00 a 2016-05-31 23:09:00) |  |

### Llave candidata con duplicados (no parece re-registro) (9)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `application.cities.cityname` |  | 14,668 filas repiten un valor (23,272 distintos en 37,940); las filas repetidas comparten el 50% de sus columnas (dos filas cualesquiera, el 52%); en 40 de 40 grupos la fila de id mayor es la de ValidTo más reciente |  |
| `application.people.preferredname` |  | 231 filas repiten un valor (880 distintos en 1,111); las filas repetidas comparten el 69% de sus columnas (dos filas cualesquiera, el 63%); en 40 de 40 grupos la fila de id mayor es la de ValidTo más reciente |  |
| `application.people.userpreferences` |  | 123 filas repiten un valor (59 distintos en 182); las filas repetidas comparten el 46% de sus columnas (dos filas cualesquiera, el 63%); en 40 de 40 grupos la fila de id mayor es la de ValidFrom más reciente |  |
| `application.people.emailaddress` |  | 81 filas repiten un valor (1,029 distintos en 1,110); las filas repetidas comparten el 71% de sus columnas (dos filas cualesquiera, el 63%); en 40 de 40 grupos la fila de id mayor es la de ValidTo más reciente |  |
| `application.people.otherlanguages` |  | 2 filas repiten un valor (17 distintos en 19); las filas repetidas comparten el 53% de sus columnas (dos filas cualesquiera, el 63%); en 1 de 1 grupos la fila de id mayor es la de ValidFrom más reciente |  |
| `sales.customers.websiteurl` |  | 60 filas repiten un valor (603 distintos en 663); las filas repetidas comparten el 34% de sus columnas (dos filas cualesquiera, el 50%); en 1 de 1 grupos la fila de id mayor es la de AccountOpenedDate más reciente |  |
| `sales.customers.deliveryaddressline1` |  | 300 filas repiten un valor (363 distintos en 663); las filas repetidas comparten el 38% de sus columnas (dos filas cualesquiera, el 50%); en 40 de 40 grupos la fila de id mayor es la de AccountOpenedDate más reciente |  |
| `sales.customers.postaladdressline1` |  | 19 filas repiten un valor (644 distintos en 663); las filas repetidas comparten el 40% de sus columnas (dos filas cualesquiera, el 50%); en 19 de 19 grupos la fila de id mayor es la de AccountOpenedDate más reciente |  |
| `sales.customers.postaladdressline2` |  | 211 filas repiten un valor (452 distintos en 663); las filas repetidas comparten el 43% de sus columnas (dos filas cualesquiera, el 50%); en 40 de 40 grupos la fila de id mayor es la de AccountOpenedDate más reciente |  |

### Columnas que ningún módulo lee (75)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `application.countries.formalname` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.countries.isoalpha3code` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.countries.isonumericcode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.countries.countrytype` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.countries.border` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.countries_archive.formalname` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.countries_archive.isoalpha3code` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.countries_archive.isonumericcode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.countries_archive.countrytype` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.countries_archive.border` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.people.logonname` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.people.isexternallogonprovider` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.people.issystemuser` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.people.emailaddress` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.people.customfields` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.people.otherlanguages` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.people_archive.logonname` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.people_archive.isexternallogonprovider` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.people_archive.issystemuser` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.people_archive.emailaddress` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.people_archive.customfields` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.people_archive.otherlanguages` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.stateprovinces.stateprovincecode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.stateprovinces.border` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.stateprovinces_archive.stateprovincecode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `application.stateprovinces_archive.border` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderlines.purchaseorderlineid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderlines.expectedunitpriceperouter` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderlines.lastreceiptdate` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorders.isorderfinalized` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers.postalcityid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers.bankaccountname` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers.bankaccountbranch` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers.bankaccountcode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers.bankaccountnumber` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers.bankinternationalcode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers.postaladdressline1` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers.postaladdressline2` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers.postalpostalcode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers_archive.postalcityid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers_archive.bankaccountname` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers_archive.bankaccountbranch` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers_archive.bankaccountcode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers_archive.bankaccountnumber` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers_archive.bankinternationalcode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers_archive.postaladdressline1` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers_archive.postaladdressline2` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.suppliers_archive.postalpostalcode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers.postalcityid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers.creditlimit` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers.accountopeneddate` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers.standarddiscountpercentage` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers.isstatementsent` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers.isoncredithold` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers.postaladdressline1` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers.postaladdressline2` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers.postalpostalcode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers_archive.postalcityid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers_archive.creditlimit` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers_archive.accountopeneddate` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers_archive.standarddiscountpercentage` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers_archive.isstatementsent` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers_archive.isoncredithold` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers_archive.postaladdressline1` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers_archive.postaladdressline2` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customers_archive.postalpostalcode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.invoices.confirmedreceivedby` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.specialdeals.specialdealid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.specialdeals.dealdescription` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `warehouse.coldroomtemperatures.coldroomtemperatureid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `warehouse.stockitems.marketingcomments` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `warehouse.stockitems.customfields` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `warehouse.stockitems_archive.marketingcomments` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `warehouse.stockitems_archive.customfields` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `warehouse.stockitemstockgroups.stockitemstockgroupid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |

### Tablas que ningún módulo lee (7)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `application.deliverymethods_archive` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `application.systemparameters` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `warehouse.coldroomtemperatures_archive` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `warehouse.colors_archive` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `warehouse.packagetypes_archive` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `warehouse.stockgroups` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `warehouse.stockgroups_archive` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |

### Literales mágicos (números y códigos en duro) (87)

| Objeto | Literales distintos | Ejemplos |
|---|---:|---|
| `dataloadsimulation.configuration_applydataloadsimulationprocedures` | 22 | `N'GetAreaCode'`, `N'FN'`, `N'DataLoadSimulation'`, `N'ActivateWebsiteLogins'`, `N'AddCustomers'`, `N'AddSpecialDeals'`, `N'AddStockItems'`, `N'ChangePasswords'`, `N'CreateCustomerOrders'`, `N'InvoicePickedOrders'`, `N'MakeTemporalChanges'`, `N'PaySuppliers'`, `N'PerformStocktake'`, `N'PickStockForC |
| `application.configuration_applypartitioning` | 7 | `N'PF_TransactionDateTime'`, `N'PF_TransactionDate'`, `N'PS_TransactionDateTime'`, `5`, `N'PS_TransactionDate'`, `N'CX_Sales_CustomerTransactions'`, `N'CX_Purchasing_SupplierTransactions'` |
| `website.invoicecustomerorders` | 7 | `51000`, `126`, `1050`, `100.0`, `2`, `N'Stock Issue'`, `N'Customer Invoice'` |
| `dataloadsimulation.deactivatetemporaltablesbeforedataload` | 5 | `N'Configuration_RemoveRowLevelSecurity'`, `N'    '`, `N'ValidFrom'`, `N'ValidTo'`, `N'Archive'` |
| `application.configuration_enableinmemory` | 4 | `5`, `N'WWI_InMemory_Data'`, `N'ColdRoomTemperatures'`, `N'VehicleTemperatures'` |
| `application.addrolememberifnonexistent` | 3 | `N'R'`, `N'S'`, `N'ALTER ROLE '` |
| `application.configuration_applyauditing` | 3 | `N'WWI_Audit'`, `N'WWI_ServerAuditSpecification'`, `N'WWI_DatabaseAuditSpecification'` |
| `application.configuration_applycolumnstoreindexing` | 3 | `N'NCCX_Sales_OrderLines'`, `N'NCCX_Sales_InvoiceLines'`, `N'CCX_Warehouse_StockItemTransactions'` |
| `application.configuration_removeauditing` | 3 | `N'WWI_DatabaseAuditSpecification'`, `N'WWI_ServerAuditSpecification'`, `N'WWI_Audit'` |
| `website.recordcoldroomtemperatures` | 3 | `N'English'`, `51000`, `2` |
| `website.recordvehicletemperature` | 3 | `N'JSON sensor data is invalid. An example of what is required is as follows:'`, `51000`, `2` |
| `website.calculatecustomerprice` | 2 | `100.0`, `2` |
| `application.createroleifnonexistent` | 2 | `N'R'`, `N'CREATE ROLE '` |
| `integration.getcityupdates` | 2 | `'99991231 23:59:59.9999999'`, `'20130101'` |
| `integration.getcustomerupdates` | 2 | `'99991231 23:59:59.9999999'`, `'20130101'` |
| `integration.getorderupdates` | 2 | `2`, `100.0` |
| `integration.getsupplierupdates` | 2 | `'99991231 23:59:59.9999999'`, `'20130101'` |
| `application.determinecustomeraccess` | 1 | `N'Website'` |
| `application.configuration_applyfulltextindexing` | 1 | `N'FTCatalog'` |
| `application.configuration_applyrowlevelsecurity` | 1 | `51000` |
| `application.configuration_removerowlevelsecurity` | 1 | `51000` |
| `dataloadsimulation.reactivatetemporaltablesafterdataload` | 1 | `N'Configuration_ApplyRowLevelSecurity'` |
| `integration.getemployeeupdates` | 1 | `'99991231 23:59:59.9999999'` |
| `integration.getpaymentmethodupdates` | 1 | `'99991231 23:59:59.9999999'` |
| `integration.getstockitemupdates` | 1 | `'99991231 23:59:59.9999999'` |
| `integration.gettransactiontypeupdates` | 1 | `'99991231 23:59:59.9999999'` |
| `sequences.reseedsequencebeyondtablevalues` | 1 | `N'Sequences'` |
| `website.activatewebsitelogon` | 1 | `51000` |
| `website.changepassword` | 1 | `51000` |

## Tiempos

arranque_contenedor: 6.3 s · restauracion: 7.7 s · inventario: 3.3 s · patrones_codigo: 0.1 s · patrones_datos: 33.7 s · total: 51.5 s

