"""Disjoncteur LLM (EX-D33) : trop de replis sur la fenêtre ⇒ repli pour tous, sans appel LLM.

Injecté (jamais global) : un par orchestrateur, partagé par ``traiter_lot`` ; le worker en crée un
pour toute sa vie. Il se referme seul quand les tentatives sortent de la fenêtre.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from time import monotonic

from .etat import Bornes


class Disjoncteur:
    def __init__(
        self,
        taux: float,
        fenetre_s: float,
        minimum: int = 10,  # volume minimal : un échec isolé n'ouvre rien (choix C2c)
        horloge: Callable[[], float] = monotonic,
    ) -> None:
        self.taux, self.fenetre_s, self.minimum, self.horloge = taux, fenetre_s, minimum, horloge
        self._tentatives: deque[tuple[float, bool]] = deque()
        self._verrou = threading.Lock()

    @classmethod
    def depuis(cls, bornes: Bornes) -> Disjoncteur:
        return cls(bornes.taux_repli_disjoncteur, bornes.fenetre_disjoncteur_s)

    def noter(self, repli: bool) -> None:
        """Une tentative LLM réelle et son issue (repli ou non)."""
        with self._verrou:
            self._tentatives.append((self.horloge(), repli))

    def ouvert(self) -> bool:
        with self._verrou:
            limite = self.horloge() - self.fenetre_s
            while self._tentatives and self._tentatives[0][0] <= limite:
                self._tentatives.popleft()
            n = len(self._tentatives)
            replis = sum(repli for _, repli in self._tentatives)
            return n >= self.minimum and replis / n > self.taux
