namespace Decant.Infrastructure.Archivos;

/// <summary>
/// Rutas que salen de datos (la carpeta del universo o del oráculo llega por la línea de órdenes): se arman con
/// <see cref="Path.Join(string?[])"/>, que nunca descarta las partes anteriores como hace <c>Path.Combine</c> ante una
/// parte absoluta, y el resultado DEBE quedar dentro de la raíz. Una parte absoluta, con <c>..</c> o vacía se rechaza.
/// </summary>
public static class RutaDentro
{
    public static string De(string raiz, params string[] partes)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(raiz);
        foreach (var parte in partes)
        {
            if (string.IsNullOrWhiteSpace(parte) || Path.IsPathRooted(parte) ||
                parte.Split('/', '\\').Any(segmento => segmento == ".."))
            {
                throw new ArgumentException($"parte de ruta no permitida: «{parte}»", nameof(partes));
            }
        }

        var base_ = Path.GetFullPath(raiz);
        var ruta = Path.GetFullPath(Path.Join([base_, .. partes]));
        var prefijo = Path.EndsInDirectorySeparator(base_) ? base_ : base_ + Path.DirectorySeparatorChar;
        if (!ruta.StartsWith(prefijo, StringComparison.Ordinal))
        {
            throw new ArgumentException($"la ruta {ruta} queda fuera de {base_}", nameof(partes));
        }

        return ruta;
    }
}
