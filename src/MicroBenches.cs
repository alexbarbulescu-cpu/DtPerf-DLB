using System.Diagnostics;
using System.Linq.Expressions;
using System.Reflection;
using System.Runtime.CompilerServices;

namespace DtPerf;

public static class MicroBenches
{
    [UnsafeAccessor(UnsafeAccessorKind.Constructor)]
    static extern Telemetry5 NewViaAccessor();
    [UnsafeAccessor(UnsafeAccessorKind.Method, Name = "set_Vibration")]
    static extern void SetVibrationViaAccessor(Telemetry5 t, double v);

    public static List<BenchResult> RunAll()
    {
        var res = new List<BenchResult>();
        res.AddRange(Instantiation());
        res.AddRange(Setters());
        res.AddRange(Materialization<Telemetry5>(5));
        res.AddRange(Materialization<Telemetry20>(20));
        res.AddRange(Materialization<Telemetry50>(50));
        return res;
    }

    public static List<BenchResult> Materialization20() => Materialization<Telemetry20>(20).ToList();

    // control suite: S4 vs S5 vs S5b on a hot payload (P = 5/20/50) and all strategies on 65,536 distinct payloads (cold caches)
    public static List<BenchResult> Control()
    {
        var res = new List<BenchResult>();
        res.AddRange(Ctl<Telemetry5>(5)); res.AddRange(Ctl<Telemetry20>(20)); res.AddRange(Ctl<Telemetry50>(50));
        var rng = new Random(11); const int N = 1 << 16;
        var payloads = new Dictionary<string, object?>[N];
        for (int i = 0; i < N; i++) payloads[i] = Payloads.Create<Telemetry20>(rng, i, i);
        foreach (var name in MaterializerNames.All.Append(MaterializerNames.GeneratedLookup))
        {
            var m = MaterializerFactory.Create<Telemetry20>(name); int k = 0;
            res.Add(Harness.Run("MaterializeCold", name, 20, n => { object? s = null; for (int i = 0; i < n; i++) s = m.Map(payloads[(k++) & (N - 1)]); Harness.Sink = s; }));
        }
        return res;
    }
    static IEnumerable<BenchResult> Ctl<T>(int p) where T : class, new()
    {
        var payload = Payloads.Create<T>(new Random(7));
        foreach (var name in MaterializerNames.Control)
        {
            var m = MaterializerFactory.Create<T>(name);
            yield return Harness.Run("MaterializeCtl", name, p, n => { object? s = null; for (int i = 0; i < n; i++) s = m.Map(payload); Harness.Sink = s; });
        }
    }

    // every strategy must produce the same snapshot for the same payload
    public static string Verify()
    {
        int checks = 0;
        string Check<T>(int seeds) where T : class, new()
        {
            var names = MaterializerNames.All.Append(MaterializerNames.GeneratedLookup).ToArray();
            var ms = names.Select(n => MaterializerFactory.Create<T>(n)).ToArray();
            var props = typeof(T).GetProperties();
            for (int s = 0; s < seeds; s++)
            {
                var pl = Payloads.Create<T>(new Random(s), s, s);
                var refObj = ms[names.Length - 2].Map(pl);   // S5
                foreach (var m in ms)
                {
                    var o = m.Map(pl);
                    foreach (var pr in props)
                        if (!Equals(pr.GetValue(o), pr.GetValue(refObj))) return $"MISMATCH {typeof(T).Name} {m.Name} {pr.Name}";
                    checks++;
                }
            }
            return "";
        }
        var r = Check<Telemetry5>(200) + Check<Telemetry20>(200) + Check<Telemetry50>(200);
        return r == "" ? $"OK {checks} snapshot comparisons, all strategies identical" : r;
    }

    // ---------------- RQ1: instantiation ----------------
    static IEnumerable<BenchResult> Instantiation()
    {
        Func<Telemetry5> direct = static () => new Telemetry5();
        var type = typeof(Telemetry5);
        var ctor = type.GetConstructor(Type.EmptyTypes)!;
        var invoker = ConstructorInvoker.Create(ctor);
        var compiled = Expression.Lambda<Func<Telemetry5>>(Expression.New(type)).Compile();

        yield return Harness.Run("Instantiate", "Direct (new T())", 5, n => { object? s = null; for (int i = 0; i < n; i++) s = direct(); Harness.Sink = s; });
        yield return Harness.Run("Instantiate", "UnsafeAccessor", 5, n => { object? s = null; for (int i = 0; i < n; i++) s = NewViaAccessor(); Harness.Sink = s; });
        yield return Harness.Run("Instantiate", "Activator.CreateInstance<T>", 5, n => { object? s = null; for (int i = 0; i < n; i++) s = Activator.CreateInstance<Telemetry5>(); Harness.Sink = s; });
        yield return Harness.Run("Instantiate", "Activator.CreateInstance(Type)", 5, n => { object? s = null; for (int i = 0; i < n; i++) s = Activator.CreateInstance(type); Harness.Sink = s; });
        yield return Harness.Run("Instantiate", "ConstructorInfo.Invoke", 5, n => { object? s = null; for (int i = 0; i < n; i++) s = ctor.Invoke(null); Harness.Sink = s; });
        yield return Harness.Run("Instantiate", "ConstructorInvoker", 5, n => { object? s = null; for (int i = 0; i < n; i++) s = invoker.Invoke(); Harness.Sink = s; });
        yield return Harness.Run("Instantiate", "Compiled expression", 5, n => { object? s = null; for (int i = 0; i < n; i++) s = compiled(); Harness.Sink = s; });
    }

    // ---------------- RQ2: property setters ----------------
    static IEnumerable<BenchResult> Setters()
    {
        var t = new Telemetry5();
        var prop = typeof(Telemetry5).GetProperty(nameof(Telemetry5.Vibration))!;
        var setM = prop.GetSetMethod()!;
        var mInvoker = MethodInvoker.Create(setM);
        var typedDelegate = (Action<Telemetry5, double>)setM.CreateDelegate(typeof(Action<Telemetry5, double>));
        var o = Expression.Parameter(typeof(Telemetry5)); var v = Expression.Parameter(typeof(double));
        var typedExpr = Expression.Lambda<Action<Telemetry5, double>>(Expression.Assign(Expression.Property(o, prop), v), o, v).Compile();
        var vo = Expression.Parameter(typeof(object));
        var boxedExpr = Expression.Lambda<Action<Telemetry5, object?>>(Expression.Assign(Expression.Property(o, prop), Expression.Convert(vo, typeof(double))), o, vo).Compile();
        double val = 42.5; object boxed = val;

        yield return Harness.Run("SetProperty", "Direct (t.P = v)", 5, n => { for (int i = 0; i < n; i++) t.Vibration = val; Harness.Sink = t; });
        yield return Harness.Run("SetProperty", "UnsafeAccessor", 5, n => { for (int i = 0; i < n; i++) SetVibrationViaAccessor(t, val); Harness.Sink = t; });
        yield return Harness.Run("SetProperty", "PropertyInfo.SetValue", 5, n => { for (int i = 0; i < n; i++) prop.SetValue(t, boxed); Harness.Sink = t; });
        yield return Harness.Run("SetProperty", "MethodInvoker", 5, n => { for (int i = 0; i < n; i++) mInvoker.Invoke(t, boxed); Harness.Sink = t; });
        yield return Harness.Run("SetProperty", "CreateDelegate (typed)", 5, n => { for (int i = 0; i < n; i++) typedDelegate(t, val); Harness.Sink = t; });
        yield return Harness.Run("SetProperty", "Compiled expression (typed)", 5, n => { for (int i = 0; i < n; i++) typedExpr(t, val); Harness.Sink = t; });
        yield return Harness.Run("SetProperty", "Compiled expression (object)", 5, n => { for (int i = 0; i < n; i++) boxedExpr(t, boxed); Harness.Sink = t; });
    }

    // ---------------- RQ3a: whole-snapshot materialization ----------------
    static IEnumerable<BenchResult> Materialization<T>(int p) where T : class, new()
    {
        var payload = Payloads.Create<T>(new Random(7));
        foreach (var name in MaterializerNames.All)
        {
            var m = MaterializerFactory.Create<T>(name);
            yield return Harness.Run("Materialize", name, p, n => { object? s = null; for (int i = 0; i < n; i++) s = m.Map(payload); Harness.Sink = s; });
        }
    }

    // ---------------- RQ3b: cold-start cost (one strategy per fresh process) ----------------
    public static string Cold(int p, string name)
    {
        var payload = p switch { 5 => Payloads.Create<Telemetry5>(new Random(7)), 20 => Payloads.Create<Telemetry20>(new Random(7)), _ => Payloads.Create<Telemetry50>(new Random(7)) };
        long t0 = Stopwatch.GetTimestamp();
        Func<object> first;
        switch (p)
        {
            case 5: { var m = MaterializerFactory.Create<Telemetry5>(name); first = () => m.Map(payload); break; }
            case 20: { var m = MaterializerFactory.Create<Telemetry20>(name); first = () => m.Map(payload); break; }
            default: { var m = MaterializerFactory.Create<Telemetry50>(name); first = () => m.Map(payload); break; }
        }
        long t1 = Stopwatch.GetTimestamp();
        Harness.Sink = first();
        long t2 = Stopwatch.GetTimestamp();
        Harness.Sink = first();
        long t3 = Stopwatch.GetTimestamp();
        double ms(long a, long b) => (b - a) * 1000.0 / Stopwatch.Frequency;
        return string.Join(",", Env.Runtime, name, p,
            ms(t0, t1).ToString("0.####", System.Globalization.CultureInfo.InvariantCulture),
            ms(t1, t2).ToString("0.####", System.Globalization.CultureInfo.InvariantCulture),
            ms(t2, t3).ToString("0.####", System.Globalization.CultureInfo.InvariantCulture));
    }
}
