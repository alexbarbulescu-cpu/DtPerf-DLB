using DtPerf;

// usage:
//   micro <out.csv>
//   cold <P> <strategy>                        (prints one CSV row; run in a fresh process)
//   sim <strategy> <assets> <budgetMs> <ticks> <seed>   (prints one CSV row)
//   env
switch (args.Length > 0 ? args[0] : "env")
{
    case "micro":
        Console.Error.WriteLine(Env.Describe());
        var rows = MicroBenches.RunAll();
        File.WriteAllLines(args[1], new[] { BenchResult.Header }.Concat(rows.Select(r => r.ToCsv())));
        break;
    case "micro20": // P = 20 materialization only (used for repeated fresh-process runs)
        File.WriteAllLines(args[1], new[] { BenchResult.Header }.Concat(MicroBenches.Materialization20().Select(r => r.ToCsv())));
        break;
    case "microctl":
        File.WriteAllLines(args[1], new[] { BenchResult.Header }.Concat(MicroBenches.Control().Select(r => r.ToCsv())));
        break;
    case "verify":
        Console.WriteLine(MicroBenches.Verify());
        break;
    case "mcbench":
        Console.WriteLine(DtSim.McBench(args.Length > 1 ? int.Parse(args[1]) : 2_000_000));
        break;
    case "cold":
        Console.WriteLine(MicroBenches.Cold(int.Parse(args[1]), args[2]));
        break;
    case "sim":
        var c = new DtSim.Config(args[1], int.Parse(args[2]), double.Parse(args[3], System.Globalization.CultureInfo.InvariantCulture), int.Parse(args[4]), int.Parse(args[5]));
        Console.WriteLine(new DtSim(c).Run());
        break;
    default:
        Console.WriteLine(Env.Describe());
        break;
}
