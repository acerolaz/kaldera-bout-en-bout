-- C3-3 (EX-D45) : le gestionnaire lance le traitement depuis l'IHM.
-- Cycle de vie : admission (pièces en analyse) → prete (admise, en attente du gestionnaire)
-- → en_cours → terminee | secours. Le worker s'arrête désormais à « prete ».
ALTER TABLE demandes DROP CONSTRAINT demandes_statut_check;
ALTER TABLE demandes ADD CONSTRAINT demandes_statut_check
  CHECK (statut IN ('admission','prete','en_cours','terminee','secours'));

-- Un lot = un lancement depuis E1 (1 ou N dossiers), suivi par E3 (GET /lots/{id}).
CREATE TABLE lots (
  id      bigserial PRIMARY KEY,
  cree_le timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lot_demandes (
  lot_id    bigint NOT NULL REFERENCES lots,
  reference text   NOT NULL REFERENCES demandes,
  PRIMARY KEY (lot_id, reference)
);
