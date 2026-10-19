using System.Diagnostics;
using System.Globalization;

namespace DtPerf;

/// <summary>
/// Closed-loop digital twin of a fleet of degrading assets (e.g., pumps) with a fixed decision-latency budget per cycle.
/// Each cycle: ingest A telemetry payloads -> materialize typed snapshots (strategy under test) -> update twin state
/// (Holt level/trend filter) -> screen -> anytime Monte-Carlo what-if analysis within the remaining budget ->
/// maintenance decisions (capacity-limited). The physical world and transport (payload decoding) are outside the budget.
/// Every strategy faces the identical world (same seed); only the time left for what-if analysis differs.
/// </summary>
public sealed class DtSim
{
    public sealed record Config(string Strategy, int Assets, double BudgetMs, int Ticks, int Seed,
        int Horizon = 10, double CostFailure = 100, double CostPm = 10, int Burnin = 50, int BatchSamples = 16, int MaxSamples = 2048, double Theta = 0.001);

    // physical world
    const double SigmaW = 0.010, SigmaObs = 0.01, ShockP = 0.003, ShockMul = 2.0;
    readonly double[] _d, _mu, _muBase; readonly bool[] _shocked;
    // twin state
    readonly double[] _L, _b; readonly long[] _last;
    readonly Config _c; readonly IMaterializer<Telemetry20> _m;
    readonly Dictionary<string, object?>[] _payloads; readonly string[] _keys; readonly Type[] _types;
    readonly Random _world;

    public DtSim(Config c)
    {
        _c = c; _m = MaterializerFactory.Create<Telemetry20>(c.Strategy);
        int a = c.Assets; _world = new Random(c.Seed);
        _d = new double[a]; _mu = new double[a]; _muBase = new double[a]; _shocked = new bool[a];
        _L = new double[a]; _b = new double[a]; _last = new long[a];
        for (int i = 0; i < a; i++)
        {
            _d[i] = _world.NextDouble() * 0.6;
            _muBase[i] = _mu[i] = Math.Exp(Math.Log(0.004) + 0.35 * Gauss(_world));
            _L[i] = _d[i]; _b[i] = 0.004; _last[i] = -1;
        }
        var props = typeof(Telemetry20).GetProperties();
        _keys = props.Select(p => p.Name).ToArray(); _types = props.Select(p => p.PropertyType).ToArray();
        _payloads = new Dictionary<string, object?>[a];
        for (int i = 0; i < a; i++) _payloads[i] = Payloads.Create<Telemetry20>(_world, i, 0);
    }

    static double Gauss(Random r)
    {
        double u1 = 1.0 - r.NextDouble(), u2 = r.NextDouble();
        return Math.Sqrt(-2.0 * Math.Log(u1)) * Math.Cos(2 * Math.PI * u2);
    }

    void EmitTelemetry(long tick) // transport layer: decoded JSON/MQTT -> boxed dictionary (outside budget)
    {
        for (int i = 0; i < _d.Length; i++)
        {
            var p = _payloads[i];
            for (int k = 0; k < _keys.Length; k++) p[_keys[k]] = Payloads.Sample(_types[k], _world);
            p["AssetId"] = i; p["Tick"] = tick; p["Running"] = true;
            p["Vibration"] = _d[i] + SigmaObs * Gauss(_world);
            p["Temperature"] = 40.0 + 30.0 * _d[i] + 0.5 * Gauss(_world);
        }
    }

    void UpdateTwin(Telemetry20 s)
    {
        int i = s.AssetId; const double alpha = 0.4, beta = 0.1;
        long gap = _last[i] < 0 ? 1 : s.Tick - _last[i];
        double pred = _L[i] + gap * _b[i];
        double L = alpha * s.Vibration + (1 - alpha) * pred;
        double b = beta * (L - _L[i]) / gap + (1 - beta) * _b[i];
        _L[i] = L; _b[i] = Math.Max(b, 1e-5); _last[i] = s.Tick;
    }

    // fast RNG for Monte Carlo
    ulong _s = 0x9E3779B97F4A7C15UL;
    int _cursor;
    double U() { _s ^= _s << 13; _s ^= _s >> 7; _s ^= _s << 17; return (_s >> 11) * (1.0 / 9007199254740992.0); }
    double N() { double u1 = 1.0 - U(), u2 = U(); return Math.Sqrt(-2.0 * Math.Log(u1)) * Math.Cos(2 * Math.PI * u2); }

    int SimulateHits(double L, double b, int H, int k)
    {
        int hits = 0;
        for (int j = 0; j < k; j++)
        {
            double x = L + 0.008 * N(), slope = Math.Max(1e-5, b + 0.0015 * N());
            bool shocked = false; // as in the physical process: at most one regime shift (drift doubling) before reset
            for (int h = 0; h < H; h++)
            {
                if (U() < ShockP && !shocked) { slope *= ShockMul; shocked = true; }
                x += slope + SigmaW * N();
                if (x >= 1.0) { hits++; break; }
            }
        }
        return hits;
    }

    public string Run()
    {
        int A = _c.Assets, H = _c.Horizon;
        int capacity = Math.Max(1, A / 100);
        double theta = double.TryParse(Environment.GetEnvironmentVariable("DT_THETA"), System.Globalization.NumberStyles.Float, CultureInfo.InvariantCulture, out var th) ? th : _c.Theta;
        long budgetTicks = (long)(_c.BudgetMs * Stopwatch.Frequency / 1000.0);
        // optional cap on samples per candidate (analysis-depth ablation): DT_KMAX
        int maxS = int.TryParse(Environment.GetEnvironmentVariable("DT_KMAX"), out var km) && km > 0 ? km : _c.MaxSamples;
        int batch = Math.Min(_c.BatchSamples, maxS);
        // the whole cycle (sync + screening + what-if + decision) is budgeted: time for screening and decision is reserved
        // from an exponentially smoothed estimate of the previous cycles (x1.25 safety factor)
        double scrEst = 0, decEst = 0; var cycleMs = new List<double>(_c.Ticks);
        double sumScrMs = 0, sumDecMs = 0;
        var samples = new int[A]; var hitsArr = new int[A]; var ttf = new double[A];
        var cand = new List<int>(A); var scheduled = new long[A]; // 0 = none, else execution tick (lead time = Horizon)
        double cost = 0; int failures = 0, pms = 0, measured = 0;
        double sumIngestMs = 0, sumSamplesPerCand = 0, sumCand = 0, sumDropped = 0, sumUnscreenedCand = 0;
        int overrunTicks = 0, overrun5 = 0, overrunGc = 0, cyclesGc = 0;
        var sw = new Stopwatch();
        for (long tick = 1; tick <= _c.Ticks; tick++)
        {
            EmitTelemetry(tick);
            _s = (ulong)(_c.Seed * 1_000_003L + tick) | 1UL; // identical MC stream for every strategy
            int gc0 = GC.CollectionCount(0);
            sw.Restart();
            long syncDeadline = budgetTicks - (long)(1.25 * (scrEst + decEst));
            long mcDeadline = budgetTicks - (long)(1.25 * decEst);
            // ---- ingest + materialize + update (budgeted) ----
            int processed = 0;
            // round-robin cursor: under overload the backlog is spread over the fleet (bounded staleness), not starved
            for (int k = 0; k < A; k++)
            {
                if ((k & 63) == 0 && sw.ElapsedTicks >= syncDeadline) break;
                UpdateTwin(_m.Map(_payloads[(_cursor + k) % A])); processed++;
            }
            _cursor = (_cursor + processed) % A;
            double ingestMs = sw.Elapsed.TotalMilliseconds;
            // ---- screening (deterministic time-to-threshold from current twin state) ----
            long tScr0 = sw.ElapsedTicks;
            cand.Clear();
            for (int i = 0; i < A; i++)
            {
                long age = tick - Math.Max(0, _last[i]);
                double Lnow = _L[i] + age * _b[i];
                ttf[i] = (1.0 - Lnow) / _b[i]; samples[i] = 0; hitsArr[i] = 0;
                if (scheduled[i] == 0 && ttf[i] < 3.0 * H) cand.Add(i);
            }
            cand.Sort((x, y) => ttf[x].CompareTo(ttf[y]));
            long tScr = sw.ElapsedTicks - tScr0;
            // ---- anytime what-if Monte Carlo within remaining budget ----
            bool progress = true;
            while (progress && sw.ElapsedTicks < mcDeadline)
            {
                progress = false;
                for (int c = 0; c < cand.Count; c++)
                {
                    if (sw.ElapsedTicks >= mcDeadline) break;
                    int i = cand[c];
                    if (samples[i] >= maxS) continue;
                    long age = tick - Math.Max(0, _last[i]);
                    hitsArr[i] += SimulateHits(_L[i] + age * _b[i], _b[i], H, batch);
                    samples[i] += batch; progress = true;
                }
            }
            long tDec0 = sw.ElapsedTicks;
            // ---- decision: risk-ranked, capacity-limited preventive maintenance ----
            // work orders execute after a lead time of H cycles; p_hat = P(failure before the order executes).
            // assets with MC evidence use p_hat >= theta; assets without evidence fall back to the point forecast TTF <= H
            var chosen = cand
                .Select(i => (i, risk: samples[i] > 0 ? (double)hitsArr[i] / samples[i] : (ttf[i] <= H ? 1.0 : 0.0)))
                .Where(x => x.risk >= theta).OrderByDescending(x => x.risk).Take(capacity).Select(x => x.i).ToList();
            bool count = tick > _c.Burnin;
            foreach (var i in chosen) scheduled[i] = tick + H;
            // decisions are issued here: the cycle latency is measured up to this point
            long tEnd = sw.ElapsedTicks, tDec = tEnd - tDec0;
            scrEst = tick == 1 ? tScr : 0.7 * scrEst + 0.3 * tScr;
            decEst = tick == 1 ? tDec : 0.7 * decEst + 0.3 * tDec;
            if (count)
            {
                double ms = tEnd * 1000.0 / Stopwatch.Frequency; cycleMs.Add(ms);
                if (tEnd > budgetTicks) overrunTicks++;
                if (tEnd > budgetTicks * 1.05) { overrun5++; if (GC.CollectionCount(0) > gc0) overrunGc++; }
                if (GC.CollectionCount(0) > gc0) cyclesGc++;
                sumScrMs += tScr * 1000.0 / Stopwatch.Frequency; sumDecMs += tDec * 1000.0 / Stopwatch.Frequency;
            }
            // ---- physical world evolves one step ----
            for (int i = 0; i < A; i++)
            {
                double uShock = _world.NextDouble();
                if (!_shocked[i] && uShock < ShockP) { _shocked[i] = true; _mu[i] = _muBase[i] * ShockMul; }
                _d[i] += _mu[i] + SigmaW * Gauss(_world);
                if (_d[i] >= 1.0) { ResetAsset(i); scheduled[i] = 0; if (count) { cost += _c.CostFailure; failures++; } }
                else if (scheduled[i] == tick) { ResetAsset(i); scheduled[i] = 0; if (count) { cost += _c.CostPm; pms++; } }
            }
            if (count)
            {
                measured++; sumIngestMs += ingestMs; sumDropped += A - processed;
                int sampled = cand.Count(i => samples[i] > 0);
                sumCand += cand.Count; sumUnscreenedCand += cand.Count - sampled;
                sumSamplesPerCand += cand.Count == 0 ? 0 : cand.Sum(i => (double)samples[i]) / cand.Count;
            }
        }
        double assetTicks = (double)A * measured;
        if (Environment.GetEnvironmentVariable("DT_GCLOG") == "1")
            Console.Error.WriteLine($"GCLOG overrun5={overrun5} overrun5_with_gc={overrunGc} cycles_with_gc={cyclesGc} measured={measured}");
        cycleMs.Sort();
        double Q(double q) => cycleMs.Count == 0 ? double.NaN : cycleMs[Math.Min(cycleMs.Count - 1, (int)Math.Ceiling(q * cycleMs.Count) - 1)];
        string F(double x) => x.ToString("0.#####", CultureInfo.InvariantCulture);
        return string.Join(",", Env.Runtime, _c.Strategy, A, F(_c.BudgetMs), _c.Seed, measured,
            F(1000 * cost / assetTicks), F(1000.0 * failures / assetTicks), F(1000.0 * pms / assetTicks),
            F(sumIngestMs / measured), F(sumIngestMs / measured / _c.BudgetMs), F(sumDropped / measured / A),
            F(sumCand / measured), F(sumUnscreenedCand / Math.Max(1, sumCand)), F(sumSamplesPerCand / measured), F((double)overrunTicks / measured), F((double)overrun5 / measured),
            F(Q(0.95)), F(Q(0.99)), F(Q(1.0)), F(sumScrMs / measured), F(sumDecMs / measured));
    }

    public static string Header => "Runtime,Strategy,Assets,BudgetMs,Seed,Ticks,CostPer1kAssetTicks,FailuresPer1k,PmPer1k,IngestMs,IngestShare,DroppedShare,Candidates,UnsampledCandShare,SamplesPerCand,OverrunShare,Overrun5Share,CycleP95Ms,CycleP99Ms,CycleMaxMs,ScreenMs,DecisionMs";

    void ResetAsset(int i)
    {
        _d[i] = 0.025; _mu[i] = _muBase[i]; _shocked[i] = false;
        _L[i] = 0.025; _b[i] = 0.004;
    }
}
