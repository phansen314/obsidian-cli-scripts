#!/usr/bin/env python3
"""
Vault Link Cycle Detector
Detects cycles in Obsidian vault note links using iterative DFS.
Calls the obsidian CLI directly (same binary the Kotlin MCP server uses).

Usage:
    detect-cycles [--vault <name>]
"""

import argparse
import subprocess
import sys
from typing import Optional


def run_obsidian(args: list[str], vault: Optional[str] = None) -> list[str]:
    cmd = ["obsidian"]
    if vault:
        cmd.append(f"vault={vault}")
    cmd.extend(args)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"error: obsidian CLI failed: {result.stdout.strip() or result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    output = result.stdout.strip()
    if not output:
        return []

    return output.splitlines()


def build_graph(vault: Optional[str]) -> dict[str, list[str]]:
    print("Listing notes...", file=sys.stderr)
    note_names = run_obsidian(["files"], vault)

    print(f"Found {len(note_names)} notes. Fetching links...", file=sys.stderr)

    graph: dict[str, list[str]] = {name: [] for name in note_names}
    note_set = set(note_names)

    for i, note in enumerate(note_names, 1):
        if i % 10 == 0 or i == len(note_names):
            print(f"  {i}/{len(note_names)}", file=sys.stderr)
        targets = run_obsidian(["links", f"path={note}"], vault)
        # Only keep edges to notes that exist in the vault (skip unresolved links)
        graph[note] = [t for t in targets if t in note_set]

    return graph


def find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """
    Iterative DFS with three-color marking.
    Returns a list of cycles, each represented as an ordered list of node names
    forming the cycle (first == last for display purposes, stored without dup here).
    """
    UNVISITED, VISITING, VISITED = 0, 1, 2
    color = {node: UNVISITED for node in graph}
    cycles: list[list[str]] = []
    # Track cycles by their canonical form to avoid duplicates
    seen_cycles: set[frozenset] = set()

    for start in graph:
        if color[start] != UNVISITED:
            continue

        # Each stack frame: (node, iterator-over-neighbors, path-so-far)
        # We use an explicit stack of (node, neighbor_index) pairs plus a path list.
        stack: list[tuple[str, int]] = [(start, 0)]
        path: list[str] = [start]
        path_set: set[str] = {start}
        color[start] = VISITING

        while stack:
            node, idx = stack[-1]
            neighbors = graph[node]

            if idx < len(neighbors):
                stack[-1] = (node, idx + 1)
                neighbor = neighbors[idx]

                if color[neighbor] == VISITING:
                    # Found a back-edge — extract cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:]
                    key = frozenset(cycle)
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        cycles.append(cycle)

                elif color[neighbor] == UNVISITED:
                    color[neighbor] = VISITING
                    path.append(neighbor)
                    path_set.add(neighbor)
                    stack.append((neighbor, 0))

            else:
                # All neighbors processed — backtrack
                color[node] = VISITED
                path.pop()
                path_set.discard(node)
                stack.pop()

    return cycles


def main():
    parser = argparse.ArgumentParser(description="Detect link cycles in an Obsidian vault.")
    parser.add_argument("--vault", metavar="NAME", help="Vault name (optional; uses active vault if omitted)")
    args = parser.parse_args()

    graph = build_graph(args.vault)

    if not graph:
        print("No notes found. Is Obsidian running with the vault registered?")
        sys.exit(0)

    print("Running cycle detection...", file=sys.stderr)
    cycles = find_cycles(graph)

    if not cycles:
        print(f"No cycles found. The vault link graph is a DAG ({len(graph)} notes checked).")
    else:
        print(f"Found {len(cycles)} cycle(s):\n")
        for cycle in cycles:
            # Display as: A → B → C → A
            print("  " + " → ".join(cycle) + " → " + cycle[0])
        print(f"\n{len(cycles)} cycle(s) detected in {len(graph)} notes.")
        sys.exit(2)


if __name__ == "__main__":
    main()
