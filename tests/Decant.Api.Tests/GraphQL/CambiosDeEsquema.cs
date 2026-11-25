using HotChocolate.Language;

namespace Decant.Api.Tests.GraphQL;

/// <summary>
/// Clasifica las diferencias entre dos SDL: qué ROMPE a un cliente que ya existe (quitar un tipo, un campo, un
/// argumento o un valor de enumeración; volver anulable una salida; cambiar un tipo; exigir un argumento nuevo) y qué
/// no (agregar). Lo usa la prueba de instantánea para decir, al fallar, si el cambio necesita versión.
/// </summary>
public static class CambiosDeEsquema
{
    public sealed record Cambio(bool Rompe, string Descripcion)
    {
        public override string ToString() => $"{(Rompe ? "ROMPE" : "no rompe")}: {Descripcion}";
    }

    public static IReadOnlyList<Cambio> Comparar(string anterior, string nuevo)
    {
        var antes = Definiciones(anterior);
        var despues = Definiciones(nuevo);
        var cambios = new List<Cambio>();
        foreach (var (nombre, viejo) in antes)
        {
            if (!despues.TryGetValue(nombre, out var actual))
            {
                cambios.Add(new(true, $"se quitó {nombre}"));
            }
            else if (viejo.Kind != actual.Kind)
            {
                cambios.Add(new(true, $"{nombre} cambió de {viejo.Kind} a {actual.Kind}"));
            }
            else
            {
                cambios.AddRange(CompararTipo(nombre, viejo, actual));
            }
        }

        cambios.AddRange(despues.Keys.Except(antes.Keys).Select(n => new Cambio(false, $"se agregó {n}")));
        return cambios;
    }

    private static Dictionary<string, IDefinitionNode> Definiciones(string sdl) =>
        Utf8GraphQLParser.Parse(sdl).Definitions.ToDictionary(Nombre, StringComparer.Ordinal);

    private static string Nombre(IDefinitionNode definicion) => definicion switch
    {
        INamedSyntaxNode n => n.Name.Value,
        DirectiveDefinitionNode d => "@" + d.Name.Value,
        SchemaDefinitionNode => "schema",
        _ => definicion.ToString(),
    };

    private static IEnumerable<Cambio> CompararTipo(string nombre, IDefinitionNode viejo, IDefinitionNode actual) =>
        (viejo, actual) switch
        {
            (ObjectTypeDefinitionNode a, ObjectTypeDefinitionNode b) => CompararCampos(nombre, a.Fields, b.Fields),
            (InterfaceTypeDefinitionNode a, InterfaceTypeDefinitionNode b) =>
                CompararCampos(nombre, a.Fields, b.Fields),
            (EnumTypeDefinitionNode a, EnumTypeDefinitionNode b) => a.Values.Select(v => v.Name.Value)
                .Except(b.Values.Select(v => v.Name.Value))
                .Select(v => new Cambio(true, $"se quitó el valor {nombre}.{v}")),
            (SchemaDefinitionNode a, SchemaDefinitionNode b) when a.ToString() != b.ToString() =>
                [new Cambio(true, "cambiaron las raíces del esquema")],
            _ => [],
        };

    private static IEnumerable<Cambio> CompararCampos(string tipo, IReadOnlyList<FieldDefinitionNode> antes,
        IReadOnlyList<FieldDefinitionNode> despues)
    {
        var nuevos = despues.ToDictionary(f => f.Name.Value, StringComparer.Ordinal);
        foreach (var campo in antes)
        {
            var nombre = $"{tipo}.{campo.Name.Value}";
            if (!nuevos.TryGetValue(campo.Name.Value, out var actual))
            {
                yield return new(true, $"se quitó el campo {nombre}");
                continue;
            }

            var (t0, t1) = (campo.Type.ToString(), actual.Type.ToString());
            if (t0 != t1)
            {
                // Una salida que se vuelve más estricta (T → T!) no rompe; todo lo demás, sí.
                yield return new(t1 != t0 + "!", $"{nombre}: {t0} → {t1}");
            }

            foreach (var cambio in CompararArgumentos(nombre, campo.Arguments, actual.Arguments))
            {
                yield return cambio;
            }
        }

        foreach (var agregado in nuevos.Keys.Except(antes.Select(f => f.Name.Value)))
        {
            yield return new(false, $"se agregó el campo {tipo}.{agregado}");
        }
    }

    private static IEnumerable<Cambio> CompararArgumentos(string campo, IReadOnlyList<InputValueDefinitionNode> antes,
        IReadOnlyList<InputValueDefinitionNode> despues)
    {
        var nuevos = despues.ToDictionary(a => a.Name.Value, StringComparer.Ordinal);
        foreach (var arg in antes)
        {
            if (!nuevos.TryGetValue(arg.Name.Value, out var actual))
            {
                yield return new(true, $"se quitó el argumento {campo}({arg.Name.Value})");
                continue;
            }

            var (t0, t1) = (arg.Type.ToString(), actual.Type.ToString());
            if (t0 != t1)
            {
                // Una entrada que se relaja (T! → T) no rompe; todo lo demás, sí.
                yield return new(t0 != t1 + "!", $"{campo}({arg.Name.Value}): {t0} → {t1}");
            }
        }

        foreach (var arg in despues.Where(a => antes.All(v => v.Name.Value != a.Name.Value)))
        {
            var exigido = arg.Type is NonNullTypeNode && arg.DefaultValue is null;
            yield return new(exigido, $"se agregó el argumento {(exigido ? "obligatorio " : "")}{campo}({arg.Name.Value})");
        }
    }
}
