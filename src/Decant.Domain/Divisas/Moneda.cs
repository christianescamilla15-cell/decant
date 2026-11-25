namespace Decant.Domain.Divisas;

/// <summary>Moneda ISO 4217. <see cref="Decimales"/> viene del estándar; el legado no la aplica a los montos (D2).</summary>
public sealed record Moneda(string Codigo, string Numerico, string Nombre, int Decimales, bool Activa);
