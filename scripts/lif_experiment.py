import argparse
import json

from services.brain.neural import Graph, LIF

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-ms", type=float, default=100)
    parser.add_argument("--seed", type=int, default=783)
    args = parser.parse_args()
    graph = Graph()
    result = LIF(graph).run(args.duration_ms, 150, list(map(int, graph.inputs[:8])), args.seed)
    result["graph_hash"] = graph.manifest["graph_hash"]
    print(json.dumps(result, indent=2))

