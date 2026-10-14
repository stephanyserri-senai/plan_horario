"""Fluxo máximo (algoritmo de Dinic) em Python puro.

Mesma interface usada de `ortools.graph.python.max_flow.SimpleMaxFlow`, para
que a análise de gargalos rode na API serverless sem depender do OR-Tools
(que excede o limite de tamanho das funções da Vercel). Os grafos de
gargalos têm poucas centenas de nós, bem dentro da capacidade deste algoritmo.
"""
from collections import deque


class SimpleMaxFlow:
    def __init__(self):
        self._tail: list[int] = []
        self._head: list[int] = []
        self._cap: list[int] = []
        self._flow: list[int] = []
        self._adj: dict[int, list[int]] = {}

    def add_arc_with_capacity(self, tail: int, head: int, capacidade: int) -> int:
        i = len(self._tail)
        self._tail.append(tail)
        self._head.append(head)
        self._cap.append(max(int(capacidade), 0))
        self._flow.append(0)
        self._adj.setdefault(tail, []).append(i)
        self._adj.setdefault(head, []).append(i)
        return i

    def num_arcs(self) -> int:
        return len(self._tail)

    def tail(self, i: int) -> int:
        return self._tail[i]

    def head(self, i: int) -> int:
        return self._head[i]

    def flow(self, i: int) -> int:
        return self._flow[i]

    def _residual(self, i: int, u: int) -> tuple[int, int]:
        """(nó vizinho, capacidade residual) do arco i visto a partir de u."""
        if self._tail[i] == u:
            return self._head[i], self._cap[i] - self._flow[i]
        return self._tail[i], self._flow[i]

    def solve(self, origem: int, destino: int) -> int:
        total = 0
        while True:
            nivel = {origem: 0}
            fila = deque([origem])
            while fila:
                u = fila.popleft()
                for i in self._adj.get(u, []):
                    v, r = self._residual(i, u)
                    if r > 0 and v not in nivel:
                        nivel[v] = nivel[u] + 1
                        fila.append(v)
            if destino not in nivel:
                return total
            ponteiro = {u: 0 for u in self._adj}

            def empurrar(u: int, limite: int) -> int:
                if u == destino:
                    return limite
                arcos = self._adj.get(u, [])
                while ponteiro[u] < len(arcos):
                    i = arcos[ponteiro[u]]
                    v, r = self._residual(i, u)
                    if r > 0 and nivel.get(v) == nivel[u] + 1:
                        f = empurrar(v, min(limite, r))
                        if f > 0:
                            if self._tail[i] == u:
                                self._flow[i] += f
                            else:
                                self._flow[i] -= f
                            return f
                    ponteiro[u] += 1
                return 0

            while True:
                f = empurrar(origem, 1 << 62)
                if f == 0:
                    break
                total += f
