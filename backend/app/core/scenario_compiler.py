from __future__ import annotations

from collections import defaultdict

from backend.app.models.scenario import CompileScenarioResponse, ExecutionStep, ScenarioGraph, ScenarioNode


class ScenarioCompileError(ValueError):
    pass


class ScenarioCompiler:
    def compile(self, graph: ScenarioGraph) -> CompileScenarioResponse:
        node_map = {node.id: node for node in graph.nodes}
        if len(node_map) != len(graph.nodes):
            raise ScenarioCompileError("Node IDs must be unique.")

        starts = [n for n in graph.nodes if n.kind == "start"]
        stops = [n for n in graph.nodes if n.kind == "stop"]
        if len(starts) != 1:
            raise ScenarioCompileError("Scenario requires exactly one Start node.")
        if len(stops) != 1:
            raise ScenarioCompileError("Scenario requires exactly one Stop node.")

        outgoing: dict[str, list[str]] = defaultdict(list)
        incoming_count: dict[str, int] = defaultdict(int)
        for edge in graph.edges:
            if edge.source not in node_map or edge.target not in node_map:
                raise ScenarioCompileError("Edge references unknown node.")
            outgoing[edge.source].append(edge.target)
            incoming_count[edge.target] += 1

        for node in graph.nodes:
            if node.kind != "stop" and len(outgoing[node.id]) > 1:
                raise ScenarioCompileError("Sequential v1 allows max 1 outgoing edge per node.")
            if node.kind != "start" and incoming_count[node.id] > 1:
                raise ScenarioCompileError("Sequential v1 allows max 1 incoming edge per node.")

        ordered_nodes = self._walk_linear_path(starts[0].id, stops[0].id, outgoing)
        used = set(ordered_nodes)
        if used != set(node_map):
            missing = sorted(set(node_map) - used)
            raise ScenarioCompileError(f"Disconnected nodes found: {', '.join(missing)}")

        steps: list[ExecutionStep] = []
        for index, node_id in enumerate(ordered_nodes):
            node = node_map[node_id]
            step = self._node_to_step(index, node)
            steps.append(step)

        return CompileScenarioResponse(
            scenario_name=graph.name,
            ordered_node_ids=ordered_nodes,
            steps=steps,
        )

    def _walk_linear_path(self, start_id: str, stop_id: str, outgoing: dict[str, list[str]]) -> list[str]:
        ordered: list[str] = []
        visited: set[str] = set()
        cursor = start_id

        while True:
            if cursor in visited:
                raise ScenarioCompileError("Cycle detected. Sequential v1 does not allow loops.")
            ordered.append(cursor)
            visited.add(cursor)

            if cursor == stop_id:
                break

            next_nodes = outgoing.get(cursor, [])
            if not next_nodes:
                raise ScenarioCompileError("Path ended before Stop node.")
            cursor = next_nodes[0]

        return ordered

    def _node_to_step(self, index: int, node: ScenarioNode) -> ExecutionStep:
        if node.kind in {"start", "stop"}:
            return ExecutionStep(
                index=index,
                node_id=node.id,
                kind="lifecycle",
                description=node.label,
            )

        if node.kind in {"configure", "trigger", "readback"}:
            command = str(node.params.get("command", "")).strip()
            if not command:
                raise ScenarioCompileError(f"Node '{node.id}' requires params.command")
            return ExecutionStep(
                index=index,
                node_id=node.id,
                kind="scpi",
                description=node.label,
                scpi=command,
            )

        if node.kind == "delay":
            delay_ms = int(node.params.get("delay_ms", 1000))
            if delay_ms < 0:
                raise ScenarioCompileError("Delay must be >= 0 ms")
            return ExecutionStep(
                index=index,
                node_id=node.id,
                kind="delay",
                description=node.label,
                delay_ms=delay_ms,
            )

        if node.kind == "assert":
            expression = str(node.params.get("expression", "")).strip()
            if not expression:
                raise ScenarioCompileError(f"Node '{node.id}' requires params.expression")
            return ExecutionStep(
                index=index,
                node_id=node.id,
                kind="assert",
                description=node.label,
                scpi=expression,
            )

        raise ScenarioCompileError(f"Unsupported node kind: {node.kind}")
