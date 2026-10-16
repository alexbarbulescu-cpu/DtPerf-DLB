using System.Diagnostics;
using System.Globalization;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace DtPerf;

public static class Env
{
    public static string Runtime =>
        RuntimeFeature.IsDynamicCodeCompiled
            ? $".NET {Environment.Version.Major}.{Environment.Version.Minor} JIT"
            : $".NET {Environment.Version.Major}.{Environment.Version.Minor} NativeAOT";
    public static string Describe() =>
        $"{RuntimeInformation.FrameworkDescription}; dynamicCodeCompiled={RuntimeFeature.IsDynamicCodeCompiled}; " +
        $"os={RuntimeInformation.OSDescription}; arch={RuntimeInformation.ProcessArchitecture}; cpus={Environment.ProcessorCount}; " +
        $"serverGC={System.Runtime.GCSettings.IsServerGC}; tieredPGO={Environment.GetEnvironmentVariable("DOTNET_TieredPGO") ?? "default"}";
}

public sealed record BenchResult(string Runtime, string Category, string Method, int P, int OpsPerIter, int Iterations,
    double MedianNs, double MeanNs, double SdNs, double Ci95Ns, double MinNs, double AllocBytesPerOp)
{
    public static string Header => "Runtime,Category,Method,P,OpsPerIter,Iterations,MedianNs,MeanNs,SdNs,Ci95Ns,MinNs,AllocBytesPerOp";
    public string ToCsv() => string.Join(",", Runtime, Category, Method, P, OpsPerIter, Iterations,
        F(MedianNs), F(MeanNs), F(SdNs), F(Ci95Ns), F(MinNs), F(AllocBytesPerOp));
    static string F(double x) => x.ToString("0.####", CultureInfo.InvariantCulture);
}

/// <summary>
/// Minimal BenchmarkDotNet-style harness (no external packages): time-based warm-up that lets tiered
/// compilation/PGO reach steady state, pilot phase to size iterations (~TargetIterMs), GC fence before
/// every iteration, per-op statistics with t-based 95% CI, and allocation tracking per op.
/// </summary>
public static class Harness
{
    public static double WarmupMs = 1500, TargetIterMs = 25;
    public static int Iterations = 30;
    public static object? Sink;

    public static BenchResult Run(string category, string method, int p, Action<int> body)
    {
        // warm-up (time based) with small batches to trigger tier-1 + OSR + dynamic PGO
        var sw = Stopwatch.StartNew();
        int n = 64;
        while (sw.Elapsed.TotalMilliseconds < WarmupMs) body(n);
        // pilot
        n = 1;
        while (true)
        {
            sw.Restart(); body(n); sw.Stop();
            if (sw.Elapsed.TotalMilliseconds >= TargetIterMs || n >= 1 << 26) break;
            n = sw.Elapsed.TotalMilliseconds < 1 ? n * 8 : (int)Math.Min(1 << 26, n * TargetIterMs / sw.Elapsed.TotalMilliseconds * 1.05);
        }
        var samples = new double[Iterations];
        long allocTotal = 0;
        for (int i = 0; i < Iterations; i++)
        {
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            long a0 = GC.GetAllocatedBytesForCurrentThread();
            long t0 = Stopwatch.GetTimestamp();
            body(n);
            long t1 = Stopwatch.GetTimestamp();
            allocTotal += GC.GetAllocatedBytesForCurrentThread() - a0;
            samples[i] = (t1 - t0) * 1e9 / Stopwatch.Frequency / n;
        }
        Array.Sort(samples);
        double mean = samples.Average();
        double sd = Math.Sqrt(samples.Sum(x => (x - mean) * (x - mean)) / (samples.Length - 1));
        double ci = TCrit95(samples.Length - 1) * sd / Math.Sqrt(samples.Length);
        double median = samples.Length % 2 == 1 ? samples[samples.Length / 2]
            : (samples[samples.Length / 2 - 1] + samples[samples.Length / 2]) / 2;
        var r = new BenchResult(Env.Runtime, category, method, p, n, Iterations, median, mean, sd, ci, samples[0],
            (double)allocTotal / ((long)n * Iterations));
        Console.Error.WriteLine($"  {category,-12} {method,-28} P={p,-3} median={median,10:F2} ns  ±{ci:F2}  alloc={r.AllocBytesPerOp:F1} B/op");
        return r;
    }

    static double TCrit95(int df) => df switch
    {
        >= 120 => 1.980, >= 60 => 2.000, >= 40 => 2.021, >= 30 => 2.042, >= 29 => 2.045, >= 20 => 2.086,
        >= 15 => 2.131, >= 10 => 2.228, >= 5 => 2.571, _ => 12.706
    };
}
