# Radiografía de `AdventureWorks2022`

Generada 2026-11-25T03:11:35+00:00 (UTC) por `python -m radiografia`. Todo lo que sigue se midió sobre el respaldo restaurado en un contenedor limpio.

## Restauración

| Base restaurada | Archivo | sha256 contra el manifiesto | Verificación | Segundos |
|---|---|---|---|---:|
| `AdventureWorks2022` | `AdventureWorks2022.bak` | sin manifiesto | íntegro (VERIFYONLY con CHECKSUM) | 2.9 |

## Criterio de salida

No aplica: no hay manifiesto con lo que publicaba el legado (base de muestra).

## Corte medido en la fuente

| Tabla | MAX(id) | IDENT_CURRENT | Fecha más reciente |
|---|---:|---:|---|
| `dbo.awbuildversion` | 1 | 1 | VersionDate 2023-01-23 13:08:53.190000, ModifiedDate 2023-05-08 12:07:29.843000 |
| `dbo.databaselog` | 1596 | 1596 | PostTime 2023-05-08 12:07:40.757000 |
| `dbo.errorlog` | None | 1 |  |
| `humanresources.department` | 16 | 16 | ModifiedDate 2008-04-30 00:00:00 |
| `humanresources.employee` | — | — | BirthDate 1991-05-31, HireDate 2013-05-30, ModifiedDate 2014-12-26 09:17:08.637000 |
| `humanresources.employeedepartmenthistory` | — | — | StartDate 2013-11-14, EndDate 2013-11-13, ModifiedDate 2013-11-13 00:00:00 |
| `humanresources.employeepayhistory` | — | — | RateChangeDate 2013-07-14 00:00:00, ModifiedDate 2014-06-30 00:00:00 |
| `humanresources.jobcandidate` | 13 | 13 | ModifiedDate 2013-12-22 18:32:21.313000 |
| `humanresources.shift` | 3 | 3 | ModifiedDate 2008-04-30 00:00:00 |
| `person.address` | 32521 | 32521 | ModifiedDate 2014-06-30 00:00:00 |
| `person.addresstype` | 6 | 6 | ModifiedDate 2008-04-30 00:00:00 |
| `person.businessentity` | 20777 | 20777 | ModifiedDate 2017-12-13 13:47:22.467000 |
| `person.businessentityaddress` | — | — | ModifiedDate 2014-09-12 11:15:06.967000 |
| `person.businessentitycontact` | — | — | ModifiedDate 2017-12-13 13:22:01.850000 |
| `person.contacttype` | 20 | 20 | ModifiedDate 2008-04-30 00:00:00 |
| `person.countryregion` | — | — | ModifiedDate 2008-04-30 00:00:00 |
| `person.emailaddress` | 19972 | 19972 | ModifiedDate 2015-04-15 16:33:33.123000 |
| `person.password` | — | — | ModifiedDate 2015-04-15 16:33:33.123000 |
| `person.person` | — | — | ModifiedDate 2015-04-15 16:33:33.123000 |
| `person.personphone` | — | — | ModifiedDate 2015-04-15 16:33:33.123000 |
| `person.phonenumbertype` | 3 | 3 | ModifiedDate 2017-12-13 13:19:22.273000 |
| `person.stateprovince` | 181 | 181 | ModifiedDate 2014-02-08 10:17:21.587000 |
| `production.billofmaterials` | 3482 | 3482 | StartDate 2010-12-23 00:00:00, EndDate 2010-11-14 00:00:00, ModifiedDate 2010-12-09 00:00:00 |
| `production.culture` | — | — | ModifiedDate 2008-04-30 00:00:00 |
| `production.document` | — | — | ModifiedDate 2017-12-13 13:58:04.037000 |
| `production.illustration` | 7 | 7 | ModifiedDate 2014-01-09 13:06:12.080000 |
| `production.location` | 60 | 60 | ModifiedDate 2008-04-30 00:00:00 |
| `production.product` | 999 | 999 | SellStartDate 2013-05-30 00:00:00, SellEndDate 2013-05-29 00:00:00, DiscontinuedDate None, ModifiedDate 2014-02-08 10:03:55.510000 |
| `production.productcategory` | 4 | 4 | ModifiedDate 2008-04-30 00:00:00 |
| `production.productcosthistory` | — | — | StartDate 2013-05-30 00:00:00, EndDate 2013-05-29 00:00:00, ModifiedDate 2013-05-29 00:00:00 |
| `production.productdescription` | 2010 | 2010 | ModifiedDate 2014-02-08 10:32:17.973000 |
| `production.productdocument` | — | — | ModifiedDate 2013-12-29 13:51:58.120000 |
| `production.productinventory` | — | — | ModifiedDate 2014-08-12 00:00:00 |
| `production.productlistpricehistory` | — | — | StartDate 2013-05-30 00:00:00, EndDate 2013-05-29 00:00:00, ModifiedDate 2013-05-29 00:00:00 |
| `production.productmodel` | 128 | 128 | ModifiedDate 2015-04-15 16:34:29.043000 |
| `production.productmodelillustration` | — | — | ModifiedDate 2014-01-09 14:41:02.200000 |
| `production.productmodelproductdescriptionculture` | — | — | ModifiedDate 2013-04-30 00:00:00 |
| `production.productphoto` | 181 | 181 | ModifiedDate 2013-04-30 00:00:00 |
| `production.productproductphoto` | — | — | ModifiedDate 2013-04-30 00:00:00 |
| `production.productreview` | 4 | 4 | ReviewDate 2013-11-15 00:00:00, ModifiedDate 2013-11-15 00:00:00 |
| `production.productsubcategory` | 37 | 37 | ModifiedDate 2008-04-30 00:00:00 |
| `production.scrapreason` | 16 | 16 | ModifiedDate 2008-04-30 00:00:00 |
| `production.transactionhistory` | 213442 | 213442 | TransactionDate 2014-08-03 00:00:00, ModifiedDate 2014-08-03 00:00:00 |
| `production.transactionhistoryarchive` | — | — | TransactionDate 2013-07-30 00:00:00, ModifiedDate 2013-07-30 00:00:00 |
| `production.unitmeasure` | — | — | ModifiedDate 2008-04-30 00:00:00 |
| `production.workorder` | 72591 | 72591 | StartDate 2014-06-02 00:00:00, EndDate 2014-06-17 00:00:00, DueDate 2014-06-13 00:00:00, ModifiedDate 2014-06-17 00:00:00 |
| `production.workorderrouting` | — | — | ScheduledStartDate 2014-06-02 00:00:00, ScheduledEndDate 2014-06-13 00:00:00, ActualStartDate 2014-06-17 00:00:00, ActualEndDate 2014-06-28 00:00:00, ModifiedDate 2014-06-28 00:00:00 |
| `purchasing.productvendor` | — | — | LastReceiptDate 2014-10-22 00:00:00, ModifiedDate 2015-08-12 12:20:28.343000 |
| `purchasing.purchaseorderdetail` | 8845 | 8845 | DueDate 2014-10-22 00:00:00, ModifiedDate 2015-08-12 12:25:46.483000 |
| `purchasing.purchaseorderheader` | 4012 | 4012 | OrderDate 2014-09-22 00:00:00, ShipDate 2014-10-17 00:00:00, ModifiedDate 2015-08-12 12:25:46.483000 |
| `purchasing.shipmethod` | 5 | 5 | ModifiedDate 2008-04-30 00:00:00 |
| `purchasing.vendor` | — | — | ModifiedDate 2012-02-18 00:00:00 |
| `sales.countryregioncurrency` | — | — | ModifiedDate 2014-02-08 10:17:21.510000 |
| `sales.creditcard` | 19237 | 19237 | ModifiedDate 2014-06-30 00:00:00 |
| `sales.currency` | — | — | ModifiedDate 2008-04-30 00:00:00 |
| `sales.currencyrate` | 13532 | 13532 | CurrencyRateDate 2014-05-31 00:00:00, ModifiedDate 2014-05-31 00:00:00 |
| `sales.customer` | 30118 | 30118 | ModifiedDate 2014-09-12 11:15:07.263000 |
| `sales.personcreditcard` | — | — | ModifiedDate 2014-06-30 00:00:00 |
| `sales.salesorderdetail` | 121317 | 121317 | ModifiedDate 2014-06-30 00:00:00 |
| `sales.salesorderheader` | 75123 | 75123 | OrderDate 2014-06-30 00:00:00, DueDate 2014-07-12 00:00:00, ShipDate 2014-07-07 00:00:00, ModifiedDate 2014-07-07 00:00:00 |
| `sales.salesorderheadersalesreason` | — | — | ModifiedDate 2014-06-30 00:00:00 |
| `sales.salesperson` | — | — | ModifiedDate 2013-05-23 00:00:00 |
| `sales.salespersonquotahistory` | — | — | QuotaDate 2014-03-01 00:00:00, ModifiedDate 2014-01-15 00:00:00 |
| `sales.salesreason` | 10 | 10 | ModifiedDate 2008-04-30 00:00:00 |
| `sales.salestaxrate` | 31 | 31 | ModifiedDate 2008-04-30 00:00:00 |
| `sales.salesterritory` | 10 | 10 | ModifiedDate 2008-04-30 00:00:00 |
| `sales.salesterritoryhistory` | — | — | StartDate 2013-05-30 00:00:00, EndDate 2012-11-29 00:00:00, ModifiedDate 2013-05-23 00:00:00 |
| `sales.shoppingcartitem` | 5 | 5 | DateCreated 2013-11-09 17:54:07.603000, ModifiedDate 2013-11-09 17:54:07.603000 |
| `sales.specialoffer` | 16 | 16 | StartDate 2014-03-31 00:00:00, EndDate 2014-11-30 00:00:00, ModifiedDate 2014-03-01 00:00:00 |
| `sales.specialofferproduct` | — | — | ModifiedDate 2014-03-01 00:00:00 |
| `sales.store` | — | — | ModifiedDate 2014-09-12 11:15:07.497000 |

## Inventario

71 tablas · 760,837 filas · 51 módulos · 10 triggers · 0 pasos de job.

| Tabla | Filas |
|---|---:|
| `Sales.SalesOrderDetail` | 121,317 |
| `Production.TransactionHistory` | 113,443 |
| `Production.TransactionHistoryArchive` | 89,253 |
| `Production.WorkOrder` | 72,591 |
| `Production.WorkOrderRouting` | 67,131 |
| `Sales.SalesOrderHeader` | 31,465 |
| `Sales.SalesOrderHeaderSalesReason` | 27,647 |
| `Person.BusinessEntity` | 20,777 |
| `Person.EmailAddress` | 19,972 |
| `Person.Password` | 19,972 |
| `Person.Person` | 19,972 |
| `Person.PersonPhone` | 19,972 |
| `Sales.Customer` | 19,820 |
| `Person.Address` | 19,614 |
| `Person.BusinessEntityAddress` | 19,614 |
| `Sales.CreditCard` | 19,118 |
| `Sales.PersonCreditCard` | 19,118 |
| `Sales.CurrencyRate` | 13,532 |
| `Purchasing.PurchaseOrderDetail` | 8,845 |
| `Purchasing.PurchaseOrderHeader` | 4,012 |
| `Production.BillOfMaterials` | 2,679 |
| `dbo.DatabaseLog` | 1,596 |
| `Production.ProductInventory` | 1,069 |
| `Person.BusinessEntityContact` | 909 |
| `Production.ProductDescription` | 762 |
| `Production.ProductModelProductDescriptionCulture` | 762 |
| `Sales.Store` | 701 |
| `Sales.SpecialOfferProduct` | 538 |
| `Production.Product` | 504 |
| `Production.ProductProductPhoto` | 504 |
| `Purchasing.ProductVendor` | 460 |
| `Production.ProductCostHistory` | 395 |
| `Production.ProductListPriceHistory` | 395 |
| `HumanResources.EmployeePayHistory` | 316 |
| `HumanResources.EmployeeDepartmentHistory` | 296 |
| `HumanResources.Employee` | 290 |
| `Person.CountryRegion` | 238 |
| `Person.StateProvince` | 181 |
| `Sales.SalesPersonQuotaHistory` | 163 |
| `Production.ProductModel` | 128 |
| `Sales.CountryRegionCurrency` | 109 |
| `Sales.Currency` | 105 |
| `Purchasing.Vendor` | 104 |
| `Production.ProductPhoto` | 101 |
| `Production.UnitMeasure` | 38 |
| `Production.ProductSubcategory` | 37 |
| `Production.ProductDocument` | 32 |
| `Sales.SalesTaxRate` | 29 |
| `Person.ContactType` | 20 |
| `Sales.SalesPerson` | 17 |
| `Sales.SalesTerritoryHistory` | 17 |
| `HumanResources.Department` | 16 |
| `Production.ScrapReason` | 16 |
| `Sales.SpecialOffer` | 16 |
| `Production.Location` | 14 |
| `HumanResources.JobCandidate` | 13 |
| `Production.Document` | 13 |
| `Sales.SalesReason` | 10 |
| `Sales.SalesTerritory` | 10 |
| `Production.Culture` | 8 |
| `Production.ProductModelIllustration` | 7 |
| `Person.AddressType` | 6 |
| `Production.Illustration` | 5 |
| `Purchasing.ShipMethod` | 5 |
| `Production.ProductCategory` | 4 |
| `Production.ProductReview` | 4 |
| `HumanResources.Shift` | 3 |
| `Person.PhoneNumberType` | 3 |
| `Sales.ShoppingCartItem` | 3 |
| `dbo.AWBuildVersion` | 1 |
| `dbo.ErrorLog` | 0 |

Módulos: 11 funcion, 10 procedimiento, 10 trigger, 20 vista.

Triggers: `humanresources.demployee` sobre `humanresources.employee`, `person.iuperson` sobre `person.person`, `production.iworkorder` sobre `production.workorder`, `production.uworkorder` sobre `production.workorder`, `purchasing.dvendor` sobre `purchasing.vendor`, `purchasing.ipurchaseorderdetail` sobre `purchasing.purchaseorderdetail`, `purchasing.upurchaseorderdetail` sobre `purchasing.purchaseorderdetail`, `purchasing.upurchaseorderheader` sobre `purchasing.purchaseorderheader`, `sales.idusalesorderdetail` sobre `sales.salesorderdetail`, `sales.usalesorderheader` sobre `sales.salesorderheader`.

Jobs: no se restauró msdb, así que no se pueden inventariar (viven ahí, no en la base).


## Hallazgos por patrón

| Patrón | Hallazgos |
|---|---:|
| Selección no determinista: TOP sin ORDER BY o asignación desde varias filas | 3 |
| INNER JOIN a una tabla hija | 10 |
| Reloj del servidor (GETDATE y similares) en una regla, directo o por una variable | 0 |
| IF EXISTS sin ELSE que escribe datos (camino silencioso) | 4 |
| IF EXISTS sin ELSE con cuerpo de guarda o DDL (informativo) | 0 |
| Conversión de zona con desfase fijo | 0 |
| ROUND con tercer argumento: trunca en vez de redondear | 0 |
| Centinelas en vez de NULL (por distribución de valores) | 14 |
| Texto con mojibake (UTF-8 leído como latin-1) | 0 |
| Espacios finales que SQL Server ignora al comparar y PostgreSQL no | 0 |
| Re-registro: el mismo documento con otra llave interna | 0 |
| Llave candidata con duplicados (no parece re-registro) | 3 |
| Columnas que ningún módulo lee | 72 |
| Tablas que ningún módulo lee | 38 |
| Literales mágicos (números y códigos en duro) | 29 |

### Selección no determinista: TOP sin ORDER BY o asignación desde varias filas (3)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.ufngetproductdealerprice` | 14 | asigna @DealerPrice desde production.product sin TOP ni agregado y sin filtro único (sin WHERE; llaves únicas de la tabla: productid; productnumber; name; rowguid): la variable se queda con la última fila que entregue el plan | `SELECT @DealerPrice = plph.[ListPrice] * @DealerDiscount` |
| `dbo.ufngetproductlistprice` | 8 | asigna @ListPrice desde production.product sin TOP ni agregado y sin filtro único (sin WHERE; llaves únicas de la tabla: productid; productnumber; name; rowguid): la variable se queda con la última fila que entregue el plan | `SELECT @ListPrice = plph.[ListPrice]` |
| `dbo.ufngetproductstandardcost` | 9 | asigna @StandardCost desde production.product sin TOP ni agregado y sin filtro único (sin WHERE; llaves únicas de la tabla: productid; productnumber; name; rowguid): la variable se queda con la última fila que entregue el plan | `SELECT @StandardCost = pch.[StandardCost]` |

### INNER JOIN a una tabla hija (10)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.ufngetproductdealerprice` | 16 | INNER JOIN de production.product a su tabla hija production.productlistpricehistory: descarta los registros de production.product sin production.productlistpricehistory | `INNER JOIN [Production].[ProductListPriceHistory] plph` |
| `dbo.ufngetproductlistprice` | 10 | INNER JOIN de production.product a su tabla hija production.productlistpricehistory: descarta los registros de production.product sin production.productlistpricehistory | `INNER JOIN [Production].[ProductListPriceHistory] plph` |
| `dbo.ufngetproductstandardcost` | 11 | INNER JOIN de production.product a su tabla hija production.productcosthistory: descarta los registros de production.product sin production.productcosthistory | `INNER JOIN [Production].[ProductCostHistory] pch` |
| `dbo.ufngetcontactinformation` | 58 | INNER JOIN de person.person a su tabla hija sales.customer: descarta los registros de person.person sin sales.customer | `INNER JOIN [Sales].[Customer] AS c` |
| `dbo.ufngetcontactinformation` | 64 | INNER JOIN de person.person a su tabla hija sales.customer: descarta los registros de person.person sin sales.customer | `INNER JOIN [Sales].[Customer] AS c` |
| `humanresources.vemployeedepartment` | 18 | INNER JOIN de humanresources.employee a su tabla hija humanresources.employeedepartmenthistory: descarta los registros de humanresources.employee sin humanresources.employeedepartmenthistory | `INNER JOIN [HumanResources].[EmployeeDepartmentHistory] edh` |
| `humanresources.vemployeedepartmenthistory` | 19 | INNER JOIN de humanresources.employee a su tabla hija humanresources.employeedepartmenthistory: descarta los registros de humanresources.employee sin humanresources.employeedepartmenthistory | `INNER JOIN [HumanResources].[EmployeeDepartmentHistory] edh` |
| `production.vproductanddescription` | 15 | INNER JOIN de production.productmodel a su tabla hija production.productmodelproductdescriptionculture: descarta los registros de production.productmodel sin production.productmodelproductdescriptionculture | `INNER JOIN [Production].[ProductModelProductDescriptionCulture] pmx` |
| `sales.vindividualcustomer` | 34 | INNER JOIN de person.person a su tabla hija sales.customer: descarta los registros de person.person sin sales.customer | `INNER JOIN [Sales].[Customer] c` |
| `sales.vsalespersonsalesbyfiscalyears` | 20 | INNER JOIN de sales.salesperson a su tabla hija sales.salesorderheader: descarta los registros de sales.salesperson sin sales.salesorderheader | `INNER JOIN [Sales].[SalesOrderHeader] soh` |

### IF EXISTS sin ELSE que escribe datos (camino silencioso) (4)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.ufngetcontactinformation` | 18 | IF EXISTS sin ELSE que escribe datos: cuando la condición no se cumple no pasa nada y nadie se entera (camino silencioso) | `IF EXISTS(SELECT * FROM [HumanResources].[Employee] e` |
| `dbo.ufngetcontactinformation` | 27 | IF EXISTS sin ELSE que escribe datos: cuando la condición no se cumple no pasa nada y nadie se entera (camino silencioso) | `IF EXISTS(SELECT * FROM [Purchasing].[Vendor] AS v` |
| `dbo.ufngetcontactinformation` | 42 | IF EXISTS sin ELSE que escribe datos: cuando la condición no se cumple no pasa nada y nadie se entera (camino silencioso) | `IF EXISTS(SELECT * FROM [Sales].[Store] AS s` |
| `dbo.ufngetcontactinformation` | 57 | IF EXISTS sin ELSE que escribe datos: cuando la condición no se cumple no pasa nada y nadie se entera (camino silencioso) | `IF EXISTS(SELECT * FROM [Person].[Person] AS p` |

### Centinelas en vez de NULL (por distribución de valores) (14)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `person.person.emailpromotion` |  | 11,158 filas (55.9%) con Decimal('0'): 0 queda fuera del rango del resto de la columna (1 … 2); la columna no usa NULL |  |
| `production.billofmaterials.bomlevel` |  | 103 filas (3.8%) con Decimal('0'): 0 queda fuera del rango del resto de la columna (1 … 4); la columna no usa NULL |  |
| `production.product.standardcost` |  | 200 filas (39.7%) con Decimal('0.0000'): 0.0000 queda fuera del rango del resto de la columna (0.8565 … 2171.2942); la columna no usa NULL |  |
| `production.product.listprice` |  | 200 filas (39.7%) con Decimal('0.0000'): 0.0000 queda fuera del rango del resto de la columna (2.2900 … 3578.2700); la columna no usa NULL |  |
| `production.product.daystomanufacture` |  | 246 filas (48.8%) con Decimal('0'): 0 queda fuera del rango del resto de la columna (1 … 4); la columna no usa NULL |  |
| `production.productinventory.shelf` |  | 290 filas (27.1%) con 'N/A': valor de relleno típico ('N/A'); la columna no usa NULL |  |
| `production.productinventory.bin` |  | 328 filas (30.7%) con Decimal('0'): 0 queda fuera del rango del resto de la columna (1 … 61); la columna no usa NULL |  |
| `production.transactionhistory.referenceorderlineid` |  | 31,002 filas (27.3%) con Decimal('0'): 0 queda fuera del rango del resto de la columna (1 … 71); la columna no usa NULL |  |
| `production.transactionhistory.actualcost` |  | 31,002 filas (27.3%) con Decimal('0.0000'): 0.0000 queda fuera del rango del resto de la columna (0.2100 … 2443.3500); la columna no usa NULL |  |
| `production.transactionhistoryarchive.referenceorderlineid` |  | 41,589 filas (46.6%) con Decimal('0'): 0 queda fuera del rango del resto de la columna (1 … 72); la columna no usa NULL |  |
| `production.transactionhistoryarchive.actualcost` |  | 41,589 filas (46.6%) con Decimal('0.0000'): 0.0000 queda fuera del rango del resto de la columna (0.2100 … 3578.2700); la columna no usa NULL |  |
| `production.workorder.scrappedqty` |  | 71,862 filas (99.0%) con Decimal('0'): 0 queda fuera del rango del resto de la columna (1 … 673); la columna no usa NULL |  |
| `purchasing.purchaseorderdetail.rejectedqty` |  | 8,282 filas (93.6%) con Decimal('0.00'): 0.00 queda fuera del rango del resto de la columna (1.00 … 1250.00); la columna no usa NULL |  |
| `sales.salesorderdetail.unitpricediscount` |  | 118,035 filas (97.3%) con Decimal('0.0000'): 0.0000 queda fuera del rango del resto de la columna (0.0200 … 0.4000); la columna no usa NULL |  |

### Llave candidata con duplicados (no parece re-registro) (3)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `person.address.addressline1` |  | 6,047 filas repiten un valor (13,567 distintos en 19,614); las filas repetidas comparten el 20% de sus columnas (dos filas cualesquiera, el 45%); en 28 de 40 grupos la fila de id mayor es la de ModifiedDate más reciente |  |
| `person.address.addressline2` |  | 167 filas repiten un valor (195 distintos en 362); las filas repetidas comparten el 9% de sus columnas (dos filas cualesquiera, el 45%); en 20 de 40 grupos la fila de id mayor es la de ModifiedDate más reciente |  |
| `production.productdescription.description` |  | 29 filas repiten un valor (733 distintos en 762); las filas repetidas comparten el 50% de sus columnas (dos filas cualesquiera, el 24%); en 29 de 29 grupos la fila de id mayor es la de ModifiedDate más reciente |  |

### Columnas que ningún módulo lee (72)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `humanresources.employee.nationalidnumber` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `humanresources.employee.loginid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `humanresources.employee.organizationlevel` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `humanresources.employee.hiredate` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `humanresources.employee.salariedflag` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `humanresources.employee.vacationhours` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `humanresources.employee.sickleavehours` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `humanresources.employee.currentflag` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `humanresources.shift.starttime` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `humanresources.shift.endtime` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `person.address.spatiallocation` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `person.emailaddress.emailaddressid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `person.person.persontype` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `person.person.namestyle` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.billofmaterials.billofmaterialsid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.billofmaterials.unitmeasurecode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.productnumber` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.makeflag` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.finishedgoodsflag` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.safetystocklevel` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.reorderpoint` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.size` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.sizeunitmeasurecode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.weightunitmeasurecode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.weight` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.daystomanufacture` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.class` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.productsubcategoryid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.sellstartdate` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.sellenddate` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.product.discontinueddate` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.productinventory.shelf` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `production.productinventory.bin` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderdetail.duedate` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderdetail.receivedqty` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderdetail.rejectedqty` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderdetail.stockedqty` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderheader.employeeid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderheader.vendorid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderheader.shipmethodid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderheader.shipdate` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderheader.taxamt` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderheader.freight` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.purchaseorderheader.totaldue` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.vendor.accountnumber` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.vendor.creditrating` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.vendor.preferredvendorstatus` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.vendor.activeflag` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `purchasing.vendor.purchasingwebserviceurl` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.customer.accountnumber` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderdetail.carriertrackingnumber` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderdetail.specialofferid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.duedate` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.shipdate` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.onlineorderflag` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.salesordernumber` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.purchaseordernumber` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.accountnumber` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.billtoaddressid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.shiptoaddressid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.shipmethodid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.creditcardid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.creditcardapprovalcode` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.currencyrateid` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.taxamt` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.freight` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.totaldue` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesorderheader.comment` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesperson.bonus` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesperson.commissionpct` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesterritory.costytd` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `sales.salesterritory.costlastyear` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |

### Tablas que ningún módulo lee (38)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.awbuildversion` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `dbo.databaselog` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `dbo.errorlog` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `humanresources.employeepayhistory` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `person.businessentity` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `person.password` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.culture` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.document` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.illustration` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.location` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.productcategory` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.productdocument` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.productmodelillustration` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.productphoto` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.productproductphoto` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.productreview` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.productsubcategory` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.scrapreason` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.transactionhistory` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.transactionhistoryarchive` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.unitmeasure` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.workorder` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `production.workorderrouting` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `purchasing.productvendor` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `purchasing.shipmethod` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `sales.countryregioncurrency` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `sales.creditcard` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `sales.currency` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `sales.currencyrate` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `sales.personcreditcard` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `sales.salesorderheadersalesreason` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `sales.salespersonquotahistory` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `sales.salesreason` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `sales.salestaxrate` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `sales.salesterritoryhistory` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `sales.shoppingcartitem` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `sales.specialoffer` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |
| `sales.specialofferproduct` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |

### Literales mágicos (números y códigos en duro) (29)

| Objeto | Literales distintos | Ejemplos |
|---|---:|---|
| `dbo.ufngetsalesorderstatustext` | 5 | `2`, `3`, `4`, `5`, `6` |
| `dbo.ufngetpurchaseorderstatustext` | 3 | `2`, `3`, `4` |
| `dbo.ufngetaccountingenddate` | 2 | `-2`, `112` |
| `dbo.ufngetdocumentstatustext` | 2 | `2`, `3` |
| `dbo.ufngetproductdealerprice` | 2 | `0.60`, `112` |
| `dbo.ufngetaccountingstartdate` | 1 | `112` |
| `dbo.ufngetproductlistprice` | 1 | `112` |
| `dbo.ufngetproductstandardcost` | 1 | `112` |
| `dbo.ufngetstock` | 1 | `'6'` |
| `dbo.ufnleadingzeros` | 1 | `8` |
| `dbo.uspgetbillofmaterials` | 1 | `25` |
| `dbo.uspgetemployeemanagers` | 1 | `25` |
| `dbo.uspgetmanageremployees` | 1 | `25` |
| `dbo.uspgetwhereusedproductid` | 1 | `25` |
| `person.iuperson` | 1 | `N'<IndividualSurvey xmlns="http://schemas.microsoft.com/sqlserver/2004/07/adventure-works/IndividualSurvey">              <TotalPurchaseYTD>0.00</TotalPurchaseYTD>              </IndividualSurvey>'` |
| `sales.usalesorderheader` | 1 | `5` |
| `humanresources.vjobcandidateeducation` | 1 | `101` |
| `humanresources.vjobcandidateemployment` | 1 | `101` |
| `sales.vpersondemographics` | 1 | `101` |
| `sales.vsalespersonsalesbyfiscalyears` | 1 | `6` |

## Tiempos

arranque_contenedor: 8.4 s · restauracion: 5.3 s · inventario: 2.2 s · patrones_codigo: 0.1 s · patrones_datos: 13.3 s · total: 29.7 s

