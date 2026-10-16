using System.Linq.Expressions;
using System.Reflection;

namespace DtPerf;

/// <summary>Maps a decoded telemetry payload (string -> boxed value) to a typed twin snapshot.</summary>
public interface IMaterializer<T>
{
    string Name { get; }
    T Map(Dictionary<string, object?> payload);
}

public static class MaterializerNames
{
    public const string Reflection = "Reflection";
    public const string Invoker = "ReflectionInvoker";
    public const string CompiledPerProperty = "CompiledPerProperty";
    public const string CompiledWhole = "CompiledWhole";
    public const string Generated = "Generated";
    public static readonly string[] All = { Reflection, Invoker, CompiledPerProperty, CompiledWhole, Generated };
}

/// <summary>S1: late-bound baseline with cached PropertyInfo (best-practice reflection, no per-call lookup by name).</summary>
public sealed class ReflectionMaterializer<T> : IMaterializer<T> where T : class, new()
{
    private readonly Dictionary<string, PropertyInfo> _props;
    public string Name => MaterializerNames.Reflection;
    public ReflectionMaterializer()
    {
        _props = typeof(T).GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .ToDictionary(p => p.Name, StringComparer.Ordinal);
    }
    public T Map(Dictionary<string, object?> payload)
    {
        var obj = (T)Activator.CreateInstance(typeof(T))!;
        foreach (var kv in payload)
            if (_props.TryGetValue(kv.Key, out var p)) p.SetValue(obj, kv.Value);
        return obj;
    }
}

/// <summary>S2: .NET 8+ ConstructorInvoker / MethodInvoker (modern reflection fast path).</summary>
public sealed class InvokerMaterializer<T> : IMaterializer<T> where T : class, new()
{
    private readonly ConstructorInvoker _ctor;
    private readonly Dictionary<string, MethodInvoker> _setters;
    public string Name => MaterializerNames.Invoker;
    public InvokerMaterializer()
    {
        _ctor = ConstructorInvoker.Create(typeof(T).GetConstructor(Type.EmptyTypes)!);
        _setters = typeof(T).GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .ToDictionary(p => p.Name, p => MethodInvoker.Create(p.GetSetMethod()!), StringComparer.Ordinal);
    }
    public T Map(Dictionary<string, object?> payload)
    {
        var obj = (T)_ctor.Invoke();
        foreach (var kv in payload)
            if (_setters.TryGetValue(kv.Key, out var s)) s.Invoke(obj, kv.Value);
        return obj;
    }
}

/// <summary>S3: compiled factory + one compiled Action&lt;T, object?&gt; per property, cached at start-up.</summary>
public sealed class CompiledPerPropertyMaterializer<T> : IMaterializer<T> where T : class, new()
{
    private readonly Func<T> _factory;
    private readonly Dictionary<string, Action<T, object?>> _setters;
    public string Name => MaterializerNames.CompiledPerProperty;
    public CompiledPerPropertyMaterializer()
    {
        _factory = Expression.Lambda<Func<T>>(Expression.New(typeof(T))).Compile();
        _setters = new Dictionary<string, Action<T, object?>>(StringComparer.Ordinal);
        foreach (var p in typeof(T).GetProperties(BindingFlags.Public | BindingFlags.Instance))
        {
            var o = Expression.Parameter(typeof(T), "o");
            var v = Expression.Parameter(typeof(object), "v");
            var body = Expression.Assign(Expression.Property(o, p), Expression.Convert(v, p.PropertyType));
            _setters[p.Name] = Expression.Lambda<Action<T, object?>>(body, o, v).Compile();
        }
    }
    public T Map(Dictionary<string, object?> payload)
    {
        var obj = _factory();
        foreach (var kv in payload)
            if (_setters.TryGetValue(kv.Key, out var s)) s(obj, kv.Value);
        return obj;
    }
}

/// <summary>S4: a single compiled delegate per type that materializes the whole snapshot
/// (new T(); for each property: if (d.TryGetValue(name, out v)) t.P = (TP)v;).</summary>
public sealed class CompiledWholeMaterializer<T> : IMaterializer<T> where T : class, new()
{
    private readonly Func<Dictionary<string, object?>, T> _map;
    public string Name => MaterializerNames.CompiledWhole;
    public CompiledWholeMaterializer()
    {
        var d = Expression.Parameter(typeof(Dictionary<string, object?>), "d");
        var t = Expression.Variable(typeof(T), "t");
        var v = Expression.Variable(typeof(object), "v");
        var tryGet = typeof(Dictionary<string, object?>).GetMethod(nameof(Dictionary<string, object?>.TryGetValue))!;
        var body = new List<Expression> { Expression.Assign(t, Expression.New(typeof(T))) };
        foreach (var p in typeof(T).GetProperties(BindingFlags.Public | BindingFlags.Instance))
        {
            body.Add(Expression.IfThen(
                Expression.Call(d, tryGet, Expression.Constant(p.Name), v),
                Expression.Assign(Expression.Property(t, p), Expression.Convert(v, p.PropertyType))));
        }
        body.Add(t);
        _map = Expression.Lambda<Func<Dictionary<string, object?>, T>>(Expression.Block(new[] { t, v }, body), d).Compile();
    }
    public T Map(Dictionary<string, object?> payload) => _map(payload);
}

/// <summary>S5: statically generated mapper (what a Roslyn source generator emits); upper bound.</summary>
public sealed class GeneratedMaterializer<T> : IMaterializer<T> where T : class, new()
{
    private readonly Func<Dictionary<string, object?>, T> _map;
    public string Name => MaterializerNames.Generated;
    public GeneratedMaterializer()
    {
        _map = typeof(T) switch
        {
            var x when x == typeof(Telemetry5) => (Func<Dictionary<string, object?>, T>)(object)(Func<Dictionary<string, object?>, Telemetry5>)GeneratedMappers.Map5,
            var x when x == typeof(Telemetry20) => (Func<Dictionary<string, object?>, T>)(object)(Func<Dictionary<string, object?>, Telemetry20>)GeneratedMappers.Map20,
            var x when x == typeof(Telemetry50) => (Func<Dictionary<string, object?>, T>)(object)(Func<Dictionary<string, object?>, Telemetry50>)GeneratedMappers.Map50,
            _ => throw new NotSupportedException(typeof(T).Name)
        };
    }
    public T Map(Dictionary<string, object?> payload) => _map(payload);
}

public static class MaterializerFactory
{
    public static IMaterializer<T> Create<T>(string name) where T : class, new() => name switch
    {
        MaterializerNames.Reflection => new ReflectionMaterializer<T>(),
        MaterializerNames.Invoker => new InvokerMaterializer<T>(),
        MaterializerNames.CompiledPerProperty => new CompiledPerPropertyMaterializer<T>(),
        MaterializerNames.CompiledWhole => new CompiledWholeMaterializer<T>(),
        MaterializerNames.Generated => new GeneratedMaterializer<T>(),
        _ when name.StartsWith("Synthetic") => new SyntheticMaterializer<T>(int.Parse(name.Substring("Synthetic".Length))),
        _ => throw new ArgumentException(name)
    };
}

/// <summary>Technology-agnostic probe: generated mapping plus a calibrated busy-wait of <c>extraNs</c> per message, so that the
/// per-message synchronization cost can be swept as a free parameter of the decision loop.</summary>
public sealed class SyntheticMaterializer<T> : IMaterializer<T> where T : class, new()
{
    private readonly GeneratedMaterializer<T> _inner = new();
    private readonly long _extraTicks;
    public string Name { get; }
    public SyntheticMaterializer(int extraNs)
    {
        Name = "Synthetic" + extraNs;
        _extraTicks = (long)Math.Round(extraNs * (double)System.Diagnostics.Stopwatch.Frequency / 1e9);
    }
    public T Map(Dictionary<string, object?> payload)
    {
        var t = _inner.Map(payload);
        if (_extraTicks > 0)
        {
            long until = System.Diagnostics.Stopwatch.GetTimestamp() + _extraTicks;
            while (System.Diagnostics.Stopwatch.GetTimestamp() < until) { }
        }
        return t;
    }
}

/// <summary>Builds realistic boxed payloads for a telemetry type.</summary>
public static class Payloads
{
    public static Dictionary<string, object?> Create<T>(Random rng, int assetId = 1, long tick = 0)
    {
        var d = new Dictionary<string, object?>(StringComparer.Ordinal);
        foreach (var p in typeof(T).GetProperties(BindingFlags.Public | BindingFlags.Instance))
            d[p.Name] = Sample(p.PropertyType, rng);
        d["AssetId"] = assetId;
        d["Tick"] = tick;
        return d;
    }
    public static object Sample(Type t, Random rng) =>
        t == typeof(double) ? rng.NextDouble() * 100.0 :
        t == typeof(int) ? rng.Next(0, 10_000) :
        t == typeof(long) ? (long)rng.Next() :
        t == typeof(bool) ? rng.Next(2) == 1 :
        t == typeof(DateTime) ? new DateTime(2026, 1, 1).AddSeconds(rng.Next()) :
        throw new NotSupportedException(t.Name);
}
